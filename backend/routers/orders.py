import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

import config
import schemas
from database import get_db
import config
import delivery
from deps import current_user, make_reference, notify, rider_user

router = APIRouter(tags=["orders"])

STATUSES = ["pending_payment", "paid", "assigned", "picked", "delivering", "delivered", "cancelled"]


def _order_out(db, o: sqlite3.Row) -> dict:
    rider = None
    if o["rider_id"]:
        r = db.execute("""SELECT r.*, u.full_name, u.phone FROM riders r JOIN users u ON u.id=r.user_id
                          WHERE r.id=?""", (o["rider_id"],)).fetchone()
        if r:
            rider = {"id": r["id"], "name": r["full_name"], "phone": r["phone"],
                     "photo": r["photo_path"], "lat": r["lat"], "lng": r["lng"],
                     "plate": r["plate"], "last_seen": r["last_seen"], "verified": bool(r["verified"])}
    buyer = db.execute("SELECT full_name, phone FROM users WHERE id=?", (o["user_id"],)).fetchone()
    return {"reference": o["reference"], "status": o["status"], "items": json.loads(o["items"]),
            "total_kg": round(o["total_kg"], 2), "amount": o["amount"], "sales_fee": o["sales_fee"],
            "payment_method": o["payment_method"], "address": o["address"],
            "lat": o["lat"], "lng": o["lng"], "credit_applied": o["credit_applied"],
            "delivery_fee": o["delivery_fee"], "delivery_km": o["delivery_km"] if "delivery_km" in o.keys() else None, "bulk": bool(o["bulk"]), "note": o["note"],
            "total": round(o["amount"] + o["delivery_fee"], 2),
            "rider": rider, "buyer": {"name": buyer["full_name"], "phone": buyer["phone"]},
            "created_at": o["created_at"], "delivered_at": o["delivered_at"]}


@router.post("/orders", status_code=201)
def create_order(body: schemas.OrderIn, db: sqlite3.Connection = Depends(get_db),
                 user=Depends(current_user)):
    if user["role"] != "user":
        raise HTTPException(403, "Only buyer accounts can place orders")
    if not user["verified"]:
        raise HTTPException(403, "Verify your work ID and bank account first (Profile page)")
    if not body.items:
        raise HTTPException(400, "Cart is empty")

    items, total_kg, amount = [], 0.0, 0.0
    for it in body.items:
        p = db.execute("SELECT * FROM products WHERE id=? AND active=1", (it.product_id,)).fetchone()
        if p is None:
            raise HTTPException(400, f"Product {it.product_id} unavailable")
        if p["stock"] < it.qty:
            raise HTTPException(409, f"Only {p['stock']:.1f}kg of {p['name']} left")
        items.append({"product_id": p["id"], "name": p["name"], "qty": round(it.qty, 2),
                      "unit_price": p["price"], "line": round(it.qty * p["price"], 2)})
        total_kg += it.qty
        amount += it.qty * p["price"]
    amount = round(amount, 2)
    sales_fee = round(amount * config.FEE_SALES / 100, 2)
    dq = delivery.quote(body.lat, body.lng)
    delivery_fee = round(dq["fee"], 2)
    total = round(amount + delivery_fee, 2)
    reference = make_reference("GF")

    credit_applied = 0.0
    initial_status = "pending_payment" if body.payment_method == "instant" else "paid"
    if body.payment_method == "credit":
        available = user["credit_limit"] - user["credit_used"]
        if available < total:
            raise HTTPException(400,
                f"Credit insufficient: GHc{available:,.2f} available of GHc{user['credit_limit']:,.0f} (incl. GHc{delivery_fee:,.0f} delivery). Use instant payment or reduce the order.")
        db.execute("UPDATE users SET credit_used = credit_used + ? WHERE id=?", (total, user["id"]))
        db.execute("INSERT INTO credit_txn (user_id, kind, amount, note) VALUES (?,?,?,?)",
                   (user["id"], "spend", total, f"Order {reference}"))
        credit_applied = total

    for it in items:
        db.execute("UPDATE products SET stock = stock - ? WHERE id=?", (it["qty"], it["product_id"]))

    db.execute("""INSERT INTO orders (reference, user_id, items, total_kg, amount, sales_fee,
                  payment_method, status, address, lat, lng, credit_applied, delivery_fee, delivery_km, bulk, note)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
               (reference, user["id"], json.dumps(items), round(total_kg, 2), amount, sales_fee,
                body.payment_method, initial_status, body.address.strip(), body.lat, body.lng, credit_applied,
                delivery_fee, dq["km"], 1 if body.bulk else 0, body.note.strip()))
    db.commit()
    if body.payment_method == "credit":
        notify(db, user["id"], "Order placed",
               f"Reference {reference} - {total_kg:.1f}kg, GHc{amount:,.2f} on credit. We are assigning a rider.")
        admins = db.execute("SELECT id FROM users WHERE role='admin'").fetchall()
        for a in admins:
            notify(db, a["id"], "New order", f"{reference} - {user['full_name']} - GHc{amount:,.2f} - assign a rider.")
    return {"reference": reference, "status": initial_status, "amount": amount, "sales_fee": sales_fee,
            "delivery_fee": delivery_fee, "delivery_km": dq["km"], "delivery_tier": dq["tier"], "total": total, "credit_applied": credit_applied}


@router.get("/delivery-quote")
def delivery_quote(lat: float = None, lng: float = None, db: sqlite3.Connection = Depends(get_db)):
    return delivery.quote(lat, lng)


@router.get("/orders/mine")
def my_orders(db: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    rows = db.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 50",
                      (user["id"],)).fetchall()
    return [_order_out(db, o) for o in rows]


@router.get("/orders/{reference}")
def order_detail(reference: str, db: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    o = db.execute("SELECT * FROM orders WHERE reference=?", (reference,)).fetchone()
    if o is None:
        raise HTTPException(404, "Order not found")
    if user["role"] == "user" and o["user_id"] != user["id"]:
        raise HTTPException(403, "Not your order")
    return _order_out(db, o)


# ---------------- rider side ----------------

@router.get("/rider/orders")
def rider_orders(db: sqlite3.Connection = Depends(get_db), user=Depends(rider_user)):
    r = db.execute("SELECT * FROM riders WHERE user_id=?", (user["id"],)).fetchone()
    if r is None:
        return []
    rows = db.execute("""SELECT o.* FROM orders o WHERE o.rider_id=? AND o.status IN ('assigned','picked','delivering')
                         ORDER BY o.id DESC""", (r["id"],)).fetchall()
    return [_order_out(db, o) for o in rows]


@router.post("/rider/location")
def rider_location(body: schemas.LocationIn, db: sqlite3.Connection = Depends(get_db),
                   user=Depends(rider_user)):
    db.execute("UPDATE riders SET lat=?, lng=?, last_seen=datetime('now') WHERE user_id=?",
               (body.lat, body.lng, user["id"]))
    db.commit()
    return {"ok": True}


@router.post("/rider/orders/{reference}/status")
def rider_status(reference: str, body: schemas.StatusIn, db: sqlite3.Connection = Depends(get_db),
                 user=Depends(rider_user)):
    o = db.execute("SELECT * FROM orders WHERE reference=?", (reference,)).fetchone()
    if o is None:
        raise HTTPException(404, "Order not found")
    r = db.execute("SELECT * FROM riders WHERE user_id=?", (user["id"],)).fetchone()
    if o["rider_id"] != r["id"]:
        raise HTTPException(403, "Not your assigned order")
    db.execute("UPDATE orders SET status=?, delivered_at=CASE WHEN ?='delivered' THEN datetime('now') ELSE delivered_at END WHERE id=?",
               (body.status, body.status, o["id"]))
    db.commit()
    from services.notify import send_notification
    buyer_u = db.execute("SELECT * FROM users WHERE id=?", (o["user_id"],)).fetchone()
    send_notification(db, o["user_id"], f"Order {body.status}", f"Reference {reference} is now {body.status}.",
                      email=buyer_u["email"], phone=buyer_u["phone"])
    return {"ok": True, "status": body.status}
