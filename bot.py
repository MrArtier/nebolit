import os, logging, io, re, tempfile, base64, json, urllib.request, psycopg2
from flask import Flask, request as flask_request
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def md_to_html(text):
    import re as _re
    text = _re.sub(r'\*\*\*(.+?)\*\*\*', r'<b><i>\1</i></b>', text)
    text = _re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = _re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    text = _re.sub(r'__(.+?)__', r'<u>\1</u>', text)
    text = _re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    return text

def check_expiry(exp_str):
    from datetime import date, timedelta
    if not exp_str or exp_str.strip() == "" or exp_str.strip() == "?":
        return "ok", None
    try:
        exp_str = exp_str.strip()
        exp_date = None
        import re as _re2
        if _re2.match(r"^\d{4}-\d{2}-\d{2}$", exp_str):
            parts = exp_str.split("-")
            exp_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
        elif _re2.match(r"^\d{4}-\d{2}$", exp_str):
            parts = exp_str.split("-")
            exp_date = date(int(parts[0]), int(parts[1]), 28)
        elif _re2.match(r"^\d{2}\.\d{2}\.\d{4}$", exp_str):
            parts = exp_str.split(".")
            exp_date = date(int(parts[2]), int(parts[1]), int(parts[0]))
        elif _re2.match(r"^\d{2}\.\d{4}$", exp_str):
            parts = exp_str.split(".")
            exp_date = date(int(parts[1]), int(parts[0]), 28)
        else:
            return "ok", None
        today = date.today()
        if exp_date < today:
            return "expired", exp_date
        elif exp_date < today + timedelta(days=60):
            return "soon", exp_date
        else:
            return "ok", exp_date
    except:
        return "ok", None
app = Flask(__name__)
def get_config():
    return {"OPENAI_API_KEY": os.getenv("OPENAI_API_KEY",""), "TELEGRAM_TOKEN": os.getenv("TELEGRAM_TOKEN",""), "DB_NAME": os.getenv("DB_NAME",""), "DB_USER": os.getenv("DB_USER",""), "DB_PASS": os.getenv("DB_PASS",""), "INSTANCE_CONNECTION_NAME": os.getenv("INSTANCE_CONNECTION_NAME",""), "DB_HOST": os.getenv("DB_HOST","")}
def get_db_connection():
    cfg = get_config()
    try:
        if cfg["INSTANCE_CONNECTION_NAME"]:
            return psycopg2.connect(host="/cloudsql/"+cfg["INSTANCE_CONNECTION_NAME"], database=cfg["DB_NAME"], user=cfg["DB_USER"], password=cfg["DB_PASS"], connect_timeout=10)
        return psycopg2.connect(host=cfg["DB_HOST"], database=cfg["DB_NAME"], user=cfg["DB_USER"], password=cfg["DB_PASS"], connect_timeout=10)
    except Exception as e:
        logger.error("DB err: %s", e)
        return None
def init_db():
    conn = get_db_connection()
    if not conn:
        return
    try:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS messages (id SERIAL PRIMARY KEY, user_id BIGINT, role TEXT NOT NULL, content TEXT NOT NULL, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS inventory (id SERIAL PRIMARY KEY, user_id BIGINT, medicine_name TEXT NOT NULL, quantity INTEGER DEFAULT 1, dosage TEXT, expiry_date DATE, category TEXT, notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS family (id SERIAL PRIMARY KEY, user_id BIGINT, name TEXT NOT NULL, age INTEGER, gender TEXT, relation TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS reminders (id SERIAL PRIMARY KEY, user_id BIGINT, family_member TEXT, medicine_name TEXT NOT NULL, dosage TEXT, schedule_time TEXT NOT NULL, meal_relation TEXT DEFAULT '', course_days INTEGER DEFAULT 0, pills_per_dose REAL DEFAULT 1, pills_in_pack INTEGER DEFAULT 0, pills_remaining REAL DEFAULT 0, start_date DATE, end_date DATE, active BOOLEAN DEFAULT TRUE, last_reminded TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS cabinets (id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL, name TEXT NOT NULL DEFAULT 'Моя аптечка', is_default BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS shared_access (id SERIAL PRIMARY KEY, owner_id BIGINT NOT NULL, shared_with_id BIGINT NOT NULL, shared_with_username TEXT, relation TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(owner_id, shared_with_id))")
        try:
            c.execute("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS cabinet_id INTEGER DEFAULT 0")
        except:
            pass
        c.execute("CREATE TABLE IF NOT EXISTS user_state (user_id BIGINT PRIMARY KEY, active_cabinet_id INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS subscriptions (id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL UNIQUE, plan TEXT DEFAULT 'free', started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TIMESTAMP, trial_used BOOLEAN DEFAULT FALSE, payment_id TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS payments (id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL, payment_id TEXT UNIQUE, amount DECIMAL(10,2), status TEXT DEFAULT 'pending', promo_code TEXT, discount_percent INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, confirmed_at TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS promo_codes (id SERIAL PRIMARY KEY, code TEXT UNIQUE NOT NULL, action TEXT DEFAULT 'discount', discount_percent INTEGER DEFAULT 0, free_days INTEGER DEFAULT 0, max_uses INTEGER DEFAULT 0, used_count INTEGER DEFAULT 0, active BOOLEAN DEFAULT TRUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS promo_usage (id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL, promo_id INTEGER REFERENCES promo_codes(id), used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, promo_id))")
        c.execute("CREATE TABLE IF NOT EXISTS reminder_log (id SERIAL PRIMARY KEY, reminder_id INTEGER REFERENCES reminders(id), sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, status TEXT DEFAULT 'sent')")
        c.execute("DELETE FROM reminders WHERE medicine_name IN ('лекарство','medicine','test') OR family_member IN ('член_семьи','member')")
        c.execute("DELETE FROM family WHERE name IN ('имя','name','test') OR gender IN ('пол','gender') OR relation IN ('отношение','relation')")
        conn.commit()
        logger.info("DB init OK")
    except Exception as e:
        logger.error("Init DB err: %s", e)
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
        logger.error("Save user err: %s", e)
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
        logger.error("Save msg err: %s", e)
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
        logger.error("History err: %s", e)
        return []
    finally:
        conn.close()
def get_subscription(uid):
    conn = get_db_connection()
    if not conn:
        return {"plan": "free", "active": False, "trial": False, "days_left": 0}
    try:
        c = conn.cursor()
        c.execute("SELECT plan, started_at, expires_at, trial_used FROM subscriptions WHERE user_id = %s", (uid,))
        row = c.fetchone()
        from datetime import datetime, timedelta
        now = datetime.now()
        if not row:
            c.execute("INSERT INTO subscriptions (user_id, plan, started_at, expires_at, trial_used) VALUES (%s, 'trial', %s, %s, FALSE)", (uid, now, now + timedelta(days=TRIAL_DAYS)))
            conn.commit()
            return {"plan": "trial", "active": True, "trial": True, "days_left": TRIAL_DAYS}
        plan, started, expires, trial_used = row
        if plan == "paid" and expires and expires > now:
            days_left = (expires - now).days
            return {"plan": "paid", "active": True, "trial": False, "days_left": days_left}
        if plan == "trial" and expires and expires > now:
            days_left = (expires - now).days
            return {"plan": "trial", "active": True, "trial": True, "days_left": days_left}
        return {"plan": "expired", "active": False, "trial": trial_used, "days_left": 0}
    except Exception as e:
        logger.error("Sub err: %s", e)
        return {"plan": "free", "active": False, "trial": False, "days_left": 0}
    finally:
        conn.close()

def activate_subscription(uid, days, payment_id=None):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        c = conn.cursor()
        from datetime import datetime, timedelta
        now = datetime.now()
        expires = now + timedelta(days=days)
        c.execute("INSERT INTO subscriptions (user_id, plan, started_at, expires_at, trial_used, payment_id) VALUES (%s, 'paid', %s, %s, TRUE, %s) ON CONFLICT (user_id) DO UPDATE SET plan='paid', started_at=%s, expires_at=%s, trial_used=TRUE, payment_id=%s", (uid, now, expires, payment_id, now, expires, payment_id))
        conn.commit()
        return True
    except Exception as e:
        logger.error("Activate err: %s", e)
        return False
    finally:
        conn.close()

def check_promo(code_text):
    conn = get_db_connection()
    if not conn:
        return None
    try:
        c = conn.cursor()
        c.execute("SELECT id, code, action, discount_percent, free_days, max_uses, used_count FROM promo_codes WHERE UPPER(code) = UPPER(%s) AND active = TRUE", (code_text,))
        row = c.fetchone()
        if not row:
            return None
        promo_id, code, action, discount, free_days, max_uses, used_count = row
        if max_uses > 0 and used_count >= max_uses:
            return None
        return {"id": promo_id, "code": code, "action": action, "discount": discount, "free_days": free_days}
    except:
        return None
    finally:
        conn.close()

def use_promo(uid, promo_id):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        c = conn.cursor()
        c.execute("SELECT id FROM promo_usage WHERE user_id = %s AND promo_id = %s", (uid, promo_id))
        if c.fetchone():
            return False
        c.execute("INSERT INTO promo_usage (user_id, promo_id) VALUES (%s, %s)", (uid, promo_id))
        c.execute("UPDATE promo_codes SET used_count = used_count + 1 WHERE id = %s", (promo_id,))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def create_yukassa_payment(uid, amount, description="Подписка НеБолит на 1 год"):
    import urllib.request
    import base64
    auth = base64.b64encode(("%s:%s" % (YUKASSA_SHOP_ID, YUKASSA_SECRET_KEY)).encode()).decode()
    import uuid
    idempotence_key = str(uuid.uuid4())
    body = json.dumps({"amount": {"value": str(amount), "currency": "RUB"}, "confirmation": {"type": "redirect", "return_url": "https://t.me/NeBolitBot"}, "capture": True, "description": description, "metadata": {"user_id": str(uid)}})
    req = urllib.request.Request("https://api.yookassa.ru/v3/payments", data=body.encode(), headers={"Content-Type": "application/json", "Authorization": "Basic " + auth, "Idempotence-Key": idempotence_key})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode())
        payment_id = data.get("id", "")
        pay_url = data.get("confirmation", {}).get("confirmation_url", "")
        conn = get_db_connection()
        if conn:
            try:
                c = conn.cursor()
                c.execute("INSERT INTO payments (user_id, payment_id, amount, status) VALUES (%s, %s, %s, 'pending') ON CONFLICT (payment_id) DO NOTHING", (uid, payment_id, amount))
                conn.commit()
            finally:
                conn.close()
        return payment_id, pay_url
    except Exception as e:
        logger.error("YuKassa err: %s", e)
        return None, None

def get_active_cabinet(uid):
    conn = get_db_connection()
    if not conn:
        return 0, "Моя аптечка"
    try:
        c = conn.cursor()
        c.execute("SELECT active_cabinet_id FROM user_state WHERE user_id = %s", (uid,))
        row = c.fetchone()
        cab_id = row[0] if row else 0
        if cab_id > 0:
            c.execute("SELECT name FROM cabinets WHERE id = %s", (cab_id,))
            cab = c.fetchone()
            return cab_id, cab[0] if cab else "Моя аптечка"
        return 0, "Моя аптечка"
    except:
        return 0, "Моя аптечка"
    finally:
        conn.close()

def set_active_cabinet(uid, cab_id):
    conn = get_db_connection()
    if not conn:
        return
    try:
        c = conn.cursor()
        c.execute("INSERT INTO user_state (user_id, active_cabinet_id) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET active_cabinet_id = %s", (uid, cab_id, cab_id))
        conn.commit()
    except:
        pass
    finally:
        conn.close()

def get_user_cabinets(uid):
    conn = get_db_connection()
    if not conn:
        return []
    try:
        c = conn.cursor()
        c.execute("SELECT id, name, is_default FROM cabinets WHERE user_id = %s ORDER BY id", (uid,))
        return c.fetchall()
    except:
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
        logger.error("Inv err: %s", e)
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
        logger.error("Fam err: %s", e)
        return []
    finally:
        conn.close()
def process_voice(voice_bytes):
    from openai import OpenAI
    client = OpenAI(api_key=get_config()["OPENAI_API_KEY"])
    try:
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp.write(voice_bytes)
            tmp_path = tmp.name
        with open(tmp_path, "rb") as af:
            transcript = client.audio.transcriptions.create(model="whisper-1", file=af, language="ru")
        os.unlink(tmp_path)
        return transcript.text.strip()
    except Exception as e:
        logger.error("Whisper err: %s", e)
        return ""
def process_photo_vision(photo_bytes):
    from openai import OpenAI
    client = OpenAI(api_key=get_config()["OPENAI_API_KEY"])
    try:
        b64 = base64.b64encode(photo_bytes).decode("utf-8")
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":[{"type":"text","text":"На фото упаковка лекарства. Определи название, действующее вещество, дозировку, срок годности, показания, категорию. Кратко."},{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+b64}}]}], max_tokens=500)
        return resp.choices[0].message.content
    except Exception as e:
        logger.error("Vision err: %s", e)
        return ""
SYSTEM_PROMPT = "Ты умный и дружелюбный помощник по домашней аптечке бот НеБолит. Задачи: хранить список лекарств, подсказывать что принять, учитывать семью, предлагать пополнить аптечку, собирать мини-аптечку для поездок, следить за сроками годности, создавать напоминания о приёме лекарств. При рекомендациях что принять - советуй из аптечки, если нет нужного - скажи что стоит купить. Предупреждай что не замена врачу. Отвечай на русском кратко и дружелюбно. Команды: [ADD_MEDICINE:название|количество|дозировка|срок|категория] - добавить лекарство. КАТЕГОРИИ определяй сам на основе своих знаний о лекарстве: ТЕМПЕРАТУРА (жаропонижающие, противопростудные), БОЛЬ (обезболивающие, спазмолитики), ЖИВОТ (ЖКТ, пищеварение), РАНЫ (антисептики, бинты, пластыри, мази для кожи), РАЗНОЕ (аллергия, сердце, давление, витамины и всё остальное). НИКОГДА не спрашивай категорию у пользователя - определяй сам. Также определяй правильное название лекарства, типовую дозировку если пользователь не указал. [REMOVE_MEDICINE:название] - удалить. [ADD_FAMILY:имя|возраст|пол|отношение] - добавить семью. [ADD_REMINDER:член_семьи|лекарство|время_приёма|до/после/во_время еды|дозировка|дней_курса|таблеток_за_приём|таблеток_в_пачке] - напоминание. ВАЖНО про напоминания: 1) Создавай напоминание даже если лекарства нет в аптечке - пользователь мог быть у врача и ещё не купил. 2) Если лекарство назначено но его нет в аптечке - добавь к ответу что нужно его купить. 3) Слова бессрочно/постоянно/всегда/пожизненно = дней_курса 0 (ноль означает бессрочный приём). 4) Если курс длинный - посчитай сколько таблеток нужно всего и хватит ли имеющихся. Время приёма: 08:00 или 08:00,14:00,20:00 для нескольких раз. Если пользователь говорит что врач назначил - ОБЯЗАТЕЛЬНО создай напоминание. Если лекарства нет в аптечке - всё равно создай напоминание и предупреди купить. При добавлении лекарства: 1) Определи правильное полное название. 2) Если пользователь не указал дозировку - подставь стандартную (например Нурофен = 200мг, Парацетамол = 500мг). 3) Категорию определи сам. 4) Если количество не указано - поставь 1. 5) Если срок не указан - поставь пустую строку. СТРОГАЯ ПРОВЕРКА СРОКОВ: Всегда сравнивай срок годности с ТЕКУЩЕЙ датой. Сегодняшнюю дату определяй из системы. Если срок годности уже прошёл - обязательно добавь к ответу предупреждение с красным восклицательным знаком что лекарство ПРОСРОЧЕНО и его НЕЛЬЗЯ принимать, в аптечку НЕ ДОБАВЛЯЙ (не пиши команду ADD_MEDICINE). Если до конца срока менее 2 месяцев - предупреди жёлтым значком. Если лекарство годно - зелёная галочка. Формат срока в команде: ГГГГ-ММ-ДД или ГГГГ-ММ. НИКОГДА не подставляй шаблонные значения типа член_семьи/лекарство/время_приёма/дозировка - используй только реальные данные из сообщения пользователя. Если пользователь не указал для кого - оставь поле члена семьи пустым. Если не указал время - спроси. Связка аптечек: если пользователь хочет поделиться аптечкой с родственником через его @username в телеграме - используй команду [SHARE_ACCESS:@username|отношение]. Множественные аптечки: пользователь может вести несколько аптечек (свою, мамы, папы и т.д.). Команды: [CREATE_CABINET:название] - создать новую аптечку. [SWITCH_CABINET:название] - переключиться на другую аптечку. По умолчанию лекарства добавляются в текущую активную аптечку. Если пользователь говорит добавить лекарство в конкретную аптечку - сначала переключи, потом добавь."
def generate_gpt_response(uid, user_text):
    from openai import OpenAI
    client = OpenAI(api_key=get_config()["OPENAI_API_KEY"])
    history = get_user_history(uid, limit=20)
    inventory = get_user_inventory(uid)
    family = get_user_family(uid)
    inv_text = "Аптечка пуста."
    if inventory:
        lines = []
        for m in inventory:
            lines.append("- %s, кол-во: %s, дозировка: %s, годен до: %s, категория: %s" % (m[0], m[1], m[2] or "?", m[3] or "?", m[4] or "?"))
        inv_text = "\n".join(lines)
    fam_text = "Семья не указана."
    if family:
        lines = []
        for f in family:
            lines.append("- %s, %s лет, %s, %s" % (f[0], f[1], f[2], f[3]))
        fam_text = "\n".join(lines)
    cab_id, cab_name = get_active_cabinet(uid)
    from datetime import date as _date
    today_str = _date.today().isoformat()
    cab_text = "Сегодня: %s. Текущая аптечка: %s" % (today_str, cab_name)
    cabs = get_user_cabinets(uid)
    if cabs:
        cab_text += ". Все аптечки: " + ", ".join([c[1] for c in cabs])
    rem_text = "Напоминаний нет."
    conn2 = get_db_connection()
    if conn2:
        try:
            c2 = conn2.cursor()
            c2.execute("SELECT family_member, medicine_name, dosage, schedule_time, meal_relation, course_days, start_date, end_date, pills_remaining FROM reminders WHERE user_id = %s AND active = TRUE", (uid,))
            rems = c2.fetchall()
            if rems:
                rlines = []
                for r in rems:
                    course_str = "бессрочно" if (r[5] == 0 or r[5] is None) else "%s дней" % r[5]
                    in_stock = "нет в аптечке"
                    c3 = conn2.cursor()
                    c3.execute("SELECT quantity FROM inventory WHERE user_id = %s AND LOWER(medicine_name) = LOWER(%s)", (uid, r[1]))
                    stock_row = c3.fetchone()
                    if stock_row:
                        in_stock = "в аптечке: %s шт" % stock_row[0]
                    rlines.append("- %s %s, приём: %s %s, курс: %s, %s" % (r[1], ("для "+r[0]) if r[0] else "", r[3], r[4] or "", course_str, in_stock))
                rem_text = "\n".join(rlines)
        except Exception as e:
            logger.error("Rem ctx err: %s", e)
        finally:
            conn2.close()
    ctx = cab_text + "\nАптечка:\n" + inv_text + "\nСемья:\n" + fam_text + "\nНапоминания:\n" + rem_text
    messages = [{"role":"system","content":SYSTEM_PROMPT},{"role":"system","content":ctx}]
    messages.extend(history)
    messages.append({"role":"user","content":user_text})
    try:
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=messages, max_tokens=1000, temperature=0.7)
        reply = resp.choices[0].message.content
        process_gpt_commands(uid, reply)
        return clean_commands(reply)
    except Exception as e:
        logger.error("GPT err: %s", e)
        return "Ошибка связи с ИИ. Попробуй ещё раз."
ADD_MED_RE = r"\[ADD_MEDICINE:(.+?)\]"
REM_MED_RE = r"\[REMOVE_MEDICINE:(.+?)\]"
ADD_FAM_RE = r"\[ADD_FAMILY:(.+?)\]"
ADD_REM_RE = r"\[ADD_REMINDER:(.+?)\]"
SHARE_RE = r"\[SHARE_ACCESS:(.+?)\]"
CABINET_CREATE_RE = r"\[CREATE_CABINET:(.+?)\]"
CABINET_SWITCH_RE = r"\[SWITCH_CABINET:(.+?)\]"
def process_gpt_commands(uid, text):
    conn = get_db_connection()
    if not conn:
        return
    try:
        c = conn.cursor()
        for med in re.findall(ADD_MED_RE, text):
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
            if name:
                c.execute("INSERT INTO inventory (user_id, medicine_name, quantity, dosage, expiry_date, category) VALUES (%s,%s,%s,%s,%s,%s)", (uid, name, qty, dosage, None, category))
        for name in re.findall(REM_MED_RE, text):
            c.execute("DELETE FROM inventory WHERE user_id = %s AND LOWER(medicine_name) = LOWER(%s)", (uid, name.strip()))
        for fam in re.findall(ADD_FAM_RE, text):
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
                c.execute("INSERT INTO family (user_id, name, age, gender, relation) VALUES (%s,%s,%s,%s,%s)", (uid, name, age, gender, relation))
        for cab in re.findall(CABINET_CREATE_RE, text):
            cab_name = cab.strip()
            if cab_name:
                c.execute("INSERT INTO cabinets (user_id, name) VALUES (%s, %s) RETURNING id", (uid, cab_name))
                new_id = c.fetchone()[0]
                c.execute("INSERT INTO user_state (user_id, active_cabinet_id) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET active_cabinet_id = %s", (uid, new_id, new_id))
        for cab in re.findall(CABINET_SWITCH_RE, text):
            cab_name = cab.strip()
            if cab_name:
                c.execute("SELECT id FROM cabinets WHERE user_id = %s AND LOWER(name) LIKE LOWER(%s)", (uid, "%" + cab_name + "%"))
                row = c.fetchone()
                if row:
                    c.execute("INSERT INTO user_state (user_id, active_cabinet_id) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET active_cabinet_id = %s", (uid, row[0], row[0]))
                elif cab_name.lower() in ("моя аптечка", "своя", "моя", "основная", "домашняя"):
                    c.execute("INSERT INTO user_state (user_id, active_cabinet_id) VALUES (%s, 0) ON CONFLICT (user_id) DO UPDATE SET active_cabinet_id = 0", (uid,))
        for sh in re.findall(SHARE_RE, text):
            parts = [p.strip() for p in sh.split("|")]
            username = parts[0].replace("@", "") if len(parts) > 0 else ""
            relation = parts[1] if len(parts) > 1 else ""
            if username:
                c.execute("INSERT INTO shared_access (owner_id, shared_with_id, shared_with_username, relation) VALUES (%s, 0, %s, %s) ON CONFLICT DO NOTHING", (uid, username, relation))
        for rem in re.findall(ADD_REM_RE, text):
            parts = [p.strip() for p in rem.split("|")]
            member = parts[0] if len(parts) > 0 else ""
            medicine = parts[1] if len(parts) > 1 else ""
            schedule = parts[2] if len(parts) > 2 else "08:00"
            meal = parts[3] if len(parts) > 3 else ""
            dosage = parts[4] if len(parts) > 4 else ""
            course_days = 0
            if len(parts) > 5:
                try:
                    course_days = int(parts[5])
                except ValueError:
                    course_days = 0
            pills_per_dose = 1.0
            if len(parts) > 6:
                try:
                    pills_per_dose = float(parts[6])
                except ValueError:
                    pills_per_dose = 1.0
            pills_in_pack = 0
            if len(parts) > 7:
                try:
                    pills_in_pack = int(parts[7])
                except ValueError:
                    pills_in_pack = 0
            if medicine:
                from datetime import date, timedelta
                start = date.today()
                end = start + timedelta(days=course_days) if course_days > 0 else None
                total_pills = 0 if course_days == 0 else total_pills
                times_per_day = len(schedule.split(","))
                total_pills = course_days * times_per_day * pills_per_dose if course_days > 0 else 0
                c.execute("INSERT INTO reminders (user_id, family_member, medicine_name, dosage, schedule_time, meal_relation, course_days, pills_per_dose, pills_in_pack, pills_remaining, start_date, end_date, active) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)", (uid, member, medicine, dosage, schedule, meal, course_days, pills_per_dose, pills_in_pack, total_pills, start, end))
        conn.commit()
    except Exception as e:
        logger.error("Cmd err: %s", e)
    finally:
        conn.close()
def clean_commands(text):
    text = re.sub(ADD_MED_RE, "", text)
    text = re.sub(REM_MED_RE, "", text)
    text = re.sub(ADD_FAM_RE, "", text)
    text = re.sub(ADD_REM_RE, "", text)
    text = re.sub(SHARE_RE, "", text)
    text = re.sub(CABINET_CREATE_RE, "", text)
    text = re.sub(CABINET_SWITCH_RE, "", text)
    return text.strip()
def tg_api(method, data=None):
    cfg = get_config()
    url = "https://api.telegram.org/bot" + cfg["TELEGRAM_TOKEN"] + "/" + method
    if data:
        req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers={"Content-Type":"application/json"})
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error("TG err: %s", e)
        return None
def tg_send(chat_id, text):
    html_text = md_to_html(text)
    try:
        return tg_api("sendMessage", {"chat_id": chat_id, "text": html_text, "parse_mode": "HTML"})
    except:
        return tg_api("sendMessage", {"chat_id": chat_id, "text": text})
def tg_send_start_button(chat_id):
    keyboard = {"keyboard": [[{"text": "\U0001f4aa Навести порядок"}]], "resize_keyboard": True, "one_time_keyboard": True}
    return tg_api("sendMessage", {"chat_id": chat_id, "text": "\U0001f48a Добро пожаловать в НеБолит!\n\nНажми кнопку ниже, чтобы начать \U0001f447", "reply_markup": keyboard})

def tg_send_with_menu(chat_id, text):
    keyboard = {"keyboard": [[{"text": "\U0001f3e0 Старт"}, {"text": "\U0001f4e6 Аптечка"}], [{"text": "\U0001f48a Курсы приёма"}, {"text": "\U0001f468\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466 Семья"}], [{"text": "\U0001f3e0 Аптечки"}]], "resize_keyboard": True, "one_time_keyboard": False}
    html_text = md_to_html(text)
    try:
        return tg_api("sendMessage", {"chat_id": chat_id, "text": html_text, "parse_mode": "HTML", "reply_markup": keyboard})
    except:
        return tg_api("sendMessage", {"chat_id": chat_id, "text": text, "reply_markup": keyboard})

def tg_get_file_bytes(file_id):
    result = tg_api("getFile", {"file_id": file_id})
    if result and result.get("ok"):
        fp = result["result"]["file_path"]
        cfg = get_config()
        url = "https://api.telegram.org/file/bot" + cfg["TELEGRAM_TOKEN"] + "/" + fp
        with urllib.request.urlopen(urllib.request.Request(url), timeout=30) as resp:
            return resp.read()
    return None
def handle_update(data):
    msg = data.get("message")
    if not msg:
        return
    chat_id = msg["chat"]["id"]
    uid = msg["from"]["id"]
    uname = msg["from"].get("username") or msg["from"].get("first_name") or ""
    is_new = False
    conn_check = get_db_connection()
    if conn_check:
        try:
            c_check = conn_check.cursor()
            c_check.execute("SELECT COUNT(*) FROM messages WHERE user_id = %s", (uid,))
            msg_count = c_check.fetchone()[0]
            if msg_count == 0:
                is_new = True
        except:
            pass
        finally:
            conn_check.close()
    save_user(uid, uname)
    if is_new and not ("text" in msg and msg["text"].strip() == "/start"):
        tg_send_start_button(chat_id)
        return
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
                user_text = "Сфотографировал упаковку лекарства:\n" + vt
                cap = msg.get("caption", "")
                if cap:
                    user_text += "\nКомментарий: " + cap
            else:
                tg_send(chat_id, "Не удалось распознать фото.")
                return
        else:
            tg_send(chat_id, "Не удалось скачать фото.")
            return
    elif "text" in msg:
        user_text = msg["text"]
        sub = get_subscription(uid)
        if user_text.strip().upper().startswith("NB-") or user_text.strip().upper().startswith("NEBOLIT"):
            promo = check_promo(user_text.strip())
            if promo:
                already_used = not use_promo(uid, promo["id"])
                if already_used:
                    tg_send(chat_id, "\u274c Вы уже использовали этот промокод.")
                    return
                if promo["action"] == "discount":
                    price = int(SUBSCRIPTION_PRICE * (100 - promo["discount"]) / 100)
                    payment_id, pay_url = create_yukassa_payment(uid, price, "Подписка НеБолит (скидка %s%%)" % promo["discount"])
                    if pay_url:
                        conn_pr = get_db_connection()
                        if conn_pr:
                            try:
                                c_pr = conn_pr.cursor()
                                c_pr.execute("UPDATE payments SET promo_code=%s, discount_percent=%s WHERE payment_id=%s", (promo["code"], promo["discount"], payment_id))
                                conn_pr.commit()
                            finally:
                                conn_pr.close()
                        tg_send(chat_id, "\U0001f389 Промокод принят! Скидка %s%%\n\U0001f4b0 Цена: %s \u20bd (вместо %s \u20bd)\n\n\U0001f449 Оплатите по ссылке:\n%s" % (promo["discount"], price, SUBSCRIPTION_PRICE, pay_url))
                    else:
                        tg_send(chat_id, "\u274c Ошибка создания платежа. Попробуйте позже.")
                    return
                elif promo["action"] == "free_days":
                    activate_subscription(uid, promo["free_days"])
                    tg_send(chat_id, "\U0001f389 Промокод принят! Вам подарено %s дней бесплатного доступа!" % promo["free_days"])
                    return
                elif promo["action"] == "full_free":
                    activate_subscription(uid, 365)
                    tg_send(chat_id, "\U0001f389 Промокод принят! Подписка на год активирована бесплатно!")
                    return
            else:
                pass
        if user_text.strip() == "/subscribe":
            if sub["plan"] == "paid" and sub["active"]:
                tg_send(chat_id, "\u2705 У вас уже есть активная подписка! Осталось дней: %s" % sub["days_left"])
                return
            payment_id, pay_url = create_yukassa_payment(uid, SUBSCRIPTION_PRICE)
            if pay_url:
                tg_send(chat_id, "\U0001f48a Подписка НеБолит на 1 год\n\U0001f4b0 Стоимость: %s \u20bd\n\n\U0001f449 Оплатите по ссылке:\n%s\n\nПосле оплаты доступ активируется автоматически!" % (SUBSCRIPTION_PRICE, pay_url))
            else:
                tg_send(chat_id, "\u274c Ошибка создания платежа. Попробуйте позже.")
            return
        if user_text.strip() == "/status":
            if sub["plan"] == "paid":
                tg_send(chat_id, "\u2705 Подписка активна! Осталось %s дней." % sub["days_left"])
            elif sub["plan"] == "trial":
                tg_send(chat_id, "\U0001f552 Пробный период. Осталось %s дней.\n\nДля оплаты: /subscribe" % sub["days_left"])
            else:
                tg_send(chat_id, "\u274c Подписка неактивна.\n\nДля оплаты: /subscribe")
            return
        if not sub["active"] and user_text.strip() not in ["/start", "/subscribe", "/status"]:
            is_free_query = any(w in user_text.lower() for w in ["что такое", "для чего", "от чего", "зачем", "описание", "инструкция", "побочные", "аналог"])
            if not is_free_query:
                if sub.get("trial"):
                    tg_send(chat_id, "\u23f0 Пробный период закончился.\n\nВам доступны бесплатные справки о лекарствах. Для полного доступа оформите подписку: /subscribe")
                else:
                    tg_send(chat_id, "\U0001f512 Эта функция доступна по подписке.\n\nВам доступны бесплатные справки о лекарствах. Для полного доступа: /subscribe")
                return
        if user_text.strip() == "/start":
            welcome = (
                "\U0001f48a Привет! Я бот НеБолит — твой персональный помощник по домашней аптечке.\n"
                "\n"
                "\U00002728 Вот что я умею:\n"
                "\n"
                "\U0001f4e6 Аптечка\n"
                "Храню полный список твоих лекарств с дозировками и сроками годности.\n"
                "\n"
                "\U0001f4f7 Распознавание по фото\n"
                "Сфотографируй упаковку — я сам определю название, дозировку и срок годности и добавлю в базу.\n"
                "\n"
                "\U0001f3a4 Голосовые сообщения\n"
                "Просто наговори что есть в аптечке или задай вопрос голосом.\n"
                "\n"
                "\U0001f912 Что принять?\n"
                "Опиши недомогание — подскажу что есть подходящего в твоей аптечке.\n"
                "\n"
                "\U0001f468\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466 Семья\n"
                "Учитываю кто в семье: взрослые, дети, мужчины, женщины — чтобы рекомендации были точнее.\n"
                "\n"
                "\U000023f0 Напоминания\n"
                "Врач назначил курс? Создам расписание приёма и буду напоминать.\n"
                "\n"
                "\U0001f4c5 Сроки годности\n"
                "Слежу за сроками и напомню выбросить просроченное.\n"
                "\n"
                "\U0001f9f3 Аптечка в дорогу\n"
                "Собираешься на море или в поход? Подберу мини-аптечку под сценарий.\n"
                "\n"
                "\U0001f6d2 Пополнение\n"
                "Подскажу чего не хватает и что стоит докупить.\n"
                "\n"
                "\U00002014\U00002014\U00002014\U00002014\U00002014\U00002014\U00002014\U00002014\U00002014\U00002014\n"
                "\U0001f4cc Команды:\n"
                "/inventory — посмотреть аптечку\n"
                "/family — состав семьи\n"
                "\n"
                "\U000027a1\ufe0f Начни прямо сейчас — напиши что у тебя есть в аптечке, отправь фото или голосовое!"
            )
            sub_info = get_subscription(uid)
            if sub_info["plan"] == "paid":
                welcome += "\n\n\u2705 Подписка активна (%s дн.)" % sub_info["days_left"]
            elif sub_info["plan"] == "trial":
                welcome += "\n\n\U0001f552 Пробный период (%s дн.). /subscribe для оплаты" % sub_info["days_left"]
            else:
                welcome += "\n\n\U0001f512 Подписка неактивна. /subscribe для оплаты"
            tg_send_with_menu(chat_id, welcome)
            return
        if user_text.strip() == "/cabinets":
            cabs = get_user_cabinets(uid)
            cab_id, cab_name = get_active_cabinet(uid)
            lines = ["\U0001f3e0 Ваши аптечки:\n"]
            if not cabs:
                lines.append("\U0001f4e6 Моя аптечка (по умолчанию) \u2705")
            else:
                for cb in cabs:
                    mark = " \u2705" if cb[0] == cab_id else ""
                    lines.append("\U0001f4e6 %s (id:%s)%s" % (cb[1], cb[0], mark))
                if cab_id == 0:
                    lines.append("\U0001f4e6 Моя аптечка (по умолчанию) \u2705")
            lines.append("\n\U0001f4ac Чтобы создать: \"Создай аптечку для мамы\"")
            lines.append("\U0001f504 Чтобы переключить: \"Переключи на аптечку мамы\"")
            tg_send(chat_id, "\n".join(lines))
            return
        if user_text.strip() == "/reminders":
            conn = get_db_connection()
            if conn:
                try:
                    c = conn.cursor()
                    c.execute("SELECT family_member, medicine_name, dosage, schedule_time, meal_relation, course_days, start_date, end_date, pills_remaining FROM reminders WHERE user_id = %s AND active = TRUE ORDER BY schedule_time", (uid,))
                    rems = c.fetchall()
                    if rems:
                        lines = ["\U0001f4cb Активные напоминания:\n"]
                        for r in rems:
                            line = "\U0001f48a %s" % r[1]
                            if r[0]:
                                line += " (для %s)" % r[0]
                            line += "\n   \U000023f0 %s" % r[3]
                            if r[4]:
                                line += " %s" % r[4]
                            if r[2]:
                                line += "\n   \U0001f4ca %s" % r[2]
                            if r[5] and r[5] > 0:
                                line += "\n   \U0001f4c5 Курс: %s дней (%s - %s)" % (r[5], r[6], r[7])
                            elif r[5] == 0 or r[5] is None:
                                line += "\n   \U0001f504 Бессрочный приём"
                            if r[8] and r[8] > 0:
                                line += "\n   \U0001f4a6 Осталось таблеток: %s" % int(r[8])
                            lines.append(line)
                        tg_send(chat_id, "\n".join(lines))
                    else:
                        tg_send(chat_id, "Нет активных напоминаний.")
                except Exception as e:
                    logger.error("Reminders err: %s", e)
                    tg_send(chat_id, "Ошибка при загрузке напоминаний.")
                finally:
                    conn.close()
            else:
                tg_send(chat_id, "Ошибка подключения к базе.")
            return
        if user_text.strip() == "/inventory":
            inv = get_user_inventory(uid)
            cab_id_d, cab_name_d = get_active_cabinet(uid)
            if inv:
                lines = ["\U0001f4e6 %s:\n" % cab_name_d]
                for i, m in enumerate(inv, 1):
                    exp = (", годен до " + str(m[3])) if m[3] else ""
                    lines.append("%d. %s - %s шт., %s%s" % (i, m[0], m[1], m[2] or "?", exp))
                tg_send(chat_id, "\n".join(lines))
            else:
                tg_send(chat_id, "Аптечка пуста.")
            return
        if user_text.strip() == "/family":
            fam = get_user_family(uid)
            if fam:
                lines = ["Семья:\n"]
                for f in fam:
                    age_str = "%s лет" % f[1] if f[1] else "возраст не указан"
                    gender_str = f[2] if f[2] else ""
                    rel_str = f[3] if f[3] else ""
                    parts = [f[0], age_str]
                    if gender_str:
                        parts.append(gender_str)
                    if rel_str:
                        parts.append(rel_str)
                    lines.append("- %s" % ", ".join(parts))
                tg_send(chat_id, "\n".join(lines))
            else:
                tg_send(chat_id, "Семья не указана.")
            return
    else:
        return
    if user_text == "\U0001f3e0 Старт":
        user_text = "/start"
    elif user_text == "\U0001f4e6 Аптечка":
        user_text = "/inventory"
    elif user_text == "\U0001f48a Курсы приёма":
        user_text = "/reminders"
    elif user_text == "\U0001f468\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466 Семья":
        user_text = "/family"
    elif user_text == "\U0001f3e0 Аптечки":
        user_text = "/cabinets"
    elif user_text == "\U0001f4aa Навести порядок":
        user_text = "/start"
    save_message(uid, "user", user_text)
    reply = generate_gpt_response(uid, user_text)
    save_message(uid, "assistant", reply)
    conn_med = get_db_connection()
    med_alerts = []
    if conn_med:
        try:
            c_med = conn_med.cursor()
            c_med.execute("SELECT medicine_name, expiry_date FROM inventory WHERE user_id = %s ORDER BY id DESC LIMIT 20", (uid,))
        except:
            pass
        finally:
            conn_med.close()
    tg_send(chat_id, reply)
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = flask_request.get_json(force=True)
        logger.info("Update received")
        handle_update(data)
    except Exception as e:
        logger.error("Webhook err: %s", e)
    return "OK", 200
@app.route("/", methods=["GET"])
def index():
    return "Bot running!", 200
try:
    init_db()
except Exception as e:
    logger.error("Init failed: %s", e)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

