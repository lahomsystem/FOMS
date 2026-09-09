"""manager_display_name 모양 계약 + 스칼라 담당자 화면 단위 회귀.

배경: structured_data['parties']['manager'] 는 dict(``{"name": ...}``)가 정본이지만
스칼라(이름 문자열·user id)도 들어온다. 곳곳이 ``(parties.get('manager') or {}).get('name')``
로 dict 를 가정해서, 스칼라 담당자 주문 한 건이 ``AttributeError: 'str' object has no
attribute 'get'`` 를 내고 대시보드 전체를 500 으로 만들었다(2026-09-09 로컬 dev 실측).
"""

from __future__ import annotations

from types import SimpleNamespace

from foms.services.erp_display import manager_display_name


def test_manager_display_name_dict_shape() -> None:
    assert manager_display_name({"manager": {"name": "홍길동"}}) == "홍길동"


def test_manager_display_name_dict_shape_missing_name_key() -> None:
    assert manager_display_name({"manager": {"id": 7}}) == ""


def test_manager_display_name_scalar_string_shape() -> None:
    """manager 가 dict 가 아니라 이름 문자열 자체인 레거시 모양."""
    assert manager_display_name({"manager": "김철수"}) == "김철수"


def test_manager_display_name_scalar_user_id_shape() -> None:
    """manager 가 user id 정수인 레거시 모양 — 예전엔 여기서 AttributeError 로 500."""
    assert manager_display_name({"manager": 42}) == "42"


def test_manager_display_name_manager_missing() -> None:
    assert manager_display_name({}) == ""


def test_manager_display_name_manager_none() -> None:
    assert manager_display_name({"manager": None}) == ""


def test_manager_display_name_parties_none() -> None:
    assert manager_display_name(None) == ""


def test_manager_display_name_parties_not_dict() -> None:
    """parties 자체가 비-dict 인 방어적 입력도 크래시 없이 빈 문자열."""
    assert manager_display_name("not-a-dict") == ""
    assert manager_display_name(["also", "not", "a", "dict"]) == ""


def test_manager_display_name_whitespace_trimmed() -> None:
    assert manager_display_name({"manager": {"name": "  이영희  "}}) == "이영희"
    assert manager_display_name({"manager": "   "}) == ""


# --- 화면 단위 회귀: 스칼라 담당자를 가진 주문이 있어도 500 없이 동작 ------------------


def test_sort_shipment_rows_survives_scalar_manager() -> None:
    """출고 대시보드 정렬 헬퍼: manager 가 스칼라(레거시 모양)여도 AttributeError 없이 정렬된다.

    수정 전에는 ``(sd.get('parties') or {}).get('manager') or {}).get('name')`` 이
    manager="99"(스칼라 user id 문자열) 인 주문에서 ``.get('name')`` 호출 시 크래시했다.
    """
    from foms.services.shipment_dashboard_display import sort_shipment_rows

    scalar_manager_order = SimpleNamespace(
        id=1,
        status="RECEIVED",
        is_erp_order=True,
        manager_name=None,
        structured_data={"parties": {"manager": "99"}},
    )
    dict_manager_order = SimpleNamespace(
        id=2,
        status="RECEIVED",
        is_erp_order=True,
        manager_name=None,
        structured_data={"parties": {"manager": {"name": "박담당"}}},
    )
    rows = [dict_manager_order, scalar_manager_order]

    sort_shipment_rows(rows)  # AttributeError 를 던지면 테스트 실패

    assert {r.id for r in rows} == {1, 2}


def test_is_order_mine_for_user_survives_scalar_manager() -> None:
    """'내 할 일' 판정: parties.manager 가 스칼라 이름 문자열이어도 크래시 없이 판정한다."""
    from foms.services.erp_shipment_settings import is_order_mine_for_user

    order = SimpleNamespace(
        structured_data={"parties": {"manager": "김담당"}},
        manager_name=None,
    )
    user = SimpleNamespace(name="김담당", username="kim")

    assert is_order_mine_for_user(order, user) is True

    other_user = SimpleNamespace(name="박다른", username="park")
    assert is_order_mine_for_user(order, other_user) is False
