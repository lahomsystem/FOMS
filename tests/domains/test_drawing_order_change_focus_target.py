"""`변경 보기` 버튼의 도착지 계약 (계약 C — 2026-09-13 운영 제보 ②).

**왜 이 파일이 따로 있나.** 운영 안드로이드에서 `변경 보기` 를 눌러도 아무 일이 없었다.
`focusTimeline()` 이 맨 먼저 데스크톱 본문의 `#dwOrderChangeFeed` 를 잡아 `scrollIntoView`
하고 **무조건 return** 했기 때문이다. 그 요소의 조상은 폰 폭에서 `d-none` 이라
`display:none` 이고, 숨은 요소로 스크롤하는 것은 아무 일도 하지 않는다. 진짜 모바일
도착지(`.foms-drawing-thread__msg--alert`)에는 영원히 닿지 못했다.

문자열 단언으로는 이 사고를 못 잡는다 — 셀렉터는 그때도 소스에 다 있었다. 그래서 함수를
떼어내 **Node 에서 실제로 실행**하고, 숨은 후보를 건너뛰는지를 호출 기록으로 본다.
선례: tests/services/integrations/test_naver_dock_amounts.py 의 `_extract_function` 패턴.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import tempfile

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_BANNER_JS = _REPO_ROOT / "static" / "js" / "drawing" / "order-change-banner.js"

_needs_node = pytest.mark.skipif(not shutil.which("node"), reason="node not on PATH")


def _source() -> str:
    """배너 JS 원문."""
    return _BANNER_JS.read_text(encoding="utf-8")


def _extract_function(source: str, name: str) -> str:
    """JS 원문에서 함수 하나를 통째로 뜯어낸다(중괄호 균형으로 끝을 찾는다).

    배너 JS 는 즉시실행 IIFE 라 통째로는 Node 에서 돌지 않는다(`document` 를 만진다).
    도착지 규칙만은 문자열이 아니라 **실제 실행**으로 못박아야 해서 함수만 떼어낸다.

    Args:
        source: JS 원문.
        name: 뜯어낼 함수 이름.

    Returns:
        `function name(...) { ... }` 원문.
    """
    start = source.index("function " + name + "(")
    depth = 0
    for index in range(source.index("{", start), len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(name + " 함수의 끝을 못 찾았다")


# 후보 셀렉터 → 스텁 노드 이름. focusTimeline 이 보는 순서 그대로다.
_SELECTOR_TO_NAME = {
    ".dw-order-change-card.is-pending": "card",
    ".foms-drawing-thread__msg--alert:not(.is-acked)": "alert",
    ".foms-drawing-thread__msg--alert": "alert_any",
    ".dw-order-change-badge": "badge",
}

_HARNESS = r"""
var SPEC = __SPEC__;
var SEL = __SEL__;
var calls = [];
var toasts = [];

function makeNode(name) {
  if (!Object.prototype.hasOwnProperty.call(SPEC, name)) return null;
  if (SPEC[name] === null) return null;
  return {
    name: name,
    offsetParent: SPEC[name] ? {} : null,
    scrollIntoView: function () { calls.push(this.name); }
  };
}

var document = {
  getElementById: function (id) {
    return id === 'dwOrderChangeFeed' ? makeNode('feed') : null;
  },
  querySelector: function (sel) {
    return Object.prototype.hasOwnProperty.call(SEL, sel) ? makeNode(SEL[sel]) : null;
  },
  querySelectorAll: function () { return []; }
};

function getComputedStyle() { return { position: 'static', display: 'block' }; }

var window = {
  location: { href: 'https://x/y' },
  history: { replaceState: function () {} },
  showToast: function (msg) { toasts.push(msg); }
};
var console = { info: function (msg) { toasts.push(msg); } };

__FUNCS__

focusTimeline();

var out = JSON.stringify({ calls: calls, toasts: toasts });
process.stdout.write(out.replace(/[\u0080-\uffff]/g, function (c) {
  return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4);
}));
"""


def _run_focus(spec: dict) -> dict:
    """`focusTimeline()` 을 Node 에서 실제로 실행한 결과.

    Args:
        spec: 스텁 노드 이름 → `True`(보임) / `False`(offsetParent 가 null) / `None`(요소 없음).
            이름은 `feed`, `card`, `alert`, `alert_any`, `badge`.

    Returns:
        `{"calls": [scrollIntoView 가 불린 노드 이름 순서], "toasts": [문구]}`.
    """
    source = _source()
    funcs = "\n".join(
        _extract_function(source, name) for name in ("toast", "isVisible", "focusTimeline")
    )
    script = (
        _HARNESS.replace("__SPEC__", json.dumps(spec))
        .replace("__SEL__", json.dumps(_SELECTOR_TO_NAME))
        .replace("__FUNCS__", funcs)
    )
    node = shutil.which("node")
    assert node, "node 가 PATH 에 없다"
    with tempfile.TemporaryDirectory(prefix="dw-focus-target-") as tmp:
        path = pathlib.Path(tmp) / "focus_target_check.js"
        path.write_text(script, encoding="utf-8")
        proc = subprocess.run([node, str(path)], capture_output=True, text=True,
                              encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


# --------------------------------------------------------------------------- #
# (1) 도착지 선택 — Node 실행
# --------------------------------------------------------------------------- #

@_needs_node
def test_hidden_desktop_feed_is_skipped_for_mobile_alert():
    """폰에서 숨은 데스크톱 피드를 **건너뛰고** 모바일 말풍선으로 간다.

    이번 제보 ②의 회귀 방지 본체다. 숨은 첫 후보에서 조기 return 하면 호출 기록이 비거나
    `feed` 하나만 남는다 — 버튼이 죽은 것처럼 보이던 그 상태다.
    """
    result = _run_focus({"feed": False, "card": None, "alert": True, "alert_any": True,
                         "badge": None})

    assert result["calls"] == ["alert"], result
    assert "feed" not in result["calls"], "숨은 데스크톱 피드로 스크롤했다"
    assert result["toasts"] == [], "도착했는데 실패 안내를 띄웠다"


@_needs_node
def test_visible_desktop_feed_still_wins():
    """데스크톱에서는 첫 후보(변경 이력 피드)가 그대로 이긴다 — 기존 동작 회귀 금지."""
    result = _run_focus({"feed": True, "card": True, "alert": True, "alert_any": True,
                         "badge": True})

    assert result["calls"] == ["feed"], result


@_needs_node
def test_no_visible_target_reports_instead_of_silence():
    """보이는 후보가 하나도 없으면 조용히 끝내지 않고 안내를 띄운다.

    아무 일도 안 하면 사용자는 버튼이 고장 난 줄 알고 같은 자리를 계속 누른다.
    """
    result = _run_focus({"feed": False, "card": False, "alert": False, "alert_any": False,
                         "badge": False})

    assert result["calls"] == [], "보이지 않는 요소로 스크롤했다"
    assert len(result["toasts"]) == 1, result


# --------------------------------------------------------------------------- #
# (2) 확인(ack) 경로는 손대지 않았다 — 계약 F
# --------------------------------------------------------------------------- #

def test_ack_handler_untouched():
    """확인 버튼 경로(2026-09-12 계약)를 이번 수정이 건드리지 않았음을 못박는다.

    옛 배너 시절 `ackBanner` 는 조상 배너에서 주소를 읽었고, 배너를 걷어낸 뒤로는 버튼이
    자기 `data-ack-url` 을 직접 싣는다. 이 두 문자열이 사라지면 확인 버튼이 다시 죽는다.
    """
    source = _source()

    assert "btn.closest('[data-ack-url]')" in source
    assert "foms-drawing-turn__change--done" in source
