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
    """filter/order_by/limit/count/all 만 지원하는 최소 쿼리 스텁."""

    def __init__(self, rows):
        self._rows = list(rows)

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def limit(self, n):
        return _FakeQuery(self._rows[:n])

    def count(self):
        return len(self._rows)

    def all(self):
        return list(self._rows)


def _order_with_balance(oid, bal):
    return _Order(
        id=oid,
        erp_stage_code="PRODUCTION",
        structured_data={"parties": {"customer": {"name": f"고객{oid}"}}, "pricing": {"balance": bal}},
    )


def test_business_window_dates_includes_today_excludes_far():
    import datetime
    today = datetime.date(2026, 6, 9)  # 화요일
    dates = ct._business_window_dates(today, max_business_days=3, window_days=10)
    assert today.isoformat() in dates  # D-0 포함
    assert (today + datetime.timedelta(days=10)).isoformat() not in dates  # 영업일 D-3 초과 제외


def test_risk_balance_due_targets_construction_d3_superset_queue():
    """잔금 미수 카드는 시공 임박(construction_d3) 큐로 연결돼야 한다(카운트 집합 포함)."""
    base = _FakeQuery([_order_with_balance(1, 100000), _order_with_balance(2, 0), _order_with_balance(3, 50000)])
    g = ct._risk_balance_due(base, ["2026-06-10"])
    assert g is not None
    assert g["count"] == 2  # 잔금>0 인 건만
    assert g["filter"] == {"alert_type": "construction_d3"}  # stage=시공(불일치) 아님


def test_risk_drawing_stalled_targets_drawing_overdue_queue():
    base = _FakeQuery([_Order(id=1, structured_data={"parties": {"customer": {"name": "가"}}})])
    g = ct._risk_drawing_stalled(base)
    assert g is not None
    assert g["filter"] == {"alert_type": "drawing_overdue"}  # stage=도면(CONFIRM 누락) 아님


def test_risk_groups_none_when_empty():
    base = _FakeQuery([])
    assert ct._risk_drawing_stalled(base) is None
    assert ct._risk_balance_due(base, ["2026-06-10"]) is None
    assert ct._risk_measure_unassigned(base, ["2026-06-10"]) is None
