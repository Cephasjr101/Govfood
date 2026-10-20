import sqlite3

from fastapi import APIRouter, Depends, HTTPException

import schemas
from database import get_db
from deps import admin_user

router = APIRouter(tags=["catalog"])


@router.get("/products")
def products(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT * FROM products WHERE active=1 ORDER BY category, name").fetchall()
    return [{"id": r["id"], "name": r["name"], "category": r["category"],
             "price": r["price"], "stock": round(r["stock"], 1)} for r in rows]


@router.post("/admin/products")
def upsert_product(body: schemas.ProductIn, product_id: int = 0,
                   db: sqlite3.Connection = Depends(get_db), user=Depends(admin_user)):
    if product_id:
        db.execute("UPDATE products SET name=?, category=?, price=?, stock=? WHERE id=?",
                   (body.name, body.category, body.price, body.stock, product_id))
    else:
        db.execute("INSERT INTO products (name, category, price, stock) VALUES (?,?,?,?)",
                   (body.name, body.category, body.price, body.stock))
    db.commit()
    return {"ok": True}


@router.post("/admin/products/{product_id}/toggle")
def toggle_product(product_id: int, db: sqlite3.Connection = Depends(get_db), user=Depends(admin_user)):
    db.execute("UPDATE products SET active = 1 - active WHERE id=?", (product_id,))
    db.commit()
    return {"ok": True}
