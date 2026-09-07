"""주문 1건이 **실측 전인가 후인가**를 한 곳에서 판정한다 (2026-09-07).

취소·반품이 들어왔을 때 담당자가 가장 먼저 알아야 하는 사실은 "이미 실측을 나갔나"다.
실측을 나갔으면 사람·차·시간이 이미 나간 것이라 회수·정산·응대가 전부 달라진다.
이 모듈은 그 판정과 **표시 문구를 한 벌만** 만든다(화면·알림이 같은 낱말을 쓰게).

무슨 신호를 왜 골랐나
---------------------
- 실측일 리더는 ``foms.services.measurement_dates.extract_all_measurement_dates`` 다.
  실측 대시보드·실측일 미정 목록·측정 API 가 전부 이 함수를 쓰고, 계약 테스트가
  "대시보드는 이 함수여야 한다"를 못박아 둔 이 저장소의 실측일 정본 리더다.
  이 함수는 ``schedule_dates`` 정규화 행 → ERP structured schedule → 레거시 컬럼 순으로
  합치므로 싱크 컬럼 ``Order.measurement_date`` 의 "첫 날짜만" 한계를 넘는다.
  그래서 싱크 컬럼도, ``measurement_time``(ERP 주문에서 전부 NULL)도 읽지 않는다.
- 날짜만 보면 그것은 "일정"이지 "방문"이 아니다(방문 취소·부재가 있다). 그래서
  사람이 직접 찍은 ``Order.measurement_completed`` 와 **진행 단계가 실측을 지났는지**를
  날짜보다 앞에 둔다. 이 둘은 ``after`` 만 올릴 뿐 ``before`` 를 증명하지 않는다
  (단계가 접수인데 실측일이 과거면 날짜 축이 ``after`` 를 낸다).
- 업무 의미가 "사람·차가 나갔나"이므로 **여러 일정 중 하나라도 과거면 ``after``** 다.
  첫 방문에 이미 비용이 나갔기 때문이다.

한계 (아는 척하지 않는다)
-------------------------
1. ``measurement_completed`` 는 자가실측·지방 4체크 흐름에서도 True 가 된다 —
   우리가 나간 것이 아닐 수 있다.
2. 진행 단계는 강제 변경으로 실제보다 앞서 있을 수 있다(단계 = 사실이 아니라 표시).
3. 모르면 ``none`` 이다. 화면·알림은 "실측일 없음"이라고 **모른다고 말한다**.
   날짜를 지어내지 않는다.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

from foms.services.datetime_kst import get_today_kst
from foms.services.measurement_dates import extract_all_measurement_dates
from foms.services.order_timeline_v3 import STAGE_SEQUENCE, STATUS_TO_STAGE
from foms.services.orders.erp_policy_constants import STAGE_NAME_TO_CODE

__all__ = [
    "MEASURE_AFTER",
    "MEASURE_BEFORE",
    "MEASURE_NONE",
    "MeasureProgress",
    "judge_measure_progress",
]


# 판정 축 코드 (화면 CSS 클래스 접미사로도 쓰인다).
MEASURE_AFTER = "after"
MEASURE_BEFORE = "before"
MEASURE_NONE = "none"

# 표시 낱말 — 사용자 원문 그대로 세 낱말만 쓴다.
_LABEL_BY_CODE: dict[str, str] = {
    MEASURE_AFTER: "실측 후",
    MEASURE_BEFORE: "실측 전",
    MEASURE_NONE: "실측일 없음",
}

# 무엇을 보고 그렇게 판정했는지 (화면 보조 줄).
_BASIS_TEXT: dict[str, str] = {
    "completed": "실측완료 표시",
    "stage": "진행 단계",
    "schedule": "실측 일정",
    "unknown": "",
}

# 진행 순서 SSOT 는 order_timeline_v3.STAGE_SEQUENCE 하나뿐이다 — 여기서 파생만 한다.
_STAGE_ORDER: dict[str, int] = {code: i for i, (code, _label, _token) in enumerate(STAGE_SEQUENCE)}
_MEASURE_ORDER: int = _STAGE_ORDER["MEASURE"]


@dataclass(frozen=True)
class MeasureProgress:
    """실측 전/후 판정 1건.

    Attributes:
        code: ``after`` / ``before`` / ``none``. 판정 축(화면 CSS 접미사 겸용).
        label: 표시 낱말 — ``실측 후`` / ``실측 전`` / ``실측일 없음``.
        date: 판정에 쓴 날짜 ISO(``2026-09-02``). 근거 날짜가 없으면 빈 문자열.
        basis: ``completed`` / ``stage`` / ``schedule`` / ``unknown``.
        basis_text: 근거 한글 표기(``unknown`` 이면 빈 문자열).
        text: 화면 한 줄 — 날짜는 ``MM-DD``.
        notice: 알림 한 문장 — 날짜는 ISO.
    """

    code: str
    label: str
    date: str
    basis: str
    basis_text: str
    text: str
    notice: str


def _screen_text(code: str, iso_date: str) -> str:
    """화면 한 줄 문구(MM-DD)."""
    label = _LABEL_BY_CODE[code]
    if not iso_date:
        # 날짜 근거가 없으면 날짜를 지어내지 않는다.
        return label
    short = iso_date[5:]  # YYYY-MM-DD → MM-DD
    if code == MEASURE_BEFORE:
        return f"{label} · {short} 예정"
    return f"{label} · {short}"


def _notice_text(code: str, iso_date: str) -> str:
    """알림 한 문장(ISO 날짜)."""
    if code == MEASURE_AFTER:
        if iso_date:
            return f"실측을 마친 뒤입니다(실측 {iso_date})."
        return "실측을 마친 뒤입니다."
    if code == MEASURE_BEFORE:
        if iso_date:
            return f"아직 실측 전입니다(실측 예정 {iso_date})."
        return "아직 실측 전입니다."
    return "실측 일정이 없어 실측 전인지 후인지 모릅니다."


def _build(code: str, basis: str, iso_date: str) -> MeasureProgress:
    """판정 결과를 문구까지 채워 만든다(문구 생성 자리는 여기 한 곳뿐)."""
    return MeasureProgress(
        code=code,
        label=_LABEL_BY_CODE[code],
        date=iso_date,
        basis=basis,
        basis_text=_BASIS_TEXT[basis],
        text=_screen_text(code, iso_date),
        notice=_notice_text(code, iso_date),
    )


def _stage_order(order: Any) -> int | None:
    """주문의 진행 단계를 표준 8단계 순번으로 접는다.

    ``structured_data['workflow']['stage']`` 가 우선이고 없으면 ``Order.status`` 다.
    한글 값은 ``STAGE_NAME_TO_CODE``, 코드 값은 ``STATUS_TO_STAGE`` 로 접는다.

    Returns:
        순번(0=접수 … 7=완료). **모르는 값이면 ``None``** — 이 축을 기권한다.
        (``order_timeline_v3._canonical_stage`` 는 미상을 RECEIVED 로 접으므로 쓰지 않는다.)
    """
    sd = getattr(order, "structured_data", None)
    raw: Any = None
    if isinstance(sd, dict):
        workflow = sd.get("workflow")
        if isinstance(workflow, dict):
            raw = workflow.get("stage")
    if not raw:
        raw = getattr(order, "status", None)
    token = str(raw or "").strip()
    if not token:
        return None

    code = STAGE_NAME_TO_CODE.get(token)
    if code is None:
        code = STATUS_TO_STAGE.get(token.upper())
    else:
        # AS 계열 등 8단계 밖 코드도 STATUS_TO_STAGE 로 한 번 더 접는다.
        code = STATUS_TO_STAGE.get(code, code)
    if code is None:
        return None
    return _STAGE_ORDER.get(code)


def judge_measure_progress(order: Any, *, today: datetime.date | None = None) -> MeasureProgress:
    """주문 1건이 실측 전인지 후인지 판정한다.

    판정 순서(먼저 맞는 것이 이긴다 — ``after`` 증거가 앞에 온다):
        1. ``order.measurement_completed`` 가 참이면 ``after`` (basis=``completed``)
        2. 진행 단계가 실측을 지났으면 ``after`` (basis=``stage``)
        3. 실측일 중 **하나라도 오늘 이하**면 ``after`` (basis=``schedule``,
           date=그중 가장 늦은 과거 날짜)
        4. 날짜가 있는데 전부 미래면 ``before`` (date=가장 이른 미래 날짜)
        5. 그 외에는 ``none``

    1·2 로 ``after`` 가 되고 과거 날짜도 있으면 ``date`` 에 그 날짜를 채운다.
    없으면 빈 문자열이고 화면은 날짜를 지어내지 않는다.

    Args:
        order: ``Order`` 또는 같은 속성을 가진 객체
            (``structured_data``·``schedule_dates``·``measurement_completed``·``status``).
        today: 기준일. ``None`` 이면 ``get_today_kst()``(KST 오늘, ``date`` 반환).

    Returns:
        MeasureProgress: 판정 코드·표시 낱말·근거·화면 문구·알림 문구 한 벌.

    Note:
        ``order.schedule_dates`` 관계를 읽는다. 목록에서 여러 건을 돌릴 때는 호출부가
        ``selectinload(Order.schedule_dates)`` 로 미리 적재해야 N+1 이 나지 않는다.
    """
    base_day = today if today is not None else get_today_kst()
    today_iso = base_day.isoformat()

    # 실측일 정본 리더 — 반환값은 이미 YYYY-MM-DD 로 정규화되어 있어 문자열 비교로 충분하다.
    dates = sorted(set(extract_all_measurement_dates(order) or []))
    past = [d for d in dates if d <= today_iso]
    future = [d for d in dates if d > today_iso]
    # 1·2 번 축이 이겼을 때 곁들일 날짜(있으면 가장 늦은 과거일).
    past_date = past[-1] if past else ""

    # ① 사람이 찍은 실측완료 표시가 가장 강한 증거다.
    if bool(getattr(order, "measurement_completed", False)):
        return _build(MEASURE_AFTER, "completed", past_date)

    # ② 진행 단계가 실측을 지났으면 실측은 끝난 것으로 본다(모르는 단계는 기권).
    order_index = _stage_order(order)
    if order_index is not None and order_index > _MEASURE_ORDER:
        return _build(MEASURE_AFTER, "stage", past_date)

    # ③ 일정 중 하나라도 오늘 이하면 이미 나간 것이다.
    if past:
        return _build(MEASURE_AFTER, "schedule", past[-1])

    # ④ 날짜가 전부 미래면 아직 안 나갔다.
    if future:
        return _build(MEASURE_BEFORE, "schedule", future[0])

    # ⑤ 근거가 없다 — 모른다고 말한다.
    return _build(MEASURE_NONE, "unknown", "")
