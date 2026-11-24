"""공장마다 제작 완료(설계서 2026-11-23 §4-4 · §4-14 · §7 · §19, 3단계 ⑥) — factory-done API · 옛 [제작 완료] · 되돌리기 · 물음 · 폼 잠금.

* 한 공장 주문 = 지금 길 그대로(표지 안 씀). 섞인 주문 첫 공장 = 표지만(단계 그대로 · 버전 +1 · 이벤트), 둘째 공장 = 그 요청 안에서
  시공 대기(버전 +1 한 번 · 표지 둘). 옛 ``production/complete`` 로 섞인 주문 = 남은 공장 모두.
* 공장 문 403 · 그 공장 장 없음 409 · 미완료 409(+left) · 보류 409 · 남이 이미 완료 409 · 같은 사람 다시 = 200(바뀜 없음).
* 새 key(새 판)가 오면 그 공장 완료가 풀림 · 장이 빠지면 안 풀림. 완료 취소 = 누른 사람 공장만(관리자 고름, 기본 둘 다) · 재제작 ·
  제작 취소 = 표지 모두 지움 · 공장 완료 취소(생산 단계).
* 카드 쓰기 응답 ``factory_ready``(섞인 주문의 그 공장 마지막 검수 장) — 한 공장 주문은 ``order_ready`` 그대로(대조군).
* 폼 저장(PUT structured)이 ``production.factory_done`` 을 못 바꾼다(앞 검토 구멍).

되돌리면 실패: 첫 공장에서 단계가 넘어감 · 둘째 공장에서 안 넘어감 · 남의 공장 완료 · 한 공장 주문에 표지 · 완료 취소가 남의 공장까지
지움 · 폼 저장이 표지를 덮음.
"""
from __future__ import annotations

import copy
import inspect

import pytest
from sqlalchemy.orm.attributes import flag_modified

import foms.api.production.orders as prod_api
import foms.services.production.complete_order as complete_order_mod
import foms.services.production.factory_complete as factory_complete_mod
from db import db_session
from foms.services.orders.drawing_factory import factory_done_entry
from foms.services.orders.structured_form_projection import lock_server_owned_keys
from models import Order, OrderEvent
from tests.support.production_factory_seed import TABLET, factory_user, mixed_order, put_mark, set_cookies, set_factory_done
from tests.support.production_part_claim_seed import fresh, login, mark

PARTS = ("cut", "edge", "assemble", "inspect")


def _api(client, oid: int, factory: int, done: bool = True):
    return client.post(f"/api/orders/{oid}/production/factory-done", json={"factory": factory, "done": done})


def _all_done(seed, js, who) -> None:
    for j in js:
        for part in PARTS:
            put_mark(seed, j, part, "DONE", who)


def _state(oid: int):
    order = fresh(oid)
    return order.erp_stage_code, int(order.mutation_version or 0), (order.structured_data.get("production") or {}).get("factory_done")


@pytest.fixture
def people():
    return {"insp1": factory_user("윤검수", part="inspect"), "insp2": factory_user("강검수", factory=2, part="inspect"),
            "admin": factory_user("정관리", role="ADMIN", team="CS"), "boss2": factory_user("강반장", factory=2, lead=True)}


def test_first_factory_marks_only_second_moves_to_construction(client, people):
    seed = mixed_order(5, f2=(3, 4))
    _all_done(seed, range(5), people["insp1"])
    login(client, people["insp2"])
    stage0, ver0, _ = _state(seed.id)
    res = _api(client, seed.id, 2)
    data = res.get_json()["data"]
    assert res.status_code == 200 and data["final"] is False and data["stage"] == "PRODUCTION"
    stage, ver, done = _state(seed.id)
    assert stage == stage0 == "PRODUCTION" and ver == ver0 + 1
    assert done["2"]["keys"] == list(seed.keys[3:]) and done["2"]["by_name"] == "강검수" and "1" not in done
    assert [e.payload["factory"] for e in db_session.query(OrderEvent).filter_by(
        order_id=seed.id, event_type="PRODUCTION_FACTORY_COMPLETED")] == [2]
    login(client, people["insp1"])
    res = _api(client, seed.id, 1)
    assert res.status_code == 200 and res.get_json()["data"]["final"] is True
    stage, ver2, done = _state(seed.id)
    assert stage == "CONSTRUCTION" and ver2 == ver + 1  # 버전 +1 한 번(전이 + 곁일 같은 tx)
    assert done["1"]["by_name"] == "윤검수" and done["2"]["by_name"] == "강검수"


def test_single_factory_order_completes_without_marks(client, people):
    seed = mixed_order(3, f2=())
    _all_done(seed, range(3), people["insp1"])
    login(client, people["insp1"])
    res = _api(client, seed.id, 1)
    assert res.status_code == 200 and res.get_json()["data"]["final"] is True
    stage, _ver, done = _state(seed.id)
    assert stage == "CONSTRUCTION" and done is None  # 한 공장 주문은 표지 없음
    seed2 = mixed_order(2, f2=())
    _all_done(seed2, range(2), people["insp1"])
    assert client.post(f"/api/orders/{seed2.id}/production/complete", json={}).status_code == 200
    assert _state(seed2.id)[0] == "CONSTRUCTION" and _state(seed2.id)[2] is None  # 대조군: 옛 길 그대로


def test_gates(client, people):
    seed = mixed_order(3, f2=(2,))
    _all_done(seed, (0, 1), people["insp1"])
    login(client, people["insp1"])
    res = _api(client, seed.id, 2)
    assert res.status_code == 403 and res.get_json()["data"]["code"] == "FACTORY_FORBIDDEN"
    assert res.get_json()["error"] == "2공장 제작 완료는 2공장 계정이나 관리자만 할 수 있어요."
    login(client, people["insp2"])
    res = _api(client, seed.id, 2)  # 2공장 장 네 파트 아직
    body = res.get_json()
    assert res.status_code == 409 and body["data"]["code"] == "FACTORY_NOT_READY"
    assert body["error"] == "2공장에 아직 미완료가 있어요 — 재단 1장 · 엣지 1장 · 조립 1장 · 검수 1장"
    plain = mixed_order(2, f2=())
    res = _api(client, plain.id, 2)
    assert res.status_code == 409 and res.get_json()["data"]["code"] == "NO_FACTORY_SHEETS"
    _all_done(seed, (2,), people["insp2"])
    order = db_session.get(Order, seed.id)
    sd = copy.deepcopy(order.structured_data)
    sd["production"]["hold"] = {"active": True, "reason": "자재 기다림"}
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    res = _api(client, seed.id, 2)
    assert res.status_code == 409 and res.get_json()["error"] == "보류된 주문이라 지금은 못 눌러요. 보류가 풀리면 다시 돼요."
    assert _state(seed.id)[2] is None


def test_already_done_by_other_and_idempotent_same_person(client, people):
    seed = mixed_order(3, f2=(2,))
    _all_done(seed, range(3), people["insp1"])
    login(client, people["insp2"])
    assert _api(client, seed.id, 2).status_code == 200
    again = _api(client, seed.id, 2)
    assert again.status_code == 200 and again.get_json()["data"]["changed"] is False
    login(client, people["boss2"])
    res = _api(client, seed.id, 2)
    assert res.status_code == 409 and res.get_json()["error"] == "그사이 강검수가 2공장 제작 완료했어요. 더 할 일은 없어요."


def test_after_construction_says_someone_completed(client, people):
    seed = mixed_order(3, f2=(2,))
    _all_done(seed, range(3), people["insp1"])
    login(client, people["admin"])
    assert client.post(f"/api/orders/{seed.id}/production/complete", json={}).status_code == 200
    _stage, _v, done = _state(seed.id)
    assert set(done) == {"1", "2"} and done["1"]["by_name"] == done["2"]["by_name"] == "정관리"  # 옛 길 = 남은 공장 모두
    login(client, people["insp2"])
    res = _api(client, seed.id, 2)
    assert res.status_code == 409 and res.get_json()["data"]["code"] == "INVALID_STAGE"
    assert res.get_json()["error"] == "그사이 정관리가 제작 완료했어요. 더 할 일은 없어요."


def test_new_drawing_releases_that_factory_and_removed_sheet_does_not(people):
    seed = mixed_order(3, f2=(1, 2))
    set_factory_done(seed.id, 2, seed.keys[1:])
    order = db_session.get(Order, seed.id)
    assert factory_done_entry(order.structured_data, 2) is not None
    sd = copy.deepcopy(order.structured_data)
    sd["drawing_current_files"] = sd["drawing_current_files"][:2]  # 2공장 장 하나 빠짐 → 완료 그대로
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    assert factory_done_entry(fresh(seed.id).structured_data, 2) is not None
    order = db_session.get(Order, seed.id)
    sd = copy.deepcopy(order.structured_data)
    sd["drawing_current_files"][1] = dict(sd["drawing_current_files"][1], key="new/v2.png")  # 같은 시트 새 판 → 풀림
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    assert factory_done_entry(fresh(seed.id).structured_data, 2) is None


def test_uncomplete_reopens_only_the_pressers_factory_and_admin_picks(client, people):
    seeds = []
    for _ in range(3):
        seed = mixed_order(3, f2=(2,))
        _all_done(seed, range(3), people["insp1"])
        login(client, people["admin"])
        assert client.post(f"/api/orders/{seed.id}/production/complete", json={}).status_code == 200
        seeds.append(seed)
    login(client, people["boss2"])
    assert client.post(f"/api/orders/{seeds[0].id}/production/uncomplete", json={}).status_code == 200
    stage, _v, done = _state(seeds[0].id)
    assert stage == "PRODUCTION" and set(done) == {"1"}  # 2공장만 다시 제작 중
    login(client, people["admin"])
    assert client.post(f"/api/orders/{seeds[1].id}/production/uncomplete", json={"factories": [1]}).status_code == 200
    assert set(_state(seeds[1].id)[2]) == {"2"}
    assert client.post(f"/api/orders/{seeds[2].id}/production/uncomplete", json={}).status_code == 200
    assert _state(seeds[2].id)[2] is None  # 관리자 기본 = 둘 다


def test_rework_and_cancel_clear_marks_and_factory_undo(client, people):
    seed = mixed_order(3, f2=(2,))
    _all_done(seed, range(3), people["insp1"])
    login(client, people["admin"])
    assert client.post(f"/api/orders/{seed.id}/production/complete", json={}).status_code == 200
    assert client.post(f"/api/orders/{seed.id}/production/rework", json={"reason": "문짝"}).status_code == 200
    assert _state(seed.id)[2] is None
    other = mixed_order(3, f2=(2,))
    set_factory_done(other.id, 2, [other.keys[2]])
    assert client.post(f"/api/orders/{other.id}/production/cancel", json={}).status_code == 200
    assert _state(other.id)[2] is None
    third = mixed_order(3, f2=(2,))
    set_factory_done(third.id, 2, [third.keys[2]])
    login(client, people["boss2"])
    res = _api(client, third.id, 2, done=False)
    assert res.status_code == 200 and _state(third.id)[2] is None and _state(third.id)[0] == "PRODUCTION"
    assert [e.event_type for e in db_session.query(OrderEvent).filter_by(order_id=third.id)
            if e.event_type.startswith("PRODUCTION_FACTORY")] == ["PRODUCTION_FACTORY_UNCOMPLETED"]


def test_card_write_asks_factory_ready_and_single_factory_keeps_order_ready(client, people):
    seed = mixed_order(3, f2=(2,))
    for j in range(3):
        for part in ("cut", "edge", "assemble"):
            put_mark(seed, j, part, "DONE", people["insp1"])
    login(client, people["insp2"])
    assert mark(client, seed, 2, "inspect", "take", "none").status_code == 200
    data = mark(client, seed, 2, "inspect", "done", "need").get_json()["data"]
    ready = data["factory_ready"]
    assert data["order_ready"] is None and ready["factory"] == 2 and ready["final"] is False
    assert ready["message"] == "2공장 도면 1장이 모두 완료됐어요. 1공장은 아직 제작 중이에요."
    plain = mixed_order(2, f2=())
    for j in range(2):
        for part in ("cut", "edge", "assemble"):
            put_mark(plain, j, part, "DONE", people["insp1"])
    put_mark(plain, 0, "inspect", "DONE", people["insp1"])
    login(client, people["insp1"])
    assert mark(client, plain, 1, "inspect", "take", "none").status_code == 200
    data = mark(client, plain, 1, "inspect", "done", "need").get_json()["data"]
    assert data["order_ready"] == {"order_id": plain.id} and data["factory_ready"] is None


def test_form_save_cannot_overwrite_factory_done():
    old = {"production": {"steps": [], "factory_done": {"2": {"keys": ["k"], "by_name": "강검수"}}}}
    form = {"production": {"steps": [{"key": "cut"}], "factory_done": {"2": {"keys": ["k", "x"]}, "1": {"keys": ["a"]}}}}
    assert lock_server_owned_keys(old, form) == ["production.factory_done"]
    assert form["production"] == {"steps": [{"key": "cut"}], "factory_done": old["production"]["factory_done"]}
    bare = {"production": {"steps": []}}
    lock_server_owned_keys(old, bare)
    assert bare["production"]["factory_done"] == old["production"]["factory_done"]  # 폼이 안 보내도 서버 값 그대로
    planted = {"production": {"factory_done": {"1": {"keys": ["a"]}}}}
    assert lock_server_owned_keys({"production": {}}, planted) == ["production.factory_done"]
    assert "factory_done" not in planted["production"]


def test_structured_put_keeps_server_factory_done(client, people):
    seed = mixed_order(3, f2=(2,))
    set_factory_done(seed.id, 2, [seed.keys[2]])
    login(client, people["admin"])
    snap = client.get(f"/api/orders/{seed.id}/structured").get_json()["structured_data"]
    snap["production"]["factory_done"] = {"1": {"keys": list(seed.keys[:2]), "by_name": "가짜"}}
    snap["parties"]["customer"].update(phone="010-0000-0000")  # 폼이 늘 싣는 필수 칸
    snap.update(site={"address_full": "가짜시 1"}, items=[{"product_name": "가짜장", "spec_width": "2400"}])
    res = client.put(f"/api/orders/{seed.id}/structured", json={"structured_data": snap})
    assert res.status_code == 200, res.get_json()
    done = fresh(seed.id).structured_data["production"]["factory_done"]
    assert set(done) == {"2"} and done["2"]["by_name"] == "강검수"


def test_one_body_for_complete_and_last_factory():
    """위치 고정(설계서 §4-14 — 제작 완료 본문을 서비스로 옮김): 옛 API 는 서비스 한 곳을 부르고, 공장 완료의 '마지막'도 같은 검수까지 게이트."""
    assert "complete_production(" in inspect.getsource(prod_api.api_production_complete)
    assert "_steps_incomplete_block(sd, marks)" in inspect.getsource(complete_order_mod._complete_gates)
    assert "_steps_incomplete_block(sd, marks)" in inspect.getsource(factory_complete_mod._final_complete)
    assert "mark_remaining_factories(sd, user)" in inspect.getsource(complete_order_mod._apply_complete_side_effects)


def _sheet(client, oid: int) -> str:
    set_cookies(client, TABLET)
    res = client.get(f"/erp/production/sheet/{oid}")
    assert res.status_code == 200
    return res.get_data(as_text=True)


def test_work_sheet_factory_buttons(client, people):
    seed = mixed_order(3, f2=(2,))
    _all_done(seed, (0, 1), people["insp1"])
    login(client, people["boss2"])
    html = _sheet(client, seed.id)
    assert 'data-foms-sheet-facline>1공장 제작 중 · 2공장 제작 중</p>' in html
    assert ('data-foms-sheet-factory="2" data-done="1"' in html and 'aria-disabled="true" data-foms-sheet-factory-why='
            '"2공장에 아직 미완료가 있어요 — 재단 1장 · 엣지 1장 · 조립 1장 · 검수 1장"' in html)
    assert 'data-tablet-sheet-action="production-complete"' not in html  # 1공장이 안 끝났으니 [제작 완료] 없음
    assert "foms-production-sheet-factory.js?v=" in html
    login(client, people["admin"])
    html = _sheet(client, seed.id)
    assert html.count("data-foms-sheet-factory=") == 2 and "<b>1공장 제작 완료</b>" in html and "<b>2공장 제작 완료</b>" in html
    set_factory_done(seed.id, 2, [seed.keys[2]])
    html = _sheet(client, seed.id)
    assert "2공장 완료(강검수 11/24 16:10)" in html and "<b>2공장 완료 취소</b>" in html
    assert 'data-tablet-sheet-action="production-complete"' in html  # 남은 공장 하나 = 지금 [제작 완료]
    plain = mixed_order(2, f2=())
    html = _sheet(client, plain.id)
    assert "data-foms-sheet-factory" not in html and "foms-production-sheet-factory.js" not in html  # 한 공장 주문 그대로


def test_sheet_factory_api_reads_the_same_done_mark(client, people):
    """도면팀 공장 지정 API(3단계 ④)의 409 ``FACTORY_DONE`` 이 ⑥ 이 쓰는 표지(``production.factory_done``)를 같은 함수로 읽는다."""
    seed = mixed_order(4, f2=(2, 3))
    _all_done(seed, (2, 3), people["insp2"])  # 2공장 두 장 네 파트 완료, 1공장 두 장은 아무도 안 만짐
    login(client, people["insp2"])
    assert _api(client, seed.id, 2).status_code == 200  # 2공장 제작 완료(마지막 아님)
    sheets = [f["sheet_id"] for f in fresh(seed.id).structured_data["drawing_current_files"]]
    login(client, factory_user("오가람", team="DRAWING"))
    url = f"/api/orders/{seed.id}/drawing/sheet-factory"
    out = client.post(url, json={"items": [{"sheet_id": sheets[2], "factory": 1}]})  # 완료한 공장에서 빼기
    body = out.get_json()
    assert out.status_code == 409 and body["data"]["code"] == "FACTORY_DONE"
    assert body["error"].startswith("2공장은 강검수가 ") and body["error"].endswith("에 제작 완료했어요. 옮기려면 2공장 완료부터 취소해 주세요.")
    into = client.post(url, json={"items": [{"sheet_id": sheets[0], "factory": 2}]})  # 완료한 공장으로 넣기
    assert into.status_code == 409 and into.get_json()["data"]["code"] == "FACTORY_DONE"
    login(client, people["insp2"])
    assert _api(client, seed.id, 2, done=False).status_code == 200  # 2공장 완료 취소
    login(client, factory_user("오나래", team="DRAWING"))
    moved = client.post(url, json={"items": [{"sheet_id": sheets[0], "factory": 2}]})
    assert moved.status_code == 200 and moved.get_json()["data"]["changed"][0]["to"] == 2
    worked = client.post(url, json={"items": [{"sheet_id": sheets[2], "factory": 1}]})  # 일한 장은 여전히 못 옮김(다른 까닭)
    assert worked.status_code == 409 and worked.get_json()["data"]["code"] == "SHEET_HAS_WORK"
