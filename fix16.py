with open('bot.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Добавляем таблицы в init_db перед reminder_log
old_reminder_log = '        c.execute("CREATE TABLE IF NOT EXISTS reminder_log'
new_reminder_log = '''        c.execute("CREATE TABLE IF NOT EXISTS subscriptions (id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL UNIQUE, plan TEXT DEFAULT 'free', started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, expires_at TIMESTAMP, trial_used BOOLEAN DEFAULT FALSE, payment_id TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS payments (id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL, payment_id TEXT UNIQUE, amount DECIMAL(10,2), status TEXT DEFAULT 'pending', promo_code TEXT, discount_percent INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, confirmed_at TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS promo_codes (id SERIAL PRIMARY KEY, code TEXT UNIQUE NOT NULL, action TEXT DEFAULT 'discount', discount_percent INTEGER DEFAULT 0, free_days INTEGER DEFAULT 0, max_uses INTEGER DEFAULT 0, used_count INTEGER DEFAULT 0, active BOOLEAN DEFAULT TRUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS promo_usage (id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL, promo_id INTEGER REFERENCES promo_codes(id), used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, promo_id))")
        c.execute("CREATE TABLE IF NOT EXISTS reminder_log'''
text = text.replace(old_reminder_log, new_reminder_log)

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Done fix16!')