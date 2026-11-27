"""
Execute Migration 003 against PostgreSQL veridoc_db and verify zero data loss.
"""

import os
import sys
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(r"c:\Users\Sabarish\Projects\VeriDoc-AI\.env"))

conn = psycopg2.connect(
    host=os.getenv("POSTGRES_HOST", "localhost"),
    port=int(os.getenv("POSTGRES_PORT", 5432)),
    dbname=os.getenv("POSTGRES_DB", "veridoc_db"),
    user=os.getenv("POSTGRES_USER", "postgres"),
    password=os.getenv("POSTGRES_PASSWORD", "")
)
cur = conn.cursor()

# Record initial counts
initial_counts = {}
for tbl in ["applicants", "documents", "audit_reviews", "ai_usage_logs", "document_type_definitions"]:
    cur.execute(f"SELECT count(*) FROM {tbl};")
    initial_counts[tbl] = cur.fetchone()[0]

migration_sql = Path(r"c:\Users\Sabarish\Projects\VeriDoc-AI\backend\database\migrations\003_universal_platform_v2.sql").read_text(encoding="utf-8")
cur.execute(migration_sql)
conn.commit()

# Verify all tables in public schema
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    ORDER BY table_name;
""")
tables = [r[0] for r in cur.fetchall()]
print("ALL TABLES IN VERIDOC_DB POST-MIGRATION 003:", tables)

# Verify post-migration counts
post_counts = {}
for tbl in ["applicants", "documents", "audit_reviews", "ai_usage_logs", "document_type_definitions"]:
    cur.execute(f"SELECT count(*) FROM {tbl};")
    post_counts[tbl] = cur.fetchone()[0]

assert initial_counts == post_counts, f"Counts changed: {initial_counts} vs {post_counts}"
print("EXISTING RECORD COUNTS 100% PRESERVED:", post_counts)

# Check new columns in document_type_definitions
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'document_type_definitions';")
dt_cols = [r[0] for r in cur.fetchall()]
print("document_type_definitions columns:", dt_cols)
assert "source_origin" in dt_cols
assert "icon" in dt_cols

# Check new columns in ai_usage_logs
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'ai_usage_logs';")
ai_cols = [r[0] for r in cur.fetchall()]
print("ai_usage_logs columns:", ai_cols)
assert "page_number" in ai_cols
assert "per_page_estimated_cost" in ai_cols

conn.close()
print("MIGRATION 003 EXECUTED SUCCESSFULLY!")
