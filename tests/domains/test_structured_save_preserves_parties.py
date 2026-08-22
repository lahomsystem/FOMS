"""폼 저장이 화면에 없는 parties 키를 지우지 않는지 (2026-08-20 스테이징 실측 회귀).

ERP 편집 폼은 ``parties`` 중 ``customer.name``·``customer.phone``·``orderer.name``·
``manager.name`` 만 렌더한다. payload 를 통째로 대입하면 네이버 수집이 채운 값이 주문을 한 번
열어 저장하는 것만으로 사라졌다:

* ``parties.orderer.phone`` — 대리주문 주문자 번호(해피콜 대상 판단에 쓴다)
* ``parties.customer.phone2`` — 보조 연락처("버리면 다시 구할 방법이 없다", 수집 코드 주석)

키가 오면 덮고, 안 오면 남긴다 — 사용자가 화면에서 지운 값은 여전히 지워져야 한다.
"""

import copy

from foms.api.erp_orders_structured import _preserve_operational_structured_state


def _collected() -> dict:
    """네이버 수집이 만든 structured_data(폼이 모르는 키를 포함)."""
    return {
        "parties": {
            "customer": {"name": "박선미", "phone": "010-6279-1403", "phone2": "010-1111-2222"},
            "orderer": {"name": "라홈", "phone": "010-9999-8888"},
            "manager": {"name": "이시영"},
        },
    }


def _form_payload() -> dict:
    """편집 폼이 실제로 보내는 모양 — phone2·orderer.phone 키 자체가 없다."""
    return {
        "parties": {
            "customer": {"name": "박선미", "phone": "010-6279-1403"},
            "orderer": {"name": "라홈"},
            "manager": {"name": "이시영"},
        },
    }


def test_form_save_keeps_keys_it_does_not_render():
    """폼이 안 보내는 키는 살아남는다."""
    old = _collected()
    incoming = _form_payload()
    _preserve_operational_structured_state(old, incoming)

    assert incoming["parties"]["orderer"]["phone"] == "010-9999-8888"
    assert incoming["parties"]["customer"]["phone2"] == "010-1111-2222"


def test_form_save_still_overwrites_rendered_keys():
    """폼이 보내는 키는 그대로 덮는다 — 보존이 편집을 막으면 안 된다."""
    old = _collected()
    incoming = _form_payload()
    incoming["parties"]["customer"]["name"] = "김철수"
    _preserve_operational_structured_state(old, incoming)

    assert incoming["parties"]["customer"]["name"] == "김철수"


def test_user_can_still_clear_a_rendered_field():
    """화면에서 지운 값은 지워진다(빈 문자열도 '보낸 값'이다)."""
    old = _collected()
    incoming = _form_payload()
    incoming["parties"]["customer"]["phone"] = ""
    _preserve_operational_structured_state(old, incoming)

    assert incoming["parties"]["customer"]["phone"] == ""
    # 같은 저장에서 폼이 모르는 키는 여전히 살아 있다.
    assert incoming["parties"]["customer"]["phone2"] == "010-1111-2222"


def test_missing_parties_subtree_is_restored_whole():
    """payload 에 parties 가 통째로 없으면 기존 값을 그대로 남긴다."""
    old = _collected()
    incoming: dict = {}
    _preserve_operational_structured_state(old, incoming)

    assert incoming["parties"] == copy.deepcopy(old["parties"])
