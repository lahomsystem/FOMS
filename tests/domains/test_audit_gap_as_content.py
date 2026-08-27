# -*- coding: utf-8 -*-
"""AUDIT-GAP-01 F2: AS 접수 본문(``shipment.as_content``) 변경 원장 계약 테스트.

``POST /api/orders/<id>/as/register`` 는 ``structured_data.shipment.as_content`` 를 **덮어쓰는
유일한 실사용 경로**다(새 건 접수 = ``register_as_cycle``, 열린 건 재접수 = 라우트의
``_apply_reregistration``). 2026-08-26 이전에는 이 경로가 ``AS_RECEIVED`` 보안로그와
``AS_REGISTERED`` OrderEvent 만 남기고 ``order_field_changes`` 원장에는 한 줄도 남기지
않았다 — ``shipment.as_content`` 는 화이트리스트(``SCALAR_PATHS``)에 등재돼 있는데도 그 값을
쓰는 화면이 원장을 안 불러서, 접수 본문을 통째로 덮어써도 "누가 언제 무엇을 지웠는지"가
어디에도 없었다(운영 실측 2026-08-26: 해당 키를 가진 주문 620건).

여기서 고정하는 것 5가지.

* **덮어쓰면 남는다**: 새 건 접수·열린 건 재접수 **둘 다** ``shipment.as_content`` 경로로
  before/after 가 원장에 실린다. 본문을 비우는 저장도 ``clear`` 로 남는다.
* **안 바뀌면 안 남는다**: 같은 본문 재저장(재접수 모달 무편집 제출)은 행을 만들지 않는다.
* **헤더↔항목 조인**: 보안로그 ``detail['change_set']`` 이 원장 행의 ``change_set_id`` 와 같다
  (관리자 감사 화면이 이 값으로 헤더와 항목을 잇는다).
* **회귀 없음**: AS 타임라인(``as_log`` append-only)·``OrderEvent``·보안로그가 그대로 남는다.
* **저장 선확인**: 행을 단언하기 **전에** 응답 코드와 저장된 본문을 먼저 확인한다 — 요청이
  500 으로 죽어도 "행 없음" 단언은 공짜로 통과하기 때문이다.

라벨(``path_label``) 단언은 여기 없다 — 라벨 등재는 별도 task 소유다.
"""

from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, OrderFieldChange, SecurityLog, User

#: 원장 ``path`` 는 점 경로 그대로다. 경로 문자열을 바꾸면 과거 행과 이력이 끊기므로
#: 레지스트리를 재사용하지 않고 문자열을 박아 대조한다.
AS_CONTENT_PATH = "shipment.as_content"


# --------------------------------------------------------------------------
# 픽스처
# --------------------------------------------------------------------------
def _login(client, username="gap-as-admin"):
    """AS 접수 권한이 있는 관리자로 로그인하고 user id 를 돌려준다."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="ADMIN",
        team="CS",
        name="AS 감사 관리자",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    user_id = user.id
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = username
        sess["role"] = "ADMIN"
    return user_id


def _create_order(*, shipment=None, status="CS"):
    """AS 접수 대상 주문 1건(원하는 ``shipment`` 초기값과 함께)."""
    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="AS 감사 고객",
        phone="010-1234-5678",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="Alice",
        is_erp_order=True,
        structured_data={"workflow": {"stage": status}, "shipment": dict(shipment or {})},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _register(client, order_id, as_content):
    return client.post(
        f"/api/orders/{order_id}/as/register", json={"as_content": as_content}
    )


def _stored(order_id):
    """저장된 ``structured_data.shipment`` (요청 뒤 재조회)."""
    db_session.expire_all()
    return (db_session.get(Order, order_id).structured_data or {}).get("shipment") or {}


def _ledger(order_id, path=None):
    db_session.expire_all()
    query = db_session.query(OrderFieldChange).filter(OrderFieldChange.order_id == order_id)
    if path is not None:
        query = query.filter(OrderFieldChange.path == path)
    return query.order_by(OrderFieldChange.id).all()


def _logs(order_id, action="AS_RECEIVED"):
    db_session.expire_all()
    return (
        db_session.query(SecurityLog)
        .filter(SecurityLog.action == action, SecurityLog.target_id == order_id)
        .order_by(SecurityLog.id)
        .all()
    )


def _events(order_id, event_type="AS_REGISTERED"):
    db_session.expire_all()
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == event_type)
        .order_by(OrderEvent.id)
        .all()
    )


# --------------------------------------------------------------------------
# 1. 새 건 접수 — 기존 본문을 덮어쓰면 원장에 남는다
# --------------------------------------------------------------------------
def test_new_cycle_register_records_as_content_overwrite(client):
    """cycle 이 없는 legacy AS 주문(본문만 있음)에 새로 접수하면 덮어쓴 사실이 남는다.

    운영 620건의 모양이 이것이다 — ``shipment.as_content`` 는 있고 ``as_lifecycle`` 은 없다.
    """
    order_id = _create_order(shipment={"as_content": "이전 접수 본문"})
    actor_id = _login(client, "gap-as-newcycle")

    res = _register(client, order_id, "새 접수 본문")

    # 저장이 실제로 반영됐는지 먼저 확인한다(500 이면 아래 행 단언이 공짜로 통과한다).
    assert res.status_code == 200, res.get_data(as_text=True)
    assert res.get_json()["is_new_cycle"] is True
    assert "새 접수 본문" in _stored(order_id)["as_content"]

    rows = _ledger(order_id, AS_CONTENT_PATH)
    assert len(rows) == 1, "본문 덮어쓰기가 원장에 1건 남아야 한다"
    assert rows[0].before_value == "이전 접수 본문"
    assert "새 접수 본문" in rows[0].after_value
    assert rows[0].op == "set"
    assert rows[0].actor_user_id == actor_id
    assert rows[0].order_id == order_id


def test_first_register_records_as_content_add(client):
    """본문이 없던 주문의 첫 접수는 ``add`` 로 남는다(빈값 → 값)."""
    order_id = _create_order()
    _login(client, "gap-as-add")

    res = _register(client, order_id, "첫 접수 본문")

    assert res.status_code == 200, res.get_data(as_text=True)
    assert "첫 접수 본문" in _stored(order_id)["as_content"]

    rows = _ledger(order_id, AS_CONTENT_PATH)
    assert len(rows) == 1
    assert rows[0].before_value is None
    assert "첫 접수 본문" in rows[0].after_value
    assert rows[0].op == "add"


def test_register_with_empty_content_records_clear(client):
    """본문을 비우는 접수도 남는다 — 지운 것이 기록되지 않으면 원장의 존재 이유가 없다."""
    order_id = _create_order(shipment={"as_content": "지워질 본문"})
    _login(client, "gap-as-clear")

    res = _register(client, order_id, "")

    assert res.status_code == 200, res.get_data(as_text=True)
    assert not _stored(order_id).get("as_content")

    rows = _ledger(order_id, AS_CONTENT_PATH)
    assert len(rows) == 1
    assert rows[0].before_value == "지워질 본문"
    assert rows[0].after_value is None
    assert rows[0].op == "clear"


# --------------------------------------------------------------------------
# 2. 열린 건 재접수 — 새 cycle 없이 본문만 갱신하는 경로
# --------------------------------------------------------------------------
def test_reregistration_records_as_content_overwrite(client):
    """열린 AS 건 재접수(새 cycle 아님)의 본문 갱신도 같은 경로로 남는다."""
    order_id = _create_order()
    _login(client, "gap-as-rereg")
    assert _register(client, order_id, "접수 본문 1").status_code == 200
    rows_before = len(_ledger(order_id))

    res = _register(client, order_id, "접수 본문 2")

    assert res.status_code == 200, res.get_data(as_text=True)
    assert res.get_json()["is_new_cycle"] is False, "열린 건 재접수여야 한다"
    assert "접수 본문 2" in _stored(order_id)["as_content"]

    rows = _ledger(order_id, AS_CONTENT_PATH)
    assert len(rows) == 2, "첫 접수 1건 + 재접수 1건"
    assert "접수 본문 1" in rows[1].before_value
    assert "접수 본문 2" in rows[1].after_value
    assert rows[1].op == "set"
    assert len(_ledger(order_id)) > rows_before
    assert rows[0].change_set_id != rows[1].change_set_id, "저장마다 다른 묶음 id 여야 한다"


# --------------------------------------------------------------------------
# 3. 무변경 저장은 행을 만들지 않는다
# --------------------------------------------------------------------------
def test_unchanged_reregistration_writes_no_ledger_row(client):
    """같은 본문 재제출(재접수 모달 무편집)은 원장을 늘리지 않는다.

    무편집 제출이 행을 쌓으면 진짜 본문 교체가 소음에 묻힌다.
    """
    order_id = _create_order()
    _login(client, "gap-as-noop")
    assert _register(client, order_id, "그대로인 본문").status_code == 200
    rows_before = len(_ledger(order_id))
    content_before = _stored(order_id)["as_content"]

    res = _register(client, order_id, "그대로인 본문")

    assert res.status_code == 200, res.get_data(as_text=True)
    assert res.get_json()["is_new_cycle"] is False
    assert _stored(order_id)["as_content"] == content_before, "본문은 그대로여야 한다"
    assert len(_ledger(order_id)) == rows_before, "무변경 저장은 행을 만들지 않는다"
    assert len(_ledger(order_id, AS_CONTENT_PATH)) == 1, "첫 접수 1건뿐"


# --------------------------------------------------------------------------
# 4. 감사 헤더 ↔ 원장 항목 조인
# --------------------------------------------------------------------------
def test_security_log_change_set_matches_ledger_row(client):
    """보안로그 ``detail['change_set']`` 이 원장 행의 ``change_set_id`` 와 같다.

    관리자 감사 화면이 ``detail->>'change_set'`` 으로 헤더와 항목을 잇는다 — 값이 어긋나면
    행은 있는데 화면에는 안 뜬다.
    """
    order_id = _create_order(shipment={"as_content": "이전 본문"})
    _login(client, "gap-as-changeset")

    res = _register(client, order_id, "바뀐 본문")

    assert res.status_code == 200, res.get_data(as_text=True)
    assert "바뀐 본문" in _stored(order_id)["as_content"]

    rows = _ledger(order_id, AS_CONTENT_PATH)
    logs = _logs(order_id)
    assert len(rows) == 1
    assert len(logs) == 1, "AS_RECEIVED 감사 헤더는 접수 1회당 1건"
    assert logs[0].detail.get("change_set"), "감사 헤더에 change_set 이 없다"
    assert logs[0].detail["change_set"] == rows[0].change_set_id


def test_no_new_audit_action_is_introduced(client):
    """접수 감사는 기존 ``AS_RECEIVED`` 를 그대로 쓴다(신규 action 코드 금지)."""
    order_id = _create_order()
    _login(client, "gap-as-action")

    assert _register(client, order_id, "본문").status_code == 200

    db_session.expire_all()
    actions = {
        log.action
        for log in db_session.query(SecurityLog)
        .filter(SecurityLog.target_id == order_id, SecurityLog.target_type == "order")
        .all()
    }
    assert actions == {"AS_RECEIVED"}


# --------------------------------------------------------------------------
# 5. 회귀 — 타임라인·이벤트는 그대로
# --------------------------------------------------------------------------
def test_as_timeline_and_event_survive_ledger_wiring(client):
    """원장 배선이 AS 타임라인(append-only)·OrderEvent·보안로그를 깨지 않는다."""
    order_id = _create_order()
    _login(client, "gap-as-regression")

    assert _register(client, order_id, "접수 원문").status_code == 200

    log = _stored(order_id).get("as_log") or []
    kinds = [entry.get("type") for entry in log]
    texts = [entry.get("text") for entry in log]
    assert "reception" in kinds, "접수 원문이 타임라인에 남아야 한다"
    assert any("접수 원문" in (text or "") for text in texts)
    assert "AS 접수됨" in texts, "접수 사실 system 항목이 남아야 한다"
    assert len(_events(order_id)) == 1
    assert len(_logs(order_id)) == 1

    # 재접수 후에도 append-only 는 줄지 않는다(원장은 별도 축이다).
    assert _register(client, order_id, "두 번째 원문").status_code == 200
    log_after = _stored(order_id).get("as_log") or []
    assert len(log_after) > len(log)
    assert any("접수 원문" in (entry.get("text") or "") for entry in log_after)


def test_as_log_is_not_recorded_in_field_change_ledger(client):
    """``shipment.as_log`` 은 별도 원장(append-only 타임라인)이라 변경 원장에 실리지 않는다."""
    order_id = _create_order()
    _login(client, "gap-as-logaxis")

    assert _register(client, order_id, "본문").status_code == 200

    paths = {row.path for row in _ledger(order_id)}
    assert AS_CONTENT_PATH in paths
    assert not any(path.startswith("shipment.as_log") for path in paths)
