"""시공일 안내 알림톡의 할 일 함수(설계서 2026-11-14-foms-graft 3.6 · 3.13 · D208 · D213).

- 할 일 ``send_construction_alimtalk`` 의 ``check`` · ``preview`` · ``verify`` · ``steps`` · ``ran`` — :mod:`.preview` 의 이름 → 함수
  표(``FUNCTIONS``)가 이 함수들을 잇는다.
- 시공일 두 할 일(``schedule_construction`` · ``move_construction``)의 넣을 값 ``notify_customer`` 줄 — 쓸 수 있는 상태
  (:func:`foms.services.kakao_alimtalk_construction.order_block` 이 ``None``) · 넣을 값 참 · 그 시공일로 아직 안 나감일 때만
  '바뀌는 칸'(:func:`notice_rows`)과 '승인하면 차례로'(:func:`notice_steps`)에 '손님 알림톡 1건 — 시공일 안내'가 붙는다.
- 순수 함수다(주문 줄 하나와 넣을 값만 — DB 질의 없음). 보내기는 :mod:`foms.services.kakao_alimtalk_construction`.
- 화면 말은 코드가 정한 말 + 날짜뿐 — 손님 이름 · 전화 · 주소 · 시공 팀 · 인원 없음(D211).
"""

from __future__ import annotations

import datetime
from typing import Any, Mapping, Optional

from foms.services import kakao_alimtalk as kakao
from foms.services import kakao_alimtalk_construction as notice
from foms.services.datetime_kst import format_datetime_kst, get_today_kst
from foms.services.erp_actions.registry import NOTIFY_CUSTOMER

__all__ = [
    "FIELD", "NOTIFY_PARAM", "REASONS", "STEP", "action_key", "check", "day_of", "notice_rows", "notice_steps",
    "notice_wanted", "param_shown", "preview", "ran", "steps", "verify",
]

NOTIFY_PARAM = NOTIFY_CUSTOMER.name
FIELD = "손님 알림톡(시공일 안내)"
STEP = "손님 알림톡 1건 — 시공일 안내"
_AFTER = "1건 보냄"
_WEEKDAYS = "월화수목금토일"
#: 나가지 않는 까닭 코드 → 승인 창 말.
REASONS: dict[str, str] = {
    "order_not_found": "주문을 찾을 수 없어요.", "partner_order": "협력사 주문은 협력사가 손님에게 알려요.",
    "not_eligible": "아직 등록 전인 초안 주문이에요.", "disabled": "시공일 안내 알림톡이 아직 꺼져 있어요.",
    "not_configured": "알림톡 설정이 없어 보낼 수 없어요.", "brand_profile_missing": "이 브랜드 시공일 안내 서식이 아직 없어요.",
    "no_valid_phone": "손님 휴대폰 번호가 없어 보낼 수 없어요.", "no_construction_date": "시공일이 없어 보낼 수 없어요.",
}

Params = Mapping[str, Any]


def _sd(order: Any) -> dict[str, Any]:
    data = getattr(order, "structured_data", None)
    return data if isinstance(data, dict) else {}


def _label(value: Any) -> str:
    """'YYYY-MM-DD…' → '11-20(금)'(못 읽으면 빈 글) — :func:`.preview.date_label` 과 같은 꼴."""
    try:
        day = datetime.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return ""
    return f"{day:%m-%d}({_WEEKDAYS[day.weekday()]})"


def day_of(value: Any) -> Optional[str]:
    """날짜 글(여러 날 · 쉼표 허용) → 이력 · 열쇠의 시공일 꼴(``YYYY-MM-DD`` 를 ``|`` 로 이음). 없으면 ``None``."""
    dates = kakao.valid_dates(value)
    return "|".join(dates) if dates else None


def action_key(order_id: int, day: Optional[str], proposal_id: int) -> str:
    """중복 막기 열쇠 ``alimtalk:construction:<주문>:<시공일>:action:<제안 번호>``(설계서 3.13 '한 번만')."""
    return f"alimtalk:construction:{int(order_id)}:{day or '-'}:action:{int(proposal_id)}"


def _before(order: Any) -> str:
    """마지막 이력 — '<보낸 날> 보냄' · '못 보냄' · '보낸 적 없음'."""
    record = notice.last_record(_sd(order))
    if record.get("sent_at") and record.get("error") is None and record.get("message_id"):
        return f"{_label(format_datetime_kst(record.get('sent_at'), '%Y-%m-%d')) or '전에'} 보냄"
    return "못 보냄" if record.get("error") else "보낸 적 없음"


# ── 시공일 두 할 일의 notify_customer 줄 ───────────────────────────────────
def notice_wanted(order: Any, params: Params) -> bool:
    """승인하면 시공일 쓰기 뒤 손님에게 시공일 안내가 나가나 — 넣을 값 참 · 쓸 수 있는 상태 · 그 날로 아직 안 나감."""
    if params.get(NOTIFY_PARAM) is not True:
        return False
    day = day_of(params.get("date"))
    return bool(day) and notice.order_block(order) is None and not notice.sent_for(_sd(order), day)


def notice_rows(order: Any, params: Params) -> list[dict[str, str]]:
    """'바뀌는 칸'에 더할 줄(나가지 않으면 빈 목록)."""
    return [{"field": FIELD, "before": _before(order), "after": _AFTER}] if notice_wanted(order, params) else []


def notice_steps(order: Any, params: Params) -> list[str]:
    """'승인하면 차례로'에 더할 줄(나가지 않으면 빈 목록)."""
    return [STEP] if notice_wanted(order, params) else []


def param_shown(action: Any, name: str, order: Any) -> bool:
    """승인 창에 넣을 값 칸을 그릴까 — ``notify_customer`` 는 쓸 수 있는 상태인 주문에서만, 그 밖의 칸은 늘."""
    return name != NOTIFY_PARAM or notice.order_block(order) is None


# ── 할 일 send_construction_alimtalk ────────────────────────────────────
def check(order: Any, _params: Params) -> Optional[str]:
    """막는 까닭 — 나가는 조건(:func:`notice.block_reason`) · 시공일이 모두 지남 · 그 시공일로 이미 나감."""
    code = notice.block_reason(order)
    if code is not None:
        return REASONS.get(code, "알림톡을 보낼 수 없는 주문이에요.")
    sd = _sd(order)
    day = notice.construction_day(sd)
    if str(day).split("|")[-1] < get_today_kst().isoformat():
        return "시공일이 지났어요."
    return "이 시공일 안내는 이미 보냈어요." if notice.sent_for(sd, day) else None


def preview(order: Any, _params: Params) -> list[dict[str, str]]:
    """바뀌는 칸 — 손님 알림톡(시공일 안내) '<지난 이력>' → '1건 보냄'."""
    return [{"field": FIELD, "before": _before(order), "after": _AFTER}]


def verify(order: Any, _params: Params) -> bool:
    """끝난 조건 — 지금 시공일로 손님에게 나갔다."""
    sd = _sd(order)
    return notice.sent_for(sd, notice.construction_day(sd))


def steps(_order: Any, _params: Params) -> list[str]:
    """승인하면 차례로 — 감싼 기능이 하는 일만."""
    return [f"{STEP}(시공일 · 시간대만)"]


def ran(order: Any, _params: Params, proposal_id: int) -> bool:
    """이 제안이 보낸 흔적 — 마지막 이력이 나감이고 열쇠가 이 제안의 것."""
    record = notice.last_record(_sd(order))
    day = record.get("construction_date")
    return notice.sent_for(_sd(order), day) and record.get("dedupe_key") == action_key(order.id, day, proposal_id)
