"""특성 시험 — 실측일 고치기 ``POST /api/update_order_field`` (칸 ``measurement_date`` 만)의 지금 행동 (T13 · D206).

T14 가 처리기 본체(``foms/api/orders/field_update.py`` ``update_order_field_response``)를 함수로 떼어 낸다.
이 파일을 한 글자도 고치지 않은 채 초록이어야 행동이 같다는 증거다. 장면마다 답 코드 · 답 값 · 주문
자국(일 기록 · 감사 · 변경 원장 · 사유 줄 · 알림 · 받는 사람 · 바깥 일 · 날짜 찾기 표 · ``structured_data`` ·
납작 칸 · ``mutation_version``)과 바깥 보내기(알림톡 · 푸시 · 화면 알림 — 모두 가짜) 횟수를 견준다.

이상해 보여도 지금 행동이면 그대로 못박았다:
* 날짜 꼴을 고르지 않는다 — ``abc`` 도 그대로 들어가고 날짜 찾기 표에 ``abc`` 줄이 생긴다. ``2031/05/07`` 은
  표에는 ``2031-05-07`` 로, 납작 칸은 빈 값으로 갈린다. 답의 ``normalized_value`` 는 납작 칸 값이다.
* 역할이 아니라 팀만 본다 — 영업팀 조회 전용(VIEWER)도 고친다(시험 레인). 정책 가드를 켜면 처리기 앞에서 403.
* 승격 전 초안 · 완료 주문 · 지운 주문도 고친다(지운 주문은 관리자 뚫기 요청일 때만 404).
* 같은 값을 다시 보내도 감사 한 줄과 알림톡 시도 한 번이 남는다. ``mutation_version`` 은 오르지 않는다.
* 답에 사유가 필요한가를 알리는 칸이 없고 사유 줄도 생기지 않는다.
* 로그인 안 한 요청은 처리기의 401 이 아니라 로그인 화면 302 다.
"""
from __future__ import annotations

import pytest

from db import db_session
from foms.api.orders import field_update
from models import Notification
from tests.support import graft_char as gc

SD = ("schedule", "drawing_transfer_history", "drawing")
FLAT = ("measurement_date", "erp_measurement_date", "manager_name", "status", "erp_stage_code",
        "erp_stage_updated_at", "structured_updated_at", "erp_phone_digits")
DATE, NEXT = "2031-05-06", "2031-05-09"
NO_RIGHT = "실측일/시공일 수정 권한이 없습니다. (영업, 라홈, 하우드, CS팀만 가능)"


@pytest.fixture
def out(monkeypatch):
    """알림톡 · 푸시 · 화면 알림을 가짜로 바꾸고 '오늘'을 고정한다(``gc.FAKE_TODAY``)."""
    return gc.install_fakes(monkeypatch)


def _order(stage: str = "RECEIVED", date: str | None = None, extra: dict | None = None, **cols) -> int:
    """ERP 주문 1건(실측일 · 시간 · 지어낸 영업 이름)."""
    sd = {"workflow": {"stage": stage}, "parties": {"manager": {"name": "특성 영업"}}}
    if date is not None:
        sd["schedule"] = {"measurement": {"date": date, "time": "10시"}}
    sd.update(extra or {})
    return gc.make_order(sd, status=cols.pop("status", stage), erp_stage_code=stage, **cols)


def _save(client, order_id: int, value="<빼기>", **body):
    """칸 고치기를 부르고 (답, 앞뒤 차이, 새 줄)을 돌려준다."""
    payload = {"order_id": order_id, "field": body.pop("field", "measurement_date"), **body}
    if value != "<빼기>":
        payload["value"] = value
    before = gc.snapshot(order_id, sd_paths=SD, flat=FLAT)
    resp = client.post("/api/update_order_field", json=payload)
    after = gc.snapshot(order_id, sd_paths=SD, flat=FLAT)
    return resp, gc.delta(before, after), gc.new_rows(before, after)


def _body(normalized: str, status: str = "RECEIVED", label: str = "접수") -> dict:
    """성공 답 값 전체(지금 꼴 — 사유 칸 없음)."""
    return {"success": True, "message": "정보가 업데이트되었습니다.", "normalized_value": normalized,
            "status": status, "status_label": label, "as_completed_date": "", "as_visit_date": "",
            "as_pending": False, "as_blueprint": False, "sales_delivery": False, "construction_workers": []}


def _changed(before, after, op) -> dict:
    """실측일 한 번 고치기가 남기는 자국(앞 · 뒤 날짜 기준)."""
    sched_b = gc.ABSENT if before is None else {"measurement": {"date": before, "time": "10시"}}
    sched_a = {"measurement": {"date": after}} if before is None else {"measurement": {"date": after, "time": "10시"}}
    added = [("measurement", after, "beta_schedule")] if after else []
    removed = [("measurement", before, "beta_schedule")] if before else []
    return {"audit": {"ORDER_FIELD_UPDATED": 1},
            "field_changes": {f"schedule.measurement.date {op} {before} -> {after or None}": 1},
            "schedule_dates": {"+": added, "-": removed},
            "sd": {"schedule": (sched_b, sched_a)},
            "flat": {"measurement_date": (before or "", after or ""), "erp_measurement_date": (before, after or None)}}


def _audit_row(oid: int, before: str, after: str, count: int, text: str) -> tuple:
    return ("ORDER_FIELD_UPDATED", "order", oid, f"주문 #{oid} (특성시험 손님) — 실측일: {text}",
            {"field": "measurement_date", "before": before, "after": after, "change_set": gc.GROUP,
             "change_count": count, "customer_name": "특성시험 손님", "order_type": "주문"})


def _run_set(client):
    gc.login_as(client, gc.make_user("ma-sales", team="SALES"))
    oid = _order()
    return (oid, *_save(client, oid, DATE))


def test_빈_실측일에_날짜를_넣으면_네_곳이_맞춰지고_커밋_뒤_알림톡을_한_번_시도한다(client, out):
    oid, resp, d, rows = _run_set(client)
    assert (resp.status_code, resp.get_json()) == (200, _body(DATE))
    assert d == _changed(None, DATE, "add")
    assert rows == {"events": [], "outbox": [], "audit": [_audit_row(oid, "", DATE, 1, f"(없음) → {DATE}")]}
    assert out.summary() == {"alimtalk": 1} and out.alimtalk == [oid]
    assert out.cache == [("order", oid, ("measurement",)), ("asrec", "field_update:measurement_date")]


@pytest.mark.parametrize("value, op, text", [(NEXT, "set", f"{DATE} → {NEXT}"), ("", "clear", f"{DATE} → (지움)")])
def test_실측일을_바꾸거나_비우면_원장_op_와_날짜_찾기_표가_따라간다(client, out, value, op, text):
    gc.login_as(client, gc.make_user("ma-sales", team="SALES"))
    oid = _order(date=DATE)
    resp, d, rows = _save(client, oid, value)
    assert (resp.status_code, resp.get_json()) == (200, _body(value))
    assert d == _changed(DATE, value, op)
    assert rows["audit"] == [_audit_row(oid, DATE, value, 1, text)]
    assert out.summary() == {"alimtalk": 1}


def test_같은_값을_다시_보내면_원장은_없고_감사와_알림톡_시도만_남는다(client, out):
    gc.login_as(client, gc.make_user("ma-sales", team="SALES"))
    oid = _order(date=DATE)
    resp, d, rows = _save(client, oid, DATE)
    assert (resp.status_code, resp.get_json()) == (200, _body(DATE))
    assert d == {"audit": {"ORDER_FIELD_UPDATED": 1}}
    assert rows["audit"] == [_audit_row(oid, DATE, DATE, 0, DATE)]
    assert out.summary() == {"alimtalk": 1}


@pytest.mark.parametrize("stage, status, label", [("DRAWING", "DRAWING", "도면"), ("COMPLETED", "COMPLETED", "완료")])
def test_도면_단계_뒤_주문은_도면_작업실_이력에_한_줄이_붙고_알림은_없다(client, out, stage, status, label):
    sales = gc.make_user("ma-sales", team="SALES")
    gc.login_as(client, sales)
    resp, d, _ = _save(client, _order(stage, date=DATE), NEXT)
    assert (resp.status_code, resp.get_json()) == (200, _body(NEXT, status, label))
    expected = _changed(DATE, NEXT, "set")
    expected["sd"]["drawing_transfer_history"] = (gc.ABSENT, [{
        "action": "ERP_ORDER_CHANGED", "by_user_id": sales.id, "by_user_name": "ma-sales 직원", "at": gc.TS,
        "note": f"실측일 {DATE}→{NEXT}", "changed_fields": ["schedule.measurement.date"],
        "changes": [{"path": "schedule.measurement.date", "label": "실측일", "from": DATE, "to": NEXT}],
        "acked": False}])
    assert d == expected
    assert out.summary() == {"alimtalk": 1}


def test_오늘로_넣으면_영업팀_당일_실측_알림과_바깥_일이_생기고_푸시와_화면_알림을_시도한다(client, out):
    sales = gc.make_user("ma-sales", team="SALES")
    gc.make_user("ma-sales2", team="SALES")
    gc.make_user("ma-cs", team="CS")
    gc.login_as(client, sales)
    oid = _order()
    resp, d, rows = _save(client, oid, gc.FAKE_TODAY)
    assert (resp.status_code, resp.get_json()) == (200, _body(gc.FAKE_TODAY))
    expected = _changed(None, gc.FAKE_TODAY, "add")
    expected.update({"events": {"MEASURE_SAME_DAY_ADDED": 1}, "outbox": {"MEAS_SAME_DAY_ALERT": 1},
                     "notifications": {"MEASURE_SAME_DAY_ADDED/TEAM/SALES": 1}, "notification_states": 2})
    assert d == expected
    note = db_session.query(Notification).filter(Notification.order_id == oid).one()
    assert rows["events"] == [("MEASURE_SAME_DAY_ADDED", {"date": gc.FAKE_TODAY, "source": "orders.update_order_field"})]
    assert rows["outbox"] == [("MEAS_SAME_DAY_ALERT", {"order_id": oid, "date": gc.FAKE_TODAY,
                                                       "notification_id": note.id}, "PENDING")]
    assert (note.title, note.message, note.created_by_name, note.is_urgent) == (
        "[긴급 실측] 오늘 시간 미정 · 특성시험 손님", "가상시 가상구 · 담당 특성 영업 · 추가 ma-sales 직원",
        "ma-sales 직원", False)
    assert out.summary() == {"push": 1, "emit": [(2, "MEASURE_SAME_DAY_ADDED")], "alimtalk": 1}


def test_승격_전_초안은_오늘로_넣어도_당일_알림이_없다(client, out):
    gc.login_as(client, gc.make_user("ma-sales", team="SALES"))
    oid = _order(extra={"meta": {"draft": True}}, status="DRAFT")
    resp, d, _ = _save(client, oid, gc.FAKE_TODAY)
    assert (resp.status_code, resp.get_json()) == (200, _body(gc.FAKE_TODAY, "DRAFT", "DRAFT"))
    assert d == _changed(None, gc.FAKE_TODAY, "add")
    assert out.summary() == {"alimtalk": 1}


@pytest.mark.parametrize("value, date_row", [("abc", "abc"), ("2031/05/07", "2031-05-07")])
def test_날짜_꼴을_고르지_않고_납작_칸은_빈_채로_둔다(client, out, value, date_row):
    gc.login_as(client, gc.make_user("ma-sales", team="SALES"))
    resp, d, _ = _save(client, _order(), value)
    assert (resp.status_code, resp.get_json()) == (200, _body(""))
    expected = _changed(None, value, "add")
    expected["schedule_dates"] = {"+": [("measurement", date_row, "beta_schedule")], "-": []}
    expected.pop("flat")
    assert d == expected


def test_값_칸이_없으면_실측일을_None_으로_적고_원장_줄은_없다(client, out):
    gc.login_as(client, gc.make_user("ma-sales", team="SALES"))
    resp, d, rows = _save(client, _order())
    assert (resp.status_code, resp.get_json()) == (200, _body(""))
    assert d == {"audit": {"ORDER_FIELD_UPDATED": 1}, "sd": {"schedule": (gc.ABSENT, {"measurement": {"date": None}})}}
    assert rows["audit"][0][4]["after"] is None and rows["audit"][0][4]["change_count"] == 0


@pytest.mark.parametrize("role, team", [("STAFF", "CS"), ("STAFF", "ACCOUNTING"), ("MANAGER", "SALES"),
                                        ("VIEWER", "SALES"), ("ADMIN", "PRODUCTION")])
def test_ERP_편집_팀이면_역할과_담당을_보지_않고_고친다(client, out, role, team):
    gc.login_as(client, gc.make_user("ma-x", role=role, team=team))
    resp, d, _ = _save(client, _order(), DATE)
    assert (resp.status_code, resp.get_json()) == (200, _body(DATE))
    assert d == _changed(None, DATE, "add")


@pytest.mark.parametrize("role, team, field, status, message", [
    ("STAFF", "PRODUCTION", "measurement_date", 403, NO_RIGHT),
    ("MANAGER", "DRAWING", "measurement_date", 403, NO_RIGHT),
    ("STAFF", "SALES", "customer_name", 400, "허용되지 않은 필드입니다: customer_name"),
    ("VIEWER", "SALES", "customer_name", 403, "이 작업을 수행할 권한이 없습니다."),
])
def test_권한과_허용_칸_거부_갈래(client, out, role, team, field, status, message):
    gc.login_as(client, gc.make_user("ma-x", role=role, team=team))
    resp, d, _ = _save(client, _order(), DATE, field=field)
    assert (resp.status_code, resp.get_json()) == (status, {"success": False, "message": message})
    assert d == {} and out.summary() == {}


def test_없는_주문은_404(client, out):
    gc.login_as(client, gc.make_user("ma-sales", team="SALES"))
    resp, d, _ = _save(client, 4242, DATE)
    assert (resp.status_code, resp.get_json()) == (404, {"success": False, "message": "유효하지 않은 주문입니다."})
    assert d == {} and out.summary() == {}


def test_지운_주문은_그냥은_고치고_관리자_뚫기_요청이면_404(client, out):
    gc.login_as(client, gc.make_user("ma-admin", role="ADMIN", team="CS"))
    oid = _order(deleted_at="2031-01-03 00:00:00")
    resp, d, _ = _save(client, oid, DATE)
    assert (resp.status_code, resp.get_json()) == (200, _body(DATE))
    assert d == _changed(None, DATE, "add")
    resp, d, _ = _save(client, oid, NEXT, admin_override=True, override_reason="시험 사유")
    assert (resp.status_code, resp.get_json()) == (404, {"success": False, "code": "NOT_FOUND",
                                                         "message": "삭제된 주문입니다. 휴지통에서 먼저 복구하세요."})
    assert d == {}


def test_관리자가_아닌_뚫기_요청은_403이고_감사에만_남긴다(client, out):
    gc.login_as(client, gc.make_user("ma-sales", team="SALES"))
    oid = _order()
    resp, d, rows = _save(client, oid, DATE, admin_override=True, override_reason="x")
    text = "관리자만 검사를 건너뛸 수 있습니다."
    assert (resp.status_code, resp.get_json()) == (403, {"success": False, "code": "ADMIN_ONLY", "message": text,
                                                         "error": text})
    assert d == {"audit": {"ADMIN_OVERRIDE_DENIED": 1}}
    assert rows["audit"] == [("ADMIN_OVERRIDE_DENIED", "order", oid,
                              f"주문 #{oid} 관리자 강제 진행 거부(ADMIN_ONLY) — orders.update_order_field",
                              {"gate": "ADMIN_ONLY", "route": "orders.update_order_field", "actor_role": "STAFF"})]


def test_ERP가_아닌_주문은_납작_칸_원장과_옛_칸_날짜_줄을_쓴다(client, out):
    gc.login_as(client, gc.make_user("ma-sales", team="SALES"))
    oid = gc.make_order(None, erp=False, measurement_date=DATE)
    resp, d, _ = _save(client, oid, NEXT)
    assert (resp.status_code, resp.get_json()) == (200, _body(NEXT))
    assert d == {"audit": {"ORDER_FIELD_UPDATED": 1}, "field_changes": {f"measurement_date set {DATE} -> {NEXT}": 1},
                 "schedule_dates": {"+": [("measurement", NEXT, "legacy_column")],
                                    "-": [("measurement", DATE, "legacy_column")]},
                 "flat": {"measurement_date": (DATE, NEXT)}}


def test_로그인_안_하면_처리기의_401이_아니라_로그인_화면_302(client, out):
    resp, d, _ = _save(client, _order(), DATE)
    assert (resp.status_code, resp.headers["Location"]) == (302, "/login?next=/api/update_order_field")
    assert d == {} and out.summary() == {}


def test_정책_가드를_켜면_조회_전용은_처리기_앞에서_403(client, out, app, monkeypatch):
    monkeypatch.setitem(app.config, "AUTH_POLICY_ENABLED", True)
    gc.login_as(client, gc.make_user("ma-viewer", role="VIEWER", team="SALES"))
    resp, d, _ = _save(client, _order(), DATE)
    text = "조회 전용 계정은 이 작업을 할 수 없습니다."
    assert (resp.status_code, resp.get_json()) == (403, {"success": False, "code": "FORBIDDEN", "data": None,
                                                         "error": text, "message": text})
    assert d == {"audit": {"ACCESS_DENIED": 1}}


# --------------------------------------------------------------------------- #
# 대조군 — 옆 효과 하나를 시험 안에서 없애면 같은 견주기가 빨개져야 자국이 못박힌 것이다.
# --------------------------------------------------------------------------- #
def test_대조군_감사_줄을_빼면_견주기가_빨개진다(client, out, monkeypatch):
    monkeypatch.setattr(field_update, "log_access", lambda *a, **k: None)
    _, resp, d, _ = _run_set(client)
    assert resp.status_code == 200 and d != _changed(None, DATE, "add") and "audit" not in d


def test_대조군_변경_원장을_빼면_견주기가_빨개진다(client, out, monkeypatch):
    monkeypatch.setattr(field_update, "record_field_changes", lambda *a, **k: 0)
    _, resp, d, _ = _run_set(client)
    assert resp.status_code == 200 and d != _changed(None, DATE, "add") and "field_changes" not in d


def test_대조군_납작_칸_맞추기를_빼면_견주기가_빨개진다(client, out, monkeypatch):
    monkeypatch.setattr(field_update, "sync_erp_flat_columns", lambda *a, **k: None)
    _, resp, d, _ = _run_set(client)
    assert resp.status_code == 200 and d != _changed(None, DATE, "add")
    assert d["flat"] == {"measurement_date": ("", DATE)}
