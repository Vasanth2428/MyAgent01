import sqlite3

db_path = r"c:\Users\vasan\Documents\Apphelix Intern\RAG\data\synthetic_sales.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables in database:")
for t in tables:
    table_name = t[0]
    print(f"\nTable: {table_name}")
    cursor.execute(f"PRAGMA table_info({table_name});")
    columns = cursor.fetchall()
    for col in columns:
        print(f" - {col[1]} ({col[2]})")
        
    # Get count
    cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
    count = cursor.fetchone()[0]
    print(f"Total rows: {count}")
    
conn.close()
