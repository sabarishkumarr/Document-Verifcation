"""
Execute Migration 002 against PostgreSQL veridoc_db.
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
for tbl in ["applicants", "documents", "audit_reviews", "ai_usage_logs"]:
    cur.execute(f"SELECT count(*) FROM {tbl};")
    initial_counts[tbl] = cur.fetchone()[0]

migration_sql = Path(r"c:\Users\Sabarish\Projects\VeriDoc-AI\backend\database\migrations\002_universal_platform.sql").read_text(encoding="utf-8")
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
print("ALL TABLES IN VERIDOC_DB:", tables)

# Verify seeded document types
cur.execute("SELECT type_key, display_name, category, is_system FROM document_type_definitions ORDER BY id;")
seeded = cur.fetchall()
print(f"SEEDED DOCUMENT TYPES: {len(seeded)}")
for s in seeded:
    print(f"  - {s[0]}: {s[1]} ({s[2]}, system={s[3]})")

# Verify post migration counts for existing tables
post_counts = {}
for tbl in ["applicants", "documents", "audit_reviews", "ai_usage_logs"]:
    cur.execute(f"SELECT count(*) FROM {tbl};")
    post_counts[tbl] = cur.fetchone()[0]

assert initial_counts == post_counts, f"Counts changed: {initial_counts} vs {post_counts}"
print("EXISTING RECORD COUNTS COMPLETELY PRESERVED:", post_counts)
conn.close()
