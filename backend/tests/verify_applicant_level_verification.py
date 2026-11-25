import os
import sys
import json
import urllib.request
import urllib.error

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.database.db import get_applicant, list_applicants, get_documents_by_applicant, get_db_connection
from backend.services.comparator import CrossDocumentComparator

def test_applicant_level_verification_workflow():
    print("==========================================================")
    print("TESTING APPLICANT-LEVEL VERIFICATION ARCHITECTURE & LOGIC")
    print("==========================================================")
    
    BASE_URL = "http://127.0.0.1:5000/api"

    # 1. Verify Queue Ledger has ONE ROW PER APPLICANT
    print("\n--- TEST 1: One Row Per Applicant in Queue Ledger ---")
    req = urllib.request.urlopen(f"{BASE_URL}/applicants?limit=100")
    res = json.loads(req.read())
    applicants = res["data"]["applicants"]
    
    # Assert unique applicant IDs
    app_ids = [a["id"] for a in applicants]
    assert len(app_ids) == len(set(app_ids)), f"Duplicate applicant entries found in ledger: {app_ids}"
    print(f"✓ Test 1 PASSED: Retrieved {len(applicants)} unique applicants in ledger (0 duplicated rows).")

    # Verify specific test applicants exist
    app_map = {a["id"]: a for a in applicants}
    assert "APPL-SYN-001" in app_map, "Applicant 1 (Aarav Mehta) missing from applicants list"
    assert "APPL-SYN-002" in app_map, "Applicant 2 (Priya Sharma) missing from applicants list"
    assert "APPL-SYN-003" in app_map, "Applicant 3 (Rohan Nair) missing from applicants list"

    # 2. Test Applicant 1: Aarav Mehta (APPL-SYN-001)
    print("\n--- TEST 2: Applicant 1 - Aarav Mehta (Aadhaar & PAN) ---")
    req = urllib.request.urlopen(f"{BASE_URL}/applicants/APPL-SYN-001")
    prof1 = json.loads(req.read())["data"]
    matrix1 = prof1["cross_comparison"]["matrix"]
    
    assert prof1["applicant"]["name"] == "Aarav Mehta"
    assert len(prof1["documents"]) == 2, f"Expected 2 documents for Aarav Mehta, got {len(prof1['documents'])}"
    
    # Verify consolidated table columns: Aadhaar, PAN
    col_types = [c["document_type"] for c in matrix1["columns"]]
    assert "aadhaar" in col_types and "pan" in col_types, f"Unexpected columns: {col_types}"
    assert len(col_types) == 2, f"Expected exactly 2 columns, got {len(col_types)}"
    
    # Verify rows: exactly 7 rows, NO issue_date
    row_keys = [r["attribute_key"] for r in matrix1["rows"]]
    assert "issue_date" not in row_keys, "Date of Issue must NOT be in consolidated table"
    assert "name" in row_keys and "dob" in row_keys and "gender" in row_keys and "id_number" in row_keys
    
    # Check field comparisons:
    for r in matrix1["rows"]:
        k = r["attribute_key"]
        if k == "name":
            assert r["result_status"] == "MATCH", f"Expected name MATCH, got {r['result_status']}"
        elif k == "dob":
            assert r["result_status"] == "MATCH", f"Expected DOB MATCH, got {r['result_status']}"
        elif k == "gender":
            # PAN has no gender, so Gender appears only on Aadhaar -> MUST NOT be an error
            assert r["result_status"] == "NOT APPLICABLE", f"Gender appearing on only 1 doc must be NOT APPLICABLE, got {r['result_status']}"
        elif k == "address":
            # Neither doc has address in this fixture -> marked NOT DETECTED or UNAVAILABLE
            assert r["result_status"] in ("MATCH", "UNAVAILABLE", "NOT DETECTED"), f"Expected MATCH, UNAVAILABLE or NOT DETECTED for address, got {r['result_status']}"
        elif k == "id_number":
            # ID numbers must not be cross-compared
            assert r["result_status"] == "MATCH", f"ID format validation must be MATCH, got {r['result_status']}"
        elif k == "expiry_date":
            # Both Aadhaar and PAN are Permanent / Lifetime
            assert r["result_status"] == "MATCH", f"Expected expiry MATCH (Permanent), got {r['result_status']}"

    print(f"✓ Test 2 PASSED: Aarav Mehta has clean consolidated table. Single-field attributes do not create false mismatches.")

    # 3. Test Applicant 2: Priya Sharma (APPL-SYN-002) - 5 documents
    print("\n--- TEST 3: Applicant 2 - Priya Sharma (Multiple Documents) ---")
    req = urllib.request.urlopen(f"{BASE_URL}/applicants/APPL-SYN-002")
    prof2 = json.loads(req.read())["data"]
    matrix2 = prof2["cross_comparison"]["matrix"]
    
    print(f"  Priya Sharma documents count: {len(prof2['documents'])}")
    print(f"  Matrix columns: {[c['type_label'] for c in matrix2['columns']]}")
    assert len(matrix2["columns"]) >= 2
    row_keys2 = [r["attribute_key"] for r in matrix2["rows"]]
    assert "issue_date" not in row_keys2
    print("✓ Test 3 PASSED: Priya Sharma documents loaded in single workspace without duplication.")

    # 4. Test Applicant 3: Rohan Nair (APPL-SYN-003) - Expired Driving Licence Gate
    print("\n--- TEST 4: Applicant 3 - Rohan Nair (Expired Driving Licence Protection) ---")
    req = urllib.request.urlopen(f"{BASE_URL}/applicants/APPL-SYN-003")
    prof3 = json.loads(req.read())["data"]
    matrix3 = prof3["cross_comparison"]["matrix"]
    
    exp_row = next((r for r in matrix3["rows"] if r["attribute_key"] == "expiry_date"), None)
    assert exp_row is not None, "Expiry Date row missing from matrix"
    assert exp_row["result_status"] == "EXPIRED", f"Expected EXPIRED for Rohan Nair's DL, got {exp_row['result_status']}"
    print(f"  Rohan Nair Expiry Status: {exp_row['result_status']} - {exp_row['explanation']}")
    
    # Attempt to mark Rohan Nair verified -> MUST BE BLOCKED BY SERVER
    review_payload = json.dumps({
        "decision": "verified",
        "notes": "Attempting illegal verification approval of expired document",
        "officer_name": "Arjun Mehta"
    }).encode("utf-8")
    
    req_verify = urllib.request.Request(
        f"{BASE_URL}/applicants/APPL-SYN-003/review",
        data=review_payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        urllib.request.urlopen(req_verify)
        raise AssertionError("Server should have REJECTED verification of applicant with expired document!")
    except urllib.error.HTTPError as e:
        err_res = json.loads(e.read().decode())
        print(f"  Server correctly rejected approval: HTTP {e.code} - {err_res['message']}")
        assert e.code == 400
        assert "expired" in err_res["message"].lower()
    
    print("✓ Test 4 PASSED: Expired document strictly prevents applicant verification approval.")

    # 5. Test Valid Approval for Aarav Mehta (APPL-SYN-001)
    print("\n--- TEST 5: Legitimate Applicant Verification Approval ---")
    approve_payload = json.dumps({
        "decision": "verified",
        "notes": "All identity attributes match across PAN and Aadhaar.",
        "officer_name": "Arjun Mehta"
    }).encode("utf-8")
    
    req_approve = urllib.request.Request(
        f"{BASE_URL}/applicants/APPL-SYN-001/review",
        data=approve_payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    res_approve = json.loads(urllib.request.urlopen(req_approve).read())
    assert res_approve["success"] is True
    assert res_approve["data"]["decision"] == "verified"
    
    # Confirm in database
    appl1 = get_applicant("APPL-SYN-001")
    assert appl1["status"] == "verified"
    docs1 = get_documents_by_applicant("APPL-SYN-001")
    assert all(d["review_status"] == "approved" for d in docs1)
    print("✓ Test 5 PASSED: Applicant verification approval successfully updated applicant and harmonized document statuses.")

    print("\n==========================================================")
    print("ALL APPLICANT-LEVEL VERIFICATION TESTS COMPLETED & PASSED!")
    print("==========================================================")

if __name__ == "__main__":
    test_applicant_level_verification_workflow()
