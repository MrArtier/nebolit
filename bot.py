# -*- coding: utf-8 -*-
import os
import logging
import datetime
import sqlite3
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from openai import OpenAI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# ==============================
# НАСТРОЙКА
# ==============================
logging.basicConfig(level=logging.INFO)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # URL Cloud Run

if not OPENAI_API_KEY or not TELEGRAM_TOKEN or not WEBHOOK_URL:
    raise ValueError("❌ Не найдены ключи OPENAI_API_KEY, TELEGRAM_TOKEN или WEBHOOK_URL")

client = OpenAI(api_key=OPENAI_API_KEY)
MAX_HISTORY = 50

# ==============================
# БАЗА ДАННЫХ
# ==============================
conn = sqlite3.connect("pharmacy_bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    created_at TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    role TEXT,
    content TEXT,
    timestamp TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    medicine_name TEXT,
    quantity INTEGER,
    dosage TEXT,
    expiry_date TEXT,
    category TEXT,
    target_group TEXT
)
""")
conn.commit()

# ==============================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================
def get_user_history(user_id):
    cursor.execute(
        "SELECT role, content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, MAX_HISTORY)
    )
    rows = cursor.fetchall()
    rows.reverse()
    return [{"role": role, "content": content} for role, content in rows]

def save_message(user_id, role, content):
    cursor.execute(
        "INSERT INTO messages (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (user_id, role, content, str(datetime.datetime.now()))
    )
    conn.commit()

def add_or_update_medicine(user_id, name, quantity=1, dosage="", expiry="", category="", target=""):
    cursor.execute(
        "SELECT id, quantity FROM inventory WHERE user_id=? AND medicine_name=? AND dosage=? AND category=? AND target_group=?",
        (user_id, name, dosage, category, target)
    )
    row = cursor.fetchone()
    if row:
        med_id, old_qty = row
        cursor.execute(
            "UPDATE inventory SET quantity=?, expiry_date=? WHERE id=?",
            (old_qty + quantity, expiry, med_id)
        )
    else:
        cursor.execute(
            "INSERT INTO inventory (user_id, medicine_name, quantity, dosage, expiry_date, category, target_group) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, name, quantity, dosage, expiry, category, target)
        )
    conn.commit()

def get_inventory(user_id):
    cursor.execute(
        "SELECT medicine_name, quantity, dosage, expiry_date, category, target_group FROM inventory WHERE user_id=?",
        (user_id,)
    )
    rows = cursor.fetchall()
    meds = []
    for name, qty, dosage, expiry, cat, group in rows:
        meds.append({
            "name": name,
            "quantity": qty,
            "dosage": dosage,
            "expiry_date": expiry,
            "category": cat or "Без категории",
            "target_group": group or "-"
        })
    return meds

# ==============================
# GPT RESPONSE
# ==============================
async def generate_gpt_response(user_id, user_text):
    history = get_user_history(user_id)
    messages = [{
        "role": "system",
        "content": "Ты профессиональный ИИ-ассистент по домашней аптечке. "
                   "Даёшь рекомендации по приёму лекарств и контролю сроков годности. "
                   "Всегда предупреждай: 'Не занимайтесь самолечением, при необходимости обратитесь к врачу.'"
    }]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})
    try:
        response = client.chat.completions.create(model="gpt-4o-mini", messages=messages)
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"Ошибка OpenAI: {e}")
        return "⚠️ Ошибка при обращении к ИИ. Попробуйте позже."

# ==============================
# ОБРАБОТКА СООБЩЕНИЙ
# ==============================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.message.from_user
        user_id = user.id
        user_text = update.message.text
        if not user_text:
            return

        # регистрация
        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username, created_at) VALUES (?, ?, ?)",
            (user_id, user.username, str(datetime.datetime.now()))
        )
        conn.commit()
        save_message(user_id, "user", user_text)

        # добавление лекарства
        if user_text.lower().startswith("добавь"):
            try:
                parts = user_text[6:].split(",")
                med_name = parts[0].strip()
                quantity = int(parts[1].strip())
                dosage = parts[2].strip() if len(parts) > 2 else ""
                expiry = parts[3].strip() if len(parts) > 3 else ""
                category = parts[4].strip() if len(parts) > 4 else ""
                target = parts[5].strip() if len(parts) > 5 else ""
                add_or_update_medicine(user_id, med_name, quantity, dosage, expiry, category, target)
                reply = f"✅ Лекарство '{med_name}' добавлено/обновлено."
            except Exception:
                reply = "⚠️ Формат:\nДобавь Название, Кол-во, Дозировка, ГГГГ-ММ-ДД, Категория, Целевая группа"
        elif user_text.lower() in ["аптечка", "сводка"]:
            meds = get_inventory(user_id)
            if not meds:
                reply = "Аптечка пуста."
            else:
                reply = "📋 Содержимое аптечки:\n"
                for m in meds:
                    reply += f"\n• {m['name']} — {m['quantity']} шт ({m['dosage']}, до {m['expiry_date']})"
        else:
            reply = await generate_gpt_response(user_id, user_text)

        save_message(user_id, "assistant", reply)
        await update.message.reply_text(reply)
    except Exception as e:
        logging.error(f"Ошибка handle_message: {e}")
        await update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")

# ==============================
# ПЛАНИРОВЩИК
# ==============================
async def monthly_check(app):
    logging.info("Проверка просроченных лекарств запущена")

async def post_init(application):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(monthly_check, 'cron', day=3, hour=9, args=[application])
    scheduler.start()
    logging.info("Планировщик запущен")

# ==============================
# ЗАПУСК
# ==============================

import threading

loop = asyncio.new_event_loop()

def start_loop():
    asyncio.set_event_loop(loop)
    loop.run_until_complete(application.initialize())
    loop.run_until_complete(application.start())

    if WEBHOOK_URL:
        loop.run_until_complete(application.bot.set_webhook(WEBHOOK_URL))

    loop.run_forever()


if __name__ == "__main__":
    t = threading.Thread(target=start_loop, daemon=True)
    t.start()

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ==============================
# ЗАПУСК
# ==============================
if __name__ == "__main__":
    loop.run_until_complete(application.initialize())
    loop.run_until_complete(application.start())

    if WEBHOOK_URL:
        loop.run_until_complete(application.bot.set_webhook(WEBHOOK_URL))

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
