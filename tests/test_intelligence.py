import io
import json
import pytest
import pymupdf
from backend.services.classifier import DocumentClassifier
from backend.services.field_extractor import FieldExtractor, mask_aadhaar
from backend.services.validator import DocumentValidator
from backend.services.comparator import CrossDocumentComparator
from backend.database.db import get_document, get_applicant


# =============================================================================
# 1. Document Classifier Tests
# =============================================================================
def test_classifier_pan():
    sample_text = """
    INCOME TAX DEPARTMENT
    GOVT. OF INDIA
    Permanent Account Number: ABCDE1234F
    Name: PRIYA SHARMA
    Father's Name: RAMESH SHARMA
    DOB: 14/05/1990
    Signature
    """
    res = DocumentClassifier.classify(sample_text)
    assert res["classified_type"] == "pan"
    assert res["confidence"] > 0.8
    assert "INCOME TAX DEPARTMENT" in res["matched_keywords"]


def test_classifier_aadhaar():
    sample_text = """
    Government of India
    Unique Identification Authority of India
    Enrolment No: 1234/56789/01234
    To: Siddharth Nair
    DOB: 20/08/1988
    MALE
    3456 7890 1234
    VID: 9182 3456 7890 1234
    Mera Aadhaar, Meri Pehchan
    """
    res = DocumentClassifier.classify(sample_text)
    assert res["classified_type"] == "aadhaar"
    assert res["confidence"] > 0.8


def test_classifier_passport():
    sample_text = """
    REPUBLIC OF INDIA
    PASSPORT
    Type: P
    Code: IND
    Passport No: Z1234567
    Surname: DESHMUKH
    Given Names: ANANYA
    Nationality: INDIAN
    Date of Birth: 12/11/1993
    Place of Birth: MUMBAI
    Date of Expiry: 15/08/2032
    """
    res = DocumentClassifier.classify(sample_text)
    assert res["classified_type"] == "passport"
    assert res["confidence"] > 0.8


def test_classifier_voter_id():
    sample_text = """
    ELECTION COMMISSION OF INDIA
    ELECTOR PHOTO IDENTITY CARD
    EPIC No: WXY1234567
    Elector's Name: VIKRAM MALHOTRA
    Father's Name: SURESH MALHOTRA
    Gender: MALE
    Assembly Constituency: 45 - BALLIMARAN
    """
    res = DocumentClassifier.classify(sample_text)
    assert res["classified_type"] == "voter_id"
    assert res["confidence"] > 0.8


def test_classifier_driving_licence():
    sample_text = """
    UNION OF INDIA
    DRIVING LICENCE
    STATE TRANSPORT DEPARTMENT
    DL No: DL-1420110012345
    Authorised to Drive: LMV, MCWG
    Name: ROHIT KULKARNI
    DOB: 05/03/1986
    Valid Till: 10/05/2030
    """
    res = DocumentClassifier.classify(sample_text)
    assert res["classified_type"] == "driving_licence"
    assert res["confidence"] > 0.8


# =============================================================================
# 2. Field Extraction Tests
# =============================================================================
def test_field_extractor_pan():
    sample_text = """
    INCOME TAX DEPARTMENT
    GOVT. OF INDIA
    PRIYA SHARMA
    RAMESH SHARMA
    14/05/1990
    Permanent Account Number: ABCDE1234F
    """
    fields = FieldExtractor.extract_fields(sample_text, document_type="pan")
    assert fields["id_number"] == "ABCDE1234F"
    assert fields["dob"] == "1990-05-14"
    assert "PRIYA SHARMA" in fields["name"]


def test_field_extractor_aadhaar_masks_digits():
    sample_text = """
    Government of India
    Unique Identification Authority of India
    Siddharth Nair
    DOB: 20/08/1988
    MALE
    3456 7890 1234
    """
    fields = FieldExtractor.extract_fields(sample_text, document_type="aadhaar")
    assert fields["id_number"] == "XXXX-XXXX-1234"
    assert fields["masked_id"] == "XXXX-XXXX-1234"
    assert "345678901234" not in fields["id_number"]
    assert fields["gender"] == "MALE"
    assert fields["dob"] == "1988-08-20"


# =============================================================================
# 3. Validation Rule Tests
# =============================================================================
def test_validator_pan_success():
    fields = {
        "name": "Priya Sharma",
        "dob": "1990-05-14",
        "id_number": "ABCDE1234F"
    }
    val = DocumentValidator.validate("pan", fields)
    assert val["is_valid"] is True
    assert val["overall_status"] == "valid"


def test_validator_expired_document_flagged():
    fields = {
        "name": "Ananya Deshmukh",
        "dob": "1993-11-12",
        "id_number": "Z1234567",
        "expiry_date": "2020-01-01"  # Expired in past
    }
    val = DocumentValidator.validate("passport", fields)
    assert val["is_valid"] is False
    assert val["overall_status"] == "invalid"
    assert any("expired" in flag.lower() for flag in val["flags"])


# =============================================================================
# 4. Cross-Document Comparison Tests (RapidFuzz)
# =============================================================================
def test_cross_document_matching():
    doc1 = {
        "id": "doc-1",
        "original_filename": "pan.pdf",
        "classified_type": "pan",
        "extracted_fields": {
            "name": "Priya Sharma",
            "dob": "1990-05-14",
            "gender": "FEMALE"
        }
    }
    doc2 = {
        "id": "doc-2",
        "original_filename": "aadhaar.pdf",
        "classified_type": "aadhaar",
        "extracted_fields": {
            "name": "Sharma Priya",  # Reordered name
            "dob": "1990-05-14",
            "gender": "FEMALE"
        }
    }
    comparison = CrossDocumentComparator.compare_applicant_documents([doc1, doc2], applicant_name="Priya Sharma")
    assert comparison["overall_verdict"] == "VERIFIED"
    assert comparison["consistency_score"] >= 90.0


def test_cross_document_mismatched_dob_flagged():
    doc1 = {
        "id": "doc-1",
        "original_filename": "pan.pdf",
        "classified_type": "pan",
        "extracted_fields": {
            "name": "Priya Sharma",
            "dob": "1990-05-14"
        }
    }
    doc2 = {
        "id": "doc-2",
        "original_filename": "passport.pdf",
        "classified_type": "passport",
        "extracted_fields": {
            "name": "Priya Sharma",
            "dob": "1995-10-22"  # Direct mismatch
        }
    }
    comparison = CrossDocumentComparator.compare_applicant_documents([doc1, doc2])
    assert comparison["overall_verdict"] == "DISCREPANCY_FLAGGED"
    assert any("mismatch" in d.lower() for d in comparison["discrepancies"])


# =============================================================================
# 5. Full Pipeline & Review API Tests
# =============================================================================
def test_api_process_and_human_review(client, app):
    # 1. Create Synthetic PDF
    pdf_doc = pymupdf.open()
    page = pdf_doc.new_page()
    page.insert_text(
        (50, 70),
        "INCOME TAX DEPARTMENT\nGOVT. OF INDIA\nPERMANENT ACCOUNT NUMBER: ABCDE1234F\nPRIYA SHARMA\nDOB: 14/05/1990\nFATHER'S NAME: RAMESH SHARMA",
        fontsize=12
    )
    pdf_bytes = pdf_doc.tobytes()
    pdf_doc.close()

    # 2. Upload Document
    upload_res = client.post(
        "/api/documents/upload",
        data={
            "files": (io.BytesIO(pdf_bytes), "sample_pan.pdf"),
            "applicant_id": "APPL-TEST-REV"
        },
        content_type="multipart/form-data"
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.get_json()["uploaded"][0]["id"]

    # 3. Process Pipeline POST /api/documents/<id>/process
    proc_res = client.post(f"/api/documents/{doc_id}/process")
    assert proc_res.status_code == 200
    pdata = proc_res.get_json()["data"]["result"]
    assert pdata["classification"]["classified_type"] == "pan"
    assert pdata["extracted_fields"]["id_number"] == "ABCDE1234F"
    assert pdata["validation"]["is_valid"] is True

    # 4. Human Review Submission POST /api/documents/<id>/review
    rev_res = client.post(
        f"/api/documents/{doc_id}/review",
        json={
            "decision": "approved",
            "notes": "Verified against physical card copy",
            "officer_name": "Arjun Mehta",
            "edited_fields": {
                "name": "Priya Ramesh Sharma"
            }
        }
    )
    assert rev_res.status_code == 200
    rev_data = rev_res.get_json()["data"]["review"]
    assert rev_data["review_status"] == "approved"
    assert rev_data["extracted_fields"]["name"] == "Priya Ramesh Sharma"

    # 5. Verify DB record updated
    doc_record = get_document(doc_id, db_path=app.config["DATABASE_PATH"])
    assert doc_record["review_status"] == "approved"
    assert doc_record["reviewed_by"] == "Arjun Mehta"


def test_api_dashboard_stats(client):
    res = client.get("/api/dashboard/stats")
    assert res.status_code == 200
    stats = res.get_json()["data"]
    assert "total_documents" in stats
    assert "processed_count" in stats
    assert "pending_review_count" in stats
