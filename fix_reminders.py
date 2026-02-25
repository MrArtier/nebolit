# fix_reminders.py - полноценные напоминания с кнопками
with open("bot.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Добавить таблицу reminder_log в init_db
old_init_end = '        c.execute("DELETE FROM family WHERE LOWER(name) IN'
new_init_tables = '''        c.execute("""CREATE TABLE IF NOT EXISTS reminder_log (
            id SERIAL PRIMARY KEY,
            reminder_id INTEGER NOT NULL,
            user_id BIGINT NOT NULL,
            scheduled_time TIMESTAMP NOT NULL,
            status TEXT DEFAULT 'pending',
            snooze_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            completed_at TIMESTAMP
        )""")
        c.execute("DELETE FROM family WHERE LOWER(name) IN'''
code = code.replace(old_init_end, new_init_tables)

# 2. Добавить функцию отправки с inline-кнопками
old_tg_api = 'def tg_api(method, data=None):'
new_tg_funcs = '''def tg_send_reminder(chat_id, text, reminder_id, log_id):
    """Отправить напоминание с inline-кнопками"""
    html_text = md_to_html(text)
    keyboard = {"inline_keyboard": [
        [{"text": "\\u2705 Принял", "callback_data": "rem_done_%s_%s" % (reminder_id, log_id)},
         {"text": "\\u23f0 Отложить (1ч)", "callback_data": "rem_snooze_%s_%s" % (reminder_id, log_id)}]
    ]}
    try:
        result = tg_api("sendMessage", {"chat_id": chat_id, "text": html_text, "parse_mode": "HTML", "reply_markup": keyboard})
        if result and result.get("ok"):
            return result["result"]["message_id"]
    except Exception as e:
        logger.error("Send reminder error: %s", e)
    return None

def tg_answer_callback(callback_query_id, text=""):
    """Ответить на нажатие inline-кнопки"""
    try:
        tg_api("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text})
    except Exception as e:
        logger.error("Answer callback error: %s", e)

def tg_edit_message(chat_id, message_id, text):
    """Отредактировать сообщение (убрать кнопки)"""
    html_text = md_to_html(text)
    try:
        tg_api("editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": html_text, "parse_mode": "HTML"})
    except Exception as e:
        logger.error("Edit message error: %s", e)

def tg_api(method, data=None):'''
code = code.replace(old_tg_api, new_tg_funcs)

# 3. Добавить эндпоинт /cron_reminders
old_cleanup_route = '@app.route("/cleanup_db", methods=["GET"])'
new_cron_route = '''@app.route("/cron_reminders", methods=["GET", "POST"])
def cron_reminders():
    """Проверяет напоминания и отправляет уведомления"""
    from datetime import datetime, timedelta
    now = datetime.utcnow() + timedelta(hours=3)  # Moscow time
    current_time = now.strftime("%H:%M")
    current_date = now.date()
    conn = get_db_connection()
    if not conn:
        return "DB error", 500
    try:
        c = conn.cursor()
        # Получить все активные напоминания
        c.execute("""SELECT r.id, r.user_id, r.family_member, r.medicine_name, r.dosage, 
                     r.schedule_time, r.meal_relation, r.course_days, r.start_date, r.pills_per_dose
                     FROM reminders r WHERE r.active = TRUE""")
        reminders = c.fetchall()
        sent_count = 0
        for rem in reminders:
            rem_id, user_id, member, med_name, dosage, schedule, meal, course_days, start_date, pills = rem
            # Проверить не закончился ли курс
            if course_days and course_days > 0 and start_date:
                end_date = start_date + timedelta(days=course_days)
                if current_date > end_date:
                    c.execute("UPDATE reminders SET active = FALSE WHERE id = %s", (rem_id,))
                    conn.commit()
                    # Уведомить о завершении курса
                    tg_send(user_id, "\\u2705 Курс **%s** для %s завершён! Поздравляю!" % (med_name, member))
                    continue
            # Проверить совпадает ли время
            if not schedule:
                continue
            times = [t.strip() for t in schedule.split(",")]
            if current_time not in times:
                # Проверить отложенные
                c.execute("""SELECT id, snooze_count FROM reminder_log 
                            WHERE reminder_id = %s AND status = 'snoozed' 
                            AND scheduled_time <= %s AND snooze_count < 3""", (rem_id, now))
                snoozed = c.fetchall()
                for slog in snoozed:
                    log_id, snooze_cnt = slog
                    # Отправить повторно
                    meal_text = ""
                    if meal:
                        meal_text = " (%s еды)" % meal
                    pills_text = ""
                    if pills and pills > 0:
                        pills_text = ", %s шт." % pills
                    msg = "\\u23f0 **Напоминание** (повтор %s/3)\\n\\n" % (snooze_cnt + 1)
                    msg += "\\U0001f48a **%s**%s\\n" % (med_name, pills_text)
                    if dosage:
                        msg += "Дозировка: %s\\n" % dosage
                    msg += "Для: %s%s" % (member, meal_text)
                    msg_id = tg_send_reminder(user_id, msg, rem_id, log_id)
                    sent_count += 1
                continue
            # Проверить не отправляли ли уже сегодня в это время
            c.execute("""SELECT id FROM reminder_log 
                        WHERE reminder_id = %s AND DATE(scheduled_time) = %s 
                        AND status IN ('pending','snoozed','done')
                        AND scheduled_time::time = %s::time""", (rem_id, current_date, current_time + ":00"))
            already_sent = c.fetchone()
            if already_sent:
                continue
            # Отправить напоминание
            meal_text = ""
            if meal:
                meal_text = " (%s еды)" % meal
            pills_text = ""
            if pills and pills > 0:
                pills_text = ", %s шт." % pills
            day_num = ""
            if course_days and course_days > 0 and start_date:
                day = (current_date - start_date).days + 1
                day_num = "\\nДень %s из %s" % (day, course_days)
            msg = "\\U0001f48a **Время принять лекарство!**\\n\\n"
            msg += "**%s**%s\\n" % (med_name, pills_text)
            if dosage:
                msg += "Дозировка: %s\\n" % dosage
            msg += "Для: %s%s%s" % (member, meal_text, day_num)
            # Создать запись в логе
            sched_dt = datetime.combine(current_date, datetime.strptime(current_time, "%H:%M").time())
            c.execute("""INSERT INTO reminder_log (reminder_id, user_id, scheduled_time, status) 
                        VALUES (%s, %s, %s, 'pending') RETURNING id""", (rem_id, user_id, sched_dt))
            log_id = c.fetchone()[0]
            conn.commit()
            msg_id = tg_send_reminder(user_id, msg, rem_id, log_id)
            sent_count += 1
        conn.commit()
        return "OK, sent: %s" % sent_count, 200
    except Exception as e:
        logger.error("Cron reminders error: %s", e)
        return "Error: %s" % str(e), 500
    finally:
        conn.close()

@app.route("/cleanup_db", methods=["GET"])'''
code = code.replace(old_cleanup_route, new_cron_route)

# 4. Добавить обработку callback_query в webhook
old_webhook_check = '    if "message" not in body:'
new_webhook_check = '''    # Обработка inline-кнопок
    if "callback_query" in body:
        handle_callback(body["callback_query"])
        return jsonify({"ok": True}), 200

    if "message" not in body:'''
code = code.replace(old_webhook_check, new_webhook_check)

# 5. Добавить функцию handle_callback перед webhook
old_webhook = '@app.route("/webhook", methods=["POST"])'
new_callback_handler = '''def handle_callback(callback):
    """Обработка нажатия inline-кнопок напоминаний"""
    from datetime import datetime, timedelta
    cb_id = callback.get("id")
    data = callback.get("data", "")
    message = callback.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")

    if data.startswith("rem_done_"):
        # Пользователь принял лекарство
        parts = data.split("_")
        if len(parts) >= 4:
            rem_id = parts[2]
            log_id = parts[3]
            conn = get_db_connection()
            if conn:
                try:
                    c = conn.cursor()
                    c.execute("UPDATE reminder_log SET status = 'done', completed_at = NOW() WHERE id = %s", (log_id,))
                    conn.commit()
                except Exception as e:
                    logger.error("Callback done error: %s", e)
                finally:
                    conn.close()
            tg_answer_callback(cb_id, "\\u2705 Отлично! Записано.")
            # Редактируем сообщение - убираем кнопки
            original_text = message.get("text", "")
            tg_edit_message(chat_id, message_id, original_text + "\\n\\n\\u2705 _Принято!_")

    elif data.startswith("rem_snooze_"):
        # Отложить на час
        parts = data.split("_")
        if len(parts) >= 4:
            rem_id = parts[2]
            log_id = parts[3]
            conn = get_db_connection()
            if conn:
                try:
                    c = conn.cursor()
                    c.execute("SELECT snooze_count FROM reminder_log WHERE id = %s", (log_id,))
                    row = c.fetchone()
                    if row:
                        snooze_count = row[0]
                        if snooze_count >= 3:
                            tg_answer_callback(cb_id, "\\u274c Лимит откладываний исчерпан (3/3)")
                            tg_edit_message(chat_id, message_id, message.get("text", "") + "\\n\\n\\u274c _Лимит откладываний исчерпан._")
                        else:
                            new_time = datetime.utcnow() + timedelta(hours=3) + timedelta(hours=1)
                            c.execute("UPDATE reminder_log SET status = 'snoozed', snooze_count = %s, scheduled_time = %s WHERE id = %s",
                                     (snooze_count + 1, new_time, log_id))
                            conn.commit()
                            left = 3 - snooze_count - 1
                            tg_answer_callback(cb_id, "\\u23f0 Напомню через час (осталось %s)" % left)
                            tg_edit_message(chat_id, message_id, message.get("text", "") + "\\n\\n\\u23f0 _Отложено на 1 час (%s/3)_" % (snooze_count + 1))
                    else:
                        tg_answer_callback(cb_id, "\\u274c Напоминание не найдено")
                except Exception as e:
                    logger.error("Callback snooze error: %s", e)
                finally:
                    conn.close()

@app.route("/webhook", methods=["POST"])'''
code = code.replace(old_webhook, new_callback_handler)

with open("bot.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Reminders with buttons applied!")