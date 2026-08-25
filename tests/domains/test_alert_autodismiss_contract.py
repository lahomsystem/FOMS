"""초기 숨김 `.alert` 는 전역 5초 자동닫힘에서 제외돼야 한다(무음 UI 차단).

`static/js/runtime/script.js` 는 DOMContentLoaded 5초 뒤 `.alert:not([data-foms-no-autodismiss])`
를 전부 ``bootstrap.Alert.close()`` 한다 — fade 없는 요소는 **DOM 에서 즉시 제거**된다.
처음부터 숨어 있는 alert(=나중에 JS 가 보여줄 배너·오류상자)는 그 시점에 사용자가 본 적이
없으므로 닫을 대상이 아니고, 제거되면 나중에 `getElementById` 가 null 을 받아 표시가 통째로
무음이 된다(2026-08-25 단계 강제 변경 실패 메시지 소멸 사고).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "templates"
ALERT_TAG = re.compile(r'<[^>]*class="[^"]*\balert\b[^"]*"[^>]*>')
HIDDEN_STYLE = re.compile(r"display\s*:\s*none")


def _initially_hidden_alerts() -> list[tuple[str, int, str]]:
    """초기 숨김(.alert + d-none/display:none) 태그를 (파일, 줄, 태그) 로 모은다."""
    found: list[tuple[str, int, str]] = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in ALERT_TAG.finditer(text):
            tag = match.group(0)
            if "d-none" not in tag and not HIDDEN_STYLE.search(tag):
                continue
            line = text.count("\n", 0, match.start()) + 1
            rel = path.relative_to(ROOT).as_posix()
            found.append((rel, line, tag))
    return found


def test_initially_hidden_alerts_opt_out_of_global_autodismiss():
    """나중에 보여줄 alert 가 자동닫힘에 지워지지 않는지 전수 확인."""
    hidden = _initially_hidden_alerts()
    assert hidden, "초기 숨김 alert 스캔이 0건 — 정규식이 마크업 변화로 죽었는지 확인"
    missing = [
        f"{rel}:{line}"
        for rel, line, tag in hidden
        if "data-foms-no-autodismiss" not in tag
    ]
    assert not missing, (
        "초기 숨김 .alert 에 data-foms-no-autodismiss 누락 — 5초 뒤 DOM 에서 사라져 "
        f"표시가 무음이 된다: {missing}"
    )


def test_autodismiss_optout_selector_is_still_the_contract():
    """자동닫힘 셀렉터가 opt-out 속성을 계속 존중하는지(계약의 반대편) 확인."""
    js = (ROOT / "static/js/runtime/script.js").read_text(encoding="utf-8")
    assert ".alert:not([data-foms-no-autodismiss])" in js
