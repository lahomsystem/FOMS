"""생산 되돌리기 3종(수정 제작·제작 취소·완료 취소)의 관리자 강제 진행 계약.

``test_admin_override_gates.py`` 와 같은 두 갈래를 본다 — 평소에는 관리자라도 막히고,
``admin_override`` 를 켜면 단계 전제만 건너뛴다. 파일이 갈린 이유는 500줄 상한뿐이다
(``tests/harness/test_file_size_ratchet.py``).

못 뚫는 것도 함께 못박는다 — 닫을 run 이 없는 제작 취소는 권한 문제가 아니라 없는 일을
되돌리라는 요청이다.
"""

from __future__ import annotations

from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, ProductionRun, User

_REASON = "고객 일정 때문에 관리자가 직접 진행"


def _make_user(username: str, *, role: str = "ADMIN", team: str = "PRODUCTION") -> User:
    """테스트 사용자 1명을 만든다."""
    user = User(username=username, password=generate_password_hash("pw"), role=role,
                team=team, name=f"{username} 이름", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    """세션에 로그인시킨다."""
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _make_order(stage_code: str) -> Order:
    """해당 단계에 올라와 있는 ERP 주문 1건."""
    order = Order(received_date=date.today().isoformat(), customer_name="강제 진행 고객",
                  phone="010-0000-0000", address="Seoul", product="붙박이장",
                  status=stage_code, manager_name="Bob", is_erp_order=True,
                  structured_data={"workflow": {"stage": stage_code}},
                  erp_stage_code=stage_code)
    db_session.add(order)
    db_session.commit()
    return order


def _saved(order_id: int) -> Order:
    """현재 커밋된 주문을 다시 읽는다."""
    db_session.expire_all()
    return db_session.get(Order, order_id)


def _override_events(order_id: int) -> list:
    """주문에 남은 ``ADMIN_OVERRIDE_USED`` 이벤트 전부."""
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id,
                OrderEvent.event_type == "ADMIN_OVERRIDE_USED")
        .all()
    )


def _punch() -> dict:
    """관리자 강제 진행 본문(공통 모양)."""
    return {"admin_override": True, "override_reason": _REASON}


def _mint_run(order_id: int) -> ProductionRun:
    """현재 진행 중인 제작 run 1건을 연다."""
    run = ProductionRun(order_id=order_id, status="IN_PROGRESS", steps=[], defects=[],
                        is_current=True)
    db_session.add(run)
    db_session.commit()
    return run


def test_수정_제작은_제작완료가_아니면_평소처럼_막힌다(client):
    """음성 대조군 — 제작완료(CONSTRUCTION)가 아니면 관리자라도 409 다."""
    _login(client, _make_user("rw_plain"))
    oid = _make_order("CS").id

    resp = client.post(f"/api/orders/{oid}/production/rework", json={})

    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert resp.get_json()["code"] == "INVALID_STAGE"
    assert _override_events(oid) == []


def test_수정_제작의_단계_전제를_관리자가_뚫는다(client):
    """ADMIN 뚫기 → 단계 전제를 건너뛰고 제작중으로 되돌린다(이벤트 1행)."""
    _login(client, _make_user("rw_punch"))
    oid = _make_order("CS").id

    resp = client.post(f"/api/orders/{oid}/production/rework", json=_punch())

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _saved(oid).status == "PRODUCTION"
    events = _override_events(oid)
    assert len(events) == 1
    assert events[0].payload["gates"] == ["INVALID_STAGE"]
    assert events[0].payload["from"] == "CS"
    assert events[0].payload["to"] == "PRODUCTION"


def test_제작_취소는_제작중이_아니면_평소처럼_막힌다(client):
    """음성 대조군 — 제작중(PRODUCTION)이 아니면 관리자라도 409 다."""
    _login(client, _make_user("cx_plain"))
    oid = _make_order("CONSTRUCTION").id
    _mint_run(oid)

    resp = client.post(f"/api/orders/{oid}/production/cancel", json={})

    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert "제작중 상태에서만" in resp.get_json()["message"]
    assert _override_events(oid) == []


def test_제작_취소의_단계_전제를_관리자가_뚫는다(client):
    """ADMIN 뚫기 → 단계 축은 그대로 두고 current run 만 닫는다(from/to 는 빈 문자열)."""
    _login(client, _make_user("cx_punch"))
    oid = _make_order("CONSTRUCTION").id
    _mint_run(oid)

    resp = client.post(f"/api/orders/{oid}/production/cancel", json=_punch())

    assert resp.status_code == 200, resp.get_data(as_text=True)
    db_session.expire_all()
    assert db_session.query(ProductionRun).filter_by(
        order_id=oid, is_current=True).count() == 0
    events = _override_events(oid)
    assert len(events) == 1
    assert events[0].payload["gates"] == ["INVALID_STAGE"]
    assert events[0].payload["from"] == ""
    assert events[0].payload["to"] == ""


def test_닫을_run_이_없으면_관리자도_제작_취소를_못_한다(client):
    """음성(못 뚫음) — 없는 일을 되돌리는 것은 권한 문제가 아니다."""
    _login(client, _make_user("cx_norun"))
    oid = _make_order("PRODUCTION").id

    resp = client.post(f"/api/orders/{oid}/production/cancel", json=_punch())

    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert "제작 시작 전" in resp.get_json()["message"]
    assert _override_events(oid) == []


def test_완료_취소는_제작완료가_아니면_평소처럼_막힌다(client):
    """음성 대조군 — 제작완료(CONSTRUCTION)가 아니면 관리자라도 409 다."""
    _login(client, _make_user("uc_plain"))
    oid = _make_order("PRODUCTION").id

    resp = client.post(f"/api/orders/{oid}/production/uncomplete", json={})

    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert resp.get_json()["code"] == "INVALID_STAGE"
    assert _override_events(oid) == []


def test_완료_취소의_단계_전제를_관리자가_뚫는다(client):
    """ADMIN 뚫기 → 하드코딩 CONSTRUCTION 대신 실제 축 값으로 전이한다(계약 C5)."""
    _login(client, _make_user("uc_punch"))
    oid = _make_order("PRODUCTION").id

    resp = client.post(f"/api/orders/{oid}/production/uncomplete", json=_punch())

    assert resp.status_code == 200, resp.get_data(as_text=True)
    events = _override_events(oid)
    assert len(events) == 1
    assert events[0].payload["gates"] == ["INVALID_STAGE"]
    assert events[0].payload["from"] == "PRODUCTION"
    assert events[0].payload["to"] == "PRODUCTION"
