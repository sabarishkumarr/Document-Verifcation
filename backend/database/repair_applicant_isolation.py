"""
VeriDoc AI - Database Repair & Applicant Isolation Script
Safely cleans contaminated test/audit records, properly associates documents
with their genuine applicant identities, and marks uncertain records as unassigned.
"""

import sqlite3
import json
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = Path(__file__).resolve().parent / "veridoc.db"

def repair_database(db_path: Path = DB_PATH):
    print(f"Connecting to database at {db_path}...")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Ensure APPL-SYN-018 (Ritika Kapoor) exists in applicants table
    cursor.execute("""
        INSERT OR IGNORE INTO applicants (id, name, status, risk_level, notes)
        VALUES ('APPL-SYN-018', 'Ritika Kapoor', 'verified', 'low', 'Synthetic KYC Benchmark Applicant 018')
    """)

    # 2. Known applicant mappings based on reliable identity signatures
    NAME_TO_APPL = {
        "AARAV MEHTA": "APPL-SYN-001",
        "PRIYA SHARMA": "APPL-SYN-002",
        "ROHAN NAIR": "APPL-SYN-003",
        "ANANYA IYER": "APPL-SYN-004",
        "ANANYA SUBRAMANIAN": "APPL-SYN-004",
        "KABIR MALHOTRA": "APPL-SYN-005",
        "MEERA KRISHNAN": "APPL-SYN-006",
        "DEV PATEL": "APPL-SYN-007",
        "ISHITA RAO": "APPL-SYN-008",
        "VIKRAM DAS": "APPL-SYN-009",
        "NEHA KAPOOR": "APPL-SYN-010",
        "RITIKA KAPOOR": "APPL-SYN-018",
    }

    FILE_PREFIX_TO_APPL = {
        "aarav_mehta_": "APPL-SYN-001",
        "priya_sharma_": "APPL-SYN-002",
        "rohan_nair_": "APPL-SYN-003",
        "ananya_iyer_": "APPL-SYN-004",
        "kabir_malhotra_": "APPL-SYN-005",
        "meera_krishnan_": "APPL-SYN-006",
        "dev_patel_": "APPL-SYN-007",
        "ishita_rao_": "APPL-SYN-008",
        "vikram_das_": "APPL-SYN-009",
        "neha_kapoor_": "APPL-SYN-010",
        "applicant_018_": "APPL-SYN-018",
    }

    # 3. Retrieve all documents from contaminated test applicants
    CONTAMINATED_APPLICANTS = [
        "APP-AUDIT-1795496949",
        "APP-TEST-E2E-LIVE",
        "APP-TEST-WORKFLOW-2",
        "APP-TEST-WORKFLOW",
        "APPL-INT-001",
        "APP-TEST-D0B2ED"
    ]

    placeholders = ",".join(["?"] * len(CONTAMINATED_APPLICANTS))
    cursor.execute(f"SELECT * FROM documents WHERE applicant_id IN ({placeholders})", CONTAMINATED_APPLICANTS)
    mixed_docs = [dict(r) for r in cursor.fetchall()]
    print(f"Found {len(mixed_docs)} documents under contaminated test applicants.")

    reassigned_count = 0
    unassigned_count = 0

    for doc in mixed_docs:
        doc_id = doc["id"]
        fname = (doc.get("original_filename") or "").lower()
        fields_str = doc.get("extracted_fields")
        fields = {}
        if fields_str:
            try:
                fields = json.loads(fields_str) if isinstance(fields_str, str) else fields_str
            except Exception:
                fields = {}

        raw_name = (fields.get("name") or fields.get("applicant_name") or "").strip().upper()

        target_appl_id = None
        # Check by extracted name first
        for k_name, appl_id in NAME_TO_APPL.items():
            if k_name in raw_name or raw_name == k_name:
                target_appl_id = appl_id
                break

        # Check by filename prefix if name was inconclusive or dummy test name
        if not target_appl_id or raw_name in ("AUDIT TEST NAME", "AUDIT NAME CORRECTED", ""):
            for prefix, appl_id in FILE_PREFIX_TO_APPL.items():
                if fname.startswith(prefix):
                    target_appl_id = appl_id
                    break

        if target_appl_id:
            cursor.execute("UPDATE documents SET applicant_id = ? WHERE id = ?", (target_appl_id, doc_id))
            reassigned_count += 1
        else:
            # Leave unassigned for human employee review
            cursor.execute("UPDATE documents SET applicant_id = NULL, review_status = 'requires_association' WHERE id = ?", (doc_id,))
            unassigned_count += 1

    print(f"Reassigned {reassigned_count} documents to genuine applicant IDs.")
    print(f"Marked {unassigned_count} documents as unassigned (requires_association).")

    # 4. Clean up redundant exact duplicate document records for the same applicant
    # Keeps the earliest or completed version of identical files
    cursor.execute("""
        SELECT applicant_id, file_hash, COUNT(*) as cnt
        FROM documents
        WHERE applicant_id IS NOT NULL AND file_hash IS NOT NULL AND file_hash != ''
        GROUP BY applicant_id, file_hash
        HAVING cnt > 1
    """)
    dup_groups = cursor.fetchall()
    total_dups_removed = 0
    for group in dup_groups:
        appl = group[0]
        fhash = group[1]
        cursor.execute("""
            SELECT id FROM documents
            WHERE applicant_id = ? AND file_hash = ?
            ORDER BY CASE WHEN processing_status = 'completed' THEN 0 ELSE 1 END, upload_timestamp ASC
        """, (appl, fhash))
        doc_ids = [r[0] for r in cursor.fetchall()]
        # Keep the first one, delete the rest
        to_delete = doc_ids[1:]
        for did in to_delete:
            cursor.execute("DELETE FROM documents WHERE id = ?", (did,))
            total_dups_removed += 1

    print(f"Removed {total_dups_removed} redundant duplicate document rows.")

    # 5. Delete contaminated/empty test applicant records
    cursor.execute(f"DELETE FROM applicants WHERE id IN ({placeholders})", CONTAMINATED_APPLICANTS)
    print(f"Deleted {len(CONTAMINATED_APPLICANTS)} contaminated test applicant records.")

    conn.commit()

    # 6. Recompute applicant status and consistency for all remaining applicants
    cursor.execute("SELECT id, name FROM applicants")
    remaining_apps = cursor.fetchall()
    print(f"\nRecomputing verification statuses for {len(remaining_apps)} clean applicants...")

    from backend.services.comparator import CrossDocumentComparator
    from backend.database.db import recompute_applicant_status

    for app_row in remaining_apps:
        app_id = app_row[0]
        recompute_applicant_status(app_id, db_path=str(db_path))

    conn.close()
    print("Database repair and applicant isolation completed successfully!")

if __name__ == "__main__":
    repair_database()
