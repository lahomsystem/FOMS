"""'도면 없음' 주문 카드 — 확정 도면이 0장인 생산 단계 주문을 카드 한 장(key ``@order``)으로 담고 끝낸다(설계서
2026-11-28-production-my-steps-flow §3-5 · 사장님 답 11 · 27 · 33 · 35).

**순수 계산 · 쿼리 0** — 표시 줄 쓰기 · 판 · '내 공정' · '작업 중' · 칸 아래 이름 · 아침 칩 · 현장 알람이 같은 판정을 여기서 읽는다.

* 약속 key :data:`ORDER_CARD_KEY` = ``"@order"``(표 ``production_part_marks`` 의 ``drawing_key`` 칸 — 표 · 마이그레이션 그대로). 한 주문 ·
  한 파트에 줄 하나(유일 제약 그대로).
* 주문 카드를 쓰는 주문 = 생산 단계 + 지금 확정 도면 0장(판 행은 :func:`row_files`). 쓰기 문은
  ``part_mark_write.current_entry`` 가 확정 도면이 0장일 때만 가짜 도면 항목(:func:`order_entry`)을 준다 — 1장 이상이면 지금처럼 409
  ``DRAWING_NOT_CURRENT``. 일괄 [남은 N장 모두 기본]은 이 key 를 받지 않는다(``part_mark_bulk`` · 판 ``bulk_count``).
* 장 목록(진행 · 공정 칸 맞추기 · 칸 아래 이름): :func:`sheet_keys`(``part_progress`` 한 곳 — 0장 + ``@order`` 줄 = ``['@order']``).
  확정 도면이 0장이면 '카드를 쓴 파트'는 미정이 아닌 ``@order`` 줄이 있는 파트뿐이다(``part_progress.parts_in_use`` — 옛 판 줄은 안 센다).
* 공장: 가짜 항목은 1공장 장이다(``drawing_factory.sheet_factory`` — 표에 없는 key = 1공장). 2공장 계정은 지금 공장 문 그대로 거절된다.
* 도면이 처음 올라오면(0장 → n장, 생산 · 시공 단계 바로 반영 전달) 미정이 아닌 ``@order`` 줄 · 손 체크 파트를 새 도면 줄로 한 번 옮긴다 —
  :mod:`.order_card_carry`(쓰기가 있어 따로 둔다 — 이 모듈은 쓰기 빌더를 부르지 않는다).
"""

from __future__ import annotations

from typing import Any, Iterable

from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.production.part_constants import ORDER_CARD_KEY
from foms.services.production.part_progress import order_card_mode, sheet_keys

#: 판 행(``build_production_home``)의 생산 단계 보기 키.
_PROD_VIEW = "prod"


def order_entry() -> dict[str, Any]:
    """가짜 도면 항목 — 확정 도면 항목(``resolve_final_drawing_files`` 한 줄)과 같은 칸 + 표지 ``order_card``.

    ``sheet_id`` 가 없어 바뀐 도면 짝 · 도면별 막힘 · 2공장 표에 안 걸린다(1공장 장). 파일이 아니라 그림 · 크게 보기가 없다.
    """
    return {"key": ORDER_CARD_KEY, "sheet_id": None, "filename": "", "view_url": "", "order_card": True}


def is_order_key(key: Any) -> bool:
    """주문 카드 key 인지."""
    return key == ORDER_CARD_KEY


def is_order_entry(entry: Any) -> bool:
    """가짜 도면 항목(:func:`order_entry`)인지."""
    return isinstance(entry, dict) and entry.get("key") == ORDER_CARD_KEY


def card_files(sd: Any, *, production: bool) -> list[dict[str, Any]]:
    """카드로 그릴 장 — 확정 도면 항목들, 생산 단계인데 0장이면 가짜 항목 한 장(주문 카드)."""
    files = resolve_final_drawing_files(sd if isinstance(sd, dict) else {})
    return files or ([order_entry()] if production else [])


def row_files(row: dict[str, Any]) -> list[dict[str, Any]]:
    """첫 화면 행의 카드 장(:func:`card_files`) — 생산 단계 행(``home_view == 'prod'``)만 주문 카드를 받는다."""
    return card_files(row.get("structured_data") or {}, production=row.get("home_view") == _PROD_VIEW)


def row_keys(row: dict[str, Any]) -> set[str]:
    """첫 화면 행의 지금 장 key 들(:func:`row_files`) — 아침 칩이 '지금 장' 줄만 세는 데 쓴다."""
    return {str(entry["key"]) for entry in row_files(row)}


def alarm_numbers(sd: Any) -> dict[str, Any]:
    """현장 알람이 읽는 ``{장 key: 도면 번호}`` — 확정 도면이 0장이면 ``{'@order': None}``(번호 없음 — 주문 카드 작업자도 받는다)."""
    keys = [entry["key"] for entry in resolve_final_drawing_files(sd if isinstance(sd, dict) else {})]
    return {key: no for no, key in enumerate(keys, 1)} if keys else {ORDER_CARD_KEY: None}


def has_order_rows(marks: Iterable[Any]) -> bool:
    """그 주문 표시 줄에 ``@order`` 줄이 있는지(상태 무관)."""
    return any(getattr(m, "drawing_key", None) == ORDER_CARD_KEY for m in marks)


__all__ = ["ORDER_CARD_KEY", "alarm_numbers", "card_files", "has_order_rows", "is_order_entry", "is_order_key",
           "order_card_mode", "order_entry", "row_files", "row_keys", "sheet_keys"]
