import urllib.request
import json
import uuid

BASE_URL = "http://127.0.0.1:5000"


def test_health():
    print("\n--- 1. Testing GET /api/health ---")
    req = urllib.request.Request(f"{BASE_URL}/api/health")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        print(f"Status: {resp.status}")
        print(f"Response: {data}")
        assert resp.status == 200
        assert data["success"] is True
        assert data["message"] == "Document Verification API is running"


def upload_multipart(filename, content, content_type="application/octet-stream", applicant_id="APPL-INT-001"):
    boundary = "----WebKitFormBoundary" + uuid.uuid4().hex
    body = bytearray()
    
    # Add applicant_id field
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="applicant_id"\r\n\r\n')
    body.extend(applicant_id.encode())
    body.extend(b"\r\n")

    # Add file field
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'.encode())
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
    body.extend(content)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        f"{BASE_URL}/api/documents/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def test_uploads():
    print("\n--- 2. Testing Valid PDF Upload ---")
    pdf_bytes = b"%PDF-1.4 synthetic housing finance kyc doc\n%%EOF"
    status, res = upload_multipart("applicant_pan.pdf", pdf_bytes, "application/pdf")
    print(f"Status: {status}, Success: {res['success']}")
    assert status == 201
    assert len(res["uploaded"]) == 1
    doc_id = res["uploaded"][0]["id"]
    stored_name = res["uploaded"][0]["stored_filename"]
    print(f"  Generated Document ID: {doc_id}")
    print(f"  Stored Filename: {stored_name}")
    print(f"  File Hash: {res['uploaded'][0]['file_hash']}")

    print("\n--- 3. Testing Valid JPEG Upload ---")
    jpg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xd9"
    status, res = upload_multipart("applicant_aadhaar.jpg", jpg_bytes, "image/jpeg")
    print(f"Status: {status}, Success: {res['success']}")
    assert status == 201
    assert len(res["uploaded"]) == 1

    print("\n--- 4. Testing Unsupported File Type (.txt) ---")
    txt_bytes = b"Some random unpermitted text"
    status, res = upload_multipart("notes.txt", txt_bytes, "text/plain")
    print(f"Status: {status}, Success: {res['success']}")
    print(f"  Errors: {res['errors']}")
    assert status == 400
    assert res["success"] is False

    print("\n--- 5. Testing Empty File Upload (0 bytes) ---")
    status, res = upload_multipart("empty_voter_id.png", b"", "image/png")
    print(f"Status: {status}, Success: {res['success']}")
    print(f"  Errors: {res['errors']}")
    assert status == 400
    assert res["success"] is False

    print("\n--- 6. Testing Document Retrieval by ID ---")
    req = urllib.request.Request(f"{BASE_URL}/api/documents/{doc_id}")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        print(f"Status: {resp.status}, Success: {data['success']}")
        doc = data["data"]["document"]
        print(f"  Retrieved Record ID: {doc['id']}")
        print(f"  Original Filename: {doc['original_filename']}")
        print(f"  Stored Filename: {doc['stored_filename']}")
        print(f"  Processing Status: {doc['processing_status']}")
        print(f"  Review Status: {doc['review_status']}")
        assert doc["id"] == doc_id
        assert doc["original_filename"] == "applicant_pan.pdf"

    print("\n--- 7. Testing Document Listing ---")
    req = urllib.request.Request(f"{BASE_URL}/api/documents")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        docs = data["data"]["documents"]
        print(f"Status: {resp.status}, Retrieved {len(docs)} documents from database.")
        assert len(docs) >= 2

    print("\n>>> ALL LIVE API VERIFICATION CHECKS PASSED SUCCESSFULLY! <<<")


if __name__ == "__main__":
    test_health()
    test_uploads()
