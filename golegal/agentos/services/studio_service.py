"""
Agent Studio Service: Pack Catalog, JSON Schema Validation, Versioning & Deployments.
Enforces AOS-02, AOS-03, AT-02, AT-03.
"""
from __future__ import annotations
import json
import hashlib
from typing import Dict, Any, List, Optional
import jsonschema
from sqlalchemy.orm import Session

from golegal.agentos.domain.models import (
    AgentPack, AgentDefinition, AgentDeployment, AgentRuntimePolicy, ToolGrant, generate_uuid
)
from golegal.agentos.services.rbac_service import RBACService, normalize_role


class ConfigurationValidationError(ValueError):
    """Raised when an agent draft configuration violates JSON Schema, pack capabilities or budget rules (AT-02)."""
    pass


class ImmutableDeploymentError(RuntimeError):
    """Raised when an attempt is made to mutate an already-published deployment or version (AT-03)."""
    pass


# Default Canonical Pack: Contract Intelligence v1
DEFAULT_PACK_KEY = "contract_intelligence_v1"
DEFAULT_PACK_VERSION = "1.0.0"

PACK_SKILLS_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["allowed_skills", "max_files", "max_tool_calls", "budget_ceiling_minor"],
    "additionalProperties": False,
    "properties": {
        "allowed_skills": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["search", "extract", "classify", "compare", "verify", "draft"]
            },
            "minItems": 1
        },
        "max_files": {"type": "integer", "minimum": 1, "maximum": 50},
        "max_tool_calls": {"type": "integer", "minimum": 1, "maximum": 200},
        "max_steps": {"type": "integer", "minimum": 1, "maximum": 30},
        "budget_ceiling_minor": {"type": "integer", "minimum": 100, "maximum": 500000},  # Up to ₹5,000.00
        "allowed_playbooks": {
            "type": "array",
            "items": {"type": "string"}
        },
        "target_clause_categories": {
            "type": "array",
            "items": {"type": "string"}
        }
    }
}


class StudioService:
    def __init__(self, session: Session):
        self.session = session

    def seed_default_pack_if_missing(self) -> AgentPack:
        pack = (
            self.session.query(AgentPack)
            .filter_by(key=DEFAULT_PACK_KEY, pack_version=DEFAULT_PACK_VERSION)
            .first()
        )
        if not pack:
            pack = AgentPack(
                key=DEFAULT_PACK_KEY,
                pack_version=DEFAULT_PACK_VERSION,
                name="Contract Intelligence Agent Pack",
                description="Investigative contract intelligence agent pack for deviation discovery, clause comparison, and evidence collection.",
                skills_schema_json=json.dumps(PACK_SKILLS_SCHEMA),
                capabilities=json.dumps(["search", "extract", "classify", "compare", "verify", "draft"]),
                system_policy_version="2026-11-v1"
            )
            self.session.add(pack)
            self.session.commit()
        return pack

    def get_or_create_default_policy(self, tenant_id: str) -> AgentRuntimePolicy:
        policy = self.session.query(AgentRuntimePolicy).filter_by(tenant_id=tenant_id).first()
        if not policy:
            policy = AgentRuntimePolicy(
                tenant_id=tenant_id,
                name="Standard Tenant Legal Ops Policy",
                version=1,
                token_limit=200000,
                budget_limit_minor=50000,  # ₹500.00
                max_tool_calls=200,
                max_steps=30,
                max_document_count=50,
                max_document_size_mb=10,
                max_aggregate_pages=1000,
                max_run_age_days=30,
                allowed_providers=json.dumps(["local_gpu_rtx3060", "local_fixture"]),
                data_residency="IN"
            )
            self.session.add(policy)
            self.session.commit()
        return policy

    def validate_config(self, pack: AgentPack, config: Dict[str, Any]) -> None:
        """Enforces AOS-02 & AT-02: Strict JSON Schema validation. Rejects unknown skills or arbitrary URLs."""
        # 1. Prohibit arbitrary URLs or scripts inside config
        config_str = json.dumps(config)
        for forbidden in ["http://", "https://", "ftp://", "eval(", "exec(", "<script"]:
            if forbidden in config_str:
                raise ConfigurationValidationError(f"422 Unprocessable: Arbitrary URL or executable code '{forbidden}' is forbidden in agent configuration.")

        # 2. JSON Schema validation
        schema = json.loads(pack.skills_schema_json)
        try:
            jsonschema.validate(instance=config, schema=schema)
        except jsonschema.ValidationError as ve:
            raise ConfigurationValidationError(f"422 Unprocessable Schema: {ve.message}")

    def create_agent_definition(
        self,
        tenant_id: str,
        name: str,
        goal_template: str,
        config: Dict[str, Any],
        actor_id: str,
        actor_role: str,
        pack_key: str = DEFAULT_PACK_KEY,
        pack_version: str = DEFAULT_PACK_VERSION,
        family_id: Optional[str] = None
    ) -> AgentDefinition:
        """Creates draft agent definition (AOS-02)."""
        RBACService.assert_can_configure_agent(actor_role)
        pack = self.seed_default_pack_if_missing()

        # Validate configuration
        self.validate_config(pack, config)

        f_id = family_id or generate_uuid()
        config_json = json.dumps(config, sort_keys=True)
        content_hash = hashlib.sha256(config_json.encode("utf-8")).hexdigest()

        # Determine version number
        latest = (
            self.session.query(AgentDefinition)
            .filter_by(tenant_id=tenant_id, family_id=f_id)
            .order_by(AgentDefinition.version.desc())
            .first()
        )
        version = (latest.version + 1) if latest else 1

        definition = AgentDefinition(
            family_id=f_id,
            tenant_id=tenant_id,
            name=name,
            pack_key=pack.key,
            version=version,
            status="DRAFT",
            goal_template=goal_template,
            config_json=config_json,
            created_by=actor_id,
            content_sha256=content_hash
        )
        self.session.add(definition)
        self.session.commit()
        return definition

    def approve_deployment(
        self,
        tenant_id: str,
        definition_id: str,
        playbook_version_id: str,
        allowed_collection_ids: List[str],
        actor_id: str,
        actor_role: str,
        tool_grants: Optional[List[str]] = None
    ) -> AgentDeployment:
        """Enforces AOS-03 & AT-03: Tenant Admin reviews and approves immutable deployment."""
        RBACService.assert_can_deploy_agent(actor_role)

        definition = self.session.query(AgentDefinition).filter_by(id=definition_id).first()
        if not definition:
            raise ValueError(f"Definition '{definition_id}' not found.")
        RBACService.assert_tenant_access(tenant_id, definition.tenant_id, "AgentDefinition")

        # Mark definition as APPROVED
        definition.status = "APPROVED"

        policy = self.get_or_create_default_policy(tenant_id)
        grant_set_id = generate_uuid()

        deployment = AgentDeployment(
            tenant_id=tenant_id,
            definition_id=definition.id,
            definition_version=definition.version,
            playbook_version_id=playbook_version_id,
            allowed_collection_ids=json.dumps(allowed_collection_ids),
            tool_grant_set_id=grant_set_id,
            runtime_policy_id=policy.id,
            approved_by=actor_id,
            state="ACTIVE"
        )
        self.session.add(deployment)
        self.session.flush()

        # Seed permitted tool grants
        default_tools = tool_grants or [
            "contract.list_revisions",
            "contract.get_native_fields",
            "document.parse_pdf",
            "document.search_clauses",
            "playbook.list_rules",
            "playbook.compare",
            "evidence.verify_span",
            "report.prepare_draft",
            "human.request_review",
        ]

        for t_name in default_tools:
            side_effect = "CREATE_DRAFT" if t_name in ("playbook.compare", "report.prepare_draft", "human.request_review") else "READ"
            tg = ToolGrant(
                tenant_id=tenant_id,
                deployment_id=deployment.id,
                tool_name=t_name,
                allowed_scopes=json.dumps(allowed_collection_ids),
                side_effect_class=side_effect,
                enabled=True
            )
            self.session.add(tg)

        self.session.commit()
        return deployment

    def list_definitions(self, tenant_id: str) -> List[AgentDefinition]:
        """Lists all definitions for a specific tenant."""
        return (
            self.session.query(AgentDefinition)
            .filter_by(tenant_id=tenant_id)
            .order_by(AgentDefinition.created_at.desc())
            .all()
        )

    def get_pack(self, pack_key: str = DEFAULT_PACK_KEY) -> Optional[AgentPack]:
        """Retrieves registered agent pack by key."""
        return self.session.query(AgentPack).filter_by(key=pack_key).first()

    def register_pack(self, pack_name: str, version: str, manifest_json: Dict[str, Any]) -> AgentPack:
        """Enforces AT-02: Validates and registers an agent pack."""
        if not manifest_json.get("name") or not manifest_json.get("version") or not manifest_json.get("capabilities"):
            raise ValueError("Pack manifest must define name, version, and non-empty capabilities.")

        pack = AgentPack(
            key=pack_name,
            pack_version=version,
            name=manifest_json["name"],
            description=manifest_json.get("description", ""),
            skills_schema_json=json.dumps(manifest_json.get("skills_schema", PACK_SKILLS_SCHEMA)),
            capabilities=json.dumps(manifest_json["capabilities"]),
            system_policy_version="2026-11-v1"
        )
        self.session.add(pack)
        self.session.commit()
        return pack

    def get_active_deployment(self, tenant_id: str) -> Optional[AgentDeployment]:
        """Retrieves active deployment for tenant."""
        return (
            self.session.query(AgentDeployment)
            .filter_by(tenant_id=tenant_id, state="ACTIVE")
            .order_by(AgentDeployment.approved_at.desc())
            .first()
        )

    def create_definition(
        self,
        tenant_id: str,
        name: str,
        goal_template: str,
        author_role: str = "AGENT_BUILDER",
        skills: Optional[List[str]] = None,
        target_categories: Optional[List[str]] = None,
        actor_id: str = "usr-builder-01",
        family_id: Optional[str] = None
    ) -> AgentDefinition:
        """Convenience factory for agent definition."""
        allowed_skills = ["extract", "compare"]
        config = {
            "allowed_skills": allowed_skills,
            "max_files": 30,
            "max_tool_calls": 150,
            "max_steps": 25,
            "budget_ceiling_minor": 25000,
            "allowed_playbooks": ["playbook_nda_2026_11"],
            "target_clause_categories": target_categories or ["confidentiality_duration", "governing_law"]
        }
        return self.create_agent_definition(
            tenant_id=tenant_id,
            name=name,
            goal_template=goal_template,
            config=config,
            actor_id=actor_id,
            actor_role=author_role,
            family_id=family_id
        )

    def deploy_definition(
        self,
        tenant_id: str,
        definition_id: str,
        actor_role: str = "TENANT_ADMIN",
        actor_id: str = "usr-admin-01"
    ) -> AgentDeployment:
        """Convenience deployment trigger."""
        return self.approve_deployment(
            tenant_id=tenant_id,
            definition_id=definition_id,
            playbook_version_id="playbook_nda_2026_11",
            allowed_collection_ids=["col_supplier_ndas"],
            actor_id=actor_id,
            actor_role=actor_role
        )
