# -*- coding: utf-8 -*-
"""유령 주문 '재결제 예정' — 라우트 · 권한 · 자동 해제 (2026-09-14).

표시를 켜고 끄는 입구가 **하나**이고, 그 입구가 사용자 결정 그대로 열려 있는지를 잰다.

1. 표시는 켤 때만 띠 모집단 안에서 받는다 — **푸는 요청에는 관문을 걸지 않는다**.
   표시가 켜진 주문이 모집단을 벗어나면 푸는 길이 없어져 판정이 영영 잠긴다.
2. 클레임 확정 전에도 표시는 허용한다(확정 전이 오히려 흔하다).
3. 표시된 주문은 휴지통이 잠기고, 풀면 다시 열린다(음성 대조군이 그 자리를 지킨다).
4. 이 화면을 쓰는 사람 모두가 켜고 끈다(ADMIN·MANAGER·STAFF) — 권한 목록 밖은 막힌다.
5. 재결제가 실제로 붙으면 표시는 사실이 아니다 — 세 붙이기 경로에서 저절로 풀린다.
"""
from __future__ import annotations

from db import db_session
from foms.services.integrations.naver_commerce.ghost_orders import (
    find_ghost_orders,
    read_repay_expected,
    set_repay_expected,
)
from models import Order
from tests.services.integrations.naver_ghost_repay_helpers import (  # noqa: F401
    ATTACH_PATH,
    AT_SHAPE,
    DISCARD_PATH,
    REPAY_PATH,
    _ghost,
    _link,
    _login,
    _order,
    _user,
    workbench_on,
)


# --------------------------------------------------------------------------- #
# 라우트 — 표시·해제 · 관문 · 휴지통 방어선
# --------------------------------------------------------------------------- #

def test_the_route_marks_and_clears(app, client, workbench_on):
    """켜면 dict, 끄면 None 을 그대로 돌려준다 — 화면이 다시 그릴 재료다."""
    _login(client)
    order = _ghost(tel="010-7914-0001", order_no="N-RX-9")
    order_id = int(order.id)

    on = client.post(REPAY_PATH.format(order_id),
                     json={"expected": True, "note": "고객이 재결제하겠다고 함"})

    assert on.status_code == 200, on.get_data(as_text=True)
    mark = on.get_json()["data"]["repay_expected"]
    assert isinstance(mark, dict) and mark["note"] == "고객이 재결제하겠다고 함"
    assert AT_SHAPE.match(mark["at"])
    assert mark["by_name"], "누가 표시했는지가 비어 있다"

    off = client.post(REPAY_PATH.format(order_id), json={"expected": False})

    assert off.status_code == 200, off.get_data(as_text=True)
    assert off.get_json()["data"]["repay_expected"] is None
    db_session.expire_all()
    assert read_repay_expected(db_session.get(Order, order_id)) is None


def test_the_route_refuses_an_order_outside_the_band(app, client, workbench_on):
    """띠에 없는 주문은 못 받는다 — 범용 쓰기 경로가 되면 안 된다."""
    _login(client)
    order = _order(tel="010-7914-0002")
    order_id = int(order.id)
    _link(order_no="N-RX-10", amount=100_000, tel="010-7914-0002", order_id=order_id)

    response = client.post(REPAY_PATH.format(order_id), json={"expected": True})

    assert response.status_code == 400
    db_session.expire_all()
    assert read_repay_expected(db_session.get(Order, order_id)) is None


def test_the_route_is_closed_when_the_gate_is_off(app, client):
    """게이트가 꺼져 있으면 라우트도 닫힌다."""
    _login(client)
    order = _ghost(tel="010-7914-0003", order_no="N-RX-11")

    response = client.post(REPAY_PATH.format(int(order.id)), json={"expected": True})

    assert response.status_code == 403


def test_the_route_allows_the_mark_before_the_claim_is_confirmed(app, client, workbench_on):
    """확정 전 건에도 표시는 열린다 — 표시는 파괴적이지 않고, 확정 전이 오히려 흔하다."""
    _login(client)
    order = _ghost(tel="010-7914-0004", order_no="N-RX-12", claim="CANCEL_REQUEST")
    order_id = int(order.id)

    response = client.post(REPAY_PATH.format(order_id), json={"expected": True})

    assert response.status_code == 200, response.get_data(as_text=True)
    db_session.expire_all()
    assert read_repay_expected(db_session.get(Order, order_id)) is not None


def test_the_trash_route_refuses_a_marked_order(app, client, workbench_on):
    """표시된 주문은 접히지 않는다 — 사유를 사람 말로 낸다(되돌리기 어려운 동작)."""
    _login(client)
    order = _ghost(tel="010-7914-0005", order_no="N-RX-13")
    order_id = int(order.id)
    assert client.post(REPAY_PATH.format(order_id),
                       json={"expected": True}).status_code == 200

    response = client.post(DISCARD_PATH.format(order_id), json={})

    assert response.status_code == 400
    assert "재결제 예정" in (response.get_json()["error"] or "")
    db_session.expire_all()
    assert not db_session.get(Order, order_id).deleted_at, "표시가 있는데 접혔다"


def test_the_trash_route_opens_again_once_the_mark_is_cleared(app, client, workbench_on):
    """★ 음성 대조군 — 표시를 풀면 같은 주문·같은 버튼이 그대로 열린다.

    잠긴 사실만 재면 "원래 못 접는 주문이었다"와 구별되지 않는다.
    """
    _login(client)
    order = _ghost(tel="010-7914-0006", order_no="N-RX-14")
    order_id = int(order.id)
    assert client.post(REPAY_PATH.format(order_id),
                       json={"expected": True}).status_code == 200
    assert client.post(DISCARD_PATH.format(order_id), json={}).status_code == 400

    assert client.post(REPAY_PATH.format(order_id),
                       json={"expected": False}).status_code == 200
    response = client.post(DISCARD_PATH.format(order_id), json={})

    assert response.status_code == 200, response.get_data(as_text=True)
    db_session.expire_all()
    assert db_session.get(Order, order_id).deleted_at, "표시를 풀었는데 안 접힌다"


def test_the_audit_row_names_the_actor(app, client, workbench_on, monkeypatch):
    """감사에 **행위자**가 남는다 — 누가 눌렀는지 없는 감사는 절반짜리다."""
    logged: list[dict] = []
    monkeypatch.setattr(
        "foms.web.admin.naver_ingest.log_access",
        lambda message, actor=None, **kw: logged.append(
            {"message": message, "actor": actor, **kw}))
    _login(client)
    order = _ghost(tel="010-7914-0007", order_no="N-RX-15")
    order_id = int(order.id)

    assert client.post(REPAY_PATH.format(order_id),
                       json={"expected": True, "note": "재결제 예정"}).status_code == 200

    assert logged, "감사 호출이 없다"
    assert logged[-1]["action"] == "NAVER_INGEST_GHOST_REPAY_EXPECTED"
    assert logged[-1]["actor"] is not None, "행위자 인자가 비었다(user_id 누락)"
    assert logged[-1]["detail"]["expected"] is True
    assert logged[-1]["detail"]["note"] == "재결제 예정"


# --------------------------------------------------------------------------- #
# 자동 해제 — 재결제가 실제로 붙으면 표시는 사실이 아니다
# --------------------------------------------------------------------------- #

def test_reconcile_succeed_clears_the_mark(app):
    """재결제 정리 승계 뒤 표시가 사라진다 — 붙은 순간 기다림이 끝난다."""
    from foms.services.integrations.naver_commerce.repay_reconcile import run_reconcile

    actor = int(_user().id)
    tel = "010-7915-0001"
    order = _ghost(tel=tel, order_no="N-RX-16")
    order_id = int(order.id)
    set_repay_expected(order, actor_user_id=actor, note="재결제 예정")
    db_session.commit()
    fresh = _link(order_no="N-RX-16R", amount=1_200_000, tel=tel)

    run_reconcile(db_session, link_id=int(fresh.id), order_id=order_id,
                  relation="REPAY", fork="SUCCEED", actor_user_id=actor)
    db_session.commit()
    db_session.expire_all()

    assert read_repay_expected(db_session.get(Order, order_id)) is None


def test_reconcile_discard_clears_the_mark(app):
    """취소 처리 갈래도 표시를 지운다 — 접힌 주문이 죽은 표시를 들고 되살아나지 않게."""
    from foms.services.integrations.naver_commerce.repay_reconcile import run_reconcile

    actor = int(_user().id)
    tel = "010-7915-0002"
    order = _ghost(tel=tel, order_no="N-RX-17")
    order_id = int(order.id)
    set_repay_expected(order, actor_user_id=actor, note="재결제 예정")
    db_session.commit()
    fresh = _link(order_no="N-RX-17R", amount=800_000, tel=tel)

    run_reconcile(db_session, link_id=int(fresh.id), order_id=order_id,
                  relation="REPAY", fork="DISCARD", actor_user_id=actor)
    db_session.commit()
    db_session.expire_all()

    assert read_repay_expected(db_session.get(Order, order_id)) is None


def test_the_attach_route_clears_the_mark(app, client, workbench_on):
    """일반 ``/attach`` 로 붙여도 풀린다 — 승계 화면만 고치면 표시가 남는다."""
    _login(client)
    tel = "010-7915-0003"
    order = _ghost(tel=tel, order_no="N-RX-18")
    order_id = int(order.id)
    set_repay_expected(order, actor_user_id=1, note="재결제 예정")
    db_session.commit()
    fresh = _link(order_no="N-RX-18R", amount=950_000, tel=tel)

    response = client.post(ATTACH_PATH.format(int(fresh.id)),
                           json={"order_id": order_id, "relation": "REPAY"})

    assert response.status_code == 200, response.get_data(as_text=True)
    db_session.expire_all()
    assert read_repay_expected(db_session.get(Order, order_id)) is None


# --------------------------------------------------------------------------- #
# 권한 — 이 화면을 쓰는 사람 모두 (+ 음성 대조군)
# --------------------------------------------------------------------------- #

def test_a_staff_can_mark_and_clear(app, client, workbench_on):
    """★ STAFF 도 켜고 끈다 — 되돌릴 수 있는 표시라 휴지통보다 문턱이 낮다.

    음성 대조군은 **권한 목록 밖 역할**이다(VIEWER). 전 테스트가 기본값 ADMIN 으로만
    돌면 나중에 권한을 ADMIN 으로 좁혀도 전부 초록이라 사용자 결정이 조용히 뒤집힌다.
    """
    _login(client, role="STAFF")
    order = _ghost(tel="010-7916-0001", order_no="N-RX-20")
    order_id = int(order.id)

    on = client.post(REPAY_PATH.format(order_id),
                     json={"expected": True, "note": "재결제 예정"})

    assert on.status_code == 200, on.get_data(as_text=True)
    db_session.expire_all()
    assert read_repay_expected(db_session.get(Order, order_id)) is not None

    off = client.post(REPAY_PATH.format(order_id), json={"expected": False})

    assert off.status_code == 200, off.get_data(as_text=True)
    db_session.expire_all()
    assert read_repay_expected(db_session.get(Order, order_id)) is None

    # ★ 음성 대조군 — 권한 목록 밖 역할은 같은 주문·같은 본문으로도 못 쓴다.
    _login(client, role="VIEWER")
    denied = client.post(REPAY_PATH.format(order_id), json={"expected": True})

    assert denied.status_code in (302, 403), denied.status_code
    db_session.expire_all()
    assert read_repay_expected(db_session.get(Order, order_id)) is None, \
        "권한 없는 역할이 표시를 남겼다"


# --------------------------------------------------------------------------- #
# 푸는 길은 막지 않는다 — 모집단 관문은 켤 때만
# --------------------------------------------------------------------------- #

def test_clearing_is_allowed_outside_the_band(app, client, workbench_on):
    """표시가 켜진 주문이 띠를 벗어나도 **푸는 길은 남는다**.

    클레임이 거부·철회되면 그 주문은 더 이상 '전부 취소'가 아니라 띠에서 사라진다.
    해제까지 모집단 관문에 걸면 행도 없고 pane 버튼은 400 이라, 판정이 `접을 수 없음`
    에 영영 물린다. 해제는 파괴적이지 않으니 관문을 걸 이유가 없다.
    """
    _login(client)
    tel = "010-7916-0002"
    order = _ghost(tel=tel, order_no="N-RX-21")
    order_id = int(order.id)
    assert client.post(REPAY_PATH.format(order_id),
                       json={"expected": True}).status_code == 200

    # 살아 있는 결제가 하나 붙으면 '전부 취소'가 깨져 띠 모집단에서 빠진다.
    _link(order_no="N-RX-21B", amount=400_000, tel=tel, order_id=order_id)
    rows = find_ghost_orders(db_session, limit=1000)["rows"]
    assert not [row for row in rows if row["order_id"] == order_id], "아직 띠에 남아 있다"
    assert client.post(REPAY_PATH.format(order_id),
                       json={"expected": True}).status_code == 400, \
        "켜는 요청은 여전히 띠 모집단 안에서만 받아야 한다"

    off = client.post(REPAY_PATH.format(order_id), json={"expected": False})

    assert off.status_code == 200, off.get_data(as_text=True)
    db_session.expire_all()
    assert read_repay_expected(db_session.get(Order, order_id)) is None
