import sqlite3

from fastapi import APIRouter, Depends, HTTPException

import schemas
from database import get_db
from deps import current_user, notify

router = APIRouter(tags=["messages"])


@router.get("/orders/{reference}/messages")
def get_messages(reference: str, db: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    o = db.execute("SELECT * FROM orders WHERE reference=?", (reference,)).fetchone()
    if o is None:
        raise HTTPException(404, "Order not found")
    ok = user["role"] == "admin" or o["user_id"] == user["id"]
    if not ok and user["role"] == "rider":
        r = db.execute("SELECT id FROM riders WHERE user_id=?", (user["id"],)).fetchone()
        ok = r is not None and o["rider_id"] == r["id"]
    if not ok:
        raise HTTPException(403, "Not part of this order")
    rows = db.execute("""SELECT m.*, u.full_name FROM messages m JOIN users u ON u.id=m.sender_id
                         WHERE m.order_id=? ORDER BY m.id""", (o["id"],)).fetchall()
    return [{"id": r["id"], "sender": r["full_name"], "role": r["sender_role"],
             "text": r["text"], "created_at": r["created_at"]} for r in rows]


@router.post("/orders/{reference}/messages", status_code=201)
def post_message(reference: str, body: schemas.MessageIn, db: sqlite3.Connection = Depends(get_db),
                 user=Depends(current_user)):
    o = db.execute("SELECT * FROM orders WHERE reference=?", (reference,)).fetchone()
    if o is None:
        raise HTTPException(404, "Order not found")
    ok = user["role"] == "admin" or o["user_id"] == user["id"]
    rider_id = None
    if user["role"] == "rider":
        r = db.execute("SELECT id FROM riders WHERE user_id=?", (user["id"],)).fetchone()
        rider_id = r["id"] if r else None
        ok = rider_id is not None and o["rider_id"] == rider_id
    if not ok:
        raise HTTPException(403, "Not part of this order")
    db.execute("INSERT INTO messages (order_id, sender_id, sender_role, text) VALUES (?,?,?,?)",
               (o["id"], user["id"], user["role"], body.text.strip()))
    db.commit()
    # notify the other party
    rider = db.execute("SELECT user_id FROM riders WHERE id=?", (o["rider_id"],)).fetchone() if o["rider_id"] else None
    targets = []
    if user["role"] == "user" and rider:
        targets.append(rider["user_id"])
    elif user["role"] == "rider":
        targets.append(o["user_id"])
    elif user["role"] == "admin":
        if rider:
            targets.append(rider["user_id"])
        targets.append(o["user_id"])
    for t in set(targets):
        notify(db, t, "New message", f"Order {reference}: {body.text.strip()[:80]}")
    return {"ok": True}


@router.get("/admin/messages")
def all_messages(limit: int = 100, db: sqlite3.Connection = Depends(get_db),
                 user=Depends(__import__("deps").admin_user)):
    rows = db.execute("""SELECT m.*, u.full_name, o.reference FROM messages m
                         JOIN users u ON u.id=m.sender_id JOIN orders o ON o.id=m.order_id
                         ORDER BY m.id DESC LIMIT ?""", (min(limit, 500),)).fetchall()
    return [{"order": r["reference"], "sender": r["full_name"], "role": r["sender_role"],
             "text": r["text"], "created_at": r["created_at"]} for r in rows]
