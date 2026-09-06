"""
GoLegal Agreement Application Service
Bridges the wizard/AI payload and the relational model. Owns draft creation,
metadata updates, party synchronisation, ownership-scoped listing, and soft delete.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from domain.models import Agreement, Party, User, utc_now
from services.rule_engine import calculate_stamp_duty, default_toggles
from services.validation import safe_mask_aadhaar, validate_wizard_payload


class AgreementAccessError(Exception):
    pass


def empty_payload(state_code: str = "KA", agreement_type: str = "Rental_Residential") -> Dict[str, Any]:
    """Canonical wizard payload shape."""
    return {
        "agreement_type": agreement_type,
        "state_code": state_code,
        "title": "",
        "owners": [{"name": "", "phone": "", "email": "", "pan": "", "aadhaar": "", "address": ""}],
        "tenants": [{"name": "", "phone": "", "email": "", "pan": "", "aadhaar": "", "address": ""}],
        "witnesses": [],
        "property": {"premises_name": "", "address": "", "city": "", "pincode": "", "property_type": "Apartment", "inclusions": ""},
        "commercials": {"monthly_rent": 25000, "security_deposit": 100000, "lease_months": 11, "lock_in_months": 6,
                        "notice_days": 30, "rent_due_day": 5, "escalation_pct": 5, "lease_start": ""},
        "clause_toggles": default_toggles(),
        "custom_clauses": "",
        "cloud_storage_consent": True,
    }


def demo_payload() -> Dict[str, Any]:
    """Pre-filled persona data from the PRD for quick demos."""
    p = empty_payload()
    p.update({
        "title": "Sunrise Apartments #402 - Rental Agreement",
        "owners": [{"name": "Ramakiran Reddy", "phone": "9876543210", "email": "ramakiran.reddy@example.com",
                    "pan": "ABCDE1234F", "aadhaar": "123456789012", "address": "101, Palm Meadows, Mahadevapura, Bangalore"}],
        "tenants": [{"name": "Mayank Tripathi", "phone": "9876543211", "email": "mayank.tripathi@example.com",
                     "pan": "XYZAB5678C", "aadhaar": "987654321098", "address": "Prayagraj, Uttar Pradesh"}],
        "witnesses": [{"name": "Suresh Kumar", "phone": "9876543212", "email": "suresh@example.com", "aadhaar": "111122223333"}],
        "property": {"premises_name": "Sunrise Apartments, Flat 402", "address": "Outer Ring Road, Bellandur", "city": "Bangalore",
                     "pincode": "560103", "property_type": "Apartment", "inclusions": "2 fans, 3 lights, geyser, 1 covered parking, 2 sets of keys"},
        "commercials": {"monthly_rent": 28000, "security_deposit": 120000, "lease_months": 11, "lock_in_months": 6,
                        "notice_days": 30, "rent_due_day": 5, "escalation_pct": 5, "lease_start": "2026-10-01"},
    })
    return p


class AgreementService:
    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------ create / update
    def save_draft(self, user: User, payload: Dict[str, Any], agreement_id: Optional[str] = None,
                   validate: bool = False) -> Agreement:
        """Create or update a Draft agreement (and its parties) from a wizard payload."""
        if validate:
            errors = validate_wizard_payload(payload)
            if errors:
                raise ValueError("; ".join(errors))

        agreement = None
        if agreement_id:
            agreement = self.session.query(Agreement).filter_by(id=agreement_id).first()
            if agreement and agreement.initiator_id != user.id:
                raise AgreementAccessError("You can only edit agreements you initiated.")
            if agreement and agreement.status != "Draft":
                raise AgreementAccessError("Only drafts can be edited. This agreement is already paid or executed.")
        if not agreement:
            agreement = Agreement(id=agreement_id, initiator_id=user.id)
            self.session.add(agreement)

        agreement.agreement_type = payload.get("agreement_type", "Rental_Residential")
        agreement.state_code = payload.get("state_code", "KA")
        agreement.title = (payload.get("title") or "").strip() or None
        agreement.set_property_details(payload.get("property", {}))
        agreement.set_commercial_terms(payload.get("commercials", {}))
        agreement.set_clause_toggles(payload.get("clause_toggles", {}))
        agreement.custom_clauses = (payload.get("custom_clauses") or "").strip() or None
        agreement.cloud_storage_consent = bool(payload.get("cloud_storage_consent", True))
        agreement.updated_at = utc_now()
        self.session.flush()

        # Re-sync parties (drafts only; identity is re-established from payload each save)
        for party in list(agreement.parties):
            self.session.delete(party)
        self.session.flush()
        for role, key in (("Owner", "owners"), ("Tenant", "tenants"), ("Witness", "witnesses")):
            for entry in payload.get(key, []) or []:
                if not (entry.get("name") or "").strip():
                    continue
                self.session.add(Party(
                    agreement_id=agreement.id,
                    party_type=role,
                    full_name=entry["name"].strip(),
                    email=(entry.get("email") or "").strip().lower(),
                    phone=re.sub(r"\D", "", entry.get("phone") or "")[-10:],
                    pan=(entry.get("pan") or "").strip().upper() or None,
                    address=(entry.get("address") or "").strip() or None,
                    aadhaar_masked=safe_mask_aadhaar(entry.get("aadhaar", "")) if entry.get("aadhaar") else None,
                ))
        self.session.commit()
        self.session.refresh(agreement)
        return agreement

    def load_payload(self, agreement: Agreement) -> Dict[str, Any]:
        """Inverse of save_draft (Aadhaar comes back masked - raw digits are never stored)."""
        payload = empty_payload(agreement.state_code, agreement.agreement_type)
        payload["title"] = agreement.title or ""
        payload["property"].update(agreement.get_property_details())
        payload["commercials"].update(agreement.get_commercial_terms())
        payload["clause_toggles"].update(agreement.get_clause_toggles())
        payload["custom_clauses"] = agreement.custom_clauses or ""
        payload["cloud_storage_consent"] = agreement.cloud_storage_consent
        groups = {"Owner": [], "Tenant": [], "Witness": []}
        for p in agreement.parties:
            groups[p.party_type].append({"name": p.full_name, "phone": p.phone, "email": p.email,
                                         "pan": p.pan or "", "aadhaar": p.aadhaar_masked or "", "address": p.address or ""})
        payload["owners"] = groups["Owner"] or payload["owners"]
        payload["tenants"] = groups["Tenant"] or payload["tenants"]
        payload["witnesses"] = groups["Witness"]
        return payload

    # ------------------------------------------------------------------ access
    def get(self, agreement_id: str) -> Optional[Agreement]:
        return self.session.query(Agreement).filter_by(id=agreement_id).first()

    def user_can_access(self, agreement: Agreement, user: Optional[User]) -> bool:
        if not user:
            return False
        if user.is_admin or agreement.initiator_id == user.id:
            return True
        email = (user.email or "").lower()
        return any((p.email or "").lower() == email or p.phone == user.phone for p in agreement.parties
                   if p.party_type != "Witness")

    def get_accessible(self, agreement_id: str, user: User) -> Agreement:
        agreement = self.get(agreement_id)
        if not agreement or not self.user_can_access(agreement, user):
            raise AgreementAccessError("Agreement not found or you are not a party to it.")
        return agreement

    def list_for_user(self, user: User, include_archived: bool = False) -> List[Agreement]:
        """Agreements the user initiated or is a named Owner/Tenant on. Witnesses never see the archive."""
        email = (user.email or "").lower()
        q = self.session.query(Agreement).outerjoin(Party).filter(
            or_(Agreement.initiator_id == user.id,
                (Party.email == email) & (Party.party_type != "Witness"),
                (Party.phone == user.phone) & (Party.party_type != "Witness"))
        ).distinct()
        rows = q.order_by(Agreement.created_at.desc()).all()
        if include_archived:
            return rows
        return [a for a in rows if not (a.is_archived and a.initiator_id == user.id)]

    def archive(self, agreement: Agreement, user: User) -> None:
        """Soft delete for the initiator's workspace; counterparties keep access."""
        if agreement.initiator_id != user.id and not user.is_admin:
            raise AgreementAccessError("Only the initiator can archive this agreement.")
        agreement.is_archived = True
        self.session.commit()

    def restore(self, agreement: Agreement, user: User) -> None:
        if agreement.initiator_id != user.id and not user.is_admin:
            raise AgreementAccessError("Only the initiator can restore this agreement.")
        agreement.is_archived = False
        self.session.commit()

    def rename(self, agreement: Agreement, user: User, title: str) -> None:
        if agreement.initiator_id != user.id:
            raise AgreementAccessError("Only the initiator can rename this agreement.")
        agreement.title = title.strip()[:255] or None
        self.session.commit()

    # ------------------------------------------------------------------ helpers
    def quote(self, agreement: Agreement) -> Dict[str, Any]:
        terms = agreement.get_commercial_terms()
        return calculate_stamp_duty(agreement.state_code, terms.get("monthly_rent", 0), terms.get("security_deposit", 0),
                                    int(terms.get("lease_months", 11) or 11))

    def status_counts(self, user: User) -> Dict[str, int]:
        counts = {"Draft": 0, "Paid": 0, "Pending_Signatures": 0, "Completed": 0, "Cancelled": 0, "Expired": 0}
        for a in self.list_for_user(user):
            counts[a.status] = counts.get(a.status, 0) + 1
        return counts
