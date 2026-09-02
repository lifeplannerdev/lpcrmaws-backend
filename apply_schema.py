import sqlite3
with open('schema.sql', 'r', encoding='utf-16') as f:
    sql = f.read()
conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()
cursor.executescript(sql)
cursor.execute("INSERT INTO django_migrations (app, name, applied) VALUES ('students', '0001_initial', datetime('now'));")
conn.commit()
conn.close()
print('Schema applied!')
