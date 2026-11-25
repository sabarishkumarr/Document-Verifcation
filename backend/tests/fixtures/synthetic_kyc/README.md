# VeriDoc AI — Synthetic KYC Testing Dataset

**Specification:** Complete synthetic test fixtures covering Indian KYC document verification pipelines.
**Generated On:** 2026-11-23 04:55:01 UTC
**Watermark Notice:** All files contain prominent top, diagonal, and bottom watermarks:
`SYNTHETIC TEST DOCUMENT — NOT VALID FOR IDENTIFICATION`
**PII Disclaimer:** 100% fictional applicants and test identity strings. No real individuals, real Aadhaar numbers, or active government credentials are used. Full Aadhaar numbers are masked to `XXXX-XXXX-XXXX`.

---

## Dataset Summary

| Total Applicants | Total Documents | PDF Documents | Image Scans (JPG/PNG) | Supported Document Types |
|:---:|:---:|:---:|:---:|:---:|
| **10** | **25** | **19** | **6** | PAN, Aadhaar, Passport, Voter ID, Driving Licence |

---

## Applicant Profiles & Test Scenarios

### 1. Aarav Mehta (`APPL-SYN-001`)
- **Folder:** `01_aarav_mehta/`
- **Contact:** `aarav.mehta@synthetic-test.veridoc.ai` | `+91 98200 11001`
- **Scenario:** Matching PAN and Aadhaar records with consistent name and DOB.
- **Expected Verification Verdict:** `VERIFIED`
- **Expected Cross-Document Consistency:** `100.0%`
- **Included Documents (2):**

| Filename | Format | Category | Expected Classification | Expected Validation |
|:---|:---:|:---:|:---:|:---|
| `aarav_mehta_pan.pdf` | `PDF` | `PAN` | `pan` | `valid` |
| `aarav_mehta_aadhaar.pdf` | `PDF` | `AADHAAR` | `aadhaar` | `valid` |

### 2. Priya Sharma (`APPL-SYN-002`)
- **Folder:** `02_priya_sharma/`
- **Contact:** `priya.sharma@synthetic-test.veridoc.ai` | `+91 98190 22002`
- **Scenario:** Matching PAN, Aadhaar (image scan) and Passport across all identity fields.
- **Expected Verification Verdict:** `VERIFIED`
- **Expected Cross-Document Consistency:** `100.0%`
- **Included Documents (3):**

| Filename | Format | Category | Expected Classification | Expected Validation |
|:---|:---:|:---:|:---:|:---|
| `priya_sharma_pan.pdf` | `PDF` | `PAN` | `pan` | `valid` |
| `priya_sharma_aadhaar.png` | `PNG` | `AADHAAR` | `aadhaar` | `valid` |
| `priya_sharma_passport.pdf` | `PDF` | `PASSPORT` | `passport` | `valid` |

### 3. Rohan Nair (`APPL-SYN-003`)
- **Folder:** `03_rohan_nair/`
- **Contact:** `rohan.nair@synthetic-test.veridoc.ai` | `+91 94471 33003`
- **Scenario:** Expired Driving Licence (expired 2022) with valid PAN.
- **Expected Verification Verdict:** `MANUAL_REVIEW`
- **Expected Cross-Document Consistency:** `95.0%`
- **Included Documents (2):**

| Filename | Format | Category | Expected Classification | Expected Validation |
|:---|:---:|:---:|:---:|:---|
| `rohan_nair_pan.pdf` | `PDF` | `PAN` | `pan` | `valid` |
| `rohan_nair_driving_licence.pdf` | `PDF` | `DRIVING_LICENCE` | `driving_licence` | `invalid (expired)` |

### 4. Ananya Iyer (`APPL-SYN-004`)
- **Folder:** `04_ananya_iyer/`
- **Contact:** `ananya.iyer@synthetic-test.veridoc.ai` | `+91 97650 44004`
- **Scenario:** Cross-document name mismatch ('Ananya Iyer' on Aadhaar vs 'Ananya Subramanian' on Voter ID).
- **Expected Verification Verdict:** `DISCREPANCY_FLAGGED`
- **Expected Cross-Document Consistency:** `60.0%`
- **Included Documents (2):**

| Filename | Format | Category | Expected Classification | Expected Validation |
|:---|:---:|:---:|:---:|:---|
| `ananya_iyer_aadhaar.pdf` | `PDF` | `AADHAAR` | `aadhaar` | `valid` |
| `ananya_iyer_voter_id.jpg` | `JPG` | `VOTER_ID` | `voter_id` | `valid` |

### 5. Kabir Malhotra (`APPL-SYN-005`)
- **Folder:** `05_kabir_malhotra/`
- **Contact:** `kabir.malhotra@synthetic-test.veridoc.ai` | `+91 98450 55005`
- **Scenario:** Severe Date of Birth mismatch: 14/04/1983 on PAN vs 28/11/1989 on Passport (6-year disparity).
- **Expected Verification Verdict:** `DISCREPANCY_FLAGGED`
- **Expected Cross-Document Consistency:** `55.0%`
- **Included Documents (2):**

| Filename | Format | Category | Expected Classification | Expected Validation |
|:---|:---:|:---:|:---:|:---|
| `kabir_malhotra_pan.pdf` | `PDF` | `PAN` | `pan` | `valid` |
| `kabir_malhotra_passport.pdf` | `PDF` | `PASSPORT` | `passport` | `valid` |

### 6. Meera Krishnan (`APPL-SYN-006`)
- **Folder:** `06_meera_krishnan/`
- **Contact:** `meera.krishnan@synthetic-test.veridoc.ai` | `+91 93300 66006`
- **Scenario:** Missing critical fields: PAN document has no ID number or DOB; Voter ID lacks name.
- **Expected Verification Verdict:** `MANUAL_REVIEW`
- **Expected Cross-Document Consistency:** `40.0%`
- **Included Documents (2):**

| Filename | Format | Category | Expected Classification | Expected Validation |
|:---|:---:|:---:|:---:|:---|
| `meera_krishnan_pan_incomplete.pdf` | `PDF` | `PAN` | `pan` | `invalid (missing ID number, missing DOB)` |
| `meera_krishnan_voter_id.pdf` | `PDF` | `VOTER_ID` | `voter_id` | `invalid (missing name and DOB)` |

### 7. Dev Patel (`APPL-SYN-007`)
- **Folder:** `07_dev_patel/`
- **Contact:** `dev.patel@synthetic-test.veridoc.ai` | `+91 98220 77007`
- **Scenario:** Passport expired over 4 years ago (expired 2020) requiring re-submission.
- **Expected Verification Verdict:** `MANUAL_REVIEW`
- **Expected Cross-Document Consistency:** `95.0%`
- **Included Documents (2):**

| Filename | Format | Category | Expected Classification | Expected Validation |
|:---|:---:|:---:|:---:|:---|
| `dev_patel_pan.pdf` | `PDF` | `PAN` | `pan` | `valid` |
| `dev_patel_passport_expired.pdf` | `PDF` | `PASSPORT` | `passport` | `invalid (expired)` |

### 8. Ishita Rao (`APPL-SYN-008`)
- **Folder:** `08_ishita_rao/`
- **Contact:** `ishita.rao@synthetic-test.veridoc.ai` | `+91 98410 88008`
- **Scenario:** Low-quality, heavily blurred scan of PAN card paired with clean Aadhaar reference.
- **Expected Verification Verdict:** `MANUAL_REVIEW`
- **Expected Cross-Document Consistency:** `50.0%`
- **Included Documents (2):**

| Filename | Format | Category | Expected Classification | Expected Validation |
|:---|:---:|:---:|:---:|:---|
| `ishita_rao_aadhaar.pdf` | `PDF` | `AADHAAR` | `aadhaar` | `valid` |
| `ishita_rao_pan_low_quality.jpg` | `JPG` | `PAN` | `pan / unknown` | `warning / invalid (unreadable)` |

### 9. Vikram Das (`APPL-SYN-009`)
- **Folder:** `09_vikram_das/`
- **Contact:** `vikram.das@synthetic-test.veridoc.ai` | `+91 97110 99009`
- **Scenario:** Complete consistency check across 3 documents: PAN, Aadhaar and Driving Licence.
- **Expected Verification Verdict:** `VERIFIED`
- **Expected Cross-Document Consistency:** `100.0%`
- **Included Documents (3):**

| Filename | Format | Category | Expected Classification | Expected Validation |
|:---|:---:|:---:|:---:|:---|
| `vikram_das_pan.pdf` | `PDF` | `PAN` | `pan` | `valid` |
| `vikram_das_aadhaar.pdf` | `PDF` | `AADHAAR` | `aadhaar` | `valid` |
| `vikram_das_driving_licence.png` | `PNG` | `DRIVING_LICENCE` | `driving_licence` | `valid` |

### 10. Neha Kapoor (`APPL-SYN-010`)
- **Folder:** `10_neha_kapoor/`
- **Contact:** `neha.kapoor@synthetic-test.veridoc.ai` | `+91 99880 11010`
- **Scenario:** Comprehensive 5-document KYC dossier covering all five supported categories with 100% correlation.
- **Expected Verification Verdict:** `VERIFIED`
- **Expected Cross-Document Consistency:** `100.0%`
- **Included Documents (5):**

| Filename | Format | Category | Expected Classification | Expected Validation |
|:---|:---:|:---:|:---:|:---|
| `neha_kapoor_pan.pdf` | `PDF` | `PAN` | `pan` | `valid` |
| `neha_kapoor_aadhaar.pdf` | `PDF` | `AADHAAR` | `aadhaar` | `valid` |
| `neha_kapoor_passport.pdf` | `PDF` | `PASSPORT` | `passport` | `valid` |
| `neha_kapoor_voter_id.jpg` | `JPG` | `VOTER_ID` | `voter_id` | `valid` |
| `neha_kapoor_driving_licence.pdf` | `PDF` | `DRIVING_LICENCE` | `driving_licence` | `valid` |

---

## How to Seed the Database (Idempotent)

To seed these 10 applicants and their 25 documents into your local SQLite database:

```bash
.\backend\venv\Scripts\python.exe backend/tests/fixtures/synthetic_kyc/seed_synthetic_kyc.py --seed
```

Or run directly from Python:
```python
from backend.tests.fixtures.synthetic_kyc.seed_synthetic_kyc import seed_synthetic_dataset
seed_synthetic_dataset()
```

## How to Upload through the Frontend

1. Ensure the backend and frontend dev servers are running.
2. Open the VeriDoc AI Web UI at `http://localhost:5173/`.
3. Click **"Enter workspace ↗"** -> **"Upload Documents"**.
4. Drag and drop any file from `backend/tests/fixtures/synthetic_kyc/<applicant>/` into the upload zone.
5. Watch the real-time PyMuPDF/Tesseract extraction, classification, field extraction, and validation execute.

---

## Pipeline Test Execution & Benchmark Results

Run the automated test runner to process all 25 documents through the full pipeline:

```bash
.\backend\venv\Scripts\python.exe backend/tests/fixtures/synthetic_kyc/seed_synthetic_kyc.py
```

### Actual Benchmark Execution Results (25 Samples)

| Applicant | Filename | Format | Classified Category | OCR Chars | Validation Status | Cross-Doc Verdict |
|:---|:---|:---:|:---:|:---:|:---:|:---:|
| **Aarav Mehta** | `aarav_mehta_pan.pdf` | PDF | `pan` | 469 | `valid` | `VERIFIED` (100%) |
| | `aarav_mehta_aadhaar.pdf` | PDF | `aadhaar` | 443 | `valid` | |
| **Priya Sharma** | `priya_sharma_pan.pdf` | PDF | `pan` | 437 | `valid` | `VERIFIED` (100%) |
| | `priya_sharma_aadhaar.png` | PNG | `aadhaar` | 407 | `valid` | |
| | `priya_sharma_passport.pdf` | PDF | `passport` | 500 | `valid` | |
| **Rohan Nair** | `rohan_nair_pan.pdf` | PDF | `pan` | 434 | `valid` | `MANUAL_REVIEW` |
| | `rohan_nair_driving_licence.pdf` | PDF | `driving_licence` | 472 | `invalid` (expired) | (DL expired 2022-04-12) |
| **Ananya Iyer** | `ananya_iyer_aadhaar.pdf` | PDF | `aadhaar` | 445 | `valid` | `DISCREPANCY_FLAGGED` |
| | `ananya_iyer_voter_id.jpg` | JPG | `voter_id` | 382 | `valid` | (Name match: 55.2%) |
| **Kabir Malhotra** | `kabir_malhotra_pan.pdf` | PDF | `pan` | 439 | `valid` | `DISCREPANCY_FLAGGED` |
| | `kabir_malhotra_passport.pdf` | PDF | `passport` | 470 | `valid` | (DOB: 1983 vs 1989) |
| **Meera Krishnan** | `meera_krishnan_pan_incomplete.pdf` | PDF | `pan` | 423 | `invalid` | `MANUAL_REVIEW` |
| | `meera_krishnan_voter_id.pdf` | PDF | `voter_id` | 411 | `warning` | (Missing mandatory fields) |
| **Dev Patel** | `dev_patel_pan.pdf` | PDF | `pan` | 433 | `valid` | `MANUAL_REVIEW` |
| | `dev_patel_passport_expired.pdf` | PDF | `passport` | 469 | `invalid` (expired) | (Passport expired 2020) |
| **Ishita Rao** | `ishita_rao_aadhaar.pdf` | PDF | `aadhaar` | 449 | `valid` | `PENDING_ADDITIONAL_DOCS` |
| | `ishita_rao_pan_low_quality.jpg` | JPG | `unknown` | 11 | `invalid` (unreadable) | (Degraded scan rejected) |
| **Vikram Das** | `vikram_das_pan.pdf` | PDF | `pan` | 430 | `valid` | `VERIFIED` (100%) |
| | `vikram_das_aadhaar.pdf` | PDF | `aadhaar` | 433 | `valid` | |
| | `vikram_das_driving_licence.png` | PNG | `driving_licence` | 432 | `valid` | |
| **Neha Kapoor** | `neha_kapoor_pan.pdf` | PDF | `pan` | 435 | `valid` | `VERIFIED` (100%) |
| | `neha_kapoor_aadhaar.pdf` | PDF | `aadhaar` | 440 | `valid` | (All 5 KYC categories) |
| | `neha_kapoor_passport.pdf` | PDF | `passport` | 469 | `valid` | |
| | `neha_kapoor_voter_id.jpg` | JPG | `voter_id` | 374 | `valid` | |
| | `neha_kapoor_driving_licence.pdf` | PDF | `driving_licence` | 473 | `valid` | |

