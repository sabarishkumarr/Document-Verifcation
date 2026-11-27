import os
import io
import pytest
import pymupdf
from pathlib import Path
from backend.services.classifier import DocumentClassifier
from backend.services.text_extractor import TextExtractor, find_text_bounding_box
from backend.services.field_extractor import FieldExtractor
from backend.services.validator import DocumentValidator
from backend.services.document_processor import DocumentProcessor
from backend.database.db import (
    init_db,
    get_db_connection,
    list_document_types,
    get_document_type,
    insert_document_type,
    get_document_extracted_attributes,
    get_document,
)


@pytest.fixture
def test_db_path(tmp_path):
    """Create a temporary SQLite database for testing."""
    db_file = tmp_path / "test_veridoc.db"
    init_db(str(db_file))
    return str(db_file)


class TestUniversalClassification:
    """Tests for universal document classification covering KYC and business documents."""

    def test_classify_kyc_documents(self):
        # PAN
        pan_text = "INCOME TAX DEPARTMENT GOVT OF INDIA PERMANENT ACCOUNT NUMBER CARD ABCDE1234F"
        res = DocumentClassifier.classify(pan_text)
        assert res["classified_type"] == "pan"
        assert res["confidence"] >= 0.80

        # Aadhaar
        aadhaar_text = "Government of India Unique Identification Authority of India Mera Aadhaar 1234 5678 9012"
        res = DocumentClassifier.classify(aadhaar_text)
        assert res["classified_type"] == "aadhaar"
        assert res["confidence"] >= 0.80

        # Passport
        passport_text = "REPUBLIC OF INDIA PASSPORT TYPE P CODE IND PASSPORT NO J1234567"
        res = DocumentClassifier.classify(passport_text)
        assert res["classified_type"] == "passport"
        assert res["confidence"] >= 0.80

        # Voter ID
        voter_text = "ELECTION COMMISSION OF INDIA ELECTOR PHOTO IDENTITY CARD EPIC NO WXY1234567"
        res = DocumentClassifier.classify(voter_text)
        assert res["classified_type"] == "voter_id"
        assert res["confidence"] >= 0.80

        # Driving Licence
        dl_text = "UNION OF INDIA DRIVING LICENCE LICENCE TO DRIVE MOTOR VEHICLES DL NO DL-0120150078901"
        res = DocumentClassifier.classify(dl_text)
        assert res["classified_type"] == "driving_licence"
        assert res["confidence"] >= 0.80

    def test_classify_salary_slip(self):
        text = """
        XYZ TECHNOLOGIES PVT LTD
        PAYSLIP FOR THE MONTH OF OCTOBER 2026
        EMPLOYEE NAME: RAHUL SHARMA
        EMP ID: EMP-9021
        BASIC PAY: 45000.00
        HOUSE RENT ALLOWANCE: 18000.00
        GROSS EARNINGS: 75000.00
        TOTAL DEDUCTIONS: 6500.00
        NET PAY: 68500.00
        """
        res = DocumentClassifier.classify(text)
        assert res["classified_type"] == "salary_slip"
        assert res["category"] == "financial"
        assert res["confidence"] >= 0.80
        assert "SALARY SLIP" in res["matched_keywords"] or "PAYSLIP" in res["matched_keywords"]

    def test_classify_bank_statement(self):
        text = """
        HDFC BANK LIMITED
        STATEMENT OF ACCOUNT
        ACCOUNT NUMBER: 987654321012
        IFSC CODE: HDFC0001234
        BRANCH: CONNAUGHT PLACE NEW DELHI
        TRANSACTION DATE: 15/10/2026
        WITHDRAWAL: 5000.00
        DEPOSIT: 25000.00
        CLOSING BALANCE: 142500.50
        """
        res = DocumentClassifier.classify(text)
        assert res["classified_type"] == "bank_statement"
        assert res["category"] == "financial"
        assert res["confidence"] >= 0.80

    def test_classify_commercial_invoice(self):
        text = """
        TAX INVOICE
        INVOICE NUMBER: INV-2026-089
        INVOICE DATE: 12/10/2026
        BILL TO: ACME SUPPLIERS
        GSTIN: 27AABCB1234F1Z5
        SUBTOTAL: 40000.00
        CGST: 2500.00
        SGST: 2500.00
        GRAND TOTAL: 45000.00
        DUE DATE: 12/11/2026
        """
        res = DocumentClassifier.classify(text)
        assert res["classified_type"] == "commercial_invoice"
        assert res["category"] == "commercial"
        assert res["confidence"] >= 0.80

    def test_classify_tax_form_16(self):
        text = """
        FORM NO. 16
        CERTIFICATE UNDER SECTION 203 OF THE INCOME-TAX ACT, 1961
        TAN OF DEDUCTOR: DELS12345A
        PAN OF EMPLOYEE: ABCDE1234F
        ASSESSMENT YEAR: 2026-27
        SUMMARY OF TAX DEDUCTED AT SOURCE
        TOTAL TAX DEDUCTED: 35000.00
        """
        res = DocumentClassifier.classify(text)
        assert res["classified_type"] == "tax_form_16"
        assert res["category"] == "tax"
        assert res["confidence"] >= 0.80

    def test_classify_utility_bill(self):
        text = """
        BSES RAJDHANI POWER LIMITED
        ELECTRICITY BILL
        CONSUMER NUMBER: CN-8849201
        METER NUMBER: MTR-99210
        BILLING PERIOD: 01/09/2026 TO 30/09/2026
        UNITS CONSUMED: 320
        BILL AMOUNT: 2450.00
        DUE DATE: 25/10/2026
        DISCONNECTION DATE: 10/11/2026
        """
        res = DocumentClassifier.classify(text)
        assert res["classified_type"] == "utility_bill"
        assert res["category"] == "utility"
        assert res["confidence"] >= 0.80

    def test_dynamic_document_type_from_database(self, test_db_path):
        # Register a new custom document type
        custom_type = {
            "id": "medical_fitness_certificate",
            "display_name": "Medical Fitness Certificate",
            "category": "medical",
            "is_system": False,
            "description": "Hospital medical fitness certificate",
            "rules_json": {
                "keywords": [
                    {"keyword": "MEDICAL FITNESS CERTIFICATE", "weight": 50},
                    {"keyword": "REGISTERED MEDICAL PRACTITIONER", "weight": 40},
                    {"keyword": "PHYSICALLY FIT", "weight": 35}
                ]
            }
        }
        insert_document_type(custom_type, db_path=test_db_path)

        text = """
        HOSPITAL OF DELHI
        MEDICAL FITNESS CERTIFICATE
        THIS IS TO CERTIFY THAT THE CANDIDATE IS PHYSICALLY FIT
        REGISTERED MEDICAL PRACTITIONER
        """
        res = DocumentClassifier.classify(text, db_path=test_db_path)
        assert res["classified_type"] == "medical_fitness_certificate"
        assert res["display_name"] == "Medical Fitness Certificate"
        assert res["category"] == "medical"
        assert res["confidence"] >= 0.80


class TestSpatialTextExtraction:
    """Tests for spatial token extraction and bounding box locator."""

    def test_spatial_token_locator(self):
        tokens = [
            {"text": "INCOME", "bbox": [100, 150, 130, 250], "page": 1},
            {"text": "TAX", "bbox": [100, 260, 130, 320], "page": 1},
            {"text": "DEPARTMENT", "bbox": [100, 330, 130, 500], "page": 1},
            {"text": "ABCDE1234F", "bbox": [300, 200, 340, 450], "page": 1},
            {"text": "NET", "bbox": [500, 100, 530, 180], "page": 1},
            {"text": "PAY:", "bbox": [500, 190, 530, 250], "page": 1},
            {"text": "68500.00", "bbox": [500, 260, 530, 400], "page": 1},
        ]

        # Multi-word match
        bbox1 = find_text_bounding_box("INCOME TAX DEPARTMENT", tokens)
        assert bbox1 == [100, 150, 130, 500]

        # Single word match
        bbox2 = find_text_bounding_box("ABCDE1234F", tokens)
        assert bbox2 == [300, 200, 340, 450]

        # Number match with partial punctuation
        bbox3 = find_text_bounding_box("68500.00", tokens)
        assert bbox3 == [500, 260, 530, 400]

        # Non-existent text
        bbox4 = find_text_bounding_box("NONEXISTENT", tokens)
        assert bbox4 is None

    def test_pdf_spatial_extraction(self, tmp_path):
        # Generate a small test PDF with digital words
        pdf_path = tmp_path / "test_doc.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        page.insert_text((50, 100), "TAX INVOICE INV-2026-999")
        page.insert_text((50, 200), "TOTAL AMOUNT 50000.00")
        doc.save(str(pdf_path))
        doc.close()

        extractor = TextExtractor()
        res = extractor.extract_spatial_tokens(pdf_path)
        assert res["status"] == "success"
        assert res["total_tokens"] > 0
        assert "spatial_tokens" in res

        # Find invoice number bounding box from spatial tokens
        bbox = find_text_bounding_box("INV-2026-999", res["spatial_tokens"])
        assert bbox is not None
        assert len(bbox) == 4
        # Normalized coordinates between 0 and 1000
        assert 0 <= bbox[0] <= 1000
        assert 0 <= bbox[1] <= 1000
        assert 0 <= bbox[2] <= 1000
        assert 0 <= bbox[3] <= 1000


class TestDynamicAttributePersistence:
    """Tests verifying dynamic attributes persistence and validation."""

    def test_pipeline_attributes_persistence(self, tmp_path, test_db_path):
        # Create test PDF
        pdf_path = tmp_path / "salary_slip.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        page.insert_text((50, 80), "XYZ CORP SALARY SLIP")
        page.insert_text((50, 120), "Employee Name: ANANYA DESHMUKH")
        page.insert_text((50, 160), "Emp ID: EMP-8821")
        page.insert_text((50, 200), "Net Salary: 72000.00")
        page.insert_text((50, 240), "Basic Salary: 50000.00")
        doc.save(str(pdf_path))
        doc.close()

        # Register document
        from werkzeug.datastructures import FileStorage
        processor = DocumentProcessor(
            upload_folder=tmp_path / "uploads",
            db_path=test_db_path,
            ai_provider="mock"
        )
        with open(pdf_path, "rb") as f:
            fs = FileStorage(stream=io.BytesIO(f.read()), filename="salary_slip.pdf", content_type="application/pdf")
            saved = processor.save_and_register_document(fs)

        doc_id = saved["id"]
        result = processor.process_document_pipeline(doc_id)

        assert result["processing_status"] == "completed"
        assert result["classification"]["classified_type"] == "salary_slip"

        # Check attributes were persisted in document_extracted_attributes
        db_attrs = get_document_extracted_attributes(doc_id, db_path=test_db_path)
        assert len(db_attrs) >= 3

        # Verify attributes exist with normalized structure
        attr_keys = [a["attribute_key"] for a in db_attrs]
        assert "employee_name" in attr_keys or "name" in attr_keys
        assert any(k in attr_keys for k in ["net_salary", "employee_id", "basic_salary"])

        # Check attributes JSON synchronized in documents table
        persisted_doc = get_document(doc_id, db_path=test_db_path)
        assert persisted_doc["classified_type"] == "salary_slip"
        import json
        extracted_fields = json.loads(persisted_doc["extracted_fields"]) if isinstance(persisted_doc["extracted_fields"], str) else persisted_doc["extracted_fields"]
        assert "attributes" in extracted_fields
        assert len(extracted_fields["attributes"]) >= 3
