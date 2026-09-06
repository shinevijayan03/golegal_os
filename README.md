# GoLegal - Digital Contracting & e-Stamping Web Application

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.63-FF4B4B.svg)](https://streamlit.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests Passing](https://img.shields.io/badge/tests-71%2F71%20passing-brightgreen.svg)]()
[![Coverage](https://img.shields.io/badge/coverage-96%25-brightgreen.svg)]()

> **100% Digital, Contactless, 3-Click Legal Agreement Drafting, e-Stamping, and Multi-Party Aadhaar e-Signing.**  
> Built strictly in adherence to the **Information Technology Act 2000 (§§ 4, 5, 10A)**, **Section 65B of the Indian Evidence Act 1872**, and the **Indian Stamp Act 1899**.

---

## 🚀 Quickstart

### 1. Prerequisites & Virtual Environment Setup
```powershell
# Clone the repository
git clone https://github.com/shinevijayan03/golegal_app.git
cd golegal_app

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # On Windows
# source .venv/bin/activate    # On Linux/macOS

# Install dependencies
pip install -r requirements.txt
```

### 2. Run Automated Pytest Suite (71 Tests, 96% Coverage)
```powershell
pytest -v --cov=services --cov=domain --cov=security tests/
```

### 3. Launch Interactive Streamlit Application
```powershell
streamlit run app.py
```
Open **`http://localhost:8501`** in your browser to interact with the full 5-step contracting wizard, split-pane clause preview, StockHolding prepaid stamping balance monitor, and user dashboard.

---

## 🏛️ System Architecture

GoLegal is built upon a decoupled **5-Layer Enterprise Architecture**:
1. **Presentation Layer**: Streamlit reactive multi-page web application with split-pane live preview and role-based views.
2. **Services Layer**: REST and internal controllers for SHCIL e-Stamping, UIDAI Aadhaar eSign, Payment gateways, and notification dispatch.
3. **Security Layer**: Capability-Based Access Control (CBAC) token engine preventing IDOR, witness privacy guards, and PII masking (`XXXXXXXX1234`).
4. **Business Layer**: Declarative signing state machines (`1..n` owners, `1..n` tenants, witnesses), statutory rule engine, and ReportLab PDF document assembly engine.
5. **Data Layer**: 3NF normalized relational schema (`users`, `agreements`, `parties`, `estamps`, `signatures`, `payments`, `audit_logs`) and append-only audit journals (`sysconfigTlb$jn`).

---

## 📜 Legal & Regulatory Compliance Invariants

- **Zero Plain-Text Aadhaar Storage**: Strictly masked (`XXXXXXXX1234`) across persistence and UI layers.
- **Section 65B Evidentiary Certificate**: Generated dynamically on the terminal page of all executed agreements with signer IP addresses, UTC timestamps, and SHA-256 cryptographic digests.
- **StockHolding (SHCIL) Prepaid Balance Guard**: Real-time statutory duty debit against corporate pool with automatic $< \text{₹}10,000$ low-balance warning.
- **Storage Consent Governance**: Explicit cloud storage consent (indefinite AES-256 storage vs. 27-day automated draft purge).

---

## 📚 Master Documentation & Agent Context

- [`GoLegal_Master_PRD_Context_v2 .md`](./GoLegal_Master_PRD_Context_v2%20.md): **Authoritative Master Product Requirements Document (PRD v1.0 / SAD v0.3)**.
- [`memory.md`](./memory.md): **Agent Context & Engineering Memory** for autonomous coding harnesses.
- [`ARCHITECTURE.md`](./ARCHITECTURE.md): Complete 5-layer model, DMZ topology, and India VPC deployment specifications.
- [`SOFTWARE_DESIGN_DOCUMENT.md`](./SOFTWARE_DESIGN_DOCUMENT.md): Low-level design, class models, and state machines.
- [`TEST_STRATEGY_AND_PLAN.md`](./TEST_STRATEGY_AND_PLAN.md): V&V plan and 22-category OWASP security matrix.
- [`DEPLOYMENT_PLAN.md`](./DEPLOYMENT_PLAN.md): Production containerization (Dockerfile) and cloud deployment.
- [`USAGE_DOCUMENTATION.md`](./USAGE_DOCUMENTATION.md): Persona manuals (Tenant, Landlord, Witness, Admin).
- [`SMART_EVALUATION_CRITERIA.md`](./SMART_EVALUATION_CRITERIA.md): Quantifiable 100-point evaluation rubric.

---

## 📄 License

This project is licensed under the MIT License.
