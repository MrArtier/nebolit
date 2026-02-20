# -*- coding: utf-8 -*-
import os
import logging
import asyncio
import io
import re
import tempfile
import base64
import psycopg2
from flask import Flask, request

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask
app = Flask(__name__)

# --- КОНФИГИ (загружаем лениво) ---

def get_config():
    return {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
        "TELEGRAM_TOKEN": os.getenv("TELEGRAM_TOKEN", ""),
        "DB_NAME": os.getenv("DB_NAME", ""),
        "DB_USER": os.getenv("DB_USER", ""),
        "DB_PASS": os.getenv("DB_PASS", ""),
        "INSTANCE_CONNECTION_NAME": os.getenv("INSTANCE_CONNECTION_NAME", ""),
        "DB_HOST": os.getenv("DB_HOST", ""),
    }

# --- ПОДКЛЮЧЕНИЕ К БАЗЕ ---

def get_db_connection():
    cfg = get_config()
    try:
        if cfg["INSTANCE_CONNECTION_NAME"]:
            return psycopg2.connect(
                host=f"/cloudsql/{cfg['INSTANCE_CONNECTION_NAME']}",
                database=cfg["DB_NAME"],
                user=cfg["DB_USER"],
                password=cfg["DB_PASS"],
                connect_timeout=10
            )
        return psycopg2.connect(
            host=cfg["DB_HOST"],
            database=cfg["DB_NAME"],
            user=cfg["DB_USER"],
            password=cfg["DB_PASS"],
            connect_timeout=10
        )
    except Exception as e:
        logger.error(f"DATABASE CONNECTION ERROR: {e}")
        return None

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ---

def init_db():
    conn = get_db_connection()
    if not conn:
        logger.error("Cannot connect to DB during init")
        return
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                medicine_name TEXT NOT NULL,
                quantity INTEGER DEFAULT 1,
                dosage TEXT,
                expiry_date DATE,
                category TEXT,
                target_group TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS family (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                name TEXT NOT NULL,
                age INTEGER,
                gender TEXT,
                relation TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                family_member TEXT,
                medicine_name TEXT NOT NULL,
                schedule TEXT NOT NULL,
                dosage TEXT,
                start_date DATE,
                end_date DATE,
                active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Init DB error: {e}")
    finally:
        conn.close()

# --- РАБОТА С БАЗОЙ ---

def save_user(user_id, username):
    conn = get_db_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET username = %s",
            (user_id, username, username)
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Save user error: {e}")
    finally:
        conn.close()

def save_message(user_id, role, content):
    conn = get_db_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (user_id, role, content) VALUES (%s, %s, %s)",
            (user_id, role, content)
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Save message error: {e}")
    finally:
        conn.close()

def get_user_history(user_id, limit=20):
    conn = get_db_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, content FROM messages WHERE user_id = %s ORDER BY timestamp DESC LIMIT %s",
            (user_id, limit)
        )
        rows = cursor.fetchall()
        rows.reverse()
        return [{"role": r[0], "content": r[1]} for r in rows]
    except Exception as e:
        logger.error(f"Get history error: {e}")
        return []
    finally:
        conn.close()

def get_user_inventory(user_id):
    conn = get_db_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT medicine_name, quantity, dosage, expiry_date, category, notes FROM inventory WHERE user_id = %s ORDER BY medicine_name",
            (user_id,)
        )
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Get inventory error: {e}")
        return []
    finally:
        conn.close()

def get_user_family(user_id):
    conn = get_db_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, age, gender, relation FROM family WHERE user_id = %s",
            (user_id,)
        )
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Get family error: {e}")
        return []
    finally:
        conn.close()

# --- РАСПОЗНАВАНИЕ ГОЛОСА (Whisper) ---

def process_voice(voice_bytes):
    from openai import OpenAI
    cfg = get_config()
    client = OpenAI(api_key=cfg["OPENAI_API_KEY"])
    try:
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp.write(voice_bytes)
            tmp_path = tmp.name
        with open(tmp_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ru"
            )
        os.unlink(tmp_path)
        return transcript.text.strip()
    except Exception as e:
        logger.error(f"Whisper Error: {e}")
        return ""

# --- РАСПОЗНАВАНИЕ ФОТО (GPT Vision) ---

def process_photo_vision(photo_bytes):
    from openai import OpenAI
    cfg = get_config()
    client = OpenAI(api_key=cfg["OPENAI_API_KEY"])
    try:
        b64 = base64.b64encode(photo_bytes).decode("utf-8")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "На фото — упаковка лекарства. Определи:\n"
                                "1. Название лекарства\n"
                                "2. Действующее вещество\n"
                                "3. Дозировка\n"
                                "4. Срок годности (если виден)\n"
                                "5. Показания к применению\n"
                                "6. Категория (обезболивающее, жаропонижающее, антибиотик и т.д.)\n"
                                "Ответь кратко и структурированно."
                            )
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Vision Error: {e}")
        return ""

# --- РАСПОЗНАВАНИЕ ФОТО (OCR fallback) ---

def process_photo_ocr(photo_bytes):
    try:
        from PIL import Image
        import pytesseract
        img = Image.open(io.BytesIO(photo_bytes))
        text = pytesseract.image_to_string(img, lang='rus+eng')
        return text.strip()
    except Exception as e:
        logger.error(f"OCR Error: {e}")
        return ""

# --- СИСТЕМНЫЙ ПРОМПТ ---

SYSTEM_PROMPT = """Ты — умный помощник по домашней аптечке. Тебя зовут «Аптечка-бот».

Твои задачи:
1. Хранить список лекарств пользователя (название, количество, дозировка, срок годности, категория).
2. Подсказывать, какое лекарство принять при недомогании, в какой дозировке по инструкции.
3. Учитывать состав семьи (взрослые, дети, мужчины, женщины) при рекомендациях.
4. Предлагать пополнить аптечку, если чего-то не хватает.
5. Собирать мини-аптечку для сценариев (поездка на море, дача, поход и т.д.).
6. Следить за сроками годности и напоминать о просроченных.
7. Создавать напоминания о приёме лекарств по назначению врача.

ВАЖНЫЕ ПРАВИЛА:
- Когда пользователь добавляет лекарство (текстом, голосом или фото), ответь подтверждением и ОБЯЗАТЕЛЬНО включи команду [ADD_MEDICINE: ...].
- Если пользователь спрашивает, что принять — рекомендуй ТОЛЬКО из его аптечки. Если нужного нет — скажи, что стоит купить.
- Всегда предупреждай: «Это не замена консультации врача».
- Отвечай на русском, кратко и по делу.
- Если пользователь присылает фото упаковки, помоги определить лекарство и предложи добавить в аптечку.
- Если пользователь просит напоминание — уточни: какое лекарство, кому, в какое время, сколько дней.

Для управления данными используй специальные команды в ответе:
- Добавить лекарство: [ADD_MEDICINE: название | количество | дозировка | срок_годности_ГГГГ-ММ-ДД | категория]
- Удалить лекарство: [REMOVE_MEDICINE: название]
- Добавить члена семьи: [ADD_FAMILY: имя | возраст | пол | отношение]
- Создать напоминание: [ADD_REMINDER: член_семьи | лекарство | расписание | дозировка | дата_начала | дата_окончания]
"""

# --- GPT ОТВЕТ ---

def generate_gpt_response(user_id, user_text):
    from openai import OpenAI
    cfg = get_config()
    client = OpenAI(api_key=cfg["OPENAI_API_KEY"])

    history = get_user_history(user_id, limit=20)
    inventory = get_user_inventory(user_id)
    family = get_user_family(user_id)

    if inventory:
        inv_lines = []
        for med in inventory:
            line = f"- {med[0]}, кол-во: {med[1]}, дозировка: {med[2] or '?'}, годен до: {med[3] or '?'}, категория: {med[4] or '?'}"
            inv_lines.append(line)
        inv_text = "\n".join(inv_lines)
    else:
        inv_text = "Аптечка пуста."

    if family:
        fam_lines = []
        for f in family:
            fam_lines.append(f"- {f[0]}, возраст: {f[1]}, пол: {f[2]}, кто: {f[3]}")
        fam_text = "\n".join(fam_lines)
    else:
        fam_text = "Состав семьи не указан."

    context_message = f"Текущая аптечка пользователя:\n{inv_text}\n\nСостав семьи:\n{fam_text}"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": context_message}
    ]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=1000,
            temperature=0.7
        )
        reply = response.choices[0].message.content
        process_gpt_commands(user_id, reply)
        clean_reply = clean_commands(reply)
        return clean_reply
    except Exception as e:
        logger.error(f"GPT Error: {e}")
        return "⚠️ Ошибка связи с ИИ. Попробуй ещё раз."

# --- ОБРАБОТКА КОМАНД GPT ---

def process_gpt_commands(user_id, text):
    conn = get_db_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()

        add_med = re.findall(r'
\[ADD_MEDICINE:\s*(.+?)\]', text)
        for med in add_med:
            parts = [p.strip() for p in med.split('|')]
            name = parts[0] if len(parts) > 0 else ""
            qty = parts[1] if len(parts) > 1 else "1"
            dosage = parts[2] if len(parts) > 2 else None
            expiry = parts[3] if len(parts) > 3 else None
            category = parts[4] if len(parts) > 4 else None
            try:
                qty_int = int(qty)
            except ValueError:
                qty_int = 1
            if expiry:
                try:
                    from datetime import datetime
                    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%m/%Y', '%d/%m/%Y'):
                        try:
                            parsed = datetime.strptime(expiry, fmt)
                            expiry = parsed.strftime('%Y-%m-%d')
                            break
                        except ValueError:
                            continue
                    else:
                        expiry = None
                except Exception:
                    expiry = None
            if name:
                cursor.execute(
                    "INSERT INTO inventory (user_id, medicine_name, quantity, dosage, expiry_date, category) VALUES (%s, %s, %s, %s, %s, %s)",
                    (user_id, name, qty_int, dosage, expiry, category)
                )

        rem_med = re.findall(r'
\[REMOVE_MEDICINE:\s*(.+?)\]', text)
        for name in rem_med:
            cursor.execute(
                "DELETE FROM inventory WHERE user_id = %s AND LOWER(medicine_name) = LOWER(%s)",
                (user_id, name.strip())
            )

        add_fam = re.findall(r'
\[ADD_FAMILY:\s*(.+?)\]', text)
        for fam in add_fam:
            parts = [p.strip() for p in fam.split('|')]
            name = parts[0] if len(parts) > 0 else ""
            age = parts[1] if len(parts) > 1 else None
            gender = parts[2] if len(parts) > 2 else None
            relation = parts[3] if len(parts) > 3 else None
            try:
                age_int = int(age) if age else None
            except ValueError:
                age_int = None
            if name:
                cursor.execute(
                    "INSERT INTO family (user_id, name, age, gender, relation) VALUES (%s, %s, %s, %s, %s)",
                    (user_id, name, age_int, gender, relation)
                )

        add_rem = re.findall(r'
\[ADD_REMINDER:\s*(.+?)\]', text)
        for rem in add_rem:
            parts = [p.strip() for p in rem.split('|')]
            member = parts[0] if len(parts) > 0 else None
            medicine = parts[1] if len(parts) > 1 else ""
            schedule = parts[2] if len(parts) > 2 else ""
            dosage = parts[3] if len(parts) > 3 else None
            start_date = parts[4] if len(parts) > 4 else None
            end_date = parts[5] if len(parts) > 5 else None
            if medicine and schedule:
                cursor.execute(
                    "INSERT INTO reminders (user_id, family_member, medicine_name, schedule, dosage, start_date, end_date) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (user_id, member, medicine, schedule, dosage, start_date, end_date)
                )

        conn.commit()
    except Exception as e:
        logger.error(f"Process commands error: {e}")
    finally:
        conn.close()

def clean_commands(text):
    text = re.sub(r'
\[ADD_MEDICINE:\s*.+?\]', '', text)
    text = re.sub(r'
\[REMOVE_MEDICINE:\s*.+?\]', '', text)
    text = re.sub(r'
\[ADD_FAMILY:\s*.+?\]', '', text)
    text = re.sub(r'
\[ADD_REMINDER:\s*.+?\]', '', text)
    return text.strip()

# --- TELEGRAM API (без библиотеки, чистые HTTP-запросы) ---

import urllib.request
import json

def tg_api(method, data=None):
    cfg = get_config()
    url = f"https://api.telegram.org/bot{cfg['TELEGRAM_TOKEN']}/{method}"
    if data:
        req_data = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error(f"Telegram API error: {e}")
        return None

def tg_send_message(chat_id, text, parse_mode=None):
    data = {"chat_id": chat_id, "text": text}
    if parse_mode:
        data["parse_mode"] = parse_mode
    return tg_api("sendMessage", data)

def tg_get_file(file_id):
    result = tg_api("getFile", {"file_id": file_id})
    if result and result.get("ok"):
        file_path = result["result"]["file_path"]
        cfg = get_config()
        file_url = f"https://api.telegram.org/file/bot{cfg['TELEGRAM_TOKEN']}/{file_path}"
        req = urllib.request.Request(file_url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    return None

# --- ОБРАБОТКА ВХОДЯЩИХ СООБЩЕНИЙ ---

def handle_update(update_data):
    message = update_data.get("message")
    if not message:
        return

    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    username = message["from"].get("username") or message["from"].get("first_name") or ""

    save_user(user_id, username)

    user_text = ""

    # --- Голосовое сообщение ---
    if "voice" in message:
        file_id = message["voice"]["file_id"]
        voice_bytes = tg_get_file(file_id)
        if voice_bytes:
            transcribed = process_voice(voice_bytes)
            if transcribed:
                user_text = transcribed
                tg_send_message(chat_id, f"🎤 Распознано: {transcribed}")
            else:
                tg_send_message(chat_id, "⚠️ Не удалось распознать голос. Попробуй ещё раз.")
                return
        else:
            tg_send_message(chat_id, "⚠️ Не удалось скачать голосовое сообщение.")
            return

    # --- Фото ---
    elif "photo" in message:
        photo = message["photo"][-1]
        file_id = photo["file_id"]
        photo_bytes = tg_get_file(file_id)

        if photo_bytes:
            tg_send_message(chat_id, "📷 Анализирую фото...")
            vision_text = process_photo_vision(photo_bytes)
            if vision_text:
                caption = message.get("caption", "")
                user_text = f"Я сфотографировал упаковку лекарства. Вот что на фото:\n{vision_text}"
                if caption:
                    user_text += f"\nМой комментарий: {caption}"
            else:
                ocr_text = process_photo_ocr(photo_bytes)
                if ocr_text:
                    user_text = f"Я сфотографировал упаковку лекарства. Распознанный текст: {ocr_text}"
                else:
                    tg_send_message(chat_id, "⚠️ Не удалось распознать фото. Попробуй сделать снимок чётче.")
                    return
        else:
            tg_send_message(chat_id, "⚠️ Не удалось скачать фото.")
            return

    # --- Текст ---
    elif "text" in message:
        user_text = message["text"]

        if user_text.strip() == "/start":
            welcome = (
                "👋 Привет! Я — Аптечка-бот.\n\n"
                "Я помогу тебе:\n"
                "💊 Вести список лекарств в аптечке\n"
                "🔍 Подсказать, что принять при недомогании\n"
                "📷 Распознать лекарство по фото упаковки\n"
                "🎤 Принять голосовые сообщения\n"
                "👨‍👩‍👧‍👦 Учитывать членов семьи\n"
                "⏰ Напоминать о приёме лекарств\n"
                "📅 Следить за сроками годности\n"
                "🧳 Собрать аптечку для поездки\n\n"
                "Просто напиши, что у тебя есть в аптечке, или задай вопрос!"
            )
            tg_send_message(chat_id, welcome)
            return

        if user_text.strip() == "/inventory":
            inventory = get_user_inventory(user_id)
            if inventory:
                lines = ["📦 Твоя аптечка:\n"]
                for i, med in enumerate(inventory, 1):
                    exp = f", годен до {med[3]}" if med[3] else ""
                    lines.append(f"{i}. {med[0]} — {med[1]} шт., {med[2] or 'дозировка не указана'}{exp}")
                tg_send_message(chat_id, "\n".join(lines))
            else:
                tg_send_message(chat_id, "📦 Аптечка пуста. Отправь фото лекарства или напиши, что у тебя есть!")
            return

        if user_text.strip() == "/family":
            family = get_user_family(user_id)
            if family:
                lines = ["👨‍👩‍👧‍👦 Состав семьи:\n"]
                for f in family:
                    lines.append(f"- {f[0]}, {f[1]} лет, {f[2]}, {f[3]}")
                tg_send_message(chat_id, "\n".join(lines))
            else:
                tg_send_message(chat_id, "👨‍👩‍👧‍👦 Семья не указана. Напиши, кто в твоей семье!")
            return
    else:
        return

    # Сохраняем и генерируем ответ
    save_message(user_id, "user", user_text)
    reply = generate_gpt_response(user_id, user_text)
    save_message(user_id, "assistant", reply)
    tg_send_message(chat_id, reply)

# --- WEBHOOK ---

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        update_data = request.get_json(force=True)
        logger.info(f"Received update: {json.dumps(update_data, ensure_ascii=False)[:200]}")
        handle_update(update_data)
        return "OK", 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "OK", 200

@app.route("/", methods=["GET"])
def index():
    return "Pharmacy Bot is running!", 200

# --- ЗАПУСК ---

try:
    init_db()
except Exception as e:
    logger.error(f"Init DB failed: {e}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)