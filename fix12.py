with open('bot.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Добавляем таблицу cabinets (аптечки) в init_db
old_shared = '        c.execute("CREATE TABLE IF NOT EXISTS shared_access'
new_shared = '''        c.execute("CREATE TABLE IF NOT EXISTS cabinets (id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL, name TEXT NOT NULL DEFAULT 'Моя аптечка', is_default BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS shared_access'''
text = text.replace(old_shared, new_shared)

# 2. Добавляем cabinet_id в inventory если его нет — через ALTER TABLE
old_reminder_log_create = '        c.execute("CREATE TABLE IF NOT EXISTS reminder_log'
new_reminder_log_create = '''        try:
            c.execute("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS cabinet_id INTEGER DEFAULT 0")
        except:
            pass
        c.execute("CREATE TABLE IF NOT EXISTS reminder_log'''
text = text.replace(old_reminder_log_create, new_reminder_log_create)

# 3. Добавляем таблицу active_cabinet для хранения текущей аптечки пользователя
old_reminder_log_full = '        c.execute("CREATE TABLE IF NOT EXISTS reminder_log (id SERIAL PRIMARY KEY, reminder_id INTEGER REFERENCES reminders(id), sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, status TEXT DEFAULT \'sent\')")'
new_reminder_log_full = '''        c.execute("CREATE TABLE IF NOT EXISTS user_state (user_id BIGINT PRIMARY KEY, active_cabinet_id INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS reminder_log (id SERIAL PRIMARY KEY, reminder_id INTEGER REFERENCES reminders(id), sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, status TEXT DEFAULT 'sent')")'''
text = text.replace(old_reminder_log_full, new_reminder_log_full)

# 4. Добавляем функции для работы с аптечками перед get_user_inventory
old_get_inv = 'def get_user_inventory(uid):'
new_get_inv = '''def get_active_cabinet(uid):
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

def get_user_inventory(uid):'''
text = text.replace(old_get_inv, new_get_inv)

# 5. Обновляем get_user_inventory — с учётом cabinet_id
old_inv_query = '''        shared_ids = [uid]
        c.execute("SELECT owner_id FROM shared_access WHERE shared_with_id = %s", (uid,))
        for row in c.fetchall():
            shared_ids.append(row[0])
        c.execute("SELECT DISTINCT ON (medicine_name) medicine_name, quantity, dosage, expiry_date, category FROM inventory WHERE user_id = ANY(%s) ORDER BY medicine_name", (shared_ids,))
        return c.fetchall()'''
new_inv_query = '''        cab_id, cab_name = get_active_cabinet(uid)
        shared_ids = [uid]
        c.execute("SELECT owner_id FROM shared_access WHERE shared_with_id = %s", (uid,))
        for row in c.fetchall():
            shared_ids.append(row[0])
        c.execute("SELECT DISTINCT ON (medicine_name) medicine_name, quantity, dosage, expiry_date, category FROM inventory WHERE user_id = ANY(%s) AND cabinet_id = %s ORDER BY medicine_name", (shared_ids, cab_id))
        return c.fetchall()'''
text = text.replace(old_inv_query, new_inv_query)

# 6. Обновляем INSERT в inventory — добавляем cabinet_id
old_ins_med = '''c.execute("INSERT INTO inventory (user_id, medicine_name, quantity, dosage, expiry_date, category) VALUES (%s,%s,%s,%s,%s,%s)", (uid, name, qty, dos, exp, cat))'''
new_ins_med = '''cab_id, _ = get_active_cabinet(uid)
                c.execute("INSERT INTO inventory (user_id, medicine_name, quantity, dosage, expiry_date, category, cabinet_id) VALUES (%s,%s,%s,%s,%s,%s,%s)", (uid, name, qty, dos, exp, cat, cab_id))'''
text = text.replace(old_ins_med, new_ins_med)

# 7. Добавляем команду /cabinets и обработку переключения перед /reminders
old_reminders_cmd = '        if user_text.strip() == "/reminders":'
new_reminders_cmd = '''        if user_text.strip() == "/cabinets":
            cabs = get_user_cabinets(uid)
            cab_id, cab_name = get_active_cabinet(uid)
            lines = ["\\U0001f3e0 Ваши аптечки:\\n"]
            if not cabs:
                lines.append("\\U0001f4e6 Моя аптечка (по умолчанию) \\u2705")
            else:
                for cb in cabs:
                    mark = " \\u2705" if cb[0] == cab_id else ""
                    lines.append("\\U0001f4e6 %s (id:%s)%s" % (cb[1], cb[0], mark))
                if cab_id == 0:
                    lines.append("\\U0001f4e6 Моя аптечка (по умолчанию) \\u2705")
            lines.append("\\n\\U0001f4ac Чтобы создать: \\\"Создай аптечку для мамы\\\"")
            lines.append("\\U0001f504 Чтобы переключить: \\\"Переключи на аптечку мамы\\\"")
            tg_send(chat_id, "\\n".join(lines))
            return
        if user_text.strip() == "/reminders":'''
text = text.replace(old_reminders_cmd, new_reminders_cmd)

# 8. Обновляем промпт — добавляем команды аптечек
old_share_prompt = 'Связка аптечек: если пользователь хочет поделиться аптечкой с родственником через его @username в телеграме - используй команду [SHARE_ACCESS:@username|отношение]. Тогда оба будут видеть общую аптечку."'
new_share_prompt = 'Связка аптечек: если пользователь хочет поделиться аптечкой с родственником через его @username в телеграме - используй команду [SHARE_ACCESS:@username|отношение]. Множественные аптечки: пользователь может вести несколько аптечек (свою, мамы, папы и т.д.). Команды: [CREATE_CABINET:название] - создать новую аптечку. [SWITCH_CABINET:название] - переключиться на другую аптечку. По умолчанию лекарства добавляются в текущую активную аптечку. Если пользователь говорит добавить лекарство в конкретную аптечку - сначала переключи, потом добавь."'
text = text.replace(old_share_prompt, new_share_prompt)

# 9. Добавляем регулярки для аптечек
old_share_re = 'SHARE_RE = r"\
\[SHARE_ACCESS:(.+?)\\]"'
new_share_re = 'SHARE_RE = r"\
\[SHARE_ACCESS:(.+?)\\]"\nCABINET_CREATE_RE = r"\
\[CREATE_CABINET:(.+?)\\]"\nCABINET_SWITCH_RE = r"\
\[SWITCH_CABINET:(.+?)\\]"'
text = text.replace(old_share_re, new_share_re)

# 10. Добавляем обработку CREATE/SWITCH CABINET перед SHARE
old_share_process = '''        for sh in re.findall(SHARE_RE, text):'''
new_share_process = '''        for cab in re.findall(CABINET_CREATE_RE, text):
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
        for sh in re.findall(SHARE_RE, text):'''
text = text.replace(old_share_process, new_share_process)

# 11. Очистка команд
old_share_clean = '''    text = re.sub(SHARE_RE, "", text)
    return text.strip()'''
new_share_clean = '''    text = re.sub(SHARE_RE, "", text)
    text = re.sub(CABINET_CREATE_RE, "", text)
    text = re.sub(CABINET_SWITCH_RE, "", text)
    return text.strip()'''
text = text.replace(old_share_clean, new_share_clean)

# 12. Добавляем инфо о текущей аптечке в контекст GPT
old_ctx_start = '    rem_text = "Напоминаний нет."'
new_ctx_start = '''    cab_id, cab_name = get_active_cabinet(uid)
    cab_text = "Текущая аптечка: %s" % cab_name
    cabs = get_user_cabinets(uid)
    if cabs:
        cab_text += ". Все аптечки: " + ", ".join([c[1] for c in cabs])
    rem_text = "Напоминаний нет."'''
text = text.replace(old_ctx_start, new_ctx_start)

old_ctx_final = '    ctx = "Аптечка:\\n" + inv_text + "\\nСемья:\\n" + fam_text + "\\nНапоминания:\\n" + rem_text'
new_ctx_final = '    ctx = cab_text + "\\nАптечка:\\n" + inv_text + "\\nСемья:\\n" + fam_text + "\\nНапоминания:\\n" + rem_text'
text = text.replace(old_ctx_final, new_ctx_final)

# 13. Показываем текущую аптечку в /inventory
old_inv_display = '''            inv = get_user_inventory(uid)
            if inv:
                lines = ["Твоя аптечка:\\n"]'''
new_inv_display = '''            inv = get_user_inventory(uid)
            cab_id_d, cab_name_d = get_active_cabinet(uid)
            if inv:
                lines = ["\\U0001f4e6 %s:\\n" % cab_name_d]'''
text = text.replace(old_inv_display, new_inv_display)

# 14. Добавляем кнопку аптечек в меню
old_menu_kb = '''    keyboard = {"keyboard": [[{"text": "\\U0001f3e0 Старт"}, {"text": "\\U0001f4e6 Аптечка"}], [{"text": "\\U0001f48a Курсы приёма"}, {"text": "\\U0001f468\\u200d\\U0001f469\\u200d\\U0001f467\\u200d\\U0001f466 Семья"}]], "resize_keyboard": True, "one_time_keyboard": False}'''
new_menu_kb = '''    keyboard = {"keyboard": [[{"text": "\\U0001f3e0 Старт"}, {"text": "\\U0001f4e6 Аптечка"}], [{"text": "\\U0001f48a Курсы приёма"}, {"text": "\\U0001f468\\u200d\\U0001f469\\u200d\\U0001f467\\u200d\\U0001f466 Семья"}], [{"text": "\\U0001f3e0 Аптечки"}]], "resize_keyboard": True, "one_time_keyboard": False}'''
text = text.replace(old_menu_kb, new_menu_kb)

# 15. Обработка кнопки Аптечки
old_family_btn = '''    elif user_text == "\\U0001f468\\u200d\\U0001f469\\u200d\\U0001f467\\u200d\\U0001f466 Семья":
        user_text = "/family"'''
new_family_btn = '''    elif user_text == "\\U0001f468\\u200d\\U0001f469\\u200d\\U0001f467\\u200d\\U0001f466 Семья":
        user_text = "/family"
    elif user_text == "\\U0001f3e0 Аптечки":
        user_text = "/cabinets"'''
text = text.replace(old_family_btn, new_family_btn)

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Done fix12!')