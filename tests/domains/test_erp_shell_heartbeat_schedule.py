"""하트비트 0단계 — 탭 경로마다 갱신 일정은 정확히 하나다 (설계서 2026-10-05 §3.8).

primary 스윕(240초)이 fresh 3경로(50초 스윕이 이미 갱신)를 또 부르던 중복을 뺐다. 정적 문자열
검사로는 "실제로 몇 번 불리나"를 못 보므로, 가짜 창·가짜 시계로 erp-shell.js 를 한 시간 돌려
fetch 를 일정별로 센다(`tests/support/erp_shell_heartbeat_schedule_node_checks.js`).

- fresh 경로: fresh 일정만 부른다(시간당 약 72회). primary 일정이 부르면 실패.
- 나머지 primary 경로: primary 일정만 부른다(시간당 약 15회, 지금 화면 경로는 0회).
- 음성 대조군: 고치기 전 코드(primary 필터에서 fresh 제외를 지운 사본)는 같은 판정에서 실패해야 한다.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from foms.services.common import erp_navigation_contract as enc

ROOT = Path(__file__).resolve().parents[2]
SHELL_JS = ROOT / "static" / "js" / "runtime" / "erp-shell.js"
SIM_JS = ROOT / "tests" / "support" / "erp_shell_heartbeat_schedule_node_checks.js"
_FRESH_FILTER = "return p !== cur && FRESH_TTL_PATHS.indexOf(p) === -1;"
_OLD_FILTER = "return p !== cur;"
# 한 시간 동안 50초·240초 주기 — 마지막 스태거가 시간 밖으로 밀리는 것까지 감안한 하한.
_MIN_FRESH_PER_HOUR = 70
_MIN_PRIMARY_PER_HOUR = 14


def _fresh_paths(src: str) -> list[str]:
    block = src.split("var FRESH_TTL_PATHS = [", 1)[1].split("];", 1)[0]
    return re.findall(r"'(/erp/[^']+)'", block)


def _run_simulation(tmp_path: Path, shell_src: str | None = None) -> list[dict]:
    node = shutil.which("node")
    assert node, "node must be on PATH for the heartbeat schedule simulation"
    script = SIM_JS
    if shell_src is not None:
        shell_copy = tmp_path / "erp-shell.js"
        shell_copy.write_text(shell_src, encoding="utf-8")
        script = tmp_path / "sim.js"
        script.write_text(
            SIM_JS.read_text(encoding="utf-8").replace(
                "path.join(ROOT, 'static/js/runtime/erp-shell.js')", json.dumps(str(shell_copy))
            ),
            encoding="utf-8",
        )
    proc = subprocess.run(
        [node, str(script)], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=120
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    return json.loads(proc.stdout)


def _schedule_violations(runs: list[dict], fresh: list[str]) -> list[str]:
    """경로마다 일정이 하나인지 판정해 위반 목록을 돌려준다(빈 목록 = 통과)."""
    problems: list[str] = []
    for run in runs:
        current = run["current"]
        for path in enc.ERP_FRAGMENT_READY_PATHS:
            labels = run["perPath"].get(path, {})
            schedules = {name for name in labels if name in ("primary", "fresh")}
            if path in fresh:
                if schedules != {"fresh"} or labels.get("fresh", 0) < _MIN_FRESH_PER_HOUR:
                    problems.append(f"{current}: fresh 경로 {path} 일정={labels}")
            elif path == current:
                if schedules:
                    problems.append(f"{current}: 지금 화면 {path} 을 하트비트가 부른다 {labels}")
            elif schedules != {"primary"} or labels.get("primary", 0) < _MIN_PRIMARY_PER_HOUR:
                problems.append(f"{current}: primary 경로 {path} 일정={labels}")
    return problems


def test_each_tab_is_refreshed_by_exactly_one_schedule(tmp_path: Path) -> None:
    src = SHELL_JS.read_text(encoding="utf-8")
    fresh = _fresh_paths(src)
    assert fresh == ["/erp/dashboard", "/erp/measurement", "/erp/production/dashboard"]
    runs = _run_simulation(tmp_path)
    assert {r["current"] for r in runs} == {"/erp/production/dashboard", "/erp/shipment"}
    assert _schedule_violations(runs, fresh) == []


def test_negative_control_old_primary_filter_double_refreshes(tmp_path: Path) -> None:
    """고치기 전 필터로 되돌린 사본은 fresh 경로를 두 일정이 부른다 — 판정이 그것을 잡아야 한다."""
    src = SHELL_JS.read_text(encoding="utf-8")
    assert src.count(_FRESH_FILTER) == 1, "primary 필터 문장이 바뀌었다 — 대조군 치환을 갱신하라"
    runs = _run_simulation(tmp_path, src.replace(_FRESH_FILTER, _OLD_FILTER))
    problems = _schedule_violations(runs, _fresh_paths(src))
    assert problems, "대조군이 통과했다 — 시뮬레이션이 중복 갱신을 못 센다"
    assert any("/erp/dashboard" in p and "primary" in p for p in problems)


def test_primary_filter_excludes_fresh_paths_statically() -> None:
    src = SHELL_JS.read_text(encoding="utf-8")
    block = src.split("function runPrimaryHeartbeat()", 1)[1].split("function runFreshHeartbeat()", 1)[0]
    assert _FRESH_FILTER in block
