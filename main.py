import uuid
import os
import psycopg
from psycopg.rows import dict_row


from datetime import datetime, timezone

from fastapi.responses import JSONResponse
from fastapi import FastAPI
from pydantic import BaseModel

DATABASE_URL = os.environ["DATABASE_URL"]

app = FastAPI()



class SlotIn(BaseModel):
    id: str
    provider: str
    start: str
    end: str


class ResetBody(BaseModel):
    slots: list[SlotIn]

class NewBooking(BaseModel):
    slot_id: str
    name: str
    email: str

@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/slots")
def list_slots(provider: str | None = None):
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        rows = conn.execute("""
            SELECT s.id, s.provider, s.start_time, s.end_time,
                   NOT EXISTS (
                       SELECT 1 FROM bookings b
                       WHERE b.slot_id = s.id AND b.status = 'confirmed'
                   ) AS available
            FROM slots s
            WHERE (%(p)s::text IS NULL OR s.provider = %(p)s)
            ORDER BY s.start_time
        """, {"p": provider}).fetchall()

    result = []
    for r in rows:
        result.append({"id": r["id"], "provider": r["provider"], "start": r["start_time"], "end": r["end_time"], "available": r["available"]})
    return {"slots": result}


@app.post("/reset")
def reset(body: ResetBody):
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("DELETE FROM bookings")
        conn.execute("DELETE FROM slots")
        for s in body.slots:
            conn.execute(
                "INSERT INTO slots (id, provider, start_time, end_time) VALUES (%s, %s, %s, %s)",
                (s.id, s.provider, s.start, s.end)
            )
    return {"Done": True}


@app.post("/bookings", status_code=201)
def create_booking(body: NewBooking):
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        slot = conn.execute("SELECT id FROM slots WHERE id = %s", (body.slot_id,)).fetchone()
        if slot is None:
            return JSONResponse(status_code=404, content={"error": "slot not found"})

        row = conn.execute("""
            INSERT INTO bookings (id, slot_id, name, email, status)
            VALUES (%s, %s, %s, %s, 'confirmed')
            RETURNING id, slot_id, name, email, status, created_at
        """, (str(uuid.uuid4()), body.slot_id, body.name, body.email)).fetchone()
    return row

@app.get("/bookings/{booking_id}")
def get_booking(booking_id: str):
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        row = conn.execute(
            "SELECT id, slot_id, name, email, status, created_at FROM bookings WHERE id = %s",
            (booking_id,),
        ).fetchone()
    if row is None:
        return JSONResponse(status_code=404, content={"error": "booking not found"})
    return row