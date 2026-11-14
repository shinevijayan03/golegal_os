"""
AgentOS RBAC & Multi-Tenant Partitioning Service.
Enforces AOS-01, AT-01, AT-09, and PRD Section 2 human role permissions.
"""
from __future__ import annotations
from typing import Set, Dict, Any, Optional


class TenantAccessDeniedError(PermissionError):
    """Raised when actor attempts to access an entity belonging to a different tenant (AT-01)."""
    pass


class RolePermissionDeniedError(PermissionError):
    """Raised when actor's role lacks the statutory permission to perform an action (AT-09)."""
    pass


# Canonical PRD Section 2 Human Roles
ROLE_TENANT_ADMIN = "TENANT_ADMIN"
ROLE_AGENT_BUILDER = "AGENT_BUILDER"
ROLE_MISSION_OPERATOR = "MISSION_OPERATOR"
ROLE_LEGAL_REVIEWER = "LEGAL_REVIEWER"
ROLE_READ_ONLY_AUDITOR = "READ_ONLY_AUDITOR"
ROLE_PLATFORM_OPERATOR = "PLATFORM_OPERATOR"

# Backward compatibility map for legacy tenant personas
LEGACY_ROLE_MAP = {
    "owner": ROLE_TENANT_ADMIN,
    "legal_admin": ROLE_TENANT_ADMIN,
    "editor": ROLE_AGENT_BUILDER,
    "approver": ROLE_LEGAL_REVIEWER,
    "operator": ROLE_MISSION_OPERATOR,
    "counterparty_signer": ROLE_READ_ONLY_AUDITOR,
    "auditor": ROLE_READ_ONLY_AUDITOR,
}


def normalize_role(role: str) -> str:
    r = role.strip().upper()
    if r in (
        ROLE_TENANT_ADMIN, ROLE_AGENT_BUILDER, ROLE_MISSION_OPERATOR,
        ROLE_LEGAL_REVIEWER, ROLE_READ_ONLY_AUDITOR, ROLE_PLATFORM_OPERATOR
    ):
        return r
    return LEGACY_ROLE_MAP.get(role.strip().lower(), ROLE_READ_ONLY_AUDITOR)


class RBACService:
    @staticmethod
    def assert_tenant_access(actor_tenant_id: str, target_tenant_id: str, resource_name: str = "Resource") -> None:
        """Enforces 100% strict tenant boundary (AOS-01 & AT-01). Zero cross-tenant metadata leak."""
        if actor_tenant_id != target_tenant_id:
            raise TenantAccessDeniedError(f"403 Forbidden: Cross-tenant access denied to {resource_name}.")

    @staticmethod
    def assert_role(actor_role: str, allowed_roles: Set[str], action: str = "Action") -> None:
        """Enforces role-based permissions (AT-09). Models or unauthorized personas are never approvers."""
        norm = normalize_role(actor_role)
        if norm not in allowed_roles:
            raise RolePermissionDeniedError(
                f"403 Forbidden: Role '{actor_role}' lacks authority to perform '{action}'. Required: {sorted(allowed_roles)}"
            )

    @classmethod
    def assert_can_configure_agent(cls, actor_role: str) -> None:
        cls.assert_role(actor_role, {ROLE_AGENT_BUILDER, ROLE_TENANT_ADMIN}, "Configure Agent Definition")

    @classmethod
    def assert_can_deploy_agent(cls, actor_role: str) -> None:
        cls.assert_role(actor_role, {ROLE_TENANT_ADMIN}, "Approve Agent Deployment")

    @classmethod
    def assert_can_launch_mission(cls, actor_role: str) -> None:
        cls.assert_role(actor_role, {ROLE_MISSION_OPERATOR, ROLE_TENANT_ADMIN}, "Launch Mission")

    @classmethod
    def assert_can_approve_scope(cls, actor_role: str) -> None:
        cls.assert_role(actor_role, {ROLE_MISSION_OPERATOR, ROLE_TENANT_ADMIN, ROLE_LEGAL_REVIEWER}, "Approve Mission Scope Plan")

    @classmethod
    def assert_can_review_findings(cls, actor_role: str) -> None:
        cls.assert_role(actor_role, {ROLE_LEGAL_REVIEWER, ROLE_TENANT_ADMIN}, "Disposition Finding / Approve Report")
