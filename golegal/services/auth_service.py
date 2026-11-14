"""
Tenant-Scoped RBAC & Membership Authentication Service.
Enforces AT-01: Zero cross-tenant data leakage.
"""
from __future__ import annotations
from typing import Optional, List
from sqlalchemy.orm import Session

from golegal.domain.models import Organisation, Membership


class TenantIsolationError(PermissionError):
    """Raised when an actor attempts cross-tenant access (403/404)."""
    pass


class AuthService:
    def __init__(self, session: Session):
        self.session = session

    def create_organisation(self, name: str, org_id: Optional[str] = None) -> Organisation:
        org = Organisation(id=org_id, name=name) if org_id else Organisation(name=name)
        self.session.add(org)
        self.session.flush()
        return org

    def add_membership(self, org_id: str, user_id: str, role: str, email: Optional[str] = None) -> Membership:
        self.assert_org_exists(org_id)
        m = Membership(organisation_id=org_id, user_id=user_id, role=role, user_email=email)
        self.session.add(m)
        self.session.flush()
        return m

    def get_membership(self, org_id: str, user_id: str) -> Optional[Membership]:
        return self.session.query(Membership).filter_by(organisation_id=org_id, user_id=user_id).first()

    def assert_org_exists(self, org_id: str) -> Organisation:
        org = self.session.query(Organisation).filter_by(id=org_id).first()
        if not org:
            raise TenantIsolationError(f"404 NOT_FOUND: Organisation '{org_id}' does not exist.")
        return org

    def verify_tenant_access(self, org_id: str, actor_id: str, required_roles: Optional[List[str]] = None) -> Membership:
        """Enforces AT-01: Actor must have active membership in the target organisation."""
        m = self.get_membership(org_id, actor_id)
        if not m:
            raise TenantIsolationError(
                f"403 TENANT_ACCESS_DENIED: Actor '{actor_id}' is not a member of organisation '{org_id}'."
            )
        if required_roles and m.role not in required_roles:
            raise TenantIsolationError(
                f"403 INSUFFICIENT_ROLE: Actor role '{m.role}' cannot perform this action (requires {required_roles})."
            )
        return m
