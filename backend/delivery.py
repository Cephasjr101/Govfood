# Distance-based delivery fees from the central depot (haversine).
import math

import config


def distance_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def quote(lat=None, lng=None) -> dict:
    """Delivery fee by distance tier from the depot. Falls back to the flat fee without GPS."""
    if lat is None or lng is None:
        return {"fee": config.DELIVERY_FEE, "km": None, "tier": "flat"}
    km = distance_km(config.DEPOT_LAT, config.DEPOT_LNG, lat, lng)
    if km <= config.DELIVERY_NEAR_KM:
        tier, fee = "near", config.DELIVERY_FEE_NEAR
    elif km <= config.DELIVERY_MID_KM:
        tier, fee = "mid", config.DELIVERY_FEE_MID
    else:
        tier, fee = "far", config.DELIVERY_FEE_FAR
    return {"fee": fee, "km": round(km, 1), "tier": tier}
