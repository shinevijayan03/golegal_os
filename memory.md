# GoLegal — Agent Context & Engineering Memory

```yaml
project: GoLegal — agentic digital contracting web application
jurisdiction: India (IT Act 2000 §§ 4, 5, 10A; Indian Evidence Act 1872 § 65B; Indian Stamp Act 1899)
stack:
  runtime: Python 3.12 (.venv)
  frontend: Streamlit 1.63 (custom design system via st.html)
  orm_db: SQLAlchemy 2.0, SQLite (golegal.db) / PostgreSQL 15 compatible
  documents: ReportLab 5, pypdf 6 (ingestion)
  ai: anthropic SDK 1.4 (claude-opus-5 by default), with a deterministic offline fallback
  tests: pytest 9 — 126 tests, 89% coverage
port: 8501
launch: .\.venv\Scripts\streamlit.exe run app.py --server.port 8501 --server.headless true
```

> [!IMPORTANT]
> **Read before any change**: [`GoLegal_Master_PRD_Context_v2 .md`](./GoLegal_Master_PRD_Context_v2%20.md)
> is the authoritative PRD / SAD. [`AGENTIC_GAP_ANALYSIS.md`](./AGENTIC_GAP_ANALYSIS.md) records what
> was wrong with the previous baseline and why each thing was built the way it is — it will save you
> from re-introducing a closed gap.

---

## 1. File map

```
golegal_app/
├── app.py                       router: product nav, or capability-link signing page
├── config.py                    ALL secrets, fees, thresholds, model settings (env-driven)
├── domain/models.py             17 entities: users, agreements, parties, estamps, signatures,
│                                payments, audit_logs, documents, otp_challenges, login_events,
│                                notifications, feedback, agent_runs, sysconfigTlb(+$jn)
├── persistence/database.py      engine, session_scope, additive migrations, demo seeding
├── security/
│   ├── cbac.py                  capability tokens, role→action map, witness downgrade
│   └── auth.py                  PBKDF2, DB-backed OTP + lockout, suspicious-ingress detection
├── services/
│   ├── validation.py            PAN/PIN/email/phone/Aadhaar + whole-payload validation
│   ├── rule_engine.py           9 states' stamp duty; statutory + optional clause library
│   ├── agreement_service.py     draft CRUD, party sync, ownership scoping, archive/restore
│   ├── payment_service.py       server-side quote, capture, numbered GST invoice PDF
│   ├── stamping_service.py      SHCIL procurement, prepaid ledger, low-balance guard
│   ├── esign_service.py         Aadhaar OTP challenge + signature rows (idempotent)
│   ├── notification.py          tokenized links, invitations, reminders, completion notices
│   ├── document_service.py      content-addressed PDF store, digest verification
│   ├── doc_assembly.py          e-Stamp page 1, Page X of Y, § 65B page, GST invoice
│   └── workflow_service.py      state machine, dispatch, seal, expire, purge, reminder sweep
├── ai/
│   ├── llm.py                   Anthropic gateway + NullLLMClient offline fallback
│   ├── tools.py                 tool registry — read | write | human tiers
│   ├── copilot.py               tool-use loop + deterministic rule router
│   ├── workflow_agent.py        observe → plan → act → journal; portfolio sweep
│   ├── clause_intelligence.py   risk scoring, PII redaction, plain/vernacular summaries
│   ├── contract_ingest.py       contract or brief → wizard payload
│   └── rent_benchmark.py        fair-rent bands, deposit norms, 7 cities
├── ui/                          theme, components, state + one module per screen
│   └── sign.py                  counterparty signing page (capability link, no account)
└── tests/                       126 tests across 11 modules
```

---

## 2. Invariants — do not break these

1. **Aadhaar is never stored raw.** One column, `parties.aadhaar_masked`, always `XXXXXXXX1234`. `mask_aadhaar()` is idempotent. Agent tools strip `aadhaar` from model-supplied parties. `redact_pii()` masks identity numbers found in free text before persistence.
2. **Agents cannot pay, stamp or sign.** Those tools are tier `human` with **no handler**. This is structural, not a prompt instruction. Never give them one.
3. **No raw UUID authorises anything.** Signing and download go through `CBACService.verify_token(token, agreement_id, action)`, which enforces the agreement match (IDOR) before the action check.
4. **Witness privacy.** After sealing, witness tokens are downgraded to `COMPLETED_ACK` in `seal_agreement()`. Witnesses never appear in `list_for_user()` results.
5. **Prices are computed server-side** from the persisted agreement. Never trust a client-supplied amount.
6. **The sealed PDF is generated once.** `seal_agreement()` returns stored bytes if the digest matches, which is what makes `final_pdf_sha256` a stable evidentiary reference.
7. **Every state change goes through `WorkflowService`,** so the state machine and the audit journal apply to humans and agents identically. Never assign `agreement.status` directly.
8. **Escape before rendering.** `_esc()` before ReportLab, `c.esc()` before HTML.
9. **Secrets come from `config.py`.** Nothing security-sensitive is hardcoded.
10. **Everything works offline.** No `ANTHROPIC_API_KEY` means the rule-based path; the entire test suite runs without one.

---

## 3. Things that will bite you

- **`st.markdown` breaks a `<style>` block.** Streamlit runs markdown over the string and terminates the HTML block, printing your CSS as text. Use `st.html()` — `ui/theme.py` does.
- **Heredocs mangle regex escapes.** Patching Python regexes through a bash heredoc turned `\b` into a literal backspace byte and silently broke intent routing. Use the Edit tool for anything containing backslashes.
- **Do not re-save a non-Draft agreement.** `AgreementService.save_draft()` refuses once the status leaves `Draft`; the checkout step must load the row instead. This caused a real post-payment crash.
- **The device fingerprint must be deterministic** (user agent + IP subnet). A random per-session id makes the suspicious-login detector fire on every visit.
- **OTP attempts carry across re-issued challenges.** Without this the lockout can be reset by requesting a new code.
- **F5 in an embedded browser may not reload Streamlit.** Navigate to the URL to force a fresh session when testing.

---

## 4. Commands

```powershell
.\.venv\Scripts\Activate.ps1

# tests (offline, no API key needed)
.\.venv\Scripts\pytest.exe -q tests/ --cov=services --cov=domain --cov=security --cov=ai

# run
.\.venv\Scripts\streamlit.exe run app.py --server.port 8501 --server.headless true

# enable Claude (optional; everything degrades gracefully without it)
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

Demo accounts (password `GoLegal@123`): `ramakiran.reddy@example.com` (owner),
`mayank.tripathi@example.com` (tenant), `admin@golegal.in` (operations).

---

## 5. Documentation

| Document | Contents |
| :--- | :--- |
| [`GoLegal_Master_PRD_Context_v2 .md`](./GoLegal_Master_PRD_Context_v2%20.md) | Authoritative PRD & SAD baseline |
| [`AGENTIC_GAP_ANALYSIS.md`](./AGENTIC_GAP_ANALYSIS.md) | What was missing, how each gap was closed, what remains |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | 6-layer model, trust boundaries, agent loop, lifecycle, deployment |
| [`SOFTWARE_DESIGN_DOCUMENT.md`](./SOFTWARE_DESIGN_DOCUMENT.md) | Domain model, CBAC, OTP, tool contract, assembly engine |
| [`UI_DESIGN_AND_INFO_ARCHITECTURE.md`](./UI_DESIGN_AND_INFO_ARCHITECTURE.md) | Design thesis, tokens, screens, components, a11y |
| [`TEST_STRATEGY_AND_PLAN.md`](./TEST_STRATEGY_AND_PLAN.md) | V&V plan and OWASP matrix |
| [`SYSTEM_TEST_CASES.md`](./SYSTEM_TEST_CASES.md) | Traceable test cases |
| [`DEPLOYMENT_PLAN.md`](./DEPLOYMENT_PLAN.md) | Containerisation, env vars, DR |
| [`USAGE_DOCUMENTATION.md`](./USAGE_DOCUMENTATION.md) | Persona manuals |
| [`DATASOURCE_PLAN.md`](./DATASOURCE_PLAN.md) | Schema and DDL |
| [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md), [`PRIORITIZED_EXECUTION_PLAN.md`](./PRIORITIZED_EXECUTION_PLAN.md), [`SMART_EVALUATION_CRITERIA.md`](./SMART_EVALUATION_CRITERIA.md) | Roadmap, backlog, rubric |
