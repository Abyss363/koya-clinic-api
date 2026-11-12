import os
import re
import secrets
import uuid
from datetime import datetime, timezone

import psycopg
from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from psycopg.rows import dict_row
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from pathlib import Path
from fastapi.staticfiles import StaticFiles

DATABASE_URL = os.environ["DATABASE_URL"]
API_KEY = os.environ["API_KEY"]

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def check_key(key: str | None = Depends(api_key_header)):
    if key is None or not secrets.compare_digest(key.encode(), API_KEY.encode()):
        raise HTTPException(status_code=401, detail="invalid or missing API key")


app = FastAPI(dependencies=[Depends(check_key)])


@app.exception_handler(RequestValidationError)
async def validation_handler(request, exc):
    return JSONResponse(status_code=400, content={"error": "invalid request"})


@app.exception_handler(StarletteHTTPException)
async def http_handler(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})


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


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def parse_time(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


@app.post("/bookings", status_code=201)
def create_booking(body: NewBooking):
    name = body.name.strip()
    email = body.email.strip().lower()
    if not body.slot_id.strip() or not name or not EMAIL_RE.match(email):
        return JSONResponse(status_code=400, content={"error": "slot_id, name and a valid email are required"})

    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        slot = conn.execute("SELECT id, start_time FROM slots WHERE id = %s", (body.slot_id,)).fetchone()
        if slot is None:
            return JSONResponse(status_code=404, content={"error": "slot not found"})
        if parse_time(slot["start_time"]) <= datetime.now(timezone.utc):
            return JSONResponse(status_code=400, content={"error": "slot has already started"})

        try:
            row = conn.execute("""
                INSERT INTO bookings (id, slot_id, name, email, status)
                VALUES (%s, %s, %s, %s, 'confirmed')
                RETURNING id, slot_id, name, email, status, created_at
            """, (str(uuid.uuid4()), body.slot_id, name, email)).fetchone()
        except psycopg.errors.UniqueViolation:
            conn.rollback()
            return JSONResponse(status_code=409, content={"error": "slot already booked"})
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

@app.delete("/bookings/{booking_id}")
def cancel_booking(booking_id: str):
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        row = conn.execute("""
            UPDATE bookings SET status = 'cancelled'
            WHERE id = %s AND status = 'confirmed'
            RETURNING id, slot_id, name, email, status, created_at
        """, (booking_id,)).fetchone()
        if row is not None:
            return row
        exists = conn.execute("SELECT 1 FROM bookings WHERE id = %s", (booking_id,)).fetchone()

    if exists is None:
        return JSONResponse(status_code=404, content={"error": "booking not found"})
    return JSONResponse(status_code=409, content={"error": "booking already cancelled"})



app.mount("/web", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="web")