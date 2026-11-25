"""생산 넘어간 주문의 도면 수정 D2 — 보내는 창 JS 를 node 로 실제로 돌린다(2026-11-25 지휘 판결 A · B · D · I · J · K).

* ``drawing-fix-send.js``: 확인은 한 번(경고 → 창 · 없으면 '바뀐 도면' 줄 확인 글) · R1 을 못 받으면 옛 확인 없이 서버 409 한 번(J) ·
  409 를 받으면 빠진 도면만 묻고 물어본 열쇠를 더해 다시 보냄 · 취소면 한 번만 보냄 · 시공 대기 표지(I).
* ``workbench-transfer-fix.js``: 고름은 파일마다(가운데 파일을 빼도 남은 고름이 제 파일에 — A) · 다른 파일이 고른 도면 · 고른 대기
  시트가 바꾸는 도면은 단추 꺼짐(D) · 창을 다시 열거나 주문이 바뀌면 비움(B).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SEND_JS = ROOT / "static/js/drawing/drawing-fix-send.js"
WB_JS = ROOT / "static/js/drawing/workbench-transfer-fix.js"
PICKS_JS = ROOT / "static/js/drawing/drawing-fix-picks.js"
HOTFIX = "생산·시공 단계라 영업 확인 없이 바로 최종 도면이 되고 생산팀에 알림이 갑니다. 전달 취소로 되돌릴 수 없습니다."


def _node(*args: str, stdin: str = "") -> dict:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    proc = subprocess.run([node, *args], input=stdin, capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _send(scenario: dict) -> dict:
    return _node(str(ROOT / "tests/domains/drawing_fix_send_runner.js"), str(SEND_JS), stdin=json.dumps(scenario))


def _wb(scenario: str) -> dict:
    return _node(str(ROOT / "tests/domains/workbench_transfer_fix_runner.js"), str(WB_JS), scenario, str(PICKS_JS))


# --- drawing-fix-send.js ----------------------------------------------------------


def test_gate_with_warnings_asks_once_and_acks_only_the_asked_drawings():
    out = _send({"action": "gate", "answers": [True], "plan": {"changed_line": "바뀐 도면: 도면 2 (고침)", "warnings": [
        {"ident": "sheet:s1", "text": "도면 2는 재단이 완료된 도면입니다.", "line": "도면 2 · 재단 완료"}]}})
    assert out["result"] == {"ok": True, "ack": {"idents": ["sheet:s1"], "orderMade": False}}
    assert len(out["dialogs"]) == 1 and out["confirms"] == []
    assert out["dialogs"][0].startswith("보내기 전 확인\n도면 2는 재단이 완료된 도면입니다.\n도면 2 · 재단 완료\n" + HOTFIX)


def test_gate_without_warnings_confirms_the_changed_line_only():
    out = _send({"action": "gate", "plan": {"changed_line": "바뀐 도면: 도면 3 (고침)", "warnings": []}})
    assert out["confirms"] == [f"바뀐 도면: 도면 3 (고침)\n\n{HOTFIX}"] and out["dialogs"] == []
    assert out["result"]["ack"] == {"idents": [], "orderMade": False}


@pytest.mark.parametrize("answer", [True, False])
def test_gate_without_preview_asks_the_old_confirm_once(answer):
    """셋째 판 1: R1 을 못 받으면(통신 · 5xx · JSON 아님) 지금 확인 글로 한 번 묻는다 — 확인 없이 최종 도면이 되는 길을 없앤다."""
    out = _send({"action": "gate", "plan": None, "confirm": answer, "oldText": "도면 2장을 전달합니다. 진행할까요?"})
    assert out["confirms"] == ["도면 2장을 전달합니다. 진행할까요?"] and out["dialogs"] == []
    assert out["result"] == {"ok": answer, "ack": {"idents": [], "orderMade": False}}


def test_gate_with_a_refused_plan_leaves_it_to_the_server():
    out = _send({"action": "gate", "plan": {"error": "바꿀 도면을 골라 주세요.", "warnings": []}})
    assert out["result"] == {"ok": True, "ack": {"idents": [], "orderMade": False}}
    assert out["confirms"] == [] and out["dialogs"] == []


def _worked(*idents: str) -> dict:
    return {"success": False, "error": "작업된 도면", "data": {"code": "WORKED_DRAWING", "warnings": [
        {"ident": i, "text": f"{i} 글", "line": ""} for i in idents]}}


def test_post_asks_only_the_missing_drawing_and_resends_with_the_merged_list():
    out = _send({"action": "post", "answers": [True], "body": {"note": "메모", "ack_worked": ["sheet:s1"]},
                 "posts": [_worked("sheet:s2"), {"success": True}]})
    bodies = [c["body"] for c in out["calls"]]
    assert [b["ack_worked"] for b in bodies] == [["sheet:s1"], ["sheet:s1", "sheet:s2"]]
    assert len(out["dialogs"]) == 1 and "sheet:s2 글" in out["dialogs"][0] and out["result"] == {"success": True}


def test_post_cancel_sends_once_and_says_cancelled():
    out = _send({"action": "post", "answers": [False], "body": {"note": "메모", "ack_worked": []}, "posts": [_worked("sheet:s1")]})
    assert len(out["calls"]) == 1 and out["result"]["cancelled"] is True


def test_post_order_made_resends_with_the_construction_flag():
    order_made = {"success": False, "error": "이미", "data": {"code": "ORDER_MADE", "warnings": [
        {"ident": None, "order_made": True, "text": "이미 제작 완료된 주문입니다. 보내면 공장에 도면 바뀜 알림이 갑니다."}]}}
    out = _send({"action": "post", "answers": [True], "body": {"note": "메모", "ack_worked": []}, "posts": [order_made, {"success": True}]})
    assert out["calls"][1]["body"]["ack_order_made"] is True and out["calls"][1]["body"]["ack_worked"] == []


def test_post_plain_refusal_is_not_asked():
    out = _send({"action": "post", "body": {"note": ""}, "posts": [{"success": False, "data": {"code": "NOTE_REQUIRED"}}]})
    assert len(out["calls"]) == 1 and out["dialogs"] == []


# --- workbench-transfer-fix.js -------------------------------------------------------


def test_removing_the_middle_file_keeps_each_pick_on_its_own_file():
    out = _wb("remove")
    picked, removed = out["steps"]
    assert [r["name"] for r in picked["view"]] == ["a.pdf", "b.pdf", "c.pdf"]
    assert removed["view"] == [{"name": "a.pdf", "chips": ["도면 1*", "도면 2", "도면 3", "새 도면"]},
                               {"name": "c.pdf", "chips": ["도면 1(off)", "도면 2", "도면 3", "새 도면*"]}]
    assert removed["check"] == ""
    assert [f["replace_of"] for f in out["attached"]] == ["k/d1.png", "NEW"]   # 빠진 b 의 '도면 2'가 c 로 밀리지 않음
    assert out["lastPreview"]["picks"] == ["k/d1.png", "NEW"]               # '바뀐 도면' 줄도 따라감
    assert out["confirm"]["text"] == "L\n\nH"                               # 확인 글 = '바뀐 도면' 줄 + 생산 확인 글


def test_a_drawing_taken_by_another_file_or_a_waiting_sheet_is_switched_off():
    one, tried = _wb("same")["steps"]
    assert one["view"][0]["chips"] == ["도면 1*", "도면 2(off)", "도면 3", "새 도면"]       # 도면 2 = 대기 시트 s2 새 판
    assert one["view"][1]["chips"] == ["도면 1(off)", "도면 2(off)", "도면 3", "새 도면"]   # 도면 1 = a 가 고름
    assert tried["check"] == "바꿀 도면을 골라 주세요."                                   # 꺼진 단추는 안 골라짐


def test_a_drawing_the_sheets_take_is_switched_off_after_the_preview():
    """셋째 판 4: 미리 보기의 sheet_taken(지운 시트의 옛 판 등)은 단추를 끄고, 이미 고른 값도 지운다."""
    before, after = _wb("dropped")["steps"]
    assert before["view"][0]["chips"] == ["도면 1", "도면 2", "도면 3*", "새 도면"]
    assert after["view"][0]["chips"] == ["도면 1", "도면 2", "도면 3(off)", "새 도면"] and after["check"] == "바꿀 도면을 골라 주세요."


def test_reopening_the_window_or_another_order_clears_the_picks():
    picked, reopened, other = _wb("reopen")["steps"]
    assert picked["check"] == ""
    assert all("*" not in chip for row in reopened["view"] for chip in row["chips"])
    assert reopened["check"] == "바꿀 도면을 골라 주세요."
    assert other["check"] == "바꿀 도면을 골라 주세요." and other["noteCheck"] == "공장에 남길 메모를 적어 주세요."
