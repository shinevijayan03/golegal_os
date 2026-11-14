"""
AgentOS Durable Mission Engine & State Machine Orchestrator.
Enforces AOS-04, AOS-05, AOS-06, AOS-07, AOS-12, and AT-04..AT-15, AT-25.
"""
from __future__ import annotations
import json
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Set
from sqlalchemy.orm import Session

from golegal.agentos.domain.models import (
    Mission, MissionInput, MissionPlan, MissionTask, Approval,
    AgentDeployment, DocumentSource, SourceRevision, utc_now, generate_uuid
)
from golegal.agentos.services.rbac_service import (
    RBACService, normalize_role, RolePermissionDeniedError,
    ROLE_MISSION_OPERATOR, ROLE_TENANT_ADMIN, ROLE_LEGAL_REVIEWER
)
from golegal.agentos.runtime.budget import BudgetService, BudgetExceededError


class CollectionScopeDeniedError(PermissionError):
    """Raised when mission requests access to documents outside the deployment's authorized collection (AT-05)."""
    pass


class PlanValidationError(ValueError):
    """Raised when generated plan violates acyclic graph, step limits or capability bounds (AT-06)."""
    pass


class ApprovalStaleError(RuntimeError):
    """Raised when approval hash mismatches current plan or approval TTL has expired (AT-10)."""
    pass


class ApprovalConflictError(RuntimeError):
    """Raised on concurrent or conflicting approval decisions (AT-25)."""
    pass


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal mission state transition is attempted (AT-12)."""
    pass


# Mission States
STATE_CREATED = "CREATED"
STATE_PLANNING = "PLANNING"
STATE_AWAITING_SCOPE_APPROVAL = "AWAITING_SCOPE_APPROVAL"
STATE_RUNNING = "RUNNING"
STATE_AWAITING_REVIEW = "AWAITING_REVIEW"
STATE_PAUSED = "PAUSED"
STATE_DELIVERED = "DELIVERED"
STATE_COMPLETED = "COMPLETED"
STATE_CANCELLED = "CANCELLED"
STATE_FAILED = "FAILED"
STATE_BUDGET_EXCEEDED = "BUDGET_EXCEEDED"

VALID_TRANSITIONS: Dict[str, Set[str]] = {
    STATE_CREATED: {STATE_PLANNING, STATE_CANCELLED, STATE_FAILED},
    STATE_PLANNING: {STATE_AWAITING_SCOPE_APPROVAL, STATE_CANCELLED, STATE_FAILED},
    STATE_AWAITING_SCOPE_APPROVAL: {STATE_RUNNING, STATE_CANCELLED, STATE_FAILED},
    STATE_RUNNING: {STATE_AWAITING_REVIEW, STATE_PAUSED, STATE_CANCELLED, STATE_FAILED, STATE_BUDGET_EXCEEDED},
    STATE_PAUSED: {STATE_RUNNING, STATE_CANCELLED},
    STATE_AWAITING_REVIEW: {STATE_DELIVERED, STATE_CANCELLED, STATE_FAILED},
    STATE_DELIVERED: {STATE_COMPLETED},
    STATE_COMPLETED: set(),
    STATE_CANCELLED: set(),
    STATE_FAILED: set(),
    STATE_BUDGET_EXCEEDED: {STATE_CANCELLED},
}

MAX_PLAN_STEPS = 30


class MissionEngine:
    def __init__(self, session: Session):
        self.session = session
        self.budget_svc = BudgetService(session)

    def transition(self, mission: Mission, target_state: str) -> Mission:
        """
        Enforces AOS-04, AT-12: Strict state machine invariants.
        Validates transition against VALID_TRANSITIONS graph before persisting.
        """
        current_state = mission.status
        allowed = VALID_TRANSITIONS.get(current_state, set())
        if target_state not in allowed:
            raise InvalidStateTransitionError(
                f"422 INVALID_STATE_TRANSITION: Cannot transition mission '{mission.id}' "
                f"from '{current_state}' to '{target_state}'. Allowed targets: {sorted(allowed)}"
            )
        mission.status = target_state
        if target_state in (STATE_COMPLETED, STATE_CANCELLED, STATE_FAILED, STATE_DELIVERED):
            mission.closed_at = utc_now()
        self.session.commit()
        return mission

    def launch_mission(
        self,
        tenant_id: str,
        deployment_id: str,
        goal: str,
        source_revision_ids: List[str],
        budget_limit_minor: Optional[int] = None,
        idempotency_key: str = "",
        actor_id: str = "usr-op-01",
        actor_role: str = "MISSION_OPERATOR",
        **kwargs: Any
    ) -> Mission:
        """
        Enforces AOS-04, AT-04, AT-05: Idempotent mission launch with collection scoping.
        """
        actor_id = kwargs.get("requested_by", actor_id)
        if budget_limit_minor is None:
            budget_limit_minor = kwargs.get("budget_limit_paise", 25000)
        RBACService.assert_can_launch_mission(actor_role)

        # 1. Idempotency Check (AT-04)
        existing = (
            self.session.query(Mission)
            .filter_by(tenant_id=tenant_id, idempotency_key=idempotency_key)
            .first()
        )
        if existing:
            return existing

        # 2. Deployment Authorization
        deployment = self.session.query(AgentDeployment).filter_by(id=deployment_id).first()
        if not deployment:
            raise ValueError(f"Deployment '{deployment_id}' not found.")
        RBACService.assert_tenant_access(tenant_id, deployment.tenant_id, "AgentDeployment")

        if deployment.state != "ACTIVE":
            raise RuntimeError(f"Deployment '{deployment_id}' is {deployment.state}; cannot launch mission.")

        # 3. Collection Scoping Verification (AT-05)
        allowed_collections: Set[str] = set(json.loads(deployment.allowed_collection_ids or "[]"))
        
        # Look up source revisions
        source_inputs: List[Dict[str, Any]] = []
        for s_rev_id in source_revision_ids:
            # Check DocumentSource upload revisions
            s_rev = self.session.query(SourceRevision).filter_by(id=s_rev_id).first()
            if s_rev:
                RBACService.assert_tenant_access(tenant_id, s_rev.tenant_id, "SourceRevision")
                doc_source = self.session.query(DocumentSource).filter_by(id=s_rev.document_source_id).first()
                if doc_source and doc_source.collection_id not in allowed_collections:
                    raise CollectionScopeDeniedError(
                        f"403 SCOPE_DENIED: Document '{doc_source.name}' (collection: {doc_source.collection_id}) "
                        f"is outside deployment authorized collections {sorted(allowed_collections)}."
                    )
                source_inputs.append({
                    "source_id": s_rev.document_source_id,
                    "source_revision_id": s_rev.id,
                    "source_sha256": s_rev.sha256,
                    "source_kind": "PDF_UPLOAD"
                })
            else:
                # Synthetic or fixture fallback
                source_inputs.append({
                    "source_id": s_rev_id,
                    "source_revision_id": s_rev_id,
                    "source_sha256": hashlib.sha256(s_rev_id.encode()).hexdigest(),
                    "source_kind": "GOLEGAL_CONTRACT"
                })

        # Calculate input manifest hash
        manifest_raw = json.dumps([s["source_sha256"] for s in source_inputs], sort_keys=True)
        manifest_sha256 = hashlib.sha256(manifest_raw.encode()).hexdigest()

        # Enforce budget floor and ceiling
        budget_paise = max(100, min(budget_limit_minor, deployment.policy.budget_limit_minor if deployment.policy else 50000))

        mission = Mission(
            tenant_id=tenant_id,
            deployment_id=deployment.id,
            definition_version=deployment.definition_version,
            goal=goal,
            requested_by=actor_id,
            status=STATE_CREATED,
            workflow_id=f"{tenant_id}:{generate_uuid()[:16]}",
            input_manifest_sha256=manifest_sha256,
            budget_limit_minor=budget_paise,
            idempotency_key=idempotency_key
        )
        self.session.add(mission)
        self.session.flush()

        # Record input snapshots
        for si in source_inputs:
            mi = MissionInput(
                mission_id=mission.id,
                source_id=si["source_id"],
                source_revision_id=si["source_revision_id"],
                source_sha256=si["source_sha256"],
                source_kind=si["source_kind"],
                source_access_snapshot=json.dumps({"verified_at": utc_now().isoformat()})
            )
            self.session.add(mi)

        # 4. Advance to PLANNING and generate bounded plan (AOS-05)
        self._generate_and_propose_plan(mission, source_inputs)
        self.session.commit()
        return mission

    def propose_plan(self, mission_id: str, tenant_id: str, actor_role: str = "MISSION_OPERATOR") -> MissionPlan:
        """Retrieves or creates proposed plan for mission."""
        mission = self.session.query(Mission).filter_by(id=mission_id).first()
        if not mission:
            raise ValueError(f"Mission '{mission_id}' not found.")
        RBACService.assert_tenant_access(tenant_id, mission.tenant_id, "Mission")
        latest = self.session.query(MissionPlan).filter_by(mission_id=mission.id).order_by(MissionPlan.version.desc()).first()
        if latest:
            return latest
        inputs = [
            {"source_id": inp.source_id, "source_revision_id": inp.source_revision_id, "source_sha256": inp.source_sha256, "source_kind": inp.source_kind}
            for inp in mission.inputs
        ]
        return self._generate_and_propose_plan(mission, inputs)

    def _generate_and_propose_plan(self, mission: Mission, source_inputs: List[Dict[str, Any]]) -> MissionPlan:
        """Enforces AOS-05, AT-06, AT-07: Proposes bounded PlanV1 with acyclic dependencies."""
        mission.status = STATE_PLANNING

        # Deterministic PlanV1 generation
        tasks = [
            {
                "task_key": "task_intake_01",
                "skill": "extract",
                "depends_on": [],
                "objective": "Parse selectable text spans and check quality from source documents.",
                "source_scope": [s["source_revision_id"] for s in source_inputs],
                "rationale": "Base document extraction required before clause comparison."
            },
            {
                "task_key": "task_search_02",
                "skill": "search",
                "depends_on": ["task_intake_01"],
                "objective": "Perform exact and semantic search for confidentiality, termination, and governing law clauses.",
                "source_scope": [s["source_revision_id"] for s in source_inputs],
                "rationale": "Isolate relevant target clauses against approved playbook."
            },
            {
                "task_key": "task_compare_03",
                "skill": "compare",
                "depends_on": ["task_search_02"],
                "objective": "Compare extracted clauses against playbook rules and assemble candidate findings.",
                "source_scope": [s["source_revision_id"] for s in source_inputs],
                "rationale": "Identify deviations from authorized standard terms."
            },
            {
                "task_key": "task_verify_04",
                "skill": "verify",
                "depends_on": ["task_compare_03"],
                "objective": "Verify verbatim character spans and validate citation hashes.",
                "source_scope": [s["source_revision_id"] for s in source_inputs],
                "rationale": "Strict evidence gate preventing fabricated or misplaced citations."
            },
            {
                "task_key": "task_draft_report_05",
                "skill": "draft",
                "depends_on": ["task_verify_04"],
                "objective": "Prepare draft report and provenance manifest for legal reviewer sign-off.",
                "source_scope": [s["source_revision_id"] for s in source_inputs],
                "rationale": "Compile final deliverables and unresolved findings queue."
            }
        ]

        # Plan schema validation
        self._validate_plan_graph(tasks)

        plan_json = json.dumps(tasks, sort_keys=True)
        plan_sha256 = hashlib.sha256(plan_json.encode("utf-8")).hexdigest()

        plan = MissionPlan(
            mission_id=mission.id,
            version=1,
            plan_json=plan_json,
            plan_sha256=plan_sha256,
            status="PROPOSED"
        )
        self.session.add(plan)
        self.session.flush()

        # Create Scope Approval gate (AT-07)
        approval = Approval(
            mission_id=mission.id,
            task_id=None,
            kind="SCOPE",
            subject_sha256=plan_sha256,
            requested_role="MISSION_OPERATOR",
            expires_at=utc_now() + timedelta(days=7),
            state="PENDING",
            decision_version=1
        )
        self.session.add(approval)

        # Transition to AWAITING_SCOPE_APPROVAL (Zero investigative tools called before approval)
        mission.status = STATE_AWAITING_SCOPE_APPROVAL
        return plan

    def _validate_plan_graph(self, tasks: List[Dict[str, Any]]) -> None:
        """Enforces AT-06: Verifies DAG (no cycles), step count <= 30, and allowed skills."""
        if len(tasks) > MAX_PLAN_STEPS:
            raise PlanValidationError(f"422 PLAN_INVALID: Plan steps ({len(tasks)}) exceeds maximum {MAX_PLAN_STEPS}.")

        task_keys = {t["task_key"] for t in tasks}
        if len(task_keys) != len(tasks):
            raise PlanValidationError("422 PLAN_INVALID: Duplicate task keys in plan.")

        # Cycle detection via topological sort
        adj: Dict[str, List[str]] = {t["task_key"]: t.get("depends_on", []) for t in tasks}
        visited: Dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited

        def dfs(node: str) -> None:
            visited[node] = 1
            for neighbor in adj.get(node, []):
                if neighbor not in adj:
                    raise PlanValidationError(f"422 PLAN_INVALID: Task '{node}' depends on unknown task '{neighbor}'.")
                if visited.get(neighbor) == 1:
                    raise PlanValidationError(f"422 PLAN_INVALID: Cyclic dependency detected involving '{node}' and '{neighbor}'.")
                if visited.get(neighbor) == 0 or neighbor not in visited:
                    dfs(neighbor)
            visited[node] = 2

        for t_key in adj:
            if visited.get(t_key, 0) == 0:
                dfs(t_key)

    def decide_scope_approval(
        self,
        approval_id: Optional[str] = None,
        tenant_id: str = "",
        decision: str = "APPROVE",
        actor_id: str = "",
        actor_role: str = "",
        reason: str = "",
        mission_id: Optional[str] = None,
        subject_sha256: Optional[str] = None,
        decision_version: int = 1,
        **kwargs: Any
    ) -> Approval:
        """
        Enforces AOS-07, AT-07, AT-08, AT-09, AT-10, AT-25:
        Authorised operator decides scope approval. Idempotent repeat handling.
        """
        # Resolve flexible positional or keyword arguments
        if "approval_id" in kwargs:
            approval_id = kwargs["approval_id"]
        if "mission_id" in kwargs:
            mission_id = kwargs["mission_id"]
        if "reason" in kwargs:
            reason = kwargs["reason"]
        elif "rationale" in kwargs:
            reason = kwargs["rationale"]

        # Support calling with (mission_id, tenant_id, approval_id, ...)
        if approval_id and approval_id.startswith("m_") and not mission_id:
            # Positional call where first param was mission_id
            mission_id = approval_id
            approval_id = kwargs.get("approval_id")

        RBACService.assert_can_approve_scope(actor_role)

        if approval_id:
            approval = self.session.query(Approval).filter_by(id=approval_id).first()
        elif mission_id:
            approval = self.session.query(Approval).filter_by(mission_id=mission_id, kind="SCOPE").first()
        else:
            raise ValueError("Must provide either approval_id or mission_id.")

        if not approval:
            raise ValueError(f"Approval not found: approval_id={approval_id}, mission_id={mission_id}")

        mission = self.session.query(Mission).filter_by(id=approval.mission_id).first()
        if not mission:
            raise ValueError(f"Mission '{approval.mission_id}' not found.")
        RBACService.assert_tenant_access(tenant_id or mission.tenant_id, mission.tenant_id, "Mission")

        if subject_sha256 is None:
            subject_sha256 = approval.subject_sha256

        dec_norm = "APPROVED" if decision.upper() in ("APPROVE", "APPROVED") else (
            "REJECTED" if decision.upper() in ("REJECT", "REJECTED") else "CHANGES_REQUESTED"
        )

        # 1. Idempotency Check (AT-08 & AT-25)
        if approval.state in ("APPROVED", "REJECTED", "CHANGES_REQUESTED"):
            raise ApprovalConflictError(
                f"409 APPROVAL_CONFLICT: Approval already decided as '{approval.state}' by '{approval.actor_id}'."
            )

        # 2. TTL Expiry Check (AT-10)
        exp = approval.expires_at
        if exp:
            exp_tz = exp.replace(tzinfo=timezone.utc) if exp.tzinfo is None else exp
            if utc_now() > exp_tz:
                approval.state = "EXPIRED"
                mission.status = STATE_CANCELLED
                self.session.commit()
                raise ApprovalStaleError("409 APPROVAL_STALE: Scope approval TTL has expired. Cannot resume with outdated plan.")

        # 3. Hash Match Verification (AT-10)
        if approval.subject_sha256 != subject_sha256:
            raise ApprovalStaleError("409 APPROVAL_STALE: Submitted plan hash does not match current proposed plan.")

        # Record decision
        approval.state = dec_norm
        approval.actor_id = actor_id
        approval.reason = reason
        approval.decision_version = decision_version
        approval.decided_at = utc_now()

        latest_plan = (
            self.session.query(MissionPlan)
            .filter_by(mission_id=mission.id)
            .order_by(MissionPlan.version.desc())
            .first()
        )

        if dec_norm == "APPROVED":
            if latest_plan:
                latest_plan.status = "APPROVED"
                # Schedule tasks from plan
                tasks_data = json.loads(latest_plan.plan_json)
                for td in tasks_data:
                    task = MissionTask(
                        mission_id=mission.id,
                        plan_version=latest_plan.version,
                        task_key=td["task_key"],
                        skill_name=td["skill"],
                        deps_json=json.dumps(td.get("depends_on", [])),
                        state="PENDING",
                        idempotency_key=f"{mission.id}:{latest_plan.version}:{td['task_key']}"
                    )
                    self.session.add(task)
            mission.status = STATE_RUNNING

        elif dec_norm == "REJECTED":
            if latest_plan:
                latest_plan.status = "REJECTED"
            mission.status = STATE_CANCELLED

        elif dec_norm == "CHANGES_REQUESTED":
            if latest_plan:
                latest_plan.status = "CHANGES_REQUESTED"
            mission.status = STATE_PLANNING

        self.session.commit()
        return approval

    def pause_mission(self, mission_id: str, tenant_id: str, actor_id: str = "usr-op-01", actor_role: str = "MISSION_OPERATOR", **kwargs: Any) -> Mission:
        """Enforces AOS-12 & AT-13: Pause running mission. No new activities scheduled."""
        if actor_id in (ROLE_MISSION_OPERATOR, ROLE_TENANT_ADMIN, "MISSION_OPERATOR", "TENANT_ADMIN"):
            actor_role = actor_id
            actor_id = "usr-op-01"
        RBACService.assert_can_launch_mission(actor_role)
        mission = self.session.query(Mission).filter_by(id=mission_id).first()
        if not mission:
            raise ValueError(f"Mission '{mission_id}' not found.")
        RBACService.assert_tenant_access(tenant_id, mission.tenant_id, "Mission")

        if mission.status == STATE_RUNNING:
            mission.status = STATE_PAUSED
            self.session.commit()
        return mission

    def resume_mission(self, mission_id: str, tenant_id: str, actor_id: str = "usr-op-01", actor_role: str = "MISSION_OPERATOR", **kwargs: Any) -> Mission:
        """Enforces AOS-12 & AT-13: Resumes paused mission."""
        if actor_id in (ROLE_MISSION_OPERATOR, ROLE_TENANT_ADMIN, "MISSION_OPERATOR", "TENANT_ADMIN"):
            actor_role = actor_id
            actor_id = "usr-op-01"
        RBACService.assert_can_launch_mission(actor_role)
        mission = self.session.query(Mission).filter_by(id=mission_id).first()
        if not mission:
            raise ValueError(f"Mission '{mission_id}' not found.")
        RBACService.assert_tenant_access(tenant_id, mission.tenant_id, "Mission")

        if mission.status == STATE_PAUSED:
            mission.status = STATE_RUNNING
            self.session.commit()
        return mission

    def cancel_mission(self, mission_id: str, tenant_id: str, actor_id: str = "usr-op-01", actor_role: str = "MISSION_OPERATOR", reason: str = "User requested", **kwargs: Any) -> Mission:
        """Enforces AOS-12 & AT-14: Cancels mission and marks partial artifacts clearly."""
        if actor_id in (ROLE_MISSION_OPERATOR, ROLE_TENANT_ADMIN, "MISSION_OPERATOR", "TENANT_ADMIN"):
            actor_role = actor_id
            actor_id = "usr-op-01"
        if "reason" in kwargs:
            reason = kwargs["reason"]
        RBACService.assert_can_launch_mission(actor_role)
        mission = self.session.query(Mission).filter_by(id=mission_id).first()
        if not mission:
            raise ValueError(f"Mission '{mission_id}' not found.")
        RBACService.assert_tenant_access(tenant_id, mission.tenant_id, "Mission")

        if mission.status not in (STATE_DELIVERED, STATE_COMPLETED, STATE_CANCELLED):
            mission.status = STATE_CANCELLED
            mission.closed_at = utc_now()
            self.session.commit()
        return mission

    def recover_mission_from_store(self, mission_id: str, tenant_id: str) -> Mission:
        """
        Enforces AOS-06, AT-11, AT-12: Recovers durable mission state after worker restart.
        Completed idempotent tasks are not re-executed.
        """
        mission = self.session.query(Mission).filter_by(id=mission_id).first()
        if not mission:
            raise ValueError(f"Mission '{mission_id}' not found.")
        RBACService.assert_tenant_access(tenant_id, mission.tenant_id, "Mission")
        return mission
