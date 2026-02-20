import os
import logging
import io
import re
import tempfile
import base64
import json
import urllib.request
import psycopg2
from flask import Flask, request as flask_request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

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

def get_db_connection():
    cfg = get_config()
    try:
        if cfg["INSTANCE_CONNECTION_NAME"]:
            return psycopg2.connect(host="/cloudsql/" + cfg["INSTANCE_CONNECTION_NAME"], database=cfg["DB_NAME"], user=cfg["DB_USER"], password=cfg["DB_PASS"], connect_timeout=10)
        return psycopg2.connect(host=cfg["DB_HOST"], database=cfg["DB_NAME"], user=cfg["DB_USER"], password=cfg["DB_PASS"], connect_timeout=10)
    except Exception as e:
        logger.error("DB CONNECTION ERROR: %s", e)
        return None

def init_db():
    conn = get_db_connection()
    if not conn:
        logger.error("Cannot connect to DB during init")
        return
    try:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS messages (id SERIAL PRIMARY KEY, user_id BIGINT REFERENCES users(user_id), role TEXT NOT NULL, content TEXT NOT NULL, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS inventory (id SERIAL PRIMARY KEY, user_id BIGINT REFERENCES users(user_id), medicine_name TEXT NOT NULL, quantity INTEGER DEFAULT 1, dosage TEXT, expiry_date DATE, category TEXT, target_group TEXT, notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS family (id SERIAL PRIMARY KEY, user_id BIGINT REFERENCES users(user_id), name TEXT NOT NULL, age INTEGER, gender TEXT, relation TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS reminders (id SERIAL PRIMARY KEY, user_id BIGINT REFERENCES users(user_id), family_member TEXT, medicine_name TEXT NOT NULL, schedule TEXT NOT NULL, dosage TEXT, start_date DATE, end_date DATE, active BOOLEAN DEFAULT TRUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.commit()
        logger.info("DB initialized OK")
    except Exception as e:
        logger.error("Init DB error: %s", e)
    finally:
        conn.close()

def save_user(uid, uname):
    conn = get_db_connection()
    if not conn:
        return
    try:
        c = conn.cursor()
        c.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET username = %s", (uid, uname, uname))
        conn.commit()
    except Exception as e:
        logger.error("Save user error: %s", e)
    finally:
        conn.close()

def save_message(uid, role, content):
    conn = get_db_connection()
    if not conn:
        return
    try:
        c = conn.cursor()
        c.execute("INSERT INTO messages (user_id, role, content) VALUES (%s, %s, %s)", (uid, role, content))
        conn.commit()
    except Exception as e:
        logger.error("Save msg error: %s", e)
    finally:
        conn.close()

def get_user_history(uid, limit=20):
    conn = get_db_connection()
    if not conn:
        return []
    try:
        c = conn.cursor()
        c.execute("SELECT role, content FROM messages WHERE user_id = %s ORDER BY timestamp DESC LIMIT %s", (uid, limit))
        rows = c.fetchall()
        rows.reverse()
        return [{"role": r[0], "content": r[1]} for r in rows]
    except Exception as e:
        logger.error("Get history error: %s", e)
        return []
    finally:
        conn.close()

def get_user_inventory(uid):
    conn = get_db_connection()
    if not conn:
        return []
    try:
        c = conn.cursor()
        c.execute("SELECT medicine_name, quantity, dosage, expiry_date, category, notes FROM inventory WHERE user_id = %s ORDER BY medicine_name", (uid,))
        return c.fetchall()
    except Exception as e:
        logger.error("Get inv error: %s", e)
        return []
    finally:
        conn.close()

def get_user_family(uid):
    conn = get_db_connection()
    if not conn:
        return []
    try:
        c = conn.cursor()
        c.execute("SELECT name, age, gender, relation FROM family WHERE user_id = %s", (uid,))
        return c.fetchall()
    except Exception as e:
        logger.error("Get family error: %s", e)
        return []
    finally:
        conn.close()
        def process_voice(voice_bytes):
    from openai import OpenAI
    cfg = get_config()
    client = OpenAI(api_key=cfg["OPENAI_API_KEY"])
    try:
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp.write(voice_bytes)
            tmp_path = tmp.name
        with open(tmp_path, "rb") as af:
            transcript = client.audio.transcriptions.create(model="whisper-1", file=af, language="ru")
        os.unlink(tmp_path)
        return transcript.text.strip()
    except Exception as e:
        logger.error("Whisper Error: %s", e)
        return ""

def process_photo_vision(photo_bytes):
    from openai import OpenAI
    cfg = get_config()
    client = OpenAI(api_key=cfg["OPENAI_API_KEY"])
    try:
        b64 = base64.b64encode(photo_bytes).decode("utf-8")
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": [{"type": "text", "text": "На фото упаковка лекарства. Определи: 1) Название 2) Действующее вещество 3) Дозировка 4) Срок годности 5) Показания 6) Категория. Ответь кратко."}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}]}], max_tokens=500)
        return resp.choices[0].message.content
    except Exception as e:
        logger.error("Vision Error: %s", e)
        return ""

def process_photo_ocr(photo_bytes):
    try:
        from PIL import Image
        import pytesseract
        img = Image.open(io.BytesIO(photo_bytes))
        text = pytesseract.image_to_string(img, lang="rus+eng")
        return text.strip()
    except Exception as e:
        logger.error("OCR Error: %s", e)
        return ""

SYSTEM_PROMPT = "Ты — умный помощник по домашней аптечке. Тебя зовут Аптечка-бот. Задачи: 1) Хранить список лекарств (название, количество, дозировка, срок годности, категория). 2) Подсказывать какое лекарство принять при недомогании. 3) Учитывать состав семьи. 4) Предлагать пополнить аптечку. 5) Собирать мини-аптечку для поездок. 6) Следить за сроками годности. 7) Напоминания о приёме. Правила: рекомендуй ТОЛЬКО из аптечки пользователя. Если нужного нет — скажи купить. Предупреждай что это не замена врачу. Отвечай на русском кратко. Для управления данными используй команды: [ADD_MEDICINE: название | количество | дозировка | срок_годности | категория] [REMOVE_MEDICINE: название] [ADD_FAMILY: имя | возраст | пол | отношение] [ADD_REMINDER: член_семьи | лекарство | расписание | дозировка | начало | конец]"

def generate_gpt_response(uid, user_text):
    from openai import OpenAI
    cfg = get_config()
    client = OpenAI(api_key=cfg["OPENAI_API_KEY"])
    history = get_user_history(uid, limit=20)
    inventory = get_user_inventory(uid)
    family = get_user_family(uid)
    inv_text = "Аптечка пуста."
    if inventory:
        lines = []
        for m in inventory:
            lines.append("- %s, кол-во: %s, дозировка: %s, годен до: %s, категория: %s" % (m[0], m[1], m[2] or "?", m[3] or "?", m[4] or "?"))
        inv_text = "\n".join(lines)
    fam_text = "Состав семьи не указан."
    if family:
        lines = []
        for f in family:
            lines.append("- %s, возраст: %s, пол: %s, кто: %s" % (f[0], f[1], f[2], f[3]))
        fam_text = "\n".join(lines)
    ctx = "Текущая аптечка:\n" + inv_text + "\n\nСостав семьи:\n" + fam_text
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "system", "content": ctx}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})
    try:
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=messages, max_tokens=1000, temperature=0.7)
        reply = resp.choices[0].message.content
        process_gpt_commands(uid, reply)
        return clean_commands(reply)
    except Exception as e:
        logger.error("GPT Error: %s", e)
        return "Ошибка связи с ИИ. Попробуй ещё раз."

def process_gpt_commands(uid, text):
    conn = get_db_connection()
    if not conn:
        return
    try:
        c = conn.cursor()
        for med in re.findall(r"
\[ADD_MEDICINE:\s*(.+?)\]", text):
            parts = [p.strip() for p in med.split("|")]
            name = parts[0] if len(parts) > 0 else ""
            qty = 1
            if len(parts) > 1:
                try:
                    qty = int(parts[1])
                except ValueError:
                    qty = 1
            dosage = parts[2] if len(parts) > 2 else None
            expiry = parts[3] if len(parts) > 3 else None
            category = parts[4] if len(parts) > 4 else None
            if expiry:
                from datetime import datetime
                parsed_ok = False
                for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%m/%Y", "%d/%m/%Y"):
                    try:
                        expiry = datetime.strptime(expiry, fmt).strftime("%Y-%m-%d")
                        parsed_ok = True
                        break
                    except ValueError:
                        continue
                if not parsed_ok:
                    expiry = None
            if name:
                c.execute("INSERT INTO inventory (user_id, medicine_name, quantity, dosage, expiry_date, category) VALUES (%s, %s, %s, %s, %s, %s)", (uid, name, qty, dosage, expiry, category))
        for name in re.findall(r"
\[REMOVE_MEDICINE:\s*(.+?)\]", text):
            c.execute("DELETE FROM inventory WHERE user_id = %s AND LOWER(medicine_name) = LOWER(%s)", (uid, name.strip()))
        for fam in re.findall(r"
\[ADD_FAMILY:\s*(.+?)\]", text):
            parts = [p.strip() for p in fam.split("|")]
            name = parts[0] if len(parts) > 0 else ""
            age = None
            if len(parts) > 1:
                try:
                    age = int(parts[1])
                except ValueError:
                    age = None
            gender = parts[2] if len(parts) > 2 else None
            relation = parts[3] if len(parts) > 3 else None
            if name:
                c.execute("INSERT INTO family (user_id, name, age, gender, relation) VALUES (%s, %s, %s, %s, %s)", (uid, name, age, gender, relation))
        for rem in re.findall(r"
\[ADD_REMINDER:\s*(.+?)\]", text):
            parts = [p.strip() for p in rem.split("|")]
            member = parts[0] if len(parts) > 0 else None
            medicine = parts[1] if len(parts) > 1 else ""
            schedule = parts[2] if len(parts) > 2 else ""
            dosage = parts[3] if len(parts) > 3 else None
            sd = parts[4] if len(parts) > 4 else None
            ed = parts[5] if len(parts) > 5 else None
            if medicine and schedule:
                c.execute("INSERT INTO reminders (user_id, family_member, medicine_name, schedule, dosage, start_date, end_date) VALUES (%s, %s, %s, %s, %s, %s, %s)", (uid, member, medicine, schedule, dosage, sd, ed))
        conn.commit()
    except Exception as e:
        logger.error("Process cmds error: %s", e)
    finally:
        conn.close()

def clean_commands(text):
    text = re.sub(r"
\[ADD_MEDICINE:\s*.+?\]", "", text)
    text = re.sub(r"
\[REMOVE_MEDICINE:\s*.+?\]", "", text)
    text = re.sub(r"
\[ADD_FAMILY:\s*.+?\]", "", text)
    text = re.sub(r"
\[ADD_REMINDER:\s*.+?\]", "", text)
    return text.strip()
def tg_api(method, data=None):
    cfg = get_config()
    url = "https://api.telegram.org/bot" + cfg["TELEGRAM_TOKEN"] + "/" + method
    if data:
        req_data = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error("TG API error: %s", e)
        return None

def tg_send(chat_id, text):
    return tg_api("sendMessage", {"chat_id": chat_id, "text": text})

def tg_get_file_bytes(file_id):
    result = tg_api("getFile", {"file_id": file_id})
    if result and result.get("ok"):
        fp = result["result"]["file_path"]
        cfg = get_config()
        file_url = "https://api.telegram.org/file/bot" + cfg["TELEGRAM_TOKEN"] + "/" + fp
        req = urllib.request.Request(file_url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    return None

def handle_update(data):
    msg = data.get("message")
    if not msg:
        return
    chat_id = msg["chat"]["id"]
    uid = msg["from"]["id"]
    uname = msg["from"].get("username") or msg["from"].get("first_name") or ""
    save_user(uid, uname)
    user_text = ""
    if "voice" in msg:
        vb = tg_get_file_bytes(msg["voice"]["file_id"])
        if vb:
            t = process_voice(vb)
            if t:
                user_text = t
                tg_send(chat_id, "Распознано: " + t)
            else:
                tg_send(chat_id, "Не удалось распознать голос.")
                return
        else:
            tg_send(chat_id, "Не удалось скачать голосовое.")
            return
    elif "photo" in msg:
        pb = tg_get_file_bytes(msg["photo"][-1]["file_id"])
        if pb:
            tg_send(chat_id, "Анализирую фото...")
            vt = process_photo_vision(pb)
            if vt:
                cap = msg.get("caption", "")
                user_text = "Я сфотографировал упаковку лекарства. Вот что на фото:\n" + vt
                if cap:
                    user_text += "\nМой комментарий: " + cap
            else:
                ot = process_photo_ocr(pb)
                if ot:
                    user_text = "Сфотографировал упаковку. Текст: " + ot
                else:
                    tg_send(chat_id, "Не удалось распознать фото.")
                    return
        else:
            tg_send(chat_id, "Не удалось скачать фото.")
            return
    elif "text" in msg:
        user_text = msg["text"]
        if user_text.strip() == "/start":
            tg_send(chat_id, "Привет! Я Аптечка-бот.\n\nЯ помогу тебе:\n- Вести список лекарств\n- Подсказать что принять\n- Распознать лекарство по фото\n- Принять голосовые сообщения\n- Учитывать членов семьи\n- Напоминать о приёме лекарств\n- Следить за сроками годности\n- Собрать аптечку для поездки\n\nПросто напиши что у тебя есть в аптечке или задай вопрос!")
            return
        if user_text.strip() == "/inventory":
            inv = get_user_inventory(uid)
            if inv:
                lines = ["Твоя аптечка:\n"]
                for i, m in enumerate(inv, 1):
                    exp = (", годен до " + str(m[3])) if m[3] else ""
                    lines.append("%d. %s - %s шт., %s%s" % (i, m[0], m[1], m[2] or "дозировка не указана", exp))
                tg_send(chat_id, "\n".join(lines))
            else:
                tg_send(chat_id, "Аптечка пуста. Отправь фото лекарства или напиши что есть!")
            return
        if user_text.strip() == "/family":
            fam = get_user_family(uid)
            if fam:
                lines = ["Состав семьи:\n"]
                for f in fam:
                    lines.append("- %s, %s лет, %s, %s" % (f[0], f[1], f[2], f[3]))
                tg_send(chat_id, "\n".join(lines))
            else:
                tg_send(chat_id, "Семья не указана. Напиши кто в твоей семье!")
            return
    else:
        return
    save_message(uid, "user", user_text)
    reply = generate_gpt_response(uid, user_text)
    save_message(uid, "assistant", reply)
    tg_send(chat_id, reply)

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = flask_request.get_json(force=True)
        logger.info("Update received")
        handle_update(data)
    except Exception as e:
        logger.error("Webhook error: %s", e)
    return "OK", 200

@app.route("/", methods=["GET"])
def index():
    return "Bot is running!", 200

try:
    init_db()
except Exception as e:
    logger.error("Init failed: %s", e)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)