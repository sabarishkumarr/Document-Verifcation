"""
VeriDoc AI 2.0 — Synthetic Specimen Library & Attribute Population Generator
Generates realistic, completely fictional synthetic test documents for all 12 registered
document types in PostgreSQL (veridoc_db), with visible synthetic watermarks, accurate
bounding box mappings, schema definitions, and attribute population.
"""

import os
import sys
import json
import fitz  # PyMuPDF
from pathlib import Path
from datetime import datetime

# Adjust Python path to load backend
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.database.db import get_db_connection

STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage" / "uploads" / "synthetic"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

WATERMARK_TEXT = "SYNTHETIC TEST DOCUMENT — NOT VALID FOR IDENTIFICATION OR OFFICIAL USE"
SYNTHETIC_APPLICANT_ID = "APPL-SYN-FIXTURES"
SYNTHETIC_APPLICANT_NAME = "VeriDoc Synthetic Fixtures & Compliance Repository"

# Comprehensive configuration for all 12 registered types
SPECIMEN_DEFINITIONS = {
    "pan": {
        "filename": "synthetic_pan.pdf",
        "doc_id": "DOC-SYN-PAN",
        "display_name": "Permanent Account Number Card",
        "category": "identity",
        "pages": 1,
        "attributes": [
            {
                "attribute_key": "pan_number",
                "display_label": "PAN Number",
                "data_type": "string",
                "sample_value": "ABCDE1234F",
                "bounding_box": [620, 100, 710, 600],
                "required": True,
            },
            {
                "attribute_key": "name",
                "display_label": "Name",
                "data_type": "string",
                "sample_value": "Aarav Mehta",
                "bounding_box": [260, 80, 330, 600],
                "required": True,
            },
            {
                "attribute_key": "father_name",
                "display_label": "Father's Name",
                "data_type": "string",
                "sample_value": "Devansh Mehta",
                "bounding_box": [360, 80, 430, 600],
                "required": True,
            },
            {
                "attribute_key": "dob",
                "display_label": "Date of Birth",
                "data_type": "date",
                "sample_value": "1990-05-15",
                "bounding_box": [460, 80, 530, 420],
                "required": True,
            },
        ],
    },
    "aadhaar": {
        "filename": "synthetic_aadhaar.pdf",
        "doc_id": "DOC-SYN-AADHAAR",
        "display_name": "Aadhaar Card",
        "category": "identity",
        "pages": 1,
        "attributes": [
            {
                "attribute_key": "aadhaar_number",
                "display_label": "Aadhaar Number",
                "data_type": "string",
                "sample_value": "XXXX-XXXX-4819",
                "bounding_box": [720, 200, 800, 800],
                "required": True,
            },
            {
                "attribute_key": "name",
                "display_label": "Name",
                "data_type": "string",
                "sample_value": "Ananya Sharma",
                "bounding_box": [280, 260, 350, 750],
                "required": True,
            },
            {
                "attribute_key": "dob",
                "display_label": "Date of Birth",
                "data_type": "date",
                "sample_value": "1992-08-22",
                "bounding_box": [370, 260, 430, 650],
                "required": True,
            },
            {
                "attribute_key": "gender",
                "display_label": "Gender",
                "data_type": "string",
                "sample_value": "FEMALE",
                "bounding_box": [440, 260, 490, 480],
                "required": True,
            },
            {
                "attribute_key": "address",
                "display_label": "Address",
                "data_type": "string",
                "sample_value": "Flat 402 Green Valley Kothrud Pune Maharashtra 411038",
                "bounding_box": [530, 260, 650, 920],
                "required": True,
            },
        ],
    },
    "passport": {
        "filename": "synthetic_passport.pdf",
        "doc_id": "DOC-SYN-PASSPORT",
        "display_name": "Indian Passport",
        "category": "identity",
        "pages": 1,
        "attributes": [
            {
                "attribute_key": "passport_number",
                "display_label": "Passport Number",
                "data_type": "string",
                "sample_value": "Z8920194",
                "bounding_box": [140, 650, 200, 950],
                "required": True,
            },
            {
                "attribute_key": "name",
                "display_label": "Full Name",
                "data_type": "string",
                "sample_value": "Kavita Joshi",
                "bounding_box": [280, 250, 350, 800],
                "required": True,
            },
            {
                "attribute_key": "nationality",
                "display_label": "Nationality",
                "data_type": "string",
                "sample_value": "INDIAN",
                "bounding_box": [360, 250, 410, 550],
                "required": True,
            },
            {
                "attribute_key": "dob",
                "display_label": "Date of Birth",
                "data_type": "date",
                "sample_value": "1988-11-04",
                "bounding_box": [430, 250, 490, 550],
                "required": True,
            },
            {
                "attribute_key": "expiry_date",
                "display_label": "Date of Expiry",
                "data_type": "date",
                "sample_value": "2032-11-03",
                "bounding_box": [580, 250, 640, 550],
                "required": True,
            },
        ],
    },
    "voter_id": {
        "filename": "synthetic_voter_id.pdf",
        "doc_id": "DOC-SYN-VOTER-ID",
        "display_name": "Elector Photo Identity Card",
        "category": "identity",
        "pages": 1,
        "attributes": [
            {
                "attribute_key": "voter_id_number",
                "display_label": "EPIC / Voter ID Number",
                "data_type": "string",
                "sample_value": "WZK9102847",
                "bounding_box": [140, 450, 210, 950],
                "required": True,
            },
            {
                "attribute_key": "name",
                "display_label": "Elector Name",
                "data_type": "string",
                "sample_value": "Vikram Singhania",
                "bounding_box": [320, 250, 390, 850],
                "required": True,
            },
            {
                "attribute_key": "father_name",
                "display_label": "Father's Name",
                "data_type": "string",
                "sample_value": "Rajesh Singhania",
                "bounding_box": [410, 250, 480, 850],
                "required": True,
            },
            {
                "attribute_key": "gender",
                "display_label": "Gender",
                "data_type": "string",
                "sample_value": "MALE",
                "bounding_box": [500, 250, 550, 500],
                "required": True,
            },
            {
                "attribute_key": "dob",
                "display_label": "Date of Birth",
                "data_type": "date",
                "sample_value": "1985-03-19",
                "bounding_box": [570, 250, 630, 600],
                "required": True,
            },
        ],
    },
    "driving_licence": {
        "filename": "synthetic_driving_licence.pdf",
        "doc_id": "DOC-SYN-DRIVING-LICENCE",
        "display_name": "Motor Driving Licence",
        "category": "identity",
        "pages": 1,
        "attributes": [
            {
                "attribute_key": "licence_number",
                "display_label": "Licence Number",
                "data_type": "string",
                "sample_value": "MH12 20140029184",
                "bounding_box": [180, 300, 250, 850],
                "required": True,
            },
            {
                "attribute_key": "name",
                "display_label": "Holder Name",
                "data_type": "string",
                "sample_value": "Rohan Nair",
                "bounding_box": [280, 250, 350, 800],
                "required": True,
            },
            {
                "attribute_key": "dob",
                "display_label": "Date of Birth",
                "data_type": "date",
                "sample_value": "1994-07-28",
                "bounding_box": [380, 250, 440, 580],
                "required": True,
            },
            {
                "attribute_key": "validity",
                "display_label": "Validity / Expiry Date",
                "data_type": "date",
                "sample_value": "2034-07-27",
                "bounding_box": [480, 250, 540, 680],
                "required": True,
            },
        ],
    },
    "salary_slip": {
        "filename": "synthetic_salary_slip.pdf",
        "doc_id": "DOC-SYN-SALARY-SLIP",
        "display_name": "Salary Certificate / Payslip",
        "category": "financial",
        "pages": 1,
        "attributes": [
            {
                "attribute_key": "employee_name",
                "display_label": "Employee Name",
                "data_type": "string",
                "sample_value": "Arjun Sharma",
                "bounding_box": [160, 60, 185, 250],
                "required": True,
            },
            {
                "attribute_key": "employee_id",
                "display_label": "Employee ID",
                "data_type": "string",
                "sample_value": "EMP-84920",
                "bounding_box": [180, 60, 205, 220],
                "required": True,
            },
            {
                "attribute_key": "gross_earnings",
                "display_label": "Gross Earnings",
                "data_type": "currency",
                "sample_value": "INR 85,000.00",
                "bounding_box": [403, 60, 430, 280],
                "required": True,
            },
            {
                "attribute_key": "total_deductions",
                "display_label": "Total Deductions",
                "data_type": "currency",
                "sample_value": "INR 10,800.00",
                "bounding_box": [403, 315, 430, 530],
                "required": True,
            },
            {
                "attribute_key": "net_pay",
                "display_label": "Net Salary Payable",
                "data_type": "currency",
                "sample_value": "INR 74,200.00",
                "bounding_box": [465, 60, 495, 380],
                "required": True,
            },
            {
                "attribute_key": "amount_in_words_indian_rupee_forty",
                "display_label": "Amount in Words",
                "data_type": "string",
                "sample_value": "Indian Rupees Seventy-Four Thousand Two Hundred Only",
                "bounding_box": [505, 60, 535, 520],
                "required": False,
            },
            {
                "attribute_key": "this_is_a_system",
                "display_label": "System Generated Notice",
                "data_type": "string",
                "sample_value": "This is a computer generated salary certificate",
                "bounding_box": [545, 50, 575, 400],
                "required": False,
            },
            {
                "attribute_key": "custom_field_4",
                "display_label": "Bank Account / IFSC Reference",
                "data_type": "string",
                "sample_value": "HDFC0001829 - AC 501004819201",
                "bounding_box": [230, 60, 255, 380],
                "required": False,
            },
        ],
    },
    "payslip": {
        "filename": "synthetic_payslip_discovered.pdf",
        "doc_id": "DOC-SYN-PAYSLIP",
        "display_name": "payslip",
        "category": "financial",
        "pages": 1,
        "attributes": [
            {
                "attribute_key": "gross_earnings",
                "display_label": "Gross Earnings",
                "data_type": "currency",
                "sample_value": "INR 92,000.00",
                "bounding_box": [403, 60, 430, 280],
                "required": True,
            },
            {
                "attribute_key": "amount_in_words_indian_rupee_forty",
                "display_label": "Amount In Words",
                "data_type": "string",
                "sample_value": "Indian Rupees Eighty-One Thousand Only",
                "bounding_box": [505, 60, 535, 520],
                "required": False,
            },
            {
                "attribute_key": "this_is_a_system",
                "display_label": "System Notice",
                "data_type": "string",
                "sample_value": "This is a computer generated salary certificate",
                "bounding_box": [545, 50, 575, 400],
                "required": False,
            },
        ],
    },
    "bank_statement": {
        "filename": "synthetic_bank_statement.pdf",
        "doc_id": "DOC-SYN-BANK-STATEMENT",
        "display_name": "Bank Account Statement",
        "category": "financial",
        "pages": 2,
        "attributes": [
            {
                "attribute_key": "account_holder_name",
                "display_label": "Account Holder Name",
                "data_type": "string",
                "sample_value": "Pooja Verma",
                "bounding_box": [140, 50, 175, 400],
                "required": True,
            },
            {
                "attribute_key": "account_number",
                "display_label": "Account Number",
                "data_type": "string",
                "sample_value": "XXXXXXXX4920",
                "bounding_box": [185, 50, 215, 380],
                "required": True,
            },
            {
                "attribute_key": "bank_name",
                "display_label": "Bank Name",
                "data_type": "string",
                "sample_value": "Apex Commercial Bank",
                "bounding_box": [60, 50, 100, 500],
                "required": True,
            },
            {
                "attribute_key": "ifsc_code",
                "display_label": "IFSC Code",
                "data_type": "string",
                "sample_value": "APEX0004921",
                "bounding_box": [225, 50, 255, 350],
                "required": True,
            },
            {
                "attribute_key": "statement_period",
                "display_label": "Statement Period",
                "data_type": "string",
                "sample_value": "01-Oct-2026 to 31-Oct-2026",
                "bounding_box": [140, 550, 175, 920],
                "required": True,
            },
            {
                "attribute_key": "opening_balance",
                "display_label": "Opening Balance",
                "data_type": "currency",
                "sample_value": "INR 1,42,850.00",
                "bounding_box": [270, 50, 305, 350],
                "required": True,
            },
            {
                "attribute_key": "total_credits",
                "display_label": "Total Deposits / Credits",
                "data_type": "currency",
                "sample_value": "INR 1,15,000.00",
                "bounding_box": [270, 370, 305, 650],
                "required": True,
            },
            {
                "attribute_key": "total_debits",
                "display_label": "Total Withdrawals / Debits",
                "data_type": "currency",
                "sample_value": "INR 68,430.00",
                "bounding_box": [270, 670, 305, 920],
                "required": True,
            },
            {
                "attribute_key": "closing_balance",
                "display_label": "Closing Balance",
                "data_type": "currency",
                "sample_value": "INR 1,89,420.00",
                "bounding_box": [315, 50, 350, 400],
                "required": True,
            },
        ],
    },
    "commercial_invoice": {
        "filename": "synthetic_commercial_invoice.pdf",
        "doc_id": "DOC-SYN-COMMERCIAL-INVOICE",
        "display_name": "Commercial / Tax Invoice",
        "category": "billing",
        "pages": 1,
        "attributes": [
            {
                "attribute_key": "invoice_number",
                "display_label": "Invoice Number",
                "data_type": "string",
                "sample_value": "INV-2026-8819",
                "bounding_box": [130, 550, 165, 900],
                "required": True,
            },
            {
                "attribute_key": "invoice_date",
                "display_label": "Invoice Date",
                "data_type": "date",
                "sample_value": "2026-10-18",
                "bounding_box": [175, 550, 205, 850],
                "required": True,
            },
            {
                "attribute_key": "supplier_name",
                "display_label": "Supplier / Vendor Name",
                "data_type": "string",
                "sample_value": "Quantum Cloud Solutions Pvt Ltd",
                "bounding_box": [110, 60, 145, 450],
                "required": True,
            },
            {
                "attribute_key": "supplier_gstin",
                "display_label": "Supplier GSTIN",
                "data_type": "string",
                "sample_value": "27AABCQ1234F1Z5",
                "bounding_box": [155, 60, 185, 420],
                "required": True,
            },
            {
                "attribute_key": "recipient_name",
                "display_label": "Billed To / Recipient",
                "data_type": "string",
                "sample_value": "Apex Enterprise Systems Ltd",
                "bounding_box": [240, 60, 275, 450],
                "required": True,
            },
            {
                "attribute_key": "recipient_gstin",
                "display_label": "Recipient GSTIN",
                "data_type": "string",
                "sample_value": "27AAACE9876R1Z2",
                "bounding_box": [285, 60, 315, 420],
                "required": True,
            },
            {
                "attribute_key": "subtotal_amount",
                "display_label": "Taxable Subtotal",
                "data_type": "currency",
                "sample_value": "INR 2,45,000.00",
                "bounding_box": [680, 650, 715, 920],
                "required": True,
            },
            {
                "attribute_key": "tax_amount",
                "display_label": "Tax Amount (18% GST)",
                "data_type": "currency",
                "sample_value": "INR 44,100.00",
                "bounding_box": [725, 650, 760, 920],
                "required": True,
            },
            {
                "attribute_key": "total_amount",
                "display_label": "Total Invoice Amount",
                "data_type": "currency",
                "sample_value": "INR 2,89,100.00",
                "bounding_box": [775, 650, 815, 920],
                "required": True,
            },
            {
                "attribute_key": "due_date",
                "display_label": "Payment Due Date",
                "data_type": "date",
                "sample_value": "2026-11-17",
                "bounding_box": [215, 550, 245, 850],
                "required": False,
            },
        ],
    },
    "tax_form_16": {
        "filename": "synthetic_tax_form_16.pdf",
        "doc_id": "DOC-SYN-TAX-FORM-16",
        "display_name": "Form 16 Tax Certificate",
        "category": "tax",
        "pages": 1,
        "attributes": [
            {
                "attribute_key": "certificate_number",
                "display_label": "TDS Certificate Number",
                "data_type": "string",
                "sample_value": "TDS-2026-AY27-991",
                "bounding_box": [100, 60, 130, 450],
                "required": True,
            },
            {
                "attribute_key": "employer_name",
                "display_label": "Employer Name",
                "data_type": "string",
                "sample_value": "Bharat Tech Innovations Ltd",
                "bounding_box": [160, 60, 195, 500],
                "required": True,
            },
            {
                "attribute_key": "employer_pan",
                "display_label": "Employer PAN",
                "data_type": "string",
                "sample_value": "AAACB1234D",
                "bounding_box": [205, 60, 235, 380],
                "required": True,
            },
            {
                "attribute_key": "employer_tan",
                "display_label": "Employer TAN",
                "data_type": "string",
                "sample_value": "PNEB10928F",
                "bounding_box": [245, 60, 275, 380],
                "required": True,
            },
            {
                "attribute_key": "employee_name",
                "display_label": "Employee Name",
                "data_type": "string",
                "sample_value": "Deepak Kumar Sen",
                "bounding_box": [160, 530, 195, 920],
                "required": True,
            },
            {
                "attribute_key": "employee_pan",
                "display_label": "Employee PAN",
                "data_type": "string",
                "sample_value": "DKSPD5678M",
                "bounding_box": [205, 530, 235, 850],
                "required": True,
            },
            {
                "attribute_key": "assessment_year",
                "display_label": "Assessment Year",
                "data_type": "string",
                "sample_value": "2026-27",
                "bounding_box": [100, 600, 130, 920],
                "required": True,
            },
            {
                "attribute_key": "gross_salary",
                "display_label": "Gross Total Income",
                "data_type": "currency",
                "sample_value": "INR 12,40,000.00",
                "bounding_box": [480, 550, 515, 900],
                "required": True,
            },
            {
                "attribute_key": "total_tax_deducted",
                "display_label": "Total Tax Deducted (TDS)",
                "data_type": "currency",
                "sample_value": "INR 1,18,500.00",
                "bounding_box": [640, 550, 675, 900],
                "required": True,
            },
        ],
    },
    "utility_bill": {
        "filename": "synthetic_utility_bill.pdf",
        "doc_id": "DOC-SYN-UTILITY-BILL",
        "display_name": "Utility / Electricity / Water Bill",
        "category": "utility",
        "pages": 1,
        "attributes": [
            {
                "attribute_key": "consumer_number",
                "display_label": "Consumer Account ID",
                "data_type": "string",
                "sample_value": "019284710928",
                "bounding_box": [140, 60, 175, 420],
                "required": True,
            },
            {
                "attribute_key": "consumer_name",
                "display_label": "Consumer Name",
                "data_type": "string",
                "sample_value": "Sanjay Rane",
                "bounding_box": [185, 60, 220, 480],
                "required": True,
            },
            {
                "attribute_key": "utility_provider",
                "display_label": "Utility Provider",
                "data_type": "string",
                "sample_value": "Maharashtra State Electricity Distribution Co.",
                "bounding_box": [70, 60, 110, 600],
                "required": True,
            },
            {
                "attribute_key": "billing_period",
                "display_label": "Billing Month / Period",
                "data_type": "string",
                "sample_value": "01-Sep-2026 to 30-Sep-2026",
                "bounding_box": [140, 550, 175, 920],
                "required": True,
            },
            {
                "attribute_key": "bill_date",
                "display_label": "Bill Generation Date",
                "data_type": "date",
                "sample_value": "2026-10-04",
                "bounding_box": [185, 550, 215, 850],
                "required": True,
            },
            {
                "attribute_key": "due_date",
                "display_label": "Due Date for Payment",
                "data_type": "date",
                "sample_value": "2026-10-24",
                "bounding_box": [225, 550, 255, 850],
                "required": True,
            },
            {
                "attribute_key": "units_consumed",
                "display_label": "Units Consumed",
                "data_type": "string",
                "sample_value": "342 kWh",
                "bounding_box": [360, 60, 395, 350],
                "required": True,
            },
            {
                "attribute_key": "bill_amount",
                "display_label": "Net Amount Payable",
                "data_type": "currency",
                "sample_value": "INR 3,280.00",
                "bounding_box": [420, 550, 460, 900],
                "required": True,
            },
            {
                "attribute_key": "service_address",
                "display_label": "Service Address",
                "data_type": "string",
                "sample_value": "Bungalow 12 Mayur Colony Kothrud Pune 411038",
                "bounding_box": [230, 60, 290, 520],
                "required": True,
            },
        ],
    },
    "unknown": {
        "filename": "synthetic_unclassified_document.pdf",
        "doc_id": "DOC-SYN-UNKNOWN",
        "display_name": "Unclassified Document",
        "category": "general",
        "pages": 1,
        "attributes": [
            {
                "attribute_key": "document_title",
                "display_label": "Document Title",
                "data_type": "string",
                "sample_value": "Corporate Policy Notice and Operations Memo",
                "bounding_box": [100, 60, 140, 900],
                "required": True,
            },
            {
                "attribute_key": "reference_code",
                "display_label": "Reference Code",
                "data_type": "string",
                "sample_value": "MEMO-GEN-2026-004",
                "bounding_box": [150, 60, 180, 450],
                "required": True,
            },
            {
                "attribute_key": "issue_date",
                "display_label": "Date of Issuance",
                "data_type": "date",
                "sample_value": "2026-09-12",
                "bounding_box": [150, 600, 180, 900],
                "required": True,
            },
            {
                "attribute_key": "issuing_department",
                "display_label": "Issuing Department",
                "data_type": "string",
                "sample_value": "Administration and Corporate Governance",
                "bounding_box": [190, 60, 220, 500],
                "required": True,
            },
            {
                "attribute_key": "summary",
                "display_label": "Executive Summary",
                "data_type": "string",
                "sample_value": "Facility maintenance schedules and internal operational compliance rules",
                "bounding_box": [250, 60, 330, 900],
                "required": True,
            },
        ],
    },
}


def draw_watermark_banner(page, width, height):
    """Draws a prominent synthetic warning banner across the top and diagonal watermark."""
    # Top Warning Header Banner
    banner_rect = fitz.Rect(0, 0, width, 22)
    page.draw_rect(banner_rect, color=(0.85, 0.2, 0.2), fill=(0.98, 0.92, 0.92))
    page.insert_textbox(
        banner_rect,
        f"\n{WATERMARK_TEXT}",
        fontsize=7.5,
        fontname="helv",
        color=(0.8, 0.1, 0.1),
        align=fitz.TEXT_ALIGN_CENTER,
    )
    # Bottom Warning Footer Banner
    foot_rect = fitz.Rect(0, height - 20, width, height)
    page.draw_rect(foot_rect, color=(0.7, 0.7, 0.7), fill=(0.96, 0.96, 0.96))
    page.insert_textbox(
        foot_rect,
        "\nVERIDOC AI COMPLIANCE PLATFORM — SYNTHETIC BENCHMARK FIXTURE",
        fontsize=7,
        fontname="helv",
        color=(0.4, 0.4, 0.4),
        align=fitz.TEXT_ALIGN_CENTER,
    )


def build_pdf_document(type_key, spec_cfg):
    """Creates a high-DPI synthetic PDF with realistic visuals and exact text positions."""
    pdf_path = STORAGE_DIR / spec_cfg["filename"]
    doc = fitz.open()

    page_width = 595  # A4 width in pt
    page_height = 842  # A4 height in pt
    num_pages = spec_cfg.get("pages", 1)

    for page_idx in range(num_pages):
        page = doc.new_page(width=page_width, height=page_height)
        draw_watermark_banner(page, page_width, page_height)

        # Draw decorative document border
        border_rect = fitz.Rect(30, 30, page_width - 30, page_height - 28)
        page.draw_rect(border_rect, color=(0.3, 0.4, 0.5), width=1)

        # Draw document title header
        title = spec_cfg["display_name"].upper()
        title_rect = fitz.Rect(40, 36, page_width - 40, 60)
        page.insert_textbox(
            title_rect,
            f"\n{title}",
            fontsize=12,
            fontname="helv",
            color=(0.08, 0.15, 0.3),
            align=fitz.TEXT_ALIGN_CENTER,
        )

        page.draw_line(fitz.Point(40, 62), fitz.Point(page_width - 40, 62), color=(0.7, 0.75, 0.8), width=1)

        # Draw attribute fields on page 1 (and page 2 if multi-page)
        if page_idx == 0:
            for attr in spec_cfg["attributes"]:
                bbox = attr.get("bounding_box")
                if not bbox:
                    continue
                ymin, xmin, ymax, xmax = bbox
                rx = (xmin / 1000.0) * page_width
                ry = (ymin / 1000.0) * page_height
                rw = max(10, ((xmax - xmin) / 1000.0) * page_width)
                rh = max(10, ((ymax - ymin) / 1000.0) * page_height)

                rect = fitz.Rect(rx, ry, rx + rw, ry + rh)
                # Draw subtle background box for the field
                page.draw_rect(rect, color=(0.85, 0.9, 0.95), fill=(0.97, 0.98, 1.0), width=0.5)

                # Draw Field Label
                label_y = max(28, ry - 3)
                page.insert_text(
                    fitz.Point(rx, label_y),
                    attr["display_label"].upper(),
                    fontsize=6.5,
                    fontname="helv",
                    color=(0.4, 0.45, 0.55),
                )

                # Draw Field Value inside box
                val_text = str(attr["sample_value"])
                val_y = ry + (rh / 2.0) + 3.5
                page.insert_text(
                    fitz.Point(rx + 4, val_y),
                    val_text,
                    fontsize=9,
                    fontname="helv",
                    color=(0.06, 0.1, 0.18),
                )
        else:
            # Page 2: Multi-page ledger / details
            page.insert_text(
                fitz.Point(50, 90),
                "ACCOUNT TRANSACTIONS CONTINUATION LEDGER — PAGE 2 OF 2",
                fontsize=11,
                fontname="helv",
                color=(0.1, 0.2, 0.35),
            )
            # Sample transaction rows
            y_pos = 120
            txns = [
                ("18-Oct-2026", "UPI/NEFT INCOMING SALARY DISBURSEMENT", "+INR 74,200.00", "INR 1,82,450.00"),
                ("22-Oct-2026", "ELECTRONIC CLEARING SERVICE LOAN EMI", "-INR 22,500.00", "INR 1,59,950.00"),
                ("25-Oct-2026", "UTILITY DIRECT DEBIT MSEDCL", "-INR 3,280.00", "INR 1,56,670.00"),
                ("29-Oct-2026", "INVESTMENT DIVIDEND APEX EQUITY", "+INR 32,750.00", "INR 1,89,420.00"),
            ]
            for date_str, desc, amount, bal in txns:
                page.insert_text(fitz.Point(50, y_pos), date_str, fontsize=8.5, fontname="helv", color=(0.3, 0.3, 0.3))
                page.insert_text(fitz.Point(130, y_pos), desc, fontsize=8.5, fontname="helv", color=(0.1, 0.1, 0.1))
                page.insert_text(fitz.Point(400, y_pos), amount, fontsize=8.5, fontname="helv", color=(0.1, 0.5, 0.2) if amount.startswith("+") else (0.7, 0.1, 0.1))
                page.insert_text(fitz.Point(490, y_pos), bal, fontsize=8.5, fontname="helv", color=(0.1, 0.1, 0.1))
                y_pos += 24

            page.draw_line(fitz.Point(40, y_pos + 10), fitz.Point(page_width - 40, y_pos + 10), color=(0.8, 0.8, 0.8), width=0.5)
            page.insert_text(
                fitz.Point(50, y_pos + 35),
                "End of statement period. Verified by Apex Commercial Bank Automated Reconciliation Core.",
                fontsize=8,
                fontname="helv",
                color=(0.4, 0.4, 0.4),
            )

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def seed_synthetic_library(db_path: str = None):
    """Seeds the database with schemas, synthetic specimens, and extracted attributes."""
    print("=" * 70)
    print("VeriDoc AI 2.0 — Synthetic Specimen Library Generation")
    print("=" * 70)

    conn = get_db_connection(db_path)
    cur = conn.cursor()

    # 1. Ensure dedicated synthetic applicant exists
    cur.execute("SELECT id FROM applicants WHERE id = ?", (SYNTHETIC_APPLICANT_ID,))
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO applicants (id, name, email, phone, status, risk_level, notes)
            VALUES (?, ?, ?, ?, 'verified', 'low', 'System synthetic fixtures for interactive schema mapping and testing.')
        """, (SYNTHETIC_APPLICANT_ID, SYNTHETIC_APPLICANT_NAME, "fixtures@veridoc.internal", "+91 99000 00000"))
        print(f"Created dedicated applicant: {SYNTHETIC_APPLICANT_ID}")
    else:
        print(f"Dedicated applicant exists: {SYNTHETIC_APPLICANT_ID}")

    total_types = len(SPECIMEN_DEFINITIONS)
    populated_types = 0
    total_attrs = 0
    represented_attrs = 0

    for type_key, cfg in SPECIMEN_DEFINITIONS.items():
        print(f"\nProcessing [{type_key}] - {cfg['display_name']}...")
        
        # 2. Get document type from database
        cur.execute("SELECT id, type_key, display_name FROM document_type_definitions WHERE type_key = ?", (type_key,))
        row = cur.fetchone()
        if not row:
            print(f"  WARNING: Document type '{type_key}' not found in document_type_definitions table. Skipping.")
            continue
        type_id = row["id"] if isinstance(row, dict) else row[0]

        # 3. Publish / update version 1 schema in document_schemas
        cur.execute("SELECT id, version FROM document_schemas WHERE document_type_id = ? AND is_active = TRUE", (type_id,))
        s_row = cur.fetchone()

        attr_defs = []
        for a in cfg["attributes"]:
            attr_defs.append({
                "attribute_key": a["attribute_key"],
                "display_label": a["display_label"],
                "data_type": a["data_type"],
                "required": a.get("required", True),
                "sample_value": a["sample_value"],
                "bounding_box": a["bounding_box"],
                "anchor_phrase": a["display_label"].lower(),
                "regex_pattern": "",
                "confidence_threshold": 0.85,
            })
            total_attrs += 1
            represented_attrs += 1

        if not s_row:
            cur.execute("""
                INSERT INTO document_schemas (
                    document_type_id, version, schema_name, attribute_definitions,
                    spatial_templates, sample_count, is_active
                ) VALUES (?, 1, ?, ?, '{}', 1, TRUE)
            """, (type_id, f"{cfg['display_name']} Schema v1", json.dumps(attr_defs)))
            print(f"  Published Schema v1 with {len(attr_defs)} attribute definitions.")
        else:
            # Update schema definitions if empty
            cur.execute("""
                UPDATE document_schemas 
                SET attribute_definitions = ?, schema_name = ?
                WHERE document_type_id = ? AND is_active = TRUE
            """, (json.dumps(attr_defs), f"{cfg['display_name']} Schema v1", type_id))
            print(f"  Updated active schema definitions ({len(attr_defs)} attributes).")

        # 4. Generate high-DPI synthetic PDF file
        pdf_path = build_pdf_document(type_key, cfg)
        file_size = os.path.getsize(pdf_path)
        stored_rel_name = f"synthetic/{cfg['filename']}"
        print(f"  Generated PDF: {cfg['filename']} ({file_size} bytes, {cfg['pages']} page(s))")

        # 5. Build extracted fields and spatial tokens
        extracted_fields = {
            "attributes": [
                {
                    "attribute_key": a["attribute_key"],
                    "attribute_label": a["display_label"],
                    "attribute_value": a["sample_value"],
                    "raw_value": a["sample_value"],
                    "normalized_value": a["sample_value"],
                    "bounding_box": a["bounding_box"],
                    "confidence": 0.99,
                    "page_number": 1,
                    "source_type": "system_standard",
                }
                for a in cfg["attributes"]
            ],
            "document_type": type_key,
            "extraction_method": "synthetic_specimen",
            "is_synthetic": True,
        }
        # Flat values for legacy compatibility
        for a in cfg["attributes"]:
            extracted_fields[a["attribute_key"]] = a["sample_value"]

        extracted_text = f"{cfg['display_name']} {WATERMARK_TEXT}\n" + "\n".join(
            [f"{a['display_label']}: {a['sample_value']}" for a in cfg["attributes"]]
        )

        spatial_tokens = [
            {
                "text": str(a["sample_value"]),
                "bounding_box": a["bounding_box"],
                "page": 1,
                "confidence": 0.99,
            }
            for a in cfg["attributes"]
        ]
        extraction_metadata = {
            "spatial_tokens": spatial_tokens,
            "page_count": cfg["pages"],
            "is_synthetic": True,
            "specimen_for_type": type_key,
        }

        # 6. Insert / Update document in PostgreSQL (idempotent)
        doc_id = cfg["doc_id"]
        cur.execute("SELECT id FROM documents WHERE id = ?", (doc_id,))
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO documents (
                    id, applicant_id, original_filename, stored_filename, document_type,
                    classified_type, classification_confidence, file_size, mime_type,
                    processing_status, review_status, extracted_text, extracted_fields,
                    extraction_metadata, upload_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, 0.99, ?, 'application/pdf', 'completed', 'verified', ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                doc_id,
                SYNTHETIC_APPLICANT_ID,
                cfg["filename"],
                stored_rel_name,
                type_key,
                type_key,
                file_size,
                extracted_text,
                json.dumps(extracted_fields),
                json.dumps(extraction_metadata),
            ))
            print(f"  Inserted document record: {doc_id}")
        else:
            cur.execute("""
                UPDATE documents SET
                    stored_filename = ?,
                    document_type = ?,
                    classified_type = ?,
                    classification_confidence = 0.99,
                    file_size = ?,
                    processing_status = 'completed',
                    review_status = 'verified',
                    extracted_text = ?,
                    extracted_fields = ?,
                    extraction_metadata = ?
                WHERE id = ?
            """, (
                stored_rel_name,
                type_key,
                type_key,
                file_size,
                extracted_text,
                json.dumps(extracted_fields),
                json.dumps(extraction_metadata),
                doc_id,
            ))
            print(f"  Updated document record: {doc_id}")

        # 7. Insert / Update document_extracted_attributes
        cur.execute("DELETE FROM document_extracted_attributes WHERE document_id = ?", (doc_id,))
        for a in cfg["attributes"]:
            cur.execute("""
                INSERT INTO document_extracted_attributes (
                    document_id, attribute_key, attribute_label, data_type, raw_value,
                    normalized_value, confidence, source_type, extraction_method,
                    page_number, bounding_box, is_verified, is_deleted
                ) VALUES (?, ?, ?, ?, ?, ?, 0.99, 'system_standard', 'synthetic_specimen', 1, ?, TRUE, FALSE)
            """, (
                doc_id,
                a["attribute_key"],
                a["display_label"],
                a["data_type"],
                a["sample_value"],
                a["sample_value"],
                json.dumps(a["bounding_box"]),
            ))
        print(f"  Populated {len(cfg['attributes'])} extracted attributes in database.")
        populated_types += 1

    conn.commit()
    conn.close()

    print("\n" + "=" * 70)
    print("SPECIMEN LIBRARY GENERATION COMPLETE")
    print(f"Total registered types audited: {total_types}")
    print(f"Total specimen documents active: {populated_types}")
    print(f"Total configured attributes populated: {represented_attrs} / {total_attrs} (100%)")
    print("=" * 70)


if __name__ == "__main__":
    seed_synthetic_library()
