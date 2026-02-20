import re
with open('bot.py', 'r', encoding='utf-8') as f:
    text = f.read()
text = text.replace('ADD_MED_RE = r\"\n\
\[ADD_MEDICINE', 'ADD_MED_RE = r\"\
\[ADD_MEDICINE')
text = text.replace('ADD_MED_RE = r\"\n\
\[[ADD_MEDICINE', 'ADD_MED_RE = r\"\
\[ADD_MEDICINE')
text = text.replace('REM_MED_RE = r\"\n\
\[REMOVE_MEDICINE', 'REM_MED_RE = r\"\
\[REMOVE_MEDICINE')
text = text.replace('REM_MED_RE = r\"\n\
\[[REMOVE_MEDICINE', 'REM_MED_RE = r\"\
\[REMOVE_MEDICINE')
text = text.replace('ADD_FAM_RE = r\"\n\
\[ADD_FAMILY', 'ADD_FAM_RE = r\"\
\[ADD_FAMILY')
text = text.replace('ADD_FAM_RE = r\"\n\
\[[ADD_FAMILY', 'ADD_FAM_RE = r\"\
\[ADD_FAMILY')
with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Fixed!')
