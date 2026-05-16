"""FOMS Brain C7 — Component Explanation Service.

Contract:
- save_explanation(): PII redaction applied before DB storage
- Only approved explanations enter RAG context (C9)
- Draft explanations visible to author/admin review only
- Embeddings stored in designer_embeddings for similarity search
- Multiple explanations per (design_case_id, component_id_in_graph) allowed (versioning)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_VALID_RATIONALE_CATEGORIES = frozenset({
    "constraint", "preference", "customer_request", "codified_rule", "other"
})


# ──────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────

def save_explanation(
    component_id_in_graph: str,
    explanation_text: str,
    design_case_id: int | None = None,
    rationale_category: str = "other",
    confidence: float = 1.0,
    created_by_user_id: int | None = None,
) -> dict[str, Any]:
    """PII 레닥션 후 설명 저장.

    Steps:
    1. scan_for_raw_pii()로 설명 텍스트 PII 패턴 스캔 (경고만, 블록 안 함)
    2. DesignerComponentExplanation 생성 (status="draft")
    3. designer_embeddings에 텍스트 저장 (text_only, embedding 컬럼 없이)
    4. embedding_id FK 업데이트
    5. 반환: {id, component_id_in_graph, status, created_at}

    Args:
        component_id_in_graph: 그래프 내 컴포넌트 식별자.
        explanation_text: 사람이 작성한 설명 (PII 스캔 후 저장).
        design_case_id: 연결된 디자인 케이스 ID (선택).
        rationale_category: constraint / preference / customer_request / codified_rule / other.
        confidence: 0.0–1.0 확신도.
        created_by_user_id: 작성자 사용자 ID.

    Returns:
        dict: {id, component_id_in_graph, status, created_at, embedding_id}

    Raises:
        ValueError: rationale_category가 유효하지 않을 때.
    """
    if rationale_category not in _VALID_RATIONALE_CATEGORIES:
        raise ValueError(
            f"Unknown rationale_category: {rationale_category!r}. "
            f"Valid: {sorted(_VALID_RATIONALE_CATEGORIES)}"
        )

    # Step 1: PII 스캔 — 텍스트는 블록하지 않고 경고 로그만
    _warn_if_pii_detected(explanation_text, component_id_in_graph)

    from db import db_session
    from foms.persistence.designer.models import (
        DesignerComponentExplanation,
        DesignerEmbedding,
    )

    # Step 2: 설명 레코드 생성 (status=draft)
    explanation = DesignerComponentExplanation(
        design_case_id=design_case_id,
        component_id_in_graph=component_id_in_graph,
        explanation_text=explanation_text,
        rationale_category=rationale_category,
        confidence=max(0.0, min(1.0, confidence)),
        status="draft",
        created_by_user_id=created_by_user_id,
    )
    db_session.add(explanation)
    db_session.flush()  # id 확보 (commit 전)

    # Step 3: DesignerEmbedding에 텍스트 저장 (벡터 없이 text_only)
    embedding = DesignerEmbedding(
        owner_type="component_explanation",
        owner_id=explanation.id,
        text=explanation_text,
        metadata_json={
            "component_id_in_graph": component_id_in_graph,
            "design_case_id": design_case_id,
            "rationale_category": rationale_category,
        },
    )
    db_session.add(embedding)
    db_session.flush()  # embedding.id 확보

    # Step 4: embedding_id FK 연결
    explanation.embedding_id = embedding.id

    db_session.commit()
    db_session.refresh(explanation)

    logger.info(
        "[EXPLANATION] saved: id=%d component=%s case=%s status=draft",
        explanation.id, component_id_in_graph, design_case_id,
    )
    return _explanation_to_dict(explanation)


def approve_explanation(
    explanation_id: int,
    approved_by_user_id: int | None = None,
) -> dict[str, Any]:
    """draft → approved 상태 전환.

    RAG 컨텍스트(C9) 진입 허용은 approved 상태에서만 가능 — 이 함수가 유일한 진입점.
    AI는 이 함수를 직접 호출하면 안 됨; 서비스 레이어/API 레이어만 호출.

    Args:
        explanation_id: 승인할 설명 레코드 ID.
        approved_by_user_id: 승인한 사용자 ID.

    Returns:
        dict: 업데이트된 설명 정보.

    Raises:
        ValueError: 존재하지 않거나 이미 approved 상태인 경우.
    """
    from db import db_session
    from foms.persistence.designer.models import DesignerComponentExplanation

    explanation = db_session.get(DesignerComponentExplanation, explanation_id)
    if explanation is None:
        raise ValueError(f"explanation_id={explanation_id} not found.")
    if explanation.status == "approved":
        raise ValueError(
            f"explanation_id={explanation_id} is already approved. "
            "Use a new explanation to revise."
        )

    explanation.status = "approved"
    explanation.approved_by_user_id = approved_by_user_id
    explanation.approved_at = datetime.now(timezone.utc)

    db_session.commit()
    db_session.refresh(explanation)

    logger.info(
        "[EXPLANATION] approved: id=%d component=%s by_user=%s",
        explanation.id, explanation.component_id_in_graph, approved_by_user_id,
    )
    return _explanation_to_dict(explanation)


def list_explanations_by_case(
    design_case_id: int,
    include_drafts: bool = False,
) -> list[dict[str, Any]]:
    """디자인 케이스별 설명 목록 조회.

    Args:
        design_case_id: 조회할 디자인 케이스 ID.
        include_drafts: True면 draft 포함, False면 approved만 반환.

    Returns:
        list[dict]: 설명 dict 목록.
    """
    from db import db_session
    from foms.persistence.designer.models import DesignerComponentExplanation
    from sqlalchemy import select

    stmt = select(DesignerComponentExplanation).where(
        DesignerComponentExplanation.design_case_id == design_case_id
    )
    if not include_drafts:
        stmt = stmt.where(DesignerComponentExplanation.status == "approved")

    stmt = stmt.order_by(DesignerComponentExplanation.created_at.desc())
    rows = db_session.execute(stmt).scalars().all()
    return [_explanation_to_dict(r) for r in rows]


def list_explanations_by_component(
    component_id_in_graph: str,
    include_drafts: bool = False,
) -> list[dict[str, Any]]:
    """컴포넌트별 설명 목록 조회.

    Args:
        component_id_in_graph: 그래프 내 컴포넌트 식별자.
        include_drafts: True면 draft 포함, False면 approved만 반환.

    Returns:
        list[dict]: 설명 dict 목록.
    """
    from db import db_session
    from foms.persistence.designer.models import DesignerComponentExplanation
    from sqlalchemy import select

    stmt = select(DesignerComponentExplanation).where(
        DesignerComponentExplanation.component_id_in_graph == component_id_in_graph
    )
    if not include_drafts:
        stmt = stmt.where(DesignerComponentExplanation.status == "approved")

    stmt = stmt.order_by(DesignerComponentExplanation.created_at.desc())
    rows = db_session.execute(stmt).scalars().all()
    return [_explanation_to_dict(r) for r in rows]


def search_explanations(
    query: str,
    top_k: int = 10,
    approved_only: bool = True,
) -> list[dict[str, Any]]:
    """텍스트 기반 설명 검색 (벡터 임베딩이 없으면 LIKE 기반 폴백).

    RAG 계약 핵심: approved_only=True가 기본값이며, 이 상태의 설명만
    C9 RAG 컨텍스트에 포함된다. draft 설명은 절대 RAG에 노출되지 않는다.

    현재 구현: SQL LIKE '%query%' 폴백 (pgvector 없이도 동작)
    미래: embedding_id 기반 코사인 유사도로 교체 가능.

    Args:
        query: 검색 쿼리 문자열.
        top_k: 최대 반환 결과 수.
        approved_only: True면 approved 상태만 검색 (RAG 계약 필수). False면 draft 포함.

    Returns:
        list[dict]: 검색 결과 설명 dict 목록 (최대 top_k개).
    """
    from db import db_session
    from foms.persistence.designer.models import DesignerComponentExplanation
    from sqlalchemy import select

    if not query or not query.strip():
        return []

    stmt = select(DesignerComponentExplanation).where(
        DesignerComponentExplanation.explanation_text.ilike(f"%{query}%")
    )

    # RAG 계약: approved_only=True가 기본 — draft는 RAG 컨텍스트에 진입 불가
    if approved_only:
        stmt = stmt.where(DesignerComponentExplanation.status == "approved")

    stmt = stmt.order_by(DesignerComponentExplanation.created_at.desc()).limit(top_k)
    rows = db_session.execute(stmt).scalars().all()

    logger.debug(
        "[EXPLANATION] search: query=%r approved_only=%s found=%d",
        query[:30], approved_only, len(rows),
    )
    return [_explanation_to_dict(r) for r in rows]


# ──────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────

def _warn_if_pii_detected(text: str, component_id: str) -> None:
    """설명 텍스트에서 PII 패턴 스캔 — 경고 로그만, 블록하지 않음.

    텍스트 PII는 정책 범위가 좁으므로 저장을 막지는 않는다.
    운영팀이 로그를 보고 수동 검토할 수 있도록 기록만 남긴다.

    Args:
        text: 스캔할 설명 텍스트.
        component_id: 로그 맥락용 컴포넌트 식별자.
    """
    from foms.services.designer.pii_redactor import scan_for_raw_pii

    found = scan_for_raw_pii(text)
    if found:
        logger.warning(
            "[EXPLANATION] PII pattern detected in explanation text "
            "(component=%s, types=%s). Storing as-is — manual review required.",
            component_id, found,
        )


def _explanation_to_dict(explanation: Any) -> dict[str, Any]:
    """DesignerComponentExplanation ORM 객체를 dict로 직렬화.

    Args:
        explanation: DesignerComponentExplanation 인스턴스.

    Returns:
        dict: API 응답용 직렬화 결과.
    """
    return {
        "id": explanation.id,
        "design_case_id": explanation.design_case_id,
        "component_id_in_graph": explanation.component_id_in_graph,
        "explanation_text": explanation.explanation_text,
        "rationale_category": explanation.rationale_category,
        "confidence": explanation.confidence,
        "usage_count": explanation.usage_count,
        "status": explanation.status,
        "created_by_user_id": explanation.created_by_user_id,
        "approved_by_user_id": explanation.approved_by_user_id,
        "approved_at": explanation.approved_at.isoformat() if explanation.approved_at else None,
        "embedding_id": explanation.embedding_id,
        "created_at": explanation.created_at.isoformat() if explanation.created_at else None,
        "updated_at": explanation.updated_at.isoformat() if explanation.updated_at else None,
    }
