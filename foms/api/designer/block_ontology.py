"""FOMS Brain C6 — Block Ontology API.

Endpoints:
  POST /api/designer/ontology/relations/propose
  GET  /api/designer/ontology/relations
  POST /api/designer/ontology/relations/<id>/approve
  POST /api/designer/ontology/relations/<id>/reject
"""

from __future__ import annotations

import logging

from flask import Blueprint, request, jsonify

from foms.web.auth import login_required

logger = logging.getLogger(__name__)

block_ontology_bp = Blueprint(
    "designer_block_ontology",
    __name__,
    url_prefix="/api/designer/ontology",
)


@block_ontology_bp.route("/relations/propose", methods=["POST"])
@login_required
def propose_relations():
    """POST /api/designer/ontology/relations/propose — 관계 후보 자동 생성.

    Request JSON (모두 optional):
        ontology_version_id (int): 귀속 버전 ID. 생략 시 최신 draft 사용.
        min_evidence (int): 최소 증거 케이스 수 (기본 3).

    Returns:
        {success, data: {created_ids, count}, error}
    """
    from foms.services.designer.block_ontology_service import propose_ontology_relations

    body = request.get_json(silent=True) or {}
    ontology_version_id: int | None = body.get("ontology_version_id")
    min_evidence: int = int(body.get("min_evidence", 3))

    try:
        created_ids = propose_ontology_relations(
            ontology_version_id=ontology_version_id,
            min_evidence=min_evidence,
        )
        return jsonify({
            "success": True,
            "data": {"created_ids": created_ids, "count": len(created_ids)},
            "error": None,
        })
    except Exception as exc:
        logger.error("[BLOCK_ONTOLOGY API] propose failed: %s", exc)
        return jsonify({
            "success": False,
            "data": None,
            "error": {"code": "PROPOSE_ERROR", "message": str(exc)},
        }), 500


@block_ontology_bp.route("/relations", methods=["GET"])
@login_required
def get_relations():
    """GET /api/designer/ontology/relations — 관계 목록 조회.

    Query params (모두 optional):
        ontology_version_id (int): 버전 필터.
        status (str): 상태 필터 (candidate|approved|rejected|promoted).
        from_block_key (str): 출발 블록 키 필터.

    Returns:
        {success, data: {relations, count}, error}
    """
    from foms.services.designer.block_ontology_service import list_relations

    ontology_version_id_str = request.args.get("ontology_version_id")
    ontology_version_id = int(ontology_version_id_str) if ontology_version_id_str else None
    status = request.args.get("status") or None
    from_block_key = request.args.get("from_block_key") or None

    try:
        relations = list_relations(
            ontology_version_id=ontology_version_id,
            status=status,
            from_block_key=from_block_key,
        )
        return jsonify({
            "success": True,
            "data": {"relations": relations, "count": len(relations)},
            "error": None,
        })
    except Exception as exc:
        logger.error("[BLOCK_ONTOLOGY API] list failed: %s", exc)
        return jsonify({
            "success": False,
            "data": None,
            "error": {"code": "LIST_ERROR", "message": str(exc)},
        }), 500


@block_ontology_bp.route("/relations/<int:relation_id>/approve", methods=["POST"])
@login_required
def approve_relation_endpoint(relation_id: int):
    """POST /api/designer/ontology/relations/<id>/approve — 관계 승인.

    Args:
        relation_id: URL 경로 파라미터.

    Request JSON (optional):
        approved_by_user_id (int): 승인 사용자 ID. 생략 시 None.

    Returns:
        {success, data: relation_dict, error}
    """
    from foms.services.designer.block_ontology_service import approve_relation

    body = request.get_json(silent=True) or {}
    approved_by_user_id: int | None = body.get("approved_by_user_id")

    try:
        relation = approve_relation(
            relation_id=relation_id,
            approved_by_user_id=approved_by_user_id,
        )
        return jsonify({"success": True, "data": relation, "error": None})
    except ValueError as exc:
        return jsonify({
            "success": False,
            "data": None,
            "error": {"code": "APPROVE_REJECTED", "message": str(exc)},
        }), 400
    except Exception as exc:
        logger.error("[BLOCK_ONTOLOGY API] approve id=%d failed: %s", relation_id, exc)
        return jsonify({
            "success": False,
            "data": None,
            "error": {"code": "APPROVE_ERROR", "message": str(exc)},
        }), 500


@block_ontology_bp.route("/relations/<int:relation_id>/reject", methods=["POST"])
@login_required
def reject_relation_endpoint(relation_id: int):
    """POST /api/designer/ontology/relations/<id>/reject — 관계 거부.

    Args:
        relation_id: URL 경로 파라미터.

    Request JSON (optional):
        reason (str): 거부 사유.

    Returns:
        {success, data: {id, status}, error}
    """
    from db import db_session
    from foms.persistence.designer.models import DesignerBlockOntologyRelation

    body = request.get_json(silent=True) or {}
    reason: str = body.get("reason", "")

    try:
        relation = db_session.get(DesignerBlockOntologyRelation, relation_id)
        if relation is None:
            return jsonify({
                "success": False,
                "data": None,
                "error": {"code": "NOT_FOUND", "message": f"Relation id={relation_id} not found."},
            }), 404

        if relation.status in ("approved", "rejected"):
            return jsonify({
                "success": False,
                "data": None,
                "error": {
                    "code": "INVALID_STATUS",
                    "message": f"Relation is already '{relation.status}'.",
                },
            }), 400

        import copy
        from sqlalchemy.orm.attributes import flag_modified

        new_report = copy.deepcopy(relation.replay_report_json or {})
        if reason:
            new_report["reject_reason"] = reason
        relation.replay_report_json = new_report
        flag_modified(relation, "replay_report_json")

        relation.status = "rejected"
        db_session.commit()

        logger.info("[BLOCK_ONTOLOGY API] rejected relation id=%d", relation_id)
        return jsonify({
            "success": True,
            "data": {"id": relation.id, "status": relation.status},
            "error": None,
        })
    except Exception as exc:
        logger.error("[BLOCK_ONTOLOGY API] reject id=%d failed: %s", relation_id, exc)
        return jsonify({
            "success": False,
            "data": None,
            "error": {"code": "REJECT_ERROR", "message": str(exc)},
        }), 500
