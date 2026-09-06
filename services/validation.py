"""
GoLegal Form & Metadata Validation Service
"""
import re

PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
PIN_REGEX = re.compile(r"^[1-9][0-9]{5}$")
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
PHONE_REGEX = re.compile(r"^(\+91[\-\s]?)?[6-9]\d{9}$")
AADHAAR_REGEX = re.compile(r"^\d{12}$")


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


def mask_aadhaar(aadhaar: str) -> str:
    """
    Strict Aadhaar masking: Ingests 12 digits, returns XXXXXXXX1234.
    Never stores or returns unmasked Aadhaar.
    """
    if not aadhaar or not isinstance(aadhaar, str):
        raise ValueError("Aadhaar must be a 12-digit string")
    clean = re.sub(r"[\s\-]", "", aadhaar)
    if not AADHAAR_REGEX.match(clean):
        raise ValueError("Invalid Aadhaar number: must be exactly 12 numeric digits")
    return f"XXXXXXXX{clean[-4:]}"


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
