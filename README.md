# GoLegal

**A stamped, signed rental deed in ten minutes.** Draft on lawyer-vetted clauses, pay state stamp duty
online, and let every party sign with Aadhaar OTP from their own phone — in any order, from anywhere.
Valid in Indian courts under the Information Technology Act 2000, with a Section 65B evidentiary
certificate attached to every sealed deed.

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.63-FF4B4B.svg)](https://streamlit.io)
[![Tests](https://img.shields.io/badge/tests-126%20passing-brightgreen.svg)]()
[![Coverage](https://img.shields.io/badge/coverage-89%25-brightgreen.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Quickstart

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Open `http://localhost:8501`. Sign in with a demo persona (Account → Demo personas) or register.
Demo password: `GoLegal@123`.

**Optional — turn on Claude.** Everything works without it; the AI features fall back to deterministic
logic and say so.

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

```powershell
.\.venv\Scripts\pytest.exe -q tests/ --cov=services --cov=domain --cov=security --cov=ai
```

---

## What it does

**For the person renting or letting**

- Describe the tenancy in a sentence, paste an old agreement, upload a PDF, or fill the form. The draft fills itself.
- See the deed as it will be executed — rendered as e-Stamp paper, updating as you type.
- Get told, before you pay, whether the rent is fair for that locality and whether any clause is unfair or unenforceable.
- Pay once: state duty plus platform fee, itemised, with a GST invoice.
- Everyone signs from their own phone with Aadhaar OTP, in any order, over seven days.
- Download the sealed PDF with its Section 65B certificate — signer IPs, timestamps, signature hashes and a SHA-256 digest.

**For the platform operator**

- Live SHCIL prepaid treasury with a low-balance guard that refuses stamping rather than taking money it cannot fulfil.
- Funnel, revenue by state, median execution time, NPS with detractor root causes.
- An autonomous workflow agent that dispatches links, reminds daily, expires stale windows, seals on the last signature and purges unconsented drafts — with every run journaled.
- Append-only audit journal, stamping ledger and notification ledger.

---

## The agentic layer

Two agents, one guarded tool surface.

**Copilot** — a conversational assistant on every screen. With a model configured it runs a real
tool-use loop; without one it routes intents to the *same tools* deterministically. It can draft,
price, benchmark, review clauses, explain terms, summarise in Hindi or Kannada, track signatures and
re-send links.

**Workflow Agent** — autonomous lifecycle operator. It observes every active agreement, plans the
steps it intends to take, executes them through the same state machine a human uses, and journals the
run.

**What agents cannot do.** Payment, e-Stamp procurement and Aadhaar eSign are declared as `human`-tier
tools with **no handler**. The model can see them, so it knows to guide you to the right screen — but
there is no code path by which an agent performs a personal legal act. Agents also run under a
read-only mode when asked to, and any Aadhaar number a model supplies is stripped before it reaches
the draft.

See [`AGENTIC_GAP_ANALYSIS.md`](./AGENTIC_GAP_ANALYSIS.md) for the full design rationale.

---

## Architecture

Six layers. The agent layer sits *beside* the presentation layer, not above it — agents reach the same
application services through a declared tool registry, so their capabilities are a subset of a user's.

```
Presentation ──┐                    Agent layer ──┐
               ├── Security (CBAC, auth, PII) ────┤
               │                                  │
               └── Application services ──────────┘
                          │
                   Domain & documents
                          │
                   Data (3NF + append-only journals + blobs)
```

Full detail in [`ARCHITECTURE.md`](./ARCHITECTURE.md) and
[`SOFTWARE_DESIGN_DOCUMENT.md`](./SOFTWARE_DESIGN_DOCUMENT.md).

---

## Compliance invariants

| Invariant | Enforcement |
| :--- | :--- |
| Aadhaar never stored in full | One column, always `XXXXXXXX1234`; agent tools strip it; free text is redacted |
| No object accessed by raw id | HMAC-SHA256 capability tokens naming agreement, party, role and actions |
| Witnesses get no copy of the deed | Tokens downgraded to `COMPLETED_ACK` at sealing; excluded from workspace listings |
| Prices cannot be tampered with | Computed server-side from the persisted agreement |
| Stamping never over-draws | Balance pre-validated; refuses rather than failing after payment |
| Evidence is complete | Section 65B page with signer IPs, UTC timestamps, PKCS#7 hashes, content digest, corporate seal and event log |
| Zero document hoarding | Drafts without storage consent purged after 27 days by the agent sweep |
| Audit is append-only | `audit_logs`, `sysconfigTlb$jn`, `agent_runs` |

---

## Configuration

Everything is environment-driven; nothing security-sensitive is in source. See `config.py`.

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `DATABASE_URL` | `sqlite:///./golegal.db` | PostgreSQL in production |
| `GOLEGAL_CBAC_SECRET` | dev placeholder | **Rotate before deployment** — signs capability tokens |
| `GOLEGAL_DSC_SECRET` | dev placeholder | **Rotate before deployment** — corporate seal |
| `ANTHROPIC_API_KEY` | unset | Enables Claude; absent means deterministic fallback |
| `GOLEGAL_LLM_MODEL` | `claude-opus-5` | Model id |
| `GOLEGAL_PLATFORM_FEE` / `GOLEGAL_GST_RATE` | `299.0` / `0.18` | Pricing |
| `GOLEGAL_LOW_BALANCE_THRESHOLD` | `10000.0` | Treasury alert |
| `GOLEGAL_SIGNING_LINK_TTL_DAYS` | `7` | Signing window |
| `GOLEGAL_MOCK_GATEWAYS` | `true` | Sandbox SHCIL / UIDAI / payments |

---

## Scope

**Implemented**: the complete MVP1 consumer rental workflow, plus commercial lease and NDA templates,
contract ingestion, vernacular summaries, clause risk scoring, rent benchmarking and the agentic layer.

**Mocked**: SHCIL, UIDAI/ESP and the payment gateway are written as adapters with the real request and
response shapes; swapping in live clients is one class per gateway. The corporate seal is HMAC-SHA256
over a deterministic content digest — tamper-evident, but not a CA-issued PKCS#7 signature, which
requires an HSM-held X.509 key.

**Out of scope**: Sub-Registrar registration (not required for 11-month tenancies), the B2B API,
broker portal and property matching (PRD MVP2/MVP3).

---

## License

MIT.
