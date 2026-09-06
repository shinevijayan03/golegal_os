# GoLegal Web Application - Deployment Plan

> **Version**: 2.0 (agentic baseline)  
> **Status**: APPROVED INFRASTRUCTURE & DEPLOYMENT SPECIFICATION  
> **Hosting Strategy**: Local Staging (Streamlit Runtime) $\rightarrow$ Docker Container $\rightarrow$ India Cloud VPC (AWS / DigitalOcean)  
> **Sovereignty Requirement**: 100% Data Localization within Indian Territorial Boundaries (MeitY / RBI Compliance)  

---

## 1. Local Staging Setup & Execution

### 1.1 Prerequisites & Python Environment
- Python 3.12 or higher
- `pip` package manager and `virtualenv`

### 1.2 Execution Commands
```bash
# 1. Clone repository & create isolated virtual environment
python -m venv .venv
# On Windows pwsh:
.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

# 2. Install core runtime and test dependencies
pip install -r requirements.txt

# 3. Initialize SQLite relational schema and configuration defaults
python -c "from persistence.database import init_db; init_db()"

# 4. Launch Streamlit interactive application
streamlit run app.py --server.port 8501 --server.headless true
```
The application will be accessible locally at `http://localhost:8501`.

---

## 2. Production Containerization (Dockerfile & .dockerignore)

### 2.1 Multi-Stage Dockerfile (`Dockerfile`)
```dockerfile
# Stage 1: Build & Dependency Resolution
FROM python:3.12-slim AS builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Final Minimal Runtime Image
FROM python:3.12-slim AS runner

WORKDIR /app
# Install minimal runtime libraries for ReportLab PDF rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    libfreetype6 \
    libjpeg62-turbo \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application source code
COPY . /app

# Expose Streamlit default port
EXPOSE 8501

# Healthcheck verification
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Launch production server
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
```

### 2.2 `.dockerignore`
```
.git
.gitignore
.venv
__pycache__
*.pyc
*.pyo
*.pyd
.pytest_cache
.coverage
htmlcov/
tests/
*.log
.env
```

---

## 3. Environment configuration

Every one of these is read by `config.py`. Nothing security-sensitive is hardcoded anywhere else in
the codebase, and the two secrets below **must** be rotated before any deployment — the defaults are
labelled dev placeholders precisely so that shipping them is visible in a diff.

```ini
# ---- Runtime -------------------------------------------------------------
GOLEGAL_ENV=production
GOLEGAL_BASE_URL=https://app.golegal.in       # used to mint signing links
DATABASE_URL=postgresql://golegal:CHANGE_ME@db.internal:5432/golegal_prod

# ---- Secrets (ROTATE) ----------------------------------------------------
GOLEGAL_CBAC_SECRET=<64+ random chars>        # signs every capability token
GOLEGAL_DSC_SECRET=<64+ random chars>         # corporate seal HMAC
GOLEGAL_PBKDF2_ITERATIONS=120000

# ---- Auth & signing windows ---------------------------------------------
GOLEGAL_SIGNING_LINK_TTL_DAYS=7
GOLEGAL_OTP_TTL_SECONDS=300
GOLEGAL_OTP_MAX_ATTEMPTS=5
GOLEGAL_OTP_LOCKOUT_SECONDS=900

# ---- Gateways ------------------------------------------------------------
GOLEGAL_MOCK_GATEWAYS=false                   # false = live SHCIL / UIDAI / payments
                                              # also stops OTPs being echoed to the screen

# ---- Pricing (server-side, never client-supplied) ------------------------
GOLEGAL_PLATFORM_FEE=299.0
GOLEGAL_GST_RATE=0.18
GOLEGAL_LOW_BALANCE_THRESHOLD=10000.0
GOLEGAL_INITIAL_PREPAID_BALANCE=50000.0

# ---- Retention -----------------------------------------------------------
GOLEGAL_DRAFT_PRUNING_DAYS=27
GOLEGAL_AGREEMENT_RETAIN_DAYS=2920            # 8 years

# ---- AI layer (optional) -------------------------------------------------
ANTHROPIC_API_KEY=sk-ant-...                  # unset = deterministic fallback
GOLEGAL_LLM_MODEL=claude-opus-5
GOLEGAL_LLM_EFFORT=medium                     # low | medium | high | xhigh | max
GOLEGAL_LLM_MAX_TOKENS=4096
GOLEGAL_LLM_ENABLED=true
GOLEGAL_AGENT_MAX_TOOL_CALLS=12

# ---- Statutory identity --------------------------------------------------
GOLEGAL_GSTIN=29AAACA0000A1Z5
```

> **`GOLEGAL_MOCK_GATEWAYS=false` is a security control, not just a feature flag.** In sandbox mode
> the application displays OTPs on screen so the flow can be demonstrated. In production this must be
> off.

### 3.1 Pre-deployment checklist

- [ ] `GOLEGAL_CBAC_SECRET` and `GOLEGAL_DSC_SECRET` rotated to high-entropy values held in a secrets manager
- [ ] `GOLEGAL_MOCK_GATEWAYS=false`
- [ ] `DATABASE_URL` points at PostgreSQL, not SQLite
- [ ] `GOLEGAL_BASE_URL` is the public HTTPS origin (signing links are minted from it)
- [ ] Demo account seeding disabled — call `init_db(seed_demo=False)` or remove the demo accounts post-migration
- [ ] Object storage configured if documents are moved out of the `documents` table

---

## 3A. Agent sweep worker

The autonomous workflow agent must run as a scheduled job, and as **exactly one** instance — two
workers sweeping concurrently would double-dispatch reminders.

```python
# sweep.py — invoked by cron / ECS scheduled task / Kubernetes CronJob
from ai.workflow_agent import WorkflowAgent
from persistence.database import SessionLocal

session = SessionLocal()
try:
    summary = WorkflowAgent(session).sweep(triggered_by="CRON")
    print(summary)          # goes to structured logs
finally:
    session.close()
```

```
# hourly is sufficient: reminders are rate-limited to one per party per 20 hours,
# and the signing window has day granularity
0 * * * *  cd /app && python sweep.py
```

Every sweep writes an `AgentRun` per agreement visited, so the job is auditable after the fact and
idempotent if it runs twice.

---

## 4. Cloud Production Topology (India VPC Localization)

```mermaid
flowchart TD
    Client["Client Traffic<br/>(HTTPS / Port 443)"] --> CDN["Cloudflare CDN & WAF<br/>(Edge Rate Limiting & SSL)"]
    CDN --> ALB["AWS Application Load Balancer<br/>(Mumbai ap-south-1 VPC)"]

    subgraph VPC["GoLegal Private Cloud VPC (India Region)"]
        subgraph PublicSubnet["Public DMZ Subnet"]
            ALB
        end

        subgraph PrivateAppSubnet["Private Application Subnet (No Public IP)"]
            Node1["Streamlit App Pod 1<br/>(Docker Container)"]
            Node2["Streamlit App Pod 2<br/>(Docker Container)"]
            Worker["Celery / Redis Worker<br/>(Async PDF & Stamping)"]
        end

        subgraph IsolatedDBSubnet["Isolated Database Subnet (No Internet Ingress)"]
            PG_Primary[("PostgreSQL 15 Primary<br/>(AES-256 Storage Encryption)")]
            PG_Standby[("PostgreSQL Read Replica<br/>(Multi-AZ Hot Standby)")]
            S3_Docs[("AWS S3 Encrypted Bucket<br/>(Mumbai ap-south-1 Object Store)")]
        end
    end

    ALB --> Node1 & Node2
    Node1 & Node2 --> PG_Primary
    Node1 & Node2 --> Worker
    Worker --> S3_Docs
    Worker --> PG_Primary
    PG_Primary -.->|Streaming Replication| PG_Standby
```

---

## 5. Health Checks, Readiness Probes & Backup Policies

1. **Liveness & Readiness Probes**: Streamlit health probe at `/_stcore/health` queried every 30 seconds.
2. **Database Point-in-Time Recovery (PITR)**: Automated continuous WAL archiving with 14-day retention in production.
3. **Disaster Recovery RPO / RTO**:
   - Recovery Point Objective (RPO): $< 5$ minutes.
   - Recovery Time Objective (RTO): $< 30$ minutes via automated container orchestration.
