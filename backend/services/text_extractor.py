import os
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import pymupdf  # PyMuPDF
import pytesseract
from PIL import Image

from backend.services.image_preprocessor import ImagePreprocessor

logger = logging.getLogger(__name__)

# Common Windows default installation directories for Tesseract OCR
DEFAULT_WINDOWS_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
]


def resolve_tesseract_cmd(configured_cmd: Optional[str] = None) -> Optional[str]:
    """
    Locate the Tesseract executable path.
    
    Checks in order:
    1. Explicitly configured path from config / environment
    2. System PATH via shutil.which('tesseract')
    3. Standard Windows install locations
    """
    if configured_cmd and os.path.isfile(configured_cmd):
        return configured_cmd

    which_path = shutil.which("tesseract")
    if which_path:
        return which_path

    for win_path in DEFAULT_WINDOWS_TESSERACT_PATHS:
        if os.path.isfile(win_path):
            return win_path

    return None


def is_tesseract_available(tesseract_cmd: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """
    Verify whether the native Tesseract engine is installed and operational.
    
    Returns:
        (is_available: bool, resolved_path_or_reason: str)
    """
    resolved = resolve_tesseract_cmd(tesseract_cmd)
    if not resolved:
        return False, "Tesseract OCR engine is not installed or not found in system PATH."

    try:
        pytesseract.pytesseract.tesseract_cmd = resolved
        version = pytesseract.get_tesseract_version()
        return True, f"Tesseract {version} available at {resolved}"
    except Exception as e:
        return False, f"Tesseract found at {resolved} but failed to execute: {str(e)}"


class TextExtractor:
    """
    Document Text Extraction Service.
    
    Coordinates:
    - Digital PDF page text extraction via PyMuPDF.
    - Configurable fallback detection for scanned PDF pages.
    - OpenCV image preprocessing followed by Tesseract OCR.
    - Page-level error isolation: a failure on one page does not discard other pages.
    """

    def __init__(
        self,
        tesseract_cmd: Optional[str] = None,
        enable_pdf_ocr_fallback: bool = True,
        min_digital_text_chars: int = 100,
        check_images_for_scan: bool = True,
        ocr_dpi: int = 300,
        preprocessor: Optional[ImagePreprocessor] = None
    ):
        self.tesseract_cmd = resolve_tesseract_cmd(tesseract_cmd)
        if self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

        self.enable_pdf_ocr_fallback = enable_pdf_ocr_fallback
        self.min_digital_text_chars = min_digital_text_chars
        self.check_images_for_scan = check_images_for_scan
        self.ocr_dpi = ocr_dpi
        self.preprocessor = preprocessor or ImagePreprocessor()

    def check_ocr_ready(self) -> Tuple[bool, Optional[str]]:
        """Check if Tesseract is currently configured and operational."""
        return is_tesseract_available(self.tesseract_cmd)

    def extract_from_file(self, file_path: Path | str, original_filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Unified extraction entry point dispatching based on file extension.
        
        Returns structured extraction payload.
        """
        target_path = Path(file_path)
        if not target_path.exists():
            return {
                "filename": original_filename or target_path.name,
                "extraction_method": "none",
                "status": "error",
                "error": f"File '{target_path.name}' does not exist on disk.",
                "pages": [],
                "full_text": "",
                "character_count": 0
            }

        ext = target_path.suffix.lower().lstrip(".")
        name = original_filename or target_path.name

        if ext == "pdf":
            return self.extract_pdf(target_path, original_filename=name)
        elif ext in ("jpg", "jpeg", "png"):
            return self.extract_image(target_path, original_filename=name)
        else:
            return {
                "filename": name,
                "extraction_method": "none",
                "status": "error",
                "error": f"Unsupported format '.{ext}' for text extraction.",
                "pages": [],
                "full_text": "",
                "character_count": 0
            }

    # -------------------------------------------------------------------------
    # PDF Extraction Pipeline
    # -------------------------------------------------------------------------
    def extract_pdf(self, pdf_path: Path | str, original_filename: str) -> Dict[str, Any]:
        """
        Extract text from a PDF document page-by-page.
        
        Uses PyMuPDF to read digital text. If a page has little/no text and
        meets scanned-page criteria, falls back to rendering + OCR.
        """
        try:
            doc = pymupdf.open(str(pdf_path))
        except Exception as e:
            return {
                "filename": original_filename,
                "extraction_method": "pymupdf_direct",
                "status": "error",
                "error": f"Failed to open PDF document: {str(e)}",
                "pages": [],
                "full_text": "",
                "character_count": 0
            }

        if len(doc) == 0:
            doc.close()
            return {
                "filename": original_filename,
                "extraction_method": "pymupdf_direct",
                "status": "error",
                "error": "PDF document contains 0 pages.",
                "pages": [],
                "full_text": "",
                "character_count": 0
            }

        pages_result: List[Dict[str, Any]] = []
        overall_methods_used = set()
        tesseract_ok, tesseract_msg = self.check_ocr_ready()

        for page_idx in range(len(doc)):
            page_num = page_idx + 1
            page = doc[page_idx]

            try:
                # 1. Direct digital text extraction via PyMuPDF
                digital_text = page.get_text("text").strip()
                char_count = len(digital_text)

                # 2. Configurable Scanned Page Detection
                # Criteria:
                # - Text length is below min_digital_text_chars threshold
                # - If check_images_for_scan is True: must also contain embedded images/drawings
                # Sparse pages with NO images (e.g. signature or cover) remain digital_text.
                is_scanned = False
                has_embedded_images = False

                if char_count < self.min_digital_text_chars:
                    if self.check_images_for_scan:
                        image_list = page.get_images()
                        has_embedded_images = bool(image_list)
                        is_scanned = has_embedded_images
                    else:
                        is_scanned = True

                # 3. Handle Scanned vs Digital
                if is_scanned and self.enable_pdf_ocr_fallback:
                    if not tesseract_ok:
                        # Tesseract is uninstalled, cannot perform OCR fallback
                        error_detail = "Page contains scanned image, but Tesseract OCR engine is not installed."
                        pages_result.append({
                            "page_number": page_num,
                            "status": "error" if char_count == 0 else "partial",
                            "method": "digital_text" if char_count > 0 else "ocr_fallback",
                            "text": digital_text,
                            "error": error_detail,
                            "character_count": char_count
                        })
                        overall_methods_used.add("digital_text" if char_count > 0 else "none")
                    else:
                        # Perform OCR on rendered page
                        ocr_text, ocr_err = self._ocr_pdf_page(page, page_num)
                        if ocr_err:
                            pages_result.append({
                                "page_number": page_num,
                                "status": "error",
                                "method": "ocr_fallback",
                                "text": digital_text,  # Keep any sparse digital text
                                "error": ocr_err,
                                "character_count": len(digital_text)
                            })
                            overall_methods_used.add("ocr_fallback")
                        else:
                            pages_result.append({
                                "page_number": page_num,
                                "status": "success",
                                "method": "ocr_fallback",
                                "text": ocr_text,
                                "error": None,
                                "character_count": len(ocr_text)
                            })
                            overall_methods_used.add("ocr_fallback")
                else:
                    # Digital page (or sparse digital page without images)
                    pages_result.append({
                        "page_number": page_num,
                        "status": "success",
                        "method": "digital_text",
                        "text": digital_text,
                        "error": None,
                        "character_count": char_count
                    })
                    overall_methods_used.add("digital_text")

            except Exception as page_exc:
                # Isolate page error so remaining pages are processed
                pages_result.append({
                    "page_number": page_num,
                    "status": "error",
                    "method": "unknown",
                    "text": "",
                    "error": f"Error extracting page {page_num}: {str(page_exc)}",
                    "character_count": 0
                })

        doc.close()

        # Aggregate full text from pages that have text
        successful_texts = [p["text"] for p in pages_result if p.get("text")]
        full_text = "\n\n".join(successful_texts).strip()

        # Determine overall document status
        statuses = [p["status"] for p in pages_result]
        if all(s == "success" for s in statuses):
            doc_status = "success"
        elif any(s in ("success", "partial") for s in statuses):
            doc_status = "partial"
        else:
            doc_status = "error"

        primary_method = "hybrid" if len(overall_methods_used) > 1 else (
            next(iter(overall_methods_used)) if overall_methods_used else "pymupdf_direct"
        )

        return {
            "filename": original_filename,
            "extraction_method": primary_method,
            "status": doc_status,
            "total_pages": len(pages_result),
            "pages": pages_result,
            "full_text": full_text,
            "character_count": len(full_text)
        }

    def _ocr_pdf_page(self, page: pymupdf.Page, page_num: int) -> Tuple[str, Optional[str]]:
        """Render a single PDF page at high DPI and run Tesseract OCR."""
        try:
            pix = page.get_pixmap(dpi=self.ocr_dpi)
            img_bytes = pix.tobytes("png")
            cv_img = self.preprocessor.read_image_from_bytes(img_bytes)
            if cv_img is None:
                return "", f"Failed to decode rendered pixmap for page {page_num}"

            preprocessed, _ = self.preprocessor.preprocess_image(cv_img)
            text = pytesseract.image_to_string(preprocessed, config="--psm 3 -l eng").strip()
            return text, None
        except Exception as e:
            return "", f"OCR failed on page {page_num}: {str(e)}"

    # -------------------------------------------------------------------------
    # Image OCR Pipeline
    # -------------------------------------------------------------------------
    def extract_image(self, image_path: Path | str, original_filename: str) -> Dict[str, Any]:
        """
        Extract text from an image (JPG, JPEG, PNG) using OpenCV + Tesseract OCR.
        
        Handles missing native Tesseract installations gracefully without crashing.
        """
        tesseract_ok, tesseract_msg = self.check_ocr_ready()
        if not tesseract_ok:
            return {
                "filename": original_filename,
                "extraction_method": "tesseract_ocr",
                "status": "error",
                "error": tesseract_msg,
                "pages": [{
                    "page_number": 1,
                    "status": "error",
                    "method": "tesseract_ocr",
                    "text": "",
                    "error": tesseract_msg,
                    "character_count": 0
                }],
                "full_text": "",
                "character_count": 0
            }

        # 1. Load image using robust unicode-safe reader
        cv_img = self.preprocessor.read_image_from_path(image_path)
        if cv_img is None:
            return {
                "filename": original_filename,
                "extraction_method": "tesseract_ocr",
                "status": "error",
                "error": f"Failed to load image '{original_filename}'. File may be corrupt or unreadable.",
                "pages": [],
                "full_text": "",
                "character_count": 0
            }

        # 2. Preprocess with OpenCV
        try:
            preprocessed, meta = self.preprocessor.preprocess_image(cv_img)
        except Exception as e:
            return {
                "filename": original_filename,
                "extraction_method": "tesseract_ocr",
                "status": "error",
                "error": f"Image preprocessing failed: {str(e)}",
                "pages": [],
                "full_text": "",
                "character_count": 0
            }

        # 3. Perform Tesseract OCR
        try:
            extracted_text = pytesseract.image_to_string(preprocessed, config="--psm 3 -l eng").strip()
        except Exception as e:
            return {
                "filename": original_filename,
                "extraction_method": "tesseract_ocr",
                "status": "error",
                "error": f"Tesseract execution error: {str(e)}",
                "pages": [{
                    "page_number": 1,
                    "status": "error",
                    "method": "tesseract_ocr",
                    "text": "",
                    "error": str(e),
                    "character_count": 0
                }],
                "full_text": "",
                "character_count": 0
            }

        return {
            "filename": original_filename,
            "extraction_method": "tesseract_ocr",
            "status": "success",
            "total_pages": 1,
            "pages": [
                {
                    "page_number": 1,
                    "status": "success",
                    "method": "tesseract_ocr",
                    "text": extracted_text,
                    "error": None,
                    "character_count": len(extracted_text)
                }
            ],
            "full_text": extracted_text,
            "character_count": len(extracted_text),
            "preprocessing_metadata": meta
        }
