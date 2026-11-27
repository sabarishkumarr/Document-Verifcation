import json
import logging
from flask import Blueprint, request, jsonify
from backend.services.triangulation_rule_service import (
    TriangulationRuleService,
    get_canonical_combination_key,
    parse_combination_key
)

logger = logging.getLogger("veridoc.routes.triangulation_rules")

triangulation_rules_bp = Blueprint("triangulation_rules", __name__, url_prefix="/api/triangulation")


@triangulation_rules_bp.route("/combinations", methods=["GET"])
def list_combinations():
    """
    List all document combinations with their active policy versions,
    configured rules counts, and all available registered document types.
    """
    try:
        registered_types = TriangulationRuleService.get_registered_doc_types()
        configurations = TriangulationRuleService.list_all_configurations()

        return jsonify({
            "success": True,
            "registered_document_types": registered_types,
            "combinations": configurations
        }), 200
    except Exception as e:
        logger.error(f"Failed to list combinations: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "message": f"Failed to retrieve comparison configurations: {str(e)}"
        }), 500


@triangulation_rules_bp.route("/combinations/<combination_key>/rules", methods=["GET"])
def get_combination_rules(combination_key: str):
    """
    Retrieve active rule set and configuration details for a given combination key (e.g. 'aadhaar+pan').
    """
    try:
        canonical_key = get_canonical_combination_key(combination_key.split("+"))
        active_rules = TriangulationRuleService.get_active_rules(canonical_key)

        return jsonify({
            "success": True,
            "combination_key": canonical_key,
            "data": active_rules
        }), 200
    except Exception as e:
        logger.error(f"Failed to get rules for {combination_key}: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "message": f"Could not retrieve comparison rules: {str(e)}"
        }), 500


@triangulation_rules_bp.route("/combinations/<combination_key>/discover", methods=["POST"])
def discover_rules(combination_key: str):
    """
    AI-assisted attribute discovery: inspects schemas of the specified document types,
    identifies shared attributes, recommends comparison policies with justifications.
    Does not save a new version until explicitly published.
    """
    try:
        payload = request.get_json(silent=True) or {}
        doc_types = payload.get("document_types")
        if not doc_types:
            doc_types = parse_combination_key(combination_key)

        discovery_result = TriangulationRuleService.discover_rules_for_combination(doc_types)

        return jsonify({
            "success": True,
            "data": discovery_result
        }), 200
    except Exception as e:
        logger.error(f"Failed to discover rules for {combination_key}: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "message": f"Rule discovery failed: {str(e)}"
        }), 500


@triangulation_rules_bp.route("/combinations/<combination_key>/rules", methods=["POST"])
def save_combination_rules(combination_key: str):
    """
    Publish and activate a new version of comparison rules for this combination.
    """
    try:
        data = request.get_json() or {}
        rules = data.get("rules", [])
        published_by = data.get("published_by", "Compliance Officer")
        change_summary = data.get("change_summary", "Updated attribute comparison rules and normalizations")
        ai_metadata = data.get("ai_metadata", {})

        canonical_key = get_canonical_combination_key(combination_key.split("+"))
        config = TriangulationRuleService.get_or_create_configuration(canonical_key)

        saved = TriangulationRuleService.save_new_rule_version(
            configuration_id=config["id"],
            attribute_rules=rules,
            published_by=published_by,
            change_summary=change_summary,
            ai_metadata=ai_metadata
        )

        return jsonify({
            "success": True,
            "message": f"Published Policy Version {saved['version']} successfully.",
            "data": saved
        }), 200
    except Exception as e:
        logger.error(f"Failed to save rules for {combination_key}: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "message": f"Failed to save rules: {str(e)}"
        }), 500


@triangulation_rules_bp.route("/combinations/<combination_key>/versions", methods=["GET"])
def list_combination_versions(combination_key: str):
    """
    List historical policy versions for this combination.
    """
    try:
        canonical_key = get_canonical_combination_key(combination_key.split("+"))
        config = TriangulationRuleService.get_or_create_configuration(canonical_key)
        versions = TriangulationRuleService.list_versions(config["id"])

        return jsonify({
            "success": True,
            "configuration_id": config["id"],
            "combination_key": canonical_key,
            "active_version": config["active_version"],
            "versions": versions
        }), 200
    except Exception as e:
        logger.error(f"Failed to list versions for {combination_key}: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "message": f"Failed to list version history: {str(e)}"
        }), 500


@triangulation_rules_bp.route("/combinations/<combination_key>/rollback", methods=["POST"])
def rollback_combination_version(combination_key: str):
    """
    Roll back active policy to an earlier version.
    """
    try:
        data = request.get_json() or {}
        target_version = data.get("target_version")
        if not target_version:
            return jsonify({
                "success": False,
                "message": "target_version is required"
            }), 400

        canonical_key = get_canonical_combination_key(combination_key.split("+"))
        config = TriangulationRuleService.get_or_create_configuration(canonical_key)
        rolled = TriangulationRuleService.rollback_version(config["id"], int(target_version), user=data.get("user", "Admin"))

        return jsonify({
            "success": True,
            "message": f"Rolled back to Policy Version {target_version}.",
            "data": rolled
        }), 200
    except Exception as e:
        logger.error(f"Failed to rollback version for {combination_key}: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "message": f"Rollback failed: {str(e)}"
        }), 500
