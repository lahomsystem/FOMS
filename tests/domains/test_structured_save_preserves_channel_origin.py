"""폼 저장이 채널 출처·채널 결제 기록을 지우지 않는지 (2026-08-24 스테이징 실사례 회귀).

주문 편집 화면은 ``structured_data['source'] == 'NAVER_SMARTSTORE'`` 일 때만 네이버 원본
도크를 렌더하고(``foms/web/orders/edit.py``), 붙이기가 기록한 추가결제를 읽는 코드는 그 도크
하나뿐이다(``dock.py._extra_payment_summary``). 그래서 표식이 사라지면 **붙이기는 성공했는데
사람이 볼 자리가 없어진다.**

실사례(주문 4485): 링크 264~269 가 REPAY 로 붙고 ``pricing.extra_payments`` 에
1,610,780원 6건이 기록됐는데 편집 화면은 빈손이었다. 원인은 폼 저장이 ``source`` 를 지운
것이고, 스테이징 전수 조사에서 네이버 링크가 붙은 주문 9건 중 ERP 편집 흔적이 있는 5건은
**전부** ``source`` 를 잃었다(편집이 없던 4건은 전부 보존, 9/9 일치).

``pricing`` 이 같이 걸려 있는 것이 더 나쁘다 — 폼 저장 한 번에 **돈 기록**이 통째로 날아간다.

allowlist(``enforce_form_allowlist``)는 들어온 dict 에서 낯선 키를 걷어낼 뿐 빠진 옛 키를
되살리지 않는다. 그래서 strip 목록에도 안 남아 로그조차 없었다.
"""

import copy

import pytest

from foms.api.erp_orders_structured import _preserve_operational_structured_state
from foms.services.orders.structured_form_projection import project_structured_form

#: 폼 저장을 한 번 거쳐도 반드시 살아남아야 하는 채널 키.
CHANNEL_KEYS = ("source", "naver", "pricing")


def _collected() -> dict:
    """네이버 수집이 만들고 붙이기가 결제까지 기록한 저장 전 서버값."""
    return {
        "source": "NAVER_SMARTSTORE",
        "naver": {"external_order_no": "2026081421699721"},
        "pricing": {"extra_payments": [
            {"amount": 1022900, "relation": "REPAY", "external_id": "2026082410074701"},
            {"amount": 170000, "relation": "REPAY", "external_id": "2026082410074751"},
        ]},
        "items": [{"price": 1000}],
        "parties": {"customer": {"name": "신중섭"}},
        "site": {},
        "workflow": {},
        "quests": {},
    }


def _form_payload() -> dict:
    """편집 폼이 실제로 보내는 모양 — 채널 키 셋은 아예 없다."""
    return {
        "items": [{"price": 1000}],
        "parties": {"customer": {"name": "신중섭"}},
        "site": {},
        "workflow": {},
        "schedule": {},
        "notes": "",
        "flags": {},
        "payment": {},
        "shipment": {},
        "entity_type": "order_structured",
    }


@pytest.mark.parametrize("key", CHANNEL_KEYS)
def test_form_save_keeps_channel_keys(key):
    """폼이 안 보내는 채널 키는 저장을 거쳐도 살아남는다."""
    old = _collected()
    incoming = _form_payload()
    _preserve_operational_structured_state(old, incoming)
    project_structured_form(old, incoming)

    assert incoming[key] == old[key], f"{key} 가 폼 저장 한 번에 사라졌다"


def test_money_record_survives_a_full_save_round():
    """붙이기가 기록한 금액이 저장 뒤에도 한 원도 줄지 않는다."""
    old = _collected()
    incoming = _form_payload()
    _preserve_operational_structured_state(old, incoming)
    project_structured_form(old, incoming)

    rows = incoming["pricing"]["extra_payments"]
    assert sum(row["amount"] for row in rows) == 1192900


def test_form_can_still_overwrite_channel_keys_it_sends():
    """보존이 편집을 막으면 안 된다 — 폼이 값을 보내면 그 값이 이긴다."""
    old = _collected()
    incoming = _form_payload()
    incoming["source"] = "OTHER_CHANNEL"
    _preserve_operational_structured_state(old, incoming)
    project_structured_form(old, incoming)

    assert incoming["source"] == "OTHER_CHANNEL"


def test_absent_channel_keys_are_not_invented():
    """원래 없던 주문에는 채널 키를 만들어 넣지 않는다(직접 만든 주문 오염 금지)."""
    old = {"items": [], "parties": {}}
    incoming = _form_payload()
    _preserve_operational_structured_state(old, incoming)
    project_structured_form(old, incoming)

    for key in CHANNEL_KEYS:
        assert key not in incoming, f"{key} 가 근거 없이 생겼다"
