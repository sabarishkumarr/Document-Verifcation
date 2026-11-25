import io
import csv
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from flask import Blueprint, request, current_app, Response
from backend.database.db import get_db_connection
from backend.services.comparator import CrossDocumentComparator
from backend.services.matrix_exporter import export_reports_summary_to_xlsx
from backend.utils.helpers import format_response

reports_bp = Blueprint("reports", __name__, url_prefix="/api/reports")


def generate_kyc_report_data(db_path: Optional[str] = None, dataset: Optional[str] = None) -> Dict[str, Any]:
    """Compile comprehensive verification audit report across applicants in SQLite."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    where_app = ""
    where_doc = ""
    if dataset == "synthetic":
        where_app = " WHERE id LIKE 'APPL-SYN-%'"
        where_doc = " WHERE applicant_id LIKE 'APPL-SYN-%'"
    elif dataset == "demo":
        where_app = " WHERE id LIKE 'APP-DEMO-%'"
        where_doc = " WHERE applicant_id LIKE 'APP-DEMO-%'"
    elif dataset == "live":
        where_app = " WHERE (id NOT LIKE 'APPL-SYN-%' AND id NOT LIKE 'APP-DEMO-%')"
        where_doc = " WHERE (applicant_id NOT LIKE 'APPL-SYN-%' AND applicant_id NOT LIKE 'APP-DEMO-%')"

    cursor.execute(f"SELECT * FROM applicants{where_app} ORDER BY id ASC")
    applicants_raw = [dict(r) for r in cursor.fetchall()]

    report_applicants = []
    category_counts = {"pan": 0, "aadhaar": 0, "passport": 0, "voter_id": 0, "driving_licence": 0, "unknown": 0}
    total_processed_docs = 0
    total_failed_docs = 0

    outcome_counts = {
        "verified": 0,
        "pending_review": 0,
        "requires_attention": 0,
        "expired_documents": 0,
        "missing_mandatory_fields": 0,
        "cross_document_discrepancies": 0
    }

    for app in applicants_raw:
        app_id = app["id"]
        cursor.execute("SELECT * FROM documents WHERE applicant_id = ?", (app_id,))
        docs = [dict(r) for r in cursor.fetchall()]

        hydrated_docs = []
        doc_types = set()
        seen_types = set()

        for d in docs:
            dtype = (d.get("classified_type") or d.get("document_type") or "unknown").lower()
            doc_types.add(dtype)

            # Category aggregation
            if dtype in category_counts:
                category_counts[dtype] += 1
            else:
                category_counts["unknown"] += 1

            if d.get("processing_status") == "failed":
                total_failed_docs += 1
            else:
                total_processed_docs += 1

            fields = {}
            if d.get("extracted_fields"):
                try:
                    fields = json.loads(d["extracted_fields"]) if isinstance(d["extracted_fields"], str) else d["extracted_fields"]
                except Exception:
                    pass
            d["extracted_fields"] = fields

            val = {}
            if d.get("validation_results"):
                try:
                    val = json.loads(d["validation_results"]) if isinstance(d["validation_results"], str) else d["validation_results"]
                except Exception:
                    pass
            d["validation_results"] = val

            # For cross-document comparison, take latest per distinct document category
            if dtype not in seen_types or dtype == "unknown":
                seen_types.add(dtype)
                hydrated_docs.append(d)

        # Cross-document identity comparison & deterministic validity checks strictly for this applicant
        cross = CrossDocumentComparator.compare_applicant_documents(
            hydrated_docs,
            applicant_name=app.get("name"),
            applicant_id=app_id
        )
        consistency_score = cross.get("consistency_score", 100)
        cross_verdict = cross.get("overall_verdict", "VERIFIED")

        # Clean, non-redundant system validation issues (excluding repeated officer rejection flags)
        system_issues = []
        for disc in cross.get("discrepancies", []):
            if "rejected by review officer" not in disc.lower() and disc not in system_issues:
                system_issues.append(disc)

        # Collect document-level validation flags & affected documents
        affected_docs = []
        for d in docs:
            d_val = d.get("validation_results") or {}
            d_flags = d_val.get("flags") or []
            for f in d_flags:
                f_str = str(f).strip()
                if f_str and f_str not in system_issues and "rejected by review officer" not in f_str.lower():
                    system_issues.append(f_str)
            is_affected = bool(d_flags) or d.get("review_status") in ("manual_review", "rejected", "resubmission_requested")
            if is_affected:
                affected_docs.append({
                    "id": d["id"],
                    "filename": d.get("original_filename"),
                    "type": (d.get("classified_type") or d.get("document_type") or "unknown").upper(),
                    "status": d.get("review_status"),
                    "flags": d_flags
                })

        # Track outcome breakdown
        if cross_verdict == "VERIFIED":
            outcome_counts["verified"] += 1
        elif cross_verdict == "PENDING_ADDITIONAL_DOCS":
            outcome_counts["pending_review"] += 1
        else:
            outcome_counts["requires_attention"] += 1

        for d_str in system_issues:
            dl = d_str.lower()
            if "expired" in dl:
                outcome_counts["expired_documents"] += 1
            if "missing" in dl or "mandatory" in dl:
                outcome_counts["missing_mandatory_fields"] += 1
            if "mismatch" in dl or "variation" in dl or "conflict" in dl:
                outcome_counts["cross_document_discrepancies"] += 1

        # Synthesize ONE clean primary reason
        app_status = (app.get("status") or "pending").lower()
        officer_notes = (app.get("notes") or "").strip()
        has_expired = any("expired" in str(s).lower() for s in system_issues)
        has_mismatch = any(kw in str(s).lower() for s in system_issues for kw in ("mismatch", "differs", "variation", "conflict"))
        has_missing = any(kw in str(s).lower() for s in system_issues for kw in ("missing", "not detected", "not found"))

        if app_status == "rejected":
            if has_expired and has_mismatch:
                primary_issue = "Rejected — Expired document and identity mismatch"
            elif has_expired:
                exp_str = next((s for s in system_issues if "expired" in str(s).lower()), "Expired Document")
                if "driving licence" in exp_str.lower():
                    primary_issue = "Rejected — Expired Driving Licence"
                elif "passport" in exp_str.lower():
                    primary_issue = "Rejected — Expired Passport"
                else:
                    primary_issue = "Rejected — Expired Document"
            elif has_mismatch:
                primary_issue = "Rejected — Identity mismatch across documents"
            elif officer_notes:
                short_note = officer_notes.split(".")[0].strip()
                if len(short_note) > 42:
                    short_note = short_note[:39] + "..."
                primary_issue = f"Rejected — {short_note}"
            else:
                primary_issue = "Rejected by review officer"

        elif app_status in ("requires_attention", "manual_review"):
            if has_expired and has_mismatch:
                primary_issue = "Expired document and identity mismatch"
            elif has_expired:
                exp_str = next((s for s in system_issues if "expired" in str(s).lower()), "Expired Document")
                if "driving licence" in exp_str.lower():
                    primary_issue = "Expired Driving Licence"
                elif "passport" in exp_str.lower():
                    primary_issue = "Expired Passport"
                else:
                    primary_issue = "Expired Document"
            elif has_mismatch:
                primary_issue = "Name/DOB mismatch detected"
            elif has_missing:
                primary_issue = "Missing mandatory field information"
            elif system_issues:
                primary_issue = system_issues[0]
            elif officer_notes:
                primary_issue = officer_notes.split(".")[0].strip()
            else:
                primary_issue = "Requires officer attention"

        elif app_status in ("verified", "approved"):
            primary_issue = "No discrepancies found"

        else:
            primary_issue = "Pending secondary review"

        report_applicants.append({
            "id": app_id,
            "name": app.get("name", "Unknown Applicant"),
            "status": app.get("status", "pending"),
            "verdict": cross_verdict,
            "risk_level": app.get("risk_level", "low"),
            "doc_count": len(docs),
            "doc_types": sorted(list(doc_types)),
            "consistency_score": consistency_score,
            "primary_issue": primary_issue,
            "validation_issues": system_issues,
            "officer_remarks": officer_notes,
            "affected_doc_count": len(affected_docs),
            "affected_docs": affected_docs,
            "discrepancies": system_issues if system_issues else ([primary_issue] if app_status == "rejected" else []),
            "comparison_matrix": cross.get("matrix"),
            "notes": officer_notes,
            "created_at": app.get("created_at")
        })

    cursor.execute(f"SELECT COUNT(*) FROM documents{where_doc}")
    total_docs = cursor.fetchone()[0]
    total_apps = len(report_applicants)
    verified_apps = sum(1 for a in report_applicants if a["status"] == "verified" and a["verdict"] == "VERIFIED")
    attention_apps = sum(1 for a in report_applicants if a["status"] == "requires_attention" or a["verdict"] in ("DISCREPANCY_FLAGGED", "MANUAL_REVIEW"))
    pending_apps = total_apps - verified_apps - attention_apps

    conn.close()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_scope": dataset or "all",
        "total_applicants": total_apps,
        "total_documents": total_docs,
        "verified_applicants": verified_apps,
        "attention_applicants": attention_apps,
        "pending_applicants": max(0, pending_apps),
        "processed_documents": total_processed_docs,
        "failed_documents": total_failed_docs,
        "category_breakdown": category_counts,
        "outcome_summary": outcome_counts,
        "applicants": report_applicants
    }


@reports_bp.route("/summary", methods=["GET"])
def get_reports_summary():
    """Retrieve structured KYC verification audit data for compliance dashboard."""
    db_path = current_app.config.get("DATABASE_PATH")
    dataset = request.args.get("dataset", "all").lower()
    report_data = generate_kyc_report_data(db_path=db_path, dataset=dataset)
    return format_response(
        success=True,
        message="KYC compliance report summary compiled successfully.",
        data=report_data
    )


@reports_bp.route("/download", methods=["GET"])
def download_report():
    """Download system KYC verification report as Excel XLSX, CSV, or JSON."""
    export_format = request.args.get("format", "csv").lower()
    dataset = request.args.get("dataset", "all").lower()
    suffix = f"_{dataset}" if dataset and dataset != "all" else ""
    db_path = current_app.config.get("DATABASE_PATH")
    report_data = generate_kyc_report_data(db_path=db_path, dataset=dataset)

    if export_format in ("xlsx", "excel"):
        xlsx_bytes = export_reports_summary_to_xlsx(report_data)
        return Response(
            xlsx_bytes,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=veridoc_kyc_compliance_report{suffix}.xlsx"
            }
        )

    if export_format == "json":
        json_str = json.dumps(report_data, indent=2)
        return Response(
            json_str,
            mimetype="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=veridoc_kyc_verification_report{suffix}.json"
            }
        )

    # Default to CSV export
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")

    # CSV Header
    writer.writerow([
        "Applicant ID",
        "Applicant Name",
        "Verification Status",
        "Cross-Check Verdict",
        "Risk Level",
        "Document Count",
        "Document Types",
        "Consistency Score (%)",
        "Discrepancies / Flags",
        "Notes",
        "Created At"
    ])

    for a in report_data["applicants"]:
        writer.writerow([
            a["id"],
            a["name"],
            a["status"],
            a.get("verdict", "PENDING"),
            a["risk_level"],
            a["doc_count"],
            ", ".join(a["doc_types"]),
            f"{a['consistency_score']}%",
            "; ".join(a["discrepancies"]) if a["discrepancies"] else "Passed all validations",
            a["notes"],
            a["created_at"] or ""
        ])

    csv_data = output.getvalue()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=veridoc_kyc_verification_report{suffix}.csv"
        }
    )
