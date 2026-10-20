import os
from pathlib import Path

def load_env(path):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

load_env(Path(__file__).resolve().parent.parent / ".env")

SECRET = os.getenv("GOVFOOD_SECRET", "dev-only-secret-change-me")
ADMIN_EMAIL = os.getenv("GOVFOOD_ADMIN_EMAIL", "admin@govfood.com").lower()
ADMIN_PASSWORD = os.getenv("GOVFOOD_ADMIN_PASSWORD", "GovFood#Admin1")
CREDIT_DEFAULT = float(os.getenv("GOVFOOD_CREDIT", "500"))
FEE_CREDIT = float(os.getenv("GOVFOOD_FEE_CREDIT", "15"))   # %
FEE_SALES = float(os.getenv("GOVFOOD_FEE_SALES", "15"))     # %
PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY", "")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
RATE_LIMIT_AUTH = int(os.getenv("RATE_LIMIT_AUTH", "10"))
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL", "no-reply@govfood.com")
SENDGRID_FROM_NAME = os.getenv("SENDGRID_FROM_NAME", "GovFood")
AT_USERNAME = os.getenv("AT_USERNAME", "sandbox")
AT_API_KEY = os.getenv("AT_API_KEY", "")
AT_SENDER_ID = os.getenv("AT_SENDER_ID", "GOVFOOD")
DELIVERY_FEE = float(os.getenv("GOVFOOD_DELIVERY_FEE", "10"))  # fallback when no GPS
DEPOT_LAT = float(os.getenv("GOVFOOD_DEPOT_LAT", "5.6037"))     # central Accra depot
DEPOT_LNG = float(os.getenv("GOVFOOD_DEPOT_LNG", "-0.1870"))
DELIVERY_NEAR_KM = float(os.getenv("GOVFOOD_DELIVERY_NEAR_KM", "5"))
DELIVERY_MID_KM = float(os.getenv("GOVFOOD_DELIVERY_MID_KM", "15"))
DELIVERY_FEE_NEAR = float(os.getenv("GOVFOOD_DELIVERY_FEE_NEAR", "8"))
DELIVERY_FEE_MID = float(os.getenv("GOVFOOD_DELIVERY_FEE_MID", "12"))
DELIVERY_FEE_FAR = float(os.getenv("GOVFOOD_DELIVERY_FEE_FAR", "20"))
UPLOAD_DIR = Path(os.getenv("GOVFOOD_UPLOADS", Path(__file__).resolve().parent.parent / "frontend" / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
