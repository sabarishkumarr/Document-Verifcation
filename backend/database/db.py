import json
import sqlite3
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from flask import current_app
from rapidfuzz import fuzz


def is_placeholder_name(name: Optional[str]) -> bool:
    """Return True if name is empty, null, or a generic placeholder."""
    if not name or not str(name).strip():
        return True
    s = str(name).strip().lower()
    placeholders = {
        "new applicant", "unknown applicant", "anonymous applicant",
        "unnamed applicant", "applicant", "null", "none", "not detected", "n/a",
        "customer name", "name", "undefined", "provisional applicant"
    }
    if s in placeholders:
        return True
    if re.match(r"^applicant\s*[\d_-]*$", s):
        return True
    if re.match(r"^app\s*[\d_-]*$", s):
        return True
    return False


def _resolve_db_path(db_path: Optional[str] = None) -> str:
    """Resolve database path from argument, Flask app config, or default fallback."""
    if db_path is not None:
        return db_path
    try:
        if current_app and "DATABASE_PATH" in current_app.config:
            return current_app.config["DATABASE_PATH"]
    except RuntimeError:
        pass
    
    default_path = Path(__file__).resolve().parent / "veridoc.db"
    return str(default_path)


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Establish an SQLite database connection.
    Configures sqlite3.Row for dict-like column access and enables foreign keys.
    """
    target_path = _resolve_db_path(db_path)
    if target_path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
        
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """
    Initialize SQLite schema and perform safe non-destructive migrations.
    Safe to call multiple times (idempotent).
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # 1. Applicants Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applicants (
            id TEXT PRIMARY KEY,
            name TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 2. Documents Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            applicant_id TEXT,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            document_type TEXT DEFAULT 'unknown',
            file_size INTEGER,
            file_hash TEXT,
            mime_type TEXT,
            processing_status TEXT DEFAULT 'pending',
            review_status TEXT DEFAULT 'pending',
            upload_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (applicant_id) REFERENCES applicants (id) ON DELETE SET NULL
        );
    """)

    # 3. Audit Review Ledger Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT,
            applicant_id TEXT,
            officer_name TEXT DEFAULT 'Review Officer',
            decision TEXT NOT NULL,
            edited_fields TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE
        );
    """)

    # 4. Performance Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_applicant ON documents(applicant_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(file_hash);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(processing_status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_review ON documents(review_status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_doc ON audit_reviews(document_id);")

    # 5. Safe Schema Migrations for documents
    cursor.execute("PRAGMA table_info(documents);")
    doc_cols = {row["name"] for row in cursor.fetchall()}
    
    new_doc_columns = {
        "extracted_text": "TEXT",
        "extraction_metadata": "TEXT",
        "classified_type": "TEXT DEFAULT 'unknown'",
        "classification_confidence": "REAL DEFAULT 0.0",
        "extracted_fields": "TEXT",
        "validation_results": "TEXT",
        "reviewed_by": "TEXT",
        "reviewed_at": "TIMESTAMP",
        "review_notes": "TEXT",
    }
    for col_name, col_type in new_doc_columns.items():
        if col_name not in doc_cols:
            cursor.execute(f"ALTER TABLE documents ADD COLUMN {col_name} {col_type};")

    # 6. Safe Schema Migrations for applicants
    cursor.execute("PRAGMA table_info(applicants);")
    app_cols = {row["name"] for row in cursor.fetchall()}
    new_app_columns = {
        "email": "TEXT",
        "phone": "TEXT",
        "consistency_score": "REAL DEFAULT 0.0",
        "risk_level": "TEXT DEFAULT 'low'",
        "notes": "TEXT",
    }
    for col_name, col_type in new_app_columns.items():
        if col_name not in app_cols:
            cursor.execute(f"ALTER TABLE applicants ADD COLUMN {col_name} {col_type};")

    conn.commit()
    conn.close()


def insert_applicant(
    applicant_id: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    db_path: Optional[str] = None
) -> None:
    """Insert an applicant. Never uses placeholders as identity values."""
    clean_name = None if is_placeholder_name(name) else str(name).strip()
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO applicants (id, name, email, phone, status)
        VALUES (?, ?, ?, ?, 'pending')
    """, (applicant_id, clean_name, email, phone))
    conn.commit()
    conn.close()


def get_applicant(applicant_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetch applicant by ID."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM applicants WHERE id = ?", (applicant_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_applicant(
    applicant_id: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    status: Optional[str] = None,
    risk_level: Optional[str] = None,
    notes: Optional[str] = None,
    db_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Update applicant profile fields."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM applicants WHERE id = ?", (applicant_id,))
    current = cursor.fetchone()
    if not current:
        conn.close()
        return None

    updates = []
    params = []
    if name is not None:
        updates.append("name = ?")
        params.append(None if is_placeholder_name(name) else name.strip())
    if email is not None:
        updates.append("email = ?")
        params.append(email.strip() if email else None)
    if phone is not None:
        updates.append("phone = ?")
        params.append(phone.strip() if phone else None)
    if status is not None:
        updates.append("status = ?")
        params.append(status.strip())
    if risk_level is not None:
        updates.append("risk_level = ?")
        params.append(risk_level.strip())
    if notes is not None:
        updates.append("notes = ?")
        params.append(notes.strip() if notes else None)

    if updates:
        params.append(applicant_id)
        query = f"UPDATE applicants SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, tuple(params))
        conn.commit()

    cursor.execute("SELECT * FROM applicants WHERE id = ?", (applicant_id,))
    updated = cursor.fetchone()
    conn.close()
    return dict(updated) if updated else None



def list_applicants(
    limit: int = 50,
    offset: int = 0,
    dataset: Optional[str] = None,
    status_filter: Optional[str] = None,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """List applicants with associated document counts and latest activity, with optional dataset and status scope."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    where_clauses = []
    if dataset == "synthetic":
        where_clauses.append("a.id LIKE 'APPL-SYN-%'")
    elif dataset == "demo":
        where_clauses.append("a.id LIKE 'APP-DEMO-%'")
    elif dataset == "live":
        where_clauses.append("(a.id NOT LIKE 'APPL-SYN-%' AND a.id NOT LIKE 'APP-DEMO-%')")

    if status_filter and status_filter != "all":
        s = status_filter.lower().strip()
        if s in ("pending", "active"):
            where_clauses.append("(a.status = 'pending' OR a.status = 'active')")
        elif s in ("requires_attention", "manual_review", "attention"):
            where_clauses.append("a.status = 'requires_attention'")
        elif s in ("verified", "approved"):
            where_clauses.append("a.status = 'verified'")
        elif s == "rejected":
            where_clauses.append("a.status = 'rejected'")
        elif s == "resubmission_requested":
            where_clauses.append("a.status = 'resubmission_requested'")

    where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    cursor.execute(f"""
        SELECT a.*, 
               COUNT(d.id) AS document_count,
               MAX(d.upload_timestamp) AS latest_document_date,
               SUM(CASE WHEN d.review_status = 'pending' THEN 1 ELSE 0 END) AS pending_reviews,
               SUM(CASE WHEN d.review_status = 'rejected' OR d.review_status = 'manual_review' THEN 1 ELSE 0 END) AS issues_count
        FROM applicants a
        LEFT JOIN documents d ON a.id = d.applicant_id
        {where_sql}
        GROUP BY a.id
        ORDER BY a.created_at DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def insert_document(doc_data: Dict[str, Any], db_path: Optional[str] = None) -> None:
    """Insert a new document record into the database."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    applicant_id = doc_data.get("applicant_id")
    if applicant_id:
        cursor.execute("INSERT OR IGNORE INTO applicants (id, name) VALUES (?, NULL)", (applicant_id,))

    cursor.execute("""
        INSERT INTO documents (
            id,
            applicant_id,
            original_filename,
            stored_filename,
            document_type,
            file_size,
            file_hash,
            mime_type,
            processing_status,
            review_status
        ) VALUES (
            :id,
            :applicant_id,
            :original_filename,
            :stored_filename,
            :document_type,
            :file_size,
            :file_hash,
            :mime_type,
            :processing_status,
            :review_status
        )
    """, {
        "id": doc_data["id"],
        "applicant_id": applicant_id,
        "original_filename": doc_data["original_filename"],
        "stored_filename": doc_data.get("stored_filename", doc_data["original_filename"]),
        "document_type": doc_data.get("document_type", "unknown"),
        "file_size": doc_data.get("file_size", 0),
        "file_hash": doc_data.get("file_hash", ""),
        "mime_type": doc_data.get("mime_type", "application/octet-stream"),
        "processing_status": doc_data.get("processing_status", "pending"),
        "review_status": doc_data.get("review_status", "pending"),
    })
    
    conn.commit()
    conn.close()


def get_document(document_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve document by ID."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def list_documents(
    limit: int = 50,
    offset: int = 0,
    status_filter: Optional[str] = None,
    doc_type_filter: Optional[str] = None,
    applicant_id: Optional[str] = None,
    dataset: Optional[str] = None,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """List documents with optional filtering, dataset scope, and pagination."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    query = """
        SELECT d.*, a.name AS applicant_name
        FROM documents d
        LEFT JOIN applicants a ON d.applicant_id = a.id
        WHERE 1=1
    """
    params: List[Any] = []

    if status_filter and status_filter != "all":
        query += " AND (d.review_status = ? OR d.processing_status = ?)"
        params.extend([status_filter, status_filter])

    if doc_type_filter and doc_type_filter != "all":
        query += " AND (d.classified_type = ? OR d.document_type = ?)"
        params.extend([doc_type_filter, doc_type_filter])

    if applicant_id == "unassigned":
        query += " AND d.applicant_id IS NULL"
    elif applicant_id:
        query += " AND d.applicant_id = ?"
        params.append(applicant_id)

    if dataset == "synthetic":
        query += " AND d.applicant_id LIKE 'APPL-SYN-%'"
    elif dataset == "demo":
        query += " AND d.applicant_id LIKE 'APP-DEMO-%'"
    elif dataset == "live":
        query += " AND (d.applicant_id NOT LIKE 'APPL-SYN-%' AND d.applicant_id NOT LIKE 'APP-DEMO-%')"

    query += " ORDER BY d.upload_timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_documents(
    status_filter: Optional[str] = None,
    doc_type_filter: Optional[str] = None,
    applicant_id: Optional[str] = None,
    dataset: Optional[str] = None,
    db_path: Optional[str] = None
) -> int:
    """Count total documents matching filtering criteria."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    query = "SELECT COUNT(*) FROM documents d WHERE 1=1"
    params: List[Any] = []

    if status_filter and status_filter != "all":
        query += " AND (d.review_status = ? OR d.processing_status = ?)"
        params.extend([status_filter, status_filter])

    if doc_type_filter and doc_type_filter != "all":
        query += " AND (d.classified_type = ? OR d.document_type = ?)"
        params.extend([doc_type_filter, doc_type_filter])

    if applicant_id == "unassigned":
        query += " AND d.applicant_id IS NULL"
    elif applicant_id:
        query += " AND d.applicant_id = ?"
        params.append(applicant_id)

    if dataset == "synthetic":
        query += " AND d.applicant_id LIKE 'APPL-SYN-%'"
    elif dataset == "demo":
        query += " AND d.applicant_id LIKE 'APP-DEMO-%'"
    elif dataset == "live":
        query += " AND (d.applicant_id NOT LIKE 'APPL-SYN-%' AND d.applicant_id NOT LIKE 'APP-DEMO-%')"

    cursor.execute(query, tuple(params))
    total = cursor.fetchone()[0]
    conn.close()
    return total


def get_documents_by_applicant(
    applicant_id: str,
    db_path: Optional[str] = None,
    distinct_types: bool = False,
    document_ids: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Get documents strictly belonging to applicant_id.
    Guarantees strict applicant isolation.
    Optionally limits to specific document_ids (for current verification session)
    or takes the latest document per document_type.
    """
    if not applicant_id or not str(applicant_id).strip():
        return []

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    query = "SELECT * FROM documents WHERE applicant_id = ?"
    params: List[Any] = [applicant_id]

    if document_ids:
        placeholders = ",".join(["?"] * len(document_ids))
        query += f" AND id IN ({placeholders})"
        params.extend(document_ids)

    query += " ORDER BY upload_timestamp DESC"
    cursor.execute(query, tuple(params))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if distinct_types and rows:
        seen_types = set()
        deduped = []
        for r in rows:
            c_t = r.get("classified_type")
            d_t = r.get("document_type")
            if c_t and c_t.lower() != "unknown":
                t = c_t.lower()
            elif d_t and d_t.lower() != "unknown":
                t = d_t.lower()
            else:
                t = (c_t or d_t or "unknown").lower()
            if t not in seen_types:
                seen_types.add(t)
                deduped.append(r)
            elif t == "unknown":
                deduped.append(r)
        return deduped

    return rows


def update_document_extraction(
    document_id: str,
    extracted_text: Optional[str],
    extraction_metadata_json: Optional[str],
    processing_status: str = "completed",
    db_path: Optional[str] = None
) -> bool:
    """Update extracted text, metadata JSON, and processing status for a document."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE documents
        SET extracted_text = ?,
            extraction_metadata = ?,
            processing_status = ?
        WHERE id = ?
    """, (extracted_text, extraction_metadata_json, processing_status, document_id))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0


def update_document_processing_results(
    document_id: str,
    classified_type: str,
    classification_confidence: float,
    extracted_fields: Dict[str, Any],
    validation_results: Dict[str, Any],
    processing_status: str = "completed",
    db_path: Optional[str] = None
) -> bool:
    """Update full intelligence processing results for a document."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    fields_json = json.dumps(extracted_fields) if extracted_fields else None
    validation_json = json.dumps(validation_results) if validation_results else None
    
    # Auto-assign initial review status based on validation
    initial_review = "pending"
    if validation_results and validation_results.get("overall_status") == "invalid":
        initial_review = "manual_review"

    cursor.execute("""
        UPDATE documents
        SET classified_type = ?,
            document_type = ?,
            classification_confidence = ?,
            extracted_fields = ?,
            validation_results = ?,
            processing_status = ?,
            review_status = CASE 
                WHEN review_status = 'pending' THEN ? 
                ELSE review_status 
            END
        WHERE id = ?
    """, (
        classified_type,
        classified_type,
        classification_confidence,
        fields_json,
        validation_json,
        processing_status,
        initial_review,
        document_id
    ))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0


def submit_document_review(
    document_id: str,
    decision: str,  # 'approved' | 'rejected' | 'manual_review'
    edited_fields: Optional[Dict[str, Any]] = None,
    notes: Optional[str] = None,
    officer_name: str = "Arjun Mehta (Review Officer)",
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Apply a human review decision, update editable fields with an audit trail,
    and refresh applicant status.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # 1. Fetch current document
    cursor.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
    doc = cursor.fetchone()
    if not doc:
        conn.close()
        raise ValueError(f"Document '{document_id}' not found.")

    applicant_id = doc["applicant_id"]
    current_fields = {}
    if doc["extracted_fields"]:
        try:
            current_fields = json.loads(doc["extracted_fields"])
        except Exception:
            current_fields = {}

    # 2. Merge edited fields
    if edited_fields:
        for k, v in edited_fields.items():
            if v is not None and str(v).strip():
                current_fields[k] = v.strip()

    updated_fields_json = json.dumps(current_fields)

    # 3. Update Document Record
    cursor.execute("""
        UPDATE documents
        SET review_status = ?,
            reviewed_by = ?,
            reviewed_at = CURRENT_TIMESTAMP,
            review_notes = ?,
            extracted_fields = ?
        WHERE id = ?
    """, (decision, officer_name, notes, updated_fields_json, document_id))

    # 4. Record into Audit Review Ledger
    cursor.execute("""
        INSERT INTO audit_reviews (
            document_id, applicant_id, officer_name, decision, edited_fields, notes
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        document_id,
        applicant_id,
        officer_name,
        decision,
        json.dumps(edited_fields) if edited_fields else None,
        notes
    ))

    # 5. If applicant has a detected name in edited/extracted fields, update applicant name
    cand_name = current_fields.get("name")
    if applicant_id and cand_name and len(cand_name) >= 3:
        cursor.execute("UPDATE applicants SET name = ? WHERE id = ? AND (name LIKE 'Applicant%' OR name = 'Anonymous Applicant')", (cand_name, applicant_id))

    conn.commit()
    conn.close()

    # 6. Re-evaluate applicant overall status using unified business rules
    if applicant_id:
        recompute_applicant_status(applicant_id, db_path=db_path)

    return {
        "document_id": document_id,
        "applicant_id": applicant_id,
        "review_status": decision,
        "reviewed_by": officer_name,
        "extracted_fields": current_fields
    }


def submit_applicant_review(
    applicant_id: str,
    decision: str,  # 'verified' | 'requires_attention' | 'manual_review' | 'resubmission_requested' | 'rejected'
    notes: Optional[str] = None,
    officer_name: str = "Arjun Mehta (Compliance Officer)",
    document_corrections: Optional[Dict[str, Dict[str, Any]]] = None,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Apply an applicant-level KYC review decision.
    Validates business rules:
    - An applicant CANNOT be marked 'verified' if:
      1. Any associated document has expired.
      2. There is an unresolved critical discrepancy (DOB or Name mismatch).
      3. Mandatory fields (Customer Name or DOB) are missing.
    Updates applicant status, risk level, notes, and harmonizes document statuses.
    Records an entry in audit_reviews ledger.
    """
    if not applicant_id:
        raise ValueError("Applicant ID is required.")

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM applicants WHERE id = ?", (applicant_id,))
    appl = cursor.fetchone()
    if not appl:
        conn.close()
        raise ValueError(f"Applicant '{applicant_id}' not found.")

    # 1. Apply any document field corrections first if provided
    if document_corrections:
        for doc_id, fields in document_corrections.items():
            cursor.execute("SELECT extracted_fields FROM documents WHERE id = ? AND applicant_id = ?", (doc_id, applicant_id))
            row = cursor.fetchone()
            if row:
                current_f = {}
                if row[0]:
                    try:
                        current_f = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                    except Exception:
                        current_f = {}
                current_f.update({k: v for k, v in fields.items() if v is not None})
                cursor.execute("UPDATE documents SET extracted_fields = ? WHERE id = ?", (json.dumps(current_f), doc_id))
        conn.commit()

    # 2. Fetch all documents for this applicant to evaluate verification eligibility
    cursor.execute("SELECT * FROM documents WHERE applicant_id = ?", (applicant_id,))
    raw_docs = cursor.fetchall()
    hydrated = []
    has_expired_doc = False
    for doc in raw_docs:
        d = dict(doc)
        f = {}
        if d.get("extracted_fields"):
            try:
                f = json.loads(d["extracted_fields"]) if isinstance(d["extracted_fields"], str) else d["extracted_fields"]
            except Exception:
                f = {}
        d["extracted_fields"] = f

        val = {}
        if d.get("validation_results"):
            try:
                val = json.loads(d["validation_results"]) if isinstance(d["validation_results"], str) else d["validation_results"]
            except Exception:
                val = {}
        d["validation_results"] = val

        # Check expired
        if any("expired" in str(flag).lower() for flag in val.get("flags", [])):
            has_expired_doc = True
        hydrated.append(d)

    from backend.services.comparator import CrossDocumentComparator
    cross = CrossDocumentComparator.compare_applicant_documents(
        hydrated,
        applicant_name=appl["name"],
        applicant_id=applicant_id
    )

    clean_decision = decision.lower().strip()

    # 3. Validation Gates for 'verified' / 'approved'
    if clean_decision in ("verified", "approved"):
        if has_expired_doc:
            conn.close()
            raise ValueError("Cannot mark applicant Verified: One or more documents have expired. Expired documents prevent approval.")
        
        matrix = cross.get("matrix") or {}
        rows = matrix.get("rows") or []
        for r in rows:
            if r.get("attribute_key") in ("name", "dob") and r.get("result_status") == "MISMATCH":
                conn.close()
                raise ValueError(f"Cannot mark applicant Verified: Critical {r.get('attribute_label')} mismatch detected between documents.")
            if r.get("attribute_key") in ("name", "dob") and r.get("result_status") == "UNAVAILABLE":
                conn.close()
                raise ValueError(f"Cannot mark applicant Verified: Mandatory field '{r.get('attribute_label')}' not detected.")
            if r.get("attribute_key") == "expiry_date" and r.get("result_status") == "EXPIRED":
                conn.close()
                raise ValueError("Cannot mark applicant Verified: Document has passed its legal expiry date.")

        new_status = "verified"
        risk_level = "low"
        doc_review_status = "approved"

    elif clean_decision in ("resubmission_requested", "resubmit"):
        new_status = "requires_attention"
        risk_level = "medium"
        doc_review_status = "resubmission_requested"

    elif clean_decision in ("manual_review", "flag", "requires_attention"):
        new_status = "requires_attention"
        risk_level = "medium"
        doc_review_status = "manual_review"

    elif clean_decision in ("rejected", "reject"):
        if not notes or not notes.strip():
            conn.close()
            raise ValueError("A reason must be recorded when rejecting an applicant.")
        new_status = "rejected"
        risk_level = "high"
        doc_review_status = "rejected"

    else:
        conn.close()
        raise ValueError(f"Invalid review decision '{decision}'. Must be 'verified', 'resubmission_requested', 'manual_review', or 'rejected'.")

    # 4. Update applicant record
    cursor.execute("""
        UPDATE applicants
        SET status = ?, risk_level = ?, notes = ?, consistency_score = ?
        WHERE id = ?
    """, (new_status, risk_level, notes or appl["notes"], cross.get("consistency_score", 100.0), applicant_id))

    # 5. Harmonize review status on all applicant's documents
    cursor.execute("""
        UPDATE documents
        SET review_status = ?, reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP
        WHERE applicant_id = ?
    """, (doc_review_status, officer_name, applicant_id))

    # 6. Record in Audit Review Ledger
    cursor.execute("""
        INSERT INTO audit_reviews (
            document_id, applicant_id, officer_name, decision, notes
        ) VALUES (NULL, ?, ?, ?, ?)
    """, (applicant_id, officer_name, new_status, notes))

    conn.commit()

    cursor.execute("SELECT * FROM applicants WHERE id = ?", (applicant_id,))
    updated_appl = dict(cursor.fetchone())
    conn.close()

    return {
        "applicant": updated_appl,
        "decision": new_status,
        "officer_name": officer_name,
        "cross_verdict": cross.get("overall_verdict"),
        "consistency_score": cross.get("consistency_score")
    }


def consolidate_applicant_name(applicant_id: str, db_path: Optional[str] = None) -> Optional[str]:
    """
    Consolidates and updates the applicant's official display name in SQLite
    based strictly on reliable extracted names from their uploaded documents.
    Never uses placeholders (e.g. 'New Applicant', 'Applicant 018') as identity values.
    """
    if not applicant_id:
        return None

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM applicants WHERE id = ?", (applicant_id,))
    appl = cursor.fetchone()
    if not appl:
        conn.close()
        return None

    current_name = appl["name"]

    cursor.execute("SELECT extracted_fields FROM documents WHERE applicant_id = ?", (applicant_id,))
    rows = cursor.fetchall()

    extracted_names = []
    for r in rows:
        if r[0]:
            try:
                f = json.loads(r[0]) if isinstance(r[0], str) else r[0]
                n = f.get("name") or f.get("applicant_name")
                if n and not is_placeholder_name(n) and len(str(n).strip()) >= 2:
                    extracted_names.append(str(n).strip())
            except Exception:
                pass

    consolidated_name = None
    if extracted_names:
        norm_map = {}
        for n in extracted_names:
            clean = re.sub(r"[^a-zA-Z\s]", "", n).strip().lower()
            if clean and clean not in norm_map:
                norm_map[clean] = n

        unique_cleans = list(norm_map.keys())
        if current_name and not is_placeholder_name(current_name):
            curr_clean = re.sub(r"[^a-zA-Z\s]", "", current_name).strip().lower()
            if curr_clean in norm_map:
                consolidated_name = current_name
        
        if not consolidated_name:
            if len(unique_cleans) == 1:
                consolidated_name = norm_map[unique_cleans[0]]
            elif len(unique_cleans) > 1:
                all_agree = True
                for i in range(len(unique_cleans)):
                    for j in range(i + 1, len(unique_cleans)):
                        sim = fuzz.token_sort_ratio(unique_cleans[i], unique_cleans[j])
                        if sim < 85:
                            all_agree = False
                            break
                    if not all_agree:
                        break

                if all_agree:
                    consolidated_name = max(norm_map.values(), key=len)
                else:
                    # Genuinely conflicting names exist across documents
                    consolidated_name = norm_map[unique_cleans[0]]
    elif not is_placeholder_name(current_name):
        consolidated_name = current_name
    else:
        consolidated_name = None

    if consolidated_name and consolidated_name.isupper():
        consolidated_name = consolidated_name.title()

    if consolidated_name != current_name:
        cursor.execute("UPDATE applicants SET name = ? WHERE id = ?", (consolidated_name, applicant_id))
        conn.commit()

    conn.close()
    return consolidated_name


def recompute_applicant_status(applicant_id: str, db_path: Optional[str] = None) -> str:
    """
    Deterministically computes and updates an applicant's overall status in SQLite
    by harmonizing:
    1. Document review statuses ('approved', 'rejected', 'manual_review', 'resubmission_requested', 'pending')
    2. Document validation results (expiry flags, invalid ID formats, missing mandatory fields)
    3. Cross-document comparison verdict from CrossDocumentComparator
    """
    if not applicant_id or not str(applicant_id).strip():
        return "pending"

    # Consolidate reliable extracted name from documents into applicant profile
    consolidate_applicant_name(applicant_id, db_path=db_path)

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM applicants WHERE id = ?", (applicant_id,))
    app = cursor.fetchone()
    if not app:
        conn.close()
        return "unknown"

    cursor.execute("SELECT * FROM documents WHERE applicant_id = ?", (applicant_id,))
    raw_docs = cursor.fetchall()
    if not raw_docs:
        conn.close()
        return app["status"]

    hydrated = []
    doc_review_statuses = []
    has_expired_doc = False
    has_invalid_doc = False

    for doc in raw_docs:
        d = dict(doc)
        doc_review_statuses.append(d.get("review_status") or "pending")

        f = {}
        if d.get("extracted_fields"):
            try:
                f = json.loads(d["extracted_fields"]) if isinstance(d["extracted_fields"], str) else d["extracted_fields"]
            except Exception:
                f = {}
        d["extracted_fields"] = f

        val = {}
        if d.get("validation_results"):
            try:
                val = json.loads(d["validation_results"]) if isinstance(d["validation_results"], str) else d["validation_results"]
            except Exception:
                val = {}
        d["validation_results"] = val

        # Check validation failures
        flags = val.get("flags", [])
        if any("expired" in str(flag).lower() for flag in flags):
            has_expired_doc = True
        if val.get("is_valid") is False or val.get("overall_status") == "invalid":
            has_invalid_doc = True

        hydrated.append(d)

    from backend.services.comparator import CrossDocumentComparator
    cross = CrossDocumentComparator.compare_applicant_documents(
        hydrated,
        applicant_name=app["name"],
        applicant_id=applicant_id
    )
    cross_verdict = cross.get("overall_verdict", "VERIFIED")
    score = cross.get("consistency_score", 100.0)

    # Business Rules for Final Verification Status:
    # 1. If the applicant was explicitly rejected by an officer (or all docs rejected), keep status 'rejected'
    if app["status"] == "rejected" or (doc_review_statuses and all(s == "rejected" for s in doc_review_statuses)):
        new_status = "rejected"
        risk_level = "high"
    elif app["status"] == "resubmission_requested":
        new_status = "resubmission_requested"
        risk_level = "medium"
    elif has_expired_doc or has_invalid_doc or cross_verdict in ("DISCREPANCY_FLAGGED", "MANUAL_REVIEW"):
        new_status = "requires_attention"
        risk_level = "high" if (has_expired_doc or cross_verdict == "DISCREPANCY_FLAGGED") else "medium"
    elif any(s in ("manual_review", "resubmission_requested") for s in doc_review_statuses):
        new_status = "requires_attention"
        risk_level = "medium"
    elif any(s == "rejected" for s in doc_review_statuses):
        new_status = "rejected"
        risk_level = "high"
    elif all(s == "approved" for s in doc_review_statuses) and doc_review_statuses and cross_verdict == "VERIFIED":
        new_status = "verified"
        risk_level = "low"
    else:
        new_status = "pending"
        risk_level = "low"

    cursor.execute("""
        UPDATE applicants
        SET status = ?, risk_level = ?, consistency_score = ?
        WHERE id = ?
    """, (new_status, risk_level, score, applicant_id))

    conn.commit()
    conn.close()
    return new_status


def assign_document_applicant(document_id: str, applicant_id: Optional[str], db_path: Optional[str] = None) -> bool:
    """Manually assign or unassign a document to/from a confirmed applicant ID."""
    if not document_id:
        return False
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT applicant_id FROM documents WHERE id = ?", (document_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False
    old_appl_id = row[0]

    if applicant_id:
        cursor.execute("SELECT id FROM applicants WHERE id = ?", (applicant_id,))
        if not cursor.fetchone():
            conn.close()
            return False
        cursor.execute("UPDATE documents SET applicant_id = ?, review_status = 'pending' WHERE id = ?", (applicant_id, document_id))
    else:
        cursor.execute("UPDATE documents SET applicant_id = NULL, review_status = 'requires_association' WHERE id = ?", (document_id,))

    conn.commit()
    conn.close()

    if applicant_id:
        recompute_applicant_status(applicant_id, db_path=db_path)
    if old_appl_id and old_appl_id != applicant_id:
        recompute_applicant_status(old_appl_id, db_path=db_path)
    return True


def get_audit_reviews(
    document_id: Optional[str] = None,
    applicant_id: Optional[str] = None,
    limit: int = 50,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Retrieve audit review history for a document or applicant."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    if document_id:
        cursor.execute("""
            SELECT * FROM audit_reviews 
            WHERE document_id = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        """, (document_id, limit))
    elif applicant_id:
        cursor.execute("""
            SELECT * FROM audit_reviews 
            WHERE applicant_id = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        """, (applicant_id, limit))
    else:
        cursor.execute("""
            SELECT * FROM audit_reviews 
            ORDER BY created_at DESC 
            LIMIT ?
        """, (limit,))

    rows = cursor.fetchall()
    conn.close()

    reviews = []
    for r in rows:
        d = dict(r)
        if d.get("edited_fields") and isinstance(d["edited_fields"], str):
            try:
                d["edited_fields"] = json.loads(d["edited_fields"])
            except Exception:
                pass
        reviews.append(d)
    return reviews


def summarize_applicant_issue(applicant_status: str, notes: Optional[str], docs: List[Dict[str, Any]]) -> str:
    """Produce a concise, single-phrase issue summary for an applicant."""
    st = (applicant_status or "").lower()

    # Analyze document-level validation results & flags
    expired_types = []
    mismatch_flags = []
    missing_fields = []
    resub_types = []

    for d in docs:
        dtype = (d.get("classified_type") or d.get("document_type") or "document").replace("_", " ").title()
        val = d.get("validation_results")
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except Exception:
                val = {}
        flags = (val or {}).get("flags", [])
        for f in flags:
            fl = str(f).lower()
            if "expired" in fl or "validity" in fl:
                if dtype not in expired_types:
                    expired_types.append(dtype)
            elif "mismatch" in fl:
                if "name" in fl and "Name Mismatch" not in mismatch_flags:
                    mismatch_flags.append("Name Mismatch")
                elif "dob" in fl and "DOB Mismatch" not in mismatch_flags:
                    mismatch_flags.append("DOB Mismatch")
                elif "Discrepancy" not in mismatch_flags:
                    mismatch_flags.append("Discrepancy")
            elif "missing" in fl or "mandatory" in fl or "not found" in fl:
                if dtype not in missing_fields:
                    missing_fields.append(dtype)

        if d.get("review_status") == "resubmission_requested":
            if dtype not in resub_types:
                resub_types.append(dtype)

    clean_note_short = ""
    if notes and str(notes).strip():
        first_sentence = str(notes).strip().split(".")[0].strip()
        if len(first_sentence) > 42:
            clean_note_short = first_sentence[:39] + "..."
        else:
            clean_note_short = first_sentence

    if st == "rejected":
        if expired_types and mismatch_flags:
            return f"Rejected — Expired document and identity mismatch"
        if expired_types:
            return f"Rejected — Expired {expired_types[0]}"
        if mismatch_flags:
            return f"Rejected — {mismatch_flags[0]}"
        if clean_note_short:
            return f"Rejected — {clean_note_short}"
        return "Rejected by review officer"

    # Pending or requires_attention
    if expired_types and mismatch_flags:
        return f"Expired {expired_types[0]} and {mismatch_flags[0].lower()}"
    if expired_types:
        return f"Expired {expired_types[0]}"
    if mismatch_flags:
        return f"{mismatch_flags[0]} detected"
    if missing_fields:
        return f"Missing {missing_fields[0]} information"
    if resub_types:
        return f"Resubmission requested for {resub_types[0]}"
    if clean_note_short:
        return clean_note_short
    if st in ("manual_review", "requires_attention"):
        return "Discrepancy flagged for review"
    return "Pending secondary review"


def get_dashboard_statistics(db_path: Optional[str] = None, dataset: Optional[str] = None) -> Dict[str, Any]:
    """
    Calculate live operational metrics for the overview dashboard.
    Supports dataset filtering ('synthetic', 'demo', or 'all').
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Scope filtering conditions
    doc_filter_clause = ""
    app_filter_clause = ""
    app_filter_and = ""
    if dataset == "synthetic":
        doc_filter_clause = " WHERE applicant_id LIKE 'APPL-SYN-%'"
        app_filter_clause = " WHERE id LIKE 'APPL-SYN-%'"
        app_filter_and = " AND applicant_id LIKE 'APPL-SYN-%'"
    elif dataset == "demo":
        doc_filter_clause = " WHERE applicant_id LIKE 'APP-DEMO-%'"
        app_filter_clause = " WHERE id LIKE 'APP-DEMO-%'"
        app_filter_and = " AND applicant_id LIKE 'APP-DEMO-%'"
    elif dataset == "live":
        doc_filter_clause = " WHERE (applicant_id NOT LIKE 'APPL-SYN-%' AND applicant_id NOT LIKE 'APP-DEMO-%')"
        app_filter_clause = " WHERE (id NOT LIKE 'APPL-SYN-%' AND id NOT LIKE 'APP-DEMO-%')"
        app_filter_and = " AND (applicant_id NOT LIKE 'APPL-SYN-%' AND applicant_id NOT LIKE 'APP-DEMO-%')"

    cursor.execute(f"SELECT COUNT(*) FROM documents{doc_filter_clause}")
    total_docs = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM documents WHERE review_status = 'approved'{app_filter_and}")
    approved_count = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM documents WHERE review_status = 'pending' AND processing_status != 'failed'{app_filter_and}")
    pending_review_count = cursor.fetchone()[0]

    issues_sql = f"""
        SELECT COUNT(*) FROM documents 
        WHERE (review_status IN ('rejected', 'manual_review', 'resubmission_requested') 
           OR processing_status = 'failed' 
           OR (review_status NOT IN ('approved', 'pending'))){app_filter_and}
    """
    cursor.execute(issues_sql)
    issues_count = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM applicants{app_filter_clause}")
    total_applicants = cursor.fetchone()[0]

    # Breakdown by document type (normalized to lowercase)
    dtype_sql = """
        SELECT LOWER(COALESCE(classified_type, document_type, 'unknown')) as dtype, COUNT(*) 
        FROM documents
    """
    if doc_filter_clause:
        dtype_sql += doc_filter_clause
    dtype_sql += " GROUP BY dtype"
    cursor.execute(dtype_sql)
    type_breakdown = {row[0]: row[1] for row in cursor.fetchall()}

    # Recent 6 documents
    recent_sql = """
        SELECT d.id, d.original_filename, d.document_type, d.classified_type,
               d.processing_status, d.review_status, d.upload_timestamp,
               a.id as applicant_id, a.name as applicant_name,
               d.extracted_fields, d.validation_results
        FROM documents d
        LEFT JOIN applicants a ON d.applicant_id = a.id
    """
    if dataset == "synthetic":
        recent_sql += " WHERE d.applicant_id LIKE 'APPL-SYN-%'"
    elif dataset == "demo":
        recent_sql += " WHERE d.applicant_id LIKE 'APP-DEMO-%'"
    elif dataset == "live":
        recent_sql += " WHERE (d.applicant_id NOT LIKE 'APPL-SYN-%' AND d.applicant_id NOT LIKE 'APP-DEMO-%')"
    recent_sql += " ORDER BY d.upload_timestamp DESC LIMIT 6"
    cursor.execute(recent_sql)
    recent_docs = [dict(r) for r in cursor.fetchall()]

    # Queue items requiring attention (ONE row per applicant)
    attn_sql = """
        SELECT d.id, d.original_filename, d.document_type, d.classified_type, d.review_status,
               d.upload_timestamp, d.validation_results,
               a.id as applicant_id, a.name as applicant_name, a.status as applicant_status,
               a.notes as applicant_notes
        FROM documents d
        JOIN applicants a ON d.applicant_id = a.id
        WHERE d.review_status IN ('pending', 'manual_review', 'rejected', 'resubmission_requested')
           OR a.status IN ('requires_attention', 'rejected', 'manual_review')
    """
    if dataset == "synthetic":
        attn_sql += " AND d.applicant_id LIKE 'APPL-SYN-%'"
    elif dataset == "demo":
        attn_sql += " AND d.applicant_id LIKE 'APP-DEMO-%'"
    elif dataset == "live":
        attn_sql += " AND (d.applicant_id NOT LIKE 'APPL-SYN-%' AND d.applicant_id NOT LIKE 'APP-DEMO-%')"
    attn_sql += """
        ORDER BY d.upload_timestamp DESC
    """
    cursor.execute(attn_sql)
    raw_attn_rows = [dict(r) for r in cursor.fetchall()]

    # Group by applicant
    grouped_by_app: Dict[str, Dict[str, Any]] = {}
    for r in raw_attn_rows:
        app_id = r["applicant_id"]
        if app_id not in grouped_by_app:
            grouped_by_app[app_id] = {
                "id": app_id,
                "applicant_id": app_id,
                "applicant_name": r["applicant_name"],
                "applicant_status": r["applicant_status"] or "pending",
                "applicant_notes": r["applicant_notes"],
                "affected_docs": [],
                "classified_types": set(),
                "latest_timestamp": r["upload_timestamp"]
            }
        grouped_by_app[app_id]["affected_docs"].append(r)
        dtype = r.get("classified_type") or r.get("document_type") or "document"
        grouped_by_app[app_id]["classified_types"].add(dtype)

    attention_items = []
    for app_id, grp in grouped_by_app.items():
        doc_list = grp["affected_docs"]
        app_status = grp["applicant_status"]
        main_issue = summarize_applicant_issue(app_status, grp["applicant_notes"], doc_list)

        # Determine highest priority review status
        statuses = [d.get("review_status") for d in doc_list]
        if "rejected" in statuses or app_status == "rejected":
            status_summary = "rejected"
        elif "manual_review" in statuses or app_status in ("requires_attention", "manual_review"):
            status_summary = "manual_review"
        elif "resubmission_requested" in statuses:
            status_summary = "resubmission_requested"
        else:
            status_summary = "pending"

        types_list = sorted(list(grp["classified_types"]))
        attention_items.append({
            "id": app_id,
            "applicant_id": app_id,
            "applicant_name": grp["applicant_name"],
            "applicant_status": app_status,
            "review_status": status_summary,
            "affected_doc_count": len(doc_list),
            "classified_type": types_list[0] if len(types_list) == 1 else "multiple",
            "document_types": types_list,
            "original_filename": doc_list[0]["original_filename"] if len(doc_list) == 1 else f"{len(doc_list)} affected documents",
            "main_issue": main_issue,
            "affected_documents": doc_list,
            "upload_timestamp": grp["latest_timestamp"]
        })

    # Sort attention_items: rejected first, then manual_review/requires_attention, then pending
    def _attn_priority(item):
        st = item["review_status"]
        if st == "rejected":
            return 1
        if st in ("manual_review", "requires_attention"):
            return 2
        return 3

    attention_items.sort(key=_attn_priority)
    attention_items = attention_items[:8]

    # Overall Database Dataset Breakdown for Transparency
    cursor.execute("SELECT COUNT(*) FROM applicants WHERE id LIKE 'APPL-SYN-%'")
    syn_apps = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM documents WHERE applicant_id LIKE 'APPL-SYN-%'")
    syn_docs = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM applicants WHERE id LIKE 'APP-DEMO-%'")
    demo_apps = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM documents WHERE applicant_id LIKE 'APP-DEMO-%'")
    demo_docs = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM applicants")
    all_db_apps = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM documents")
    all_db_docs = cursor.fetchone()[0]

    dataset_breakdown = {
        "synthetic_kyc": {
            "applicants": syn_apps,
            "documents": syn_docs,
            "label": "Synthetic KYC Benchmark Dataset (APPL-SYN-001..010)"
        },
        "demo": {
            "applicants": demo_apps,
            "documents": demo_docs,
            "label": "Demo Fixtures (APP-DEMO-001..010)"
        },
        "live_batches": {
            "applicants": max(0, all_db_apps - syn_apps - demo_apps),
            "documents": max(0, all_db_docs - syn_docs - demo_docs),
            "label": "Live Uploads & Pipeline Test Runs"
        },
        "all_database": {
            "applicants": all_db_apps,
            "documents": all_db_docs,
            "label": "All Database Records"
        }
    }

    conn.close()

    return {
        "total_documents": total_docs,
        "approved_count": approved_count,
        "processed_count": approved_count,
        "pending_review_count": pending_review_count,
        "issues_count": issues_count,
        "total_applicants": total_applicants,
        "type_breakdown": type_breakdown,
        "recent_documents": recent_docs,
        "attention_queue": attention_items,
        "attention_items": attention_items,
        "dataset_scope": dataset or "all",
        "dataset_breakdown": dataset_breakdown
    }


def search_all(query: str, limit: int = 10, db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Global search across applicants and documents.
    Matches applicants by:
    - ID, Name, Email, Phone
    Matches documents by:
    - Document ID, Original Filename, Document Type, Classified Type,
      Extracted Text, Extracted JSON Fields (e.g. ID numbers, names)
    """
    if not query or len(query.strip()) < 1:
        return {"applicants": [], "documents": []}

    term = f"%{query.strip()}%"
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # 1. Search Applicants
    cursor.execute("""
        SELECT a.id, a.name, a.email, a.phone, a.status, a.risk_level,
               COUNT(d.id) AS document_count
        FROM applicants a
        LEFT JOIN documents d ON a.id = d.applicant_id
        WHERE a.id LIKE ? OR a.name LIKE ? OR a.email LIKE ? OR a.phone LIKE ?
        GROUP BY a.id
        ORDER BY a.name ASC
        LIMIT ?
    """, (term, term, term, term, limit))
    applicants = [dict(r) for r in cursor.fetchall()]

    # 2. Search Documents
    cursor.execute("""
        SELECT d.id, d.original_filename, d.document_type, d.classified_type,
               d.processing_status, d.review_status, d.upload_timestamp,
               d.extracted_fields, d.applicant_id,
               COALESCE(a.name, 'Unknown Applicant') as applicant_name
        FROM documents d
        LEFT JOIN applicants a ON d.applicant_id = a.id
        WHERE d.id LIKE ?
           OR d.original_filename LIKE ?
           OR d.classified_type LIKE ?
           OR d.extracted_text LIKE ?
           OR d.extracted_fields LIKE ?
        ORDER BY d.upload_timestamp DESC
        LIMIT ?
    """, (term, term, term, term, term, limit))
    documents = [dict(r) for r in cursor.fetchall()]

    conn.close()

    # Parse extracted_fields for clean client representation
    for doc in documents:
        if doc.get("extracted_fields"):
            try:
                doc["extracted_fields"] = json.loads(doc["extracted_fields"])
            except Exception:
                pass

    return {
        "applicants": applicants,
        "documents": documents
    }
