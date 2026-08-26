"""ORDER-FLAG-01: 라홈시스템(2공장)·지방주문 권한 + 변경 원장 계약 테스트.

고정하는 것 4가지.

* **권한 판정**: ADMIN 또는 CS(라홈팀/하우드팀)만 켜고 끈다. 팀이 다른 MANAGER 는 못 바꾼다.
* **거부가 아니라 무시**: 무권한 저장은 403 이 아니라 200 이고, 두 값만 기존값으로 남는다
  (이 PUT 은 견적 미리보기·알림톡 발송도 태우므로 403 이면 정상 저장 전체가 막힌다).
* **체크박스 제거 금지**: 폼이 ``factory2: false`` 를 실어 보내도 기존 ``true`` 가 살아남는다.
* **원장 기록**: 권한자가 바꾸면 ``order_field_changes`` 에 ``flags.factory2``·``is_regional``
  이 before/after 와 함께 남는다(둘 다 2026-08-26 이전에는 어디에도 안 남던 값이다).
"""

import copy

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderFieldChange, User
from foms.services.audit_message_display import PATH_LABELS, path_label
from foms.services.orders.order_flag_permissions import can_toggle_order_flags
from foms.services.orders.structured_diff import SCALAR_PATHS


# --------------------------------------------------------------------------
# 픽스처
# --------------------------------------------------------------------------
class _FakeUser:
    def __init__(self, role=None, team=None):
        self.role = role
        self.team = team


def _login(client, username, role, team):
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{username}-name",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = username
        sess["role"] = role
    return user.id


def _valid_sd(**overrides):
    sd = {
        "entity_type": "order_structured",
        "workflow": {"stage": "RECEIVED"},
        "parties": {"customer": {"name": "홍길동", "phone": "010-1234-5678"}},
        "site": {"address_full": "서울 테헤란로 1", "address_main": "서울 테헤란로 1"},
        "items": [{"product_name": "붙박이장", "price": 0}],
        "flags": {"urgent": False, "urgent_reason": "", "factory2": False},
    }
    sd.update(overrides)
    return sd


def _create_order(**cols):
    sd = cols.pop("structured_data", None)
    order = Order(
        received_date="2026-08-26",
        customer_name="홍길동",
        phone="010-1234-5678",
        address="서울 테헤란로 1",
        product="붙박이장",
        status="RECEIVED",
        is_erp_order=True,
        structured_data=sd if sd is not None else _valid_sd(),
    )
    for key, value in cols.items():
        setattr(order, key, value)
    db_session.add(order)
    db_session.commit()
    return order.id


def _fresh(oid):
    db_session.expire_all()
    return db_session.get(Order, oid)


def _ledger(oid, path):
    db_session.expire_all()
    return (
        db_session.query(OrderFieldChange)
        .filter(OrderFieldChange.order_id == oid, OrderFieldChange.path == path)
        .order_by(OrderFieldChange.id)
        .all()
    )


def _put(client, oid, **payload):
    body = {"structured_data": _valid_sd()}
    body.update(payload)
    return client.put(f"/api/orders/{oid}/structured", json=body)


# --------------------------------------------------------------------------
# 1. 권한 판정 (순수 함수 — DB 없이)
# --------------------------------------------------------------------------
def test_admin_can_toggle_regardless_of_team():
    """관리자는 팀과 무관하게 켜고 끈다."""
    assert can_toggle_order_flags(_FakeUser(role="ADMIN", team="SALES")) is True
    assert can_toggle_order_flags(_FakeUser(role="ADMIN", team=None)) is True


def test_cs_team_can_toggle_at_any_role():
    """CS(라홈팀/하우드팀)는 역할과 무관하게 켜고 끈다 — 접수 담당이 값의 주인이다."""
    assert can_toggle_order_flags(_FakeUser(role="STAFF", team="CS")) is True
    assert can_toggle_order_flags(_FakeUser(role="MANAGER", team="cs")) is True


def test_manager_outside_cs_cannot_toggle():
    """'매니저 이상'이 아니라 'CS·관리자'다 — 영업팀 매니저는 못 바꾼다."""
    assert can_toggle_order_flags(_FakeUser(role="MANAGER", team="SALES")) is False
    assert can_toggle_order_flags(_FakeUser(role="STAFF", team="DRAWING")) is False


def test_viewer_and_anonymous_cannot_toggle():
    """뷰어는 CS 팀이어도 못 바꾼다. 미인증도 마찬가지."""
    assert can_toggle_order_flags(_FakeUser(role="VIEWER", team="CS")) is False
    assert can_toggle_order_flags(None) is False


# --------------------------------------------------------------------------
# 2. 감사 경로 등재 (라벨 미등재는 화면에 raw 경로를 띄운다)
# --------------------------------------------------------------------------
def test_factory2_is_audited_path_with_label():
    """``flags.factory2`` 가 감사 대상이고 한글 라벨이 있다."""
    assert "flags.factory2" in SCALAR_PATHS
    assert PATH_LABELS["flags.factory2"] == "라홈시스템(2공장)"


def test_flat_regional_paths_have_labels():
    """평면 컬럼 경로도 라벨이 있어야 변경 이력 표가 읽힌다."""
    assert path_label("is_regional") == "지방 주문"
    assert path_label("construction_type") == "지방주문 구분"


# --------------------------------------------------------------------------
# 3. 서버 게이트 — 무권한은 거부가 아니라 무시
# --------------------------------------------------------------------------
def test_unauthorized_save_succeeds_but_keeps_both_values(client):
    """무권한 저장은 200 이고, 라홈시스템·지방주문만 기존값으로 남는다."""
    oid = _create_order(
        structured_data=_valid_sd(flags={"urgent": False, "urgent_reason": "", "factory2": True}),
        is_regional=True,
        construction_type="협력사 시공",
    )
    _login(client, "flag-sales-manager", "MANAGER", "SALES")

    sd = _valid_sd(flags={"urgent": False, "urgent_reason": "", "factory2": False})
    res = _put(client, oid, structured_data=sd, is_regional=False, construction_type="")

    assert res.status_code == 200, res.get_data(as_text=True)
    assert res.get_json()["success"] is True
    order = _fresh(oid)
    assert order.structured_data["flags"]["factory2"] is True, "무권한 요청이 2공장을 껐다"
    assert order.is_regional is True, "무권한 요청이 지방주문을 껐다"
    assert order.construction_type == "협력사 시공"


def test_unauthorized_save_does_not_write_flag_ledger_rows(client):
    """무권한 요청은 값이 안 바뀌었으니 원장에도 남지 않는다(무변경을 변경으로 적지 않는다)."""
    oid = _create_order(
        structured_data=_valid_sd(flags={"urgent": False, "urgent_reason": "", "factory2": True}),
        is_regional=True,
        construction_type="협력사 시공",
    )
    _login(client, "flag-drawing-staff", "STAFF", "DRAWING")

    sd = _valid_sd(flags={"urgent": False, "urgent_reason": "", "factory2": False})
    _put(client, oid, structured_data=sd, is_regional=False, construction_type="")

    assert _ledger(oid, "flags.factory2") == []
    assert _ledger(oid, "is_regional") == []


def test_unauthorized_save_still_writes_other_fields(client):
    """게이트는 두 값만 잠근다 — 같은 저장의 나머지 변경은 정상 반영된다."""
    oid = _create_order(is_regional=True, construction_type="협력사 시공")
    _login(client, "flag-sales-staff", "STAFF", "SALES")

    sd = _valid_sd()
    sd["parties"]["customer"]["name"] = "김철수"
    res = _put(client, oid, structured_data=sd, is_regional=False)

    assert res.status_code == 200
    order = _fresh(oid)
    assert order.structured_data["parties"]["customer"]["name"] == "김철수"
    assert order.is_regional is True


def test_missing_factory2_key_is_not_resurrected_as_false(client):
    """기존 sd 에 키가 없었으면 없는 채로 둔다 — 없던 키를 False 로 채우면 가짜 변경이 생긴다."""
    sd_without_key = _valid_sd()
    sd_without_key["flags"] = {"urgent": False, "urgent_reason": ""}
    oid = _create_order(structured_data=sd_without_key)
    _login(client, "flag-prod-staff", "STAFF", "PRODUCTION")

    sd = _valid_sd(flags={"urgent": False, "urgent_reason": "", "factory2": True})
    _put(client, oid, structured_data=sd)

    order = _fresh(oid)
    assert "factory2" not in order.structured_data["flags"]
    assert _ledger(oid, "flags.factory2") == []


# --------------------------------------------------------------------------
# 4. 권한자 저장 — 값이 바뀌고 원장에 남는다
# --------------------------------------------------------------------------
def test_cs_staff_toggles_factory2_and_it_lands_in_ledger(client):
    """CS 직원이 라홈시스템을 켜면 값이 바뀌고 원장에 before/after 가 남는다."""
    oid = _create_order()
    _login(client, "flag-cs-staff", "STAFF", "CS")

    sd = _valid_sd(flags={"urgent": False, "urgent_reason": "", "factory2": True})
    res = _put(client, oid, structured_data=sd)

    assert res.status_code == 200
    assert _fresh(oid).structured_data["flags"]["factory2"] is True
    rows = _ledger(oid, "flags.factory2")
    assert len(rows) == 1
    assert rows[0].after_value == "True"
    assert rows[0].op == "set"


def test_admin_toggles_regional_and_flat_columns_land_in_ledger(client):
    """지방주문은 평면 컬럼이라 structured diff 밖이다 — 그래도 원장에 남아야 한다."""
    oid = _create_order()
    _login(client, "flag-admin", "ADMIN", "SALES")

    res = _put(client, oid, is_regional=True, construction_type="협력사 시공")

    assert res.status_code == 200, res.get_data(as_text=True)
    order = _fresh(oid)
    assert order.is_regional is True
    assert order.construction_type == "협력사 시공"

    regional_rows = _ledger(oid, "is_regional")
    assert len(regional_rows) == 1
    assert regional_rows[0].before_value == "False"
    assert regional_rows[0].after_value == "True"
    ctype_rows = _ledger(oid, "construction_type")
    assert len(ctype_rows) == 1
    assert ctype_rows[0].after_value == "협력사 시공"


def test_authorized_save_without_flag_change_writes_no_flag_rows(client):
    """값이 그대로면 원장에 적지 않는다 — 저장 버튼만 눌러도 쌓이면 진짜 변경이 묻힌다."""
    oid = _create_order(is_regional=True, construction_type="협력사 시공")
    _login(client, "flag-cs-admin", "ADMIN", "CS")

    _put(client, oid, is_regional=True, construction_type="협력사 시공")

    assert _ledger(oid, "is_regional") == []
    assert _ledger(oid, "construction_type") == []


# --------------------------------------------------------------------------
# 5. 화면 계약 — 체크박스는 숨기지 말고 비활성으로
# --------------------------------------------------------------------------
def test_edit_page_renders_disabled_checkboxes_for_unauthorized(client):
    """무권한 화면은 체크박스를 **비활성**으로 낸다. 제거하면 폼 수집기가 false 를 실어 보낸다."""
    oid = _create_order(
        structured_data=_valid_sd(flags={"urgent": False, "urgent_reason": "", "factory2": True}),
        is_regional=True,
        construction_type="협력사 시공",
    )
    # SALES 는 ERP 편집 화면 자체는 열 수 있고(can_edit_erp), 이 두 값만 못 바꾼다.
    _login(client, "flag-view-staff", "STAFF", "SALES")

    body = client.get(f"/edit/{oid}?open=erp-order").get_data(as_text=True)
    squashed = " ".join(body.split())

    assert 'id="erp-factory2"' in body, "체크박스를 DOM 에서 빼면 저장 시 값이 지워진다"
    assert 'id="erp-regional-order"' in body
    assert 'id="erp-factory2" autocomplete="off" disabled' in squashed
    assert 'id="erp-regional-order" autocomplete="off" disabled' in squashed


def test_edit_page_renders_enabled_checkboxes_for_cs(client):
    """CS 는 두 체크박스를 그대로 쓴다(비활성 표식이 붙지 않는다)."""
    oid = _create_order()
    _login(client, "flag-cs-editor", "STAFF", "CS")

    body = client.get(f"/edit/{oid}?open=erp-order").get_data(as_text=True)
    squashed = " ".join(body.split())

    assert 'id="erp-factory2"' in body
    assert 'id="erp-factory2" autocomplete="off" disabled' not in squashed
    assert 'id="erp-regional-order" autocomplete="off" disabled' not in squashed


def test_structured_get_exposes_permission_flag(client):
    """태블릿 폼이 서버와 같은 판정을 쓰도록 GET 이 권한을 내려준다."""
    oid = _create_order()
    _login(client, "flag-cs-tablet", "STAFF", "CS")
    assert client.get(f"/api/orders/{oid}/structured").get_json()["can_toggle_order_flags"] is True

    _login(client, "flag-sales-tablet", "STAFF", "SALES")
    assert client.get(f"/api/orders/{oid}/structured").get_json()["can_toggle_order_flags"] is False
