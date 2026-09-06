"""
GoLegal Form & Metadata Validation Service
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
PIN_REGEX = re.compile(r"^[1-9][0-9]{5}$")
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
PHONE_REGEX = re.compile(r"^(\+91[\-\s]?)?[6-9]\d{9}$")
AADHAAR_REGEX = re.compile(r"^\d{12}$")
MASKED_AADHAAR_REGEX = re.compile(r"^X{8}\d{4}$")


def validate_pan(pan: str) -> bool:
    """Validate 10-character Permanent Account Number (PAN) format."""
    if not pan or not isinstance(pan, str):
        return False
    return bool(PAN_REGEX.match(pan.strip().upper()))


def validate_pincode(pincode: str) -> bool:
    """Validate 6-digit Indian Postal PIN code (cannot start with 0)."""
    if not pincode or not isinstance(pincode, str):
        return False
    return bool(PIN_REGEX.match(pincode.strip()))


def validate_email(email: str) -> bool:
    """Validate RFC-compliant email address."""
    if not email or not isinstance(email, str):
        return False
    return bool(EMAIL_REGEX.match(email.strip()))


def validate_phone(phone: str) -> bool:
    """Validate 10-digit Indian mobile number."""
    if not phone or not isinstance(phone, str):
        return False
    clean = re.sub(r"[\s\-]", "", phone)
    return bool(PHONE_REGEX.match(clean))


def validate_aadhaar(aadhaar: str) -> bool:
    """Non-raising check that a raw Aadhaar is 12 digits (or already masked)."""
    if not aadhaar or not isinstance(aadhaar, str):
        return False
    clean = re.sub(r"[\s\-]", "", aadhaar)
    return bool(AADHAAR_REGEX.match(clean) or MASKED_AADHAAR_REGEX.match(clean))


def mask_aadhaar(aadhaar: str) -> str:
    """
    Strict Aadhaar masking: Ingests 12 digits, returns XXXXXXXX1234.
    Never stores or returns unmasked Aadhaar. Already-masked input is returned unchanged.
    """
    if not aadhaar or not isinstance(aadhaar, str):
        raise ValueError("Aadhaar must be a 12-digit string")
    clean = re.sub(r"[\s\-]", "", aadhaar)
    if MASKED_AADHAAR_REGEX.match(clean):
        return clean
    if not AADHAAR_REGEX.match(clean):
        raise ValueError("Invalid Aadhaar number: must be exactly 12 numeric digits")
    return f"XXXXXXXX{clean[-4:]}"


def safe_mask_aadhaar(aadhaar: str) -> str:
    """Mask when valid, otherwise return a placeholder. Never raises."""
    try:
        return mask_aadhaar(aadhaar)
    except ValueError:
        return "XXXXXXXX----"


def validate_commercial_terms(monthly_rent: float, deposit: float, lease_months: int) -> list[str]:
    """Validate commercial parameters for legal sanity."""
    errors = []
    if monthly_rent is None or monthly_rent < 500:
        errors.append("Monthly rent must be at least ₹500")
    if deposit is None or deposit < 0:
        errors.append("Security deposit cannot be negative")
    if lease_months is None or lease_months < 1 or lease_months > 60:
        errors.append("Lease period must be between 1 and 60 months")
    return errors


def validate_party(party: Dict[str, Any], label: str, require_pan: bool = False) -> List[str]:
    """Validate a single party dict {name, phone, email, pan?, aadhaar?}."""
    errors = []
    if not (party.get("name") or "").strip() or len(party["name"].strip()) < 2:
        errors.append(f"{label}: full legal name is required")
    if not validate_phone(party.get("phone", "")):
        errors.append(f"{label}: enter a valid 10-digit Indian mobile number")
    if not validate_email(party.get("email", "")):
        errors.append(f"{label}: enter a valid email address")
    if require_pan and not validate_pan(party.get("pan", "")):
        errors.append(f"{label}: PAN must look like ABCDE1234F")
    elif party.get("pan") and not validate_pan(party["pan"]):
        errors.append(f"{label}: PAN must look like ABCDE1234F")
    if party.get("aadhaar") and not validate_aadhaar(party["aadhaar"]):
        errors.append(f"{label}: Aadhaar must be exactly 12 digits")
    return errors


def validate_wizard_payload(data: Dict[str, Any]) -> List[str]:
    """Validate the full metadata payload captured by the wizard (owners, tenants, witnesses, property, terms)."""
    errors: List[str] = []
    owners = data.get("owners") or []
    tenants = data.get("tenants") or []
    witnesses = data.get("witnesses") or []
    if not owners:
        errors.append("At least one owner / lessor is required")
    if not tenants:
        errors.append("At least one tenant / lessee is required")
    if len(witnesses) > 2:
        errors.append("A maximum of two witnesses is permitted")
    for i, o in enumerate(owners, 1):
        errors += validate_party(o, f"Owner {i}", require_pan=True)
    for i, t in enumerate(tenants, 1):
        errors += validate_party(t, f"Tenant {i}")
    for i, w in enumerate(witnesses, 1):
        errors += validate_party(w, f"Witness {i}")

    prop = data.get("property") or {}
    if not (prop.get("address") or "").strip():
        errors.append("Property address is required")
    if not validate_pincode(str(prop.get("pincode", ""))):
        errors.append("Property PIN code must be 6 digits")

    comm = data.get("commercials") or {}
    errors += validate_commercial_terms(comm.get("monthly_rent"), comm.get("security_deposit"), comm.get("lease_months"))
    lock_in = comm.get("lock_in_months", 0) or 0
    if lock_in < 0 or (comm.get("lease_months") and lock_in > comm["lease_months"]):
        errors.append("Lock-in period cannot exceed the lease duration")
    notice = comm.get("notice_days", 30) or 0
    if notice < 0 or notice > 180:
        errors.append("Notice period must be between 0 and 180 days")
    return errors
