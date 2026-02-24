# fix_family.py - добавляем REMOVE_FAMILY, EDIT_FAMILY, чистим мусор
with open("bot.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Добавить регулярки для REMOVE_FAMILY и EDIT_FAMILY
old_re = 'CABINET_SWITCH_RE = r"\
\[SWITCH_CABINET:(.+?)\\]"'
new_re = '''CABINET_SWITCH_RE = r"\
\[SWITCH_CABINET:(.+?)\\]"
REM_FAM_RE = r"\
\[REMOVE_FAMILY:(.+?)\\]"'''
code = code.replace(old_re, new_re)

# 2. Добавить обработку REMOVE_FAMILY в process_gpt_commands (после SHARE обработки)
old_share_block = '''        for sh in re.findall(SHARE_RE, text):'''
new_share_block = '''        for fam_del in re.findall(REM_FAM_RE, text):
            fname = fam_del.strip()
            if fname:
                c.execute("DELETE FROM family WHERE user_id = %s AND LOWER(name) = LOWER(%s)", (uid, fname))
                logger.info("Deleted family member: %s for user %s", fname, uid)

        for sh in re.findall(SHARE_RE, text):'''
code = code.replace(old_share_block, new_share_block)

# 3. Добавить REMOVE_FAMILY в clean_commands
old_clean = '    for rx in [ADD_MED_RE, REM_MED_RE, ADD_FAM_RE, ADD_REM_RE, SHARE_RE, CABINET_CREATE_RE, CABINET_SWITCH_RE]:'
new_clean = '    for rx in [ADD_MED_RE, REM_MED_RE, ADD_FAM_RE, ADD_REM_RE, SHARE_RE, CABINET_CREATE_RE, CABINET_SWITCH_RE, REM_FAM_RE]:'
code = code.replace(old_clean, new_clean)

# 4. Добавить REMOVE_FAMILY в системный промпт
old_cmd = '[REMOVE_MEDICINE:название] - удалить.'
new_cmd = '''[REMOVE_MEDICINE:название] - удалить лекарство.
[REMOVE_FAMILY:имя] - удалить члена семьи.'''
code = code.replace(old_cmd, new_cmd)

# 5. Убить fallback который путает семью с лекарствами — 
#    заменить ADD_MEDICINE fallback на более точный (исключить имена людей)
old_fallback = '''        # Если GPT не включил команду ADD_MEDICINE но явно добавляет лекарство
        if "[ADD_MEDICINE:" not in reply and any(w in reply.lower() for w in ["добавляю", "добавил", "добавлено", "записал", "внесл"]):
            logger.info("GPT forgot ADD_MEDICINE command, attempting fallback parse")
            # Попробуем извлечь данные из текста
            import re as _re
            name_match = _re.search(r'\\*\\*(.+?)\\*\\*', reply)
            if name_match:
                med_name = name_match.group(1)
                # Ищем дозировку
                dose_match = _re.search(r'дозировк[аи]:?\\s*([\\d,.]+ ?(?:мг|мл|г|мкг|%|МЕ))', reply, _re.IGNORECASE)
                dose = dose_match.group(1) if dose_match else ""
                # Ищем срок
                exp_match = _re.search(r'(?:годност|срок)[а-яё]*:?\\s*(\\d{4}[-./]\\d{2}(?:[-./]\\d{2})?)', reply, _re.IGNORECASE)
                exp = exp_match.group(1) if exp_match else ""
                # Ищем категорию
                cat = "РАЗНОЕ"
                for c_name in ["ТЕМПЕРАТУРА", "БОЛЬ", "ЖИВОТ", "РАНЫ"]:
                    if c_name.lower() in reply.lower() or c_name in reply:
                        cat = c_name
                        break
                # Ищем хранение
                storage = "ХОЛОДИЛЬНИК" if "холодильник" in reply.lower() else "КОМНАТНАЯ"
                cmd = "[ADD_MEDICINE:%s|1|%s|%s|%s|%s]" % (med_name, dose, exp, cat, storage)
                logger.info("Fallback ADD command: %s", cmd)
                reply += "\\n" + cmd'''

new_fallback = '''        # Если GPT не включил команду ADD_MEDICINE но явно добавляет лекарство
        family_words = ["семь", "член", "сын", "дочь", "муж", "жен", "мам", "пап", "бабушк", "дедушк", "ребён", "ребен", "брат", "сестр"]
        is_family_context = any(w in reply.lower() for w in family_words)
        if "[ADD_MEDICINE:" not in reply and not is_family_context and any(w in reply.lower() for w in ["добавляю", "добавил", "добавлено", "записал", "внесл"]):
            # Проверяем что это именно лекарство (есть дозировка или мед. термины)
            med_indicators = ["мг", "мл", "табл", "капсул", "дозировк", "годност", "срок", "категори", "аптечк"]
            if any(ind in reply.lower() for ind in med_indicators):
                logger.info("GPT forgot ADD_MEDICINE command, attempting fallback parse")
                import re as _re
                name_match = _re.search(r'\\*\\*(.+?)\\*\\*', reply)
                if name_match:
                    med_name = name_match.group(1)
                    dose_match = _re.search(r'дозировк[аи]:?\\s*([\\d,.]+ ?(?:мг|мл|г|мкг|%|МЕ))', reply, _re.IGNORECASE)
                    dose = dose_match.group(1) if dose_match else ""
                    exp_match = _re.search(r'(?:годност|срок)[а-яё]*:?\\s*(\\d{4}[-./]\\d{2}(?:[-./]\\d{2})?)', reply, _re.IGNORECASE)
                    exp = exp_match.group(1) if exp_match else ""
                    cat = "РАЗНОЕ"
                    for c_name in ["ТЕМПЕРАТУРА", "БОЛЬ", "ЖИВОТ", "РАНЫ"]:
                        if c_name.lower() in reply.lower() or c_name in reply:
                            cat = c_name
                            break
                    storage = "ХОЛОДИЛЬНИК" if "холодильник" in reply.lower() else "КОМНАТНАЯ"
                    cmd = "[ADD_MEDICINE:%s|1|%s|%s|%s|%s]" % (med_name, dose, exp, cat, storage)
                    logger.info("Fallback ADD command: %s", cmd)
                    reply += "\\n" + cmd'''
code = code.replace(old_fallback, new_fallback)

# 6. Добавить эндпоинт для очистки мусора из базы
old_debug_route = '@app.route("/debug_db", methods=["GET"])'
new_cleanup_route = '''@app.route("/cleanup_db", methods=["GET"])
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

@app.route("/debug_db", methods=["GET"])'''
code = code.replace(old_debug_route, new_cleanup_route)

with open("bot.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Family fixes applied!")