# Services module
from .file_validator import validate_file, is_allowed_extension, get_file_extension
from .document_processor import DocumentProcessor
from .image_preprocessor import ImagePreprocessor
from .text_extractor import TextExtractor, is_tesseract_available, resolve_tesseract_cmd
from .classifier import DocumentClassifier
from .field_extractor import FieldExtractor
from .validator import DocumentValidator
from .comparator import CrossDocumentComparator

__all__ = [
    "validate_file",
    "is_allowed_extension",
    "get_file_extension",
    "DocumentProcessor",
    "ImagePreprocessor",
    "TextExtractor",
    "is_tesseract_available",
    "resolve_tesseract_cmd",
    "DocumentClassifier",
    "FieldExtractor",
    "DocumentValidator",
    "CrossDocumentComparator",
]
