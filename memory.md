# GoLegal Application - Agent Context & Engineering Memory

```yaml
project: GoLegal Digital Contracting Web Application
jurisdiction: India (IT Act 2000 §§ 4, 5, 10A; Indian Evidence Act 1872 § 65B; Indian Stamp Act 1899)
stack:
  runtime: Python 3.12+ (.venv)
  frontend: Streamlit 1.63, streamlit-option-menu 0.4.0
  orm_db: SQLAlchemy 2.0+, SQLite (local golegal.db) / PostgreSQL 15+ compatible
  pdf_crypto: ReportLab 5.0+, SHA-256 digests, simulated PKCS#7 X.509 signature containers
  test_framework: Pytest 9.1+, pytest-cov, pytest-mock (71 tests, 96% coverage)
port: 8501
daemon_status: Stopped (Launch with: .\.venv\Scripts\streamlit.exe run app.py --server.port 8501 --server.headless true)
```

> [!IMPORTANT]
> **MANDATORY DIRECTIVE FOR INCOMING CODING AGENTS & HARNESSES**:
> The authoritative, exhaustive Master Product Requirements Document (PRD v1.0), Requirement Design Specification, and Software Architecture Baseline (SAD v0.3) is located in [`GoLegal_Master_PRD_Context_v2 .md`](./GoLegal_Master_PRD_Context_v2%20.md).
> **BEFORE STARTING ANY TASK, FEATURE WORK, OR CODEBASE MODIFICATION**, you MUST thoroughly review and deeply ingest `GoLegal_Master_PRD_Context_v2 .md` to maintain total alignment with the statutory boundaries, user workflows, 5-layer architecture, and legal compliance invariants.

---

## 1. Directory & Codebase File Map

```
golegal_app/
├── app.py                     # Main Streamlit router, navbar, theme styles, DB init
├── requirements.txt           # Production & testing dependency pin
├── golegal.db                 # SQLite 3NF database
├── domain/
│   ├── __init__.py            # Domain entity exports
│   └── models.py              # 3NF SQLAlchemy models: User, Agreement, Party, EStamp,
│                              # Signature, Payment, AuditLog, SysConfig, SysConfigJn
├── persistence/
│   ├── __init__.py
│   └── database.py            # Engine, SessionLocal, init_db() bootstrapper
├── security/
│   ├── __init__.py
│   └── cbac.py                # HMAC-SHA256 capability tokens, IDOR blocker, witness privacy,
│                              # XSS sanitization, 27-day draft purge evaluator
├── services/
│   ├── __init__.py            # Subsystem facade exports
│   ├── validation.py          # PAN, PIN, Email, Phone, Aadhaar masking (XXXXXXXX1234), financials
│   ├── rule_engine.py         # State stamp duty (KA ₹100, DL ₹100, MH 0.25%) & non-derogable clauses
│   ├── stamping_service.py    # SHCIL e-Stamp procurement, prepaid balance debit, < ₹10k alert, idempotency
│   ├── esign_service.py       # UIDAI Aadhaar eSign OTP (123456), rate limiting (5 attempts), PKCS#7 hash
│   ├── workflow_service.py    # Asynchronous non-atomic state machine, order-independent signing, atomic seal
│   ├── doc_assembly.py        # ReportLab PDF assembler, Page 1 e-Stamp, NumberedCanvas (Page X of Y), 65B cert
│   └── notification.py        # Tokenized sign links (WhatsApp/SMS) & daily reminder cron
├── ui/
│   ├── __init__.py
│   ├── landing.py             # Public landing, value pillars, 3-click flow, dynamic stamp duty calculator
│   ├── auth_profile.py        # Mobile OTP (123456), persona switch, suspicious ingress simulator
│   ├── wizard.py              # 5-step rental agreement wizard, split-pane editor, checkout, eSign modal
│   ├── dashboard.py           # User workspace (Pending, Completed, Drafts, MyInvoices, NPS rating)
│   └── admin.py               # StockHolding prepaid balance monitor, debit ledger, GMV metrics, NPS logs
└── tests/
    ├── conftest.py            # In-memory SQLite session & domain fixtures
    ├── test_validation.py     # 38 tests: regex, PII masking, numerical bounds
    ├── test_rule_engine.py    # 7 tests: state duty calculation, statutory clause protection
    ├── test_stamping.py       # 5 tests: SHCIL debit, balance alert (< ₹10k), idempotency
    ├── test_esign.py          # 5 tests: OTP challenge, consent, rate limit lockout (5 attempts)
    ├── test_workflow.py       # 4 tests: async order independence, atomic DSC sealing
    ├── test_doc_assembly.py   # 3 tests: PDF layout, Page X of Y, SHA-256 tamper verification
    ├── test_security_owasp.py # 6 tests: IDOR prevention, witness privacy, XSS, draft purge
    └── test_notification.py   # 3 tests: tokenized URL generation, WhatsApp dispatch, reminders
```

---

## 2. Core Architectural & Legal Invariants

1. **Strict PII Redaction**: Raw 12-digit Aadhaar numbers are never persisted. They are ingested in memory for mock OTP verification and masked immediately to `XXXXXXXX1234` via `services.validation.mask_aadhaar()`.
2. **StockHolding Stamping Balance Guard**: Corporate prepaid balance stored in `sysconfigTlb.stockholding_prepaid_balance`. Stamping calls debit duty in real-time. If balance $< \text{₹}10,000$, a visual crimson alert triggers on all admin pages. Debits append to `sysconfigTlb$jn`.
3. **Non-Atomic Asynchronous Multi-Party Execution**: Signatories (`1..n` owners, `1..n` tenants, witnesses) sign independently via tokenized links without order constraints. Contract atomically transitions to `'Completed'` and applies GoLegal Corporate DSC seal only when all designated parties have signed.
4. **Section 65B Evidentiary Audit Trail**: Terminal page of generated PDF contains server hostname, UTC timestamps, originating client IP addresses, PKCS#7 signature hashes, and SHA-256 tamper-evident checksums.
5. **Capability-Based Access Control (CBAC)**: Document endpoints require `HMAC-SHA256` capability tokens (`security.cbac`). Tokens encode `agr_id`, `pty_id`, `role`, and `actions`. Cross-agreement tampering triggers IDOR rejection.
6. **Witness Privacy Policy**: Witness tokens are downgraded post-signature; witnesses cannot view or download executed commercial deeds.
7. **Zero Document Hoarding**: Agreements without explicit cloud storage consent are purged after 27 days (`sysconfigTlb.data_pruning_days`).

---

## 3. Key Data Schemas & Table Models

- `users`: `id (UUID)`, `user_type`, `full_name`, `email`, `phone`, `address`, `created_at`.
- `agreements`: `id (UUID)`, `initiator_id (FK)`, `agreement_type`, `state_code`, `status` (`Draft`, `Paid`, `Pending_Signatures`, `Completed`, `Cancelled`, `Expired`), `property_details (JSON)`, `commercial_terms (JSON)`, `custom_clauses (Text)`, `cloud_storage_consent (Bool)`, `executed_at`.
- `parties`: `id (UUID)`, `agreement_id (FK)`, `party_type` (`Owner`, `Tenant`, `Witness`), `full_name`, `email`, `phone`, `aadhaar_masked (XXXXXXXX1234)`, `signing_status` (`Pending`, `Signed`), `access_token`.
- `estamps`: `id (UUID)`, `agreement_id (FK Unique)`, `certificate_number`, `state_code`, `stamp_amount`, `purchased_by`, `vendor`, `issued_at`.
- `signatures`: `id (UUID)`, `agreement_id (FK)`, `party_id (FK)`, `auth_type`, `transaction_ref`, `signature_hash (SHA-256)`, `signed_at`, `ip_address`.
- `payments`: `id (UUID)`, `agreement_id (FK)`, `total_amount`, `stamp_duty_amount`, `platform_fee`, `payment_gateway`, `status`.
- `audit_logs`: `id (UUID)`, `agreement_id (FK)`, `event_type`, `triggered_by`, `event_data (JSON)`, `recorded_at`.
- `sysconfigTlb`: `id`, `stockholding_prepaid_balance`, `low_balance_threshold (10000.0)`, `data_pruning_days (27)`.
- `sysconfigTlb$jn`: `jn_id`, `timestamp`, `operation`, `updated_by_user`, `previous_value`, `new_value`.

---

## 4. Key Operational Commands

```powershell
# Activate local virtualenv (Windows pwsh)
.\.venv\Scripts\Activate.ps1

# Execute full Pytest test suite with code coverage (71 tests)
.\.venv\Scripts\pytest.exe -v --cov=services --cov=domain --cov=security tests/

# Run Streamlit interactive application (Port 8501)
.\.venv\Scripts\streamlit.exe run app.py --server.port 8501 --server.headless true

# Check HTTP service health
curl -I http://localhost:8501
```

---

## 5. Phase Documentation References
- [`GoLegal_Master_PRD_Context_v2 .md`](./GoLegal_Master_PRD_Context_v2%20.md): **Authoritative Master PRD & SAD Baseline** (Mandatory pre-reading).
- [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md): 5-phase roadmap, Agile schedule, and subsystem architecture.
- [`DATASOURCE_PLAN.md`](./DATASOURCE_PLAN.md): 3NF schema, SQLite DDL, JSONB covenant schemas.
- [`ARCHITECTURE.md`](./ARCHITECTURE.md): 5-layer model, network DMZ topology, India VPC localization.
- [`SOFTWARE_DESIGN_DOCUMENT.md`](./SOFTWARE_DESIGN_DOCUMENT.md): Low-level design, state machines, CBAC specs.
- [`TEST_STRATEGY_AND_PLAN.md`](./TEST_STRATEGY_AND_PLAN.md): 4-tier V&V plan, 22-category OWASP matrix.
- [`UI_DESIGN_AND_INFO_ARCHITECTURE.md`](./UI_DESIGN_AND_INFO_ARCHITECTURE.md): UX flows, split-pane preview, session states.
- [`SYSTEM_TEST_CASES.md`](./SYSTEM_TEST_CASES.md): 30+ traceable test case definitions.
- [`DEPLOYMENT_PLAN.md`](./DEPLOYMENT_PLAN.md): Staging, Dockerfile, env vars, DR procedures.
- [`USAGE_DOCUMENTATION.md`](./USAGE_DOCUMENTATION.md): Tenant, Landlord, Witness, Admin operational manuals.
- [`SMART_EVALUATION_CRITERIA.md`](./SMART_EVALUATION_CRITERIA.md): 100-point rubric, LegalTech KPIs.
- [`PRIORITIZED_EXECUTION_PLAN.md`](./PRIORITIZED_EXECUTION_PLAN.md): P0-P4 prioritized engineering matrix.
