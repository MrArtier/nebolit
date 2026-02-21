with open('bot.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Добавляем очистку мусора из family в init_db
old_clean = '''        c.execute("DELETE FROM reminders WHERE medicine_name IN ('лекарство','medicine','test') OR family_member IN ('член_семьи','member')")'''
new_clean = '''        c.execute("DELETE FROM reminders WHERE medicine_name IN ('лекарство','medicine','test') OR family_member IN ('член_семьи','member')")
        c.execute("DELETE FROM family WHERE name IN ('имя','name','test') OR gender IN ('пол','gender') OR relation IN ('отношение','relation')")'''
text = text.replace(old_clean, new_clean)

# 2. Добавляем таблицу shared_access для связки пользователей
old_reminder_log = '''        c.execute("CREATE TABLE IF NOT EXISTS reminder_log'''
new_reminder_log = '''        c.execute("CREATE TABLE IF NOT EXISTS shared_access (id SERIAL PRIMARY KEY, owner_id BIGINT NOT NULL, shared_with_id BIGINT NOT NULL, shared_with_username TEXT, relation TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(owner_id, shared_with_id))")
        c.execute("CREATE TABLE IF NOT EXISTS reminder_log'''
text = text.replace(old_reminder_log, new_reminder_log)

# 3. Правим промпт - добавляем команду для связки
old_prompt_end = 'Если не указал время - спроси."'
new_prompt_end = 'Если не указал время - спроси. Связка аптечек: если пользователь хочет поделиться аптечкой с родственником через его @username в телеграме - используй команду [SHARE_ACCESS:@username|отношение]. Тогда оба будут видеть общую аптечку."'
text = text.replace(old_prompt_end, new_prompt_end)

# 4. Добавляем регулярку SHARE_ACCESS
old_add_rem_re = 'ADD_REM_RE = r"\
\[ADD_REMINDER:(.+?)\\]"'
new_add_rem_re = 'ADD_REM_RE = r"\
\[ADD_REMINDER:(.+?)\\]"\nSHARE_RE = r"\
\[SHARE_ACCESS:(.+?)\\]"'
text = text.replace(old_add_rem_re, new_add_rem_re)

# 5. Добавляем обработку SHARE_ACCESS в process_gpt_commands и очистку
old_add_rem_clean = '''    text = re.sub(ADD_REM_RE, "", text)
    return text.strip()'''
new_add_rem_clean = '''    text = re.sub(ADD_REM_RE, "", text)
    text = re.sub(SHARE_RE, "", text)
    return text.strip()'''
text = text.replace(old_add_rem_clean, new_add_rem_clean)

# 6. Добавляем обработку SHARE в process_gpt_commands перед conn.commit()
old_rem_commit = '''        for rem in re.findall(ADD_REM_RE, text):'''
new_rem_commit = '''        for sh in re.findall(SHARE_RE, text):
            parts = [p.strip() for p in sh.split("|")]
            username = parts[0].replace("@", "") if len(parts) > 0 else ""
            relation = parts[1] if len(parts) > 1 else ""
            if username:
                c.execute("INSERT INTO shared_access (owner_id, shared_with_id, shared_with_username, relation) VALUES (%s, 0, %s, %s) ON CONFLICT DO NOTHING", (uid, username, relation))
        for rem in re.findall(ADD_REM_RE, text):'''
text = text.replace(old_rem_commit, new_rem_commit)

# 7. Обновляем get_user_inventory чтобы показывать и shared аптечки
old_get_inv = '''def get_user_inventory(uid):
    conn = get_db_connection()
    if not conn:
        return []
    try:
        c = conn.cursor()
        c.execute("SELECT medicine_name, quantity, dosage, expiry_date, category FROM inventory WHERE user_id = %s ORDER BY medicine_name", (uid,))
        return c.fetchall()'''
new_get_inv = '''def get_user_inventory(uid):
    conn = get_db_connection()
    if not conn:
        return []
    try:
        c = conn.cursor()
        shared_ids = [uid]
        c.execute("SELECT owner_id FROM shared_access WHERE shared_with_id = %s", (uid,))
        for row in c.fetchall():
            shared_ids.append(row[0])
        c.execute("SELECT DISTINCT ON (medicine_name) medicine_name, quantity, dosage, expiry_date, category FROM inventory WHERE user_id = ANY(%s) ORDER BY medicine_name", (shared_ids,))
        return c.fetchall()'''
text = text.replace(old_get_inv, new_get_inv)

# 8. Правим вывод семьи - если пустая, пишем красиво
old_family_empty = '''                tg_send(chat_id, "Семья не указана. Напиши кто в твоей семье!")'''
new_family_empty = '''                tg_send(chat_id, "\\U0001f468\\u200d\\U0001f469\\u200d\\U0001f467\\u200d\\U0001f466 Вы пока никого не добавили.\\n\\nНапишите кто в вашей семье, например:\\n\\\"Моя жена Анна, 30 лет\\\"")'''
text = text.replace(old_family_empty, new_family_empty)

# 9. Правим вывод семьи - пропускаем None значения
old_family_display = '''                for f in fam:
                    lines.append("- %s, %s лет, %s, %s" % (f[0], f[1], f[2], f[3]))'''
new_family_display = '''                for f in fam:
                    age_str = "%s лет" % f[1] if f[1] else "возраст не указан"
                    gender_str = f[2] if f[2] else ""
                    rel_str = f[3] if f[3] else ""
                    parts = [f[0], age_str]
                    if gender_str:
                        parts.append(gender_str)
                    if rel_str:
                        parts.append(rel_str)
                    lines.append("- %s" % ", ".join(parts))'''
text = text.replace(old_family_display, new_family_display)

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Done!')