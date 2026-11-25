"""생산 넘어간 주문의 도면 수정 D2 — 수정본 보내기 규칙(설계서 2026-11-25 §2-3 · §4-1 · §4-2 · §5 C1 · C2 순서).

두 길이 같은 규칙 · 같은 차례다: ``drawing`` = 작업실 [도면 전달]/[수정본 전달] · 마법사 [저장] 창(``transfer-drawing``),
``pending`` = 작업실 일괄 · 태블릿(``drawing-wizard/transfer-pending``). 둘 다 ``perform_drawing_transfer`` 하나를 거친다.

* 생산 · 시공 단계는 도면팀 누구나 보낸다(담당 없음이어도) — 그 밖 단계는 지금 권한 그대로(음성 대조군).
* 차례: 메모(400 ``NOTE_REQUIRED``) → 파일 바꿀 도면(400 ``PICK_TARGET``) → 열린 공장 요청(400 ``FACTORY_REQUEST_OPEN`` —
  [반영 완료] · [요청 반려]된 요청은 열림이 아님) → 지금 검사들 → 작업이 닿은 도면(409 ``WORKED_DRAWING``) · 시공 대기(409
  ``ORDER_MADE``) → 물어본 도면 열쇠 목록(``ack_worked``) · 시공 대기 표지(``ack_order_made``)면 지나감. 거절이면 아무것도 안 쓴다.
* 막힌 도면이 없는 보통 전달은 전과 똑같다(``changed`` 만 더 적힘). 쓰기 쪽(풀림 · 손 처리 · 패킹 · 이어받기 · R1)은
  ``test_drawing_fix_transfer_writes.py``.

되돌리면 실패: 도면팀 비담당 403 · 메모 없이 생산 주문 전달 200 · 고르지 않은 파일 200 · 열린 공장 요청 무시 · 작업된 도면을 묻지 않고
보냄 · 시공 대기 단계가 바뀜. 이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import pytest

from tests.support.drawing_fix_transfer_seed import (  # noqa: F401  quiet · team = 시험 준비물
    key,
    last_transfer as _last_transfer,
    login,
    make_order,
    manual_key,
    names as _names,
    patch,
    put_mark,
    quiet,
    sd_of,
    send,
    team,
)

PATHS = ("drawing", "pending")
AGAIN = "보내면 공장에서 다시 작업해야 합니다."


def _code(res) -> str | None:
    return ((res.get_json() or {}).get("data") or {}).get("code")


# --- 누가 --------------------------------------------------------------------


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("who", ["other", "admin"])
def test_production_anyone_in_drawing_team_sends_even_with_no_assignee(client, quiet, team, path, who):
    oid = make_order(assignees=())   # 담당 없음
    login(client, getattr(team, who))
    res = send(client, path, oid, "s1")
    assert res.status_code == 200, res.get_json()
    sd = sd_of(oid)
    assert sd["drawing_status"] == "CONFIRMED" and _names(sd) == ["s0.png", "s1-v2.png", "s2.png"]
    assert _last_transfer(sd)["by_user_name"] == getattr(team, who).name   # 누가 보냈는지 기록(답 4)


@pytest.mark.parametrize("path", PATHS)
def test_construction_waiting_also_open_to_drawing_team_after_warning(client, quiet, team, path):
    oid = make_order(stage="CONSTRUCTION", assignees=(team.drawer.id,))
    login(client, team.other)
    res = send(client, path, oid, "s1")
    assert res.status_code == 409 and _code(res) == "ORDER_MADE"
    assert res.get_json()["data"]["warnings"] == [{"no": None, "ident": None, "order_made": True, "line": "주문은 시공 대기 그대로예요.",
                                                   "text": "이미 제작 완료된 주문입니다. 보내면 공장에 도면 바뀜 알림이 갑니다."}]
    assert _names(sd_of(oid)) == ["s0.png", "s1.png", "s2.png"]      # 묻는 동안 아무것도 안 씀
    assert send(client, path, oid, "s1", ack_worked=["sheet:s1"]).status_code == 409   # 도면 목록은 시공 대기 확인이 아니다
    res = send(client, path, oid, "s1", ack_order_made=True)
    assert res.status_code == 200, res.get_json()
    sd = sd_of(oid)
    assert sd["workflow"]["stage"] == "CONSTRUCTION" and sd["drawing_status"] == "CONFIRMED"   # 단계 그대로(답 7)


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("stage", ["DRAWING", "CONFIRM"])
def test_negative_control_other_stages_keep_today_rights(client, quiet, team, path, stage):
    oid = make_order(stage=stage, assignees=(team.drawer.id,))
    login(client, team.other)                                          # 담당 아닌 도면팀
    assert send(client, path, oid, "s1").status_code == 403
    none_oid = make_order(stage=stage, assignees=())
    res = send(client, path, none_oid, "s1")
    assert res.status_code == 400 and "도면 담당자가 지정되지 않아" in res.get_json()["message"]
    login(client, team.drawer)                                         # 담당은 메모 없이도 지금처럼 보낸다
    res = send(client, path, oid, "s1", note="")
    assert res.status_code == 200, res.get_json()
    sd = sd_of(oid)
    assert sd["drawing_status"] == "TRANSFERRED"
    assert "changed" not in _last_transfer(sd) and "drawing_fix" not in sd


def test_sales_cannot_send_production_fix(client, quiet, team):
    oid = make_order(assignees=(team.drawer.id,))
    login(client, team.sales)
    assert send(client, "drawing", oid, "s1").status_code == 403
    assert send(client, "pending", oid, "s1").status_code == 403


# --- 메모 · 파일 · 공장 요청 ------------------------------------------------------


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("note", ["", "   "])
def test_memo_is_required_in_production_and_nothing_is_written(client, quiet, team, path, note):
    oid = make_order(assignees=(team.drawer.id,))
    login(client, team.drawer)
    res = send(client, path, oid, "s1", note=note)
    assert res.status_code == 400 and _code(res) == "NOTE_REQUIRED"
    assert res.get_json()["error"] == res.get_json()["message"] == "공장에 남길 메모를 적어 주세요."
    sd = sd_of(oid)
    assert _names(sd) == ["s0.png", "s1.png", "s2.png"] and len(sd["drawing_transfer_history"]) == 2


def test_uploaded_file_must_pick_the_drawing_it_replaces(client, quiet, team):
    oid = make_order(assignees=(team.drawer.id,))
    login(client, team.drawer)
    upload = {"key": manual_key(oid, "new"), "filename": "new.pdf"}
    for pick in (None, "", "orders/999/drawing/x.pdf"):               # 안 고름 · 빈 값 · 지금 도면에 없는 key
        res = send(client, "drawing", oid, manual=[dict(upload, replace_of=pick)])
        assert res.status_code == 400 and _code(res) == "PICK_TARGET", pick
        assert res.get_json()["error"] == "바꿀 도면을 골라 주세요."
    res = send(client, "drawing", oid, manual=[dict(upload, replace_of="NEW")])   # '새 도면'
    assert res.status_code == 200, res.get_json()
    sd = sd_of(oid)
    assert _names(sd) == ["s0.png", "s1.png", "s2.png", "new.pdf"]
    assert _last_transfer(sd)["changed"] == {"replaced": [], "added": [4], "removed": []}


def test_uploaded_file_replaces_the_picked_drawing_in_place(client, quiet, team):
    oid = make_order(assignees=(team.drawer.id,))
    login(client, team.drawer)
    upload = {"key": manual_key(oid, "new"), "filename": "new.pdf", "replace_of": key(oid, "s1")}
    res = send(client, "drawing", oid, manual=[upload])
    assert res.status_code == 200, res.get_json()
    sd = sd_of(oid)
    assert _names(sd) == ["s0.png", "new.pdf", "s2.png"]
    assert _last_transfer(sd)["changed"] == {"replaced": [2], "added": [], "removed": []}


def test_mixed_upload_goes_to_the_picked_drawing_and_other_sheets_keep_their_rule(client, quiet, team):
    """뜻이 바뀐 곳(옛 ``test_drawing_production_hotfix`` 대조): 직접 올린 파일이 섞여도 그 파일은 고른 도면 자리로 가고(§3-5), 다른
    시트는 지금 규칙(한 장뿐인 최종 도면과 다른 시트면 더하기)대로. 전에는 시트 신원을 몰라 한 장을 통째로 바꿨다."""
    oid = make_order(1, assignees=(team.drawer.id,))
    wizard = dict(sd_of(oid)["drawing_wizard"])
    wizard["sheets"] = wizard["sheets"] + [{"id": "s1", "name": "시트1", "form": {}, "objects": []}]
    patch(oid, drawing_wizard=wizard)
    login(client, team.drawer)
    upload = {"key": manual_key(oid, "hand"), "filename": "hand.pdf", "replace_of": key(oid, "s0")}
    res = client.post(f"/api/orders/{oid}/transfer-drawing", json={
        "note": "메모", "files": [{"key": key(oid, "s1-v2"), "filename": "s1-v2.png", "sheet_id": "s1"}, upload]})
    assert res.status_code == 200, res.get_json()
    assert _names(sd_of(oid)) == ["hand.pdf", "s1-v2.png"]


def _requests(state: str, **extra) -> dict:
    return {"requests": [{"id": "fr_1", "from": "factory", "targets": ["sheet:s2"], "numbers": [3], "note": "측판 길이",
                          "factory": 1, "by_name": "박반장", "state": state, **extra}]}


@pytest.mark.parametrize("path", PATHS)
def test_open_factory_request_must_be_handled_first(client, quiet, team, path):
    oid = make_order(assignees=(team.drawer.id,), extra={"drawing_fix": _requests("open")})
    login(client, team.drawer)
    res = send(client, path, oid, "s1")
    assert res.status_code == 400 and _code(res) == "FACTORY_REQUEST_OPEN"
    assert res.get_json()["error"] == "공장 수정 요청을 [반영 완료]나 [요청 반려]로 처리한 뒤에 보낼 수 있어요."
    assert _names(sd_of(oid)) == ["s0.png", "s1.png", "s2.png"]


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("state", ["done", "rejected"])
def test_handled_factory_request_is_not_open_and_transfer_leaves_it_alone(client, quiet, team, path, state):
    oid = make_order(assignees=(team.drawer.id,), extra={"drawing_fix": _requests(state)})
    login(client, team.drawer)
    res = send(client, path, oid, "s2")
    assert res.status_code == 200, res.get_json()
    assert sd_of(oid)["drawing_fix"]["requests"] == _requests(state)["requests"]   # 전달은 요청을 바꾸지 않는다


def test_refusals_come_in_the_spec_order(client, quiet, team):
    """메모 → 파일 → 공장 요청 → 반영 안 한 영업 요청 → 작업이 닿은 도면 → ack."""
    oid = make_order(assignees=(team.drawer.id,), extra={"drawing_fix": _requests("open")})
    put_mark(oid, key(oid, "s1"), "cut", "DONE", sheet_id="s1")
    login(client, team.drawer)
    upload = {"key": manual_key(oid, "new"), "filename": "new.pdf"}
    assert _code(send(client, "drawing", oid, "s1", note="", manual=[upload])) == "NOTE_REQUIRED"
    assert _code(send(client, "drawing", oid, "s1", manual=[upload])) == "PICK_TARGET"
    upload["replace_of"] = "NEW"
    assert _code(send(client, "drawing", oid, "s1", manual=[upload])) == "FACTORY_REQUEST_OPEN"
    sd = sd_of(oid)
    history = sd["drawing_transfer_history"] + [{"action": "REQUEST_REVISION", "note": "손잡이", "files": []}]
    patch(oid, drawing_fix=_requests("open", checked=True), drawing_status="RETURNED", drawing_transfer_history=history)
    res = send(client, "drawing", oid, "s1", manual=[upload])
    assert res.status_code == 400 and "반영 완료" in res.get_json()["message"]
    history[-1]["review_check"] = {"checked": True}
    patch(oid, drawing_transfer_history=history)
    assert _code(send(client, "drawing", oid, "s1", manual=[upload])) == "WORKED_DRAWING"
    res = send(client, "drawing", oid, "s1", manual=[upload], ack_worked=["sheet:s1"])
    assert res.status_code == 200, res.get_json()
    sd = sd_of(oid)
    assert sd["drawing_status"] == "CONFIRMED" and sd["drawing_fix"]["requests"][0]["state"] == "open"   # 안 건드린 도면 3 요청


# --- 보내기 전 확인(409) --------------------------------------------------------


@pytest.mark.parametrize("path", PATHS)
def test_worked_drawings_are_asked_once_with_progress_then_ack_sends(client, quiet, team, path):
    oid = make_order(4, assignees=(team.drawer.id,))
    put_mark(oid, key(oid, "s1"), "cut", "DONE", name="김재단", sheet_id="s1")
    put_mark(oid, key(oid, "s1"), "edge", "NEED", name="박엣지", sheet_id="s1")
    put_mark(oid, key(oid, "s2"), "edge", "NEED", name="박엣지", sheet_id="s2")
    put_mark(oid, key(oid, "s3"), "cut", "BASIC", sheet_id="s3")
    login(client, team.other)
    res = send(client, path, oid, "s1", "s2", "s3")
    assert res.status_code == 409 and _code(res) == "WORKED_DRAWING"
    assert res.get_json()["data"]["warnings"] == [
        {"no": 2, "ident": "sheet:s1", "text": f"도면 2는 재단이 완료된 도면입니다. {AGAIN}", "line": "도면 2 · 재단 완료 · 엣지 작업 중"},
        {"no": 3, "ident": "sheet:s2", "text": f"도면 3은 박엣지가 엣지 작업 중인 도면입니다. {AGAIN}", "line": "도면 3 · 엣지 작업 중"},
        {"no": 4, "ident": "sheet:s3", "text": f"도면 4는 재단이 완료된 도면입니다. {AGAIN}", "line": "도면 4 · 재단 기본"},
    ]
    assert _names(sd_of(oid)) == ["s0.png", "s1.png", "s2.png", "s3.png"]
    res = send(client, path, oid, "s1", "s2", "s3", ack_worked=["sheet:s1", "sheet:s2", "sheet:s3"])
    assert res.status_code == 200, res.get_json()
    assert _names(sd_of(oid)) == ["s0.png", "s1-v2.png", "s2-v2.png", "s3-v2.png"]


@pytest.mark.parametrize("path", PATHS)
def test_untouched_drawing_change_sends_without_asking(client, quiet, team, path):
    oid = make_order(assignees=(team.drawer.id,))
    put_mark(oid, key(oid, "s1"), "cut", "DONE", sheet_id="s1")   # 작업된 도면은 이번에 안 바뀜
    login(client, team.drawer)
    res = send(client, path, oid, "s0")
    assert res.status_code == 200, res.get_json()


def test_factory_made_drawing_counts_as_worked(client, quiet, team):
    oid = make_order(assignees=(team.drawer.id,))
    production = dict(sd_of(oid)["production"])
    production["factory_done"] = {"1": {"keys": [key(oid, f"s{j}") for j in range(3)], "at": "2026-11-24T07:10:00+00:00",
                                        "by_name": "강검수"}}
    patch(oid, production=production)
    login(client, team.drawer)
    res = send(client, "drawing", oid, "s1")
    assert res.status_code == 409 and _code(res) == "WORKED_DRAWING"
    assert res.get_json()["data"]["warnings"][0]["text"] == f"도면 2는 재단 · 엣지 · 조립 · 검수가 완료된 도면입니다. {AGAIN}"


# --- 보통 전달은 전과 똑같이 ---------------------------------------------------------


def test_plain_production_transfer_writes_nothing_new_but_the_changed_numbers(client, quiet, team):
    oid = make_order(assignees=(team.drawer.id,))
    before = sd_of(oid)
    login(client, team.drawer)
    res = send(client, "drawing", oid, "s1")
    assert res.status_code == 200 and res.get_json()["changed"] == {"replaced": [2], "added": [], "removed": []}
    sd = sd_of(oid)
    assert "drawing_fix" not in sd and sd["production"] == before["production"] and "shipment" not in sd
    transfer = _last_transfer(sd)
    assert transfer["hotfix"] is True and transfer["note"] == "상판 깊이 600 → 580"
    assert transfer["mode"] == "REPLACE" and transfer["replace_target_numbers"] == [2]   # 지금 규칙 그대로
