import io
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest
import pymupdf
from PIL import Image

from backend.services.image_preprocessor import ImagePreprocessor
from backend.services.text_extractor import TextExtractor, is_tesseract_available
from backend.database.db import get_document


def create_synthetic_digital_pdf(pages_text: list[str]) -> bytes:
    """Generate a multi-page digital PDF in memory using PyMuPDF."""
    doc = pymupdf.open()
    for text in pages_text:
        page = doc.new_page()
        page.insert_text((50, 72), text, fontsize=12)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_synthetic_image_pdf(text_on_image: str = "SYNTHETIC SCANNED KYC") -> bytes:
    """Generate a PDF containing a rendered bitmap image (simulating a scanned document)."""
    # Create PIL image
    img = Image.new("RGB", (400, 200), color=(255, 255, 255))
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="PNG")
    img_bytes = img_byte_arr.getvalue()

    doc = pymupdf.open()
    page = doc.new_page(width=400, height=200)
    rect = pymupdf.Rect(0, 0, 400, 200)
    page.insert_image(rect, stream=img_bytes)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# =============================================================================
# 1. Image Preprocessing Tests (OpenCV)
# =============================================================================
def test_image_preprocessor_grayscale_and_thresholding(tmp_path):
    """Verify that OpenCV converts color images to grayscale and performs Otsu binarization."""
    preprocessor = ImagePreprocessor(processed_folder=tmp_path)

    # Synthetic BGR color image (100x100)
    color_img = np.zeros((100, 100, 3), dtype=np.uint8)
    color_img[20:80, 20:80] = [200, 200, 200]  # Light box

    processed, meta = preprocessor.preprocess_image(color_img, target_min_dim=300)

    # Should be 1-channel grayscale
    assert len(processed.shape) == 2
    # Should be scaled to at least target_min_dim
    assert min(processed.shape) >= 300
    assert "bgr_to_grayscale" in meta["pipeline_actions"]
    assert "otsu_binarization" in meta["pipeline_actions"]

    # Verify saving to disk
    saved_path = preprocessor.save_processed_image(processed, "test_out.png")
    assert saved_path is not None
    assert saved_path.exists()


# =============================================================================
# 2. Digital PDF Text Extraction Tests (PyMuPDF)
# =============================================================================
def test_digital_pdf_multipage_extraction(tmp_path):
    """Verify multi-page digital PDF extracts each page cleanly with page numbers."""
    pdf_bytes = create_synthetic_digital_pdf([
        "Page 1: Government Identity Proof\nName: Test Applicant",
        "Page 2: Housing Loan Application Details\nProperty: Flat 402"
    ])
    pdf_path = tmp_path / "digital_sample.pdf"
    pdf_path.write_bytes(pdf_bytes)

    extractor = TextExtractor(enable_pdf_ocr_fallback=False)
    result = extractor.extract_pdf(pdf_path, original_filename="digital_sample.pdf")

    assert result["status"] == "success"
    assert result["extraction_method"] == "digital_text"
    assert result["total_pages"] == 2
    assert len(result["pages"]) == 2

    assert result["pages"][0]["page_number"] == 1
    assert "Government Identity Proof" in result["pages"][0]["text"]
    assert result["pages"][0]["method"] == "digital_text"

    assert result["pages"][1]["page_number"] == 2
    assert "Housing Loan Application Details" in result["pages"][1]["text"]

    assert "Government Identity Proof" in result["full_text"]
    assert "Housing Loan Application Details" in result["full_text"]


def test_sparse_digital_pdf_not_falsely_scanned(tmp_path):
    """
    Ensure sparse digital pages (few characters, e.g. cover/signature) with NO images
    are NOT falsely marked as scanned.
    """
    pdf_bytes = create_synthetic_digital_pdf(["Sign"])  # Only 4 characters
    pdf_path = tmp_path / "sparse.pdf"
    pdf_path.write_bytes(pdf_bytes)

    extractor = TextExtractor(
        min_digital_text_chars=15,
        check_images_for_scan=True  # Checks whether page has embedded images
    )
    result = extractor.extract_pdf(pdf_path, original_filename="sparse.pdf")

    assert result["status"] == "success"
    assert result["pages"][0]["method"] == "digital_text"
    assert result["pages"][0]["text"] == "Sign"


# =============================================================================
# 3. Scanned PDF Fallback Detection & Isolation Tests
# =============================================================================
def test_scanned_pdf_fallback_with_mocked_tesseract(tmp_path):
    """
    [MOCK TEST] Test scanned PDF page fallback when Tesseract OCR is available.
    Mocks pytesseract to verify that the high-DPI rendering and OCR pipeline triggers.
    """
    pdf_bytes = create_synthetic_image_pdf("MOCK OCR TEXT")
    pdf_path = tmp_path / "scanned.pdf"
    pdf_path.write_bytes(pdf_bytes)

    extractor = TextExtractor(
        enable_pdf_ocr_fallback=True,
        min_digital_text_chars=10,
        check_images_for_scan=True
    )

    with patch.object(extractor, "check_ocr_ready", return_value=(True, "Mock Tesseract")), \
         patch("pytesseract.image_to_string", return_value="MOCK OCR TEXT EXTRACTED"):
        result = extractor.extract_pdf(pdf_path, original_filename="scanned.pdf")

    assert result["status"] == "success"
    assert result["pages"][0]["method"] == "ocr_fallback"
    assert result["pages"][0]["text"] == "MOCK OCR TEXT EXTRACTED"


def test_page_level_error_isolation(tmp_path):
    """
    Ensure if an extraction error happens on Page 2, Page 1 text is preserved
    and overall status is 'partial'.
    """
    pdf_bytes = create_synthetic_digital_pdf(["Valid Page 1 Text", "Page 2 Text"])
    pdf_path = tmp_path / "two_pages.pdf"
    pdf_path.write_bytes(pdf_bytes)

    extractor = TextExtractor()

    # Mock page 2 extraction to throw an error
    original_get_text = pymupdf.Page.get_text
    def flaky_get_text(self, *args, **kwargs):
        if self.number == 1:  # 0-indexed page 2
            raise RuntimeError("Corrupted page stream")
        return original_get_text(self, *args, **kwargs)

    with patch.object(pymupdf.Page, "get_text", flaky_get_text):
        result = extractor.extract_pdf(pdf_path, original_filename="two_pages.pdf")

    assert result["status"] == "partial"
    assert result["pages"][0]["status"] == "success"
    assert "Valid Page 1 Text" in result["pages"][0]["text"]
    assert result["pages"][1]["status"] == "error"
    assert "Corrupted page stream" in result["pages"][1]["error"]
    assert "Valid Page 1 Text" in result["full_text"]


# =============================================================================
# 4. Graceful Handling of Missing Tesseract
# =============================================================================
def test_missing_tesseract_returns_structured_error_on_image(tmp_path):
    """
    Verify that if native Tesseract is not installed, image extraction fails
    gracefully without crashing the server, returning a clear informative message.
    """
    img_path = tmp_path / "test_pan.jpg"
    # Create simple JPG
    img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    img.save(img_path, format="JPEG")

    extractor = TextExtractor()
    with patch.object(extractor, "check_ocr_ready", return_value=(False, "Tesseract OCR engine is not installed or not found in system PATH.")):
        result = extractor.extract_image(img_path, original_filename="test_pan.jpg")

    assert result["status"] == "error"
    assert "not installed" in result["error"]
    assert result["full_text"] == ""


def test_missing_tesseract_does_not_break_digital_pdf(tmp_path):
    """
    Verify that digital PDFs extract perfectly even when Tesseract is completely missing.
    """
    pdf_bytes = create_synthetic_digital_pdf(["Digital KYC Document Page"])
    pdf_path = tmp_path / "digital_doc.pdf"
    pdf_path.write_bytes(pdf_bytes)

    extractor = TextExtractor()
    with patch.object(extractor, "check_ocr_ready", return_value=(False, "Tesseract not found")):
        result = extractor.extract_pdf(pdf_path, original_filename="digital_doc.pdf")

    assert result["status"] == "success"
    assert "Digital KYC Document Page" in result["full_text"]


# =============================================================================
# 5. Full API Endpoints Integration (Extract & Text endpoints)
# =============================================================================
def test_api_extract_and_get_text_endpoint(client, app):
    """
    Full end-to-end test through Flask API:
    1. Upload digital PDF
    2. POST /api/documents/<id>/extract
    3. GET /api/documents/<id>/text
    """
    pdf_bytes = create_synthetic_digital_pdf(["Applicant PAN Card\nName: John Doe\nITD Govt"])
    upload_res = client.post(
        "/api/documents/upload",
        data={"files": (io.BytesIO(pdf_bytes), "sample_kyc.pdf")},
        content_type="multipart/form-data"
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.get_json()["uploaded"][0]["id"]

    # 1. Trigger extraction
    extract_res = client.post(f"/api/documents/{doc_id}/extract")
    assert extract_res.status_code == 200
    extract_data = extract_res.get_json()
    assert extract_data["success"] is True
    extraction = extract_data["data"]["extraction"]
    assert extraction["status"] == "success"
    assert "Applicant PAN Card" in extraction["full_text"]

    # 2. Verify database was updated
    db_record = get_document(doc_id, db_path=app.config["DATABASE_PATH"])
    assert db_record["processing_status"] == "completed"
    assert "Applicant PAN Card" in db_record["extracted_text"]

    # 3. Retrieve text via GET endpoint
    text_res = client.get(f"/api/documents/{doc_id}/text")
    assert text_res.status_code == 200
    text_data = text_res.get_json()["data"]
    assert text_data["processing_status"] == "completed"
    assert "Applicant PAN Card" in text_data["extracted_text"]


def test_api_extract_nonexistent_document(client):
    """POST /api/documents/<id>/extract with unknown ID returns 404."""
    res = client.post("/api/documents/unknown-uuid-0000/extract")
    assert res.status_code == 404
    assert res.get_json()["success"] is False


def test_api_ocr_status_endpoint(client):
    """GET /api/documents/ocr-status returns host OCR availability."""
    res = client.get("/api/documents/ocr-status")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "tesseract_available" in data["data"]
