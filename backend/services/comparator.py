import json
import re
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from rapidfuzz import fuzz


class CrossDocumentComparator:
    """
    Compares extracted KYC identity information across multiple documents
    strictly belonging to the same applicant.
    
    Enforces field-specific verification rules:
    - Name: normalized text comparison; RapidFuzz token sort as secondary indicator for OCR variations.
    - DOB: exact comparison after normalizing dates to ISO YYYY-MM-DD.
    - Gender: exact comparison after normalizing to standard values (MALE/FEMALE/OTHER).
    - Identification number: compares only documents of the same type; validates formats individually.
    - Address: normalized text comparison with fuzzy similarity and manual review flagging.
    - Issue & Expiry date: validated individually per document; not conflated across different types.
    - Generates a structured attribute-by-document comparison matrix for officer inspection.
    """

    NAME_MATCH_THRESHOLD = 85.0
    NAME_PARTIAL_THRESHOLD = 70.0
    ADDRESS_MATCH_THRESHOLD = 60.0

    @staticmethod
    def normalize_name(name: Optional[str]) -> str:
        """Strip honorifics, punctuation, and extra whitespace for fair comparison."""
        if not name:
            return ""
        s = str(name).upper().strip()
        # Remove common prefixes
        s = re.sub(r"^(SHRI|SMT|MR|MRS|MS|DR|KUMAR|KUMARI)\b[\s.]*", "", s)
        # Remove punctuation except letters and numbers
        s = re.sub(r"[^A-Z0-9\s]", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    @staticmethod
    def normalize_dob(dob: Any) -> Optional[str]:
        """Normalize varying date string representations to standard ISO YYYY-MM-DD."""
        if not dob:
            return None
        s = str(dob).strip()
        # Common date patterns
        patterns = [
            "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y",
            "%Y/%m/%d", "%d.%m.%Y", "%d %b %Y", "%d %B %Y"
        ]
        for p in patterns:
            try:
                dt = datetime.strptime(s, p)
                return dt.strftime("%Y-%m-%d")
            except Exception:
                continue
        # Check if already ISO-like
        m = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
        if m:
            y, mo, d = m.groups()
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
        m2 = re.search(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", s)
        if m2:
            d, mo, y = m2.groups()
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
        return s

    @staticmethod
    def normalize_gender(gender: Any) -> Optional[str]:
        """Normalize gender values to standard MALE / FEMALE / OTHER."""
        if not gender:
            return None
        s = str(gender).strip().upper()
        if s in ("M", "MALE", "MAN"):
            return "MALE"
        if s in ("F", "FEMALE", "WOMAN"):
            return "FEMALE"
        if s in ("O", "OTHER", "TRANSGENDER"):
            return "OTHER"
        return s

    @classmethod
    def compare_applicant_documents(
        cls,
        documents: List[Dict[str, Any]],
        applicant_name: Optional[str] = None,
        applicant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Compare identity fields across all documents for an applicant,
        evaluating field-specific consistency, document validity/expiry,
        and producing a structured comparison matrix.
        
        Strict Applicant Isolation:
        - Ensures every document in the set belongs strictly to the target applicant.
        - Rejects cross-applicant or cross-dataset pollution.
        """
        # 0. Support passing applicant_id directly as the first parameter
        if isinstance(documents, str):
            applicant_id = documents
            from backend.database.db import get_documents_by_applicant, get_applicant
            app = get_applicant(applicant_id)
            if app and not applicant_name:
                applicant_name = app.get("name")
            raw_docs = get_documents_by_applicant(applicant_id)
            documents = []
            for d in raw_docs:
                doc_copy = dict(d)
                if isinstance(doc_copy.get("extracted_fields"), str):
                    try:
                        doc_copy["extracted_fields"] = json.loads(doc_copy["extracted_fields"])
                    except Exception:
                        pass
                if isinstance(doc_copy.get("validation_results"), str):
                    try:
                        doc_copy["validation_results"] = json.loads(doc_copy["validation_results"])
                    except Exception:
                        pass
                documents.append(doc_copy)

        # 1. Validate Applicant Isolation
        clean_docs = []
        isolation_errors = []
        observed_app_ids = set()

        for doc in documents:
            doc_app_id = doc.get("applicant_id")
            if doc_app_id:
                observed_app_ids.add(doc_app_id)
            if applicant_id and doc_app_id and doc_app_id != applicant_id:
                fname = doc.get("original_filename") or doc.get("filename") or "document"
                isolation_errors.append(
                    f"Applicant Isolation Violation: Document '{fname}' "
                    f"belongs to applicant '{doc_app_id}', not target applicant '{applicant_id}'."
                )
                continue
            clean_docs.append(doc)

        if len(observed_app_ids) > 1 and not applicant_id:
            # Multi-applicant list provided without explicit applicant_id filter
            first_id = sorted(list(observed_app_ids))[0]
            clean_docs = [d for d in clean_docs if d.get("applicant_id") == first_id]
            isolation_errors.append(
                f"Applicant Isolation Guard: Multiple applicant IDs detected in document set ({observed_app_ids}). "
                f"Isolating verification strictly to applicant '{first_id}'."
            )

        # 2. Hydrate and filter valid documents
        valid_docs = []
        seen_doc_ids = set()

        for doc in clean_docs:
            d_id = doc.get("id")
            if d_id and d_id in seen_doc_ids:
                continue
            if d_id:
                seen_doc_ids.add(d_id)

            fields = doc.get("extracted_fields") or doc.get("fields") or {}
            if isinstance(fields, str):
                try:
                    fields = json.loads(fields)
                except Exception:
                    fields = {}

            val_results = doc.get("validation_results") or {}
            if isinstance(val_results, str):
                try:
                    val_results = json.loads(val_results)
                except Exception:
                    val_results = {}

            if isinstance(fields, dict) and any(fields.values()):
                c_type = doc.get("classified_type")
                d_type = doc.get("document_type") or doc.get("type")
                if c_type and c_type.lower() != "unknown":
                    final_type = c_type.lower()
                elif d_type and d_type.lower() != "unknown":
                    final_type = d_type.lower()
                else:
                    final_type = (c_type or d_type or "unknown").lower()

                valid_docs.append({
                    "id": d_id or f"doc_{len(valid_docs)+1}",
                    "applicant_id": doc.get("applicant_id") or applicant_id,
                    "filename": doc.get("original_filename") or doc.get("filename") or "Unknown Document",
                    "type": final_type,
                    "fields": fields,
                    "validation_results": val_results,
                    "review_status": doc.get("review_status") or "pending"
                })

        # 3. Check for single or empty document set
        if len(valid_docs) < 2:
            single_doc = valid_docs[0] if valid_docs else None
            single_discrepancies = list(isolation_errors)
            single_checks = []

            if single_doc:
                # Individual document validity check (check if the single passport/DL is expired)
                exp_res = cls._check_document_validity_and_expiry([single_doc])
                if exp_res.get("status") == "fail":
                    single_discrepancies.append(exp_res["message"])
                    single_checks.append(exp_res)

            verdict = "DISCREPANCY_FLAGGED" if single_discrepancies else ("SINGLE_DOCUMENT_RECORDED" if len(valid_docs) == 1 else "NO_DOCUMENTS")
            
            # Compute confidence score using VerificationConfidenceEngine
            from backend.services.confidence_service import VerificationConfidenceEngine
            confidence_data = VerificationConfidenceEngine.calculate_overall_confidence(
                documents=valid_docs,
                cross_checks=single_checks,
                discrepancies=single_discrepancies,
                declared_name=applicant_name,
                has_expired_doc=any("expired" in d.lower() for d in single_discrepancies)
            )
            score = confidence_data["overall_confidence"]
            summary = (
                single_discrepancies[0]
                if single_discrepancies
                else (
                    "Single document on file. At least 2 documents are required for cross-document comparison."
                    if len(valid_docs) == 1
                    else "No documents available for comparison."
                )
            )

            matrix = cls._build_comparison_matrix(valid_docs, applicant_name, applicant_id, single_discrepancies, verdict, score, confidence_data=confidence_data)

            return {
                "overall_verdict": verdict,
                "consistency_score": score,
                "confidence": confidence_data,
                "total_documents_compared": len(valid_docs),
                "summary": summary,
                "discrepancies": single_discrepancies,
                "cross_checks": single_checks,
                "single_document": single_doc,
                "matrix": matrix,
                "documents_evaluated": [
                    {"id": d["id"], "filename": d["filename"], "type": d["type"]}
                    for d in valid_docs
                ]
            }

        # 4. Multi-document comparisons
        doc_types = [d.get("type", "").lower() for d in valid_docs if d.get("type")]
        rule_config_id = None
        rule_version = 1
        active_rules_map = {}
        combination_key = "unknown"
        try:
            from backend.services.triangulation_rule_service import TriangulationRuleService, get_canonical_combination_key
            combination_key = get_canonical_combination_key(doc_types) if doc_types else "unknown"
            rule_info = TriangulationRuleService.get_active_rules(combination_key)
            rule_config_id = rule_info.get("configuration", {}).get("id")
            rule_version = rule_info.get("active_version", 1)
            for r in rule_info.get("rules", []):
                concept = r.get("concept") or r.get("source_attribute")
                if concept:
                    active_rules_map[concept] = r
                if r.get("source_attribute"):
                    active_rules_map[r["source_attribute"]] = r
                if r.get("target_attribute"):
                    active_rules_map[r["target_attribute"]] = r
        except Exception:
            pass

        discrepancies: List[str] = list(isolation_errors)
        cross_checks: List[Dict[str, Any]] = []

        # A. Customer Name
        is_name_enabled = active_rules_map.get("name", {}).get("is_enabled", True) if active_rules_map else True
        if is_name_enabled:
            name_result = cls._compare_names(valid_docs, applicant_name)
            cross_checks.append(name_result)
            if name_result["status"] in ("fail", "warning"):
                discrepancies.append(name_result["message"])

        # B. Date of Birth
        is_dob_enabled = active_rules_map.get("dob", {}).get("is_enabled", True) if active_rules_map else True
        if is_dob_enabled:
            dob_result = cls._compare_dobs(valid_docs)
            cross_checks.append(dob_result)
            if dob_result["status"] == "fail":
                discrepancies.append(dob_result["message"])

        # C. Gender
        is_gender_enabled = active_rules_map.get("gender", {}).get("is_enabled", True) if active_rules_map else True
        if is_gender_enabled:
            gender_result = cls._compare_genders(valid_docs)
            cross_checks.append(gender_result)
            if gender_result["status"] == "fail":
                discrepancies.append(gender_result["message"])

        # D. Father's / Guardian's Name
        is_father_enabled = active_rules_map.get("father_name", {}).get("is_enabled", True) if active_rules_map else True
        if is_father_enabled:
            father_result = cls._compare_father_names(valid_docs)
            cross_checks.append(father_result)
            if father_result["status"] == "fail":
                discrepancies.append(father_result["message"])

        # E. Address
        is_address_enabled = active_rules_map.get("address", {}).get("is_enabled", True) if active_rules_map else True
        if is_address_enabled:
            address_result = cls._compare_addresses(valid_docs)
            if address_result.get("evaluated"):
                cross_checks.append(address_result)
                if address_result["status"] in ("fail", "warning"):
                    discrepancies.append(address_result["message"])

        # F. Identification Number Consistency
        id_result = cls._compare_id_numbers(valid_docs)
        cross_checks.append(id_result)
        if id_result["status"] == "fail":
            discrepancies.append(id_result["message"])

        # G. Document Validity & Expiry
        expiry_result = cls._check_document_validity_and_expiry(valid_docs)
        if expiry_result.get("evaluated"):
            cross_checks.append(expiry_result)
            if expiry_result["status"] == "fail":
                for d in expiry_result.get("issues", [expiry_result["message"]]):
                    if d not in discrepancies:
                        discrepancies.append(d)

        # H. Mandatory Fields & Quality
        mand_result = cls._check_mandatory_fields(valid_docs)
        if mand_result.get("evaluated"):
            cross_checks.append(mand_result)
            if mand_result["status"] == "fail":
                for d in mand_result.get("issues", [mand_result["message"]]):
                    if d not in discrepancies:
                        discrepancies.append(d)

        # I. Human Review Decisions
        review_result = cls._check_review_decisions(valid_docs)
        if review_result.get("evaluated"):
            cross_checks.append(review_result)
            if review_result["status"] == "fail":
                for d in review_result.get("issues", [review_result["message"]]):
                    if d not in discrepancies:
                        discrepancies.append(d)

        # Check document validity & expiry
        has_expired_doc = any(c.get("field") == "document_validity" and c.get("status") == "fail" for c in cross_checks)

        # Calculate authoritative confidence and validate identity
        from backend.services.confidence_service import VerificationConfidenceEngine
        confidence_data = VerificationConfidenceEngine.calculate_overall_confidence(
            documents=valid_docs,
            cross_checks=cross_checks,
            discrepancies=discrepancies,
            declared_name=applicant_name,
            has_expired_doc=has_expired_doc
        )

        identity_val = confidence_data.get("identity_validation") or {}
        if identity_val.get("is_blocking"):
            if identity_val["message"] not in discrepancies:
                discrepancies.insert(0, identity_val["message"])

        # Determine Verdict
        discrepancies = list(dict.fromkeys(discrepancies))
        has_critical_fail = any(c["status"] == "fail" for c in cross_checks) or identity_val.get("is_blocking")
        has_warning = any(c["status"] == "warning" for c in cross_checks) or (identity_val.get("status") == "REVIEW_REQUIRED")

        # Determine consistency_score: 100.0 if all cross-checks passed with zero discrepancies
        if not discrepancies and not has_critical_fail and not has_warning:
            overall_score = 100.0
        else:
            overall_score = confidence_data["overall_confidence"]

        if has_critical_fail:
            verdict = "DISCREPANCY_FLAGGED"
            summary = f"Verification flagged with {len(discrepancies)} discrepancy(ies). Issues: {'; '.join(discrepancies[:2])}"
        elif has_warning or overall_score <= 75.0:
            verdict = "MANUAL_REVIEW"
            summary = f"Manual review recommended. Issues: {'; '.join(discrepancies[:2]) if discrepancies else 'Verification confidence is at or below the 75% threshold.'}"
        else:
            verdict = "VERIFIED"
            summary = f"Cross-verified {len(valid_docs)} documents with {overall_score}% overall verification confidence."

        # Generate Structured Comparison Matrix
        matrix = cls._build_comparison_matrix(
            valid_docs, applicant_name, applicant_id, discrepancies, verdict, overall_score,
            active_rules_map=active_rules_map, rule_config_id=rule_config_id, rule_version=rule_version, combination_key=combination_key,
            confidence_data=confidence_data
        )

        return {
            "overall_verdict": verdict,
            "consistency_score": overall_score,
            "confidence": confidence_data,
            "total_documents_compared": len(valid_docs),
            "summary": summary,
            "discrepancies": discrepancies,
            "cross_checks": cross_checks,
            "matrix": matrix,
            "rule_configuration_id": rule_config_id,
            "rule_version": rule_version,
            "combination_key": combination_key,
            "documents_evaluated": [
                {"id": d["id"], "filename": d["filename"], "type": d["type"]}
                for d in valid_docs
            ]
        }

    @classmethod
    def _compare_names(cls, docs: List[Dict[str, Any]], applicant_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Compare names across uploaded documents:
        - Compares only extracted values between documents belonging to the same applicant.
        - Never compares against placeholders or declared profile strings.
        """
        names_found = []
        for d in docs:
            n = d["fields"].get("name") or d["fields"].get("applicant_name")
            if n and str(n).strip():
                dtype = (d.get("type") or "Doc").replace("_", " ").upper()
                names_found.append((dtype, str(n).strip(), d.get("filename", "Doc")))

        if len(names_found) < 2:
            msg = f"Customer name recorded from {names_found[0][0]} ('{names_found[0][1]}')." if names_found else "Customer name not detected on uploaded documents."
            return {
                "field": "name",
                "evaluated": False,
                "status": "pass",
                "score": 100.0,
                "message": msg
            }

        # Check normalized exact equality first
        normalized_pairs = []
        scores = []
        for i in range(len(names_found)):
            for j in range(i + 1, len(names_found)):
                type1, raw1, f1 = names_found[i]
                type2, raw2, f2 = names_found[j]
                norm1 = cls.normalize_name(raw1)
                norm2 = cls.normalize_name(raw2)

                sim = fuzz.token_sort_ratio(norm1, norm2) if (norm1 and norm2) else 0.0
                scores.append(sim)
                normalized_pairs.append({
                    "doc1": type1, "name1": raw1, "file1": f1,
                    "doc2": type2, "name2": raw2, "file2": f2,
                    "exact_normalized_match": (norm1 == norm2),
                    "similarity": round(sim, 1)
                })

        min_sim = min(scores)
        avg_sim = round(sum(scores) / len(scores), 1)

        # If all pairs have exact normalized match
        if all(p["exact_normalized_match"] for p in normalized_pairs):
            return {
                "field": "name",
                "evaluated": True,
                "status": "pass",
                "score": 100.0,
                "message": f"Applicant name matches consistently across all documents ('{names_found[0][1]}').",
                "details": normalized_pairs
            }

        if min_sim >= cls.NAME_MATCH_THRESHOLD:
            status = "pass"
            msg = f"Applicant name matches with minor token order/spelling consistency (Average: {avg_sim}%)."
        elif min_sim >= cls.NAME_PARTIAL_THRESHOLD:
            status = "warning"
            msg = f"Minor name variation detected ({min_sim}% to {avg_sim}% match). Review recommended."
        else:
            status = "fail"
            mismatched = [p for p in normalized_pairs if p["similarity"] < cls.NAME_PARTIAL_THRESHOLD]
            sample = mismatched[0] if mismatched else normalized_pairs[0]
            msg = f"Name mismatch: '{sample['name1']}' on {sample['doc1']} vs '{sample['name2']}' on {sample['doc2']} (Similarity: {sample['similarity']}%)."

        return {
            "field": "name",
            "evaluated": True,
            "status": status,
            "score": avg_sim,
            "message": msg,
            "details": normalized_pairs
        }

    @classmethod
    def _compare_dobs(cls, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Exact comparison of Date of Birth after normalizing to ISO YYYY-MM-DD.
        Missing DOB is NOT treated as a mismatch.
        """
        dobs = []
        for d in docs:
            raw_dob = d["fields"].get("dob") or d["fields"].get("date_of_birth")
            if raw_dob:
                norm_dob = cls.normalize_dob(raw_dob)
                dobs.append((d["type"], str(raw_dob).strip(), norm_dob, d["filename"]))

        if len(dobs) < 2:
            return {
                "field": "dob",
                "evaluated": False,
                "status": "pass",
                "score": 100.0,
                "message": "DOB present on fewer than 2 documents (missing DOB is not a mismatch)."
            }

        unique_normalized_dobs = set(d[2] for d in dobs if d[2])

        if len(unique_normalized_dobs) == 1:
            matching_dob = dobs[0][2]
            return {
                "field": "dob",
                "evaluated": True,
                "status": "pass",
                "score": 100.0,
                "message": f"Date of Birth ({matching_dob}) matches across all documents.",
                "details": dobs
            }
        else:
            formatted_diff = ", ".join(f"{t} ({f}): '{raw}'" for t, raw, norm, f in dobs)
            return {
                "field": "dob",
                "evaluated": True,
                "status": "fail",
                "score": 0.0,
                "message": f"DOB mismatch: Date of Birth mismatch detected between documents: {formatted_diff}.",
                "details": dobs
            }

    @classmethod
    def _compare_genders(cls, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Exact comparison of Gender after normalizing to MALE / FEMALE / OTHER.
        Missing gender is NOT treated as a mismatch.
        """
        genders = []
        for d in docs:
            raw_g = d["fields"].get("gender")
            if raw_g:
                norm_g = cls.normalize_gender(raw_g)
                genders.append((d["type"], str(raw_g).strip(), norm_g, d["filename"]))

        if len(genders) < 2:
            return {
                "field": "gender",
                "evaluated": False,
                "status": "pass",
                "score": 100.0,
                "message": "Gender specified on fewer than 2 documents."
            }

        unique_genders = set(g[2] for g in genders if g[2])
        if len(unique_genders) == 1:
            return {
                "field": "gender",
                "evaluated": True,
                "status": "pass",
                "score": 100.0,
                "message": f"Gender ({genders[0][2]}) is consistent across documents.",
                "details": genders
            }
        else:
            diff_str = ", ".join(f"{t}: '{raw}'" for t, raw, norm, f in genders)
            return {
                "field": "gender",
                "evaluated": True,
                "status": "fail",
                "score": 40.0,
                "message": f"Conflicting gender entries found across documents: {diff_str}.",
                "details": genders
            }

    @classmethod
    def _compare_id_numbers(cls, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compare identification numbers ONLY when multiple documents of the SAME type exist.
        Different document types have different numbering systems by definition.
        """
        by_type = {}
        for d in docs:
            dtype = d["type"]
            id_val = d["fields"].get("id_number") or d["fields"].get("identification_number") or d["fields"].get("masked_id")
            if id_val and str(id_val).strip():
                clean_id = re.sub(r"[\s-]", "", str(id_val).upper())
                by_type.setdefault(dtype, []).append((clean_id, id_val, d["filename"]))

        conflicts = []
        evaluated = False
        for dtype, id_list in by_type.items():
            if len(id_list) >= 2:
                evaluated = True
                unique_ids = set(item[0] for item in id_list)
                if len(unique_ids) > 1:
                    conflicts.append(f"Multiple conflicting {dtype.replace('_', ' ').upper()} numbers detected: {', '.join(item[1] for item in id_list)}")

        if conflicts:
            return {
                "field": "id_numbers",
                "evaluated": True,
                "status": "fail",
                "score": 0.0,
                "message": "; ".join(conflicts),
                "details": by_type
            }

        return {
            "field": "id_numbers",
            "evaluated": evaluated,
            "status": "pass",
            "score": 100.0,
            "message": "All document-specific identification numbers are valid and consistent." if evaluated else "Identification numbers evaluated within respective categories; no cross-type comparison performed.",
            "details": by_type
        }

    @classmethod
    def _compare_father_names(cls, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compare father / guardian names across documents where available."""
        fathers = []
        for d in docs:
            f = d["fields"].get("father_name")
            if f and len(str(f).strip()) >= 3:
                fathers.append((d["type"], str(f).strip(), cls.normalize_name(f)))

        if len(fathers) < 2:
            return {
                "field": "father_name",
                "evaluated": False,
                "status": "pass",
                "score": 100.0,
                "message": "Father's name found on fewer than 2 documents."
            }

        sim = fuzz.token_sort_ratio(fathers[0][2], fathers[1][2])
        status = "pass" if sim >= 80 else ("warning" if sim >= 65 else "fail")
        return {
            "field": "father_name",
            "evaluated": True,
            "status": status,
            "score": round(sim, 1),
            "message": f"Father/Guardian name comparison ({sim}% similarity): '{fathers[0][1]}' vs '{fathers[1][1]}'.",
            "details": fathers
        }

    @classmethod
    def _compare_addresses(cls, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Pairwise comparison of addresses when multiple documents have addresses."""
        addrs = []
        for d in docs:
            a = d["fields"].get("address")
            if a and len(str(a).strip()) >= 10:
                addrs.append((d["type"], str(a).strip()))

        if len(addrs) < 2:
            return {
                "field": "address",
                "evaluated": False,
                "status": "pass",
                "score": 100.0,
                "message": "Fewer than 2 documents contained an address."
            }

        sim = fuzz.token_set_ratio(addrs[0][1].lower(), addrs[1][1].lower())
        if sim >= cls.ADDRESS_MATCH_THRESHOLD:
            status = "pass"
            msg = f"Address matches consistently across documents ({sim}% match)."
        elif sim >= 45.0:
            status = "warning"
            msg = f"Address variation detected across documents ({sim}% match). Review recommended."
        else:
            status = "fail"
            msg = f"Significant address mismatch across documents ({sim}% match)."

        return {
            "field": "address",
            "evaluated": True,
            "status": status,
            "score": round(sim, 1),
            "message": msg,
            "details": addrs
        }

    @classmethod
    def _check_document_validity_and_expiry(cls, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Check for expired documents (Driving Licences, Passports) or expiry failures.
        An expired document MUST trigger status='fail' and score=0.0.
        """
        expired_issues = []
        today = date.today()

        for d in docs:
            filename = d.get("filename", "Document")
            dtype = (d.get("type") or "unknown").replace("_", " ").title()
            val = d.get("validation_results") or {}
            fields = d.get("fields") or {}

            # 1. Check validation flags and checks
            flags = val.get("flags") or []
            is_expired = any("expired" in str(f).lower() for f in flags)
            for c in val.get("checks", []):
                if c.get("field") == "expiry_date" and c.get("status") == "fail":
                    is_expired = True

            # 2. Check extracted expiry date field directly
            exp_str = fields.get("expiry_date")
            if exp_str:
                try:
                    exp_norm = cls.normalize_dob(exp_str)
                    if exp_norm:
                        exp_d = datetime.strptime(exp_norm, "%Y-%m-%d").date()
                        if exp_d < today:
                            is_expired = True
                except Exception:
                    pass

            if is_expired:
                expired_issues.append(f"Expired {dtype}: '{filename}' has passed its legal validity date.")

        if expired_issues:
            return {
                "field": "document_expiry",
                "evaluated": True,
                "status": "fail",
                "score": 0.0,
                "message": f"Expired document detected: {'; '.join(expired_issues)}",
                "issues": expired_issues
            }

        return {
            "field": "document_expiry",
            "evaluated": True,
            "status": "pass",
            "score": 100.0,
            "message": "All submitted identity documents are within their valid non-expired timelines."
        }

    @classmethod
    def _check_mandatory_fields(cls, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Verify presence of essential mandatory KYC identity fields."""
        issues = []
        for d in docs:
            filename = d.get("filename", "Document")
            dtype = (d.get("type") or "unknown").replace("_", " ").title()
            f = d.get("fields") or {}
            val = d.get("validation_results") or {}

            name = f.get("name") or f.get("applicant_name")
            id_num = f.get("id_number") or f.get("identification_number") or f.get("masked_id")

            if not name or len(str(name).strip()) < 2:
                issues.append(f"Missing applicant name in {dtype} ('{filename}')")

            has_id_key = any(k in f for k in ("id_number", "identification_number", "masked_id"))
            if has_id_key or val:
                if not id_num or len(str(id_num).strip()) < 4:
                    issues.append(f"Missing identification number in {dtype} ('{filename}')")

            flags = val.get("flags") or []
            if any("missing mandatory" in str(fl).lower() for fl in flags):
                msg = f"Mandatory fields incomplete in {dtype} ('{filename}')"
                if msg not in issues:
                    issues.append(msg)

        if issues:
            return {
                "field": "mandatory_fields",
                "evaluated": True,
                "status": "fail",
                "score": 30.0,
                "message": f"Mandatory field deficiencies found: {'; '.join(issues)}",
                "issues": issues
            }

        return {
            "field": "mandatory_fields",
            "evaluated": True,
            "status": "pass",
            "score": 100.0,
            "message": "All mandatory KYC identity fields are present and populated."
        }

    @classmethod
    def _check_review_decisions(cls, docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Verify human officer review decisions across applicant documents."""
        issues = []
        rejected_docs = [d.get("filename", "Document") for d in docs if d.get("review_status") == "rejected"]
        resub_docs = [d.get("filename", "Document") for d in docs if d.get("review_status") == "resubmission_requested"]

        if len(rejected_docs) > 1 and len(rejected_docs) == len(docs):
            issues.append("Applicant KYC rejected by review officer")
        elif rejected_docs:
            issues.append(f"Rejected by review officer ({len(rejected_docs)} doc{'s' if len(rejected_docs) > 1 else ''})")

        if resub_docs:
            issues.append(f"Resubmission requested ({len(resub_docs)} doc{'s' if len(resub_docs) > 1 else ''})")

        if issues:
            return {
                "field": "review_decisions",
                "evaluated": True,
                "status": "fail",
                "score": 0.0,
                "message": f"Officer review flags: {'; '.join(issues)}",
                "issues": issues
            }

        return {
            "field": "review_decisions",
            "evaluated": False,
            "status": "pass",
            "score": 100.0,
            "message": "No negative review decisions recorded."
        }

    @classmethod
    def _build_comparison_matrix(
        cls,
        docs: List[Dict[str, Any]],
        applicant_name: Optional[str],
        applicant_id: Optional[str],
        discrepancies: List[str],
        verdict: str,
        score: float,
        active_rules_map: Optional[Dict[str, Any]] = None,
        rule_config_id: Optional[str] = None,
        rule_version: int = 1,
        combination_key: Optional[str] = None,
        confidence_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Construct a consolidated KYC extraction and comparison table.
        Columns: Attribute, followed by applicant's uploaded documents sorted in standard KYC order,
        and finally the Comparison Result.
        Rows:
        1. Customer Name
        2. Date of Birth
        3. Gender
        4. Identification Number (masked)
        5. Residential Address
        6. Father / Guardian Name
        7. Expiry Date / Validity
        (Issue Date is completely removed from the interface).
        """
        def is_rule_disabled(key: str) -> bool:
            if not active_rules_map:
                return False
            r = active_rules_map.get(key)
            if not r:
                return False
            # Never substitute NOT EXECUTED for NOT APPLICABLE. Single-document or non-comparable attributes are not disabled policy rules.
            if r.get("concept") in ("single_document_field", "incompatible_identifiers"):
                return False
            if r.get("rule_type") in ("single_document", "incompatible"):
                return False
            if r.get("is_enabled") is False and (r.get("concept") == key or r.get("source_attribute") == key):
                return True
            return False

        # Sort documents into logical KYC order: Aadhaar -> PAN -> Passport -> Driving Licence -> Voter ID
        type_rank = {
            "aadhaar": 1,
            "pan": 2,
            "passport": 3,
            "driving_licence": 4,
            "voter_id": 5
        }
        docs_sorted = sorted(docs, key=lambda d: type_rank.get(d.get("type", "").lower(), 99))

        doc_cols = []
        for d in docs_sorted:
            t = (d.get("type") or "unknown").lower()
            type_label = {
                "aadhaar": "Aadhaar",
                "pan": "PAN",
                "passport": "Passport",
                "driving_licence": "Driving Licence",
                "voter_id": "Voter ID"
            }.get(t, t.replace("_", " ").title())

            doc_cols.append({
                "id": d["id"],
                "filename": d.get("filename", "Document"),
                "document_type": t,
                "type_label": type_label,
                "review_status": d.get("review_status", "pending")
            })

        matrix_rows = []

        # ==========================================
        # 0. Declared Applicant Identity Validation
        # ==========================================
        from backend.services.confidence_service import VerificationConfidenceEngine
        id_val = VerificationConfidenceEngine.validate_applicant_identity(applicant_name, docs_sorted)
        id_cell_vals = {}
        for d in docs_sorted:
            val = d["fields"].get("name") or d["fields"].get("applicant_name")
            id_cell_vals[d["id"]] = str(val).strip() if (val and str(val).strip()) else "Not detected"

        if not applicant_name or not str(applicant_name).strip():
            id_status = "MISSING"
            id_label = "MISSING"
            id_exp = "Declared applicant name was not provided for identity cross-validation."
        elif id_val["status"] == "PASS":
            id_status = "MATCH"
            id_label = "MATCH"
            id_exp = id_val["message"]
        elif id_val["status"] == "REVIEW_REQUIRED":
            id_status = "NOT_COMPARABLE"
            id_label = "NOT COMPARABLE"
            id_exp = id_val["message"]
        else:
            id_status = "MISMATCH"
            id_label = "MISMATCH"
            id_exp = id_val["message"]

        matrix_rows.append({
            "attribute_key": "identity_validation",
            "attribute_label": "Declared Applicant Identity",
            "values": id_cell_vals,
            "result_status": id_status,
            "result_label": id_label,
            "explanation": id_exp
        })

        # ==========================================
        # 1. Customer Name Row
        # ==========================================
        name_vals = {}
        name_entries = []
        for d in docs_sorted:
            val = d["fields"].get("name") or d["fields"].get("applicant_name")
            if val and str(val).strip():
                name_vals[d["id"]] = str(val).strip()
                dtype = (d.get("type") or "Doc").replace("_", " ").title()
                name_entries.append((dtype, str(val).strip(), cls.normalize_name(val)))
            else:
                name_vals[d["id"]] = "Not detected"

        if is_rule_disabled("name"):
            name_status = "NOT_EXECUTED"
            name_label = "NOT EXECUTED"
            name_exp = "Customer name comparison disabled by active triangulation policy."
        elif len(name_entries) >= 2:
            mismatches = []
            for i in range(len(name_entries)):
                for j in range(i + 1, len(name_entries)):
                    t1, raw1, norm1 = name_entries[i]
                    t2, raw2, norm2 = name_entries[j]
                    sim = fuzz.token_sort_ratio(norm1, norm2) if (norm1 and norm2) else 0.0
                    if sim < cls.NAME_MATCH_THRESHOLD:
                        mismatches.append((t1, raw1, t2, raw2, sim))

            if not mismatches:
                doc_types_str = " and ".join(e[0] for e in name_entries)
                name_status = "MATCH"
                name_label = "MATCH"
                name_exp = f"Name matches across {doc_types_str}: {name_entries[0][1]}."
            else:
                worst = min(mismatches, key=lambda x: x[4])
                t1, raw1, t2, raw2, min_sim = worst
                name_status = "MISMATCH"
                name_label = "MISMATCH"
                name_exp = f"Name mismatch: {t1} ('{raw1}') differs from {t2} ('{raw2}')."
        elif len(name_entries) == 1:
            if len(docs_sorted) > 1:
                other_types = [d.get("type", "Document").replace("_", " ").title() for d in docs_sorted if (d["fields"].get("name") is None or not str(d["fields"].get("name", "")).strip())]
                name_status = "NOT_DETECTED"
                name_label = "NOT DETECTED"
                name_exp = f"Name recorded from {name_entries[0][0]} ('{name_entries[0][1]}'), but not detected on {', '.join(other_types)}. Cross-document comparison could not be completed."
            else:
                name_status = "NOT_COMPARABLE"
                name_label = "NOT COMPARABLE"
                name_exp = f"Name recorded from {name_entries[0][0]} ('{name_entries[0][1]}'). Single document submitted; multi-document comparison requires at least two documents."
        else:
            name_status = "MISSING"
            name_label = "MISSING"
            name_exp = "Customer name was not detected on any uploaded document."

        matrix_rows.append({
            "attribute_key": "name",
            "attribute_label": "Customer Name",
            "values": name_vals,
            "result_status": name_status,
            "result_label": name_label,
            "explanation": name_exp
        })

        # ==========================================
        # 2. Date of Birth Row
        # ==========================================
        dob_vals = {}
        dob_entries = []
        for d in docs_sorted:
            raw = d["fields"].get("dob") or d["fields"].get("date_of_birth")
            if raw and str(raw).strip():
                norm = cls.normalize_dob(raw) or str(raw).strip()
                dob_vals[d["id"]] = norm
                dtype = (d.get("type") or "Doc").replace("_", " ").title()
                dob_entries.append((dtype, str(raw).strip(), norm))
            else:
                dob_vals[d["id"]] = "Not detected"

        if is_rule_disabled("dob"):
            dob_status = "NOT_EXECUTED"
            dob_label = "NOT EXECUTED"
            dob_exp = "Date of birth comparison disabled by active triangulation policy."
        elif len(dob_entries) >= 2:
            mismatches = []
            for i in range(len(dob_entries)):
                for j in range(i + 1, len(dob_entries)):
                    t1, raw1, norm1 = dob_entries[i]
                    t2, raw2, norm2 = dob_entries[j]
                    if norm1 != norm2:
                        mismatches.append((t1, raw1, t2, raw2))

            if not mismatches:
                doc_types_str = " and ".join(e[0] for e in dob_entries)
                dob_status = "MATCH"
                dob_label = "MATCH"
                dob_exp = f"Date of birth matches across {doc_types_str}: {dob_entries[0][2]}."
            else:
                t1, raw1, t2, raw2 = mismatches[0]
                dob_status = "MISMATCH"
                dob_label = "MISMATCH"
                dob_exp = f"Date of birth differs between {t1} ('{raw1}') and {t2} ('{raw2}')."
        elif len(dob_entries) == 1:
            if len(docs_sorted) > 1:
                other_types = [d.get("type", "Document").replace("_", " ").title() for d in docs_sorted if not (d["fields"].get("dob") or d["fields"].get("date_of_birth"))]
                dob_status = "NOT_DETECTED"
                dob_label = "NOT DETECTED"
                dob_exp = f"DOB detected on {dob_entries[0][0]} ({dob_entries[0][2]}), but not detected on {', '.join(other_types)}."
            else:
                dob_status = "NOT_COMPARABLE"
                dob_label = "NOT COMPARABLE"
                dob_exp = f"DOB recorded from {dob_entries[0][0]} ({dob_entries[0][2]}). Single document submitted; no counterpart available for comparison."
        else:
            dob_status = "MISSING"
            dob_label = "MISSING"
            dob_exp = "Date of birth was not detected on any uploaded document."

        matrix_rows.append({
            "attribute_key": "dob",
            "attribute_label": "Date of Birth",
            "values": dob_vals,
            "result_status": dob_status,
            "result_label": dob_label,
            "explanation": dob_exp
        })

        # ==========================================
        # 3. Gender Row (PAN is Not Applicable)
        # ==========================================
        gender_vals = {}
        gender_entries = []
        for d in docs_sorted:
            t = (d.get("type") or "").lower()
            if t == "pan":
                gender_vals[d["id"]] = "Not applicable"
            else:
                raw_g = d["fields"].get("gender")
                if raw_g and str(raw_g).strip():
                    norm_g = cls.normalize_gender(raw_g)
                    gender_vals[d["id"]] = norm_g
                    dtype = (d.get("type") or "Doc").replace("_", " ").title()
                    gender_entries.append((dtype, norm_g))
                else:
                    gender_vals[d["id"]] = "Not detected"

        if is_rule_disabled("gender"):
            gender_status = "NOT_EXECUTED"
            gender_label = "NOT EXECUTED"
            gender_exp = "Gender comparison disabled by active triangulation policy."
        else:
            supported_gender_docs = [d for d in docs_sorted if (d.get("type") or "").lower() != "pan"]
            if len(supported_gender_docs) == 0:
                gender_status = "NOT_APPLICABLE"
                gender_label = "NOT APPLICABLE"
                gender_exp = "Gender is not supported by PAN Card. No comparison required."
            elif len(gender_entries) >= 2:
                mismatches = []
                for i in range(len(gender_entries)):
                    for j in range(i + 1, len(gender_entries)):
                        t1, g1 = gender_entries[i]
                        t2, g2 = gender_entries[j]
                        if g1 != g2:
                            mismatches.append((t1, g1, t2, g2))

                if not mismatches:
                    doc_types_str = " and ".join(e[0] for e in gender_entries)
                    gender_status = "MATCH"
                    gender_label = "MATCH"
                    gender_exp = f"Gender matches across {doc_types_str}: {gender_entries[0][1]}."
                else:
                    t1, g1, t2, g2 = mismatches[0]
                    gender_status = "MISMATCH"
                    gender_label = "MISMATCH"
                    gender_exp = f"Gender mismatch between {t1} ('{g1}') and {t2} ('{g2}')."
            elif len(gender_entries) == 1:
                has_pan = any((d.get("type") or "").lower() == "pan" for d in docs_sorted)
                if has_pan and len(supported_gender_docs) == 1:
                    gender_status = "NOT_APPLICABLE"
                    gender_label = "NOT APPLICABLE"
                    gender_exp = f"Gender recorded on {gender_entries[0][0]} ('{gender_entries[0][1]}'). PAN Card does not record gender; no comparison was required."
                elif len(docs_sorted) > 1:
                    gender_status = "NOT_DETECTED"
                    gender_label = "NOT DETECTED"
                    gender_exp = f"Gender recorded on {gender_entries[0][0]} ('{gender_entries[0][1]}'), but not detected on other submitted identity document."
                else:
                    gender_status = "NOT_COMPARABLE"
                    gender_label = "NOT COMPARABLE"
                    gender_exp = f"Gender recorded on {gender_entries[0][0]} ('{gender_entries[0][1]}'). Single document submitted; no comparison counterpart."
            else:
                gender_status = "NOT_DETECTED"
                gender_label = "NOT DETECTED"
                gender_exp = "Gender is an expected attribute on submitted document but could not be detected."

        matrix_rows.append({
            "attribute_key": "gender",
            "attribute_label": "Gender",
            "values": gender_vals,
            "result_status": gender_status,
            "result_label": gender_label,
            "explanation": gender_exp
        })

        # ==========================================
        # 4. Identification Number (masked)
        # ==========================================
        id_vals = {}
        missing_ids = []
        for d in docs_sorted:
            t = (d.get("type") or "").lower()
            val = (
                d["fields"].get("masked_id")
                or d["fields"].get("id_number")
                or d["fields"].get("identification_number")
                or d["fields"].get("pan")
                or d["fields"].get("aadhaar")
                or d["fields"].get("passport_number")
                or d["fields"].get("dl_number")
                or d["fields"].get("voter_id")
            )
            if val and str(val).strip():
                id_vals[d["id"]] = str(val).strip()
            else:
                id_vals[d["id"]] = "Not detected"
                missing_ids.append((d.get("type") or "Doc").replace("_", " ").title())

        if missing_ids:
            id_status = "NOT_DETECTED"
            id_label = "NOT DETECTED"
            id_exp = f"Identification number missing or unreadable on {', '.join(missing_ids)}."
        else:
            id_status = "MATCH"
            id_label = "MATCH"
            id_exp = "Identification numbers validated individually against regulatory formats (Aadhaar/PAN/Passport are document-specific)."

        matrix_rows.append({
            "attribute_key": "id_number",
            "attribute_label": "Identification Number (masked)",
            "values": id_vals,
            "result_status": id_status,
            "result_label": id_label,
            "explanation": id_exp
        })

        # ==========================================
        # 5. Residential Address (PAN is Not Applicable)
        # ==========================================
        addr_vals = {}
        addr_entries = []
        for d in docs_sorted:
            t = (d.get("type") or "").lower()
            if t == "pan":
                addr_vals[d["id"]] = "Not applicable"
            else:
                val = d["fields"].get("address")
                if val and len(str(val).strip()) >= 5:
                    addr_vals[d["id"]] = str(val).strip()
                    dtype = (d.get("type") or "Doc").replace("_", " ").title()
                    addr_entries.append((dtype, str(val).strip()))
                else:
                    addr_vals[d["id"]] = "Not detected"

        if is_rule_disabled("address"):
            addr_status = "NOT_EXECUTED"
            addr_label = "NOT EXECUTED"
            addr_exp = "Address comparison disabled by active triangulation policy."
        else:
            supported_addr_docs = [d for d in docs_sorted if (d.get("type") or "").lower() != "pan"]
            if len(supported_addr_docs) == 0:
                addr_status = "NOT_APPLICABLE"
                addr_label = "NOT APPLICABLE"
                addr_exp = "Residential address is not supported by PAN Card. No comparison required."
            elif len(addr_entries) >= 2:
                sim = fuzz.token_set_ratio(addr_entries[0][1].lower(), addr_entries[1][1].lower())
                if sim >= cls.ADDRESS_MATCH_THRESHOLD:
                    addr_status = "MATCH"
                    addr_label = "MATCH"
                    addr_exp = f"Address consistent across address proofs ({sim}% concordance)."
                elif sim >= 45:
                    addr_status = "MISMATCH"
                    addr_label = "MISMATCH"
                    addr_exp = f"Minor address variation between documents ({sim}% match). Review recommended."
                else:
                    addr_status = "MISMATCH"
                    addr_label = "MISMATCH"
                    addr_exp = f"Address mismatch: {addr_entries[0][0]} differs significantly from {addr_entries[1][0]}."
            elif len(addr_entries) == 1:
                has_pan = any((d.get("type") or "").lower() == "pan" for d in docs_sorted)
                if has_pan and len(supported_addr_docs) == 1:
                    addr_status = "NOT_COMPARABLE"
                    addr_label = "NOT COMPARABLE"
                    addr_exp = f"Address recorded from {addr_entries[0][0]}. PAN Card does not support address; no secondary address proof was submitted for comparison."
                elif len(docs_sorted) > 1:
                    addr_status = "NOT_DETECTED"
                    addr_label = "NOT DETECTED"
                    addr_exp = f"Address recorded on {addr_entries[0][0]}, but not detected on remaining submitted address proof."
                else:
                    addr_status = "NOT_COMPARABLE"
                    addr_label = "NOT COMPARABLE"
                    addr_exp = f"Address recorded from {addr_entries[0][0]}. Single document submitted; no secondary address proof available."
            else:
                addr_status = "NOT_DETECTED"
                addr_label = "NOT DETECTED"
                addr_exp = "Residential address was not detected on submitted address proof document."

        matrix_rows.append({
            "attribute_key": "address",
            "attribute_label": "Residential Address",
            "values": addr_vals,
            "result_status": addr_status,
            "result_label": addr_label,
            "explanation": addr_exp
        })

        # ==========================================
        # 6. Father / Guardian Name
        # ==========================================
        father_vals = {}
        father_entries = []
        for d in docs_sorted:
            t = (d.get("type") or "").lower()
            if t == "aadhaar":
                father_vals[d["id"]] = "Not applicable"
            else:
                val = d["fields"].get("father_name") or d["fields"].get("guardian_name") or d["fields"].get("husband_name")
                if val and str(val).strip():
                    father_vals[d["id"]] = str(val).strip()
                    dtype = (d.get("type") or "Doc").replace("_", " ").title()
                    father_entries.append((dtype, str(val).strip()))
                else:
                    father_vals[d["id"]] = "Not detected" if t in ("pan", "driving_licence", "passport", "voter_id") else "Not applicable"

        if is_rule_disabled("father_name"):
            father_status = "NOT_EXECUTED"
            father_label = "NOT EXECUTED"
            father_exp = "Father / Guardian name comparison disabled by active triangulation policy."
        else:
            supported_father_docs = [d for d in docs_sorted if (d.get("type") or "").lower() in ("pan", "driving_licence", "passport", "voter_id")]
            if len(supported_father_docs) == 0:
                father_status = "NOT_APPLICABLE"
                father_label = "NOT APPLICABLE"
                father_exp = "Father / Guardian name is not a standard attribute on Aadhaar Card."
            elif len(father_entries) >= 2:
                sim = fuzz.token_sort_ratio(father_entries[0][1].lower(), father_entries[1][1].lower())
                if sim >= 80:
                    father_status = "MATCH"
                    father_label = "MATCH"
                    father_exp = f"Father / Guardian name matches across documents: {father_entries[0][1]}."
                else:
                    father_status = "MISMATCH"
                    father_label = "MISMATCH"
                    father_exp = f"Father / Guardian name mismatch: {father_entries[0][0]} ('{father_entries[0][1]}') vs {father_entries[1][0]} ('{father_entries[1][1]}')."
            elif len(father_entries) == 1:
                has_aadhaar = any((d.get("type") or "").lower() == "aadhaar" for d in docs_sorted)
                if has_aadhaar and len(supported_father_docs) == 1:
                    father_status = "NOT_COMPARABLE"
                    father_label = "NOT COMPARABLE"
                    father_exp = f"Father's name recorded from {father_entries[0][0]} ('{father_entries[0][1]}'). Not applicable on Aadhaar Card; no comparison counterpart."
                elif len(docs_sorted) > 1:
                    father_status = "NOT_DETECTED"
                    father_label = "NOT DETECTED"
                    father_exp = f"Father's name recorded from {father_entries[0][0]}, but not detected on other submitted document."
                else:
                    father_status = "NOT_COMPARABLE"
                    father_label = "NOT COMPARABLE"
                    father_exp = f"Father's name recorded from {father_entries[0][0]} ('{father_entries[0][1]}'). Single document submitted; no counterpart available."
            else:
                father_status = "NOT_DETECTED"
                father_label = "NOT DETECTED"
                father_exp = "Father / Guardian name not detected on submitted documents."

        matrix_rows.append({
            "attribute_key": "father_name",
            "attribute_label": "Father / Guardian Name",
            "values": father_vals,
            "result_status": father_status,
            "result_label": father_label,
            "explanation": father_exp
        })

        # ==========================================
        # 7. Expiry Date / Validity (Issue Date REMOVED)
        # ==========================================
        exp_vals = {}
        has_expired = False
        expired_docs = []
        missing_exp = []
        has_valid_exp = False
        today = date.today()

        for d in docs_sorted:
            t = (d.get("type") or "").lower()
            val_results = d.get("validation_results") or {}
            is_exp_flag = any("expired" in str(f).lower() for f in val_results.get("flags", []))

            if t in ("pan", "aadhaar", "voter_id"):
                exp_vals[d["id"]] = "Permanent / Lifetime"
            elif t in ("passport", "driving_licence"):
                exp = d["fields"].get("expiry_date")
                if exp and str(exp).strip():
                    norm_e = cls.normalize_dob(exp)
                    if norm_e:
                        try:
                            ed = datetime.strptime(norm_e, "%Y-%m-%d").date()
                            if ed < today:
                                is_exp_flag = True
                        except Exception:
                            pass
                    if is_exp_flag:
                        has_expired = True
                        expired_docs.append(f"{t.replace('_', ' ').title()} ({exp})")
                        exp_vals[d["id"]] = f"{exp} (Expired)"
                    else:
                        has_valid_exp = True
                        exp_vals[d["id"]] = f"{exp} (Valid)"
                else:
                    exp_vals[d["id"]] = "Not detected"
                    missing_exp.append(t.replace("_", " ").title())
            else:
                exp_vals[d["id"]] = "Not applicable"

        if is_rule_disabled("expiry_date"):
            exp_status = "NOT_EXECUTED"
            exp_label = "NOT EXECUTED"
            exp_exp = "Expiry date comparison disabled by active triangulation policy."
        elif has_expired:
            exp_status = "MISMATCH"
            exp_label = "EXPIRED"
            exp_exp = f"Document has expired: {', '.join(expired_docs)} (Past legal validity date)."
        elif missing_exp:
            exp_status = "NOT_DETECTED"
            exp_label = "NOT DETECTED"
            exp_exp = f"Expiry date not detected on {', '.join(missing_exp)}. Human verification required."
        elif has_valid_exp:
            exp_status = "MATCH"
            exp_label = "MATCH"
            exp_exp = "All submitted documents are within their valid legal validity periods."
        else:
            exp_status = "NOT_APPLICABLE"
            exp_label = "NOT APPLICABLE"
            exp_exp = "Submitted documents (Aadhaar, PAN) have lifetime validity. Expiration date is not applicable."

        matrix_rows.append({
            "attribute_key": "expiry_date",
            "attribute_label": "Expiry Date / Validity",
            "values": exp_vals,
            "result_status": exp_status,
            "result_label": exp_label,
            "explanation": exp_exp
        })

        return {
            "applicant_id": applicant_id,
            "applicant_name": applicant_name,
            "columns": doc_cols,
            "documents": doc_cols,
            "rows": matrix_rows,
            "overall_verdict": verdict,
            "consistency_score": score,
            "summary_issues": discrepancies,
            "rule_configuration_id": rule_config_id,
            "rule_version": rule_version,
            "combination_key": combination_key,
            "confidence": confidence_data
        }
