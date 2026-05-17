"""FOMS Brain C6 — Block Ontology Service.

Contract:
- infer_ontology_from_case(): analyze block instances/positions → extract relations
- propose_ontology_relations(): min_evidence=3 gate (same as B5 rule candidate gate)
- approve_relation(): human approval required; auto-promotion strictly forbidden
- Only approved/promoted relations enter active ontology
- Replay failure blocks promotion
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# 위치 관계 판별 임계값
_ADJACENT_GAP_MM = 20.0   # X축 인접 판단 최대 거리 (mm)
_ALIGNED_TOL_MM = 5.0     # Y 좌표 정렬 판단 허용 오차 (mm)


# ──────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────

def infer_ontology_from_case(design_case_id: int) -> list[dict[str, Any]]:
    """한 케이스의 컴포넌트에서 블록 관계 패턴을 추출한다.

    Args:
        design_case_id: 분석 대상 DesignerDesignCase ID.

    Returns:
        추출된 관계 목록. 각 항목은
        {from_block_key, to_block_key, relation_type, params_json, case_id} 형태.

    Raises:
        ValueError: design_case_id가 존재하지 않을 때.
    """
    from db import db_session
    from foms.persistence.designer.models import DesignerDesignCase

    case = db_session.get(DesignerDesignCase, design_case_id)
    if case is None:
        raise ValueError(f"DesignerDesignCase id={design_case_id} not found.")

    graph = case.design_graph_json or {}
    components = graph.get("components") or []

    block_comps = [
        c for c in components
        if _component_block_key(c) is not None
    ]

    relations: list[dict[str, Any]] = []
    for i, comp_a in enumerate(block_comps):
        for comp_b in block_comps[i + 1:]:
            rel = _classify_relation(comp_a, comp_b)
            if rel is None:
                continue
            relations.append({
                "from_block_key": _component_block_key(comp_a),
                "to_block_key": _component_block_key(comp_b),
                "relation_type": rel["relation_type"],
                "params_json": rel["params_json"],
                "case_id": design_case_id,
            })

    logger.debug("[ONTOLOGY] case=%d extracted %d relations", design_case_id, len(relations))
    return relations


def propose_ontology_relations(
    ontology_version_id: int | None = None,
    min_evidence: int = 3,
) -> list[int]:
    """여러 케이스에서 반복되는 관계를 DesignerBlockOntologyRelation으로 생성한다.

    Args:
        ontology_version_id: 관계를 귀속시킬 온톨로지 버전 ID.
            None이면 draft 버전 중 가장 최신을 사용하거나 새로 생성한다.
        min_evidence: 후보로 승격할 최소 증거 케이스 수 (B5 rule candidate gate와 동일).

    Returns:
        새로 생성된 DesignerBlockOntologyRelation ID 목록.
    """
    from db import db_session
    from foms.persistence.designer.models import (
        DesignerDesignCase,
        DesignerBlockOntologyVersion,
        DesignerBlockOntologyRelation,
    )

    # 온톨로지 버전 확보
    ontology_version_id = _resolve_ontology_version(
        db_session, ontology_version_id, DesignerBlockOntologyVersion
    )

    # 모든 approved DesignerDesignCase에서 관계 추출
    cases = (
        db_session.query(DesignerDesignCase)
        .filter(DesignerDesignCase.approved_at.isnot(None))
        .all()
    )

    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for case in cases:
        try:
            rels = infer_ontology_from_case(case.id)
        except Exception as exc:
            logger.warning("[ONTOLOGY] case=%d infer failed: %s", case.id, exc)
            continue
        for rel in rels:
            key = (rel["from_block_key"], rel["to_block_key"], rel["relation_type"])
            grouped[key].append(rel)

    created_ids: list[int] = []
    for (from_key, to_key, rel_type), evidence_list in grouped.items():
        if len(evidence_list) < min_evidence:
            continue

        relation_key = f"{from_key}__{rel_type}__{to_key}"
        existing = (
            db_session.query(DesignerBlockOntologyRelation)
            .filter(
                DesignerBlockOntologyRelation.ontology_version_id == ontology_version_id,
                DesignerBlockOntologyRelation.relation_key == relation_key,
            )
            .first()
        )
        if existing is not None:
            logger.debug("[ONTOLOGY] relation_key=%s already exists, skip", relation_key)
            continue

        case_ids = list({e["case_id"] for e in evidence_list})
        merged_params = _merge_params([e["params_json"] for e in evidence_list])

        relation = DesignerBlockOntologyRelation(
            ontology_version_id=ontology_version_id,
            relation_key=relation_key,
            from_block_key=from_key,
            to_block_key=to_key,
            relation_type=rel_type,
            params_json=merged_params,
            evidence_case_ids_json=case_ids,
            evidence_count=len(case_ids),
            status="candidate",
        )
        db_session.add(relation)
        db_session.flush()
        created_ids.append(relation.id)
        logger.info(
            "[ONTOLOGY] proposed relation: %s (evidence=%d)", relation_key, len(case_ids)
        )

    db_session.commit()
    return created_ids


def approve_relation(
    relation_id: int,
    approved_by_user_id: int | None = None,
) -> dict[str, Any]:
    """관계를 candidate 상태에서 approved로 변경한다.

    Args:
        relation_id: 승인할 DesignerBlockOntologyRelation ID.
        approved_by_user_id: 승인한 사용자 ID.

    Returns:
        승인된 relation 정보 dict.

    Raises:
        ValueError: relation이 존재하지 않거나 이미 approved/rejected 상태일 때.
        ValueError: replay_report_json에 실패 기록이 있을 때.
    """
    from db import db_session
    from foms.persistence.designer.models import DesignerBlockOntologyRelation

    relation = db_session.get(DesignerBlockOntologyRelation, relation_id)
    if relation is None:
        raise ValueError(f"DesignerBlockOntologyRelation id={relation_id} not found.")

    if relation.status in ("approved", "rejected"):
        raise ValueError(
            f"Relation id={relation_id} is already '{relation.status}'. "
            "Cannot approve again."
        )

    _check_replay_report(relation)

    relation.status = "approved"
    relation.approved_by_user_id = approved_by_user_id
    relation.approved_at = datetime.now(timezone.utc)
    db_session.commit()

    logger.info(
        "[ONTOLOGY] approved relation id=%d key=%s by user=%s",
        relation.id, relation.relation_key, approved_by_user_id,
    )
    return _relation_to_dict(relation)


def list_relations(
    ontology_version_id: int | None = None,
    status: str | None = None,
    from_block_key: str | None = None,
) -> list[dict[str, Any]]:
    """블록 온톨로지 관계 목록을 조회한다.

    Args:
        ontology_version_id: 특정 버전으로 필터 (None이면 전체).
        status: 상태 필터 ('candidate'|'approved'|'rejected'|'promoted').
        from_block_key: 출발 블록 키 필터.

    Returns:
        relation dict 목록 (created_at 역순).
    """
    from db import db_session
    from foms.persistence.designer.models import DesignerBlockOntologyRelation

    q = db_session.query(DesignerBlockOntologyRelation)

    if ontology_version_id is not None:
        q = q.filter(DesignerBlockOntologyRelation.ontology_version_id == ontology_version_id)
    if status is not None:
        q = q.filter(DesignerBlockOntologyRelation.status == status)
    if from_block_key is not None:
        q = q.filter(DesignerBlockOntologyRelation.from_block_key == from_block_key)

    relations = q.order_by(DesignerBlockOntologyRelation.created_at.desc()).all()
    return [_relation_to_dict(r) for r in relations]


# ──────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────

def _resolve_ontology_version(
    db_session: Any,
    ontology_version_id: int | None,
    model_cls: Any,
) -> int:
    """온톨로지 버전 ID를 확정한다. None이면 최신 draft 또는 신규 생성."""
    if ontology_version_id is not None:
        return ontology_version_id

    latest = (
        db_session.query(model_cls)
        .filter(model_cls.status == "draft")
        .order_by(model_cls.created_at.desc())
        .first()
    )
    if latest is not None:
        return latest.id

    # 새 draft 버전 생성
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    new_version = model_cls(
        version_key=f"auto-{ts}",
        status="draft",
        description="Auto-created by propose_ontology_relations",
    )
    db_session.add(new_version)
    db_session.flush()
    logger.info("[ONTOLOGY] created new draft version: %s", new_version.version_key)
    return new_version.id


def _classify_relation(
    comp_a: dict[str, Any],
    comp_b: dict[str, Any],
) -> dict[str, Any] | None:
    """두 컴포넌트의 위치 관계를 분류한다.

    Args:
        comp_a: 첫 번째 컴포넌트 dict (position, size 포함).
        comp_b: 두 번째 컴포넌트 dict.

    Returns:
        {relation_type, params_json} 또는 관계 없으면 None.
    """
    pos_a = comp_a.get("position") or {}
    size_a = comp_a.get("size") or comp_a.get("dimensions") or {}
    pos_b = comp_b.get("position") or {}
    size_b = comp_b.get("size") or comp_b.get("dimensions") or {}

    ax, ay = float(pos_a.get("x", 0)), float(pos_a.get("y", 0))
    aw, ah = _width_height(size_a)
    bx, by = float(pos_b.get("x", 0)), float(pos_b.get("y", 0))
    bw, bh = _width_height(size_b)

    # contains: A의 bounding box가 B를 완전히 포함
    if ax <= bx and ay <= by and (ax + aw) >= (bx + bw) and (ay + ah) >= (by + bh):
        return {"relation_type": "contains", "params_json": {}}

    # adjacent_to: X축으로 A 오른쪽 끝과 B 왼쪽 끝 gap < _ADJACENT_GAP_MM
    gap_x = bx - (ax + aw)
    if 0 <= gap_x < _ADJACENT_GAP_MM:
        return {
            "relation_type": "adjacent_to",
            "params_json": {"gap_mm": round(gap_x, 1), "axis": "x"},
        }

    # aligned_with: Y 좌표 차이 < _ALIGNED_TOL_MM
    if abs(ay - by) < _ALIGNED_TOL_MM:
        return {
            "relation_type": "aligned_with",
            "params_json": {"axis": "y", "tolerance_mm": _ALIGNED_TOL_MM},
        }

    return None


def _component_block_key(component: dict[str, Any]) -> str | None:
    custom_props = component.get("custom_props") or {}
    key = custom_props.get("from_block_key") or custom_props.get("block_key") or custom_props.get("source_block_key")
    return str(key) if key else None


def _width_height(size: dict[str, Any]) -> tuple[float, float]:
    width = size.get("w", size.get("width", size.get("width_mm", 0)))
    height = size.get("h", size.get("height", size.get("height_mm", 0)))
    return float(width or 0), float(height or 0)


def _merge_params(params_list: list[dict[str, Any]]) -> dict[str, Any]:
    """여러 관계의 params_json을 병합한다 (수치는 평균)."""
    if not params_list:
        return {}
    merged: dict[str, Any] = {}
    for params in params_list:
        for k, v in params.items():
            if k not in merged:
                merged[k] = []
            merged[k].append(v)
    result: dict[str, Any] = {}
    for k, vals in merged.items():
        if vals and isinstance(vals[0], (int, float)):
            result[k] = round(sum(vals) / len(vals), 2)
        else:
            result[k] = vals[0]
    return result


def _check_replay_report(relation: Any) -> None:
    """replay_report_json에 실패 기록이 있으면 ValueError를 발생시킨다."""
    report = relation.replay_report_json
    if report is None:
        return
    if report.get("status") == "failed" or report.get("passed") is False:
        raise ValueError(
            f"Relation id={relation.id} has a failed replay report. "
            "Fix replay failures before approving."
        )


def _relation_to_dict(relation: Any) -> dict[str, Any]:
    """DesignerBlockOntologyRelation 인스턴스를 직렬화 가능한 dict로 변환한다."""
    return {
        "id": relation.id,
        "ontology_version_id": relation.ontology_version_id,
        "relation_key": relation.relation_key,
        "from_block_key": relation.from_block_key,
        "to_block_key": relation.to_block_key,
        "relation_type": relation.relation_type,
        "params_json": relation.params_json,
        "evidence_case_ids_json": relation.evidence_case_ids_json,
        "evidence_count": relation.evidence_count,
        "replay_report_json": relation.replay_report_json,
        "status": relation.status,
        "approved_by_user_id": relation.approved_by_user_id,
        "approved_at": relation.approved_at.isoformat() if relation.approved_at else None,
        "created_at": relation.created_at.isoformat() if relation.created_at else None,
    }
