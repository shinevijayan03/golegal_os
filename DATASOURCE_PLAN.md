# GoLegal Web Application - Datasource & Persistence Plan

> **Document Version**: 1.0 (Master Engineering Baseline)  
> **Status**: APPROVED ARCHITECTURAL SPECIFICATION  
> **Database Engines**: SQLite 3 (Local Development & Staging) / PostgreSQL 15+ (Production Enterprise)  
> **ORM Layer**: SQLAlchemy 2.0+ (Declarative 3NF Models with JSON support)  

---

## 1. Entity-Relationship Architecture (3NF Normalization)

The GoLegal persistence architecture isolates entities into Third Normal Form (3NF) relational tables, while selectively utilizing dynamic JSON/JSONB document attributes for variable legal covenants, property inventories, and telemetry payloads.

```mermaid
erDiagram
    USERS ||--o{ AGREEMENTS : initiates
    USERS ||--o{ AUDIT_LOGS : triggers
    AGREEMENTS ||--|{ PARTIES : binds
    AGREEMENTS ||--o| ESTAMPS : secures
    AGREEMENTS ||--o{ SIGNATURES : authenticates
    AGREEMENTS ||--o| PAYMENTS : settles
    AGREEMENTS ||--o{ AUDIT_LOGS : generates
    PARTIES ||--o{ SIGNATURES : affixes

    USERS {
        TEXT id PK "UUID string"
        TEXT user_type "Single_User, Multi_User, Hybrid_User, Admin"
        TEXT full_name "Legal individual or corporate name"
        TEXT email "Unique contact email address"
        TEXT phone "E.164 phone number"
        TEXT address "Permanent postal address"
        TIMESTAMP created_at "Account creation UTC timestamp"
        TIMESTAMP updated_at "Profile last modified UTC"
    }

    AGREEMENTS {
        TEXT id PK "UUID string"
        TEXT initiator_id FK "References users(id)"
        TEXT agreement_type "Rental_Residential, Rental_Commercial, NDA, Lease, Custom"
        TEXT state_code "ISO state code (KA, DL, MH, etc.)"
        TEXT status "Draft, Paid, Pending_Signatures, Completed, Cancelled, Expired"
        JSON property_details "Premises, fittings, inventory"
        JSON commercial_terms "Rent, deposit, due date, escalation %"
        TEXT custom_clauses "Customized legal clauses text"
        TEXT final_pdf_url "Local path or S3 URL of certified PDF"
        BOOLEAN cloud_storage_consent "Indefinite AES-256 storage vs 27d purge"
        TIMESTAMP created_at "Draft initiation UTC"
        TIMESTAMP executed_at "Final DSC sealing UTC timestamp"
    }

    PARTIES {
        TEXT id PK "UUID string"
        TEXT agreement_id FK "References agreements(id)"
        TEXT party_type "Owner, Tenant, Witness"
        TEXT full_name "Full legal name as per government ID"
        TEXT email "Signatory email address"
        TEXT phone "Signatory mobile phone number"
        TEXT aadhaar_masked "Masked identifier: XXXXXXXX1234"
        TEXT signing_status "Pending, Sent, Signed, Rejected"
        TEXT access_token "Cryptographically secure capability token"
        TIMESTAMP access_token_expires_at "Token expiry timestamp"
        TIMESTAMP created_at "Party record creation timestamp"
    }

    ESTAMPS {
        TEXT id PK "UUID string"
        TEXT agreement_id FK "Unique 1-to-1 references agreements(id)"
        TEXT certificate_number "Official SHCIL certificate code (IN-KA...)"
        TEXT state_code "State jurisdiction code"
        REAL stamp_amount "Duty consideration value (e.g. 100.00)"
        TEXT purchased_by "First Party / Purchaser identifier"
        TEXT vendor "StockHolding, StateTreasury_Direct, Mock_Sandbox"
        TIMESTAMP issued_at "Certificate generation timestamp"
        TEXT certificate_url "Certificate PDF artifact path"
    }

    SIGNATURES {
        TEXT id PK "UUID string"
        TEXT agreement_id FK "References agreements(id)"
        TEXT party_id FK "References parties(id)"
        TEXT auth_type "Aadhaar_OTP, Biometric, DSC_Hardware, Internal_DSC"
        TEXT transaction_ref "External gateway transaction ID"
        TEXT cert_issuer "CCA accredited CA (NSDL, eMudhra, GoLegal)"
        TEXT signature_hash "SHA-256 digest / PKCS#7 container hash"
        TIMESTAMP signed_at "Aadhaar verification timestamp (IST/UTC)"
        TEXT ip_address "Originating network client IP address"
        TEXT user_agent "Client browser / device user-agent string"
    }

    PAYMENTS {
        TEXT id PK "UUID string"
        TEXT agreement_id FK "References agreements(id)"
        REAL total_amount "Total charged amount (INR)"
        REAL stamp_duty_amount "Government statutory duty (INR)"
        REAL platform_fee "GoLegal service fee + GST (INR)"
        TEXT payment_gateway "Razorpay, Cashfree, Mock_Sandbox"
        TEXT gateway_payment_id "External transaction reference"
        TEXT status "Pending, Success, Failed, Refunded"
        TEXT invoice_pdf_url "Signed GST tax invoice artifact path"
        TIMESTAMP created_at "Payment processing timestamp"
    }

    AUDIT_LOGS {
        TEXT id PK "UUID string"
        TEXT agreement_id FK "References agreements(id)"
        TEXT event_type "DRAFT_SAVED, PAYMENT_CAPTURED, STAMP_ACQUIRED, PARTY_SIGNED, DSC_SEALED"
        TEXT triggered_by "User ID, Party ID, System Worker, Gateway Webhook"
        JSON event_data "Diagnostic parameters, SHA-256 hashes, network IPs"
        TIMESTAMP recorded_at "Append-only immutable timestamp"
    }
```

---

## 2. Relational Data Definition Language (SQLite & PostgreSQL DDL)

### 2.1 SQLite DDL (Development & Staging Implementation)

```sql
-- Enforce Foreign Key Integrity
PRAGMA foreign_keys = ON;

-- 1. Users Master Table
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    user_type TEXT NOT NULL CHECK (user_type IN ('Single_User', 'Multi_User', 'Hybrid_User', 'Admin')),
    full_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    phone TEXT NOT NULL,
    address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Agreements Master Table
CREATE TABLE IF NOT EXISTS agreements (
    id TEXT PRIMARY KEY,
    initiator_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agreement_type TEXT NOT NULL CHECK (agreement_type IN ('Rental_Residential', 'Rental_Commercial', 'NDA', 'Lease', 'Custom')),
    state_code TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Draft' CHECK (status IN ('Draft', 'Paid', 'Pending_Signatures', 'Completed', 'Cancelled', 'Expired')),
    property_details TEXT NOT NULL, -- JSON serialized string
    commercial_terms TEXT NOT NULL, -- JSON serialized string
    custom_clauses TEXT,
    final_pdf_url TEXT,
    cloud_storage_consent INTEGER NOT NULL DEFAULT 1, -- 1=True, 0=False
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agreements_initiator ON agreements(initiator_id);
CREATE INDEX IF NOT EXISTS idx_agreements_status ON agreements(status);

-- 3. Parties / Signatories Table
CREATE TABLE IF NOT EXISTS parties (
    id TEXT PRIMARY KEY,
    agreement_id TEXT NOT NULL REFERENCES agreements(id) ON DELETE CASCADE,
    party_type TEXT NOT NULL CHECK (party_type IN ('Owner', 'Tenant', 'Witness')),
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL,
    aadhaar_masked TEXT, -- Stored strictly as XXXXXXXX1234
    signing_status TEXT NOT NULL DEFAULT 'Pending' CHECK (signing_status IN ('Pending', 'Sent', 'Signed', 'Rejected')),
    access_token TEXT UNIQUE,
    access_token_expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_parties_agreement ON parties(agreement_id);
CREATE INDEX IF NOT EXISTS idx_parties_token ON parties(access_token);

-- 4. e-Stamps Records Table
CREATE TABLE IF NOT EXISTS estamps (
    id TEXT PRIMARY KEY,
    agreement_id TEXT UNIQUE NOT NULL REFERENCES agreements(id) ON DELETE CASCADE,
    certificate_number TEXT UNIQUE NOT NULL,
    state_code TEXT NOT NULL,
    stamp_amount REAL NOT NULL,
    purchased_by TEXT NOT NULL,
    vendor TEXT NOT NULL DEFAULT 'StockHolding',
    issued_at TIMESTAMP NOT NULL,
    certificate_url TEXT NOT NULL
);

-- 5. Digital Signatures Audit Table
CREATE TABLE IF NOT EXISTS signatures (
    id TEXT PRIMARY KEY,
    agreement_id TEXT NOT NULL REFERENCES agreements(id) ON DELETE CASCADE,
    party_id TEXT NOT NULL REFERENCES parties(id) ON DELETE CASCADE,
    auth_type TEXT NOT NULL CHECK (auth_type IN ('Aadhaar_OTP', 'Biometric', 'DSC_Hardware', 'Internal_DSC')),
    transaction_ref TEXT NOT NULL,
    cert_issuer TEXT NOT NULL,
    signature_hash TEXT NOT NULL,
    signed_at TIMESTAMP NOT NULL,
    ip_address TEXT NOT NULL,
    user_agent TEXT
);

CREATE INDEX IF NOT EXISTS idx_signatures_agreement ON signatures(agreement_id);
CREATE INDEX IF NOT EXISTS idx_signatures_party ON signatures(party_id);

-- 6. Payments & Invoices Table
CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY,
    agreement_id TEXT NOT NULL REFERENCES agreements(id) ON DELETE CASCADE,
    total_amount REAL NOT NULL,
    stamp_duty_amount REAL NOT NULL,
    platform_fee REAL NOT NULL,
    payment_gateway TEXT NOT NULL,
    gateway_payment_id TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('Pending', 'Success', 'Failed', 'Refunded')),
    invoice_pdf_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_payments_agreement ON payments(agreement_id);

-- 7. Section 65B Evidentiary Audit Trail (Append-Only)
CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    agreement_id TEXT NOT NULL REFERENCES agreements(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    triggered_by TEXT NOT NULL,
    event_data TEXT NOT NULL, -- JSON serialized string
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_agreement ON audit_logs(agreement_id);

-- 8. Platform System Configuration Table (sysconfigTlb)
CREATE TABLE IF NOT EXISTS sysconfigTlb (
    id TEXT PRIMARY KEY DEFAULT 'GLOBAL_CONFIG',
    lang TEXT NOT NULL DEFAULT 'en',
    dig_sign TEXT NOT NULL DEFAULT 'Aadhaar_eSign',
    estamp INTEGER NOT NULL DEFAULT 1,
    estamp_vendor TEXT NOT NULL DEFAULT 'StockHolding',
    currency TEXT NOT NULL DEFAULT 'INR',
    system_commission REAL NOT NULL DEFAULT 18.0,
    discount REAL NOT NULL DEFAULT 0.0,
    country TEXT NOT NULL DEFAULT 'IND',
    data_pruning_days INTEGER NOT NULL DEFAULT 27,
    agreement_retain_days INTEGER NOT NULL DEFAULT 2920,
    stockholding_prepaid_balance REAL NOT NULL DEFAULT 50000.0,
    low_balance_threshold REAL NOT NULL DEFAULT 10000.0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 9. Append-Only System Configuration Audit Journal (sysconfigTlb$jn)
CREATE TABLE IF NOT EXISTS "sysconfigTlb$jn" (
    jn_id TEXT PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    operation TEXT NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    updated_by_user TEXT NOT NULL,
    previous_value TEXT, -- JSON snapshot of old state
    new_value TEXT NOT NULL -- JSON snapshot of new state
);
```

---

## 3. Dynamic JSON Schemas (Covenants & Audit Payloads)

### 3.1 `property_details` JSON Schema
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "PropertyDetails",
  "type": "object",
  "required": ["address_line1", "city", "state", "pincode", "property_type"],
  "properties": {
    "premises_name": { "type": "string" },
    "address_line1": { "type": "string" },
    "address_line2": { "type": "string" },
    "city": { "type": "string" },
    "state": { "type": "string" },
    "pincode": { "type": "string", "pattern": "^[1-9][0-9]{5}$" },
    "property_type": { "type": "string", "enum": ["Apartment", "Independent_House", "Villa", "Commercial_Office"] },
    "bedroom_count": { "type": "integer", "minimum": 1 },
    "bathroom_count": { "type": "integer", "minimum": 1 },
    "parking_slots": { "type": "integer", "minimum": 0 },
    "fittings_and_fixtures": {
      "type": "array",
      "items": { "type": "string" }
    },
    "keys_handed_over": { "type": "integer", "minimum": 1 }
  }
}
```

### 3.2 `commercial_terms` JSON Schema
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "CommercialTerms",
  "type": "object",
  "required": ["monthly_rent", "security_deposit", "lease_period_months", "rent_commencement_date", "rent_due_day"],
  "properties": {
    "monthly_rent": { "type": "number", "minimum": 500 },
    "security_deposit": { "type": "number", "minimum": 0 },
    "maintenance_charges": { "type": "number", "minimum": 0 },
    "lease_period_months": { "type": "integer", "default": 11 },
    "lock_in_period_months": { "type": "integer", "default": 1 },
    "rent_commencement_date": { "type": "string", "format": "date" },
    "rent_due_day": { "type": "integer", "minimum": 1, "maximum": 31, "default": 5 },
    "notice_period_days": { "type": "integer", "default": 30 },
    "annual_escalation_pct": { "type": "number", "default": 5.0 },
    "payment_mode": { "type": "string", "enum": ["UPI", "Bank_NEFT_IMPS", "Cash"] }
  }
}
```

### 3.3 `audit_logs.event_data` JSON Schema
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AuditEventData",
  "type": "object",
  "required": ["action", "status", "client_ip"],
  "properties": {
    "action": { "type": "string" },
    "status": { "type": "string", "enum": ["SUCCESS", "FAILURE", "WARNING"] },
    "client_ip": { "type": "string" },
    "user_agent": { "type": "string" },
    "document_sha256": { "type": "string" },
    "gateway_payload": { "type": "object" },
    "diagnostic_message": { "type": "string" }
  }
}
```

---

## 4. Evidentiary Cloud Storage Consent & Data Retention

### 4.1 Storage Consent Governance
1. **Explicit Cloud Storage Consent**: If `cloud_storage_consent == 1` (True), the final signed PDF and Section 65B certificate are archived indefinitely in AES-256 encrypted object storage for user access, tax filing, and dispute resolution.
2. **Zero Document Hoarding Policy**: If `cloud_storage_consent == 0` (False), drafts and uncompleted files are scheduled for automatic purge after `sysconfigTlb.data_pruning_days` (default 27 days).
3. **Sensitive Identifier Redaction**:
   - Aadhaar numbers are never stored in plain text.
   - The system strictly enforces regular expression masking to `XXXXXXXX1234` prior to writing to the `parties.aadhaar_masked` column.
   - Any raw Aadhaar passed in memory for mock UIDAI OTP validation is purged from heap space immediately following verification.

---

## 5. StockHolding Prepaid Balance Ledger Mechanics

To prevent transaction failures due to exhausted state stamping funds, the platform maintains a synchronized ledger within `sysconfigTlb`:
- **Real-Time Debit**: Upon calling the SHCIL e-Stamp issuance service, the statutory duty amount (e.g. ₹100) + platform fee is debited from `stockholding_prepaid_balance`.
- **Low-Balance Guard**: If `stockholding_prepaid_balance < low_balance_threshold` (₹10,000), the system generates an urgent visual alert in the Admin Console and dispatches an automated alert to finance administrators.
- **Audit Logging**: Every debit or top-up event records a full immutable entry in `sysconfigTlb$jn`.
