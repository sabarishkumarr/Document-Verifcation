import os
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import cv2
import numpy as np


class ImagePreprocessor:
    """
    OpenCV-based image preprocessing pipeline designed specifically for OCR intake.
    
    Operations:
    1. Safe file loading (handles Windows Unicode paths and memory streams).
    2. Conversion to grayscale.
    3. Resolution scaling for low-DPI / small images (preserves aspect ratio).
    4. Gentle noise reduction.
    5. Adaptive/Otsu binarization to enhance text legibility against complex backgrounds.
    """

    def __init__(self, processed_folder: Optional[Path | str] = None):
        self.processed_folder = Path(processed_folder) if processed_folder else None
        if self.processed_folder:
            self.processed_folder.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def read_image_from_path(image_path: Path | str) -> Optional[np.ndarray]:
        """
        Safely read an image from disk.
        
        Uses np.fromfile + cv2.imdecode to prevent issues with Unicode/spaces in Windows paths.
        """
        path_str = str(image_path)
        if not os.path.exists(path_str):
            return None
        
        try:
            with open(path_str, "rb") as f:
                data = bytearray(f.read())
            if not data:
                return None
            nparr = np.asarray(data, dtype=np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            return img
        except Exception:
            return None

    @staticmethod
    def read_image_from_bytes(image_bytes: bytes) -> Optional[np.ndarray]:
        """Decode raw image bytes directly into an OpenCV BGR array."""
        if not image_bytes:
            return None
        try:
            nparr = np.asarray(bytearray(image_bytes), dtype=np.uint8)
            return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except Exception:
            return None

    def preprocess_image(
        self,
        img: np.ndarray,
        target_min_dim: int = 1200,
        apply_threshold: bool = True
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Apply non-destructive preprocessing filters to optimize OCR accuracy.
        
        Returns:
            (preprocessed_image: np.ndarray, metadata: Dict[str, Any])
        """
        if img is None:
            raise ValueError("Input image array is None")

        orig_h, orig_w = img.shape[:2]
        channels = 1 if len(img.shape) == 2 else img.shape[2]
        actions_taken = []

        # 1. Grayscale Conversion
        if channels == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            actions_taken.append("bgr_to_grayscale")
        elif channels == 4:
            gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
            actions_taken.append("bgra_to_grayscale")
        else:
            gray = img.copy()

        # 2. Rescaling for small / low-resolution images
        # OCR performs best around 300 DPI, requiring sufficient stroke width for characters.
        current_min = min(orig_h, orig_w)
        if current_min < target_min_dim and current_min > 0:
            scale = target_min_dim / float(current_min)
            # Bound scale to avoid extreme memory allocation
            scale = min(scale, 3.0)
            new_w = int(orig_w * scale)
            new_h = int(orig_h * scale)
            gray = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
            actions_taken.append(f"rescaled_{orig_w}x{orig_h}_to_{new_w}x{new_h}")
        else:
            new_w, new_h = orig_w, orig_h

        # 3. Denoising: gentle Gaussian blur to eliminate camera grain without blurring text strokes
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        actions_taken.append("gaussian_blur_3x3")

        # 4. Contrast & Thresholding
        if apply_threshold:
            # Otsu automatically calculates optimal global threshold between foreground text and background
            _, thresholded = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            final_img = thresholded
            actions_taken.append("otsu_binarization")
        else:
            final_img = blurred

        metadata = {
            "original_dimensions": {"width": orig_w, "height": orig_h, "channels": channels},
            "processed_dimensions": {"width": new_w, "height": new_h},
            "pipeline_actions": actions_taken
        }

        return final_img, metadata

    def save_processed_image(self, img: np.ndarray, output_filename: str) -> Optional[Path]:
        """Save a preprocessed OpenCV image array to storage/processed/."""
        if self.processed_folder is None:
            return None
        out_path = self.processed_folder / output_filename
        success, encoded = cv2.imencode(".png", img)
        if success:
            with open(out_path, "wb") as f:
                f.write(encoded.tobytes())
            return out_path
        return None
