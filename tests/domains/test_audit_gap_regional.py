"""AUDIT-GAP-01: 지방 체크리스트·메모의 변경 원장 계약 테스트.

``POST /api/update_regional_status`` 는 지방 체크리스트 6종의 **실사용 정본 쓰기 경로**다.
2026-08-26 이전에는 이 경로가 ``ORDER_CHECKLIST_UPDATED`` 보안로그와
``REGIONAL_CHECKLIST_UPDATED`` OrderEvent 만 남기고 ``order_field_changes`` 원장에는 한 줄도
남기지 않았다(운영 실측: 지방 주문 106건 중 체크가 켜진 건이 필드별 25~93건인데 원장 행은 0).
그래서 "이 필드가 바뀐 주문 전부"를 원장 한 곳에서 물을 수 없었다.

여기서 고정하는 것 4가지.

* **바뀌면 남는다**: 6종 각각이 ``order_field_changes`` 에 before/after 와 함께 실린다.
  경로는 점 없는 **평면 컬럼명 그대로**(``regional_blueprint_sent`` 등).
* **안 바뀌면 안 남는다**: 같은 값 재저장(중복 클릭·재요청)은 행을 만들지 않는다.
* **회귀 없음**: 기존 보안로그·OrderEvent 는 그대로 남는다.
* **헤더↔항목 조인**: 보안로그 ``detail['change_set']`` 이 원장 행의 ``change_set_id`` 와 같다.
  (관리자 감사 화면이 이 값으로 헤더와 항목을 잇는다.)

라벨(``path_label``) 단언은 여기 없다 — 라벨 등재는 별도 task 소유다.
"""

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.api.orders.regional import REGIONAL_ALLOWED_FIELDS
from models import Order, OrderEvent, OrderFieldChange, SecurityLog, User

#: 원장 ``path`` 로 쓰이는 평면 컬럼명. 컬럼명을 바꾸면 과거 원장 행과 이력이 끊기므로
#: 여기에 **문자열 그대로** 박아 대조한다(레지스트리를 그대로 재사용하면 리네임을 못 잡는다).
_CHECKLIST_COLUMNS = (
    "measurement_completed",
    "regional_sales_order_upload",
    "regional_blueprint_sent",
    "regional_order_upload",
    "regional_cargo_sent",
    "regional_construction_info_sent",
)


# --------------------------------------------------------------------------
# 픽스처
# --------------------------------------------------------------------------
def _login(client, username, role="ADMIN", team="CS"):
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


def _create_order(**cols):
    order = Order(
        received_date="2026-08-26",
        customer_name="김철수",
        phone="010-1234-5678",
        address="강원도 원주시 지방로 1",
        product="붙박이장",
        status="RECEIVED",
        is_regional=True,
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


def _ledger_all(oid):
    db_session.expire_all()
    return (
        db_session.query(OrderFieldChange)
        .filter(OrderFieldChange.order_id == oid)
        .order_by(OrderFieldChange.id)
        .all()
    )


def _logs(oid, action):
    db_session.expire_all()
    return (
        db_session.query(SecurityLog)
        .filter(SecurityLog.action == action, SecurityLog.target_id == oid)
        .order_by(SecurityLog.id)
        .all()
    )


def _events(oid, event_type):
    db_session.expire_all()
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == oid, OrderEvent.event_type == event_type)
        .order_by(OrderEvent.id)
        .all()
    )


def _toggle(client, oid, field, value):
    return client.post(
        "/api/update_regional_status",
        json={"order_id": oid, "field": field, "value": value},
    )


# --------------------------------------------------------------------------
# 0. 경로 이름 자체가 계약이다
# --------------------------------------------------------------------------
def test_ledger_paths_match_the_allowed_field_registry():
    """원장 경로 = 허용 필드 레지스트리와 **같은 이름**(점 경로로 바꿔 쓰지 않는다)."""
    assert set(_CHECKLIST_COLUMNS) == set(REGIONAL_ALLOWED_FIELDS)
    assert len(_CHECKLIST_COLUMNS) == 6
    assert not any("." in column for column in _CHECKLIST_COLUMNS), "평면 컬럼명은 점이 없다"


# --------------------------------------------------------------------------
# 1. 켜기 / 끄기 — 6종 전부
# --------------------------------------------------------------------------
@pytest.mark.parametrize("field", _CHECKLIST_COLUMNS)
def test_checklist_turn_on_lands_in_ledger(client, field):
    """체크를 켜면 그 컬럼명 경로로 ``False → True`` 가 원장에 남는다."""
    oid = _create_order(**{field: False})
    _login(client, f"gap-reg-on-{field}")

    res = _toggle(client, oid, field, True)

    assert res.status_code == 200, res.get_data(as_text=True)
    assert getattr(_fresh(oid), field) is True
    rows = _ledger(oid, field)
    assert len(rows) == 1, f"{field} 원장 행이 1건이어야 한다"
    assert rows[0].before_value == "False"
    assert rows[0].after_value == "True"
    assert rows[0].op == "set"
    assert rows[0].path_template == field


@pytest.mark.parametrize("field", _CHECKLIST_COLUMNS)
def test_checklist_turn_off_lands_in_ledger(client, field):
    """체크를 끄면 ``True → False`` 로 남는다(해제도 변경이다)."""
    oid = _create_order(**{field: True})
    _login(client, f"gap-reg-off-{field}")

    res = _toggle(client, oid, field, False)

    assert res.status_code == 200, res.get_data(as_text=True)
    assert getattr(_fresh(oid), field) is False
    rows = _ledger(oid, field)
    assert len(rows) == 1
    assert rows[0].before_value == "True"
    assert rows[0].after_value == "False"
    assert rows[0].op == "set"


def test_checklist_ledger_records_actor(client):
    """원장 행에 누가 바꿨는지가 남는다."""
    oid = _create_order(regional_cargo_sent=False)
    user_id = _login(client, "gap-reg-actor")

    assert _toggle(client, oid, "regional_cargo_sent", True).status_code == 200

    rows = _ledger(oid, "regional_cargo_sent")
    assert len(rows) == 1
    assert rows[0].actor_user_id == user_id
    assert rows[0].order_id == oid


# --------------------------------------------------------------------------
# 2. 무변경 저장은 원장을 늘리지 않는다
# --------------------------------------------------------------------------
def test_unchanged_checklist_save_writes_no_ledger_row(client):
    """같은 값 재저장은 행을 만들지 않는다 — 재클릭이 쌓이면 진짜 토글이 묻힌다."""
    oid = _create_order(regional_blueprint_sent=True)
    _login(client, "gap-reg-noop")

    res = _toggle(client, oid, "regional_blueprint_sent", True)

    assert res.status_code == 200, res.get_data(as_text=True)
    assert _ledger(oid, "regional_blueprint_sent") == []
    assert _ledger_all(oid) == []


def test_null_column_set_to_false_is_not_a_change(client):
    """NULL(미설정) 컬럼을 False 로 저장하는 것은 변경이 아니다.

    낡은 행은 이 컬럼이 NULL 이다. NULL 은 '체크 안 됨'이지 별개 값이 아니라서,
    화면을 한 번 여는 것만으로 원장에 ``(없음) → False`` 가 쌓이면 안 된다.
    """
    oid = _create_order()
    order = db_session.get(Order, oid)
    order.regional_order_upload = None
    db_session.commit()
    _login(client, "gap-reg-null")

    res = _toggle(client, oid, "regional_order_upload", False)

    assert res.status_code == 200, res.get_data(as_text=True)
    assert _ledger_all(oid) == []


def test_second_toggle_appends_a_second_row(client):
    """켰다 끄면 행이 2개 쌓인다(이력이 덮어써지지 않는다)."""
    oid = _create_order(measurement_completed=False)
    _login(client, "gap-reg-twice")

    assert _toggle(client, oid, "measurement_completed", True).status_code == 200
    assert _toggle(client, oid, "measurement_completed", False).status_code == 200

    rows = _ledger(oid, "measurement_completed")
    assert [(r.before_value, r.after_value) for r in rows] == [
        ("False", "True"), ("True", "False"),
    ]
    assert rows[0].change_set_id != rows[1].change_set_id, "저장마다 다른 묶음 id 여야 한다"


# --------------------------------------------------------------------------
# 3. 회귀 방지 — 기존 보안로그·OrderEvent 는 그대로
# --------------------------------------------------------------------------
def test_existing_security_log_and_event_still_recorded(client):
    """원장을 붙여도 기존 감사 2종(보안로그·OrderEvent)은 그대로 남는다."""
    oid = _create_order(regional_sales_order_upload=False)
    _login(client, "gap-reg-regress")

    assert _toggle(client, oid, "regional_sales_order_upload", True).status_code == 200

    logs = _logs(oid, "ORDER_CHECKLIST_UPDATED")
    assert len(logs) == 1
    assert logs[0].detail["field"] == "regional_sales_order_upload"
    assert logs[0].detail["before"] is False
    assert logs[0].detail["after"] is True

    events = _events(oid, "REGIONAL_CHECKLIST_UPDATED")
    assert len(events) == 1
    assert events[0].payload == {"field": "regional_sales_order_upload", "value": True}


# --------------------------------------------------------------------------
# 4. 헤더 ↔ 항목 조인 열쇠
# --------------------------------------------------------------------------
def test_security_log_change_set_matches_ledger_row(client):
    """보안로그 ``detail['change_set']`` 이 원장 행의 ``change_set_id`` 와 같다.

    관리자 감사 화면이 ``detail->>'change_set'`` 으로 헤더와 항목을 잇는다. 값이 어긋나면
    원장 행이 있어도 화면에서는 보이지 않는다.
    """
    oid = _create_order(regional_construction_info_sent=False)
    _login(client, "gap-reg-changeset")

    assert _toggle(client, oid, "regional_construction_info_sent", True).status_code == 200

    logs = _logs(oid, "ORDER_CHECKLIST_UPDATED")
    rows = _ledger(oid, "regional_construction_info_sent")
    assert len(logs) == 1 and len(rows) == 1
    assert logs[0].detail.get("change_set"), "감사 헤더에 change_set 이 없다"
    assert logs[0].detail["change_set"] == rows[0].change_set_id


# --------------------------------------------------------------------------
# 5. 지방 메모 — 같은 경로에 함께 실린다
# --------------------------------------------------------------------------
def test_regional_memo_change_lands_in_ledger(client):
    """메모 저장이 ``regional_memo`` 경로로 원장에 남는다."""
    oid = _create_order()
    _login(client, "gap-reg-memo")

    res = client.post(
        "/api/update_regional_memo",
        json={"order_id": oid, "memo": "8/1 시공 예정"},
    )

    assert res.status_code == 200, res.get_data(as_text=True)
    rows = _ledger(oid, "regional_memo")
    assert len(rows) == 1
    assert rows[0].before_value is None
    assert rows[0].after_value == "8/1 시공 예정"
    assert rows[0].op == "add"

    logs = _logs(oid, "ORDER_MEMO_UPDATED")
    assert len(logs) == 1
    assert logs[0].detail["change_set"] == rows[0].change_set_id


def test_regional_memo_unchanged_save_writes_no_ledger_row(client):
    """같은 메모 재저장(자동저장 디바운스 + blur 이중 발사)은 행을 만들지 않는다."""
    oid = _create_order()
    _login(client, "gap-reg-memo-noop")

    first = client.post("/api/update_regional_memo",
                        json={"order_id": oid, "memo": "중복 검증 메모"})
    assert first.status_code == 200
    second = client.post("/api/update_regional_memo",
                         json={"order_id": oid, "memo": "중복 검증 메모"})
    assert second.status_code == 200
    assert second.get_json().get("unchanged") is True

    assert len(_ledger(oid, "regional_memo")) == 1, "재저장이 원장에 또 쌓였다"


def test_regional_memo_clear_is_recorded(client):
    """메모를 지운 것도 남는다 — 무엇을 지웠는지가 원장에 있어야 한다."""
    oid = _create_order(regional_memo="지워질 메모")
    _login(client, "gap-reg-memo-clear")

    res = client.post("/api/update_regional_memo", json={"order_id": oid, "memo": ""})

    assert res.status_code == 200, res.get_data(as_text=True)
    rows = _ledger(oid, "regional_memo")
    assert len(rows) == 1
    assert rows[0].before_value == "지워질 메모"
    assert rows[0].after_value is None
    assert rows[0].op == "clear"


def test_long_memo_tail_edit_is_recorded(client):
    """**120자 이후만** 고친 메모 변경도 원장에 남는다 (AUDIT-GAP-01 회귀 방어).

    원장 표시값은 120자에서 잘린다. 그 절단값으로 변경 여부를 판정하면 앞 120자가 같은
    긴 메모의 꼬리 수정이 통째로 사라진다 — 메모 상한이 2000자이고 잔금 조건·열쇠 보관처
    같은 분쟁 소재가 뒤쪽에 적히므로 실제로 흔한 모양이다. 판정은 절단 전 원문으로 한다.
    """
    head = "고객 요청 정리. " + ("가" * 110)
    before_memo = f"{head} 잔금 300만원 현금"
    after_memo = f"{head} 잔금 500만원 계좌"
    assert len(before_memo) > 120 and before_memo[:120] == after_memo[:120]

    oid = _create_order()
    _login(client, "gap-reg-memo-long")

    first = client.post(
        "/api/update_regional_memo",
        json={"order_id": oid, "memo": before_memo},
    )
    assert first.status_code == 200, first.get_data(as_text=True)

    second = client.post(
        "/api/update_regional_memo",
        json={"order_id": oid, "memo": after_memo},
    )
    assert second.status_code == 200, second.get_data(as_text=True)

    # 저장이 실제로 반영됐는지 먼저 확인한다 — 요청이 죽어도 "행 없음"은 통과하기 때문이다.
    db_session.expire_all()
    assert db_session.get(Order, oid).regional_memo == after_memo

    rows = _ledger(oid, "regional_memo")
    assert len(rows) == 2, "꼬리만 고친 변경이 원장에서 누락됐다"

    tail_row = rows[-1]
    assert tail_row.op == "set"
    # 표시값이 절단으로 같아 보이면 원장이 ``A → A`` 로 거짓말을 한다 — 표식으로 구분한다.
    assert tail_row.before_value != tail_row.after_value
    assert "내용 수정" in tail_row.after_value


def test_long_memo_unchanged_save_still_writes_no_row(client):
    """긴 메모를 **그대로** 재저장하면 표식도 행도 생기지 않는다."""
    memo = "현장 안내. " + ("나" * 140)
    oid = _create_order()
    _login(client, "gap-reg-memo-long-noop")

    assert client.post(
        "/api/update_regional_memo", json={"order_id": oid, "memo": memo}
    ).status_code == 200
    before_rows = len(_ledger(oid, "regional_memo"))

    assert client.post(
        "/api/update_regional_memo", json={"order_id": oid, "memo": memo}
    ).status_code == 200

    assert len(_ledger(oid, "regional_memo")) == before_rows
