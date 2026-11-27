# VeriDoc AI 2.0 — Architecture Baseline & Evolution Plan
**Universal Document Intelligence, Repository, Mapping, Testing and Verification Platform**
*Recorded: November 26, 2026*

---

## 1. Existing System Architecture Baseline

### 1.1 Core Components
- **Backend**: Flask 3.1 REST API + PyMuPDF 1.25 + Tesseract OCR + RapidFuzz + Google GenAI SDK (`gemini-3.5-flash-lite`).
- **Database**: PostgreSQL 19 (`veridoc_db` on `localhost:5432`) active production engine.
  - Baseline record counts completely preserved:
    - `applicants`: 69 rows
    - `documents`: 133 rows
    - `audit_reviews`: 59 rows
    - `ai_usage_logs`: 95 rows
    - `document_type_definitions`: 12 rows (pre-seeded with KYC + commercial types)
    - `document_schemas`: 3 rows (versioned schemas)
    - `document_extracted_attributes`: 5 rows (normalized attributes with bounding boxes)
    - `processing_jobs`: 0 rows
    - `api_keys`: 0 rows
    - `webhook_subscriptions`: 0 rows
- **Frontend**: React 18 + Vite 8.3 + Tailwind CSS standalone web application.
  - Active views: Welcome (`welcome`), Overview (`overview`), Upload (`upload`), Verification Queue (`queue`), Applicants (`applicants`), Reports (`reports`).
  - Interactive workspace: `VisualDocumentWorkspace.jsx` (PyMuPDF high-DPI rendering, SVG bounding box overlays, marquee extraction).
- **Asynchronous & REST Engine**: `/api/v1` versioned REST API + PostgreSQL-backed atomic job worker (`FOR UPDATE SKIP LOCKED`) + HMAC-SHA256 signed webhooks.
- **Privacy & Safety**: Strict Aadhaar masking (`mask_aadhaar()`), API key scrubbing in logs (`_sanitize_error()`), and applicant data isolation.

---

## 2. Evolution Objectives & Module Architecture

VeriDoc AI 2.0 expands from a KYC document verification tool into a comprehensive enterprise document intelligence platform:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          VERIDOC AI 2.0 PLATFORM                           │
├─────────────────────────────────────────────────────────────────────────────┤
│  1. Overview / Dashboard         │  6. Applicants / Entities                │
│  2. Upload Documents (No Train)  │  7. Testing & Evaluation                 │
│  3. Document Repository          │  8. Reports (Expanded Export)            │
│  4. Document Mapping / Triang.   │  9. API & Integration Management         │
│  5. Verification Queue           │ 10. Settings & Security                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Four-Milestone Implementation Plan

### Milestone 1: Document Repository and Dynamic Schema
- **Database Extension**: Migration `003_universal_platform_v2.sql` to add `source_origin` to `document_type_definitions`, add `applicant_triangulations`, `benchmark_runs`, and per-page AI usage tracking columns.
- **Backend Services**:
  - `DocumentRepositoryService`: CRUD for document types, schema versioning, attribute definitions, sample discovery, and schema publish/rollback.
  - Endpoints: `GET /api/repository/types`, `POST /api/repository/types`, `GET /api/repository/types/<id>`, `PUT /api/repository/types/<id>`, `POST /api/repository/types/<id>/schemas`, `POST /api/repository/types/<id>/rollback`.
- **Frontend View**: `RepositoryView.jsx`:
  - Catalogue landing page: filters, search, statistics (types, active schemas, doc count).
  - Type detail drawer/modal: attribute editor, data types, required flags, regexes, extraction guidance.
  - Registration wizard: name, description, sample upload, AI discover, manual attribute builder.

### Milestone 2: Intelligent Upload and Visual Workspace (Simplified UX)
- **Eliminate Upfront Training Requirement**:
  - Direct drop/upload: User selects or creates an applicant/entity, drops documents without pre-defining types.
  - Automatic local intake -> classifier -> AI type/attribute discovery for unknown documents.
  - Provisional schema proposal for uncataloged documents with employee approval flow.
- **Visual Document Intelligence Workspace Enhancements**:
  - Adjacent dual-pane viewer: Left = PDF/image with zoom/rotation/marquee; Right = extracted attributes table with confidence, page, coordinates, validation status.
  - Click attribute -> jump to & highlight document bounding box.
  - Marquee OCR selection -> add custom attribute with provenance ('ai', 'ocr', 'manual').
  - Multi-page document support with explicit page tracking.

### Milestone 3: Triangulation, Testing, Reports and APIs
- **Document Mapping / Triangulation Module** (`MappingView.jsx`):
  - Cross-document attribute matrix for documents belonging to the SAME applicant/entity.
  - Normalization (dates, names, currency), match vs conflict vs missing field resolution.
  - Deterministic Python rules + explainable semantic mapping reasoning.
  - Persistence in `applicant_triangulations`.
- **Testing & Evaluation Module** (`TestingView.jsx`):
  - Single and batch testing with synthetic test fixtures.
  - Ground truth comparison: Precision, Recall, F1, Accuracy, FAR, FRR, CER, latency, token usage, cost.
  - Persistence in `benchmark_runs`.
- **Expanded Reports & APIs**:
  - Processing, applicant, triangulation, AI usage, and testing reports with CSV/Excel exports.
  - `/api/v1` REST integration + API Integration Management view.

### Milestone 4: Hybrid Deployment, Security and Final Validation
- **Local-First Tiered Hybrid Processing**:
  - Tier 1: Local PyMuPDF / Tesseract + regex + deterministic checks.
  - Tier 2: AI escalation on low confidence, sparse text, or missing mandatory fields.
- **Per-Page AI Usage & Cost Tracking**:
  - Input/output token tracking, per-page cost calculation, configurable model pricing versioning.
- **Privacy & Security**:
  - Aadhaar masking, DPDPA safeguards, API key scopes, and comprehensive deployment docs.
- **Full Regression Testing & Handover**.
