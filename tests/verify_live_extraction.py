import urllib.request
import json
import uuid
import pymupdf

BASE_URL = "http://127.0.0.1:5000"


def run_live_extraction_verification():
    print("=== LIVE EXTRACTION PIPELINE VERIFICATION ===")

    # 1. Generate synthetic multi-page PDF with digital text
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((50, 70), "INCOME TAX DEPARTMENT\nGOVT OF INDIA\nPAN CARD SAMPLE", fontsize=12)
    p2 = doc.new_page()
    p2.insert_text((50, 70), "APPLICANT KYC VERIFICATION\nSTATUS: ACTIVE", fontsize=12)
    pdf_bytes = doc.tobytes()
    doc.close()

    # 2. Upload to POST /api/documents/upload
    boundary = "----WebKitFormBoundary" + uuid.uuid4().hex
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="files"; filename="synthetic_pan.pdf"\r\n')
    body.extend(b'Content-Type: application/pdf\r\n\r\n')
    body.extend(pdf_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        f"{BASE_URL}/api/documents/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        upload_res = json.loads(resp.read().decode())
        doc_id = upload_res["uploaded"][0]["id"]
        print(f"1. Uploaded Document ID: {doc_id} (Status: {resp.status})")

    # 3. Trigger extraction via POST /api/documents/<id>/extract
    extract_req = urllib.request.Request(
        f"{BASE_URL}/api/documents/{doc_id}/extract",
        data=b"",
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(extract_req) as resp:
        extract_res = json.loads(resp.read().decode())
        print(f"2. Triggered Extraction: HTTP {resp.status}")
        extraction = extract_res["data"]["extraction"]
        print(f"   Extraction Method: {extraction['extraction_method']}")
        print(f"   Extraction Status: {extraction['status']}")
        print(f"   Total Pages: {extraction['total_pages']}")
        for p in extraction["pages"]:
            print(f"   Page {p['page_number']}: method={p['method']}, chars={p['character_count']}")

    # 4. Fetch extracted text via GET /api/documents/<id>/text
    text_req = urllib.request.Request(f"{BASE_URL}/api/documents/{doc_id}/text")
    with urllib.request.urlopen(text_req) as resp:
        text_res = json.loads(resp.read().decode())
        data = text_res["data"]
        print(f"3. Retrieved Extracted Text: HTTP {resp.status}")
        print(f"   DB Processing Status: {data['processing_status']}")
        print(f"   Character Count: {len(data['extracted_text'])}")
        assert "INCOME TAX DEPARTMENT" in data["extracted_text"]
        assert "APPLICANT KYC VERIFICATION" in data["extracted_text"]

    # 5. Check OCR Status endpoint
    ocr_req = urllib.request.Request(f"{BASE_URL}/api/documents/ocr-status")
    with urllib.request.urlopen(ocr_req) as resp:
        ocr_res = json.loads(resp.read().decode())
        print(f"4. Host OCR Availability: {ocr_res['data']['tesseract_available']}")
        print(f"   Details: {ocr_res['data']['details']}")

    print("\n>>> ALL LIVE EXTRACTION VERIFICATIONS SUCCEEDED! <<<")


if __name__ == "__main__":
    run_live_extraction_verification()
