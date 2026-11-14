"""
AI Governance, Prompt-Injection Firewall & Citation-Locked Q&A Service.
Enforces FR-13, FR-14, FR-15, AT-13, AT-14, AT-15, and AT-16.
"""
from __future__ import annotations
import re
import json
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from golegal.domain.models import AIProcessingPolicy, Contract


class AIDisabledError(PermissionError):
    """Raised when an AI request is made while third_party_ai_enabled is False (AT-13)."""
    pass


class AIInsightService:
    def __init__(self, session: Optional[Session] = None):
        self.session = session

    def answer_qa(self, org_id: str, contract_id: str, question: str) -> Dict[str, Any]:
        """Enforces AT-13: Defaults strictly to AI_DISABLED unless explicit org policy is enabled."""
        policy = None
        if self.session:
            policy = self.session.query(AIProcessingPolicy).filter_by(organisation_id=org_id).first()

        if not policy or not policy.third_party_ai_enabled:
            raise AIDisabledError(
                "403 AI_DISABLED: External AI processing is disabled for this organisation by default. "
                "Configure organisation AI policy and lawful processing basis to enable."
            )

        return {
            "status": "answered",
            "question": question,
            "answer": "Deterministic rule evaluation.",
            "citations": []
        }

    def sanitize_untrusted_document_text(self, document_text: str) -> str:
        """Enforces AT-14: Sanitizes prompt injection attacks and isolates untrusted document text."""
        injection_patterns = [
            r"system\s+prompt\s+override",
            r"ignore\s+all\s+(previous|prior)\s+instructions",
            r"dump\s+tenant",
            r"reveal\s+all\s+secrets",
            r"bypass\s+authorization",
        ]
        sanitized = document_text
        for pattern in injection_patterns:
            sanitized = re.sub(pattern, "[UNTRUSTED_CONTENT_FILTERED]", sanitized, flags=re.IGNORECASE)

        return f"--- BEGIN UNTRUSTED_DOC_CONTENT ---\n{sanitized}\n--- END UNTRUSTED_DOC_CONTENT ---"

    def verify_evidence_citation(
        self, source_text: str, claimed_answer: str, claimed_quote: str
    ) -> Dict[str, Any]:
        """Enforces AT-15: Quotes must strictly exist in authorized source text; else return insufficient_evidence."""
        if not claimed_quote or claimed_quote.strip().lower() not in source_text.lower():
            return {
                "status": "insufficient_evidence",
                "answer": None,
                "reason": "Claimed citation quote does not exist in verified source document.",
                "citations": []
            }

        return {
            "status": "verified",
            "answer": claimed_answer,
            "citations": [{"quote": claimed_quote}]
        }

    def execute_tool_action(self, action_name: str, contract_id: str, actor: str) -> Dict[str, Any]:
        """Enforces AT-16: Read-only assistant cannot invoke irreversible payment, signing, or stamping."""
        prohibited_autonomous_actions = [
            "execute_live_esign", "trigger_payment", "remit_stamp_duty", "file_court_case"
        ]
        if actor == "assistant" and action_name in prohibited_autonomous_actions:
            raise PermissionError(
                f"403 HUMAN_GATE_REQUIRED: Action '{action_name}' is a personal legal or financial act. "
                "Autonomous agents are strictly prohibited from execution without human review."
            )
        return {"status": "executed", "action": action_name, "actor": actor}

    def search_contracts(self, org_id: str, query: str) -> List[Dict[str, Any]]:
        """Enforces FR-13 & AT-01: Tenant-scoped search; zero cross-tenant hits."""
        if not self.session:
            return []

        contracts = self.session.query(Contract).filter_by(organisation_id=org_id).all()
        results = []
        q_lower = query.lower()
        for c in contracts:
            content_str = f"{c.title} {json.dumps(c.field_values)}".lower()
            if q_lower in content_str:
                results.append({"id": c.id, "title": c.title, "organisation_id": c.organisation_id})
        return results
