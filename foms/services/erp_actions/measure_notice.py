"""실측 예약 알림톡의 할 일 함수(설계서 2026-11-14-foms-graft 3.4 · 3.10 O1 · 점검 2차 w6-01).

- 할 일 ``send_measure_alimtalk`` 의 ``preview`` · ``verify`` · ``steps`` · ``ran`` · ``deadline`` · ``scope`` 와 막는 조건의 뒤쪽
  (:func:`check` — 실측일이 지났나 · 지금 일정으로 이미 나갔나)을 둔다. :mod:`.preview` 의 이름 → 함수 표(``FUNCTIONS``)가 잇는다.
  막는 조건의 앞쪽(삭제 · 초안 · 발송 자격 — ``kakao_alimtalk._ineligible_reason``)은 :mod:`.preview` 에 그대로 있다.
- 시공일 안내(:mod:`.construction_notice`)와 같은 두 막이: 실측일(여러 날이면 마지막 날)이 한국 오늘보다 앞이면 '실측일이 지났어요',
  지금 실측 일정으로 손님에게 나간 기록(:func:`measure_sent`)이 있으면 '이미 보냈어요'. 승인 첫 걸음 · 실행기가 지금 주문을 다시 읽어
  이 판정을 돈다 — 제안 승인은 주문 화면 손 발송 단추('누른 만큼 나간다' 계약)가 아니다. 그 단추와 자동 발송은 건드리지 않는다.
- 기간 끝(:func:`deadline`)은 실측일이 끝나는 때(한국 자정) — 넣을 값이 비어도 7일이 아니다. 겹침 열쇠 상황(:func:`scope`)은 자동
  발송 열쇠(실측 일정 · 시간)라 일정이 바뀌면 옛 제안은 낡은 것이 된다(:mod:`.freshness`).
- 순수 함수다(주문 줄 하나와 넣을 값만 — DB 질의 없음). 화면 말은 코드가 정한 말 + 날짜뿐(손님 이름 · 전화 없음).
"""

from __future__ import annotations

import datetime
from typing import Any, Mapping, Optional

from foms.services import kakao_alimtalk as kakao
from foms.services.datetime_kst import format_datetime_kst, get_today_kst

__all__ = [
    "FIELD", "PAST", "SENT", "STEP", "action_key", "check", "deadline", "last_day", "measure_sent", "preview", "ran",
    "record", "scope", "sent", "steps", "verify",
]

FIELD = "손님 알림톡(실측 예약)"
STEP = "손님 알림톡 1건 — 실측 예약 안내(지금 있는 서식 그대로)"
PAST = "실측일이 지났어요."
SENT = "이 실측 예약 안내는 이미 보냈어요."
_WEEKDAYS = "월화수목금토일"

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


def action_key(order_id: int, proposal_id: int) -> str:
    """할 일 알림톡의 중복 막기 열쇠 — ``alimtalk:measure:<주문>:action:<제안 번호>``(설계서 3.4 '한 번만')."""
    return f"alimtalk:measure:{int(order_id)}:action:{int(proposal_id)}"


def record(order: Any) -> dict[str, Any]:
    """실측 예약 알림톡 마지막 기록(``structured_data.alimtalk_measurement`` — 없으면 빈 dict)."""
    value = _sd(order).get("alimtalk_measurement")
    return value if isinstance(value, dict) else {}


def sent(value: Mapping[str, Any]) -> bool:
    """기록이 '나감'인가 — 보낸 때 · 벤더 번호 있음 · 오류 없음."""
    return bool(value.get("sent_at")) and value.get("error") is None and bool(value.get("message_id"))


def measure_sent(order_id: int, sd: dict[str, Any]) -> bool:
    """지금 실측 일정으로 실측 예약 알림톡이 손님에게 나갔나(훑기 규칙 O1 · 승인 막는 조건이 같이 쓴다).

    나감 = :func:`sent`. 실패 · 건너뜀 기록은 안 보냄이다. 일정은 기록이 가진 만큼 견준다 — 자동 발송 열쇠
    (``alimtalk:measure:<주문>:<날짜>:<시간>``)는 지금 일정의 열쇠와 같아야, 마법사 초안 이력은 ``draft_schedule`` 이 지금 일정
    서명과 같아야 한다. 사람이 누른 발송(``manual`` · 할 일 ``action`` 열쇠)은 일정을 싣지 않아 나감 그대로 본다(손님에게 두 번
    가지 않는 쪽으로 — 원장 F-19).
    """
    value = sd.get("alimtalk_measurement")
    if not isinstance(value, dict) or not sent(value):
        return False
    if value.get("draft_schedule") is not None:
        return value.get("draft_schedule") == kakao.build_draft_schedule_signature(sd)
    key = str(value.get("dedupe_key") or "")
    if key.startswith((f"alimtalk:measure:{order_id}:manual:", f"alimtalk:measure:{order_id}:action:")):
        return True
    return bool(key) and key == kakao.build_dedupe_key(order_id, sd)


def last_day(sd: dict[str, Any]) -> Optional[str]:
    """실측 일정의 마지막 날 'YYYY-MM-DD'(자동 발송과 같은 정규화 — 못 읽으면 ``None``)."""
    schedule = kakao.normalize_measure_schedule(sd)
    return schedule[0].split("|")[-1] if schedule else None


def check(order: Any) -> Optional[str]:
    """막는 조건의 뒤쪽 — 실측일(마지막 날)이 지났거나 지금 일정으로 이미 나갔으면 그 까닭, 아니면 ``None``.

    앞쪽(삭제 · 초안 · 발송 자격)은 :func:`.preview.check` 가 먼저 본다. 실측일을 못 읽으면 이 판정은 지나간다(발송 자격이
    '실측 날짜가 없어 보낼 수 없어요'로 막는다).
    """
    sd = _sd(order)
    day = last_day(sd)
    if day is not None and day < get_today_kst().isoformat():
        return PAST
    return SENT if measure_sent(int(order.id), sd) else None


def preview(order: Any, _params: Params) -> list[dict[str, str]]:
    """바뀌는 칸 — 손님 알림톡(실측 예약) '<지난 기록>' → '1건 보냄'."""
    value = record(order)
    if sent(value):
        before = f"{_label(format_datetime_kst(value.get('sent_at'), '%Y-%m-%d')) or '전에'} 보냄"
    else:
        before = "못 보냄" if value.get("error") else "보낸 적 없음"
    return [{"field": FIELD, "before": before, "after": "1건 보냄"}]


def verify(order: Any, _params: Params) -> bool:
    """끝난 조건 — 마지막 기록이 나감."""
    return sent(record(order))


def steps(_order: Any, _params: Params) -> list[str]:
    """승인하면 차례로 — 감싼 기능이 하는 일만."""
    return [STEP]


def ran(order: Any, _params: Params, proposal_id: int) -> bool:
    """이 제안이 보낸 흔적 — 마지막 기록이 나감이고 열쇠가 이 제안의 것."""
    value = record(order)
    return sent(value) and value.get("dedupe_key") == action_key(order.id, proposal_id)


def deadline(order: Any, _params: Params) -> Optional[str]:
    """제안 기간이 끝나는 날 — 실측일(마지막 날). 그 날 한국 자정에 기간이 끝난다(못 읽으면 ``None`` — 7일)."""
    return last_day(_sd(order))


def scope(order: Any) -> str:
    """겹침 열쇠 상황 — 지금 실측 일정의 자동 발송 열쇠(일정이 없으면 ``'measure'``). 훑기 규칙 O1 이 쓰던 값과 같다."""
    return kakao.build_dedupe_key(int(order.id), _sd(order)) or "measure"
