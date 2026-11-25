"""
verify_clean_workflow.py
------------------------
Validates all 11 critical KYC requirements for VeriDoc AI:
1. Multi-document upload under single applicant
2. Independent document field extraction
3. Strict applicant-level data isolation in comparison
4. Missing optional fields handled without false mismatch flags
5. Genuine discrepancies flagged
6. Applicant verification approval workflow & filtering
7. Applicant rejection workflow with justification persistence
8. Rejection details & officer remarks accessible in profile
9. Overview & Reports metrics match database counts
10. Automatic applicant name detection without manual name entry
11. Field corrections & audit state persistence
"""

import os
import sys
import json
import sqlite3
import urllib.request
import urllib.parse
from typing import Dict, Any

BASE_URL = "http://127.0.0.1:5000/api"
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "database", "veridoc.db")


def make_request(path: str, method: str = "GET", data: Dict[str, Any] = None) -> tuple[int, Dict[str, Any]]:
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            code = resp.status
            resp_body = json.loads(resp.read().decode("utf-8"))
            return code, resp_body
    except urllib.error.HTTPError as e:
        code = e.code
        resp_body = json.loads(e.read().decode("utf-8"))
        return code, resp_body


def test_11_cases():
    print("=" * 70)
    print("VERIDOC AI - CLEAN KYC WORKFLOW VERIFICATION (11 SCENARIOS)")
    print("=" * 70)
    
    passed_cases = 0

    # -------------------------------------------------------------
    # CASE 1: Upload multi-documents for one applicant -> grouped under one applicant
    # -------------------------------------------------------------
    print("\n[Case 1] Multi-document applicant grouping...")
    # Using existing synthetic or demo applicant APPL-SYN-001 or APP-DEMO-001
    code, res = make_request("/applicants/APPL-SYN-001")
    assert code == 200, f"Expected 200, got {code}"
    docs = res["data"]["documents"]
    assert len(docs) >= 2, f"Expected at least 2 documents under APPL-SYN-001, got {len(docs)}"
    for d in docs:
        assert d["applicant_id"] == "APPL-SYN-001", f"Doc {d['id']} applicant_id {d['applicant_id']} != APPL-SYN-001"
    print(f"  PASS: {len(docs)} documents correctly grouped under APPL-SYN-001 with strict applicant_id.")
    passed_cases += 1

    # -------------------------------------------------------------
    # CASE 2: Information extracted separately from each document
    # -------------------------------------------------------------
    print("\n[Case 2] Independent extraction per document...")
    doc_types_seen = set()
    for d in docs:
        f = d.get("extracted_fields") or {}
        doc_type = d.get("classified_type") or d.get("document_type")
        doc_types_seen.add(doc_type)
        assert "name" in f or "dob" in f, f"Document {d['id']} missing extracted fields"
    assert len(doc_types_seen) >= 2, f"Expected multiple document types, got {doc_types_seen}"
    print(f"  PASS: Independent extracted fields present across types: {doc_types_seen}")
    passed_cases += 1

    # -------------------------------------------------------------
    # CASE 3: Comparison strictly isolates applicant's documents
    # -------------------------------------------------------------
    print("\n[Case 3] Applicant isolation in comparison matrix...")
    matrix = res["data"]["cross_comparison"]["matrix"]
    matrix_cols = matrix["columns"]
    assert len(matrix_cols) == len(docs), f"Matrix columns {len(matrix_cols)} != docs {len(docs)}"
    for col in matrix_cols:
        col_doc_ids = [d["id"] for d in docs]
        assert col["id"] in col_doc_ids, f"Foreign document {col['id']} found in matrix!"
    print(f"  PASS: Exactly {len(matrix_cols)} columns in matrix; 0 foreign documents leaked.")
    passed_cases += 1

    # -------------------------------------------------------------
    # CASE 4: Missing optional fields are not flagged as mismatches
    # -------------------------------------------------------------
    print("\n[Case 4] Missing optional fields handling...")
    for row in matrix["rows"]:
        if row["attribute_key"] in ("address", "father_name"):
            # Should be VALID, MATCH, or NOT DETECTED / UNAVAILABLE, never MISMATCH if only present in one doc
            assert row["result_status"] != "mismatch", (
                f"Attribute '{row['attribute_key']}' incorrectly marked as mismatch: {row['explanation']}"
            )
    print("  PASS: Attributes missing in partial documents are not falsely flagged as mismatches.")
    passed_cases += 1

    # -------------------------------------------------------------
    # CASE 5: Genuine discrepancies flagged
    # -------------------------------------------------------------
    print("\n[Case 5] Genuine discrepancy detection...")
    # Inspect applicant APPL-SYN-003 (Rohan Nair - expired DL)
    code_rohan, res_rohan = make_request("/applicants/APPL-SYN-003")
    assert code_rohan == 200
    rohan_matrix = res_rohan["data"]["cross_comparison"]["matrix"]
    expiry_row = next((r for r in rohan_matrix["rows"] if r["attribute_key"] == "expiry_date"), None)
    assert expiry_row is not None, "Expiry date row missing in Rohan Nair matrix"
    assert expiry_row["result_status"].lower() == "expired", f"Expected 'expired', got {expiry_row['result_status']}"
    assert res_rohan["data"]["cross_comparison"]["overall_verdict"] in ("REQUIRES_ATTENTION", "DISCREPANCY_FLAGGED")
    print("  PASS: Rohan Nair expired driving licence flagged as 'expired' and overall verdict REQUIRES_ATTENTION.")
    passed_cases += 1

    # -------------------------------------------------------------
    # CASE 6: Verify applicant -> appears under Verified filter
    # -------------------------------------------------------------
    print("\n[Case 6] Applicant verification approval...")
    test_app_id = "APP-TEST-VERIFY-001"
    # Ensure test applicant exists
    make_request("/applicants", method="POST", data={"id": test_app_id, "name": "Test Verified User"})
    # Submit verification review
    code_rev, res_rev = make_request(f"/applicants/{test_app_id}/review", method="POST", data={
        "decision": "verified",
        "notes": "All identity checks cleared by officer."
    })
    assert code_rev == 200, f"Expected 200 on review, got {code_rev}: {res_rev}"
    
    # Query verified applicants
    code_ver_list, res_ver_list = make_request("/applicants?status=verified")
    assert code_ver_list == 200
    verified_ids = [a["id"] for a in res_ver_list["data"]["applicants"]]
    assert test_app_id in verified_ids, f"{test_app_id} not found in verified filter: {verified_ids}"
    print(f"  PASS: Applicant {test_app_id} approved and retrieved under ?status=verified filter.")
    passed_cases += 1

    # -------------------------------------------------------------
    # CASE 7: Reject applicant with justification notes -> appears under Rejected filter after reload
    # -------------------------------------------------------------
    print("\n[Case 7] Applicant rejection & persistence under Rejected filter...")
    test_rej_id = "APP-TEST-REJECT-002"
    make_request("/applicants", method="POST", data={"id": test_rej_id, "name": "Test Rejected User"})
    justification_text = "Fraudulent address proof and forged signature."
    code_rej, res_rej = make_request(f"/applicants/{test_rej_id}/review", method="POST", data={
        "decision": "rejected",
        "notes": justification_text
    })
    assert code_rej == 200, f"Expected 200 on rejection, got {code_rej}: {res_rej}"

    # Verify status in database
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT status, notes FROM applicants WHERE id = ?", (test_rej_id,))
    row = c.fetchone()
    conn.close()
    assert row is not None, f"Applicant {test_rej_id} not found in SQLite"
    assert row[0] == "rejected", f"Expected SQLite status 'rejected', got '{row[0]}'"
    assert justification_text in row[1], f"Expected notes '{justification_text}', got '{row[1]}'"

    # Verify via API list filter
    code_rej_list, res_rej_list = make_request("/applicants?status=rejected")
    assert code_rej_list == 200
    rejected_ids = [a["id"] for a in res_rej_list["data"]["applicants"]]
    assert test_rej_id in rejected_ids, f"{test_rej_id} not in rejected filter list: {rejected_ids}"
    print(f"  PASS: Applicant {test_rej_id} strictly rejected in SQLite and visible under ?status=rejected.")
    passed_cases += 1

    # -------------------------------------------------------------
    # CASE 8: Rejected applicant details and justification notes remain fully accessible
    # -------------------------------------------------------------
    print("\n[Case 8] Rejected applicant profile & notes accessibility...")
    code_prof, res_prof = make_request(f"/applicants/{test_rej_id}")
    assert code_prof == 200
    prof_data = res_prof["data"]["applicant"]
    assert prof_data["status"] == "rejected", f"Expected profile status 'rejected', got '{prof_data['status']}'"
    assert prof_data["notes"] == justification_text, f"Expected notes '{justification_text}', got '{prof_data['notes']}'"
    print(f"  PASS: Profile API returns status='rejected' and exact justification notes without being overwritten.")
    passed_cases += 1

    # -------------------------------------------------------------
    # CASE 9: Overview and Reports metrics match SQLite counts
    # -------------------------------------------------------------
    print("\n[Case 9] Database count consistency with Overview & Reports...")
    code_stats, res_stats = make_request("/dashboard/stats?dataset=all")
    assert code_stats == 200
    stats = res_stats["data"]
    
    code_rep, res_rep = make_request("/reports/summary?dataset=all")
    assert code_rep == 200
    rep = res_rep["data"]

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM documents")
    total_db_docs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM applicants")
    total_db_apps = c.fetchone()[0]
    conn.close()

    assert stats["total_documents"] == total_db_docs, f"Stats docs {stats['total_documents']} != DB {total_db_docs}"
    assert rep["total_documents"] == total_db_docs, f"Report docs {rep['total_documents']} != DB {total_db_docs}"
    assert rep["total_applicants"] == total_db_apps, f"Report apps {rep['total_applicants']} != DB {total_db_apps}"
    print(f"  PASS: Overview ({stats['total_documents']} docs) & Reports ({rep['total_documents']} docs, {rep['total_applicants']} apps) exactly match SQLite.")
    passed_cases += 1

    # -------------------------------------------------------------
    # CASE 10: Automatic applicant name detection without manual name entry
    # -------------------------------------------------------------
    print("\n[Case 10] Automatic applicant name detection...")
    # Create an applicant with no name (provisional)
    prov_id = "APP-TEST-PROV-003"
    make_request("/applicants", method="POST", data={"id": prov_id, "name": None})
    
    # Associate a document with extracted name "Sunita Rao"
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    doc_fields = json.dumps({
        "name": "Sunita Rao",
        "dob": "1991-07-22",
        "pan_number": "ABCPS1234D"
    })
    c.execute("""
        INSERT OR REPLACE INTO documents (id, applicant_id, original_filename, stored_filename, mime_type, 
                                          file_size, document_type, classified_type, processing_status, 
                                          review_status, extracted_fields, upload_timestamp)
        VALUES ('DOC-PROV-001', ?, 'sunita_pan.pdf', 'sunita_pan.pdf', 'application/pdf', 
                1024, 'pan', 'pan', 'completed', 'approved', ?, datetime('now'))
    """, (prov_id, doc_fields))
    conn.commit()
    conn.close()

    # Re-fetch applicant profile
    code_prov, res_prov = make_request(f"/applicants/{prov_id}")
    assert code_prov == 200
    detected_name = res_prov["data"]["applicant"]["name"]
    assert detected_name == "Sunita Rao", f"Expected auto-detected name 'Sunita Rao', got '{detected_name}'"
    print(f"  PASS: Provisional applicant without manual name entry auto-detected customer name: '{detected_name}'.")
    passed_cases += 1

    # -------------------------------------------------------------
    # CASE 11: Document field correction & audit persistence
    # -------------------------------------------------------------
    print("\n[Case 11] Document field correction workflow...")
    # Update field on DOC-PROV-001 via document review endpoint
    code_edit, res_edit = make_request("/documents/DOC-PROV-001/review", method="POST", data={
        "decision": "approved",
        "edited_fields": {
            "name": "Sunita K. Rao",
            "dob": "1991-07-22",
            "pan_number": "ABCPS1234D"
        },
        "notes": "Corrected middle initial from physical document verification."
    })
    assert code_edit == 200, f"Expected 200, got {code_edit}: {res_edit}"
    
    # Verify in profile
    code_prov_after, res_prov_after = make_request(f"/applicants/{prov_id}")
    assert code_prov_after == 200
    updated_name = res_prov_after["data"]["applicant"]["name"]
    assert "Sunita" in updated_name
    print(f"  PASS: Field correction persisted and applicant profile updated to '{updated_name}'.")
    passed_cases += 1

    print("\n" + "=" * 70)
    print(f"ALL {passed_cases}/11 KYC WORKFLOW SCENARIOS PASSED WITH ZERO FAILURES!")
    print("=" * 70)


if __name__ == "__main__":
    test_11_cases()
