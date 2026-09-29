"""도면 탭 '고객에게 보내기' — 회차 함수와 작업실 화면값(설계서 2026-09-29 §4.3 · §4.4 · §4.5).

S1a 뼈대: 회차 함수 ``drawing_round_info`` 와 모든 화면값 키를 빈 값으로 채운
``empty_customer_send_view``. 상세 ctx 는 늘 ``customer_send`` 를 싣는다 — Jinja 기본
Undefined 는 없는 변수의 속성을 읽는 순간 오류라, S2·S3 템플릿이 먼저 합쳐져도 500 이 나지 않게.
발송·열람 판정과 버튼 목록(``bar``) 채우기는 S1 이 이 모듈에 더한다.

회차 규칙(사용자 결정 Q2): 전달이 없으면 0, 있으면 1 + 마지막 TRANSFER 앞의 REQUEST_REVISION 수.
수정요청 없이 더 올린 전달은 같은 회차의 추가 전달이다. 수정요청 취소는 요청 항목을 이력에서
빼고(REVISION_CANCELLED 로 보존) 전달 취소는 최신 TRANSFER 를 빼기만 하므로, 이력을 그대로
세면 두 취소가 자동으로 반영된다.
"""

from __future__ import annotations

from typing import Any, Mapping, NamedTuple

# 버튼 목록 항목 키(PC 결정 바 · 모바일 하단 바가 같은 목록을 순회한다, §3.0 + Q5).
BAR_KEYS: tuple[str, ...] = (
    "send", "resend", "rev_customer", "rev_sales", "ok", "ok_no_customer", "rev_post",
    "approve_confirm", "production", "cancel_revision", "edit_revision", "urgent_call",
)
# 버튼 목록 항목 하나의 필드. slot 은 "main" | "more"(모바일 바 넘침 규칙, §3.0).
BAR_ITEM_FIELDS: tuple[str, ...] = ("key", "label", "tone", "slot")

# 스위치 꺼짐 = 지금 고정 표 이름(foms/api/share.py _SMS_KIND_LABEL 과 같은 글자).
_DEFAULT_DOC_LABEL_DRAWING = "도면"
_DEFAULT_DOC_LABEL_BUNDLE = "도면·계약서"


class RoundInfo(NamedTuple):
    round: int
    round_at: str
    transfer_count: int
    is_append: bool
    revisions_before: int


def _history(sd: Mapping[str, Any] | None) -> list[dict]:
    if not isinstance(sd, Mapping):
        return []
    raw = sd.get("drawing_transfer_history")
    if not isinstance(raw, list):
        return []
    return [h for h in raw if isinstance(h, dict)]


def _transfer_at(entry: Mapping[str, Any]) -> str:
    return str(entry.get("transferred_at") or entry.get("at") or "").strip()


def drawing_round_info(sd: Mapping[str, Any] | None) -> RoundInfo:
    """이력 한 번 훑어 지금 회차를 정한다(화면의 모든 "N차"와 고객 문서 이름이 이 함수 하나)."""
    history = _history(sd)
    transfer_idx = [i for i, h in enumerate(history) if h.get("action") == "TRANSFER"]
    if not transfer_idx:
        return RoundInfo(round=0, round_at="", transfer_count=0, is_append=False, revisions_before=0)
    last = transfer_idx[-1]
    revisions_before = sum(1 for h in history[:last] if h.get("action") == "REQUEST_REVISION")
    is_append = False
    if len(transfer_idx) > 1:
        prev = transfer_idx[-2]
        is_append = not any(h.get("action") == "REQUEST_REVISION" for h in history[prev + 1:last])
    return RoundInfo(
        round=1 + revisions_before,
        round_at=_transfer_at(history[last]),
        transfer_count=len(transfer_idx),
        is_append=is_append,
        revisions_before=revisions_before,
    )


def round_text(round_no: int) -> str:
    """"2차"(0 이면 "")."""
    return f"{round_no}차" if round_no > 0 else ""


def empty_customer_send_view() -> dict[str, Any]:
    """``customer_send`` 의 모든 키를 빈 값으로(새 버튼·줄은 하나도 안 보인다). 부를 때마다 새 객체."""
    return {
        # 회차(§4.3)
        "round": 0,
        "round_text": "",
        "round_at": "",
        "is_append": False,
        "arrived_at_text": "",
        "arrival_label": "",
        # 보내기 가능·번호(§4.5, Q5-②)
        "can_send": False,
        "has_phone": False,
        "phone_masked": "",
        "can_change_phone": False,
        "can_save_phone": False,
        # 이번 회차 발송·열람(§4.4)
        "sent_this_round": False,
        "sent_text": "",
        "link_only_text": "",
        "failed_text": "",
        "views": 0,
        "last_viewed_text": "",
        "status_line": "",
        "turn_hint": "",
        "steps": [],
        "prev_summary": "",
        # 시트 미리보기(§3.5 가)
        "doc_label_drawing": _DEFAULT_DOC_LABEL_DRAWING,
        "doc_label_bundle": _DEFAULT_DOC_LABEL_BUNDLE,
        "bundle_both_template": False,
        # 고객 OK · 컨펌(§3.5 나)
        "can_customer_ok": False,
        "can_approve_after_confirm": False,
        # 버튼 목록(§3.0 + Q5)
        "bar": [],
        # 요청 고치기 미리 채움(Q5-③)
        "edit_revision": {},
        # 전달 취소 경고(§3.4)
        "cancel_warning_text_pc": "",
        "cancel_warning_text_mobile": "",
    }


CUSTOMER_SEND_KEYS: tuple[str, ...] = tuple(empty_customer_send_view())


def skeleton_customer_send_view(sd: Mapping[str, Any] | None) -> dict[str, Any]:
    """빈 화면값 + 회차 값만(S1a). S1 의 build_customer_send_view 가 이 자리를 대신한다."""
    view = empty_customer_send_view()
    info = drawing_round_info(sd)
    view.update(
        round=info.round,
        round_text=round_text(info.round),
        round_at=info.round_at,
        is_append=info.is_append,
    )
    return view
