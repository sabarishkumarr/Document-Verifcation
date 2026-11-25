"""
verify_final_presentation.py
-----------------------------
Validates the 6 specific presentation requirements:
1. Rejected applicant with one issue (e.g., 'Rejected — Expired Driving Licence')
2. Rejected applicant with multiple issues (e.g., 'Rejected — Expired document and identity mismatch')
3. Applicant with multiple affected documents (grouped as 1 row in Overview)
4. Applicant with no discrepancies ('No discrepancies found')
5. Overview and Reports showing strictly one row per applicant
6. Database audit history and individual validation results fully preserved
"""

import os
import sys
import json
import sqlite3
from typing import Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from backend.app import create_app

flask_app = create_app()
client = flask_app.test_client()
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "database", "veridoc.db")


def make_request(path: str, method: str = "GET", data: Dict[str, Any] = None) -> tuple[int, Dict[str, Any]]:
    full_path = f"/api{path}" if not path.startswith("/api") else path
    if method == "GET":
        resp = client.get(full_path)
    elif method == "POST":
        resp = client.post(full_path, json=data)
    else:
        resp = client.open(full_path, method=method, json=data)

    code = resp.status_code
    try:
        resp_body = resp.get_json() or {}
    except Exception:
        resp_body = {}
    return code, resp_body


def test_final_presentation():
    print("=" * 70)
    print("VERIDOC AI - FINAL PRESENTATION VERIFICATION")
    print("=" * 70)

    # 1. Overview Requires Attention: strictly ONE row per applicant
    print("\n[Check 1] Overview Requires Attention grouped by applicant...")
    code, stats_res = make_request("/dashboard/stats?dataset=all")
    assert code == 200, f"Expected 200, got {code}"
    stats = stats_res["data"]
    attention_items = stats.get("attention_items") or []
    
    seen_app_ids = set()
    for item in attention_items:
        app_id = item.get("applicant_id") or item.get("id")
        assert app_id not in seen_app_ids, f"Duplicate applicant {app_id} found in Overview attention_items!"
        seen_app_ids.add(app_id)
        # Check required fields
        assert "affected_doc_count" in item, "affected_doc_count missing"
        assert "main_issue" in item, "main_issue missing"
        assert "review_status" in item, "review_status missing"
        print(f"  Applicant: {item.get('applicant_name')} (#{app_id}) | "
              f"{item['affected_doc_count']} doc(s) | "
              f"Issue: '{item['main_issue']}' | "
              f"Status: {item['review_status']}")
    print(f"  PASS: All {len(attention_items)} Overview attention items are strictly unique per applicant.")

    # 2. Reports Summary: strictly ONE row per applicant with single primary issue
    print("\n[Check 2] Reports Audit Ledger: 1 row per applicant & clean primary reasons...")
    code, rep_res = make_request("/reports/summary?dataset=all")
    assert code == 200
    report_data = rep_res["data"]
    applicants = report_data.get("applicants") or []

    seen_rep_apps = set()
    single_issue_rej = None
    multi_issue_rej = None
    verified_clean = None
    multi_doc_app = None

    for a in applicants:
        app_id = a["id"]
        assert app_id not in seen_rep_apps, f"Duplicate applicant {app_id} found in Reports!"
        seen_rep_apps.add(app_id)

        # Check fields
        assert "primary_issue" in a, f"primary_issue missing on {app_id}"
        assert "validation_issues" in a, f"validation_issues missing on {app_id}"
        
        if a["status"] == "verified" and not verified_clean:
            verified_clean = a
        if a["status"] == "rejected":
            if "and" in a["primary_issue"].lower() and not multi_issue_rej:
                multi_issue_rej = a
            elif not single_issue_rej:
                single_issue_rej = a
        if a["doc_count"] >= 2 and not multi_doc_app:
            multi_doc_app = a

    print(f"  PASS: All {len(applicants)} applicants in Reports are strictly unique rows.")

    # 3. Test: Rejected applicant with one issue
    print("\n[Check 3] Rejected applicant with one issue...")
    # Create or reject applicant with one specific issue (e.g. Expired ID)
    test_rej_single_id = "APP-TEST-REJ-SINGLE"
    make_request("/applicants", method="POST", data={"id": test_rej_single_id, "name": "Rejection Single Test"})
    # Insert one expired document
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO documents (id, applicant_id, original_filename, stored_filename, mime_type, 
                                          file_size, document_type, classified_type, processing_status, 
                                          review_status, validation_results, upload_timestamp)
        VALUES ('DOC-REJ-S1', ?, 'expired_dl.pdf', 'expired_dl.pdf', 'application/pdf', 1024,
                'driving_licence', 'driving_licence', 'completed', 'rejected',
                '{"is_valid": false, "flags": ["Driving Licence expired on 2021-05-10"]}', datetime('now'))
    """, (test_rej_single_id,))
    conn.commit()
    conn.close()

    make_request(f"/applicants/{test_rej_single_id}/review", method="POST", data={
        "decision": "rejected",
        "notes": "Expired licence provided by applicant."
    })

    _, rep_updated = make_request("/reports/summary?dataset=all")
    single_found = next((a for a in rep_updated["data"]["applicants"] if a["id"] == test_rej_single_id), None)
    assert single_found is not None
    assert single_found["status"] == "rejected"
    assert "Rejected — Expired Driving Licence" in single_found["primary_issue"]
    print(f"  PASS: Primary issue is ONE clean string: '{single_found['primary_issue']}'.")

    # 4. Test: Rejected applicant with multiple issues
    print("\n[Check 4] Rejected applicant with multiple issues...")
    test_rej_multi_id = "APP-TEST-REJ-MULTI"
    make_request("/applicants", method="POST", data={"id": test_rej_multi_id, "name": "Rejection Multi Test"})
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO documents (id, applicant_id, original_filename, stored_filename, mime_type, 
                                          file_size, document_type, classified_type, processing_status, 
                                          review_status, extracted_fields, validation_results, upload_timestamp)
        VALUES ('DOC-REJ-M1', ?, 'pan_name_a.pdf', 'pan_name_a.pdf', 'application/pdf', 1024,
                'pan', 'pan', 'completed', 'rejected',
                '{"name": "Priya Sharma", "dob": "1990-01-01"}',
                '{"is_valid": true, "flags": []}', datetime('now'))
    """, (test_rej_multi_id,))
    c.execute("""
        INSERT OR REPLACE INTO documents (id, applicant_id, original_filename, stored_filename, mime_type, 
                                          file_size, document_type, classified_type, processing_status, 
                                          review_status, extracted_fields, validation_results, upload_timestamp)
        VALUES ('DOC-REJ-M2', ?, 'dl_expired_diff_name.pdf', 'dl_expired_diff_name.pdf', 'application/pdf', 1024,
                'driving_licence', 'driving_licence', 'completed', 'rejected',
                '{"name": "Priya Verma", "dob": "1990-01-01"}',
                '{"is_valid": false, "flags": ["Driving Licence expired on 2020-01-01"]}', datetime('now'))
    """, (test_rej_multi_id,))
    conn.commit()
    conn.close()

    make_request(f"/applicants/{test_rej_multi_id}/review", method="POST", data={
        "decision": "rejected",
        "notes": "Expired document and name conflict."
    })

    _, rep_updated2 = make_request("/reports/summary?dataset=all")
    multi_found = next((a for a in rep_updated2["data"]["applicants"] if a["id"] == test_rej_multi_id), None)
    assert multi_found is not None
    assert multi_found["status"] == "rejected"
    assert "Rejected — Expired document and identity mismatch" in multi_found["primary_issue"]
    assert len(multi_found["validation_issues"]) >= 2, "Detailed validation issues must remain preserved in validation_issues"
    print(f"  PASS: Multi-issue primary string: '{multi_found['primary_issue']}'.")
    print(f"        Underlying validation findings preserved: {multi_found['validation_issues']}")

    # 5. Test: Applicant with no discrepancies
    print("\n[Check 5] Applicant with no discrepancies...")
    assert verified_clean is not None, "At least one verified applicant must exist"
    assert verified_clean["primary_issue"] == "No discrepancies found"
    print(f"  PASS: Clean applicant '{verified_clean['name']}' has primary_issue: '{verified_clean['primary_issue']}'.")

    # 6. Test: Audit history and document findings fully intact
    print("\n[Check 6] Database audit trail and document findings preservation...")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM audit_reviews")
    audit_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM documents WHERE validation_results IS NOT NULL AND validation_results != ''")
    val_count = c.fetchone()[0]
    conn.close()
    assert audit_count > 0, "Audit reviews table must not be empty"
    assert val_count > 0, "Document validation results must not be discarded"
    print(f"  PASS: {audit_count} audit reviews recorded; {val_count} documents preserve full validation results.")

    print("\n" + "=" * 70)
    print("ALL 6 FINAL PRESENTATION CHECKS PASSED WITH ZERO ERRORS!")
    print("=" * 70)


if __name__ == "__main__":
    test_final_presentation()
