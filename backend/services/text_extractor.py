import os
import re
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


def find_text_bounding_box(
    search_text: str,
    spatial_tokens: List[Dict[str, Any]],
    page_number: Optional[int] = None
) -> Optional[List[int]]:
    """
    Search for a text snippet within spatial tokens and calculate the combined bounding box.
    Returns normalized [ymin, xmin, ymax, xmax] (0-1000 scale) or None if not found.
    """
    if not search_text or not spatial_tokens:
        return None

    cleaned_search = re.sub(r"\s+", " ", search_text.strip().lower())
    if not cleaned_search:
        return None

    tokens = [t for t in spatial_tokens if page_number is None or t.get("page") == page_number]
    if not tokens:
        tokens = spatial_tokens

    search_words = cleaned_search.split()
    n_words = len(search_words)

    # 1. Multi-word exact / contiguous token sequence match
    for i in range(len(tokens) - n_words + 1):
        window_tokens = tokens[i:i + n_words]
        window_str = " ".join(t.get("text", "").lower().strip(".,:;()[]{}") for t in window_tokens)
        if window_str == cleaned_search or cleaned_search in window_str:
            ymins = [t["bbox"][0] for t in window_tokens if "bbox" in t]
            xmins = [t["bbox"][1] for t in window_tokens if "bbox" in t]
            ymaxs = [t["bbox"][2] for t in window_tokens if "bbox" in t]
            xmaxs = [t["bbox"][3] for t in window_tokens if "bbox" in t]
            if ymins and xmins and ymaxs and xmaxs:
                return [min(ymins), min(xmins), max(ymaxs), max(xmaxs)]

    # 2. Substring matching in individual tokens
    for token in tokens:
        t_text = token.get("text", "").lower()
        if cleaned_search in t_text or (len(cleaned_search) > 3 and t_text in cleaned_search):
            return token.get("bbox")

    # 3. Partial overlap matching (if search_words has multiple words)
    if n_words > 1:
        matched_indices = []
        for word in search_words:
            if len(word) < 3:
                continue
            for idx, token in enumerate(tokens):
                if word in token.get("text", "").lower():
                    matched_indices.append(idx)
                    break
        if matched_indices:
            matched_tokens = [tokens[idx] for idx in matched_indices if "bbox" in tokens[idx]]
            if matched_tokens:
                ymins = [t["bbox"][0] for t in matched_tokens]
                xmins = [t["bbox"][1] for t in matched_tokens]
                ymaxs = [t["bbox"][2] for t in matched_tokens]
                xmaxs = [t["bbox"][3] for t in matched_tokens]
                return [min(ymins), min(xmins), max(ymaxs), max(xmaxs)]

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
        all_spatial_tokens: List[Dict[str, Any]] = []
        overall_methods_used = set()
        tesseract_ok, tesseract_msg = self.check_ocr_ready()

        for page_idx in range(len(doc)):
            page_num = page_idx + 1
            page = doc[page_idx]
            page_tokens: List[Dict[str, Any]] = []

            try:
                # 1. Direct digital text extraction via PyMuPDF
                digital_text = page.get_text("text").strip()
                char_count = len(digital_text)

                # Extract word tokens with normalized bounding boxes [ymin, xmin, ymax, xmax] (0-1000 scale)
                rect = page.rect
                pw = rect.width or 1.0
                ph = rect.height or 1.0
                try:
                    words = page.get_text("words")
                    for w in words:
                        w_text = str(w[4]).strip()
                        if not w_text:
                            continue
                        ymin = max(0, min(1000, int(round((w[1] / ph) * 1000))))
                        xmin = max(0, min(1000, int(round((w[0] / pw) * 1000))))
                        ymax = max(0, min(1000, int(round((w[3] / ph) * 1000))))
                        xmax = max(0, min(1000, int(round((w[2] / pw) * 1000))))
                        page_tokens.append({
                            "text": w_text,
                            "bbox": [ymin, xmin, ymax, xmax],
                            "page": page_num,
                            "confidence": 1.0
                        })
                except Exception as w_exc:
                    logger.debug(f"Could not extract digital words on page {page_num}: {w_exc}")

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
                            "character_count": char_count,
                            "spatial_tokens": page_tokens
                        })
                        all_spatial_tokens.extend(page_tokens)
                        overall_methods_used.add("digital_text" if char_count > 0 else "none")
                    else:
                        # Perform OCR on rendered page
                        ocr_text, ocr_tokens, ocr_err = self._ocr_pdf_page(page, page_num)
                        effective_tokens = ocr_tokens if ocr_tokens else page_tokens
                        if ocr_err:
                            pages_result.append({
                                "page_number": page_num,
                                "status": "error",
                                "method": "ocr_fallback",
                                "text": digital_text,  # Keep any sparse digital text
                                "error": ocr_err,
                                "character_count": len(digital_text),
                                "spatial_tokens": effective_tokens
                            })
                            all_spatial_tokens.extend(effective_tokens)
                            overall_methods_used.add("ocr_fallback")
                        else:
                            pages_result.append({
                                "page_number": page_num,
                                "status": "success",
                                "method": "ocr_fallback",
                                "text": ocr_text,
                                "error": None,
                                "character_count": len(ocr_text),
                                "spatial_tokens": effective_tokens
                            })
                            all_spatial_tokens.extend(effective_tokens)
                            overall_methods_used.add("ocr_fallback")
                else:
                    # Digital page (or sparse digital page without images)
                    pages_result.append({
                        "page_number": page_num,
                        "status": "success",
                        "method": "digital_text",
                        "text": digital_text,
                        "error": None,
                        "character_count": char_count,
                        "spatial_tokens": page_tokens
                    })
                    all_spatial_tokens.extend(page_tokens)
                    overall_methods_used.add("digital_text")

            except Exception as page_exc:
                # Isolate page error so remaining pages are processed
                pages_result.append({
                    "page_number": page_num,
                    "status": "error",
                    "method": "unknown",
                    "text": "",
                    "error": f"Error extracting page {page_num}: {str(page_exc)}",
                    "character_count": 0,
                    "spatial_tokens": []
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
            "character_count": len(full_text),
            "spatial_tokens": all_spatial_tokens
        }

    def _ocr_pdf_page(self, page: pymupdf.Page, page_num: int) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
        """Render a single PDF page at high DPI and run Tesseract OCR with spatial tokens."""
        try:
            pix = page.get_pixmap(dpi=self.ocr_dpi)
            img_bytes = pix.tobytes("png")
            cv_img = self.preprocessor.read_image_from_bytes(img_bytes)
            if cv_img is None:
                return "", [], f"Failed to decode rendered pixmap for page {page_num}"

            preprocessed, _ = self.preprocessor.preprocess_image(cv_img)
            text = pytesseract.image_to_string(preprocessed, config="--psm 3 -l eng").strip()

            tokens: List[Dict[str, Any]] = []
            try:
                ocr_data = pytesseract.image_to_data(preprocessed, output_type=pytesseract.Output.DICT)
                H, W = preprocessed.shape[:2]
                n_boxes = len(ocr_data.get("text", []))
                for i in range(n_boxes):
                    t_str = str(ocr_data["text"][i]).strip()
                    if not t_str:
                        continue
                    top = ocr_data["top"][i]
                    left = ocr_data["left"][i]
                    width = ocr_data["width"][i]
                    height = ocr_data["height"][i]
                    conf = float(ocr_data["conf"][i]) / 100.0 if ocr_data["conf"][i] != -1 else 0.5
                    ymin = max(0, min(1000, int(round((top / H) * 1000))))
                    xmin = max(0, min(1000, int(round((left / W) * 1000))))
                    ymax = max(0, min(1000, int(round(((top + height) / H) * 1000))))
                    xmax = max(0, min(1000, int(round(((left + width) / W) * 1000))))
                    tokens.append({
                        "text": t_str,
                        "bbox": [ymin, xmin, ymax, xmax],
                        "page": page_num,
                        "confidence": max(0.0, min(1.0, conf))
                    })
            except Exception as tok_err:
                logger.debug(f"Could not extract OCR data tokens for page {page_num}: {tok_err}")

            return text, tokens, None
        except Exception as e:
            return "", [], f"OCR failed on page {page_num}: {str(e)}"

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
        tokens: List[Dict[str, Any]] = []
        try:
            extracted_text = pytesseract.image_to_string(preprocessed, config="--psm 3 -l eng").strip()
            try:
                ocr_data = pytesseract.image_to_data(preprocessed, output_type=pytesseract.Output.DICT)
                H, W = preprocessed.shape[:2]
                n_boxes = len(ocr_data.get("text", []))
                for i in range(n_boxes):
                    t_str = str(ocr_data["text"][i]).strip()
                    if not t_str:
                        continue
                    top = ocr_data["top"][i]
                    left = ocr_data["left"][i]
                    width = ocr_data["width"][i]
                    height = ocr_data["height"][i]
                    conf = float(ocr_data["conf"][i]) / 100.0 if ocr_data["conf"][i] != -1 else 0.5
                    ymin = max(0, min(1000, int(round((top / H) * 1000))))
                    xmin = max(0, min(1000, int(round((left / W) * 1000))))
                    ymax = max(0, min(1000, int(round(((top + height) / H) * 1000))))
                    xmax = max(0, min(1000, int(round(((left + width) / W) * 1000))))
                    tokens.append({
                        "text": t_str,
                        "bbox": [ymin, xmin, ymax, xmax],
                        "page": 1,
                        "confidence": max(0.0, min(1.0, conf))
                    })
            except Exception as tok_err:
                logger.debug(f"Could not extract OCR data tokens for image: {tok_err}")
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
                    "character_count": 0,
                    "spatial_tokens": []
                }],
                "full_text": "",
                "character_count": 0,
                "spatial_tokens": []
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
                    "character_count": len(extracted_text),
                    "spatial_tokens": tokens
                }
            ],
            "full_text": extracted_text,
            "character_count": len(extracted_text),
            "spatial_tokens": tokens,
            "preprocessing_metadata": meta
        }

    def extract_spatial_tokens(self, file_path: Path | str, original_filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract word tokens with normalized bounding boxes [ymin, xmin, ymax, xmax] (0-1000 scale).
        Returns:
            {
                "spatial_tokens": [...],
                "total_tokens": int,
                "pages": [...],
                "status": str
            }
        """
        result = self.extract_from_file(file_path, original_filename=original_filename)
        tokens = result.get("spatial_tokens", [])
        return {
            "filename": result.get("filename"),
            "status": result.get("status"),
            "total_tokens": len(tokens),
            "spatial_tokens": tokens,
            "pages": result.get("pages", [])
        }

