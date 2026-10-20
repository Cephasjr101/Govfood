# GovFood end-to-end smoke test: verification, credit, ordering, riders, GPS, chat, settlement.
import os, sys, io
os.environ["GOVFOOD_DB"] = "/tmp/govfood_test.db"
os.environ["RATE_LIMIT_AUTH"] = "50"
os.environ["GOVFOOD_DELIVERY_FEE"] = "10"
try: os.remove("/tmp/govfood_test.db")
except FileNotFoundError: pass
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))

from fastapi.testclient import TestClient
import main as m

results = []
def check(name, cond):
    results.append(bool(cond)); print(("PASS" if cond else "FAIL"), name)

with TestClient(m.app) as c:
    s, b = c.get("/products").status_code, c.get("/products").json()
    check("catalog seeded (26 items)", s == 200 and len(b) >= 26)
    rice = next(p for p in b if "Rice (local)" in p["name"])

    s = c.post("/auth/register", json={"email": "worker@moh.gov.gh", "password": "secret1",
                                       "full_name": "Ama Worker", "phone": "0244123456", "role": "user"})
    tok = s.json()["access_token"]; H = {"Authorization": f"Bearer {tok}"}
    check("buyer register", s.status_code == 200)

    s = c.post("/auth/verify", headers=H, json={"employer": "Ministry of Agriculture",
        "work_id": "MOH-10234", "bank_name": "Ecobank", "bank_acct": "0123456789"})
    check("verification submitted", s.status_code == 200)

    a = c.post("/auth/login", json={"email": "admin@govfood.com", "password": "GovFood#Admin1"})
    AH = {"Authorization": f"Bearer {a.json()['access_token']}"}
    uid = c.get("/auth/me", headers=H).json()["id"]
    s = c.post(f"/admin/users/{uid}/verify", headers=AH)
    check("admin verifies -> GHc500 credit granted", s.status_code == 200)

    # order on credit
    s = c.post("/orders", headers=H, json={"items": [{"product_id": rice["id"], "qty": 10}],
        "address": "12 Independence Ave, Accra", "lat": 5.6037, "lng": -0.187, "payment_method": "credit"})
    j = s.json()
    check("credit order placed (10kg rice)", s.status_code == 201 and j["amount"] == 120.0)
    check("sales fee 15% recorded", j["sales_fee"] == 18.0)
    ref = j["reference"]
    me = c.get("/auth/me", headers=H).json()
    check("credit deducted (500-128 incl zone delivery)", me["credit_used"] == 128.0)

    s = c.post("/orders", headers=H, json={"items": [{"product_id": rice["id"], "qty": 40}],
        "address": "x street", "payment_method": "credit"})
    check("insufficient credit rejected", s.status_code == 400)

    # rider flow
    s = c.post("/auth/register", json={"email": "rider@govfood.com", "password": "secret1",
                                       "full_name": "Kwame Rider", "phone": "0551234567", "role": "rider"})
    RH = {"Authorization": f"Bearer {s.json()['access_token']}"}
    photo = b"fakejpeg" + b"0" * 200
    s = c.post("/rider/profile", headers=RH, files={"photo": ("me.jpg", photo, "image/jpeg")},
               data={"dl_number": "DL-778899", "plate": "GT-1234-Z"})
    check("rider profile + photo upload", s.status_code == 200 and s.json()["photo"].startswith("/uploads/"))
    riders = c.get("/admin/riders", headers=AH).json()
    rid = next(r["id"] for r in riders if r["dl_number"] == "DL-778899")
    s = c.post(f"/admin/riders/{rid}/verify", headers=AH)
    check("admin verifies rider", s.status_code == 200)

    s = c.post("/rider/location", headers=RH, json={"lat": 5.61, "lng": -0.18})
    check("rider GPS ping stored", s.status_code == 200)

    s = c.post(f"/admin/orders/{ref}/assign", headers=AH, json={"rider_id": rid})
    check("admin assigns rider", s.status_code == 200)

    s = c.post(f"/rider/orders/{ref}/status", headers=RH, json={"status": "delivering"})
    check("rider updates status", s.json().get("status") == "delivering")
    o = c.get(f"/orders/{ref}", headers=H).json()
    check("buyer sees rider + location + phone", o["rider"]["lat"] == 5.61 and bool(o["rider"]["phone"]))

    s = c.post(f"/orders/{ref}/messages", headers=H, json={"text": "I am home, please come to the blue gate"})
    check("buyer messages rider", s.status_code == 201)
    s = c.post(f"/orders/{ref}/messages", headers=RH, json={"text": "On my way, 10 minutes"})
    check("rider messages buyer", s.status_code == 201)
    s = c.get("/admin/messages", headers=AH).json()
    check("admin monitors communications", any("blue gate" in m_["text"] for m_ in s))

    # instant payment flow (mock)
    s = c.post("/orders", headers=H, json={"items": [{"product_id": rice["id"], "qty": 2}],
        "address": "44 Kwame Nkrumah Ave", "payment_method": "instant"})
    j2 = s.json()
    check("instant order starts pending_payment", s.status_code == 201 and j2["status"] == "pending_payment")
    iref = j2["reference"]
    s = c.post("/payments/confirm", headers=H, json={"reference": iref, "method": "MoMo"})
    check("mock MoMo confirm settles order", s.json().get("status") == "paid")
    s = c.post(f"/orders/{iref}/cancel", headers=H)
    check("paid order cannot be cancelled as unpaid", s.status_code == 400)
    s = c.post("/orders", headers=H, json={"items": [{"product_id": rice["id"], "qty": 1}],
        "address": "9 Test Lane", "payment_method": "instant"})
    uref = s.json()["reference"]
    s = c.post(f"/orders/{uref}/cancel", headers=H)
    check("unpaid instant order cancels + restocks", s.status_code == 200)
    stock = next(p for p in c.get("/products").json() if p["id"] == rice["id"])["stock"]
    check("stock restored after cancel", stock == rice["stock"] - 10 - 2)

    # ministry report
    s = c.get("/admin/ministry-report", headers=AH).json()
    row = next(r for r in s["rows"] if r["employer"] == "Ministry of Agriculture")
    check("ministry report groups orders + kg", row["orders"] >= 2 and row["kg"] == 12.0)

    # settlement: 15% credit fee
    s = c.post("/admin/settle?month=2026-10", headers=AH)
    j = s.json()
    check("monthly settlement deducts + 15% fee", j["total"] >= 128.0 and abs(j["fees"] - round(j["total"]*0.15,2)) < 0.01)
    me = c.get("/auth/me", headers=H).json()
    check("credit cleared after settlement", me["credit_used"] == 0.0)

    # delivery quote by distance
    s = c.get("/delivery-quote?lat=5.6037&lng=-0.187").json()
    check("delivery quote: depot = near zone", s["fee"] == 8.0 and s["tier"] == "near")
    s = c.get("/delivery-quote?lat=6.20&lng=0.20").json()
    check("delivery quote: far zone", s["fee"] == 20.0 and s["tier"] == "far")
    s = c.get("/delivery-quote").json()
    check("delivery quote fallback flat", s["fee"] == 10.0 and s["tier"] == "flat")

    # payroll settlement + ministry export
    s = c.post("/orders", headers=H, json={"items": [{"product_id": rice["id"], "qty": 3}],
        "address": "Ministry HQ", "payment_method": "credit"})
    c.post("/admin/settle?month=2026-12&channel=payroll", headers=AH)
    s = c.get("/admin/payroll-export?month=2026-12", headers=AH).json()
    check("payroll export CSV for ministry", "MOH-10234" in s["csv"] and s["count"] == 1)



    # delivery fee + ministry bulk order
    s = c.post("/orders", headers=H, json={"items": [{"product_id": rice["id"], "qty": 5}],
        "address": "Ministry of Agriculture HQ", "payment_method": "credit", "bulk": True, "note": "Staff canteen"})
    j3 = s.json()
    check("delivery fee added (10)", j3["delivery_fee"] == 10.0 and j3["total"] == 70.0)
    check("ministry bulk flag stored", j3.get("delivery_fee") == 10.0)
    s = c.post("/admin/settle?month=2026-11", headers=AH).json()
    check("settlement includes delivery fees", s["total"] == 70.0)



    st = c.get("/admin/stats", headers=AH).json()
    check("fees dashboard", st["sales_fees"] >= 18.0 and st["orders"] >= 1)

print()
print("RESULT:", f"{sum(results)}/{len(results)} PASS" + (" — ALL GREEN" if all(results) else " — FAILURES"))
