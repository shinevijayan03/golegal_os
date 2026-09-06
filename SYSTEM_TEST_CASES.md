# GoLegal Web Application - System Test Cases Matrix

> **Document Version**: 1.0 (Master Engineering Baseline)  
> **Status**: APPROVED SYSTEM VERIFICATION SPECIFICATION  
> **Traceability**: Mapped directly to PRD User Stories (US-01 to US-08) & OWASP Matrix  

---

## 1. Metadata Validation Test Cases (`TC-VAL`)

| Test ID | Test Title | Preconditions | Input Data | Execution Steps | Expected Outcome | Priority |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-VAL-01** | Valid PAN Format Validation | User on Step 2 | PAN: `ABCDE1234F` | Input PAN and trigger validation | System accepts input; field marks valid | P0 |
| **TC-VAL-02** | Invalid PAN Rejection | User on Step 2 | PAN: `12345ABCDE` | Input malformed PAN | Field highlights error: *"Invalid PAN format"* | P0 |
| **TC-VAL-03** | Indian PIN Code Validation | User on Step 2 | PIN: `560103` | Input valid 6-digit postal PIN | Validated successfully | P0 |
| **TC-VAL-04** | Invalid PIN Code Rejection | User on Step 2 | PIN: `012345` or `56010` | Input invalid PIN | Error: *"Invalid 6-digit postal code"* | P0 |
| **TC-VAL-05** | Strict Aadhaar Masking Enforcement | User on Step 2 | Raw Aadhaar: `123456789012` | Enter 12 digits | Ingested into memory, masked to `XXXXXXXX9012` | P0 |
| **TC-VAL-06** | Invalid Email Format | User on Step 2 | Email: `tenant@` | Enter malformed email | Rejects with format validation message | P1 |
| **TC-VAL-07** | Commercial Terms Bounds | User on Step 2 | Rent: `-500` or `0` | Enter zero or negative rent | Rejects with *"Rent must be $\ge$ ₹500"* | P0 |

---

## 2. Statutory Rule Engine Test Cases (`TC-RULE`)

| Test ID | Test Title | Preconditions | Input Data | Execution Steps | Expected Outcome | Priority |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-RULE-01** | Karnataka Residential Stamping Fee | State selected: KA | Agreement: Residential 11 Mo | Query rule engine | Returns exact statutory duty: ₹100.00 | P0 |
| **TC-RULE-02** | Maharashtra Leave & License Fee | State selected: MH | Rent: ₹30,000, Deposit: ₹1.5L | Query rule engine | Computes 0.25% consideration value | P1 |
| **TC-RULE-03** | Delhi NCR Duty Rate | State selected: DL | Agreement: Residential 11 Mo | Query rule engine | Returns statutory duty: ₹100.00 | P1 |
| **TC-RULE-04** | Mandatory Statutory Clause Protection | User on Step 3 | Attempt deletion of statutory clause | Inspect editor state | Non-derogable legal clause cannot be purged | P0 |

---

## 3. Mock SHCIL e-Stamp Stamping Test Cases (`TC-STAMP`)

| Test ID | Test Title | Preconditions | Input Data | Execution Steps | Expected Outcome | Priority |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-STAMP-01** | Successful e-Stamp Procurement | Prepaid Balance: ₹50,000 | State: KA, Duty: ₹100.00 | Invoke purchase API | Debits ₹100; returns cert `IN-KA...` | P0 |
| **TC-STAMP-02** | Low-Balance Threshold Alert | Prepaid Balance: ₹10,050 | State: KA, Duty: ₹100.00 | Invoke purchase API | Balance reaches ₹9,950; triggers `< ₹10,000` alert | P0 |
| **TC-STAMP-03** | Exhausted Balance Rejection | Prepaid Balance: ₹50.00 | State: KA, Duty: ₹100.00 | Invoke purchase API | Transaction halted; returns `Insufficient Funds` | P0 |
| **TC-STAMP-04** | Prepaid Stamping Top-Up | Admin Console | Top-up: ₹25,000 | Admin submits top-up | Balance increments; journals `sysconfigTlb$jn` | P1 |

---

## 4. Mock UIDAI Aadhaar eSign Test Cases (`TC-ESIGN`)

| Test ID | Test Title | Preconditions | Input Data | Execution Steps | Expected Outcome | Priority |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-ESIGN-01** | Valid Aadhaar OTP Verification | eSign modal open | OTP: `123456` (Mock Valid) | Submit OTP | Verifies identity; issues PKCS#7 hash stamp | P0 |
| **TC-ESIGN-02** | Invalid Aadhaar OTP Rejection | eSign modal open | OTP: `999999` (Incorrect) | Submit OTP | Rejection: *"Invalid OTP. 2 attempts remaining."* | P0 |
| **TC-ESIGN-03** | Rate Limit Lockout | 5 failed attempts | OTP: `000000` 6 times | Attempt 6th failure | Lockout triggered; returns 429 Too Many Requests | P1 |
| **TC-ESIGN-04** | Aadhaar Consent Disclaimer Check | eSign modal open | Uncheck consent box | Attempt submit | Prevent submission until consent is acknowledged | P0 |

---

## 5. Multi-Party Asynchronous Signing Test Cases (`TC-WORKFLOW`)

| Test ID | Test Title | Preconditions | Input Data | Execution Steps | Expected Outcome | Priority |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-WORKFLOW-01** | Initiator First Signing | Agreement: `Paid` | Initiator executes eSign | Submit valid OTP | Party marked `Signed`; status $\rightarrow$ `Pending_Signatures` | P0 |
| **TC-WORKFLOW-02** | Asynchronous Sign Order Independence | 1 Owner, 2 Tenants, 1 Witness | Tenant 2 signs before Tenant 1 | Sign via token | Signatures recorded without requiring sequential order | P0 |
| **TC-WORKFLOW-03** | Atomic Final Document Sealing | 1 pending witness left | Final witness submits OTP | Verify agreement state | Status atomically switches to `Completed`; DSC sealed | P0 |
| **TC-WORKFLOW-04** | Multi-Tenant Concurrency | 2 Co-tenants signing simultaneously | Concurrent OTP submissions | Wrapped in DB row lock | Both signatures captured without race conditions | P1 |
| **TC-WORKFLOW-05** | Expiration Window Enforcement | Agreement pending > 7 days | Trigger reminder scheduler | Check agreement status | Status marks `Expired`; sign links invalidated | P1 |

---

## 6. Document Assembly & Section 65B Integrity (`TC-DOC`)

| Test ID | Test Title | Preconditions | Input Data | Execution Steps | Expected Outcome | Priority |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-DOC-01** | Page 1 Official e-Stamp Header | Agreement paid | Merged PDF generated | Inspect Page 1 layout | Features StockHolding seal, cert code, duty amount | P0 |
| **TC-DOC-02** | Dynamic Continuous Pagination | Multi-page agreement | 4-page contract body | Inspect page footers | Renders `Page 1 of 5`, `Page 2 of 5`, ..., `Page 5 of 5` | P0 |
| **TC-DOC-03** | Section 65B Certificate Inclusion | Agreement completed | Inspect terminal page | Verify certificate | Contains IP audit, timestamp, and SHA-256 hashes | P0 |
| **TC-DOC-04** | SHA-256 Tamper-Evidence | Completed PDF generated | Modify 1 character in PDF bytes | Recompute SHA-256 | Hash mismatch detected; document flagged as tampered | P0 |

---

## 7. OWASP & Capability-Based Access Control (`TC-SEC`)

| Test ID | Test Title | Preconditions | Input Data | Execution Steps | Expected Outcome | Priority |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-SEC-01** | IDOR Horizontal Escalation Guard | Token for Agreement A | Request Agreement B endpoint | Submit request | Rejection: 403 Forbidden / Invalid Capability | P0 |
| **TC-SEC-02** | Witness Privacy Policy Post-Sign | Witness signed contract | Witness attempts PDF view | Submit request | Access denied: Witness token downgraded | P0 |
| **TC-SEC-03** | SQL Injection in Search Parameters | User on Dashboard | Query: `' UNION SELECT *--` | Submit search | Safely escaped by ORM; zero injection | P0 |
| **TC-SEC-04** | Stored XSS in Custom Clauses | User on Step 3 | `<script>alert('XSS')</script>` | Save clause | HTML escaped in view and stripped in PDF builder | P0 |
| **TC-SEC-05** | Storage Consent vs 27-Day Purge | Draft created with consent=False | Advance clock by 28 days | Run purge job | Draft purged from database and temporary store | P1 |
