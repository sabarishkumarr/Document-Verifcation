import pytest
from pathlib import Path
import fitz
from PIL import Image
import pytesseract

from backend.tests.fixtures.synthetic_kyc.seed_synthetic_kyc import (
    SYNTHETIC_KYC_APPLICANTS,
    FIXTURES_DIR,
    WATERMARK_TEXT,
    seed_synthetic_dataset
)
from backend.services.document_processor import DocumentProcessor
from backend.services.classifier import DocumentClassifier
from backend.services.field_extractor import FieldExtractor
from backend.services.validator import DocumentValidator
from backend.services.comparator import CrossDocumentComparator


def test_fixtures_directory_and_files_exist():
    """Verify that all 10 applicant directories and 25 documents exist on disk."""
    assert FIXTURES_DIR.exists()
    assert (FIXTURES_DIR / "README.md").exists()

    total_files = 0
    for app in SYNTHETIC_KYC_APPLICANTS:
        app_dir = FIXTURES_DIR / app["folder"]
        assert app_dir.exists(), f"Applicant folder {app_dir} does not exist"
        for doc in app["documents"]:
            doc_path = app_dir / doc["filename"]
            assert doc_path.exists(), f"Fixture file {doc_path} does not exist"
            assert doc_path.stat().st_size > 0, f"Fixture file {doc_path} is empty"
            total_files += 1

    assert total_files == 25, f"Expected 25 documents, found {total_files}"


def test_watermark_present_in_fixtures():
    """Verify that every PDF fixture contains the exact prominent watermark."""
    for app in SYNTHETIC_KYC_APPLICANTS:
        app_dir = FIXTURES_DIR / app["folder"]
        for doc in app["documents"]:
            if doc["format"] == "pdf":
                doc_path = app_dir / doc["filename"]
                pdf_doc = fitz.open(str(doc_path))
                text = ""
                for page in pdf_doc:
                    text += page.get_text()
                pdf_doc.close()
                assert "SYNTHETIC TEST DOCUMENT" in text, f"Missing watermark in {doc_path}"


def test_scenarios_classification_and_validation():
    """Verify classification and edge case expectations on key test applicants."""
    # Scenario 1: Aarav Mehta (PAN & Aadhaar match)
    aarav_pan = FIXTURES_DIR / "01_aarav_mehta" / "aarav_mehta_pan.pdf"
    aarav_doc = fitz.open(str(aarav_pan))
    pan_text = aarav_doc[0].get_text()
    aarav_doc.close()

    pan_cls = DocumentClassifier.classify(pan_text)
    assert pan_cls["classified_type"] == "pan"
    pan_fields = FieldExtractor.extract_fields(pan_text, "pan")
    assert pan_fields["name"] == "AARAV MEHTA"
    assert pan_fields["id_number"] == "ABCPM1234D"
    pan_val = DocumentValidator.validate("pan", pan_fields, pan_text)
    assert pan_val["is_valid"] is True

    # Scenario 3: Rohan Nair (Expired Driving Licence)
    rohan_dl = FIXTURES_DIR / "03_rohan_nair" / "rohan_nair_driving_licence.pdf"
    rohan_doc = fitz.open(str(rohan_dl))
    dl_text = rohan_doc[0].get_text()
    rohan_doc.close()

    dl_cls = DocumentClassifier.classify(dl_text)
    assert dl_cls["classified_type"] == "driving_licence"
    dl_fields = FieldExtractor.extract_fields(dl_text, "driving_licence")
    assert dl_fields["expiry_date"] == "2022-04-12"
    dl_val = DocumentValidator.validate("driving_licence", dl_fields, dl_text)
    assert dl_val["is_valid"] is False
    assert any("expired" in flag.lower() for flag in dl_val["flags"])

    # Scenario 5: Kabir Malhotra (DOB mismatch between PAN and Passport)
    kabir_pan = fitz.open(str(FIXTURES_DIR / "05_kabir_malhotra" / "kabir_malhotra_pan.pdf"))
    kabir_pass = fitz.open(str(FIXTURES_DIR / "05_kabir_malhotra" / "kabir_malhotra_passport.pdf"))
    k_pan_fields = FieldExtractor.extract_fields(kabir_pan[0].get_text(), "pan")
    k_pass_fields = FieldExtractor.extract_fields(kabir_pass[0].get_text(), "passport")
    kabir_pan.close()
    kabir_pass.close()

    comp = CrossDocumentComparator.compare_applicant_documents([
        {"id": "doc1", "classified_type": "pan", "extracted_fields": k_pan_fields},
        {"id": "doc2", "classified_type": "passport", "extracted_fields": k_pass_fields}
    ], "Kabir Malhotra")
    assert comp["overall_verdict"] == "DISCREPANCY_FLAGGED"
    assert any("DOB mismatch" in d for d in comp["discrepancies"])

    # Scenario 6: Meera Krishnan (Missing mandatory fields)
    meera_pan = fitz.open(str(FIXTURES_DIR / "06_meera_krishnan" / "meera_krishnan_pan_incomplete.pdf"))
    m_pan_fields = FieldExtractor.extract_fields(meera_pan[0].get_text(), "pan")
    meera_pan.close()
    m_val = DocumentValidator.validate("pan", m_pan_fields)
    assert m_val["is_valid"] is False
    assert "PAN number missing from document" in m_val["flags"]

    # Scenario 7: Dev Patel (Expired Passport)
    dev_pass = fitz.open(str(FIXTURES_DIR / "07_dev_patel" / "dev_patel_passport_expired.pdf"))
    d_pass_fields = FieldExtractor.extract_fields(dev_pass[0].get_text(), "passport")
    dev_pass.close()
    d_val = DocumentValidator.validate("passport", d_pass_fields)
    assert d_val["is_valid"] is False
    assert any("expired" in flag.lower() for flag in d_val["flags"])
