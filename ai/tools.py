"""
GoLegal Agent Tool Registry

Every capability an AI agent can exercise is declared here with a JSON schema,
a permission tier and a handler that calls the same application services the
UI uses. Guardrails:

- `read`  : pure lookups, always allowed.
- `write` : mutates session/draft state or dispatches notifications; allowed
            in assist mode, never for a read-only run.
- `human` : payment, e-Stamp procurement and Aadhaar eSign are legally personal
            acts. They are described to the model so it can guide the user, but
            they have no handler and can never be executed by an agent.

The registry records every call (input, output, ok) so runs are auditable.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from ai.clause_intelligence import ClauseIntelligence, redact_pii
from ai.contract_ingest import extract_terms, merge_into_payload
from ai.rent_benchmark import benchmark, supported_cities
from domain.models import User
from services.agreement_service import AgreementAccessError, AgreementService, empty_payload
from services.rule_engine import STATE_STAMP_RULES, calculate_stamp_duty
from services.validation import validate_wizard_payload
from services.workflow_service import WorkflowService


class ToolPermissionError(Exception):
    pass


@dataclass
class ToolContext:
    session: Session
    user: Optional[User] = None
    payload: Dict[str, Any] = field(default_factory=empty_payload)  # live wizard draft (session state)
    agreement_id: Optional[str] = None
    mode: str = "assist"  # assist | readonly
    llm: Any = None
    payload_changed: bool = False


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: Dict[str, Any]
    tier: str
    handler: Optional[Callable[[ToolContext, Dict[str, Any]], Any]] = None

    def anthropic_definition(self) -> Dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


def _obj(props: Dict[str, Any], required: Optional[List[str]] = None) -> Dict[str, Any]:
    return {"type": "object", "properties": props, "required": required or [], "additionalProperties": False}


# ---------------------------------------------------------------- handlers
def _t_stamp_duty(ctx: ToolContext, inp: Dict[str, Any]) -> Dict[str, Any]:
    c = ctx.payload.get("commercials", {})
    return calculate_stamp_duty(
        inp.get("state_code") or ctx.payload.get("state_code", "KA"),
        float(inp.get("monthly_rent") or c.get("monthly_rent") or 0),
        float(inp.get("security_deposit") or c.get("security_deposit") or 0),
        int(inp.get("lease_months") or c.get("lease_months") or 11),
    )


def _t_benchmark(ctx: ToolContext, inp: Dict[str, Any]) -> Dict[str, Any]:
    p = ctx.payload.get("property", {})
    c = ctx.payload.get("commercials", {})
    return benchmark(
        inp.get("city") or p.get("city", ""),
        inp.get("locality") or p.get("address", ""),
        inp.get("bhk") or ("2BHK" if "2" in str(p.get("property_type", "")) else "3BHK" if "3" in str(p.get("property_type", "")) else "2BHK"),
        float(inp.get("monthly_rent") or c.get("monthly_rent") or 0) or None,
        float(inp.get("security_deposit") or c.get("security_deposit") or 0) or None,
    )


def _t_risk(ctx: ToolContext, inp: Dict[str, Any]) -> Dict[str, Any]:
    ci = ClauseIntelligence(ctx.llm)
    commercials = {**ctx.payload.get("commercials", {}), **(inp.get("commercials") or {})}
    text = inp.get("custom_clauses") if inp.get("custom_clauses") is not None else ctx.payload.get("custom_clauses", "")
    report = ci.assess_risk(text or "", commercials, ctx.payload.get("clause_toggles"),
                            ctx.payload.get("agreement_type", "Rental_Residential"), ctx.payload.get("state_code", "KA"),
                            use_llm=False)  # the calling agent already is the model; keep tool deterministic
    if report.redacted_text is not None and ctx.mode == "assist":
        ctx.payload["custom_clauses"] = report.redacted_text
        ctx.payload_changed = True
    return report.to_dict()


def _t_explain(ctx: ToolContext, inp: Dict[str, Any]) -> Dict[str, Any]:
    return {"term": inp.get("term", ""), "explanation": ClauseIntelligence(ctx.llm).explain_clause(inp.get("term", ""))}


def _t_prefill(ctx: ToolContext, inp: Dict[str, Any]) -> Dict[str, Any]:
    updates = {k: v for k, v in inp.items() if v not in (None, "", [], {})}
    for group in ("owners", "tenants", "witnesses"):
        for p in updates.get(group, []) or []:
            p.pop("aadhaar", None)  # agents never handle Aadhaar numbers
    ctx.payload = merge_into_payload(ctx.payload, updates)
    ctx.payload_changed = True
    errors = validate_wizard_payload(ctx.payload)
    return {"applied": sorted(updates.keys()), "remaining_validation_issues": errors[:8],
            "ready_for_payment": not errors}


def _t_extract(ctx: ToolContext, inp: Dict[str, Any]) -> Dict[str, Any]:
    result = extract_terms(inp.get("text", ""), llm=ctx.llm, use_llm=False)
    if inp.get("apply", True) and result.payload_updates and ctx.mode == "assist":
        ctx.payload = merge_into_payload(ctx.payload, result.payload_updates)
        ctx.payload_changed = True
    out = result.to_dict()
    out["remaining_validation_issues"] = validate_wizard_payload(ctx.payload)[:8]
    return out


def _t_validate(ctx: ToolContext, inp: Dict[str, Any]) -> Dict[str, Any]:
    errors = validate_wizard_payload(ctx.payload)
    p = ctx.payload
    return {
        "issues": errors,
        "ready_for_payment": not errors,
        "snapshot": {
            "agreement_type": p.get("agreement_type"), "state_code": p.get("state_code"),
            "owners": [o.get("name") for o in p.get("owners", [])],
            "tenants": [t.get("name") for t in p.get("tenants", [])],
            "witnesses": [w.get("name") for w in p.get("witnesses", [])],
            "property": {k: p.get("property", {}).get(k) for k in ("premises_name", "address", "city", "pincode")},
            "commercials": p.get("commercials"),
            "clause_toggles": p.get("clause_toggles"),
            "custom_clauses": (p.get("custom_clauses") or "")[:300],
        },
    }


def _t_list(ctx: ToolContext, inp: Dict[str, Any]) -> Dict[str, Any]:
    if not ctx.user:
        return {"agreements": [], "note": "Sign in to see your agreements."}
    svc = AgreementService(ctx.session)
    rows = []
    for a in svc.list_for_user(ctx.user)[:20]:
        rows.append({"id": a.id, "title": a.display_title, "type": a.agreement_type, "state": a.state_code,
                     "status": a.status, "signed": f"{a.signed_count()}/{len(a.parties)}",
                     "created_at": a.created_at.isoformat() if a.created_at else None,
                     "expires_at": a.expires_at.isoformat() if a.expires_at else None})
    return {"agreements": rows}


def _resolve_agreement(ctx: ToolContext, inp: Dict[str, Any]):
    svc = AgreementService(ctx.session)
    agr_id = inp.get("agreement_id") or ctx.agreement_id
    if not agr_id and ctx.user:
        pending = [a for a in svc.list_for_user(ctx.user) if a.status == "Pending_Signatures"]
        if len(pending) == 1:
            agr_id = pending[0].id
    if not agr_id:
        raise AgreementAccessError("Which agreement? Provide agreement_id (use list_my_agreements).")
    return svc.get_accessible(agr_id, ctx.user) if ctx.user else None


def _t_progress(ctx: ToolContext, inp: Dict[str, Any]) -> Dict[str, Any]:
    agr = _resolve_agreement(ctx, inp)
    wf = WorkflowService(ctx.session)
    prog = wf.get_signing_progress(agr.id)
    prog.update({"title": agr.display_title, "status": agr.status,
                 "expires_at": agr.expires_at.isoformat() if agr.expires_at else None,
                 "sealed": bool(agr.final_pdf_sha256)})
    return prog


def _t_remind(ctx: ToolContext, inp: Dict[str, Any]) -> Dict[str, Any]:
    agr = _resolve_agreement(ctx, inp)
    if agr.status != "Pending_Signatures":
        return {"sent": 0, "note": f"Agreement is {agr.status}; reminders only apply while signatures are pending."}
    if agr.initiator_id != ctx.user.id and not ctx.user.is_admin:
        raise ToolPermissionError("Only the initiator can send reminders.")
    wf = WorkflowService(ctx.session)
    sent = wf.resend_invitations(agr, inp.get("party_ids"), triggered_by=f"COPILOT:{ctx.user.id[:8]}")
    return {"sent": len(sent), "recipients": [s["party_name"] for s in sent]}


def _t_save_draft(ctx: ToolContext, inp: Dict[str, Any]) -> Dict[str, Any]:
    if not ctx.user:
        raise ToolPermissionError("Sign in to save a draft.")
    svc = AgreementService(ctx.session)
    agr = svc.save_draft(ctx.user, ctx.payload, agreement_id=ctx.agreement_id)
    ctx.agreement_id = agr.id
    return {"agreement_id": agr.id, "status": agr.status, "title": agr.display_title}


def _t_summary(ctx: ToolContext, inp: Dict[str, Any]) -> Dict[str, Any]:
    return ClauseIntelligence(ctx.llm).plain_language_summary(ctx.payload, inp.get("language", "en"))


def _t_redact(ctx: ToolContext, inp: Dict[str, Any]) -> Dict[str, Any]:
    clean, n = redact_pii(inp.get("text", ""))
    return {"redacted_text": clean, "redactions": n}


def _t_states(ctx: ToolContext, inp: Dict[str, Any]) -> Dict[str, Any]:
    return {"states": [{"code": k, "name": v["name"], "flat_duty": v["flat_duty"], "pct_rate": v.get("pct_rate", 0)}
                       for k, v in STATE_STAMP_RULES.items()], "benchmark_cities": supported_cities()}


PARTY_SCHEMA = {"type": "array", "items": _obj({
    "name": {"type": "string"}, "phone": {"type": "string"}, "email": {"type": "string"},
    "pan": {"type": "string"}, "address": {"type": "string"}})}


def build_registry(ctx: ToolContext) -> "ToolRegistry":
    specs = [
        ToolSpec("calculate_stamp_duty", "Compute statutory stamp duty, GoLegal OS platform fee, GST and total payable for a state and rent terms. Always use this instead of guessing prices.",
                 _obj({"state_code": {"type": "string"}, "monthly_rent": {"type": "number"}, "security_deposit": {"type": "number"}, "lease_months": {"type": "integer"}}),
                 "read", _t_stamp_duty),
        ToolSpec("list_supported_states", "List states with stamp rules and cities with rent benchmarks.", _obj({}), "read", _t_states),
        ToolSpec("get_rent_benchmark", "Fair-rent band and deposit norms for a city/locality and BHK; compares the proposed rent and deposit.",
                 _obj({"city": {"type": "string"}, "locality": {"type": "string"}, "bhk": {"type": "string"}, "monthly_rent": {"type": "number"}, "security_deposit": {"type": "number"}}),
                 "read", _t_benchmark),
        ToolSpec("assess_clause_risk", "Score the risk of the current draft's commercial terms and custom covenants; flags unfair or unenforceable clauses and masks PII.",
                 _obj({"custom_clauses": {"type": "string"}, "commercials": {"type": "object"}}), "read", _t_risk),
        ToolSpec("explain_legal_term", "Plain-language explanation of a clause or legal term (lock-in, e-stamp, Section 65B, deposit...).",
                 _obj({"term": {"type": "string"}}, ["term"]), "read", _t_explain),
        ToolSpec("get_draft_status", "Show the current wizard draft snapshot and what is still missing before payment.", _obj({}), "read", _t_validate),
        ToolSpec("summarize_agreement", "Plain-language summary of the current draft; language: en, hi (Hindi), kn (Kannada), ta, te.",
                 _obj({"language": {"type": "string"}}), "read", _t_summary),
        ToolSpec("redact_pii", "Mask Aadhaar, PAN and phone numbers in a piece of text.", _obj({"text": {"type": "string"}}, ["text"]), "read", _t_redact),
        ToolSpec("list_my_agreements", "List the signed-in user's agreements with status and signing progress.", _obj({}), "read", _t_list),
        ToolSpec("get_signing_progress", "Per-party signing status for an agreement (defaults to the user's single pending agreement).",
                 _obj({"agreement_id": {"type": "string"}}), "read", _t_progress),
        ToolSpec("extract_terms_from_text", "Extract parties, property and commercial terms from pasted contract text or a natural-language brief and apply them to the draft.",
                 _obj({"text": {"type": "string"}, "apply": {"type": "boolean"}}, ["text"]), "write", _t_extract),
        ToolSpec("prefill_agreement", "Set fields on the current draft. Provide only the keys you know. Never include Aadhaar numbers.",
                 _obj({"agreement_type": {"type": "string"}, "state_code": {"type": "string"}, "title": {"type": "string"},
                       "owners": PARTY_SCHEMA, "tenants": PARTY_SCHEMA, "witnesses": PARTY_SCHEMA,
                       "property": _obj({"premises_name": {"type": "string"}, "address": {"type": "string"}, "city": {"type": "string"},
                                         "pincode": {"type": "string"}, "property_type": {"type": "string"}, "inclusions": {"type": "string"}}),
                       "commercials": _obj({"monthly_rent": {"type": "number"}, "security_deposit": {"type": "number"}, "lease_months": {"type": "integer"},
                                            "lock_in_months": {"type": "integer"}, "notice_days": {"type": "integer"}, "rent_due_day": {"type": "integer"},
                                            "escalation_pct": {"type": "number"}, "lease_start": {"type": "string"}}),
                       "clause_toggles": _obj({"pets_allowed": {"type": "boolean"}, "painting_deduction": {"type": "boolean"},
                                               "subletting_allowed": {"type": "boolean"}, "parking_included": {"type": "boolean"}}),
                       "custom_clauses": {"type": "string"}, "cloud_storage_consent": {"type": "boolean"}}),
                 "write", _t_prefill),
        ToolSpec("save_draft", "Persist the current draft to the user's workspace so it can be resumed later.", _obj({}), "write", _t_save_draft),
        ToolSpec("send_signing_reminders", "Re-send tokenized signing links to parties who have not signed yet (initiator only).",
                 _obj({"agreement_id": {"type": "string"}, "party_ids": {"type": "array", "items": {"type": "string"}}}), "write", _t_remind),
        # Human-only acts: described, never executable.
        ToolSpec("pay_and_procure_estamp", "HUMAN ONLY. Payment and e-Stamp purchase happen on the Checkout step; guide the user there.", _obj({}), "human"),
        ToolSpec("aadhaar_esign", "HUMAN ONLY. Each signatory completes Aadhaar OTP eSign personally via their secure link.", _obj({}), "human"),
    ]
    return ToolRegistry(ctx, specs)


class ToolRegistry:
    def __init__(self, ctx: ToolContext, specs: List[ToolSpec]):
        self.ctx = ctx
        self.specs = {s.name: s for s in specs}
        self.calls: List[Dict[str, Any]] = []

    def definitions(self, include_human: bool = True) -> List[Dict[str, Any]]:
        return [s.anthropic_definition() for s in self.specs.values() if include_human or s.tier != "human"]

    def execute(self, name: str, inp: Optional[Dict[str, Any]]) -> tuple[str, bool]:
        """Run a tool with guardrails. Returns (json_result, ok)."""
        inp = inp or {}
        spec = self.specs.get(name)
        record: Dict[str, Any] = {"tool": name, "input": inp}
        try:
            if not spec:
                raise ToolPermissionError(f"Unknown tool '{name}'.")
            if spec.tier == "human":
                raise ToolPermissionError(f"'{name}' is a human-only action. Explain to the user how to do it in the app.")
            if spec.tier == "write" and self.ctx.mode == "readonly":
                raise ToolPermissionError(f"'{name}' modifies state and is not allowed in read-only mode.")
            result = spec.handler(self.ctx, inp)
            out = json.dumps(result, default=str, ensure_ascii=False)
            record.update({"output": result, "ok": True})
            self.calls.append(record)
            return out, True
        except (ToolPermissionError, AgreementAccessError, ValueError) as exc:
            record.update({"output": str(exc), "ok": False})
            self.calls.append(record)
            return json.dumps({"error": str(exc)}), False
        except Exception as exc:  # defensive: never crash the agent loop
            record.update({"output": f"{type(exc).__name__}: {exc}", "ok": False})
            self.calls.append(record)
            return json.dumps({"error": f"Tool failed: {type(exc).__name__}: {exc}"}), False
