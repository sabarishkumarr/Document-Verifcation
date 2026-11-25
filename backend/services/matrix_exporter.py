"""
Matrix Exporter for VeriDoc AI.
Generates genuine Excel XLSX workbooks and CSV files from the applicant comparison matrix.
"""

import io
import csv
from datetime import datetime
from typing import Dict, Any, List
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


def export_comparison_matrix_to_xlsx(matrix_data: Dict[str, Any]) -> bytes:
    """
    Generate a styled, presentation-ready Excel spreadsheet (.xlsx) 
    representing the applicant's cross-document verification matrix.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "KYC Verification Matrix"

    # Styling definitions
    font_title = Font(name="Calibri", size=16, bold=True, color="0F172A")
    font_subtitle = Font(name="Calibri", size=11, italic=True, color="64748B")
    font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    font_bold = Font(name="Calibri", size=11, bold=True, color="0F172A")
    font_regular = Font(name="Calibri", size=11, color="1E293B")
    font_muted = Font(name="Calibri", size=10, italic=True, color="94A3B8")

    fill_header = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    fill_match = PatternFill(start_color="EDF4EE", end_color="EDF4EE", fill_type="solid")  # soft green
    fill_mismatch = PatternFill(start_color="F9EFEB", end_color="F9EFEB", fill_type="solid")  # soft red
    fill_warn = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")  # soft amber
    fill_na = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")  # soft gray

    thin_border = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"),
        bottom=Side(style="thin", color="E2E8F0")
    )

    # 1. Header Information Block
    ws.merge_cells("A1:G1")
    ws["A1"] = "VERIDOC AI — APPLICANT IDENTITY VERIFICATION MATRIX"
    ws["A1"].font = font_title
    ws["A1"].alignment = Alignment(vertical="center")

    applicant_name = matrix_data.get("applicant_name") or "Applicant"
    applicant_id = matrix_data.get("applicant_id") or "N/A"
    verdict = matrix_data.get("overall_verdict") or "PENDING"
    score = matrix_data.get("consistency_score", 0.0)

    ws.merge_cells("A2:G2")
    ws["A2"] = f"Applicant: {applicant_name} ({applicant_id})  |  Verification Verdict: {verdict}  |  Consistency Score: {score}%"
    ws["A2"].font = font_subtitle
    ws["A2"].alignment = Alignment(vertical="center")

    ws.append([])  # Blank row 3

    # 2. Matrix Table Headers
    docs = matrix_data.get("documents", [])
    headers = ["Attribute"]
    for d in docs:
        label = d.get("type_label") or d.get("document_type", "Document").replace("_", " ").title()
        fname = d.get("filename") or ""
        headers.append(f"{label}\n({fname})")
    headers.extend(["Comparison Result", "Audit & Discrepancy Explanation"])

    ws.append(headers)
    header_row_idx = 4

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=header_row_idx, column=col_idx)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
    ws.row_dimensions[header_row_idx].height = 36

    # 3. Populate Rows
    rows = matrix_data.get("rows", [])
    for row_info in rows:
        attr_label = row_info.get("attribute_label", "Attribute")
        values = row_info.get("values", {})
        result_label = row_info.get("result_label", "N/A")
        result_status = row_info.get("result_status", "not_available")
        explanation = row_info.get("explanation", "")

        row_cells = [attr_label]
        for d in docs:
            doc_id = d.get("id")
            val = values.get(doc_id, "Not Available")
            row_cells.append(str(val))

        row_cells.extend([result_label, explanation])
        ws.append(row_cells)
        cur_row = ws.max_row
        ws.row_dimensions[cur_row].height = 24

        # Style cells
        ws.cell(row=cur_row, column=1).font = font_bold
        ws.cell(row=cur_row, column=1).border = thin_border

        for c_idx in range(2, len(docs) + 2):
            cell = ws.cell(row=cur_row, column=c_idx)
            cell.border = thin_border
            val_text = str(cell.value or "")
            if val_text in ("Not Available", "Not Applicable"):
                cell.font = font_muted
                cell.fill = fill_na
            else:
                cell.font = font_regular
            cell.alignment = Alignment(vertical="center")

        # Result Cell
        res_col_idx = len(docs) + 2
        res_cell = ws.cell(row=cur_row, column=res_col_idx)
        res_cell.font = font_bold
        res_cell.border = thin_border
        res_cell.alignment = Alignment(horizontal="center", vertical="center")
        if result_status in ("match", "valid"):
            res_cell.fill = fill_match
        elif result_status in ("mismatch", "expired"):
            res_cell.fill = fill_mismatch
        elif result_status in ("warning", "partial_match", "variation"):
            res_cell.fill = fill_warn
        else:
            res_cell.fill = fill_na

        # Explanation Cell
        exp_col_idx = len(docs) + 3
        exp_cell = ws.cell(row=cur_row, column=exp_col_idx)
        exp_cell.font = font_regular
        exp_cell.border = thin_border
        exp_cell.alignment = Alignment(vertical="center", wrap_text=True)

    # 4. Summary Findings Block
    ws.append([])
    summary_issues = matrix_data.get("summary_issues") or matrix_data.get("discrepancies") or []
    ws.append(["VERIFICATION FINDINGS & ISSUES REQUIRING ATTENTION:"])
    ws.cell(row=ws.max_row, column=1).font = font_bold

    if not summary_issues:
        ws.append(["All submitted KYC documents are consistent and passed deterministic validity checks."])
        ws.cell(row=ws.max_row, column=1).font = font_regular
    else:
        for idx, issue in enumerate(summary_issues, 1):
            ws.append([f"  {idx}. {issue}"])
            ws.cell(row=ws.max_row, column=1).font = font_regular

    # Auto-adjust column widths
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            val_str = str(cell.value or "")
            first_line = val_str.split("\n")[0]
            if len(first_line) > max_len:
                max_len = len(first_line)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 16)

    # Save to memory buffer
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def export_comparison_matrix_to_csv(matrix_data: Dict[str, Any]) -> str:
    """Generate CSV string matching the comparison matrix."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    docs = matrix_data.get("columns") or matrix_data.get("documents") or []
    headers = ["Attribute"]
    for d in docs:
        label = d.get("type_label") or d.get("document_type", "Document").replace("_", " ").title()
        fname = d.get("filename") or ""
        headers.append(f"{label} ({fname})")
    headers.extend(["Comparison Result", "Audit Explanation"])
    writer.writerow(headers)

    # Rows
    rows = matrix_data.get("rows", [])
    for r in rows:
        attr_label = r.get("attribute_label", "")
        values = r.get("values", {})
        result_label = r.get("result_label", "")
        explanation = r.get("explanation", "")

        row_vals = [attr_label]
        for d in docs:
            doc_id = d.get("id")
            row_vals.append(values.get(doc_id, "Not Available"))
        row_vals.extend([result_label, explanation])
        writer.writerow(row_vals)

    return output.getvalue()


def export_reports_summary_to_xlsx(report_data: Dict[str, Any]) -> bytes:
    """
    Generate a complete business-facing compliance audit workbook (.xlsx)
    with 'KYC Summary' and 'Applicant Audit Ledger' worksheets.
    """
    wb = openpyxl.Workbook()

    # Sheet 1: Summary Dashboard
    ws_summary = wb.active
    ws_summary.title = "KYC Summary"

    font_title = Font(name="Calibri", size=16, bold=True, color="0F172A")
    font_section = Font(name="Calibri", size=13, bold=True, color="1E293B")
    font_bold = Font(name="Calibri", size=11, bold=True, color="0F172A")
    font_regular = Font(name="Calibri", size=11, color="334155")
    font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")

    fill_header = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    fill_green = PatternFill(start_color="EDF4EE", end_color="EDF4EE", fill_type="solid")
    fill_red = PatternFill(start_color="F9EFEB", end_color="F9EFEB", fill_type="solid")
    fill_amber = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")

    thin_border = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"),
        bottom=Side(style="thin", color="E2E8F0")
    )

    ws_summary["A1"] = "VERIDOC AI — KYC COMPLIANCE AUDIT REPORT"
    ws_summary["A1"].font = font_title
    ws_summary["A2"] = f"Generated: {report_data.get('generated_at', '')}  |  Scope: {report_data.get('dataset_scope', 'all').upper()}"
    ws_summary["A2"].font = Font(name="Calibri", size=10, italic=True, color="64748B")

    # Section A: Summary Metrics
    ws_summary["A4"] = "A. KYC Processing Summary"
    ws_summary["A4"].font = font_section

    summary_items = [
        ("Total Applicants", report_data.get("total_applicants", 0)),
        ("Total Uploaded Documents", report_data.get("total_documents", 0)),
        ("Verified Applicants", report_data.get("verified_applicants", 0)),
        ("Pending Review Applicants", report_data.get("pending_applicants", 0)),
        ("Applicants Requiring Attention", report_data.get("attention_applicants", 0)),
        ("Successfully Processed Documents", report_data.get("processed_documents", report_data.get("total_documents", 0))),
        ("Failed / Unreadable Documents", report_data.get("failed_documents", 0)),
    ]

    for idx, (label, val) in enumerate(summary_items, start=5):
        ws_summary.cell(row=idx, column=1, value=label).font = font_bold
        ws_summary.cell(row=idx, column=1).border = thin_border
        val_cell = ws_summary.cell(row=idx, column=2, value=val)
        val_cell.font = font_bold
        val_cell.border = thin_border
        val_cell.alignment = Alignment(horizontal="right")

    # Section B: Category Breakdown
    cat_start = len(summary_items) + 7
    ws_summary.cell(row=cat_start, column=1, value="B. Document Category Breakdown").font = font_section

    categories = report_data.get("category_breakdown", {})
    if not categories:
        categories = {"PAN": 0, "Aadhaar": 0, "Passport": 0, "Voter ID": 0, "Driving Licence": 0, "Unknown": 0}

    for idx, (cat_name, cat_count) in enumerate(categories.items(), start=cat_start + 1):
        ws_summary.cell(row=idx, column=1, value=str(cat_name).replace("_", " ").title()).font = font_regular
        ws_summary.cell(row=idx, column=1).border = thin_border
        c_cell = ws_summary.cell(row=idx, column=2, value=cat_count)
        c_cell.font = font_bold
        c_cell.border = thin_border
        c_cell.alignment = Alignment(horizontal="right")

    ws_summary.column_dimensions["A"].width = 38
    ws_summary.column_dimensions["B"].width = 20

    # Sheet 2: Applicant Audit Ledger
    ws_ledger = wb.create_sheet(title="Applicant Audit Ledger")
    ledger_headers = [
        "Applicant Reference",
        "Applicant Name",
        "Total Documents",
        "Document Types",
        "Verification Status",
        "Cross-Check Verdict",
        "Consistency Score",
        "Concise Discrepancy Summary",
        "Last Updated"
    ]
    ws_ledger.append(ledger_headers)
    ws_ledger.row_dimensions[1].height = 28

    for c_idx in range(1, len(ledger_headers) + 1):
        cell = ws_ledger.cell(row=1, column=c_idx)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    applicants = report_data.get("applicants", [])
    for app in applicants:
        status = str(app.get("status", "pending")).replace("_", " ").title()
        verdict = str(app.get("verdict", "PENDING")).replace("_", " ").title()
        discs = app.get("discrepancies", [])
        disc_text = "; ".join(discs) if discs else "Passed all validations"

        created = app.get("created_at")
        if isinstance(created, datetime):
            if created.tzinfo is not None:
                created = created.replace(tzinfo=None)
            created_str = created.strftime("%Y-%m-%d %H:%M:%S")
        else:
            created_str = str(created) if created else ""

        row_data = [
            app.get("id"),
            app.get("name"),
            app.get("doc_count", 0),
            ", ".join(app.get("doc_types", [])),
            status,
            verdict,
            f"{app.get('consistency_score', 0)}%",
            disc_text,
            created_str
        ]
        ws_ledger.append(row_data)
        cur_row = ws_ledger.max_row
        ws_ledger.row_dimensions[cur_row].height = 20

        for col_idx in range(1, len(row_data) + 1):
            c = ws_ledger.cell(row=cur_row, column=col_idx)
            c.border = thin_border
            c.font = font_regular
            c.alignment = Alignment(vertical="center")

        # Color-code status cell (col 5)
        st_cell = ws_ledger.cell(row=cur_row, column=5)
        if "Verified" in status:
            st_cell.fill = fill_green
        elif "Attention" in status:
            st_cell.fill = fill_red
        else:
            st_cell.fill = fill_amber

    # Auto-adjust column widths for ledger
    for col in ws_ledger.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws_ledger.column_dimensions[col_letter].width = max(min(max_len + 3, 50), 14)

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


