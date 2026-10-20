import sqlite3

from fastapi import APIRouter, Depends, HTTPException

import config
import schemas
import security
from database import get_db
from deps import current_user, public_user

router = APIRouter(prefix="/auth", tags=["auth"])


def ensure_admin(db: sqlite3.Connection):
    if db.execute("SELECT id FROM users WHERE email=?", (config.ADMIN_EMAIL,)).fetchone() is None:
        db.execute("INSERT INTO users (email, password_hash, full_name, role, verified, credit_limit) VALUES (?,?,'GovFood Admin','admin',1,0)",
                   (config.ADMIN_EMAIL, security.hash_password(config.ADMIN_PASSWORD)))
        db.commit()


@router.post("/register")
def register(body: schemas.RegisterIn, db: sqlite3.Connection = Depends(get_db)):
    email = body.email.lower().strip()
    if db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
        raise HTTPException(409, "An account with this email already exists")
    cur = db.execute(
        "INSERT INTO users (email, password_hash, full_name, phone, role) VALUES (?,?,?,?,?)",
        (email, security.hash_password(body.password), body.full_name.strip(), body.phone.strip(), body.role))
    db.commit()
    user = db.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    if body.role == "rider":
        db.execute("INSERT INTO riders (user_id) VALUES (?)", (user["id"],))
        db.commit()
    return {"access_token": security.create_token(user["id"], user["role"]),
            "token_type": "bearer", "user": public_user(user)}


@router.post("/login")
def login(body: schemas.LoginIn, db: sqlite3.Connection = Depends(get_db)):
    user = db.execute("SELECT * FROM users WHERE email=?", (body.email.lower().strip(),)).fetchone()
    if user is None or not security.verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Incorrect email or password")
    return {"access_token": security.create_token(user["id"], user["role"]),
            "token_type": "bearer", "user": public_user(user)}


@router.get("/me")
def me(user=Depends(current_user)):
    return public_user(user)


@router.post("/verify")
def submit_verification(body: schemas.VerifyIn, db: sqlite3.Connection = Depends(get_db),
                        user=Depends(current_user)):
    if user["role"] == "rider":
        raise HTTPException(400, "Riders are verified through the rider dashboard")
    db.execute("UPDATE users SET employer=?, work_id=?, bank_name=?, bank_acct=? WHERE id=?",
               (body.employer.strip(), body.work_id.strip(), body.bank_name.strip(), body.bank_acct.strip(), user["id"]))
    db.commit()
    return {"ok": True, "detail": "Verification submitted - admin will review and approve your account + GHc500 credit."}
