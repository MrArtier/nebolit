with open('bot.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_sub_check = '        sub = get_subscription(uid)'
new_sub_check = '''        if user_text.strip() == "/admin" and uid == ADMIN_ID:
            conn_a = get_db_connection()
            if conn_a:
                try:
                    ca = conn_a.cursor()
                    ca.execute("SELECT COUNT(*) FROM users")
                    total_users = ca.fetchone()[0]
                    ca.execute("SELECT COUNT(*) FROM users WHERE created_at >= CURRENT_DATE")
                    new_today = ca.fetchone()[0]
                    ca.execute("SELECT COUNT(*) FROM users WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'")
                    new_week = ca.fetchone()[0]
                    ca.execute("SELECT COUNT(*) FROM messages")
                    total_msgs = ca.fetchone()[0]
                    ca.execute("SELECT COUNT(DISTINCT user_id) FROM messages")
                    active_users = ca.fetchone()[0]
                    avg_msgs = round(total_msgs / active_users, 1) if active_users > 0 else 0
                    ca.execute("SELECT COUNT(*) FROM messages WHERE created_at >= CURRENT_DATE")
                    msgs_today = ca.fetchone()[0]
                    ca.execute("SELECT COUNT(*) FROM inventory")
                    total_meds = ca.fetchone()[0]
                    ca.execute("SELECT COUNT(DISTINCT user_id) FROM inventory")
                    users_with_meds = ca.fetchone()[0]
                    avg_meds = round(total_meds / users_with_meds, 1) if users_with_meds > 0 else 0
                    ca.execute("SELECT medicine_name, COUNT(*) as cnt FROM inventory GROUP BY medicine_name ORDER BY cnt DESC LIMIT 5")
                    top_meds = ca.fetchall()
                    top_meds_str = "\\n".join(["  %s (%s)" % (m[0], m[1]) for m in top_meds]) if top_meds else "  нет данных"
                    ca.execute("SELECT COUNT(*) FROM reminders WHERE active = TRUE")
                    active_rem = ca.fetchone()[0]
                    ca.execute("SELECT COUNT(*) FROM family")
                    total_family = ca.fetchone()[0]
                    ca.execute("SELECT COUNT(*) FROM cabinets")
                    total_cabs = ca.fetchone()[0]
                    ca.execute("SELECT plan, COUNT(*) FROM subscriptions GROUP BY plan")
                    sub_stats = dict(ca.fetchall())
                    trial_cnt = sub_stats.get("trial", 0)
                    paid_cnt = sub_stats.get("paid", 0)
                    expired_cnt = sub_stats.get("expired", 0)
                    ca.execute("SELECT COUNT(*) FROM payments WHERE status = 'succeeded'")
                    paid_payments = ca.fetchone()[0]
                    ca.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'succeeded'")
                    total_revenue = ca.fetchone()[0]
                    ca.execute("SELECT code, used_count, max_uses, discount_percent, free_days, action FROM promo_codes WHERE active = TRUE")
                    promos = ca.fetchall()
                    promo_str = ""
                    if promos:
                        promo_lines = []
                        for p in promos:
                            info = "%s: %s/%s исп." % (p[0], p[1], p[2] if p[2] > 0 else "\\u221e")
                            if p[5] == "discount":
                                info += " (-%s%%)" % p[3]
                            elif p[5] == "free_days":
                                info += " (+%s дн.)" % p[4]
                            elif p[5] == "full_free":
                                info += " (бесплатно)"
                            promo_lines.append("  " + info)
                        promo_str = "\\n".join(promo_lines)
                    else:
                        promo_str = "  нет активных"
                    stat = (
                        "\\U0001f4ca Статистика НеБолит\\n"
                        "\\u2500\\u2500\\u2500\\u2500\\u2500\\u2500\\u2500\\u2500\\u2500\\u2500\\u2500\\u2500\\u2500\\u2500\\u2500\\n"
                        "\\n\\U0001f465 Пользователи:\\n"
                        "  Всего: %s\\n"
                        "  Сегодня: +%s\\n"
                        "  За неделю: +%s\\n"
                        "\\n\\U0001f4ac Сообщения:\\n"
                        "  Всего: %s\\n"
                        "  Сегодня: %s\\n"
                        "  Среднее на юзера: %s\\n"
                        "\\n\\U0001f48a Лекарства:\\n"
                        "  Всего в аптечках: %s\\n"
                        "  Юзеров с аптечкой: %s\\n"
                        "  Среднее на юзера: %s\\n"
                        "\\n\\U0001f3c6 Топ-5 лекарств:\\n%s\\n"
                        "\\n\\U0001f4cb Прочее:\\n"
                        "  Напоминаний активных: %s\\n"
                        "  Членов семей: %s\\n"
                        "  Аптечек создано: %s\\n"
                        "\\n\\U0001f4b3 Подписки:\\n"
                        "  Trial: %s\\n"
                        "  Paid: %s\\n"
                        "  Expired: %s\\n"
                        "  Платежей успешных: %s\\n"
                        "  Выручка: %s \\u20bd\\n"
                        "\\n\\U0001f3ab Промокоды:\\n%s"
                    ) % (total_users, new_today, new_week, total_msgs, msgs_today, avg_msgs, total_meds, users_with_meds, avg_meds, top_meds_str, active_rem, total_family, total_cabs, trial_cnt, paid_cnt, expired_cnt, paid_payments, total_revenue, promo_str)
                    tg_send(chat_id, stat)
                except Exception as e:
                    tg_send(chat_id, "Ошибка: %s" % str(e))
                finally:
                    conn_a.close()
            return
        sub = get_subscription(uid)'''
text = text.replace(old_sub_check, new_sub_check)

# Убираем дубль /admin который был добавлен fix19 (после проверки подписки)
old_admin_dupe = '''        if user_text.strip() == "/admin" and uid == ADMIN_ID:
            conn_a = get_db_connection()
            if conn_a:
                try:
                    ca = conn_a.cursor()
                    ca.execute("SELECT COUNT(*) FROM users")
                    total_users = ca.fetchone()[0]
                    ca.execute("SELECT COUNT(*) FROM users WHERE created_at >= CURRENT_DATE")
                    new_today = ca.fetchone()[0]
                    ca.execute("SELECT COUNT(*) FROM users WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'")
                    new_week = ca.fetchone()[0]
                    ca.execute("SELECT COUNT(*) FROM messages")
                    total_msgs = ca.fetchone()[0]
                    ca.execute("SELECT COUNT(DISTINCT user_id) FROM messages")
                    active_users = ca.fetchone()[0]
                    avg_msgs = round(total_msgs / active_users, 1) if active_users > 0 else 0
                    ca.execute("SELECT COUNT(*) FROM messages WHERE created_at >= CURRENT_DATE")
                    msgs_today = ca.fetchone()[0]
                    ca.execute("SELECT COUNT(*) FROM inventory")
                    total_meds = ca.fetchone()[0]
                    ca.execute("SELECT COUNT(DISTINCT user_id) FROM inventory")
                    users_with_meds = ca.fetchone()[0]
                    avg_meds = round(total_meds / users_with_meds, 1) if users_with_meds > 0 else 0
                    ca.execute("SELECT medicine_name, COUNT(*) as cnt FROM inventory GROUP BY medicine_name ORDER BY cnt DESC LIMIT 5")
                    top_meds = ca.fetchall()
                    top_meds_str = "\\n".join(["  %s (%s)" % (m[0], m[1]) for m in top_meds]) if top_meds else "  нет данных"
                    ca.execute("SELECT COUNT(*) FROM reminders WHERE active = TRUE")
                    active_rem = ca.fetchone()[0]
                    ca.execute("SELECT COUNT(*) FROM family")
                    total_family = ca.fetchone()[0]
                    ca.execute("SELECT COUNT(*) FROM cabinets")
                    total_cabs = ca.fetchone()[0]
                    ca.execute("SELECT plan, COUNT(*) FROM subscriptions GROUP BY plan")
                    sub_stats = dict(ca.fetchall())
                    trial_cnt = sub_stats.get("trial", 0)
                    paid_cnt = sub_stats.get("paid", 0)
                    expired_cnt = sub_stats.get("expired", 0)
                    ca.execute("SELECT COUNT(*) FROM payments WHERE status = 'succeeded'")
                    paid_payments = ca.fetchone()[0]
                    ca.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'succeeded'")
                    total_revenue = ca.fetchone()[0]
                    ca.execute("SELECT code, used_count, max_uses, discount_percent, free_days, action FROM promo_codes WHERE active = TRUE")
                    promos = ca.fetchall()
                    promo_str = ""
                    if promos:
                        promo_lines = []
                        for p in promos:
                            info = "%s: %s/%s исп." % (p[0], p[1], p[2] if p[2] > 0 else "\\u221e")
                            if p[5] == "discount":
                                info += " (-%s%%)" % p[3]
                            elif p[5] == "free_days":
                                info += " (+%s дн.)" % p[4]
                            elif p[5] == "full_free":
                                info += " (бесплатно)"
                            promo_lines.append("  " + info)
                        promo_str = "\\n".join(promo_lines)
                    else:
                        promo_str = "  нет активных"
                    stat = (
                        "\\U0001f4ca Статистика НеБолит\\n"
                        "\\u2500\\u2500\\u2500\\u2500\\u2500\\u2500\\u2500\\u2500\\u2500\\u2500\\u2500\\u2500\\u2500\\u2500\\u2500\\n"
                        "\\n\\U0001f465 Пользователи:\\n"
                        "  Всего: %s\\n"
                        "  Сегодня: +%s\\n"
                        "  За неделю: +%s\\n"
                        "\\n\\U0001f4ac Сообщения:\\n"
                        "  Всего: %s\\n"
                        "  Сегодня: %s\\n"
                        "  Среднее на юзера: %s\\n"
                        "\\n\\U0001f48a Лекарства:\\n"
                        "  Всего в аптечках: %s\\n"
                        "  Юзеров с аптечкой: %s\\n"
                        "  Среднее на юзера: %s\\n"
                        "\\n\\U0001f3c6 Топ-5 лекарств:\\n%s\\n"
                        "\\n\\U0001f4cb Прочее:\\n"
                        "  Напоминаний активных: %s\\n"
                        "  Членов семей: %s\\n"
                        "  Аптечек создано: %s\\n"
                        "\\n\\U0001f4b3 Подписки:\\n"
                        "  Trial: %s\\n"
                        "  Paid: %s\\n"
                        "  Expired: %s\\n"
                        "  Платежей успешных: %s\\n"
                        "  Выручка: %s \\u20bd\\n"
                        "\\n\\U0001f3ab Промокоды:\\n%s"
                    ) % (total_users, new_today, new_week, total_msgs, msgs_today, avg_msgs, total_meds, users_with_meds, avg_meds, top_meds_str, active_rem, total_family, total_cabs, trial_cnt, paid_cnt, expired_cnt, paid_payments, total_revenue, promo_str)
                    tg_send(chat_id, stat)
                except Exception as e:
                    tg_send(chat_id, "Ошибка: %s" % str(e))
                finally:
                    conn_a.close()
            return
        if user_text.strip() == "/start":'''

new_admin_clean = '        if user_text.strip() == "/start":'

text = text.replace(old_admin_dupe, new_admin_clean)

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Done fix20!')