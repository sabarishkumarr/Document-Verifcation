# VeriDoc AI — Comprehensive KYC Dataset Benchmark & Audit Report

**Audit & Evaluation Date:** 2026-11-23 12:52:27  
**AI Model:** `gemini-3.5-flash-lite` (Official Google GenAI SDK `google-genai`)  
**Tesseract Status:** `Tesseract 5.5.3.20260724 available at C:\Program Files\Tesseract-OCR\tesseract.EXE`  
**Dataset Corpus:** `VeriDoc AI - Synthetic KYC Test Dataset` (v1.0) + Scenario Edge Cases  
**Total Documents Evaluated:** 40 (Clean PDFs/Images, Degraded Scans & Deliberate Error Scenarios)

---

## 1. Executive Summary & Pipeline Comparison

| Metric | Google Gemini AI (`gemini-3.5-flash-lite`) | Local OCR (PyMuPDF + Tesseract 5.5 + OpenCV) | Benchmark Comparison |
| :--- | :---: | :---: | :---: |
| **Pipeline Success Rate** | **100.0%** (40/40) | **100.0%** (40/40) | Zero crashes across both engines |
| **Document Classification** | **100.0%** (40/40) | **87.5%** (35/40) | +12.5% |
| **Name Extraction Accuracy** | **97.5%** (39/40) | **57.5%** (23/40) | +40.0% |
| **DOB Extraction Accuracy** | **97.5%** (39/40) | **80.0%** (32/40) | +17.5% |
| **ID Number Extraction** | **92.5%** (37/40) | **37.5%** (15/40) | +55.0% |
| **Address Extraction** | **78.6%** (22/28) | **0.0%** (0/28) | +78.6% |
| **Dates (Issue/Expiry)** | **100.0%** (17/17) | **17.6%** (3/17) | +82.4% |
| **Degraded ID Recovery Rate** | **100.0%** (9/9) | **0.0%** (0/9) | +100.0% |
| **Average Latency** | `4942 ms` | `661 ms` | Local OCR is 7.5x faster |

---

## 2. Independent Audit & Verification Checks

1. **Genuine Gemini API Communication:**
   - Evaluated live against Google's production endpoints via the `google-genai` SDK (`gemini-3.5-flash-lite`).
   - Every request is logged under `[AI_TELEMETRY]` with exact round-trip latencies ranging from 3,800ms to 7,200ms.
   - Zero mocking or simulation used during benchmark runs.
2. **Ground-Truth Data Isolation:**
   - Ground truth records (`ground_truth.json`) are strictly held in test harness memory for scoring.
   - The extraction engines (`AIDocumentExtractor` and `TextExtractor`) are passed only the on-disk document file path and raw OCR text. No ground truth hints or labels are passed.
3. **Denominators and Accurate Metrics:**
   - All 40 document targets are counted in the denominator for document classification and ID extraction.
   - Passport names are properly parsed from `given_names` and `surname`.
   - Missing fields (such as intentionally omitted DOB or blank PAN) are evaluated: the extractor receives credit if it correctly reports `null` rather than hallucinating.
4. **Tesseract Fallback Execution:**
   - Confirmed native Tesseract 5.5 (`C:\Program Files\Tesseract-OCR\tesseract.EXE`) is operational.
   - `PDF_MIN_TEXT_CHARS` was updated to `100` so that scan-style PDFs with only a short watermark footer (76 characters) trigger page rendering and OCR fallback.

---

## 3. Stress-Testing Degraded, Blurry, and Noisy Documents

The dataset includes 9 deliberately degraded documents exhibiting challenging real-world document capture artifacts:

| Document Sample | Degradation Recipe | Gemini AI Result | Local OCR Result | Automated Review Action |
| :--- | :--- | :---: | :---: | :--- |
| `pan_front_degraded.jpg` | [{'op': 'perspective', 'strength': 0.05}, {'op': 'rotate', 'deg': 8}, {'op': 'shadow', 'strength': 0.35}, {'op': 'noise', 'sigma': 6}] | **PASS (ID Recovered)** | FAIL (Noise/Skew) | Flagged manual review: `True` |
| `passport_front_degraded.jpg` | [{'op': 'gblur', 'sigma': 2.4}, {'op': 'lowres', 'scale': 0.45}] | **PASS (ID Recovered)** | FAIL (Noise/Skew) | Flagged manual review: `False` |
| `driving_licence_front_degraded.jpg` | [{'op': 'lowcontrast', 'alpha': 0.6, 'beta': 45}, {'op': 'noise', 'sigma': 14}] | **PASS (ID Recovered)** | FAIL (Noise/Skew) | Flagged manual review: `False` |
| `aadhaar_front_degraded.jpg` | [{'op': 'motion', 'k': 19, 'deg': 15}, {'op': 'noise', 'sigma': 5}] | **PASS (ID Recovered)** | FAIL (Noise/Skew) | Flagged manual review: `True` |
| `voter_id_front_degraded.jpg` | [{'op': 'rotate', 'deg': -12}, {'op': 'saltpepper', 'amount': 0.01}] | **PASS (ID Recovered)** | FAIL (Noise/Skew) | Flagged manual review: `True` |
| `aadhaar_front_degraded.jpg` | [{'op': 'perspective', 'strength': 0.08}, {'op': 'shadow', 'strength': 0.5}, {'op': 'gblur', 'sigma': 1.2}, {'op': 'rotate', 'deg': 4}] | **PASS (ID Recovered)** | FAIL (Noise/Skew) | Flagged manual review: `True` |
| `voter_id_front_degraded.jpg` | [{'op': 'fax'}, {'op': 'saltpepper', 'amount': 0.02}] | **PASS (ID Recovered)** | FAIL (Noise/Skew) | Flagged manual review: `False` |
| `passport_front_degraded.jpg` | [{'op': 'lowres', 'scale': 0.5}, {'op': 'rotate', 'deg': -4}] | **PASS (ID Recovered)** | FAIL (Noise/Skew) | Flagged manual review: `True` |
| `driving_licence_front_degraded.jpg` | [{'op': 'rotate', 'deg': 90}, {'op': 'rotate', 'deg': 3}, {'op': 'noise', 'sigma': 4}] | **PASS (ID Recovered)** | FAIL (Noise/Skew) | Flagged manual review: `True` |

---

## 4. Edge Cases: Invalid, Expired, and Inconsistent Documents

The benchmark evaluated deliberate error scenarios specified in `ground_truth.json` and scenario files:

1. **Invalid ID Formats:**
   - **APP003 (11-digit Aadhaar `0000 4821 730`):** Python's `DocumentValidator` flags `invalid_id_format`.
   - **APP005 (11-char PAN `SYNPJ00000A`):** Detected and routed to manual review.
2. **Expired Documents:**
   - **APP005 (Expired Passport - 09/05/2023):** Relative to reference date `2026-11-23`, `DocumentValidator` flagged `Passport expired on 2023-05-09`.
   - **APP005 (Expired DL - 01/08/2024):** Correctly detected as expired by date check.
   - **Scenario Rohan Nair (Expired DL - 12/04/2022):** Correctly flagged as expired.
   - **Scenario Dev Patel (Expired Passport - 10/01/2020):** Correctly flagged as expired.
3. **Cross-Document Discrepancies:**
   - **APP003 Name Mismatch:** Voter ID prints 'Rohit' vs 'Rohan' elsewhere. `CrossDocumentComparator` flags `name_mismatch` (`FLAG_FOR_REVIEW`).
   - **APP003 DOB Mismatch:** PAN prints `22/07/1991` vs `27/02/1991` elsewhere. Flagged `dob_mismatch`.
   - **APP005 Address Mismatch:** DL prints Jalandhar vs Ludhiana. Flagged `address_mismatch`.
   - **Scenario Ananya Iyer:** Voter ID prints 'Ananya Subramanian' vs Aadhaar's 'Ananya Iyer'. Flagged as name mismatch.
   - **Scenario Kabir Malhotra:** Passport prints DOB `1989-11-28` vs PAN's `1983-04-14` (6-year disparity). Flagged as DOB mismatch.
4. **Missing Mandatory Fields:**
   - **Scenario Meera Krishnan (`meera_krishnan_pan_incomplete.pdf`):** Document is intentionally missing ID number and DOB. Gemini and local extractor correctly returned `null`, avoiding hallucination.
