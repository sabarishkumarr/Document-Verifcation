# VeriDoc AI — KYC Document Intelligence & Verification Platform

VeriDoc AI is an automated KYC document intake, classification, and cross-verification intelligence platform built for housing finance and retail lending operations. It processes multi-category identity documents, extracts normalized customer identity attributes, enforces deterministic business rules, and provides compliance review ledgers with full audit trails.

---

## Key Features

1. **Multi-Category KYC Intake**:
   - Supports **Aadhaar**, **PAN Card**, **Passport**, **Driving Licence**, and **Voter ID (EPIC)** in PDF, JPG, and PNG formats.
   - Intelligent document classification with automated category recognition.

2. **Hybrid Extraction Pipeline**:
   - **Google Gemini Multimodal AI**: High-accuracy structured entity extraction with confidence scoring.
   - **PyMuPDF Digital Text Engine**: Instant text parsing for digitally generated PDFs.
   - **Tesseract OCR Fallback**: Adaptive grayscale and thresholding for scanned physical documents and camera captures.
   - Strict regulatory privacy protection with automated Aadhaar 8-digit masking (`XXXX-XXXX-1234`).

3. **Deterministic Cross-Document Comparison**:
   - Compares identity attributes across all documents uploaded for an applicant:
     - Customer Name (with Levenshtein and token-sort similarity)
     - Date of Birth (ISO 8601 normalization: `YYYY-MM-DD`)
     - Gender consistency
     - Identification Numbers (individually validated against statutory formats, never mismatched across distinct ID categories)
     - Residential Address
     - Father / Guardian Name
     - Document Expiry & Legal Validity (expired documents prevent automatic approval)
   - Strict **applicant-level data isolation** ensuring zero document leakage across applicants.

4. **Applicant-Centric Verification Workflow**:
   - Verification queue structured as one review item per applicant.
   - Consolidated attribute-by-document comparison matrix.
   - Officer decisioning: Approval, Rejection with mandatory justification remarks, and Request Resubmission.
   - In-place field correction with immutable audit trail logging.

5. **Compliance Reporting & Audit Trail**:
   - Single clear primary issue per applicant (e.g., `Rejected — Expired Driving Licence`).
   - Expandable breakdown for detailed validation findings and officer remarks.
   - Export reports in **XLSX (multi-sheet workbook)**, **CSV**, and structured **JSON**.

6. **Monochrome Editorial Interface**:
   - Professional, typography-first user interface with muted blue accents.
   - Operational Overview dashboard grouped by applicant.
   - Icon-only officer profile menu with instant demo reset controls.

---

## Architecture

- **Backend**: Python 3.10+, Flask, SQLite, PyMuPDF (fitz), OpenCV, Tesseract OCR, Google GenAI SDK.
- **Frontend**: React 18, Vite, Tailwind CSS, Material Symbols.
- **Data Storage**: SQLite (`backend/database/veridoc.db`) with relational integrity and foreign keys.

---

## Directory Structure

```text
VeriDoc-AI/
├── backend/
│   ├── app.py                     # Flask application factory & blueprint registration
│   ├── config.py                  # Environment configuration & paths
│   ├── database/
│   │   ├── db.py                  # SQLite schema, connection management & queries
│   │   └── repair_applicant_isolation.py
│   ├── routes/
│   │   ├── applicants.py          # Applicant directory & profile endpoints
│   │   ├── dashboard.py           # Operational metrics & attention queue
│   │   ├── documents.py           # Document inspection & OCR status
│   │   ├── reports.py             # Compliance reports & export handlers
│   │   ├── search.py              # Global search endpoint
│   │   └── upload.py              # Multi-file intake & pipeline runner
│   ├── services/
│   │   ├── ai_extractor.py        # Gemini multimodal AI extraction
│   │   ├── classifier.py          # Rule-based & regex document classifier
│   │   ├── comparator.py          # Deterministic cross-document matching & matrix
│   │   ├── document_processor.py  # End-to-end ingestion pipeline
│   │   ├── field_extractor.py     # Regex field extraction fallback
│   │   ├── file_validator.py      # Magic byte & MIME type verification
│   │   ├── image_preprocessor.py  # Contrast enhancement & thresholding
│   │   ├── matrix_exporter.py     # XLSX / CSV export generators
│   │   ├── text_extractor.py      # PyMuPDF digital parser & Tesseract OCR
│   │   └── validator.py           # Statutory format & expiry date validations
│   └── tests/                     # Verification test suites & benchmarks
├── frontend/
│   ├── src/
│   │   ├── App.jsx                # Main application state & tab router
│   │   ├── api.js                 # Unified API client & download helpers
│   │   └── Components/
│   │       ├── ApplicantsView.jsx         # Applicant directory & profiles
│   │       ├── ComparisonMatrix.jsx       # Consolidated matrix table
│   │       ├── DashboardView.jsx          # Operational overview dashboard
│   │       ├── Header.jsx                 # Top bar with icon-only profile dropdown
│   │       ├── ReportsView.jsx            # Compliance reports & audit ledger
│   │       ├── UploadView.jsx             # Ingestion workflow
│   │       ├── VerificationQueueView.jsx  # Applicant review queue
│   │       └── WelcomeView.jsx            # Officer welcome screen
│   ├── package.json
│   └── vite.config.js
├── tests/                         # Pytest test suite (77 tests)
├── storage/                       # Document storage (.gitkeep preserved)
├── .env.example                   # Environment configuration template
├── .gitignore                     # Git ignore rules
└── README.md                      # Documentation
```

---

## Quickstart Guide

### 1. Prerequisites

- **Python 3.10+** (Python 3.11 or 3.12 recommended)
- **Node.js 18+** and **npm**
- *(Optional)* **Tesseract OCR** (for scanned image OCR fallback):
  - Windows: Install via [UB-Mannheim Tesseract installer](https://github.com/UB-Mannheim/tesseract/wiki) and add to `PATH`.

### 2. Backend Setup

```bash
# Clone the repository
git clone https://github.com/sabarishkumarr/Document-Verifcation.git
cd Document-Verifcation

# Create and activate virtual environment
python -m venv backend/venv

# Windows
backend\venv\Scripts\activate

# macOS / Linux
source backend/venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Configure environment variables
cp .env.example .env
```

Edit `.env` to supply your **Google Gemini API Key**:
```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash-lite
```

### 3. Frontend Setup

```bash
cd frontend
npm install
cd ..
```

### 4. Running the Application

You can start both servers together using the Windows batch launcher:
```bash
Start_Veridoc.bat
```

Or start them individually in separate terminal windows:

**Terminal 1 — Backend:**
```bash
python backend/app.py
# Server starts on http://127.0.0.1:5000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
# Vite dev server starts on http://localhost:5173
```

Open `http://localhost:5173` in your browser.

---

## Running Test Suites

### Unit & Integration Tests (77 tests)
```bash
pytest tests -v
```

### 11-Scenario Clean Workflow Verification
```bash
python backend/tests/verify_clean_workflow.py
```

### Final Presentation & Rejection Logic Checks
```bash
python backend/tests/verify_final_presentation.py
```

### Frontend Production Build
```bash
cd frontend
npm run build
```

---

## Security & Privacy Notice

- Real KYC documents and credentials must **never** be committed to version control.
- All documents in `storage/` and database files (`*.db`) are strictly excluded by `.gitignore`.
- Aadhaar numbers are automatically masked in extraction layers to comply with UIDAI privacy guidelines.

---

## License

This project is licensed under the MIT License.
