"""미리 받은 조각의 CSS 미리 받기(2026-11-19) — 가짜 문서로 erp-shell.js 를 돌려 센다.

폰 첫 진입: 조각 HTML 은 미리 받아 두었는데 그 전용 CSS 는 누른 뒤에야 받기 시작해, 서버 작업자가 다른 조각을 그리느라
바쁘면 CSS 가 줄을 서 도착이 두 봉우리였다(운영 시공 첫 진입 7번 중 2번 ~1,050ms). 미리 받은 순간 그 조각의 새
stylesheet 를 ``<link rel="preload" as="style">`` 로 받아 둔다 — 규칙을 걸지 않아 화면 모양은 그대로다.

- (a) 미리 받은 조각의 새 CSS 가 preload link 로 붙는다(응답 처리 안이 아니라 다음 작업에서).
- (b) 문서 머리 · 본문에 이미 있는 stylesheet · 이미 건 style preload 는 안 붙는다.
- (c) 같은 조각을 두 번 받아도(하트비트 304) · 다른 조각이 같은 CSS 를 들어도 한 번만.
- (d) stylesheet 아닌 link(rel=icon · manifest)는 무시한다. 데이터 절약이면 받지 않는다. 누름(스왑)은 preload 를 걸지 않는다.

음성 대조군: 부르지 않는 사본 · 응답 처리 안에서 바로 부르는 사본 · 문서 확인을 뺀 사본은 각 판정에서 실패해야 한다.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHELL_JS = ROOT / "static" / "js" / "runtime" / "erp-shell.js"
SIM_JS = ROOT / "tests" / "support" / "erp_shell_style_warm_node_checks.js"
_DEFERRED_CALL = "          afterNextPaint(warmFragmentStylesheets.bind(null, payload.html));\n"
_PRESENT_SKIP = "      if (present[h]) {\n"
_A, _B, _LATE, _D = ("/static/css/a.css?v=1", "/static/css/b.css?v=1", "/static/css/late.css?v=1", "/static/css/d.css?v=1")


def _run(shell_js: Path | None = None) -> dict:
    node = shutil.which("node")
    assert node, "node must be on PATH for the erp-shell style warm simulation"
    env = dict(os.environ)
    if shell_js is not None:
        env["FOMS_SIM_SHELL_JS"] = str(shell_js)
    proc = subprocess.run(
        [node, str(SIM_JS)], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=120, env=env
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    return json.loads(proc.stdout)


def _copy(tmp_path: Path, name: str, old: str, new: str) -> Path:
    src = SHELL_JS.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert src.count(old) == 1, "미리 받기 문장이 바뀌었다 — 대조군 치환을 갱신하라"
    out = tmp_path / name
    out.write_text(src.replace(old, new), encoding="utf-8")
    return out


def test_prefetched_fragment_css_is_preloaded_once() -> None:
    out = _run()
    w = out["warm"]
    assert w["atResponse"] == 0  # 응답 처리 안에서는 0개 — 그린 뒤 다음 작업에서
    assert w["first"] == [["preload", "style", _A], ["preload", "style", _B], ["preload", "style", _LATE]]  # (a)(b)(d)
    assert w["refetchCalls"] == 1 and w["afterRefetch"] == 3  # (c) 하트비트 304 다시 받기 — 늘지 않는다
    assert w["afterOther"] == [["preload", "style", _D]]  # (c) 다른 조각의 같은 a.css 는 다시 걸지 않는다
    assert out["saveData"]["first"] == [] and out["saveData"]["afterOther"] == []
    assert out["nav"] == {"appended": [["stylesheet", None, _A], ["stylesheet", None, _D]], "swapped": 1}


def test_negative_control_missing_or_sync_or_no_document_check(tmp_path: Path) -> None:
    assert _run(_copy(tmp_path, "none.js", _DEFERRED_CALL, ""))["warm"]["first"] == []
    sync = _copy(tmp_path, "sync.js", _DEFERRED_CALL, "          warmFragmentStylesheets(payload.html);\n")
    assert _run(sync)["warm"]["atResponse"] == 3
    no_doc = _run(_copy(tmp_path, "no_doc.js", _PRESENT_SKIP, "      if (false) {\n"))["warm"]["first"]
    assert ["preload", "style", "/static/css/head.css?v=1"] in no_doc and len(no_doc) == 6
