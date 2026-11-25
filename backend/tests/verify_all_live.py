import os
import sys
import json
import urllib.request
import urllib.parse
import mimetypes
import uuid
from pathlib import Path

BASE_URL = "http://127.0.0.1:5000"
FIXTURES_DIR = Path("backend/tests/fixtures/synthetic_kyc")

def log_section(title):
    print("\n" + "=" * 80)
    print(f" {title.upper()} ")
    print("=" * 80)

def http_get(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))

def http_post_json(url, data=None):
    body = json.dumps(data or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))

def http_put_json(url, data=None):
    body = json.dumps(data or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="PUT"
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))

def http_post_multipart(url, file_path, form_data):
    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    body = bytearray()
    
    # Form fields
    for k, v in form_data.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode("utf-8"))
        body.extend(f"{v}\r\n".encode("utf-8"))
        
    # File field
    filename = Path(file_path).name
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("utf-8"))
    body.extend(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
    with open(file_path, "rb") as f:
        body.extend(f.read())
    body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    
    req = urllib.request.Request(
        url,
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))

def test_live_api():
    results = {
        "passed": [],
        "failed": [],
        "details": {}
    }
    
    # 1. Health check & Diagnostics
    log_section("1. Live Health Check & Engine Diagnostics")
    try:
        status, data = http_get(f"{BASE_URL}/api/health")
        assert status == 200, f"Expected 200, got {status}"
        assert data.get("success") is True
        print(f"✓ Health check OK: {data.get('message')}")
        results["passed"].append("Health check endpoint (/api/health)")
    except Exception as e:
        print(f"✗ Health check FAILED: {e}")
        results["failed"].append(("Health check", str(e)))

    try:
        status, data = http_get(f"{BASE_URL}/api/documents/ocr-status")
        assert status == 200, f"Expected 200, got {status}"
        ocr_info = data.get("data", {})
        print(f"✓ Local OCR Engine Status: Tesseract available={ocr_info.get('tesseract_available')}")
        results["passed"].append("OCR status endpoint (/api/documents/ocr-status)")
    except Exception as e:
        print(f"✗ OCR status FAILED: {e}")
        results["failed"].append(("OCR status", str(e)))

    try:
        status, data = http_get(f"{BASE_URL}/api/documents/ai-status")
        assert status == 200, f"Expected 200, got {status}"
        ai_info = data.get("data", {})
        print(f"✓ AI Document Intelligence Status: Provider={ai_info.get('provider')}, Configured={ai_info.get('configured')}, Message='{ai_info.get('status_message')}'")
        results["passed"].append("AI status endpoint (/api/documents/ai-status)")
    except Exception as e:
        print(f"✗ AI status FAILED: {e}")
        results["failed"].append(("AI status", str(e)))

    # 2. Upload and Process All 5 Types with Actual Files
    log_section("2. Live Upload & Processing for All 5 Document Types")
    doc_samples = {
        "passport": FIXTURES_DIR / "10_neha_kapoor" / "neha_kapoor_passport.pdf",
        "voter_id": FIXTURES_DIR / "10_neha_kapoor" / "neha_kapoor_voter_id.jpg",
        "pan": FIXTURES_DIR / "10_neha_kapoor" / "neha_kapoor_pan.pdf",
        "aadhaar": FIXTURES_DIR / "10_neha_kapoor" / "neha_kapoor_aadhaar.pdf",
        "driving_licence": FIXTURES_DIR / "10_neha_kapoor" / "neha_kapoor_driving_licence.pdf",
    }
    
    uploaded_docs = {}
    for doc_type, file_path in doc_samples.items():
        assert file_path.exists(), f"File {file_path} not found"
        try:
            status, upload_res = http_post_multipart(
                f"{BASE_URL}/api/documents/upload",
                file_path,
                {"applicant_id": "APPL-SYN-010"}
            )
            assert status == 201, f"Upload status {status}: {upload_res}"
            uploaded_list = upload_res.get("data", {}).get("uploaded", [])
            assert len(uploaded_list) > 0, "No document in uploaded response list"
            doc_data = uploaded_list[0]
            doc_id = doc_data["id"]
            
            # Trigger pipeline processing
            status, proc_res = http_post_json(f"{BASE_URL}/api/documents/{doc_id}/process")
            assert status == 200, f"Process status {status}: {proc_res}"
            pipeline_data = proc_res["data"]["result"]
            
            classified = pipeline_data.get("classification", {}).get("classified_type")
            assert classified == doc_type, f"Expected {doc_type}, got {classified}"
            
            extracted = pipeline_data.get("extracted_fields", {})
            assert extracted.get("name") or extracted.get("applicant_name"), f"Missing extracted name for {doc_type}"
            assert extracted.get("id_number") or extracted.get("identification_number"), f"Missing extracted id_number for {doc_type}"
            
            val_status = pipeline_data.get("validation", {}).get("overall_status")
            strat = pipeline_data.get("extraction_strategy", "hybrid")
            print(f"✓ {doc_type.upper():16} | File: {file_path.name:32} | ID: {doc_id[:8]}... | Classified: {classified:15} | Strategy: {strat:20} | Validation: {val_status}")
            uploaded_docs[doc_type] = {
                "id": doc_id,
                "classified": classified,
                "extracted": extracted,
                "validation": pipeline_data.get("validation")
            }
            results["passed"].append(f"Upload and process {doc_type}")
        except Exception as e:
            print(f"✗ Failed {doc_type}: {e}")
            results["failed"].append((f"Upload/process {doc_type}", str(e)))

    # 3. Test Cross-Document Comparison, Mismatches & Expiry Cases
    log_section("3. Cross-Document Comparisons, Mismatches, and Expiry Cases")
    
    # 3a. Matching applicant: Neha Kapoor
    try:
        status, comp_res = http_get(f"{BASE_URL}/api/applicants/APPL-SYN-010")
        assert status == 200, f"Compare status {status}: {comp_res}"
        data = comp_res.get("data", {})
        comp = data.get("cross_comparison", {})
        verdict = comp.get("overall_verdict")
        consistency = comp.get("consistency_score")
        print(f"✓ Neha Kapoor (APPL-SYN-010) Cross-Doc Check: Verdict={verdict}, Consistency={consistency}%")
        assert verdict == "VERIFIED", f"Expected VERIFIED, got {verdict}"
        results["passed"].append("Cross-document matching: Neha Kapoor")
    except Exception as e:
        print(f"✗ Neha Kapoor comparison failed: {e}")
        results["failed"].append(("Cross-doc Neha Kapoor", str(e)))
        
    # 3b. Name mismatch case: Ananya Iyer (APPL-SYN-004)
    try:
        status, comp_res = http_get(f"{BASE_URL}/api/applicants/APPL-SYN-004")
        assert status == 200
        data = comp_res.get("data", {})
        comp = data.get("cross_comparison", {})
        verdict = comp.get("overall_verdict")
        discrepancies = comp.get("discrepancies", [])
        assert verdict == "DISCREPANCY_FLAGGED" or len(discrepancies) > 0
        print(f"✓ Ananya Iyer (APPL-SYN-004) Name Mismatch Flagged: Verdict={verdict}, Discrepancies={len(discrepancies)} ({discrepancies[0] if discrepancies else ''})")
        results["passed"].append("Name mismatch detection: Ananya Iyer")
    except Exception as e:
        print(f"✗ Ananya Iyer comparison check failed: {e}")
        results["failed"].append(("Name mismatch Ananya Iyer", str(e)))

    # 3c. DOB mismatch case: Kabir Malhotra (APPL-SYN-005)
    try:
        status, comp_res = http_get(f"{BASE_URL}/api/applicants/APPL-SYN-005")
        assert status == 200
        data = comp_res.get("data", {})
        comp = data.get("cross_comparison", {})
        verdict = comp.get("overall_verdict")
        discrepancies = comp.get("discrepancies", [])
        assert verdict == "DISCREPANCY_FLAGGED" or len(discrepancies) > 0
        print(f"✓ Kabir Malhotra (APPL-SYN-005) DOB Mismatch Flagged: Verdict={verdict}, Discrepancies={len(discrepancies)} ({discrepancies[0] if discrepancies else ''})")
        results["passed"].append("DOB mismatch detection: Kabir Malhotra")
    except Exception as e:
        print(f"✗ Kabir Malhotra comparison check failed: {e}")
        results["failed"].append(("DOB mismatch Kabir Malhotra", str(e)))

    # 3d. Expired document cases: Dev Patel (expired Passport)
    try:
        expired_passport_path = FIXTURES_DIR / "07_dev_patel" / "dev_patel_passport_expired.pdf"
        status, upload_res = http_post_multipart(
            f"{BASE_URL}/api/documents/upload",
            expired_passport_path,
            {"applicant_id": "APPL-SYN-007"}
        )
        doc_id = upload_res["data"]["uploaded"][0]["id"]
        status, proc_res = http_post_json(f"{BASE_URL}/api/documents/{doc_id}/process")
        val = proc_res["data"]["result"]["validation"]
        assert val["overall_status"] == "invalid"
        expiry_check = next((c for c in val["checks"] if c["field"] == "expiry_date"), None)
        assert expiry_check is not None and expiry_check["status"] == "fail"
        print(f"✓ Dev Patel Expired Passport Flagged: status={val['overall_status']}, reason={expiry_check['message']}")
        results["passed"].append("Expired passport validation: Dev Patel")
    except Exception as e:
        print(f"✗ Expired passport test failed: {e}")
        results["failed"].append(("Expired passport test", str(e)))

    # 4. Profile Editing & Audit Review History
    log_section("4. Applicant Profile Editing & Document History")
    try:
        status, edit_res = http_put_json(
            f"{BASE_URL}/api/applicants/APPL-SYN-001",
            {"email": "aarav.mehta@verified-kyc.com", "risk_level": "low", "notes": "Primary KYC confirmed"}
        )
        assert status == 200
        updated = edit_res.get("data", {}).get("applicant", {})
        assert updated.get("email") == "aarav.mehta@verified-kyc.com"
        assert updated.get("notes") == "Primary KYC confirmed"
        print(f"✓ Applicant Profile Edit Succeeded: Name='{updated.get('name')}', Email='{updated.get('email')}', Risk='{updated.get('risk_level')}'")
        results["passed"].append("Applicant profile editing endpoint (PUT /api/applicants/<id>)")
    except Exception as e:
        print(f"✗ Profile editing failed: {e}")
        results["failed"].append(("Applicant profile editing", str(e)))

    try:
        sample_doc_id = uploaded_docs["passport"]["id"]
        status, hist_res = http_get(f"{BASE_URL}/api/documents/{sample_doc_id}/history")
        assert status == 200
        reviews = hist_res.get("data", {}).get("reviews", [])
        print(f"✓ Document History Endpoint OK: {len(reviews)} review entries retrieved for doc {sample_doc_id[:8]}")
        results["passed"].append("Document audit history endpoint (/api/documents/<id>/history)")
    except Exception as e:
        print(f"✗ Document history failed: {e}")
        results["failed"].append(("Document audit history", str(e)))

    # 5. Dashboard Statistics, Applicants, Verification Queue, Search
    log_section("5. Dashboard Statistics, Applicants, Queue & Search")
    
    # 5a. Dashboard Stats
    try:
        status, stats_res = http_get(f"{BASE_URL}/api/dashboard/stats")
        assert status == 200
        stats = stats_res.get("data", {})
        total_docs = stats.get("total_documents", 0)
        approved = stats.get("approved_count", 0)
        pending = stats.get("pending_review_count", 0)
        issues = stats.get("issues_count", 0)
        print(f"✓ Dashboard Stats:")
        print(f"   - Total Documents: {total_docs}")
        print(f"   - Approved: {approved}, Pending: {pending}, Issues: {issues}")
        print(f"   - Type Breakdown: {stats.get('type_breakdown')}")
        assert total_docs == approved + pending + issues, f"Equation mismatch: {total_docs} != {approved} + {pending} + {issues}"
        results["passed"].append("Dashboard statistics and reconciled formula")
    except Exception as e:
        print(f"✗ Dashboard stats verification failed: {e}")
        results["failed"].append(("Dashboard stats", str(e)))

    # 5b. Applicants list
    try:
        status, app_res = http_get(f"{BASE_URL}/api/applicants")
        assert status == 200
        applicants = app_res.get("data", {}).get("applicants", [])
        print(f"✓ Applicants List: {len(applicants)} applicants retrieved")
        assert len(applicants) >= 10
        results["passed"].append("Applicants list endpoint (/api/applicants)")
    except Exception as e:
        print(f"✗ Applicants list failed: {e}")
        results["failed"].append(("Applicants list", str(e)))

    # 5c. Verification Queue
    try:
        status, q_res = http_get(f"{BASE_URL}/api/documents/queue?status=pending")
        assert status == 200
        queue = q_res.get("data", {}).get("queue", [])
        print(f"✓ Verification Queue: {len(queue)} pending items in queue")
        results["passed"].append("Verification queue endpoint (/api/documents/queue)")
    except Exception as e:
        print(f"✗ Verification queue failed: {e}")
        results["failed"].append(("Verification queue", str(e)))

    # 5d. Global Search
    try:
        status, s_res = http_get(f"{BASE_URL}/api/search?q=Passport")
        assert status == 200
        doc_matches = s_res.get("data", {}).get("documents", [])
        print(f"✓ Global Search (query='Passport'): {len(doc_matches)} matching documents found")
        assert len(doc_matches) > 0, "Expected at least 1 document matching 'Passport'"
        results["passed"].append("Global search endpoint (/api/search)")
    except Exception as e:
        print(f"✗ Global search failed: {e}")
        results["failed"].append(("Global search", str(e)))

    # Print summary
    log_section("Live Verification Summary")
    print(f"Total Passed Checks: {len(results['passed'])}")
    print(f"Total Failed Checks: {len(results['failed'])}")
    for f_name, f_err in results["failed"]:
        print(f"  FAILED: {f_name} -> {f_err}")

if __name__ == "__main__":
    test_live_api()
