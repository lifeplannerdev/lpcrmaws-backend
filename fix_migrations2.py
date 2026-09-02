import sqlite3
conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()
cursor.execute("INSERT INTO django_migrations (app, name, applied) VALUES ('fees', '0003_alter_studentfeeaccount_student', datetime('now'));")
conn.commit()
conn.close()
print('Fixed 2')
