"""FOMS Brain C7/C8 — Component Explanation API.

Endpoints:
  POST /api/designer/explanations                         — 설명 저장 (draft)
  GET  /api/designer/explanations/search                  — 텍스트 검색
  GET  /api/designer/explanations/by-component/<id>       — 컴포넌트별 목록
  POST /api/designer/explanations/<id>/approve            — draft → approved

RAG 계약:
  approved 상태의 설명만 C9 RAG 컨텍스트에 진입한다.
  search 엔드포인트의 approved_only=true(기본값)가 이 계약의 API 진입점이다.
"""

from __future__ import annotations

import logging

from flask import Blueprint, request, jsonify

from foms.web.auth import login_required

logger = logging.getLogger(__name__)

explanations_bp = Blueprint(
    "designer_explanations",
    __name__,
    url_prefix="/api/designer/explanations",
)


# ──────────────────────────────────────────────────────────
# POST /api/designer/explanations
# ──────────────────────────────────────────────────────────

@explanations_bp.route("", methods=["POST"])
@login_required
def create_explanation():
    """설명 저장 (status=draft).

    Body (JSON):
        component_id_in_graph (str, required): 그래프 내 컴포넌트 ID.
        explanation_text (str, required): 설명 텍스트.
        design_case_id (int, optional): 연결 디자인 케이스 ID.
        rationale_category (str, optional): constraint/preference/customer_request/codified_rule/other.
        confidence (float, optional): 0.0–1.0, 기본값 1.0.

    Returns:
        JSON: {success, data: {id, component_id_in_graph, status, created_at, ...}, error}
    """
    try:
        body = request.get_json(silent=True) or {}

        component_id_in_graph = body.get("component_id_in_graph", "").strip()
        explanation_text = body.get("explanation_text", "").strip()

        if not component_id_in_graph:
            return jsonify({"success": False, "error": "component_id_in_graph is required", "data": None}), 400
        if not explanation_text:
            return jsonify({"success": False, "error": "explanation_text is required", "data": None}), 400

        design_case_id = body.get("design_case_id")
        rationale_category = body.get("rationale_category", "other")
        confidence = float(body.get("confidence", 1.0))

        # created_by_user_id는 g.user에서 가져옴 (login_required 보장)
        from flask import g
        created_by_user_id = getattr(g, "user_id", None) or getattr(getattr(g, "user", None), "id", None)

        from foms.services.designer.explanation_service import save_explanation
        result = save_explanation(
            component_id_in_graph=component_id_in_graph,
            explanation_text=explanation_text,
            design_case_id=design_case_id,
            rationale_category=rationale_category,
            confidence=confidence,
            created_by_user_id=created_by_user_id,
        )
        return jsonify({"success": True, "data": result, "error": None}), 201

    except ValueError as exc:
        logger.warning("[EXPLANATION API] create validation error: %s", exc)
        return jsonify({"success": False, "error": str(exc), "data": None}), 400
    except Exception as exc:
        logger.error("[EXPLANATION API] create failed: %s", exc)
        return jsonify({"success": False, "error": str(exc), "data": None}), 500


# ──────────────────────────────────────────────────────────
# GET /api/designer/explanations/search
# ──────────────────────────────────────────────────────────

@explanations_bp.route("/search", methods=["GET"])
@login_required
def search_explanations_endpoint():
    """텍스트 기반 설명 검색.

    RAG 계약: approved_only=true(기본값)일 때만 C9 RAG 컨텍스트 적합 결과 반환.
    draft 설명은 approved_only=false를 명시해야만 포함된다.

    Query params:
        q (str): 검색 쿼리 (필수).
        top_k (int): 최대 결과 수, 기본값 10.
        approved_only (bool): true(기본)면 approved 상태만, false면 draft 포함.

    Returns:
        JSON: {success, data: {results: [...], count: int, approved_only: bool}, error}
    """
    try:
        query = request.args.get("q", "").strip()
        if not query:
            return jsonify({"success": False, "error": "q parameter is required", "data": None}), 400

        top_k = int(request.args.get("top_k", 10))
        top_k = max(1, min(top_k, 100))  # 1~100 범위 제한

        # approved_only 기본값 True — RAG 계약 핵심
        approved_only_raw = request.args.get("approved_only", "true").lower()
        approved_only = approved_only_raw not in ("false", "0", "no")

        from foms.services.designer.explanation_service import search_explanations
        results = search_explanations(query=query, top_k=top_k, approved_only=approved_only)

        return jsonify({
            "success": True,
            "data": {
                "results": results,
                "count": len(results),
                "approved_only": approved_only,
            },
            "error": None,
        })

    except Exception as exc:
        logger.error("[EXPLANATION API] search failed: %s", exc)
        return jsonify({"success": False, "error": str(exc), "data": None}), 500


# ──────────────────────────────────────────────────────────
# GET /api/designer/explanations/by-component/<component_id>
# ──────────────────────────────────────────────────────────

@explanations_bp.route("/by-component/<path:component_id>", methods=["GET"])
@login_required
def list_by_component(component_id: str):
    """컴포넌트별 설명 목록 조회.

    Args (URL):
        component_id: 그래프 내 컴포넌트 식별자 (슬래시 포함 가능).

    Query params:
        include_drafts (bool): false(기본)면 approved만, true면 draft 포함.

    Returns:
        JSON: {success, data: {component_id_in_graph, results: [...], count: int}, error}
    """
    try:
        include_drafts_raw = request.args.get("include_drafts", "false").lower()
        include_drafts = include_drafts_raw in ("true", "1", "yes")

        from foms.services.designer.explanation_service import list_explanations_by_component
        results = list_explanations_by_component(
            component_id_in_graph=component_id,
            include_drafts=include_drafts,
        )

        return jsonify({
            "success": True,
            "data": {
                "component_id_in_graph": component_id,
                "results": results,
                "count": len(results),
            },
            "error": None,
        })

    except Exception as exc:
        logger.error("[EXPLANATION API] list_by_component failed: %s", exc)
        return jsonify({"success": False, "error": str(exc), "data": None}), 500


# ──────────────────────────────────────────────────────────
# POST /api/designer/explanations/<id>/approve
# ──────────────────────────────────────────────────────────

@explanations_bp.route("/<int:explanation_id>/approve", methods=["POST"])
@login_required
def approve_explanation_endpoint(explanation_id: int):
    """설명 승인 (draft → approved).

    approved 상태 전환 후 C9 RAG 컨텍스트 진입이 허용된다.
    AI는 이 엔드포인트를 직접 호출하면 안 됨; 사람이 검토 후 호출.

    Args (URL):
        explanation_id: 승인할 설명 레코드 ID.

    Returns:
        JSON: {success, data: {id, status, approved_at, ...}, error}
    """
    try:
        from flask import g
        approved_by_user_id = getattr(g, "user_id", None) or getattr(getattr(g, "user", None), "id", None)

        from foms.services.designer.explanation_service import approve_explanation
        result = approve_explanation(
            explanation_id=explanation_id,
            approved_by_user_id=approved_by_user_id,
        )
        return jsonify({"success": True, "data": result, "error": None})

    except ValueError as exc:
        logger.warning("[EXPLANATION API] approve validation error: %s", exc)
        return jsonify({"success": False, "error": str(exc), "data": None}), 400
    except Exception as exc:
        logger.error("[EXPLANATION API] approve failed: %s", exc)
        return jsonify({"success": False, "error": str(exc), "data": None}), 500
