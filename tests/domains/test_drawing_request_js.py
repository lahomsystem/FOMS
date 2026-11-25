"""생산 넘어간 주문의 도면 수정 D4 — 새 JS 둘을 서버가 그린 진짜 화면 위에서 node 로 실제로 돌린다(설계서 2026-11-25 §2-2 · §2-4 · §10).

* ``foms-production-drawing-request.js``(태블릿 도면 판 [도면 수정 요청] 창): 누른 장이 미리 골라짐 · 고르기는 그 사람 몫(파트 계정 =
  자기 공장 장) · 사유 빈 글 · 도면 0장은 보내지 않고 창 안 글 · 사진 4장은 "3장까지" · 고른 사진은 바로 올림(올리는 동안 [요청 보내기]
  꺼짐) · 같은 몸으로 다시 누르면 같은 ``Idempotency-Key``, 몸이 바뀌면 새 열쇠 · 서버 거절 · 끊김은 창 안 글(창 그대로) · 되면 창 닫힘 ·
  "도면팀에 수정 요청을 보냈어요." · 보낸 도면 카드만 '도면 고치는 중'(서버가 준 막힌 칸) · 그 카드 [도면 수정 요청] 숨김.
* ``workbench-factory-request.js``(작업실 요청사항 칸): [반영 완료] = POST check · 서버 거절은 칸 아래 글 · 되면 다시 읽기. [요청 반려] = 창
  "요청 반려" · 서버 글 본문 · [취소] [요청 반려] · 사유 빈 글이면 보내지 않고 "반려 사유를 적어 주세요." · 거절은 창 안 글(단추 다시 켜짐).

되돌리면 실패: 사유 없이 보냄 · 열쇠가 누를 때마다 바뀜(두 번 눌러 두 건) · 다른 주문 · 다른 장 카드가 막힘 · 반려 사유 없이 보냄.
이름은 모두 지어낸 값이다(서버 답은 가짜).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from db import db_session
from models import Order
from tests.support.drawing_fix_workbench_seed import day, login as wb_login, make_order as wb_order, people
from tests.support.production_factory_seed import TABLET, factory_user, mixed_order, set_cookies
from tests.support.production_part_claim_seed import login

ROOT = Path(__file__).resolve().parents[2]
BOARD_CHECK = ROOT / "tests/support/production_drawing_request_node_checks.js"
WB_CHECK = ROOT / "tests/support/workbench_factory_request_node_checks.js"
REVISING = "도면을 고치는 중이라 지금은 못 눌러요. 새 도면이 오면 다시 돼요."


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _node(script: Path, page: Path, want: dict) -> dict:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    proc = subprocess.run([node, str(script), str(page), json.dumps(want, ensure_ascii=False)], capture_output=True, text=True,
                          encoding="utf-8", timeout=60, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_board_request_dialog_end_to_end(client, cohort, tmp_path):
    seed = mixed_order(4, f2=(3,))                                  # 도면 4 = 2공장(파트 계정 고르기에 없다)
    part = factory_user("최엣지", part="edge")
    login(client, part)
    set_cookies(client, TABLET)
    page = tmp_path / "board.html"
    page.write_text(client.get("/erp/production/home?day=none").get_data(as_text=True), encoding="utf-8")
    sids = [f["sheet_id"] for f in db_session.get(Order, seed.id).structured_data["drawing_current_files"]]
    block = {"kind": "revise", "text": "도면 고치는 중", "why": REVISING}
    ok = {"success": True, "data": {"keys": [seed.keys[0], seed.keys[1]], "block": block, "request": {"id": "fr_x"}}}
    refused = {"success": False, "data": {"code": "REQUEST_FORBIDDEN"}, "error": "도면 수정 요청은 반장이나 그 도면 파트 담당만 할 수 있어요."}
    photo = lambda n: {"success": True, "data": {"file": {"key": f"orders/{seed.id}/drawing_gateway/revisions/{n}", "filename": n}}}
    out = _node(BOARD_CHECK, page, {"oid": seed.id, "card_no": 2, "posts": [refused, "offline", ok],
                                    "uploads": [photo("a.jpg"), photo("b.jpg")]})
    assert out["opened"] is True and out["who"].endswith(f"#{seed.id}")
    assert out["picks"] == [["도면 1", "false"], ["도면 2", "true"], ["도면 3", "false"]]   # 누른 장 미리 · 자기 공장 장만
    assert out["noNote"] == "사유를 적어 주세요." and out["noPick"] == "수정할 도면을 골라 주세요." and out["callsBeforePick"] == 0
    assert out["tooMany"] == "사진은 3장까지 올릴 수 있어요." and out["sendDisabledWhileUploading"] is True
    assert out["thumbs"] == 2 and len(out["uploadCalls"]) == 2
    assert out["refused"] == refused["error"] and out["stillOpen"] is True
    assert out["offline"] == "연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요."
    assert out["keys"][0] == out["keys"][1] != out["keys"][2]                              # 같은 몸 = 같은 열쇠
    assert out["lastBody"] == {"targets": [{"sheet_id": sids[0]}], "note": "측판 길이가 실측과 달라요(고침)",
                               "photos": [{"key": f"orders/{seed.id}/drawing_gateway/revisions/a.jpg", "filename": "a.jpg"},
                                          {"key": f"orders/{seed.id}/drawing_gateway/revisions/b.jpg", "filename": "b.jpg"}]}
    assert out["closed"] is True and out["status"] == "도면팀에 수정 요청을 보냈어요."
    assert out["blocked"] == ["1", "2"] and set(out["blockWhy"]) == {REVISING} and out["rendered"] == [seed.keys[0], seed.keys[1]]
    assert out["hiddenReq"] == ["1", "2"]                                                  # 남은 장(도면 3)은 단추 그대로


def test_workbench_check_and_reject_dialog(client, tmp_path):
    who = people()
    request = {"id": "fr_w1", "from": "factory", "targets": ["sheet:s1"], "numbers": [2], "note": "측판", "photos": [],
               "factory": 1, "by_user_id": who.lead.id, "by_name": "박반장", "at": "2026-11-25T04:40:00Z", "state": "open",
               "checked": False, "resolved": []}
    oid = wb_order(3, cdate=day(3), extra={"drawing_fix": {"requests": [request]}})
    wb_login(client, who.staff)
    html = client.get(f"/erp/drawing-workbench/{oid}").get_data(as_text=True)
    start = html.index('<div class="dfr" data-dfr')
    page = tmp_path / "requests.html"
    page.write_text(html[start:html.index('<p class="dwp-err" data-dfr-error', start)] + '<p data-dfr-error hidden></p></div>',
                    encoding="utf-8")
    fail = {"success": False, "error": "이미 처리된 요청이에요. 화면을 다시 열어 주세요."}
    out = _node(WB_CHECK, page, {"posts": [fail, fail, {"success": True}, {"success": True}]})
    assert out["checkError"] == fail["error"]
    assert out["dialogOpen"] is True
    assert out["dialogText"] == "요청 반려|반려 사유를 적어 주세요. 요청한 사람에게 알림이 가고, 도면 2 막힘이 풀려요."
    assert out["buttons"] == ["취소", "요청 반려"]
    assert out["emptyNote"] == "반려 사유를 적어 주세요." and out["callsAfterEmpty"] == 0
    assert out["rejectError"] == fail["error"] and out["reenabled"] is True
    assert out["reloadsAfterReject"] == 1 and out["reloads"] == 2
    assert [(c["url"], c["body"]) for c in out["calls"]] == [
        (f"/api/orders/{oid}/drawing/fix/requests/fr_w1/check", {"checked": True}),
        (f"/api/orders/{oid}/drawing/fix/requests/fr_w1/reject", {"note": "실측과 같아요"}),
        (f"/api/orders/{oid}/drawing/fix/requests/fr_w1/reject", {"note": "실측과 같아요"}),
        (f"/api/orders/{oid}/drawing/fix/requests/fr_w1/check", {"checked": True}),
    ]
