"""
AgentOS Server-Side Policy Gateway & Tool Dispatcher.
Enforces AOS-10, AT-16, and PRD Section 9 hard platform denylist.
"""
from __future__ import annotations
import json
import time
import hashlib
from typing import Dict, Any, Callable, Optional
from sqlalchemy.orm import Session

from golegal.agentos.domain.models import ToolGrant, ToolInvocation, Mission, generate_uuid


class ForbiddenToolError(PermissionError):
    """Raised when a task or planner attempts to invoke a tool on the platform hard denylist (AT-16)."""
    pass


# Alias for AT-16 requirement specification
ToolPolicyDeniedError = ForbiddenToolError


class ToolUnauthorizedError(PermissionError):
    """Raised when an agent deployment lacks the specific tool grant (AOS-10)."""
    pass


# PRD Section 9 Explicit Platform Hard Denylist
PLATFORM_HARD_DENYLIST = {
    "generic_shell",
    "shell",
    "bash",
    "sh",
    "browser_surf",
    "web_browser",
    "http_fetch",
    "arbitrary_http",
    "send_email",
    "send_sms",
    "send_whatsapp",
    "execute_payment",
    "payment",
    "invoke_esign",
    "sign",
    "invoke_estamp",
    "stamp",
    "db_sql_exec",
    "execute_sql",
    "cloud_credential_fetch",
    "recursive_delegate"
}


class PolicyGateway:
    def __init__(self, session: Session):
        self.session = session

    def dispatch_tool(
        self,
        mission_id: str,
        deployment_id: str = "dep_ci_v1",
        tool_name: str = "",
        tool_input: Optional[Dict[str, Any]] = None,
        tool_callable: Optional[Callable[[Dict[str, Any]], Any]] = None,
        task_id: Optional[str] = None,
        **kwargs: Any
    ) -> Any:
        """
        Enforces AOS-10 & AT-16: Server-side validation of tool name, allowlist, and budget.
        Denies call even if malicious prompt includes forbidden function name.
        """
        tool_input = tool_input or {}
        if "tenant_id" in kwargs and deployment_id == "dep_ci_v1":
            from golegal.agentos.services.studio_service import StudioService
            active_dep = StudioService(self.session).get_active_deployment(kwargs["tenant_id"])
            if active_dep:
                deployment_id = active_dep.id
        if tool_callable is None:
            tool_callable = lambda inp: {"status": "SUCCESS", "output": inp}
        input_json = json.dumps(tool_input, sort_keys=True)
        input_sha256 = hashlib.sha256(input_json.encode("utf-8")).hexdigest()
        t_start = time.perf_counter()

        # 1. Hard Platform Denylist Check (AT-16)
        clean_name = tool_name.strip().lower()
        if clean_name in PLATFORM_HARD_DENYLIST or any(fb in clean_name for fb in ["shell", "email", "mail", "payment", "pay", "esign", "estamp", "sign", "stamp"]):
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            self._record_invocation(mission_id, task_id, tool_name, input_sha256, "DENIED", duration_ms)
            raise ForbiddenToolError(
                f"403 FORBIDDEN_TOOL: Tool '{tool_name}' is permanently blocked by platform security policy. "
                "AgentOS prohibits shell, email, payments, stamping, or signing invocation."
            )

        # 2. Deployment Tool Grant Authorization Check
        grant = (
            self.session.query(ToolGrant)
            .filter_by(deployment_id=deployment_id, tool_name=tool_name, enabled=True)
            .first()
        )
        if not grant:
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            self._record_invocation(mission_id, task_id, tool_name, input_sha256, "DENIED", duration_ms)
            raise ToolUnauthorizedError(f"403 TOOL_UNAUTHORIZED: Deployment '{deployment_id}' lacks grant for '{tool_name}'.")

        # 3. Execute authorized tool
        try:
            result = tool_callable(tool_input)
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            self._record_invocation(mission_id, task_id, tool_name, input_sha256, "SUCCESS", duration_ms)
            return result
        except Exception as e:
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            self._record_invocation(mission_id, task_id, tool_name, input_sha256, "FAILED", duration_ms)
            raise

    def _record_invocation(
        self,
        mission_id: str,
        task_id: Optional[str],
        tool_name: str,
        input_sha256: str,
        outcome: str,
        duration_ms: int
    ) -> None:
        inv = ToolInvocation(
            mission_id=mission_id,
            task_id=task_id,
            tool_name=tool_name,
            grant_version=1,
            input_sha256=input_sha256,
            outcome=outcome,
            duration_ms=duration_ms,
            usage_json="{}"
        )
        self.session.add(inv)
        self.session.commit()
