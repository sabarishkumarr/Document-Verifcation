import re
from datetime import datetime, date
from typing import Dict, Any, List, Optional


class DocumentValidator:
    """
    Validates extracted KYC fields against official format definitions,
    mandatory presence requirements, and expiry thresholds.
    
    Note: Validates document data structure and formatting.
    Does NOT query or claim access to government databases.
    """

    STATE_CODES = {
        "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN", "GA", "GJ", "HR",
        "HP", "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML", "MN", "MP", "MZ",
        "NL", "OD", "PB", "PY", "RJ", "SK", "TN", "TR", "TS", "UK", "UP", "WB"
    }

    @classmethod
    def validate(
        cls,
        document_type: str,
        extracted_fields: Dict[str, Any],
        raw_text: str = ""
    ) -> Dict[str, Any]:
        """
        Run validation checks on extracted fields.
        
        Returns:
            {
                "is_valid": bool,
                "overall_status": "valid" | "warning" | "invalid",
                "checks": List[Dict[str, Any]],
                "flags": List[str],
                "confidence_score": float
            }
        """
        checks: List[Dict[str, Any]] = []
        flags: List[str] = []

        is_kyc = document_type in ("pan", "aadhaar", "passport", "voter_id", "driving_licence")

        if is_kyc:
            # 1. Mandatory Fields Check for KYC identity documents
            name = extracted_fields.get("name")
            if name and len(name.strip()) >= 3:
                checks.append({
                    "field": "name",
                    "status": "pass",
                    "message": f"Mandatory field 'name' found: '{name}'"
                })
            else:
                checks.append({
                    "field": "name",
                    "status": "fail",
                    "message": "Applicant name could not be identified or is incomplete"
                })
                flags.append("Missing applicant name")

            dob = extracted_fields.get("dob")
            if dob:
                # Validate age
                age_check = cls._validate_dob(dob)
                checks.append(age_check)
                if age_check["status"] == "fail":
                    flags.append(age_check["message"])
            else:
                checks.append({
                    "field": "dob",
                    "status": "warning",
                    "message": "Date of Birth not clearly identified on document"
                })
                flags.append("Missing Date of Birth")

            # 2. Document-Specific Format Validations for KYC
            id_number = extracted_fields.get("id_number")
        if document_type == "pan":
            pan_check = cls._validate_pan(id_number, extracted_fields)
            checks.append(pan_check)
            if pan_check["status"] == "fail":
                flags.append(pan_check["message"])

        elif document_type == "aadhaar":
            aadhaar_check = cls._validate_aadhaar(id_number, extracted_fields)
            checks.append(aadhaar_check)
            if aadhaar_check["status"] == "fail":
                flags.append(aadhaar_check["message"])

        elif document_type == "passport":
            pass_check = cls._validate_passport(id_number, extracted_fields)
            checks.append(pass_check)
            if pass_check["status"] == "fail":
                flags.append(pass_check["message"])

            # Issue Date vs Expiry Date validation
            issue_date = extracted_fields.get("extra_fields", {}).get("date_of_issue")
            expiry_date = extracted_fields.get("expiry_date")
            if issue_date and expiry_date:
                if issue_date >= expiry_date:
                    checks.append({
                        "field": "passport_dates",
                        "status": "fail",
                        "message": f"Invalid passport timeline: Issue date ({issue_date}) is not earlier than expiry date ({expiry_date})"
                    })
                    flags.append("Invalid passport issue/expiry timeline")
                else:
                    checks.append({
                        "field": "passport_dates",
                        "status": "pass",
                        "message": f"Valid passport issue-to-expiry window ({issue_date} to {expiry_date})"
                    })
            
            # Expiry check
            exp_check = cls._validate_expiry(extracted_fields.get("expiry_date"), "Passport")
            checks.append(exp_check)
            if exp_check["status"] == "fail":
                flags.append(exp_check["message"])

        elif document_type == "voter_id":
            voter_check = cls._validate_voter_id(id_number, extracted_fields)
            checks.append(voter_check)
            if voter_check["status"] == "fail":
                flags.append(voter_check["message"])

            # Voter ID has lifetime validity in India
            checks.append({
                "field": "expiry_date",
                "status": "pass",
                "message": "Voter ID provides permanent lifetime validity (no renewal required)"
            })

            # Check for parent / spouse relation
            rel = extracted_fields.get("father_name") or extracted_fields.get("extra_fields", {}).get("relation_name")
            if rel and len(rel.strip()) >= 3:
                checks.append({
                    "field": "relation_name",
                    "status": "pass",
                    "message": f"Parent / Spouse relation identified: '{rel}'"
                })

        elif document_type == "driving_licence":
            dl_check = cls._validate_dl(id_number, extracted_fields)
            checks.append(dl_check)
            if dl_check["status"] == "fail":
                flags.append(dl_check["message"])

            # Expiry check
            exp_check = cls._validate_expiry(extracted_fields.get("expiry_date"), "Driving Licence")
            checks.append(exp_check)
            if exp_check["status"] == "fail":
                flags.append(exp_check["message"])

        elif document_type == "salary_slip":
            # Salary Slip Validations
            name = extracted_fields.get("name") or extracted_fields.get("applicant_name")
            if name:
                checks.append({"field": "employee_name", "status": "pass", "message": f"Employee name identified: '{name}'"})
            else:
                checks.append({"field": "employee_name", "status": "warning", "message": "Employee name not clearly identified"})

            extra = extracted_fields.get("extra_fields", {})
            net = extra.get("net_salary")
            if net:
                try:
                    net_float = float(str(net).replace(",", ""))
                    if net_float > 0:
                        checks.append({"field": "net_salary", "status": "pass", "message": f"Valid net salary amount: {net}"})
                    else:
                        checks.append({"field": "net_salary", "status": "fail", "message": f"Invalid net salary: {net}"})
                        flags.append("Invalid net salary amount")
                except ValueError:
                    checks.append({"field": "net_salary", "status": "warning", "message": f"Net salary format ambiguous: {net}"})
            else:
                checks.append({"field": "net_salary", "status": "warning", "message": "Net salary amount not identified"})

        elif document_type == "bank_statement":
            # Bank Statement Validations
            id_num = extracted_fields.get("id_number") or extracted_fields.get("extra_fields", {}).get("account_number")
            if id_num and len(re.sub(r"\D", "", str(id_num))) >= 9:
                checks.append({"field": "account_number", "status": "pass", "message": f"Bank account number identified: {id_num}"})
            else:
                checks.append({"field": "account_number", "status": "warning", "message": "Bank account number missing or incomplete"})

            ifsc = extracted_fields.get("extra_fields", {}).get("ifsc_code")
            if ifsc:
                if re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", str(ifsc).strip().upper()):
                    checks.append({"field": "ifsc_code", "status": "pass", "message": f"Valid 11-character IFSC code: {ifsc}"})
                else:
                    checks.append({"field": "ifsc_code", "status": "fail", "message": f"Invalid IFSC code format: {ifsc}"})
                    flags.append("Invalid IFSC code format")

        elif document_type == "commercial_invoice":
            # Commercial Invoice Validations
            inv_no = extracted_fields.get("id_number") or extracted_fields.get("extra_fields", {}).get("invoice_number")
            if inv_no:
                checks.append({"field": "invoice_number", "status": "pass", "message": f"Invoice number identified: {inv_no}"})
            else:
                checks.append({"field": "invoice_number", "status": "warning", "message": "Invoice number not identified"})

            tot = extracted_fields.get("extra_fields", {}).get("total_amount")
            if tot:
                try:
                    tot_float = float(str(tot).replace(",", ""))
                    checks.append({"field": "total_amount", "status": "pass", "message": f"Total amount identified: {tot}"})
                except ValueError:
                    checks.append({"field": "total_amount", "status": "warning", "message": f"Total amount format ambiguous: {tot}"})

        elif document_type == "tax_form_16":
            # Form 16 Validations
            pan_val = extracted_fields.get("id_number") or extracted_fields.get("extra_fields", {}).get("pan")
            if pan_val and re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", str(pan_val).strip().upper()):
                checks.append({"field": "pan", "status": "pass", "message": f"Valid employee PAN identified: {pan_val}"})
            else:
                checks.append({"field": "pan", "status": "warning", "message": "Employee PAN missing or invalid in Form 16"})

        elif document_type == "utility_bill":
            # Utility Bill Validations
            c_no = extracted_fields.get("id_number") or extracted_fields.get("extra_fields", {}).get("consumer_number")
            if c_no:
                checks.append({"field": "consumer_number", "status": "pass", "message": f"Consumer identifier found: {c_no}"})
            else:
                checks.append({"field": "consumer_number", "status": "warning", "message": "Consumer / Meter number not identified"})

        else:
            checks.append({
                "field": "document_type",
                "status": "warning",
                "message": f"Document classified as '{document_type}'; generic validation applied"
            })
            flags.append(f"Document type '{document_type}' uses generic schema")

        # Compute overall status
        has_fail = any(c["status"] == "fail" for c in checks)
        has_warning = any(c["status"] == "warning" for c in checks)

        if has_fail:
            overall_status = "invalid"
            is_valid = False
        elif has_warning:
            overall_status = "warning"
            is_valid = True
        else:
            overall_status = "valid"
            is_valid = True

        passed_count = sum(1 for c in checks if c["status"] == "pass")
        score = round(passed_count / max(len(checks), 1), 2)

        return {
            "is_valid": is_valid,
            "overall_status": overall_status,
            "checks": checks,
            "flags": flags,
            "validation_score": score
        }

    @classmethod
    def _validate_pan(cls, pan: Optional[str], fields: Dict[str, Any]) -> Dict[str, Any]:
        if not pan:
            return {
                "field": "pan_number",
                "status": "fail",
                "message": "PAN number missing from document"
            }
        pan_clean = pan.strip().upper()
        if re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", pan_clean):
            # Check 4th character: 'P' = Individual (standard for housing loan applicant)
            entity_type = "Individual" if pan_clean[3] == "P" else f"Entity type '{pan_clean[3]}'"
            return {
                "field": "pan_number",
                "status": "pass",
                "message": f"Valid 10-character PAN format ({entity_type})"
            }
        return {
            "field": "pan_number",
            "status": "fail",
            "message": f"Invalid PAN format '{pan_clean}'. Must be 5 letters, 4 digits, 1 letter."
        }

    @classmethod
    def _validate_aadhaar(cls, aadhaar_masked: Optional[str], fields: Dict[str, Any]) -> Dict[str, Any]:
        if not aadhaar_masked:
            return {
                "field": "aadhaar_number",
                "status": "fail",
                "message": "Aadhaar number missing from document"
            }
        # Masked should match format XXXX-XXXX-1234
        if re.match(r"^XXXX-XXXX-\d{4}$", aadhaar_masked):
            return {
                "field": "aadhaar_number",
                "status": "pass",
                "message": f"Valid masked 12-digit Aadhaar pattern ({aadhaar_masked})"
            }
        return {
            "field": "aadhaar_number",
            "status": "warning",
            "message": f"Aadhaar identification format incomplete: '{aadhaar_masked}'"
        }

    @classmethod
    def _validate_passport(cls, pass_num: Optional[str], fields: Dict[str, Any]) -> Dict[str, Any]:
        if not pass_num:
            return {
                "field": "passport_number",
                "status": "fail",
                "message": "Passport number missing from document"
            }
        if re.match(r"^[A-Z][0-9]{7}$", pass_num.strip().upper()):
            return {
                "field": "passport_number",
                "status": "pass",
                "message": f"Valid Republic of India Passport number format ({pass_num})"
            }
        return {
            "field": "passport_number",
            "status": "fail",
            "message": f"Invalid Passport format '{pass_num}'. Must be 1 letter followed by 7 digits."
        }

    @classmethod
    def _validate_voter_id(cls, epic_num: Optional[str], fields: Dict[str, Any]) -> Dict[str, Any]:
        if not epic_num:
            return {
                "field": "epic_number",
                "status": "fail",
                "message": "Voter ID (EPIC) number missing from document"
            }
        if re.match(r"^[A-Z]{3}[0-9]{7}$", epic_num.strip().upper()) or re.match(r"^[A-Z]{2}[0-9]{8}$", epic_num.strip().upper()):
            return {
                "field": "epic_number",
                "status": "pass",
                "message": f"Valid Election Commission EPIC number format ({epic_num})"
            }
        return {
            "field": "epic_number",
            "status": "warning",
            "message": f"Non-standard Voter ID pattern: '{epic_num}'"
        }

    @classmethod
    def _validate_dl(cls, dl_num: Optional[str], fields: Dict[str, Any]) -> Dict[str, Any]:
        if not dl_num:
            return {
                "field": "dl_number",
                "status": "fail",
                "message": "Driving Licence number missing from document"
            }
        clean = dl_num.replace("-", "").replace(" ", "").upper()
        state = clean[:2]
        if state in cls.STATE_CODES and len(clean) >= 13:
            return {
                "field": "dl_number",
                "status": "pass",
                "message": f"Valid Driving Licence format with recognized state code '{state}'"
            }
        return {
            "field": "dl_number",
            "status": "warning",
            "message": f"Driving Licence pattern may require verification: '{dl_num}'"
        }

    @classmethod
    def _validate_expiry(cls, expiry_date_str: Optional[str], doc_name: str) -> Dict[str, Any]:
        if not expiry_date_str:
            return {
                "field": "expiry_date",
                "status": "warning",
                "message": f"{doc_name} validity expiry date not detected"
            }
        try:
            exp_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
            today = date.today()
            if exp_date < today:
                return {
                    "field": "expiry_date",
                    "status": "fail",
                    "message": f"{doc_name} expired on {expiry_date_str} (Past validity date)"
                }
            return {
                "field": "expiry_date",
                "status": "pass",
                "message": f"{doc_name} is currently valid (Expires on {expiry_date_str})"
            }
        except Exception:
            return {
                "field": "expiry_date",
                "status": "warning",
                "message": f"Could not parse expiry date '{expiry_date_str}'"
            }

    @classmethod
    def _validate_dob(cls, dob_str: str) -> Dict[str, Any]:
        try:
            dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
            today = date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            if age < 18:
                return {
                    "field": "dob",
                    "status": "fail",
                    "message": f"Applicant age ({age} yrs) is under the legal minimum of 18 years"
                }
            if age > 100:
                return {
                    "field": "dob",
                    "status": "warning",
                    "message": f"Applicant age ({age} yrs) requires manual confirmation"
                }
            return {
                "field": "dob",
                "status": "pass",
                "message": f"Valid Date of Birth: {dob_str} (Applicant age: {age} yrs)"
            }
        except Exception:
            return {
                "field": "dob",
                "status": "warning",
                "message": f"Unrecognized date format for DOB: '{dob_str}'"
            }
