"""
Tests for Statutory Rule Engine (TC-RULE)
"""
from services.rule_engine import calculate_stamp_duty, get_default_clauses


class TestStatutoryRuleEngine:
    # -------------------------------------------------------------
    # State Stamp Duty Computation Tests (TC-RULE-01, 02, 03)
    # -------------------------------------------------------------
    def test_karnataka_flat_duty(self):
        res = calculate_stamp_duty(state_code="KA", monthly_rent=25000, deposit=100000, months=11)
        assert res["state_code"] == "KA"
        assert res["state_name"] == "Karnataka"
        assert res["stamp_duty_amount"] == 100.0
        assert res["platform_fee"] == 299.0
        assert res["total_payable"] > res["stamp_duty_amount"]

    def test_delhi_flat_duty(self):
        res = calculate_stamp_duty(state_code="DL", monthly_rent=35000, deposit=70000, months=11)
        assert res["state_code"] == "DL"
        assert res["stamp_duty_amount"] == 100.0

    def test_maharashtra_duty_computation(self):
        # Rent: 40,000 * 11 = 440,000; Deposit interest: 200,000 * 0.10 * (11/12) = 18,333.33
        # Total consideration = 458,333.33 * 0.0025 = 1,145.83 -> duty should be approx 1145.83
        res = calculate_stamp_duty(state_code="MH", monthly_rent=40000, deposit=200000, months=11)
        assert res["state_code"] == "MH"
        assert res["stamp_duty_amount"] > 500.0
        assert round(res["stamp_duty_amount"], 2) == 1145.83

    def test_maharashtra_minimum_duty(self):
        # Low rent where 0.25% < 500 -> should enforce 500 flat minimum
        res = calculate_stamp_duty(state_code="MH", monthly_rent=5000, deposit=10000, months=11)
        assert res["stamp_duty_amount"] == 500.0

    def test_unregistered_state_fallback(self):
        res = calculate_stamp_duty(state_code="XX", monthly_rent=20000, deposit=50000)
        assert res["stamp_duty_amount"] == 100.0

    # -------------------------------------------------------------
    # Non-Derogable Statutory Clauses Tests (TC-RULE-04)
    # -------------------------------------------------------------
    def test_mandatory_clauses_are_non_derogable(self):
        clauses = get_default_clauses()
        mandatory = [c for c in clauses if not c["derogable"]]
        assert len(mandatory) == 4
        # Verify specific required protections
        clause_ids = [c["id"] for c in mandatory]
        assert "CLAUSE_01_TENANCY" in clause_ids
        assert "CLAUSE_02_RENT" in clause_ids
        assert "CLAUSE_03_TERMINATION" in clause_ids
        assert "CLAUSE_04_JURISDICTION" in clause_ids

    def test_custom_clause_toggles(self):
        # Pets allowed toggle
        clauses_with_pets = get_default_clauses(custom_toggles={"pets_allowed": True})
        pet_clause = next(c for c in clauses_with_pets if c["id"] == "CLAUSE_OPT_PETS")
        assert "Domestic pets are permitted" in pet_clause["text"]

        clauses_no_pets = get_default_clauses(custom_toggles={"pets_allowed": False})
        no_pet_clause = next(c for c in clauses_no_pets if c["id"] == "CLAUSE_OPT_PETS")
        assert "No domestic pets" in no_pet_clause["text"]
