"""FOMS Brain C3 — Reusable Block Library API.

Blueprint: designer_blocks_bp
URL prefix: /api/designer/blocks

Endpoints:
  GET    /api/designer/blocks/                  목록 조회 (approved 기본, include_drafts 옵션)
  POST   /api/designer/blocks/save              컴포넌트로부터 블록 저장
  GET    /api/designer/blocks/<id>              단일 블록 조회
  POST   /api/designer/blocks/<id>/instantiate  블록 인스턴스화 (approved 블록만 허용)
  POST   /api/designer/blocks/<id>/approve      블록 승인 (draft → approved)

모든 엔드포인트: @login_required, 응답 {success, data, error}
"""

from __future__ import annotations

import logging

from flask import Blueprint, request, jsonify

from foms.web.auth import login_required
from foms.api.designer.security import require_designer_write

logger = logging.getLogger(__name__)

designer_blocks_bp = Blueprint(
    "designer_blocks",
    __name__,
    url_prefix="/api/designer/blocks",
)


@designer_blocks_bp.route("/", methods=["GET"])
@login_required
def list_blocks_route():
    """GET /api/designer/blocks/ — 재사용 블록 목록 조회.

    Query params:
        category (str): panel | module | assembly | hardware | other
        tags (str): 쉼표 구분 태그 문자열 (예: "상단,하단")
        include_drafts (str): "true"이면 draft 블록도 포함 (리뷰 UI 전용)
        limit (int): 최대 반환 건수 (기본 50, 최대 100)

    Returns:
        {success, data: {blocks, total}, error}
    """
    category = request.args.get("category") or None
    tags_raw = request.args.get("tags") or None
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else None
    include_drafts_raw = request.args.get("include_drafts", "false").lower()
    include_drafts = include_drafts_raw == "true"
    limit = min(int(request.args.get("limit", 50)), 100)

    try:
        from foms.services.designer.block_library import list_blocks
        blocks = list_blocks(
            category=category,
            tags=tags,
            include_drafts=include_drafts,
            limit=limit,
        )
        return jsonify({"success": True, "data": {"blocks": blocks, "total": len(blocks)}, "error": None})
    except Exception as exc:
        logger.error("[BLOCKS API] list failed: %s", exc)
        return jsonify({"success": False, "data": None, "error": str(exc)}), 500


@designer_blocks_bp.route("/", methods=["POST"])
@designer_blocks_bp.route("/save", methods=["POST"])
@login_required
@require_designer_write
def save_block_route():
    """POST /api/designer/blocks/save — 컴포넌트로부터 재사용 블록 저장.

    Request JSON:
        components (list[dict]): 컴포넌트 dict 목록 (필수)
        label_ko (str): 한국어 레이블 (필수)
        category (str): panel | module | assembly | hardware | other (기본 "panel")
        block_key (str|null): 고유 키. null이면 자동 생성
        tags (list[str]): 태그 목록
        source_design_case_id (int|null): 기원 디자인 케이스 ID
        parameters (dict): 조정 가능 파라미터
        auto_generated (bool): AI 생성 여부 (기본 false)

    Returns:
        {success, data: {id, block_key, label_ko, category, status, created_at}, error}
    """
    body = request.get_json(silent=True) or {}

    components = body.get("components")
    if components is None:
        components = body.get("component_dicts")
    geometry_json = body.get("geometry_json")
    label_ko = body.get("label_ko", "").strip()

    if geometry_json is None and (not components or not isinstance(components, list)):
        return jsonify({"success": False, "data": None, "error": "components 또는 geometry_json이 필요합니다."}), 400
    if not label_ko:
        return jsonify({"success": False, "data": None, "error": "label_ko가 필요합니다."}), 400

    category = body.get("category", "panel")
    block_key = body.get("block_key") or None
    tags = body.get("tags") or []
    source_design_case_id = body.get("source_design_case_id")
    parameters = body.get("parameters") or body.get("parameters_json") or {}
    auto_generated = bool(body.get("auto_generated", False))

    # 로그인 사용자 ID 추출 (g.current_user는 before_request에서 설정됨)
    from flask import g, session
    user = getattr(g, "current_user", None)
    created_by_user_id = user.id if user else session.get("user_id")

    try:
        from foms.services.designer.block_library import save_block_from_components
        result = save_block_from_components(
            component_dicts=components or [],
            label_ko=label_ko,
            category=category,
            block_key=block_key,
            tags=tags,
            created_by_user_id=created_by_user_id,
            source_design_case_id=source_design_case_id,
            parameters=parameters,
            auto_generated=auto_generated,
            geometry_json=geometry_json,
        )
        return jsonify({"success": True, "data": result, "error": None}), 201
    except ValueError as exc:
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400
    except Exception as exc:
        logger.error("[BLOCKS API] save failed: %s", exc)
        return jsonify({"success": False, "data": None, "error": str(exc)}), 500


@designer_blocks_bp.route("/<int:block_id>", methods=["GET"])
@login_required
def get_block_route(block_id: int):
    """GET /api/designer/blocks/<id> — 단일 블록 상세 조회.

    Args:
        block_id: URL 경로 내 블록 ID.

    Returns:
        {success, data: 블록 dict, error}
    """
    try:
        from foms.services.designer.block_library import get_block
        block = get_block(block_id)
        if block is None:
            return jsonify({"success": False, "data": None, "error": f"블록 ID {block_id}를 찾을 수 없습니다."}), 404
        return jsonify({"success": True, "data": block, "error": None})
    except Exception as exc:
        logger.error("[BLOCKS API] get_block(%d) failed: %s", block_id, exc)
        return jsonify({"success": False, "data": None, "error": str(exc)}), 500


@designer_blocks_bp.route("/<int:block_id>/instantiate", methods=["POST"])
@login_required
@require_designer_write
def instantiate_block_route(block_id: int):
    """POST /api/designer/blocks/<id>/instantiate — 블록 인스턴스화.

    approved 블록만 허용. RAG/active UI 정책 준수.

    Request JSON:
        at_position (dict|null): {x, y, z} 위치. null이면 {0,0,0}
        scale (float): 스케일 배율 (기본 1.0)

    Returns:
        {success, data: 컴포넌트 dict, error}
    """
    body = request.get_json(silent=True) or {}
    at_position = body.get("at_position") or None
    scale = float(body.get("scale", 1.0))

    try:
        from foms.services.designer.block_library import instantiate_block
        component = instantiate_block(block_id=block_id, at_position=at_position, scale=scale)
        return jsonify({"success": True, "data": component, "error": None})
    except ValueError as exc:
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400
    except Exception as exc:
        logger.error("[BLOCKS API] instantiate(%d) failed: %s", block_id, exc)
        return jsonify({"success": False, "data": None, "error": str(exc)}), 500


@designer_blocks_bp.route("/<int:block_id>/approve", methods=["POST"])
@login_required
@require_designer_write
def approve_block_route(block_id: int):
    """POST /api/designer/blocks/<id>/approve — 블록 승인 (draft → approved).

    AI MUST NOT call this endpoint. 반드시 사람이 UI를 통해 호출.

    Returns:
        {success, data: 갱신된 블록 dict, error}
    """
    from flask import g, session
    user = getattr(g, "current_user", None)
    approved_by_user_id = user.id if user else session.get("user_id")

    try:
        from foms.services.designer.block_library import approve_block
        block = approve_block(block_id=block_id, approved_by_user_id=approved_by_user_id)
        return jsonify({"success": True, "data": block, "error": None})
    except ValueError as exc:
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400
    except Exception as exc:
        logger.error("[BLOCKS API] approve(%d) failed: %s", block_id, exc)
        return jsonify({"success": False, "data": None, "error": str(exc)}), 500
