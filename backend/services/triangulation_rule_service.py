import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from backend.database.db import get_db_connection

logger = logging.getLogger("veridoc.triangulation_rules")

SEMANTIC_CONCEPTS = {
    "name": {
        "keys": ["name", "customer_name", "full_name", "applicant_name", "employee_name", "account_holder_name", "holder_name"],
        "label": "Customer / Employee Name",
        "recommendation": "COMPARE",
        "normalization": "normalized_text",
        "explanation": "Primary identity cross-reference. Essential for customer identity verification.",
        "default_enabled": True
    },
    "dob": {
        "keys": ["dob", "date_of_birth", "birth_date"],
        "label": "Date of Birth",
        "recommendation": "COMPARE",
        "normalization": "date_iso",
        "explanation": "Critical biographical anchor. Standardized ISO YYYY-MM-DD cross-match.",
        "default_enabled": True
    },
    "gender": {
        "keys": ["gender", "sex"],
        "label": "Gender",
        "recommendation": "COMPARE",
        "normalization": "exact",
        "explanation": "Standard demographic cross-check (MALE / FEMALE / OTHER).",
        "default_enabled": True
    },
    "address": {
        "keys": ["address", "permanent_address", "current_address", "residence_address", "billing_address"],
        "label": "Residential / Billing Address",
        "recommendation": "CONDITIONAL",
        "normalization": "fuzzy_text",
        "explanation": "Address may vary across permanent and correspondence residences. Flagged for review if score < 60%.",
        "default_enabled": True
    },
    "father_name": {
        "keys": ["father_name", "father_husband_name", "parent_name"],
        "label": "Father's / Guardian's Name",
        "recommendation": "CONDITIONAL",
        "normalization": "normalized_text",
        "explanation": "Parental cross-reference. Useful secondary verification indicator.",
        "default_enabled": True
    },
    "pan_number": {
        "keys": ["pan_number", "pan", "permanent_account_number"],
        "label": "PAN Number",
        "recommendation": "COMPARE",
        "normalization": "exact",
        "explanation": "Official Tax Identification Number. Must match exactly across tax documents.",
        "default_enabled": True
    },
    "aadhaar_number": {
        "keys": ["aadhaar_number", "aadhaar", "uid", "aadhaar_no"],
        "label": "Aadhaar UID Number",
        "recommendation": "COMPARE",
        "normalization": "exact",
        "explanation": "National biometric identity number. High precision match.",
        "default_enabled": True
    },
    "passport_number": {
        "keys": ["passport_number", "passport_no"],
        "label": "Passport Number",
        "recommendation": "COMPARE",
        "normalization": "exact",
        "explanation": "Travel document identification number.",
        "default_enabled": True
    },
    "employer_name": {
        "keys": ["employer_name", "company_name", "organization", "deductor_name"],
        "label": "Employer / Deductor Name",
        "recommendation": "COMPARE",
        "normalization": "normalized_text",
        "explanation": "Corporate entity verification across payslips, bank statements, and tax forms.",
        "default_enabled": True
    },
    "account_number": {
        "keys": ["account_number", "bank_account_number", "acc_no"],
        "label": "Bank Account Number",
        "recommendation": "COMPARE",
        "normalization": "exact",
        "explanation": "Disbursement and salary credit account cross-verification.",
        "default_enabled": True
    },
    "salary_amount": {
        "keys": ["gross_salary", "net_salary", "total_salary", "gross_amount", "salary_credited"],
        "label": "Gross / Net Salary Amount",
        "recommendation": "CONDITIONAL",
        "normalization": "currency",
        "explanation": "Income verification between salary slip and bank statement credit amount.",
        "default_enabled": True
    }
}


def get_canonical_combination_key(doc_types: List[str]) -> str:
    """Produce a deterministic, alphabetically sorted combination key (e.g. 'aadhaar+pan')."""
    clean_types = sorted(list({dt.strip().lower() for dt in doc_types if dt and dt.strip()}))
    return "+".join(clean_types)


def parse_combination_key(combination_key: str) -> List[str]:
    """Parse combination key into individual document types."""
    return [dt.strip().lower() for dt in combination_key.split("+") if dt.strip()]


def _row_val(row, key, index=0):
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except Exception:
        try:
            return row[index]
        except Exception:
            return None


class TriangulationRuleService:
    """
    Manages document combination comparison rules, AI-assisted attribute discovery,
    rule versioning, and policy enforcement across VeriDoc AI.
    """

    @classmethod
    def get_registered_doc_types(cls) -> List[Dict[str, Any]]:
        """Retrieve all active registered document types from database."""
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT type_key, display_name, category, description 
                FROM document_type_definitions 
                WHERE (is_active = TRUE OR is_active = 1)
                ORDER BY display_name ASC
            """)
            rows = cur.fetchall()
            return [
                {
                    "type_key": r[0],
                    "display_name": r[1],
                    "category": r[2],
                    "description": r[3]
                }
                for r in rows
            ]
        finally:
            conn.close()

    @classmethod
    def get_doc_type_attributes(cls, doc_type_key: str) -> List[Dict[str, Any]]:
        """Retrieve defined schema attributes for a given document type."""
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT s.attribute_definitions 
                FROM document_schemas s
                JOIN document_type_definitions dt ON s.document_type_id = dt.id
                WHERE dt.type_key = ? AND (s.is_active = TRUE OR s.is_active = 1)
                ORDER BY s.version DESC
                LIMIT 1
            """, (doc_type_key.lower(),))
            row = cur.fetchone()
            attr_def = _row_val(row, "attribute_definitions", 0)
            if not row or not attr_def:
                baseline_attributes = {
                    "pan": [
                        {"key": "name", "label": "Name", "data_type": "string"},
                        {"key": "dob", "label": "Date of Birth", "data_type": "date"},
                        {"key": "father_name", "label": "Father's Name", "data_type": "string"},
                        {"key": "pan_number", "label": "PAN Number", "data_type": "string"}
                    ],
                    "aadhaar": [
                        {"key": "name", "label": "Name", "data_type": "string"},
                        {"key": "dob", "label": "Date of Birth", "data_type": "date"},
                        {"key": "gender", "label": "Gender", "data_type": "string"},
                        {"key": "address", "label": "Address", "data_type": "string"},
                        {"key": "aadhaar_number", "label": "Aadhaar Number", "data_type": "string"}
                    ],
                    "passport": [
                        {"key": "name", "label": "Name", "data_type": "string"},
                        {"key": "dob", "label": "Date of Birth", "data_type": "date"},
                        {"key": "gender", "label": "Gender", "data_type": "string"},
                        {"key": "passport_number", "label": "Passport Number", "data_type": "string"}
                    ],
                    "driving_licence": [
                        {"key": "name", "label": "Name", "data_type": "string"},
                        {"key": "dob", "label": "Date of Birth", "data_type": "date"},
                        {"key": "gender", "label": "Gender", "data_type": "string"},
                        {"key": "dl_number", "label": "Driving Licence Number", "data_type": "string"},
                        {"key": "address", "label": "Address", "data_type": "string"}
                    ],
                    "voter_id": [
                        {"key": "name", "label": "Name", "data_type": "string"},
                        {"key": "dob", "label": "Date of Birth", "data_type": "date"},
                        {"key": "gender", "label": "Gender", "data_type": "string"},
                        {"key": "father_name", "label": "Father's Name", "data_type": "string"},
                        {"key": "voter_id_number", "label": "Voter ID Number", "data_type": "string"}
                    ],
                    "salary_slip": [
                        {"key": "employee_name", "label": "Employee Name", "data_type": "string"},
                        {"key": "employer_name", "label": "Employer Name", "data_type": "string"},
                        {"key": "gross_salary", "label": "Gross Salary", "data_type": "number"},
                        {"key": "account_number", "label": "Account Number", "data_type": "string"}
                    ],
                    "bank_statement": [
                        {"key": "account_holder_name", "label": "Account Holder Name", "data_type": "string"},
                        {"key": "account_number", "label": "Account Number", "data_type": "string"},
                        {"key": "salary_credited", "label": "Salary Credited", "data_type": "number"}
                    ],
                    "tax_form_16": [
                        {"key": "employee_name", "label": "Employee Name", "data_type": "string"},
                        {"key": "employer_name", "label": "Employer Name", "data_type": "string"},
                        {"key": "pan_number", "label": "PAN Number", "data_type": "string"},
                        {"key": "gross_salary", "label": "Gross Salary", "data_type": "number"}
                    ]
                }
                return baseline_attributes.get(doc_type_key.lower(), [])
            attrs = json.loads(attr_def) if isinstance(attr_def, str) else attr_def
            result = []
            for a in attrs:
                key = a.get("attribute_key") or a.get("key")
                if key:
                    result.append({
                        "key": key,
                        "label": a.get("display_label") or a.get("label") or key.replace("_", " ").title(),
                        "data_type": a.get("data_type") or "string",
                        "sample_value": a.get("sample_value") or "",
                        "anchor_phrase": a.get("anchor_phrase") or ""
                    })
            return result
        finally:
            conn.close()

    @classmethod
    def discover_rules_for_combination(cls, doc_types: List[str]) -> Dict[str, Any]:
        """
        AI-assisted rule discovery: inspects schemas of the specified document types,
        identifies shared attributes, recommends comparison policies with justifications.
        """
        canonical_key = get_canonical_combination_key(doc_types)
        parsed_types = parse_combination_key(canonical_key)

        type_attrs: Dict[str, List[Dict[str, Any]]] = {}
        for dt in parsed_types:
            type_attrs[dt] = cls.get_doc_type_attributes(dt)

        rules: List[Dict[str, Any]] = []
        covered_attributes = set()

        # Step 1: Detect semantic concept matches across pairs of document types
        for concept_name, concept_cfg in SEMANTIC_CONCEPTS.items():
            matching_by_type: Dict[str, Dict[str, Any]] = {}
            for dt, attrs in type_attrs.items():
                for a in attrs:
                    if a["key"].lower() in concept_cfg["keys"]:
                        matching_by_type[dt] = a
                        break

            # If present in at least 2 document types, recommend cross-comparison
            if len(matching_by_type) >= 2:
                # Pick the primary source and target types
                types_present = list(matching_by_type.keys())
                source_type = types_present[0]
                target_type = types_present[1]
                source_attr = matching_by_type[source_type]
                target_attr = matching_by_type[target_type]

                rule_id = f"rule_{source_type}_{source_attr['key']}_vs_{target_type}_{target_attr['key']}"
                rules.append({
                    "id": rule_id,
                    "concept": concept_name,
                    "source_doc_type": source_type,
                    "source_attribute": source_attr["key"],
                    "source_label": source_attr["label"],
                    "target_doc_type": target_type,
                    "target_attribute": target_attr["key"],
                    "target_label": target_attr["label"],
                    "participating_types": types_present,
                    "recommendation": concept_cfg["recommendation"],  # COMPARE | CONDITIONAL
                    "explanation": concept_cfg["explanation"],
                    "normalization": concept_cfg["normalization"],
                    "is_enabled": concept_cfg["default_enabled"]
                })
                for dt, a in matching_by_type.items():
                    covered_attributes.add((dt, a["key"]))

        # Step 2: Handle attributes with identical keys that weren't caught in SEMANTIC_CONCEPTS
        for i in range(len(parsed_types)):
            for j in range(i + 1, len(parsed_types)):
                t1, t2 = parsed_types[i], parsed_types[j]
                for a1 in type_attrs.get(t1, []):
                    for a2 in type_attrs.get(t2, []):
                        if (t1, a1["key"]) in covered_attributes and (t2, a2["key"]) in covered_attributes:
                            continue
                        if a1["key"].lower() == a2["key"].lower():
                            rules.append({
                                "id": f"rule_{t1}_{a1['key']}_vs_{t2}_{a2['key']}",
                                "concept": a1["key"],
                                "source_doc_type": t1,
                                "source_attribute": a1["key"],
                                "source_label": a1["label"],
                                "target_doc_type": t2,
                                "target_attribute": a2["key"],
                                "target_label": a2["label"],
                                "participating_types": [t1, t2],
                                "recommendation": "COMPARE",
                                "explanation": f"Identical attribute '{a1['key']}' detected in both documents. Direct comparison enabled.",
                                "normalization": "normalized_text" if a1.get("data_type") == "string" else "exact",
                                "is_enabled": True
                            })
                            covered_attributes.add((t1, a1["key"]))
                            covered_attributes.add((t2, a2["key"]))

        # Step 3: Flag obvious incompatible cross-attribute checks as NOT_RECOMMENDED
        # e.g., PAN number vs Aadhaar number if both exist in combination
        pan_attr = None
        aadhaar_attr = None
        for dt, attrs in type_attrs.items():
            for a in attrs:
                if a["key"] in ("pan_number", "pan"):
                    pan_attr = (dt, a)
                elif a["key"] in ("aadhaar_number", "aadhaar", "uid"):
                    aadhaar_attr = (dt, a)

        if pan_attr and aadhaar_attr:
            rules.append({
                "id": f"rule_incompat_{pan_attr[0]}_{pan_attr[1]['key']}_vs_{aadhaar_attr[0]}_{aadhaar_attr[1]['key']}",
                "concept": "incompatible_identifiers",
                "source_doc_type": pan_attr[0],
                "source_attribute": pan_attr[1]["key"],
                "source_label": pan_attr[1]["label"],
                "target_doc_type": aadhaar_attr[0],
                "target_attribute": aadhaar_attr[1]["key"],
                "target_label": aadhaar_attr[1]["label"],
                "participating_types": [pan_attr[0], aadhaar_attr[0]],
                "recommendation": "NOT_RECOMMENDED",
                "explanation": "Different government identity formats. Cross-comparing PAN with Aadhaar will produce 100% false mismatches.",
                "normalization": "exact",
                "is_enabled": False
            })

        # Step 4: Add single-document attributes (attributes present in only one document)
        for dt, attrs in type_attrs.items():
            for a in attrs:
                if (dt, a["key"]) not in covered_attributes:
                    rules.append({
                        "id": f"rule_single_{dt}_{a['key']}",
                        "concept": "single_document_field",
                        "source_doc_type": dt,
                        "source_attribute": a["key"],
                        "source_label": a["label"],
                        "target_doc_type": "-",
                        "target_attribute": "-",
                        "target_label": "-",
                        "participating_types": [dt],
                        "recommendation": "SINGLE_DOC",
                        "explanation": f"Attribute exists only in {dt.replace('_', ' ').title()}. Recorded for single-document dossier completeness.",
                        "normalization": "exact",
                        "is_enabled": False
                    })

        return {
            "combination_key": canonical_key,
            "document_types": parsed_types,
            "total_rules_discovered": len(rules),
            "rules": rules,
            "discovery_method": "ai_assisted_schema_crossmatch",
            "timestamp": datetime.now().isoformat()
        }

    @classmethod
    def get_or_create_configuration(
        cls,
        combination_key: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        created_by: str = "System"
    ) -> Dict[str, Any]:
        """Fetch existing configuration or initialize a new one."""
        parts = combination_key.split("+") if "+" in combination_key else [p for p in combination_key.split("_") if p]
        canonical_key = get_canonical_combination_key(parts) if len(parts) > 1 else combination_key
        doc_types = parse_combination_key(canonical_key)
        config_id = f"rule_cfg_{canonical_key.replace('+', '_')}"
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT id, combination_key, document_types, name, description, active_version, is_active, created_by, created_at, updated_at
                FROM comparison_rule_configurations
                WHERE combination_key = ? OR id = ?
            """, (canonical_key, config_id))
            row = cur.fetchone()
            if row:
                doc_types_raw = _row_val(row, "document_types", 2)
                return {
                    "id": _row_val(row, "id", 0),
                    "combination_key": _row_val(row, "combination_key", 1),
                    "document_types": json.loads(doc_types_raw) if isinstance(doc_types_raw, str) else doc_types_raw,
                    "name": _row_val(row, "name", 3),
                    "description": _row_val(row, "description", 4),
                    "active_version": _row_val(row, "active_version", 5),
                    "is_active": bool(_row_val(row, "is_active", 6)),
                    "created_by": _row_val(row, "created_by", 7),
                    "created_at": str(_row_val(row, "created_at", 8)),
                    "updated_at": str(_row_val(row, "updated_at", 9))
                }

            # Create default configuration
            config_id = f"rule_cfg_{canonical_key.replace('+', '_')}"
            default_name = name or (" + ".join([dt.replace("_", " ").title() for dt in doc_types]) + " Comparison Policy")
            default_desc = description or f"Authoritative cross-document verification rules for {', '.join(doc_types)}."
            cur.execute("""
                INSERT INTO comparison_rule_configurations (
                    id, combination_key, document_types, name, description, active_version, is_active, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (
                config_id,
                canonical_key,
                json.dumps(doc_types),
                default_name,
                default_desc,
                1,
                True,
                created_by
            ))

            # Automatically run discovery to initialize Version 1
            discovery = cls.discover_rules_for_combination(doc_types)
            cur.execute("""
                INSERT INTO comparison_rule_versions (
                    configuration_id, version, attribute_rules, ai_metadata, published_by, change_summary, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                config_id,
                1,
                json.dumps(discovery["rules"]),
                json.dumps({"discovery_method": "ai_assisted_initial_seeding"}),
                created_by,
                "Initial baseline comparison rules automatically discovered from registered schemas"
            ))
            conn.commit()

            return {
                "id": config_id,
                "combination_key": canonical_key,
                "document_types": doc_types,
                "name": default_name,
                "description": default_desc,
                "active_version": 1,
                "is_active": True,
                "created_by": created_by,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
        finally:
            conn.close()

    @classmethod
    def get_active_rules(cls, combination_key: str) -> Dict[str, Any]:
        """Retrieve the currently active rule version and rules for a document combination."""
        parts = combination_key.split("+") if "+" in combination_key else [p for p in combination_key.split("_") if p]
        canonical_key = get_canonical_combination_key(parts) if len(parts) > 1 else combination_key
        config = cls.get_or_create_configuration(canonical_key)
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT version, attribute_rules, ai_metadata, published_by, change_summary, created_at
                FROM comparison_rule_versions
                WHERE configuration_id = ? AND version = ?
            """, (config["id"], config["active_version"]))
            v_row = cur.fetchone()
            if not v_row:
                # Version 1 fallback
                discovery = cls.discover_rules_for_combination(config["document_types"])
                return {
                    "configuration": config,
                    "active_version": 1,
                    "rules": discovery["rules"],
                    "published_by": "System",
                    "change_summary": "Auto-generated default rules",
                    "created_at": datetime.now().isoformat()
                }

            raw_rules = _row_val(v_row, "attribute_rules", 1)
            raw_meta = _row_val(v_row, "ai_metadata", 2)
            rules = json.loads(raw_rules) if isinstance(raw_rules, str) else raw_rules
            return {
                "configuration": config,
                "active_version": _row_val(v_row, "version", 0),
                "rules": rules,
                "ai_metadata": json.loads(raw_meta) if raw_meta and isinstance(raw_meta, str) else (raw_meta or {}),
                "published_by": _row_val(v_row, "published_by", 3),
                "change_summary": _row_val(v_row, "change_summary", 4),
                "created_at": str(_row_val(v_row, "created_at", 5))
            }
        finally:
            conn.close()

    @classmethod
    def save_new_rule_version(
        cls,
        configuration_id: str,
        attribute_rules: List[Dict[str, Any]],
        published_by: str = "Compliance Officer",
        change_summary: str = "Updated comparison rules and normalizations",
        ai_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Save a new version of the rules and make it the active version."""
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT COALESCE(MAX(version), 0) FROM comparison_rule_versions WHERE configuration_id = ?", (configuration_id,))
            max_v = cur.fetchone()[0] or 0
            new_v = max_v + 1

            cur.execute("""
                INSERT INTO comparison_rule_versions (
                    configuration_id, version, attribute_rules, ai_metadata, published_by, change_summary, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                configuration_id,
                new_v,
                json.dumps(attribute_rules),
                json.dumps(ai_metadata or {}),
                published_by,
                change_summary
            ))

            cur.execute("""
                UPDATE comparison_rule_configurations 
                SET active_version = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (new_v, configuration_id))

            conn.commit()
            return {
                "configuration_id": configuration_id,
                "version": new_v,
                "status": "published",
                "rules_count": len(attribute_rules),
                "published_by": published_by,
                "change_summary": change_summary,
                "created_at": datetime.now().isoformat()
            }
        finally:
            conn.close()

    @classmethod
    def list_versions(cls, configuration_id: str) -> List[Dict[str, Any]]:
        """List all version history for a configuration."""
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT version, attribute_rules, published_by, change_summary, created_at
                FROM comparison_rule_versions
                WHERE configuration_id = ?
                ORDER BY version DESC
            """, (configuration_id,))
            rows = cur.fetchall()
            versions = []
            for r in rows:
                rules = json.loads(r[1]) if isinstance(r[1], str) else r[1]
                active_count = sum(1 for rule in rules if rule.get("is_enabled"))
                versions.append({
                    "version": r[0],
                    "total_rules": len(rules),
                    "enabled_rules": active_count,
                    "published_by": r[2],
                    "change_summary": r[3],
                    "created_at": str(r[4])
                })
            return versions
        finally:
            conn.close()

    @classmethod
    def rollback_version(cls, configuration_id: str, target_version: int, user: str = "Admin") -> Dict[str, Any]:
        """Roll back active version to an earlier version."""
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT version FROM comparison_rule_versions WHERE configuration_id = ? AND version = ?", (configuration_id, target_version))
            if not cur.fetchone():
                raise ValueError(f"Version {target_version} does not exist for configuration {configuration_id}")

            cur.execute("""
                UPDATE comparison_rule_configurations
                SET active_version = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (target_version, configuration_id))
            conn.commit()

            return {
                "configuration_id": configuration_id,
                "active_version": target_version,
                "status": "rolled_back",
                "updated_by": user
            }
        finally:
            conn.close()

    @classmethod
    def list_all_configurations(cls) -> List[Dict[str, Any]]:
        """List all registered combinations with their active version details."""
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT c.id, c.combination_key, c.document_types, c.name, c.description, c.active_version, c.updated_at,
                       v.attribute_rules
                FROM comparison_rule_configurations c
                LEFT JOIN comparison_rule_versions v ON c.id = v.configuration_id AND c.active_version = v.version
                ORDER BY c.combination_key ASC
            """)
            rows = cur.fetchall()
            configs = []
            for r in rows:
                rules = []
                if r[7]:
                    try:
                        rules = json.loads(r[7]) if isinstance(r[7], str) else r[7]
                    except Exception:
                        rules = []
                configs.append({
                    "id": r[0],
                    "combination_key": r[1],
                    "document_types": json.loads(r[2]) if isinstance(r[2], str) else r[2],
                    "name": r[3],
                    "description": r[4],
                    "active_version": r[5],
                    "updated_at": str(r[6]),
                    "total_rules": len(rules),
                    "enabled_rules": sum(1 for rule in rules if rule.get("is_enabled"))
                })
            return configs
        finally:
            conn.close()

    @classmethod
    def seed_default_configurations(cls):
        """Seed default comparison policies for standard KYC document combinations."""
        standard_combinations = [
            ("aadhaar+pan", "Aadhaar + PAN Verification Policy", "Standard National Identity Cross-Check"),
            ("aadhaar+passport", "Aadhaar + Passport Verification Policy", "Citizen Passport and Address Triangulation"),
            ("pan+tax_form_16", "PAN + Form 16 Tax Policy", "Income Tax & Employer Cross-Verification"),
            ("bank_statement+salary_slip", "Salary Slip + Bank Statement Policy", "Income Disbursement Verification"),
            ("aadhaar+driving_licence", "Aadhaar + Driving Licence Policy", "Demographic Cross-Verification"),
            ("aadhaar+voter_id", "Aadhaar + Voter ID Policy", "Electoral Cross-Verification"),
            ("pan+salary_slip", "PAN + Salary Slip Policy", "Employee Identity and PAN Cross-Verification"),
        ]

        for combo_key, name, desc in standard_combinations:
            try:
                cls.get_or_create_configuration(combo_key, name=name, description=desc, created_by="System Seeder")
            except Exception as e:
                logger.warning(f"Could not seed default configuration for {combo_key}: {e}")
