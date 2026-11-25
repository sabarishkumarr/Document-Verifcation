# VeriDoc AI - Synthetic KYC Test Dataset (v1.0)

**ALL DATA IN THIS DATASET IS FICTIONAL. Every image and PDF is marked `SYNTHETIC / NOT VALID FOR IDENTIFICATION`.**
It exists only to develop and test OCR / document-intelligence pipelines (Tesseract, OpenCV preprocessing, field extraction, cross-document validation).

## Safety design
- Names, addresses, photos and people are invented. Any resemblance to real persons is coincidental.
- Identifier values are **reserved sentinel patterns** that cannot be valid real-world numbers (see "Identifier rules").
- No emblems, seals, holograms, guilloche, microtext, signatures of officials or scannable QR codes. The Aadhaar-style QR area is an explicit dashed `QR PLACEHOLDER - NOT SCANNABLE` box.
- Each image carries a solid red footer band plus a tiled diagonal watermark. Do not remove them, and do not use this data in any production identity flow.
- Document headers say "STYLE" / "SPECIMEN" and the layouts are generic approximations, not replicas of official templates.

## Folder structure
```
ground_truth.json            expected fields + deliberate errors for every document
README.md                    this file
preview_contact_sheet.jpg    one-glance overview (clean front sides)
generate_dataset.py          deterministic generator (re-run to reproduce)
ocr_baseline.py              optional Tesseract baseline (raw vs OpenCV preprocessing)
applicant_NN_<name>/
    portrait_source.png      the stylised portrait used on the documents (for face-crop tests)
    aadhaar/ pan/ passport/ voter_id/ driving_licence/
        <doc>_front.(png|jpg)  <doc>_back.* (or <doc>_address_page.* for passports)
        <doc>.pdf              image-only, scan-style A4 PDF of the clean images
        <doc>_front_degraded.jpg / <doc>_back_degraded.jpg / <doc>_degraded.pdf   (only for degraded documents)
```
Clean images are PNG for most documents and JPG for a few (format variety). Degraded images are always JPG.
Total: 5 applicants x 5 documents, with PNG/JPG images and PDFs for every document.

## Applicants
| ID | Name | Profile | Deliberate issues (ground truth) |
|---|---|---|---|
| APP001 | Arvind Raghunathan Iyer | normal | none |
| APP002 | Meera Sundaram Pillai | normal | none |
| APP003 | Rohan Kishor Deshmukh | **errors** | Voter ID name printed "Rohit" (name mismatch); PAN DOB 22/07/1991 vs 27/02/1991 (incorrect DOB); Aadhaar number has 11 digits (invalid format) |
| APP004 | Fatima Zahra Sheikh | normal | none |
| APP005 | Gurpreet Singh Sandhu | **errors** | Passport expired 09/05/2023; Driving Licence expired 01/08/2024; DL address is Jalandhar vs Ludhiana elsewhere; Voter ID missing DOB; PAN has 11 characters (invalid format) |

"Normal" applicants have identical name, DOB and address across all five documents (case/format differences only, e.g. PAN prints names in UPPERCASE).
Expiry checks use the reference date **2026-11-23**.

## Degraded images (17 degraded JPGs, plus PDFs built from them)
Clean reference images are always kept alongside, so you can measure the gain from preprocessing.
| Applicant / document | Degradation (OpenCV recipe) | Suggested fix |
|---|---|---|
| APP001 PAN | perspective + 8 deg rotation + shadow gradient + noise | perspective/deskew, illumination correction |
| APP002 Passport | Gaussian blur (sigma 2.4) + 0.45x downscale/upscale | unsharp mask / super-resolution |
| APP002 Driving licence | low contrast, heavy noise, JPEG q22 | CLAHE, denoise |
| APP003 Voter ID | -12 deg rotation + salt-and-pepper noise | deskew, median filter |
| APP003 Aadhaar | horizontal-ish motion blur (k=19, 15 deg) + noise | deconvolution / sharpen |
| APP004 Aadhaar | phone-photo style: perspective + shadow + blur + 4 deg tilt | perspective correction |
| APP004 Voter ID | fax-style binarisation + speckle | morphological clean-up |
| APP005 Driving licence | rotated 90 deg (+3 deg skew) + noise | orientation detection (OSD) then deskew |
| APP005 Passport | 0.5x resolution loss + -4 deg rotation + JPEG q30 | upscale, deskew |
Exact parameters are in `ground_truth.json -> documents.<doc>.image_quality[].degradations` (rotation angles are counter-clockwise, OpenCV convention).

## ground_truth.json
Top level: `dataset` (metadata, identifier rules, conventions) and `applicants[]`.
Per applicant: `canonical_profile`, `documents`, `cross_document_expectations`.
Per document:
- `files` - every file for the document, with `image_quality` entries (clean/degraded, recipe, JPEG quality)
- `expected_fields` - the **correct, normalised** truth (ISO dates, title-case names)
- `rendered_fields` - the **exact strings printed** on the image, including deliberate errors, `null` where a field is intentionally absent. This is what a perfect OCR + extractor should return.
- `intentional_errors[]` - `field`, `error_type` (`name_mismatch`, `incorrect_dob`, `invalid_id_format`, `expired_document`, `missing_field`, `address_mismatch`), `printed_value`, `correct_value`, `description`
- `validation` - `id_matches_synthetic_pattern`, expiry/`is_expired_on_reference_date`, `missing_fields`
Per applicant `cross_document_expectations` gives `name_consistent`, `dob_consistent`, `address_consistent`, `expected_flags` and `expected_decision` (`PASS` or `FLAG_FOR_REVIEW`).

## Identifier rules (sentinel patterns)
| Document | Synthetic pattern | Why it cannot be a real number |
|---|---|---|
| Aadhaar | `0000 NNNN NNNN` | real Aadhaar numbers never begin with 0 or 1 |
| PAN | `SYNP?0000?` | numeric block 0000 is not issued |
| Passport | `Z000NNNN` | real format excludes the letter Z and a leading-zero numeric part |
| Voter ID (EPIC) | `ZZZ0000NNN` | reserved ZZZ prefix with 0000 block |
| Driving licence | `SSRR 0000 NNNNNNN` | year field 0000 is impossible |
These deliberately fail real-world validators. Point your format validator at these patterns when running on this dataset (it is a good test that your pipeline's rules are configurable), and keep the "invalid format" applicants (Aadhaar APP003, PAN APP005) as true negatives.
The passport MRZ-style lines are plain OCR-B-like text with correctly computed check digits so MRZ parsing logic can be tested; the passport number inside is a sentinel.

## Known limitations
- Portraits are procedurally drawn, stylised illustrations, **not photorealistic**. They are good for layout, cropping and face-region tests, not for face-matching/liveness evaluation.
- English only (no Devanagari/Tamil/other scripts), a single font per document, and generic layouts.
- Only 5 applicants / 25 documents; extend `APPS` in `generate_dataset.py` for more (it is deterministic and seeded).
- PDFs are image-only (scan-style) with a small vector footer; there are no born-digital text PDFs.

## Quick start
```bash
pip install pillow numpy opencv-python reportlab pytesseract   # + system tesseract
python generate_dataset.py          # optional: regenerate (OUT_DIR env var sets the output folder)
python ocr_baseline.py .            # Tesseract baseline, raw vs OpenCV-preprocessed
```
Baseline from the shipped script (identifier recovered, lenient O/0 and I/1 matching, front sides): clean images 30/30 raw; degraded images 2/11 raw and 5/11 with the simple included preprocessing. The preprocessing is intentionally basic: it is a starting point for you to beat.
