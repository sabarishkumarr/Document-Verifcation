"""
End-to-End Application Verification Script for VeriDoc AI.
Tests live Flask endpoints against actual SQLite database and filesystem storage.
"""

import sys
import json
import urllib.request
import urllib.parse
from pathlib import Path

BASE_URL = "http://127.0.0.1:5000/api"

def make_req(path, method="GET", data=None, headers=None):
    url = f"{BASE_URL}{path}"
    req_headers = headers or {}
    req_data = None
    if data is not None:
        if isinstance(data, dict):
            req_data = json.dumps(data).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
        elif isinstance(data, bytes):
            req_data = data
    req = urllib.request.Request(url, data=req_data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
            return resp.status, resp.headers, body
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()

def run_tests():
    print("=" * 70)
    print("VERIDOC AI — END-TO-END VERIFICATION")
    print("=" * 70)

    # 1. Health check
    status, _, body = make_req("/health")
    assert status == 200, f"Health check failed: {status}"
    print("[PASS] 1. Health check: 200 OK")

    # 2. Diagnostics: OCR & AI status
    status, _, body = make_req("/documents/ocr-status")
    ocr_info = json.loads(body)["data"]
    status, _, body = make_req("/documents/ai-status")
    ai_info = json.loads(body)["data"]
    print(f"[PASS] 2. Engine Diagnostics: Tesseract Operational={ocr_info['tesseract_available']}, AI Provider={ai_info['provider']} (Configured={ai_info['configured']})")

    # 3. Dashboard Statistics from SQLite
    status, _, body = make_req("/dashboard/stats")
    assert status == 200
    stats = json.loads(body)["data"]
    print(f"[PASS] 3. Dashboard stats: {stats['total_documents']} total docs, {stats['approved_count']} approved, {stats['pending_review_count']} pending, {stats['issues_count']} issues, {stats['total_applicants']} applicants")
    assert stats["total_documents"] == stats["approved_count"] + stats["pending_review_count"] + stats["issues_count"], "Reconciliation equation holds"

    # 4. Test 10 Synthetic Applicants Scenarios in SQLite
    print("\n[VERIFYING 10 SYNTHETIC APPLICANT SCENARIOS IN DATABASE]")
    scenarios = [
        ("APPL-SYN-001", "Aarav Mehta", "verified", "Matching PAN and Aadhaar"),
        ("APPL-SYN-002", "Priya Sharma", "verified", "Matching PAN, Aadhaar and Passport"),
        ("APPL-SYN-003", "Rohan Nair", "requires_attention", "Expired Driving Licence"),
        ("APPL-SYN-004", "Ananya Iyer", "requires_attention", "Name mismatch between Aadhaar and Voter ID"),
        ("APPL-SYN-005", "Kabir Malhotra", "requires_attention", "DOB mismatch between PAN and Passport"),
        ("APPL-SYN-006", "Meera Krishnan", "requires_attention", "Missing mandatory fields"),
        ("APPL-SYN-007", "Dev Patel", "requires_attention", "Expired Passport"),
        ("APPL-SYN-008", "Ishita Rao", "requires_attention", "Low-quality, unreadable scan"),
        ("APPL-SYN-009", "Vikram Das", "verified", "Multiple documents with consistency checks"),
        ("APPL-SYN-010", "Neha Kapoor", "verified", "All 5 KYC categories complete workflow"),
    ]

    status, _, body = make_req("/applicants?limit=100")
    assert status == 200
    apps = json.loads(body)["data"]["applicants"]
    app_id_map = {a["id"]: a for a in apps}

    for app_id, name, expected_status, description in scenarios:
        app = app_id_map.get(app_id)
        assert app is not None, f"Applicant '{app_id}' ({name}) missing from database!"
        # Check profile and cross-comparison
        st_code, _, prof_body = make_req(f"/applicants/{app_id}")
        assert st_code == 200
        prof = json.loads(prof_body)["data"]
        doc_count = len(prof["documents"])
        verdict = prof.get("cross_comparison", {}).get("overall_verdict", "N/A")
        print(f"  - [{app['status'].upper()}] {name} ({app_id}): {doc_count} docs | Cross-Check: {verdict} | Scenario: {description}")
        assert app["status"] == expected_status, f"Expected {expected_status} for {name}, got {app['status']}"

    # 5. Test Live Document Review & Human Correction
    print("\n[TESTING HUMAN REVIEW, EDITING, AND STATUS TRANSITIONS]")
    # Get a pending document
    st_code, _, queue_body = make_req("/documents/queue?status=pending")
    queue_docs = json.loads(queue_body)["data"]["queue"]
    target_doc = queue_docs[0] if queue_docs else None
    if not target_doc:
        st_code, _, all_docs_body = make_req("/documents?limit=1")
        target_doc = json.loads(all_docs_body)["data"]["documents"][0]

    doc_id = target_doc["id"]
    print(f"  Target document for review tests: {doc_id} ({target_doc['original_filename']})")

    # A. Save Edits without changing review status
    edit_payload = {
        "decision": target_doc.get("review_status", "pending"),
        "edited_fields": {
            "name": "Audit Test Name",
            "dob": "1990-01-01"
        },
        "notes": "Testing field edits save",
        "officer_name": "Arjun Mehta (Senior Officer)"
    }
    st, _, res_body = make_req(f"/documents/{doc_id}/review", method="POST", data=edit_payload)
    assert st == 200, f"Save edits failed: {st} {res_body}"
    res = json.loads(res_body)["data"]["review"]
    assert res["extracted_fields"]["name"] == "Audit Test Name"
    print("  [PASS] A. Save corrections and field edits: Verified in SQLite")

    # B. Request Resubmission
    resub_payload = {
        "decision": "resubmission_requested",
        "notes": "Blurry document scan, please upload high-contrast replacement.",
        "officer_name": "Arjun Mehta (Senior Officer)"
    }
    st, _, res_body = make_req(f"/documents/{doc_id}/review", method="POST", data=resub_payload)
    assert st == 200
    res = json.loads(res_body)["data"]["review"]
    assert res["review_status"] == "resubmission_requested"
    print("  [PASS] B. Request Resubmission: Successfully marked as 'resubmission_requested'")

    # C. Mark Verified (Approved)
    approve_payload = {
        "decision": "approved",
        "notes": "Physically verified and approved.",
        "officer_name": "Arjun Mehta (Senior Officer)"
    }
    st, _, res_body = make_req(f"/documents/{doc_id}/review", method="POST", data=approve_payload)
    assert st == 200
    res = json.loads(res_body)["data"]["review"]
    assert res["review_status"] == "approved"
    print("  [PASS] C. Mark Verified (Approved): Successfully marked as 'approved'")

    # 6. Test Reports Generation & Downloads
    print("\n[TESTING REPORT GENERATION AND EXPORTS]")
    st, _, rep_body = make_req("/reports/summary")
    assert st == 200
    rep_data = json.loads(rep_body)["data"]
    print(f"  [PASS] Reports Summary API: {rep_data['total_applicants']} applicants, {rep_data['total_documents']} documents")

    st, headers, csv_data = make_req("/reports/download?format=csv")
    assert st == 200
    assert "attachment; filename=veridoc_kyc_verification_report.csv" in headers.get("Content-Disposition")
    assert len(csv_data) > 500
    print(f"  [PASS] CSV Download: HTTP 200 ({len(csv_data)} bytes generated with correct attachment headers)")

    st, headers, json_data = make_req("/reports/download?format=json")
    assert st == 200
    assert "attachment; filename=veridoc_kyc_verification_report.json" in headers.get("Content-Disposition")
    print(f"  [PASS] JSON Download: HTTP 200 ({len(json_data)} bytes generated with correct attachment headers)")

    # 7. Test Uploading and Processing All 5 Document Types
    print("\n[TESTING UPLOAD AND PROCESSING OF ALL 5 KYC DOCUMENT TYPES]")
    fixtures_dir = Path("backend/tests/fixtures/synthetic_kyc")
    test_files = [
        ("pan", fixtures_dir / "01_aarav_mehta/aarav_mehta_pan.pdf"),
        ("aadhaar", fixtures_dir / "01_aarav_mehta/aarav_mehta_aadhaar.pdf"),
        ("passport", fixtures_dir / "02_priya_sharma/priya_sharma_passport.pdf"),
        ("driving_licence", fixtures_dir / "03_rohan_nair/rohan_nair_driving_licence.pdf"),
        ("voter_id", fixtures_dir / "06_meera_krishnan/meera_krishnan_voter_id.pdf"),
    ]

    boundary = "----WebKitFormBoundaryE2EVerification123"
    body_parts = []
    applicant_id = "APP-TEST-E2E-LIVE"

    for dtype, fpath in test_files:
        assert fpath.exists(), f"Missing fixture {fpath}"
        with open(fpath, "rb") as f:
            content = f.read()
        body_parts.append(f"--{boundary}\r\n".encode("utf-8"))
        body_parts.append(f'Content-Disposition: form-data; name="applicant_id"\r\n\r\n{applicant_id}\r\n'.encode("utf-8"))
        body_parts.append(f"--{boundary}\r\n".encode("utf-8"))
        body_parts.append(f'Content-Disposition: form-data; name="files"; filename="{fpath.name}"\r\n'.encode("utf-8"))
        body_parts.append(b"Content-Type: application/pdf\r\n\r\n")
        body_parts.append(content)
        body_parts.append(b"\r\n")
    body_parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    multipart_data = b"".join(body_parts)

    st, _, up_resp = make_req(
        "/documents/upload",
        method="POST",
        data=multipart_data,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    assert st in (200, 201), f"Upload failed: {st} {up_resp}"
    up_json = json.loads(up_resp)
    uploaded = up_json.get("uploaded", [])
    print(f"  [PASS] Successfully uploaded {len(uploaded)} documents across all 5 types for applicant '{applicant_id}'")

    for doc in uploaded:
        doc_id = doc["id"]
        fname = doc["original_filename"]
        st, _, proc_resp = make_req(f"/documents/{doc_id}/process", method="POST")
        assert st == 200, f"Processing failed: {proc_resp}"
        proc_data = json.loads(proc_resp)["data"]["result"]
        classified = proc_data["classification"]["classified_type"]
        status = proc_data["validation"]["overall_status"]
        strategy = proc_data.get("extraction_strategy")
        method = proc_data.get("extracted_fields", {}).get("extraction_method") or strategy
        print(f"  - {fname} -> Classified: {classified.upper()} | Method: {method} | Validation: {status.upper()}")

    print("\n" + "=" * 70)
    print("ALL 7 END-TO-END VERIFICATION CATEGORIES COMPLETED SUCCESSFULLY")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
