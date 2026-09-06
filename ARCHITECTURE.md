# GoLegal Web Application - System Architecture Document

> **Document Version**: 1.0 (Master Engineering Baseline)  
> **Status**: APPROVED ARCHITECTURAL SPECIFICATION  
> **Framework**: 5-Layer Decoupled Enterprise Model & Tiered Network Security Topology  
> **Jurisdiction Compliance**: India Region Localization (IT Act 2000, Indian Evidence Act 1872)  

---

## 1. 5-Layer Enterprise Architectural Model

The GoLegal system architecture decouples responsibilities across five distinct layers, ensuring horizontal scalability, zero lateral movement in security breaches, and modular testability.

```mermaid
graph TD
    classDef pres fill:#D4E6F1,stroke:#2980B9,stroke-width:2px;
    classDef srv fill:#D5F5E3,stroke:#27AE60,stroke-width:2px;
    classDef sec fill:#FCF3CF,stroke:#F39C12,stroke-width:2px;
    classDef biz fill:#E8DAEF,stroke:#8E44AD,stroke-width:2px;
    classDef data fill:#FADBD8,stroke:#C0392B,stroke-width:2px;

    subgraph Presentation_Layer ["1. Presentation Layer (Streamlit Frontend)"]
        UI["Multi-Page Web UI Components"]:::pres
        DocRender["Dynamic Split-Pane Clause & PDF Preview"]:::pres
        WorkflowUI["Interactive 5-Step Guided Wizard & Dashboard"]:::pres
        AdminConsole["Admin Stamping Ledger & Analytics Console"]:::pres
    end

    subgraph Services_Layer ["2. Services Layer (API & Communications)"]
        APIGateway["REST & Session Controller Gateway"]:::srv
        WebServers["Web Server Cluster & Request Router"]:::srv
        NotificationEng["Multi-Party Notification Dispatch (SMS, WhatsApp, Email)"]:::srv
        SecFilter["WAF Rules & Parameter Sanitization Filters"]:::srv
    end

    subgraph Security_Layer ["3. Security Layer (Capability-Based Access Control)"]
        AccessControl["CBAC Token Policy & Cryptographic Verification"]:::sec
        AuthAudit["Authentication & Security Ingress Auditing"]:::sec
        ResManager["Resource Gate & IDOR Prevention Shield"]:::sec
    end

    subgraph Business_Layer ["4. Business Layer (Domain & Orchestration)"]
        WorkflowEng["Declarative Signing State Machine Engine"]:::biz
        ComplianceEng["Statutory Stamp & Legal Rules Compliance Engine"]:::biz
        DocMerger["Document Assembly & Headless PDF Merger Engine"]:::biz
        CryptoSeal["SHA-256 Digest & X.509 PKCS#7 Sealing Engine"]:::biz
        EventMgmt["Section 65B Event & Audit Trail Publisher"]:::biz
        AsyncScheduler["Daily Reminder Scheduler & Retry Queue"]:::biz
    end

    subgraph Data_Layer ["5. Data Layer (Relational 3NF & Object Store)"]
        TxDB[("Primary 3NF Transactional Database<br/>(SQLite / PostgreSQL)")]:::data
        AuditDB[("Append-Only Audit Journal Tables<br/>(audit_logs, sysconfigTlb$jn)")]:::data
        DocStore[("Encrypted Document Store (AES-256)<br/>(Drafts, Certificates, Final Contracts)")]:::data
    end

    Presentation_Layer --> Services_Layer
    Services_Layer --> Security_Layer
    Security_Layer --> Business_Layer
    Business_Layer --> Data_Layer
```

---

## 2. 4-Tier Enterprise Architecture & External Trust Services

The application interacts with external government and banking trust utilities via strict gateway adapters:

```mermaid
flowchart TD
    subgraph PresentationTier["Presentation Tier"]
        A1["Streamlit Responsive Web App (Desktop / Mobile)"]
        A2["Split-Screen Live Clause Diff Viewer"]
    end

    subgraph ServicesSecurityTier["Services & Security Tier"]
        B1["Session State & Request Controllers"]
        B2["CBAC Capability Token Validator"]
        B3["WAF & Input Sanitization Layer"]
    end

    subgraph BusinessTier["Business & Orchestration Tier"]
        C1["Statutory Rule Engine (State Duties)"]
        C2["Asynchronous Multi-Party Signing Orchestrator"]
        C3["Document Assembly & PDF Cryptographic Sealer"]
        C4["GST Invoice Generation Engine"]
    end

    subgraph DataTier["Data Tier (India Region)"]
        D1[("SQLite / PostgreSQL 3NF DB")]
        D2[("Append-Only Evidentiary Audit Journal")]
        D3[("AES-256 Encrypted PDF Document Store")]
    end

    subgraph ExternalTrustServices["External Trust Services Tier"]
        E1["SHCIL e-Stamp Paper API & Prepaid Balance"]
        E2["UIDAI / Licensed ESP Aadhaar eSign Gateway"]
        E3["Razorpay / Cashfree Payment Gateway"]
        E4["Transactional SMS & WhatsApp Delivery Service"]
    end

    PresentationTier --> ServicesSecurityTier
    ServicesSecurityTier --> BusinessTier
    BusinessTier --> DataTier

    C1 <--> E1
    C2 <--> E2
    C4 <--> E3
    BusinessTier <--> E4
```

---

## 3. Tiered Network Perimeter & DMZ Security Topology

Infrastructure security prevents unauthorized lateral traversal through four isolated operational zones:

```mermaid
flowchart TD
    subgraph Clients["1. Client Ingress Layer"]
        BrowserClient["Tenant / Owner Web Browser"]
        MobileClient["Signatory Mobile Device (WhatsApp/SMS Link)"]
        AdminUser["Platform Operations Admin"]
    end

    subgraph Perimeter["2. Network Edge & Perimeter Tier"]
        Cloudflare["Cloudflare CDN & WAF (DDoS Mitigation)"]
        ALB["Application Load Balancer (TLS 1.3 Termination)"]
    end

    subgraph DMZ["3. Public DMZ Application Tier"]
        WebInstance1["Streamlit Web Server Node 1"]
        WebInstance2["Streamlit Web Server Node 2"]
        EmailGateway["Outbound Notification Worker"]
    end

    subgraph Internal_Security["4. Internal Security & Filter Tier"]
        InternalFirewall["Internal Subnet Firewall & CBAC Token Filter"]
    end

    subgraph Private_App["5. Private Core Business Subnet"]
        CoreApp["GoLegal Core Orchestrator & PDF Sealer"]
        Worker["Background Async Reminder Worker"]
    end

    subgraph Isolated_Data["6. Isolated Data Subnet (No Public IP)"]
        DBCluster[("PostgreSQL / SQLite Cluster<br/>(AES-256 Encrypted at Rest)")]
        S3Bucket[("Encrypted Artifact Store<br/>(Strict IAM Bucket Policies)")]
    end

    Clients -->|HTTPS 443 / TLS 1.3| Cloudflare
    Cloudflare --> ALB
    ALB --> WebInstance1 & WebInstance2
    WebInstance1 & WebInstance2 --> InternalFirewall
    InternalFirewall --> CoreApp
    EmailGateway --> CoreApp
    CoreApp --> Worker
    CoreApp --> DBCluster
    CoreApp --> S3Bucket
    Worker --> DBCluster
```

---

## 4. Multi-Party Distributed Execution Topology

The platform coordinates geographically separated contracting parties in real time, upholding jurisdiction rules regardless of user location:

```mermaid
flowchart LR
    subgraph RemoteParties["Distributed Contracting Parties"]
        Landlord["Landlord in Delhi<br/>(Desktop Browser)"]
        Tenant["Tenant in Mumbai<br/>(Mobile Browser)"]
        Witness1["Witness 1 in Bangalore<br/>(SMS Deep-Link)"]
        Witness2["Witness 2 in Hyderabad<br/>(WhatsApp Link)"]
    end

    subgraph CoreCloud["GoLegal Cloud Platform (India VPC)"]
        Orchestrator["Async Signing State Machine"]
        DocMerger["PDF Assembler & Stamp Merger"]
    end

    subgraph StateTrust["Government & Gateway Integrations"]
        KA_Treasury["Karnataka e-Stamp (SHCIL)"]
        UIDAI["UIDAI Aadhaar eSign (ESP)"]
        Bank["UPI / NetBanking Gateway"]
    end

    Landlord -->|1. Drafts, Pays & Signs| Orchestrator
    Orchestrator -->|2. Debits Prepaid Ledger| KA_Treasury
    Orchestrator -->|3. Dispatches Tokenized Links| Tenant & Witness1 & Witness2
    Tenant -->|4. Aadhaar OTP Sign| UIDAI
    Witness1 -->|5. Aadhaar OTP Sign| UIDAI
    Witness2 -->|6. Aadhaar OTP Sign| UIDAI
    UIDAI -->|7. Cryptographic Hashes| Orchestrator
    Orchestrator -->|8. Seals Final PDF & Audit Trail| DocMerger
```

---

## 5. Operations Telemetry & System Health SLAs

| Metric / KPI | Threshold / Target SLA | Operational Action on Breach |
| :--- | :--- | :--- |
| **SHCIL Stamping Prepaid Balance** | Must remain $\ge$ ₹10,000 | Trigger visual warning banner in Admin Console and dispatch urgent SMS/email alert to finance team. |
| **Aadhaar eSign OTP Latency** | $< 3.5$ seconds (p95) | Failover to secondary licensed ESP gateway (eMudhra $\leftrightarrow$ NSDL). |
| **PDF Rendering & Sealing Turnaround** | $< 2.0$ seconds | Asynchronous offloading to background worker with polling status notification. |
| **Payment Webhook Confirmation** | $< 5.0$ seconds | Automatic webhook reconciliation poll every 30 seconds for pending payments. |
| **System Uptime & Availability** | $99.9\%$ Availability | Multi-AZ automated health check restart and load balancer rerouting. |
