"""③ 질문 카드 — 카드가 생긴 뒤 다루는 지식이 바뀌었나(결함 2026-11-27).

엇갈림 카드의 바깥 글은 카드가 생긴 밤의 글 그대로다. 그 뒤 다루는 지식이 고쳐졌으면(사장님 · 직원이 이미 정리했으면) 화면이
그 바깥 글을 고칠 글에 붙여 미리 채우면 이미 걷어낸 옛 내용이 다시 들어간다. 그래서 카드 응답의 ``about`` 마다
``changed_since`` 를 싣고, 화면은 참이면 지금 지식 글만 칸에 넣는다(``ds-inbox-question.js``).

판정(새 DB 칸 없음 — 있는 재료로):

1. 카드를 만들 때 실음 칸에 대상과 그때 판(``payload.target`` · ``payload.target_version`` — 밤 배우기 · 채팅 신고 · 사진 다시
   배우기 카드)을 남겼고 대상 키가 같으면, 그 판 ≠ 지금 판.
2. 아니면(계획 파일 카드 등) 카드 생긴 시각 < 지금 판 기록 시각(``recorded_at`` — 둘 다 UTC naive).

DB 를 읽지 않는다 — 지금 판 · 기록 시각은 :func:`.inbox.about_items` 가 한 번에 읽어 :data:`RECORDED` 칸에 실어 준다(화면에는
그 칸을 빼고 보낸다).
"""

from __future__ import annotations

from typing import Any, Mapping

__all__ = ["RECORDED", "about_changed", "about_view"]

#: ``about_items`` 항목의 속 칸 — 지금 판 기록 시각(화면 응답에는 빠진다).
RECORDED = "_recorded_at"


def _made_with(change: Any) -> Mapping[str, Any]:
    """카드를 만들 때 실음 칸 값(만들기 제안의 '후')."""
    entry = (change.fields or {}).get("payload") if isinstance(change.fields, dict) else None
    after = entry.get("after") if isinstance(entry, dict) else None
    return after if isinstance(after, dict) else {}


def about_changed(change: Any, item: Mapping[str, Any]) -> bool:
    """카드(``change``)가 생긴 뒤 다루는 지식(``item`` — :func:`.inbox.about_items` 한 항목)이 바뀌었나(모듈 설명의 판정)."""
    made = _made_with(change)
    version = made.get("target_version")
    if made.get("target") == item.get("key") and type(version) is int:
        return version != item.get("version")
    recorded, created = item.get(RECORDED), getattr(change, "created_at", None)
    return bool(recorded is not None and created is not None and created < recorded)


def about_view(change: Any, item: Mapping[str, Any]) -> dict[str, Any]:
    """화면에 보낼 항목 — 속 칸을 빼고 ``changed_since`` 를 더한다."""
    out = {k: v for k, v in item.items() if k != RECORDED}
    out["changed_since"] = about_changed(change, item)
    return out
