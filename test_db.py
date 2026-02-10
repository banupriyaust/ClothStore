import psycopg
import os
from dotenv import load_dotenv

load_dotenv()

conn = psycopg.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()
cur.execute("SELECT NOW();")
print(cur.fetchone())
conn.close()
