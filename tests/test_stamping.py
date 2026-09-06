"""
Tests for StockHolding (SHCIL) e-Stamping Service (TC-STAMP)
"""
import pytest
from services.stamping_service import StampingService, InsufficientStampingBalanceError
from domain.models import SysConfig, SysConfigJn, AuditLog


class TestStampingService:
    # -------------------------------------------------------------
    # Procurement & Prepaid Ledger Debit Tests (TC-STAMP-01)
    # -------------------------------------------------------------
    def test_successful_estamp_procurement(self, stamping_svc, sample_agreement, db_session):
        initial_balance = stamping_svc.get_prepaid_balance()
        assert initial_balance == 50000.0

        estamp = stamping_svc.procure_estamp(
            agreement_id=sample_agreement.id,
            state_code="KA",
            stamp_amount=100.0,
            purchased_by="Ramakiran Reddy"
        )

        assert estamp is not None
        assert estamp.certificate_number.startswith("IN-KA0100")
        assert estamp.stamp_amount == 100.0
        assert estamp.state_code == "KA"

        # Verify balance debited
        new_balance = stamping_svc.get_prepaid_balance()
        assert new_balance == 49900.0

        # Verify journal entry recorded
        jn = db_session.query(SysConfigJn).filter_by(operation="UPDATE").first()
        assert jn is not None
        assert "49900.0" in jn.new_value

        # Verify audit log entry
        audit = db_session.query(AuditLog).filter_by(agreement_id=sample_agreement.id).first()
        assert audit is not None
        assert audit.event_type == "ESTAMP_PROCURED"

    # -------------------------------------------------------------
    # Low-Balance Alert (< ₹10,000) (TC-STAMP-02)
    # -------------------------------------------------------------
    def test_low_balance_threshold_alert(self, stamping_svc, sample_agreement, db_session):
        # Manually lower balance to near threshold
        config = db_session.query(SysConfig).filter_by(id="GLOBAL_CONFIG").first()
        config.stockholding_prepaid_balance = 10050.0
        db_session.commit()

        assert stamping_svc.is_low_balance() is False

        # Procure e-Stamp for ₹100 -> balance becomes 9950.0 (< 10000)
        stamping_svc.procure_estamp(
            agreement_id=sample_agreement.id,
            state_code="KA",
            stamp_amount=100.0,
            purchased_by="Ramakiran Reddy"
        )

        assert stamping_svc.get_prepaid_balance() == 9950.0
        assert stamping_svc.is_low_balance() is True

    # -------------------------------------------------------------
    # Insufficient Balance Rejection (TC-STAMP-03)
    # -------------------------------------------------------------
    def test_insufficient_stamping_balance(self, stamping_svc, sample_agreement, db_session):
        # Lower balance below required duty
        config = db_session.query(SysConfig).filter_by(id="GLOBAL_CONFIG").first()
        config.stockholding_prepaid_balance = 50.0
        db_session.commit()

        with pytest.raises(InsufficientStampingBalanceError) as exc_info:
            stamping_svc.procure_estamp(
                agreement_id=sample_agreement.id,
                state_code="KA",
                stamp_amount=100.0,
                purchased_by="Ramakiran Reddy"
            )
        assert "insufficient" in str(exc_info.value).lower()

    # -------------------------------------------------------------
    # Balance Top-Up Functionality (TC-STAMP-04)
    # -------------------------------------------------------------
    def test_top_up_balance(self, stamping_svc, db_session):
        current = stamping_svc.get_prepaid_balance()
        new_bal = stamping_svc.top_up_balance(25000.0, admin_user="FINANCE_ADMIN")
        assert new_bal == current + 25000.0
        assert stamping_svc.get_prepaid_balance() == new_bal

        # Test invalid negative top up
        with pytest.raises(ValueError):
            stamping_svc.top_up_balance(-500.0)

    # -------------------------------------------------------------
    # Idempotent Stamping Test
    # -------------------------------------------------------------
    def test_idempotent_estamp_call(self, stamping_svc, sample_agreement):
        e1 = stamping_svc.procure_estamp(sample_agreement.id, "KA", 100.0, "Ramakiran")
        bal1 = stamping_svc.get_prepaid_balance()

        # Second call with same agreement_id returns existing record without double-debit
        e2 = stamping_svc.procure_estamp(sample_agreement.id, "KA", 100.0, "Ramakiran")
        bal2 = stamping_svc.get_prepaid_balance()

        assert e1.id == e2.id
        assert e1.certificate_number == e2.certificate_number
        assert bal1 == bal2
