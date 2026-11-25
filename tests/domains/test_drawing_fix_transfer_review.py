"""생산 넘어간 주문의 도면 수정 D2 — 검토 고침(2026-11-25 지휘 판결 C · D · E · F · G · H · I).

* C 파일마다 고르는 전달은 전달 모드의 '교체 대상'을 쓰지 않는다 — 서버 계획 · 미리 보기 줄이 같은 계산(대조: 파일 없는 교체 모드).
* D 두 파일이 같은 도면 · 이번 시트 새 판이 바꾸는 도면을 고르면 400 ``PICK_TARGET`` "바꿀 도면을 골라 주세요."(대조: 다른 도면).
* E 고침 · 빠짐 = 옛 번호(전체 교체에서 "도면 2 (고침) · 도면 2 (빠짐)" 이 안 나옴).
* F 손 처리 칸에 이름이 없으면 완료한 사람을 비워 둔다(보낸 도면팀원 아님) · 시각 = 칸 시각, 없으면 지금(대조: 이름 있는 칸).
* G [반영 완료](``checked``)는 막힘을 안 푼다 — 보낼 수는 있고, 건드린 도면의 요청만 ``done``(대조: 체크 안 한 요청 400).
* H 그 밖 단계 감사 줄에 ``changed`` 칸이 안 붙는다(대조: 생산 단계는 붙음).
* I ``ack_worked`` = 물어본 도면 열쇠 목록 — 빠진 도면이 있으면 그 도면 글로 다시 409, 참 · 거짓은 받지 않는다.
이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import datetime

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


def test_pick_transfer_ignores_replace_targets_and_says_only_the_changed_line():
    old = _files(3)
    plan = plan_transfer_files(old, [{"key": "o/up.pdf"}], _wizard(0, 1, 2), drawing_status="CONFIRMED", hotfix=True,
                               mode="REPLACE", replace_target_keys=["o/s2.png"], is_retransfer=True,
                               picks={"o/up.pdf": "o/s1.png"})
    assert [f["key"] for f in plan.updated_files] == ["o/s0.png", "o/up.pdf", "o/s2.png"] and plan.replace_target_keys == []
    assert changed_line(changed_numbers(old, plan.updated_files, plan.pairs)) == "바뀐 도면: 도면 2 (고침)"
    new_sheet = plan_transfer_files(old, [{"key": "o/s9.png", "sheet_id": "s9"}, {"key": "o/up.pdf"}], _wizard(0, 1, 2, 9),
                                    drawing_status="CONFIRMED", hotfix=True, mode="REPLACE", replace_target_keys=["o/s2.png"],
                                    is_retransfer=True, picks={"o/up.pdf": "NEW"})
    assert [f["key"] for f in new_sheet.updated_files] == ["o/s0.png", "o/s1.png", "o/s2.png", "o/s9.png", "o/up.pdf"]


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


def test_pick_transfer_through_the_api_keeps_targets_out_of_the_history(client, quiet, team):
    oid = make_order(assignees=(team.drawer.id,))
    login(client, team.drawer)
    res = send(client, "drawing", oid, manual=[_upload(oid, "up", key(oid, "s1"))], mode="REPLACE", is_retransfer=True,
               replace_target_keys=[key(oid, "s2")])
    assert res.status_code == 200, res.get_json()
    sd = sd_of(oid)
    assert names(sd) == ["s0.png", "up.pdf", "s2.png"]
    transfer = last_transfer(sd)
    assert transfer["replace_target_keys"] is None and transfer["changed"] == {"replaced": [2], "added": [], "removed": []}


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
    assert page.status_code == 200 and "None" not in page.get_data(as_text=True).split("<body", 1)[-1]


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
    assert progress[1]["requests"] == [{"id": "fr_1", "from": "factory", "checked": True}]
    assert send(client, "drawing", oid, "s1").status_code == 200
    sd = sd_of(oid)
    first, second = sd["drawing_fix"]["requests"]
    assert first["state"] == "done" and first["done_at"] and first["checked"] is True
    assert second["state"] == "open"                                   # 안 건드린 도면 3 은 열린 채
    assert fx.blocked(sd).idents == frozenset({"sheet:s2"})


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
