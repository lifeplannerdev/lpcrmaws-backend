import sqlite3
conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'students_%';")
tables = [row[0] for row in cursor.fetchall()]
for table in tables:
    print(f'Dropping {table}')
    cursor.execute(f'DROP TABLE {table};')
cursor.execute("DELETE FROM django_migrations WHERE app='students';")
conn.commit()
conn.close()
print('Done!')
