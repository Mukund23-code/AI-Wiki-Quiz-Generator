import sqlite3

# Path to your SQLite DB
db_path = "quiz.db"  # adjust if your DB is in a different folder

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check if 'summary' column exists
cursor.execute("PRAGMA table_info(quiz_history);")
columns = [col[1] for col in cursor.fetchall()]

if "summary" not in columns:
    cursor.execute("ALTER TABLE quiz_history ADD COLUMN summary TEXT;")
    print("Column 'summary' added successfully!")
else:
    print("Column 'summary' already exists.")

conn.commit()
conn.close()
