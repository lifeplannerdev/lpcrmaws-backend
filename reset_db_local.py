import sqlite3

def reset():
    conn = sqlite3.connect('db.sqlite3')
    cursor = conn.cursor()
    tables = [
        'programs_program',
        'programs_programcountry',
        'programs_programuniversity',
        'programs_programintake'
    ]
    for table in tables:
        cursor.execute(f"DROP TABLE IF EXISTS {table}")
    cursor.execute("DELETE FROM django_migrations WHERE app='programs'")
    conn.commit()
    conn.close()
    print("Local DB tables dropped.")

if __name__ == '__main__':
    reset()
