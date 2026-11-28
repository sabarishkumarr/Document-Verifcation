"""
VeriDoc AI — Safe, Repeatable PostgreSQL & SQLite Schema Migration Runner
Usage:
    python -m backend.migrate
"""
import logging
import sys
from pathlib import Path

from backend.config import Config
from backend.database.db import get_db_connection, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("veridoc.migrate")

REQUIRED_TABLES = [
    "ai_usage_logs",
    "api_keys",
    "applicant_triangulations",
    "applicants",
    "audit_access_logs",
    "audit_reviews",
    "batch_documents",
    "batch_submissions",
    "benchmark_runs",
    "comparison_rule_configurations",
    "comparison_rule_versions",
    "document_extracted_attributes",
    "document_schemas",
    "document_type_definitions",
    "documents",
    "external_applicant_mappings",
    "processing_jobs",
    "webhook_deliveries",
    "webhook_subscriptions",
]


def run_migrations() -> bool:
    """Apply all schema migrations idempotently without deleting or overwriting existing data."""
    logger.info(f"Starting schema migration (DATABASE_TYPE={Config.DATABASE_TYPE})...")

    # 1. Ensure all core & v2 tables and columns exist via init_db()
    init_db()

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # 2. Create migration tracking table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                description TEXT,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 3. Ensure webhook_deliveries exists (in case not created by init_db)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS webhook_deliveries (
                id TEXT PRIMARY KEY,
                subscription_id TEXT,
                event_type TEXT NOT NULL,
                payload TEXT,
                status_code INTEGER,
                response_body TEXT,
                attempt_count INTEGER DEFAULT 1,
                success BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 4. Record baseline & v2 migration versions idempotently
        migrations = [
            ("001_core_schema", "Core applicants, documents, audit_reviews, ai_usage_logs"),
            ("002_universal_platform", "Dynamic document_type_definitions, document_schemas, extracted_attributes, benchmark_runs"),
            ("003_universal_platform_v2", "Triangulation rules, processing_jobs, batch_submissions, api_keys, webhooks, audit_access_logs"),
        ]
        for ver, desc in migrations:
            cur.execute("SELECT version FROM schema_migrations WHERE version = ?", (ver,))
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
                    (ver, desc),
                )

        conn.commit()

        # 5. Verify all 19 required tables exist
        if Config.DATABASE_TYPE == "postgres":
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
            existing = {r["table_name"] for r in cur.fetchall()}
        else:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing = {r["name"] for r in cur.fetchall()}

        missing = [t for t in REQUIRED_TABLES if t not in existing]
        if missing:
            logger.error(f"Migration incomplete. Missing tables: {missing}")
            return False

        logger.info(f"Schema migration complete. All {len(REQUIRED_TABLES)} required tables verified.")
        return True
    except Exception as exc:
        conn.rollback()
        logger.error(f"Migration failed and was rolled back: {exc}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    ok = run_migrations()
    sys.exit(0 if ok else 1)
