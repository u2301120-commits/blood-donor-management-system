import sqlite3
from pathlib import Path

DATABASE = Path(__file__).resolve().parent / "donors.db"

conn = sqlite3.connect(DATABASE)
cursor = conn.cursor()

cursor.execute("DELETE FROM donors")

conn.commit()
conn.close()

print("All registered donor data has been deleted successfully.")