import sqlite3
import os

try:
    conn = sqlite3.connect('db.sqlite3')
    cursor = conn.cursor()
    cursor.execute('DROP TABLE IF EXISTS programs_program')
    cursor.execute("DELETE FROM django_migrations WHERE app='programs'")
    conn.commit()
    conn.close()
    print("Database cleaned.")
except Exception as e:
    print("Error:", e)

try:
    for file in os.listdir(r'programs\migrations'):
        if file != '__init__.py' and file.endswith('.py'):
            os.remove(os.path.join(r'programs\migrations', file))
    print("Migrations cleaned.")
except Exception as e:
    print("Error cleaning migrations:", e)
