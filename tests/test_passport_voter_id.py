import pytest
from datetime import datetime, date, timedelta
from io import BytesIO
from backend.services.classifier import DocumentClassifier
from backend.services.field_extractor import FieldExtractor
from backend.services.validator import DocumentValidator
from backend.services.comparator import CrossDocumentComparator
from backend.app import create_app
from backend.database.db import get_db_connection, init_db


@pytest.fixture
def client(tmp_path):
    test_db = tmp_path / "test_passport_voter.db"
    test_upload = tmp_path / "uploads"
    test_processed = tmp_path / "processed"
    test_upload.mkdir(parents=True, exist_ok=True)
    test_processed.mkdir(parents=True, exist_ok=True)

    app = create_app("testing")
    app.config["DATABASE_PATH"] = str(test_db)
    app.config["UPLOAD_FOLDER"] = test_upload
    app.config["PROCESSED_FOLDER"] = test_processed
    app.config["TESTING"] = True
    init_db(str(test_db))
    with app.test_client() as client:
        yield client


# ==============================================================================
# 1. Document Classification Tests
# ==============================================================================

def test_passport_classification():
    """Verify Passport classification across standard, MRZ, and minimal layouts."""
    # Standard Indian passport text
    text1 = """
    PASSPORT - REPUBLIC OF INDIA
    Type: P | Country Code: IND
    Passport No: Z9876543
    Surname: DESHMUKH
    Given Name: ANANYA
    Nationality: INDIAN
    Sex: F
    Date of Birth: 04/09/1995
    Place of Birth: MUMBAI
    Date of Issue: 16/08/2021
    Date of Expiry: 15/08/2031
    """
    cls1 = DocumentClassifier.classify(text1)
    assert cls1["classified_type"] == "passport"
    assert cls1["confidence"] >= 0.85

    # MRZ format passport text
    text_mrz = """
    GOVERNMENT OF INDIA
    MINISTRY OF EXTERNAL AFFAIRS
    PASSPORT
    P<INDSHARMA<<PRIYA<<<<<<<<<<<<<<<<<<<<<<<<<<
    K7654321<5IND9408226F3110158<<<<<<<<<<<<<<0
    """
    cls2 = DocumentClassifier.classify(text_mrz)
    assert cls2["classified_type"] == "passport"


def test_voter_id_classification():
    """Verify Voter ID (EPIC) classification across Election Commission formats."""
    text1 = """
    ELECTION COMMISSION OF INDIA
    ELECTOR PHOTO IDENTITY CARD
    EPIC No: WXY1234567
    Elector Name: NEHA KAPOOR
    Father's Name: SUNIL KAPOOR
    Sex: FEMALE
    Date of Birth: 14/11/1993
    Assembly Constituency: 43 - NOIDA
    """
    cls1 = DocumentClassifier.classify(text1)
    assert cls1["classified_type"] == "voter_id"
    assert cls1["confidence"] >= 0.85

    # Hindi / Regional heading variant
    text2 = """
    BHARAT NIRVACHAN AAYOG
    ELECTION COMMISSION OF INDIA
    PHOTO IDENTITY CARD
    EPIC: ABC1234567
    """
    cls2 = DocumentClassifier.classify(text2)
    assert cls2["classified_type"] == "voter_id"


# ==============================================================================
# 2. Field Extraction & Normalization Tests
# ==============================================================================

def test_passport_field_extraction_and_normalization():
    """Verify Passport field extraction, Given/Surname combination, and normalization."""
    text = """
    PASSPORT
    REPUBLIC OF INDIA
    Passport No: K 7654321
    Given Name:  Shri PRIYA
    Surname:     SHARMA
    Nationality: INDIAN
    Sex:         F
    Date of Birth: 22/08/1994
    Place of Birth: BENGALURU
    Date of Issue: 16/10/2021
    Date of Expiry: 15/10/2031
    """
    fields = FieldExtractor.extract_fields(text, "passport")
    assert fields["id_number"] == "K7654321"  # Normalized without space
    assert fields["masked_id"] == "*****321"
    assert fields["name"] == "PRIYA SHARMA"  # Stripped 'Shri' salutation
    assert fields["gender"] == "FEMALE"  # Normalized 'F' -> 'FEMALE'
    assert fields["dob"] == "1994-08-22"
    assert fields["expiry_date"] == "2031-10-15"
    assert fields["extra_fields"]["nationality"] == "INDIAN"
    assert fields["extra_fields"]["date_of_issue"] == "2021-10-16"


def test_voter_id_field_extraction_and_normalization():
    """Verify Voter ID field extraction, relative relation, and normalization."""
    text = """
    ELECTION COMMISSION OF INDIA
    ELECTOR PHOTO IDENTITY CARD
    EPIC No:  XYZ-9876543
    Elector's Name: Smt. Ananya Subramanian
    Husband's Name: K. Subramanian
    DOB: 05/12/1996
    Sex: Female
    Assembly Constituency: 12 - T. Nagar
    """
    fields = FieldExtractor.extract_fields(text, "voter_id")
    assert fields["id_number"] == "XYZ9876543"  # Normalized without hyphen
    assert fields["name"] == "Ananya Subramanian"  # Stripped 'Smt.'
    assert fields["father_name"] == "K. Subramanian"
    assert fields["gender"] == "FEMALE"
    assert fields["dob"] == "1996-12-05"
    assert fields["extra_fields"]["assembly_constituency"] == "12 - T. Nagar"
    assert fields["extra_fields"]["validity"] == "PERMANENT"


def test_voter_id_age_fallback_estimation():
    """Verify Voter ID birth year estimation when only Age is specified on card."""
    text = """
    ELECTION COMMISSION OF INDIA
    ELECTOR PHOTO IDENTITY CARD
    EPIC: DEF1234567
    Name: Vikram Rao
    Age: 30
    Sex: Male
    """
    fields = FieldExtractor.extract_fields(text, "voter_id")
    assert fields["id_number"] == "DEF1234567"
    assert fields["name"] == "Vikram Rao"
    assert fields["gender"] == "MALE"
    assert fields["extra_fields"]["age"] == 30
    assert fields["extra_fields"]["dob_estimated"] is True
    assert fields["dob"].startswith(str(datetime.now().year - 30))


# ==============================================================================
# 3. Format, Mandatory Field & Expiry Validation Tests
# ==============================================================================

def test_passport_validations_success_and_failures():
    """Verify Passport format checks, mandatory fields, and expiry windows."""
    # 1. Valid in-force Passport
    valid_fields = {
        "id_number": "J4567890",
        "name": "Neha Kapoor",
        "dob": "1993-11-14",
        "expiry_date": (date.today() + timedelta(days=365 * 5)).strftime("%Y-%m-%d"),
        "extra_fields": {
            "date_of_issue": "2023-01-01"
        }
    }
    v1 = DocumentValidator.validate("passport", valid_fields)
    assert v1["is_valid"] is True
    assert v1["overall_status"] == "valid"

    # 2. Expired Passport (past date)
    expired_fields = {
        "id_number": "L3456789",
        "name": "Dev Patel",
        "dob": "1990-09-18",
        "expiry_date": "2020-01-10",
        "extra_fields": {}
    }
    v2 = DocumentValidator.validate("passport", expired_fields)
    assert v2["is_valid"] is False
    assert any("expired" in f.lower() for f in v2["flags"])

    # 3. Invalid Passport format (e.g., numbers only, lowercase, too short)
    invalid_format_fields = {
        "id_number": "12345678",  # Missing series letter
        "name": "Arjun Kumar",
        "dob": "1992-05-14",
        "expiry_date": "2030-01-01",
        "extra_fields": {}
    }
    v3 = DocumentValidator.validate("passport", invalid_format_fields)
    assert v3["is_valid"] is False
    assert any("Invalid Passport format" in f for f in v3["flags"])

    # 4. Missing mandatory name
    missing_name_fields = {
        "id_number": "K1122334",
        "name": None,
        "dob": "1995-05-10",
        "expiry_date": "2030-01-01",
        "extra_fields": {}
    }
    v4 = DocumentValidator.validate("passport", missing_name_fields)
    assert v4["is_valid"] is False
    assert "Missing applicant name" in v4["flags"]


def test_voter_id_validations_success_and_failures():
    """Verify Voter ID format, lifetime validity rule, and missing mandatory fields."""
    # 1. Valid Voter ID
    valid_fields = {
        "id_number": "WXY1234567",
        "name": "Neha Kapoor",
        "dob": "1993-11-14",
        "father_name": "Sunil Kapoor",
        "extra_fields": {}
    }
    v1 = DocumentValidator.validate("voter_id", valid_fields)
    assert v1["is_valid"] is True
    # Verify lifetime validity check passed
    exp_checks = [c for c in v1["checks"] if c["field"] == "expiry_date"]
    assert len(exp_checks) == 1
    assert exp_checks[0]["status"] == "pass"
    assert "lifetime validity" in exp_checks[0]["message"]

    # 2. Invalid EPIC format (e.g., wrong length)
    bad_epic_fields = {
        "id_number": "INVALID99",
        "name": "Rohan Verma",
        "dob": "1988-10-10",
        "extra_fields": {}
    }
    v2 = DocumentValidator.validate("voter_id", bad_epic_fields)
    assert any("Non-standard Voter ID pattern" in c["message"] for c in v2["checks"])

    # 3. Missing mandatory fields (no EPIC number, no name)
    missing_fields = {
        "id_number": None,
        "name": None,
        "dob": None,
        "extra_fields": {}
    }
    v3 = DocumentValidator.validate("voter_id", missing_fields)
    assert v3["is_valid"] is False
    assert "Missing applicant name" in v3["flags"]
    assert "Voter ID (EPIC) number missing from document" in v3["flags"]


# ==============================================================================
# 4. Cross-Document Consistency Tests with Passport & Voter ID
# ==============================================================================

def test_cross_document_matching_with_passport_and_pan():
    """Verify 100% correlation between Passport and PAN."""
    pan_doc = {
        "id": "doc_pan",
        "type": "pan",
        "extracted_fields": {
            "name": "Priya Sharma",
            "dob": "1994-08-22",
            "id_number": "ABCPS5678E"
        }
    }
    passport_doc = {
        "id": "doc_pass",
        "type": "passport",
        "extracted_fields": {
            "name": "PRIYA SHARMA",
            "dob": "1994-08-22",
            "id_number": "K7654321",
            "expiry_date": "2031-10-15"
        }
    }
    res = CrossDocumentComparator.compare_applicant_documents([pan_doc, passport_doc], "Priya Sharma")
    assert res["overall_verdict"] == "VERIFIED"
    assert res["consistency_score"] == 100.0
    assert len(res["discrepancies"]) == 0


def test_cross_document_name_mismatch_voter_id_flagged():
    """Verify name mismatch between Aadhaar and Voter ID (Ananya Iyer vs Ananya Subramanian)."""
    aadhaar_doc = {
        "id": "doc_aadhaar",
        "type": "aadhaar",
        "extracted_fields": {
            "name": "Ananya Iyer",
            "dob": "1996-12-05",
            "id_number": "XXXX-XXXX-0987"
        }
    }
    voter_doc = {
        "id": "doc_voter",
        "type": "voter_id",
        "extracted_fields": {
            "name": "Ananya Subramanian",
            "dob": "1996-12-05",
            "id_number": "XYZ9876543"
        }
    }
    res = CrossDocumentComparator.compare_applicant_documents([aadhaar_doc, voter_doc], "Ananya Iyer")
    assert res["overall_verdict"] == "DISCREPANCY_FLAGGED"
    assert any("name mismatch" in d.lower() for d in res["discrepancies"])


def test_cross_document_dob_mismatch_passport_flagged():
    """Verify critical DOB mismatch between PAN and Passport (1983 vs 1989)."""
    pan_doc = {
        "id": "doc_pan",
        "type": "pan",
        "extracted_fields": {
            "name": "Kabir Malhotra",
            "dob": "1983-04-14",
            "id_number": "ABCPM8899G"
        }
    }
    passport_doc = {
        "id": "doc_pass",
        "type": "passport",
        "extracted_fields": {
            "name": "Kabir Malhotra",
            "dob": "1989-11-28",  # 6-year mismatch!
            "id_number": "M2345678"
        }
    }
    res = CrossDocumentComparator.compare_applicant_documents([pan_doc, passport_doc], "Kabir Malhotra")
    assert res["overall_verdict"] == "DISCREPANCY_FLAGGED"
    assert any("DOB mismatch" in d for d in res["discrepancies"])


# ==============================================================================
# 5. End-to-End API Upload & Processing Integration Test
# ==============================================================================

def test_api_upload_and_pipeline_passport(client):
    """Upload a real generated synthetic Passport fixture, extract text, and verify queue integration."""
    from backend.tests.fixtures.synthetic_kyc.seed_synthetic_kyc import FIXTURES_DIR

    passport_path = FIXTURES_DIR / "10_neha_kapoor" / "neha_kapoor_passport.pdf"
    assert passport_path.exists()

    with open(passport_path, "rb") as f:
        data = {
            "applicant_name": "Neha Kapoor",
            "files": (f, "neha_kapoor_passport.pdf")
        }
        upload_res = client.post("/api/documents/upload", data=data, content_type="multipart/form-data")
    
    assert upload_res.status_code == 201
    doc_id = upload_res.get_json()["data"]["uploaded"][0]["id"]

    # Process document through the intelligence pipeline
    proc_res = client.post(f"/api/documents/{doc_id}/process")
    assert proc_res.status_code == 200
    p_data = proc_res.get_json()["data"]["result"]

    assert p_data["classification"]["classified_type"] == "passport"
    assert p_data["extracted_fields"]["id_number"] == "J4567890"
    assert p_data["extracted_fields"]["name"] == "NEHA KAPOOR"
    assert p_data["extracted_fields"]["dob"] == "1993-11-14"
    assert p_data["extracted_fields"]["expiry_date"] == "2033-08-30"
    assert p_data["validation"]["is_valid"] is True

    # Confirm present in verification queue
    queue_res = client.get("/api/documents/queue?status=all")
    assert queue_res.status_code == 200
    q_docs = queue_res.get_json()["data"]["queue"]
    found = [d for d in q_docs if d["id"] == doc_id]
    assert len(found) == 1
    assert found[0]["classified_type"] == "passport"
