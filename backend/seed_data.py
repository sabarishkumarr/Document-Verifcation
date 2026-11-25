"""
Synthetic Demonstration Dataset Generator & Database Seeder for VeriDoc-AI.

Generates realistic but completely fictional KYC test fixtures (PDFs & Images)
with prominent "SYNTHETIC TEST DOCUMENT — NOT VALID FOR IDENTIFICATION" watermarks.
Seeds the SQLite database idempotently with 10 fictional applicants and 16 documents
covering all supported document types and edge cases:
- PAN, Aadhaar, Passport, Voter ID, Driving Licence
- Perfect match, Name variations, Critical DOB discrepancy, Expired document,
  Incomplete data, Unreadable scan, Invalid format, and Pending queue items.

Zero real PII is used. Full Aadhaar numbers are strictly masked.
"""

import os
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont

# Ensure backend directory is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database.db import get_db_connection, init_db

DEMO_STORAGE_DIR = PROJECT_ROOT / "storage" / "uploads" / "synthetic"
WATERMARK_TEXT = "SYNTHETIC TEST DOCUMENT — NOT VALID FOR IDENTIFICATION"


def _calculate_file_hash(filepath: Path) -> str:
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            sha.update(chunk)
    return sha.hexdigest()


def generate_synthetic_pdf(filepath: Path, title: str, lines: List[str], doc_type: str) -> None:
    """Generate a clean synthetic PDF document with prominent watermarks and formatted fields."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # Standard A4 size

    # Background tint
    rect = fitz.Rect(0, 0, 595, 842)
    page.draw_rect(rect, color=(0.96, 0.96, 0.95), fill=(0.98, 0.98, 0.97))

    # Outer decorative border
    page.draw_rect(fitz.Rect(30, 30, 565, 812), color=(0.7, 0.7, 0.7), width=1.5)
    page.draw_rect(fitz.Rect(36, 36, 559, 806), color=(0.85, 0.85, 0.85), width=0.8)

    # Top Watermark Banner
    page.draw_rect(fitz.Rect(40, 44, 555, 74), color=(0.8, 0.3, 0.25), fill=(0.98, 0.92, 0.91))
    page.insert_text(
        fitz.Point(70, 64),
        WATERMARK_TEXT,
        fontsize=11,
        fontname="helv",
        color=(0.7, 0.15, 0.1)
    )

    # Document Header
    page.insert_text(fitz.Point(50, 115), title, fontsize=15, fontname="tibo", color=(0.1, 0.1, 0.1))
    page.insert_text(fitz.Point(50, 135), f"Category: {doc_type} | Housing Finance Demo Intake", fontsize=9, fontname="helv", color=(0.4, 0.4, 0.4))
    page.draw_line(fitz.Point(50, 145), fitz.Point(545, 145), color=(0.8, 0.8, 0.8), width=1)

    # Document Content Body
    y = 180
    for line in lines:
        if line.startswith("---"):
            page.draw_line(fitz.Point(50, y - 5), fitz.Point(545, y - 5), color=(0.85, 0.85, 0.85), width=0.5)
            y += 15
        elif ":" in line:
            parts = line.split(":", 1)
            lbl = parts[0].strip() + ":"
            val = parts[1].strip()
            page.insert_text(fitz.Point(50, y), lbl, fontsize=11, fontname="hebo", color=(0.2, 0.2, 0.2))
            page.insert_text(fitz.Point(210, y), val, fontsize=11, fontname="helv", color=(0.05, 0.05, 0.05))
            y += 26
        else:
            page.insert_text(fitz.Point(50, y), line, fontsize=10, fontname="helv", color=(0.3, 0.3, 0.3))
            y += 22

    # Diagonal/Centered Watermark across the page
    center_pt = fitz.Point(75, 480)
    page.insert_text(
        center_pt,
        "SYNTHETIC TEST DOCUMENT — NOT VALID",
        fontsize=24,
        fontname="hebo",
        color=(0.82, 0.82, 0.82)
    )

    # Bottom Watermark Banner & Footer
    page.draw_rect(fitz.Rect(40, 765, 555, 795), color=(0.8, 0.3, 0.25), fill=(0.98, 0.92, 0.91))
    page.insert_text(
        fitz.Point(65, 785),
        WATERMARK_TEXT + " — VERIDOC AI TEST ENVIRONMENT",
        fontsize=9,
        fontname="helv",
        color=(0.7, 0.15, 0.1)
    )

    doc.save(str(filepath))
    doc.close()


def generate_synthetic_image(filepath: Path, title: str, lines: List[str], doc_type: str, blurry: bool = False) -> None:
    """Generate a synthetic image document (JPG/PNG) with clear watermarks."""
    width, height = 900, 600
    img = Image.new("RGB", (width, height), color=(248, 248, 246))
    draw = ImageDraw.Draw(img)

    # Border
    draw.rectangle([20, 20, width - 20, height - 20], outline=(180, 180, 180), width=2)

    # Top Watermark
    draw.rectangle([30, 30, width - 30, 65], fill=(250, 235, 235), outline=(220, 120, 120))
    draw.text((70, 40), WATERMARK_TEXT, fill=(180, 40, 30))

    # Title
    draw.text((50, 90), title, fill=(20, 20, 20))
    draw.text((50, 115), f"Document Type: {doc_type}", fill=(100, 100, 100))
    draw.line([(50, 140), (width - 50, 140)], fill=(200, 200, 200), width=1)

    y = 165
    for line in lines:
        draw.text((50, y), line, fill=(30, 30, 30))
        y += 30

    # Diagonal Watermark
    draw.text((120, 400), "SYNTHETIC TEST DOCUMENT", fill=(225, 225, 225))

    # Bottom Banner
    draw.rectangle([30, height - 60, width - 30, height - 30], fill=(250, 235, 235), outline=(220, 120, 120))
    draw.text((60, height - 50), WATERMARK_TEXT + " (SAMPLE FIXTURE)", fill=(180, 40, 30))

    if blurry:
        # Create unreadable/low quality effect
        from PIL import ImageFilter
        img = img.filter(ImageFilter.GaussianBlur(radius=8))

    img.save(str(filepath))


# Comprehensive Definition of the 10 Synthetic Demonstration Applicants & Documents
DEMO_APPLICANTS = [
    {
        "id": "APP-DEMO-001",
        "name": "Priya Sharma",
        "email": "priya.sharma@demo-synthetic.org",
        "phone": "+91 98201 11223",
        "status": "verified",
        "risk_level": "low",
        "consistency_score": 100.0,
        "notes": "All identity records match. Perfect PAN and Aadhaar correlation.",
        "documents": [
            {
                "id": "DOC-DEMO-001",
                "filename": "demo_priya_sharma_pan.pdf",
                "title": "INCOME TAX DEPARTMENT - GOVT. OF INDIA",
                "doc_type": "PAN",
                "review_status": "approved",
                "processing_status": "completed",
                "extracted_fields": {
                    "name": "PRIYA SHARMA",
                    "id_number": "ABCPS1234F",
                    "dob": "1992-05-14",
                    "father_name": "RAMESH SHARMA"
                },
                "validation": {"is_valid": True, "issues": [], "age": 32},
                "lines": [
                    "INCOME TAX DEPARTMENT - GOVT. OF INDIA",
                    "PERMANENT ACCOUNT NUMBER CARD",
                    "Permanent Account Number: ABCPS1234F",
                    "Name: PRIYA SHARMA",
                    "Father's Name: RAMESH SHARMA",
                    "Date of Birth: 14/05/1992",
                    "Signature: Verified Digital Asset"
                ]
            },
            {
                "id": "DOC-DEMO-002",
                "filename": "demo_priya_sharma_aadhaar.pdf",
                "title": "GOVERNMENT OF INDIA - UIDAI",
                "doc_type": "AADHAAR",
                "review_status": "approved",
                "processing_status": "completed",
                "extracted_fields": {
                    "name": "Priya Sharma",
                    "id_number": "XXXX-XXXX-4821",
                    "dob": "1992-05-14",
                    "gender": "Female",
                    "address": "Flat 402, Sunrise Heights, Andheri West, Mumbai 400053"
                },
                "validation": {"is_valid": True, "issues": [], "age": 32},
                "lines": [
                    "UNIQUE IDENTIFICATION AUTHORITY OF INDIA",
                    "To: Priya Sharma",
                    "DOB: 14/05/1992",
                    "Gender: Female",
                    "Address: Flat 402, Sunrise Heights, Andheri West, Mumbai 400053",
                    "Your Aadhaar No. : 9876 5432 4821"
                ]
            }
        ]
    },
    {
        "id": "APP-DEMO-002",
        "name": "Rajesh Kumar Verma",
        "email": "rajesh.verma@demo-synthetic.org",
        "phone": "+91 98111 22334",
        "status": "requires_attention",
        "risk_level": "medium",
        "consistency_score": 86.0,
        "notes": "Name variance: 'Rajesh Kumar Verma' on Driving Licence vs 'Rajesh Kumar V.' on PAN Card.",
        "documents": [
            {
                "id": "DOC-DEMO-003",
                "filename": "demo_rajesh_verma_dl.pdf",
                "title": "UNION OF INDIA - DRIVING LICENCE",
                "doc_type": "DRIVING_LICENCE",
                "review_status": "approved",
                "processing_status": "completed",
                "extracted_fields": {
                    "name": "RAJESH KUMAR VERMA",
                    "id_number": "DL-1420110012345",
                    "dob": "1988-11-20",
                    "expiry_date": "2033-11-19"
                },
                "validation": {"is_valid": True, "issues": [], "age": 36},
                "lines": [
                    "TRANSPORT DEPARTMENT - DRIVING LICENCE",
                    "Licence Number: DL-1420110012345",
                    "Name: RAJESH KUMAR VERMA",
                    "Date of Birth: 20/11/1988",
                    "Valid Till: 19/11/2033",
                    "Non-Transport Class: LMV, MCWG"
                ]
            },
            {
                "id": "DOC-DEMO-004",
                "filename": "demo_rajesh_verma_pan.pdf",
                "title": "INCOME TAX DEPARTMENT - GOVT. OF INDIA",
                "doc_type": "PAN",
                "review_status": "manual_review",
                "processing_status": "completed",
                "extracted_fields": {
                    "name": "RAJESH KUMAR V",
                    "id_number": "ABCPV5678G",
                    "dob": "1988-11-20"
                },
                "validation": {"is_valid": True, "issues": ["Minor name variation against DL"], "age": 36},
                "lines": [
                    "INCOME TAX DEPARTMENT - GOVT. OF INDIA",
                    "PERMANENT ACCOUNT NUMBER CARD",
                    "Permanent Account Number: ABCPV5678G",
                    "Name: RAJESH KUMAR V",
                    "Date of Birth: 20/11/1988"
                ]
            }
        ]
    },
    {
        "id": "APP-DEMO-003",
        "name": "Ananya Deshmukh",
        "email": "ananya.deshmukh@demo-synthetic.org",
        "phone": "+91 97654 33445",
        "status": "requires_attention",
        "risk_level": "high",
        "consistency_score": 72.0,
        "notes": "Passport expired on 15/08/2021. Requires valid renewed proof of identification.",
        "documents": [
            {
                "id": "DOC-DEMO-005",
                "filename": "demo_ananya_deshmukh_passport.pdf",
                "title": "PASSPORT - REPUBLIC OF INDIA",
                "doc_type": "PASSPORT",
                "review_status": "manual_review",
                "processing_status": "completed",
                "extracted_fields": {
                    "name": "ANANYA DESHMUKH",
                    "id_number": "Z9876543",
                    "dob": "1995-09-04",
                    "expiry_date": "2021-08-15"
                },
                "validation": {"is_valid": False, "issues": ["Document has expired (Expired: 2021-08-15)"], "age": 29},
                "lines": [
                    "PASSPORT - REPUBLIC OF INDIA",
                    "Passport No: Z9876543",
                    "Type: P | Country Code: IND",
                    "Given Name: ANANYA",
                    "Surname: DESHMUKH",
                    "Date of Birth: 04/09/1995",
                    "Date of Issue: 16/08/2011",
                    "Date of Expiry: 15/08/2021"
                ]
            },
            {
                "id": "DOC-DEMO-006",
                "filename": "demo_ananya_deshmukh_pan.pdf",
                "title": "INCOME TAX DEPARTMENT - GOVT. OF INDIA",
                "doc_type": "PAN",
                "review_status": "approved",
                "processing_status": "completed",
                "extracted_fields": {
                    "name": "ANANYA DESHMUKH",
                    "id_number": "ABCPD9012E",
                    "dob": "1995-09-04"
                },
                "validation": {"is_valid": True, "issues": [], "age": 29},
                "lines": [
                    "INCOME TAX DEPARTMENT - GOVT. OF INDIA",
                    "Permanent Account Number: ABCPD9012E",
                    "Name: ANANYA DESHMUKH",
                    "Date of Birth: 04/09/1995"
                ]
            }
        ]
    },
    {
        "id": "APP-DEMO-004",
        "name": "Vikram Malhotra",
        "email": "vikram.malhotra@demo-synthetic.org",
        "phone": "+91 98450 55667",
        "status": "requires_attention",
        "risk_level": "high",
        "consistency_score": 58.0,
        "notes": "Critical Date of Birth mismatch: 1985-04-12 on PAN vs 1990-08-20 on Aadhaar.",
        "documents": [
            {
                "id": "DOC-DEMO-007",
                "filename": "demo_vikram_malhotra_pan.pdf",
                "title": "INCOME TAX DEPARTMENT - GOVT. OF INDIA",
                "doc_type": "PAN",
                "review_status": "manual_review",
                "processing_status": "completed",
                "extracted_fields": {
                    "name": "VIKRAM MALHOTRA",
                    "id_number": "ABCPM9988D",
                    "dob": "1985-04-12"
                },
                "validation": {"is_valid": True, "issues": [], "age": 39},
                "lines": [
                    "INCOME TAX DEPARTMENT - GOVT. OF INDIA",
                    "Permanent Account Number: ABCPM9988D",
                    "Name: VIKRAM MALHOTRA",
                    "Date of Birth: 12/04/1985"
                ]
            },
            {
                "id": "DOC-DEMO-008",
                "filename": "demo_vikram_malhotra_aadhaar.pdf",
                "title": "GOVERNMENT OF INDIA - UIDAI",
                "doc_type": "AADHAAR",
                "review_status": "manual_review",
                "processing_status": "completed",
                "extracted_fields": {
                    "name": "Vikram Malhotra",
                    "id_number": "XXXX-XXXX-9912",
                    "dob": "1990-08-20",
                    "gender": "Male"
                },
                "validation": {"is_valid": True, "issues": ["Cross-document DOB mismatch with PAN (1985 vs 1990)"], "age": 34},
                "lines": [
                    "UNIQUE IDENTIFICATION AUTHORITY OF INDIA",
                    "Name: Vikram Malhotra",
                    "DOB: 20/08/1990",
                    "Gender: Male",
                    "Your Aadhaar No. : 1234 5678 9912"
                ]
            }
        ]
    },
    {
        "id": "APP-DEMO-005",
        "name": "Sunita Banerjee",
        "email": "sunita.banerjee@demo-synthetic.org",
        "phone": "+91 93300 66778",
        "status": "verified",
        "risk_level": "low",
        "consistency_score": 98.0,
        "notes": "Verified against Election Commission Voter ID and PAN card.",
        "documents": [
            {
                "id": "DOC-DEMO-009",
                "filename": "demo_sunita_banerjee_voterid.pdf",
                "title": "ELECTION COMMISSION OF INDIA - IDENTITY CARD",
                "doc_type": "VOTER_ID",
                "review_status": "approved",
                "processing_status": "completed",
                "extracted_fields": {
                    "name": "SUNITA BANERJEE",
                    "id_number": "ABC1234567",
                    "dob": "1978-02-10",
                    "gender": "Female"
                },
                "validation": {"is_valid": True, "issues": [], "age": 46},
                "lines": [
                    "ELECTION COMMISSION OF INDIA - IDENTITY CARD",
                    "EPIC No: ABC1234567",
                    "Elector's Name: SUNITA BANERJEE",
                    "Father's Name: PRADIP BANERJEE",
                    "Sex: Female",
                    "Date of Birth: 10/02/1978"
                ]
            },
            {
                "id": "DOC-DEMO-010",
                "filename": "demo_sunita_banerjee_pan.pdf",
                "title": "INCOME TAX DEPARTMENT - GOVT. OF INDIA",
                "doc_type": "PAN",
                "review_status": "approved",
                "processing_status": "completed",
                "extracted_fields": {
                    "name": "SUNITA BANERJEE",
                    "id_number": "ABCPB3344F",
                    "dob": "1978-02-10"
                },
                "validation": {"is_valid": True, "issues": [], "age": 46},
                "lines": [
                    "INCOME TAX DEPARTMENT - GOVT. OF INDIA",
                    "Permanent Account Number: ABCPB3344F",
                    "Name: SUNITA BANERJEE",
                    "Date of Birth: 10/02/1978"
                ]
            }
        ]
    },
    {
        "id": "APP-DEMO-006",
        "name": "Siddharth Nair",
        "email": "siddharth.nair@demo-synthetic.org",
        "phone": "+91 94470 77889",
        "status": "pending",
        "risk_level": "medium",
        "consistency_score": 45.0,
        "notes": "Low quality OCR scan. ID number missing from document text. Needs officer review.",
        "documents": [
            {
                "id": "DOC-DEMO-011",
                "filename": "demo_siddharth_nair_incomplete.pdf",
                "title": "INCOME TAX DEPARTMENT - (LOW QUALITY SCAN)",
                "doc_type": "PAN",
                "review_status": "manual_review",
                "processing_status": "completed",
                "extracted_fields": {
                    "name": "SIDDHARTH NAIR",
                    "id_number": None,
                    "dob": None
                },
                "validation": {"is_valid": False, "issues": ["PAN ID number not detected", "Mandatory field 'dob' missing"]},
                "lines": [
                    "INCOME TAX DEPARTMENT - GOVT. OF INDIA",
                    "Name: SIDDHARTH NAIR",
                    "...[UNREADABLE SMUDGE OCCURRED HERE]...",
                    "Signature: Verified"
                ]
            }
        ]
    },
    {
        "id": "APP-DEMO-007",
        "name": "Rohit Kulkarni",
        "email": "rohit.kulkarni@demo-synthetic.org",
        "phone": "+91 98220 88990",
        "status": "requires_attention",
        "risk_level": "high",
        "consistency_score": 0.0,
        "notes": "Severely blurred uploaded image. Text extraction failed. Resubmission required.",
        "documents": [
            {
                "id": "DOC-DEMO-012",
                "filename": "demo_rohit_kulkarni_unreadable.png",
                "title": "BLURRED / UNREADABLE SCAN",
                "doc_type": "UNKNOWN",
                "is_image": True,
                "blurry": True,
                "review_status": "rejected",
                "processing_status": "failed",
                "extracted_fields": {},
                "validation": {"is_valid": False, "issues": ["Image resolution/blur prevented text extraction"]},
                "lines": [
                    "~~~ UNREADABLE NOISE ARTIFACTS ~~~"
                ]
            }
        ]
    },
    {
        "id": "APP-DEMO-008",
        "name": "Meera Venkatesh",
        "email": "meera.venkatesh@demo-synthetic.org",
        "phone": "+91 98410 99001",
        "status": "pending",
        "risk_level": "low",
        "consistency_score": 0.0,
        "notes": "Fresh upload. Awaiting verification officer queue review.",
        "documents": [
            {
                "id": "DOC-DEMO-013",
                "filename": "demo_meera_venkatesh_pan.pdf",
                "title": "INCOME TAX DEPARTMENT - GOVT. OF INDIA",
                "doc_type": "PAN",
                "review_status": "pending",
                "processing_status": "completed",
                "extracted_fields": {
                    "name": "MEERA VENKATESH",
                    "id_number": "ABCPV7788M",
                    "dob": "1998-07-22"
                },
                "validation": {"is_valid": True, "issues": [], "age": 26},
                "lines": [
                    "INCOME TAX DEPARTMENT - GOVT. OF INDIA",
                    "PERMANENT ACCOUNT NUMBER CARD",
                    "Permanent Account Number: ABCPV7788M",
                    "Name: MEERA VENKATESH",
                    "Father's Name: K. VENKATESH",
                    "Date of Birth: 22/07/1998"
                ]
            }
        ]
    },
    {
        "id": "APP-DEMO-009",
        "name": "Kavita Joshi",
        "email": "kavita.joshi@demo-synthetic.org",
        "phone": "+91 99887 11224",
        "status": "verified",
        "risk_level": "low",
        "consistency_score": 100.0,
        "notes": "Housing finance applicant verified with international passport and PAN.",
        "documents": [
            {
                "id": "DOC-DEMO-014",
                "filename": "demo_kavita_joshi_passport.pdf",
                "title": "PASSPORT - REPUBLIC OF INDIA",
                "doc_type": "PASSPORT",
                "review_status": "approved",
                "processing_status": "completed",
                "extracted_fields": {
                    "name": "KAVITA JOSHI",
                    "id_number": "P1234567",
                    "dob": "1984-03-15",
                    "expiry_date": "2032-12-31"
                },
                "validation": {"is_valid": True, "issues": [], "age": 40},
                "lines": [
                    "PASSPORT - REPUBLIC OF INDIA",
                    "Passport No: P1234567",
                    "Given Name: KAVITA",
                    "Surname: JOSHI",
                    "Date of Birth: 15/03/1984",
                    "Date of Issue: 01/01/2023",
                    "Date of Expiry: 31/12/2032"
                ]
            },
            {
                "id": "DOC-DEMO-015",
                "filename": "demo_kavita_joshi_pan.pdf",
                "title": "INCOME TAX DEPARTMENT - GOVT. OF INDIA",
                "doc_type": "PAN",
                "review_status": "approved",
                "processing_status": "completed",
                "extracted_fields": {
                    "name": "KAVITA JOSHI",
                    "id_number": "ABCPJ4455K",
                    "dob": "1984-03-15"
                },
                "validation": {"is_valid": True, "issues": [], "age": 40},
                "lines": [
                    "INCOME TAX DEPARTMENT - GOVT. OF INDIA",
                    "Permanent Account Number: ABCPJ4455K",
                    "Name: KAVITA JOSHI",
                    "Date of Birth: 15/03/1984"
                ]
            }
        ]
    },
    {
        "id": "APP-DEMO-010",
        "name": "Gaurav Singhania",
        "email": "gaurav.singhania@demo-synthetic.org",
        "phone": "+91 97110 55443",
        "status": "requires_attention",
        "risk_level": "high",
        "consistency_score": 0.0,
        "notes": "Invalid ID structure detected. PAN format does not comply with official specification.",
        "documents": [
            {
                "id": "DOC-DEMO-016",
                "filename": "demo_gaurav_singhania_pan.pdf",
                "title": "INCOME TAX DEPARTMENT - (DEFECTIVE RECORD)",
                "doc_type": "PAN",
                "review_status": "rejected",
                "processing_status": "completed",
                "extracted_fields": {
                    "name": "GAURAV SINGHANIA",
                    "id_number": "ABC1234567",  # Malformed PAN (only 3 letters)
                    "dob": "1989-10-05"
                },
                "validation": {"is_valid": False, "issues": ["Invalid PAN structure: Expected 5 letters, 4 digits, 1 letter"]},
                "lines": [
                    "INCOME TAX DEPARTMENT - GOVT. OF INDIA",
                    "Permanent Account Number: ABC1234567",
                    "Name: GAURAV SINGHANIA",
                    "Date of Birth: 05/10/1989"
                ]
            }
        ]
    }
]


def seed_demo_dataset(db_path: Optional[str] = None, force_reset: bool = False) -> Dict[str, Any]:
    """
    Idempotently seed the SQLite database and create synthetic file fixtures.
    If force_reset is True, deletes existing demo records before re-inserting.
    Never alters or destroys non-demo user data.
    """
    DEMO_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    init_db(db_path=db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    demo_applicant_ids = [app["id"] for app in DEMO_APPLICANTS]
    placeholders = ",".join("?" for _ in demo_applicant_ids)

    if force_reset:
        cursor.execute(f"DELETE FROM audit_reviews WHERE applicant_id IN ({placeholders})", demo_applicant_ids)
        cursor.execute(f"DELETE FROM documents WHERE applicant_id IN ({placeholders})", demo_applicant_ids)
        cursor.execute(f"DELETE FROM applicants WHERE id IN ({placeholders})", demo_applicant_ids)
        conn.commit()

    created_applicants = 0
    created_documents = 0

    for app in DEMO_APPLICANTS:
        # 1. Insert or update applicant
        cursor.execute("""
            INSERT INTO applicants (id, name, email, phone, status, risk_level, consistency_score, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                email = excluded.email,
                phone = excluded.phone,
                status = excluded.status,
                risk_level = excluded.risk_level,
                consistency_score = excluded.consistency_score,
                notes = excluded.notes
        """, (
            app["id"],
            app["name"],
            app["email"],
            app["phone"],
            app["status"],
            app["risk_level"],
            app["consistency_score"],
            app["notes"]
        ))
        created_applicants += 1

        # 2. Generate documents for applicant
        for doc_info in app["documents"]:
            file_path = DEMO_STORAGE_DIR / doc_info["filename"]
            is_img = doc_info.get("is_image", False)
            blurry = doc_info.get("blurry", False)

            # Generate physical file fixture on disk
            if is_img:
                generate_synthetic_image(file_path, doc_info["title"], doc_info["lines"], doc_info["doc_type"], blurry=blurry)
                mime = "image/png"
            else:
                generate_synthetic_pdf(file_path, doc_info["title"], doc_info["lines"], doc_info["doc_type"])
                mime = "application/pdf"

            file_size = file_path.stat().st_size
            file_hash = _calculate_file_hash(file_path)

            extracted_text = "\n".join(doc_info["lines"]) + f"\n{WATERMARK_TEXT}"
            fields_json = json.dumps(doc_info.get("extracted_fields", {}))
            validation_json = json.dumps(doc_info.get("validation", {}))

            cursor.execute("""
                INSERT INTO documents (
                    id, applicant_id, original_filename, stored_filename,
                    document_type, classified_type, classification_confidence,
                    file_size, file_hash, mime_type,
                    processing_status, review_status,
                    extracted_text, extracted_fields, validation_results,
                    reviewed_by, reviewed_at, review_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    original_filename = excluded.original_filename,
                    stored_filename = excluded.stored_filename,
                    document_type = excluded.document_type,
                    classified_type = excluded.classified_type,
                    classification_confidence = excluded.classification_confidence,
                    file_size = excluded.file_size,
                    file_hash = excluded.file_hash,
                    mime_type = excluded.mime_type,
                    processing_status = excluded.processing_status,
                    review_status = excluded.review_status,
                    extracted_text = excluded.extracted_text,
                    extracted_fields = excluded.extracted_fields,
                    validation_results = excluded.validation_results,
                    reviewed_by = excluded.reviewed_by,
                    reviewed_at = excluded.reviewed_at,
                    review_notes = excluded.review_notes
            """, (
                doc_info["id"],
                app["id"],
                doc_info["filename"],
                str(file_path),
                doc_info["doc_type"].lower(),
                doc_info["doc_type"],
                0.96 if doc_info["doc_type"] != "UNKNOWN" else 0.0,
                file_size,
                file_hash,
                mime,
                doc_info["processing_status"],
                doc_info["review_status"],
                extracted_text,
                fields_json,
                validation_json,
                "Arjun Mehta (Review Officer)" if doc_info["review_status"] == "approved" else None,
                datetime.now(timezone.utc).isoformat() if doc_info["review_status"] == "approved" else None,
                f"Demonstration fixture: {doc_info['review_status'].upper()}"
            ))
            created_documents += 1

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "message": f"Demonstration dataset successfully seeded ({created_applicants} applicants, {created_documents} documents).",
        "applicants_count": created_applicants,
        "documents_count": created_documents
    }


def reset_demo_dataset(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Cleanly re-seed demonstration data to its initial pristine benchmark state."""
    return seed_demo_dataset(db_path=db_path, force_reset=True)


if __name__ == "__main__":
    print("=" * 70)
    print("Seeding VeriDoc-AI Synthetic Demonstration Dataset...")
    print("=" * 70)
    res = seed_demo_dataset()
    print(f"Status: {res['status']}")
    print(f"Details: {res['message']}")
