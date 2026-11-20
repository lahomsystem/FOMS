"""AS PUSH 판정(다시 보내기 / 새 AS 건의 첫 PUSH) — 순수 계산 시험.

설계서 docs/specs/2026-11-20-multi-item-split-schedule_SPEC.md §7.1 (M18). 전송 · 미리 보기까지 잇는 시험은
``tests/domains/test_channel_integration_smoke.py`` 끝의 ``test_as_push_*`` 다.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from foms.services.channel_as_push_cycle import compose_as_push, judge_as_push

C1 = {"cycle_id": "c1", "opened_at": "2026-09-01T00:00:00", "transitions": []}
C2 = {"cycle_id": "c2", "opened_at": "2026-11-10T00:00:00", "transitions": []}
BRIDGE = {"cycle_id": "cb", "opened_at": "2026-11-10T00:00:00", "origin": "LEGACY_BRIDGE", "transitions": []}


def _sd(cycles, history=None, *, current=None, **lifecycle_extra):
    sd = {"shipment": {"as_content": "문짝 처짐"}}
    if cycles is not None:
        sd["as_lifecycle"] = {"current_cycle_id": current or (cycles[-1]["cycle_id"] if cycles else None),
                              "cycles": cycles, **lifecycle_extra}
    if history is not None:
        sd["channeltalk_push_as"] = history
    return sd


@pytest.mark.parametrize("sd,expected", [
    # 건 표식이 없는 옛 주문 — 지금까지처럼 이력의 pushed 만 본다.
    (_sd(None), (False, None, "")),
    (_sd(None, {"pushed": True}), (True, None, "")),
    # 끌어올린 건 — 연 시각을 믿지 않는다.
    (_sd([BRIDGE]), (False, "cb", "")),
    (_sd([BRIDGE], {"pushed": True, "sent_at": "2026-01-01T00:00:00+00:00"}), (True, "cb", "")),
    # 첫 건의 첫 PUSH — 머리말 없음.
    (_sd([C1]), (False, "c1", "")),
    (_sd([C1], {"pushed": True, "sent_at": "2026-08-01T00:00:00+00:00"}), (False, "c1", "")),
    # 같은 건 다시 보내기.
    (_sd([C1], {"pushed": True, "as_cycle_id": "c1"}), (True, "c1", "")),
    (_sd([C1, C2], {"pushed": True, "sent_at": "2026-11-10T00:00:00+00:00"}), (True, "c2", "")),  # 같은 시각 = 지난 건으로 보지 않는다
    (_sd([C1, C2], {"pushed": True, "sent_at": "깨진 값"}), (True, "c2", "")),
    # 둘째 건의 첫 PUSH — 건 번호가 이기고, 건 번호가 없으면 시각으로.
    (_sd([C1, C2], {"pushed": True, "as_cycle_id": "c1", "sent_at": "2026-11-11T00:00:00+00:00"}),
     (False, "c2", "새 AS 접수 (2번째 AS)")),
    (_sd([C1, C2], {"pushed": True, "sent_at": "2026-09-01T01:00:00+00:00"}), (False, "c2", "새 AS 접수 (2번째 AS)")),
    # 지난 건 때 한 번도 안 올린 주문의 둘째 건 — 다시 보내기는 아니고, 둘째 AS 라는 한 줄은 붙는다.
    (_sd([C1, C2]), (False, "c2", "새 AS 접수 (2번째 AS)")),
])
def test_judge_as_push(sd, expected):
    verdict = judge_as_push(sd)
    assert (verdict.resend, verdict.cycle_id, verdict.headline) == expected


def test_cancelled_cycles_are_not_counted():
    """취소되어 ``cancelled_cycles[]`` 로 빠진 건은 순번에 넣지 않는다 — 있어도 깨지지 않는다."""
    gone = {"cycle_id": "cx", "opened_at": "2026-10-01T00:00:00", "transitions": []}
    sd = _sd([C1, C2], {"pushed": True, "as_cycle_id": "cx"}, cancelled_cycles=[gone])
    assert judge_as_push(sd).headline == "새 AS 접수 (2번째 AS)"
    # 취소한 건에서 보낸 이력만 남고 지금 건이 첫 건으로 돌아간 주문: 머리말 없는 보통 첫 PUSH.
    back = _sd([C1], {"pushed": True, "as_cycle_id": "cx"}, cancelled_cycles=[gone])
    verdict = judge_as_push(back)
    assert (verdict.resend, verdict.headline) == (False, "")


@pytest.mark.parametrize("raw", [None, "", [], {"as_lifecycle": "깨진 값", "channeltalk_push_as": "깨진 값"}])
def test_judge_tolerates_broken_data(raw):
    assert judge_as_push(raw) == (False, None, "")


def test_compose_puts_headline_before_body_and_never_alone():
    order = SimpleNamespace(structured_data=_sd([C1, C2], {"pushed": True, "as_cycle_id": "c1"}),
                            customer_name="홍길동", phone="010", address="서울", erp_construction_date="")
    text, verdict = compose_as_push(order)
    assert text.split("\n")[:3] == ["새 AS 접수 (2번째 AS)", "", "고객명 : 홍길동"]
    assert verdict.resend is False

    order.structured_data["shipment"]["as_content"] = ""  # 접수 내용이 없으면 머리말만 보내지 않는다
    assert compose_as_push(order)[0] == ""
