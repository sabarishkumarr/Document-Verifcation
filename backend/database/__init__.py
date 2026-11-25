# Database module
from .db import (
    get_db_connection,
    init_db,
    insert_document,
    get_document,
    list_documents,
    insert_applicant,
    get_applicant,
    list_applicants,
    get_documents_by_applicant,
    update_document_extraction,
    update_document_processing_results,
    submit_document_review,
    get_dashboard_statistics,
)

__all__ = [
    "get_db_connection",
    "init_db",
    "insert_document",
    "get_document",
    "list_documents",
    "insert_applicant",
    "get_applicant",
    "list_applicants",
    "get_documents_by_applicant",
    "update_document_extraction",
    "update_document_processing_results",
    "submit_document_review",
    "get_dashboard_statistics",
]
