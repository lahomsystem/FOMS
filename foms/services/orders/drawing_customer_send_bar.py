"""도면 탭 버튼 목록 ``customer_send.bar`` — PC 결정 바와 모바일 하단 바가 같이 순회한다.

설계서 2026-09-29 §3.0 표(영업 쪽) + 사용자 결정 Q5 ①③(도면팀 PC 긴급 호출 ``urgent_call`` ·
영업의 요청 고치기 ``edit_revision``)를 서버가 **한 번** 판정한다. 두 표면이 같은 조건을 각자
Jinja 로 쓰면 반드시 한쪽이 어긋난다(2차 M14 사례).

항목은 ``{key, label, tone, slot}`` 네 필드다(``BAR_ITEM_FIELDS``).

* ``tone``: ``primary``(주 버튼 · 파랑) · ``success``(주 버튼 · 초록) · ``warning`` · ``secondary`` ·
  ``link``(화면 이동 링크) · ``urgent``(긴급 호출). 모양은 표면이 정한다.
* ``slot``: 모바일 바 넘침 규칙. 모바일 바는 도면 쪽 버튼(전달·전달 취소 — 템플릿이 따로 그림)을
  합쳐 앞 3칸만 바에 두고 나머지는 [더 보기]로. 우선순위는 도면 쪽 버튼 → 영업 쪽 주 버튼 →
  나머지 목록 순서. 영업 쪽 주 버튼 하나는 늘 ``main`` 이다. PC 결정 바는 세로라 slot 을 무시한다.
* ``urgent_call`` 은 도면 쪽(도면 담당·도면팀·관리자) PC 전용이다. 모바일 바는 긴급 호출을 이미
  자기 블록(``[data-foms-urgent-call]``)으로 그리므로 이 항목을 건너뛴다. slot 은 늘 ``main``.
"""
from __future__ import annotations

from typing import Any

from foms.services.orders.confirm_drawing_gate import normalize_stage_code

#: 키 → (라벨, 톤). 라벨은 모바일 기준 짧은 이름이다(PC 는 표면에서 길게 바꿀 수 있다).
_LABELS: dict[str, tuple[str, str]] = {
    "send": ("고객에게 보내기", "primary"),
    "resend": ("다시 보내기", "secondary"),
    "rev_customer": ("고객이 고쳐 달래요", "warning"),
    "rev_sales": ("내 의견", "secondary"),
    "ok": ("고객 OK · 확정", "success"),
    "ok_no_customer": ("확정", "secondary"),
    "rev_post": ("고객이 또 바꿔 달래요", "warning"),
    "approve_confirm": ("고객 컨펌하고 생산으로", "success"),
    "production": ("생산 현황 보기", "link"),
    "cancel_revision": ("수정요청 취소", "secondary"),
    "edit_revision": ("요청 고치기", "secondary"),
    "urgent_call": ("긴급 호출", "urgent"),
}

#: 모바일 바에 두는 칸 수(도면 쪽 버튼 포함, 긴급 호출 제외).
MOBILE_BAR_MAIN_SLOTS = 3


def _item(key: str, *, tone: str | None = None) -> dict[str, str]:
    label, default_tone = _LABELS[key]
    return {"key": key, "label": label, "tone": tone or default_tone, "slot": "main"}


def _sales_items(
    *, drawing_status: str, stage_code: str, can_send: bool, sent_this_round: bool,
    can_confirm_receipt: bool, can_cancel_revision: bool, can_edit_revision: bool,
    can_approve_after_confirm: bool,
) -> tuple[list[dict[str, str]], str | None]:
    """영업 쪽 버튼(§3.0 표 순서)과 주 버튼 키."""
    status = (drawing_status or "").upper()
    items: list[dict[str, str]] = []
    primary: str | None = None
    if status == "TRANSFERRED":
        if sent_this_round:
            if can_send:
                items.append(_item("resend"))
            items.append(_item("rev_customer"))
            if can_confirm_receipt:
                items.append(_item("ok"))
                primary = "ok"
        else:
            items.append(_item("rev_sales"))
            if can_send:
                items.append(_item("send"))
                primary = "send"
            if can_confirm_receipt:
                items.append(_item("ok_no_customer"))
    elif status == "RETURNED":
        if can_edit_revision:
            items.append(_item("edit_revision"))
        if can_cancel_revision:
            items.append(_item("cancel_revision"))
    elif status == "CONFIRMED":
        items.append(_item("rev_post"))
        if can_send:
            items.append(_item("send", tone="secondary"))
        if normalize_stage_code(stage_code) == "CONFIRM" and can_approve_after_confirm:
            items.append(_item("approve_confirm"))
            primary = "approve_confirm"
        else:
            items.append(_item("production"))
    if primary is None and items:
        primary = items[0]["key"]
    return items, primary


def _assign_slots(items: list[dict[str, str]], primary: str | None, drawing_mobile_buttons: int) -> None:
    capacity = max(1, MOBILE_BAR_MAIN_SLOTS - max(0, int(drawing_mobile_buttons or 0)))
    order = sorted(range(len(items)), key=lambda i: (0 if items[i]["key"] == primary else 1, i))
    for rank, idx in enumerate(order):
        items[idx]["slot"] = "main" if rank < capacity else "more"


def build_customer_send_bar(
    *,
    drawing_status: str,
    stage_code: Any,
    sales_side: bool,
    can_send: bool,
    sent_this_round: bool,
    can_confirm_receipt: bool,
    can_cancel_revision: bool,
    can_edit_revision: bool,
    can_approve_after_confirm: bool,
    show_urgent_call: bool,
    drawing_mobile_buttons: int,
) -> list[dict[str, str]]:
    """버튼 목록을 만든다.

    Args:
        drawing_status: 판정 정본 도면 상태(``effective_drawing_status``).
        stage_code: 주문 단계값(영문·한글 모두 받는다).
        sales_side: 영업 쪽인가(``is_admin or (can_sales_domain and not is_drawing_team)``).
        can_send: 영업 쪽 + TRANSFERRED·CONFIRMED + 현재 도면 1장 이상.
        sent_this_round: 이번 회차 표지와 같은 성공 발송이 있나.
        can_confirm_receipt: 지금 화면의 수령 확정 판정(상태 TRANSFERRED 포함).
        can_cancel_revision: 수정요청 취소 권한(상태는 여기서 RETURNED 로 본다).
        can_edit_revision: 요청 고치기 가능(RETURNED · 반영 체크 전 · 요청자/배정 영업/관리자).
        can_approve_after_confirm: 확정 뒤 고객 컨펌 승인 예측(승인 라우트와 같은 quest 고르기).
        show_urgent_call: 도면 쪽 PC 긴급 호출을 보이나.
        drawing_mobile_buttons: 모바일 바에 템플릿이 따로 그리는 도면 쪽 버튼 수(전달·전달 취소).

    Returns:
        ``[{key, label, tone, slot}]``.
    """
    items: list[dict[str, str]] = []
    if sales_side:
        items, primary = _sales_items(
            drawing_status=drawing_status, stage_code=str(stage_code or ""), can_send=can_send,
            sent_this_round=sent_this_round, can_confirm_receipt=can_confirm_receipt,
            can_cancel_revision=can_cancel_revision, can_edit_revision=can_edit_revision,
            can_approve_after_confirm=can_approve_after_confirm,
        )
        _assign_slots(items, primary, drawing_mobile_buttons)
    if show_urgent_call:
        items.append(_item("urgent_call"))
    return items


__all__ = ["MOBILE_BAR_MAIN_SLOTS", "build_customer_send_bar"]
