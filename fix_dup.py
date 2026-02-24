# fix_dup.py - убрать дубль cleanup_db
with open("bot.py", "r", encoding="utf-8") as f:
    code = f.read()

# Найти и удалить второй cleanup_db (оставить первый)
first = code.find('@app.route("/cleanup_db"')
if first >= 0:
    second = code.find('@app.route("/cleanup_db"', first + 1)
    if second >= 0:
        # Найти конец второго cleanup_db (до следующего @app.route)
        next_route = code.find('@app.route(', second + 1)
        if next_route >= 0:
            code = code[:second] + code[next_route:]
            print("Removed duplicate cleanup_db")
        else:
            print("Could not find next route after duplicate")
    else:
        print("No duplicate found")
else:
    print("cleanup_db not found at all")

with open("bot.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Done!")