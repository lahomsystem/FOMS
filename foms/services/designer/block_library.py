"""FOMS Brain C3 — Reusable Block Library Service.

Contract:
- save_block_from_components(): only draft status, auto_generated=False for user-saved
- approve_block(): human approval required before status="approved"
- list_blocks(): by default returns only approved blocks
- list_blocks(include_drafts=True): includes draft (for review UI)
- AI-generated blocks: auto_generated=True, status="draft" only
- RAG/active UI: only approved blocks are eligible — do NOT use draft blocks in retrieval
"""

from __future__ import annotations

import copy
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

logger = logging.getLogger(__name__)

_VALID_CATEGORIES = frozenset({"panel", "module", "assembly", "hardware", "other"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _auto_block_key() -> str:
    """UUID prefix (12자) 자동 생성 block_key."""
    return str(uuid.uuid4())[:12]


def _build_geometry_json(component_dicts: list[dict]) -> dict:
    """컴포넌트 목록을 geometry_json 구조로 변환.

    Args:
        component_dicts: 컴포넌트 dict 목록.

    Returns:
        {"schema_version": "v2", "components": [...], "relations": []} 형식의 dict.
    """
    return {
        "schema_version": "v2",
        "components": component_dicts,
        "relations": [],
    }


def _block_to_dict(block: Any) -> dict:
    """DesignerReusableBlock ORM 객체를 직렬화 가능한 dict로 변환.

    Args:
        block: DesignerReusableBlock 인스턴스.

    Returns:
        직렬화 가능한 dict.
    """
    return {
        "id": block.id,
        "block_key": block.block_key,
        "label_ko": block.label_ko,
        "label_en": block.label_en,
        "category": block.category,
        "status": block.status,
        "auto_generated": block.auto_generated,
        "usage_count": block.usage_count,
        "tags": list(block.tags_json or []),
        "geometry_json": copy.deepcopy(block.geometry_json or {}),
        "parameters_json": copy.deepcopy(block.parameters_json or {}),
        "geometry_schema_version": block.geometry_schema_version,
        "source_design_case_id": block.source_design_case_id,
        "created_by_user_id": block.created_by_user_id,
        "approved_by_user_id": block.approved_by_user_id,
        "approved_at": block.approved_at.isoformat() if block.approved_at else None,
        "created_at": block.created_at.isoformat() if block.created_at else None,
        "updated_at": block.updated_at.isoformat() if block.updated_at else None,
    }


# ──────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────


def save_block_from_components(
    component_dicts: list[dict],
    label_ko: str,
    category: str = "panel",
    block_key: str | None = None,
    tags: list[str] | None = None,
    created_by_user_id: int | None = None,
    source_design_case_id: int | None = None,
    parameters: dict | None = None,
    auto_generated: bool = False,
    geometry_json: dict | None = None,
) -> dict:
    """사용자 선택 컴포넌트를 재사용 블록으로 저장 (status=draft).

    AI 자동 생성 블록은 auto_generated=True, status='draft'로만 저장.
    RAG/active UI에서는 approved 블록만 사용 가능.

    Args:
        component_dicts: geometry_json의 components로 저장할 컴포넌트 dict 목록.
        geometry_json: 스케치/커스텀 블록이 이미 구성한 geometry_json. 지정 시
            component_dicts 기반 생성보다 우선한다.
        label_ko: 블록의 한국어 레이블.
        category: "panel" | "module" | "assembly" | "hardware" | "other".
        block_key: 블록 고유 키. None이면 UUID 12자 자동 생성.
        tags: 태그 문자열 목록.
        created_by_user_id: 생성 사용자 ID.
        source_design_case_id: 기원 디자인 케이스 ID.
        parameters: 조정 가능한 파라미터 dict (width_range 등).
        auto_generated: True이면 AI 생성 블록 (승인 전 RAG 사용 금지).

    Returns:
        {id, block_key, label_ko, category, status, created_at} dict.

    Raises:
        ValueError: block_key가 중복되거나 category가 유효하지 않을 때.
    """
    if category not in _VALID_CATEGORIES:
        raise ValueError(f"유효하지 않은 category: {category!r}. 허용값: {sorted(_VALID_CATEGORIES)}")

    resolved_key = block_key or _auto_block_key()

    from db import db_session
    from foms.persistence.designer.models import DesignerReusableBlock

    existing = db_session.query(DesignerReusableBlock).filter_by(block_key=resolved_key).first()
    if existing is not None:
        raise ValueError(f"block_key 중복: {resolved_key!r}")

    geometry = copy.deepcopy(geometry_json) if geometry_json is not None else _build_geometry_json(component_dicts)
    if not isinstance(geometry, dict):
        raise ValueError("geometry_json은 dict여야 합니다.")
    geometry.setdefault("schema_version", "v2")
    if "components" not in geometry:
        geometry["components"] = component_dicts or []
    geometry.setdefault("relations", [])

    block = DesignerReusableBlock(
        block_key=resolved_key,
        label_ko=label_ko,
        category=category,
        geometry_json=geometry,
        parameters_json=parameters or {},
        status="draft",
        auto_generated=auto_generated,
        tags_json=tags or [],
        source_design_case_id=source_design_case_id,
        created_by_user_id=created_by_user_id,
        usage_count=0,
    )
    db_session.add(block)
    db_session.commit()
    db_session.refresh(block)

    logger.info("[BLOCK_LIB] 블록 저장: id=%d key=%s auto_generated=%s", block.id, resolved_key, auto_generated)

    return {
        "id": block.id,
        "block_key": block.block_key,
        "label_ko": block.label_ko,
        "category": block.category,
        "status": block.status,
        "created_at": block.created_at.isoformat() if block.created_at else None,
    }


def list_blocks(
    category: str | None = None,
    tags: list[str] | None = None,
    include_drafts: bool = False,
    limit: int = 50,
) -> list[dict]:
    """재사용 블록 목록 조회.

    기본값(include_drafts=False)은 approved 블록만 반환.
    RAG / active UI는 반드시 include_drafts=False로만 호출할 것.

    Args:
        category: 필터링할 카테고리. None이면 전체.
        tags: 하나라도 일치하는 태그를 가진 블록 필터링 (클라이언트 측 후처리).
        include_drafts: True이면 draft 블록도 포함 (리뷰 UI 전용).
        limit: 최대 반환 건수 (1~100).

    Returns:
        블록 dict 목록.
    """
    from db import db_session
    from foms.persistence.designer.models import DesignerReusableBlock

    limit = max(1, min(limit, 100))
    query = db_session.query(DesignerReusableBlock)

    if not include_drafts:
        # approved 블록만 — RAG/active asset 기준
        query = query.filter(DesignerReusableBlock.status == "approved")
    else:
        # 리뷰 UI: draft + approved (rejected/retired 제외)
        query = query.filter(DesignerReusableBlock.status.in_(["draft", "approved"]))

    if category is not None:
        query = query.filter(DesignerReusableBlock.category == category)

    query = query.order_by(DesignerReusableBlock.created_at.desc()).limit(limit)
    blocks = query.all()

    result = [_block_to_dict(b) for b in blocks]

    # 태그 필터 (후처리 — JSONB 배열 포함 검색)
    if tags:
        tag_set = set(tags)
        result = [b for b in result if tag_set.intersection(b.get("tags", []))]

    return result


def get_block(block_id: int) -> dict | None:
    """ID로 단일 블록 조회.

    Args:
        block_id: DesignerReusableBlock.id 값.

    Returns:
        블록 dict 또는 None (존재하지 않을 때).
    """
    from db import db_session
    from foms.persistence.designer.models import DesignerReusableBlock

    block = db_session.get(DesignerReusableBlock, block_id)
    if block is None:
        return None
    return _block_to_dict(block)


def _scale_number(value: Any, scale: float) -> Any:
    if isinstance(value, (int, float)):
        return round(value * scale, 2)
    return value


def _instantiate_geometry(
    *,
    block_id: int,
    block_key: str,
    label_ko: str,
    category: str,
    geometry: dict,
    at_position: dict | None = None,
    scale: float = 1.0,
) -> dict:
    """Instantiate saved block geometry as a module plus cloned components."""
    raw_components = copy.deepcopy(geometry.get("components") or [])
    if not raw_components:
        raise ValueError("블록 geometry_json.components가 비어 있습니다.")

    position = at_position if at_position is not None else {"x": 0, "y": 0, "z": 0}
    base_x = float(position.get("x") or 0)
    base_y = float(position.get("y") or 0)
    base_z = float(position.get("z") or 0)

    def pos_of(component: dict) -> dict:
        return component.get("position") or {}

    min_x = min(float(pos_of(c).get("x") or 0) for c in raw_components)
    min_y = min(float(pos_of(c).get("y") or 0) for c in raw_components)
    min_z = min(float(pos_of(c).get("z") or 0) for c in raw_components)

    module_id = str(uuid.uuid4())
    id_map: dict[str, str] = {}
    components: list[dict] = []

    for source in raw_components:
        original_id = str(source.get("id") or uuid.uuid4())
        new_id = str(uuid.uuid4())
        id_map[original_id] = new_id

        dims = copy.deepcopy(source.get("dimensions") or {})
        scaled_dims = {
            key: _scale_number(value, scale)
            for key, value in dims.items()
            if key in {"width", "height", "depth", "width_mm", "height_mm", "depth_mm"}
        }
        for axis in ("width", "height", "depth"):
            if axis not in scaled_dims:
                scaled_dims[axis] = _scale_number(dims.get(axis) or 1, scale)

        src_pos = source.get("position") or {}
        new_pos = {
            "x": round(base_x + (float(src_pos.get("x") or 0) - min_x) * scale, 2),
            "y": round(base_y + (float(src_pos.get("y") or 0) - min_y) * scale, 2),
            "z": round(base_z + (float(src_pos.get("z") or 0) - min_z) * scale, 2),
        }

        custom_props = copy.deepcopy(source.get("custom_props") or {})
        custom_props.update({
            "from_block_id": block_id,
            "from_block_key": block_key,
            "source_component_id": original_id,
            "scale": scale,
        })

        cloned = copy.deepcopy(source)
        cloned.update({
            "id": new_id,
            "parent_id": module_id,
            "dimensions": scaled_dims,
            "position": new_pos,
            "custom_props": custom_props,
        })
        components.append(cloned)

    def extent(axis: str) -> float:
        return max(
            float(c["position"][axis]) + float(c["dimensions"][{"x": "width", "y": "height", "z": "depth"}[axis]])
            for c in components
        ) - {"x": base_x, "y": base_y, "z": base_z}[axis]

    module = {
        "id": module_id,
        "type": f"reusable_block_{category}",
        "name": f"{label_ko} 인스턴스",
        "dimensions": {
            "width": round(max(1.0, extent("x")), 2),
            "height": round(max(1.0, extent("y")), 2),
            "depth": round(max(1.0, extent("z")), 2),
        },
        "position": {"x": base_x, "y": base_y, "z": base_z},
        "component_ids": [c["id"] for c in components],
        "door_type": "open",
        "custom_props": {
            "from_block_id": block_id,
            "from_block_key": block_key,
            "scale": scale,
        },
    }

    return {
        "block_id": block_id,
        "block_key": block_key,
        "module": module,
        "components": components,
        "relations": [
            {"from": module_id, "to": c["id"], "type": "contains_component"}
            for c in components
        ],
        "id_map": id_map,
    }


def instantiate_block(
    block_id: int,
    at_position: dict | None = None,
    scale: float = 1.0,
) -> dict:
    """블록을 특정 위치에 인스턴스화하여 모듈 + 부재 목록을 반환.

    반환된 dict는 design_graph.assembly.modules와 components에 함께 추가한다.
    승인(approved)된 블록만 인스턴스화 가능 — RAG/active asset 정책 준수.

    Args:
        block_id: DesignerReusableBlock.id 값.
        at_position: {x, y, z} 위치 dict. None이면 {x:0, y:0, z:0}.
        scale: 스케일 배율 (기본 1.0).

    Returns:
        {module, components, relations, block_id, block_key} dict.

    Raises:
        ValueError: 블록이 존재하지 않거나 approved 상태가 아닐 때.
    """
    from db import db_session
    from foms.persistence.designer.models import DesignerReusableBlock

    block = db_session.get(DesignerReusableBlock, block_id)
    if block is None:
        raise ValueError(f"블록 ID {block_id}를 찾을 수 없습니다.")
    if block.status != "approved":
        # approved 블록 외에는 RAG/active asset 사용 금지
        raise ValueError(
            f"블록 {block_id} (key={block.block_key!r})는 status={block.status!r}로 "
            "인스턴스화 불가. approved 블록만 사용 가능."
        )

    # usage_count 증가 (JSONB가 아니므로 단순 정수 갱신)
    block.usage_count = (block.usage_count or 0) + 1
    db_session.commit()

    geometry = copy.deepcopy(block.geometry_json or {})
    return _instantiate_geometry(
        block_id=block.id,
        block_key=block.block_key,
        label_ko=block.label_ko,
        category=block.category,
        geometry=geometry,
        at_position=at_position,
        scale=scale,
    )


def approve_block(block_id: int, approved_by_user_id: int | None = None) -> dict:
    """블록 상태를 draft → approved로 변경.

    AI MUST NOT call this directly — 반드시 사람이 API를 통해 호출해야 한다.

    Args:
        block_id: DesignerReusableBlock.id 값.
        approved_by_user_id: 승인 사용자 ID.

    Returns:
        갱신된 블록 dict.

    Raises:
        ValueError: 블록이 존재하지 않거나 이미 approved 상태일 때.
    """
    from db import db_session
    from foms.persistence.designer.models import DesignerReusableBlock

    block = db_session.get(DesignerReusableBlock, block_id)
    if block is None:
        raise ValueError(f"블록 ID {block_id}를 찾을 수 없습니다.")
    if block.status == "approved":
        raise ValueError(f"블록 {block_id}는 이미 approved 상태입니다.")

    # JSONB가 아닌 단순 컬럼이므로 직접 갱신
    block.status = "approved"
    block.approved_by_user_id = approved_by_user_id
    block.approved_at = _now()
    db_session.commit()
    db_session.refresh(block)

    logger.info("[BLOCK_LIB] 블록 승인: id=%d key=%s by_user=%s", block.id, block.block_key, approved_by_user_id)
    return _block_to_dict(block)
