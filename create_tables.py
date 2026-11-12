import os
import psycopg

url = os.environ["DATABASE_URL"]

with psycopg.connect(url) as conn:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS slots (
            id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id TEXT PRIMARY KEY,
            slot_id TEXT NOT NULL REFERENCES slots(id),
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS one_confirmed_per_slot
        ON bookings (slot_id) WHERE status = 'confirmed'
    """)
    print("tables ready")