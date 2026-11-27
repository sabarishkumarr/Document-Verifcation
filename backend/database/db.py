import json
import sqlite3
import os
import re
import hashlib
import uuid
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from flask import current_app
from rapidfuzz import fuzz

try:
    import psycopg2
    from psycopg2.extras import DictCursor, RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    psycopg2 = None
    DictCursor = None
    RealDictCursor = None
    PSYCOPG2_AVAILABLE = False


class PostgresRow(dict):
    """
    Row wrapper that supports both dict key lookup (row['name'])
    and integer indexing (row[0]) exactly matching sqlite3.Row.
    """
    def __init__(self, raw_row, description):
        self._raw_row = raw_row
        col_names = [d[0] for d in description] if description else []
        super().__init__(zip(col_names, raw_row))

    def __getitem__(self, item):
        if isinstance(item, int):
            return self._raw_row[item]
        return super().__getitem__(item)


class PostgresCursorWrapper:
    """
    Transparent psycopg2 cursor wrapper providing:
    1. Automatic translation of '?' positional placeholders to '%s'.
    2. Automatic translation of ':key' named placeholders to '%(key)s'.
    3. Seamless compatibility with SQLite 'INSERT OR IGNORE' via 'ON CONFLICT (id) DO NOTHING'.
    4. lastrowid property emulation for serial tables.
    5. Dict-compatible row return types identical to sqlite3.Row (both row['key'] and row[0]).
    """
    def __init__(self, raw_cursor):
        self._cur = raw_cursor
        self._lastrowid = None

    def execute(self, sql: str, params: Any = None):
        clean_sql = sql
        # Adapt SQLite 'INSERT OR IGNORE'
        if "INSERT OR IGNORE INTO applicants" in clean_sql:
            clean_sql = clean_sql.replace("INSERT OR IGNORE INTO applicants", "INSERT INTO applicants")
            if "ON CONFLICT" not in clean_sql:
                clean_sql = clean_sql.rstrip().rstrip(";") + " ON CONFLICT (id) DO NOTHING"

        # Adapt boolean comparisons for Postgres strict boolean typing
        clean_sql = re.sub(r'\b(is_\w+)\s*=\s*1\b', r'\1 = TRUE', clean_sql)
        clean_sql = re.sub(r'\b(is_\w+)\s*=\s*0\b', r'\1 = FALSE', clean_sql)
        clean_sql = re.sub(r'\b(is_\w+)\s*=\s*TRUE\s+OR\s+\1\s*=\s*TRUE\b', r'\1 = TRUE', clean_sql)
        clean_sql = re.sub(r'\b(is_\w+)\s*=\s*FALSE\s+OR\s+\1\s*=\s*FALSE\b', r'\1 = FALSE', clean_sql)

        # Auto-append RETURNING id for lastrowid emulation on serial tables
        is_insert = clean_sql.strip().upper().startswith("INSERT INTO")
        has_returning = "RETURNING" in clean_sql.upper()
        if is_insert and not has_returning and ("ai_usage_logs" in clean_sql or "audit_reviews" in clean_sql):
            clean_sql = clean_sql.rstrip().rstrip(";") + " RETURNING id"
            has_returning = True

        if params is not None:
            if isinstance(params, (tuple, list)):
                # Escape literal '%' to '%%' before converting '?' to '%s'
                clean_sql = clean_sql.replace("%", "%%").replace("?", "%s")
                self._cur.execute(clean_sql, params)
            elif isinstance(params, dict):
                clean_sql = clean_sql.replace("%", "%%")
                clean_sql = re.sub(r':([a-zA-Z0-9_]+)', r'%(\1)s', clean_sql)
                self._cur.execute(clean_sql, params)
            else:
                self._cur.execute(clean_sql, params)
        else:
            self._cur.execute(clean_sql)

        if is_insert and has_returning:
            try:
                row = self._cur.fetchone()
                if row:
                    self._lastrowid = row[0] if isinstance(row, (tuple, list)) else row.get("id")
            except Exception:
                self._lastrowid = None

        return self

    def executemany(self, sql: str, seq_of_parameters: Any):
        clean_sql = sql
        if "INSERT OR IGNORE INTO applicants" in clean_sql:
            clean_sql = clean_sql.replace("INSERT OR IGNORE INTO applicants", "INSERT INTO applicants")
            if "ON CONFLICT" not in clean_sql:
                clean_sql = clean_sql.rstrip().rstrip(";") + " ON CONFLICT (id) DO NOTHING"
        clean_sql = re.sub(r'\b(is_\w+)\s*=\s*1\b', r'\1 = TRUE', clean_sql)
        clean_sql = re.sub(r'\b(is_\w+)\s*=\s*0\b', r'\1 = FALSE', clean_sql)
        clean_sql = clean_sql.replace("?", "%s")
        return self._cur.executemany(clean_sql, seq_of_parameters)

    @property
    def lastrowid(self):
        return self._lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def description(self):
        return self._cur.description

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        return PostgresRow(row, self._cur.description)

    def fetchall(self):
        rows = self._cur.fetchall()
        desc = self._cur.description
        return [PostgresRow(r, desc) for r in rows]

    def close(self):
        self._cur.close()

    def __iter__(self):
        desc = self._cur.description
        for r in self._cur:
            yield PostgresRow(r, desc)


class PostgresConnectionWrapper:
    """Postgres connection wrapper providing sqlite3.Connection compatible interface."""
    def __init__(self, raw_conn):
        self._conn = raw_conn

    def cursor(self):
        return PostgresCursorWrapper(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def execute(self, sql: str, params: Any = None):
        cur = self.cursor()
        return cur.execute(sql, params)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def execute(self, sql: str, params: Any = None):
        cur = self.cursor()
        return cur.execute(sql, params)


def is_postgres_configured() -> bool:
    """Return True if PostgreSQL is enabled and configured via environment or Flask config."""
    try:
        if current_app:
            if current_app.config.get("TESTING"):
                if current_app.config.get("DATABASE_TYPE") != "postgres":
                    return False
            if "DATABASE_TYPE" in current_app.config:
                cfg_type = str(current_app.config.get("DATABASE_TYPE", "")).lower().strip()
                if cfg_type in ("postgres", "postgresql"):
                    return True
                elif cfg_type == "sqlite":
                    return False
    except RuntimeError:
        pass
    
    db_type = os.getenv("DATABASE_TYPE")
    if not db_type:
        from dotenv import load_dotenv
        root_env = Path(__file__).resolve().parent.parent.parent / ".env"
        if root_env.exists():
            load_dotenv(root_env)
        db_type = os.getenv("DATABASE_TYPE", "")

    db_type = str(db_type or "").lower().strip()
    db_url = os.getenv("DATABASE_URL", "").strip()
    if db_type in ("postgres", "postgresql") or db_url.startswith("postgres"):
        return True
    return False


def get_postgres_connection() -> PostgresConnectionWrapper:
    """Establish and return a wrapped PostgreSQL connection."""
    if not PSYCOPG2_AVAILABLE:
        raise RuntimeError("psycopg2-binary is required for PostgreSQL. Run: pip install psycopg2-binary")
    
    url = os.getenv("DATABASE_URL")
    if url:
        raw_conn = psycopg2.connect(url)
    else:
        raw_conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            dbname=os.getenv("POSTGRES_DB", "veridoc_db"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            sslmode=os.getenv("POSTGRES_SSLMODE", "prefer")
        )
    return PostgresConnectionWrapper(raw_conn)


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


def get_db_connection(db_path: Optional[str] = None):
    """
    Establish a database connection.
    Connects to PostgreSQL if configured (DATABASE_TYPE=postgres or DATABASE_URL)
    unless an explicit custom SQLite file path or :memory: is provided for isolated unit tests.
    """
    # 1. Isolated pytest temporary database fixture override
    if db_path is not None:
        if db_path == ":memory:" or (db_path.endswith(".db") and os.path.basename(db_path) != "veridoc.db"):
            if db_path != ":memory:":
                os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            return conn

    try:
        if current_app:
            if current_app.config.get("DATABASE_TYPE") == "postgres" and (not db_path or os.path.basename(db_path) == "veridoc.db"):
                if is_postgres_configured():
                    return get_postgres_connection()
            if current_app.config.get("TESTING") or current_app.config.get("DATABASE_TYPE") == "sqlite":
                test_db = current_app.config.get("DATABASE_PATH")
                if test_db and os.path.basename(test_db) != "veridoc.db":
                    if test_db != ":memory:":
                        os.makedirs(os.path.dirname(os.path.abspath(test_db)), exist_ok=True)
                    conn = sqlite3.connect(test_db)
                    conn.row_factory = sqlite3.Row
                    conn.execute("PRAGMA foreign_keys = ON;")
                    return conn
    except RuntimeError:
        pass

    # 2. Production & Application Database: PostgreSQL when configured
    if is_postgres_configured():
        return get_postgres_connection()

    # 3. Default fallback: SQLite
    target_path = _resolve_db_path(db_path)
    if target_path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
        
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """
    Initialize schema and perform safe non-destructive migrations.
    Operates on PostgreSQL when configured; otherwise initializes SQLite.
    Safe to call multiple times (idempotent).
    """
    # Handle isolated unit test sqlite databases
    is_custom_test_db = False
    if db_path is not None and (os.path.basename(db_path) != "veridoc.db" or db_path == ":memory:"):
        is_custom_test_db = True
    try:
        if current_app:
            if current_app.config.get("DATABASE_TYPE") == "postgres" and (not db_path or os.path.basename(db_path) == "veridoc.db"):
                is_custom_test_db = False
            elif current_app.config.get("TESTING") or current_app.config.get("DATABASE_TYPE") == "sqlite":
                t_db = current_app.config.get("DATABASE_PATH")
                if t_db and os.path.basename(t_db) != "veridoc.db":
                    is_custom_test_db = True
    except RuntimeError:
        pass

    if not is_custom_test_db and is_postgres_configured():
        from backend.database.migrate_to_postgres import POSTGRES_DDL
        conn = get_postgres_connection()
        cur = conn.cursor()
        cur.execute(POSTGRES_DDL)
        conn.commit()
        conn.close()
        return

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

    # 5. AI API Usage & Cost Tracking Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT,
            applicant_id TEXT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt_tokens INTEGER,
            candidate_tokens INTEGER,
            total_tokens INTEGER,
            latency_ms INTEGER,
            status TEXT NOT NULL,
            estimated_cost REAL,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE,
            FOREIGN KEY (applicant_id) REFERENCES applicants (id) ON DELETE SET NULL
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_doc ON ai_usage_logs(document_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_applicant ON ai_usage_logs(applicant_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_status ON ai_usage_logs(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_provider ON ai_usage_logs(provider);")

    # Safe Schema Migrations for ai_usage_logs
    cursor.execute("PRAGMA table_info(ai_usage_logs);")
    usage_cols = {row["name"] for row in cursor.fetchall()}
    if "request_type" not in usage_cols:
        cursor.execute("ALTER TABLE ai_usage_logs ADD COLUMN request_type TEXT DEFAULT 'multimodal_extraction';")
    if "channel" not in usage_cols:
        cursor.execute("ALTER TABLE ai_usage_logs ADD COLUMN channel TEXT DEFAULT 'sdk';")

    # 6. Safe Schema Migrations for documents
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

    # 7. Safe Schema Migrations for applicants
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

    # 8. Safe backfill for legacy documents processed via Gemini before usage tracking table existed
    cursor.execute("SELECT COUNT(*) as count FROM ai_usage_logs;")
    if cursor.fetchone()["count"] == 0:
        cursor.execute("""
            SELECT id, applicant_id, extracted_fields, upload_timestamp 
            FROM documents 
            WHERE extracted_fields LIKE '%"provider": "gemini"%'
               OR extracted_fields LIKE '%"extraction_method": "ai_gemini"%'
        """)
        for d in cursor.fetchall():
            fields = {}
            try:
                fields = json.loads(d["extracted_fields"]) if d["extracted_fields"] else {}
            except Exception:
                pass
            p_meta = fields.get("provider_metadata", {})
            cursor.execute("""
                INSERT INTO ai_usage_logs (
                    document_id, applicant_id, provider, model,
                    prompt_tokens, candidate_tokens, total_tokens,
                    latency_ms, status, estimated_cost, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                d["id"],
                d["applicant_id"],
                p_meta.get("provider", "gemini"),
                p_meta.get("model", "gemini-3.5-flash-lite"),
                p_meta.get("prompt_tokens"),
                p_meta.get("candidate_tokens"),
                p_meta.get("total_tokens"),
                p_meta.get("latency_ms"),
                "success",
                p_meta.get("estimated_cost"),
                d["upload_timestamp"] or "2026-11-25 00:00:00"
            ))

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            user_id TEXT NOT NULL,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_access_event ON audit_access_logs(event_type);")

    # Document Type Definitions Catalog
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_type_definitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type_key TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            description TEXT,
            is_system BOOLEAN DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            source_origin TEXT DEFAULT 'system',
            icon TEXT DEFAULT 'file-text',
            tags TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_doc_type_key ON document_type_definitions(type_key);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_doc_type_category ON document_type_definitions(category);")

    # Safe Schema Migrations for document_type_definitions
    cursor.execute("PRAGMA table_info(document_type_definitions);")
    dt_cols = {row["name"] for row in cursor.fetchall()}
    if "rules_json" not in dt_cols:
        cursor.execute("ALTER TABLE document_type_definitions ADD COLUMN rules_json TEXT DEFAULT '{}';")

    # Pre-seed standard types if empty
    cursor.execute("SELECT COUNT(*) FROM document_type_definitions;")
    if cursor.fetchone()[0] == 0:
        standard_types = [
            ("pan", "Permanent Account Number Card", "identity", "Income Tax Department PAN Identity Card", 1, 1, "system", "id-card", '["identity", "kyc"]'),
            ("aadhaar", "Aadhaar Card", "identity", "Unique Identification Authority of India (UIDAI)", 1, 1, "system", "id-card", '["identity", "kyc"]'),
            ("passport", "Indian Passport", "identity", "Republic of India Travel & Identity Passport", 1, 1, "system", "id-card", '["identity", "kyc"]'),
            ("voter_id", "Elector Photo Identity Card", "identity", "Election Commission of India Voter ID", 1, 1, "system", "id-card", '["identity", "kyc"]'),
            ("driving_licence", "Motor Driving Licence", "identity", "State Transport Department Driving Licence", 1, 1, "system", "id-card", '["identity", "kyc"]'),
            ("salary_slip", "Salary Certificate / Payslip", "financial", "Monthly corporate employee payslip and earnings statement", 0, 1, "system", "file-text", '["financial"]'),
            ("bank_statement", "Bank Account Statement", "financial", "Official bank transaction ledger and account summary", 0, 1, "system", "file-text", '["financial"]'),
            ("commercial_invoice", "Commercial / Tax Invoice", "billing", "Itemized billing invoice with GSTIN and payment breakdown", 0, 1, "system", "file-text", '["billing"]'),
            ("tax_form_16", "Form 16 Tax Certificate", "tax", "Employer certificate of tax deducted at source (TDS)", 0, 1, "system", "file-text", '["tax"]'),
            ("utility_bill", "Utility / Electricity / Water Bill", "utility", "Recurring utility billing receipt for address verification", 0, 1, "system", "file-text", '["utility"]'),
            ("unknown", "Unclassified Document", "general", "Novel or unclassified document type requiring identification", 1, 1, "system", "file-text", '["general"]'),
        ]
        cursor.executemany("""
            INSERT OR IGNORE INTO document_type_definitions (
                type_key, display_name, category, description, is_system, is_active, source_origin, icon, tags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, standard_types)

    # Document Schemas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_schemas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_type_id INTEGER NOT NULL,
            version INTEGER DEFAULT 1,
            schema_name TEXT NOT NULL,
            attribute_definitions TEXT NOT NULL DEFAULT '[]',
            spatial_templates TEXT DEFAULT '{}',
            sample_count INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_schema_type ON document_schemas(document_type_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_schema_active ON document_schemas(is_active);")

    # Document Extracted Attributes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_extracted_attributes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL,
            attribute_key TEXT NOT NULL,
            attribute_label TEXT,
            data_type TEXT DEFAULT 'string',
            raw_value TEXT,
            normalized_value TEXT,
            confidence REAL DEFAULT 1.0,
            source_type TEXT DEFAULT 'discovered',
            extraction_method TEXT DEFAULT 'deterministic',
            page_number INTEGER DEFAULT 1,
            bounding_box TEXT DEFAULT '[]',
            is_verified BOOLEAN DEFAULT 1,
            is_deleted BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_attr_doc_id ON document_extracted_attributes(document_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_attr_key ON document_extracted_attributes(attribute_key);")

    # Applicant Triangulations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applicant_triangulations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            applicant_id TEXT UNIQUE,
            triangulation_status TEXT DEFAULT 'pending',
            consistency_score REAL DEFAULT 0.0,
            mapped_attributes TEXT DEFAULT '[]',
            conflicts_detected TEXT DEFAULT '[]',
            evidence_summary TEXT DEFAULT '{}',
            reviewed_by TEXT,
            reviewed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_triang_applicant ON applicant_triangulations(applicant_id);")

    # Comparison Rule Configurations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comparison_rule_configurations (
            id TEXT PRIMARY KEY,
            combination_key TEXT UNIQUE NOT NULL,
            document_types TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            active_version INTEGER DEFAULT 1,
            is_active BOOLEAN DEFAULT 1,
            created_by TEXT DEFAULT 'System',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_comp_rules_comb ON comparison_rule_configurations(combination_key);")

    # Comparison Rule Versions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comparison_rule_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            configuration_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            attribute_rules TEXT NOT NULL,
            ai_metadata TEXT DEFAULT '{}',
            published_by TEXT DEFAULT 'System',
            change_summary TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (configuration_id) REFERENCES comparison_rule_configurations(id) ON DELETE CASCADE,
            UNIQUE(configuration_id, version)
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_comp_rule_ver ON comparison_rule_versions(configuration_id, version);")

    # Benchmark Runs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS benchmark_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_run_name TEXT,
            dataset_name TEXT NOT NULL,
            pipeline_mode TEXT DEFAULT 'hybrid',
            model_name TEXT,
            document_count INTEGER DEFAULT 0,
            classification_accuracy REAL,
            precision_score REAL,
            recall_score REAL,
            f1_score REAL,
            mean_cer REAL,
            false_acceptance_rate REAL,
            false_rejection_rate REAL,
            avg_latency_ms REAL,
            total_tokens INTEGER,
            total_cost REAL,
            per_page_cost REAL,
            status TEXT DEFAULT 'completed',
            executed_by TEXT,
            results_summary TEXT DEFAULT '{}',
            metrics_json TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_benchmark_dataset ON benchmark_runs(dataset_name);")

    # API Keys
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash TEXT UNIQUE NOT NULL,
            key_prefix TEXT NOT NULL,
            name TEXT NOT NULL,
            permissions TEXT DEFAULT '["read", "write"]',
            rate_limit_rpm INTEGER DEFAULT 60,
            status TEXT DEFAULT 'active',
            last_used_at TIMESTAMP,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_status ON api_keys(status);")

    # Webhook Subscriptions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS webhook_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_url TEXT NOT NULL,
            secret_token TEXT NOT NULL,
            subscribed_events TEXT DEFAULT '["document.completed", "document.failed"]',
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Processing Jobs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processing_jobs (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            status TEXT DEFAULT 'queued',
            progress INTEGER DEFAULT 0,
            stage TEXT DEFAULT 'intake',
            attempt_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            error_message TEXT,
            result_summary TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON processing_jobs(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_doc ON processing_jobs(document_id);")

    # External Applicant Mappings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS external_applicant_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_system TEXT NOT NULL,
            external_applicant_ref TEXT NOT NULL,
            external_application_ref TEXT,
            applicant_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_system, external_applicant_ref)
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ext_appl_ref ON external_applicant_mappings(source_system, external_applicant_ref);")

    # Batch Submissions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS batch_submissions (
            id TEXT PRIMARY KEY,
            source_system TEXT,
            external_applicant_reference TEXT,
            external_application_reference TEXT,
            idempotency_key TEXT UNIQUE,
            applicant_id TEXT,
            status TEXT DEFAULT 'processing',
            total_documents INTEGER DEFAULT 0,
            accepted_documents INTEGER DEFAULT 0,
            failed_documents INTEGER DEFAULT 0,
            verification_status TEXT DEFAULT 'pending',
            results_summary TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_batch_idemp ON batch_submissions(idempotency_key);")

    # Batch Documents
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS batch_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            document_id TEXT,
            file_name TEXT,
            mime_type TEXT,
            specified_document_type TEXT,
            external_document_reference TEXT,
            status TEXT DEFAULT 'processing',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_batch_docs ON batch_documents(batch_id);")

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

    syn_condition = (
        "(a.id LIKE 'APPL-SYN-%' OR a.id LIKE 'APP-DEMO-%' OR a.id LIKE 'APP-TEST-%' "
        "OR a.id LIKE 'APP-GATE-%' OR a.id LIKE 'APPL-PG-VERIFY-%' OR a.id LIKE 'APPL-TEST-%' "
        "OR a.id LIKE 'APPL-EXP-%' OR a.id LIKE 'APPL-MULTI-%' OR a.id LIKE 'APPL-FINAL-%' "
        "OR LOWER(TRIM(COALESCE(a.name, ''))) IN ('placeholder', 'test placeholder', 'updated legal name', 'gate test applicant', 'consolidated applicant test'))"
    )
    where_clauses = []
    if dataset == "synthetic":
        where_clauses.append(syn_condition)
    elif dataset == "demo":
        where_clauses.append("a.id LIKE 'APP-DEMO-%'")
    elif dataset == "unclassified":
        where_clauses.append(f"(NOT {syn_condition} AND (a.name IS NULL OR TRIM(a.name) = ''))")
    elif dataset == "live":
        where_clauses.append(f"(NOT {syn_condition} AND a.name IS NOT NULL AND TRIM(a.name) != '')")

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
    result = []
    for r in rows:
        d = dict(r)
        raw_name = d.get("name")
        if not raw_name or not str(raw_name).strip():
            d["display_name"] = f"Provisional Applicant ({d['id']})"
            d["is_provisional"] = True
        else:
            d["display_name"] = str(raw_name).strip()
            d["is_provisional"] = False
        result.append(d)
    return result


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
    result = []
    for r in rows:
        d = dict(r)
        raw_name = d.get("name")
        if not raw_name or not str(raw_name).strip():
            d["display_name"] = f"Provisional Applicant ({d['id']})"
            d["is_provisional"] = True
        else:
            d["display_name"] = str(raw_name).strip()
            d["is_provisional"] = False
        result.append(d)
    return result


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
        
        # Mandatory >75% Confidence Threshold Gate
        confidence_data = cross.get("confidence") or {}
        overall_conf = float(confidence_data.get("overall_confidence", cross.get("consistency_score", 100.0)))
        if overall_conf <= 75.0:
            conn.close()
            blocking_reasons = confidence_data.get("blocking_reasons") or [f"Overall verification confidence is {overall_conf}%, which does not exceed the mandatory 75% threshold."]
            raise ValueError(f"Verification confidence is {overall_conf}%. The minimum required confidence is greater than 75%. Resolve outstanding issues before submitting: {'; '.join(blocking_reasons)}")

        # Mandatory Identity Validation Gate
        id_val = confidence_data.get("identity_validation") or {}
        if id_val.get("is_blocking"):
            conn.close()
            raise ValueError(f"Cannot mark applicant Verified: {id_val.get('message', 'Applicant Identity Mismatch detected between declared name and submitted KYC documents.')}")

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

    # Scope filtering conditions (authoritative operational vs synthetic/test)
    syn_app_cond = (
        "(id LIKE 'APPL-SYN-%' OR id LIKE 'APP-DEMO-%' OR id LIKE 'APP-TEST-%' "
        "OR id LIKE 'APP-GATE-%' OR id LIKE 'APPL-PG-VERIFY-%' OR id LIKE 'APPL-TEST-%' "
        "OR id LIKE 'APPL-EXP-%' OR id LIKE 'APPL-MULTI-%' OR id LIKE 'APPL-FINAL-%' "
        "OR LOWER(TRIM(COALESCE(name, ''))) IN ('placeholder', 'test placeholder', 'updated legal name', 'gate test applicant', 'consolidated applicant test'))"
    )
    live_app_cond = f"(NOT {syn_app_cond} AND name IS NOT NULL AND TRIM(name) != '')"
    doc_filter_clause = ""
    app_filter_clause = ""
    app_filter_and = ""
    if dataset == "synthetic":
        doc_filter_clause = f" WHERE applicant_id IN (SELECT id FROM applicants WHERE {syn_app_cond})"
        app_filter_clause = f" WHERE {syn_app_cond}"
        app_filter_and = f" AND applicant_id IN (SELECT id FROM applicants WHERE {syn_app_cond})"
    elif dataset == "demo":
        doc_filter_clause = " WHERE applicant_id LIKE 'APP-DEMO-%'"
        app_filter_clause = " WHERE id LIKE 'APP-DEMO-%'"
        app_filter_and = " AND applicant_id LIKE 'APP-DEMO-%'"
    elif dataset == "live":
        doc_filter_clause = f" WHERE applicant_id IN (SELECT id FROM applicants WHERE {live_app_cond})"
        app_filter_clause = f" WHERE {live_app_cond}"
        app_filter_and = f" AND applicant_id IN (SELECT id FROM applicants WHERE {live_app_cond})"

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
        recent_sql += f" WHERE d.applicant_id IN (SELECT id FROM applicants WHERE {syn_app_cond})"
    elif dataset == "demo":
        recent_sql += " WHERE d.applicant_id LIKE 'APP-DEMO-%'"
    elif dataset == "live":
        recent_sql += f" WHERE d.applicant_id IN (SELECT id FROM applicants WHERE {live_app_cond})"
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
        WHERE (d.review_status IN ('pending', 'manual_review', 'rejected', 'resubmission_requested')
           OR a.status IN ('requires_attention', 'rejected', 'manual_review'))
    """
    if dataset == "synthetic":
        attn_sql += f" AND d.applicant_id IN (SELECT id FROM applicants WHERE {syn_app_cond})"
    elif dataset == "demo":
        attn_sql += " AND d.applicant_id LIKE 'APP-DEMO-%'"
    elif dataset == "live":
        attn_sql += f" AND d.applicant_id IN (SELECT id FROM applicants WHERE {live_app_cond})"
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


def insert_ai_usage_log(entry: Dict[str, Any], db_path: Optional[str] = None) -> int:
    """
    Record an AI API request execution and token usage log linked to a document.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO ai_usage_logs (
            document_id, applicant_id, provider, model,
            prompt_tokens, candidate_tokens, total_tokens,
            latency_ms, status, estimated_cost, error_message,
            request_type, channel
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        entry.get("document_id"),
        entry.get("applicant_id"),
        entry.get("provider", "gemini"),
        entry.get("model", "gemini-3.5-flash-lite"),
        entry.get("prompt_tokens"),
        entry.get("candidate_tokens"),
        entry.get("total_tokens"),
        entry.get("latency_ms"),
        entry.get("status", "success"),
        entry.get("estimated_cost"),
        entry.get("error_message"),
        entry.get("request_type", "multimodal_extraction"),
        entry.get("channel", "sdk")
    ))
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_ai_usage_summary(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Retrieve aggregated AI usage and cost metrics for reporting and dashboard visibility.
    Excludes local fallback processing.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # 1. Document processing breakdown (Requirement 8 metrics 1-3)
    cursor.execute("""
        SELECT 
            COUNT(*) as total_docs,
            SUM(CASE WHEN processing_status = 'completed' THEN 1 ELSE 0 END) as total_processed,
            SUM(CASE WHEN (extracted_fields LIKE '%"provider": "gemini"%' OR extracted_fields LIKE '%"extraction_method": "ai_gemini"%') THEN 1 ELSE 0 END) as gemini_docs,
            SUM(CASE WHEN (extracted_fields NOT LIKE '%"provider": "gemini"%' AND extracted_fields NOT LIKE '%"extraction_method": "ai_gemini"%' OR extracted_fields IS NULL) AND processing_status = 'completed' THEN 1 ELSE 0 END) as local_docs
        FROM documents;
    """)
    doc_row = cursor.fetchone()
    total_processed = doc_row["total_processed"] if doc_row and doc_row["total_processed"] is not None else 0
    gemini_docs = doc_row["gemini_docs"] if doc_row and doc_row["gemini_docs"] is not None else 0
    local_docs = doc_row["local_docs"] if doc_row and doc_row["local_docs"] is not None else 0

    # 2. AI usage logs aggregation for Gemini (Requirement 8 metrics 4-11)
    cursor.execute("""
        SELECT 
            COUNT(*) as total_calls,
            COUNT(DISTINCT document_id) as gemini_documents_with_logs,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful_calls,
            SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as failed_calls,
            SUM(prompt_tokens) as total_prompt_tokens,
            SUM(candidate_tokens) as total_candidate_tokens,
            SUM(total_tokens) as total_tokens,
            SUM(estimated_cost) as total_cost,
            AVG(latency_ms) as avg_latency_ms
        FROM ai_usage_logs
        WHERE provider = 'gemini'
    """)
    row = cursor.fetchone()

    cursor.execute("""
        SELECT 
            u.id, u.document_id, u.applicant_id, u.provider, u.model,
            u.prompt_tokens, u.candidate_tokens, u.total_tokens,
            u.latency_ms, u.status, u.estimated_cost, u.error_message, u.created_at,
            u.channel, u.request_type,
            d.original_filename, d.document_type
        FROM ai_usage_logs u
        LEFT JOIN documents d ON u.document_id = d.id
        WHERE u.provider = 'gemini'
        ORDER BY u.id DESC
        LIMIT 25
    """)
    recent_logs = [dict(r) for r in cursor.fetchall()]
    conn.close()

    total_calls = row["total_calls"] if row and row["total_calls"] is not None else 0
    prompt_tokens = row["total_prompt_tokens"] if row and row["total_prompt_tokens"] is not None else 0
    cand_tokens = row["total_candidate_tokens"] if row and row["total_candidate_tokens"] is not None else 0
    tot_tokens = row["total_tokens"] if row and row["total_tokens"] is not None else 0
    cost_val = row["total_cost"]

    from backend.config import Config
    price_in = Config.GEMINI_PRICE_PER_M_INPUT_TOKENS
    price_out = Config.GEMINI_PRICE_PER_M_OUTPUT_TOKENS
    model = Config.GEMINI_MODEL

    return {
        "provider": "gemini",
        "model": model,
        "pricing": {
            "input_per_m": price_in,
            "output_per_m": price_out,
            "currency": "USD",
            "pricing_description": "Configurable estimated application accounting ($0.075 / 1M input, $0.300 / 1M output for Flash tier). Not an invoice from Google."
        },
        "metrics": {
            # 1. Total documents processed
            "total_documents_processed": total_processed,
            # 2. Gemini-processed documents
            "gemini_documents_count": gemini_docs,
            # 3. Locally processed documents
            "locally_processed_documents": local_docs,
            # 4. Total Gemini API calls
            "total_api_calls": total_calls,
            # 5. Successful API calls
            "successful_calls": row["successful_calls"] if row and row["successful_calls"] is not None else 0,
            # 6. Failed API calls
            "failed_calls": row["failed_calls"] if row and row["failed_calls"] is not None else 0,
            # 7. Total input tokens
            "total_prompt_tokens": prompt_tokens,
            # 8. Total output tokens
            "total_candidate_tokens": cand_tokens,
            # 9. Total tokens consumed
            "total_tokens": tot_tokens,
            # 10. Estimated cumulative API cost
            "estimated_total_cost": round(cost_val, 6) if cost_val is not None else None,
            "cost_available": cost_val is not None,
            # 11. Average API response latency
            "avg_latency_ms": round(row["avg_latency_ms"]) if row and row["avg_latency_ms"] is not None else None
        },
        "recent_logs": recent_logs
    }


def get_ai_usage_history(
    limit: int = 50,
    offset: int = 0,
    status_filter: Optional[str] = None,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieve paginated individual request-level AI usage records.
    Requirement 3 & 8: Historical audit ledger of individual API calls.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    where_clause = "WHERE u.provider = 'gemini'"
    params: List[Any] = []
    if status_filter and status_filter.lower() in ("success", "error"):
        where_clause += " AND u.status = ?"
        params.append(status_filter.lower())

    cursor.execute(f"SELECT COUNT(*) as total FROM ai_usage_logs u {where_clause}", tuple(params))
    total_count = cursor.fetchone()["total"]

    query = f"""
        SELECT 
            u.id, u.document_id, u.applicant_id, u.provider, u.model,
            u.prompt_tokens, u.candidate_tokens, u.total_tokens,
            u.latency_ms, u.status, u.estimated_cost, u.error_message, u.created_at,
            u.channel, u.request_type,
            d.original_filename, d.document_type
        FROM ai_usage_logs u
        LEFT JOIN documents d ON u.document_id = d.id
        {where_clause}
        ORDER BY u.id DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    cursor.execute(query, tuple(params))
    logs = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return {
        "logs": logs,
        "total_count": total_count,
        "limit": limit,
        "offset": offset
    }


def insert_audit_log(
    event_type: str,
    user_id: str,
    details: Optional[str] = None,
    db_path: Optional[str] = None
) -> int:
    """Record a security or access audit trail entry in audit_access_logs."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO audit_access_logs (event_type, user_id, details, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (event_type, user_id, details or "{}"))
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        logger.warning(f"insert_audit_log warning: {e}")
        return 0
    finally:
        conn.close()


def list_audit_access_logs(
    event_type: Optional[str] = None,
    limit: int = 50,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Retrieve security and document access audit logs."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        if event_type:
            cursor.execute("""
                SELECT * FROM audit_access_logs
                WHERE event_type = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (event_type, limit))
        else:
            cursor.execute("""
                SELECT * FROM audit_access_logs
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


# ==============================================================================
# Universal Document Repository & Schema Catalog Management
# ==============================================================================

def get_document_type(id_or_key: Any, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve document type definition by ID or type_key slug."""
    if not id_or_key:
        return None
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        if isinstance(id_or_key, int) or (isinstance(id_or_key, str) and id_or_key.isdigit()):
            cursor.execute("SELECT * FROM document_type_definitions WHERE id = ?", (int(id_or_key),))
        else:
            cursor.execute("SELECT * FROM document_type_definitions WHERE type_key = ?", (str(id_or_key).lower().strip(),))
        row = cursor.fetchone()
        if not row:
            return None
        dt = dict(row)
        if isinstance(dt.get("tags"), str):
            try:
                dt["tags"] = json.loads(dt["tags"])
            except Exception:
                dt["tags"] = []
        return dt
    finally:
        conn.close()


def list_document_types(
    active_only: bool = False,
    category: Optional[str] = None,
    source_origin: Optional[str] = None,
    search: Optional[str] = None,
    include_stats: bool = False,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """List cataloged document types with flexible filtering."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        conditions = []
        params = []
        if active_only:
            conditions.append("is_active = TRUE")
        if category and category.lower() != "all":
            conditions.append("LOWER(category) = ?")
            params.append(category.lower().strip())
        if source_origin and source_origin.lower() != "all":
            conditions.append("source_origin = ?")
            params.append(source_origin.strip())
        if search and search.strip():
            term = f"%{search.strip().lower()}%"
            conditions.append("(LOWER(type_key) LIKE ? OR LOWER(display_name) LIKE ? OR LOWER(description) LIKE ?)")
            params.extend([term, term, term])

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM document_type_definitions {where_clause} ORDER BY is_system DESC, display_name ASC"
        cursor.execute(query, tuple(params))
        results = [dict(r) for r in cursor.fetchall()]

        for r in results:
            if isinstance(r.get("tags"), str):
                try:
                    r["tags"] = json.loads(r["tags"])
                except Exception:
                    r["tags"] = []

        if include_stats:
            for r in results:
                # Count documents matching this type
                t_key = r.get("type_key")
                cursor.execute("""
                    SELECT COUNT(*) FROM documents
                    WHERE document_type = ? OR classified_type = ?
                """, (t_key, t_key))
                cnt = cursor.fetchone()[0]
                r["specimen_count"] = cnt
                r["document_count"] = cnt
                r["has_specimen"] = cnt > 0

                # Attribute count from active schema
                cursor.execute("""
                    SELECT attribute_definitions FROM document_schemas
                    WHERE document_type_id = ? AND is_active = TRUE
                    ORDER BY version DESC LIMIT 1
                """, (r["id"],))
                sch_row = cursor.fetchone()
                attr_count = 0
                if sch_row:
                    attrs = sch_row[0]
                    if isinstance(attrs, str):
                        try:
                            attrs = json.loads(attrs)
                        except Exception:
                            attrs = []
                    attr_count = len(attrs) if isinstance(attrs, list) else 0
                r["attribute_count"] = attr_count

        return results
    finally:
        conn.close()


def insert_document_type(doc_type_data: Dict[str, Any], db_path: Optional[str] = None) -> Dict[str, Any]:
    """Register a new document type definition."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        t_key = (doc_type_data.get("type_key") or doc_type_data.get("id") or "").lower().strip()
        tags_val = doc_type_data.get("tags", [])
        if isinstance(tags_val, (list, dict)):
            tags_val = json.dumps(tags_val)
        rules_val = doc_type_data.get("rules_json", {})
        if isinstance(rules_val, (list, dict)):
            rules_val = json.dumps(rules_val)

        cursor.execute("""
            INSERT INTO document_type_definitions (
                type_key, display_name, category, description,
                is_system, is_active, source_origin, icon, tags, rules_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (
            t_key,
            doc_type_data.get("display_name", t_key.replace("_", " ").title()),
            doc_type_data.get("category", "general"),
            doc_type_data.get("description", ""),
            True if doc_type_data.get("is_system") else False,
            True if doc_type_data.get("is_active", True) else False,
            doc_type_data.get("source_origin", "employee_created"),
            doc_type_data.get("icon", "file-text"),
            tags_val,
            rules_val,
        ))
        conn.commit()
        return get_document_type(t_key, db_path=db_path)
    finally:
        conn.close()


def update_document_type_definition(
    id_or_key: Any,
    update_data: Dict[str, Any],
    db_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Update metadata of an existing document type definition."""
    existing = get_document_type(id_or_key, db_path=db_path)
    if not existing:
        return None

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        fields = []
        params = []
        for col in ("display_name", "category", "description", "is_active", "icon", "source_origin"):
            if col in update_data:
                fields.append(f"{col} = ?")
                val = update_data[col]
                if col == "is_active":
                    val = 1 if val else 0
                params.append(val)
        if "tags" in update_data:
            fields.append("tags = ?")
            t_val = update_data["tags"]
            params.append(json.dumps(t_val) if isinstance(t_val, (list, dict)) else str(t_val))

        if fields:
            fields.append("updated_at = CURRENT_TIMESTAMP")
            params.append(existing["id"])
            cursor.execute(f"UPDATE document_type_definitions SET {', '.join(fields)} WHERE id = ?", tuple(params))
            conn.commit()

        return get_document_type(existing["id"], db_path=db_path)
    finally:
        conn.close()


def get_document_schema(
    doc_type_id_or_key: Any,
    version: Optional[int] = None,
    active_only: bool = False,
    db_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Retrieve document schema (active version or specific historical version)."""
    dt = get_document_type(doc_type_id_or_key, db_path=db_path)
    if not dt:
        return None

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        if version:
            cursor.execute("""
                SELECT * FROM document_schemas
                WHERE document_type_id = ? AND version = ?
            """, (dt["id"], int(version)))
        elif active_only:
            cursor.execute("""
                SELECT * FROM document_schemas
                WHERE document_type_id = ? AND (is_active = TRUE OR is_active = 1)
                ORDER BY version DESC LIMIT 1
            """, (dt["id"],))
        else:
            cursor.execute("""
                SELECT * FROM document_schemas
                WHERE document_type_id = ? AND (is_active = TRUE OR is_active = 1)
                ORDER BY version DESC LIMIT 1
            """, (dt["id"],))

        row = cursor.fetchone()
        if not row:
            # Fall back to highest version if no active schema
            cursor.execute("""
                SELECT * FROM document_schemas
                WHERE document_type_id = ?
                ORDER BY version DESC LIMIT 1
            """, (dt["id"],))
            row = cursor.fetchone()

        if not row:
            return None

        schema = dict(row)
        for json_col in ("attribute_definitions", "spatial_templates"):
            if isinstance(schema.get(json_col), str):
                try:
                    schema[json_col] = json.loads(schema[json_col])
                except Exception:
                    schema[json_col] = [] if json_col == "attribute_definitions" else {}
        return schema
    finally:
        conn.close()


def save_document_schema(
    doc_type_id_or_data: Any,
    schema_data: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """Save or update document schema, supporting either (doc_type_id, schema_data) or a single schema dict."""
    if isinstance(doc_type_id_or_data, dict):
        payload = doc_type_id_or_data
        doc_type_id = payload.get("document_type_id")
    else:
        doc_type_id = doc_type_id_or_data
        payload = schema_data or {}

    if not doc_type_id:
        raise ValueError("document_type_id is required to save document schema.")

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        version = payload.get("version", 1)
        name = payload.get("schema_name", f"Schema v{version}")
        attrs = payload.get("attribute_definitions", [])
        if isinstance(attrs, (list, dict)):
            attrs = json.dumps(attrs)
        spatial = payload.get("spatial_templates", {})
        if isinstance(spatial, (list, dict)):
            spatial = json.dumps(spatial)
        sample_count = payload.get("sample_count", 0)

        # Deactivate previous active schemas
        cursor.execute("UPDATE document_schemas SET is_active = 0 WHERE document_type_id = ?", (doc_type_id,))

        cursor.execute("""
            INSERT INTO document_schemas (
                document_type_id, version, schema_name, attribute_definitions,
                spatial_templates, sample_count, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (doc_type_id, version, name, attrs, spatial, sample_count))
        conn.commit()

        return get_document_schema(doc_type_id, version=version, db_path=db_path)
    finally:
        conn.close()


def publish_document_schema(
    doc_type_id_or_key: Any,
    schema_payload: Dict[str, Any],
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """Publish a new immutable version of a document type schema."""
    dt = get_document_type(doc_type_id_or_key, db_path=db_path)
    if not dt:
        raise ValueError(f"Document type '{doc_type_id_or_key}' not found.")

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT MAX(version) FROM document_schemas WHERE document_type_id = ?", (dt["id"],))
        max_ver = cursor.fetchone()[0] or 0
        new_version = max_ver + 1

        attrs = schema_payload.get("attribute_definitions", [])
        if isinstance(attrs, (list, dict)):
            attrs = json.dumps(attrs)
        spatial = schema_payload.get("spatial_templates", {})
        if isinstance(spatial, (list, dict)):
            spatial = json.dumps(spatial)
        name = schema_payload.get("schema_name") or f"{dt['display_name']} Schema v{new_version}"
        sample_cnt = schema_payload.get("sample_count", 0)

        # Deactivate existing active versions
        cursor.execute("UPDATE document_schemas SET is_active = 0 WHERE document_type_id = ?", (dt["id"],))

        cursor.execute("""
            INSERT INTO document_schemas (
                document_type_id, version, schema_name, attribute_definitions,
                spatial_templates, sample_count, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (dt["id"], new_version, name, attrs, spatial, sample_cnt))
        conn.commit()

        return get_document_schema(dt["id"], version=new_version, db_path=db_path)
    finally:
        conn.close()


def rollback_document_schema(
    doc_type_id_or_key: Any,
    target_version: int,
    db_path: Optional[str] = None
) -> bool:
    """Roll back active schema for a document type to a target version."""
    dt = get_document_type(doc_type_id_or_key, db_path=db_path)
    if not dt:
        return False

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id FROM document_schemas
            WHERE document_type_id = ? AND version = ?
        """, (dt["id"], int(target_version)))
        if not cursor.fetchone():
            return False

        cursor.execute("UPDATE document_schemas SET is_active = 0 WHERE document_type_id = ?", (dt["id"],))
        cursor.execute("""
            UPDATE document_schemas SET is_active = 1, updated_at = CURRENT_TIMESTAMP
            WHERE document_type_id = ? AND version = ?
        """, (dt["id"], int(target_version)))
        conn.commit()
        return True
    finally:
        conn.close()


def get_document_type_details(id_or_key: Any, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve full details for a document type including active schema and history."""
    dt = get_document_type(id_or_key, db_path=db_path)
    if not dt:
        return None

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        active_sch = get_document_schema(dt["id"], db_path=db_path)

        cursor.execute("""
            SELECT id, version, schema_name, sample_count, is_active, created_at
            FROM document_schemas
            WHERE document_type_id = ?
            ORDER BY version DESC
        """, (dt["id"],))
        history = [dict(r) for r in cursor.fetchall()]

        cursor.execute("""
            SELECT COUNT(*) FROM documents
            WHERE document_type = ? OR classified_type = ?
        """, (dt["type_key"], dt["type_key"]))
        specimen_count = cursor.fetchone()[0]

        attributes = active_sch.get("attribute_definitions", []) if active_sch else []

        return {
            **dt,
            "active_schema": active_sch,
            "schema": active_sch,
            "schema_history": history,
            "specimen_count": specimen_count,
            "document_count": specimen_count,
            "attributes": attributes,
            "attribute_count": len(attributes) if isinstance(attributes, list) else 0,
        }
    finally:
        conn.close()


def get_repository_stats(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve aggregate statistics for the Universal Document Repository."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM document_type_definitions;")
        total_types = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM document_type_definitions WHERE is_system = 1 OR is_system = TRUE;")
        system_types = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM document_type_definitions WHERE source_origin = 'ai_discovered';")
        ai_types = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM document_type_definitions WHERE source_origin = 'employee_created';")
        emp_types = cursor.fetchone()[0]

        cursor.execute("SELECT attribute_definitions FROM document_schemas WHERE is_active = 1 OR is_active = TRUE;")
        total_attrs = 0
        for row in cursor.fetchall():
            val = row[0]
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except Exception:
                    val = []
            if isinstance(val, list):
                total_attrs += len(val)

        cursor.execute("""
            SELECT COUNT(*) FROM documents
            WHERE processing_status = 'completed' OR review_status = 'verified'
        """)
        total_specimens = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM document_type_definitions WHERE is_active = 1 OR is_active = TRUE;")
        active_types = cursor.fetchone()[0]

        cursor.execute("""
            SELECT category, COUNT(*) as cnt
            FROM document_type_definitions
            GROUP BY category
            ORDER BY cnt DESC
        """)
        categories = {r[0]: r[1] for r in cursor.fetchall()}

        return {
            "total_document_types": total_types,
            "total_types": total_types,
            "active_types": active_types,
            "system_types": system_types,
            "ai_discovered_types": ai_types,
            "employee_created_types": emp_types,
            "total_attributes_mapped": total_attrs,
            "total_specimens": total_specimens,
            "categories": categories,
        }
    finally:
        conn.close()


def get_document_extracted_attributes(document_id: str, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve extracted attribute records for a document."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT * FROM document_extracted_attributes
            WHERE document_id = ? AND (is_deleted = 0 OR is_deleted = FALSE)
            ORDER BY page_number ASC, id ASC
        """, (document_id,))
        rows = [dict(r) for r in cursor.fetchall()]
        for r in rows:
            bbox = r.get("bounding_box")
            if isinstance(bbox, str):
                try:
                    bbox = json.loads(bbox)
                except Exception:
                    bbox = []
            if isinstance(bbox, dict):
                bbox = [
                    bbox.get("ymin", bbox.get("top", 0)),
                    bbox.get("xmin", bbox.get("left", 0)),
                    bbox.get("ymax", bbox.get("bottom", 0)),
                    bbox.get("xmax", bbox.get("right", 0))
                ]
            r["bounding_box"] = bbox if isinstance(bbox, list) else []
        return rows
    finally:
        conn.close()


def insert_extracted_attribute(attr_data: Dict[str, Any], db_path: Optional[str] = None) -> int:
    """Insert a single extracted attribute record."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        bbox = attr_data.get("bounding_box", [])
        if isinstance(bbox, (list, dict)):
            bbox = json.dumps(bbox)

        cursor.execute("""
            INSERT INTO document_extracted_attributes (
                document_id, attribute_key, attribute_label, data_type,
                raw_value, normalized_value, confidence, source_type,
                extraction_method, page_number, bounding_box, is_verified,
                is_deleted, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
        """, (
            attr_data.get("document_id"),
            attr_data.get("attribute_key"),
            attr_data.get("attribute_label"),
            attr_data.get("data_type", "string"),
            attr_data.get("raw_value"),
            attr_data.get("normalized_value"),
            float(attr_data.get("confidence", 1.0)),
            attr_data.get("source_type", "discovered"),
            attr_data.get("extraction_method", "deterministic"),
            int(attr_data.get("page_number", 1)),
            bbox,
            1 if attr_data.get("is_verified", True) else 0,
        ))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def insert_extracted_attributes_batch(
    document_id: str,
    attributes: List[Dict[str, Any]],
    db_path: Optional[str] = None
) -> int:
    """Persist a list of extracted attribute dictionaries for a document."""
    if not attributes:
        return 0
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    inserted_count = 0
    try:
        for attr in attributes:
            bbox = attr.get("bounding_box", [])
            if isinstance(bbox, (list, dict)):
                bbox = json.dumps(bbox)
            cursor.execute("""
                INSERT INTO document_extracted_attributes (
                    document_id, attribute_key, attribute_label, data_type,
                    raw_value, normalized_value, confidence, source_type,
                    extraction_method, page_number, bounding_box, is_verified,
                    is_deleted, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
            """, (
                document_id,
                attr.get("attribute_key") or attr.get("key"),
                attr.get("attribute_label") or attr.get("label") or (str(attr.get("attribute_key", "")).replace("_", " ").title()),
                attr.get("data_type", "string"),
                attr.get("raw_value") or attr.get("attribute_value") or str(attr.get("value", "")),
                attr.get("normalized_value") or attr.get("attribute_value") or str(attr.get("value", "")),
                float(attr.get("confidence", 1.0)),
                attr.get("source_type", "discovered"),
                attr.get("extraction_method", "deterministic"),
                int(attr.get("page_number", 1)),
                bbox,
                1 if attr.get("is_verified", True) else 0,
            ))
            inserted_count += 1
        conn.commit()
        return inserted_count
    finally:
        conn.close()


def update_extracted_attribute(
    attribute_id: int,
    updates: Dict[str, Any],
    db_path: Optional[str] = None
) -> bool:
    """Update an extracted attribute record."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        fields = []
        params = []
        for col in ("attribute_label", "data_type", "raw_value", "normalized_value", "confidence", "is_verified", "is_deleted"):
            if col in updates:
                fields.append(f"{col} = ?")
                val = updates[col]
                if col in ("is_verified", "is_deleted"):
                    val = 1 if val else 0
                params.append(val)
        if "bounding_box" in updates:
            fields.append("bounding_box = ?")
            bbox = updates["bounding_box"]
            params.append(json.dumps(bbox) if isinstance(bbox, (list, dict)) else str(bbox))

        if fields:
            params.append(attribute_id)
            cursor.execute(f"UPDATE document_extracted_attributes SET {', '.join(fields)} WHERE id = ?", tuple(params))
            conn.commit()
            return True
        return False
    finally:
        conn.close()


def get_applicant_triangulation(applicant_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve saved applicant triangulation record."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM applicant_triangulations WHERE applicant_id = ?", (applicant_id,))
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        for json_col in ("mapped_attributes", "conflicts_detected", "evidence_summary"):
            if isinstance(res.get(json_col), str):
                try:
                    res[json_col] = json.loads(res[json_col])
                except Exception:
                    pass
        matrix = res.get("mapped_attributes") if isinstance(res.get("mapped_attributes"), dict) else {}
        discrepancies = res.get("conflicts_detected") or []
        evidence = res.get("evidence_summary") or {}
        return {
            "applicant_id": applicant_id,
            "triangulation_matrix": matrix.get("matrix", matrix),
            "overall_status": res.get("triangulation_status", "pending"),
            "consistency_score": res.get("consistency_score", 0.0),
            "discrepancy_count": len(discrepancies) if isinstance(discrepancies, list) else 0,
            "discrepancies": discrepancies,
            "rule_configuration_id": evidence.get("rule_configuration_id"),
            "rule_version": evidence.get("rule_version", 1),
            "documents_analyzed": evidence.get("documents_analyzed", 0),
            "created_at": res.get("created_at"),
            "updated_at": res.get("updated_at"),
            "verified_by": res.get("reviewed_by"),
            "notes": evidence.get("notes"),
        }
    finally:
        conn.close()


def save_applicant_triangulation(
    applicant_id: str,
    payload: Dict[str, Any],
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """Persist or update applicant triangulation record."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        matrix = payload.get("triangulation_matrix") or {}
        mapped_attrs = json.dumps(matrix) if isinstance(matrix, (dict, list)) else str(matrix)
        discrepancies = payload.get("discrepancies") or []
        conflicts = json.dumps(discrepancies) if isinstance(discrepancies, (dict, list)) else str(discrepancies)
        evidence = {
            "rule_configuration_id": payload.get("rule_configuration_id"),
            "rule_version": payload.get("rule_version", 1),
            "documents_analyzed": payload.get("documents_analyzed", 0),
            "notes": payload.get("notes")
        }
        evidence_str = json.dumps(evidence)
        status = payload.get("overall_status", "pending")
        score = float(payload.get("consistency_score", 0.0))
        reviewed_by = payload.get("verified_by")

        cursor.execute("SELECT id FROM applicant_triangulations WHERE applicant_id = ?", (applicant_id,))
        existing = cursor.fetchone()
        if existing:
            cursor.execute("""
                UPDATE applicant_triangulations SET
                    triangulation_status = ?,
                    consistency_score = ?,
                    mapped_attributes = ?,
                    conflicts_detected = ?,
                    evidence_summary = ?,
                    reviewed_by = ?,
                    reviewed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE applicant_id = ?
            """, (status, score, mapped_attrs, conflicts, evidence_str, reviewed_by, applicant_id))
        else:
            cursor.execute("""
                INSERT INTO applicant_triangulations (
                    applicant_id, triangulation_status, consistency_score,
                    mapped_attributes, conflicts_detected, evidence_summary,
                    reviewed_by, reviewed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (applicant_id, status, score, mapped_attrs, conflicts, evidence_str, reviewed_by))
        conn.commit()

        return get_applicant_triangulation(applicant_id, db_path=db_path) or {}
    finally:
        conn.close()


# ==============================================================================
# Benchmark Runs Tracking
# ==============================================================================

def insert_benchmark_run(run_data: Dict[str, Any], db_path: Optional[str] = None) -> int:
    """Record an empirical benchmark evaluation run."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        metrics = run_data.get("metrics_json", {})
        if isinstance(metrics, (dict, list)):
            metrics = json.dumps(metrics)
        results = run_data.get("results_summary", {})
        if isinstance(results, (dict, list)):
            results = json.dumps(results)

        cursor.execute("""
            INSERT INTO benchmark_runs (
                test_run_name, dataset_name, pipeline_mode, model_name,
                document_count, classification_accuracy, precision_score,
                recall_score, f1_score, mean_cer, false_acceptance_rate,
                false_rejection_rate, avg_latency_ms, total_tokens, total_cost,
                per_page_cost, status, executed_by, results_summary, metrics_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            run_data.get("test_run_name") or run_data.get("dataset_name"),
            run_data.get("dataset_name", "synthetic_kyc"),
            run_data.get("pipeline_mode", "hybrid"),
            run_data.get("model_name", "gemini-3.5-flash-lite"),
            int(run_data.get("total_documents", run_data.get("document_count", 0))),
            float(run_data.get("accuracy", run_data.get("classification_accuracy", 1.0))),
            float(run_data.get("precision_score", 1.0)),
            float(run_data.get("recall_score", 1.0)),
            float(run_data.get("f1_score", 1.0)),
            float(run_data.get("avg_cer", run_data.get("mean_cer", 0.0))),
            float(run_data.get("false_acceptance_rate", 0.0)),
            float(run_data.get("false_rejection_rate", 0.0)),
            float(run_data.get("avg_latency_ms", 0.0)),
            int(run_data.get("total_tokens_used", run_data.get("total_tokens", 0))),
            float(run_data.get("estimated_cost_usd", run_data.get("total_cost", 0.0))),
            float(run_data.get("per_page_cost", 0.0)),
            run_data.get("status", "completed"),
            run_data.get("executed_by", "Benchmark Suite"),
            results,
            metrics,
        ))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def list_benchmark_runs(
    limit: int = 50,
    offset: int = 0,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Retrieve historical benchmark evaluation runs."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT * FROM benchmark_runs
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        rows = [dict(r) for r in cursor.fetchall()]
        for r in rows:
            for json_col in ("results_summary", "metrics_json"):
                if isinstance(r.get(json_col), str):
                    try:
                        r[json_col] = json.loads(r[json_col])
                    except Exception:
                        pass
        return rows
    finally:
        conn.close()


# ==============================================================================
# API Keys Authentication & Authorization
# ==============================================================================

def validate_api_key(api_key: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Validate raw API key string against stored SHA-256 key hash."""
    if not api_key or not isinstance(api_key, str):
        return None
    key_hash = hashlib.sha256(api_key.strip().encode("utf-8")).hexdigest()

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM api_keys WHERE key_hash = ? AND status = 'active'", (key_hash,))
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        cursor.execute("UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?", (res["id"],))
        conn.commit()

        if isinstance(res.get("permissions"), str):
            try:
                res["permissions"] = json.loads(res["permissions"])
            except Exception:
                res["permissions"] = []
        return res
    finally:
        conn.close()


def create_api_key(
    name: str,
    permissions: Optional[List[str]] = None,
    rate_limit_rpm: int = 60,
    db_path: Optional[str] = None
) -> Tuple[str, Dict[str, Any]]:
    """Generate and store a new machine-to-machine API key."""
    raw_key = f"vdoc_live_{uuid.uuid4().hex}"
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    key_prefix = raw_key[:14]
    perms = permissions or ["documents:read", "documents:write"]
    perms_json = json.dumps(perms)

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO api_keys (
                key_hash, key_prefix, name, permissions,
                rate_limit_rpm, status, created_at
            ) VALUES (?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)
        """, (key_hash, key_prefix, name, perms_json, rate_limit_rpm))
        conn.commit()

        cursor.execute("SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,))
        record = dict(cursor.fetchone())
        record["permissions"] = perms
        return raw_key, record
    finally:
        conn.close()


def list_api_keys(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """List API keys metadata (without exposing raw secrets)."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, key_prefix, name, permissions, rate_limit_rpm, status, last_used_at, expires_at, created_at FROM api_keys ORDER BY created_at DESC")
        rows = [dict(r) for r in cursor.fetchall()]
        for r in rows:
            if isinstance(r.get("permissions"), str):
                try:
                    r["permissions"] = json.loads(r["permissions"])
                except Exception:
                    r["permissions"] = []
        return rows
    finally:
        conn.close()


def revoke_api_key(key_id: int, db_path: Optional[str] = None) -> bool:
    """Revoke an active API key."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE api_keys SET status = 'revoked' WHERE id = ?", (key_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# ==============================================================================
# Webhook Subscriptions
# ==============================================================================

def create_webhook_subscription(
    target_url: str,
    secret_token: Optional[str] = None,
    subscribed_events: Optional[List[str]] = None,
    is_active: bool = True,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """Register a new webhook subscription endpoint."""
    token = secret_token or f"whsec_{uuid.uuid4().hex}"
    events = subscribed_events or ["document.completed", "document.failed", "job.completed"]
    events_json = json.dumps(events)

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO webhook_subscriptions (
                target_url, secret_token, subscribed_events, is_active, created_at
            ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (target_url, token, events_json, 1 if is_active else 0))
        conn.commit()

        cursor.execute("SELECT * FROM webhook_subscriptions WHERE id = ?", (cursor.lastrowid,))
        res = dict(cursor.fetchone())
        res["subscribed_events"] = events
        return res
    finally:
        conn.close()


def list_webhook_subscriptions(
    active_only: bool = True,
    event: Optional[str] = None,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """List webhook subscription endpoints."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        if active_only:
            cursor.execute("SELECT * FROM webhook_subscriptions WHERE is_active = 1 OR is_active = TRUE ORDER BY created_at DESC")
        else:
            cursor.execute("SELECT * FROM webhook_subscriptions ORDER BY created_at DESC")
        rows = [dict(r) for r in cursor.fetchall()]
        result = []
        for r in rows:
            if isinstance(r.get("subscribed_events"), str):
                try:
                    r["subscribed_events"] = json.loads(r["subscribed_events"])
                except Exception:
                    r["subscribed_events"] = []
            if event:
                if event in r.get("subscribed_events", []):
                    result.append(r)
            else:
                result.append(r)
        return result
    finally:
        conn.close()


def delete_webhook_subscription(subscription_id: int, db_path: Optional[str] = None) -> bool:
    """Delete a webhook subscription."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM webhook_subscriptions WHERE id = ?", (subscription_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# ==============================================================================
# Asynchronous Processing Jobs
# ==============================================================================

def create_processing_job(
    document_id: str,
    job_id: Optional[str] = None,
    status: str = "queued",
    stage: str = "intake",
    progress: int = 0,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """Initialize a new background processing job record."""
    clean_id = job_id or f"job_{uuid.uuid4().hex[:12]}"
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO processing_jobs (
                id, document_id, status, progress, stage, attempt_count,
                max_retries, error_message, result_summary, created_at
            ) VALUES (?, ?, ?, ?, ?, 0, 3, NULL, '{}', CURRENT_TIMESTAMP)
        """, (clean_id, document_id, status, progress, stage))
        conn.commit()
        return get_processing_job(clean_id, db_path=db_path)
    finally:
        conn.close()


def get_processing_job(job_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve processing job by ID."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM processing_jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        if isinstance(res.get("result_summary"), str):
            try:
                res["result_summary"] = json.loads(res["result_summary"])
            except Exception:
                pass
        return res
    finally:
        conn.close()


def update_processing_job(
    job_id: str,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    stage: Optional[str] = None,
    error_message: Optional[str] = None,
    result_summary: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None,
    **kwargs
) -> Optional[Dict[str, Any]]:
    """Update state machine progress and status for a processing job."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        fields = []
        params = []
        if status is not None:
            fields.append("status = ?")
            params.append(status)
            if status == "processing":
                fields.append("started_at = COALESCE(started_at, CURRENT_TIMESTAMP)")
            elif status in ("completed", "failed"):
                fields.append("completed_at = CURRENT_TIMESTAMP")
        if progress is not None:
            fields.append("progress = ?")
            params.append(int(progress))
        if stage is not None:
            fields.append("stage = ?")
            params.append(stage)
        if error_message is not None:
            fields.append("error_message = ?")
            params.append(error_message)
        if result_summary is not None:
            fields.append("result_summary = ?")
            params.append(json.dumps(result_summary) if isinstance(result_summary, (dict, list)) else str(result_summary))

        if fields:
            params.append(job_id)
            cursor.execute(f"UPDATE processing_jobs SET {', '.join(fields)} WHERE id = ?", tuple(params))
            conn.commit()

        return get_processing_job(job_id, db_path=db_path)
    finally:
        conn.close()


def claim_specific_job(job_id: str, db_path: Optional[str] = None) -> bool:
    """Atomically claim a specific job from queued to processing."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE processing_jobs 
            SET status = 'processing', started_at = CURRENT_TIMESTAMP, attempt_count = attempt_count + 1
            WHERE id = ? AND status = 'queued'
        """, (job_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def claim_next_queued_job(db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Atomically claim the next queued job."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM processing_jobs WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1")
        row = cursor.fetchone()
        if not row:
            return None
        job_id = row[0]
        if claim_specific_job(job_id, db_path=db_path):
            return get_processing_job(job_id, db_path=db_path)
        return None
    finally:
        conn.close()


def recover_stuck_jobs(timeout_seconds: int = 300, db_path: Optional[str] = None) -> Dict[str, int]:
    """Recover jobs that have stalled in processing state."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        # Re-queue recoverable jobs
        cursor.execute("""
            UPDATE processing_jobs
            SET status = 'queued', stage = 'recovered_requeued'
            WHERE status = 'processing' AND attempt_count < max_retries
        """)
        requeued = cursor.rowcount

        # Fail jobs that exceeded retries
        cursor.execute("""
            UPDATE processing_jobs
            SET status = 'failed', stage = 'failed',
                error_message = 'Job timed out and exceeded maximum retries'
            WHERE status = 'processing' AND attempt_count >= max_retries
        """)
        failed = cursor.rowcount
        conn.commit()
        return {"recovered": requeued, "failed": failed}
    finally:
        conn.close()


def list_pending_jobs(limit: int = 50, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """List jobs currently in queued or processing status."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT * FROM processing_jobs
            WHERE status IN ('queued', 'processing')
            ORDER BY created_at ASC
            LIMIT ?
        """, (limit,))
        rows = [dict(r) for r in cursor.fetchall()]
        for r in rows:
            if isinstance(r.get("result_summary"), str):
                try:
                    r["result_summary"] = json.loads(r["result_summary"])
                except Exception:
                    pass
        return rows
    finally:
        conn.close()


# ==============================================================================
# External System Applicants & Bulk Batch Ingestion
# ==============================================================================

def get_or_create_external_applicant(
    source_system: str,
    external_applicant_ref: str,
    external_application_ref: Optional[str] = None,
    applicant_name: Optional[str] = None,
    db_path: Optional[str] = None
) -> str:
    """Resolve internal applicant ID for an external core-banking applicant reference."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT applicant_id FROM external_applicant_mappings
            WHERE source_system = ? AND external_applicant_ref = ?
        """, (source_system, external_applicant_ref))
        row = cursor.fetchone()
        if row:
            appl_id = row[0]
            # Update name if provided and existing applicant is unnamed or placeholder
            if applicant_name and applicant_name.strip():
                cursor.execute("SELECT name FROM applicants WHERE id = ?", (appl_id,))
                cur_name_row = cursor.fetchone()
                if cur_name_row and (not cur_name_row[0] or is_placeholder_name(cur_name_row[0])):
                    cursor.execute("UPDATE applicants SET name = ? WHERE id = ?", (applicant_name.strip(), appl_id))
                    conn.commit()
            return appl_id

        # Generate new deterministic internal applicant ID
        digest = hashlib.sha256(f"{source_system}:{external_applicant_ref}".encode("utf-8")).hexdigest()[:8].upper()
        new_applicant_id = f"APPL-EXT-{digest}"

        # Insert internal applicant
        cursor.execute("""
            INSERT INTO applicants (id, name, status, risk_level, created_at)
            VALUES (?, ?, 'pending', 'low', CURRENT_TIMESTAMP)
        """, (new_applicant_id, applicant_name.strip() if applicant_name else None))

        # Insert mapping
        cursor.execute("""
            INSERT INTO external_applicant_mappings (
                source_system, external_applicant_ref, external_application_ref, applicant_id, created_at
            ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (source_system, external_applicant_ref, external_application_ref, new_applicant_id))
        conn.commit()

        return new_applicant_id
    finally:
        conn.close()


def create_batch_submission(batch_data: Dict[str, Any], db_path: Optional[str] = None) -> Dict[str, Any]:
    """Create a new batch ingestion tracking record."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        res_summary = batch_data.get("results_summary", {})
        if isinstance(res_summary, (dict, list)):
            res_summary = json.dumps(res_summary)

        cursor.execute("""
            INSERT INTO batch_submissions (
                id, source_system, external_applicant_reference,
                external_application_reference, idempotency_key,
                applicant_id, status, total_documents, accepted_documents,
                failed_documents, verification_status, results_summary,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (
            batch_data["id"],
            batch_data.get("source_system"),
            batch_data.get("external_applicant_reference"),
            batch_data.get("external_application_reference"),
            batch_data.get("idempotency_key"),
            batch_data.get("applicant_id"),
            batch_data.get("status", "processing"),
            int(batch_data.get("total_documents", 0)),
            int(batch_data.get("accepted_documents", 0)),
            int(batch_data.get("failed_documents", 0)),
            batch_data.get("verification_status", "pending"),
            res_summary,
        ))
        conn.commit()
        return get_batch_submission(batch_data["id"], db_path=db_path)
    finally:
        conn.close()


def get_batch_submission(id_or_idemp: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve batch submission record by Batch ID or Idempotency Key."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT * FROM batch_submissions
            WHERE id = ? OR idempotency_key = ?
        """, (id_or_idemp, id_or_idemp))
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        if isinstance(res.get("results_summary"), str):
            try:
                res["results_summary"] = json.loads(res["results_summary"])
            except Exception:
                pass
        return res
    finally:
        conn.close()


def update_batch_submission(
    batch_id: str,
    update_data: Dict[str, Any],
    db_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Update status, counters, or results of a batch submission."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        fields = []
        params = []
        for col in ("status", "accepted_documents", "failed_documents", "verification_status"):
            if col in update_data:
                fields.append(f"{col} = ?")
                params.append(update_data[col])
        if "results_summary" in update_data:
            fields.append("results_summary = ?")
            r_val = update_data["results_summary"]
            params.append(json.dumps(r_val) if isinstance(r_val, (dict, list)) else str(r_val))

        if fields:
            fields.append("updated_at = CURRENT_TIMESTAMP")
            params.append(batch_id)
            cursor.execute(f"UPDATE batch_submissions SET {', '.join(fields)} WHERE id = ?", tuple(params))
            conn.commit()

        return get_batch_submission(batch_id, db_path=db_path)
    finally:
        conn.close()


def insert_batch_document(doc_data: Dict[str, Any], db_path: Optional[str] = None) -> int:
    """Record an individual document item within a batch submission."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO batch_documents (
                batch_id, document_id, file_name, mime_type,
                specified_document_type, external_document_reference,
                status, error_message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            doc_data["batch_id"],
            doc_data.get("document_id"),
            doc_data.get("file_name"),
            doc_data.get("mime_type"),
            doc_data.get("specified_document_type"),
            doc_data.get("external_document_reference"),
            doc_data.get("status", "processing"),
            doc_data.get("error_message"),
        ))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_batch_documents(batch_id: str, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve all document records for a batch submission."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT * FROM batch_documents
            WHERE batch_id = ?
            ORDER BY id ASC
        """, (batch_id,))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()




