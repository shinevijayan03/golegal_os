"""
GoLegal Rental Rate Assist (PRD 12.2 - Rental Rate Negotiation Assist)

Micro-market benchmark for fair monthly rent and customary deposit norms.
The dataset is a curated seed (INR per month, 2026) and is intentionally
small; production would source it from the platform's own executed deals.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# city -> locality -> {bhk: (low, high)}
MICRO_MARKET: Dict[str, Dict[str, Dict[str, tuple]]] = {
    "bangalore": {
        "_default": {"1BHK": (14000, 22000), "2BHK": (24000, 38000), "3BHK": (38000, 65000)},
        "bellandur": {"1BHK": (16000, 24000), "2BHK": (26000, 40000), "3BHK": (42000, 70000)},
        "whitefield": {"1BHK": (15000, 22000), "2BHK": (24000, 36000), "3BHK": (38000, 60000)},
        "indiranagar": {"1BHK": (22000, 32000), "2BHK": (35000, 55000), "3BHK": (55000, 95000)},
        "koramangala": {"1BHK": (22000, 32000), "2BHK": (35000, 55000), "3BHK": (55000, 90000)},
        "hsr layout": {"1BHK": (18000, 26000), "2BHK": (28000, 42000), "3BHK": (45000, 70000)},
        "mahadevapura": {"1BHK": (14000, 21000), "2BHK": (23000, 34000), "3BHK": (36000, 55000)},
        "electronic city": {"1BHK": (11000, 17000), "2BHK": (17000, 26000), "3BHK": (26000, 40000)},
        "jayanagar": {"1BHK": (16000, 24000), "2BHK": (26000, 40000), "3BHK": (40000, 65000)},
        "varthur": {"1BHK": (13000, 19000), "2BHK": (20000, 30000), "3BHK": (30000, 48000)},
    },
    "delhi": {
        "_default": {"1BHK": (12000, 20000), "2BHK": (20000, 35000), "3BHK": (35000, 65000)},
        "dwarka": {"1BHK": (13000, 20000), "2BHK": (20000, 32000), "3BHK": (32000, 50000)},
        "saket": {"1BHK": (18000, 28000), "2BHK": (30000, 50000), "3BHK": (50000, 90000)},
        "lajpat nagar": {"1BHK": (15000, 24000), "2BHK": (25000, 40000), "3BHK": (40000, 65000)},
    },
    "gurgaon": {
        "_default": {"1BHK": (14000, 24000), "2BHK": (25000, 45000), "3BHK": (40000, 80000)},
    },
    "mumbai": {
        "_default": {"1BHK": (25000, 45000), "2BHK": (45000, 85000), "3BHK": (80000, 160000)},
        "andheri": {"1BHK": (28000, 45000), "2BHK": (45000, 80000), "3BHK": (80000, 140000)},
        "powai": {"1BHK": (30000, 48000), "2BHK": (50000, 85000), "3BHK": (85000, 150000)},
        "thane": {"1BHK": (16000, 26000), "2BHK": (26000, 42000), "3BHK": (40000, 65000)},
    },
    "hyderabad": {
        "_default": {"1BHK": (11000, 18000), "2BHK": (18000, 30000), "3BHK": (28000, 50000)},
        "gachibowli": {"1BHK": (14000, 22000), "2BHK": (22000, 36000), "3BHK": (35000, 60000)},
        "madhapur": {"1BHK": (14000, 22000), "2BHK": (22000, 36000), "3BHK": (35000, 58000)},
    },
    "chennai": {
        "_default": {"1BHK": (11000, 18000), "2BHK": (18000, 30000), "3BHK": (28000, 50000)},
        "omr": {"1BHK": (12000, 19000), "2BHK": (18000, 30000), "3BHK": (28000, 48000)},
    },
    "pune": {
        "_default": {"1BHK": (12000, 19000), "2BHK": (19000, 32000), "3BHK": (30000, 52000)},
        "hinjewadi": {"1BHK": (12000, 18000), "2BHK": (18000, 28000), "3BHK": (26000, 42000)},
    },
}

# Customary security deposit norms in months of rent
DEPOSIT_NORMS: Dict[str, tuple] = {
    "bangalore": (5, 10), "delhi": (2, 3), "gurgaon": (2, 3), "mumbai": (3, 6),
    "hyderabad": (2, 4), "chennai": (5, 10), "pune": (3, 6),
}

CITY_ALIASES = {"bengaluru": "bangalore", "new delhi": "delhi", "gurugram": "gurgaon", "bombay": "mumbai", "madras": "chennai"}


def _norm_city(city: str) -> str:
    c = (city or "").strip().lower()
    return CITY_ALIASES.get(c, c)


def _find_locality(city_data: Dict[str, Any], locality: str) -> tuple[str, Dict[str, tuple]]:
    loc = (locality or "").strip().lower()
    if loc:
        for key, band in city_data.items():
            if key != "_default" and (key in loc or loc in key):
                return key.title(), band
    return "City average", city_data["_default"]


def benchmark(city: str, locality: str = "", bhk: str = "2BHK", monthly_rent: Optional[float] = None,
              security_deposit: Optional[float] = None) -> Dict[str, Any]:
    """Return a fair-rent band and deposit norm with a plain-language verdict."""
    city_key = _norm_city(city)
    bhk = (bhk or "2BHK").upper().replace(" ", "")
    if bhk not in ("1BHK", "2BHK", "3BHK"):
        bhk = "2BHK"
    if city_key not in MICRO_MARKET:
        return {"supported": False, "city": city, "message": f"No benchmark data for {city or 'this city'} yet. "
                "GoLegal OS currently covers Bangalore, Delhi, Gurgaon, Mumbai, Hyderabad, Chennai and Pune."}

    locality_name, band = _find_locality(MICRO_MARKET[city_key], locality)
    low, high = band[bhk]
    dep_low, dep_high = DEPOSIT_NORMS.get(city_key, (2, 6))
    result: Dict[str, Any] = {
        "supported": True,
        "city": city_key.title(),
        "locality": locality_name,
        "bhk": bhk,
        "fair_rent_low": low,
        "fair_rent_high": high,
        "fair_rent_mid": (low + high) // 2,
        "deposit_norm_months": [dep_low, dep_high],
        "insights": [],
    }
    if monthly_rent:
        if monthly_rent < low:
            result["rent_position"] = "below_market"
            result["insights"].append(f"₹{monthly_rent:,.0f} is below the typical {bhk} band for {locality_name} "
                                      f"(₹{low:,}–₹{high:,}). Good deal for the tenant; owners often compensate with a higher deposit.")
        elif monthly_rent > high:
            over = (monthly_rent - high) / high * 100
            result["rent_position"] = "above_market"
            result["insights"].append(f"₹{monthly_rent:,.0f} is about {over:.0f}% above the typical {bhk} band for {locality_name} "
                                      f"(₹{low:,}–₹{high:,}). Tenants may negotiate towards ₹{(low + high) // 2:,}.")
        else:
            result["rent_position"] = "fair"
            result["insights"].append(f"₹{monthly_rent:,.0f} sits within the fair band for a {bhk} in {locality_name} (₹{low:,}–₹{high:,}).")
        if security_deposit is not None and monthly_rent > 0:
            months = security_deposit / monthly_rent
            result["deposit_months"] = round(months, 1)
            if months > dep_high:
                result["deposit_position"] = "high"
                result["insights"].append(f"A deposit of {months:.1f} months is above the {city_key.title()} norm of "
                                          f"{dep_low}–{dep_high} months. Consider negotiating it down or adding a clear refund timeline.")
            elif months < dep_low:
                result["deposit_position"] = "low"
                result["insights"].append(f"A deposit of {months:.1f} months is below the local norm of {dep_low}–{dep_high} months; "
                                          f"owners may want stronger damage clauses.")
            else:
                result["deposit_position"] = "normal"
                result["insights"].append(f"A deposit of {months:.1f} months is customary for {city_key.title()}.")
    return result


def supported_cities() -> list[str]:
    return [c.title() for c in MICRO_MARKET]
