import os
import re
import logging
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger(__name__)


class DocumentClassifier:
    """
    Classifies Indian KYC documents into one of 5 supported types:
    - pan (Permanent Account Number / Form 49A)
    - aadhaar (Unique Identification Authority of India)
    - passport (Republic of India Passport)
    - voter_id (Election Commission of India / EPIC)
    - driving_licence (State Transport / Ministry of Road Transport)
    """

    # Keyword rules with positive weights (supports OCR variations and spacing)
    KEYWORD_RULES = {
        "pan": [
            ("INCOME TAX DEPARTMENT", 35),
            ("INCOMETAX DEPARTMENT", 35),
            ("INCOME TAX", 20),
            ("PERMANENT ACCOUNT NUMBER", 35),
            ("PERMANENT ACCOUNT NO", 35),
            ("PERMANENT ACCOUNT", 25),
            ("ACCOUNT NUMBER", 15),
            ("PAN CARD", 30),
            ("FORM 49A", 30),
            ("GOVT. OF INDIA", 15),
            ("GOVT OF INDIA", 15),
            ("GOVERNMENT OF INDIA", 15),
            ("FATHER'S NAME", 10),
            ("FATHERS NAME", 10),
            ("DATE OF BIRTH", 10),
            ("SIGNATURE", 5),
            ("PAN", 15),
        ],
        "aadhaar": [
            ("UNIQUE IDENTIFICATION AUTHORITY OF INDIA", 40),
            ("UNIQUE IDENTIFICATION", 30),
            ("AUTHORITY OF INDIA", 20),
            ("UIDAI", 35),
            ("GOVERNMENT OF INDIA", 20),
            ("GOVT OF INDIA", 15),
            ("AADHAAR", 35),
            ("AADHAR", 35),
            ("ADHAAR", 30),
            ("AADHAAR NO", 30),
            ("AADHAR NO", 30),
            ("ENROLMENT NO", 25),
            ("ENROLLMENT NO", 25),
            ("MERA AADHAAR", 30),
            ("MERI PEHCHAN", 25),
            ("VID", 20),
            ("HELP@UIDAI", 20),
            ("DOB", 10),
            ("YEAR OF BIRTH", 15),
            ("FEMALE", 10),
            ("MALE", 10),
        ],
        "passport": [
            ("REPUBLIC OF INDIA", 35),
            ("PASSPORT", 40),
            ("PASSEPORT", 30),
            ("PASSPORT NO", 35),
            ("PASSPORT NUMBER", 35),
            ("TYPE P", 25),
            ("CODE IND", 25),
            ("NATIONALITY", 20),
            ("PLACE OF BIRTH", 20),
            ("PLACE OF ISSUE", 20),
            ("DATE OF ISSUE", 20),
            ("DATE OF EXPIRY", 25),
            ("MINISTRY OF EXTERNAL AFFAIRS", 35),
            ("EXTERNAL AFFAIRS", 25),
            ("GIVEN NAME", 15),
            ("SURNAME", 15),
            ("P<IND", 35),
        ],
        "voter_id": [
            ("ELECTION COMMISSION OF INDIA", 40),
            ("ELECTION COMMISSION", 35),
            ("ELECTOR PHOTO IDENTITY CARD", 40),
            ("ELECTOR'S PHOTO IDENTITY CARD", 40),
            ("ELECTORS PHOTO IDENTITY CARD", 40),
            ("ELECTOR", 30),
            ("ELECTORAL", 25),
            ("EPIC", 35),
            ("EPIC NO", 35),
            ("EPIC NUMBER", 35),
            ("PHOTO IDENTITY CARD", 30),
            ("BHARAT NIRVACHAN AAYOG", 35),
            ("BHARAT NIRVACHAN", 35),
            ("NIRVACHAN", 25),
            ("IDENTITY CARD", 20),
            ("ASSEMBLY CONSTITUENCY", 25),
            ("PARLIAMENTARY CONSTITUENCY", 20),
            ("ELECTOR'S NAME", 25),
            ("ELECTORS NAME", 25),
        ],
        "driving_licence": [
            ("DRIVING LICENCE", 40),
            ("DRIVING LICENSE", 40),
            ("UNION OF INDIA", 25),
            ("MOTOR VEHICLES", 30),
            ("MOTOR VEHICLE", 25),
            ("LICENCE TO DRIVE", 35),
            ("LICENSE TO DRIVE", 35),
            ("VALIDITY", 20),
            ("NON-TRANSPORT", 25),
            ("TRANSPORT", 20),
            ("DL NO", 35),
            ("DL NUMBER", 35),
            ("AUTHORISED TO DRIVE", 25),
            ("FORM 7", 20),
            ("SARATHI", 25),
        ],
        "salary_slip": [
            ("SALARY SLIP", 45),
            ("PAYSLIP", 45),
            ("PAY SLIP", 45),
            ("EARNINGS", 25),
            ("BASIC PAY", 30),
            ("BASIC SALARY", 30),
            ("HOUSE RENT ALLOWANCE", 30),
            ("HRA", 25),
            ("PROVIDENT FUND", 30),
            ("EPF", 25),
            ("PF NO", 25),
            ("GROSS SALARY", 35),
            ("GROSS EARNINGS", 35),
            ("GROSS PAY", 35),
            ("NET SALARY", 40),
            ("NET PAY", 40),
            ("TOTAL DEDUCTIONS", 30),
            ("DEDUCTIONS", 20),
            ("EMPLOYEE ID", 25),
            ("EMP ID", 25),
            ("PAY PERIOD", 25),
            ("PAYSLIP FOR THE MONTH", 40),
        ],
        "bank_statement": [
            ("BANK STATEMENT", 45),
            ("ACCOUNT STATEMENT", 45),
            ("STATEMENT OF ACCOUNT", 45),
            ("TRANSACTION DATE", 30),
            ("VALUE DATE", 25),
            ("WITHDRAWAL", 25),
            ("DEPOSIT", 25),
            ("CLOSING BALANCE", 35),
            ("OPENING BALANCE", 30),
            ("IFSC", 35),
            ("IFSC CODE", 35),
            ("ACCOUNT NUMBER", 30),
            ("A/C NO", 25),
            ("SAVINGS ACCOUNT", 30),
            ("CURRENT ACCOUNT", 30),
            ("AVAILABLE BALANCE", 30),
            ("BRANCH NAME", 20),
        ],
        "commercial_invoice": [
            ("TAX INVOICE", 45),
            ("COMMERCIAL INVOICE", 45),
            ("INVOICE NO", 40),
            ("INVOICE NUMBER", 40),
            ("INVOICE DATE", 30),
            ("BILL TO", 35),
            ("SHIP TO", 35),
            ("GSTIN", 40),
            ("GST NO", 35),
            ("SUBTOTAL", 30),
            ("TOTAL AMOUNT", 35),
            ("GRAND TOTAL", 35),
            ("DUE DATE", 25),
            ("PURCHASE ORDER", 25),
            ("PO NUMBER", 25),
            ("UNIT PRICE", 25),
            ("CGST", 30),
            ("SGST", 30),
            ("IGST", 30),
            ("HSN CODE", 25),
        ],
        "tax_form_16": [
            ("FORM NO. 16", 50),
            ("FORM 16", 50),
            ("CERTIFICATE UNDER SECTION 203", 45),
            ("INCOME-TAX ACT", 35),
            ("TAN OF DEDUCTOR", 40),
            ("PAN OF EMPLOYEE", 35),
            ("ASSESSMENT YEAR", 35),
            ("FINANCIAL YEAR", 25),
            ("TAX DEDUCTED AT SOURCE", 40),
            ("TDS", 30),
            ("PART A", 25),
            ("PART B", 25),
            ("SUMMARY OF TAX", 30),
        ],
        "utility_bill": [
            ("ELECTRICITY BILL", 50),
            ("UTILITY BILL", 45),
            ("CONSUMER NUMBER", 40),
            ("CONSUMER NO", 40),
            ("METER NUMBER", 35),
            ("METER NO", 35),
            ("UNITS CONSUMED", 35),
            ("BILL AMOUNT", 30),
            ("AMOUNT PAYABLE", 30),
            ("DISCONNECTION DATE", 35),
            ("BILLING PERIOD", 25),
            ("POWER DISTRIBUTION", 30),
            ("WATER BILL", 45),
            ("GAS BILL", 45),
        ],
    }

    # Regex patterns that strongly identify document types
    PATTERN_RULES = {
        "pan": [
            re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.IGNORECASE),
            re.compile(r"PAN[:\s\-\#]*([A-Z]{5}[0-9]{4}[A-Z])", re.IGNORECASE),
        ],
        "aadhaar": [
            re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b"),
            re.compile(r"\b\d{4}-\d{4}-\d{4}\b"),
            re.compile(r"\b[X\d]{4}\s[X\d]{4}\s\d{4}\b", re.IGNORECASE),
            re.compile(r"\b[X\d]{4}-[X\d]{4}-\d{4}\b", re.IGNORECASE),
            re.compile(r"\b\d{12}\b"),
            re.compile(r"VID[:\s]*\d{4}\s\d{4}\s\d{4}\s\d{4}", re.IGNORECASE),
        ],
        "passport": [
            re.compile(r"\b[A-Z][0-9]{7}\b", re.IGNORECASE),
            re.compile(r"P<[A-Z]{3}", re.IGNORECASE),
            re.compile(r"PASSPORT[\s\w]*[:\s\-\#]*([A-Z][0-9]{7})", re.IGNORECASE),
        ],
        "voter_id": [
            re.compile(r"\b[A-Z]{3}[\s\-]?[0-9]{7}\b", re.IGNORECASE),
            re.compile(r"\b[A-Z]{2}[0-9]{8}\b", re.IGNORECASE),
            re.compile(r"EPIC[:\s\-\#]*([A-Z0-9\s\-]{10,12})", re.IGNORECASE),
        ],
        "driving_licence": [
            re.compile(r"\b[A-Z]{2}[-\s]?[0-9]{2}[-\s]?[0-9]{11}\b", re.IGNORECASE),
            re.compile(r"\b[A-Z]{2}[0-9]{13,15}\b", re.IGNORECASE),
            re.compile(r"\bDL[-\s]?[A-Z0-9]{8,16}\b", re.IGNORECASE),
            re.compile(r"DL\s*NO[:\s\-]*([A-Z0-9\-]+)", re.IGNORECASE),
        ],
        "salary_slip": [
            re.compile(r"NET\s*(?:PAY|SALARY)[\s:]*(?:RS\.?|INR)?\s*[\d,]+(?:\.\d{2})?", re.IGNORECASE),
            re.compile(r"EMP(?:LOYEE)?\s*ID[\s:]*([A-Z0-9\-]+)", re.IGNORECASE),
        ],
        "bank_statement": [
            re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b"),  # IFSC code
            re.compile(r"ACCOUNT\s*(?:NO|NUMBER)?[:\s\-]*\d{9,18}", re.IGNORECASE),
        ],
        "commercial_invoice": [
            re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}\b"),  # Indian GSTIN
            re.compile(r"INV(?:OICE)?\s*(?:NO|NUMBER)?[:\s\-#]*([A-Z0-9\-\/]+)", re.IGNORECASE),
        ],
        "tax_form_16": [
            re.compile(r"\b[A-Z]{4}\d{5}[A-Z]\b"),  # TAN 10-char
            re.compile(r"ASSESSMENT\s*YEAR[:\s\-]*\d{4}[-\s]?\d{2,4}", re.IGNORECASE),
        ],
        "utility_bill": [
            re.compile(r"CONSUMER\s*(?:NO|NUMBER|ID)[:\s\-]*([A-Z0-9\-]+)", re.IGNORECASE),
            re.compile(r"METER\s*(?:NO|NUMBER)[:\s\-]*([A-Z0-9\-]+)", re.IGNORECASE),
        ],
    }

    # Metadata for classification types
    TYPE_METADATA = {
        "pan": {"display_name": "PAN Card", "category": "kyc_identity"},
        "aadhaar": {"display_name": "Aadhaar Card", "category": "kyc_identity"},
        "passport": {"display_name": "Passport", "category": "kyc_identity"},
        "voter_id": {"display_name": "Voter ID", "category": "kyc_identity"},
        "driving_licence": {"display_name": "Driving Licence", "category": "kyc_identity"},
        "salary_slip": {"display_name": "Salary Certificate / Payslip", "category": "financial"},
        "bank_statement": {"display_name": "Bank Statement", "category": "financial"},
        "commercial_invoice": {"display_name": "Commercial Invoice", "category": "commercial"},
        "tax_form_16": {"display_name": "Form 16 / Tax Statement", "category": "tax"},
        "utility_bill": {"display_name": "Utility Bill", "category": "utility"},
        "unknown": {"display_name": "Unknown Document", "category": "general"},
    }

    @classmethod
    def classify(cls, text: str, db_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Classify document text based on weighted keyword occurrences and regex patterns.
        Supports both built-in types (KYC identity + business documents) and dynamic document
        types defined in document_type_definitions.
        """
        if not text or not text.strip():
            return {
                "classified_type": "unknown",
                "confidence": 0.0,
                "display_name": cls.TYPE_METADATA["unknown"]["display_name"],
                "category": cls.TYPE_METADATA["unknown"]["category"],
                "matched_keywords": [],
                "matched_patterns": [],
                "scores": {k: 0.0 for k in cls.KEYWORD_RULES.keys()},
            }

        # Normalize text for matching
        upper_text = text.upper()
        # Cleaned text with single spaces and punctuation stripped for loose matching
        clean_norm_text = re.sub(r"[^\w\s]", " ", upper_text)
        clean_norm_text = " ".join(clean_norm_text.split())

        raw_scores: Dict[str, float] = {k: 0.0 for k in cls.KEYWORD_RULES.keys()}
        matched_keywords_by_type: Dict[str, List[str]] = {k: [] for k in cls.KEYWORD_RULES.keys()}
        matched_patterns_by_type: Dict[str, List[str]] = {k: [] for k in cls.KEYWORD_RULES.keys()}

        # Check for dynamic database-registered document types if database is accessible
        dynamic_types: Dict[str, Dict[str, Any]] = {}
        if db_path is not None or os.getenv("DATABASE_URL") or os.getenv("USE_POSTGRES"):
            try:
                from backend.database.db import list_document_types, get_document_schema
                db_types = list_document_types(db_path=db_path)
                for dt in db_types:
                    t_id = str(dt.get("type_key") or dt.get("id") or "")
                    if not t_id or t_id in cls.KEYWORD_RULES:
                        continue
                    dynamic_types[t_id] = dt
                    raw_scores[t_id] = 0.0
                    matched_keywords_by_type[t_id] = []
                    matched_patterns_by_type[t_id] = []

                    # Also load rules_json from schema if available
                    if not dt.get("rules_json"):
                        try:
                            s_row = get_document_schema(t_id, db_path=db_path)
                            if s_row and (s_row.get("attribute_definitions") or s_row.get("schema_definition")):
                                s_def = s_row.get("attribute_definitions") or s_row.get("schema_definition")
                                if isinstance(s_def, str):
                                    import json
                                    s_def = json.loads(s_def)
                                dt["rules_json"] = s_def.get("rules") or s_def
                        except Exception:
                            pass
            except Exception as dt_exc:
                logger.debug(f"Could not load dynamic document types: {dt_exc}")

        # 1. Match Keywords
        for doc_type, rules in cls.KEYWORD_RULES.items():
            for kw, weight in rules:
                clean_kw = " ".join(re.sub(r"[^\w\s]", " ", kw).split())
                if kw in upper_text or clean_kw in clean_norm_text:
                    raw_scores[doc_type] += weight
                    matched_keywords_by_type[doc_type].append(kw)

        # 1b. Match Dynamic Keywords from database rules_json or display_name
        for dt_id, dt_data in dynamic_types.items():
            # Check display_name matching
            disp_name = dt_data.get("display_name", "")
            if disp_name:
                clean_disp = " ".join(re.sub(r"[^\w\s]", " ", disp_name.upper()).split())
                if disp_name.upper() in upper_text or clean_disp in clean_norm_text:
                    raw_scores[dt_id] += 40
                    matched_keywords_by_type[dt_id].append(disp_name.upper())

            rules_cfg = dt_data.get("rules_json")
            if isinstance(rules_cfg, str):
                try:
                    import json
                    rules_cfg = json.loads(rules_cfg)
                except Exception:
                    rules_cfg = {}
            if isinstance(rules_cfg, dict):
                kw_list = rules_cfg.get("keywords", [])
                for kw_item in kw_list:
                    kw_text = kw_item if isinstance(kw_item, str) else kw_item.get("keyword", "")
                    weight = kw_item.get("weight", 30) if isinstance(kw_item, dict) else 30
                    if kw_text:
                        clean_kw = " ".join(re.sub(r"[^\w\s]", " ", kw_text.upper()).split())
                        if kw_text.upper() in upper_text or clean_kw in clean_norm_text:
                            raw_scores[dt_id] += weight
                            matched_keywords_by_type[dt_id].append(kw_text)

        # 2. Match Regex Patterns (High-impact score booster: +50 points)
        for doc_type, patterns in cls.PATTERN_RULES.items():
            for pattern in patterns:
                matches = pattern.findall(text)
                if matches:
                    raw_scores[doc_type] += 50
                    sample_match = matches[0] if isinstance(matches[0], str) else str(matches[0])
                    matched_patterns_by_type[doc_type].append(sample_match)

        # 3. Direct Pattern Override: If explicit pattern matches and doc has supporting context
        for dt_key in ["pan", "aadhaar", "passport", "voter_id", "driving_licence", "salary_slip", "bank_statement", "commercial_invoice", "tax_form_16", "utility_bill"]:
            if matched_patterns_by_type.get(dt_key) and raw_scores.get(dt_key, 0) >= 50:
                raw_scores[dt_key] += 25

        # Find highest scoring type
        best_type = "unknown"
        best_score = 0.0

        for doc_type, score in raw_scores.items():
            if score > best_score:
                best_score = score
                best_type = doc_type

        # Lower threshold: 18 points is sufficient for sparse/concise synthetic documents
        if best_score < 18:
            best_type = "unknown"
            confidence = round(min(best_score / 60.0, 0.25), 2)
        else:
            # Map 18 to 100+ -> 0.50 to 0.99
            confidence = round(min(0.50 + (best_score / 120.0) * 0.49, 0.99), 2)

        meta = cls.TYPE_METADATA.get(best_type)
        if not meta and best_type in dynamic_types:
            dt_info = dynamic_types[best_type]
            meta = {
                "display_name": dt_info.get("display_name", str(best_type).replace("_", " ").title()),
                "category": dt_info.get("category", "custom")
            }
        elif not meta:
            meta = {
                "display_name": str(best_type).replace("_", " ").title(),
                "category": "general"
            }

        return {
            "classified_type": best_type,
            "confidence": confidence,
            "display_name": meta["display_name"],
            "category": meta["category"],
            "matched_keywords": matched_keywords_by_type.get(best_type, []),
            "matched_patterns": matched_patterns_by_type.get(best_type, []),
            "scores": {k: round(v, 1) for k, v in raw_scores.items()},
        }
