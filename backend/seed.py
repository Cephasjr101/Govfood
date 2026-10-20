# Starter catalog - everything priced PER KILOGRAM (GHc).
CATEGORIES = ["Staples", "Vegetables", "Proteins", "Frozen", "Grains", "Condiments", "Beverages", "Packaged"]

PRODUCTS = [
    ("Rice (local)", "Grains", 12.0), ("Rice (perfumed)", "Grains", 18.0),
    ("Beans (black-eyed)", "Staples", 14.0), ("Beans (red)", "Staples", 15.0),
    ("Plantain", "Staples", 8.0), ("Cassava", "Staples", 6.0),
    ("Tomatoes (fresh)", "Vegetables", 10.0), ("Pepper (scotch bonnet)", "Vegetables", 16.0),
    ("Pepper (bell)", "Vegetables", 14.0), ("Okro", "Vegetables", 9.0),
    ("Tin tomatoes", "Packaged", 22.0), ("Baked beans", "Packaged", 20.0),
    ("Fish (tilapia)", "Proteins", 28.0), ("Fish (mackerel)", "Proteins", 26.0),
    ("Meat (beef)", "Proteins", 38.0), ("Meat (goat)", "Proteins", 42.0),
    ("Chicken (whole)", "Frozen", 30.0), ("Fish (frozen)", "Frozen", 24.0),
    ("Gari", "Staples", 7.0), ("Sugar", "Condiments", 11.0), ("Salt", "Condiments", 4.0),
    ("Milo", "Beverages", 34.0), ("Milk (powdered)", "Beverages", 32.0),
    ("Spaghetti", "Packaged", 13.0), ("Maize", "Grains", 7.0), ("Yam", "Staples", 9.0),
]

def ensure_seed(db):
    if db.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        for name, cat, price in PRODUCTS:
            db.execute("INSERT INTO products (name, category, price, stock) VALUES (?,?,?,?)",
                       (name, cat, price, 500.0))
        db.commit()
