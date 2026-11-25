import urllib.request
import json
import uuid
import pymupdf

BASE_URL = "http://127.0.0.1:5000"


def run_mvp_e2e_verification():
    print("=" * 60)
    print(">>> VERIDOC AI MVP END-TO-END VERIFICATION <<<")
    print("=" * 60)

    applicant_id = f"APP-TEST-{uuid.uuid4().hex[:6].upper()}"
    applicant_name = "Priya Sharma"

    # 1. Create Applicant
    print(f"\n1. Registering Applicant: {applicant_name} ({applicant_id})")
    create_req = urllib.request.Request(
        f"{BASE_URL}/api/applicants",
        data=json.dumps({"id": applicant_id, "name": applicant_name, "email": "priya.sharma@example.com"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(create_req) as resp:
        app_res = json.loads(resp.read().decode())
        print(f"   Registered successfully: HTTP {resp.status}, ID: {app_res['data']['applicant']['id']}")

    # 2. Generate Synthetic Document 1: PAN Card
    doc1 = pymupdf.open()
    p1 = doc1.new_page()
    p1.insert_text(
        (50, 70),
        "INCOME TAX DEPARTMENT\nGOVT. OF INDIA\nPERMANENT ACCOUNT NUMBER: ABCDE1234F\nPRIYA SHARMA\nRAMESH SHARMA\nDOB: 14/05/1990\nSIGNATURE",
        fontsize=12
    )
    pan_bytes = doc1.tobytes()
    doc1.close()

    # 3. Generate Synthetic Document 2: Aadhaar Card
    doc2 = pymupdf.open()
    p2 = doc2.new_page()
    p2.insert_text(
        (50, 70),
        "Government of India\nUnique Identification Authority of India\nPRIYA SHARMA\nDOB: 14/05/1990\nFEMALE\n9876 5432 1098\nVID: 1029 3847 5610 2938\nMera Aadhaar, Meri Pehchan",
        fontsize=12
    )
    aadhaar_bytes = doc2.tobytes()
    doc2.close()

    # 4. Upload Documents
    def upload_file(filename, file_bytes):
        boundary = "----WebKitFormBoundary" + uuid.uuid4().hex
        body = bytearray()
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(b'Content-Disposition: form-data; name="applicant_id"\r\n\r\n')
        body.extend(applicant_id.encode())
        body.extend(b"\r\n")

        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'.encode())
        body.extend(b"Content-Type: application/pdf\r\n\r\n")
        body.extend(file_bytes)
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode())

        req = urllib.request.Request(
            f"{BASE_URL}/api/documents/upload",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST"
        )
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode())

    print("\n2. Uploading Synthetic Documents...")
    res1 = upload_file("applicant_pan.pdf", pan_bytes)
    pan_doc_id = res1["uploaded"][0]["id"]
    print(f"   Uploaded PAN: doc_id={pan_doc_id}")

    res2 = upload_file("applicant_aadhaar.pdf", aadhaar_bytes)
    aadhaar_doc_id = res2["uploaded"][0]["id"]
    print(f"   Uploaded Aadhaar: doc_id={aadhaar_doc_id}")

    # 5. Process Document 1: PAN Pipeline
    print("\n3. Processing PAN Document Intelligence Pipeline...")
    proc_req1 = urllib.request.Request(f"{BASE_URL}/api/documents/{pan_doc_id}/process", data=b"", method="POST")
    with urllib.request.urlopen(proc_req1) as resp:
        pan_proc = json.loads(resp.read().decode())["data"]["result"]
        print(f"   Classification: {pan_proc['classification']['classified_type']} (Confidence: {pan_proc['classification']['confidence']})")
        print(f"   Extracted PAN: {pan_proc['extracted_fields']['id_number']}")
        print(f"   Extracted Name: {pan_proc['extracted_fields']['name']}")
        print(f"   Validation Status: {pan_proc['validation']['overall_status']}")
        assert pan_proc["classification"]["classified_type"] == "pan"
        assert pan_proc["extracted_fields"]["id_number"] == "ABCDE1234F"
        assert pan_proc["validation"]["is_valid"] is True

    # 6. Process Document 2: Aadhaar Pipeline
    print("\n4. Processing Aadhaar Document Intelligence Pipeline...")
    proc_req2 = urllib.request.Request(f"{BASE_URL}/api/documents/{aadhaar_doc_id}/process", data=b"", method="POST")
    with urllib.request.urlopen(proc_req2) as resp:
        aadhaar_proc = json.loads(resp.read().decode())["data"]["result"]
        print(f"   Classification: {aadhaar_proc['classification']['classified_type']} (Confidence: {aadhaar_proc['classification']['confidence']})")
        print(f"   Extracted Masked Aadhaar: {aadhaar_proc['extracted_fields']['id_number']}")
        print(f"   Validation Status: {aadhaar_proc['validation']['overall_status']}")
        assert aadhaar_proc["classification"]["classified_type"] == "aadhaar"
        assert aadhaar_proc["extracted_fields"]["id_number"] == "XXXX-XXXX-1098"
        assert "987654321098" not in aadhaar_proc["extracted_fields"]["id_number"]

        # Cross Comparison Check
        cross = aadhaar_proc.get("cross_comparison")
        assert cross is not None
        print(f"\n5. Cross-Document Comparison Result:")
        print(f"   Verdict: {cross['overall_verdict']}")
        print(f"   Consistency Score: {cross['consistency_score']}%")
        print(f"   Total Documents Compared: {cross['total_documents_compared']}")
        assert cross["overall_verdict"] == "VERIFIED"
        assert cross["consistency_score"] >= 90.0

    # 7. Test Human Review Workflow
    print("\n6. Submitting Officer Verification Review...")
    rev_payload = {
        "decision": "approved",
        "officer_name": "Arjun Mehta (Senior Officer)",
        "notes": "All identity checks passed. Name & DOB consistent across PAN and Aadhaar.",
        "edited_fields": {
            "name": "Priya Sharma"
        }
    }
    rev_req = urllib.request.Request(
        f"{BASE_URL}/api/documents/{pan_doc_id}/review",
        data=json.dumps(rev_payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(rev_req) as resp:
        rev_res = json.loads(resp.read().decode())["data"]["review"]
        print(f"   Review Decision: {rev_res['review_status']}")
        print(f"   Reviewed By: {rev_res['reviewed_by']}")
        assert rev_res["review_status"] == "approved"

    # 8. Check Dashboard Stats
    print("\n7. Verifying Dashboard Metrics Update...")
    stats_req = urllib.request.Request(f"{BASE_URL}/api/dashboard/stats")
    with urllib.request.urlopen(stats_req) as resp:
        stats = json.loads(resp.read().decode())["data"]
        print(f"   Total Documents in System: {stats['total_documents']}")
        print(f"   Processed Documents: {stats['processed_count']}")
        print(f"   Total Registered Applicants: {stats['total_applicants']}")
        print(f"   Breakdown: {stats['type_breakdown']}")

    print("\n>>> SUCCESS: ALL END-TO-END VERIFICATION CHECKS COMPLETED WITH ZERO ERRORS! <<<")


if __name__ == "__main__":
    run_mvp_e2e_verification()
