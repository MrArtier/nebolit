with open('bot.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Фикс разбитых регулярок (строки 698-707)
content = content.replace('ADD_MED_RE = r"\n\
\[ADD_MEDICINE:(.+?)\\]"', 'ADD_MED_RE = r"\
\[ADD_MEDICINE:(.+?)\\]"')
content = content.replace('REM_MED_RE = r"\n\
\[REMOVE_MEDICINE:(.+?)\\]"', 'REM_MED_RE = r"\
\[REMOVE_MEDICINE:(.+?)\\]"')
content = content.replace('ADD_FAM_RE = r"\n\
\[ADD_FAMILY:(.+?)\\]"', 'ADD_FAM_RE = r"\
\[ADD_FAMILY:(.+?)\\]"')
content = content.replace('ADD_REM_RE = r"\n\
\[ADD_REMINDER:(.+?)\\]"', 'ADD_REM_RE = r"\
\[ADD_REMINDER:(.+?)\\]"')
content = content.replace('SHARE_RE = r"\n\
\[SHARE_ACCESS:(.+?)\\]"', 'SHARE_RE = r"\
\[SHARE_ACCESS:(.+?)\\]"')
content = content.replace('CABINET_CREATE_RE = r"\n\
\[CREATE_CABINET:(.+?)\\]"', 'CABINET_CREATE_RE = r"\
\[CREATE_CABINET:(.+?)\\]"')
content = content.replace('CABINET_SWITCH_RE = r"\n\
\[SWITCH_CABINET:(.+?)\\]"', 'CABINET_SWITCH_RE = r"\
\[SWITCH_CABINET:(.+?)\\]"')

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fix 1 done - regex patterns fixed")