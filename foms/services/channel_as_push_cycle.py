"""AS PUSH 가 다시 보내기인지, 새 AS 건의 첫 PUSH 인지 — 판정 하나.

AS PUSH 이력 칸(``structured_data['channeltalk_push_as']``)은 주문마다 하나다. 이력의 ``pushed`` 만 보면
둘째 AS 건의 첫 PUSH 가 "[수정] 다시 보내기"가 되어 바뀐 내용을 강요한다. 그래서 이력에 보낸 건
(``as_cycle_id``)을 같이 적고, 지금 건과 견줘 가른다. 본사 AS PUSH(미리 보기 · 전송)와 협력사 AS 접수 PUSH,
도면 작업실 AS 카드가 이 함수 하나를 쓴다 — 판정이 갈리면 미리 본 글과 나간 글이 달라진다.

설계서: docs/specs/2026-11-20-multi-item-split-schedule_SPEC.md §7.1 (결정 M18)
"""
from __future__ import annotations

import datetime
from typing import Any, NamedTuple

from foms.services.channel_as_message import build_as_push_text
from foms.services.orders.as_cycle_service import current_cycle
from foms.services.orders.as_cycle_view import current_cycle_ordinal, is_history_unknown

__all__ = [
    "PUSH_HISTORY_KEY",
    "AsPushVerdict",
    "compose_as_push",
    "judge_as_push",
    "parse_utc",
]

#: AS PUSH 이력 칸 — ``channel_integration._PUSH_KIND_CONFIG['as']['history_key']`` 와 같은 칸.
PUSH_HISTORY_KEY = "channeltalk_push_as"


class AsPushVerdict(NamedTuple):
    """AS PUSH 한 번의 판정.

    Attributes:
        resend: 같은 건을 다시 보내는가(참이면 바뀐 내용 필수 · ``[수정]`` 머리말).
        cycle_id: 지금 AS 건 id(이력에 적을 값). 건이 없으면 None.
        headline: 본문 맨 앞에 붙일 한 줄. 둘째 건부터의 첫 PUSH 만 값이 있다.
    """

    resend: bool
    cycle_id: str | None
    headline: str


def parse_utc(raw: Any) -> datetime.datetime | None:
    """ISO 시각을 UTC 로 읽는다. 시간대가 없는 값(AS 건 ``opened_at``)은 UTC 로 본다."""
    try:
        at = datetime.datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
    return at if at.tzinfo else at.replace(tzinfo=datetime.timezone.utc)


def _sent_in_cycle(history: dict, cycle: dict, cycle_id: str) -> bool:
    """마지막 PUSH 가 지금 건에서 나갔는가. 가를 근거가 없으면 참(= 다시 보내기)으로 둔다."""
    recorded = str(history.get("as_cycle_id") or "")
    if recorded:
        return recorded == cycle_id
    # 건 번호가 없는 옛 이력: 건을 열기 전에 보낸 것만 지난 건의 PUSH 로 본다.
    opened, sent = parse_utc(cycle.get("opened_at")), parse_utc(history.get("sent_at"))
    return not (opened is not None and sent is not None and sent < opened)


def judge_as_push(sd: Any) -> AsPushVerdict:
    """저장된 주문 값으로 이번 AS PUSH 를 판정한다(순수 계산 — 아무것도 바꾸지 않는다).

    * 지금 건이 없거나(건 표식이 없는 옛 주문) 옛 주문을 끌어올린 건이면 지금까지처럼 이력의 ``pushed`` 만 본다.
      끌어올린 건의 ``opened_at`` 은 접수 시각이 아니라 시각 비교를 믿을 수 없다.
    * 그 밖에는 마지막 PUSH 가 지금 건에서 나갔으면 다시 보내기, 아니면 이 건의 첫 PUSH 다.
    * 첫 PUSH 인데 건 순번이 2 이상이면 "새 AS 접수 (N번째 AS)" 한 줄을 본문 앞에 붙인다. 순번은
      ``as_lifecycle.cycles[]`` 만 센다(취소되어 빠진 건은 세지 않는다).

    Args:
        sd: 주문 ``structured_data``.

    Returns:
        :class:`AsPushVerdict`.
    """
    sd = sd if isinstance(sd, dict) else {}
    history = sd.get(PUSH_HISTORY_KEY) if isinstance(sd.get(PUSH_HISTORY_KEY), dict) else {}
    pushed = bool(history.get("pushed"))
    cycle = current_cycle(sd)
    cycle_id = (str(cycle.get("cycle_id") or "") or None) if cycle else None
    if cycle is None or cycle_id is None or is_history_unknown(cycle):
        return AsPushVerdict(pushed, cycle_id, "")
    if pushed and _sent_in_cycle(history, cycle, cycle_id):
        return AsPushVerdict(True, cycle_id, "")
    ordinal = current_cycle_ordinal(sd)
    return AsPushVerdict(False, cycle_id, f"새 AS 접수 ({ordinal}번째 AS)" if ordinal >= 2 else "")


def compose_as_push(order: Any) -> tuple[str, AsPushVerdict]:
    """AS PUSH 본문과 판정을 같이 만든다 — 미리 보기와 전송이 이 함수 하나를 쓴다.

    Args:
        order: 대상 주문(``structured_data`` 포함).

    Returns:
        ``(본문, 판정)``. AS 접수 내용이 없으면 본문은 빈 문자열이다(머리말만 나가지 않는다).
    """
    verdict = judge_as_push(getattr(order, "structured_data", None))
    text = build_as_push_text(order)
    if text and verdict.headline:
        text = f"{verdict.headline}\n\n{text}"
    return text, verdict
