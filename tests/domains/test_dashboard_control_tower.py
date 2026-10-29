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
    """담당이 있으면 칩 없음(빈 라벨) — 전 행 '준비완료'는 정보가 없다(2026-10-14)."""
    assert ct._measure_readiness(_Order(manager_name="한용희"), {}) == ("ok", "")
    sd = {"assignments": {"sales_assignee_user_ids": [7]}}
    assert ct._measure_readiness(_Order(), sd) == ("ok", "")


def test_construction_readiness_risk_only_today_and_tomorrow():
    # 출고 전 단계: 오늘·내일만 '출고 전'(위험), 먼 날짜는 정상 진행이라 칩 없음.
    for code in ("PRODUCTION", "CONFIRM", "DRAWING", "RECEIVED"):
        for offset in (0, 1):
            assert ct._construction_readiness(_Order(erp_stage_code=code), {}, day_offset=offset) == ("risk", "출고 전")
        assert ct._construction_readiness(_Order(erp_stage_code=code), {}, day_offset=2) == ("ok", "")


def test_construction_readiness_silent_for_past_days():
    assert ct._construction_readiness(_Order(erp_stage_code="PRODUCTION"), {}, day_offset=-1) == ("ok", "")


def test_construction_readiness_ok_when_installed_and_paid():
    assert ct._construction_readiness(_Order(erp_stage_code="CONSTRUCTION"), {}) == ("ok", "")


def test_construction_readiness_warns_on_outstanding_balance():
    sd = {"pricing": {"balance": 480000}}
    state, label = ct._construction_readiness(_Order(erp_stage_code="CONSTRUCTION", structured_data=sd), sd, day_offset=5)
    assert state == "warn" and label == "잔금 48만"


def test_man_label_rounds_to_man_and_eok():
    assert ct._man_label(None) == ""
    assert ct._man_label(0) == ""
    assert ct._man_label(34_700_000) == "3,470만"
    assert ct._man_label(123_000_000) == "1억 2,300만"
    assert ct._man_label(200_000_000) == "2억"
    assert ct._man_label(4_000) == "4,000원"


def test_time_group_and_items_label():
    assert [ct._time_group(t) for t in ("09:00", "오전", "13:00", "3~4시", "오후", "종일", None, "미정")] == [
        "오전", "오전", "오후", "오후", "오후", "종일", "시간 미정", "시간 미정",
    ]
    assert ct._items_label({"items": [{"product_name": "붙박이장"}, {"product_name": "화장대"}, {}]}) == "붙박이장 외 1"
    assert ct._items_label({"items": []}) == ""


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


def test_month_calendar_grid_starts_sunday():
    """2026-10: 1일=목요일 → 일요일 시작 5주, 앞 4칸(9/27~30)은 달 밖. 오늘 칸 1개."""
    import datetime

    today = datetime.date(2026, 10, 14)
    cal = ct._month_calendar(_FakeQuery([]), today, today.replace(day=1))
    cells = [c for week in cal["weeks"] for c in week]
    assert len(cal["weeks"]) == 5 and all(len(w) == 7 for w in cal["weeks"])
    assert [c["iso"] for c in cells[:5]] == ["2026-09-27", "2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"]
    assert [c["in_month"] for c in cells[:5]] == [False, False, False, False, True]
    assert cells[-1]["iso"] == "2026-10-31" and cells[-1]["dow"] == 6
    assert [c["iso"] for c in cells if c["is_today"]] == ["2026-10-14"]
    assert next(c for c in cells if c["iso"] == "2026-10-09")["is_holiday"] is True  # 한글날
    assert cal["label"] == "2026년 10월" and cal["month"] == "2026-10" and cal["is_this_month"] is True
    assert (cal["prev"], cal["next"]) == ("2026-09", "2026-11")
    assert cal["amount_label"] == "0원" and cal["as_total"] == 0


def test_month_first_clamps_bad_or_far_months():
    import datetime

    today = datetime.date(2026, 10, 14)
    assert ct._month_first("2026-12", today) == datetime.date(2026, 12, 1)
    assert ct._month_first("2027-10", today) == datetime.date(2027, 10, 1)
    assert ct._month_first("2027-11", today) == datetime.date(2026, 10, 1)  # 12개월 밖
    assert ct._month_first("bogus", today) == datetime.date(2026, 10, 1)
    assert ct._month_first(None, today) == datetime.date(2026, 10, 1)
    cal = ct._month_calendar(_FakeQuery([]), today, datetime.date(2027, 10, 1))
    assert cal["next"] is None and cal["prev"] == "2027-09"


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
    assert payload["rows"][0]["readiness_label"] == ""  # AS 는 묶음 머리가 종류를 말한다
    assert [s["type_code"] for s in payload["sections"]] == ["as"]


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


def test_tower_counts_multi_date_orders_on_each_date(app):
    """콤마 복수 실측/시공일 주문은 주간 스트립·타입 카운트·일자 리스트 각 날짜에 모두 잡힌다.

    운영 2026-08-06 사건 회귀 가드: erp_measurement_date 싱크 컬럼은 첫 날짜만 담아
    2차 실측일이 모바일 홈에서 누락됐다(PC 25 vs 모바일 홈 23). 날짜 술어는
    order_schedule_dates SSOT를 써야 한다.
    """
    import datetime

    from db import db_session
    from models import Order

    today = datetime.date(2026, 6, 30)
    meas2 = "2026-07-02"
    cons1, cons2 = "2026-07-03", "2026-07-05"
    order = Order(
        received_date=today.isoformat(),
        customer_name="복수일정 고객",
        phone="010-1212-3434",
        address="서울",
        product="붙박이장",
        status="MEASURE",
        erp_stage_code="MEASURE",
        is_erp_order=True,
        structured_data={
            "parties": {"customer": {"name": "복수일정 고객"}},
            "schedule": {
                "measurement": {"date": f"{today.isoformat()}, {meas2}"},
                "construction": {"date": f"{cons1}, {cons2}"},
            },
        },
    )
    db_session.add(order)
    db_session.commit()
    # date-sync 리스너가 콤마 날짜를 order_schedule_dates 행으로 펼쳤는지 전제 확인.
    assert {(d.kind, d.date) for d in order.schedule_dates} >= {
        ("measurement", today.isoformat()),
        ("measurement", meas2),
        ("construction", cons1),
        ("construction", cons2),
    }

    base = ct._tower_base_query(db_session, None)
    cal = ct._month_calendar(base, today, datetime.date(2026, 7, 1))
    by_iso = {c["iso"]: c for week in cal["weeks"] for c in week if c["in_month"]}
    by_iso[today.isoformat()] = next(
        c for week in ct._month_calendar(base, today, today.replace(day=1))["weeks"] for c in week
        if c["iso"] == today.isoformat()
    )
    assert by_iso[today.isoformat()]["measure"] == 1
    assert by_iso[meas2]["measure"] == 1  # 2차 실측일도 카운트 (구현 전 0)
    assert by_iso[cons1]["construction"] == 1
    assert by_iso[cons2]["construction"] == 1  # 2차 시공일도 카운트

    measure, construction, as_count = ct._type_counts_for_date(base, meas2)
    assert (measure, construction, as_count) == (1, 0, 0)

    payload = ct.build_field_ops_for_day(db_session, None, meas2, field_type="all", today=today)
    assert payload["measure_count"] == 1
    assert [r["id"] for r in payload["rows"]] == [order.id]
    assert payload["rows"][0]["type_code"] == "measure"

    payload2 = ct.build_field_ops_for_day(db_session, None, cons2, field_type="all", today=today)
    assert payload2["construction_count"] == 1
    assert payload2["rows"][0]["type_code"] == "construction"


def test_tower_measure_counts_exclude_self_measurement_done(app):
    """자가실측 4체크 완료 주문은 실측 집계에서 제외(실측 대시보드 패널과 동일 제외)."""
    import datetime

    from db import db_session
    from models import Order

    today = datetime.date(2026, 6, 30)
    order = Order(
        received_date=today.isoformat(),
        customer_name="자가실측 완료 고객",
        phone="010-5656-7878",
        address="전북",
        product="붙박이장",
        status="MEASURE",
        erp_stage_code="MEASURE",
        is_erp_order=True,
        is_self_measurement=True,
        measurement_completed=True,
        regional_sales_order_upload=True,
        regional_blueprint_sent=True,
        regional_order_upload=True,
        structured_data={"schedule": {"measurement": {"date": today.isoformat()}}},
    )
    db_session.add(order)
    db_session.commit()

    base = ct._tower_base_query(db_session, None)
    measure, _construction, _as_count = ct._type_counts_for_date(base, today.isoformat())
    assert measure == 0
    cal = ct._month_calendar(base, today, today.replace(day=1))
    assert next(c for w in cal["weeks"] for c in w if c["iso"] == today.isoformat())["measure"] == 0


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


def test_orders_dashboard_date_field_measure_lands_second_measurement_date(app):
    """?date=&field=measure 착지 큐도 콤마 2차 실측일 주문을 포함한다(타워 카운트=리스트 정합)."""
    from db import db_session
    from foms.services.orders.dashboard_filters import OrdersDashboardFilters
    from foms.services.orders.dashboard_read_model import build_orders_dashboard_queries
    from models import Order

    first, second = "2026-06-30", "2026-07-02"
    order = Order(
        received_date=first,
        customer_name="착지 복수실측 고객",
        phone="010-8686-9797",
        address="서울",
        product="붙박이장",
        status="MEASURE",
        erp_stage_code="MEASURE",
        is_erp_order=True,
        structured_data={"schedule": {"measurement": {"date": f"{first}, {second}"}}},
    )
    db_session.add(order)
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
        date=second,
        field="measure",
        risk="",
        focus_order_id=None,
    )
    query, _stats, _today_date, _today_iso = build_orders_dashboard_queries(
        db_session,
        None,
        True,
        filters,
    )

    assert [o.id for o in query.all()] == [order.id]


def test_field_ops_sort_puts_unknown_time_last_and_reads_free_text():
    """현장 목록 시각 정렬 회귀 가드(2026-10-14 운영 화면).

    문자열 비교 시절엔 미정("99:99")이 "오전"·"오후"보다 앞섰고 "3~4시"가 "18:00" 뒤로 갔다.
    """
    def row(type_code, time):
        return {"type_code": type_code, "time": time}

    rows = [
        row("construction", None),
        row("construction", "오후"),
        row("construction", "오전"),
        row("measure", None),
        row("measure", "종일"),
        row("measure", "오후"),
        row("measure", "3~4시"),
        row("measure", "18:00"),
        row("measure", "오전"),
        row("measure", "09:00"),
        row("as", "15:30"),
    ]
    ordered = [(r["type_code"], r["time"]) for r in sorted(rows, key=ct._field_ops_sort_key)]
    assert ordered == [
        ("construction", "오전"),
        ("construction", "오후"),
        ("construction", None),
        ("measure", "09:00"),
        ("measure", "오전"),
        ("measure", "3~4시"),
        ("measure", "18:00"),
        ("measure", "오후"),
        ("measure", "종일"),
        ("measure", None),
        ("as", "15:30"),
    ]


def test_field_sections_group_by_type_then_time():
    rows = []
    for type_code, time, amount, label in (
        ("construction", "오전", 4_120_000, "출고 전"),
        ("construction", None, 1_320_000, "잔금 48만"),
        ("measure", "09:00", None, ""),
        ("measure", "오후", None, ""),
    ):
        rows.append({
            "type_code": type_code, "type": "x", "time": time, "time_group": ct._time_group(time),
            "amount": amount, "readiness_label": label,
        })
    sections = ct._field_sections(rows, day_offset=0)
    assert [(s["title"], s["count"]) for s in sections] == [("시공", 2), ("실측", 2)]
    assert sections[0]["amount_label"] == "544만"
    assert sections[0]["unshipped"] == 1 and sections[0]["unshipped_when"] == "오늘"
    assert [g["label"] for g in sections[0]["groups"]] == ["오전", "시간 미정"]
    assert [g["label"] for g in sections[1]["groups"]] == ["오전", "오후"]
    assert ct._field_sections(rows, day_offset=3)[0]["unshipped_when"] == ""


def test_month_calendar_amounts_and_soon_risk(app):
    """날짜 칸 금액 = 그날 시공 출고가 합(여러 날 시공은 시공일 수로 나눈 몫), 이달 합계 = 발주방 PUSH 된 주문 몫 합. 빨간 점은 오늘·내일만."""
    import datetime

    from db import db_session
    from models import Order

    today = datetime.date(2026, 6, 10)
    far = "2026-06-20"

    def _order(name, stage, dates, total):
        return Order(
            received_date=today.isoformat(),
            customer_name=name,
            phone="010-1000-2000",
            address="서울",
            product="붙박이장",
            status=stage,
            erp_stage_code=stage,
            is_erp_order=True,
            structured_data={
                "parties": {"customer": {"name": name, "phone": "010-1000-2000"}},
                "schedule": {"construction": {"date": dates}},
                "totals": {"items_total": total},
                "items": [{"product_name": "붙박이장"}],
            },
        )

    unshipped_today = _order("출고전 오늘", "PRODUCTION", today.isoformat(), 4_120_000)
    two_days = _order("이틀 시공", "PRODUCTION", f"{today.isoformat()}, {far}", 2_000_000)
    unshipped_far = _order("출고전 먼날", "PRODUCTION", far, 1_000_000)
    two_days.structured_data = {**two_days.structured_data, "channeltalk_push_drawing": {"pushed": True}}
    unshipped_far.structured_data = {**unshipped_far.structured_data, "channeltalk_push_drawing": {"pushed": False}}
    db_session.add_all([unshipped_today, two_days, unshipped_far])
    db_session.commit()

    base = ct._tower_base_query(db_session, None)
    cal = ct._month_calendar(base, today, today.replace(day=1))
    by_iso = {c["iso"]: c for w in cal["weeks"] for c in w if c["in_month"]}
    assert by_iso[today.isoformat()]["construction"] == 2
    assert by_iso[today.isoformat()]["amount_label"] == "512만"  # 412만 + 이틀 시공 200만의 절반
    assert by_iso[today.isoformat()]["unshipped"] == 2
    assert by_iso[far]["amount_label"] == "200만"  # 100만 + 이틀 시공 몫 100만
    assert by_iso[far]["unshipped"] == 0  # 먼 날짜 출고 전은 점 없음
    # 이달 합계 = 발주방 PUSH 된 주문만(사용자 결정 2026-10-29) — 이틀 시공 200만(몫 둘 다 6월). 날짜 칸은 전체 그대로.
    assert cal["amount_label"] == "200만"

    payload = ct.build_field_ops_for_day(db_session, None, today.isoformat(), today=today)
    assert payload["amount_label"] == "512만" and payload["is_today"] is True
    split = {r["name"]: r for r in payload["rows"]}["이틀 시공"]
    assert split["amount_label"] == "100만" and split["amount_split_label"] == "2일 나눔 · 전체 200만"
    assert {r["readiness_label"] for r in payload["rows"]} == {"출고 전"}
    assert payload["sections"][0]["unshipped"] == 2
    assert payload["rows"][0]["items_label"] == "붙박이장" and payload["rows"][0]["phone"]

    far_payload = ct.build_field_ops_for_day(db_session, None, far, today=today)
    assert {r["readiness_label"] for r in far_payload["rows"]} == {""}


def test_field_calendar_route_renders_month_and_clamps(auth_client):
    """달 이동 swap 라우트: 달력 조각 HTML + 정규화된 month. 형식 오류·12개월 밖은 이번 달."""
    from foms.services.erp_display import get_today_kst

    this_month = get_today_kst().strftime("%Y-%m")
    res = auth_client.get("/erp/dashboard/field-calendar?month=bogus")
    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True and body["data"]["month"] == this_month
    assert "data-foms-cal" in body["data"]["html"] and "data-foms-day-tile" in body["data"]["html"]

    far = auth_client.get("/erp/dashboard/field-calendar?month=1999-01").get_json()
    assert far["data"]["month"] == this_month


def test_field_ops_route_renders_sections(auth_client):
    res = auth_client.get("/erp/dashboard/field-ops?date=2026-06-30&field=all")
    data = res.get_json()["data"]
    assert data["amount_label"] == "0원" and "is_today" in data
    assert "foms-tower__empty" in data["html"]


def test_split_price_by_day_keeps_total():
    """여러 날 시공 출고가는 날짜별 몫으로 — 나머지 원은 첫 날, 몫을 더하면 출고가 그대로(사용자 2026-10-15)."""
    dates = ["2026-10-20", "2026-10-22", "2026-10-23"]
    shares = [ct.split_price_by_day(10_000_001, dates, d) for d in dates]
    assert shares == [3_333_335, 3_333_333, 3_333_333] and sum(shares) == 10_000_001
    assert ct.split_price_by_day(10_000_000, ["2026-10-20"], "2026-10-20") == 10_000_000
    assert ct.split_price_by_day(0, dates, dates[0]) == 0
