import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

import config
from database import get_db
from deps import current_user, make_reference
from services.notify import send_notification

router = APIRouter(tags=["payments"])


def _settle(db, order_id: int, method: str) -> dict:
    o = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    db.execute("""UPDATE orders SET status='paid' WHERE id=? AND status='pending_payment'""", (order_id,))
    db.execute("""UPDATE payments SET status='paid', method=?, paid_at=datetime('now')
                  WHERE order_id=? AND status='pending'""", (method, order_id))
    buyer = db.execute("SELECT * FROM users WHERE id=?", (o["user_id"],)).fetchone()
    send_notification(db, o["user_id"], "Order confirmed",
        f"Reference {o['reference']} - {o['total_kg']:.1f}kg, GHc{o['amount']:,.2f} paid. Assigning a rider.",
        email=buyer["email"], phone=buyer["phone"])
    for a in db.execute("SELECT id FROM users WHERE role='admin'").fetchall():
        send_notification(db, a["id"], "New order", f"{o['reference']} - {buyer['full_name']} - GHc{o['amount']:,.2f}")
    return {"ok": True, "status": "paid", "reference": o["reference"]}


@router.post("/payments/initialize")
def initialize(body: dict, db: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    ref = str(body.get("reference", ""))
    o = db.execute("SELECT * FROM orders WHERE reference=? AND user_id=?", (ref, user["id"])).fetchone()
    if o is None:
        raise HTTPException(404, "Order not found")
    if o["status"] != "pending_payment":
        return {"already_paid": o["status"] == "paid", "reference": ref}
    if not config.PAYSTACK_SECRET_KEY:
        return {"mock": True, "reference": ref, "amount": o["amount"] + o["delivery_fee"],
                "pay_path": f"/#/pay/{ref}"}
    gateway_ref = "pay-" + make_reference("")[3:]
    db.execute("INSERT INTO payments (order_id, reference, amount) VALUES (?,?,?)",
               (o["id"], gateway_ref, o["amount"] + o["delivery_fee"]))
    try:
        import urllib.request
        req = urllib.request.Request("https://api.paystack.co/transaction/initialize",
            data=json.dumps({"email": user["email"], "amount": int(o["amount"] * 100),
                             "reference": gateway_ref, "currency": "GHS",
                             "callback_url": f"{config.BASE_URL}/api/payments/callback",
                             "metadata": {"order_reference": ref}}).encode(),
            headers={"Authorization": "Bearer " + config.PAYSTACK_SECRET_KEY, "Content-Type": "application/json"}, method="POST")
        d = json.loads(urllib.request.urlopen(req, timeout=25).read().decode())
        return {"authorization_url": d["data"]["authorization_url"], "reference": ref}
    except Exception as exc:
        raise HTTPException(502, f"Paystack error: {exc}")


@router.post("/payments/confirm")
def confirm(body: dict, db: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    ref = str(body.get("reference", ""))
    o = db.execute("SELECT * FROM orders WHERE reference=? AND user_id=?", (ref, user["id"])).fetchone()
    if o is None:
        raise HTTPException(404, "Order not found")
    if config.PAYSTACK_SECRET_KEY:
        raise HTTPException(400, "Live mode: complete payment on the Paystack checkout page")
    if o["status"] == "paid":
        return {"ok": True, "status": "paid", "reference": ref}
    if o["status"] != "pending_payment":
        raise HTTPException(400, f"Order is {o['status']}")
    covered = db.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE order_id=? AND status IN ('pending','paid')", (o["id"],)).fetchone()[0]
    if covered < o["amount"]:
        db.execute("INSERT INTO payments (order_id, reference, amount, status) VALUES (?,?,?,'pending')",
                   (o["id"], "pay-" + make_reference("")[3:], o["amount"]))
    return _settle(db, o["id"], str(body.get("method", "MoMo")))


@router.get("/payments/callback")
def callback(request: Request, db: sqlite3.Connection = Depends(get_db)):
    gateway_ref = request.query_params.get("reference", "")
    row = db.execute("SELECT * FROM payments WHERE reference=?", (gateway_ref,)).fetchone()
    ok = False
    if row and config.PAYSTACK_SECRET_KEY:
        try:
            import urllib.request
            req = urllib.request.Request("https://api.paystack.co/transaction/verify/" + gateway_ref,
                headers={"Authorization": "Bearer " + config.PAYSTACK_SECRET_KEY})
            d = json.loads(urllib.request.urlopen(req, timeout=25).read().decode())
            ok = d.get("status") and d["data"]["status"] == "success"
        except Exception:
            ok = False
    if row and ok:
        _settle(db, row["order_id"], "Card/MoMo")
    return RedirectResponse(f"/#/orders")


@router.post("/payments/webhook")
async def webhook(request: Request, db: sqlite3.Connection = Depends(get_db)):
    raw = await request.body()
    try:
        payload = json.loads(raw or b"{}")
    except Exception:
        return {"ok": True}
    if config.PAYSTACK_SECRET_KEY:
        import hashlib, hmac
        sig = request.headers.get("x-paystack-signature", "")
        expected = hmac.new(config.PAYSTACK_SECRET_KEY.encode(), raw, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise HTTPException(401, "Invalid signature")
    if payload.get("event") == "charge.success":
        gateway_ref = (payload.get("data") or {}).get("reference", "")
        row = db.execute("SELECT * FROM payments WHERE reference=? AND status='pending'", (gateway_ref,)).fetchone()
        if row:
            _settle(db, row["order_id"], "Card/MoMo")
    return {"ok": True}


@router.post("/orders/{reference}/cancel")
def cancel_pending(reference: str, db: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    """Cancel an unpaid (pending_payment) order - restocks the items."""
    o = db.execute("SELECT * FROM orders WHERE reference=? AND user_id=?", (reference, user["id"])).fetchone()
    if o is None:
        raise HTTPException(404, "Order not found")
    if o["status"] != "pending_payment":
        raise HTTPException(400, f"Order is {o['status']} - cannot cancel here")
    for it in json.loads(o["items"]):
        db.execute("UPDATE products SET stock = stock + ? WHERE id=?", (it["qty"], it["product_id"]))
    db.execute("UPDATE orders SET status='cancelled' WHERE id=?", (o["id"],))
    db.execute("DELETE FROM payments WHERE order_id=? AND status='pending'", (o["id"],))
    db.commit()
    return {"ok": True, "status": "cancelled"}
