import uuid
from datetime import datetime, timezone

from fastapi.responses import JSONResponse
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

slots = []
bookings = []


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

@app.get("/slots")
def list_slots():
    return {"slots": slots}


@app.post("/reset")
def reset(body: ResetBody):
    bookings.clear()
    slots.clear()
    for s in body.slots:
        slots.append({"id": s.id, "provider": s.provider, "start": s.start, "end": s.end, "available": True})
    return {"message": "Done"}


@app.post("/bookings", status_code=201)
def create_booking(body: NewBooking):
    found = None
    for slot in slots:
        if slot["id"] == body.slot_id:
            found = slot
            break

    if found is None:
        return JSONResponse(status_code=404, content={"error": "slot not found"})

    booking = {
        "id": str(uuid.uuid4()),
        "slot_id": body.slot_id,
        "name": body.name,
        "email": body.email,
        "status": "confirmed",
        "created_at": datetime.now(timezone.utc)
    }
    bookings.append(booking)
    found["available"] = False
    return booking

@app.get("/bookings/{booking_id}")
def get_booking(booking_id: str):
    found = None
    for b in bookings:
        if b["id"] == booking_id:
            found = b
            break

    if found is None:
        return JSONResponse(status_code=404, content={"error": "booking not found"})

    return found