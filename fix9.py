with open('bot.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Добавляем в init_db очистку мусорных записей
old_init_commit = '''        c.execute("CREATE TABLE IF NOT EXISTS reminder_log (id SERIAL PRIMARY KEY, reminder_id INTEGER REFERENCES reminders(id), sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, status TEXT DEFAULT 'sent')")
        conn.commit()'''

new_init_commit = '''        c.execute("CREATE TABLE IF NOT EXISTS reminder_log (id SERIAL PRIMARY KEY, reminder_id INTEGER REFERENCES reminders(id), sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, status TEXT DEFAULT 'sent')")
        c.execute("DELETE FROM reminders WHERE medicine_name IN ('лекарство','medicine','test') OR family_member IN ('член_семьи','member')")
        conn.commit()'''

text = text.replace(old_init_commit, new_init_commit)

# Подправим промпт - запретим шаблонные данные
old_end_prompt = 'Если лекарства нет в аптечке - всё равно создай напоминание и предупреди купить."'
new_end_prompt = 'Если лекарства нет в аптечке - всё равно создай напоминание и предупреди купить. НИКОГДА не подставляй шаблонные значения типа член_семьи/лекарство/время_приёма/дозировка - используй только реальные данные из сообщения пользователя. Если пользователь не указал для кого - оставь поле члена семьи пустым. Если не указал время - спроси."'

text = text.replace(old_end_prompt, new_end_prompt)

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Done!')