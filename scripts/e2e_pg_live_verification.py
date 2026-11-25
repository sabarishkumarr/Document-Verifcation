"""
VeriDoc AI — Live End-to-End Verification against PostgreSQL veridoc_db.
Executes real HTTP requests against the live Flask server (http://127.0.0.1:5000)
and validates end-to-end data persistence in PostgreSQL.
"""

import io
import json
import os
import sys
import uuid
from pathlib import Path
from dotenv import load_dotenv

# Load environment configuration from .env
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import urllib.request
import urllib.parse
import psycopg2
import fitz  # PyMuPDF

BASE_URL = "http://127.0.0.1:5000"

def log_step(name, status, details=""):
    badge = "[PASS]" if status else "[FAIL]"
    print(f"{badge} {name}")
    if details:
        print(f"       {details}")

def http_get(endpoint):
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        return resp.status, resp.read()

def http_post_json(endpoint, payload):
    url = f"{BASE_URL}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))

def http_post_multipart(endpoint, fields, files):
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = bytearray()
    
    for k, v in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode("utf-8"))
        body.extend(f"{v}\r\n".encode("utf-8"))
        
    for name, filename, content, mime in files:
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8"))
        body.extend(f"Content-Type: {mime}\r\n\r\n".encode("utf-8"))
        body.extend(content)
        body.extend(b"\r\n")
        
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    
    url = f"{BASE_URL}{endpoint}"
    req = urllib.request.Request(
        url,
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))

def generate_synthetic_pan():
    doc = fitz.open()
    page = doc.new_page(width=400, height=250)
    page.insert_text((50, 40), "INCOME TAX DEPARTMENT - GOVT. OF INDIA", fontsize=12)
    page.insert_text((50, 70), "Permanent Account Number Card", fontsize=10)
    page.insert_text((50, 100), "Name: VIKRAM ADITYA VERMA", fontsize=11)
    page.insert_text((50, 130), "Father's Name: SURESH CHANDRA VERMA", fontsize=10)
    page.insert_text((50, 160), "Date of Birth: 15/06/1988", fontsize=11)
    page.insert_text((50, 190), "PAN: ABCDE1234F", fontsize=14)
    page.insert_text((50, 220), "[SYNTHETIC TEST DOCUMENT FOR VERIFICATION]", fontsize=8)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes

def generate_synthetic_aadhaar():
    doc = fitz.open()
    page = doc.new_page(width=400, height=250)
    page.insert_text((50, 40), "UNIQUE IDENTIFICATION AUTHORITY OF INDIA", fontsize=11)
    page.insert_text((50, 65), "Government of India", fontsize=9)
    page.insert_text((50, 95), "Name: Vikram Aditya Verma", fontsize=12)
    page.insert_text((50, 125), "DOB: 15/06/1988", fontsize=11)
    page.insert_text((50, 150), "Gender: Male", fontsize=10)
    page.insert_text((50, 180), "Aadhaar No: 9876 5432 1098", fontsize=14)
    page.insert_text((50, 210), "Address: Flat 402, Lotus Towers, Bangalore 560001", fontsize=9)
    page.insert_text((50, 230), "[SYNTHETIC TEST DOCUMENT FOR VERIFICATION]", fontsize=8)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes

def run_e2e_verification():
    print("=" * 80)
    print("  VERIDOC AI — POST-MIGRATION END-TO-END VERIFICATION ON POSTGRESQL")
    print("=" * 80)

    # 1. Direct PostgreSQL Database Check
    try:
        pg_conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            dbname=os.getenv("POSTGRES_DB", "veridoc_db"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
        )
        cur = pg_conn.cursor()
        cur.execute("SELECT current_database(), current_user, version();")
        db_name, db_user, pg_ver = cur.fetchone()
        assert db_name == "veridoc_db"
        
        cur.execute("SELECT count(*) FROM applicants;")
        init_apps = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM documents;")
        init_docs = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM audit_reviews;")
        init_audits = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM ai_usage_logs;")
        init_usage = cur.fetchone()[0]
        
        log_step(
            "1. Direct PostgreSQL Connection & Active Database",
            True,
            f"Active DB: {db_name} | User: {db_user} | Initial records: {init_apps} applicants, {init_docs} documents, {init_audits} audits, {init_usage} ai_usage"
        )
    except Exception as e:
        log_step("1. Direct PostgreSQL Connection & Active Database", False, str(e))
        return False

    # 2. SQLite Database Preservation Check
    sqlite_prod = Path("backend/database/veridoc.db")
    sqlite_backup = Path("backend/database/backups/veridoc_backup_pre_postgres.db")
    preserved = sqlite_prod.exists() and sqlite_backup.exists()
    log_step(
        "2. Original SQLite & Backup Preservation",
        preserved,
        f"veridoc.db: {sqlite_prod.stat().st_size:,} bytes | backup: {sqlite_backup.stat().st_size:,} bytes"
    )

    # 3. Health & Dashboard Stats API
    status, health_bytes = http_get("/api/health")
    health = json.loads(health_bytes.decode())
    status, stats_bytes = http_get("/api/dashboard/stats")
    stats = json.loads(stats_bytes.decode())
    log_step(
        "3. Live Health & Dashboard Statistics API",
        status == 200 and stats.get("success") and health.get("success"),
        f"Backend Health: {health.get('message')} | Total Docs: {stats['data']['total_documents']} | Approved: {stats['data'].get('approved_count', 0)}"
    )

    # 4. Upload Synthetic KYC Documents
    app_id = f"APPL-PG-VERIFY-{uuid.uuid4().hex[:6].upper()}"
    pan_bytes = generate_synthetic_pan()
    aadhaar_bytes = generate_synthetic_aadhaar()

    upload_status, upload_res = http_post_multipart(
        "/api/documents/upload",
        {"applicant_id": app_id},
        [
            ("files", "synthetic_pan_vikram.pdf", pan_bytes, "application/pdf"),
            ("files", "synthetic_aadhaar_vikram.pdf", aadhaar_bytes, "application/pdf")
        ]
    )
    uploaded = upload_res.get("uploaded", [])
    assert len(uploaded) == 2
    pan_id = uploaded[0]["id"]
    aadhaar_id = uploaded[1]["id"]
    log_step(
        "4. Document Upload via Multipart API",
        upload_status == 201 and len(uploaded) == 2,
        f"Uploaded {len(uploaded)} documents for {app_id} (PAN ID: {pan_id[:8]}..., Aadhaar ID: {aadhaar_id[:8]}...)"
    )

    # 5. Process Pipeline (Classification + Extraction + Validation)
    p_status1, proc_pan = http_post_json(f"/api/documents/{pan_id}/process", {})
    p_data1 = proc_pan["data"]["result"]
    pan_type = p_data1["classification"]["classified_type"]
    pan_num = p_data1["extracted_fields"].get("id_number")
    pan_valid = p_data1["validation"]["is_valid"]

    p_status2, proc_aadhaar = http_post_json(f"/api/documents/{aadhaar_id}/process", {})
    p_data2 = proc_aadhaar["data"]["result"]
    aadhaar_type = p_data2["classification"]["classified_type"]
    aadhaar_num = p_data2["extracted_fields"].get("id_number")
    aadhaar_valid = p_data2["validation"]["is_valid"]

    extraction_ok = (
        pan_type == "pan" and pan_num == "ABCDE1234F" and pan_valid is True and
        aadhaar_type == "aadhaar" and "1098" in str(aadhaar_num) and aadhaar_valid is True
    )
    log_step(
        "5. Pipeline Extraction & Classification",
        extraction_ok,
        f"PAN: classified={pan_type}, number={pan_num}, valid={pan_valid} | Aadhaar: classified={aadhaar_type}, masked_id={aadhaar_num}, valid={aadhaar_valid}"
    )

    # 6. Cross-Document Matching within Same Applicant
    status, comp_bytes = http_get(f"/api/applicants/{app_id}")
    app_data = json.loads(comp_bytes.decode())["data"]
    comp = app_data.get("comparison_matrix", {})
    score = comp.get("consistency_score", 0)
    verdict = comp.get("overall_verdict")
    docs_compared = len(comp.get("documents", []))
    
    comp_ok = docs_compared == 2 and score >= 80 and verdict in ("VERIFIED", "MATCH")
    log_step(
        "6. Strict Single-Applicant Cross-Document Comparison",
        comp_ok,
        f"Applicant: {app_id} | Docs Compared: {docs_compared} | Score: {score}% | Verdict: {verdict}"
    )

    # 7. Verification Queue & Officer Review (Approve PAN)
    r_status, rev_res = http_post_json(
        f"/api/documents/{pan_id}/review",
        {
            "decision": "approved",
            "notes": "Verified against physical card copy in handover audit",
            "officer_name": "Chief Compliance Officer",
            "edited_fields": {
                "name": "Vikram Aditya Verma"
            }
        }
    )
    rev_ok = r_status == 200 and rev_res["data"]["review"]["review_status"] == "approved"
    log_step(
        "7. Verification Queue Review (Approve Document)",
        rev_ok,
        f"Document {pan_id[:8]}... review status: {rev_res['data']['review']['review_status']} | Officer: Chief Compliance Officer"
    )

    # 8. Verification Queue Review (Reject / Request Resubmission test on Aadhaar)
    r_status2, rev_res2 = http_post_json(
        f"/api/documents/{aadhaar_id}/review",
        {
            "decision": "resubmission_requested",
            "notes": "Please provide front and back copy",
            "officer_name": "Chief Compliance Officer"
        }
    )
    resub_ok = r_status2 == 200 and rev_res2["data"]["review"]["review_status"] == "resubmission_requested"
    log_step(
        "8. Verification Queue Review (Resubmission Requested)",
        resub_ok,
        f"Document {aadhaar_id[:8]}... review status: {rev_res2['data']['review']['review_status']}"
    )

    # 9. Audit History Persistence
    status, audit_bytes = http_get(f"/api/documents/{pan_id}/history")
    audit_data = json.loads(audit_bytes.decode())["data"]
    audit_ok = len(audit_data.get("reviews", [])) >= 1
    log_step(
        "9. Document Audit Trail Endpoint",
        audit_ok,
        f"Audit entries for {pan_id[:8]}...: {len(audit_data.get('reviews', []))} review logs found"
    )

    # 10. Reports Summary & AI Usage
    status, rep_bytes = http_get("/api/reports/summary")
    reports = json.loads(rep_bytes.decode())["data"]
    status, ai_bytes = http_get("/api/reports/ai-usage")
    ai_usage = json.loads(ai_bytes.decode())["data"]

    rep_ok = reports["total_documents"] >= init_docs + 2
    log_step(
        "10. Compliance Reports & AI Usage Endpoints",
        rep_ok,
        f"Report Total Docs: {reports['total_documents']} | AI Total Calls: {ai_usage.get('total_api_calls', 0)} | Total Cost: ${ai_usage.get('total_estimated_cost_usd', 0):.4f}"
    )

    # 11. Report and Matrix File Downloads (XLSX and CSV)
    s_xlsx, d_xlsx = http_get("/api/reports/download?format=xlsx")
    s_csv, d_csv = http_get("/api/reports/download?format=csv")
    s_m_xlsx, d_m_xlsx = http_get(f"/api/applicants/{app_id}/comparison/export?format=xlsx")
    s_m_csv, d_m_csv = http_get(f"/api/applicants/{app_id}/comparison/export?format=csv")

    export_ok = (
        s_xlsx == 200 and len(d_xlsx) > 1000 and
        s_csv == 200 and b"Applicant ID" in d_csv and
        s_m_xlsx == 200 and len(d_m_xlsx) > 1000 and
        s_m_csv == 200 and b"Comparison Result" in d_m_csv
    )
    log_step(
        "11. Excel (.xlsx) & CSV Matrix/Report Downloads",
        export_ok,
        f"Report XLSX: {len(d_xlsx):,} bytes | Report CSV: {len(d_csv):,} bytes | Matrix XLSX: {len(d_m_xlsx):,} bytes"
    )

    # 12. Direct PostgreSQL Post-Verification Audit (Row Parity & FK Integrity)
    cur.execute("SELECT count(*) FROM applicants;")
    post_apps = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM documents;")
    post_docs = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM audit_reviews;")
    post_audits = cur.fetchone()[0]

    cur.execute("SELECT id, name, status FROM applicants WHERE id = %s;", (app_id,))
    app_row = cur.fetchone()

    cur.execute("SELECT id, document_type, processing_status, review_status FROM documents WHERE applicant_id = %s;", (app_id,))
    doc_rows = cur.fetchall()

    cur.execute("SELECT decision, officer_name, notes FROM audit_reviews WHERE document_id = %s;", (pan_id,))
    pan_audit_rows = cur.fetchall()

    pg_persistence_ok = (
        post_apps == init_apps + 1 and
        post_docs == init_docs + 2 and
        post_audits == init_audits + 2 and
        app_row is not None and
        len(doc_rows) == 2 and
        len(pan_audit_rows) >= 1
    )
    log_step(
        "12. Direct PostgreSQL Persistence Audit",
        pg_persistence_ok,
        f"Applicants: {init_apps} -> {post_apps} | Documents: {init_docs} -> {post_docs} | Audit Reviews: {init_audits} -> {post_audits}"
    )

    pg_conn.close()

    print("=" * 80)
    all_passed = all([
        preserved, health.get("success") is True, upload_status == 201,
        extraction_ok, comp_ok, rev_ok, resub_ok, audit_ok, rep_ok, export_ok, pg_persistence_ok
    ])
    if all_passed:
        print("  ALL VERIFICATION CHECKS PASSED SUCCESSFULLY ON POSTGRESQL veridoc_db!")
    else:
        print("  ONE OR MORE VERIFICATION CHECKS FAILED.")
    print("=" * 80)
    return all_passed

if __name__ == "__main__":
    success = run_e2e_verification()
    sys.exit(0 if success else 1)
