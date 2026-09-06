# GoLegal — Agentic AI Readiness: Gap Analysis & Closure Report

> **Scope**: Evaluation of the GoLegal codebase against the Master PRD (`GoLegal_Master_PRD_Context_v2 .md`)
> and against the bar for a *complete agentic AI web application*.
> **Baseline audited**: commit `d9ff23e` (71 tests, 96% coverage, Streamlit UI, 5 services).
> **Status**: all P0–P2 gaps closed in this cycle; residual items listed in §4 with rationale.

---

## 1. How the baseline scored

The baseline was a competent **scripted demo**, not an agentic product. It rendered the PRD's five
steps and passed its own tests, but the tests largely exercised the services in isolation while the UI
re-implemented the same logic inline. Nothing in the system could *decide* or *act*.

| Dimension | Baseline | Now |
| :--- | :--- | :--- |
| AI / agency | None. No model, no tools, no autonomy. | Copilot (tool-using loop), autonomous Workflow Agent, clause intelligence, ingestion, benchmarks |
| Persistence of work | Draft state lived only in `st.session_state` | Every draft, document, notification, login and agent run is a database row |
| Identity | Hardcoded dict; a "persona switcher" | Real accounts, PBKDF2 passwords, DB-backed OTP with lockout, suspicious-ingress journal |
| Counterparty journey | Absent — a single operator clicked "Sign as X" | Capability-link page: no account, token is the credential, witness downgrade enforced |
| Money | Fees computed in the UI; `payments` table never written | `PaymentService` with server-side quote, captured payment, numbered GST invoice PDF |
| Documents | Rebuilt on every page render, never stored | Content-addressed `documents` store, sealed once, digest recorded and verified |
| Lifecycle | Manual `agr.status = "Completed"` in the UI | State machine + agent that dispatches, reminds, expires, seals and purges |
| Tests | 71, service-level | 126, including a full lifecycle test and agent guardrail tests |

---

## 2. Gaps found, by severity

### 2.1 Critical — the application was not agentic at all

| # | Gap | Evidence in baseline | Closure |
| :-- | :--- | :--- | :--- |
| A1 | **No AI layer of any kind.** The PRD's §12.2 AI roadmap (clause risk scoring, PII redaction, rate assist) and §4.1 "AI chatbot for contract terminology" were entirely unimplemented. | No model client, no `ai/` package, no dependency on any LLM SDK. | New `ai/` package: `llm` gateway, `tools` registry, `copilot`, `workflow_agent`, `clause_intelligence`, `contract_ingest`, `rent_benchmark`. |
| A2 | **No agency.** Nothing observed state or acted on it; every transition needed a human click. | `ui/wizard.py` set `agr.status = "Completed"` directly. | `WorkflowAgent` observes → plans → acts across the whole portfolio, with a journaled `AgentRun` per execution. |
| A3 | **No tool boundary.** There was no way for an agent to act safely, because there was no notion of a permitted action. | — | `ai/tools.py`: every capability declared with a JSON schema and a tier (`read` / `write` / `human`). Payment, stamping and eSign are `human` and have *no handler* — an agent cannot execute them even if instructed to. |
| A4 | **No agent auditability.** | — | `agent_runs` table stores goal, model, status, token usage and the full step log; surfaced in the Operations console. |
| A5 | **No graceful degradation.** | — | Every AI feature has a deterministic fallback. With no `ANTHROPIC_API_KEY` the Copilot routes intents by rule and the whole test suite runs offline. |

### 2.2 High — PRD requirements missing or faked

| # | Gap | Closure |
| :-- | :--- | :--- |
| B1 | **Counterparty signing journey absent** (PRD §6.5, US-06). The tokenized link was generated but nothing consumed it; one operator signed for everybody. | `ui/sign.py` + router branch on `?sign_token=`. No account needed; the CBAC token authorises view / sign / download independently. |
| B2 | **Witness privacy not enforced end to end** (§6.9.3). The rule existed in `cbac.py` but tokens were never downgraded after signing. | `seal_agreement()` re-mints every party token; witnesses get `COMPLETED_ACK` only, and the signing page shows the policy instead of a download. |
| B3 | **Payments never persisted** (US-05). The `payments` table was defined and never written; `MyInvoices` showed a hardcoded HTML row. | `PaymentService.checkout()` writes the payment, allocates `INV-YYYY-NNNNN`, renders a GST invoice PDF (HSN 998319, duty as pure agent) and journals `PAYMENT_CAPTURED`. |
| B4 | **Authentication was a stub.** A dict in session state, OTP compared to a literal, no registration, no password storage. | `security/auth.py`: PBKDF2-HMAC-SHA256, registration with validation, DB-persisted OTP challenges with expiry + 5-attempt lockout that survives restarts. |
| B5 | **Suspicious ingress was theatre** (US-02, §11.1). A button set a dict of fake values. | Every sign-in is journaled; a real detector compares device fingerprint, IP subnet and geo against the account's history and dispatches an alert. The simulator now drives the real detector. |
| B6 | **Multi-party `1..n` unsupported** (§6.7). The wizard had exactly one owner, one tenant, one witness; "add co-tenant" appended a hardcoded person. | `owners[] / tenants[] / witnesses[]` throughout, with add/remove in the UI and validation per party. |
| B7 | **Ownership and access control absent.** The dashboard listed *every* agreement in the database to *every* visitor. | `AgreementService.list_for_user()` scopes to initiator or named non-witness party; `get_accessible()` raises otherwise. Verified by test. |
| B8 | **Soft delete missing** (§5.1). "Soft Delete Draft" hard-deleted the row, destroying counterparty access. | `is_archived` flag; archive/restore; counterparties keep full access. Verified by test. |
| B9 | **Section 65B certificate incomplete** (§6.9.2). Signer IPs, timestamps and hashes were hardcoded strings (`"06-Sep-2026 14:40:00"`, `"SHA256: 4f3a9e...GoLegalSeal"`). | Real signature rows, real IPs and user agents, a deterministic content digest, an HMAC corporate seal, the server hostname and a 25-event evidentiary log. |
| B10 | **No expiry, no reminders, no purge.** The 7-day window, daily reminder cron and 27-day purge were documented but unimplemented. | `expire_stale_agreements()`, `run_reminder_sweep()`, `purge_unconsented_drafts()`, all driven by the agent sweep. |
| B11 | **OCR / existing-contract ingestion missing** (§5.1 MVP1). | `ai/contract_ingest.py` reads pasted text or a PDF and fills the wizard; deterministic extractor plus optional model extraction. |
| B12 | **Vernacular support missing** (§5.1, persona 4). | Plain-language summary in English deterministically; Hindi / Kannada / Tamil / Telugu via the model, offered on the wizard *and* on the counterparty signing page where the non-tech-savvy user actually reads it. |

### 2.3 Medium — engineering quality

| # | Gap | Closure |
| :-- | :--- | :--- |
| C1 | **Secrets hardcoded.** `DEFAULT_SECRET_KEY = "golegal_crypto_secure_hmac_secret_2026"` in source — the exact failure OWASP category 21 in the PRD's own matrix warns about. | `config.py` reads every secret, fee and threshold from the environment. |
| C2 | **Business logic duplicated in the UI.** The wizard created users, agreements and parties inline; the dashboard rebuilt PDFs on every render. | UI calls services only. `AgreementService`, `PaymentService`, `DocumentService` own the logic. |
| C3 | **In-memory rate limiting.** `ESignService._failed_attempts` was a dict on an instance the UI recreated on every rerun, so the 5-attempt lockout could never actually trigger in the app. | `otp_challenges` table; attempts carry across re-issued OTPs so re-requesting cannot reset the counter. |
| C4 | **PDF injection risk.** User text went unescaped into ReportLab's mini-HTML parser; a name containing `<b>` corrupted or crashed the document. | `_esc()` on every interpolated value. |
| C5 | **Hardcoded values in generated documents.** Date, consideration, stamp amount and signature hashes were literals. | All derived from the agreement. |
| C6 | **No transactional boundary or additive migrations.** | `session_scope()`; `_apply_additive_migrations()` so an existing `golegal.db` survives new columns. |
| C7 | **Naive datetime mixing.** `datetime.utcnow()` (deprecated) alongside timezone-aware values. | Single `utc_now()` helper, consistently naive-UTC to match SQLite storage. |

### 2.4 Medium — experience

| # | Gap | Closure |
| :-- | :--- | :--- |
| D1 | **Generic UI.** Default Streamlit chrome with a blue tint; a "preview" that was a markdown dump. | A design system rooted in the product's own artefact: the deed renders as **e-Stamp paper** — guilloche security tint, certificate header, serif body, a red `DRAFT · NOT EXECUTED` seal that turns green `SEALED · SECTION 65B` on execution. |
| D2 | **No sense of progress or trust.** | Signature progress ring, per-party status pills, live market check, transparent itemised invoice before payment. |
| D3 | **Errors were raw exceptions.** | Every failure path renders a sentence a tenant can act on. |
| D4 | **No empty states, no sort, no rename, no archive.** | All present in the workspace. |

---

## 3. What "agentic" means in this codebase

Three properties, each verifiable:

**1. The agent perceives.** `WorkflowAgent.observe()` reads real state: who has signed, when each party
was last contacted, whether the window has lapsed, whether the seal digest still matches.

**2. The agent decides and acts.** `plan()` returns the steps it intends to take; `run()` executes them
through `WorkflowService`, so the state machine, audit journal and notification ledger apply exactly as
they do for a human action. `sweep()` runs the whole portfolio.

**3. The agent is bounded.** Three guardrails, all tested:

- **Tier system.** `human`-tier tools (`pay_and_procure_estamp`, `aadhaar_esign`) have no handler.
  Calling one returns an error telling the model to guide the user instead. Payment and signature are
  personal legal acts; no amount of prompt injection can make the agent perform them.
- **Read-only mode.** `ToolContext(mode="readonly")` rejects every `write` tool.
- **PII refusal.** `prefill_agreement` strips `aadhaar` from any party the model supplies, and
  `assess_clause_risk` masks identity numbers found in free text before they are persisted.

The Copilot uses the same registry. With a model configured it runs a real tool-use loop
(`stop_reason == "tool_use"` → execute → feed results back); without one it routes intents to the same
tools deterministically. Both paths write an `AgentRun`.

---

## 4. Residual gaps (deliberately not closed)

| Item | Why it remains | Path to close |
| :--- | :--- | :--- |
| Real SHCIL / UIDAI / Razorpay APIs | Require commercial contracts, ESP empanelment and a CCA-licensed DSC. The services are written as adapters with the real request/response shapes, so swapping the mock for a live client is a single class per gateway. | Replace `StampingService.procure_estamp`, `ESignService.verify_otp_and_sign` and `PaymentService.checkout` internals; the interfaces do not change. |
| Cryptographic PKCS#7 signing | A genuine detached CMS signature needs an HSM-held X.509 key from a licensed CA. The current seal is HMAC-SHA256 over a deterministic content digest — tamper-evident but not a legally-issued DSC. | `cryptography` + `endesive` with the CA-issued key. |
| Session persistence across page reloads | Streamlit's session state is per-websocket; there is no first-party cookie API. Reloading the browser signs the user out. | Cookie-based session behind a reverse proxy, or `streamlit-cookies-controller`. |
| Registration under Registration Act s.17 | Out of scope by law for 11-month tenancies; the app warns when a term of 12 months or more is selected. | Sub-Registrar appointment integration (MVP2). |
| Full OCR of scanned images | `pypdf` extracts embedded text only. Scanned paper needs Tesseract or a vision model. | Route image PDFs through a vision call in `contract_ingest`. |
| B2B API, broker portal, property matching | PRD MVP2/MVP3. | — |

---

## 5. Verification

```
126 passed
Coverage: 89% across services, domain, security, ai, config
```

Covering, among others:

- **Full lifecycle** (`test_payment_and_flow.py`): draft → pay → stamp → dispatch → out-of-order
  signing → reminder → atomic seal → witness downgrade → terminal-state immutability, asserting the
  audit event set and that sealing twice yields byte-identical output.
- **Agent guardrails** (`test_ai_layer.py`): human-tier refusal, read-only refusal, Aadhaar stripping,
  and that the agent returns `NEEDS_HUMAN` rather than advancing an unpaid agreement.
- **Agent lifecycle**: plan and act across Draft → Paid → Pending → sealed → digest verification,
  including the 20-hour reminder cadence and expiry of a breached window.
- **Auth**: OTP lockout after five failures, lockout blocking re-request, suspicious-ingress detection
  on a changed device/IP/geo, password round-trip.
- **LLM seam** (`test_llm_gateway.py`): response parsing, usage accounting, refusal handling and
  error mapping against a stubbed SDK.

Manual verification in the running application confirmed: the counterparty link signing a deed with no
account, the seal turning green on the last signature, the witness being refused the download, the
3-page sealed PDF containing signer IPs and no raw Aadhaar, and the agent advancing a Paid agreement to
Pending_Signatures on a sweep.
