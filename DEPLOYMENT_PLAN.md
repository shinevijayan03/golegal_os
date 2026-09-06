# GoLegal Web Application - Deployment Plan

> **Document Version**: 1.0 (Master Engineering Baseline)  
> **Status**: APPROVED INFRASTRUCTURE & DEPLOYMENT SPECIFICATION  
> **Hosting Strategy**: Local Staging (Streamlit Runtime) $\rightarrow$ Docker Container $\rightarrow$ India Cloud VPC (AWS / DigitalOcean)  
> **Sovereignty Requirement**: 100% Data Localization within Indian Territorial Boundaries (MeitY / RBI Compliance)  

---

## 1. Local Staging Setup & Execution

### 1.1 Prerequisites & Python Environment
- Python 3.10 or higher
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
FROM python:3.11-slim AS builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Final Minimal Runtime Image
FROM python:3.11-slim AS runner

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

## 3. Environment Variables Configuration (`.env.example`)

```ini
# Platform Environment & Secret Keys
ENV=production
SECRET_KEY=golegal_crypto_secure_hmac_secret_2026_change_in_prod
PORT=8501

# Database Persistence Configuration
# Development SQLite:
DATABASE_URL=sqlite:///./golegal.db
# Production PostgreSQL (India VPC):
# DATABASE_URL=postgresql://golegal_user:StrongPass123@db.internal:5432/golegal_prod

# Mock vs Live Trust Service Toggles
MOCK_SHCIL_ENABLED=true
SHCIL_API_URL=https://api.stockholding.mock.internal/v1/estamp
SHCIL_CLIENT_ID=golegal_corp_in
SHCIL_INITIAL_PREPAID_BALANCE=50000.00
LOW_BALANCE_THRESHOLD=10000.00

MOCK_UIDAI_ENABLED=true
UIDAI_ESP_GATEWAY_URL=https://esign.esp.mock.internal/v2/otp

# Payment Gateway Configuration
PAYMENT_GATEWAY_PROVIDER=Razorpay
PAYMENT_KEY_ID=rzp_live_golegal_mock_key
PAYMENT_KEY_SECRET=rzp_live_secret_mock

# Section 65B & Evidentiary Retention
STORAGE_RETENTION_PURGE_DAYS=27
DATA_LOCALIZATION_REGION=ap-south-1
```

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
