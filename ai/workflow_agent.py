"""
GoLegal Workflow Agent - autonomous lifecycle operator.

Observes every active agreement and drives it forward without a human in the
loop wherever the law allows: dispatching signing links once payment has
cleared, reminding laggards daily, expiring stale signing windows, sealing
the deed the moment the last signature lands, and purging unconsented drafts.

Hard guardrails (never crossed by the agent):
  * it never pays, never buys e-stamp paper, never signs for anyone;
  * every action goes through WorkflowService, so state-machine rules and
    audit journaling apply exactly as they do for human actions;
  * every run is persisted as an AgentRun with its plan and step log.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from domain.models import AgentRun, Agreement, utc_now
from services.document_service import DocumentService
from services.validation import validate_wizard_payload
from services.workflow_service import WorkflowService


@dataclass
class AgentStep:
    action: str
    detail: str
    ok: bool = True
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"tool": self.action, "input": {}, "output": {"detail": self.detail, **self.data}, "ok": self.ok}


class WorkflowAgent:
    def __init__(self, session: Session, workflow: Optional[WorkflowService] = None):
        self.session = session
        self.workflow = workflow or WorkflowService(session)
        self.documents = DocumentService(session)

    # ------------------------------------------------------------------ planning
    def observe(self, agreement: Agreement, now=None) -> Dict[str, Any]:
        now = now or utc_now()
        parties = agreement.parties
        pending = [p for p in parties if p.signing_status != "Signed"]
        return {
            "status": agreement.status,
            "parties": len(parties),
            "signed": len(parties) - len(pending),
            "pending": [p.full_name for p in pending],
            "expired": bool(agreement.expires_at and agreement.expires_at < now and agreement.status == "Pending_Signatures"),
            "due_for_reminder": [p.full_name for p in pending
                                 if not p.last_notified_at or now - p.last_notified_at >= timedelta(hours=20)],
            "has_estamp": agreement.estamp is not None,
            "has_payment": agreement.payment is not None and agreement.payment.status == "Success",
            "sealed": bool(agreement.final_pdf_sha256),
        }

    def plan(self, agreement: Agreement, now=None) -> List[str]:
        obs = self.observe(agreement, now)
        status = obs["status"]
        if status == "Draft":
            from services.agreement_service import AgreementService
            issues = validate_wizard_payload(AgreementService(self.session).load_payload(agreement))
            plan = ["Validate draft completeness"]
            plan.append("Wait for the initiator to pay and procure the e-Stamp (human gate)" if not issues
                        else f"Ask the initiator to fix {len(issues)} validation issue(s)")
            return plan
        if status == "Paid":
            return ["Mint capability tokens for every party", "Dispatch signing invitations (WhatsApp/SMS/Email)", "Open the 7-day signing window"]
        if status == "Pending_Signatures":
            plan = []
            if obs["expired"]:
                plan.append("Signing window breached - mark agreement Expired and notify initiator")
            else:
                if obs["pending"] and obs["due_for_reminder"]:
                    plan.append(f"Send daily reminders to {', '.join(obs['due_for_reminder'])}")
                if not obs["pending"]:
                    plan.append("All parties signed - seal with corporate DSC and distribute")
                if not plan:
                    plan.append(f"Wait: {len(obs['pending'])} signature(s) outstanding, reminders already sent today")
            return plan
        if status == "Completed":
            return ["Verify sealed document digest"] + ([] if obs["sealed"] else ["Seal document (missing final PDF)"])
        return [f"No action for status {status}"]

    # ------------------------------------------------------------------ execution
    def run(self, agreement: Agreement, triggered_by: str = "WORKFLOW_AGENT", now=None) -> AgentRun:
        now = now or utc_now()
        plan = self.plan(agreement, now)
        run = AgentRun(agent_type="WORKFLOW", agreement_id=agreement.id, user_id=None,
                       goal=f"Advance agreement {agreement.id[:8]} ({agreement.status}): " + "; ".join(plan),
                       status="RUNNING", model="rule-based")
        self.session.add(run)
        self.session.flush()
        steps: List[AgentStep] = []
        status = "COMPLETED"
        try:
            obs = self.observe(agreement, now)
            if agreement.status == "Draft":
                from services.agreement_service import AgreementService
                issues = validate_wizard_payload(AgreementService(self.session).load_payload(agreement))
                steps.append(AgentStep("validate_draft", "Draft is complete" if not issues else f"{len(issues)} issue(s)", ok=not issues, data={"issues": issues}))
                steps.append(AgentStep("human_gate", "Payment and e-Stamp procurement must be done by the initiator", data={"gate": "PAYMENT"}))
                status = "NEEDS_HUMAN"
            elif agreement.status == "Paid":
                if not obs["has_estamp"]:
                    steps.append(AgentStep("human_gate", "Paid but no e-Stamp certificate found; initiator must complete checkout", ok=False))
                    status = "NEEDS_HUMAN"
                else:
                    sent = self.workflow.open_for_signatures(agreement, triggered_by=triggered_by)
                    steps.append(AgentStep("dispatch_invitations", f"Dispatched {len(sent)} signing link(s)",
                                           data={"recipients": [s["party_name"] for s in sent],
                                                 "expires_at": agreement.expires_at}))
            elif agreement.status == "Pending_Signatures":
                if obs["expired"]:
                    self.workflow.transition_state(agreement, "Expired", triggered_by=triggered_by)
                    steps.append(AgentStep("expire", "Signing window breached; agreement marked Expired"))
                else:
                    completed = self.workflow.check_and_complete_signing(agreement.id)
                    if completed:
                        steps.append(AgentStep("seal", "All signatures present; sealed with corporate DSC",
                                               data={"sha256": agreement.final_pdf_sha256}))
                    elif obs["due_for_reminder"]:
                        targets = [p.id for p in agreement.parties if p.full_name in obs["due_for_reminder"]]
                        sent = self.workflow.resend_invitations(agreement, targets, triggered_by=triggered_by)
                        steps.append(AgentStep("remind", f"Reminded {len(sent)} party(ies)", data={"recipients": [s["party_name"] for s in sent]}))
                    else:
                        steps.append(AgentStep("wait", f"{len(obs['pending'])} signature(s) outstanding; reminders already sent within 20h"))
            elif agreement.status == "Completed":
                doc = self.documents.latest(agreement.id, "FINAL")
                if not doc:
                    self.workflow.seal_agreement(agreement)
                    steps.append(AgentStep("seal", "Final PDF was missing; regenerated and sealed"))
                else:
                    ok = self.documents.verify(doc) and doc.sha256 == agreement.final_pdf_sha256
                    steps.append(AgentStep("verify_seal", "Sealed document digest verified" if ok else "DIGEST MISMATCH - tamper alert", ok=ok,
                                           data={"sha256": doc.sha256}))
                    if not ok:
                        status = "FAILED"
            else:
                steps.append(AgentStep("noop", f"No action for status {agreement.status}"))
        except Exception as exc:
            steps.append(AgentStep("error", f"{type(exc).__name__}: {exc}", ok=False))
            status = "FAILED"
        run.status = status
        run.set_steps([s.to_dict() for s in steps])
        run.outcome = "; ".join(s.detail for s in steps)
        run.completed_at = utc_now()
        self.session.commit()
        return run

    def sweep(self, triggered_by: str = "WORKFLOW_AGENT_CRON", now=None) -> Dict[str, Any]:
        """Run the agent across every active agreement plus the retention purge (the platform 'cron')."""
        now = now or utc_now()
        active = (self.session.query(Agreement)
                  .filter(Agreement.status.in_(["Paid", "Pending_Signatures"])).all())
        summary: Dict[str, Any] = {"agreements_visited": len(active), "runs": [], "purged_drafts": 0}
        for agr in active:
            run = self.run(agr, triggered_by=triggered_by, now=now)
            summary["runs"].append({"agreement_id": agr.id, "status": run.status, "outcome": run.outcome})
        summary["purged_drafts"] = self.workflow.purge_unconsented_drafts(now)
        return summary

    def recent_runs(self, limit: int = 25) -> List[AgentRun]:
        return self.session.query(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit).all()
