import secrets
import sqlite3

from fastapi import Depends, HTTPException

import security
from database import get_db


def current_user(request: __import__("fastapi").Request, db: sqlite3.Connection = Depends(get_db)):
    auth = request.headers.get("Authorization", "")
    payload = security.decode_token(auth[7:]) if auth.startswith("Bearer ") else None
    if not payload:
        raise HTTPException(401, "Sign in to continue")
    user = db.execute("SELECT * FROM users WHERE id = ?", (int(payload["sub"]),)).fetchone()
    if user is None:
        raise HTTPException(401, "Account no longer exists")
    return user


def admin_user(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Admin access required")
    return user


def rider_user(user=Depends(current_user)):
    if user["role"] != "rider":
        raise HTTPException(403, "Rider access required")
    return user


def make_reference(prefix="GF"):
    return f"{prefix}-{secrets.token_urlsafe(5).upper().replace('_', 'X').replace('-', 'K')}"


def notify(db, user_id, title, body=""):
    db.execute("INSERT INTO notifications (user_id, title, body) VALUES (?,?,?)",
               (user_id, title[:200], body[:500]))


def public_user(u: sqlite3.Row) -> dict:
    return {"id": u["id"], "email": u["email"], "full_name": u["full_name"], "phone": u["phone"],
            "role": u["role"], "employer": u["employer"], "work_id": u["work_id"],
            "verified": bool(u["verified"]), "credit_limit": u["credit_limit"],
            "credit_used": round(u["credit_used"], 2),
            "credit_available": round(max(u["credit_limit"] - u["credit_used"], 0), 2),
            "created_at": u["created_at"]}
