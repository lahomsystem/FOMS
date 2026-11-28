"""[N공장 완료 취소]도 반장과 관리자만(사장님 결정 2026-11-28 "반장 · 관리자만" — [완료 취소] · [수정 제작]과 같은 규칙).

공장이 둘인 주문의 제작 중 단계 — 전에는 파트 계정도 자기 공장 완료를 ``POST /api/orders/<id>/production/factory-done``
``{factory, done: false}`` 로 취소할 수 있었다. 이제 ``done: false`` 는 반장 · 관리자만 지나고, 그 밖 생산팀(파트 계정 · 파트도 반장도
아닌 계정 · 반장이 아닌 매니저)은 403 ``LEAD_REQUIRED`` + "[2공장 완료 취소]는 반장이나 관리자만 할 수 있어요."(그 길의 다른 거절과 같은
꼴 ``{success: false, data: {code, factory}, error}``)이고 아무것도 안 바뀐다. ``done: true``([N공장 제작 완료])는 그대로 파트 계정도
누른다. 반장의 공장 범위(자기 공장만 — 403 ``FACTORY_FORBIDDEN``)도 그대로. 작업 시트(태블릿 · 휴대폰 · PC [고치기] 켬 — 같은 템플릿)는
파트 계정에게 [N공장 완료 취소] 단추를 안 그리고, 끝난 공장은 공장 줄 "2공장 완료(강검수 11/24 16:10)"로만 보인다.

되돌리면 실패: 파트 계정이 공장 완료를 취소함 · 거절인데 표지 · 버전 · 이벤트가 바뀜 · 파트 계정의 [N공장 제작 완료]가 같이 막힘 ·
반장이나 관리자가 막힘 · 반장이 남의 공장을 취소함 · 파트 계정 시트에 취소 단추가 남음 · 반장 시트에서 취소 단추가 사라짐.
모든 이름 · 번호는 가짜 값이다.
"""
from __future__ import annotations

import copy
import time

import pytest

from db import db_session
from foms.services.production.part_access import factory_uncomplete_lead_only_message
from foms.services.production.pc_view import EDIT_COOKIE, EDIT_COOKIE_PATH
from models import Order, OrderEvent
from tests.support.production_factory_seed import PC, TABLET, factory_user, mixed_order, put_mark, set_cookies, set_factory_done
from tests.support.production_part_claim_seed import login

PARTS = ("cut", "edge", "assemble", "inspect")
PHONE = {"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "915"}
F2 = '<em class="foms-fac foms-fac--2">2공장</em>'
UNDO_BTN = 'data-foms-sheet-factory="2" data-done="0"'
DONE_BTN = 'data-foms-sheet-factory="2" data-done="1"'
MESSAGE_2 = "[2공장 완료 취소]는 반장이나 관리자만 할 수 있어요."
#: 못 하게 된 2공장 생산팀 — (이름, role, 파트)
BLOCKED = (("강검수", "STAFF", "inspect"), ("강재단", "STAFF", "cut"), ("강파트없음", "STAFF", None), ("강매니저", "MANAGER", None),
           ("강파트매니저", "MANAGER", "edge"))
#: 지금처럼 되는 사람 — (이름, role, 팀, 공장, 파트, 반장 칸)
ALLOWED = (("정관리", "ADMIN", "CS", 1, None, None), ("강반장", "STAFF", "PRODUCTION", 2, None, True),
           ("강파트반장", "STAFF", "PRODUCTION", 2, "inspect", True), ("강매니저반장", "MANAGER", "PRODUCTION", 2, None, True))
DEVICES = (("태블릿", TABLET, False), ("휴대폰", PHONE, False), ("PC 고치기 켬", PC, True))


def _api(client, oid: int, factory: int, done: bool):
    return client.post(f"/api/orders/{oid}/production/factory-done", json={"factory": factory, "done": done})


def _factory2_done_order():
    """섞인 주문(장 셋 — 셋째만 2공장) · 2공장 완료 표지가 살아 있고 1공장은 제작 중."""
    seed = mixed_order(3, f2=(2,))
    set_factory_done(seed.id, 2, [seed.keys[2]])
    return seed


def _snapshot(oid: int) -> dict:
    db_session.expire_all()
    row = db_session.get(Order, oid)
    events = db_session.query(OrderEvent).filter(OrderEvent.order_id == oid).order_by(OrderEvent.id).all()
    return {"stage": (row.erp_stage_code, row.status), "version": row.mutation_version, "sd": copy.deepcopy(row.structured_data),
            "events": [(e.id, e.event_type) for e in events]}


def _factory_done(oid: int):
    db_session.expire_all()
    return (db_session.get(Order, oid).structured_data.get("production") or {}).get("factory_done") or {}


def _sheet(client, oid: int, device: dict, *, edit: bool = False) -> str:
    set_cookies(client, device)
    client.delete_cookie(EDIT_COOKIE, domain="localhost", path=EDIT_COOKIE_PATH)
    if edit:
        client.set_cookie(EDIT_COOKIE, str(int(time.time())), domain="localhost", path=EDIT_COOKIE_PATH)
    res = client.get(f"/erp/production/sheet/{oid}")
    assert res.status_code == 200
    return res.get_data(as_text=True)


# --------------------------------------------------------------------------- #
# 1. 서버
# --------------------------------------------------------------------------- #
def test_거절_글은_공장_이름이_든_해요체_한_문장이다() -> None:
    assert factory_uncomplete_lead_only_message(2) == MESSAGE_2
    assert factory_uncomplete_lead_only_message(1) == "[1공장 완료 취소]는 반장이나 관리자만 할 수 있어요."


@pytest.mark.parametrize("name,role,part", BLOCKED)
def test_반장도_관리자도_아닌_생산팀의_공장_완료_취소는_403이고_아무것도_안_바뀐다(client, name, role, part) -> None:
    seed = _factory2_done_order()
    before = _snapshot(seed.id)
    login(client, factory_user(name, factory=2, role=role, part=part))
    res = _api(client, seed.id, 2, done=False)
    assert res.status_code == 403, (name, res.get_json())
    assert res.get_json() == {"success": False, "data": {"code": "LEAD_REQUIRED", "factory": 2}, "error": MESSAGE_2}, name
    assert _snapshot(seed.id) == before, name


def test_파트_계정은_공장_제작_완료는_그대로_하고_취소만_못_한다(client) -> None:
    seed = mixed_order(3, f2=(2,))
    insp2 = factory_user("강검수", factory=2, part="inspect")
    for part in PARTS:
        put_mark(seed, 2, part, "DONE", insp2)
    login(client, insp2)
    res = _api(client, seed.id, 2, done=True)
    assert res.status_code == 200 and res.get_json()["data"]["final"] is False, res.get_json()
    assert set(_factory_done(seed.id)) == {"2"}
    before = _snapshot(seed.id)
    # 완료한 바로 그 사람도 취소는 못 한다
    res = _api(client, seed.id, 2, done=False)
    assert res.status_code == 403 and res.get_json()["error"] == MESSAGE_2
    assert _snapshot(seed.id) == before
    # 대조: 반장이 취소하면 지금처럼 풀린다
    login(client, factory_user("강반장", factory=2, lead=True))
    res = _api(client, seed.id, 2, done=False)
    assert res.status_code == 200 and res.get_json()["data"]["changed"] is True, res.get_json()
    assert _factory_done(seed.id) == {}


@pytest.mark.parametrize("name,role,team,factory,part,lead", ALLOWED)
def test_반장과_관리자는_지금처럼_공장_완료를_취소한다(client, name, role, team, factory, part, lead) -> None:
    seed = _factory2_done_order()
    login(client, factory_user(name, factory=factory, role=role, team=team, part=part, lead=lead))
    res = _api(client, seed.id, 2, done=False)
    assert res.status_code == 200 and res.get_json()["data"]["factory_done"] == {"1": None, "2": None}, (name, res.get_json())
    after = _snapshot(seed.id)
    assert after["stage"][0] == "PRODUCTION"
    assert [t for _i, t in after["events"] if t.startswith("PRODUCTION_FACTORY")] == ["PRODUCTION_FACTORY_UNCOMPLETED"], name


def test_반장의_공장_범위는_그대로_자기_공장만이다(client) -> None:
    seed = _factory2_done_order()
    before = _snapshot(seed.id)
    login(client, factory_user("윤반장", factory=1, lead=True))
    res = _api(client, seed.id, 2, done=False)
    assert res.status_code == 403 and res.get_json()["data"]["code"] == "FACTORY_FORBIDDEN", res.get_json()
    assert _snapshot(seed.id) == before


# --------------------------------------------------------------------------- #
# 2. 화면 — 작업 시트(태블릿 · 휴대폰 · PC [고치기] 켬 — 같은 템플릿)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name,role,part", BLOCKED)
def test_작업_시트는_파트_계정에게_공장_완료_취소_단추를_안_그린다(client, name, role, part) -> None:
    done = _factory2_done_order()
    making = mixed_order(3, f2=(2,))  # 대조: 2공장이 아직 안 끝난 주문
    login(client, factory_user(name, factory=2, role=role, part=part))
    for label, device, edit in DEVICES:
        page = _sheet(client, done.id, device, edit=edit)
        assert UNDO_BTN not in page and f"<b>{F2} 완료 취소</b>" not in page, (name, label)
        assert f"{F2} 완료(강검수 11/24 16:10)" in page, (name, label)  # 끝난 공장은 공장 줄로만(누를 수 없는 글)
        assert 'data-tablet-sheet-action="production-hold"' in page, (name, label)  # 쓰기 단추 줄은 그대로
        page = _sheet(client, making.id, device, edit=edit)
        assert DONE_BTN in page and f"<b>{F2} 제작 완료</b>" in page, (name, label)  # [2공장 제작 완료]는 그대로


@pytest.mark.parametrize("name,role,team,factory,part,lead", ALLOWED)
def test_작업_시트는_반장과_관리자에게_공장_완료_취소_단추를_그대로_그린다(client, name, role, team, factory, part, lead) -> None:
    done = _factory2_done_order()
    login(client, factory_user(name, factory=factory, role=role, team=team, part=part, lead=lead))
    for label, device, edit in DEVICES:
        page = _sheet(client, done.id, device, edit=edit)
        assert page.count(UNDO_BTN) == 1 and f"<b>{F2} 완료 취소</b>" in page, (name, label)
