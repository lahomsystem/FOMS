"""[제작 완료]는 검수까지 끝나기 전엔 막는다 — 서버도 막기, 모든 화면 같은 규칙(사용자 결정 2026-11-21).

"검수까지 끝남" = 공정 4칸(재단 · 엣지 · 조립 · 검수)이 모두 켜짐. **공정 칸을 쓴 주문만 막는다**(11-21 사용자
"공정 칸을 쓴 주문만 막기" — 운영 생산팀이 아직 공정 칸을 안 쓴다): 한 칸이라도 켰으면 4칸을 다 켜야 완료되고,
한 칸도 안 켠 주문(칸 없음 · 모두 꺼짐 · production 없음 · 모두 켰다가 모두 끔)은 규칙 밖이라 그대로 완료된다. 판정은 한 함수
:func:`foms.services.production.steps.production_complete_ready` — 제작 완료 API · 일반 단계 쓰기(생산 → 시공) ·
작업 시트 / 옆 시트 단추 · 공정 API 응답이 같은 함수를 쓴다(이 파일이 위치를 고정).

되돌리면 실패: 완료 API 게이트 빼기(검수 전 200) · 일반 쓰기 옆문 열기(update_order_status · bulk · field 로 시공) ·
판정 복사(화면 · 서버가 다른 함수) · 단계 강제 변경까지 막기(막다른 길) · 관리자 뚫기 기록 빼기.
대조군: 검수 끝 주문 · 한 칸도 안 켠 주문은 그대로 완료(같은 자료 모양), 생산 → 시공이 아닌 일반 쓰기는 그대로,
단계 강제 변경은 검수 전이어도 된다.
"""
from __future__ import annotations

import inspect
from datetime import date
from itertools import count

import pytest
from werkzeug.security import generate_password_hash

import foms.api.drawing.erp_orders_drawing as drawing_routes
import foms.api.orders.field_update as field_update_mod
import foms.api.orders.status as status_mod
import foms.api.production.orders as prod_api
import foms.services.orders.stage_override as stage_override_mod
import foms.services.production_sheet_view as sheet_view_mod
from db import db_session
from foms.services.orders.admin_override import ADMIN_OVERRIDE_EVENT, GATE_CODES, GATE_STEPS_INCOMPLETE
from foms.services.production import complete_move as complete_move_mod
from foms.services.production import part_progress as progress_mod
from foms.services.production import steps as steps_mod
from foms.services.production.steps import (
    STEPS_INCOMPLETE_CODE,
    STEPS_INCOMPLETE_MESSAGE,
    production_complete_block_body,
    production_complete_ready,
    production_steps_missing,
)
from foms.services.production_home_read_model import production_home_stage, production_home_steps
from models import Order, OrderEvent, ProductionRun, User
from tests.support.production_steps_seed import inspected_steps, mark_order_inspected, with_inspected_steps

_seq = count(1)
_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
_REASON = "시험 — 검수 칸 건너뜀"


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def _user(*, role: str = "STAFF", team: str | None = "PRODUCTION", part: str | None = None) -> User:
    n = next(_seq)
    user = User(username=f"inspect_gate_{n}", password=generate_password_hash("pw"), role=role, team=team,
                name=f"가짜작업자{n}", is_active=True, production_part=part)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role


def _order(*, stage: str = "PRODUCTION", production: dict | None = None, extra: dict | None = None,
           run: bool = True) -> int:
    """생산 단계 가짜 ERP 주문(+ current run). ``production`` 을 주지 않으면 공정 칸 자체가 없는 옛 주문이다(규칙 밖)."""
    sd: dict = {"workflow": {"stage": stage}, "parties": {"customer": {"name": "가짜고객"}}, **(extra or {})}
    if production is not None:
        sd["production"] = production
    order = Order(received_date=date.today().isoformat(), customer_name="가짜고객", phone="010-0000-0000",
                  address="가짜시 가짜로 1", product="가짜장", status=stage, is_erp_order=True,
                  erp_stage_code=stage, structured_data=sd)
    db_session.add(order)
    db_session.commit()
    if run:
        db_session.add(ProductionRun(order_id=order.id, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
        db_session.commit()
    return order.id


def _fresh(oid: int) -> Order:
    db_session.expire_all()
    return db_session.get(Order, oid)


def _events(oid: int, event_type: str) -> list[OrderEvent]:
    return db_session.query(OrderEvent).filter_by(order_id=oid, event_type=event_type).order_by(OrderEvent.id).all()


def _complete(client, oid: int, body: dict | None = None):
    return client.post(f"/api/orders/{oid}/production/complete", json=body or {})


def _assert_untouched(oid: int) -> None:
    """거절이면 단계 · 버전 · 이벤트 · run 이 그대로다."""
    saved = _fresh(oid)
    assert saved.erp_stage_code == "PRODUCTION" and saved.status == "PRODUCTION"
    assert saved.structured_data["workflow"]["stage"] == "PRODUCTION"
    assert saved.mutation_version == 1
    for kind in ("PRODUCTION_COMPLETED", "STAGE_CHANGED", ADMIN_OVERRIDE_EVENT):
        assert _events(oid, kind) == [], kind
    assert db_session.query(ProductionRun).filter_by(order_id=oid, is_current=True).count() == 1


def _all_off() -> list[dict]:
    return [dict(s, done=False, at=None, by_name=None) for s in inspected_steps()]


# 막힘 = 한 칸 이상 켰지만 4칸 미만: 재단만 · 재단+엣지+조립 · 검수만(앞 칸 꺼짐)
_NOT_INSPECTED = {
    "cut_only": {"steps": inspected_steps(upto="cut")},
    "cut_edge_assemble": {"steps": inspected_steps(upto="assemble")},
    "inspect_only": {"steps": [dict(s, done=s["key"] == "inspect") for s in _all_off()]},
}
#: 막힌 주문 기본 모양(관리자 · 보류 · 옆문 · 비상구 시험) — 재단만 켬
_CUT_ONLY = _NOT_INSPECTED["cut_only"]

# 규칙 밖 = 한 칸도 안 켬: 모두 꺼짐 · 칸 목록 자체 없음 · production 자체 없음(옛 주문)
_UNUSED_STEPS = {
    "none_on": {"steps": _all_off()},
    "no_steps_key": {"hold": {"active": False}},
    "no_production": None,
}


# --------------------------------------------------------------------------- #
# 1. 판정 함수(순수)
# --------------------------------------------------------------------------- #
def test_판정_함수는_4칸_모두_켜져야_참이다() -> None:
    assert production_complete_ready({"production": {"steps": inspected_steps()}}) is True
    assert production_steps_missing({"production": {"steps": inspected_steps()}}) == []
    cut_only = {"production": {"steps": inspected_steps(upto="cut")}}
    assert production_complete_ready(cut_only) is False
    assert [m["key"] for m in production_steps_missing(cut_only)] == ["edge", "assemble", "inspect"]
    three = {"production": {"steps": inspected_steps(upto="assemble")}}
    assert production_complete_ready(three) is False
    assert [m["key"] for m in production_steps_missing(three)] == ["inspect"]
    # 검수만 켜도 앞 칸이 꺼져 있으면 아니다(검수까지 = 4칸 모두 — 첫 화면 '검수 끝' 과 같은 뜻)
    only_inspect = {"production": {"steps": [{"key": "inspect", "done": True}]}}
    assert production_complete_ready(only_inspect) is False
    assert [m["key"] for m in production_steps_missing(only_inspect)] == ["cut", "edge", "assemble"]


def test_한_칸도_안_켠_주문은_규칙_밖이다() -> None:
    """11-21 사용자 "공정 칸을 쓴 주문만 막기": 칸 없는 옛 주문 · 모두 꺼짐 · 이상한 값 = 빈 목록(막지 않음)."""
    for sd in ({}, {"production": {}}, {"production": {"steps": []}}, {"production": "x"}, None, "x",
               {"production": {"steps": _all_off()}}, {"production": {"hold": {"active": True}}}):
        assert production_steps_missing(sd) == [], sd
        assert production_complete_ready(sd) is True, sd
        assert production_complete_block_body(sd) is None, sd
    # 옛 도장 칸만 켜진 주문도 공정 4칸은 안 쓴 것이다(D15 — paint 는 보지 않는다)
    assert production_complete_ready({"production": {"steps": _all_off() + [{"key": "paint", "done": True}]}}) is True


def test_옛_도장_칸은_보지_않는다() -> None:
    """D15: 옛 주문 목록에 남은 paint 는 켜졌든 꺼졌든 판정과 무관하다."""
    with_paint_off = {"production": {"steps": inspected_steps() + [{"key": "paint", "done": False}]}}
    assert production_complete_ready(with_paint_off) is True
    paint_on_inspect_off = {"production": {"steps": inspected_steps(upto="assemble") + [{"key": "paint", "done": True}]}}
    assert production_complete_ready(paint_on_inspect_off) is False


def test_거절_본문은_기존_게이트_모양_쉬운_말_남은_공정() -> None:
    body = production_complete_block_body({"production": {"steps": inspected_steps(upto="edge")}})
    assert body["success"] is False and body["code"] == STEPS_INCOMPLETE_CODE == "STEPS_INCOMPLETE"
    assert body["message"] == f"{STEPS_INCOMPLETE_MESSAGE} (남은 공정: 조립 · 검수)"
    assert STEPS_INCOMPLETE_MESSAGE == "검수까지 끝나야 제작 완료할 수 있어요."
    assert body["missing_steps"] == [{"key": "assemble", "label": "조립"}, {"key": "inspect", "label": "검수"}]
    assert production_complete_block_body({"production": {"steps": inspected_steps()}}) is None


def test_판정은_첫_화면_검수_끝과_같다() -> None:
    """공정 칸을 쓴 주문에서 서버 판정 == 첫 화면 큰 글자 '검수 끝'(제작 중 · run 있음) — 두 화면이 다른 말을 하지 않는다.

    한 칸도 안 켠 주문은 규칙 밖이라 판정은 참이지만 첫 화면은 '검수 끝' 이 아니다(공정을 안 쓴 주문을 검수 끝이라 하지 않는다)."""
    cases = [{"production": {"steps": inspected_steps(upto=k)}} for k in ("cut", "edge", "assemble", "inspect")]
    cases += [{"production": {"steps": [{"key": "inspect", "done": True}]}}]
    for sd in cases:
        big, _small, _view = production_home_stage("PRODUCTION", True, production_home_steps(sd, mark_now=True), False)
        assert (big == "검수 끝") is production_complete_ready(sd), sd
    for sd in ({}, {"production": {"steps": _all_off()}}):
        big, _small, _view = production_home_stage("PRODUCTION", True, production_home_steps(sd, mark_now=True), False)
        assert big != "검수 끝" and production_complete_ready(sd) is True, sd


# --------------------------------------------------------------------------- #
# 2. 제작 완료 API — 검수 끝 성공 · 검수 전 거절
# --------------------------------------------------------------------------- #
def test_검수_끝이면_제작_완료된다(client) -> None:
    _login(client, _user())
    oid = _order(production={"steps": inspected_steps()})

    resp = _complete(client, oid)

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["new_status"] == "CONSTRUCTION"
    saved = _fresh(oid)
    assert saved.erp_stage_code == "CONSTRUCTION" and saved.mutation_version == 2
    assert len(_events(oid, "PRODUCTION_COMPLETED")) == 1
    assert db_session.query(ProductionRun).filter_by(order_id=oid, is_current=True).count() == 0


@pytest.mark.parametrize("shape", list(_NOT_INSPECTED))
def test_검수_전이면_거절하고_아무것도_안_바뀐다(client, shape: str) -> None:
    _login(client, _user())
    oid = _order(production=_NOT_INSPECTED[shape])

    resp = _complete(client, oid)

    assert resp.status_code == 409, resp.get_data(as_text=True)
    data = resp.get_json()
    assert data["success"] is False and data["code"] == "STEPS_INCOMPLETE"
    assert data["message"].startswith("검수까지 끝나야 제작 완료할 수 있어요.")
    assert data["missing_steps"] == production_steps_missing({"production": _NOT_INSPECTED[shape]})
    assert data["missing_steps"] and len(data["missing_steps"]) < 4
    _assert_untouched(oid)


@pytest.mark.parametrize("shape", list(_UNUSED_STEPS))
def test_공정_칸을_안_쓴_주문은_그대로_제작_완료된다(client, shape: str) -> None:
    """대조군(규칙 밖, 11-21 사용자 "공정 칸을 쓴 주문만 막기"): 한 칸도 안 켠 주문은 검수 게이트를 타지 않는다."""
    _login(client, _user())
    oid = _order(production=_UNUSED_STEPS[shape])

    resp = _complete(client, oid)

    assert resp.status_code == 200, resp.get_data(as_text=True)
    saved = _fresh(oid)
    assert saved.erp_stage_code == "CONSTRUCTION" and saved.mutation_version == 2
    assert len(_events(oid, "PRODUCTION_COMPLETED")) == 1
    assert _events(oid, ADMIN_OVERRIDE_EVENT) == []


def test_관리자도_평소엔_막히고_사유를_적으면_뚫는다(client) -> None:
    """ADMIN 도 admin_override 없이는 409. 사유를 실으면 완료되고 건너뛴 검사가 STEPS_INCOMPLETE 로 남는다."""
    _login(client, _user(role="ADMIN", team=None))
    oid = _order(production=_CUT_ONLY)

    assert _complete(client, oid).status_code == 409
    _assert_untouched(oid)

    resp = _complete(client, oid, {"admin_override": True, "override_reason": _REASON})

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _fresh(oid).erp_stage_code == "CONSTRUCTION"
    events = _events(oid, ADMIN_OVERRIDE_EVENT)
    assert len(events) == 1 and events[0].payload["gates"] == ["STEPS_INCOMPLETE"]
    assert events[0].payload["reason"] == _REASON
    assert GATE_STEPS_INCOMPLETE in GATE_CODES


def test_비관리자는_사유를_실어도_못_뚫는다(client) -> None:
    _login(client, _user(role="MANAGER", team="PRODUCTION"))
    oid = _order(production=_CUT_ONLY)
    resp = _complete(client, oid, {"admin_override": True, "override_reason": _REASON})
    assert resp.status_code == 403 and resp.get_json()["code"] == "ADMIN_ONLY"
    _assert_untouched(oid)


def test_보류가_먼저_말하고_검수는_그다음이다(client) -> None:
    """게이트 순서: 보류(HOLD_ACTIVE, 스스로 풀기 흐름) → 승인 → 검수. 보류를 풀며 다시 눌러도 검수 전이면 거절 — 보류는 그대로."""
    _login(client, _user())
    oid = _order(production={"hold": {"active": True, "reason": "자재 대기"}, **_CUT_ONLY})
    first = _complete(client, oid)
    assert first.status_code == 409 and first.get_json()["code"] == "HOLD_ACTIVE"
    again = _complete(client, oid, {"release_hold": True})
    assert again.status_code == 409 and again.get_json()["code"] == "STEPS_INCOMPLETE"
    assert _fresh(oid).structured_data["production"]["hold"]["active"] is True  # 거절된 요청은 보류도 안 풀었다
    _assert_untouched(oid)


def test_공정_칸을_안_쓴_보류_주문은_보류를_풀며_완료된다(client) -> None:
    """대조군: 같은 보류 주문이 공정 칸을 안 썼으면(규칙 밖) 보류만 말하고, 풀며 누르면 완료된다."""
    _login(client, _user())
    oid = _order(production={"hold": {"active": True, "reason": "자재 대기"}})
    assert _complete(client, oid).get_json()["code"] == "HOLD_ACTIVE"
    resp = _complete(client, oid, {"release_hold": True})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    saved = _fresh(oid)
    assert saved.erp_stage_code == "CONSTRUCTION" and saved.structured_data["production"]["hold"]["active"] is False


# --------------------------------------------------------------------------- #
# 3. 비상구 — 단계 강제 변경은 이 규칙을 타지 않는다
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("role", ["ADMIN", "MANAGER"])
def test_단계_강제_변경은_검수_전이어도_시공으로_넘긴다(client, role: str) -> None:
    _login(client, _user(role=role, team=None))
    oid = _order(production=_CUT_ONLY)  # 재단만 켬 — 검수 전(막다른 길 후보)

    resp = client.post(f"/api/orders/{oid}/workflow/stage-override",
                       json={"to_stage": "CONSTRUCTION", "reason": "공정 칸을 안 쓰던 주문 정리", "confirm": True})

    assert resp.status_code == 200, resp.get_data(as_text=True)
    saved = _fresh(oid)
    assert saved.erp_stage_code == "CONSTRUCTION"
    assert len(_events(oid, "STAGE_OVERRIDE")) == 1


def test_일괄_단계_강제_변경도_검수_전이어도_넘긴다(client) -> None:
    _login(client, _user(role="MANAGER", team=None))
    ids = [_order(production=_CUT_ONLY), _order(production={"steps": inspected_steps(upto="assemble")})]
    resp = client.post("/api/orders/workflow/stage-override/bulk",
                       json={"order_ids": ids, "to_stage": "CONSTRUCTION", "reason": "일괄 정리", "confirm": True})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert [_fresh(i).erp_stage_code for i in ids] == ["CONSTRUCTION", "CONSTRUCTION"]


def test_단계_강제_변경_길은_검수_판정을_부르지_않는다() -> None:
    """비상구 고정: apply_stage_override 몸통에 검수 판정이 없다(일반 쓰기 문지기만 부른다)."""
    src = inspect.getsource(stage_override_mod.apply_stage_override)
    assert "production_complete" not in src and "STEPS_INCOMPLETE" not in src


# --------------------------------------------------------------------------- #
# 4. 파트 계정 동기화로 켜진 칸
# --------------------------------------------------------------------------- #
@pytest.fixture
def _quiet_push(monkeypatch):
    monkeypatch.setattr(drawing_routes, "emit_erp_notification_to_users", lambda *a, **k: None)
    monkeypatch.setattr("foms.services.notifications.realtime_notifications.emit_erp_notification_to_users",
                        lambda *a, **k: None)
    monkeypatch.setattr("foms.services.notifications.push_sender.enqueue_push_for_notification",
                        lambda *a, **k: None)


def _part_order() -> tuple[int, str]:
    prefix = f"pg{next(_seq)}"
    files = [{"key": f"{prefix}/d0.png", "filename": "d0.png", "sheet_id": f"{prefix}-s0"}]
    oid = _order(production={"steps": [dict(s, done=False, at=None, by_name=None) for s in inspected_steps()]},
                 extra={"drawing_current_files": files})
    return oid, files[0]["key"]


def _finish_part(client, oid: int, key: str, part: str) -> None:
    _login(client, _user(part=part))
    for action, seen in (("take", "none"), ("done", "need")):
        resp = client.post("/api/production/part-marks",
                           json={"order_id": oid, "drawing_key": key, "part": part, "action": action, "seen": seen})
        assert resp.status_code == 200, resp.get_data(as_text=True)


@pytest.mark.usefixtures("_quiet_push")
def test_파트_카드로_네_칸이_켜지면_완료된다(client) -> None:
    oid, key = _part_order()
    assert production_complete_ready(_fresh(oid).structured_data) is True  # 카드 전 = 한 칸도 안 켬(규칙 밖)
    for part in ("cut", "edge", "assemble", "inspect"):
        _finish_part(client, oid, key, part)
        if part != "inspect":  # 첫 카드가 칸을 켜는 순간부터 공정을 쓴 주문 — 4칸 전엔 막힌다
            assert production_complete_ready(_fresh(oid).structured_data) is False, part
    assert production_complete_ready(_fresh(oid).structured_data) is True
    # 마지막(검수) 파트 계정이 그대로 [제작 완료]를 누른다 — 파트 계정도 완료 권한은 생산팀과 같다
    resp = _complete(client, oid)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _fresh(oid).erp_stage_code == "CONSTRUCTION"


@pytest.mark.usefixtures("_quiet_push")
def test_카드를_안_쓴_파트가_있으면_막히고_파트_없는_계정이_칸을_켜면_풀린다(client) -> None:
    """막다른 길 분석: 엣지가 카드를 안 쓰면 엣지 칸은 손 값 그대로(꺼짐). 파트 계정은 칸을 손으로 못 켠다(403) →
    파트 없는 계정(생산 관리자 · CS · 영업 · 관리자)이 작업 시트에서 켜면 풀린다. 2026-11-23(§4-7 B11): 그동안 검수 카드도 막힌다."""
    oid, key = _part_order()
    for part in ("cut", "assemble"):
        _finish_part(client, oid, key, part)
    _login(client, _user(part="inspect"))
    early = client.post("/api/production/part-marks",
                        json={"order_id": oid, "drawing_key": key, "part": "inspect", "action": "take", "seen": "none"})
    assert early.status_code == 409 and early.get_json()["data"]["left"] == [{"part": "edge", "holder": None}]
    blocked = _complete(client, oid)  # 카드를 쓴 주문 — 엣지(칸 꺼짐) · 검수(카드 미완료)가 남음
    assert blocked.status_code == 409
    assert blocked.get_json()["missing_steps"] == [{"key": "edge", "label": "엣지"}, {"key": "inspect", "label": "검수"}]
    edge_part = _user(part="edge")
    _login(client, edge_part)
    denied = client.post(f"/api/orders/{oid}/production/steps", json={"key": "edge", "done": True})
    assert denied.status_code == 403  # 파트 계정 = 카드로만

    _login(client, _user(part=None))
    ok = client.post(f"/api/orders/{oid}/production/steps", json={"key": "edge", "done": True})
    assert ok.status_code == 200 and ok.get_json()["data"]["complete_ready"] is False  # 검수가 아직
    _finish_part(client, oid, key, "inspect")  # 엣지 칸이 켜져 검수가 열린다
    assert _complete(client, oid).status_code == 200


# --------------------------------------------------------------------------- #
# 5. 다른 길도 같은 규칙 — 일반 상태 쓰기(단건 · 일괄 · 칸 고치기)
# --------------------------------------------------------------------------- #
def test_단건_상태_쓰기로_시공에_넣는_옆문도_막힌다(client) -> None:
    _login(client, _user(role="ADMIN", team="CS"))
    blocked_id = _order(production=_CUT_ONLY)
    ok_id = _order(production={"steps": inspected_steps()})
    unused_id = _order()  # 칸 없는 옛 주문 — 규칙 밖

    resp = client.post("/api/update_order_status", json={"order_id": blocked_id, "status": "CONSTRUCTION"})
    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert resp.get_json()["code"] == "STEPS_INCOMPLETE"
    _assert_untouched(blocked_id)

    resp = client.post("/api/update_order_status", json={"order_id": ok_id, "status": "CONSTRUCTION"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _fresh(ok_id).erp_stage_code == "CONSTRUCTION"  # 대조군 — 검수 끝은 그대로 된다
    resp = client.post("/api/update_order_status", json={"order_id": unused_id, "status": "CONSTRUCTION"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _fresh(unused_id).erp_stage_code == "CONSTRUCTION"  # 대조군 — 공정 칸을 안 쓴 주문도 그대로 된다

    resp = client.post("/api/update_order_status", json={"order_id": blocked_id, "status": "CONSTRUCTION",
                                                         "admin_override": True, "override_reason": _REASON})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    events = _events(blocked_id, ADMIN_OVERRIDE_EVENT)
    assert len(events) == 1 and events[0].payload["gates"] == ["STEPS_INCOMPLETE"]


def test_단건_상태_쓰기의_다른_이동은_그대로다(client) -> None:
    """대조군: 생산 → 시공이 아닌 이동(같은 자료의 시공 → CS)은 검수 판정을 타지 않는다."""
    _login(client, _user(role="ADMIN", team="CS"))
    oid = _order(stage="CONSTRUCTION", run=False)
    resp = client.post("/api/update_order_status", json={"order_id": oid, "status": "CS"})
    assert resp.status_code == 200, resp.get_data(as_text=True)


def test_일괄_상태_쓰기는_검수_전_주문만_빼고_알린다(client) -> None:
    _login(client, _user(role="ADMIN", team="CS"))
    blocked_id = _order(production={"steps": inspected_steps(upto="assemble")})
    ok_id = _order(production={"steps": inspected_steps()})
    unused_id = _order(production={"steps": _all_off()})  # 모두 꺼짐 — 규칙 밖

    resp = client.post("/api/bulk_update_order_status",
                       json={"order_ids": [blocked_id, ok_id, unused_id], "status": "CONSTRUCTION"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["updated"] == 2 and body["blocked_steps_incomplete"] == [blocked_id]
    assert "1건은 검수까지 끝나지 않아 바꾸지 않았습니다" in body["message"]
    assert _fresh(ok_id).erp_stage_code == "CONSTRUCTION"
    assert _fresh(unused_id).erp_stage_code == "CONSTRUCTION"
    _assert_untouched(blocked_id)

    only = client.post("/api/bulk_update_order_status", json={"order_ids": [blocked_id], "status": "CONSTRUCTION"})
    assert only.status_code == 409 and only.get_json()["success"] is False
    assert only.get_json()["blocked_steps_incomplete"] == [blocked_id]


def test_칸_고치기로_상태를_시공에_넣는_옆문도_막힌다(client) -> None:
    _login(client, _user(role="ADMIN", team="CS"))
    oid = _order(production=_CUT_ONLY)
    resp = client.post("/api/update_order_field", json={"order_id": oid, "field": "status", "value": "CONSTRUCTION"})
    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert resp.get_json()["code"] == "STEPS_INCOMPLETE"
    _assert_untouched(oid)
    mark_order_inspected(oid)
    resp = client.post("/api/update_order_field", json={"order_id": oid, "field": "status", "value": "CONSTRUCTION"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _fresh(oid).erp_stage_code == "CONSTRUCTION"
    unused = _order()  # 대조군 — 칸 없는 옛 주문은 칸 고치기로도 그대로 된다
    resp = client.post("/api/update_order_field", json={"order_id": unused, "field": "status", "value": "CONSTRUCTION"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _fresh(unused).erp_stage_code == "CONSTRUCTION"


# --------------------------------------------------------------------------- #
# 6. 화면(모든 단추가 같은 완료 API · 시트 회색/파랑 · 공정 API complete_ready)
#    → ``test_production_complete_inspect_screens.py`` 로 나눔(파일 크기 래칫 500줄)
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# 7. 위치 고정 — 서버 · 화면이 같은 한 함수
# --------------------------------------------------------------------------- #
def test_판정_함수는_한_곳이고_모두_그것을_부른다() -> None:
    # 2026-11-23 §4-3: 판정 한 곳 = part_progress(카드를 쓴 주문은 표시 줄로, 안 쓴 주문은 steps 칸 규칙을 그대로 부름)
    for mod in (prod_api, complete_move_mod):
        assert mod.complete_block_body is progress_mod.complete_block_body
    assert prod_api.complete_ready is sheet_view_mod.complete_ready is progress_mod.complete_ready
    for mod in (status_mod, field_update_mod):
        assert mod.production_complete_move_block is complete_move_mod.production_complete_move_block
    assert "production_complete_block_body(sd)" in inspect.getsource(progress_mod.complete_block_body)
    assert "_steps_incomplete_block(sd, marks)" in inspect.getsource(prod_api.api_production_complete)  # 일반 쓰기 셋도 아래
    assert "production_complete_move_block(order, from_stage, new_status)" in inspect.getsource(
        status_mod.update_order_status_response)
    assert "marks=bulk_marks.get(order.id))" in inspect.getsource(status_mod.bulk_update_order_status_response)
    assert "production_complete_move_block(" in inspect.getsource(field_update_mod)
    assert "'complete_ready': complete_ready(sd, marks)" in inspect.getsource(sheet_view_mod._full_sheet_extras)
    # 판정 몸통은 공정 모듈 안에만(다른 곳에서 4칸을 다시 세지 않는다)
    assert "step_done_map(sd)" in inspect.getsource(steps_mod.production_steps_missing)


def test_완료_API_주석이_새_규칙을_말한다() -> None:
    doc = prod_api.api_production_complete.__doc__ or ""
    assert "hard gate 가 아니다" not in doc and "검수까지 끝남" in doc and "STEPS_INCOMPLETE" in doc


def test_시험_준비물_모양은_공정_API_칸과_같다() -> None:
    """준비물이 실제 공정 칸 모양(key · label · done · at · by_name)과 다르면 판정이 우연히 통과할 수 있다."""
    sd: dict = {}
    steps_mod.set_production_step(sd, "cut", True, by_name="x", at_iso="t")
    assert set(sd["production"]["steps"][0]) == set(inspected_steps()[0])
    assert production_complete_ready(with_inspected_steps({"production": {"hold": {"active": True}}})) is True
