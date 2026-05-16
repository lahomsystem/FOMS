"""FOMS Brain PG-L2 — Retrieval-Augmented Design Brain.

Retrieves approved design cases and correction patterns to enrich
Gemini prompts with project-specific knowledge.

Contract:
- Only approved cases are retrievable (PII-free).
- Retrieval payload must not contain raw PII fields.
- Missing vector backend falls back to deterministic dimension search.
- Gemini prompt builder formats top-k cases as structured context.

Usage (PG-L2 integration):
    from foms.services.designer.design_retrieval import (
        retrieve_similar_cases, build_gemini_context_prompt
    )
    cases = retrieve_similar_cases(furniture_type="wardrobe", width_mm=2400)
    context = build_gemini_context_prompt(cases, request_description="3칸 붙박이장 설계")
    # Prepend context to Gemini extraction/design prompt
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_PII_KEYS = frozenset({
    "customer_name", "phone", "address", "customer_phone",
    "customer_address", "client_name",
})


# ──────────────────────────────────────────────────────────
# Core retrieval
# ──────────────────────────────────────────────────────────

def retrieve_similar_cases(
    furniture_type: str | None = None,
    width_mm: int | None = None,
    height_mm: int | None = None,
    depth_mm: int | None = None,
    tolerance_mm: int = 300,
    tags: list[str] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Retrieve approved design cases for retrieval-augmented generation.

    Falls back to deterministic dimension search if pgvector unavailable.

    Args:
        furniture_type: Filter by type.
        width_mm/height_mm/depth_mm: Target dimensions.
        tolerance_mm: Dimension search tolerance.
        tags: Tag filter (AND).
        limit: Max cases returned.

    Returns:
        List of PII-free design case dicts, ordered by similarity.
    """
    try:
        from foms.services.designer.design_case_memory import find_similar, list_design_cases

        if width_mm is not None:
            cases = find_similar(
                furniture_type=furniture_type or "wardrobe",
                width_mm=width_mm,
                height_mm=height_mm,
                depth_mm=depth_mm,
                tolerance_mm=tolerance_mm,
                limit=limit,
            )
        else:
            cases = list_design_cases(
                furniture_type=furniture_type,
                tags=tags,
                limit=limit,
            )

        # Double-check PII removal before returning
        return [_ensure_pii_free(c) for c in cases]

    except Exception as exc:
        logger.warning("[RETRIEVAL] DB query failed (returning empty): %s", exc)
        return []


def retrieve_recent_corrections(
    furniture_type: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Retrieve recent approved corrections as pattern evidence.

    Used to show Gemini what users commonly fix so it can do better upfront.
    """
    try:
        from db import db_session
        from foms.persistence.designer.models import DesignerCorrection
        from sqlalchemy import desc

        q = db_session.query(DesignerCorrection).order_by(
            desc(DesignerCorrection.created_at)
        ).limit(limit * 3)

        corrections = q.all()
        result = []
        for c in corrections:
            after = c.after_json or {}
            # Filter out corrections without useful hints
            if not after.get("candidate_rule_hint") and after.get("source") != "user_manual_edit":
                continue
            result.append({
                "field": after.get("field", "unknown"),
                "correction_pattern": after.get("candidate_rule_hint", "manual_edit"),
                "source": after.get("source", "unknown"),
            })
            if len(result) >= limit:
                break
        return result

    except Exception as exc:
        logger.warning("[RETRIEVAL] corrections query failed: %s", exc)
        return []


def retrieve_replay_passed_rules(limit: int = 5) -> list[dict[str, Any]]:
    """Retrieve rule candidates that passed replay (promoted or approved).

    These represent validated design knowledge.
    """
    try:
        from db import db_session
        from foms.persistence.designer.models import DesignerRuleCandidate
        from sqlalchemy import or_

        q = db_session.query(DesignerRuleCandidate).filter(
            or_(
                DesignerRuleCandidate.status == "approved",
                DesignerRuleCandidate.status == "promoted",
            )
        ).order_by(DesignerRuleCandidate.id.desc()).limit(limit)

        rules = []
        for rc in q.all():
            rj = rc.replay_report_json or {}
            if rj.get("fail_count", 1) == 0:
                cj = rc.candidate_json or {}
                rules.append({
                    "rule_hint": cj.get("rule_hint", ""),
                    "correction_count": cj.get("correction_count", 0),
                    "evidence_strength": cj.get("evidence_strength", 0.0),
                })
        return rules

    except Exception as exc:
        logger.warning("[RETRIEVAL] rules query failed: %s", exc)
        return []


# ──────────────────────────────────────────────────────────
# Gemini prompt builder
# ──────────────────────────────────────────────────────────

def build_gemini_context_prompt(
    similar_cases: list[dict[str, Any]],
    recent_corrections: list[dict[str, Any]] | None = None,
    validated_rules: list[dict[str, Any]] | None = None,
    request_description: str = "",
) -> str:
    """Build a structured context block to prepend to Gemini prompts.

    Includes:
    - Top-k approved similar design cases
    - Recent correction patterns
    - Validated rule hints

    Args:
        similar_cases: From retrieve_similar_cases().
        recent_corrections: From retrieve_recent_corrections().
        validated_rules: From retrieve_replay_passed_rules().
        request_description: Optional description of the current request.

    Returns:
        Structured Korean/English context string.
    """
    lines: list[str] = []

    if request_description:
        lines.append(f"[현재 요청] {request_description}\n")

    # Similar approved cases
    if similar_cases:
        lines.append(f"[유사 승인 설계 사례 — 상위 {len(similar_cases)}개]")
        for i, c in enumerate(similar_cases[:5], 1):
            ft = c.get("furniture_type", "unknown")
            w = c.get("width_mm", "?")
            h = c.get("height_mm", "?")
            d = c.get("depth_mm", "?")
            mc = c.get("module_count", "?")
            pname = c.get("product_name") or ""
            tags = ", ".join(c.get("tags") or [])
            opts = c.get("options_json") or {}
            color = opts.get("color", "")
            lines.append(
                f"  사례{i}: {ft} W{w}×H{h}×D{d}mm {mc}통"
                + (f" [{pname}]" if pname else "")
                + (f" 색상:{color}" if color else "")
                + (f" 태그:{tags}" if tags else "")
            )
        lines.append("")

    # Correction patterns
    if recent_corrections:
        unique_patterns = list({c["correction_pattern"] for c in recent_corrections})[:5]
        if unique_patterns:
            lines.append("[자주 수정되는 패턴 — 추출 시 주의]")
            for p in unique_patterns:
                lines.append(f"  - {p}")
            lines.append("")

    # Validated rules
    if validated_rules:
        lines.append("[검증된 설계 규칙]")
        for r in validated_rules[:3]:
            hint = r.get("rule_hint", "")
            cnt = r.get("correction_count", 0)
            if hint:
                lines.append(f"  - {hint} (근거 {cnt}개)")
        lines.append("")

    if not lines:
        return ""

    header = "=== FOMS Brain 설계 지식 컨텍스트 (Retrieval-Augmented) ===\n"
    footer = "=== 위 사례를 참고해 추출 정확도를 높이세요 ===\n"
    return header + "\n".join(lines) + "\n" + footer


# ──────────────────────────────────────────────────────────
# Full RAG pipeline
# ──────────────────────────────────────────────────────────

def build_rag_context(
    furniture_type: str | None = None,
    width_mm: int | None = None,
    height_mm: int | None = None,
    depth_mm: int | None = None,
    request_description: str = "",
    top_k: int = 3,
) -> str:
    """Full RAG pipeline: retrieve all sources + build context prompt.

    Args:
        furniture_type: Target furniture type.
        width_mm/height_mm/depth_mm: Target dimensions.
        request_description: What the user is asking for.
        top_k: Max similar cases to retrieve.

    Returns:
        Context string ready to prepend to Gemini prompt.
    """
    cases = retrieve_similar_cases(
        furniture_type=furniture_type,
        width_mm=width_mm,
        height_mm=height_mm,
        depth_mm=depth_mm,
        limit=top_k,
    )
    corrections = retrieve_recent_corrections(furniture_type=furniture_type, limit=8)
    rules = retrieve_replay_passed_rules(limit=3)

    context = build_gemini_context_prompt(
        similar_cases=cases,
        recent_corrections=corrections,
        validated_rules=rules,
        request_description=request_description,
    )

    if cases or corrections or rules:
        logger.info(
            "[RAG] context built: cases=%d corrections=%d rules=%d",
            len(cases), len(corrections), len(rules),
        )
    return context


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────

def _ensure_pii_free(case: dict[str, Any]) -> dict[str, Any]:
    """Strip any PII that may have leaked into a case dict."""
    return {k: v for k, v in case.items() if k not in _PII_KEYS}


# ──────────────────────────────────────────────────────────
# C9: Explanation-Augmented Retrieval
# ──────────────────────────────────────────────────────────

def build_explanation_rag_context(
    query: str,
    top_k: int = 5,
    approved_only: bool = True,
) -> dict[str, Any]:
    """Build RAG context from approved component explanations.

    Contract:
    - Only approved explanations enter AI prompt context.
    - draft/rejected explanations are strictly excluded.
    - Returns empty context (not error) when no matches found.
    - Never raises: all exceptions are caught and reported via retrieval_warning.

    Args:
        query: Natural language query to match against explanations.
        top_k: Maximum number of explanations to include.
        approved_only: If True (default), exclude non-approved explanations.

    Returns:
        {
            "explanations": [{"component_id", "explanation_text",
                               "rationale_category", "design_case_id"}],
            "context_text": "... formatted for Gemini prompt ...",
            "match_count": int,
            "retrieval_warning": str | None  # set if search failed
        }
    """
    try:
        from foms.services.designer.explanation_service import search_explanations
        results = search_explanations(query=query, top_k=top_k, approved_only=approved_only)
    except Exception as exc:
        logger.warning("[RAG] explanation search failed (non-fatal): %s", exc)
        return {
            "explanations": [],
            "context_text": "",
            "match_count": 0,
            "retrieval_warning": f"explanation_search_failed: {exc}",
        }

    if not results:
        return {
            "explanations": results,
            "context_text": "",
            "match_count": 0,
            "retrieval_warning": None,
        }

    # Format for Gemini prompt injection
    lines = ["## 관련 설계 의도 (승인된 학습 데이터)"]
    for i, exp in enumerate(results[:top_k], 1):
        cat = exp.get("rationale_category", "other")
        text = exp.get("explanation_text", "")
        lines.append(f"{i}. [{cat}] {text}")
    context_text = "\n".join(lines)

    return {
        "explanations": results,
        "context_text": context_text,
        "match_count": len(results),
        "retrieval_warning": None,
    }
