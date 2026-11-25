import os
from typing import Tuple, Optional, Set
from werkzeug.datastructures import FileStorage

# Known magic numbers / header signatures for permitted document types
MAGIC_SIGNATURES = {
    "pdf": [b"%PDF-"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "png": [b"\x89PNG\r\n\x1a\n"],
}

MIME_TYPE_MAP = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}


def get_file_extension(filename: str) -> str:
    """Extract lowercase file extension without dot."""
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def is_allowed_extension(filename: str, allowed_extensions: Set[str]) -> bool:
    """Check if file extension matches allowed KYC document extensions."""
    ext = get_file_extension(filename)
    return ext in allowed_extensions


def validate_magic_bytes(file_storage: FileStorage, ext: str) -> bool:
    """
    Validate that the file stream header matches the declared extension.
    Protects against disguised files (e.g. executable renamed to .jpg).
    Always resets file pointer to offset 0 after inspection.
    """
    signatures = MAGIC_SIGNATURES.get(ext)
    if not signatures:
        return False

    header = file_storage.read(16)
    file_storage.seek(0)  # Always rewind back to the beginning

    for sig in signatures:
        if header.startswith(sig):
            return True
    return False


def validate_file(
    file_storage: FileStorage,
    allowed_extensions: Set[str],
    max_size_bytes: int
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Comprehensive validation for an incoming uploaded file.
    
    Checks:
    1. File presence and filename validity.
    2. Allowed file extension (.pdf, .jpg, .jpeg, .png).
    3. Non-empty file size (> 0 bytes).
    4. Maximum file size within permitted threshold.
    5. Header magic bytes match declared format.
    
    Returns:
        (is_valid: bool, error_message: Optional[str], detected_mime: Optional[str])
    """
    if not file_storage or not file_storage.filename or file_storage.filename.strip() == "":
        return False, "No file selected or filename is empty.", None

    filename = file_storage.filename.strip()
    ext = get_file_extension(filename)

    if not ext or ext not in allowed_extensions:
        allowed_list = ", ".join(sorted(allowed_extensions))
        return False, f"Unsupported file type '.{ext}'. Allowed types are: {allowed_list}.", None

    # Check file size by seeking to end
    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)  # Rewind to start

    if size == 0:
        return False, f"File '{filename}' is empty (0 bytes).", None

    if size > max_size_bytes:
        max_mb = max_size_bytes / (1024 * 1024)
        return False, f"File '{filename}' exceeds maximum allowed size of {max_mb:.1f} MB.", None

    # Header signature verification
    if not validate_magic_bytes(file_storage, ext):
        return False, f"File content of '{filename}' does not match the valid format for '.{ext}'.", None

    mime_type = MIME_TYPE_MAP.get(ext, file_storage.mimetype or "application/octet-stream")
    return True, None, mime_type
