"""작업 시트 회색 [제작 완료] 누름 글 — '도면 없음' 카드 주문은 서버 막힘 글과 같은 글(2026-11-28 ⓑ 검토에서 찾은 어긋남).

'도면 없음' 카드 주문은 확정 도면이 0장이라 공정 자료 ``sheets`` 가 0 이지만, 장은 ``@order`` 한 장이다(``part_progress.sheet_keys``).
서버 막힘 글은 "미완료가 있어요 — 엣지 1장 · …" 인데 시트 JS(``foms-production-sheet-parts.js`` why)는 ``sheets`` 0 만 보고
"도면이 없어요 — 공정 칸을 완료로 처리하거나 …" 를 띄웠다. 되돌리면 실패: 아래 첫 시험의 JS 글이 서버 글과 달라진다.
이름은 모두 지어낸 값이다(김재단).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from db import db_session
from foms.services.production.part_marks_query import order_marks
from foms.services.production.part_progress import complete_block_body, step_api_extras
from models import Order
from tests.support.drawing_fix_transfer_seed import make_order, quiet, team  # noqa: F401 — quiet · team = 픽스처
from tests.support.production_part_claim_seed import ONE, login, make_user

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "static/js/production/foms-production-sheet-parts.js"
NO_DRAWINGS = "도면이 없어요 — 공정 칸을 완료로 처리하거나 관리자에게 말해 주세요."

# 시트 JS 를 가짜 창에서 읽고 why(page) 하나만 부른다 — page 는 data-foms-sheet-parts 를 쥔 자리(작업 시트 루트와 같은 꼴)
NODE = r"""
const fs = require('fs'); const vm = require('vm');
const [file, info] = [process.argv[1], process.argv[2]];
const noop = () => {};
const el = () => ({ hidden: true, classList: { add: noop, remove: noop }, setAttribute: noop, getAttribute: () => null,
  appendChild: noop, addEventListener: noop, querySelector: () => null, querySelectorAll: () => [] });
const document = { addEventListener: noop, removeEventListener: noop, querySelector: () => null, querySelectorAll: () => [],
  createElement: el, body: el(), documentElement: el(), readyState: 'complete' };
const window = { document, addEventListener: noop, removeEventListener: noop };
const ctx = { window, document, console, setTimeout, clearTimeout, CustomEvent: function () {}, JSON };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(file, 'utf8'), ctx);
const page = { hasAttribute: (n) => n === 'data-foms-sheet-parts', getAttribute: () => info, querySelector: () => null };
process.stdout.write(JSON.stringify({ why: window.FomsSheetParts.why(page) }));
"""


def _why(info: dict) -> str | None:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    proc = subprocess.run([node, "-e", NODE, str(JS), json.dumps(info, ensure_ascii=False)],
                          capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)["why"]


def _press(client, who, oid: int, action: str, seen: str) -> None:
    login(client, who)
    resp = client.post(ONE, json={"order_id": oid, "drawing_key": "@order", "part": "cut", "action": action, "seen": seen})
    assert resp.status_code == 200, resp.get_json()


def _state(oid: int):
    db_session.expire_all()
    sd = db_session.get(Order, oid).structured_data
    marks = order_marks(db_session, oid)
    return step_api_extras(sd, marks), (complete_block_body(sd, marks) or {}).get("message")


def test_order_card_order_shows_the_server_left_line_not_no_drawings(client, quiet, team):
    oid = make_order(0)
    kim = make_user("김재단", part="cut")
    _press(client, kim, oid, "take", "none")
    _press(client, kim, oid, "done", "need")
    payload, server = _state(oid)
    assert payload["sheets"] == 0 and payload["parts"]["cut"]["total_n"] == 1  # 확정 도면 0장 · 장은 @order 한 장
    assert server and server.startswith("미완료가 있어요 — ")
    assert _why(payload) == server  # 옛 코드: NO_DRAWINGS


def test_zero_sheet_cards_with_no_sheet_at_all_keep_the_no_drawings_line():
    # 음성 대조군: 카드를 썼다고 적혔지만 장이 하나도 없는 자료(서버는 지금 이 꼴을 안 만든다)면 옛 글 그대로
    parts = {k: {"uses_cards": True, "done": False, "done_n": 0, "total_n": 0, "left_n": 0, "via": None}
             for k in ("cut", "edge", "assemble", "inspect")}
    assert _why({"sheets": 0, "parts": parts}) == NO_DRAWINGS
