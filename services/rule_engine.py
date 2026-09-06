"""
GoLegal Statutory Rule Engine
Calculates statutory stamp duty fees and compiles compliant legal clauses across Indian jurisdictions.
"""
from typing import Dict, List, Any

# Statutory stamp duty fees in INR
STATE_STAMP_RULES = {
    "KA": {"name": "Karnataka", "flat_duty": 100.0, "vendor": "StockHolding"},
    "DL": {"name": "Delhi", "flat_duty": 100.0, "vendor": "StockHolding"},
    "MH": {"name": "Maharashtra", "flat_duty": 500.0, "pct_rate": 0.0025, "vendor": "StockHolding"},
    "TN": {"name": "Tamil Nadu", "flat_duty": 100.0, "vendor": "StockHolding"},
    "TS": {"name": "Telangana", "flat_duty": 100.0, "vendor": "StockHolding"},
}

MANDATORY_STATUTORY_CLAUSES = [
    {
        "id": "CLAUSE_01_TENANCY",
        "title": "Tenancy Grant & Demised Premises",
        "text": "The Lessor hereby grants and the Lessee takes on lease the demised premises for residential dwelling purposes only for the agreed term.",
        "derogable": False
    },
    {
        "id": "CLAUSE_02_RENT",
        "title": "Monthly Rent & Utility Charges",
        "text": "The Lessee shall pay the agreed monthly rent on or before the due date specified. Electricity and water consumption shall be paid directly by the Lessee.",
        "derogable": False
    },
    {
        "id": "CLAUSE_03_TERMINATION",
        "title": "Notice Period & Termination",
        "text": "Either party may terminate this agreement by providing the agreed written notice period. Unexpired lock-in conditions shall apply as stipulated.",
        "derogable": False
    },
    {
        "id": "CLAUSE_04_JURISDICTION",
        "title": "Governing Law & Dispute Resolution",
        "text": "This agreement shall be governed strictly by the laws of India and the exclusive jurisdiction of the competent civil courts of the State where the property is located.",
        "derogable": False
    }
]


def calculate_stamp_duty(state_code: str, monthly_rent: float, deposit: float, months: int = 11) -> Dict[str, Any]:
    """
    Calculate statutory state stamp duty based on state article rules.
    """
    code = state_code.upper()
    if code not in STATE_STAMP_RULES:
        # Default fallback
        duty = 100.0
        state_name = "Other"
    else:
        rule = STATE_STAMP_RULES[code]
        state_name = rule["name"]
        if code == "MH":
            # Maharashtra Leave & License consideration formula
            total_rent = monthly_rent * months
            interest_on_deposit = deposit * 0.10 * (months / 12.0)
            total_consideration = total_rent + interest_on_deposit
            computed = total_consideration * rule["pct_rate"]
            duty = max(float(rule["flat_duty"]), round(computed, 2))
        else:
            duty = float(rule["flat_duty"])

    return {
        "state_code": code,
        "state_name": state_name,
        "stamp_duty_amount": duty,
        "platform_fee": 299.0,
        "gst_amount": round((299.0 + duty) * 0.18, 2),
        "total_payable": round(duty + 299.0 + ((299.0 + duty) * 0.18), 2)
    }


def get_default_clauses(custom_toggles: Dict[str, bool] = None) -> List[Dict[str, Any]]:
    """Return mandatory clauses along with optional toggled clauses."""
    toggles = custom_toggles or {}
    clauses = list(MANDATORY_STATUTORY_CLAUSES)

    if toggles.get("pets_allowed", False):
        clauses.append({
            "id": "CLAUSE_OPT_PETS",
            "title": "Pet Policy",
            "text": "Domestic pets are permitted within the premises provided they do not cause nuisance to neighbors or damage premises fixtures.",
            "derogable": True
        })
    else:
        clauses.append({
            "id": "CLAUSE_OPT_PETS",
            "title": "Pet Policy",
            "text": "No domestic pets or animals shall be kept on the premises without prior explicit written permission from the Lessor.",
            "derogable": True
        })

    if toggles.get("painting_deduction", True):
        clauses.append({
            "id": "CLAUSE_OPT_PAINTING",
            "title": "Painting & Maintenance Liabilities",
            "text": "A standard one month rent or fixed painting deduction will be adjusted from the security deposit upon vacating the premises.",
            "derogable": True
        })

    return clauses
