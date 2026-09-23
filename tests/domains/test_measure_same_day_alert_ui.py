"""당일 실측 긴급 추가 — 화면 확인창·미확인 재조회 API 계약.

왜: 확인창은 socket 으로 받은 순간에만 떴다. 소켓이 끊긴 동안(화면 꺼짐·이동 중) 온
긴급 실측 알림은 영영 뜨지 않고, 탭을 여러 개 열면 한 탭에서 확인해도 다른 탭에 창이 남았다.
여기서 고정하는 것:
  - `GET /erp/api/notifications/pending-interrupts` 는 **본인** 미확인(ack·보관 안 됨) 오늘
    당일 실측 알림만 돌려준다(도면 수정 요청은 대상 아님 — 도면 동작 불변).
  - 레이아웃 두 분기(인라인 + 사본)가 소켓 재연결 때 같은 재조회 줄을 부른다.
  - 탭 간 동기 채널·재조회 모듈 문자열 계약, 두 JS 파일 300줄 미만.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.notifications import measure_same_day as msd
from foms.services.datetime_kst import get_today_kst, now_utc_naive, to_utc_naive
from models import (
    Notification,
    NotificationRecipientSource,
    NotificationUserState,
    Order,
    User,
)

ROOT = Path(__file__).resolve().parents[2]
ENDPOINT = "/erp/api/notifications/pending-interrupts"
MEASURE_TYPE = "MEASURE_SAME_DAY_ADDED"
RESYNC_LINE = (
    "if (window.FOMSAlertSync && typeof window.FOMSAlertSync.resync === 'function') "
    "{ window.FOMSAlertSync.resync('socket-connect'); }"
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _make_user(username, *, team="SALES", name="영업"):
    user = User(
        username=username,
        password=generate_password_hash("pass"),
        role="MANAGER",
        team=team,
        name=name,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    # 요청 뒤에는 scoped 세션이 닫혀 인스턴스가 분리된다 — 필요한 값만 dict 로 받는다.
    info = user if isinstance(user, dict) else {
        "id": user.id, "username": user.username, "role": user.role,
    }
    with client.session_transaction() as sess:
        sess["user_id"] = info["id"]
        sess["username"] = info["username"]
        sess["role"] = info["role"]
    return info


@pytest.fixture(autouse=True)
def _no_real_dispatch(monkeypatch):
    # 오늘 실측 주문을 만들면 감지 리스너가 별도 알림을 만들어 집계를 흐린다 — 예약만 막는다.
    monkeypatch.setattr(msd, "reserve_measure_same_day_alert", lambda *_a, **_k: None)


def _make_order(customer_name="긴급고객", *, measure_date=None, **extra):
    # 재조회 API 는 실측일에 아직 오늘이 있는 주문만 돌려준다.
    measure_date = measure_date or get_today_kst().isoformat()
    order = Order(
        received_date=get_today_kst().strftime("%Y-%m-%d"),
        customer_name=customer_name,
        phone="010-0000-0000",
        address="서울 강남구 테헤란로 1",
        product="붙박이장",
        status="RECEIVED",
        manager_name="담당영업",
        measurement_time="14:00",
        is_erp_order=True,
        structured_data={
            "parties": {"customer": {"name": customer_name}},
            "schedule": {"measurement": {"date": measure_date, "time": "14:00"}},
        },
        **extra,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _make_notification(order, *, ntype=MEASURE_TYPE, created_at=None, by="추가자"):
    notif = Notification(
        order_id=order.id if order is not None else None,
        notification_type=ntype,
        target_type="TEAM",
        target_team="SALES",
        title="오늘 실측이 긴급 추가됐어요",
        message="당일 실측",
        created_by_name=by,
        created_at=created_at or now_utc_naive(),
    )
    db_session.add(notif)
    db_session.commit()
    return notif


def _make_state(notif, user, **kwargs):
    state = NotificationUserState(
        notification_id=notif.id,
        user_id=user.id,
        recipient_source=NotificationRecipientSource.TARGET_TEAM,
        **kwargs,
    )
    db_session.add(state)
    db_session.commit()
    return state


def _items(client):
    res = client.get(ENDPOINT)
    assert res.status_code == 200, res.get_data(as_text=True)
    body = res.get_json()
    assert body["success"] is True
    assert body["error"] is None
    return body["data"]["items"]


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def test_pending_interrupts_returns_only_my_unacked_today_measure_alerts(client):
    me = _make_user("msd_ui_me", name="나영업")
    other = _make_user("msd_ui_other", name="남영업")
    order = _make_order()

    mine = _make_notification(order)
    _make_state(mine, me)

    # 다른 사람 state 만 있는 알림 — 나에게는 안 나온다.
    others_only = _make_notification(order)
    _make_state(others_only, other)

    # 이미 확인(ack)한 건, 보관한 건 — 제외.
    acked = _make_notification(order)
    _make_state(acked, me, ack_at=now_utc_naive())
    archived = _make_notification(order)
    _make_state(archived, me, archived_at=now_utc_naive())

    # 어제(KST) 만든 건 — 제외.
    today_start_utc = to_utc_naive(
        dt.datetime.combine(get_today_kst(), dt.time.min), assume_utc_if_naive=False
    )
    yesterday = _make_notification(order, created_at=today_start_utc - dt.timedelta(minutes=1))
    _make_state(yesterday, me)

    # 도면 수정 요청 — 이 API 대상이 아니다(도면 확인창 동작 불변).
    drawing = _make_notification(order, ntype="DRAWING_REVISION_REQUESTED")
    _make_state(drawing, me)

    mine_id, others_only_id, order_id = mine.id, others_only.id, order.id
    other_info = {"id": other.id, "username": other.username, "role": other.role}

    _login(client, me)
    items = _items(client)
    assert [item["notification_id"] for item in items] == [mine_id]

    item = items[0]
    assert item["interrupt"] is True
    assert item["alert_kind"] == "measure_same_day"
    assert item["order_id"] == order_id
    assert item["order_url"].startswith("/erp/")
    assert "urgent" not in item
    for key in ("customer_name", "area", "time", "manager", "added_by", "added_at"):
        assert key in item, key

    # 다른 사람 로그인 시에는 자기 것만.
    _login(client, other_info)
    assert [item["notification_id"] for item in _items(client)] == [others_only_id]


def test_pending_interrupts_oldest_first_and_capped_at_five(client):
    me = _make_user("msd_ui_cap")
    order = _make_order("상한고객")
    base = now_utc_naive() - dt.timedelta(seconds=30)
    created = []
    for i in range(7):
        notif = _make_notification(order, created_at=base + dt.timedelta(seconds=i))
        _make_state(notif, me)
        created.append(notif.id)
    _login(client, me)
    ids = [item["notification_id"] for item in _items(client)]
    assert ids == created[:5]


def test_pending_interrupts_skips_orders_no_longer_today(client):
    me = _make_user("msd_ui_stale")
    live = _make_order("살아있는고객")
    moved = _make_order("옮긴고객", measure_date="2099-01-01")
    deleted = _make_order("삭제고객", deleted_at="2026-09-01 10:00:00")
    ids = {}
    for key, order in (("live", live), ("moved", moved), ("deleted", deleted)):
        notif = _make_notification(order)
        _make_state(notif, me)
        ids[key] = notif.id
    _login(client, me)
    assert [item["notification_id"] for item in _items(client)] == [ids["live"]]


def test_pending_interrupts_requires_login(client):
    res = client.get(ENDPOINT)
    assert res.status_code in (301, 302, 401, 403)


# ---------------------------------------------------------------------------
# 화면 문자열 계약
# ---------------------------------------------------------------------------


def test_socket_connect_resyncs_in_both_layout_branches():
    head = _read("templates/partials/shared/layout_head.html")
    init_js = _read("static/js/runtime/layout-head-init.js")
    for text in (head, init_js):
        assert RESYNC_LINE in text
        # 기존 배지 갱신·등급 분기는 그대로.
        assert "refreshErpNotificationUI({ reason: 'socket-connect' });" in text
        assert "window.FOMSDrawingAlert.handle(data)" in text
        assert "triggerUrgentBriefingAlert(data)" in text


def test_alert_sync_module_contract():
    js = _read("static/js/foms/foms-alert-sync.js")
    assert "BroadcastChannel('foms-alerts')" in js
    assert "typeof window.BroadcastChannel === 'function'" in js  # 미지원 가드
    assert "'/erp/api/notifications/pending-interrupts'" in js
    assert "data.success" in js
    assert "credentials: 'same-origin'" in js
    assert "sessionStorage" in js
    assert "'foms:alert-ack'" in js
    assert "visibilitychange" in js
    assert "window.FOMSAlertSync" in js
    assert "innerHTML" not in js


def test_dialog_module_renders_measure_kind_and_queues():
    js = _read("static/js/foms/foms-drawing-alert.js")
    assert "measure_same_day" in js
    assert "visibilityState" in js
    assert "'foms:alert-ack'" in js
    assert "'foms:alert-shown'" in js
    assert "dismiss: dismiss" in js
    assert "markShown: markShown" in js
    assert "queue.push(" in js
    # 당일 실측 분기는 textContent 로만 그린다.
    measure_block = js.split("data.alert_kind === MEASURE_KIND", 1)[1].split("} else {", 1)[0]
    assert "innerHTML" not in measure_block
    assert "safeOrderUrl(data.order_url)" in measure_block
    # AudioContext 는 하나만 만들어 재사용한다.
    assert js.count("new Ctx()") == 1


def test_layout_scripts_loads_sync_module_deferred():
    scripts = _read("templates/partials/shared/layout_scripts.html")
    tags = [line for line in scripts.splitlines() if "js/foms/foms-alert-sync.js" in line]
    assert len(tags) == 1
    assert "defer" in tags[0]
    assert "?v=20260923a" in tags[0]
    alert_idx = scripts.index("js/foms/foms-drawing-alert.js")
    sync_idx = scripts.index("js/foms/foms-alert-sync.js")
    assert alert_idx < sync_idx


def test_alert_js_files_stay_under_300_lines():
    for rel in ("static/js/foms/foms-drawing-alert.js", "static/js/foms/foms-alert-sync.js"):
        lines = _read(rel).splitlines()
        assert len(lines) < 300, (rel, len(lines))
