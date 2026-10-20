# GovFood — Ministry Food Supply Platform

Government workers order foodstuffs at per-kg prices with GHc500 monthly credit,
instant MoMo/card payment, live GPS rider tracking, and in-app chat.

## Roles
- **Buyer (worker)**: registers → submits work ID + bank → admin verifies → GHc500
  credit granted → orders on credit (1-month repayment, 15% fee) or pays instantly.
- **Rider**: registers → uploads DL + photo → admin verifies → receives assignments,
  shares GPS, updates status (picked → delivering → delivered).
- **Admin**: verifies users & riders, assigns riders, manages catalog & credit limits,
  runs monthly settlements (15% credit fee), monitors all chats, views the weekly
  **Ministry report** (per-employer kg/orders/fees), sees 15% sales-fee totals.

## Run
    cd backend && pip install -r requirements.txt
    python tests_smoke.py        # 29/29
    uvicorn main:app --reload    # http://localhost:8000

## Deploy (Render)
GitHub repo → Dockerfile → attach 1GB persistent disk at /var/data → set env vars
(same pattern as the JapaFly platform; BROTHERSTRUST_* vars are not used here).
Rider photos persist via GOVFOOD_UPLOADS=/var/data/uploads.

## Fees (configurable via env)
- 15% on sales (recorded per order, Fees tab)
- 15% on credit (recorded at monthly settlement)
- Flat delivery fee per order (GOVFOOD_DELIVERY_FEE, default GHc10)

## Phase 4
- **Distance-based delivery fees**: haversine from the depot (GOVFOOD_DEPOT_LAT/LNG);
  tiers near ≤5km / mid ≤15km / far (env-settable fees). Live quote at checkout updates
  when the buyer captures GPS; flat fallback without coordinates.
- **Payroll channel**: settle with ?channel=payroll to mark deductions as Ministry
  salary deductions. /admin/payroll-export returns a CSV deduction schedule
  (employer, work ID, name, credit, 15% fee, total) ready for Ministry HR.

## Going live with Paystack (instant MoMo/card)
1. Paystack dashboard → activate business → copy LIVE secret key
2. Render env: PAYSTACK_SECRET_KEY=sk_live_...
3. Paystack dashboard → Webhooks → https://your-domain.com/payments/webhook
4. Orders placed with "instant" payment redirect to Paystack; the signed webhook
   settles them automatically (mock checkout is used automatically when no key is set).
