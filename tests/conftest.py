import io
import shutil
import tempfile
from pathlib import Path
import pytest
from flask import Flask

import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import create_app
from backend.database.db import init_db


@pytest.fixture
def app():
    """Create an isolated test application instance with temporary storage and database."""
    temp_dir = tempfile.mkdtemp()
    temp_upload = Path(temp_dir) / "uploads"
    temp_processed = Path(temp_dir) / "processed"
    temp_upload.mkdir(parents=True, exist_ok=True)
    temp_processed.mkdir(parents=True, exist_ok=True)
    temp_db = Path(temp_dir) / "test_veridoc.db"

    app = create_app("testing")
    app.config.update({
        "TESTING": True,
        "UPLOAD_FOLDER": temp_upload,
        "PROCESSED_FOLDER": temp_processed,
        "DATABASE_PATH": str(temp_db),
        "MAX_CONTENT_LENGTH": 5 * 1024 * 1024  # 5MB for testing
    })

    with app.app_context():
        init_db(str(temp_db))

    yield app

    # Cleanup temporary files
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def client(app: Flask):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def sample_pdf():
    """A valid synthetic PDF file stream with standard PDF header and trailer."""
    content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nxref\n0 1\n0000000000 65535 f \ntrailer\n<< /Root 1 0 R >>\n%%EOF"
    return io.BytesIO(content), "sample_kyc_pan.pdf"


@pytest.fixture
def sample_jpeg():
    """A minimal valid JPEG byte stream."""
    content = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\xff\xd9"
    return io.BytesIO(content), "sample_aadhaar.jpg"


@pytest.fixture
def sample_png():
    """A minimal valid PNG byte stream."""
    content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    return io.BytesIO(content), "sample_voter_id.png"


@pytest.fixture
def empty_file():
    """An empty file stream (0 bytes)."""
    return io.BytesIO(b""), "empty_doc.pdf"


@pytest.fixture
def unsupported_file():
    """A text file with unsupported extension."""
    return io.BytesIO(b"Plain text content not allowed"), "kyc_notes.txt"


@pytest.fixture
def fake_disguised_file():
    """A text file disguised with a .pdf extension."""
    return io.BytesIO(b"This is not a real PDF file!"), "disguised_malicious.pdf"
