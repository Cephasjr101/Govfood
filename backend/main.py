import os
import time
from collections import defaultdict, deque

import config  # noqa: loads .env

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import seed
from database import get_db, init_db, DB_PATH
from routers import admin, auth, catalog, messages, orders, payments, riders

FRONTEND = os.path.join(os.path.dirname(__file__).replace("/backend", ""), "frontend")

app = FastAPI(title="GovFood API", version="1.0.0",
              description="Government worker food supply platform - orders, credit, riders, GPS tracking")


@app.on_event("startup")
def startup():
    init_db()
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    try:
        auth.ensure_admin(conn)
        seed.ensure_seed(conn)
        print(f"[govfood] admin: {config.ADMIN_EMAIL} | credit: GHc{config.CREDIT_DEFAULT:.0f} @ {config.FEE_CREDIT:.0f}% | sales fee {config.FEE_SALES:.0f}%")
    finally:
        conn.close()


@app.middleware("http")
async def force_https(request: Request, call_next):
    if request.method == "HEAD":
        return await call_next(request)
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = (request.headers.get("x-forwarded-host") or request.url.hostname or "")
    if proto == "http" and host.split(":")[0] not in ("localhost", "127.0.0.1", "testserver") and not os.getenv("ALLOW_HTTP"):
        return JSONResponse({"detail": "HTTPS required"}, status_code=308)
    return await call_next(request)


_buckets = defaultdict(deque)

@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path.startswith(("/uploads", "/css", "/js")):
        return await call_next(request)
    now = time.time()
    cls = "auth" if request.url.path.startswith("/auth/") else "global"
    limit = config.RATE_LIMIT_AUTH if cls == "auth" else 300
    fwd = request.headers.get("x-forwarded-for", "")
    ip = (fwd.split(",")[0].strip() if fwd else "") or (request.client.host if request.client else "anon")
    q = _buckets[(ip, cls)]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
        return JSONResponse({"detail": "Too many requests - slow down."}, status_code=429)
    q.append(now)
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline' https://unpkg.com; "
        "script-src 'self' 'unsafe-inline' https://unpkg.com; connect-src 'self' https://*.tile.openstreetmap.org; "
        "frame-ancestors 'none'")
    return resp


for r in (auth.router, catalog.router, orders.router, payments.router, riders.router, messages.router, admin.router):
    app.include_router(r)

if os.path.isdir(FRONTEND):
    app.mount("/uploads", StaticFiles(directory=os.path.join(FRONTEND, "uploads")), name="uploads")
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")


@app.exception_handler(404)
async def not_found(request, exc):
    if request.method == "GET" and not request.url.path.startswith("/api"):
        idx = os.path.join(FRONTEND, "index.html")
        if os.path.exists(idx):
            return FileResponse(idx)
    return JSONResponse({"detail": "Not found"}, status_code=404)
