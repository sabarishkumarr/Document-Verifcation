import os
import sys
import json
import sqlite3

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.services.comparator import CrossDocumentComparator
from backend.database.db import get_documents_by_applicant, get_applicant, get_db_connection

compare_applicant_documents = CrossDocumentComparator.compare_applicant_documents

def test_applicant_isolation():
    print("==================================================")
    print("PHASE 5: APPLICANT DATA ISOLATION VERIFICATION TEST")
    print("==================================================")
    
    # 1. Create or verify test applicants in the database:
    # Applicant A: Aarav Mehta (PAN & Aadhaar, matching DOB 1991-06-15)
    # Applicant B: Priya Sharma (PAN & Passport, matching DOB 1994-08-22)
    # Applicant C: Rohan Nair (Aadhaar & DL, intentional DOB mismatch)
    # Unassigned document: applicant_id = None
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Clean up any previous test run records
    cursor.execute("DELETE FROM documents WHERE applicant_id IN ('TEST-APPL-A', 'TEST-APPL-B', 'TEST-APPL-C')")
    cursor.execute("DELETE FROM documents WHERE id = 'TEST-DOC-UNASSIGNED'")
    cursor.execute("DELETE FROM applicants WHERE id IN ('TEST-APPL-A', 'TEST-APPL-B', 'TEST-APPL-C')")
    
    # Insert Applicant A, B, C
    cursor.execute("""
        INSERT INTO applicants (id, name, status, consistency_score, risk_level)
        VALUES ('TEST-APPL-A', 'Aarav Mehta', 'active', 100.0, 'low')
    """)
    cursor.execute("""
        INSERT INTO applicants (id, name, status, consistency_score, risk_level)
        VALUES ('TEST-APPL-B', 'Priya Sharma', 'active', 100.0, 'low')
    """)
    cursor.execute("""
        INSERT INTO applicants (id, name, status, consistency_score, risk_level)
        VALUES ('TEST-APPL-C', 'Rohan Nair', 'active', 60.0, 'medium')
    """)
    
    # Documents for Applicant A (Aarav Mehta: PAN & Aadhaar, matching DOB)
    doc_a_pan = {
        "id": "TEST-A-PAN",
        "applicant_id": "TEST-APPL-A",
        "document_type": "pan",
        "filename": "aarav_pan.png",
        "file_path": "uploads/aarav_pan.png",
        "review_status": "approved",
        "extracted_fields": json.dumps({
            "name": "Aarav Mehta",
            "dob": "1991-06-15",
            "pan": "ABCDE1234F",
            "gender": None
        })
    }
    doc_a_aadhaar = {
        "id": "TEST-A-AADHAAR",
        "applicant_id": "TEST-APPL-A",
        "document_type": "aadhaar",
        "filename": "aarav_aadhaar.png",
        "file_path": "uploads/aarav_aadhaar.png",
        "review_status": "approved",
        "extracted_fields": json.dumps({
            "name": "Aarav Mehta",
            "dob": "1991-06-15",
            "aadhaar": "123456789012",
            "gender": "MALE",
            "address": "123 MG Road, Bengaluru"
        })
    }
    
    # Documents for Applicant B (Priya Sharma: PAN & Passport, matching DOB)
    doc_b_pan = {
        "id": "TEST-B-PAN",
        "applicant_id": "TEST-APPL-B",
        "document_type": "pan",
        "filename": "priya_pan.png",
        "file_path": "uploads/priya_pan.png",
        "review_status": "approved",
        "extracted_fields": json.dumps({
            "name": "Priya Sharma",
            "dob": "1994-08-22",
            "pan": "XYZPK9876Q",
            "gender": None
        })
    }
    doc_b_passport = {
        "id": "TEST-B-PASSPORT",
        "applicant_id": "TEST-APPL-B",
        "document_type": "passport",
        "filename": "priya_passport.png",
        "file_path": "uploads/priya_passport.png",
        "review_status": "approved",
        "extracted_fields": json.dumps({
            "name": "Priya Sharma",
            "dob": "1994-08-22",
            "passport_number": "M1234567",
            "gender": "FEMALE",
            "address": "456 Park Street, Kolkata"
        })
    }
    
    # Documents for Applicant C (Rohan Nair: Aadhaar & Driving Licence, intentional DOB mismatch)
    doc_c_aadhaar = {
        "id": "TEST-C-AADHAAR",
        "applicant_id": "TEST-APPL-C",
        "document_type": "aadhaar",
        "filename": "rohan_aadhaar.png",
        "file_path": "uploads/rohan_aadhaar.png",
        "review_status": "manual_review",
        "extracted_fields": json.dumps({
            "name": "Rohan Nair",
            "dob": "1988-12-04",
            "aadhaar": "998877665544",
            "gender": "MALE",
            "address": "789 Marine Drive, Mumbai"
        })
    }
    doc_c_dl = {
        "id": "TEST-C-DL",
        "applicant_id": "TEST-APPL-C",
        "document_type": "driving_licence",
        "filename": "rohan_dl.png",
        "file_path": "uploads/rohan_dl.png",
        "review_status": "manual_review",
        "extracted_fields": json.dumps({
            "name": "Rohan Nair",
            "dob": "1982-01-01",  # Intentional DOB mismatch!
            "dl_number": "MH-01-2015-0012345",
            "gender": "MALE",
            "expiry_date": "2030-01-01"
        })
    }
    
    # Unassigned document
    doc_unassigned = {
        "id": "TEST-DOC-UNASSIGNED",
        "applicant_id": None,
        "document_type": "pan",
        "filename": "unknown_pan.png",
        "file_path": "uploads/unknown_pan.png",
        "review_status": "requires_association",
        "extracted_fields": json.dumps({
            "name": "Stranger Danger",
            "dob": "2000-01-01",
            "pan": "ZZZZZ9999Z"
        })
    }
    
    for d in [doc_a_pan, doc_a_aadhaar, doc_b_pan, doc_b_passport, doc_c_aadhaar, doc_c_dl, doc_unassigned]:
        cursor.execute("""
            INSERT INTO documents (id, applicant_id, document_type, original_filename, stored_filename, review_status, extracted_fields)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (d["id"], d["applicant_id"], d["document_type"], d["filename"], d["file_path"], d["review_status"], d["extracted_fields"]))
    
    conn.commit()
    conn.close()
    
    # -----------------------------------------------------------------
    # Verification Point 1: Applicant A is compared ONLY with Applicant A
    # -----------------------------------------------------------------
    docs_a = get_documents_by_applicant("TEST-APPL-A")
    assert len(docs_a) == 2, f"Applicant A should have exactly 2 documents, got {len(docs_a)}"
    res_a = compare_applicant_documents(docs_a, applicant_name="Aarav Mehta")
    
    print("\n--- TEST 1: Applicant A (Aarav Mehta) ---")
    print(f"Overall verdict: {res_a['overall_verdict']}")
    print(f"Consistency score: {res_a['consistency_score']}")
    print(f"Discrepancies count: {len(res_a['discrepancies'])}")
    print(f"Discrepancies: {res_a['discrepancies']}")
    
    assert res_a["overall_verdict"] == "VERIFIED", f"Expected VERIFIED, got {res_a['overall_verdict']}"
    assert res_a["consistency_score"] == 100.0, f"Expected 100.0, got {res_a['consistency_score']}"
    assert len(res_a["discrepancies"]) == 0, f"Expected 0 discrepancies for Applicant A, got {res_a['discrepancies']}"
    print("✓ Test 1 PASSED: Applicant A has 100% consistency, 0 discrepancies, compared only with own documents.")
    
    # -----------------------------------------------------------------
    # Verification Point 2: Applicant B is compared ONLY with Applicant B
    # -----------------------------------------------------------------
    docs_b = get_documents_by_applicant("TEST-APPL-B")
    assert len(docs_b) == 2, f"Applicant B should have exactly 2 documents, got {len(docs_b)}"
    res_b = compare_applicant_documents(docs_b, applicant_name="Priya Sharma")
    
    print("\n--- TEST 2: Applicant B (Priya Sharma) ---")
    print(f"Overall verdict: {res_b['overall_verdict']}")
    print(f"Consistency score: {res_b['consistency_score']}")
    print(f"Discrepancies count: {len(res_b['discrepancies'])}")
    print(f"Discrepancies: {res_b['discrepancies']}")
    
    assert res_b["overall_verdict"] == "VERIFIED", f"Expected VERIFIED, got {res_b['overall_verdict']}"
    assert res_b["consistency_score"] == 100.0, f"Expected 100.0, got {res_b['consistency_score']}"
    assert len(res_b["discrepancies"]) == 0, f"Expected 0 discrepancies for Applicant B, got {res_b['discrepancies']}"
    print("✓ Test 2 PASSED: Applicant B has 100% consistency, 0 discrepancies, compared only with own documents.")
    
    # -----------------------------------------------------------------
    # Verification Point 3: Applicant C shows ONLY intentional DOB mismatch
    # -----------------------------------------------------------------
    docs_c = get_documents_by_applicant("TEST-APPL-C")
    assert len(docs_c) == 2, f"Applicant C should have exactly 2 documents, got {len(docs_c)}"
    res_c = compare_applicant_documents(docs_c, applicant_name="Rohan Nair")
    
    print("\n--- TEST 3: Applicant C (Rohan Nair - intentional DOB mismatch) ---")
    print(f"Overall verdict: {res_c['overall_verdict']}")
    print(f"Consistency score: {res_c['consistency_score']}")
    print(f"Discrepancies count: {len(res_c['discrepancies'])}")
    for d in res_c["discrepancies"]:
        print(f"  - {d}")
    
    assert res_c["overall_verdict"] in ["DISCREPANCY_FLAGGED", "FLAG_FOR_REVIEW", "REQUIRES_ATTENTION"], f"Expected discrepancy/review flag, got {res_c['overall_verdict']}"
    assert any("dob" in d.lower() for d in res_c["discrepancies"]), "Expected DOB mismatch in discrepancies"
    # Ensure NO name mismatch, NO gender mismatch, NO ID number cross-comparison mismatch
    assert not any("name" in d.lower() for d in res_c["discrepancies"]), f"Did not expect name mismatch for Rohan: {res_c['discrepancies']}"
    assert not any("gender" in d.lower() for d in res_c["discrepancies"]), f"Did not expect gender mismatch: {res_c['discrepancies']}"
    assert not any("id number" in d.lower() for d in res_c["discrepancies"]), f"Did not expect cross-ID comparison: {res_c['discrepancies']}"
    print("✓ Test 3 PASSED: Applicant C shows ONLY the intentional DOB mismatch.")
    
    # -----------------------------------------------------------------
    # Verification Point 4: No cross-applicant mismatch between A, B, C
    # -----------------------------------------------------------------
    # Ensure query for Applicant A returns NO document belonging to B or C or unassigned
    doc_ids_a = {d["id"] for d in docs_a}
    assert "TEST-B-PAN" not in doc_ids_a and "TEST-C-DL" not in doc_ids_a and "TEST-DOC-UNASSIGNED" not in doc_ids_a
    print("\n✓ Test 4 PASSED: Strict SQL data isolation verified: docs_a contains only Applicant A documents.")
    
    # -----------------------------------------------------------------
    # Verification Point 5: Unassigned documents are never compared
    # -----------------------------------------------------------------
    docs_unassigned = get_documents_by_applicant(None)
    assert docs_unassigned == [], f"get_documents_by_applicant(None) must return [], got {docs_unassigned}"
    
    docs_empty = get_documents_by_applicant("")
    assert docs_empty == [], f"get_documents_by_applicant('') must return [], got {docs_empty}"
    
    # Single doc comparison check
    res_single = compare_applicant_documents([doc_unassigned])
    assert res_single["overall_verdict"] == "SINGLE_DOCUMENT_RECORDED"
    assert len(res_single["discrepancies"]) == 0
    print("✓ Test 5 PASSED: Unassigned/single documents are never compared and produce 0 discrepancies.")
    
    # -----------------------------------------------------------------
    # Clean up test rows
    # -----------------------------------------------------------------
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM documents WHERE applicant_id IN ('TEST-APPL-A', 'TEST-APPL-B', 'TEST-APPL-C')")
    cursor.execute("DELETE FROM documents WHERE id = 'TEST-DOC-UNASSIGNED'")
    cursor.execute("DELETE FROM applicants WHERE id IN ('TEST-APPL-A', 'TEST-APPL-B', 'TEST-APPL-C')")
    conn.commit()
    conn.close()
    
    print("\n==================================================")
    print("ALL PHASE 5 APPLICANT DATA ISOLATION TESTS PASSED!")
    print("==================================================")

if __name__ == "__main__":
    test_applicant_isolation()
