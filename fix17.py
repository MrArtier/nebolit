with open('bot.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Добавляем YUKASSA_SHOP_ID и SECRET_KEY после OPENAI
old_openai_key = 'OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")'
new_openai_key = '''OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
YUKASSA_SHOP_ID = os.environ.get("YUKASSA_SHOP_ID", "")
YUKASSA_SECRET_KEY = os.environ.get("YUKASSA_SECRET_KEY", "")
SUBSCRIPTION_PRICE = 1490
TRIAL_DAYS = 7'''
text = text.replace(old_openai_key, new_openai_key)

# 2. Добавляем функции подписки перед get_active_cabinet
old_get_active = 'def get_active_cabinet(uid):'
new_get_active = '''def get_subscription(uid):
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

def get_active_cabinet(uid):'''
text = text.replace(old_get_active, new_get_active)

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Done fix17!')