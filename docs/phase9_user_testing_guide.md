# PHASE 9 GUIDE: GOLEGAL OS INTERACTIVE TESTING CHEAT-SHEET

## 1. Application Access
- **Local Web URL:** [http://localhost:8501](http://localhost:8501)
- **Status:** **LIVE (HTTP 200 OK)**
- **Hardware Acceleration:** NVIDIA GeForce RTX 3060 (12GB VRAM, CUDA 13.3)
- **Design System:** Executive Crimson Red (`#D32F2F`) & Vibrant Orange (`#FF6D00`) High-Contrast Dark Theme

---

## 2. Multi-Tenant Roster & Personas (Top Bar Switcher)

Switch tenants and persona roles using the dropdowns in the top bar:

### Tenant A: `Acme Logistics Pvt. Ltd.` (`org-alpha-101`)
| Role Persona | Synthetic User ID | Name | Governance Scope |
| :--- | :--- | :--- | :--- |
| **Owner** | `usr-alice-01` | Alice Sharma | Full administrative authority & review sign-off |
| **Editor** | `usr-edward-01` | Edward D'Souza | Contract drafting, field updates, camera uploads |
| **Approver** | `usr-arthur-01` | Arthur Pendelton | Review sign-off & statutory approval |
| **Signer** | `usr-signer-01` | Signer A | Counterparty digital signatory |
| **Legal Admin** | `usr-legal-01` | Advocate Mehra | Template catalog rules & statutory eligibility |
| **Operator** | `usr-op-01` | DevOps Engineer | Hardware intake & treasury stamp processing |

### Tenant B: `Starlight Retail Ventures` (`org-beta-202`)
| Role Persona | Synthetic User ID | Name | Governance Scope |
| :--- | :--- | :--- | :--- |
| **Owner** | `usr-bob-01` | Bob Henderson | Isolated tenant owner |
| **Editor** | `usr-elena-01` | Elena Rostova | Isolated tenant editor |
| **Approver** | `usr-beverly-01` | Beverly Marsh | Isolated tenant approver |

---

## 3. Step-by-Step Interactive Testing Walkthrough

### Step 1: Legal Catalog & Statutory Guardrails
- **Tab:** `📜 Legal Catalog & Rules`
- **Actions:**
  1. Inspect `Karnataka Residential Rental Agreement` (`tpl_ka_rental_v1`).
  2. Observe the prominent amber banner: `DRAFT_NOT_LEGAL_APPROVED`.
  3. Verify that execution mode defaults strictly to `draft_only`.
  4. (Optional) Switch role to `legal_admin` to modify the execution mode to `provider_allowed`.

### Step 2: Guided Contract Wizard & Live Document Assembly
- **Tab:** `📝 Guided Contract Wizard`
- **Actions:**
  1. Select template `tpl_ka_rental_v1`.
  2. **Test Real-Time Validation:** Change `Expiration Date` to be earlier than `Commencement Date`. Observe instant red alert: `422 DATE_ORDER_INVALID: end_date must be strictly after start_date`.
  3. **Test Deterministic PII Checklist:** Enter `Tenant Aadhaar is 4912 3456 7890` into the covenants box. Save draft and observe the lawyer-authored checklist alert: `[RULE-PII-01] CRITICAL: Raw 12-digit Aadhaar number detected. Must be masked.`
  4. Click `📥 Download Watermarked Draft PDF` to inspect the generated legal deed with its semi-transparent 45° `"DRAFT — NOT EXECUTED"` watermark and cryptographic SHA-256 seal.

### Step 3: Review Console, Diffs & Submitter Self-Approval Block
- **Tab:** `🔍 Review & Sign-Off`
- **Actions:**
  1. Select contract `Commercial Lease - Indiranagar Tech Park Unit 4B` (submitted by Editor Edward).
  2. **Test Self-Approval Block (FR-06):** In the top bar, set role to `Editor`. Observe the red banner: `SELF-APPROVAL FORBIDDEN: Submitter cannot approve their own submission.` The `✅ Approve` button is disabled.
  3. **Approve Contract:** Switch role to `Approver` in the top bar. Click `✅ Approve`. Observe status transition to `APPROVED`.
  4. **Test Approval Invalidation (AT-05):** Expand `Modify Fields`, change Monthly Rent, and click `Apply Field Edit`. Observe that `etag_version` increments, prior approvals are wiped, and contract status immediately resets to `DRAFT`.

### Step 4: Stamping Duty Gate & Mock eSign Ceremony
- **Tab:** `⚖️ Stamping & eSign`
- **Actions:**
  1. Observe the pre-execution gates. Gate 2 blocks execution with `422 STAMP_UNVERIFIED` if Karnataka stamp duty is unrecorded.
  2. Fill out the `Record Karnataka e-Stamp Certificate` form (Duty: ₹500, Jurisdiction: KA) and click `Verify & Attach e-Stamp Certificate`.
  3. Click `🚀 Advance to READY_FOR_EXECUTION`.
  4. Click `🔏 Sign with Mock eSign Provider`.
  5. **Verify Invariant (AT-07):** Observe that the contract badge updates strictly to `MOCK_COMPLETED` (never `EXECUTED`).

### Step 5: GPU Camera Intake Lab & Blur Quality Gate
- **Tab:** `📷 GPU Camera Lab`
- **Actions:**
  1. Click `📸 Ingest Sharp Camera Scan`. Observe high sharpness score ($\ge 0.75$), side-by-side deskewed comparison, and GPU stage timing breakdown ($214.9\text{ms} \ll 50.0\text{s}$ SLA).
  2. Click `⚠️ Ingest Blurred Camera Scan`. Observe that image variance $< 0.75$ triggers the **Quality Gate Alert (AT-11)**: frame is flagged `needs_manual_review` and auto-commit is blocked.
  3. In the `Human-in-the-Loop Review Queue`, click `Accept Candidate` on a proposed date candidate. Observe that the downstream statutory reminder is scheduled only after explicit human confirmation (`AT-12`).

### Step 6: Cryptographic Audit Trail & BSA 2023 §63 Vault
- **Tab:** `🛡️ Audit & BSA §63 Vault`
- **Actions:**
  1. Explore the hash-chain nodes where each event is cryptographically linked via $H_n = \text{SHA256}(H_{n-1} \parallel \text{payload})$.
  2. Click `🚨 Simulate 1-Byte Document Tamper`. Observe the immediate fail-closed security defense: `422 TAMPER_DETECTED: SHA-256 hash mismatch! Document integrity violated.` (`AT-09`).
  3. Click `📥 Download BSA §63 Draft Manifest (.json)` to inspect the legal evidentiary certificate marked `"AWAITING HUMAN SIGNATORY / EXPERT REVIEW"` (`AT-18`).
