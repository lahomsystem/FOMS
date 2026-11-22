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
import os
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


def _run_simulation(tmp_path: Path, shell_src: str | None = None, env: dict[str, str] | None = None) -> list[dict]:
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
    run_env = {k: v for k, v in os.environ.items() if not k.startswith("FOMS_SIM_")}
    run_env.update(env or {})
    proc = subprocess.run(
        [node, str(script)], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=120,
        env=run_env,
    )
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    return json.loads(proc.stdout)


def _schedule_violations(runs: list[dict], fresh: list[str], entry_only: tuple[str, ...] = ()) -> list[str]:
    """경로마다 일정이 하나인지 판정해 위반 목록을 돌려준다(빈 목록 = 통과).

    ``entry_only``: 하트비트가 부르지 않아야 하는 경로(들어갈 때 받는다 — 일터가 아닌 사람의 생산 첫 화면, 그 화면에 있을 때도).
    """
    problems: list[str] = []
    for run in runs:
        current = run["current"]
        for path in enc.ERP_FRAGMENT_READY_PATHS:
            labels = run["perPath"].get(path, {})
            schedules = {name for name in labels if name in ("primary", "fresh")}
            if path in entry_only:
                if schedules:
                    problems.append(f"{current}: 들어갈 때만 받을 {path} 을 하트비트가 부른다 {labels}")
            elif path in fresh:
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
    # 9탭의 생산 칸 = 생산 첫 화면(2026-11-21, 설계서 production-pc-viewer §9-5) — 옛 보드 자리의 fresh 경로를 이어받았다.
    assert fresh == ["/erp/dashboard", "/erp/measurement", "/erp/production/home"]
    runs = _run_simulation(tmp_path)
    assert {r["current"] for r in runs} == {"/erp/production/home", "/erp/shipment"}
    # 보통 직원(생산 쓰기 팀 아님 · 레일 없음): 생산 첫 화면은 하트비트가 부르지 않는다 — 들어갈 때 받는다(11-22).
    assert _schedule_violations(runs, fresh, entry_only=(_PROD_HOME,)) == []
    here = next(r for r in runs if r["current"] == _PROD_HOME)["perPath"].get(_PROD_HOME, {})
    assert "fresh" not in here and "primary" not in here, "그 화면에 있는 동안 자기 화면을 50초마다 받지 않는다"


_PROD_HOME = "/erp/production/home"


def test_production_home_heartbeat_only_where_production_is_work(tmp_path: Path) -> None:
    """생산 첫 화면 50초 하트비트는 일터인 사람만 — 생산 쓰기 팀 · 태블릿 가로 레일 · 지금 그 화면(11-22 터치 감사).

    PR #890(11-21) 뒤로 PC · 폰 · 도면/시공/출고 팀까지 모두 50초마다 받았다.
    """
    def prod_calls(env: dict[str, str]) -> dict:
        run = _run_simulation(tmp_path, env={"FOMS_SIM_CURRENT": "/erp/shipment", **env})[0]
        return run["perPath"].get(_PROD_HOME, {})

    assert "fresh" not in prod_calls({}) and "primary" not in prod_calls({}), "보통 직원은 다른 화면에서 생산을 받지 않는다"
    for env in ({"FOMS_SIM_PRODUCTION_WORK": "1"}, {"FOMS_SIM_RAIL": "1"}):
        calls = prod_calls(env)
        assert calls.get("fresh", 0) >= _MIN_FRESH_PER_HOUR and "primary" not in calls, (env, calls)
    # 생산 쓰기 팀이어도 그 화면에 있는 동안은 자기 화면을 받지 않는다(받은 사본은 보이는 화면을 다시 그리지 않는다).
    runs = _run_simulation(tmp_path, env={"FOMS_SIM_PRODUCTION_WORK": "1", "FOMS_SIM_RAIL": "1"})
    here = next(r for r in runs if r["current"] == _PROD_HOME)["perPath"].get(_PROD_HOME, {})
    assert "fresh" not in here and "primary" not in here, here
    shipment = next(r for r in runs if r["current"] == "/erp/shipment")
    assert _schedule_violations([shipment], _fresh_paths(SHELL_JS.read_text(encoding="utf-8"))) == []


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


def test_negative_control_old_fresh_targets_heartbeat_production_everywhere(tmp_path: Path) -> None:
    """음성 대조군: 옛 대상(fresh 셋을 누구에게나)으로 되돌린 사본은 보통 직원 출고 화면에서도 생산 첫 화면을 50초마다 받는다."""
    src = SHELL_JS.read_text(encoding="utf-8")
    new_targets = "    var targets = freshRefreshPaths(true);\n"
    assert src.count(new_targets) == 1
    old = src.replace(new_targets, "    var targets = FRESH_TTL_PATHS.concat(visibleLinkedFreshPaths());\n")
    runs = _run_simulation(tmp_path, old, env={"FOMS_SIM_CURRENT": "/erp/shipment"})
    assert runs[0]["perPath"].get(_PROD_HOME, {}).get("fresh", 0) >= _MIN_FRESH_PER_HOUR


def test_shell_stamps_check_time_for_the_rendered_fragment() -> None:
    """생산 첫 화면 '방금 받음'(11-22): 받은 시각은 본문에 없고, 셸이 #main-content 에 끼운 본문을 받거나 확인한 때를 적는다.

    - 끼울 때: 캐시 줄이면 그 줄의 ts(받은 · 304 로 확인한 때), 망이면 지금 — 화면 스크립트가 돌기 전에.
    - 지금 화면과 같은 열쇠 · 같은 ETag 로 재검증이 끝나면(304) 지금으로 다시 적고 foms:shell-fragment-checked.
    """
    src = SHELL_JS.read_text(encoding="utf-8")
    apply = src.split("function applyFragmentToMain(html, swapUrl, meta) {", 1)[1].split("\n  }\n", 1)[0]
    stamp = "main.setAttribute(FRAGMENT_CHECKED_ATTR, String((meta && meta.checkedAt) || Date.now()));"
    assert stamp in apply and apply.index(stamp) < apply.index("activateScripts(main);")
    assert "renderedFragment = { key: lastRenderedKey, etag: (meta && meta.etag) || null };" in apply
    assert "{ etag: cachedRow.etag, checkedAt: cachedRow.ts }" in src
    assert "applyFragmentToMain(payload.html, finalUrl.href, { etag: payload.etag })" in src
    note = src.split("function noteRenderedStillCurrent(key, etag) {", 1)[1].split("\n  }\n", 1)[0]
    assert "renderedFragment.key !== key || renderedFragment.etag !== etag" in note
    assert "'foms:shell-fragment-checked'" in note
    assert "noteRenderedStillCurrent(finalKey, payload.etag);" in src.split("function fetchFragment(canonical)", 1)[1]
    home = (ROOT / "static" / "js" / "production" / "foms-production-home.js").read_text(encoding="utf-8")
    assert "main.getAttribute('data-foms-shell-checked-at')" in home and "data-loaded-at" not in home
    assert "document.addEventListener('foms:shell-fragment-checked'" in home
