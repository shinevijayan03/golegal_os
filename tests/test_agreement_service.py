"""
Tests for the Agreement application service: drafts, party sync, ownership scoping, soft delete (TC-AGR)
"""
import pytest

from domain.models import Party, User
from services.agreement_service import AgreementAccessError, demo_payload, empty_payload
from services.validation import validate_wizard_payload


class TestAgreementService:
    def test_save_draft_creates_parties_for_multi_party(self, agreement_svc, sample_users, db_session):
        payload = demo_payload()
        payload["owners"].append({"name": "Lakshmi Reddy", "phone": "9876543219", "email": "lakshmi@example.com", "pan": "LMNOP1234Q", "aadhaar": "555566667777"})
        payload["tenants"].append({"name": "Anushka Verma", "phone": "9876543215", "email": "anushka@example.com", "aadhaar": "222233334444"})
        payload["witnesses"].append({"name": "Priya Nair", "phone": "9876543218", "email": "priya@example.com", "aadhaar": "999988887777"})
        agr = agreement_svc.save_draft(sample_users["owner"], payload)
        parties = db_session.query(Party).filter_by(agreement_id=agr.id).all()
        assert len(parties) == 6
        assert sum(1 for p in parties if p.party_type == "Owner") == 2
        assert sum(1 for p in parties if p.party_type == "Tenant") == 2
        assert sum(1 for p in parties if p.party_type == "Witness") == 2
        # Aadhaar is never stored raw
        assert all(p.aadhaar_masked.startswith("XXXXXXXX") for p in parties)
        assert not any("123456789012" in (p.aadhaar_masked or "") for p in parties)
        assert agr.status == "Draft"
        assert agr.title == "Sunrise Apartments #402 - Rental Agreement"

    def test_save_draft_updates_existing_and_resyncs(self, agreement_svc, sample_users, db_session):
        payload = demo_payload()
        agr = agreement_svc.save_draft(sample_users["owner"], payload)
        payload["witnesses"] = []
        payload["commercials"]["monthly_rent"] = 30000
        agr2 = agreement_svc.save_draft(sample_users["owner"], payload, agreement_id=agr.id)
        assert agr2.id == agr.id
        assert agr2.get_commercial_terms()["monthly_rent"] == 30000
        assert len(agr2.parties) == 2

    def test_only_initiator_can_edit_and_only_drafts(self, agreement_svc, sample_users):
        agr = agreement_svc.save_draft(sample_users["owner"], demo_payload())
        with pytest.raises(AgreementAccessError):
            agreement_svc.save_draft(sample_users["tenant"], demo_payload(), agreement_id=agr.id)
        agr.status = "Paid"
        with pytest.raises(AgreementAccessError):
            agreement_svc.save_draft(sample_users["owner"], demo_payload(), agreement_id=agr.id)

    def test_load_payload_roundtrip_masks_aadhaar(self, agreement_svc, sample_users):
        agr = agreement_svc.save_draft(sample_users["owner"], demo_payload())
        payload = agreement_svc.load_payload(agr)
        assert payload["owners"][0]["name"] == "Ramakiran Reddy"
        assert payload["owners"][0]["aadhaar"] == "XXXXXXXX9012"
        assert payload["commercials"]["monthly_rent"] == 28000
        assert validate_wizard_payload(payload) == []  # masked Aadhaar validates

    def test_listing_is_scoped_to_initiator_and_counterparties(self, agreement_svc, sample_users, db_session):
        agr = agreement_svc.save_draft(sample_users["owner"], demo_payload())
        stranger = User(id="usr-x", full_name="Stranger", email="stranger@example.com", phone="9000000000")
        witness_user = User(id="usr-w", full_name="Suresh Kumar", email="suresh@example.com", phone="9876543212")
        db_session.add_all([stranger, witness_user])
        db_session.commit()
        assert [a.id for a in agreement_svc.list_for_user(sample_users["owner"])] == [agr.id]
        assert [a.id for a in agreement_svc.list_for_user(sample_users["tenant"])] == [agr.id]  # named tenant
        assert agreement_svc.list_for_user(stranger) == []
        assert agreement_svc.list_for_user(witness_user) == []  # witness privacy
        assert agreement_svc.user_can_access(agr, sample_users["tenant"])
        assert not agreement_svc.user_can_access(agr, stranger)
        with pytest.raises(AgreementAccessError):
            agreement_svc.get_accessible(agr.id, stranger)

    def test_soft_delete_preserves_counterparty_access(self, agreement_svc, sample_users):
        agr = agreement_svc.save_draft(sample_users["owner"], demo_payload())
        with pytest.raises(AgreementAccessError):
            agreement_svc.archive(agr, sample_users["tenant"])
        agreement_svc.archive(agr, sample_users["owner"])
        assert agreement_svc.list_for_user(sample_users["owner"]) == []
        assert [a.id for a in agreement_svc.list_for_user(sample_users["tenant"])] == [agr.id]
        agreement_svc.restore(agr, sample_users["owner"])
        assert len(agreement_svc.list_for_user(sample_users["owner"])) == 1

    def test_validation_rejects_incomplete_payload(self):
        errors = validate_wizard_payload(empty_payload())
        assert any("Owner 1" in e for e in errors)
        assert any("PIN" in e for e in errors)
        bad = demo_payload()
        bad["commercials"]["lock_in_months"] = 12
        bad["witnesses"] = [{"name": f"W{i}", "phone": "9876543212", "email": "w@example.com"} for i in range(3)]
        errors = validate_wizard_payload(bad)
        assert any("Lock-in" in e for e in errors)
        assert any("two witnesses" in e for e in errors)
