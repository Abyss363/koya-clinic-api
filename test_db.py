import os
import psycopg

url = os.environ["DATABASE_URL"]

with psycopg.connect(url) as conn:
    print(conn.execute("SELECT 1").fetchone())