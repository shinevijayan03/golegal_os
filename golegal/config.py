"""
GoLegal vNext Central Configuration & Tunables.
Sourced from environment with safe local defaults.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass(frozen=True)
class Settings:
    # Runtime & Branding
    app_name: str = "GoLegal OS"
    tagline: str = "The agentic operating system for legal work."
    environment: str = os.getenv("GOLEGAL_ENV", "development")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./golegal_vnext.db")
    base_url: str = os.getenv("GOLEGAL_BASE_URL", "http://localhost:8501")

    # Security & Capability Secrets
    cbac_secret: str = os.getenv("GOLEGAL_CBAC_SECRET", "dev-vnext-cbac-secret-rotate-in-production")
    webhook_secret: str = os.getenv("GOLEGAL_WEBHOOK_SECRET", "test-webhook-hmac-secret-key-32bytes")
    webhook_replay_window_seconds: int = 300  # 5-minute replay window

    # Performance & File Limits (NFR)
    max_attachment_size_bytes: int = 10 * 1024 * 1024  # 10 MiB limit
    max_attachment_pages: int = 50                     # 50 page threshold
    form_read_p95_target_ms: float = 400.0             # 400 ms SLA
    pdf_render_p95_target_s: float = 10.0              # 10.0 s SLA
    camera_pipeline_sla_s: float = 50.0                # 50.0 s SLA

    # AI & Privacy Boundaries
    third_party_ai_default_enabled: bool = False       # Default-disabled (AT-13)
    draft_retention_days: int = 27                     # Purge unconsented drafts after 27 days

    # Statutory Identity & Support
    company_name: str = "AAS Innovation Labs Pvt. Ltd."
    company_gstin: str = os.getenv("GOLEGAL_GSTIN", "29AAACA0000A1Z5")
    company_state: str = "Karnataka"
    support_email: str = "support@golegalos.in"


settings = Settings()
