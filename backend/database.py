# GovFood - SQLite storage (persistent disk path via GOVFOOD_DB env).
import os
import sqlite3

DB_PATH = os.getenv("GOVFOOD_DB", "/var/data/govfood.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'user',          -- user | rider | admin
    employer TEXT NOT NULL DEFAULT '',
    work_id TEXT NOT NULL DEFAULT '',
    bank_name TEXT NOT NULL DEFAULT '',
    bank_acct TEXT NOT NULL DEFAULT '',
    verified INTEGER NOT NULL DEFAULT 0,
    credit_limit REAL NOT NULL DEFAULT 0,
    credit_used REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS riders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL REFERENCES users(id),
    dl_number TEXT NOT NULL DEFAULT '',
    plate TEXT NOT NULL DEFAULT '',
    photo_path TEXT NOT NULL DEFAULT '',
    verified INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    lat REAL, lng REAL, last_seen TEXT
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Staples',
    price REAL NOT NULL,             -- GHc per kg
    stock REAL NOT NULL DEFAULT 0,   -- kg
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reference TEXT UNIQUE NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id),
    items TEXT NOT NULL DEFAULT '[]',   -- [{product_id,name,qty,unit_price}]
    total_kg REAL NOT NULL DEFAULT 0,
    amount REAL NOT NULL,
    sales_fee REAL NOT NULL DEFAULT 0,  -- 15% on sales
    payment_method TEXT NOT NULL DEFAULT 'credit',  -- credit | instant
    status TEXT NOT NULL DEFAULT 'paid', -- paid | assigned | picked | delivering | delivered | cancelled
    rider_id INTEGER REFERENCES riders(id),
    address TEXT NOT NULL DEFAULT '',
    lat REAL, lng REAL,
    credit_applied REAL NOT NULL DEFAULT 0,
    delivery_fee REAL NOT NULL DEFAULT 0,
    delivery_km REAL,
    bulk INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    assigned_at TEXT, delivered_at TEXT
);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    reference TEXT UNIQUE NOT NULL,
    amount REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    method TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    paid_at TEXT
);
CREATE TABLE IF NOT EXISTS credit_txn (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    kind TEXT NOT NULL,             -- grant | spend | settle | adjust
    amount REAL NOT NULL,
    fee REAL NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS settlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    fee REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'deducted',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(month, user_id)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    sender_id INTEGER NOT NULL,
    sender_role TEXT NOT NULL DEFAULT 'user',
    text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    read_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    scols = {r[1] for r in conn.execute("PRAGMA table_info(settlements)")}
    if "channel" not in scols:
        conn.execute("ALTER TABLE settlements ADD COLUMN channel TEXT NOT NULL DEFAULT 'bank'")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(orders)")}
    if "delivery_fee" not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN delivery_fee REAL NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE orders ADD COLUMN delivery_km REAL")
        conn.execute("ALTER TABLE orders ADD COLUMN bulk INTEGER NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE orders ADD COLUMN note TEXT NOT NULL DEFAULT ''")
    conn.commit()
    conn.close()
