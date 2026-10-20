import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

import config
import schemas
from database import get_db
from deps import admin_user, notify

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
def stats(db: sqlite3.Connection = Depends(get_db), user=Depends(admin_user)):
    def one(sql, a=()):
        return db.execute(sql, a).fetchone()[0]
    return {
        "users": one("SELECT COUNT(*) FROM users WHERE role='user'"),
        "verified_users": one("SELECT COUNT(*) FROM users WHERE role='user' AND verified=1"),
        "riders": one("SELECT COUNT(*) FROM riders"),
        "verified_riders": one("SELECT COUNT(*) FROM riders WHERE verified=1"),
        "orders": one("SELECT COUNT(*) FROM orders"),
        "orders_active": one("SELECT COUNT(*) FROM orders WHERE status IN ('paid','assigned','picked','delivering')"),
        "gmv": one("SELECT COALESCE(SUM(amount),0) FROM orders WHERE status!='cancelled'"),
        "sales_fees": one("SELECT COALESCE(SUM(sales_fee),0) FROM orders WHERE status!='cancelled'"),
        "credit_outstanding": one("SELECT COALESCE(SUM(credit_used),0) FROM users WHERE role='user'"),
        "credit_fees_est": round(one("SELECT COALESCE(SUM(credit_used),0) FROM users WHERE role='user'") * config.FEE_CREDIT / 100, 2),
        "delivery_fees": one("SELECT COALESCE(SUM(delivery_fee),0) FROM orders WHERE status!='cancelled'"),
        "bulk_orders": one("SELECT COUNT(*) FROM orders WHERE bulk=1"),
        "by_status": {r["status"]: r["n"] for r in db.execute("SELECT status, COUNT(*) n FROM orders GROUP BY status")},
    }


@router.get("/users")
def users(db: sqlite3.Connection = Depends(get_db), user=Depends(admin_user)):
    rows = db.execute("SELECT * FROM users WHERE role='user' ORDER BY verified, id DESC").fetchall()
    from deps import public_user
    return [public_user(r) for r in rows]


@router.post("/users/{user_id}/verify")
def verify_user(user_id: int, db: sqlite3.Connection = Depends(get_db), user=Depends(admin_user)):
    u = db.execute("SELECT * FROM users WHERE id=? AND role='user'", (user_id,)).fetchone()
    if u is None:
        raise HTTPException(404, "User not found")
    if not u["verified"]:
        db.execute("UPDATE users SET verified=1, credit_limit=? WHERE id=? AND employer!='' AND work_id!=''",
                   (config.CREDIT_DEFAULT, user_id))
        db.commit()
        u2 = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if u2["verified"]:
            db.execute("INSERT INTO credit_txn (user_id, kind, amount, note) VALUES (?,?,?,?)",
                       (user_id, "grant", config.CREDIT_DEFAULT, "Verification credit"))
            db.commit()
            from services.notify import send_notification
            send_notification(db, user_id, "Account approved",
                   f"Your GovFood account is verified. GHc{config.CREDIT_DEFAULT:.0f} credit activated - repayable in 1 month at {config.FEE_CREDIT:.0f}% fee.",
                   email=u["email"], phone=u["phone"])
    return {"ok": True, "verified": True, "credit_limit": config.CREDIT_DEFAULT}


@router.post("/credit")
def adjust_credit(body: schemas.CreditAdjustIn, db: sqlite3.Connection = Depends(get_db),
                  user=Depends(admin_user)):
    u = db.execute("SELECT * FROM users WHERE id=?", (body.user_id,)).fetchone()
    if u is None:
        raise HTTPException(404, "User not found")
    delta = body.limit - u["credit_limit"]
    db.execute("UPDATE users SET credit_limit=? WHERE id=?", (body.limit, body.user_id))
    db.execute("INSERT INTO credit_txn (user_id, kind, amount, note) VALUES (?,?,?,?)",
               (body.user_id, "adjust", delta, f"Admin set limit to {body.limit}"))
    db.commit()
    notify(db, body.user_id, "Credit updated", f"Your credit limit is now GHc{body.limit:,.0f}.")
    return {"ok": True}


@router.post("/settle")
def settle_month(month: str = "", channel: str = "bank", db: sqlite3.Connection = Depends(get_db), user=Depends(admin_user)):
    """Deduct outstanding credit for a month. channel='bank' (charge linked account via Paystack)
    or 'payroll' (Ministry deducts from worker salary). Records settlement + 15% credit fee."""
    month = month or __import__("datetime").date.today().strftime("%Y-%m")
    users = db.execute("SELECT * FROM users WHERE role='user' AND credit_used > 0").fetchall()
    total, fees, count = 0.0, 0.0, 0
    for u in users:
        existing = db.execute("SELECT id FROM settlements WHERE month=? AND user_id=?", (month, u["id"])).fetchone()
        if existing:
            continue
        amount = round(u["credit_used"], 2)
        fee = round(amount * config.FEE_CREDIT / 100, 2)
        db.execute("INSERT INTO settlements (month, user_id, amount, fee, channel) VALUES (?,?,?,?,?)",
                   (month, u["id"], amount, fee, channel))
        db.execute("UPDATE users SET credit_used=0 WHERE id=?", (u["id"],))
        db.execute("INSERT INTO credit_txn (user_id, kind, amount, fee, note) VALUES (?,?,?,?,?)",
                   (u["id"], "settle", amount, fee, f"{month} settlement - deducted from linked account"))
        from services.notify import send_notification
        via = "your salary (Ministry payroll)" if channel == "payroll" else "your linked bank account"
        send_notification(db, u["id"], "Credit settlement",
               f"GHc{amount:,.2f} credit (+GHc{fee:,.2f} fee) deducted from {via} for {month}.",
               email=u["email"], phone=u["phone"])
        total += amount; fees += fee; count += 1
    db.commit()
    return {"ok": True, "month": month, "settlements": count, "total": total, "fees": fees}


@router.get("/ministry-report")
def ministry_report(db: sqlite3.Connection = Depends(get_db), user=Depends(admin_user)):
    """Weekly invoice-style report per employer (ministry): workers, orders, kg per product, totals."""
    import datetime
    today = datetime.date.today()
    week_start = today - datetime.timedelta(days=today.weekday())
    rows = db.execute("""SELECT o.*, u.employer, u.full_name FROM orders o JOIN users u ON u.id=o.user_id
                         WHERE o.status!='cancelled' AND date(o.created_at) >= ?""",
                      (week_start.isoformat(),)).fetchall()
    ministries = {}
    for r in rows:
        m = ministries.setdefault(r["employer"] or "Unspecified", {"orders": 0, "workers": set(),
                                   "kg": 0.0, "amount": 0.0, "fees": 0.0, "items": {}})
        m["orders"] += 1; m["workers"].add(r["full_name"]); m["kg"] += r["total_kg"]
        m["amount"] += r["amount"]; m["fees"] += r["sales_fee"]
        for it in json.loads(r["items"]):
            m["items"][it["name"]] = round(m["items"].get(it["name"], 0) + it["qty"], 1)
    return {"week_start": week_start.isoformat(), "rows": [
        {"employer": k, "workers": len(v["workers"]), "orders": v["orders"], "kg": round(v["kg"], 1),
         "amount": round(v["amount"], 2), "fees": round(v["fees"], 2),
         "items": dict(sorted(v["items"].items(), key=lambda x: -x[1]))} for k, v in
        sorted(ministries.items(), key=lambda x: -x[1]["amount"])]}


@router.get("/payroll-export")
def payroll_export(employer: str = "", month: str = "", db: sqlite3.Connection = Depends(get_db),
                   user=Depends(admin_user)):
    """CSV deduction schedule for Ministry HR: worker, work ID, amount+fee to deduct from salary."""
    month = month or __import__("datetime").date.today().strftime("%Y-%m")
    sql = """SELECT u.full_name, u.work_id, u.employer, s.amount, s.fee, s.channel, s.month
             FROM settlements s JOIN users u ON u.id=s.user_id WHERE s.month=?"""
    args = [month]
    if employer:
        sql += " AND u.employer=?"; args.append(employer)
    sql += " ORDER BY u.employer, u.full_name"
    rows = db.execute(sql, args).fetchall()
    lines = ["Employer,Work ID,Name,Credit deducted,Fee (15%),Total deduction,Month"]
    for r in rows:
        lines.append(f'"{r["employer"]}","{r["work_id"]}","{r["full_name"]}",{r["amount"]:.2f},{r["fee"]:.2f},{r["amount"]+r["fee"]:.2f},{r["month"]}')
    return {"month": month, "count": len(rows), "csv": "\n".join(lines)}


@router.get("/orders")
def orders(status: str = "", db: sqlite3.Connection = Depends(get_db), user=Depends(admin_user)):
    sql = "SELECT * FROM orders"
    args = ()
    if status:
        sql += " WHERE status=?"; args = (status,)
    sql += " ORDER BY CASE WHEN status='paid' THEN 0 ELSE 1 END, id DESC LIMIT 200"
    rows = db.execute(sql, args).fetchall()
    from routers.orders import _order_out
    return [_order_out(db, o) for o in rows]


@router.post("/orders/{reference}/assign")
def assign_rider(reference: str, body: schemas.AssignIn, db: sqlite3.Connection = Depends(get_db),
                 user=Depends(admin_user)):
    o = db.execute("SELECT * FROM orders WHERE reference=?", (reference,)).fetchone()
    if o is None:
        raise HTTPException(404, "Order not found")
    if o["status"] not in ("paid", "assigned"):
        raise HTTPException(400, f"Order is {o['status']} - cannot reassign")
    r = db.execute("SELECT r.*, u.full_name FROM riders r JOIN users u ON u.id=r.user_id WHERE r.id=? AND r.verified=1 AND r.active=1",
                   (body.rider_id,)).fetchone()
    if r is None:
        raise HTTPException(400, "Rider not available (must be verified & active)")
    db.execute("UPDATE orders SET rider_id=?, status='assigned', assigned_at=datetime('now') WHERE id=?",
               (body.rider_id, o["id"]))
    db.commit()
    notify(db, r["user_id"], "New delivery", f"You are assigned order {reference}. Pick up and deliver.")
    notify(db, o["user_id"], "Rider assigned",
           f"{r['full_name']} is delivering your order {reference}. Chat and track live on your order page.")
    return {"ok": True, "rider": r["full_name"]}


@router.get("/riders")
def riders(db: sqlite3.Connection = Depends(get_db), user=Depends(admin_user)):
    rows = db.execute("""SELECT r.*, u.full_name, u.email, u.phone FROM riders r
                         JOIN users u ON u.id=r.user_id ORDER BY r.verified, r.id""").fetchall()
    return [{"id": r["id"], "name": r["full_name"], "email": r["email"], "phone": r["phone"],
             "dl_number": r["dl_number"], "plate": r["plate"], "photo": r["photo_path"],
             "verified": bool(r["verified"]), "active": bool(r["active"]),
             "lat": r["lat"], "lng": r["lng"]} for r in rows]


@router.post("/riders/{rider_id}/verify")
def verify_rider(rider_id: int, db: sqlite3.Connection = Depends(get_db), user=Depends(admin_user)):
    r = db.execute("SELECT * FROM riders WHERE id=?", (rider_id,)).fetchone()
    if r is None:
        raise HTTPException(404, "Rider not found")
    if not r["dl_number"] or not r["photo_path"]:
        raise HTTPException(400, "Rider must submit DL number + photo before verification")
    db.execute("UPDATE riders SET verified=1 WHERE id=?", (rider_id,))
    db.commit()
    notify(db, r["user_id"], "Rider verified", "You are verified! You will now receive delivery assignments.")
    return {"ok": True}


@router.post("/riders/{rider_id}/toggle")
def toggle_rider(rider_id: int, db: sqlite3.Connection = Depends(get_db), user=Depends(admin_user)):
    db.execute("UPDATE riders SET active = 1 - active WHERE id=?", (rider_id,))
    db.commit()
    return {"ok": True}
