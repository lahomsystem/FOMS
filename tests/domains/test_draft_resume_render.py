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
    type: "",
    disabled: false,
    textContent: "",
    hidden: false,
    children: [],
    attrs: {},
    listeners: {},
    appendChild: function (child) { this.children.push(child); return child; },
    removeChild: function (child) {
      var index = this.children.indexOf(child);
      if (index >= 0) { this.children.splice(index, 1); }
      return child;
    },
    setAttribute: function (key, value) { this.attrs[key] = value; },
    removeAttribute: function (key) { delete this.attrs[key]; },
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

// 삭제 경로가 쓰는 브라우저 전역 3종. 실제로 무엇이 불렸는지 기록해 단언한다.
global.__toasts = [];
global.__confirms = [];
global.__calls = [];
global.window = {
  confirm: function (message) { global.__confirms.push(message); return CONFIRM_ANSWER; },
  alert: function (message) { global.__toasts.push(message); },
  fomsShowToast: function (message) { global.__toasts.push(message); },
};

// 행 래퍼 안의 구조를 그대로 읽는다: [0] 이어쓰기 링크 <a>, [1] 지우기 <button>.
function snapshot() {
  return {
    root_hidden: root.hidden,
    sheet_hidden: sheet.hidden,
    count_text: count.textContent,
    rows: sheet.children.map(function (item) {
      var link = item.children[0] || {};
      var del = item.children[1] || {};
      return {
        href: link.href || "",
        className: link.className || "",
        item_class: item.className,
        key: item.attrs["data-draft-key"],
        text: textOf(item),
        delete_label: del.attrs ? del.attrs["aria-label"] : null,
        delete_bound: !!(del.listeners && typeof del.listeners.click === "function"),
        delete_disabled: del.disabled === true,
      };
    }),
    bar_bound: typeof bar.listeners.click === "function",
    calls: global.__calls,
    toasts: global.__toasts,
    confirms: global.__confirms,
    event: global.__event,
  };
}
"""


def _run(
    drafts: list[dict],
    click_index: int = -1,
    confirm: bool = True,
    delete_payload: dict | None = None,
    click_times: int = 1,
) -> dict:
    """목록을 그린 뒤(before) 지정한 행의 지우기 버튼을 눌러 본다(after)."""
    harness = textwrap.dedent(
        _DOM_STUB
        + """
        global.fetch = function (url, opts) {
          var method = (opts && opts.method) || "GET";
          global.__calls.push({ url: url, method: method });
          var payload = method === "DELETE"
            ? DELETE_PAYLOAD
            : { success: true, data: { drafts: DRAFTS } };
          return Promise.resolve({
            ok: true,
            json: function () { return Promise.resolve(payload); },
          });
        };

        require(RESUME_JS_PATH);

        setTimeout(function () {
          var before = snapshot();
          var target = sheet.children[CLICK_INDEX];
          if (CLICK_INDEX >= 0 && target) {
            // 삭제 탭이 이어쓰기 링크·띠 토글로 새면 안 된다 — 둘 다 막았는지 본다.
            global.__event = { prevented: false, stopped: false };
            for (var t = 0; t < CLICK_TIMES; t++) {
              target.children[1].listeners.click({
                preventDefault: function () { global.__event.prevented = true; },
                stopPropagation: function () { global.__event.stopped = true; },
              });
            }
          }
          setTimeout(function () {
            console.log(JSON.stringify({ before: before, after: snapshot() }));
            process.exit(0);
          }, 20);
        }, 20);
        """
    ).replace("RESUME_JS_PATH", json.dumps(str(RESUME_JS))).replace(
        "DELETE_PAYLOAD", json.dumps(delete_payload or {"success": True})
    ).replace(
        "CLICK_INDEX", str(click_index)
    ).replace(
        "CLICK_TIMES", str(click_times)
    ).replace(
        "CONFIRM_ANSWER", "true" if confirm else "false"
    ).replace(
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
    out = _run([])["after"]
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
    )["after"]
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
    )["after"]
    hrefs = [row["href"] for row in out["rows"]]
    assert hrefs == [
        "/add?key=new.big&wizard=1&step=4",
        "/add?key=new.zero&wizard=1&step=1",
    ]


def test_sheet_starts_closed_and_toggles() -> None:
    """시트는 닫힌 채로 시작한다 — 줄을 눌러야 열린다."""
    out = _run([{"draft_key": "new.one", "step": 1, "has_send_history": False}])["after"]
    assert out["sheet_hidden"] is True
    assert out["bar_bound"] is True


# --------------------------------------------------------------------------
# 삭제 — 원치 않는 초안을 버리는 길. 되돌릴 수 없으므로 확인·잠금·복구를 모두 본다.
# --------------------------------------------------------------------------
_TWO_DRAFTS = [
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


def test_every_row_has_a_delete_button_with_korean_label() -> None:
    """행마다 지우기 버튼이 서고, aria-label 이 어느 초안인지 말해 준다."""
    out = _run(_TWO_DRAFTS)["after"]
    first, second = out["rows"]
    assert first["item_class"] == "foms-draft-resume__item"
    assert first["key"] == "new.ff7475d50b3a42ac"
    assert first["delete_bound"] is True
    assert first["delete_label"] == "이광일 작성 중인 주문 지우기"
    assert second["delete_label"] == "이름 아직 없음 작성 중인 주문 지우기"


def test_delete_asks_first_and_names_the_draft() -> None:
    """확인 없이는 요청이 나가지 않고, 문구가 고객명과 되돌릴 수 없음을 말한다."""
    out = _run(_TWO_DRAFTS, click_index=0, confirm=False)["after"]
    assert len(out["confirms"]) == 1
    text = out["confirms"][0]
    assert "이광일" in text, "어느 초안인지 안 알려주면 옆줄을 지운다"
    assert "되돌릴 수 없습니다" in text
    assert "사진도 함께 사라집니다" in text
    assert [c for c in out["calls"] if c["method"] == "DELETE"] == []
    assert len(out["rows"]) == 2, "취소했는데 행이 사라졌다"


def test_delete_calls_endpoint_and_drops_the_row() -> None:
    """확인하면 DELETE 가 나가고, 그 행만 사라지며 개수 문구가 줄어든다."""
    out = _run(_TWO_DRAFTS, click_index=0)
    assert out["before"]["count_text"] == "작성 중인 주문 2건"

    after = out["after"]
    deletes = [c for c in after["calls"] if c["method"] == "DELETE"]
    assert deletes == [
        {"url": "/api/erp/order-draft?key=new.ff7475d50b3a42ac", "method": "DELETE"}
    ]
    assert after["event"] == {"prevented": True, "stopped": True}, "이어쓰기로 샜다"
    assert [row["key"] for row in after["rows"]] == ["new.quiet"]
    assert after["count_text"] == "작성 중인 주문 1건"
    assert after["root_hidden"] is False
    # 성공은 따로 알리지 않는다 — 행이 사라지고 건수가 줄어드는 것이 결과다.
    # 대시보드에는 공용 토스트 CSS 가 안 실려서, 토스트로 알리면 조용히 묻힐 수 있다.
    assert after["toasts"] == [], "성공에 막는 알림을 띄우지 않는다"


def test_deleting_the_last_draft_hides_the_bar() -> None:
    """0건이 되면 띠 자체를 감춘다(빈 띠가 홈 상단을 먹으면 안 된다)."""
    out = _run(
        [{"draft_key": "new.one", "step": 1, "customer_name": "김", "has_send_history": False}],
        click_index=0,
    )["after"]
    assert out["rows"] == []
    assert out["count_text"] == ""
    assert out["root_hidden"] is True
    assert out["sheet_hidden"] is True


def test_failed_delete_keeps_the_row_and_reopens_the_button() -> None:
    """음성 대조군 — 실패하면 행이 남고, 알림이 뜨고, 버튼이 다시 눌린다."""
    out = _run(
        _TWO_DRAFTS,
        click_index=0,
        delete_payload={"success": False, "error": "MISSING_KEY"},
    )["after"]
    assert [row["key"] for row in out["rows"]] == [
        "new.ff7475d50b3a42ac",
        "new.quiet",
    ]
    assert out["count_text"] == "작성 중인 주문 2건"
    assert out["rows"][0]["delete_disabled"] is False, "다시 시도할 수 없다"
    assert "지우지 못했습니다" in " ".join(out["toasts"]), "무음 실패 금지"


def test_double_tap_sends_only_one_delete() -> None:
    """연타해도 DELETE 는 한 번만 나간다.

    되돌릴 수 없는 삭제라, 느린 회선에서 두 번 눌러 두 건이 나가면 **옆 초안까지** 지워질
    수 있다(첫 응답 뒤 목록이 밀리는 경우). 요청 전에 버튼을 잠그는 것이 그 방어라
    여기서 계약으로 못 박는다.
    """
    after = _run(_TWO_DRAFTS, click_index=0, click_times=2)["after"]
    deletes = [c for c in after["calls"] if c["method"] == "DELETE"]
    assert len(deletes) == 1, f"연타에 DELETE 가 {len(deletes)}건 나갔다"
    assert len(after["confirms"]) == 1, "확인창도 한 번만 떠야 한다"


def test_network_failure_tells_the_user_and_unlocks_the_button() -> None:
    """요청 자체가 실패해도 무음으로 끝나지 않고, 다시 누를 수 있어야 한다."""
    after = _run(_TWO_DRAFTS, click_index=0, delete_payload={"success": False})["after"]
    assert "지우지 못했습니다" in " ".join(after["toasts"]), "무음 실패 금지"
    assert len(after["rows"]) == 2, "실패했는데 행이 사라졌다"


def test_draft_bar_can_shrink_inside_the_grid_home() -> None:
    """모바일 홈 본문은 `display: grid` 라, 띠가 줄어들 수 있어야 한다.

    그리드 아이템의 기본값은 `min-width: auto` 여서 **내용의 최소 폭 아래로 못 줄어든다.**
    띠 안의 주소는 `white-space: nowrap` 이라, 주소가 긴 초안이 하나라도 있으면 그 최소
    폭이 화면을 넘고 그리드 칼럼째 넓어져 **홈 화면 전체가 오른쪽으로 밀렸다**
    (2026-09-15 제보, 운영·스테이징 공통. 재현 실측: 390px 화면에서 문서가 710px).

    타워 CSS 가 자기 자식들에게 하나씩 걸어 둔 계약과 같은 것을 컴포넌트 쪽에 둔다 —
    여기 있어야 타워·큐 두 분기에 함께 적용된다.
    """
    css = (ROOT / "static" / "css" / "components" / "foms-draft-resume.css").read_text(encoding="utf-8")
    block = css.split(".foms-draft-resume {", 1)[1].split("}", 1)[0]
    assert "min-width: 0" in block, "그리드 안에서 줄어들 수 없으면 홈 화면이 통째로 밀린다"
    assert "max-width: 100%" in block
