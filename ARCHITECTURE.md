# GoLegal — System Architecture

> **Version**: 2.0 (agentic baseline)
> **Supersedes**: 1.0, which described a 5-layer model with no AI layer and no autonomy.
> **Jurisdiction**: India — IT Act 2000 §§ 4, 5, 10A; Indian Evidence Act 1872 § 65B; Indian Stamp Act 1899.

---

## 1. Shape of the system

Six layers. The **Agent layer** is new in 2.0 and sits *beside* the presentation layer rather than
under it: agents are peers of the human user, calling the same business services through a guarded
tool registry. Nothing an agent can do is outside what a user could do, and several things a user can
do are closed to agents by construction.

```mermaid
graph TD
    classDef pres fill:#D4E6F1,stroke:#2980B9,stroke-width:2px;
    classDef agent fill:#E7F3EA,stroke:#1B5E3A,stroke-width:2px;
    classDef srv fill:#D5F5E3,stroke:#27AE60,stroke-width:2px;
    classDef sec fill:#FCF3CF,stroke:#F39C12,stroke-width:2px;
    classDef biz fill:#E8DAEF,stroke:#8E44AD,stroke-width:2px;
    classDef data fill:#FADBD8,stroke:#C0392B,stroke-width:2px;

    subgraph P ["1. Presentation (Streamlit)"]
        Landing["Landing & pricing"]:::pres
        Wizard["5-step wizard + deed preview"]:::pres
        Workspace["Workspace, invoices, NPS"]:::pres
        SignPage["Counterparty signing page<br/>(capability link, no account)"]:::pres
        Admin["Operations console"]:::pres
    end

    subgraph AG ["2. Agent layer"]
        Copilot["Copilot<br/>(tool-use loop / rule router)"]:::agent
        WFAgent["Workflow Agent<br/>(observe → plan → act → journal)"]:::agent
        Registry["Tool registry<br/>read | write | human tiers"]:::agent
        LLM["LLM gateway<br/>(Claude, with offline fallback)"]:::agent
    end

    subgraph SEC ["3. Security"]
        Auth["AuthService<br/>PBKDF2 · OTP · ingress detection"]:::sec
        CBAC["CBAC capability tokens<br/>HMAC-SHA256 · IDOR guard"]:::sec
        PII["PII masking & redaction"]:::sec
    end

    subgraph SVC ["4. Application services"]
        AgrSvc["AgreementService"]:::srv
        PaySvc["PaymentService"]:::srv
        StampSvc["StampingService (SHCIL)"]:::srv
        ESignSvc["ESignService (UIDAI/ESP)"]:::srv
        NotifSvc["NotificationService"]:::srv
    end

    subgraph BIZ ["5. Domain & documents"]
        WF["WorkflowService<br/>state machine · sealing · sweeps"]:::biz
        Rules["Rule engine<br/>state duty · statutory clauses"]:::biz
        Doc["Assembly engine<br/>e-Stamp p.1 · Page X of Y · § 65B"]:::biz
        DocStore["DocumentService<br/>content-addressed store"]:::biz
    end

    subgraph DATA ["6. Data"]
        DB[("3NF relational store<br/>SQLite / PostgreSQL")]:::data
        Journal[("Append-only journals<br/>audit_logs · sysconfigTlb$jn · agent_runs")]:::data
        Blobs[("Document blobs<br/>SHA-256 addressed")]:::data
    end

    P --> SEC
    AG --> Registry
    Registry --> SVC
    Copilot --> LLM
    WFAgent --> WF
    P --> SVC
    SEC --> SVC
    SVC --> BIZ
    BIZ --> DATA
```

### Why the agent layer is a peer, not a controller

An agent that sits *above* the UI can do anything the UI can. An agent that sits *beside* it, reaching
the same services through a declared tool surface, can only do what that surface exposes. This is what
makes "the agent cannot pay or sign" a structural property rather than a prompt instruction: those
tools exist in the registry so the model knows they exist, and they have no handler.

---

## 2. Trust boundaries

```mermaid
flowchart TD
    subgraph Untrusted["Untrusted input"]
        U1["User form input"]
        U2["Pasted contracts / uploaded PDFs"]
        U3["Model output (tool arguments)"]
        U4["Capability link from WhatsApp/SMS"]
    end

    subgraph Gate["Validation & authorisation gate"]
        V["validate_wizard_payload · PAN/PIN/email/phone"]
        R["redact_pii · mask_aadhaar"]
        E["_esc() before ReportLab"]
        T["CBAC.verify_token → agreement id + action + role"]
        Tier["Tool tier check: read | write | human"]
    end

    subgraph Trusted["Trusted core"]
        S["Application services"]
        D[("Database")]
    end

    U1 --> V --> S
    U2 --> R --> S
    U3 --> Tier --> S
    U4 --> T --> S
    S --> E
    S --> D
```

Four rules the code enforces:

1. **A model's output is user input.** Tool arguments pass the same validation as a form. `prefill_agreement` strips `aadhaar` from anything the model supplies.
2. **A raw UUID never authorises anything.** Document and signing endpoints require a capability token that names the agreement, the party, the role and the permitted actions.
3. **Money is computed server-side.** `calculate_stamp_duty` reads the persisted agreement, never a client-supplied amount (PRD OWASP category 20).
4. **Nothing user-supplied reaches a parser unescaped.** ReportLab's mini-HTML and every HTML component are escaped at the boundary.

---

## 3. The autonomous workflow loop

```mermaid
sequenceDiagram
    autonumber
    participant Cron as Sweep trigger (console / scheduler)
    participant Agent as WorkflowAgent
    participant WF as WorkflowService
    participant Notif as NotificationService
    participant Doc as Assembly + DocumentService
    participant DB as Database

    Cron->>Agent: sweep()
    Agent->>DB: read agreements in {Paid, Pending_Signatures}
    loop each agreement
        Agent->>Agent: observe() — signed, pending, last contact, expiry, seal digest
        Agent->>Agent: plan() — the steps it intends to take
        alt Paid and e-Stamp present
            Agent->>WF: open_for_signatures()
            WF->>Notif: mint tokens, dispatch invitations
        else Paid without e-Stamp
            Agent-->>DB: AgentRun status NEEDS_HUMAN (payment gate)
        else window breached
            Agent->>WF: transition to Expired
        else all parties signed
            Agent->>WF: check_and_complete_signing()
            WF->>Doc: seal once, record SHA-256
            WF->>Notif: completion notices (witness gets no copy)
        else reminders due (> 20h)
            Agent->>WF: resend_invitations()
        else
            Agent->>Agent: wait
        end
        Agent->>DB: persist AgentRun (goal, plan, steps, outcome)
    end
    Agent->>WF: purge_unconsented_drafts()
```

The agent never calls a gateway directly. Everything routes through `WorkflowService`, so state-machine
validation, audit journaling and the notification ledger apply identically whether the actor is a
person, the Copilot, or the sweep.

---

## 4. Agreement lifecycle

```mermaid
stateDiagram-v2
    [*] --> Draft: initiator creates (wizard or Copilot)
    Draft --> Draft: edit metadata & clauses
    Draft --> Paid: payment captured + e-Stamp procured (HUMAN ONLY)
    Draft --> Cancelled: abandoned
    Paid --> Pending_Signatures: tokens minted, links dispatched (agent or initiator)
    Paid --> Cancelled

    state Pending_Signatures {
        [*] --> Awaiting
        Awaiting --> Recording: a party completes Aadhaar OTP (HUMAN ONLY)
        Recording --> Awaiting: signature row + audit entry
        Awaiting --> Awaiting: daily reminder (agent)
        Awaiting --> AllSigned: count(signed) == count(parties)
    }

    Pending_Signatures --> Completed: seal with corporate DSC, issue § 65B, distribute
    Pending_Signatures --> Expired: window > 7 days (agent sweep)
    Pending_Signatures --> Cancelled: initiator revokes
    Completed --> [*]
    Expired --> [*]
    Cancelled --> [*]
```

Transitions are validated by `WorkflowService.VALID_TRANSITIONS`. Terminal states accept nothing.
Two transitions are marked HUMAN ONLY and are unreachable from any agent tool.

---

## 5. Deployment topology

```mermaid
flowchart TD
    Client["Browsers & mobile signers"] --> CF["Cloudflare CDN + WAF"]
    CF --> ALB["Load balancer · TLS 1.3 termination"]

    subgraph VPC["India-region VPC"]
        subgraph Public["Public subnet"]
            ALB
        end
        subgraph App["Private app subnet"]
            W1["Streamlit node 1"]
            W2["Streamlit node 2"]
            Sweep["Agent sweep worker<br/>(cron → WorkflowAgent.sweep)"]
        end
        subgraph Data["Isolated data subnet (no public IP)"]
            PG[("PostgreSQL 15 · AES-256 at rest")]
            Obj[("Object store · sealed PDFs")]
        end
    end

    subgraph Ext["External trust services"]
        SHCIL["SHCIL e-Stamp API"]
        UIDAI["UIDAI / licensed ESP"]
        PayGW["Razorpay / Cashfree"]
        Msg["SMS / WhatsApp gateway"]
        Claude["Anthropic API (Claude)"]
    end

    ALB --> W1 & W2
    W1 & W2 --> PG
    W1 & W2 --> Obj
    Sweep --> PG
    W1 & W2 --> Claude
    W1 & W2 --> SHCIL & UIDAI & PayGW
    Sweep --> Msg
```

**Notes on scaling.** The application is stateless apart from Streamlit session state; agreement state
lives in the database, so nodes are interchangeable. The agent sweep must run as a *single* worker
(or hold an advisory lock) so two nodes do not both dispatch the same reminder. Documents move from
the `documents` table to object storage by swapping `DocumentService`'s backend; its interface
(`store`, `latest`, `verify`) does not change.

---

## 6. Operational SLAs

| Indicator | Target | Breach action |
| :--- | :--- | :--- |
| SHCIL prepaid balance | ≥ ₹10,000 | Crimson banner in the console; stamping refuses rather than accepting a payment it cannot fulfil |
| Aadhaar eSign OTP latency | < 3.5 s (p95) | Fail over to the secondary ESP |
| Seal turnaround after final signature | < 2 s | Offload to the sweep worker |
| Copilot tool-loop turns | ≤ `agent_max_tool_calls` (12) | Loop exits and reports the tools it ran |
| Model unavailable | — | Copilot answers from the rule router; the notice names the reason |
| Signing window | 7 days | Agent transitions to Expired and notifies the initiator |
| Unconsented draft retention | 27 days | Agent purges on sweep |
