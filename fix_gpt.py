# fix_gpt.py - усиливаем промпт и добавляем fallback-парсинг
with open("bot.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Усилить SYSTEM_PROMPT - добавить жёсткое требование
old_prompt_end = 'НИКОГДА не подставляй шаблонные значения."""'
new_prompt_end = '''НИКОГДА не подставляй шаблонные значения.

КРИТИЧЕСКИ ВАЖНО: Когда пользователь просит добавить лекарство (текстом, голосом или фото) — ты ОБЯЗАН включить команду [ADD_MEDICINE:...] в свой ответ. Без этой команды лекарство НЕ будет добавлено в аптечку! Всегда используй команды в квадратных скобках. Пример: [ADD_MEDICINE:Нурофен|1|400 мг|2027-01|БОЛЬ|КОМНАТНАЯ]

Аналогично для удаления ОБЯЗАТЕЛЬНО используй [REMOVE_MEDICINE:название], для семьи [ADD_FAMILY:...], для напоминаний [ADD_REMINDER:...]."""'''
code = code.replace(old_prompt_end, new_prompt_end)

# 2. Добавить fallback-парсинг если GPT забыл команду
old_return = '''        process_gpt_commands(uid, reply)
        return clean_commands(reply)
    except Exception as e: logger.error("GPT err: %s", e); return "Ошибка связи с ИИ."'''

new_return = '''        # Если GPT не включил команду ADD_MEDICINE но явно добавляет лекарство
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
                reply += "\\n" + cmd
        process_gpt_commands(uid, reply)
        return clean_commands(reply)
    except Exception as e: logger.error("GPT err: %s", e); return "Ошибка связи с ИИ."'''
code = code.replace(old_return, new_return)

# 3. Удалить шаблонные записи при init_db (усилить очистку)
old_cleanup = '        c.execute("DELETE FROM reminders WHERE medicine_name IN (\'лекарство\',\'medicine\',\'test\') OR family_member IN (\'член_семьи\',\'member\')")'
new_cleanup = '''        c.execute("DELETE FROM reminders WHERE medicine_name IN ('лекарство','medicine','test') OR family_member IN ('член_семьи','member')")
        c.execute("DELETE FROM inventory WHERE dosage = 'дозировка' OR category = 'категория' OR medicine_name IN ('лекарство','medicine','test')")'''
code = code.replace(old_cleanup, new_cleanup)

with open("bot.py", "w", encoding="utf-8") as f:
    f.write(code)

print("GPT fixes applied!")