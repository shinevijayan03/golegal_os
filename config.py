"""
GoLegal central configuration.

Every tunable, secret, and magic number lives here and is sourced from the
environment so that nothing security-sensitive is hard-coded in the codebase
(OWASP category 21 - Source Code Security).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # ---- Runtime -----------------------------------------------------------
    app_name: str = "GoLegal OS"
    tagline: str = "The agentic operating system for legal work."
    environment: str = os.getenv("GOLEGAL_ENV", "development")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./golegal.db")
    base_url: str = os.getenv("GOLEGAL_BASE_URL", "http://localhost:8501")

    # ---- Security ----------------------------------------------------------
    cbac_secret: str = os.getenv("GOLEGAL_CBAC_SECRET", "dev-only-cbac-secret-rotate-me")
    dsc_seal_secret: str = os.getenv("GOLEGAL_DSC_SECRET", "dev-only-dsc-seal-secret-rotate-me")
    password_iterations: int = _env_int("GOLEGAL_PBKDF2_ITERATIONS", 120_000)
    signing_link_ttl_days: int = _env_int("GOLEGAL_SIGNING_LINK_TTL_DAYS", 7)
    otp_ttl_seconds: int = _env_int("GOLEGAL_OTP_TTL_SECONDS", 300)
    otp_max_attempts: int = _env_int("GOLEGAL_OTP_MAX_ATTEMPTS", 5)
    otp_lockout_seconds: int = _env_int("GOLEGAL_OTP_LOCKOUT_SECONDS", 900)
    mock_otp: str = os.getenv("GOLEGAL_MOCK_OTP", "123456")
    mock_gateways: bool = _env_bool("GOLEGAL_MOCK_GATEWAYS", True)

    # ---- Pricing (server-side; never trusted from the client) --------------
    platform_fee: float = _env_float("GOLEGAL_PLATFORM_FEE", 299.0)
    gst_rate: float = _env_float("GOLEGAL_GST_RATE", 0.18)
    low_balance_threshold: float = _env_float("GOLEGAL_LOW_BALANCE_THRESHOLD", 10_000.0)
    initial_prepaid_balance: float = _env_float("GOLEGAL_INITIAL_PREPAID_BALANCE", 50_000.0)
    draft_pruning_days: int = _env_int("GOLEGAL_DRAFT_PRUNING_DAYS", 27)
    agreement_retain_days: int = _env_int("GOLEGAL_AGREEMENT_RETAIN_DAYS", 2920)

    # ---- AI / Agent layer --------------------------------------------------
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    llm_model: str = os.getenv("GOLEGAL_LLM_MODEL", "claude-opus-5")
    llm_effort: str = os.getenv("GOLEGAL_LLM_EFFORT", "medium")
    llm_max_tokens: int = _env_int("GOLEGAL_LLM_MAX_TOKENS", 4096)
    llm_enabled: bool = _env_bool("GOLEGAL_LLM_ENABLED", True)
    agent_max_tool_calls: int = _env_int("GOLEGAL_AGENT_MAX_TOOL_CALLS", 12)

    # ---- Company / statutory identity --------------------------------------
    company_name: str = "AAS Innovation Labs Pvt. Ltd."
    company_gstin: str = os.getenv("GOLEGAL_GSTIN", "29AAACA0000A1Z5")
    company_state: str = "Karnataka"
    support_email: str = "support@golegal.in"

    demo_accounts: tuple = field(default_factory=lambda: (
        {"id": "usr-tenant-001", "full_name": "Mayank Tripathi", "email": "mayank.tripathi@example.com",
         "phone": "9876543211", "user_type": "Single_User", "address": "Flat 202, Green Glen, Bellandur, Bangalore"},
        {"id": "usr-owner-001", "full_name": "Ramakiran Reddy", "email": "ramakiran.reddy@example.com",
         "phone": "9876543210", "user_type": "Single_User", "address": "101, Palm Meadows, Mahadevapura, Bangalore"},
        {"id": "usr-admin-001", "full_name": "GoLegal OS Operations", "email": "admin@golegal.in",
         "phone": "9876543299", "user_type": "Admin", "address": "GoLegal HQ, Bangalore"},
    ))

    @property
    def llm_available(self) -> bool:
        """True when a real model can be called (key present and feature enabled)."""
        return bool(self.llm_enabled and self.anthropic_api_key)


settings = Settings()
