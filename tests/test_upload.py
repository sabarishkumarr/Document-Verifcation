import io
from pathlib import Path
from backend.database.db import get_document, list_documents


def test_upload_no_files(client):
    """POST /api/documents/upload with empty request should return 400 Bad Request."""
    response = client.post("/api/documents/upload")
    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert "No file part" in data["message"]


def test_upload_valid_pdf(client, sample_pdf, app):
    """POST /api/documents/upload with a valid PDF file."""
    stream, filename = sample_pdf
    response = client.post(
        "/api/documents/upload",
        data={
            "files": (stream, filename),
            "applicant_id": "APPL-TEST-001"
        },
        content_type="multipart/form-data"
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["success"] is True
    assert len(data["uploaded"]) == 1
    assert len(data["errors"]) == 0

    record = data["uploaded"][0]
    assert record["original_filename"] == filename
    assert record["document_type"] == "unknown"
    assert record["processing_status"] == "pending"
    assert record["review_status"] == "pending"
    assert record["file_hash"] != ""
    assert record["file_size"] > 0
    assert record["applicant_id"] == "APPL-TEST-001"

    # Verify document exists on disk
    stored_path = Path(app.config["UPLOAD_FOLDER"]) / record["stored_filename"]
    assert stored_path.exists()
    assert stored_path.stat().st_size == record["file_size"]

    # Verify document recorded in SQLite database
    db_record = get_document(record["id"], db_path=app.config["DATABASE_PATH"])
    assert db_record is not None
    assert db_record["id"] == record["id"]
    assert db_record["original_filename"] == filename


def test_upload_valid_jpeg(client, sample_jpeg, app):
    """POST /api/documents/upload with a valid JPEG document."""
    stream, filename = sample_jpeg
    response = client.post(
        "/api/documents/upload",
        data={"files": (stream, filename)},
        content_type="multipart/form-data"
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["success"] is True
    assert len(data["uploaded"]) == 1
    assert data["uploaded"][0]["mime_type"] == "image/jpeg"


def test_upload_multiple_documents(client, sample_pdf, sample_png, app):
    """POST /api/documents/upload supporting multiple files simultaneously."""
    pdf_stream, pdf_name = sample_pdf
    png_stream, png_name = sample_png

    response = client.post(
        "/api/documents/upload",
        data={
            "files": [
                (pdf_stream, pdf_name),
                (png_stream, png_name)
            ],
            "applicant_id": "APPL-MULTI-01"
        },
        content_type="multipart/form-data"
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["success"] is True
    assert len(data["uploaded"]) == 2
    assert len(data["errors"]) == 0

    # Ensure each received a unique document id and distinct stored filename
    doc1, doc2 = data["uploaded"]
    assert doc1["id"] != doc2["id"]
    assert doc1["stored_filename"] != doc2["stored_filename"]


def test_upload_unsupported_file_extension(client, unsupported_file):
    """POST /api/documents/upload with an unsupported file extension (.txt)."""
    stream, filename = unsupported_file
    response = client.post(
        "/api/documents/upload",
        data={"files": (stream, filename)},
        content_type="multipart/form-data"
    )
    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert len(data["errors"]) == 1
    assert "Unsupported file type" in data["errors"][0]["error"]


def test_upload_empty_file(client, empty_file):
    """POST /api/documents/upload with an empty file (0 bytes)."""
    stream, filename = empty_file
    response = client.post(
        "/api/documents/upload",
        data={"files": (stream, filename)},
        content_type="multipart/form-data"
    )
    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert len(data["errors"]) == 1
    assert "empty (0 bytes)" in data["errors"][0]["error"]


def test_upload_disguised_file(client, fake_disguised_file):
    """POST /api/documents/upload with a text file renamed to .pdf (magic byte mismatch)."""
    stream, filename = fake_disguised_file
    response = client.post(
        "/api/documents/upload",
        data={"files": (stream, filename)},
        content_type="multipart/form-data"
    )
    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert len(data["errors"]) == 1
    assert "does not match the valid format" in data["errors"][0]["error"]


def test_no_overwrite_duplicate_filename(client, sample_pdf, app):
    """Ensure uploading files with identical original names does not overwrite either."""
    stream1, filename = sample_pdf
    stream2 = io.BytesIO(stream1.getvalue())

    res1 = client.post("/api/documents/upload", data={"files": (stream1, filename)}, content_type="multipart/form-data")
    res2 = client.post("/api/documents/upload", data={"files": (stream2, filename)}, content_type="multipart/form-data")

    assert res1.status_code == 201
    assert res2.status_code == 201

    doc1 = res1.get_json()["uploaded"][0]
    doc2 = res2.get_json()["uploaded"][0]

    assert doc1["id"] != doc2["id"]
    assert doc1["stored_filename"] != doc2["stored_filename"]

    # Both files must coexist on disk
    path1 = Path(app.config["UPLOAD_FOLDER"]) / doc1["stored_filename"]
    path2 = Path(app.config["UPLOAD_FOLDER"]) / doc2["stored_filename"]
    assert path1.exists()
    assert path2.exists()


def test_get_document_by_id(client, sample_pdf):
    """Verify GET /api/documents/<id> endpoint."""
    stream, filename = sample_pdf
    upload_res = client.post("/api/documents/upload", data={"files": (stream, filename)}, content_type="multipart/form-data")
    doc_id = upload_res.get_json()["uploaded"][0]["id"]

    fetch_res = client.get(f"/api/documents/{doc_id}")
    assert fetch_res.status_code == 200
    fetch_data = fetch_res.get_json()
    assert fetch_data["success"] is True
    assert fetch_data["data"]["document"]["id"] == doc_id
    assert fetch_data["data"]["document"]["original_filename"] == filename


def test_get_nonexistent_document(client):
    """Verify GET /api/documents/<id> returns 404 for unknown ID."""
    res = client.get("/api/documents/non-existent-uuid")
    assert res.status_code == 404
    data = res.get_json()
    assert data["success"] is False
