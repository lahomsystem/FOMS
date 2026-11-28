"""[완료 취소] · [수정 제작]은 반장과 관리자만(사장님 결정 2026-11-28 "파트 계정은 제작 완료 · 보류까지").

전에는 생산팀이면 누구나(검수 파트 계정도) 작업 시트에서 제작 완료한 주문을 [완료 취소] · [수정 제작]으로 되돌릴 수 있었다.
이제 두 API(``POST /api/orders/<id>/production/uncomplete`` · ``…/rework``)는 반장 · 관리자만 지나고, 그 밖 생산팀(파트 계정 ·
파트도 반장도 아닌 계정 · 반장이 아닌 매니저)은 403 ``LEAD_REQUIRED`` + 해요체 한 문장이다 — 주문을 읽기 전에 막아 단계 · 회차 ·
이벤트가 그대로다. 작업 시트(태블릿 · 휴대폰 · PC [고치기] 켬 — 같은 템플릿)는 그 사람에게 두 단추를 안 그린다.
판정은 한 곳(``part_access.can_revert_completed`` = PC [완료 처리]를 막는 ``can_override_marks``). [제작 완료] · [보류]는 그대로.

되돌리면 실패: 파트 계정이 두 길을 지남 · 거절인데 무엇인가 바뀜 · 반장이나 관리자가 막힘 · 파트 계정 시트에 두 단추가 남음 ·
반장 시트에서 두 단추가 사라짐 · 파트 계정의 [제작 완료] · [보류]가 같이 막힘. 모든 이름 · 번호는 가짜 값이다.
"""
from __future__ import annotations

import copy
import time
from types import SimpleNamespace

import pytest
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.production.part_access import (
    REWORK_LEAD_ONLY_MESSAGE,
    UNCOMPLETE_LEAD_ONLY_MESSAGE,
    can_override_marks,
    can_revert_completed,
)
from foms.services.production.pc_view import EDIT_COOKIE, EDIT_COOKIE_PATH
from foms.services.production.write_access import PRODUCTION_WRITE_DENIED_MESSAGE
from models import Order, OrderEvent, ProductionRun
from tests.support.production_home_step_panel_seed import TABLET, add_order, get_html, set_cookies
from tests.support.production_part_claim_seed import login, make_user

ALL_STEPS = ("cut", "edge", "assemble", "inspect")
PHONE = {"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "915"}
PC = {"foms_ptr": "fine", "foms_vw": "wide", "foms_scr": "1920"}
UNCOMPLETE_BTN = 'data-tablet-sheet-action="production-uncomplete"'
REWORK_BTN = 'data-tablet-sheet-action="production-rework"'
#: (길, 몸, 거절 글)
PATHS = (("uncomplete", {}, UNCOMPLETE_LEAD_ONLY_MESSAGE), ("rework", {"reason": "가짜 사유"}, REWORK_LEAD_ONLY_MESSAGE))
#: 못 하게 된 생산팀 — (이름, role, 파트, 반장 칸)
BLOCKED = (
    ("검수파트", "STAFF", "inspect", None),
    ("재단파트", "STAFF", "cut", None),
    ("파트없음", "STAFF", None, None),
    ("반장아닌매니저", "MANAGER", None, None),
    ("파트매니저", "MANAGER", "edge", None),
)
#: 지금처럼 되는 사람 — (이름, role, 팀, 파트, 반장 칸)
ALLOWED = (
    ("관리자", "ADMIN", None, None, None),
    ("생산팀관리자", "ADMIN", "PRODUCTION", "inspect", None),
    ("반장", "STAFF", "PRODUCTION", None, True),
    ("파트반장", "STAFF", "PRODUCTION", "inspect", True),
    ("매니저반장", "MANAGER", "PRODUCTION", None, True),
)


def _making_order(name: str, **kwargs) -> int:
    """제작 중 주문(공정 넷을 끝냄)의 id."""
    return add_order(name, 1, done=ALL_STEPS, **kwargs).id


def _done_order(name: str) -> int:
    """제작 완료한 주문(시공 대기)의 id — 공정 넷을 끝낸 제작 중 주문의 단계만 옮긴다(옛 시험과 같은 준비물)."""
    oid = _making_order(name)
    row = db_session.get(Order, oid)
    sd = copy.deepcopy(row.structured_data)
    sd["workflow"]["stage"] = "CONSTRUCTION"
    row.structured_data = sd
    flag_modified(row, "structured_data")
    row.erp_stage_code = row.status = "CONSTRUCTION"
    db_session.commit()
    return oid


def _snapshot(oid: int) -> dict:
    """단계 · 회차 · 이벤트 — 거절 앞뒤로 견줄 값 전부."""
    db_session.expire_all()
    row = db_session.get(Order, oid)
    runs = db_session.query(ProductionRun).filter(ProductionRun.order_id == oid).order_by(ProductionRun.id).all()
    events = db_session.query(OrderEvent).filter(OrderEvent.order_id == oid).order_by(OrderEvent.id).all()
    return {
        "stage": (row.erp_stage_code, row.status), "version": row.mutation_version,
        "sd": copy.deepcopy(row.structured_data),
        "runs": [(r.id, r.status, r.is_current) for r in runs],
        "events": [(e.id, e.event_type) for e in events],
    }


def _sheet(client, oid: int, device: dict, *, edit: bool = False) -> str:
    set_cookies(client, device)
    client.delete_cookie(EDIT_COOKIE, domain="localhost", path=EDIT_COOKIE_PATH)
    if edit:
        client.set_cookie(EDIT_COOKIE, str(int(time.time())), domain="localhost", path=EDIT_COOKIE_PATH)
    return get_html(client, f"/erp/production/sheet/{oid}")


# --------------------------------------------------------------------------- #
# 1. 한 함수 — PC [완료 처리]를 막는 것과 같은 판정
# --------------------------------------------------------------------------- #
def test_판정은_완료_처리와_같은_함수다() -> None:
    def person(role, team, *, part=None, lead=None, partner=None, active=True):
        return SimpleNamespace(id=990128, role=role, team=team, production_part=part, production_parts=None,
                               production_lead=lead, partner_org_id=partner, is_active=active, name="가짜")

    yes = (person("ADMIN", None), person("ADMIN", "CS"), person("STAFF", "PRODUCTION", lead=True),
           person("MANAGER", "PRODUCTION", lead=True), person("STAFF", "PRODUCTION", part="inspect", lead=True))
    no = (None, person("STAFF", "PRODUCTION", part="inspect"), person("STAFF", "PRODUCTION"), person("MANAGER", "PRODUCTION"),
          person("MANAGER", "PRODUCTION", part="cut"), person("MANAGER", "CS"), person("STAFF", "SALES", lead=True),
          person("VIEWER", "PRODUCTION", lead=True), person("STAFF", "PRODUCTION", lead=True, partner=3),
          person("ADMIN", None, active=False))
    for user in yes:
        assert can_revert_completed(user) is True and can_override_marks(user) is True, vars(user)
    for user in no:
        assert can_revert_completed(user) is False and can_override_marks(user) is False, user and vars(user)


# --------------------------------------------------------------------------- #
# 2. 서버 — 파트 계정 · 반장 아닌 생산팀은 403, 아무것도 안 바뀐다
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name,role,part,lead", BLOCKED)
def test_반장도_관리자도_아닌_생산팀은_두_길이_403이고_아무것도_안_바뀐다(client, name, role, part, lead) -> None:
    order = _done_order(f"가람{name}집")
    before = _snapshot(order)
    login(client, make_user(name, role=role, part=part, lead=lead))
    for path, body, message in PATHS:
        resp = client.post(f"/api/orders/{order}/production/{path}", json=body)
        assert resp.status_code == 403, (name, path, resp.get_json())
        assert resp.get_json() == {"success": False, "code": "LEAD_REQUIRED", "message": message}, (name, path)
        assert _snapshot(order) == before, (name, path)
    # 없는 주문도 같은 답(주문을 읽기 전에 막는다) — 반장은 지금처럼 404
    resp = client.post("/api/orders/99999999/production/uncomplete", json={})
    assert resp.status_code == 403 and resp.get_json()["code"] == "LEAD_REQUIRED"


def test_거절_글은_해요체_한_문장이다() -> None:
    assert UNCOMPLETE_LEAD_ONLY_MESSAGE == "[완료 취소]는 반장이나 관리자만 할 수 있어요."
    assert REWORK_LEAD_ONLY_MESSAGE == "[수정 제작]은 반장이나 관리자만 할 수 있어요."


def test_생산팀이_아닌_사람은_지금처럼_생산_쓰기_문이_먼저_막는다(client) -> None:
    order = _done_order("가람상담집")
    before = _snapshot(order)
    login(client, make_user("상담직원", team="CS"))
    for path, body, _message in PATHS:
        resp = client.post(f"/api/orders/{order}/production/{path}", json=body)
        assert resp.status_code == 403 and resp.get_json().get("error") == PRODUCTION_WRITE_DENIED_MESSAGE, (path, resp.get_json())
        assert resp.get_json().get("code") != "LEAD_REQUIRED", path
    assert _snapshot(order) == before


@pytest.mark.parametrize("name,role,team,part,lead", ALLOWED)
def test_반장과_관리자는_지금처럼_완료_취소와_수정_제작을_한다(client, name, role, team, part, lead) -> None:
    login(client, make_user(name, team=team, role=role, part=part, lead=lead))
    first = _done_order(f"가람{name}취소집")
    resp = client.post(f"/api/orders/{first}/production/uncomplete", json={})
    assert resp.status_code == 200 and resp.get_json()["new_status"] == "PRODUCTION", (name, resp.get_json())
    after = _snapshot(first)
    assert after["stage"] == ("PRODUCTION", "PRODUCTION")
    assert "PRODUCTION_COMPLETE_REVERTED" in [t for _i, t in after["events"]]
    assert [cur for _i, _s, cur in after["runs"]].count(True) == 1

    second = _done_order(f"가람{name}수정집")
    keys = [db_session.get(Order, second).structured_data["drawing_current_files"][0]["key"]]  # 다시 만들 도면 한 장(11-28)
    resp = client.post(f"/api/orders/{second}/production/rework", json={"reason": "문짝 치수", "keys": keys})
    assert resp.status_code == 200 and resp.get_json()["new_status"] == "PRODUCTION", (name, resp.get_json())
    after = _snapshot(second)
    assert after["stage"] == ("PRODUCTION", "PRODUCTION")
    assert after["sd"]["production"]["rework"]["active"] is True and after["sd"]["production"]["rework"]["count"] == 1
    assert "PRODUCTION_REWORK_STARTED" in [t for _i, t in after["events"]]
    # 없는 주문 — 문을 지나 지금처럼 404
    assert client.post("/api/orders/99999999/production/uncomplete", json={}).status_code == 404


def test_파트_계정의_제작_완료와_보류는_그대로다(client) -> None:
    login(client, make_user("강검수", part="inspect"))
    order = _making_order("가람검수집", pngs=0)
    resp = client.post(f"/api/orders/{order}/production/hold", json={"active": True, "reason": "자재 기다림"})
    assert resp.status_code == 200, resp.get_json()
    resp = client.post(f"/api/orders/{order}/production/hold", json={"active": False, "reason": ""})
    assert resp.status_code == 200, resp.get_json()
    resp = client.post(f"/api/orders/{order}/production/complete", json={})
    assert resp.status_code == 200, resp.get_json()
    assert _snapshot(order)["stage"][0] == "CONSTRUCTION"
    # 완료한 바로 그 사람도 되돌리기는 못 한다
    resp = client.post(f"/api/orders/{order}/production/uncomplete", json={})
    assert resp.status_code == 403 and resp.get_json()["message"] == UNCOMPLETE_LEAD_ONLY_MESSAGE
    assert _snapshot(order)["stage"][0] == "CONSTRUCTION"


# --------------------------------------------------------------------------- #
# 3. 화면 — 작업 시트(태블릿 · 휴대폰 · PC [고치기] 켬)
# --------------------------------------------------------------------------- #
DEVICES = (("태블릿", TABLET, False), ("휴대폰", PHONE, False), ("PC 고치기 켬", PC, True))


@pytest.mark.parametrize("name,role,part,lead", BLOCKED)
def test_작업_시트는_반장_아닌_생산팀에게_두_단추를_안_그린다(client, name, role, part, lead) -> None:
    login(client, make_user(name, role=role, part=part, lead=lead))
    done, making = _done_order(f"가람{name}완료집"), _making_order(f"가람{name}제작집")
    for label, device, edit in DEVICES:
        page = _sheet(client, done, device, edit=edit)
        assert UNCOMPLETE_BTN not in page and REWORK_BTN not in page, (name, label)
        assert ">완료 취소</button>" not in page and ">수정 제작</button>" not in page, (name, label)
        # 쓰기 단추 줄은 그대로 있다 — [보류] · [불량 알리기]
        assert 'data-tablet-sheet-action="production-hold"' in page and "data-foms-sheet-defect-toggle" in page, (name, label)
        # 음성 대조 — 같은 사람 · 같은 기기의 제작 중 주문에는 [제작 완료] · [보류]가 그대로
        page = _sheet(client, making, device, edit=edit)
        assert 'data-tablet-sheet-action="production-complete"' in page and "<b>제작 완료</b>" in page, (name, label)
        assert 'data-tablet-sheet-action="production-hold"' in page, (name, label)


@pytest.mark.parametrize("name,role,team,part,lead", ALLOWED)
def test_작업_시트는_반장과_관리자에게_두_단추를_그대로_그린다(client, name, role, team, part, lead) -> None:
    login(client, make_user(name, team=team, role=role, part=part, lead=lead))
    done = _done_order(f"가람{name}완료집")
    for label, device, edit in DEVICES:
        page = _sheet(client, done, device, edit=edit)
        assert page.count(UNCOMPLETE_BTN) == 1 and page.count(REWORK_BTN) == 1, (name, label)
        assert ">완료 취소</button>" in page and ">수정 제작</button>" in page, (name, label)
    # PC 보기 전용([고치기] 끔)은 지금처럼 쓰기 단추 줄이 통째 없다
    page = _sheet(client, done, PC, edit=False)
    assert UNCOMPLETE_BTN not in page and REWORK_BTN not in page, name
