import sqlite3
import json

db_path = r"c:\Users\vasan\Documents\Apphelix Intern\RAG\memory.db"

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

try:
    cursor.execute("SELECT * FROM memory ORDER BY timestamp DESC LIMIT 10;")
    rows = cursor.fetchall()
    print(f"Found {len(rows)} recent memory rows:")
    for idx, row in enumerate(rows):
        row_dict = dict(row)
        print(f"Row {idx+1}: {row_dict.get('role')} | Session: {row_dict.get('session_id')} | Time: {row_dict.get('timestamp')}")
        text_preview = row_dict.get('text', '').replace('\n', ' ')
        print(f"  Text: {text_preview[:120]}...")
except Exception as e:
    print("Error:", e)
finally:
    conn.close()
