"""
AgentOS Reasoning Protocol & Local GPU / Fixture Agent Brains.
Enforces AOS-09, AOS-16, AT-18, AT-23, and PRD Section 5 local deployment profiles.
"""
from __future__ import annotations
import json
import re
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from golegal.agentos.domain.models import SourceSpan, Finding, Mission, generate_uuid
from golegal.agentos.integrations.contract_gateway import FixtureContractGateway, PlaybookRuleDTO
from golegal.agentos.intelligence.gpu_rag import GPURAGEngine


class AgentBrain:
    """Protocol for AgentOS Reasoning & Investigation Brain."""
    def analyze_source_spans(
        self,
        mission_id: str,
        tenant_id: str,
        source_revision_ids: List[str],
        playbook_version_id: str
    ) -> List[Finding]:
        raise NotImplementedError


class FixtureAgentBrain(AgentBrain):
    """
    Deterministic P0 Simulation Brain (PRD §5 & §9).
    Compares extracted document spans against dated playbook rules without outbound LLM calls.
    Labels simulation outputs explicitly (AT-23).
    """
    def __init__(self, session: Session):
        self.session = session
        self.gateway = FixtureContractGateway()
        self.gpu_rag = GPURAGEngine(session)

    def analyze_source_spans(
        self,
        mission_id: str,
        tenant_id: str,
        source_revision_ids: List[str],
        playbook_version_id: str
    ) -> List[Finding]:
        rules = self.gateway.get_approved_playbook(playbook_version_id)
        if not rules:
            return []

        findings: List[Finding] = []

        # 1. Inspect GoLegal Native Contracts via Gateway (AT-19)
        for s_rev_id in source_revision_ids:
            native_fields = self.gateway.get_native_fields(s_rev_id, tenant_id)
            if native_fields:
                findings.extend(self._evaluate_native_fields(mission_id, tenant_id, s_rev_id, native_fields, rules))

        # 2. Inspect Uploaded PDF Spans via GPU RAG & Regex Patterns
        spans = (
            self.session.query(SourceSpan)
            .filter(
                SourceSpan.tenant_id == tenant_id,
                SourceSpan.source_revision_id.in_(source_revision_ids)
            )
            .all()
        )

        for span in spans:
            text = span.verbatim_excerpt.lower()
            
            # Check Rule NDA-TERM-04: Confidentiality duration > 36 months / 3 years
            for match in re.finditer(r'(\d+)\s*(years|months)', text):
                val = int(match.group(1))
                unit = match.group(2)
                months = val * 12 if "year" in unit else val
                if months > 36:
                    rule = next((r for r in rules if r.rule_id == "NDA-TERM-04"), None)
                    if rule:
                        f = Finding(
                            mission_id=mission_id,
                            source_span_id=span.id,
                            playbook_rule_id=rule.rule_id,
                            playbook_version=playbook_version_id,
                            category=rule.category,
                            severity=rule.severity,
                            statement=f"Confidentiality duration of {months} months exceeds approved playbook ceiling of 36 months.",
                            verification_state="CANDIDATE",
                            review_state="OPEN",
                            rationale=f"Simulated rule match against span text: '{span.verbatim_excerpt[:80]}...'"
                        )
                        self.session.add(f)
                        findings.append(f)

            # Check Rule NDA-GOV-02: Non-Indian governing law
            if any(fl in text for fl in ["delaware", "california", "new york", "england and wales", "singapore"]):
                rule = next((r for r in rules if r.rule_id == "NDA-GOV-02"), None)
                if rule:
                    f = Finding(
                        mission_id=mission_id,
                        source_span_id=span.id,
                        playbook_rule_id=rule.rule_id,
                        playbook_version=playbook_version_id,
                        category=rule.category,
                        severity=rule.severity,
                        statement="Foreign governing law detected. Playbook mandates Republic of India jurisdiction.",
                        verification_state="CANDIDATE",
                        review_state="OPEN",
                        rationale=f"Non-compliant jurisdiction identified in excerpt: '{span.verbatim_excerpt[:80]}...'"
                    )
                    self.session.add(f)
                    findings.append(f)

            # Check Rule NDA-INDEM-01: Uncapped indemnity
            if "indemnif" in text and any(w in text for w in ["without limit", "uncapped", "all damages", "consequential"]):
                rule = next((r for r in rules if r.rule_id == "NDA-INDEM-01"), None)
                if rule:
                    f = Finding(
                        mission_id=mission_id,
                        source_span_id=span.id,
                        playbook_rule_id=rule.rule_id,
                        playbook_version=playbook_version_id,
                        category=rule.category,
                        severity=rule.severity,
                        statement="Uncapped indemnity provision detected in mutual non-disclosure agreement.",
                        verification_state="CANDIDATE",
                        review_state="OPEN",
                        rationale=f"Indemnity clause identified in excerpt: '{span.verbatim_excerpt[:80]}...'"
                    )
                    self.session.add(f)
                    findings.append(f)

        self.session.commit()
        return findings

    def _evaluate_native_fields(
        self,
        mission_id: str,
        tenant_id: str,
        s_rev_id: str,
        fields: Dict[str, Any],
        rules: List[PlaybookRuleDTO]
    ) -> List[Finding]:
        """Evaluates native contract fields directly with zero AI/OCR cost (AT-19)."""
        findings = []
        # Create anchor span for native fields if needed
        anchor_span = (
            self.session.query(SourceSpan)
            .filter_by(source_revision_id=s_rev_id)
            .first()
        )
        if not anchor_span:
            anchor_span = SourceSpan(
                tenant_id=tenant_id,
                source_revision_id=s_rev_id,
                source_sha256="native-fields-hash",
                page_index_0=0,
                char_start=0,
                char_end=len(str(fields)),
                verbatim_excerpt=str(fields)[:200],
                excerpt_sha256=hashlib.sha256(str(fields).encode()).hexdigest(),
                extraction_method="NATIVE_TYPED_FIELD"
            )
            self.session.add(anchor_span)
            self.session.flush()

        months = fields.get("confidentiality_duration_months") or fields.get("confidentiality_term_months") or 0
        try:
            months = int(months)
        except (ValueError, TypeError):
            months = 0

        def _get_rule_prop(r_obj: Any, prop: str, default: Any = "") -> Any:
            if isinstance(r_obj, dict):
                return r_obj.get(prop, default)
            return getattr(r_obj, prop, default)

        if months > 36:
            rule = next((r for r in rules if _get_rule_prop(r, "rule_id") == "NDA-TERM-04"), None)
            if rule:
                f = Finding(
                    mission_id=mission_id,
                    source_span_id=anchor_span.id,
                    playbook_rule_id=_get_rule_prop(rule, "rule_id"),
                    playbook_version="2026-11-v1",
                    category=_get_rule_prop(rule, "category", "confidentiality_duration"),
                    severity=_get_rule_prop(rule, "severity", "HIGH"),
                    statement=f"Native field confidentiality duration ({months} months) violates 36-month ceiling.",
                    verification_state="CANDIDATE",
                    review_state="OPEN",
                    rationale="Extracted directly from GoLegal native structured contract record without OCR/LLM cost."
                )
                self.session.add(f)
                findings.append(f)

        gov_law = str(fields.get("governing_law", ""))
        if "india" not in gov_law.lower() and gov_law != "":
            rule = next((r for r in rules if _get_rule_prop(r, "rule_id") == "NDA-GOV-02"), None)
            if rule:
                f = Finding(
                    mission_id=mission_id,
                    source_span_id=anchor_span.id,
                    playbook_rule_id=_get_rule_prop(rule, "rule_id"),
                    playbook_version="2026-11-v1",
                    category=_get_rule_prop(rule, "category", "governing_law"),
                    severity=_get_rule_prop(rule, "severity", "HIGH"),
                    statement=f"Native field governing law '{gov_law}' differs from Republic of India.",
                    verification_state="CANDIDATE",
                    review_state="OPEN",
                    rationale="Extracted directly from GoLegal native contract record."
                )
                self.session.add(f)
                findings.append(f)

        return findings

    evaluate_contract_native_fields = _evaluate_native_fields
