"""
Legal Catalog & Statutory Eligibility Service.
Enforces FR-02 & AT-02: Unapproved templates block execution with 422.
"""
from __future__ import annotations
import json
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from golegal.domain.models import TemplateVersion, EligibilityRule


class LegalEligibilityError(ValueError):
    """Raised when an unapproved template or blocked execution mode is triggered."""
    pass


class CatalogService:
    def __init__(self, session: Session):
        self.session = session

    def seed_demo_templates_if_missing(self) -> None:
        """Seed demo Karnataka rental & mutual NDA templates with safe unapproved states."""
        if not self.session.query(TemplateVersion).filter_by(id="tpl_ka_rental_v1").first():
            ka_tpl = TemplateVersion(
                id="tpl_ka_rental_v1",
                agreement_type="Rental_Residential",
                jurisdiction_code="KA",
                version="1.0.0",
                state="draft",  # DRAFT_NOT_LEGAL_APPROVED
                schema_json_raw=json.dumps({
                    "required": ["monthly_rent_paise", "start_date", "end_date"],
                    "properties": {
                        "monthly_rent_paise": {"type": "integer", "minimum": 100},
                        "security_deposit_paise": {"type": "integer", "minimum": 0},
                        "start_date": {"type": "string", "format": "date"},
                        "end_date": {"type": "string", "format": "date"},
                    }
                })
            )
            ka_rule = EligibilityRule(
                template_version_id="tpl_ka_rental_v1",
                document_type="Rental_Residential",
                jurisdiction_code="KA",
                execution_mode="draft_only",  # Fail-closed default
                requires_stamping=True,
                requires_registration_review=True,
                rule_version="1.0.0"
            )
            self.session.add_all([ka_tpl, ka_rule])

        if not self.session.query(TemplateVersion).filter_by(id="tpl_mutual_nda_v1").first():
            nda_tpl = TemplateVersion(
                id="tpl_mutual_nda_v1",
                agreement_type="Commercial_NDA",
                jurisdiction_code="ALL",
                version="1.0.0",
                state="draft",
                schema_json_raw=json.dumps({
                    "required": ["term_months", "purpose"],
                    "properties": {"term_months": {"type": "integer", "minimum": 1}}
                })
            )
            nda_rule = EligibilityRule(
                template_version_id="tpl_mutual_nda_v1",
                document_type="Commercial_NDA",
                jurisdiction_code="ALL",
                execution_mode="draft_only",
                requires_stamping=False,
                requires_registration_review=False,
                rule_version="1.0.0"
            )
            self.session.add_all([nda_tpl, nda_rule])

        self.session.flush()

    def get_template(self, template_id: str) -> Optional[TemplateVersion]:
        return self.session.query(TemplateVersion).filter_by(id=template_id).first()

    def list_templates(self, jurisdiction: Optional[str] = None) -> List[TemplateVersion]:
        q = self.session.query(TemplateVersion)
        if jurisdiction and jurisdiction != "ALL":
            q = q.filter(TemplateVersion.jurisdiction_code.in_([jurisdiction, "ALL"]))
        return q.all()

    def verify_execution_eligibility(self, template_version_id: str) -> EligibilityRule:
        """Enforces AT-02: Template state must be legal_approved and execution_mode provider_allowed."""
        tpl = self.get_template(template_version_id)
        if not tpl:
            raise LegalEligibilityError(f"404 NOT_FOUND: Template '{template_version_id}' not found.")
        
        rule = self.session.query(EligibilityRule).filter_by(template_version_id=template_version_id).first()
        if not rule or rule.execution_mode != "provider_allowed" or tpl.state != "legal_approved":
            raise LegalEligibilityError(
                f"422 LEGAL_ELIGIBILITY_UNVERIFIED: Template '{template_version_id}' is marked '{tpl.state}' "
                f"with execution_mode '{rule.execution_mode if rule else 'none'}'. "
                "Draft rendering permitted; execution blocked pending qualified legal sign-off."
            )
        return rule
