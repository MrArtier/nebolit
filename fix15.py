with open('bot.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Добавляем функцию проверки срока годности после md_to_html
old_md_end = '''    text = _re.sub(r'`(.+?)`', r'<code>\\1</code>', text)
    return text'''
new_md_end = '''    text = _re.sub(r'`(.+?)`', r'<code>\\1</code>', text)
    return text

def check_expiry(exp_str):
    from datetime import date, timedelta
    if not exp_str or exp_str.strip() == "" or exp_str.strip() == "?":
        return "ok", None
    try:
        exp_str = exp_str.strip()
        exp_date = None
        import re as _re2
        if _re2.match(r"^\\d{4}-\\d{2}-\\d{2}$", exp_str):
            parts = exp_str.split("-")
            exp_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
        elif _re2.match(r"^\\d{4}-\\d{2}$", exp_str):
            parts = exp_str.split("-")
            exp_date = date(int(parts[0]), int(parts[1]), 28)
        elif _re2.match(r"^\\d{2}\\.\\d{2}\\.\\d{4}$", exp_str):
            parts = exp_str.split(".")
            exp_date = date(int(parts[2]), int(parts[1]), int(parts[0]))
        elif _re2.match(r"^\\d{2}\\.\\d{4}$", exp_str):
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
        return "ok", None'''
text = text.replace(old_md_end, new_md_end)

# 2. Заменяем обработку ADD_MEDICINE — добавляем проверку срока
old_add_med = '''        for med in re.findall(ADD_MED_RE, text):
            parts = [p.strip() for p in med.split("|")]
            name = parts[0] if len(parts) > 0 else ""
            qty = parts[1] if len(parts) > 1 else "1"
            dos = parts[2] if len(parts) > 2 else ""
            exp = parts[3] if len(parts) > 3 else ""
            cat = parts[4] if len(parts) > 4 else ""
            if name:
                cab_id, _ = get_active_cabinet(uid)
                c.execute("INSERT INTO inventory (user_id, medicine_name, quantity, dosage, expiry_date, category, cabinet_id) VALUES (%s,%s,%s,%s,%s,%s,%s)", (uid, name, qty, dos, exp, cat, cab_id))'''

new_add_med = '''        med_results = []
        for med in re.findall(ADD_MED_RE, text):
            parts = [p.strip() for p in med.split("|")]
            name = parts[0] if len(parts) > 0 else ""
            qty = parts[1] if len(parts) > 1 else "1"
            dos = parts[2] if len(parts) > 2 else ""
            exp = parts[3] if len(parts) > 3 else ""
            cat = parts[4] if len(parts) > 4 else ""
            if name:
                status, exp_date = check_expiry(exp)
                if status == "expired":
                    med_results.append(("expired", name, exp))
                elif status == "soon":
                    cab_id, _ = get_active_cabinet(uid)
                    c.execute("INSERT INTO inventory (user_id, medicine_name, quantity, dosage, expiry_date, category, cabinet_id) VALUES (%s,%s,%s,%s,%s,%s,%s)", (uid, name, qty, dos, exp, cat, cab_id))
                    med_results.append(("soon", name, exp))
                else:
                    cab_id, _ = get_active_cabinet(uid)
                    c.execute("INSERT INTO inventory (user_id, medicine_name, quantity, dosage, expiry_date, category, cabinet_id) VALUES (%s,%s,%s,%s,%s,%s,%s)", (uid, name, qty, dos, exp, cat, cab_id))
                    med_results.append(("ok", name, exp))'''
text = text.replace(old_add_med, new_add_med)

# 3. Добавляем вывод результатов после process_gpt_commands
old_save_reply = '    save_message(uid, "assistant", reply)\n    tg_send(chat_id, reply)'
new_save_reply = '''    save_message(uid, "assistant", reply)
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
    tg_send(chat_id, reply)'''
text = text.replace(old_save_reply, new_save_reply)

# 4. Обновляем промпт — строгая проверка дат
old_date_prompt = 'Если срок не указан - поставь пустую строку.'
new_date_prompt = 'Если срок не указан - поставь пустую строку. СТРОГАЯ ПРОВЕРКА СРОКОВ: Всегда сравнивай срок годности с ТЕКУЩЕЙ датой. Сегодняшнюю дату определяй из системы. Если срок годности уже прошёл - обязательно добавь к ответу предупреждение с красным восклицательным знаком что лекарство ПРОСРОЧЕНО и его НЕЛЬЗЯ принимать, в аптечку НЕ ДОБАВЛЯЙ (не пиши команду ADD_MEDICINE). Если до конца срока менее 2 месяцев - предупреди жёлтым значком. Если лекарство годно - зелёная галочка. Формат срока в команде: ГГГГ-ММ-ДД или ГГГГ-ММ.'
text = text.replace(old_date_prompt, new_date_prompt)

# 5. Добавляем текущую дату в контекст GPT
old_cab_text = '    cab_text = "Текущая аптечка: %s" % cab_name'
new_cab_text = '''    from datetime import date as _date
    today_str = _date.today().isoformat()
    cab_text = "Сегодня: %s. Текущая аптечка: %s" % (today_str, cab_name)'''
text = text.replace(old_cab_text, new_cab_text)

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Done fix15!')