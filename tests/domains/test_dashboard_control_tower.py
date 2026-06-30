"""컨트롤 타워 준비도/잔금 분류기 계약 테스트 (DB 불필요, 순수 함수)."""

from foms.services.orders import dashboard_control_tower as ct


class _Order:
    """경량 Order 스텁 (flat 컬럼 + structured_data만 노출)."""

    def __init__(self, **kw):
        self.id = kw.get("id", 1)
        self.erp_stage_code = kw.get("erp_stage_code")
        self.manager_name = kw.get("manager_name")
        self.structured_data = kw.get("structured_data")


def test_to_int_parses_money_strings():
    assert ct._to_int("1,410,000원") == 1410000
    assert ct._to_int(5000) == 5000
    assert ct._to_int("  300000 ") == 300000


def test_to_int_rejects_invalid():
    assert ct._to_int(None) is None
    assert ct._to_int("없음") is None
    assert ct._to_int(True) is None  # bool은 금액이 아님


def test_balance_remaining_prefers_explicit_fields():
    assert ct._balance_remaining({"pricing": {"balance": "1,410,000"}}) == 1410000
    assert ct._balance_remaining({"totals": {"balance": 50000}}) == 50000


def test_balance_remaining_none_when_unknown():
    assert ct._balance_remaining({}) is None
    assert ct._balance_remaining({"pricing": {}, "totals": {}}) is None


def test_measure_readiness_warns_when_unassigned():
    state, label = ct._measure_readiness(_Order(structured_data={}), {})
    assert state == "warn" and label == "담당 미배정"


def test_measure_readiness_ok_by_manager_or_ids():
    assert ct._measure_readiness(_Order(manager_name="한용희"), {})[0] == "ok"
    sd = {"assignments": {"sales_assignee_user_ids": [7]}}
    assert ct._measure_readiness(_Order(), sd)[0] == "ok"


def test_construction_readiness_risk_when_not_yet_shipped():
    # 시공일인데 아직 생산/컨펌 단계 → 출고 미확인(위험)
    for code in ("PRODUCTION", "CONFIRM", "DRAWING", "RECEIVED"):
        state, label = ct._construction_readiness(_Order(erp_stage_code=code), {})
        assert state == "risk" and label == "출고 미확인"


def test_construction_readiness_ok_when_installed_and_paid():
    state, label = ct._construction_readiness(_Order(erp_stage_code="CONSTRUCTION"), {})
    assert state == "ok" and label == "준비완료"


def test_construction_readiness_warns_on_outstanding_balance():
    sd = {"pricing": {"balance": 100000}}
    state, label = ct._construction_readiness(_Order(erp_stage_code="CONSTRUCTION", structured_data=sd), sd)
    assert state == "warn" and label == "잔금 미수"


def test_risk_group_shape():
    g = ct._risk_group("k", "🔨", "red", "t", "why", 3, {"stage": "시공"})
    assert g["key"] == "k" and g["tone"] == "red" and g["count"] == 3
    assert g["filter"] == {"stage": "시공"}


class _FakeQuery:
    """filter/order_by/limit/count/with_entities/all 만 지원하는 최소 쿼리 스텁.

    with_entities(Order.id) 이후 all()은 실제 ORM처럼 (id,) 튜플을 돌려준다.
    """

    def __init__(self, rows, as_id_tuples=False):
        self._rows = list(rows)
        self._as_id_tuples = as_id_tuples

    def filter(self, *a, **k):
        return self

    def join(self, *a, **k):
        return self

    def group_by(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def limit(self, n):
        return _FakeQuery(self._rows[:n], self._as_id_tuples)

    def with_entities(self, *a, **k):
        return _FakeQuery(self._rows, as_id_tuples=True)

    def count(self):
        return len(self._rows)

    def all(self):
        if self._as_id_tuples:
            return [(o.id,) for o in self._rows]
        return list(self._rows)


def _order_with_balance(oid, bal):
    return _Order(
        id=oid,
        erp_stage_code="PRODUCTION",
        structured_data={"parties": {"customer": {"name": f"고객{oid}"}}, "pricing": {"balance": bal}},
    )


def test_week_strip_marks_first_day_as_today():
    """주간 타일 첫 칸만 is_today/dow=오늘 (KST today 인자 SSOT)."""
    import datetime

    today = datetime.date(2026, 6, 17)
    week = ct._week_strip(_FakeQuery([]), today)
    assert week["days"][0]["iso"] == "2026-06-17"
    assert week["days"][0]["is_today"] is True
    assert week["days"][0]["dow"] == "오늘"
    assert week["days"][1]["iso"] == "2026-06-18"
    assert week["days"][1]["is_today"] is False
    # AS 출고 집계 계약: 일자별 as_count + 주간 as_total 키 존재(빈 base=0).
    assert week["days"][0]["as_count"] == 0
    assert week["as_total"] == 0


def test_business_window_dates_includes_today_excludes_far():
    import datetime
    today = datetime.date(2026, 6, 9)  # 화요일
    dates = ct._business_window_dates(today, max_business_days=3, window_days=10)
    assert today.isoformat() in dates  # D-0 포함
    assert (today + datetime.timedelta(days=10)).isoformat() not in dates  # 영업일 D-3 초과 제외


def test_risk_balance_due_targets_own_risk_key():
    """잔금 미수 카드는 자기 위험 key로 착지(SSOT). construction_d3 상위집합 붕괴 금지."""
    base = _FakeQuery([_order_with_balance(1, 100000), _order_with_balance(2, 0), _order_with_balance(3, 50000)])
    g = ct._risk_balance_due(base, ["2026-06-10"])
    assert g is not None
    assert g["count"] == 2  # 잔금>0 인 건만
    assert g["filter"] == {"risk": "balance_due"}  # construction_unready와 분리


def test_risk_construction_unready_distinct_from_balance_due():
    """미준비와 잔금은 동일 URL로 붕괴되면 안 된다(연구 핵심 결함 회귀 가드)."""
    base = _FakeQuery([_Order(id=1, erp_stage_code="PRODUCTION",
                              structured_data={"parties": {"customer": {"name": "가"}}})])
    g = ct._risk_construction_unready(base, __import__("datetime").date(2026, 6, 9), ["2026-06-10"])
    assert g is not None
    assert g["filter"] == {"risk": "construction_unready"}
    assert g["filter"] != {"risk": "balance_due"}


def test_risk_drawing_stalled_targets_own_risk_key():
    base = _FakeQuery([_Order(id=1, structured_data={"parties": {"customer": {"name": "가"}}})])
    g = ct._risk_drawing_stalled(base)
    assert g is not None
    assert g["filter"] == {"risk": "drawing_stalled"}


def test_risk_groups_none_when_empty():
    base = _FakeQuery([])
    assert ct._risk_drawing_stalled(base) is None
    assert ct._risk_balance_due(base, ["2026-06-10"]) is None
    assert ct._risk_measure_unassigned(base, ["2026-06-10"]) is None


def test_build_risk_frame_meta_per_key():
    """risk_frame 착지 헤더는 모든 위험 key에 대해 제목·결함·CTA를 제공한다."""
    for key in ct.RISK_KEYS:
        f = ct.build_risk_frame(key, 3, back_href="/erp/dashboard")
        assert f["key"] == key and f["count"] == 3
        assert f["title"] and f["defect"] and f["cta"]
        assert f["tone"] in ("red", "amber")
        assert f["back_href"] == "/erp/dashboard"
    assert ct.build_risk_frame("bogus", 1) is None


def test_build_risk_order_ids_rejects_unknown_key():
    assert ct.build_risk_order_ids(None, None, "bogus") == []


def test_channel_desk_url_resolution(monkeypatch):
    """출고 확인 CTA가 여는 채널톡 데스크 URL: 기본 하우드(haud), CHANNEL_DESK_URL로 override."""
    from foms.web.orders.dashboard import _channel_desk_url
    monkeypatch.delenv("CHANNEL_DESK_URL", raising=False)
    assert _channel_desk_url() == "https://desk.channel.io/haud"
    monkeypatch.setenv("CHANNEL_DESK_URL", "https://desk.channel.io/haud/user_chats/y")
    assert _channel_desk_url() == "https://desk.channel.io/haud/user_chats/y"


def test_risk_row_cta_meta_per_key():
    """P1: 위험 key마다 행별 단일 CTA(label/icon/kind/tone) 존재. kind는 라우트 해석 토큰."""
    expected_kind = {
        "construction_unready": "channel", "balance_due": "tel",
        "measure_unassigned": "edit", "drawing_stalled": "tel",
    }
    for key in ct.RISK_KEYS:
        m = ct.risk_row_cta_meta(key)
        assert m and m["label"] and m["icon"]
        assert m["kind"] == expected_kind[key]
        assert m["tone"] in ("danger", "warning")
    assert ct.risk_row_cta_meta("bogus") is None


def test_field_ops_for_day_supports_as_visit_rows(app):
    """오늘의 현장 AS 탭은 as_visit 일정의 AS 행과 카운트를 반환한다."""
    import datetime

    from db import db_session
    from models import Order, OrderScheduleDate

    today = "2026-06-30"
    order = Order(
        received_date=today,
        customer_name="AS 타워 고객",
        phone="010-1111-2222",
        address="서울",
        product="붙박이장",
        status="AS_RECEIVED",
        erp_stage_code="AS_RECEIVED",
        is_erp_order=True,
        structured_data={
            "parties": {
                "customer": {"name": "AS 타워 고객"},
                "manager": {"name": "담당자"},
            },
            "site": {"address_full": "서울 테스트로 1"},
            "schedule": {"as_visit": {"date": today, "time": "15:30"}},
        },
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderScheduleDate(
            order_id=order.id,
            kind="as_visit",
            date=today,
            source="beta_schedule",
        )
    )
    db_session.commit()

    payload = ct.build_field_ops_for_day(
        db_session,
        None,
        today,
        field_type="as",
        today=datetime.date.fromisoformat(today),
    )

    assert payload["as_count"] == 1
    assert payload["count"] == 1
    assert payload["rows"][0]["type_code"] == "as"
    assert payload["rows"][0]["type"] == "AS"
    assert payload["rows"][0]["time"] == "15:30"
    assert payload["rows"][0]["readiness_label"] == "AS 방문"


def test_mobile_control_tower_exposes_today_as_count(app):
    """초기 렌더 AS 뱃지는 today_as_count를 사용한다."""
    import datetime

    from db import db_session
    from models import Order, OrderScheduleDate

    today = datetime.date(2026, 6, 30)
    order = Order(
        received_date=today.isoformat(),
        customer_name="AS 뱃지 고객",
        phone="010-3333-4444",
        address="서울",
        product="붙박이장",
        status="AS_RECEIVED",
        erp_stage_code="AS_RECEIVED",
        is_erp_order=True,
        structured_data={"schedule": {"as_visit": {"date": today.isoformat()}}},
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderScheduleDate(
            order_id=order.id,
            kind="as_visit",
            date=today.isoformat(),
            source="beta_schedule",
        )
    )
    db_session.commit()

    tower = ct.build_mobile_control_tower(db_session, None, today=today)

    assert tower["today_as_count"] == 1
    assert tower["today_count"] == 1


def test_orders_dashboard_date_field_as_filters_as_visit_queue(app):
    """타워 AS 탭의 큐 링크는 as_visit 일정 주문으로 착지한다."""
    from db import db_session
    from foms.services.orders.dashboard_filters import OrdersDashboardFilters
    from foms.services.orders.dashboard_read_model import build_orders_dashboard_queries
    from models import Order, OrderScheduleDate

    today = "2026-06-30"
    as_order = Order(
        received_date=today,
        customer_name="AS 큐 고객",
        phone="010-5555-6666",
        address="서울",
        product="붙박이장",
        status="AS_RECEIVED",
        erp_stage_code="AS_RECEIVED",
        is_erp_order=True,
        structured_data={"schedule": {"as_visit": {"date": today}}},
    )
    measure_order = Order(
        received_date=today,
        customer_name="실측 큐 고객",
        phone="010-7777-8888",
        address="서울",
        product="붙박이장",
        status="MEASURE",
        erp_stage_code="MEASURE",
        erp_measurement_date=today,
        is_erp_order=True,
        structured_data={"schedule": {"measurement": {"date": today}}},
    )
    non_as_visit_order = Order(
        received_date=today,
        customer_name="비AS 방문 고객",
        phone="010-9999-0000",
        address="서울",
        product="붙박이장",
        status="MEASURE",
        erp_stage_code="MEASURE",
        is_erp_order=True,
        structured_data={"schedule": {"as_visit": {"date": today}}},
    )
    db_session.add_all([as_order, measure_order, non_as_visit_order])
    db_session.flush()
    db_session.add_all(
        [
            OrderScheduleDate(
                order_id=as_order.id,
                kind="as_visit",
                date=today,
                source="beta_schedule",
            ),
            OrderScheduleDate(
                order_id=non_as_visit_order.id,
                kind="as_visit",
                date=today,
                source="beta_schedule",
            ),
        ]
    )
    db_session.commit()

    filters = OrdersDashboardFilters(
        stage="",
        urgent="",
        has_alert="",
        alert_type="",
        q="",
        effective_stage="",
        team="",
        sort="latest",
        today="",
        tower_mine=False,
        mine=False,
        date=today,
        field="as",
        risk="",
        focus_order_id=None,
    )
    query, _stats, _today_date, _today_iso = build_orders_dashboard_queries(
        db_session,
        None,
        True,
        filters,
    )

    assert [o.id for o in query.all()] == [as_order.id]
