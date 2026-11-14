# GoLegal vNext — Open Decisions Log (`docs/open_decisions.md`)

**Document Version:** 1.0.0  
**Date:** 13 November 2026  
**Audience:** Principal Systems Architect, Legal Content Reviewer, Security Auditor, CTO  
**Product Specification:** `GoLegal_Spec_Driven_Development_PRD_v1.md`  
**Governing Standard:** Antigravity Multi-Agent Engineering Governance (Phase 1 Deliverable)

---

## 1. Governance Principles for Open Decisions

In accordance with Section 11 & Section 12 of the GoLegal vNext PRD, the autonomous engineering swarm operates under strict **fail-closed, default-deny principles**:
1. **Never Invent Laws, Rules or Fees:** Where statutory rules or provider integrations are unconfirmed, the platform sets execution mode to `draft_only` or `blocked` and uses configurable administrator records.
2. **Never Fabricate Attestation or Signatures:** Electronic records produced by the system will generate cryptographic hash manifests and draft Section 63 manifests marked **"AWAITING HUMAN SIGNATORY / EXPERT REVIEW"**.
3. **Never Enable Third-Party AI by Default:** External model inference defaults to disabled (`AI_DISABLED`) until explicit per-organisation opt-in, purpose tracking, and data-use basis records are established.

---

## 2. Authoritative Open Decisions Register

| Decision ID | Domain / Scope | Question & Context | Proposed Safe Default Pending Sign-Off | Legal & Architectural Rationale | Audit & Traceability |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **OD-01** | **Initial Legal Templates** | Which template versions should be seeded for local staging and test validation? | Seed one **demonstration Karnataka Rental Agreement** (`tpl_ka_rental_v1`) and one **demonstration Mutual NDA** (`tpl_mutual_nda_v1`), both hard-coded with status `DRAFT_NOT_LEGAL_APPROVED`. | Prevents assuming legal validity from template title alone. Blocks `READY_FOR_EXECUTION` under `AT-02` with `422 LEGAL_ELIGIBILITY_UNVERIFIED`. | Traceable to `FR-02`, `AT-02`, `EligibilityRule`. |
| **OD-02** | **Jurisdiction Execution Mode** | How should state-dependent e-signing and registration eligibility be handled for Karnataka? | Default `EligibilityRule.execution_mode = draft_only` with `requires_stamping = True` and `requires_registration_review = True`. Execution transitions fail closed until legal sign-off. | 11-month residential tenancies require verified state stamp duty; Karnataka registration exemption requires specific legal counsel sign-off. | Traceable to `FR-02`, `FR-08`, `AT-06`. |
| **OD-03** | **eSign Provider Strategy** | How to handle multi-party electronic signing without live CCA/ESP credentials? | Provide an isolated `MockESignAdapter` returning status `MOCK_COMPLETED`. Prohibit displaying `EXECUTED` in mock mode. Live adapter interface (`LiveESignAdapter`) raises `PROVIDER_NOT_CONFIGURED`. | Meets Information Technology Act 2000 § 4/5/10A compliance without collecting or persisting real Aadhaar OTP or impersonating Certifying Authorities. | Traceable to `FR-07`, `AT-07`, `AT-17`. |
| **OD-04** | **Stamp Duty Calculation & Accounting** | What stamp duty fee schedule should be applied across jurisdictions? | All stamp duty amounts are retrieved from an explicit `StampRecord` or administrator-configured `EligibilityRule`. The engine never infers or hard-codes statutory fees. | Prevents misrepresenting statutory taxes or promising margin on government duties. Unverified stamp record blocks execution with `422`. | Traceable to `FR-08`, `AT-06`, `StampRecord`. |
| **OD-05** | **Commercial Pricing Model** | Should platform service fees be hardcoded (e.g. ₹500/₹299)? | Service fees are stored strictly in tenant/admin configuration (`platform_fee_paise` in INR integer paise) and rendered with GST itemization. No fee is inferred from unverified pitch deck figures. | Avoids unverified commercial assertions and ensures clean accounting auditability. | Traceable to `FR-03`, `FR-04`, `config.py`. |
| **OD-06** | **Third-Party AI & LLM Inference** | When should external LLMs (e.g. Claude/Anthropic) be invoked? | Default `AIProcessingPolicy.third_party_ai_enabled = False`. Native templates bypass AI completely (`AT-03`). Q&A returns `AI_DISABLED` under `AT-13` unless explicit org policy is set. Local embeddings run on host GPU. | Ensures zero PII leakage, zero document hoarding, and eliminates LLM prompt-injection risks (`AT-14`). | Traceable to `FR-14`, `FR-15`, `AT-13`, `AT-14`. |
| **OD-07** | **Data Residency & DPDP Compliance** | What data storage and retention parameters apply? | Production database and document storage default to Indian territory. Unexecuted drafts without storage consent purged automatically after 27 days (`AT-12`). | Aligns with Digital Personal Data Protection Act 2023 / 2025 Rules and CERT-In 180-day secure log retention guidelines. | Traceable to `NFR-01`, `FR-09`, `AuditEvent`. |
| **OD-08** | **BSA 2023 Section 63 Manifest** | What evidentiary certificate can software automatically issue? | The platform generates an immutable JSON/PDF hash manifest linking SHA-256 binary digests, timestamps, and audit event hashes. It is explicitly watermarked: **"DRAFT SECTION 63 MANIFEST — AWAITING HUMAN EXPERT/CUSTODIAN SIGN-OFF"**. | Software cannot legally attest personal knowledge or fabricate human expert certificates under Bharatiya Sakshya Adhiniyam 2023 §63. | Traceable to `FR-09`, `AT-09`, `AT-18`. |
| **OD-09** | **GPU Acceleration & Vision SLA** | What is the fallback if GPU CUDA is unavailable or during CPU testing? | Host machine has verified **NVIDIA GeForce RTX 3060 (12GB VRAM)**. Testing executes on `cuda` device. If no CUDA device is present in CI, fallback gracefully to CPU with telemetry logging, while maintaining $< 50.0\text{s}$ SLA on GPU. | Ensures maximum performance while guaranteeing build reliability across diverse developer workstations. | Traceable to `NFR-GPU`, `AT-11`. |
| **OD-10** | **Concurrent Session & Lockout** | How should concurrent edits and OTP rate-limiting be managed? | Use optimistic locking via integer `etag_version` on `Contract`. Return `409 Conflict` on mismatch. Enforce max 5 OTP attempts with 15-minute exponential backoff lockout. | Prevents state-machine race conditions and brute-force capability token discovery. | Traceable to `FR-01`, `FR-03`, `AT-05`. |

---

## 3. Human Review & Approval Gate

All above open decisions are locked with safe, defensive defaults. Any modification requires a formal Architecture Decision Record (ADR) approved by the human project sponsor.
