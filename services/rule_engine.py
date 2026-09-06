"""
GoLegal Statutory Rule Engine
Calculates statutory stamp duty fees and compiles compliant legal clauses across Indian jurisdictions.
All pricing is computed server-side from configuration (OWASP category 20 - hidden field tamper).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from config import settings

# Statutory stamp duty rules in INR. flat_duty is the minimum; pct_rate (where present)
# is applied to the consideration (total rent + notional interest on deposit).
STATE_STAMP_RULES: Dict[str, Dict[str, Any]] = {
    "KA": {"name": "Karnataka", "flat_duty": 100.0, "vendor": "StockHolding", "article": "Article 30 - Lease of immovable property"},
    "DL": {"name": "Delhi", "flat_duty": 100.0, "vendor": "StockHolding", "article": "Article 35 - Lease"},
    "MH": {"name": "Maharashtra", "flat_duty": 500.0, "pct_rate": 0.0025, "vendor": "StockHolding", "article": "Article 36A - Leave & Licence"},
    "TN": {"name": "Tamil Nadu", "flat_duty": 100.0, "vendor": "StockHolding", "article": "Article 35 - Lease"},
    "TS": {"name": "Telangana", "flat_duty": 100.0, "vendor": "StockHolding", "article": "Article 31 - Lease"},
    "GJ": {"name": "Gujarat", "flat_duty": 100.0, "vendor": "StockHolding", "article": "Article 30 - Lease"},
    "WB": {"name": "West Bengal", "flat_duty": 100.0, "vendor": "StockHolding", "article": "Article 33 - Lease"},
    "HR": {"name": "Haryana", "flat_duty": 100.0, "vendor": "StockHolding", "article": "Article 35 - Lease"},
    "UP": {"name": "Uttar Pradesh", "flat_duty": 100.0, "vendor": "StockHolding", "article": "Article 35 - Lease"},
}

AGREEMENT_TYPE_LABELS = {
    "Rental_Residential": "Residential rental (11 months)",
    "Rental_Commercial": "Commercial lease",
    "Lease": "Long-term lease",
    "NDA": "Non-disclosure agreement",
    "Custom": "Custom contract",
}

MANDATORY_STATUTORY_CLAUSES: List[Dict[str, Any]] = [
    {
        "id": "CLAUSE_01_TENANCY",
        "title": "Tenancy Grant & Demised Premises",
        "text": "The Lessor hereby grants and the Lessee takes on lease the demised premises for residential dwelling purposes only for the agreed term.",
        "derogable": False,
    },
    {
        "id": "CLAUSE_02_RENT",
        "title": "Monthly Rent & Utility Charges",
        "text": "The Lessee shall pay the agreed monthly rent on or before the due date specified. Electricity and water consumption shall be paid directly by the Lessee.",
        "derogable": False,
    },
    {
        "id": "CLAUSE_03_TERMINATION",
        "title": "Notice Period & Termination",
        "text": "Either party may terminate this agreement by providing the agreed written notice period. Unexpired lock-in conditions shall apply as stipulated.",
        "derogable": False,
    },
    {
        "id": "CLAUSE_04_JURISDICTION",
        "title": "Governing Law & Dispute Resolution",
        "text": "This agreement shall be governed strictly by the laws of India and the exclusive jurisdiction of the competent civil courts of the State where the property is located.",
        "derogable": False,
    },
]

STANDARD_COVENANTS: List[Dict[str, Any]] = [
    {
        "id": "CLAUSE_05_DEPOSIT",
        "title": "Security Deposit & Refund",
        "text": "The Lessee has paid an interest-free refundable security deposit which the Lessor shall refund within thirty (30) days of vacant possession, less lawful deductions for unpaid dues or damage beyond normal wear and tear.",
        "derogable": True,
    },
    {
        "id": "CLAUSE_06_MAINTENANCE",
        "title": "Maintenance, Fixtures & Repairs",
        "text": "The Lessee shall maintain the premises and fixtures in good and tenantable condition. Structural repairs remain the responsibility of the Lessor; day-to-day upkeep is the Lessee's responsibility.",
        "derogable": True,
    },
    {
        "id": "CLAUSE_07_ESCALATION",
        "title": "Renewal & Rent Escalation",
        "text": "On expiry, the agreement may be renewed on mutually agreed terms with rent escalated by the agreed annual escalation percentage.",
        "derogable": True,
    },
    {
        "id": "CLAUSE_08_HANDOVER",
        "title": "Peaceful Enjoyment & Handover",
        "text": "The Lessor shall not interfere with the Lessee's peaceful enjoyment of the premises and shall give at least 24 hours' notice before any inspection. On termination the Lessee shall hand over vacant possession with all keys.",
        "derogable": True,
    },
]

OPTIONAL_TOGGLES: Dict[str, Dict[str, Any]] = {
    "pets_allowed": {
        "label": "Pets allowed on premises",
        "default": False,
        "on": {"id": "CLAUSE_OPT_PETS", "title": "Pet Policy",
               "text": "Domestic pets are permitted within the premises provided they do not cause nuisance to neighbors or damage premises fixtures."},
        "off": {"id": "CLAUSE_OPT_PETS", "title": "Pet Policy",
                "text": "No domestic pets or animals shall be kept on the premises without prior explicit written permission from the Lessor."},
    },
    "painting_deduction": {
        "label": "Standard painting deduction on vacating",
        "default": True,
        "on": {"id": "CLAUSE_OPT_PAINTING", "title": "Painting & Maintenance Liabilities",
               "text": "A standard one month rent or fixed painting deduction will be adjusted from the security deposit upon vacating the premises."},
        "off": None,
    },
    "subletting_allowed": {
        "label": "Subletting permitted",
        "default": False,
        "on": {"id": "CLAUSE_OPT_SUBLET", "title": "Subletting",
               "text": "The Lessee may sublet a portion of the premises with prior written consent of the Lessor, which shall not be unreasonably withheld."},
        "off": {"id": "CLAUSE_OPT_SUBLET", "title": "Prohibition on Subletting",
                "text": "The Lessee shall not sublet, assign or part with possession of the premises or any part thereof."},
    },
    "parking_included": {
        "label": "Dedicated parking included",
        "default": True,
        "on": {"id": "CLAUSE_OPT_PARKING", "title": "Parking",
               "text": "One dedicated parking slot is included in the rent for the Lessee's vehicle. Guest parking is subject to society rules."},
        "off": None,
    },
}

NDA_CLAUSES: List[Dict[str, Any]] = [
    {"id": "NDA_01", "title": "Definition of Confidential Information", "derogable": False,
     "text": "Confidential Information means all non-public business, technical and financial information disclosed by either party, whether orally, in writing or electronically."},
    {"id": "NDA_02", "title": "Obligations of the Receiving Party", "derogable": False,
     "text": "The Receiving Party shall hold Confidential Information in strict confidence, use it solely for the Purpose, and protect it with at least the same degree of care it uses for its own confidential information."},
    {"id": "NDA_03", "title": "Term & Survival", "derogable": True,
     "text": "These obligations survive for three (3) years from the date of disclosure, or indefinitely for trade secrets."},
    {"id": "NDA_04", "title": "Governing Law", "derogable": False,
     "text": "This agreement is governed by the laws of India. Disputes are subject to the exclusive jurisdiction of the courts at Bangalore."},
]


def compute_fees(stamp_duty: float, discount_pct: float = 0.0) -> Dict[str, float]:
    """Platform fee + GST on top of statutory duty. Duty itself is not taxable."""
    fee = round(settings.platform_fee * (1 - discount_pct / 100.0), 2)
    gst = round(fee * settings.gst_rate, 2)
    return {
        "platform_fee": fee,
        "gst_amount": gst,
        "total_payable": round(stamp_duty + fee + gst, 2),
    }


def calculate_stamp_duty(state_code: str, monthly_rent: float, deposit: float, months: int = 11,
                         discount_pct: float = 0.0) -> Dict[str, Any]:
    """
    Calculate statutory state stamp duty based on state article rules and the
    server-side platform fee + GST.
    """
    code = (state_code or "KA").upper()
    monthly_rent = float(monthly_rent or 0)
    deposit = float(deposit or 0)
    months = int(months or 11)
    if code not in STATE_STAMP_RULES:
        duty = 100.0
        state_name = "Other"
        article = "Lease of immovable property"
    else:
        rule = STATE_STAMP_RULES[code]
        state_name = rule["name"]
        article = rule.get("article", "Lease")
        if rule.get("pct_rate"):
            total_rent = monthly_rent * months
            interest_on_deposit = deposit * 0.10 * (months / 12.0)
            total_consideration = total_rent + interest_on_deposit
            computed = total_consideration * rule["pct_rate"]
            duty = max(float(rule["flat_duty"]), round(computed, 2))
        else:
            duty = float(rule["flat_duty"])

    fees = compute_fees(duty, discount_pct)
    return {
        "state_code": code,
        "state_name": state_name,
        "article": article,
        "stamp_duty_amount": duty,
        "platform_fee": fees["platform_fee"],
        "gst_amount": fees["gst_amount"],
        "total_payable": fees["total_payable"],
        "consideration": round(monthly_rent * months, 2),
    }


def get_default_clauses(custom_toggles: Optional[Dict[str, bool]] = None,
                        agreement_type: str = "Rental_Residential") -> List[Dict[str, Any]]:
    """Return mandatory clauses along with standard covenants and toggled optional clauses."""
    if agreement_type == "NDA":
        return [dict(c) for c in NDA_CLAUSES]

    toggles = dict(custom_toggles or {})
    clauses: List[Dict[str, Any]] = [dict(c) for c in MANDATORY_STATUTORY_CLAUSES]
    if agreement_type == "Rental_Commercial":
        clauses[0] = dict(clauses[0], text=clauses[0]["text"].replace("residential dwelling purposes only", "lawful commercial purposes only"))
    clauses += [dict(c) for c in STANDARD_COVENANTS]

    for key, spec in OPTIONAL_TOGGLES.items():
        enabled = toggles.get(key, spec["default"])
        variant = spec["on"] if enabled else spec["off"]
        if variant:
            clauses.append(dict(variant, derogable=True))
    return clauses


def default_toggles() -> Dict[str, bool]:
    return {k: v["default"] for k, v in OPTIONAL_TOGGLES.items()}


def render_clauses_text(clauses: List[Dict[str, Any]], custom_text: str = "") -> str:
    """Plain-text rendering used by the AI layer and previews."""
    lines = [f"{i}. {c['title']}: {c['text']}" for i, c in enumerate(clauses, 1)]
    if custom_text and custom_text.strip():
        lines.append(f"{len(clauses) + 1}. Additional Covenants: {custom_text.strip()}")
    return "\n".join(lines)
