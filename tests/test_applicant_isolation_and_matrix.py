"""
VeriDoc AI - Comprehensive Unit and Integration Tests for:
1. Applicant Data Isolation (Priority 1)
2. Field-Specific Cross-Document Comparison (Priority 2)
3. Structured Comparison Matrix Generation (Priority 3)
4. Spreadsheet Export (XLSX and CSV) (Priority 3 & 6)
"""

import io
import pytest
from backend.services.comparator import CrossDocumentComparator
from backend.services.matrix_exporter import (
    export_comparison_matrix_to_xlsx,
    export_comparison_matrix_to_csv,
    export_reports_summary_to_xlsx,
)
from backend.database.db import (
    insert_applicant,
    insert_document,
    get_documents_by_applicant,
    get_applicant,
    recompute_applicant_status,
)


class TestApplicantDataIsolation:
    """Test strict isolation between applicants."""

    def test_cross_applicant_documents_rejected(self):
        """Documents belonging to different applicant IDs must be isolated and flagged."""
        docs = [
            {
                "id": "doc-1",
                "applicant_id": "APPL-A",
                "type": "pan",
                "filename": "appl_a_pan.pdf",
                "fields": {"name": "Aarav Sharma", "dob": "1990-05-14", "id_number": "ABCDE1234F"},
            },
            {
                "id": "doc-2",
                "applicant_id": "APPL-B",  # Conflicting applicant ID
                "type": "aadhaar",
                "filename": "appl_b_aadhaar.pdf",
                "fields": {"name": "Priya Nair", "dob": "1995-10-20", "id_number": "9876 5432 1098"},
            },
        ]

        result = CrossDocumentComparator.compare_applicant_documents(
            documents=docs,
            applicant_name="Aarav Sharma",
            applicant_id="APPL-A"
        )

        assert result["overall_verdict"] == "DISCREPANCY_FLAGGED"
        assert any("isolation" in d.lower() for d in result["discrepancies"])
        # Cross comparison matrix must still be generated safely
        assert "matrix" in result
        assert result["matrix"]["applicant_id"] == "APPL-A"

    def test_database_applicant_isolation(self, app):
        """Database queries must strictly isolate documents by applicant_id."""
        with app.app_context():
            # Create two applicants
            insert_applicant("APPL-TEST-001", "Rohan Mehta", "test1@example.com")
            insert_applicant("APPL-TEST-002", "Sneha Kapoor", "test2@example.com")

            # Insert docs for APPL-TEST-001
            insert_document({
                "id": "doc-t1",
                "applicant_id": "APPL-TEST-001",
                "original_filename": "rohan_pan.pdf",
                "stored_filename": "rohan_pan.pdf",
                "file_hash": "hash-rohan-pan",
                "file_size": 1024,
                "mime_type": "application/pdf",
                "document_type": "pan",
                "review_status": "approved"
            })
            insert_document({
                "id": "doc-t2",
                "applicant_id": "APPL-TEST-001",
                "original_filename": "rohan_aadhaar.pdf",
                "stored_filename": "rohan_aadhaar.pdf",
                "file_hash": "hash-rohan-aadhaar",
                "file_size": 2048,
                "mime_type": "application/pdf",
                "document_type": "aadhaar",
                "review_status": "approved"
            })

            # Insert doc for APPL-TEST-002
            insert_document({
                "id": "doc-t3",
                "applicant_id": "APPL-TEST-002",
                "original_filename": "sneha_passport.pdf",
                "stored_filename": "sneha_passport.pdf",
                "file_hash": "hash-sneha-passport",
                "file_size": 4096,
                "mime_type": "application/pdf",
                "document_type": "passport",
                "review_status": "approved"
            })

            # Verify APPL-TEST-001 receives only its own 2 documents
            docs_001 = get_documents_by_applicant("APPL-TEST-001")
            assert len(docs_001) == 2
            assert all(d["applicant_id"] == "APPL-TEST-001" for d in docs_001)
            assert not any(d["id"] == "doc-t3" for d in docs_001)

            # Verify APPL-TEST-002 receives only its 1 document
            docs_002 = get_documents_by_applicant("APPL-TEST-002")
            assert len(docs_002) == 1
            assert docs_002[0]["id"] == "doc-t3"


class TestFieldSpecificComparisons:
    """Test deterministic attribute rules (DOB exact ISO, Name normalization, ID scoped)."""

    def test_dob_matching_iso_normalized(self):
        """DOB in different standard formats (DD/MM/YYYY vs YYYY-MM-DD) must match exactly."""
        norm1 = CrossDocumentComparator.normalize_dob("14/05/1990")
        norm2 = CrossDocumentComparator.normalize_dob("1990-05-14")
        norm3 = CrossDocumentComparator.normalize_dob("14-05-1990")
        norm4 = CrossDocumentComparator.normalize_dob("14 May 1990")

        assert norm1 == "1990-05-14"
        assert norm2 == "1990-05-14"
        assert norm3 == "1990-05-14"
        assert norm4 == "1990-05-14"

        docs = [
            {
                "id": "doc-1",
                "applicant_id": "APPL-1",
                "type": "pan",
                "filename": "pan.pdf",
                "fields": {"name": "Sunil Verma", "dob": "14/05/1990", "id_number": "ABCDE1234F"},
            },
            {
                "id": "doc-2",
                "applicant_id": "APPL-1",
                "type": "aadhaar",
                "filename": "aadhaar.pdf",
                "fields": {"name": "Sunil Verma", "dob": "1990-05-14", "id_number": "9876 5432 1098"},
            },
        ]
        result = CrossDocumentComparator.compare_applicant_documents(
            documents=docs,
            applicant_name="Sunil Verma",
            applicant_id="APPL-1"
        )
        dob_check = next(c for c in result["cross_checks"] if c["field"] in ("dob", "date_of_birth"))
        assert dob_check["status"] == "pass"
        assert dob_check["score"] == 100.0

    def test_dob_mismatch_flags_review(self):
        """Conflicting dates of birth must fail and prevent automatic verification."""
        docs = [
            {
                "id": "doc-1",
                "applicant_id": "APPL-1",
                "type": "pan",
                "filename": "pan.pdf",
                "fields": {"name": "Sunil Verma", "dob": "14/05/1990", "id_number": "ABCDE1234F"},
            },
            {
                "id": "doc-2",
                "applicant_id": "APPL-1",
                "type": "aadhaar",
                "filename": "aadhaar.pdf",
                "fields": {"name": "Sunil Verma", "dob": "20/11/1988", "id_number": "9876 5432 1098"},
            },
        ]
        result = CrossDocumentComparator.compare_applicant_documents(
            documents=docs,
            applicant_name="Sunil Verma",
            applicant_id="APPL-1"
        )
        assert result["overall_verdict"] == "DISCREPANCY_FLAGGED"
        assert any("Date of Birth mismatch" in d or "DOB mismatch" in d for d in result["discrepancies"])

    def test_id_number_never_compared_across_different_types(self):
        """PAN and Aadhaar must never have their ID numbers compared against each other."""
        docs = [
            {
                "id": "doc-1",
                "applicant_id": "APPL-1",
                "type": "pan",
                "filename": "pan.pdf",
                "fields": {"name": "Sunil Verma", "dob": "1990-05-14", "id_number": "ABCDE1234F"},
            },
            {
                "id": "doc-2",
                "applicant_id": "APPL-1",
                "type": "aadhaar",
                "filename": "aadhaar.pdf",
                "fields": {"name": "Sunil Verma", "dob": "1990-05-14", "id_number": "9876 5432 1098"},
            },
        ]
        result = CrossDocumentComparator.compare_applicant_documents(
            documents=docs,
            applicant_name="Sunil Verma",
            applicant_id="APPL-1"
        )
        # ID check must not compare PAN to Aadhaar and should pass
        id_check = next(c for c in result["cross_checks"] if c["field"] in ("id_numbers", "identification_number"))
        assert id_check["status"] == "pass"
        assert "different" in id_check["message"].lower() or "respective" in id_check["message"].lower()

    def test_expired_document_never_verified(self):
        """An expired document must trigger a critical discrepancy and prevent VERIFIED status."""
        docs = [
            {
                "id": "doc-1",
                "applicant_id": "APPL-1",
                "type": "pan",
                "filename": "pan.pdf",
                "fields": {"name": "Dev Patel", "dob": "1985-04-12", "id_number": "ABCDE1234F"},
            },
            {
                "id": "doc-2",
                "applicant_id": "APPL-1",
                "type": "passport",
                "filename": "passport.pdf",
                "fields": {
                    "name": "Dev Patel",
                    "dob": "1985-04-12",
                    "id_number": "Z1234567",
                    "expiry_date": "2020-01-01"  # Expired
                },
            },
        ]
        result = CrossDocumentComparator.compare_applicant_documents(
            documents=docs,
            applicant_name="Dev Patel",
            applicant_id="APPL-1"
        )
        assert result["overall_verdict"] == "DISCREPANCY_FLAGGED"
        assert any("expired" in d.lower() for d in result["discrepancies"])
        assert result["consistency_score"] <= 60.0


class TestStructuredMatrixAndExport:
    """Test comparison matrix structure and openpyxl XLSX / CSV export."""

    def test_matrix_structure_has_all_attributes(self):
        """The comparison matrix must contain all 8 compliance attribute rows."""
        docs = [
            {
                "id": "doc-1",
                "applicant_id": "APPL-1",
                "type": "pan",
                "filename": "pan.pdf",
                "fields": {
                    "name": "Ananya Sen",
                    "dob": "1992-07-22",
                    "id_number": "ABCDE1234F",
                    "gender": "FEMALE",
                    "father_name": "Ramesh Sen",
                },
            },
            {
                "id": "doc-2",
                "applicant_id": "APPL-1",
                "type": "driving_licence",
                "filename": "dl.pdf",
                "fields": {
                    "name": "Ananya Sen",
                    "dob": "1992-07-22",
                    "id_number": "DL-1420110012345",
                    "gender": "FEMALE",
                    "address": "45 Park Street, Kolkata",
                    "issue_date": "2015-08-10",
                    "expiry_date": "2035-08-09"
                },
            },
        ]

        result = CrossDocumentComparator.compare_applicant_documents(
            documents=docs,
            applicant_name="Ananya Sen",
            applicant_id="APPL-1"
        )

        matrix = result.get("matrix")
        assert matrix is not None
        assert len(matrix["columns"]) == 2
        
        row_keys = [r["attribute_key"] for r in matrix["rows"]]
        assert "name" in row_keys
        assert "dob" in row_keys
        assert "gender" in row_keys
        assert "id_number" in row_keys
        assert "address" in row_keys
        assert "father_name" in row_keys
        assert "issue_date" not in row_keys  # Issue date removed per requirements
        assert "validity" in row_keys or "expiry_date" in row_keys

    def test_export_comparison_matrix_xlsx(self):
        """Exporting the comparison matrix to XLSX must return valid Excel binary bytes."""
        matrix_data = {
            "applicant_id": "APPL-TEST-001",
            "applicant_name": "Ananya Sen",
            "overall_verdict": "VERIFIED",
            "consistency_score": 98.0,
            "columns": [
                {"id": "doc-1", "filename": "pan.pdf", "type_label": "PAN Card"},
                {"id": "doc-2", "filename": "dl.pdf", "type_label": "Driving Licence"},
            ],
            "rows": [
                {
                    "attribute_label": "Customer Name",
                    "values": {"doc-1": "Ananya Sen", "doc-2": "Ananya Sen"},
                    "result_status": "match",
                    "result_label": "Match",
                    "explanation": "Customer name matches across submitted documents."
                },
                {
                    "attribute_label": "Date of Birth",
                    "values": {"doc-1": "1992-07-22", "doc-2": "1992-07-22"},
                    "result_status": "match",
                    "result_label": "Match",
                    "explanation": "Date of Birth matches across submitted documents."
                }
            ]
        }

        xlsx_bytes = export_comparison_matrix_to_xlsx(matrix_data)
        assert isinstance(xlsx_bytes, bytes)
        assert len(xlsx_bytes) > 1000
        # Excel .xlsx is a ZIP file starting with PK\x03\x04
        assert xlsx_bytes[:4] == b"PK\x03\x04"

    def test_export_comparison_matrix_csv(self):
        """Exporting the comparison matrix to CSV must return valid formatted text."""
        matrix_data = {
            "applicant_id": "APPL-TEST-001",
            "applicant_name": "Ananya Sen",
            "columns": [
                {"id": "doc-1", "type_label": "PAN Card"},
                {"id": "doc-2", "type_label": "Driving Licence"},
            ],
            "rows": [
                {
                    "attribute_label": "Customer Name",
                    "values": {"doc-1": "Ananya Sen", "doc-2": "Ananya Sen"},
                    "result_label": "Match",
                    "explanation": "Consistent name across documents."
                }
            ]
        }

        csv_text = export_comparison_matrix_to_csv(matrix_data)
        assert isinstance(csv_text, str)
        assert "Customer Name" in csv_text
        assert "Ananya Sen" in csv_text
        assert "Match" in csv_text

    def test_api_matrix_export_endpoint(self, client, app):
        """GET /api/applicants/<id>/comparison/export?format=xlsx|csv must return HTTP 200."""
        with app.app_context():
            insert_applicant("APPL-EXP-001", "Vikram Malhotra", "vikram@example.com")
            insert_document({
                "id": "doc-exp-1",
                "applicant_id": "APPL-EXP-001",
                "original_filename": "pan.pdf",
                "stored_filename": "pan.pdf",
                "file_hash": "hash-pan",
                "file_size": 1024,
                "mime_type": "application/pdf",
                "document_type": "pan",
                "review_status": "approved",
                "extracted_fields": {"name": "Vikram Malhotra", "dob": "1988-03-15"}
            })

        # Test XLSX export endpoint
        res_xlsx = client.get("/api/applicants/APPL-EXP-001/comparison/export?format=xlsx")
        assert res_xlsx.status_code == 200
        assert "spreadsheetml" in res_xlsx.content_type
        assert res_xlsx.data[:4] == b"PK\x03\x04"

        # Test CSV export endpoint
        res_csv = client.get("/api/applicants/APPL-EXP-001/comparison/export?format=csv")
        assert res_csv.status_code == 200
        assert "text/csv" in res_csv.content_type
        assert b"Customer Name" in res_csv.data

    def test_api_reports_download_xlsx(self, client, app):
        """GET /api/reports/download?format=xlsx must return HTTP 200 with Excel workbook."""
        with app.app_context():
            insert_applicant("APPL-REP-001", "Kavita Rao", "kavita@example.com")

        res = client.get("/api/reports/download?format=xlsx&dataset=all")
        assert res.status_code == 200
        assert "spreadsheetml" in res.content_type
        assert res.data[:4] == b"PK\x03\x04"
