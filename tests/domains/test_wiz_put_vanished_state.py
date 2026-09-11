"""DATA-01 도면 마법사 PUT — 사라진 서버 상태 위의 저장 차단 + 자동/수동 감사 계측.

2026-09-10 주문 5177 사고의 두 번째 구멍을 고정한다.

폼 전체 저장(``PUT /api/orders/<id>/structured``, mode=full)이 ``structured_data``
최상위의 ``drawing_wizard`` 키를 통째로 지웠다. 그 뒤 마법사가 열렸을 때 GET 은
``state: null`` 을 줬고(``foms/api/drawing/wizard.py`` ``api_get_drawing_wizard``),
클라이언트는 빈 상태로 렌더한 뒤 저장을 보냈다. 그런데 당시 ``_mutate`` 의 stale 검사는

    if isinstance(saved, dict) and saved.get('updated_at') != (base_updated_at or None):

라서 ``saved is None`` 이면 검사를 **통째로 건너뛰었다** — 상태가 사라진 직후의 첫 저장은
base_updated_at 이 무엇이든 무조건 200 이었다. 이제 ``base_updated_at`` 이 실려 있는데
서버 상태가 없으면 409(``conflict_reason='vanished'``)로 막는다.

**음성 대조군을 함께 둔다**(과잉 수정 방지):

* ``base_updated_at`` 이 없는 정상 최초 저장은 그대로 200 이어야 한다.
* 기존 stale 경로(다른 사용자가 먼저 저장)는 그대로 409 + ``conflict_reason='stale'``.
* 빈 ``objects`` 저장 금지는 **하지 않는다** — 사용자가 전부 지우는 것은 정당한 편집이고,
  서버는 '지운 것'과 '못 불러온 것'을 내용만으로 구분할 근거가 없다. 그 증거는 기존
  ``tests/domains/test_wiz_put.py`` 가 ``objects: []`` 로 계속 green 인 것이다.

픽스처·클라이언트 패턴은 ``tests/domains/test_wiz_put.py`` 를 그대로 재사용한다.
"""

import copy
from datetime import date

from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, SecurityLog, User

#: 사고 당시 클라이언트가 들고 있었을 법한 base(서버에서 이미 사라진 상태의 updated_at).
_VANISHED_BASE = "2026-09-10 00:15:17"


def _login_admin(client, username="wiz-vanish-admin"):
    user = User(
        username=username,
        password=generate_password_hash("x"),
        role="ADMIN",
        team="DRAWING",
        name=f"{username}-name",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _erp_order():
    """drawing_wizard 키가 **없는** ERP 주문(= 폼 저장이 키를 지운 뒤의 모습)."""
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"),
        customer_name="임인경",
        phone="010-3333-4444",
        address="양산",
        product="붙박이장",
        status="DRAWING",
        manager_name="하우드 김성일",
        is_erp_order=True,
        structured_data={"parties": {"customer": {"name": "임인경"}}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _pen(oid="o1"):
    return {
        "type": "pen",
        "id": oid,
        "points": [10, 10, 20, 20, 30, 30],
        "stroke": "#111111",
        "strokeWidth": 2,
    }


def _state(sheet_name="도면 1", objects=None):
    return {
        "v": 1,
        "sheets": [
            {
                "id": "s-1",
                "name": sheet_name,
                "form": {},
                "objects": list(objects if objects is not None else []),
            }
        ],
    }


def _put(client, order_id, state, base=None, auto=None, headers=None):
    body = {"state": state, "base_updated_at": base}
    if auto is not None:
        body["auto"] = auto
    return client.put(
        f"/api/orders/{order_id}/drawing-wizard",
        json=body,
        headers=headers or {},
    )


def _stored_dw(order_id):
    db_session.expire_all()
    order = db_session.query(Order).filter_by(id=order_id).first()
    return (order.structured_data or {}).get("drawing_wizard")


# --------------------------------------------------------------------------- #
# 1. 사라진 서버 상태 위의 저장 → 409 vanished (이 버그를 빨갛게 만드는 계약)
# --------------------------------------------------------------------------- #
def test_put_conflicts_when_server_state_vanished(client):
    """base_updated_at 은 있는데 서버 drawing_wizard 가 없으면 409 + vanished, 덮어쓰기 0."""
    _login_admin(client)
    order = _erp_order()
    order_id = order.id
    assert _stored_dw(order_id) is None  # 전제: 폼 저장이 키를 지운 상태

    resp = _put(client, order_id, _state("빈 캔버스"), base=_VANISHED_BASE)

    assert resp.status_code == 409, resp.get_json()
    body = resp.get_json()
    assert body["error"] == "conflict"
    assert body["conflict_reason"] == "vanished"
    # 채택할 서버 값이 없으므로 server_updated_* 는 비어 있다(클라가 base 로 삼으면 안 된다).
    assert body["server_updated_at"] is None
    assert body["server_updated_by_name"] is None

    # 핵심: 409 로 막힌 저장이 새 상태를 만들지 않았다(빈 캔버스가 자리를 차지하지 않는다).
    assert _stored_dw(order_id) is None


# --------------------------------------------------------------------------- #
# 2. 음성 대조군 — 정상 최초 저장은 그대로 통과해야 한다
# --------------------------------------------------------------------------- #
def test_put_still_allows_first_ever_save(client):
    """base_updated_at 이 없으면(진짜 최초 저장) 200 이고 상태가 생성된다."""
    _login_admin(client)
    order = _erp_order()
    order_id = order.id

    resp = _put(client, order_id, _state("도면 1", objects=[_pen()]), base=None)

    assert resp.status_code == 200, resp.get_json()
    dw = _stored_dw(order_id)
    assert dw is not None
    assert dw["sheets"][0]["name"] == "도면 1"
    assert len(dw["sheets"][0]["objects"]) == 1
    assert dw["updated_at"] == resp.get_json()["data"]["updated_at"]


# --------------------------------------------------------------------------- #
# 3. 음성 대조군 2 — 기존 stale 경로는 그대로 stale 로 남는다
# --------------------------------------------------------------------------- #
def test_put_stale_conflict_still_reports_stale(client):
    """서버 상태가 살아 있는데 base 가 다르면 종전대로 409 + conflict_reason='stale'."""
    _login_admin(client)
    order = _erp_order()
    order_id = order.id

    first = _put(client, order_id, _state(), base=None)
    assert first.status_code == 200, first.get_json()

    # 오래된 base(None)로 재저장 → stale.
    conflict = _put(client, order_id, _state("stale"), base=None)
    assert conflict.status_code == 409, conflict.get_json()
    body = conflict.get_json()
    assert body["error"] == "conflict"
    assert body["conflict_reason"] == "stale"
    assert body["server_updated_at"]
    assert body["server_updated_by_name"]
    # 충돌 저장은 반영되지 않는다.
    assert _stored_dw(order_id)["sheets"][0]["name"] == "도면 1"


# --------------------------------------------------------------------------- #
# 4. 감사 계측 — 자동/수동 구분과 규모(sheets·objects)를 남긴다
# --------------------------------------------------------------------------- #
def _saved_logs(order_id):
    db_session.expire_all()
    return (
        db_session.query(SecurityLog)
        .filter(
            SecurityLog.target_id == order_id,
            SecurityLog.action == "DRAWING_WIZARD_SAVED",
        )
        .order_by(SecurityLog.id)
        .all()
    )


def test_put_audit_records_auto_flag(client):
    """auto=True PUT 의 감사 detail 에 auto·sheets·objects 가 남는다(정황 추론 종료)."""
    _login_admin(client)
    order = _erp_order()
    order_id = order.id

    state = _state("도면 1", objects=[_pen("o1"), _pen("o2")])
    resp = _put(client, order_id, state, base=None, auto=True)
    assert resp.status_code == 200, resp.get_json()

    logs = _saved_logs(order_id)
    assert len(logs) == 1, logs
    detail = logs[0].detail
    assert detail["auto"] is True
    assert detail["sheets"] == 1
    assert detail["objects"] == 2


def test_put_audit_auto_defaults_false_when_absent(client):
    """auto 를 안 보내는 구 클라이언트는 auto=False 로 기록된다(하위호환)."""
    _login_admin(client)
    order = _erp_order()
    order_id = order.id

    resp = _put(client, order_id, _state("도면 1", objects=[_pen()]), base=None)
    assert resp.status_code == 200, resp.get_json()

    detail = _saved_logs(order_id)[0].detail
    assert detail["auto"] is False
    assert detail["sheets"] == 1
    assert detail["objects"] == 1


# --------------------------------------------------------------------------- #
# 5. 사라진 상태 뒤 정상 복구 경로 — 새로고침(base=None)이면 다시 저장할 수 있다
# --------------------------------------------------------------------------- #
def test_put_after_vanished_conflict_succeeds_on_reload(client):
    """409 vanished 뒤 클라가 새로고침해 base=None 으로 다시 저장하면 통과한다."""
    _login_admin(client)
    order = _erp_order()
    order_id = order.id

    blocked = _put(client, order_id, _state(), base=_VANISHED_BASE)
    assert blocked.status_code == 409

    retry = _put(client, order_id, _state("복구", objects=[_pen()]), base=None)
    assert retry.status_code == 200, retry.get_json()
    assert _stored_dw(order_id)["sheets"][0]["name"] == "복구"


# --------------------------------------------------------------------------- #
# 6. 회귀 방어 — 살아 있는 상태 위의 정상 저장은 pending 을 잃지 않는다
# --------------------------------------------------------------------------- #
def test_put_on_live_state_still_preserves_server_owned_keys(client):
    """vanished 가드가 기존 projection 보존 계약을 깨지 않았는지 확인."""
    _login_admin(client)
    order = _erp_order()
    order_id = order.id

    first = _put(client, order_id, _state(), base=None)
    base = first.get_json()["data"]["updated_at"]

    db_session.expire_all()
    o = db_session.query(Order).filter_by(id=order_id).first()
    sd = copy.deepcopy(o.structured_data)
    sd["drawing_wizard"]["versions"] = [{"v": 1, "key": "orders/1/versions/v1.json"}]
    o.structured_data = sd
    flag_modified(o, "structured_data")
    db_session.commit()

    second = _put(client, order_id, _state("v2"), base=base)
    assert second.status_code == 200, second.get_json()
    assert _stored_dw(order_id)["versions"] == [
        {"v": 1, "key": "orders/1/versions/v1.json"}
    ]
