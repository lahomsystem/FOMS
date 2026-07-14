"""B2 실측 캡처 API 계약 테스트 (POST /api/erp/measurement/capture/<id>).

앱 요청이 teardown에서 세션을 close → 테스트가 만든 ORM 인스턴스는 detach된다.
따라서 요청 전 정수 id만 확보하고, 요청 후 db_session.remove()로 세션을 리셋한 뒤
새 쿼리로 결과를 검증한다(test_call_log_api 준용).
"""

from datetime import date

from werkzeug.security import generate_password_hash

from foms.web.measurement import dashboard as erp_measurement_dashboard
from db import db_session
from models import Order, OrderEvent, OrderScheduleDate, User

_URL = "/api/erp/measurement/capture/{oid}"


def _login(client, *, username, role, team):
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
    uid = user.id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["username"] = username
        sess["role"] = role
    return uid


def _create_order(*, structured_data=None):
    order = Order(
        received_date="2026-04-07",
        customer_name="실측 대상",
        phone="010-1234-5678",
        address="Seoul",
        product="붙박이장",
        status="MEASURE",
        manager_name="Alice",
        is_erp_order=True,
        structured_data=structured_data if structured_data is not None else {"workflow": {"stage": "MEASURE"}},
    )
    db_session.add(order)
    db_session.commit()
    oid = order.id
    return oid


def _fresh_order(oid):
    db_session.remove()
    return db_session.query(Order).filter_by(id=oid).first()


def test_capture_saves_dims(client, app):
    """dims 저장 → 200, sd['measurement']['dims'] + OrderEvent(MEASUREMENT_DIMS_SAVED)."""
    _login(client, username="meas-dims", role="STAFF", team="CS")
    oid = _create_order()

    resp = client.post(_URL.format(oid=oid), json={"dims": {"w": 2400, "d": 620, "h": 2380}})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True

    refreshed = _fresh_order(oid)
    dims = refreshed.structured_data["measurement"]["dims"]
    assert dims["w"] == 2400
    assert dims["d"] == 620
    assert dims["h"] == 2380
    assert dims["by_name"] == "meas-dims-name"
    assert "noted_at" in dims

    events = db_session.query(OrderEvent).filter_by(order_id=oid, event_type="MEASUREMENT_DIMS_SAVED").all()
    assert len(events) == 1
    assert events[0].payload["has_dims"] is True
    assert events[0].payload["note_len"] == 0


def test_capture_saves_note(client, app):
    """note 저장 → sd['measurement']['note'] 문자열, payload note_len 반영."""
    _login(client, username="meas-note", role="STAFF", team="CS")
    oid = _create_order()

    resp = client.post(_URL.format(oid=oid), json={"note": "좌측 벽면 배관 돌출"})
    assert resp.status_code == 200

    refreshed = _fresh_order(oid)
    assert refreshed.structured_data["measurement"]["note"] == "좌측 벽면 배관 돌출"
    assert "dims" not in refreshed.structured_data["measurement"]

    events = db_session.query(OrderEvent).filter_by(order_id=oid, event_type="MEASUREMENT_DIMS_SAVED").all()
    assert len(events) == 1
    assert events[0].payload["has_dims"] is False
    assert events[0].payload["note_len"] == len("좌측 벽면 배관 돌출")


def test_capture_partial_update_keeps_other_field(client, app):
    """dims 저장 후 note만 저장 → dims 유지(부분 갱신)."""
    _login(client, username="meas-partial", role="STAFF", team="CS")
    oid = _create_order()

    assert client.post(_URL.format(oid=oid), json={"dims": {"w": 3000, "d": 600, "h": 2400}}).status_code == 200
    assert client.post(_URL.format(oid=oid), json={"note": "천장 몰딩 확인"}).status_code == 200

    refreshed = _fresh_order(oid)
    meas = refreshed.structured_data["measurement"]
    assert meas["dims"]["w"] == 3000
    assert meas["note"] == "천장 몰딩 확인"


def test_capture_rejects_out_of_range_dim(client, app):
    """치수 범위(0<v<10000) 위반 → 400, 저장 없음."""
    _login(client, username="meas-range", role="STAFF", team="CS")
    oid = _create_order()

    resp = client.post(_URL.format(oid=oid), json={"dims": {"w": 12000, "d": 600, "h": 2400}})
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False

    refreshed = _fresh_order(oid)
    assert "measurement" not in (refreshed.structured_data or {})


def test_capture_rejects_empty_payload(client, app):
    """dims·note 둘 다 없으면 400."""
    _login(client, username="meas-empty", role="STAFF", team="CS")
    oid = _create_order()

    resp = client.post(_URL.format(oid=oid), json={})
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_capture_forbidden_for_ineligible_team(client, app):
    """자격 없는 팀(DRAWING) → 403, 저장/이벤트 없음."""
    _login(client, username="meas-drawing", role="STAFF", team="DRAWING")
    oid = _create_order()

    resp = client.post(_URL.format(oid=oid), json={"dims": {"w": 2400, "d": 600, "h": 2400}})
    assert resp.status_code == 403

    refreshed = _fresh_order(oid)
    assert "measurement" not in (refreshed.structured_data or {})
    assert db_session.query(OrderEvent).filter_by(order_id=oid).count() == 0


def test_capture_leaves_spec_rows_untouched(client, app):
    """spec_rows·items 등 금액 SSOT는 캡처 저장 후에도 불변."""
    _login(client, username="meas-spec", role="STAFF", team="CS")
    spec_rows = [{"w": 1200, "label": "본체"}]
    items = [{"product_name": "상부장", "price": 500000}]
    oid = _create_order(structured_data={"spec_rows": spec_rows, "items": items})

    resp = client.post(_URL.format(oid=oid), json={"dims": {"w": 2400, "d": 620, "h": 2380}, "note": "메모"})
    assert resp.status_code == 200

    refreshed = _fresh_order(oid)
    assert refreshed.structured_data["spec_rows"] == spec_rows
    assert refreshed.structured_data["items"] == items
    assert refreshed.structured_data["measurement"]["dims"]["w"] == 2400


def test_capture_ui_renders_on_v2_measurement_page(client, monkeypatch):
    """v2 실측 페이지에 캡처 버튼·시트·스테퍼·프리셋 마크업과 저장된 dims 메타가 렌더된다."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    fake_today = date(2026, 4, 8)
    monkeypatch.setattr(erp_measurement_dashboard, "get_today_kst", lambda: fake_today)
    uid = _login(client, username="meas-render", role="ADMIN", team="CS")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(uid))

    today = fake_today.strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="캡처 렌더 고객",
        phone="010-2222-3333",
        address="Seoul",
        product="붙박이장",
        status="MEASURE",
        is_erp_order=True,
        structured_data={
            "items": [{"product_name": "상부장"}],
            "measurement": {"dims": {"w": 2400, "d": 620, "h": 2380}, "note": "기록 메모"},
        },
    )
    db_session.add(order)
    db_session.flush()
    oid = order.id
    db_session.add(OrderScheduleDate(order_id=oid, kind="measurement", date=today, source="beta_schedule"))
    db_session.commit()

    body = client.get("/erp/measurement").get_data(as_text=True)
    assert "data-foms-measure-capture-open" in body        # 진입 버튼
    assert "data-foms-measure-capture-sheet" in body        # 시트
    assert "data-foms-measure-step" in body                 # 스테퍼 ±버튼
    assert 'data-foms-measure-preset="2400"' in body        # W 프리셋 칩
    assert "data-foms-measure-capture-mic" in body          # 음성 버튼
    assert "foms-measure-capture.js" in body                # defer 로드
    assert "W2400·D620·H2380 기록됨" in body                # 카드 메타 행
