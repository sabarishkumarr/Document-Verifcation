# VeriDoc AI 2.0 — Deployment, Integration & Operations Guide

This guide describes how to deploy, configure, and operate **VeriDoc AI 2.0: Universal Document Intelligence & Verification Platform** across both **Personal Workstations / Developer Laptops** and **Company / Enterprise Production Servers**.

---

## 1. System Architecture Overview

VeriDoc AI 2.0 combines:
1. **Core Processing Engine**: Multi-format document ingestion (PDF, JPG, PNG), universal document classification (11 built-in standard types + dynamic custom types), spatial OCR extraction with normalized bounding boxes `[0, 1000]`, and rule-based validation.
2. **AI Document Intelligence**: External inference (Google Gemini 2.5 Flash / Flash-Lite) for high-accuracy multimodal extraction, combined with local Tesseract OCR fallback for offline resilience.
3. **Versioned Document Schema Learning**: Continuous in-context attribute learning and regex synthesis from employee reviews without neural fine-tuning.
4. **Asynchronous Background Processing**: PostgreSQL-backed job queue with atomic job reservation (`FOR UPDATE SKIP LOCKED`), exponential backoff retries, and HMAC-SHA256 signed webhooks.
5. **Interactive Visual Document Workspace**: High-DPI page rendering, SVG bounding box overlay, bi-directional token highlight sync, and marquee drag-and-drop OCR extraction.
6. **Unified Dual Interface**: Versioned REST API (`/api/v1`) for external enterprise systems alongside the standalone React 19 UI for operational officers.

---

## 2. Prerequisites

| Component | Minimum Version | Recommended |
| :--- | :--- | :--- |
| **Operating System** | Windows 10/11, Ubuntu 22.04 LTS, macOS 13+ | Ubuntu 22.04 LTS (Server) / Windows 11 (Desktop) |
| **Python** | Python 3.10+ | Python 3.11 / 3.12 |
| **Node.js** | Node.js 18+ | Node.js 20 LTS |
| **Database** | SQLite 3.35+ (Personal) / PostgreSQL 14+ (Enterprise) | PostgreSQL 16+ or 19 |
| **Tesseract OCR** | Tesseract 5.0+ | Installed and in system `PATH` |

---

## 3. Deployment Scenario A: Personal Computer / Developer Workstation

This mode allows rapid development and testing using either local PostgreSQL or zero-configuration SQLite.

### Step A.1: Clone & Environment Setup
```bash
git clone https://github.com/your-org/VeriDoc-AI.git
cd VeriDoc-AI

# Create Python virtual environment
python -m venv backend/venv

# Activate virtual environment
# Windows (PowerShell):
.\backend\venv\Scripts\Activate.ps1
# Linux / macOS:
source backend/venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt
```

### Step A.2: Configure `.env`
Create `.env` from template:
```bash
cp .env.example .env
```
For personal testing, configure either PostgreSQL or SQLite:
```ini
# --- For Local PostgreSQL ---
DATABASE_TYPE=postgres
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=veridoc_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_local_password

# --- External AI Inference (Optional) ---
AI_EXTRACTION_ENABLED=True
AI_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
```

### Step A.3: Initialize Database Schema
If using PostgreSQL, apply the schema and V2 migrations:
```bash
psql -U postgres -h localhost -p 5432 -d veridoc_db -f veridoc_schema.sql
psql -U postgres -h localhost -p 5432 -d veridoc_db -f backend/database/migrations/002_universal_platform.sql
```

### Step A.4: Run Application
Open two terminal tabs:

**Terminal 1 (Flask Backend + Background Worker):**
```bash
# Windows
.\backend\venv\Scripts\python backend/app.py
# Linux / macOS
python backend/app.py
```
*(Backend and async worker initialize on `http://127.0.0.1:5000`)*

**Terminal 2 (React Vite Frontend):**
```bash
cd frontend
npm install
npm run dev
```
*(UI is live at `http://localhost:5173`)*

---

## 4. Deployment Scenario B: Enterprise / Company Server

For secure enterprise deployments, the backend runs behind Gunicorn/Nginx, connecting to a managed PostgreSQL cluster.

### Step B.1: PostgreSQL Cluster Initialization
Execute the schema creation on your production database instance:
```bash
psql -h pg-server.internal.company.com -U veridoc_app -d veridoc_db -f veridoc_schema.sql
psql -h pg-server.internal.company.com -U veridoc_app -d veridoc_db -f backend/database/migrations/002_universal_platform.sql
```

### Step B.2: Environment Configuration
Configure `/etc/veridoc/.env` with strict permissions (`chmod 600`):
```ini
FLASK_ENV=production
SECRET_KEY=9a8f27c4b1d6e8a0f3c2e5b7a1d4f6c8e0b2a4d6f8
DATABASE_TYPE=postgres
POSTGRES_HOST=pg-server.internal.company.com
POSTGRES_PORT=5432
POSTGRES_DB=veridoc_db
POSTGRES_USER=veridoc_app
POSTGRES_PASSWORD=production_secure_vault_secret
POSTGRES_SSLMODE=verify-full

# Worker & Queue Tuning
ASYNC_WORKER_ENABLED=True
ASYNC_WORKER_INTERVAL_SECONDS=2
ASYNC_WORKER_MAX_RETRIES=3
ASYNC_WORKER_CONCURRENCY=4

# AI Inference Gateway
AI_EXTRACTION_ENABLED=True
AI_PROVIDER=gemini
GEMINI_API_KEY=production_enterprise_gemini_key
GEMINI_MODEL=gemini-2.5-flash
```

### Step B.3: Systemd Service for Web Application (`/etc/systemd/system/veridoc-web.service`)
```ini
[Unit]
Description=VeriDoc AI Web Backend
After=network.target

[Service]
User=veridoc
WorkingDirectory=/opt/veridoc
EnvironmentFile=/etc/veridoc/.env
ExecStart=/opt/veridoc/backend/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 backend.app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

### Step B.4: Systemd Service for Asynchronous Worker (`/etc/systemd/system/veridoc-worker.service`)
```ini
[Unit]
Description=VeriDoc AI Async Job Worker
After=network.target veridoc-web.service

[Service]
User=veridoc
WorkingDirectory=/opt/veridoc
EnvironmentFile=/etc/veridoc/.env
ExecStart=/opt/veridoc/backend/venv/bin/python -m backend.services.async_worker
Restart=always

[Install]
WantedBy=multi-user.target
```

### Step B.5: Nginx Reverse Proxy Configuration
```nginx
server {
    listen 443 ssl http2;
    server_name veridoc.internal.company.com;

    ssl_certificate /etc/ssl/certs/veridoc.crt;
    ssl_certificate_key /etc/ssl/private/veridoc.key;

    # Static Frontend Assets
    location / {
        root /opt/veridoc/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # API & Backend Routing
    location /api/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 50M;
    }
}
```

---

## 5. Database Migration & Rollback Procedures

### 5.1 SQLite to PostgreSQL Migration
To migrate an existing SQLite database into PostgreSQL while preserving all IDs, sequences, and relationships:
```bash
# Dry run verification first
python backend/scripts/migrate_to_postgres.py --dry-run

# Execute full migration with transaction safety
python backend/scripts/migrate_to_postgres.py
```

### 5.2 Schema Learning Version Rollback
When an updated document schema needs to be rolled back to a previous stable version:
```bash
# Rollback via API
curl -X POST http://localhost:5000/api/v1/schemas/commercial_invoice/rollback \
  -H "X-API-Key: admin_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{"target_version": 1}'

# Programmatic Python Rollback
python -c "from backend.services.schema_learner import SchemaLearner; SchemaLearner.rollback_schema('commercial_invoice', target_version=1)"
```

---

## 6. REST API v1 Reference & `curl` Examples

All `/api/v1` routes require an API key passed via header `X-API-Key: <key>` or `Authorization: Bearer <key>`.

### 6.1 Ingest Document (Asynchronous Processing)
Uploads a document and queues an asynchronous extraction job.
```bash
curl -X POST http://localhost:5000/api/v1/documents \
  -H "X-API-Key: doc_write_key_sample" \
  -F "file=@invoice_2026.pdf" \
  -F "applicant_id=APPL-2026-001" \
  -F "document_type=commercial_invoice"
```
**Response (202 Accepted):**
```json
{
  "document_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "job_id": "job_01h7v8k9p3q4r5s6t7u8v9w0",
  "status": "queued",
  "message": "Document uploaded and processing job queued"
}
```

### 6.2 Poll Job Status
```bash
curl -X GET http://localhost:5000/api/v1/jobs/job_01h7v8k9p3q4r5s6t7u8v9w0 \
  -H "X-API-Key: doc_read_key_sample"
```
**Response (200 OK):**
```json
{
  "job_id": "job_01h7v8k9p3q4r5s6t7u8v9w0",
  "document_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "status": "completed",
  "progress_percentage": 100,
  "stage": "completed",
  "result_data": {
    "document_type": "commercial_invoice",
    "is_valid": true,
    "confidence": 0.98
  }
}
```

### 6.3 Retrieve Extraction & Bounding Boxes
```bash
curl -X GET http://localhost:5000/api/v1/documents/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d/extraction \
  -H "X-API-Key: doc_read_key_sample"
```
**Response (200 OK):**
```json
{
  "document_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "classified_type": "commercial_invoice",
  "extracted_fields": {
    "invoice_number": "INV-2026-9921",
    "invoice_date": "2026-11-20",
    "total_amount": "4500.00"
  },
  "attributes": [
    {
      "attribute_key": "invoice_number",
      "display_label": "Invoice Number",
      "data_type": "string",
      "attribute_value": "INV-2026-9921",
      "confidence": 0.99,
      "page_number": 1,
      "bounding_box": [120, 85, 240, 105],
      "source_type": "learned_schema"
    }
  ]
}
```

### 6.4 Marquee Drag-and-Drop Extraction (Interactive Workspace)
Extracts text from a user-drawn marquee rectangle `[ymin, xmin, ymax, xmax]` normalized to `[0, 1000]`.
```bash
curl -X POST http://localhost:5000/api/documents/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d/marquee-extract \
  -H "Content-Type: application/json" \
  -d '{
    "page": 1,
    "box": [120, 85, 240, 105],
    "attribute_label": "Tax Number"
  }'
```
**Response (200 OK):**
```json
{
  "success": true,
  "extracted_text": "US-EIN-992011",
  "suggested_key": "tax_number",
  "suggested_label": "Tax Number",
  "suggested_type": "string",
  "bounding_box": [120, 85, 240, 105]
}
```

### 6.5 Learn Schema for Document Type
Synthesizes anchor phrases, regex patterns, and few-shot exemplars from employee-reviewed documents:
```bash
curl -X POST http://localhost:5000/api/v1/schemas/commercial_invoice/learn \
  -H "X-API-Key: admin_api_key_sample"
```
**Response (200 OK):**
```json
{
  "success": true,
  "schema": {
    "document_type": "commercial_invoice",
    "version": 2,
    "attribute_count": 8,
    "sample_documents_count": 12,
    "anchor_phrases": {
      "tax_id": ["Tax ID:", "EIN:"]
    },
    "regex_patterns": {
      "tax_id": "\\b[A-Z0-9]+(?:-[A-Z0-9]+)+\\b"
    }
  }
}
```

### 6.6 Run Dataset Evaluation Benchmark
Executes end-to-end benchmarking against the 10-applicant synthetic KYC dataset:
```bash
curl -X POST http://localhost:5000/api/v1/evaluation/benchmark \
  -H "X-API-Key: admin_api_key_sample"
```
**Response (200 OK):**
```json
{
  "success": true,
  "summary": {
    "dataset_name": "Authorized 10-Applicant Synthetic KYC Dataset",
    "total_applicants": 10,
    "total_documents": 25,
    "classification_accuracy": 0.96,
    "validation_accuracy": 0.80,
    "overall_precision": 0.9615,
    "overall_recall": 0.9901,
    "overall_f1_score": 0.9756,
    "mean_character_error_rate": 0.0476
  },
  "privacy_compliance": {
    "pii_masked": true,
    "unauthorized_data_used": false
  }
}
```

---

## 7. Webhook Configuration & Signature Verification

External client applications can receive asynchronous job updates via HTTP webhooks.

### 7.1 Webhook Delivery Payload
When a job completes or fails, VeriDoc AI sends a POST request with headers:
- `Content-Type: application/json`
- `X-VeriDoc-Signature: <hmac_sha256_hex_digest>`
- `X-VeriDoc-Event: job.completed`

### 7.2 Webhook Signature Verification (Python Example)
```python
import hmac
import hashlib

def verify_webhook_signature(payload_bytes: bytes, signature_header: str, secret_key: str) -> bool:
    computed = hmac.new(secret_key.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature_header)
```

---

## 8. Privacy & Data Protection Safeguards

1. **PII Masking**: Identity numbers (Aadhaar, SSN), full addresses, and names are masked in logs, evaluation summaries, and few-shot exemplars (`XXXX-XXXX-1234`).
2. **In-Context Learning vs Fine-Tuning**: VeriDoc AI uses **Retrieval-Augmented Few-Shot In-Context Learning** and deterministic regex synthesis. It **never modifies neural network weights** or shares proprietary data across client tenants.
3. **Database Security**: All queries use parameterized SQL; multi-tenant API scopes (`read`, `write`, `admin`) are strictly enforced per endpoint.
