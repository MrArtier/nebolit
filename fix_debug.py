# fix_debug.py - добавляет отладку БД операций
import re

with open("bot.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Добавить логирование в process_gpt_commands чтобы видеть что GPT возвращает
old = '    save_message(uid, "assistant", reply)\n    tg_send(chat_id, reply)'
new = '    save_message(uid, "assistant", reply)\n    logger.info("GPT reply for %s: %s", uid, reply[:300])\n    tg_send(chat_id, reply)'
code = code.replace(old, new)

# 2. Улучшить логирование ошибок в process_gpt_commands
old = '    except Exception as e: logger.error("Cmd err: %s", e)\n    finally: conn.close()'
new = '    except Exception as e:\n        logger.error("Cmd err: %s", e, exc_info=True)\n        try: conn.rollback()\n        except: pass\n    finally: conn.close()'
code = code.replace(old, new)

# 3. Добавить логирование в save_message
old = '    except Exception as e: logger.error("Save msg err: %s", e)\n    finally: conn.close()'
new = '    except Exception as e:\n        logger.error("Save msg err: %s", e, exc_info=True)\n        try: conn.rollback()\n        except: pass\n    finally: conn.close()'
code = code.replace(old, new)

# 4. Добавить логирование в save_user
old = '    except Exception as e: logger.error("Save user err: %s", e)\n    finally: conn.close()'
new = '    except Exception as e:\n        logger.error("Save user err: %s", e, exc_info=True)\n        try: conn.rollback()\n        except: pass\n    finally: conn.close()'
code = code.replace(old, new)

# 5. Добавить проверку колонки storage при init_db (может падать если колонка уже есть в другом формате)
old = """        try:
            c.execute("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS storage TEXT DEFAULT ''")
        except:
            pass"""
new = """        try:
            c.execute("ALTER TABLE inventory ADD COLUMN IF NOT EXISTS storage TEXT DEFAULT ''")
            conn.commit()
        except:
            conn.rollback()"""
code = code.replace(old, new)

# 6. Добавить диагностический эндпоинт
old = '''@app.route("/", methods=["GET"])
def index():
    return "Bot running!", 200'''
new = '''@app.route("/debug_db", methods=["GET"])
def debug_db():
    conn = get_db_connection()
    if not conn:
        return "DB connection FAILED", 500
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM messages")
        msgs = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM inventory")
        inv = c.fetchone()[0]
        c.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'inventory' ORDER BY ordinal_position")
        cols = c.fetchall()
        col_str = ", ".join(["%s(%s)" % (c[0], c[1]) for c in cols])
        c.execute("SELECT * FROM inventory ORDER BY id DESC LIMIT 3")
        recent = c.fetchall()
        return "DB OK. Users: %s, Msgs: %s, Inv: %s\\nColumns: %s\\nRecent: %s" % (users, msgs, inv, col_str, str(recent)), 200
    except Exception as e:
        return "DB error: %s" % str(e), 500
    finally:
        conn.close()

@app.route("/", methods=["GET"])
def index():
    return "Bot running!", 200'''
code = code.replace(old, new)

with open("bot.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Debug fixes applied!")