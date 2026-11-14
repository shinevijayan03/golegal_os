"""
AgentOS ContractGateway: Typed Integration Bridge to GoLegal Contracts.
Enforces AOS-08, AT-19, and PRD Section 2 integration decisions.
"""
from __future__ import annotations
import json
import hashlib
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class ContractRevisionDTO:
    id: str
    contract_id: str
    tenant_id: str
    revision_no: int
    title: str
    sha256: str
    field_values: Dict[str, Any]
    created_at: str


@dataclass
class PlaybookRuleDTO:
    rule_id: str
    category: str
    title: str
    criteria: str
    target_value: str
    standard_clause: str
    severity: str


class FixtureContractGateway:
    """
    Standard fixture gateway with synthetic tenants and contracts (PRD §2 & §12).
    Set by default via CONTRACT_GATEWAY_MODE=fixture.
    """
    def __init__(self, session: Optional[Any] = None):
        self.session = session
        # Seeded Playbook Rules (Playbook 2026-11)
        self.playbooks: Dict[str, List[PlaybookRuleDTO]] = {
            "playbook_nda_2026_11": [
                PlaybookRuleDTO(
                    rule_id="NDA-TERM-04",
                    category="confidentiality_duration",
                    title="Confidentiality Term Limit",
                    criteria="Confidentiality obligations must not exceed 3 years (36 months) from the expiration or termination date.",
                    target_value="<= 36 months",
                    standard_clause="The obligations of confidentiality shall survive for a period of three (3) years from the date of disclosure.",
                    severity="HIGH"
                ),
                PlaybookRuleDTO(
                    rule_id="NDA-GOV-02",
                    category="governing_law",
                    title="Indian Governing Law Mandatory",
                    criteria="Governing law must be the Republic of India with jurisdiction in Bengaluru (Karnataka), Mumbai, or New Delhi.",
                    target_value="Republic of India",
                    standard_clause="This Agreement shall be governed by and construed in accordance with the laws of the Republic of India, subject to the jurisdiction of the courts at Bengaluru.",
                    severity="HIGH"
                ),
                PlaybookRuleDTO(
                    rule_id="NDA-INDEM-01",
                    category="indemnity",
                    title="Uncapped Indemnity Exclusion",
                    criteria="Mutual NDAs must exclude uncapped consequential or indirect damages indemnity.",
                    target_value="No uncapped indemnity",
                    standard_clause="Neither party shall be liable for any indirect, incidental, or consequential damages under this NDA.",
                    severity="REVIEW"
                ),
                PlaybookRuleDTO(
                    rule_id="NDA-NON-SOLICIT-03",
                    category="non_solicitation",
                    title="Non-Solicitation Ceiling",
                    criteria="Non-solicitation of personnel must be limited to 12 months.",
                    target_value="<= 12 months",
                    standard_clause="Neither party shall actively solicit the employees of the other for a period exceeding twelve (12) months.",
                    severity="REVIEW"
                )
            ]
        }

        # Seeded Synthetic GoLegal Native Contracts across Tenant A and B
        self.contracts: Dict[str, ContractRevisionDTO] = {
            "rev-ka-nda-001": ContractRevisionDTO(
                id="rev-ka-nda-001",
                contract_id="c-ka-nda-001",
                tenant_id="org-alpha-101",
                revision_no=1,
                title="Mutual Non-Disclosure Agreement - Vendor Alpha",
                sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                field_values={
                    "title": "Mutual Non-Disclosure Agreement - Vendor Alpha",
                    "first_party": "Acme Logistics Pvt. Ltd.",
                    "second_party": "Zenith Cloud Solutions Pvt. Ltd.",
                    "disclosing_party": "Acme Logistics Pvt. Ltd.",
                    "receiving_party": "Zenith Cloud Solutions Pvt. Ltd.",
                    "effective_date": "2026-11-01",
                    "termination_date": "2029-11-01",  # Exactly 36 months (compliant)
                    "governing_law": "Republic of India (Bengaluru, Karnataka)",
                    "confidentiality_duration_months": 36,
                    "monthly_rent_paise": 4500000,
                    "custom_covenants": "Mutual standard disclosure of technical logistics architecture."
                },
                created_at="2026-11-01T10:00:00Z"
            ),
            "rev-ka-nda-deviated-002": ContractRevisionDTO(
                id="rev-ka-nda-deviated-002",
                contract_id="c-ka-nda-deviated-002",
                tenant_id="org-alpha-101",
                revision_no=1,
                title="Supplier NDA - Deviation Test Case",
                sha256="a1b2c3d4e5f60718293a4b5c6d7e8f901234567890abcdef1234567890abcdef",
                field_values={
                    "title": "Supplier NDA - Deviation Test Case",
                    "disclosing_party": "Global Logistics Conglomerate",
                    "receiving_party": "Acme Logistics Pvt. Ltd.",
                    "effective_date": "2026-11-10",
                    "termination_date": "2036-11-10",  # 120 months (violates NDA-TERM-04)
                    "governing_law": "State of Delaware, United States",  # Violates NDA-GOV-02
                    "confidentiality_duration_months": 120,
                    "custom_covenants": "Receiving party indemnifies disclosing party without limitation for any breach."
                },
                created_at="2026-11-10T12:00:00Z"
            ),
            # Tenant B Contract (Isolation test)
            "rev-beta-nda-999": ContractRevisionDTO(
                id="rev-beta-nda-999",
                contract_id="c-beta-nda-999",
                tenant_id="org-beta-202",
                revision_no=1,
                title="Tenant B Private MSA",
                sha256="ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
                field_values={
                    "title": "Tenant B Private MSA",
                    "party_a": "Starlight Retail Ventures",
                    "party_b": "Beta Partner Corp"
                },
                created_at="2026-11-12T09:00:00Z"
            )
        }

    def list_contracts(self, tenant_id: str) -> List[Dict[str, Any]]:
        """
        Enforces PRD §2: Lists tenant-scoped GoLegal contract revisions.
        """
        res = []
        for c in self.contracts.values():
            if c.tenant_id == tenant_id:
                res.append({
                    "id": c.id,
                    "contract_id": c.contract_id,
                    "tenant_id": c.tenant_id,
                    "revision_no": c.revision_no,
                    "title": c.title,
                    "sha256": c.sha256,
                    "field_values": c.field_values,
                    "created_at": c.created_at
                })
        return res

    def get_revision(self, revision_id: str, tenant_id: str) -> Optional[ContractRevisionDTO]:
        rev = self.contracts.get(revision_id)
        if rev and rev.tenant_id == tenant_id:
            return rev
        return None

    def get_native_fields(self, revision_id: str, tenant_id: str) -> Dict[str, Any]:
        """
        Enforces AOS-08 & AT-19: Reuse typed fields in GoLegal-native contracts.
        Bypasses OCR and LLM extraction entirely for existing structured values.
        """
        rev = self.get_revision(revision_id, tenant_id)
        if not rev:
            return {}
        return dict(rev.field_values)

    def get_contract_native_fields(self, contract_or_rev_id: str, tenant_id: str) -> Dict[str, Any]:
        """
        Look up native fields by either contract_id or revision_id for tenant.
        """
        # 1. Try revision ID lookup
        rev = self.get_revision(contract_or_rev_id, tenant_id)
        if rev:
            return dict(rev.field_values)

        # 2. Try contract_id lookup
        for c in self.contracts.values():
            if (c.contract_id == contract_or_rev_id or c.id == contract_or_rev_id) and c.tenant_id == tenant_id:
                return dict(c.field_values)
        return {}

    def download_revision(self, revision_id: str, tenant_id: str) -> bytes:
        rev = self.get_revision(revision_id, tenant_id)
        if not rev:
            raise ValueError(f"Revision '{revision_id}' not found for tenant '{tenant_id}'.")
        return json.dumps(rev.field_values).encode("utf-8")

    def subscribe_revision_events(self, tenant_id: str, callback: Any = None) -> Dict[str, str]:
        return {"status": "SUBSCRIBED", "tenant_id": tenant_id}

    def get_approved_playbook(self, playbook_version_id: str) -> List[PlaybookRuleDTO]:
        return self.playbooks.get(playbook_version_id, [])
