"""초안 되찾기 줄의 실제 거동 — node DOM 스텁 (2026-09-11).

소스 계약(`test_erp_order_draft_list.py`)은 "그런 코드가 있다"까지만 본다. 이 화면의
실패 방식은 **조용한 미렌더**다 — 목록은 왔는데 줄이 안 뜨거나, 0건인데 빈 줄이 뜨거나,
링크가 잘못돼 다른 초안을 여는 것. 그래서 실제로 한 번 그려 본다.

node 가 없는 환경에서는 skip 한다(소스 계약이 최소선을 지킨다).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RESUME_JS = ROOT / "static/js/foms/draft_resume.js"

_DOM_STUB = """
function makeNode(tag) {
  return {
    tag: tag,
    className: "",
    href: "",
    textContent: "",
    hidden: false,
    children: [],
    attrs: {},
    listeners: {},
    appendChild: function (child) { this.children.push(child); return child; },
    setAttribute: function (key, value) { this.attrs[key] = value; },
    addEventListener: function (type, fn) { this.listeners[type] = fn; },
  };
}

function textOf(node) {
  if (node.nodeText !== undefined) { return node.nodeText; }
  var own = node.textContent || "";
  return own + node.children.map(textOf).join("");
}

var root = makeNode("div");
root.hidden = true;
var bar = makeNode("button");
var sheet = makeNode("div");
sheet.hidden = true;
var count = makeNode("span");
root.querySelector = function (selector) {
  if (selector === "#foms-draft-resume-bar") { return bar; }
  if (selector === "#foms-draft-resume-sheet") { return sheet; }
  if (selector === ".foms-draft-resume__count") { return count; }
  return null;
};

global.document = {
  readyState: "complete",
  addEventListener: function () {},
  getElementById: function (id) { return id === "foms-draft-resume" ? root : null; },
  createElement: makeNode,
  createTextNode: function (value) { return { nodeText: value, children: [] }; },
};
global.window = {};
"""


def _run(drafts: list[dict]) -> dict:
    harness = textwrap.dedent(
        _DOM_STUB
        + """
        global.fetch = function () {
          return Promise.resolve({
            ok: true,
            json: function () {
              return Promise.resolve({ success: true, data: { drafts: DRAFTS } });
            },
          });
        };

        require(RESUME_JS_PATH);

        setTimeout(function () {
          console.log(JSON.stringify({
            root_hidden: root.hidden,
            sheet_hidden: sheet.hidden,
            count_text: count.textContent,
            rows: sheet.children.map(function (row) {
              return { href: row.href, className: row.className, text: textOf(row) };
            }),
            bar_bound: typeof bar.listeners.click === "function",
          }));
          process.exit(0);
        }, 20);
        """
    ).replace("RESUME_JS_PATH", json.dumps(str(RESUME_JS))).replace(
        "DRAFTS", json.dumps(drafts)
    )

    result = subprocess.run(
        ["node", "-e", harness], capture_output=True, text=True, timeout=60, cwd=str(ROOT)
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")


def test_zero_drafts_draws_nothing() -> None:
    """0건이면 줄 자체가 나타나지 않는다(빈 줄이 홈 상단을 먹으면 안 된다)."""
    out = _run([])
    assert out["root_hidden"] is True
    assert out["rows"] == []
    assert out["count_text"] == ""


def test_rows_render_with_resume_link_and_badge() -> None:
    """행마다 이어쓰기 링크가 붙고, 발송만 하고 등록 안 한 초안에는 배지가 선다."""
    out = _run(
        [
            {
                "draft_key": "new.ff7475d50b3a42ac",
                "step": 4,
                "customer_name": "이광일",
                "address": "서울 중구 동호로14길 35",
                "updated_label": "09-10 10:40",
                "expires_in_days": 6,
                "has_send_history": True,
            },
            {
                "draft_key": "new.quiet",
                "step": 2,
                "customer_name": None,
                "address": None,
                "updated_label": "09-11 08:00",
                "expires_in_days": 0,
                "has_send_history": False,
            },
        ]
    )
    assert out["root_hidden"] is False
    assert out["count_text"] == "작성 중인 주문 2건"
    assert out["bar_bound"] is True, "누를 수 없는 줄은 의미가 없다"

    first, second = out["rows"]
    assert first["href"] == "/add?key=new.ff7475d50b3a42ac&wizard=1&step=4"
    assert "이광일" in first["text"]
    assert "발송함 · 등록 전" in first["text"], "이 배지가 이 화면이 생긴 이유다"
    assert "단계 4/4" in first["text"]
    assert "만료까지 6일" in first["text"]

    assert second["href"] == "/add?key=new.quiet&wizard=1&step=2"
    assert "이름 아직 없음" in second["text"], "초안은 어느 칸이든 비어 있을 수 있다"
    assert "발송함" not in second["text"], "발송 안 한 초안에 배지가 섰다"
    assert "오늘 만료" in second["text"]


def test_out_of_range_step_is_clamped() -> None:
    """망가진 step 이 와도 링크는 1~4 안에 머문다(서버가 그 값을 다시 읽는다)."""
    out = _run(
        [
            {"draft_key": "new.big", "step": 99, "has_send_history": False},
            {"draft_key": "new.zero", "step": 0, "has_send_history": False},
        ]
    )
    hrefs = [row["href"] for row in out["rows"]]
    assert hrefs == [
        "/add?key=new.big&wizard=1&step=4",
        "/add?key=new.zero&wizard=1&step=1",
    ]


def test_sheet_starts_closed_and_toggles() -> None:
    """시트는 닫힌 채로 시작한다 — 줄을 눌러야 열린다."""
    out = _run([{"draft_key": "new.one", "step": 1, "has_send_history": False}])
    assert out["sheet_hidden"] is True
    assert out["bar_bound"] is True
