import os
import sys
import json
import sqlite3

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.database.db import (
    get_db_connection,
    get_applicant,
    get_documents_by_applicant,
    insert_applicant,
    insert_document,
    update_document_processing_results,
    consolidate_applicant_name,
    is_placeholder_name
)
from backend.services.comparator import CrossDocumentComparator

def run_all_verification_scenarios():
    print("=" * 70)
    print("VERIDOC AI: VERIFICATION OF NAME DETECTION, ISOLATION & COMPARISON")
    print("=" * 70)

    conn = get_db_connection()
    cursor = conn.cursor()

    # Clean up test artifacts
    cursor.execute("DELETE FROM documents WHERE applicant_id LIKE 'TEST-NAMEDET-%'")
    cursor.execute("DELETE FROM applicants WHERE id LIKE 'TEST-NAMEDET-%'")
    conn.commit()
    conn.close()

    # -------------------------------------------------------------
    # SCENARIO 1: Upload document without applicant name -> provisional applicant
    # -------------------------------------------------------------
    print("\n--- SCENARIO 1: Upload documents without applicant name ---")
    app_id_1 = "TEST-NAMEDET-001"
    # Create provisional applicant with name = None or placeholder like 'New Applicant'
    insert_applicant(app_id_1, name="New Applicant")
    
    app_before = get_applicant(app_id_1)
    assert app_before["name"] is None, f"Expected provisional applicant name to be None, got {app_before['name']}"
    print(f"  ✓ Provisional applicant created with ID {app_id_1}, name is correctly None (placeholder suppressed)")

    # Insert document with extracted name "Ritika Kapoor"
    insert_document({
        "id": "DOC-NAMEDET-1A",
        "applicant_id": app_id_1,
        "document_type": "aadhaar",
        "original_filename": "ritika_aadhaar.png",
        "stored_filename": "ritika_aadhaar.png",
        "file_size": 1024,
        "file_hash": "hash1a",
        "mime_type": "image/png",
        "processing_status": "completed",
        "review_status": "pending"
    })
    update_document_processing_results(
        document_id="DOC-NAMEDET-1A",
        classified_type="aadhaar",
        classification_confidence=0.98,
        extracted_fields={
            "name": "Ritika Kapoor",
            "dob": "1993-04-12",
            "id_number": "998877665544",
            "gender": "Female",
            "address": "402 Palm Heights, Mumbai, Maharashtra"
        },
        validation_results={"overall_status": "valid", "field_validations": {}}
    )

    # Consolidate name
    consolidated_name = consolidate_applicant_name(app_id_1)
    assert consolidated_name == "Ritika Kapoor", f"Expected Ritika Kapoor, got {consolidated_name}"
    
    app_after = get_applicant(app_id_1)
    assert app_after["name"] == "Ritika Kapoor", f"Expected Ritika Kapoor in DB, got {app_after['name']}"
    print(f"  ✓ Name automatically extracted and consolidated to: '{app_after['name']}'")

    # Run comparison matrix
    res1 = CrossDocumentComparator.compare_applicant_documents(app_id_1)
    matrix1 = res1["matrix"]
    assert len(matrix1["columns"]) == 1
    # Check that name row is MATCH (single doc) and has NO discrepancy against placeholder
    name_row1 = next(r for r in matrix1["rows"] if r["attribute_key"] == "name")
    assert name_row1["result_status"] == "MATCH"
    assert len(res1["discrepancies"]) == 0, f"Expected 0 discrepancies, got {res1['discrepancies']}"
    print("  ✓ Comparison matrix generated with 0 false mismatches against declared placeholder!")

    # -------------------------------------------------------------
    # SCENARIO 2: Upload two consistent documents for same applicant
    # -------------------------------------------------------------
    print("\n--- SCENARIO 2: Two consistent documents for same applicant ---")
    insert_document({
        "id": "DOC-NAMEDET-1B",
        "applicant_id": app_id_1,
        "document_type": "pan",
        "original_filename": "ritika_pan.png",
        "stored_filename": "ritika_pan.png",
        "file_size": 1024,
        "file_hash": "hash1b",
        "mime_type": "image/png",
        "processing_status": "completed",
        "review_status": "pending"
    })
    update_document_processing_results(
        document_id="DOC-NAMEDET-1B",
        classified_type="pan",
        classification_confidence=0.99,
        extracted_fields={
            "name": "Ritika Kapoor",
            "dob": "1993-04-12",
            "id_number": "ABCDE1234F"
        },
        validation_results={"overall_status": "valid", "field_validations": {}}
    )

    res2 = CrossDocumentComparator.compare_applicant_documents(app_id_1)
    matrix2 = res2["matrix"]
    assert len(matrix2["columns"]) == 2
    name_row2 = next(r for r in matrix2["rows"] if r["attribute_key"] == "name")
    dob_row2 = next(r for r in matrix2["rows"] if r["attribute_key"] == "dob")
    assert name_row2["result_status"] == "MATCH", f"Expected MATCH, got {name_row2['result_status']}"
    assert dob_row2["result_status"] == "MATCH", f"Expected MATCH, got {dob_row2['result_status']}"
    assert len(res2["discrepancies"]) == 0, f"Expected 0 discrepancies, got {res2['discrepancies']}"
    assert res2["consistency_score"] == 100, f"Expected 100, got {res2['consistency_score']}"
    print(f"  ✓ Consistent Aadhaar and PAN comparison yielded 100% score, 0 discrepancies, Name: MATCH, DOB: MATCH.")

    # -------------------------------------------------------------
    # SCENARIO 3: Two documents with genuinely different names
    # -------------------------------------------------------------
    print("\n--- SCENARIO 3: Two documents with genuinely conflicting names ---")
    app_id_3 = "TEST-NAMEDET-003"
    insert_applicant(app_id_3, name=None)
    insert_document({
        "id": "DOC-NAMEDET-3A",
        "applicant_id": app_id_3,
        "document_type": "aadhaar",
        "original_filename": "doc3a.png",
        "stored_filename": "doc3a.png",
        "file_size": 1024,
        "file_hash": "hash3a",
        "mime_type": "image/png",
        "processing_status": "completed",
        "review_status": "pending"
    })
    update_document_processing_results(
        document_id="DOC-NAMEDET-3A",
        classified_type="aadhaar",
        classification_confidence=0.95,
        extracted_fields={"name": "Aarav Mehta", "dob": "1990-01-01"},
        validation_results={"overall_status": "valid", "field_validations": {}}
    )
    insert_document({
        "id": "DOC-NAMEDET-3B",
        "applicant_id": app_id_3,
        "document_type": "pan",
        "original_filename": "doc3b.png",
        "stored_filename": "doc3b.png",
        "file_size": 1024,
        "file_hash": "hash3b",
        "mime_type": "image/png",
        "processing_status": "completed",
        "review_status": "pending"
    })
    update_document_processing_results(
        document_id="DOC-NAMEDET-3B",
        classified_type="pan",
        classification_confidence=0.95,
        extracted_fields={"name": "Priya Sharma", "dob": "1990-01-01"},
        validation_results={"overall_status": "valid", "field_validations": {}}
    )

    res3 = CrossDocumentComparator.compare_applicant_documents(app_id_3)
    name_row3 = next(r for r in res3["matrix"]["rows"] if r["attribute_key"] == "name")
    assert name_row3["result_status"] == "MISMATCH", f"Expected MISMATCH, got {name_row3['result_status']}"
    assert any("Name mismatch" in d for d in res3["discrepancies"]), "Expected discrepancy alert for name mismatch"
    print(f"  ✓ Conflicting documents correctly flagged: {name_row3['result_status']} - {name_row3['explanation']}")

    # -------------------------------------------------------------
    # SCENARIO 4: Document where name cannot be read / missing
    # -------------------------------------------------------------
    print("\n--- SCENARIO 4: Document where name cannot be read ---")
    app_id_4 = "TEST-NAMEDET-004"
    insert_applicant(app_id_4, name=None)
    insert_document({
        "id": "DOC-NAMEDET-4A",
        "applicant_id": app_id_4,
        "document_type": "passport",
        "original_filename": "unreadable_passport.png",
        "stored_filename": "unreadable_passport.png",
        "file_size": 1024,
        "file_hash": "hash4a",
        "mime_type": "image/png",
        "processing_status": "completed",
        "review_status": "pending"
    })
    update_document_processing_results(
        document_id="DOC-NAMEDET-4A",
        classified_type="passport",
        classification_confidence=0.90,
        extracted_fields={"name": None, "dob": None, "id_number": "Z1234567"},
        validation_results={"overall_status": "valid", "field_validations": {}}
    )
    consolidate_applicant_name(app_id_4)
    app4 = get_applicant(app_id_4)
    assert app4["name"] is None, f"Expected None for unreadable name, got {app4['name']}"
    
    res4 = CrossDocumentComparator.compare_applicant_documents(app_id_4)
    name_row4 = next(r for r in res4["matrix"]["rows"] if r["attribute_key"] == "name")
    assert name_row4["result_status"] == "NOT DETECTED", f"Expected NOT DETECTED, got {name_row4['result_status']}"
    assert name_row4["values"]["DOC-NAMEDET-4A"] == "Not detected"
    print(f"  ✓ Handled unreadable document cleanly: status is {name_row4['result_status']}, value is 'Not detected', no crash.")

    # -------------------------------------------------------------
    # SCENARIO 5: Missing optional field (e.g. PAN has no address or gender)
    # -------------------------------------------------------------
    print("\n--- SCENARIO 5: Document with missing optional field ---")
    addr_row2 = next(r for r in matrix2["rows"] if r["attribute_key"] == "address")
    gender_row2 = next(r for r in matrix2["rows"] if r["attribute_key"] == "gender")
    assert addr_row2["result_status"] in ("NOT APPLICABLE", "MATCH", "NOT DETECTED"), f"Got {addr_row2['result_status']}"
    assert gender_row2["result_status"] == "NOT APPLICABLE", f"Got {gender_row2['result_status']}"
    assert not any("Address mismatch" in d for d in res2["discrepancies"])
    assert not any("Gender mismatch" in d for d in res2["discrepancies"])
    print("  ✓ Missing optional fields on single documents handled without false mismatches.")

    # -------------------------------------------------------------
    # SCENARIO 6: Cross-applicant isolation
    # -------------------------------------------------------------
    print("\n--- SCENARIO 6: Cross-applicant isolation ---")
    doc_ids_in_matrix1 = [c["id"] for c in matrix2["columns"]]
    assert doc_ids_in_matrix1 == ["DOC-NAMEDET-1A", "DOC-NAMEDET-1B"]
    assert "DOC-NAMEDET-3A" not in doc_ids_in_matrix1
    assert "DOC-NAMEDET-4A" not in doc_ids_in_matrix1
    print(f"  ✓ Isolation verified: Applicant 1's comparison contains solely {doc_ids_in_matrix1}.")

    # -------------------------------------------------------------
    # SCENARIO 7: Consolidated Table Structure & Status Badges
    # -------------------------------------------------------------
    print("\n--- SCENARIO 7: Table rows and status vocabulary ---")
    expected_attributes = ["name", "dob", "gender", "address", "id_number", "expiry_date"]
    matrix_keys = [r["attribute_key"] for r in matrix2["rows"]]
    for ea in expected_attributes:
        assert ea in matrix_keys, f"Expected attribute '{ea}' in matrix rows"
    assert "issue_date" not in matrix_keys, "issue_date should be omitted from cross-comparison matrix"
    
    valid_statuses = {"MATCH", "MISMATCH", "NOT DETECTED", "NOT APPLICABLE", "EXPIRED", "NEEDS REVIEW"}
    for r in matrix2["rows"]:
        assert r["result_status"] in valid_statuses, f"Invalid status: {r['result_status']}"
    print(f"  ✓ Matrix attributes and status vocabulary verified against specification: {valid_statuses}")

    # Clean up test records
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM documents WHERE applicant_id LIKE 'TEST-NAMEDET-%'")
    cursor.execute("DELETE FROM applicants WHERE id LIKE 'TEST-NAMEDET-%'")
    conn.commit()
    conn.close()

    print("\n" + "=" * 70)
    print("ALL 7 VERIFICATION SCENARIOS PASSED WITH ZERO FAILURES!")
    print("=" * 70)

if __name__ == "__main__":
    run_all_verification_scenarios()
