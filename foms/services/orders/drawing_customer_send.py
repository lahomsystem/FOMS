"""도면 탭 '고객에게 보내기' — 회차 함수와 작업실 화면값(설계서 2026-09-29 §4.3 · §4.4 · §4.5).

회차 함수 ``drawing_round_info`` 와 모든 화면값 키를 빈 값으로 채운 ``empty_customer_send_view``,
그리고 고객 문서 이름(``share_doc_label`` · ``share_round_label``)·발송 이벤트 표지
(``send_event_tags``)·이번 발송 번호(``resolve_send_phone``, 사용자 결정 Q5-②)를 둔다. 발송·열람
판정과 화면값 채우기는 ``drawing_customer_send_view``, 버튼 목록은 ``drawing_customer_send_bar``.
상세 ctx 는 늘 ``customer_send`` 를 싣는다 — Jinja 기본 Undefined 는 없는 변수의 속성을 읽는
순간 오류라 모든 키가 늘 있어야 한다.

회차 규칙(사용자 결정 Q2): 전달이 없으면 0, 있으면 1 + 마지막 TRANSFER 앞의 REQUEST_REVISION 수.
수정요청 없이 더 올린 전달은 같은 회차의 추가 전달이다. 수정요청 취소는 요청 항목을 이력에서
빼고(REVISION_CANCELLED 로 보존) 전달 취소는 최신 TRANSFER 를 빼기만 하므로, 이력을 그대로
세면 두 취소가 자동으로 반영된다.
"""

from __future__ import annotations

import os
from typing import Any, Mapping, NamedTuple

from foms.services import kakao_alimtalk as ka

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
        # 추가 전달 뒤: 같은 회차 앞 전달분을 보낸 시각·경로("11:52 알림톡"). 없으면 "".
        "sent_earlier_text": "",
        # 이번 회차 마지막 시도 결과 — "sent" | "failed" | "unsure"(network·보내는 중) | ""(시도 없음).
        "last_attempt_state": "",
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


# ── 고객 문서 이름(알림톡 ``#{문서종류}`` · 문자 본문 · 공유 화면 제목, §4.3 · Q3 · Q6) ──────────
#: ``"1"`` 일 때만 켜진다. 없거나 다른 값이면 지금 고정 표 그대로(배포 없이 되돌리기).
SHARE_ROUND_DOC_LABEL_ENV = "FOMS_SHARE_ROUND_DOC_LABEL"

#: 스위치 꺼짐 표(``foms/api/share.py`` 옛 ``_SMS_KIND_LABEL`` 과 같은 글자).
_FIXED_DOC_LABELS = {"drawing": _DEFAULT_DOC_LABEL_DRAWING, "estimate": "견적서",
                     "bundle": _DEFAULT_DOC_LABEL_BUNDLE}


def round_doc_label_enabled() -> bool:
    """회차 이름 스위치가 켜졌나(``FOMS_SHARE_ROUND_DOC_LABEL == "1"``)."""
    return (os.getenv(SHARE_ROUND_DOC_LABEL_ENV) or "").strip() == "1"


def share_doc_label(sd: Mapping[str, Any] | None, kind: str) -> str:
    """고객에게 보이는 문서 이름. 스위치가 켜지고 회차 2 이상이면 "수정 도면(N차)"."""
    fixed = _FIXED_DOC_LABELS.get(kind, "문서")
    if kind not in ("drawing", "bundle") or not round_doc_label_enabled():
        return fixed
    info = drawing_round_info(sd)
    if info.round < 2:
        return fixed
    drawing = f"수정 도면({info.round}차)"
    return drawing if kind == "drawing" else f"{drawing}·계약서"


def share_round_label(sd: Mapping[str, Any] | None) -> str:
    """공유 화면 제목 앞 회차("2차", Q3) — 스위치가 켜지고 회차 2 이상일 때만, 아니면 ""."""
    if not round_doc_label_enabled():
        return ""
    info = drawing_round_info(sd)
    return round_text(info.round) if info.round >= 2 else ""


# ── 발송 이벤트 표지(§4.4) · 이번 발송 번호(Q5-②) ─────────────────────────────────────────────
#: 발송 본문 ``source_screen`` 으로 받는 값(목록 밖이면 키를 넣지 않는다).
SEND_SOURCE_SCREENS: tuple[str, ...] = ("drawing_tab",)

#: 보내기 창에서 바꾼 번호가 틀렸을 때의 오류 코드(발송 라우트 400).
INVALID_PHONE = "INVALID_PHONE"


def send_event_tags(sd: Mapping[str, Any] | None, body: Any) -> dict[str, Any]:
    """발송 선점 이벤트 payload 에 박을 회차 표지 ``{round_at, round[, source_screen]}``.

    회차 경계는 이력 시각이 아니라 이 표지로 판정한다 — 전달 취소는 최신 TRANSFER 를 이력에서
    빼기만 하므로, 시각만 비교하면 취소된 회차에 보낸 것이 앞 회차 발송으로 잡힌다.
    """
    info = drawing_round_info(sd)
    tags: dict[str, Any] = {"round_at": info.round_at, "round": info.round}
    screen = body.get("source_screen") if isinstance(body, Mapping) else None
    if isinstance(screen, str) and screen in SEND_SOURCE_SCREENS:
        tags["source_screen"] = screen
    return tags


def resolve_send_phone(sd: Mapping[str, Any] | None, body: Any) -> tuple[str | None, bool, str | None]:
    """이번 발송 수신 번호. 본문 ``to_phone`` 이 있으면 그 번호(이번 발송에만), 없으면 주문 번호.

    ``to_phone`` 은 주문 번호와 같은 정규화·검증 규칙(:func:`ka.extract_valid_phone`)으로 본다.

    Returns:
        ``(숫자만 남긴 번호, 바꾼 번호인가, 오류 코드)``. 바꾼 번호가 틀리면
        ``(None, False, "INVALID_PHONE")``, 주문 번호가 없으면 ``(None, False, "no_valid_phone")``.
    """
    raw = body.get("to_phone") if isinstance(body, Mapping) else None
    if raw is not None and not (isinstance(raw, str) and not raw.strip()):
        if not isinstance(raw, str):
            return None, False, INVALID_PHONE
        phone = ka.extract_valid_phone({"parties": {"customer": {"phone": raw}}})
        return (phone, True, None) if phone else (None, False, INVALID_PHONE)
    phone = ka.extract_valid_phone(dict(sd or {}))
    return (phone, False, None) if phone else (None, False, "no_valid_phone")
