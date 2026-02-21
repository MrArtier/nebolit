with open('bot.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Находим старый init_db и заменяем на новый с таблицей reminders
old_init = '''c.execute("CREATE TABLE IF NOT EXISTS family (id SERIAL PRIMARY KEY, user_id BIGINT, name TEXT NOT NULL, age INTEGER, gender TEXT, relation TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.commit()'''

new_init = '''c.execute("CREATE TABLE IF NOT EXISTS family (id SERIAL PRIMARY KEY, user_id BIGINT, name TEXT NOT NULL, age INTEGER, gender TEXT, relation TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS reminders (id SERIAL PRIMARY KEY, user_id BIGINT, family_member TEXT, medicine_name TEXT NOT NULL, dosage TEXT, schedule_time TEXT NOT NULL, meal_relation TEXT DEFAULT '', course_days INTEGER DEFAULT 0, pills_per_dose REAL DEFAULT 1, pills_in_pack INTEGER DEFAULT 0, pills_remaining REAL DEFAULT 0, start_date DATE, end_date DATE, active BOOLEAN DEFAULT TRUE, last_reminded TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS reminder_log (id SERIAL PRIMARY KEY, reminder_id INTEGER REFERENCES reminders(id), sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, status TEXT DEFAULT 'sent')")
        conn.commit()'''

text = text.replace(old_init, new_init)

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Step 1 done - DB tables added!')