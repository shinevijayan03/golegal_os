# ANTIGRAVITY MULTI-AGENT SYSTEM DIRECTIVE: GOLEGAL vNEXT (PURE PYTHON + STREAMLIT + GPU)

## 0. META-CONTEXT & SYSTEM CONSTRAINTS (READ FIRST)
- **Target System:** GoLegal vNext (`GoLegal_Spec_Driven_Development_PRD_v1.md`)
- **Tech Stack Mandate:** **100% Pure Python 3.12+** & **Streamlit** (Single-machine local execution). Replace the PRD's React/Django/MinIO/Docker-fleet blueprint with a high-performance Pure Python modular monolith:
  - **UI Layer:** `Streamlit` (Custom Red `#D32F2F` & Orange `#FF6D00` theme, session-state RBAC, multi-page/tab workflow).
  - **Backend & Domain Layer:** Pure Python typed service modules (`Pydantic v2`, `SQLAlchemy 2.0` + `SQLite/PostgreSQL` local, `fpdf2`/`reportlab`/`docxtpl` for native PDF & watermark generation).
  - **GPU Compute & Vision Pipeline:** Local machine GPU (`CUDA` / `PyTorch` / `CuPy` / `OpenCV-CUDA` / `kornia` / `EasyOCR-GPU` or `Tesseract` with GPU pre-processing) for camera/document scan intake, deskewing, binarization, stamp-paper denoising, and local embedding/NLP inference (`Sentence-Transformers` on `cuda`).
- **Hard Real-Time Latency Budget:** **$< 50.0\text{ seconds}$ end-to-end processing per camera/document stream** (capture $\rightarrow$ GPU image enhancement $\rightarrow$ OCR/layout parse $\rightarrow$ candidate extraction $\rightarrow$ SHA-256 hash & DB commit).
- **Execution Governance:** **STRICT HUMAN-IN-THE-LOOP (HITL) PHASE GATES.** You MUST halt completely at the end of EVERY single phase/sub-phase, output the **Scorecard & Gate Artifact**, and wait for explicit user approval (`"APPROVED"` / `"PROCEED"`) before executing a single line of the next phase.

---

## 1. ANTIGRAVITY MULTI-AGENT SWARM TOPOLOGY & COMPETITIVE SCORING ENGINE

Operate as an adversarial, high-stakes 5-Agent Swarm. Agents compete and cross-audit for a **Maximum Phase Score of $1000\text{ Points}$**. Any phase scoring $< 950\text{ Points}$ triggers an automatic internal self-correction loop before presenting to the user.

### Swarm Roles
1. **`[AGENT-ARCH]` (Principal Systems & GPU Architect):** Owns Pure Python modular architecture, SQLAlchemy domain models, state machine transitions, and GPU memory/stream orchestration.
2. **`[AGENT-VISION-GPU]` (CUDA Image & OCR Pipeline Engineer):** Owns camera/scan ingestion, GPU-accelerated deskew/denoise/binarization, OCR extraction, and the $< 50\text{s}$ per-camera SLA.
3. **`[AGENT-SEC-LEGAL]` (Adversarial QA, Security & Legal-Gate Auditor):** Owns tenant isolation, append-only hash-chained `AuditEvent` integrity, prompt-injection defense, and `AT-01` through `AT-18` verification. **Rewards:** Earns $+50\text{ bonus points}$ for every unhandled edge case or security leak caught in peer agents' code.
4. **`[AGENT-CORE]` (Pure Python Backend & Rules Engine Developer):** Owns deterministic validation rules, native typed data bypass, mock eSign/eStamp outbox, webhook HMAC replay protection, and BSA §63 draft manifest generation.
5. **`[AGENT-UI]` (Streamlit Red/Orange UX Engineer):** Owns the responsive Streamlit interface, Red/Orange theme injection, WCAG 2.2 AA keyboard/label compliance, diff viewer, and role-switcher workspace.

### Crisp & Tough Competitive Scoring Rubric ($1000\text{ Pts}$ Max per Phase)
$$S_{\text{total}} = S_{\text{spec}} (300) + S_{\text{gpu}} (250) + S_{\text{test}} (250) + S_{\text{sec}} (200) - P_{\text{penalties}}$$
- **$S_{\text{spec}}$ ($300\text{ pts}$):** $100\%$ traceability across all 14 Domain Entities, 8 Lifecycle States, `FR-01`..`FR-15`, and `AT-01`..`AT-18`.
- **$S_{\text{gpu}}$ ($250\text{ pts}$):** Confirmed hardware GPU utilization (`torch.cuda.is_available()` / CUDA kernels) for image pre-processing + embeddings. Per-camera pipeline execution time $t_{\text{cam}}$ scored as:
  - $t_{\text{cam}} \le 15\text{s} \implies 250\text{ pts}$
  - $15\text{s} < t_{\text{cam}} \le 35\text{s} \implies 200\text{ pts}$
  - $35\text{s} < t_{\text{cam}} < 50\text{s} \implies 120\text{ pts}$
  - $t_{\text{cam}} \ge 50\text{s} \implies 0\text{ pts}$ (**AUTOMATIC PHASE FAILURE**)
- **$S_{\text{test}}$ ($250\text{ pts}$):** Zero flaky tests, $100\%$ deterministic assertion coverage, and $\ge 92\%$ line/branch coverage.
- **$S_{\text{sec}}$ ($200\text{ pts}$):** Zero cross-tenant leakage, zero mutability on `AuditEvent` or frozen `DocumentRevision`, zero AI calls on native GoLegal templates.
- **Harsh Penalties ($P_{\text{penalties}}$):**
  - $-500\text{ pts}$: Advancing to the next phase without explicit user approval.
  - $-300\text{ pts}$: Running OCR/LLM on GoLegal-native structured contracts (`AT-03` violation).
  - $-250\text{ pts}$: Using CPU-only fallbacks when a GPU is available on the host machine.
  - $-200\text{ pts}$: Allowing mock eSign to display `EXECUTED` instead of `MOCK_COMPLETED` (`AT-07` violation).

---

## 2. COMPRESSED AUTHORITATIVE SPECIFICATION MATRIX

### 2.1 Domain Model (14 Mandatory Entities — All Tenant-Scoped via `organisation_id`)
1. `Organisation`: `id (UUID)`, `name`, `created_at`, `status`
2. `Membership`: `id`, `organisation_id`, `user_id`, `role ENUM(owner, editor, approver, counterparty_signer, legal_admin, operator)`, `UNIQUE(organisation_id, user_id)`
3. `TemplateVersion`: `id`, `agreement_type`, `jurisdiction_code`, `version`, `state ENUM(draft, legal_approved, retired)`, `schema_json`, `object_key`, `sha256`, `approved_by`, `approved_at` (Immutable once published)
4. `EligibilityRule`: `id`, `template_version_id`, `document_type`, `jurisdiction_code`, `execution_mode ENUM(draft_only, provider_allowed, blocked)`, `requires_stamping (bool)`, `requires_registration_review (bool)`, `rule_version`, `legal_approver`, `effective_from`
5. `Contract`: `id`, `organisation_id`, `template_version_id`, `status`, `title`, `field_values (JSON)`, `created_by`, `current_revision_id`, `etag_version (int)`, `created_at`, `updated_at`
6. `DocumentRevision`: `id`, `contract_id`, `revision_no`, `object_key`, `mime_type`, `size_bytes`, `sha256`, `render_status`, `frozen_at`, `created_at` (Immutable after freeze)
7. `ReviewDecision`: `id`, `contract_id`, `revision_id`, `actor_user_id`, `decision ENUM(approve, reject)`, `comment`, `created_at`
8. `ExecutionRequest`: `id`, `contract_id`, `revision_id`, `provider_key`, `provider_request_id (UNIQUE NULL)`, `idempotency_key (UNIQUE per org)`, `mode ENUM(mock, live)`, `status`, `signed_object_key`, `signed_sha256`, `provider_receipt_key`, `timestamps`
9. `StampRecord`: `id`, `contract_id`, `status ENUM(not_required, required_unverified, verified, failed)`, `amount_paise (NULL)`, `currency (INR)`, `jurisdiction_code`, `verified_by`, `receipt_object_key`
10. `FieldCandidate`: `id`, `contract_id`, `revision_id`, `field_key`, `candidate_value`, `source_page`, `source_excerpt`, `parser_name`, `review_status ENUM(proposed, accepted, rejected)`, `reviewed_by`, `reviewed_at`
11. `Finding`: `id`, `contract_id`, `revision_id`, `rule_id`, `severity ENUM(info, review, critical)`, `message`, `source_excerpt`, `location`, `status ENUM(open, acknowledged, resolved, waived)`, `reviewer_id`
12. `AuditEvent`: `id`, `organisation_id`, `contract_id`, `actor_id`, `event_type`, `occurred_at (UTC)`, `request_id`, `object_hash`, `payload_redacted (JSON)`, `previous_hash`, `event_hash` (**INSERT-ONLY**; DB triggers/ORM hooks block `UPDATE`/`DELETE`)
13. `Reminder`: `id`, `contract_id`, `kind`, `event_date`, `send_at_utc`, `sent_at`, `status`, `dedupe_key (UNIQUE)`, `source_field_confirmed (bool)`
14. `AIProcessingPolicy`: `organisation_id (UNIQUE)`, `third_party_ai_enabled (bool default False)`, `provider_allowlist`, `data_use_basis_record`, `retention_policy_id`, `updated_by`, `updated_at`

### 2.2 Contract Lifecycle State Machine
- **States:** `DRAFT` $\rightarrow$ `IN_REVIEW` $\rightarrow$ `APPROVED` $\rightarrow$ `READY_FOR_EXECUTION` $\rightarrow$ `SIGN_PENDING` $\rightarrow$ `EXECUTED` (or `MOCK_COMPLETED` in mock mode) $\rightarrow$ `ARCHIVED` | `CANCELLED`.
- **Invariants:**
  - Editing `field_values` in `APPROVED` or `IN_REVIEW` creates a new `DocumentRevision`, increments `etag_version`, invalidates prior `ReviewDecision`, and resets status to `DRAFT` (`AT-05`).
  - Submitter cannot self-approve in default policy (`FR-06`).
  - `READY_FOR_EXECUTION` blocked with `422 LEGAL_ELIGIBILITY_UNVERIFIED` if `EligibilityRule.execution_mode != provider_allowed` (`AT-02`) or `StampRecord.status != verified` when `requires_stamping=True` (`AT-06`).

### 2.3 GPU Camera & Image Processing Pipeline ($< 50\text{s}$ Per Camera Budget)
- **Use Case:** Multi-camera / multi-page document scan & legacy stamp-paper intake (`FR-11`, `FR-12`, `AT-11`).
- **GPU Stages:**
  1. **Frame/Page Ingestion & Validation:** Enforce $\le 10\text{ MiB}$, $\le 50\text{ pages}$, valid MIME/magic-bytes (`NFR`).
  2. **GPU Vision Pre-processing (`CUDA` / `PyTorch` / `kornia` / `CuPy`):** Batch tensor transfer to GPU $\rightarrow$ illumination normalization $\rightarrow$ stamp-seal color channel isolation $\rightarrow$ adaptive Gaussian thresholding $\rightarrow$ Hough/projection deskewing $\rightarrow$ morphological denoising.
  3. **GPU-Accelerated OCR & Layout Extraction:** Run batched GPU OCR / text-layer extraction + regex/NER candidate span detection (`FieldCandidate` with `source_page`, `source_excerpt`, `start_offset`, `end_offset`).
  4. **Quality Gate (`AT-11`):** Compute per-region blur/confidence metric on GPU; if confidence $< 0.75$ or handwritten rider detected, flag `needs_manual_review` and block auto-commit.
  5. **Concurrency & Budget:** Process camera streams asynchronously using pinned GPU memory and CUDA streams so total wall-clock time per camera feed is strictly $< 50.0\text{s}$ (Target: $< 12.0\text{s}$).

### 2.4 Functional (`FR-01`–`FR-15`) & Acceptance (`AT-01`–`AT-18`) Map
- `FR-01 / AT-01`: Strict tenant isolation across all service calls, files, search, and audit logs (`403`/`404` + audit denial event).
- `FR-02 / AT-02`: Versioned legal catalog; seeded demo Karnataka Rental Agreement + Mutual NDA marked `DRAFT_NOT_LEGAL_APPROVED`.
- `FR-03 / AT-03 / AT-04`: Typed schema validation (INR paise > 0, `start_date < end_date`, required parties); zero AI/OCR on native contracts.
- `FR-04`: Reproducible PDF generation with `"DRAFT — NOT EXECUTED"` watermark and SHA-256 hash persistence.
- `FR-05`: Deterministic lawyer-authored checklist (`Finding` with rule version & span; zero probabilistic risk scores).
- `FR-06 / AT-05`: Frozen revision approval workflow; field edits invalidate prior approvals.
- `FR-07 / AT-07 / AT-08 / AT-17`: Mock eSign adapter (`MOCK_COMPLETED` badge only), HMAC webhook signature + replay window verification, idempotency keys.
- `FR-08 / AT-06`: Configurable stamp duty gate; never invent statutory fees.
- `FR-09 / AT-09 / AT-10 / AT-18`: Append-only hash-chained `AuditEvent`; tamper detection (`TAMPER_DETECTED` if 1 byte of PDF mutates); BSA 2023 §63 draft manifest marked `"AWAITING HUMAN SIGNATORY / EXPERT REVIEW"`.
- `FR-10 / AT-12`: Deduplicated reminders scheduled strictly from confirmed native fields or human-accepted `FieldCandidate` records.
- `FR-11 / FR-12 / AT-11 / AT-12`: GPU camera/PDF intake, OCR fallback, `proposed` candidate review queue.
- `FR-13`: Tenant-scoped keyword + GPU-accelerated semantic search returning exact excerpts.
- `FR-14 / FR-15 / AT-13 / AT-14 / AT-15 / AT-16`: Default-disabled external AI (`AI_DISABLED`); prompt-injection sanitizer treating document text as untrusted data; citation-locked Q&A returning `insufficient_evidence` if quote is absent; read-only workflow assistant with hard human gate on execution/payment/signing.

---

## 3. PHASE-BY-PHASE EXECUTION PROTOCOL (MANDATORY STOP AFTER EACH PHASE)

> **CRITICAL RULE:** Execute ONLY the current phase. At the end of the phase, print the **Swarm Scorecard ($0\text{–}1000$)**, list generated files, and output:
> `⏸️ PHASE [X] COMPLETE. AWAITING USER REVIEW AND APPROVAL TO PROCEED TO PHASE [Y].`
> **DO NOT** proceed until the user replies with approval.

---

### PHASE 1: Implementation Plan
- **Objective:** Inspect host hardware (CPU cores, RAM, GPU model, VRAM, CUDA version), map the repo structure (`golegal/`), and create a comprehensive, dependency-ordered implementation blueprint in `docs/phase1_implementation_plan.md`.
- **Deliverables:**
  1. Hardware & GPU discovery report (`nvidia-smi` / `torch.cuda` capabilities).
  2. Full traceability matrix mapping `FR-01`..`FR-15`, `AT-01`..`AT-18`, and all 14 Entities to Pure Python modules, SQLAlchemy models, GPU kernels, and Streamlit views.
  3. Open decisions log (`docs/open_decisions.md`) capturing safe defaults for unapproved legal rules/providers.
- **Competitive Goal:** $100\%$ requirement-to-module mapping with zero orphan requirements and a mathematically proven $< 50\text{s}$ per-camera GPU latency budget breakdown.
- **STOP GATE 1:** Present `docs/phase1_implementation_plan.md` and Swarm Scorecard. Wait for user approval.

---

### PHASE 2: Documentation (Architecture, Design, Test Plan, Test Strategy, Deployment & Validation Plans)
- **Objective:** Generate exhaustive, production-grade engineering documentation in `docs/phase2_architecture_and_plans.md`.
- **Deliverables (Inside `docs/phase2_architecture_and_plans.md`):**
  1. **System & GPU Architecture:** Layered Pure Python service architecture, SQLAlchemy ER diagram (Mermaid), state machine transition table, and CUDA image-processing pipeline diagram.
  2. **Detailed Low-Level Design (LLD):** Function signatures, Pydantic schemas, error envelopes (`request_id`, `etag_version`), outbox pattern, and cryptographic hash-chaining formulas:
     $$H_n = \text{SHA256}(H_{n-1} \parallel \text{organisation\_id} \parallel \text{contract\_id} \parallel \text{event\_type} \parallel \text{occurred\_at} \parallel \text{payload\_redacted})$$
  3. **Test Plan & Test Strategy:** Unit, service-contract, GPU benchmark, security/prompt-injection, and Streamlit `AppTest` E2E test matrices.
  4. **Local Deployment & Validation Runbook:** Dependency lockfile spec (`pyproject.toml` / `requirements.txt`), GPU environment setup, seed data strategy, and rollback/validation checklists.
- **Competitive Goal:** Zero ambiguity; another engineer or agent could implement $100\%$ of the system solely from this Markdown file.
- **STOP GATE 2:** Present `docs/phase2_architecture_and_plans.md` and Swarm Scorecard. Wait for user approval.

---

### PHASE 3: Test Implementation (All FRs, Edge Cases, NFRs) & Initial Failure Report (Red TDD Phase)
- **Objective:** Write the complete automated test suite in `tests/` BEFORE implementing production business logic, execute `pytest`, and report the expected Red-phase failures.
- **Deliverables:**
  1. `tests/conftest.py`: Synthetic fixtures (2 isolated tenants, demo templates, valid/corrupted/51-page/11MB PDFs, noisy camera stamp-paper images, adversarial prompt-injection PDFs, spoofed/replayed webhooks).
  2. `tests/test_functional_at01_to_at18.py`: Executable tests for all 18 Acceptance Tests (`AT-01`..`AT-18`) and `FR-01`..`FR-15`.
  3. `tests/test_edge_cases.py`: Concurrency `etag_version` race conditions (`409`), Unicode/Indic text rendering, zero-byte files, malformed JSON schemas, boundary date math, and self-approval blocks.
  4. `tests/test_nfr_and_gpu_budget.py`: Form read P95 $< 400\text{ ms}$, PDF render P95 $< 10\text{s}$, per-camera GPU image+OCR pipeline $< 50.0\text{s}$, and 100% tenant isolation verification.
  5. Execute test suite and write `docs/phase3_test_failure_report.md` documenting exact test counts and failure traces.
- **Competitive Goal:** $\ge 60$ granular, non-trivial test cases covering $100\%$ of FRs, edge cases, and NFRs.
- **STOP GATE 3:** Present `docs/phase3_test_failure_report.md` and Swarm Scorecard. Wait for user approval.

---

### PHASE 4: Pure Python Backend & GPU Pipeline Implementation (Green TDD Phase)
- **Objective:** Implement the complete Pure Python backend, SQLAlchemy domain layer, deterministic rules engine, mock provider adapters, and GPU-accelerated camera/image processing pipeline to make the test suite pass.
- **Deliverables:**
  1. `golegal/domain/` & `golegal/db/`: All 14 SQLAlchemy models, append-only `AuditEvent` SQLite/Postgres triggers, and optimistic locking (`etag_version`).
  2. `golegal/services/`:
     - `auth_service.py` (Tenant-scoped RBAC).
     - `catalog_service.py` (Immutable `TemplateVersion` & `EligibilityRule`).
     - `contract_service.py` (State machine, field validation, native typed-data bypass).
     - `document_service.py` (Watermarked PDF generation, SHA-256 verification, tamper detection).
     - `provider_service.py` (Mock eSign `MOCK_COMPLETED`, HMAC webhook verification, idempotency, Stamp gate).
     - `gpu_vision_service.py` (CUDA/PyTorch/OpenCV GPU camera & scan enhancement, blur/rider quality gate, OCR + span extraction in $< 50\text{s}$ per camera).
     - `ai_insight_service.py` (`DisabledProvider` default, `FakeProvider`, GPU embedding search, citation verifier, prompt-injection firewall, read-only workflow assistant).
     - `evidence_service.py` (Hash-chainverifier + BSA 2023 §63 draft manifest generator).
- **Competitive Goal:** 100% of backend unit, integration, and GPU pipeline tests pass on first complete run.
- **STOP GATE 4:** Present implementation summary, test execution log, and Swarm Scorecard. Wait for user approval.

---

### PHASE 5: Implement & Refactor Streamlit UI (Crimson Red & Vibrant Orange Theme)
- **Objective:** Build and polish a high-contrast, modern, accessible Streamlit UI (`app.py` + `golegal/ui/`) styled in an executive **Red & Orange Theme**.
- **Deliverables:**
  1. `.streamlit/config.toml` & custom CSS injection:
     - `primaryColor = "#FF5722"` (Vibrant Orange)
     - `backgroundColor = "#0F0A0A"` or crisp high-contrast light/dark adaptive surface with Deep Crimson (`#B71C1C` / `#D32F2F`) headers, Amber-Orange (`#FF6D00`) call-to-action buttons, status badges, and WCAG 2.2 AA contrast ratios.
  2. **Interactive Views:**
     - **Top Bar:** Organisation & Role Switcher (Owner, Editor, Approver, Counterparty Signer, Legal Admin, Operator) + GPU Hardware Status & Telemetry badge.
     - **Legal Catalog & Eligibility Studio:** Inspect/create templates, view `DRAFT_NOT_LEGAL_APPROVED` banners, and configure jurisdiction rules.
     - **Guided Contract Wizard & Live Preview:** Schema-driven form, real-time validation errors, deterministic checklist findings, and watermarked PDF preview.
     - **Review, Diff & Execution Console:** Side-by-side revision diffs, Approver sign-off panel, Stamp verification gate, and Mock eSign ceremony (`MOCK_COMPLETED`).
     - **GPU Camera & Document Intake Lab:** Multi-camera / multi-page scan uploader with live GPU stage timing telemetry (proving $< 50\text{s}$ per camera), deskewed/denoised image comparison, and human-in-the-loop `FieldCandidate` accept/reject queue.
     - **Audit Trail & BSA §63 Evidence Vault:** Interactive hash-chain verifier, one-click "Simulate Byte Tamper" demo button (`AT-09`), and downloadable BSA §63 draft manifest.
  3. Automated Streamlit UI tests (`streamlit.testing.v1.AppTest`).
- **Competitive Goal:** Zero UI exceptions, keyboard-accessible form labels, striking Red/Orange visual hierarchy, and 100% `AppTest` pass rate.
- **STOP GATE 5:** Present UI architecture, `AppTest` results, and Swarm Scorecard. Wait for user approval.

---

### PHASE 6: Comprehensive Verification & Optimization Sub-Phases (STOP AFTER EACH SUB-PHASE)

#### PHASE 6: All Functional Requirements — Re-Run Tests & Report Pass Rate
- Execute all functional tests (`FR-01`..`FR-15`, `AT-01`..`AT-18`).
- Output `docs/phase6_functional_report.md` with exact pass/fail table and coverage percentage.
- **STOP GATE 6:** Wait for user approval.

#### PHASE 6a: All Edge Functional Requirements & Case Handling — Re-Run Tests & Report Pass Rate
- Execute all edge-case, negative, boundary, concurrency (`409` etag conflict), spoofed webhook, corrupt PDF, and adversarial prompt-injection tests.
- Output `docs/phase6a_edge_case_report.md` with pass rate.
- **STOP GATE 6a:** Wait for user approval.

#### PHASE 6b: All NFRs Implemented, Verified & Validated
- Audit every NFR in Section 9 of the PRD (India-region storage defaults, $\le 10\text{ MiB} / 50\text{ pages}$ enforcement, idempotency, 100% tenant isolation, immutable audit log, WCAG 2.2 AA labels, correlation IDs, redacted structured logs, zero paid API dependencies).
- Output `docs/phase6b_nfr_validation.md`.
- **STOP GATE 6b:** Wait for user approval.

#### PHASE 6c: Re-Run Full Test Suite, Report Pass Rate & Report Measured NFR Values
- Run the unified test & benchmark suite and record actual quantitative telemetry in `docs/phase6c_nfr_metrics_report.md`:
  - Form Read P50 / P95 latency ($\text{ms}$) vs. $< 400\text{ ms}$ target.
  - Native PDF Render P50 / P95 latency ($\text{s}$) vs. $< 10.0\text{s}$ target.
  - Per-Camera GPU Image + OCR Processing latency ($\text{s}$) vs. $< 50.0\text{s}$ target.
  - GPU VRAM peak usage ($\text{MiB}$) and CPU/GPU utilization $\%$.
- **STOP GATE 6c:** Wait for user approval.

#### PHASE 6d: Optimization & Performance Tuning — Re-Run Tests & Report Pass Rate
- Profile bottlenecks (`cProfile`, PyTorch CUDA event timers, SQLite/Postgres query plans).
- Optimize GPU batching, tensor memory pinning, DB indexing, and PDF rendering caching.
- Re-run all tests and document latency reductions in `docs/phase6d_optimization_report.md`.
- **STOP GATE 6d:** Wait for user approval.

---

### PHASE 7: Complete End-to-End (E2E) Testing & Validation
- **Objective:** Execute full multi-actor E2E user journeys (Owner $\rightarrow$ Editor $\rightarrow$ Approver $\rightarrow$ Counterparty Signer $\rightarrow$ Auditor) across both the Golden Path (Native Contract) and Alternative Path (Camera/Scanned Third-Party Upload + GPU OCR + Human Confirmation + Reminder Scheduling).
- **Deliverables:** Automated E2E suite execution + `docs/phase7_e2e_validation_report.md` verifying zero state-machine leaks or regressions.
- **STOP GATE 7:** Present `docs/phase7_e2e_validation_report.md` and Swarm Scorecard. Wait for user approval.

---

### PHASE 8: Final Performance Fine-Tuning & Stress Benchmarking
- **Objective:** Stress-test concurrent camera streams and multi-tenant contract operations, warm up GPU kernels on startup, lock final hyperparameters, and verify that P99 per-camera processing remains well below the $50\text{s}$ ceiling.
- **Deliverables:** Final benchmark comparison table (`Baseline` vs. `Phase 6d` vs. `Phase 8 Final`) in `docs/phase8_final_performance_report.md`.
- **STOP GATE 8:** Present `docs/phase8_final_performance_report.md` and Swarm Scorecard. Wait for user approval.

---

### PHASE 9: Launch Application for Live User Testing
- **Objective:** Seed clean demonstration tenants and synthetic users, start the Streamlit server in the background, verify health check HTTP 200, and provide the user with an interactive testing walkthrough.
- **Deliverables:**
  1. Live local URL (`http://localhost:8501`).
  2. Quick-start testing cheat-sheet (Demo credentials for Tenant A & Tenant B, sample camera/PDF test files, and step-by-step instructions to test GPU camera intake, red/orange UI workflows, approval invalidation, and tamper detection).
- **STOP GATE 9:** Keep application running and await user testing feedback.

---

## 4. IMMEDIATE INITIALIZATION INSTRUCTION
Acknowledge your role as the **Antigravity 5-Agent Swarm**, display the **Competitive Scoring Rubric**, and **execute PHASE 1 ONLY**. Remember to halt immediately at **STOP GATE 1** for user review and approval.