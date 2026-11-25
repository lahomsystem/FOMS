"""생산 넘어간 주문의 도면 수정 D2 — 검토 고침(2026-11-25 지휘 판결 C · D · E · F · G · H · I).

* C 파일은 고른 자리로만 가고 확인 글 = '바뀐 도면' 계산 하나 · 셋째 판 2: 시트는 파일이 같이 가든 말든 지금 자리 규칙 그대로.
* D 두 파일이 같은 도면 · 이번 시트 새 판이 바꾸는 도면을 고르면 400 ``PICK_TARGET`` "바꿀 도면을 골라 주세요."(대조: 다른 도면).
* E 고침 · 빠짐 = 옛 번호(전체 교체에서 "도면 2 (고침) · 도면 2 (빠짐)" 이 안 나옴).
* F 손 처리 칸에 이름이 없으면 완료한 사람을 비워 둔다(보낸 도면팀원 아님) · 시각 = 칸 시각, 없으면 지금(대조: 이름 있는 칸).
* G [반영 완료](``checked``)는 막힘을 안 푼다 — 보낼 수는 있고, 건드린 도면의 요청만 ``done``(대조: 체크 안 한 요청 400).
* N 대상이 여러 장인 요청은 보낸 열쇠만 풀린다(``resolved``) — 막는 열쇠 = ``targets`` − ``resolved``, 모두 풀려야 ``done``.
* 셋째 판 3 · 4 · 5: 이름 빈 옛 이벤트 기록은 전과 같음 · R1 ``sheet_taken``(지운 시트 옛 판 포함) · 관리 시트 막는 까닭 차례.
* H 그 밖 단계 감사 줄에 ``changed`` 칸이 안 붙는다(대조: 생산 단계는 붙음).
* I ``ack_worked`` = 물어본 도면 열쇠 목록 — 빠진 도면이 있으면 그 도면 글로 다시 409, 참 · 거짓은 받지 않는다.
이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import datetime
import re

import pytest

from db import db_session
from foms.services.orders import drawing_fix as fx
from foms.services.orders.drawing_transfer_plan import changed_line, changed_numbers, plan_transfer_files
from models import SecurityLog
from tests.support.drawing_fix_transfer_seed import (  # noqa: F401  quiet · team = 시험 준비물
    STEP_AT,
    key,
    last_transfer,
    login,
    make_order,
    manual_key,
    marks,
    names,
    patch,
    put_mark,
    quiet,
    sd_of,
    send,
    team,
)

PICK_MSG = "바꿀 도면을 골라 주세요."


def _code(res) -> str | None:
    return ((res.get_json() or {}).get("data") or {}).get("code")


def _upload(oid: int, name: str, pick: str) -> dict:
    return {"key": manual_key(oid, name), "filename": f"{name}.pdf", "replace_of": pick}


# --- C · E (순수 계산) ------------------------------------------------------------


def _files(n: int) -> list[dict]:
    return [{"key": f"o/s{j}.png", "sheet_id": f"s{j}"} for j in range(n)]


def _wizard(*ids: int) -> dict:
    return {"drawing_wizard": {"sheets": [{"id": f"s{j}"} for j in ids]}}


def _plan(old, new, sd, picks, **kw):
    opts = {"drawing_status": "CONFIRMED", "hotfix": True, "mode": "", "replace_target_keys": [], "is_retransfer": False, **kw}
    return plan_transfer_files(old, new, sd, picks=picks, **opts)


def test_uploads_go_to_their_pick_and_the_changed_line_is_the_one_calculation():
    old = _files(3)
    plan = _plan(old, [{"key": "o/up.pdf"}], _wizard(0, 1, 2), {"o/up.pdf": "o/s1.png"}, mode="REPLACE",
                 replace_target_keys=["o/s2.png"], is_retransfer=True)
    assert [f["key"] for f in plan.updated_files] == ["o/s0.png", "o/up.pdf", "o/s2.png"]   # 시트가 없으니 교체 대상은 안 쓰임
    assert changed_line(changed_numbers(old, plan.updated_files, plan.pairs)) == "바뀐 도면: 도면 2 (고침)"


@pytest.mark.parametrize("old,wizard,kw", [
    ([{"key": "o/only.pdf"}], (9,), {}),                                         # 한 장뿐인 확정 도면(시트 모름) — 한 장이면 교체
    ([{"key": "o/only.pdf"}], (9,), {"drawing_status": "RETURNED", "is_retransfer": True}),
    (_files(3), (0, 1, 2, 9), {"mode": "REPLACE", "replace_target_keys": ["o/s2.png"], "is_retransfer": True}),   # 교체 대상
    (_files(3), (0, 1, 2, 9), {"mode": "APPEND"}),
])
def test_sheets_keep_their_place_whether_or_not_a_file_goes_along(old, wizard, kw):
    """셋째 판 2: 파일을 같이 보내도 시트 자리 규칙은 그대로 — 옛 도면 + 새 도면이 둘 다 최종이 되는 사고 꼴이 다시 안 생긴다."""
    sheet = {"key": "o/s9.png", "sheet_id": "s9"}
    alone = _plan(old, [sheet], _wizard(*wizard), {}, **kw)
    along = _plan(old, [sheet, {"key": "o/up.pdf"}], _wizard(*wizard), {"o/up.pdf": "NEW"}, **kw)
    assert alone.error is None and along.error is None
    assert [f["key"] for f in along.updated_files] == [f["key"] for f in alone.updated_files] + ["o/up.pdf"]
    if len(old) == 1:
        assert "o/only.pdf" not in [f["key"] for f in along.updated_files]


def test_control_replace_mode_without_uploads_still_uses_targets():
    old = _files(3)
    plan = plan_transfer_files(old, [{"key": "o/s9.png", "sheet_id": "s9"}], _wizard(0, 1, 2, 9), drawing_status="CONFIRMED",
                               hotfix=True, mode="REPLACE", replace_target_keys=["o/s2.png"], is_retransfer=True, picks={})
    assert [f["key"] for f in plan.updated_files] == ["o/s0.png", "o/s1.png", "o/s9.png"]
    assert changed_numbers(old, plan.updated_files, plan.pairs) == {"replaced": [3], "added": [], "removed": []}


def test_replace_all_numbers_never_repeat_replaced_and_removed():
    old = _files(4)
    new = [{"key": f"o/s{j}v2.png", "sheet_id": f"s{j}"} for j in (0, 2, 3)]
    plan = plan_transfer_files(old, new, _wizard(0, 2, 3), drawing_status="CONFIRMED", hotfix=True, mode="REPLACE_ALL",
                               replace_target_keys=[], is_retransfer=False, picks={})
    changed = changed_numbers(old, plan.updated_files, plan.pairs)
    assert changed == {"replaced": [1, 3, 4], "added": [], "removed": [2]}
    assert changed_line(changed) == "바뀐 도면: 도면 1 (고침) · 도면 3 (고침) · 도면 4 (고침) · 도면 2 (빠짐)"


# --- C · D (API) -------------------------------------------------------------------


def test_upload_only_transfer_through_the_api_places_by_the_pick(client, quiet, team):
    oid = make_order(assignees=(team.drawer.id,))
    login(client, team.drawer)
    res = send(client, "drawing", oid, manual=[_upload(oid, "up", key(oid, "s1"))], mode="REPLACE", is_retransfer=True,
               replace_target_keys=[key(oid, "s2")])
    assert res.status_code == 200, res.get_json()
    sd = sd_of(oid)
    assert names(sd) == ["s0.png", "up.pdf", "s2.png"]
    assert last_transfer(sd)["changed"] == {"replaced": [2], "added": [], "removed": []}


@pytest.mark.parametrize("case", ["same_drawing_twice", "sheet_already_replaces_it"])
def test_one_drawing_is_replaced_once_or_pick_target(client, quiet, team, case):
    oid = make_order(assignees=(team.drawer.id,))
    login(client, team.drawer)
    if case == "same_drawing_twice":
        res = send(client, "drawing", oid, manual=[_upload(oid, "a", key(oid, "s1")), _upload(oid, "b", key(oid, "s1"))])
    else:
        res = send(client, "drawing", oid, "s1", manual=[_upload(oid, "a", key(oid, "s1"))])
    assert res.status_code == 400 and _code(res) == "PICK_TARGET" and res.get_json()["error"] == PICK_MSG
    assert names(sd_of(oid)) == ["s0.png", "s1.png", "s2.png"]
    res = send(client, "drawing", oid, "s2", manual=[_upload(oid, "a", key(oid, "s1")), _upload(oid, "b", key(oid, "s0"))])
    assert res.status_code == 200, res.get_json()                      # 대조: 서로 다른 도면
    assert names(sd_of(oid)) == ["b.pdf", "a.pdf", "s2-v2.png"]


# --- F ----------------------------------------------------------------------------


@pytest.mark.parametrize("step_by,step_at", [("", True), ("", False), ("박반장", True)])
def test_hand_step_without_a_name_leaves_the_finisher_empty(client, quiet, team, step_by, step_at):
    oid = make_order(assignees=(team.drawer.id,), steps_done=("cut",), step_by=step_by)
    if not step_at:
        steps = sd_of(oid)["production"]
        steps["steps"][0]["at"] = None
        patch(oid, production=steps)
    login(client, team.drawer)
    before = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(seconds=5)
    assert send(client, "drawing", oid, "s1", ack_worked=["sheet:s1"]).status_code == 200
    row = marks(oid)[(key(oid, "s0"), "cut")]
    assert row.done_by_name == (step_by or None) and row.done_by_user_id is None   # 보낸 도면팀원(김도면)이 아님
    if step_at:
        assert row.done_at == datetime.datetime.fromisoformat(STEP_AT).replace(tzinfo=None)
    else:
        assert row.done_at >= before                                    # 칸 시각이 없으면 지금
    login(client, team.admin)
    items = client.get(f"/api/production/part-history?order_id={oid}&key={key(oid, 's0')}").get_json()["data"]["items"]
    assert [i["by_name"] for i in items] == [step_by or None]
    page = client.get(f"/erp/production/sheet/{oid}")
    body = page.get_data(as_text=True).split("<body", 1)[-1]
    # 낱말로 선 None 만 본다 — 같은 워커의 다른 시험이 만든 계정 이름("ADMIN-None-4")이 머리 메뉴에 섞여 나올 수 있다
    assert page.status_code == 200 and not re.search(r"(?<![\w-])None(?![\w-])", body)


def test_history_of_an_old_step_event_by_a_nameless_account_is_as_before(client, quiet, team):
    """셋째 판 3 대조: 이름이 빈 계정이 공정 칸을 누른 옛 이벤트는 지금처럼 사용자 표 이름(로그인 아이디)으로 보인다."""
    from tests.support.production_part_claim_seed import check_step, make_order as prod_order, make_user as prod_user
    seed = prod_order(2)
    lead = prod_user("", lead=True)
    login(client, lead)
    assert check_step(client, seed.id, "cut", True).status_code == 200
    login(client, team.admin)
    items = client.get(f"/api/production/part-history?order_id={seed.id}&part=cut").get_json()["data"]["items"]
    assert [(i["kind"], i["by_name"]) for i in items] == [("step_on", lead.username)]


def test_preview_lists_drawings_this_transfers_sheets_take(client, quiet, team):
    """셋째 판 4: R1 ``sheet_taken`` = 이번 시트가 바꾸는 도면 + 마법사에서 지운 시트의 옛 판 — 파일 고르기 단추가 끈다."""
    oid = make_order(assignees=(team.drawer.id,))
    wizard = dict(sd_of(oid)["drawing_wizard"])
    wizard["sheets"] = [s for s in wizard["sheets"] if s["id"] != "s2"]
    patch(oid, drawing_wizard=wizard)
    login(client, team.drawer)
    plan = client.get(f"/api/orders/{oid}/drawing/fix/progress?sheet=s1&mode=APPEND").get_json()["data"]["plan"]
    assert sorted(plan["sheet_taken"]) == sorted([key(oid, "s1"), key(oid, "s2")])
    res = send(client, "drawing", oid, "s1", manual=[_upload(oid, "a", key(oid, "s2"))])
    assert res.status_code == 400 and _code(res) == "PICK_TARGET"          # 그래도 고르면 서버가 막는다


def test_tablet_sheet_reason_order_is_the_servers(client, quiet, team):
    """셋째 판 5: 공장 요청과 반영 안 한 영업 요청이 둘 다 있으면 서버처럼 공장 요청 까닭이 먼저."""
    from tests.support.drawing_fix_transfer_seed import seed_pending
    history = [{"action": "TRANSFER", "files": []}, {"action": "REQUEST_REVISION", "note": "손잡이", "files": []}]
    oid = make_order(assignees=(team.drawer.id,), extra={"drawing_status": "RETURNED", "drawing_transfer_history": history,
                                                         "drawing_fix": {"requests": [_request("fr_1", "sheet:s2")]}})
    seed_pending(oid, "s1")
    login(client, team.drawer)
    page = client.get(f"/erp/drawing-workbench/tablet-sheet/{oid}").get_data(as_text=True)
    assert "공장 수정 요청을 [반영 완료]나 [요청 반려]로 처리한 뒤에 보낼 수 있어요." in page
    assert _code(send(client, "drawing", oid, "s1")) == "FACTORY_REQUEST_OPEN"


# --- G ----------------------------------------------------------------------------


def _request(rid: str, target: str, **extra) -> dict:
    return {"id": rid, "from": "factory", "targets": [target], "numbers": [int(target[-1]) + 1], "note": "측판", "factory": 1,
            "by_name": "박반장", "state": "open", **extra}


def test_checked_factory_request_lets_the_fix_go_and_only_the_touched_one_closes(client, quiet, team):
    checked = {"checked": True, "checked_by_name": "오도면", "checked_at": "2026-11-25T06:00:00+00:00"}
    oid = make_order(assignees=(team.drawer.id,), extra={"drawing_fix": {"requests": [
        _request("fr_1", "sheet:s1", **checked), _request("fr_2", "sheet:s2", **checked)]}})
    assert fx.blocked(sd_of(oid)).idents == frozenset({"sheet:s1", "sheet:s2"})   # [반영 완료]여도 막힌 채
    login(client, team.drawer)
    progress = client.get(f"/api/orders/{oid}/drawing/fix/progress").get_json()["data"]["drawings"]
    assert progress[1]["requests"] == [{"id": "fr_1", "from": "factory", "checked": True, "left": ["sheet:s1"]}]
    assert send(client, "drawing", oid, "s1").status_code == 200
    sd = sd_of(oid)
    first, second = sd["drawing_fix"]["requests"]
    assert first["state"] == "done" and first["done_at"] and first["checked"] is True
    assert second["state"] == "open"                                   # 안 건드린 도면 3 은 열린 채
    assert fx.blocked(sd).idents == frozenset({"sheet:s2"})


def test_request_on_two_drawings_frees_only_the_sent_one_until_both_are_sent(client, quiet, team):
    request = _request("fr_9", "sheet:s1", checked=True)
    request.update(targets=["sheet:s1", "sheet:s2"], numbers=[2, 3])
    oid = make_order(assignees=(team.drawer.id,), extra={"drawing_fix": {"requests": [request]}})
    login(client, team.drawer)
    assert send(client, "drawing", oid, "s1").status_code == 200       # 도면 2 만 고쳐 보냄
    sd = sd_of(oid)
    row = sd["drawing_fix"]["requests"][0]
    assert (row["state"], row["resolved"], row["checked"]) == ("open", ["sheet:s1"], True)
    assert fx.blocked(sd).idents == frozenset({"sheet:s2"}) and fx.open_request_idents(sd) == frozenset({"sheet:s2"})
    progress = client.get(f"/api/orders/{oid}/drawing/fix/progress").get_json()["data"]["drawings"]
    assert progress[1]["requests"] == [] and progress[2]["requests"][0]["left"] == ["sheet:s2"]
    assert sd["drawing_fix"]["log"][-1]["idents"] == ["sheet:s1"] and sd["drawing_fix"]["log"][-1]["closed"] == []
    assert send(client, "drawing", oid, "s2").status_code == 200       # 남은 도면 3 을 보냄 → 닫힘
    sd = sd_of(oid)
    row = sd["drawing_fix"]["requests"][0]
    assert (row["state"], row["resolved"]) == ("done", ["sheet:s1", "sheet:s2"]) and row["done_at"]
    assert fx.blocked(sd).idents == frozenset() and sd["drawing_fix"]["log"][-1]["closed"] == ["fr_9"]


def test_control_one_drawing_request_closes_at_once(client, quiet, team):
    oid = make_order(assignees=(team.drawer.id,), extra={"drawing_fix": {"requests": [_request("fr_1", "sheet:s1", checked=True)]}})
    login(client, team.drawer)
    assert send(client, "drawing", oid, "s1").status_code == 200
    row = sd_of(oid)["drawing_fix"]["requests"][0]
    assert (row["state"], row["resolved"]) == ("done", ["sheet:s1"]) and fx.blocked(sd_of(oid)).idents == frozenset()


def test_control_unchecked_open_request_still_stops_the_fix(client, quiet, team):
    oid = make_order(assignees=(team.drawer.id,), extra={"drawing_fix": {"requests": [
        _request("fr_1", "sheet:s1", checked=True), _request("fr_2", "sheet:s2", checked=False)]}})
    login(client, team.drawer)
    res = send(client, "drawing", oid, "s1")
    assert res.status_code == 400 and _code(res) == "FACTORY_REQUEST_OPEN"
    assert [r["state"] for r in sd_of(oid)["drawing_fix"]["requests"]] == ["open", "open"]


# --- H ----------------------------------------------------------------------------


@pytest.mark.parametrize("stage,has_changed", [("DRAWING", False), ("PRODUCTION", True)])
def test_audit_detail_gains_changed_only_in_production_stages(client, quiet, team, stage, has_changed):
    oid = make_order(stage=stage, assignees=(team.drawer.id,))
    login(client, team.drawer)
    assert send(client, "drawing", oid, "s1").status_code == 200
    db_session.expire_all()
    log = db_session.query(SecurityLog).filter_by(target_id=oid, action="DRAWING_DELIVERED").order_by(SecurityLog.id).all()[-1]
    assert ("changed" in (log.detail or {})) is has_changed


# --- I ----------------------------------------------------------------------------


def test_ack_lists_only_the_asked_drawings_and_missing_ones_are_asked_again(client, quiet, team):
    oid = make_order(assignees=(team.drawer.id,))
    put_mark(oid, key(oid, "s1"), "cut", "DONE", sheet_id="s1")
    put_mark(oid, key(oid, "s2"), "edge", "NEED", name="박엣지", sheet_id="s2")
    login(client, team.drawer)
    res = send(client, "drawing", oid, "s1", "s2", ack_worked=["sheet:s1"])      # 저장 전 예측으로 도면 2 만 물음
    assert res.status_code == 409 and _code(res) == "WORKED_DRAWING"
    assert [w["ident"] for w in res.get_json()["data"]["warnings"]] == ["sheet:s2"]   # 빠진 도면 글만
    assert send(client, "drawing", oid, "s1", "s2", ack_worked=True).status_code == 409   # 참 · 거짓은 받지 않음
    assert send(client, "drawing", oid, "s1", "s2", ack_worked=["sheet:s1", "sheet:s2"]).status_code == 200
    assert names(sd_of(oid)) == ["s0.png", "s1-v2.png", "s2-v2.png"]
