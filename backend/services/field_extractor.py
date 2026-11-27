import re
from datetime import datetime
from typing import Dict, Any, Optional, List


def mask_aadhaar(raw_number: str) -> str:
    """
    Strictly mask 12-digit Aadhaar numbers in accordance with UIDAI and privacy standards.
    Example: 1234 5678 9012 -> XXXX-XXXX-9012
    """
    clean = re.sub(r"\D", "", raw_number)
    if len(clean) >= 4:
        last4 = clean[-4:]
        return f"XXXX-XXXX-{last4}"
    return "XXXX-XXXX-XXXX"


def mask_id_number(id_val: str, visible_suffix_len: int = 4) -> str:
    """Mask general identity strings leaving only suffix visible."""
    if not id_val or len(id_val) <= visible_suffix_len:
        return id_val
    prefix_len = len(id_val) - visible_suffix_len
    return ("*" * prefix_len) + id_val[-visible_suffix_len:]


def parse_date(date_str: str) -> Optional[str]:
    """
    Normalize various date string formats (DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD)
    into standard ISO format (YYYY-MM-DD).
    """
    if not date_str:
        return None
    cleaned = date_str.strip().replace(".", "/").replace("-", "/")
    formats = [
        "%d/%m/%Y",
        "%d/%m/%y",
        "%Y/%m/%d",
        "%d %b %Y",
        "%d %B %Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(cleaned, fmt)
            # Ensure reasonable year (1900 to 2099)
            if 1900 <= dt.year <= 2099:
                return dt.strftime("%Y-%m-%d")
        except Exception:
            continue
    return None


class FieldExtractor:
    """
    Extracts structured KYC fields from document text based on classified document type.
    """

    # Common Regex Patterns
    DOB_PATTERN = re.compile(
        r"(?:DOB|Date of Birth|Birth Date|D\.O\.B\.?)[\s\:\-]+([0-3]?[0-9][\/\-\.][0-1]?[0-9][\/\-\.][1-2][0-9]{3})",
        re.IGNORECASE,
    )
    FALLBACK_DATE_PATTERN = re.compile(
        r"\b([0-3][0-9][\/\-\.][0-1][0-9][\/\-\.][1-2][0-9]{3})\b"
    )
    GENDER_PATTERN = re.compile(
        r"\b(FEMALE|MALE|TRANSGENDER)\b",
        re.IGNORECASE,
    )
    FATHER_PATTERN = re.compile(
        r"(?:Father\'?s?\s*Name|Father|S\/O|D\/O|W\/O)[\s\:\-]+([A-Za-z\s\.]{3,40})",
        re.IGNORECASE,
    )

    # Document-Specific Patterns
    PAN_REGEX = re.compile(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b")
    AADHAAR_REGEX = re.compile(r"\b(\d{4}\s\d{4}\s\d{4})\b")
    AADHAAR_NOSPACE_REGEX = re.compile(r"\b(\d{12})\b")
    PASSPORT_REGEX = re.compile(r"\b([A-Z][\s\-]?[0-9]{7})\b")
    VOTER_ID_REGEX = re.compile(r"\b([A-Z]{3}[\s\-]?[0-9]{7})\b")
    DL_REGEX = re.compile(r"\b([A-Z]{2}[-\s]?[0-9]{2}[-\s]?[0-9]{11})\b")

    @classmethod
    def extract_fields(
        cls,
        text: str,
        document_type: str = "unknown",
        learned_schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Extract structured fields tailored to the document type, augmented by versioned learned schemas.
        """
        if not text:
            return {}

        fields: Dict[str, Any] = {
            "name": None,
            "dob": None,
            "gender": None,
            "father_name": None,
            "id_number": None,
            "masked_id": None,
            "expiry_date": None,
            "extra_fields": {},
        }

        # 1. Extract Universal Fields (DOB, Gender, Father's Name)
        dob_match = cls.DOB_PATTERN.search(text)
        if dob_match:
            fields["dob"] = parse_date(dob_match.group(1))
        else:
            fallback_dates = cls.FALLBACK_DATE_PATTERN.findall(text)
            if fallback_dates:
                # First valid date is frequently DOB if document has no other dates
                for d in fallback_dates:
                    parsed = parse_date(d)
                    if parsed and int(parsed.split("-")[0]) < 2015:
                        fields["dob"] = parsed
                        break

        gender_match = cls.GENDER_PATTERN.search(text)
        if gender_match:
            fields["gender"] = gender_match.group(1).upper()
        else:
            # Check Sex: M / Sex: F pattern (standard on Passports & Voter IDs)
            sex_match = re.search(r"(?:Sex|Gender)[\s\:\-]+([A-Za-z]+)\b", text, re.IGNORECASE)
            if sex_match:
                g = sex_match.group(1).strip().upper()
                if g in ("F", "FEMALE"):
                    fields["gender"] = "FEMALE"
                elif g in ("M", "MALE"):
                    fields["gender"] = "MALE"

        father_match = cls.FATHER_PATTERN.search(text)
        if father_match:
            raw_f = father_match.group(1).split("\n")[0].strip()
            # Clean common label tails
            raw_f = re.split(r"(DOB|Date|Address|Permanent|Pin)", raw_f, flags=re.IGNORECASE)[0].strip()
            if len(raw_f) >= 3:
                fields["father_name"] = raw_f

        # 2. Document-Specific Extraction
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        if document_type == "pan":
            cls._extract_pan_fields(text, lines, fields)
        elif document_type == "aadhaar":
            cls._extract_aadhaar_fields(text, lines, fields)
        elif document_type == "passport":
            cls._extract_passport_fields(text, lines, fields)
        elif document_type == "voter_id":
            cls._extract_voter_fields(text, lines, fields)
        elif document_type == "driving_licence":
            cls._extract_dl_fields(text, lines, fields)
        elif document_type == "salary_slip":
            cls._extract_salary_fields(text, lines, fields)
        elif document_type == "bank_statement":
            cls._extract_bank_fields(text, lines, fields)
        elif document_type == "commercial_invoice":
            cls._extract_invoice_fields(text, lines, fields)
        elif document_type == "tax_form_16":
            cls._extract_tax16_fields(text, lines, fields)
        elif document_type == "utility_bill":
            cls._extract_utility_fields(text, lines, fields)
        else:
            # Try to auto-detect ID number if type is generic or unknown
            cls._extract_generic_id(text, fields)

        # 3. Fallback Name Detection if not found specifically
        if not fields.get("name"):
            fields["name"] = cls._detect_candidate_name(lines, fields.get("father_name"))

        # 4. Field Normalization & Sanitization
        cls._normalize_fields(fields, document_type)

        # 5. In-Context Learned Schema Matching (Anchors & Regex Patterns)
        if learned_schema:
            anchors = learned_schema.get("anchor_phrases", {})
            regexes = learned_schema.get("regex_patterns", {})
            attr_defs = learned_schema.get("attribute_definitions", [])

            extra_attrs = fields.get("extra_fields", {}).setdefault("attributes", [])
            existing_keys = {a.get("attribute_key") for a in extra_attrs if isinstance(a, dict)}

            for attr in attr_defs:
                key = attr.get("attribute_key")
                if not key or key in existing_keys:
                    continue
                val = None
                # Check regex
                rx_pat = regexes.get(key) or attr.get("regex_pattern")
                if rx_pat:
                    try:
                        m = re.search(rx_pat, text)
                        if m:
                            val = m.group(0).strip()
                    except Exception:
                        pass
                # Check anchor phrases
                if not val and key in anchors:
                    for anchor in anchors[key]:
                        pattern = re.escape(anchor) + r"\s*([^\n\r]+)"
                        try:
                            am = re.search(pattern, text, re.IGNORECASE)
                            if am:
                                val = am.group(1).strip()
                                break
                        except Exception:
                            pass
                if val:
                    extra_attrs.append({
                        "attribute_key": key,
                        "display_label": attr.get("display_label") or key.replace("_", " ").title(),
                        "attribute_value": val,
                        "data_type": attr.get("data_type", "string"),
                        "confidence": 0.95,
                        "source_type": "learned_schema"
                    })

        return fields

    @classmethod
    def _extract_pan_fields(cls, text: str, lines: List[str], fields: Dict[str, Any]) -> None:
        pan_match = cls.PAN_REGEX.search(text)
        if pan_match:
            pan_val = pan_match.group(1).upper()
            fields["id_number"] = pan_val
            fields["masked_id"] = pan_val  # Standard PAN is displayed or masked as ABCDE****F
            fields["extra_fields"]["pan_number"] = pan_val

        # PAN card structure typically has Name right after Income Tax Dept
        # or preceding Father's Name
        blacklist = {"INCOME", "TAX", "DEPARTMENT", "GOVT", "GOVERNMENT", "INDIA", "PERMANENT", "ACCOUNT", "NUMBER", "CARD", "FATHER", "FATHER'S", "SIGNATURE", "DATE", "OF", "BIRTH"}
        for i, line in enumerate(lines):
            upper = line.upper()
            if "INCOME TAX DEPARTMENT" in upper or "GOVT. OF INDIA" in upper:
                for j in range(i + 1, min(i + 5, len(lines))):
                    cand = lines[j].strip()
                    if re.match(r"^[A-Za-z\s\.]+$", cand) and len(cand) >= 3:
                        cand_words = set(cand.upper().replace(".", "").split())
                        if not cand_words.intersection(blacklist):
                            fields["name"] = cand
                            break
                if fields.get("name"):
                    break

    @classmethod
    def _extract_aadhaar_fields(cls, text: str, lines: List[str], fields: Dict[str, Any]) -> None:
        aadhaar_match = cls.AADHAAR_REGEX.search(text)
        if not aadhaar_match:
            aadhaar_match = cls.AADHAAR_NOSPACE_REGEX.search(text)

        if aadhaar_match:
            raw_aadhaar = aadhaar_match.group(1).replace(" ", "")
            masked = mask_aadhaar(raw_aadhaar)
            fields["id_number"] = masked  # Never store or expose unmasked Aadhaar in output!
            fields["masked_id"] = masked
            fields["extra_fields"]["aadhaar_masked"] = masked

        # Search for Name: explicit pattern or line above DOB
        name_match = re.search(r"(?:To|Name|Resident\'?s?\s*Name)[\s\:\-]+([A-Za-z\s\.]{3,40})", text, re.IGNORECASE)
        if name_match:
            cand = name_match.group(1).split("\n")[0].strip()
            if not any(k in cand.upper() for k in ["GOVERNMENT", "INDIA", "UIDAI", "AUTHORITY", "UNIQUE"]):
                fields["name"] = cand

        if not fields.get("name"):
            for i, line in enumerate(lines):
                if "DOB" in line.upper() or "DATE OF BIRTH" in line.upper() or "YEAR OF BIRTH" in line.upper():
                    if i > 0:
                        cand = lines[i - 1].strip()
                        # Strip Name: prefix if present
                        cand = re.sub(r"^(?:Name|To|Resident)[\s\:\-]+", "", cand, flags=re.IGNORECASE).strip()
                        if re.match(r"^[A-Za-z\s\.]+$", cand) and len(cand) >= 3:
                            if not any(k in cand.upper() for k in ["GOVERNMENT", "INDIA", "UIDAI", "AUTHORITY"]):
                                fields["name"] = cand
                                break

    @classmethod
    def _extract_passport_fields(cls, text: str, lines: List[str], fields: Dict[str, Any]) -> None:
        match = cls.PASSPORT_REGEX.search(text)
        if match:
            pass_num = match.group(1).upper().replace(" ", "").replace("-", "")
            fields["id_number"] = pass_num
            fields["masked_id"] = mask_id_number(pass_num, 3)
            fields["extra_fields"]["passport_number"] = pass_num

        # Name extraction for Passport (Given Name + Surname or Name)
        given_match = re.search(r"(?:Given Name|First Name)[\s\:\-]+([A-Za-z\s\.]{2,40})", text, re.IGNORECASE)
        surname_match = re.search(r"(?:Surname|Last Name)[\s\:\-]+([A-Za-z\s\.]{2,40})", text, re.IGNORECASE)
        if given_match and surname_match:
            g = given_match.group(1).split("\n")[0].strip()
            s = surname_match.group(1).split("\n")[0].strip()
            fields["name"] = f"{g} {s}".strip()
            fields["extra_fields"]["given_name"] = g
            fields["extra_fields"]["surname"] = s
        elif given_match:
            fields["name"] = given_match.group(1).split("\n")[0].strip()
            fields["extra_fields"]["given_name"] = fields["name"]
        else:
            name_match = re.search(r"(?:Name)[\s\:\-]+([A-Za-z\s\.]{3,40})", text, re.IGNORECASE)
            if name_match:
                cand = name_match.group(1).split("\n")[0].strip()
                if not any(k in cand.upper() for k in ["PASSPORT", "REPUBLIC", "INDIA", "TYPE"]):
                    fields["name"] = cand

        # Expiry date pattern
        expiry_match = re.search(r"(?:Expiry|Date of Expiry|Valid Until)[\s\:\-]+([0-3]?[0-9][\/\-\.][0-1]?[0-9][\/\-\.][1-2][0-9]{3})", text, re.IGNORECASE)
        if expiry_match:
            fields["expiry_date"] = parse_date(expiry_match.group(1))

        # Date of Issue pattern
        issue_match = re.search(r"(?:Date of Issue|Issue Date|Date d\'emission)[\s\:\-]+([0-3]?[0-9][\/\-\.][0-1]?[0-9][\/\-\.][1-2][0-9]{3})", text, re.IGNORECASE)
        if issue_match:
            fields["extra_fields"]["date_of_issue"] = parse_date(issue_match.group(1))

        # Place of Issue / Place of Birth
        pob_match = re.search(r"(?:Place of Birth|Place of Issue)[\s\:\-]+([A-Za-z\s\.]{3,30})", text, re.IGNORECASE)
        if pob_match:
            fields["extra_fields"]["place_of_birth"] = pob_match.group(1).split("\n")[0].strip()

        # Nationality
        if "IND" in text or "INDIAN" in text.upper():
            fields["extra_fields"]["nationality"] = "INDIAN"

        # MRZ Check (ICAO Doc 9303 Type 3)
        mrz_matches = re.findall(r"P<[A-Z0-9<]{40,}", text)
        if mrz_matches:
            fields["extra_fields"]["mrz_detected"] = True
            fields["extra_fields"]["mrz_header"] = mrz_matches[0][:10]

    @classmethod
    def _extract_voter_fields(cls, text: str, lines: List[str], fields: Dict[str, Any]) -> None:
        match = cls.VOTER_ID_REGEX.search(text)
        if match:
            epic_num = match.group(1).upper().replace(" ", "").replace("-", "")
            fields["id_number"] = epic_num
            fields["masked_id"] = mask_id_number(epic_num, 4)
            fields["extra_fields"]["epic_number"] = epic_num

        # Elector's name
        name_match = re.search(r"(?:Elector\'?s?\s*Name|Elector\s*Name|Name)[\s\:\-]+([A-Za-z\s\.]{3,40})", text, re.IGNORECASE)
        if name_match:
            cand = name_match.group(1).split("\n")[0].strip()
            if not any(k in cand.upper() for k in ["ELECTION", "COMMISSION", "INDIA", "PHOTO"]):
                fields["name"] = cand

        # Father's or Husband's Name
        rel_match = re.search(r"(?:Father\'?s?\s*Name|Husband\'?s?\s*Name|Relation\'?s?\s*Name)[\s\:\-]+([A-Za-z\s\.]{3,40})", text, re.IGNORECASE)
        if rel_match:
            rname = rel_match.group(1).split("\n")[0].strip()
            if not any(k in rname.upper() for k in ["ELECTION", "COMMISSION", "INDIA"]):
                fields["father_name"] = rname
                fields["extra_fields"]["relation_name"] = rname

        # Age or DOB fallback
        if not fields.get("dob"):
            age_match = re.search(r"(?:Age|Age as on[\s\w\.]*)[\s\:\-]+([0-9]{2})\b", text, re.IGNORECASE)
            if age_match:
                age_val = int(age_match.group(1))
                fields["extra_fields"]["age"] = age_val
                est_year = datetime.now().year - age_val
                fields["dob"] = f"{est_year}-01-01"
                fields["extra_fields"]["dob_estimated"] = True

        # Assembly Constituency
        ac_match = re.search(r"(?:Assembly Constituency|Constituency|AC)[\s\:\-]+([A-Za-z0-9\s\.\-]+)", text, re.IGNORECASE)
        if ac_match:
            fields["extra_fields"]["assembly_constituency"] = ac_match.group(1).split("\n")[0].strip()

        # Permanent lifetime validity
        fields["extra_fields"]["validity"] = "PERMANENT"

    @classmethod
    def _normalize_fields(cls, fields: Dict[str, Any], document_type: str) -> None:
        """
        Normalize and sanitize extracted field values:
        - Trim whitespace and remove redundant colons/labels.
        - Normalize names (strip common salutations like Shri, Smt, etc.).
        - Normalize ID numbers according to official specifications.
        - Normalize Gender (M -> MALE, F -> FEMALE).
        """
        # Normalize Name
        if fields.get("name"):
            name = str(fields["name"]).strip()
            name = re.sub(r"^(?:Name|Given Name|Elector Name|Holder Name|To)[\s\:\-]+", "", name, flags=re.IGNORECASE).strip()
            name = re.sub(r"^(?:Shri|Smt|Mr|Mrs|Ms|Dr|Kumari)\.?\s+", "", name, flags=re.IGNORECASE).strip()
            name = re.sub(r"\s+", " ", name)
            fields["name"] = name if len(name) >= 2 else None

        # Normalize Father's / Guardian Name
        if fields.get("father_name"):
            fname = str(fields["father_name"]).strip()
            fname = re.sub(r"^(?:Father|Father\'?s?\s*Name|S\/O|D\/O|W\/O|Husband\'?s?\s*Name)[\s\:\-]+", "", fname, flags=re.IGNORECASE).strip()
            fname = re.sub(r"^(?:Shri|Mr|Late)\.?\s+", "", fname, flags=re.IGNORECASE).strip()
            fname = re.sub(r"\s+", " ", fname)
            fields["father_name"] = fname if len(fname) >= 2 else None

        # Normalize Gender
        if fields.get("gender"):
            g = str(fields["gender"]).strip().upper()
            if g in ("M", "MALE"):
                fields["gender"] = "MALE"
            elif g in ("F", "FEMALE"):
                fields["gender"] = "FEMALE"
            elif "TRANS" in g:
                fields["gender"] = "TRANSGENDER"

        # Document-specific ID normalization
        if document_type == "passport" and fields.get("id_number"):
            clean_pass = re.sub(r"[^A-Za-z0-9]", "", str(fields["id_number"])).upper()
            fields["id_number"] = clean_pass
            fields["masked_id"] = mask_id_number(clean_pass, 3)
            fields["extra_fields"]["passport_number"] = clean_pass

        elif document_type == "voter_id" and fields.get("id_number"):
            clean_epic = re.sub(r"[^A-Za-z0-9]", "", str(fields["id_number"])).upper()
            fields["id_number"] = clean_epic
            fields["masked_id"] = mask_id_number(clean_epic, 4)
            fields["extra_fields"]["epic_number"] = clean_epic

    @classmethod
    def _extract_dl_fields(cls, text: str, lines: List[str], fields: Dict[str, Any]) -> None:
        match = cls.DL_REGEX.search(text)
        if match:
            dl_num = match.group(1).upper().replace(" ", "-")
            fields["id_number"] = dl_num
            fields["masked_id"] = mask_id_number(dl_num, 4)
            fields["extra_fields"]["dl_number"] = dl_num

        # Name
        name_match = re.search(r"(?:Name|Holder\'?s?\s*Name)[\s\:\-]+([A-Za-z\s\.]{3,40})", text, re.IGNORECASE)
        if name_match:
            cand = name_match.group(1).split("\n")[0].strip()
            if not any(k in cand.upper() for k in ["UNION", "INDIA", "STATE", "TRANSPORT", "LICENCE"]):
                fields["name"] = cand

        # Validity / Expiry
        val_match = re.search(r"(?:Valid Till|Validity|Expires|NT)[\s\:\-]+([0-3]?[0-9][\/\-\.][0-1]?[0-9][\/\-\.][1-2][0-9]{3})", text, re.IGNORECASE)
        if val_match:
            fields["expiry_date"] = parse_date(val_match.group(1))

    @classmethod
    def _extract_salary_fields(cls, text: str, lines: List[str], fields: Dict[str, Any]) -> None:
        """Extract fields specific to Salary Slips / Payslips."""
        # Employee Name
        name_m = re.search(r"(?:Employee\s*Name|Emp\s*Name|Name)[\s\:\-]+([A-Za-z\s\.]{3,40})", text, re.IGNORECASE)
        if name_m:
            fields["name"] = name_m.group(1).split("\n")[0].strip()

        # Employee ID
        id_m = re.search(r"EMP(?:LOYEE)?\s*ID[\s\:\-]*([A-Z0-9\-]+)", text, re.IGNORECASE)
        if id_m:
            fields["id_number"] = id_m.group(1).strip()
            fields["masked_id"] = mask_id_number(fields["id_number"], 4)
            fields["extra_fields"]["employee_id"] = fields["id_number"]

        # Net Salary
        net_m = re.search(r"NET\s*(?:PAY|SALARY)[\s\:\-]*(?:RS\.?|INR)?\s*([\d,]+(?:\.\d{2})?)", text, re.IGNORECASE)
        if net_m:
            fields["extra_fields"]["net_salary"] = net_m.group(1).replace(",", "").strip()

        # Gross Salary
        gross_m = re.search(r"GROSS\s*(?:PAY|SALARY|EARNINGS)?[\s\:\-]*(?:RS\.?|INR)?\s*([\d,]+(?:\.\d{2})?)", text, re.IGNORECASE)
        if gross_m:
            fields["extra_fields"]["gross_salary"] = gross_m.group(1).replace(",", "").strip()

        # Basic Pay
        basic_m = re.search(r"BASIC\s*(?:PAY|SALARY)?[\s\:\-]*(?:RS\.?|INR)?\s*([\d,]+(?:\.\d{2})?)", text, re.IGNORECASE)
        if basic_m:
            fields["extra_fields"]["basic_salary"] = basic_m.group(1).replace(",", "").strip()

        # HRA
        hra_m = re.search(r"(?:HRA|HOUSE\s*RENT\s*ALLOWANCE)[\s\:\-]*(?:RS\.?|INR)?\s*([\d,]+(?:\.\d{2})?)", text, re.IGNORECASE)
        if hra_m:
            fields["extra_fields"]["hra"] = hra_m.group(1).replace(",", "").strip()

        # Total Deductions
        ded_m = re.search(r"(?:TOTAL\s*)?DEDUCTIONS[\s\:\-]*(?:RS\.?|INR)?\s*([\d,]+(?:\.\d{2})?)", text, re.IGNORECASE)
        if ded_m:
            fields["extra_fields"]["deductions"] = ded_m.group(1).replace(",", "").strip()

        # Pay Period
        period_m = re.search(r"(?:PAY\s*PERIOD|MONTH|PAYSLIP\s*FOR)[\s\:\-]*([A-Za-z]+\s*\d{4})", text, re.IGNORECASE)
        if period_m:
            fields["extra_fields"]["pay_period"] = period_m.group(1).strip()

    @classmethod
    def _extract_bank_fields(cls, text: str, lines: List[str], fields: Dict[str, Any]) -> None:
        """Extract fields specific to Bank Statements."""
        # Account Holder Name
        name_m = re.search(r"(?:Account\s*Holder|Customer\s*Name|Name)[\s\:\-]+([A-Za-z\s\.]{3,40})", text, re.IGNORECASE)
        if name_m:
            fields["name"] = name_m.group(1).split("\n")[0].strip()

        # Account Number
        acc_m = re.search(r"ACCOUNT\s*(?:NO|NUMBER)?[\s\:\-]*(\d{9,18})", text, re.IGNORECASE)
        if acc_m:
            fields["id_number"] = acc_m.group(1).strip()
            fields["masked_id"] = mask_id_number(fields["id_number"], 4)
            fields["extra_fields"]["account_number"] = fields["id_number"]

        # IFSC Code
        ifsc_m = re.search(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", text)
        if ifsc_m:
            fields["extra_fields"]["ifsc_code"] = ifsc_m.group(1).strip()

        # Closing Balance
        bal_m = re.search(r"(?:CLOSING\s*BALANCE|AVAILABLE\s*BALANCE|BALANCE)[\s\:\-]*(?:RS\.?|INR)?\s*([\d,]+(?:\.\d{2})?)", text, re.IGNORECASE)
        if bal_m:
            fields["extra_fields"]["closing_balance"] = bal_m.group(1).replace(",", "").strip()

    @classmethod
    def _extract_invoice_fields(cls, text: str, lines: List[str], fields: Dict[str, Any]) -> None:
        """Extract fields specific to Commercial Invoices."""
        # Invoice Number
        inv_m = re.search(r"INV(?:OICE)?\s*(?:NO|NUMBER)?[\s\:\-#]*([A-Z0-9\-\/]+)", text, re.IGNORECASE)
        if inv_m:
            fields["id_number"] = inv_m.group(1).strip()
            fields["masked_id"] = fields["id_number"]
            fields["extra_fields"]["invoice_number"] = fields["id_number"]

        # Bill To Name
        bill_m = re.search(r"(?:BILL\s*TO|CUSTOMER|BUYER|CLIENT)[\s\:\-]+([A-Za-z\s\.]{3,40})", text, re.IGNORECASE)
        if bill_m:
            fields["name"] = bill_m.group(1).split("\n")[0].strip()

        # GSTIN
        gstin_m = re.search(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1})\b", text)
        if gstin_m:
            fields["extra_fields"]["gstin"] = gstin_m.group(1).strip()

        # Total Amount
        tot_m = re.search(r"(?:TOTAL\s*AMOUNT|GRAND\s*TOTAL|TOTAL)[\s\:\-]*(?:RS\.?|INR|\$)?\s*([\d,]+(?:\.\d{2})?)", text, re.IGNORECASE)
        if tot_m:
            fields["extra_fields"]["total_amount"] = tot_m.group(1).replace(",", "").strip()

        # Due Date
        due_m = re.search(r"DUE\s*DATE[\s\:\-]*([0-3]?[0-9][\/\-\.][0-1]?[0-9][\/\-\.][1-2][0-9]{3})", text, re.IGNORECASE)
        if due_m:
            fields["expiry_date"] = parse_date(due_m.group(1))

    @classmethod
    def _extract_tax16_fields(cls, text: str, lines: List[str], fields: Dict[str, Any]) -> None:
        """Extract fields specific to Tax Form 16."""
        # Employee Name
        name_m = re.search(r"(?:Name\s*of\s*Employee|Employee\s*Name)[\s\:\-]+([A-Za-z\s\.]{3,40})", text, re.IGNORECASE)
        if name_m:
            fields["name"] = name_m.group(1).split("\n")[0].strip()

        # PAN of Employee
        pan_m = re.search(r"PAN\s*(?:of\s*Employee)?[\s\:\-]*([A-Z]{5}[0-9]{4}[A-Z])", text, re.IGNORECASE)
        if pan_m:
            fields["id_number"] = pan_m.group(1).strip().upper()
            fields["masked_id"] = mask_id_number(fields["id_number"], 4)
            fields["extra_fields"]["pan"] = fields["id_number"]

        # TAN of Deductor
        tan_m = re.search(r"TAN\s*(?:of\s*Deductor)?[\s\:\-]*([A-Z]{4}\d{5}[A-Z])", text, re.IGNORECASE)
        if tan_m:
            fields["extra_fields"]["tan"] = tan_m.group(1).strip().upper()

        # Assessment Year
        ay_m = re.search(r"ASSESSMENT\s*YEAR[\s\:\-]*(\d{4}[-\s]?\d{2,4})", text, re.IGNORECASE)
        if ay_m:
            fields["extra_fields"]["assessment_year"] = ay_m.group(1).strip()

        # Tax Deducted
        tax_m = re.search(r"(?:TOTAL\s*TAX\s*DEDUCTED|TAX\s*DEDUCTED)[\s\:\-]*(?:RS\.?|INR)?\s*([\d,]+(?:\.\d{2})?)", text, re.IGNORECASE)
        if tax_m:
            fields["extra_fields"]["tax_deducted"] = tax_m.group(1).replace(",", "").strip()

    @classmethod
    def _extract_utility_fields(cls, text: str, lines: List[str], fields: Dict[str, Any]) -> None:
        """Extract fields specific to Utility Bills."""
        # Consumer Name
        name_m = re.search(r"(?:Consumer\s*Name|Customer\s*Name|Name)[\s\:\-]+([A-Za-z\s\.]{3,40})", text, re.IGNORECASE)
        if name_m:
            fields["name"] = name_m.group(1).split("\n")[0].strip()

        # Consumer Number
        c_m = re.search(r"CONSUMER\s*(?:NO|NUMBER|ID)[\s\:\-]*([A-Z0-9\-]+)", text, re.IGNORECASE)
        if c_m:
            fields["id_number"] = c_m.group(1).strip()
            fields["masked_id"] = mask_id_number(fields["id_number"], 4)
            fields["extra_fields"]["consumer_number"] = fields["id_number"]

        # Meter Number
        m_m = re.search(r"METER\s*(?:NO|NUMBER)[\s\:\-]*([A-Z0-9\-]+)", text, re.IGNORECASE)
        if m_m:
            fields["extra_fields"]["meter_number"] = m_m.group(1).strip()

        # Bill Amount
        amt_m = re.search(r"(?:BILL\s*AMOUNT|AMOUNT\s*PAYABLE|TOTAL\s*AMOUNT)[\s\:\-]*(?:RS\.?|INR)?\s*([\d,]+(?:\.\d{2})?)", text, re.IGNORECASE)
        if amt_m:
            fields["extra_fields"]["bill_amount"] = amt_m.group(1).replace(",", "").strip()

        # Units Consumed
        unit_m = re.search(r"UNITS\s*(?:CONSUMED)?[\s\:\-]*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
        if unit_m:
            fields["extra_fields"]["units_consumed"] = unit_m.group(1).strip()

        # Due Date
        due_m = re.search(r"DUE\s*DATE[\s\:\-]*([0-3]?[0-9][\/\-\.][0-1]?[0-9][\/\-\.][1-2][0-9]{3})", text, re.IGNORECASE)
        if due_m:
            fields["expiry_date"] = parse_date(due_m.group(1))

    @classmethod
    def _extract_generic_id(cls, text: str, fields: Dict[str, Any]) -> None:
        for reg in [cls.PAN_REGEX, cls.AADHAAR_REGEX, cls.PASSPORT_REGEX, cls.VOTER_ID_REGEX, cls.DL_REGEX]:
            m = reg.search(text)
            if m:
                val = m.group(1).strip()
                if len(val.replace(" ", "")) == 12 and val.replace(" ", "").isdigit():
                    fields["id_number"] = mask_aadhaar(val)
                    fields["masked_id"] = fields["id_number"]
                else:
                    fields["id_number"] = val
                    fields["masked_id"] = mask_id_number(val, 4)
                break

    @classmethod
    def _detect_candidate_name(cls, lines: List[str], father_name: Optional[str] = None) -> Optional[str]:
        """Heuristic fallback to locate applicant name from text lines."""
        blacklist = {
            "GOVERNMENT", "INDIA", "INCOME", "TAX", "DEPARTMENT", "PERMANENT",
            "ACCOUNT", "NUMBER", "CARD", "AADHAAR", "UIDAI", "AUTHORITY",
            "MALE", "FEMALE", "SIGNATURE", "PASSPORT", "ELECTION", "COMMISSION",
            "EPIC", "DRIVING", "LICENCE", "UNION", "MOTOR", "VEHICLE", "TRANSPORT"
        }
        for line in lines:
            words = line.strip().split()
            if 2 <= len(words) <= 4:
                if re.match(r"^[A-Za-z\s\.]+$", line):
                    upper_words = [w.upper() for w in words]
                    if not any(w in blacklist for w in upper_words):
                        cand = line.strip()
                        if father_name and cand.upper() == father_name.upper():
                            continue
                        return cand
        return None
