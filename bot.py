import os, logging, io, re, tempfile, base64, json, urllib.request, psycopg2
from flask import Flask, request as flask_request
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
YUKASSA_SHOP_ID = os.environ.get("YUKASSA_SHOP_ID", "")
YUKASSA_SECRET_KEY = os.environ.get("YUKASSA_SECRET_KEY", "")
SUBSCRIPTION_PRICE = 1490
TRIAL_DAYS = 7
ADMIN_ID = 210064232

app = Flask(__name__)

def get_config():
    return {"OPENAI_API_KEY": OPENAI_API_KEY, "TELEGRAM_TOKEN": TELEGRAM_TOKEN, "DB_NAME": os.getenv("DB_NAME",""), "DB_USER": os.getenv("DB_USER",""), "DB_PASS": os.getenv("DB_PASS",""), "INSTANCE_CONNECTION_NAME": os.getenv("INSTANCE_CONNECTION_NAME",""), "DB_HOST": os.getenv("DB_HOST","")}

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
        c.execute("CREATE TABLE IF NOT EXISTS inventory (id SERIAL PRIMARY KEY, user_id BIGINT, medicine_name TEXT NOT NULL, quantity INTEGER DEFAULT 1, dosage TEXT, expiry_date DATE, category TEXT, notes TEXT, cabinet_id INTEGER DEFAULT 0, storage TEXT DEFAULT '', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS family (id SERIAL PRIMARY KEY, user_id BIGINT, name TEXT NOT NULL, age INTEGER, gender TEXT, relation TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS reminders (id SERIAL PRIMARY KEY, user_id BIGINT, family_member TEXT, medicine_name TEXT NOT NULL, dosage TEXT, schedule_time TEXT NOT NULL, meal_relation TEXT DEFAULT '', course_days INTEGER DEFAULT 0, pills_per_dose REAL DEFAULT 1, pills_in_pack INTEGER DEFAULT 0, pills_remaining REAL DEFAULT 0, start_date DATE, end_date DATE, active BOOLEAN DEFAULT TRUE, last_reminded TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS cabinets (id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL, name TEXT NOT NULL DEFAULT 'Моя аптечка', is_default BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS shared_access (id SERIAL PRIMARY KEY, owner_id BIGINT NOT NULL, shared_with_id BIGINT NOT NULL, shared_with_username TEXT, relation TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(owner_id, shared_with_id))")
        c.execute("CREATE TABLE IF NOT EXISTS user_state (user_id BIGINT PRIMARY KEY, active_cabinet_id INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS subscriptions (id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL UNIQUE, plan TEXT DEFAULT 'free', started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TIMESTAMP, trial_used BOOLEAN DEFAULT FALSE, payment_id TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS payments (id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL, payment_id TEXT UNIQUE, amount DECIMAL(10,2), status TEXT DEFAULT 'pending', promo_code TEXT, discount_percent INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, confirmed_at TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS promo_codes (id SERIAL PRIMARY KEY, code TEXT UNIQUE NOT NULL, action TEXT DEFAULT 'discount', discount_percent INTEGER DEFAULT 0, free_days INTEGER DEFAULT 0, max_uses INTEGER DEFAULT 0, used_count INTEGER DEFAULT 0, active BOOLEAN DEFAULT TRUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS promo_usage (id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL, promo_id INTEGER REFERENCES promo_codes(id), used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, promo_id))")
        c.execute("CREATE TABLE IF NOT EXISTS reminder_log (id SERIAL PRIMARY KEY, reminder_id INTEGER REFERENCES reminders(id), sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, status TEXT DEFAULT 'sent')")
        try:
            c.execute("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS storage TEXT DEFAULT ''")
            conn.commit()
        except:
            conn.rollback()
        c.execute("DELETE FROM reminders WHERE medicine_name IN ('лекарство','medicine','test') OR family_member IN ('член_семьи','member')")
        c.execute("DELETE FROM inventory WHERE dosage = 'дозировка' OR category = 'категория' OR medicine_name IN ('лекарство','medicine','test')")
        c.execute("DELETE FROM family WHERE name IN ('имя','name','test','член_семьи','member') OR gender IN ('пол','gender') OR relation IN ('отношение','relation','родство') OR age = 0")
        conn.commit()
        logger.info("DB init OK")
    except Exception as e:
        logger.error("Init DB err: %s", e)
    finally:
        conn.close()

def md_to_html(text):
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<b><i>\1</i></b>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\w)\*(.+?)\*(?!\w)', r'<i>\1</i>', text)
    text = re.sub(r'__(.+?)__', r'<u>\1</u>', text)
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    return text

def check_expiry(exp_str):
    from datetime import date, timedelta
    if not exp_str or str(exp_str).strip() in ("", "?", "None"):
        return "ok", None
    try:
        exp_str = str(exp_str).strip()
        exp_date = None
        if re.match(r"^\d{4}-\d{2}-\d{2}$", exp_str):
            p = exp_str.split("-"); exp_date = date(int(p[0]), int(p[1]), int(p[2]))
        elif re.match(r"^\d{4}-\d{2}$", exp_str):
            p = exp_str.split("-"); exp_date = date(int(p[0]), int(p[1]), 28)
        elif re.match(r"^\d{2}\.\d{2}\.\d{4}$", exp_str):
            p = exp_str.split("."); exp_date = date(int(p[2]), int(p[1]), int(p[0]))
        elif re.match(r"^\d{2}\.\d{4}$", exp_str):
            p = exp_str.split("."); exp_date = date(int(p[1]), int(p[0]), 28)
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

# === DB helpers ===

def save_user(uid, uname):
    conn = get_db_connection()
    if not conn: return
    try:
        c = conn.cursor()
        c.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET username = %s", (uid, uname, uname))
        conn.commit()
    except Exception as e:
        logger.error("Save user err: %s", e, exc_info=True)
        try: conn.rollback()
        except: pass
    finally: conn.close()

def save_message(uid, role, content):
    conn = get_db_connection()
    if not conn: return
    try:
        c = conn.cursor()
        c.execute("INSERT INTO messages (user_id, role, content) VALUES (%s, %s, %s)", (uid, role, content))
        conn.commit()
    except Exception as e:
        logger.error("Save msg err: %s", e, exc_info=True)
        try: conn.rollback()
        except: pass
    finally: conn.close()

def get_user_history(uid, limit=20):
    conn = get_db_connection()
    if not conn: return []
    try:
        c = conn.cursor()
        c.execute("SELECT role, content FROM messages WHERE user_id = %s ORDER BY timestamp DESC LIMIT %s", (uid, limit))
        rows = c.fetchall(); rows.reverse()
        return [{"role": r[0], "content": r[1]} for r in rows]
    except: return []
    finally: conn.close()

def get_active_cabinet(uid):
    conn = get_db_connection()
    if not conn: return 0, "Моя аптечка"
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
    except: return 0, "Моя аптечка"
    finally: conn.close()

def get_user_cabinets(uid):
    conn = get_db_connection()
    if not conn: return []
    try:
        c = conn.cursor()
        c.execute("SELECT id, name, is_default FROM cabinets WHERE user_id = %s ORDER BY id", (uid,))
        return c.fetchall()
    except: return []
    finally: conn.close()

def get_user_inventory(uid):
    conn = get_db_connection()
    if not conn: return []
    try:
        c = conn.cursor()
        cab_id, _ = get_active_cabinet(uid)
        c.execute("SELECT medicine_name, quantity, dosage, expiry_date, category, storage FROM inventory WHERE user_id = %s AND cabinet_id = %s ORDER BY medicine_name", (uid, cab_id))
        return c.fetchall()
    except Exception as e: logger.error("Inv err: %s", e); return []
    finally: conn.close()

def get_user_family(uid):
    conn = get_db_connection()
    if not conn: return []
    try:
        c = conn.cursor()
        c.execute("SELECT name, age, gender, relation FROM family WHERE user_id = %s", (uid,))
        return c.fetchall()
    except: return []
    finally: conn.close()

# === Subscription ===

def get_subscription(uid):
    conn = get_db_connection()
    if not conn: return {"plan": "free", "active": False, "trial": False, "days_left": 0}
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
            return {"plan": "paid", "active": True, "trial": False, "days_left": (expires - now).days}
        if plan == "trial" and expires and expires > now:
            return {"plan": "trial", "active": True, "trial": True, "days_left": (expires - now).days}
        return {"plan": "expired", "active": False, "trial": trial_used, "days_left": 0}
    except Exception as e: logger.error("Sub err: %s", e); return {"plan": "free", "active": False, "trial": False, "days_left": 0}
    finally: conn.close()

def activate_subscription(uid, days, payment_id=None):
    conn = get_db_connection()
    if not conn: return False
    try:
        c = conn.cursor()
        from datetime import datetime, timedelta
        now = datetime.now(); expires = now + timedelta(days=days)
        c.execute("INSERT INTO subscriptions (user_id, plan, started_at, expires_at, trial_used, payment_id) VALUES (%s, 'paid', %s, %s, TRUE, %s) ON CONFLICT (user_id) DO UPDATE SET plan='paid', started_at=%s, expires_at=%s, trial_used=TRUE, payment_id=%s", (uid, now, expires, payment_id, now, expires, payment_id))
        conn.commit(); return True
    except Exception as e: logger.error("Activate err: %s", e); return False
    finally: conn.close()

def check_promo(code_text):
    conn = get_db_connection()
    if not conn: return None
    try:
        c = conn.cursor()
        c.execute("SELECT id, code, action, discount_percent, free_days, max_uses, used_count FROM promo_codes WHERE UPPER(code) = UPPER(%s) AND active = TRUE", (code_text,))
        row = c.fetchone()
        if not row: return None
        if row[5] > 0 and row[6] >= row[5]: return None
        return {"id": row[0], "code": row[1], "action": row[2], "discount": row[3], "free_days": row[4]}
    except: return None
    finally: conn.close()

def use_promo(uid, promo_id):
    conn = get_db_connection()
    if not conn: return False
    try:
        c = conn.cursor()
        c.execute("SELECT id FROM promo_usage WHERE user_id = %s AND promo_id = %s", (uid, promo_id))
        if c.fetchone(): return False
        c.execute("INSERT INTO promo_usage (user_id, promo_id) VALUES (%s, %s)", (uid, promo_id))
        c.execute("UPDATE promo_codes SET used_count = used_count + 1 WHERE id = %s", (promo_id,))
        conn.commit(); return True
    except: return False
    finally: conn.close()

def create_yukassa_payment(uid, amount, description="Подписка НеБолит на 1 год"):
    import uuid
    auth = base64.b64encode(("%s:%s" % (YUKASSA_SHOP_ID, YUKASSA_SECRET_KEY)).encode()).decode()
    body = json.dumps({"amount": {"value": str(amount), "currency": "RUB"}, "confirmation": {"type": "redirect", "return_url": "https://t.me/NeBolitBot"}, "capture": True, "description": description, "metadata": {"user_id": str(uid)}})
    req = urllib.request.Request("https://api.yookassa.ru/v3/payments", data=body.encode(), headers={"Content-Type": "application/json", "Authorization": "Basic " + auth, "Idempotence-Key": str(uuid.uuid4())})
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
            finally: conn.close()
        return payment_id, pay_url
    except Exception as e: logger.error("YuKassa err: %s", e); return None, None

# === Voice & Photo ===

def process_voice(voice_bytes):
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp.write(voice_bytes); tmp_path = tmp.name
        with open(tmp_path, "rb") as af:
            transcript = client.audio.transcriptions.create(model="whisper-1", file=af, language="ru")
        os.unlink(tmp_path)
        return transcript.text.strip()
    except Exception as e: logger.error("Whisper err: %s", e); return ""

def process_photo_vision(photo_bytes):
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    try:
        b64 = base64.b64encode(photo_bytes).decode("utf-8")
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role":"user","content":[{"type":"text","text":"На фото упаковка лекарства. Определи название, действующее вещество, дозировку, срок годности, показания, категорию. Также определи условия хранения: если лекарство требует хранения в холодильнике (2-8°C) — укажи ХОЛОДИЛЬНИК, иначе — КОМНАТНАЯ. Кратко."},{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+b64}}]}], max_tokens=500)
        return resp.choices[0].message.content
    except Exception as e: logger.error("Vision err: %s", e); return ""

# === GPT ===

SYSTEM_PROMPT = """Ты умный и дружелюбный помощник по домашней аптечке бот НеБолит. Задачи: хранить список лекарств, подсказывать что принять, учитывать семью, предлагать пополнить аптечку, собирать мини-аптечку для поездок, следить за сроками годности, создавать напоминания о приёме лекарств. При рекомендациях что принять - советуй из аптечки, если нет нужного - скажи что стоит купить. Предупреждай что не замена врачу. Отвечай на русском кратко и дружелюбно.

Команды:
[ADD_MEDICINE:название|количество|дозировка|срок|категория|хранение] - добавить лекарство.
Поле хранение: ХОЛОДИЛЬНИК или КОМНАТНАЯ. Определяй сам на основе знаний о лекарстве. Лекарства, требующие холодильника: инсулин, свечи (суппозитории), многие глазные капли, вакцины, интерфероны, некоторые мази, живые пробиотики (Линекс, Бифидумбактерин), Виферон свечи, оксолиновая мазь и др. Если сомневаешься — ставь КОМНАТНАЯ.

КАТЕГОРИИ определяй сам: ТЕМПЕРАТУРА, БОЛЬ, ЖИВОТ, РАНЫ, РАЗНОЕ. НИКОГДА не спрашивай категорию.
[REMOVE_MEDICINE:название] - удалить лекарство.
[REMOVE_FAMILY:имя] - удалить члена семьи.
[ADD_FAMILY:имя|возраст|пол|отношение] - добавить семью.
[ADD_REMINDER:член_семьи|лекарство|время_приёма|до/после/во_время еды|дозировка|дней_курса|таблеток_за_приём|таблеток_в_пачке] - напоминание. Бессрочно = дней_курса 0.
[CREATE_CABINET:название] - создать аптечку.
[SWITCH_CABINET:название] - переключить.
[SHARE_ACCESS:@username|отношение] - поделиться.

При добавлении лекарства: определи правильное название, стандартную дозировку если не указана, категорию сам, условия хранения сам.
СТРОГАЯ ПРОВЕРКА СРОКОВ: сравнивай с текущей датой. Просрочено — НЕ добавляй, предупреди. Менее 2 месяцев — предупреди. Годно — зелёная галочка. Формат срока: ГГГГ-ММ-ДД или ГГГГ-ММ.
НИКОГДА не подставляй шаблонные значения.

КРИТИЧЕСКИ ВАЖНО: Когда пользователь просит добавить лекарство (текстом, голосом или фото) — ты ОБЯЗАН включить команду [ADD_MEDICINE:...] в свой ответ. Без этой команды лекарство НЕ будет добавлено в аптечку! Всегда используй команды в квадратных скобках. Пример: [ADD_MEDICINE:Нурофен|1|400 мг|2027-01|БОЛЬ|КОМНАТНАЯ]

Аналогично для удаления ОБЯЗАТЕЛЬНО используй [REMOVE_MEDICINE:название].
Для добавления члена семьи ОБЯЗАТЕЛЬНО используй [ADD_FAMILY:имя|возраст|пол|отношение]. Пример: [ADD_FAMILY:Анна|30|Ж|жена]
Для напоминаний ОБЯЗАТЕЛЬНО используй [ADD_REMINDER:...].
НИКОГДА не используй шаблонные значения типа "имя", "возраст", "пол", "отношение" - только реальные данные от пользователя!"""

def generate_gpt_response(uid, user_text):
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    history = get_user_history(uid, limit=20)
    inventory = get_user_inventory(uid)
    family = get_user_family(uid)
    inv_text = "Аптечка пуста."
    if inventory:
        inv_lines = []
        for m in inventory:
            storage_info = ""
            if m[5] and m[5].strip():
                storage_info = ", хранение: %s" % m[5]
            inv_lines.append("- %s, кол-во: %s, дозировка: %s, годен до: %s, категория: %s%s" % (m[0], m[1], m[2] or "?", m[3] or "?", m[4] or "?", storage_info))
        inv_text = "\n".join(inv_lines)
    fam_text = "Семья не указана."
    if family:
        fam_text = "\n".join(["- %s, %s лет, %s, %s" % (f[0], f[1], f[2], f[3]) for f in family])
    from datetime import date as _date
    cab_id, cab_name = get_active_cabinet(uid)
    cab_text = "Сегодня: %s. Текущая аптечка: %s" % (_date.today().isoformat(), cab_name)
    cabs = get_user_cabinets(uid)
    if cabs:
        cab_text += ". Все аптечки: " + ", ".join([c[1] for c in cabs])
    rem_text = "Напоминаний нет."
    conn2 = get_db_connection()
    if conn2:
        try:
            c2 = conn2.cursor()
            c2.execute("SELECT family_member, medicine_name, dosage, schedule_time, meal_relation, course_days FROM reminders WHERE user_id = %s AND active = TRUE", (uid,))
            rems = c2.fetchall()
            if rems:
                rlines = []
                for r in rems:
                    course_str = "бессрочно" if (r[5] == 0 or r[5] is None) else "%s дней" % r[5]
                    rlines.append("- %s %s, приём: %s %s, курс: %s" % (r[1], ("для "+r[0]) if r[0] else "", r[3], r[4] or "", course_str))
                rem_text = "\n".join(rlines)
        except: pass
        finally: conn2.close()
    ctx = cab_text + "\nАптечка:\n" + inv_text + "\nСемья:\n" + fam_text + "\nНапоминания:\n" + rem_text
    messages = [{"role":"system","content":SYSTEM_PROMPT},{"role":"system","content":ctx}]
    messages.extend(history)
    messages.append({"role":"user","content":user_text})
    try:
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=messages, max_tokens=1000, temperature=0.7)
        reply = resp.choices[0].message.content
        # Если GPT не включил команду ADD_MEDICINE но явно добавляет лекарство
        family_words = ["семь", "член", "сын", "дочь", "муж", "жен", "мам", "пап", "бабушк", "дедушк", "ребён", "ребен", "брат", "сестр"]
        is_family_context = any(w in reply.lower() for w in family_words)
        if "[ADD_MEDICINE:" not in reply and not is_family_context and any(w in reply.lower() for w in ["добавляю", "добавил", "добавлено", "записал", "внесл"]):
            # Проверяем что это именно лекарство (есть дозировка или мед. термины)
            med_indicators = ["мг", "мл", "табл", "капсул", "дозировк", "годност", "срок", "категори", "аптечк"]
            if any(ind in reply.lower() for ind in med_indicators):
                logger.info("GPT forgot ADD_MEDICINE command, attempting fallback parse")
                import re as _re
                name_match = _re.search(r'\*\*(.+?)\*\*', reply)
                if name_match:
                    med_name = name_match.group(1)
                    dose_match = _re.search(r'дозировк[аи]:?\s*([\d,.]+ ?(?:мг|мл|г|мкг|%|МЕ))', reply, _re.IGNORECASE)
                    dose = dose_match.group(1) if dose_match else ""
                    exp_match = _re.search(r'(?:годност|срок)[а-яё]*:?\s*(\d{4}[-./]\d{2}(?:[-./]\d{2})?)', reply, _re.IGNORECASE)
                    exp = exp_match.group(1) if exp_match else ""
                    cat = "РАЗНОЕ"
                    for c_name in ["ТЕМПЕРАТУРА", "БОЛЬ", "ЖИВОТ", "РАНЫ"]:
                        if c_name.lower() in reply.lower() or c_name in reply:
                            cat = c_name
                            break
                    storage = "ХОЛОДИЛЬНИК" if "холодильник" in reply.lower() else "КОМНАТНАЯ"
                    cmd = "[ADD_MEDICINE:%s|1|%s|%s|%s|%s]" % (med_name, dose, exp, cat, storage)
                    logger.info("Fallback ADD command: %s", cmd)
                    reply += "\n" + cmd
        # Если GPT не включил команду ADD_FAMILY но явно добавляет члена семьи
        if "[ADD_FAMILY:" not in reply and any(w in reply.lower() for w in ["добавил", "добавила", "записал", "добавляю", "внёс", "внес"]):
            if any(w in reply.lower() for w in ["семь", "член", "родствен", "ребён", "ребен", "муж", "жен", "сын", "дочь", "мам", "пап", "бабушк", "дедушк"]):
                logger.info("GPT forgot ADD_FAMILY command, checking text")
                import re as _re2
                # Ищем имя в жирном
                name_m = _re2.search(r'\*\*(.+?)\*\*', reply)
                if name_m:
                    fam_name = name_m.group(1)
                    age_m = _re2.search(r'(\d+)\s*(?:лет|год|года)', reply)
                    age = age_m.group(1) if age_m else ""
                    gender = ""
                    if any(w in reply.lower() for w in ["жена", "дочь", "мама", "бабушка", "сестра", "девочка"]): gender = "Ж"
                    elif any(w in reply.lower() for w in ["муж", "сын", "папа", "дедушка", "брат", "мальчик"]): gender = "М"
                    relation = ""
                    for rel_word, rel_val in [("жена","жена"),("муж","муж"),("сын","сын"),("дочь","дочь"),("мама","мама"),("папа","папа"),("бабушка","бабушка"),("дедушка","дедушка"),("брат","брат"),("сестра","сестра"),("ребёнок","ребёнок"),("ребенок","ребёнок")]:
                        if rel_word in reply.lower():
                            relation = rel_val
                            break
                    cmd = "[ADD_FAMILY:%s|%s|%s|%s]" % (fam_name, age, gender, relation)
                    logger.info("Fallback FAMILY command: %s", cmd)
                    reply += "\n" + cmd

        process_gpt_commands(uid, reply)
        return clean_commands(reply)
    except Exception as e: logger.error("GPT err: %s", e); return "Ошибка связи с ИИ."

ADD_MED_RE = r"\[ADD_MEDICINE:(.+?)\]"
REM_MED_RE = r"\[REMOVE_MEDICINE:(.+?)\]"
ADD_FAM_RE = r"\[ADD_FAMILY:(.+?)\]"
ADD_REM_RE = r"\[ADD_REMINDER:(.+?)\]"
SHARE_RE = r"\[SHARE_ACCESS:(.+?)\]"
CABINET_CREATE_RE = r"\[CREATE_CABINET:(.+?)\]"
CABINET_SWITCH_RE = r"\[SWITCH_CABINET:(.+?)\]"
REM_FAM_RE = r"\[REMOVE_FAMILY:(.+?)\]"
REM_FAM_RE = r"\[REMOVE_FAMILY:(.+?)\]"

def process_gpt_commands(uid, text):
    conn = get_db_connection()
    if not conn: return
    try:
        c = conn.cursor()
        for med in re.findall(ADD_MED_RE, text):
            parts = [p.strip() for p in med.split("|")]
            name = parts[0] if len(parts) > 0 else ""
            qty = 1
            if len(parts) > 1:
                try: qty = int(parts[1])
                except: qty = 1
            dosage = parts[2] if len(parts) > 2 else None
            expiry = parts[3] if len(parts) > 3 else None
            category = parts[4] if len(parts) > 4 else None
            storage = parts[5] if len(parts) > 5 else ""
            if name:
                status, _ = check_expiry(expiry or "")
                if status == "expired":
                    continue
                cab_id, _ = get_active_cabinet(uid)
                exp_date = None
                if expiry and expiry.strip() and expiry.strip() != "?":
                    try:
                        if re.match(r"^\d{4}-\d{2}-\d{2}$", expiry.strip()):
                            exp_date = expiry.strip()
                        elif re.match(r"^\d{4}-\d{2}$", expiry.strip()):
                            exp_date = expiry.strip() + "-28"
                    except: exp_date = None
                c.execute("INSERT INTO inventory (user_id, medicine_name, quantity, dosage, expiry_date, category, cabinet_id, storage) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (uid, name, qty, dosage, exp_date, category, cab_id, storage or ""))
        for name in re.findall(REM_MED_RE, text):
            c.execute("DELETE FROM inventory WHERE user_id = %s AND LOWER(medicine_name) = LOWER(%s)", (uid, name.strip()))
        for fam in re.findall(ADD_FAM_RE, text):
            parts = [p.strip() for p in fam.split("|")]
            name = parts[0] if len(parts) > 0 else ""
            age = None
            if len(parts) > 1:
                try: age = int(parts[1])
                except: age = None
            gender = parts[2] if len(parts) > 2 else None
            relation = parts[3] if len(parts) > 3 else None
            # Проверка на шаблонные значения
            bad_values = ['имя', 'name', 'test', 'член_семьи', 'member', 'пол', 'gender', 'отношение', 'relation', 'возраст']
            if name and name.lower() not in bad_values:
                if gender and gender.lower() in bad_values: gender = None
                if relation and relation.lower() in bad_values: relation = None
                # Проверяем дубликат
                c.execute("SELECT id FROM family WHERE user_id = %s AND LOWER(name) = LOWER(%s)", (uid, name))
                existing = c.fetchone()
                if existing:
                    c.execute("UPDATE family SET age=%s, gender=%s, relation=%s WHERE id=%s", (age, gender, relation, existing[0]))
                    logger.info("Updated family member: %s for user %s", name, uid)
                else:
                    c.execute("INSERT INTO family (user_id, name, age, gender, relation) VALUES (%s,%s,%s,%s,%s)", (uid, name, age, gender, relation))
                    logger.info("Added family member: %s for user %s", name, uid)
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
                elif cab_name.lower() in ("моя аптечка", "своя", "моя", "основная"):
                    c.execute("INSERT INTO user_state (user_id, active_cabinet_id) VALUES (%s, 0) ON CONFLICT (user_id) DO UPDATE SET active_cabinet_id = 0", (uid,))
        for fam_del in re.findall(REM_FAM_RE, text):
            fname = fam_del.strip()
            if fname:
                c.execute("DELETE FROM family WHERE user_id = %s AND LOWER(name) = LOWER(%s)", (uid, fname))
                logger.info("Deleted family member: %s for user %s", fname, uid)

        for fam_del in re.findall(REM_FAM_RE, text):
            fname = fam_del.strip()
            if fname:
                c.execute("DELETE FROM family WHERE user_id = %s AND LOWER(name) = LOWER(%s)", (uid, fname))
                logger.info("Deleted family member: %s for user %s", fname, uid)

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
                try: course_days = int(parts[5])
                except: course_days = 0
            pills_per_dose = 1.0
            if len(parts) > 6:
                try: pills_per_dose = float(parts[6])
                except: pills_per_dose = 1.0
            pills_in_pack = 0
            if len(parts) > 7:
                try: pills_in_pack = int(parts[7])
                except: pills_in_pack = 0
            if medicine:
                from datetime import date, timedelta
                start = date.today()
                end = start + timedelta(days=course_days) if course_days > 0 else None
                times_per_day = len(schedule.split(","))
                total_pills = course_days * times_per_day * pills_per_dose if course_days > 0 else 0
                c.execute("INSERT INTO reminders (user_id, family_member, medicine_name, dosage, schedule_time, meal_relation, course_days, pills_per_dose, pills_in_pack, pills_remaining, start_date, end_date, active) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)", (uid, member, medicine, dosage, schedule, meal, course_days, pills_per_dose, pills_in_pack, total_pills, start, end))
        conn.commit()
    except Exception as e:
        logger.error("Cmd err: %s", e, exc_info=True)
        try: conn.rollback()
        except: pass
    finally: conn.close()

def clean_commands(text):
    for rx in [ADD_MED_RE, REM_MED_RE, ADD_FAM_RE, ADD_REM_RE, SHARE_RE, CABINET_CREATE_RE, CABINET_SWITCH_RE, REM_FAM_RE]:
        text = re.sub(rx, "", text)
    return text.strip()

# === Telegram ===

def tg_api(method, data=None):
    url = "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/" + method
    if data:
        req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers={"Content-Type":"application/json"})
    else:
        req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e: logger.error("TG err: %s", e); return None

def tg_send(chat_id, text):
    html_text = md_to_html(text)
    try:
        result = tg_api("sendMessage", {"chat_id": chat_id, "text": html_text, "parse_mode": "HTML"})
        if not result or not result.get("ok"):
            return tg_api("sendMessage", {"chat_id": chat_id, "text": text})
        return result
    except:
        return tg_api("sendMessage", {"chat_id": chat_id, "text": text})

def tg_send_with_menu(chat_id, text):
    keyboard = {"keyboard": [
        [{"text": "\U0001f3e0 Старт"}, {"text": "\U0001f4e6 Моя аптечка"}],
        [{"text": "\U0001f48a Курсы приёма"}, {"text": "\U0001f468\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466 Семья"}],
        [{"text": "\U0001f3e5 Другие аптечки"}]
    ], "resize_keyboard": True, "one_time_keyboard": False}
    html_text = md_to_html(text)
    try:
        result = tg_api("sendMessage", {"chat_id": chat_id, "text": html_text, "parse_mode": "HTML", "reply_markup": keyboard})
        if not result or not result.get("ok"):
            return tg_api("sendMessage", {"chat_id": chat_id, "text": text, "reply_markup": keyboard})
        return result
    except:
        return tg_api("sendMessage", {"chat_id": chat_id, "text": text, "reply_markup": keyboard})

def tg_send_start_button(chat_id):
    keyboard = {"keyboard": [[{"text": "\U0001f4aa Навести порядок"}]], "resize_keyboard": True, "one_time_keyboard": True}
    return tg_api("sendMessage", {"chat_id": chat_id, "text": "\U0001f48a Добро пожаловать в НеБолит!\n\nНажми кнопку ниже, чтобы начать \U0001f447", "reply_markup": keyboard})

def tg_get_file_bytes(file_id):
    result = tg_api("getFile", {"file_id": file_id})
    if result and result.get("ok"):
        fp = result["result"]["file_path"]
        url = "https://api.telegram.org/file/bot" + TELEGRAM_TOKEN + "/" + fp
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.read()
    return None

def tg_delete_message(chat_id, message_id):
    try:
        tg_api("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
    except: pass

def cleanup_recognition_messages(chat_id):
    try:
        result = tg_api("getUpdates", {"offset": -10, "limit": 10})
        if not result or not result.get("ok"):
            return
        bot_info = tg_api("getMe")
        if not bot_info or not bot_info.get("ok"):
            return
        bot_id = bot_info["result"]["id"]
        for upd in result.get("result", []):
            msg = upd.get("message")
            if not msg:
                continue
            if msg.get("chat", {}).get("id") != chat_id:
                continue
            if msg.get("from", {}).get("id") != bot_id:
                continue
            text = msg.get("text", "")
            if text.startswith("Распознано:") or text.startswith("Анализирую фото"):
                tg_delete_message(chat_id, msg["message_id"])
    except Exception as e:
        logger.error("Cleanup err: %s", e)

# === Admin stats ===

def handle_admin(chat_id):
    conn_a = get_db_connection()
    if not conn_a: tg_send(chat_id, "Ошибка БД"); return
    try:
        ca = conn_a.cursor()
        ca.execute("SELECT COUNT(*) FROM users"); total_users = ca.fetchone()[0]
        ca.execute("SELECT COUNT(*) FROM users WHERE created_at >= CURRENT_DATE"); new_today = ca.fetchone()[0]
        ca.execute("SELECT COUNT(*) FROM users WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'"); new_week = ca.fetchone()[0]
        ca.execute("SELECT COUNT(*) FROM messages"); total_msgs = ca.fetchone()[0]
        ca.execute("SELECT COUNT(DISTINCT user_id) FROM messages"); active_users = ca.fetchone()[0]
        avg_msgs = round(total_msgs / active_users, 1) if active_users > 0 else 0
        ca.execute("SELECT COUNT(*) FROM messages WHERE timestamp >= CURRENT_DATE"); msgs_today = ca.fetchone()[0]
        ca.execute("SELECT COUNT(*) FROM inventory"); total_meds = ca.fetchone()[0]
        ca.execute("SELECT COUNT(DISTINCT user_id) FROM inventory"); users_with_meds = ca.fetchone()[0]
        avg_meds = round(total_meds / users_with_meds, 1) if users_with_meds > 0 else 0
        ca.execute("SELECT medicine_name, COUNT(*) as cnt FROM inventory GROUP BY medicine_name ORDER BY cnt DESC LIMIT 5"); top_meds = ca.fetchall()
        top_str = "\n".join(["  %s (%s)" % (m[0], m[1]) for m in top_meds]) if top_meds else "  нет"
        ca.execute("SELECT COUNT(*) FROM reminders WHERE active = TRUE"); active_rem = ca.fetchone()[0]
        ca.execute("SELECT COUNT(*) FROM family"); total_family = ca.fetchone()[0]
        ca.execute("SELECT COUNT(*) FROM cabinets"); total_cabs = ca.fetchone()[0]
        ca.execute("SELECT plan, COUNT(*) FROM subscriptions GROUP BY plan"); sub_stats = dict(ca.fetchall())
        ca.execute("SELECT COUNT(*) FROM payments WHERE status = 'succeeded'"); paid_payments = ca.fetchone()[0]
        ca.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'succeeded'"); total_revenue = ca.fetchone()[0]
        ca.execute("SELECT code, used_count, max_uses, discount_percent, free_days, action FROM promo_codes WHERE active = TRUE"); promos = ca.fetchall()
        promo_str = "  нет активных"
        if promos:
            pl = []
            for p in promos:
                info = "%s: %s/%s исп." % (p[0], p[1], p[2] if p[2] > 0 else "\u221e")
                if p[5] == "discount": info += " (-%s%%)" % p[3]
                elif p[5] == "free_days": info += " (+%s дн.)" % p[4]
                elif p[5] == "full_free": info += " (бесплатно)"
                pl.append("  " + info)
            promo_str = "\n".join(pl)
        stat = "\U0001f4ca Статистика НеБолит\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n\U0001f465 Пользователи: %s (сегодня +%s, неделя +%s)\n\U0001f4ac Сообщения: %s (сегодня %s, средн. %s/юзер)\n\U0001f48a Лекарств: %s (у %s юзеров, средн. %s)\n\U0001f3c6 Топ-5:\n%s\n\n\U0001f4cb Напоминаний: %s | Семья: %s | Аптечек: %s\n\n\U0001f4b3 Trial: %s | Paid: %s | Expired: %s\n\U0001f4b0 Платежей: %s | Выручка: %s \u20bd\n\n\U0001f3ab Промокоды:\n%s" % (total_users, new_today, new_week, total_msgs, msgs_today, avg_msgs, total_meds, users_with_meds, avg_meds, top_str, active_rem, total_family, total_cabs, sub_stats.get("trial", 0), sub_stats.get("paid", 0), sub_stats.get("expired", 0), paid_payments, total_revenue, promo_str)
        tg_send(chat_id, stat)
    except Exception as e: tg_send(chat_id, "Ошибка: %s" % str(e))
    finally: conn_a.close()

# === Main handler ===

def handle_update(data):
    msg = data.get("message")
    if not msg:
        return
    chat_id = msg["chat"]["id"]
    uid = msg["from"]["id"]
    uname = msg["from"].get("username") or msg["from"].get("first_name") or ""
    voice_msg_id = None
    photo_msg_id = None

    # Check if new user
    conn_check = get_db_connection()
    is_new = False
    if conn_check:
        try:
            c_check = conn_check.cursor()
            c_check.execute("SELECT COUNT(*) FROM messages WHERE user_id = %s", (uid,))
            if c_check.fetchone()[0] == 0:
                is_new = True
        except: pass
        finally: conn_check.close()

    save_user(uid, uname)

    # Extract user_text from voice/photo/text
    user_text = ""
    recognition_msg_ids = []

    if "voice" in msg:
        vb = tg_get_file_bytes(msg["voice"]["file_id"])
        if vb:
            t = process_voice(vb)
            if t:
                user_text = t
                result = tg_send(chat_id, "\U0001f3a4 Распознано: " + t)
                if result and result.get("ok"):
                    recognition_msg_ids.append(result["result"]["message_id"])
            else:
                tg_send(chat_id, "Не удалось распознать голос."); return
        else:
            tg_send(chat_id, "Не удалось скачать голосовое."); return
    elif "photo" in msg:
        pb = tg_get_file_bytes(msg["photo"][-1]["file_id"])
        if pb:
            result = tg_send(chat_id, "\U0001f50d Анализирую фото...")
            if result and result.get("ok"):
                recognition_msg_ids.append(result["result"]["message_id"])
            vt = process_photo_vision(pb)
            if vt:
                user_text = "Сфотографировал упаковку лекарства:\n" + vt
                cap = msg.get("caption", "")
                if cap: user_text += "\nКомментарий: " + cap
            else:
                tg_send(chat_id, "Не удалось распознать фото."); return
        else:
            tg_send(chat_id, "Не удалось скачать фото."); return
    elif "text" in msg:
        user_text = msg["text"]
    else:
        return

    # Map buttons to commands
    button_map = {
        "\U0001f3e0 Старт": "/start",
        "\U0001f4aa Навести порядок": "/start",
        "\U0001f4e6 Моя аптечка": "/inventory",
        "\U0001f48a Курсы приёма": "/reminders",
        "\U0001f468\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466 Семья": "/family",
        "\U0001f3e5 Другие аптечки": "/cabinets",
        "\U0001f4e6 Аптечка": "/inventory",
        "\U0001f3e0 Аптечки": "/cabinets",
    }
    if user_text in button_map:
        user_text = button_map[user_text]

    # Show start button for brand new users
    if is_new and user_text != "/start":
        tg_send_start_button(chat_id)
        return

    # Admin - no restrictions
    if user_text.strip() == "/admin" and uid == ADMIN_ID:
        handle_admin(chat_id)
        return

    # Subscription check
    if uid == ADMIN_ID:
        sub = {"plan": "paid", "active": True, "trial": False, "days_left": 999}
    else:
        sub = get_subscription(uid)

    # Promo codes (NB-xxx or NEBOLITxxx)
    upper_text = user_text.strip().upper()
    if upper_text.startswith("NB-") or upper_text.startswith("NEBOLIT"):
        promo = check_promo(user_text.strip())
        if promo:
            if not use_promo(uid, promo["id"]):
                tg_send(chat_id, "\u274c Вы уже использовали этот промокод."); return
            if promo["action"] == "discount":
                price = int(SUBSCRIPTION_PRICE * (100 - promo["discount"]) / 100)
                pid, pay_url = create_yukassa_payment(uid, price, "НеБолит (скидка %s%%)" % promo["discount"])
                if pay_url:
                    conn_pr = get_db_connection()
                    if conn_pr:
                        try:
                            c_pr = conn_pr.cursor()
                            c_pr.execute("UPDATE payments SET promo_code=%s, discount_percent=%s WHERE payment_id=%s", (promo["code"], promo["discount"], pid))
                            conn_pr.commit()
                        finally: conn_pr.close()
                    tg_send(chat_id, "\U0001f389 Промокод принят! Скидка %s%%\n\U0001f4b0 Цена: %s \u20bd (вместо %s \u20bd)\n\n\U0001f449 Оплатите:\n%s" % (promo["discount"], price, SUBSCRIPTION_PRICE, pay_url))
                else:
                    tg_send(chat_id, "\u274c Ошибка создания платежа.")
                return
            elif promo["action"] == "free_days":
                activate_subscription(uid, promo["free_days"])
                tg_send(chat_id, "\U0001f389 Промокод принят! +%s дней доступа!" % promo["free_days"]); return
            elif promo["action"] == "full_free":
                activate_subscription(uid, 365)
                tg_send(chat_id, "\U0001f389 Промокод принят! Подписка на год активирована!"); return

    # /subscribe
    if user_text.strip() == "/subscribe":
        if sub["active"] and sub["plan"] == "paid":
            tg_send(chat_id, "\u2705 Подписка активна! Осталось %s дней." % sub["days_left"]); return
        pid, pay_url = create_yukassa_payment(uid, SUBSCRIPTION_PRICE)
        if pay_url:
            tg_send(chat_id, "\U0001f48a Подписка НеБолит \u2014 1 год\n\U0001f4b0 Стоимость: %s \u20bd\n\n\U0001f449 Оплатите:\n%s\n\nДоступ активируется автоматически!" % (SUBSCRIPTION_PRICE, pay_url))
        else:
            tg_send(chat_id, "\u274c Ошибка создания платежа.")
        return

    # /status
    if user_text.strip() == "/status":
        if sub["plan"] == "paid":
            tg_send(chat_id, "\u2705 Подписка активна! Осталось %s дней." % sub["days_left"])
        elif sub["plan"] == "trial":
            tg_send(chat_id, "\U0001f552 Пробный период \u2014 %s дней. /subscribe для оплаты" % sub["days_left"])
        else:
            tg_send(chat_id, "\u274c Подписка неактивна. /subscribe для оплаты")
        return

    # Block paid features if not active
    if not sub["active"]:
        free_words = ["что такое", "для чего", "от чего", "зачем", "описание", "инструкция", "побочные", "аналог", "что принять", "что выпить", "болит", "температура", "кашель", "насморк", "тошнит", "голова"]
        is_free = any(w in user_text.lower() for w in free_words)
        if not is_free and user_text.strip() != "/start":
            tg_send(chat_id, "\U0001f512 Эта функция доступна по подписке.\n\nБесплатно: справки о лекарствах и советы при недомогании.\nПолный доступ: /subscribe")
            return

    # === Commands ===

    if user_text.strip() == "/start":
        welcome = ("\U0001f48a Привет! Я бот НеБолит \u2014 твой помощник по домашней аптечке.\n\n"
            "\u2728 Что я умею:\n\n"
            "\U0001f4e6 Аптечка \u2014 храню лекарства с дозировками и сроками\n"
            "\U0001f4f7 Фото \u2014 сфотографируй упаковку, я распознаю\n"
            "\U0001f3a4 Голос \u2014 наговори что есть в аптечке\n"
            "\U0001f912 Что принять? \u2014 подскажу из твоей аптечки\n"
            "\U0001f468\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466 Семья \u2014 учитываю возраст и особенности\n"
            "\u23f0 Напоминания \u2014 курс от врача\n"
            "\U0001f4c5 Сроки \u2014 слежу за годностью\n"
            "\u2744\ufe0f Хранение \u2014 подскажу что держать в холодильнике\n"
            "\U0001f9f3 В дорогу \u2014 соберу аптечку\n\n"
            "\U0001f4cc /inventory \u2014 аптечка | /family \u2014 семья\n"
            "/reminders \u2014 напоминания | /cabinets \u2014 аптечки\n"
            "/subscribe \u2014 подписка | /status \u2014 статус\n\n"
            "\u27a1\ufe0f Начни \u2014 напиши, отправь фото или голосовое!")
        if sub["plan"] == "paid":
            welcome += "\n\n\u2705 Подписка активна (%s дн.)" % sub["days_left"]
        elif sub["plan"] == "trial":
            welcome += "\n\n\U0001f552 Пробный период (%s дн.)" % sub["days_left"]
        else:
            welcome += "\n\n\U0001f512 Подписка неактивна. /subscribe"
        tg_send_with_menu(chat_id, welcome)
        return

    if user_text.strip() == "/inventory":
        inv = get_user_inventory(uid)
        cab_id_d, cab_name_d = get_active_cabinet(uid)
        if inv:
            lines = ["\U0001f4e6 %s:\n" % cab_name_d]
            fridge_items = []
            for i, m in enumerate(inv, 1):
                exp_str = ""
                if m[3]:
                    status, _ = check_expiry(str(m[3]))
                    if status == "expired": exp_str = " \u274c ПРОСРОЧЕНО!"
                    elif status == "soon": exp_str = " \u26a0\ufe0f скоро истекает"
                    else: exp_str = " (до %s)" % m[3]
                cat = " [%s]" % m[4] if m[4] else ""
                storage_icon = ""
                if m[5] and "ХОЛОД" in str(m[5]).upper():
                    storage_icon = " \u2744\ufe0f"
                    fridge_items.append(m[0])
                lines.append("%d. %s \u2014 %s шт., %s%s%s%s" % (i, m[0], m[1], m[2] or "?", exp_str, cat, storage_icon))
            if fridge_items:
                lines.append("\n\u2744\ufe0f В холодильнике: %s" % ", ".join(fridge_items))
            tg_send(chat_id, "\n".join(lines))
        else:
            tg_send(chat_id, "\U0001f4e6 %s пуста.\n\nДобавьте лекарства текстом, фото или голосом!" % cab_name_d)
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
                        if r[0]: line += " (для %s)" % r[0]
                        line += "\n   \u23f0 %s" % r[3]
                        if r[4]: line += " %s" % r[4]
                        if r[2]: line += "\n   \U0001f4ca %s" % r[2]
                        if r[5] and r[5] > 0:
                            line += "\n   \U0001f4c5 Курс: %s дней (%s \u2014 %s)" % (r[5], r[6], r[7])
                        else:
                            line += "\n   \U0001f504 Бессрочный приём"
                        if r[8] and r[8] > 0:
                            line += "\n   \U0001f4a6 Осталось: %s табл." % int(r[8])
                        lines.append(line)
                    tg_send(chat_id, "\n".join(lines))
                else:
                    tg_send(chat_id, "Нет активных напоминаний.\n\nСкажите, например: \"Врач назначил амоксициллин 3 раза в день 7 дней\"")
            except Exception as e: logger.error("Rem err: %s", e); tg_send(chat_id, "Ошибка загрузки.")
            finally: conn.close()
        return

    if user_text.strip() == "/family":
        fam = get_user_family(uid)
        if fam:
            lines = ["\U0001f468\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466 Семья:\n"]
            for f in fam:
                age_str = "%s лет" % f[1] if f[1] else "возраст не указан"
                parts = [f[0], age_str]
                if f[2]: parts.append(f[2])
                if f[3]: parts.append(f[3])
                lines.append("- %s" % ", ".join(parts))
            tg_send(chat_id, "\n".join(lines))
        else:
            tg_send(chat_id, "\U0001f468\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466 Вы пока никого не добавили.\n\nНапишите, например: \"Моя жена Анна, 30 лет\"")
        return

    if user_text.strip() == "/cabinets":
        cabs = get_user_cabinets(uid)
        cab_id, cab_name = get_active_cabinet(uid)
        lines = ["\U0001f3e5 Ваши аптечки:\n"]
        if not cabs:
            lines.append("\U0001f4e6 Моя аптечка (по умолчанию) \u2705")
        else:
            for cb in cabs:
                mark = " \u2705" if cb[0] == cab_id else ""
                lines.append("\U0001f4e6 %s%s" % (cb[1], mark))
            if cab_id == 0:
                lines.append("\U0001f4e6 Моя аптечка (по умолчанию) \u2705")
        lines.append("\n\U0001f4ac Создать: \"Создай аптечку для мамы\"")
        lines.append("\U0001f504 Переключить: \"Переключи на аптечку мамы\"")
        tg_send(chat_id, "\n".join(lines))
        return

    # GPT response for everything else
    save_message(uid, "user", user_text)
    reply = generate_gpt_response(uid, user_text)
    save_message(uid, "assistant", reply)
    logger.info("GPT reply for %s: %s", uid, reply[:300])
    tg_send(chat_id, reply)

    # Cleanup recognition messages after response
    for mid in recognition_msg_ids:
        tg_delete_message(chat_id, mid)

# === Flask routes ===

@app.route("/yukassa", methods=["POST"])
def yukassa_webhook():
    try:
        data = flask_request.get_json(force=True)
        event = data.get("event", "")
        obj = data.get("object", {})
        if event == "payment.succeeded":
            payment_id = obj.get("id", "")
            metadata = obj.get("metadata", {})
            user_id = int(metadata.get("user_id", 0))
            if user_id and payment_id:
                activate_subscription(user_id, 365, payment_id)
                conn_p = get_db_connection()
                if conn_p:
                    try:
                        c_p = conn_p.cursor()
                        c_p.execute("UPDATE payments SET status='succeeded', confirmed_at=CURRENT_TIMESTAMP WHERE payment_id=%s", (payment_id,))
                        conn_p.commit()
                    finally: conn_p.close()
                tg_send(user_id, "\u2705 Оплата прошла! Подписка активирована на 1 год. Спасибо!")
    except Exception as e: logger.error("YuKassa webhook err: %s", e)
    return "ok", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = flask_request.get_json(force=True)
        logger.info("Update received")
        handle_update(data)
    except Exception as e: logger.error("Webhook err: %s", e)
    return "OK", 200

@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

@app.route("/cleanup_db", methods=["GET"])
def cleanup_db():
    conn = get_db_connection()
    if not conn:
        return "DB connection FAILED", 500
    try:
        c = conn.cursor()
        # Удалить не-лекарства из inventory
        c.execute("DELETE FROM inventory WHERE LOWER(medicine_name) IN ('лев', 'циньян', 'ян', 'анна')")
        inv_del = c.rowcount
        # Удалить дубли из family
        c.execute("""DELETE FROM family WHERE id NOT IN (
            SELECT MIN(id) FROM family GROUP BY user_id, LOWER(name)
        )""")
        fam_dedup = c.rowcount
        # Удалить шаблонные записи
        c.execute("DELETE FROM family WHERE LOWER(name) IN ('имя','name','test','член_семьи')")
        fam_tpl = c.rowcount
        conn.commit()
        return "Cleanup done. Inv removed: %s, Family deduped: %s, Family templates: %s" % (inv_del, fam_dedup, fam_tpl), 200
    except Exception as e:
        return "Error: %s" % str(e), 500
    finally:
        conn.close()

@app.route("/debug_db", methods=["GET"])
def debug_db():
    conn = get_db_connection()
    if not conn:
        return "DB connection FAILED", 500
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM messages")
        msgs = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM inventory")
        inv = c.fetchone()[0]
        c.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'inventory' ORDER BY ordinal_position")
        cols = c.fetchall()
        col_str = ", ".join(["%s(%s)" % (c[0], c[1]) for c in cols])
        c.execute("SELECT * FROM inventory ORDER BY id DESC LIMIT 3")
        recent = c.fetchall()
        c.execute("SELECT COUNT(*) FROM family")
        fam_count = c.fetchone()[0]
        c.execute("SELECT * FROM family ORDER BY id DESC LIMIT 10")
        fam_recent = c.fetchall()
        c.execute("SELECT content FROM messages WHERE content LIKE '%%ADD_FAMILY%%' ORDER BY id DESC LIMIT 5")
        fam_msgs = c.fetchall()
        return "DB OK. Users: %s, Msgs: %s, Inv: %s\nColumns: %s\nRecent inv: %s\n\nFamily: %s\nRecent fam: %s\nFam cmds in msgs: %s" % (users, msgs, inv, col_str, str(recent), fam_count, str(fam_recent), str(fam_msgs)), 200
    except Exception as e:
        return "DB error: %s" % str(e), 500
    finally:
        conn.close()

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
