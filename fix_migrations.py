import sqlite3
conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()
cursor.execute("DELETE FROM django_migrations WHERE app='fees' AND name='0003_alter_studentfeeaccount_student';")
conn.commit()
conn.close()
print('Fixed')
