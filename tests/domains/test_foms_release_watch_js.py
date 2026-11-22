"""STALE-TAB-01: 열어 둔 탭의 새 배포 새로고침 — 언제 읽고 언제 기다리나(브라우저 쪽, 2026-11-22).

정적 문자열 검사로는 "몇 번 새로 읽나"를 못 보므로 가짜 창 · 가짜 시계 · 가짜 fetch/XHR 로
``static/js/runtime/foms-release-watch.js`` 를 시나리오마다 돌린다(``tests/support/foms_release_watch_node_checks.js``).

- 다른 릴리스 + 한가함 → 한 번 새로 읽는다. 같은 릴리스 → 읽지 않는다.
- 글 칸 커서 · 열린 창 · 고친 칸 · 쓰기 요청 · 방금 누름 · 바쁨 · 인쇄 · 숨음 · 오프라인 → 기다렸다가 풀리면 읽는다.
- 되풀이 방지: 같은 릴리스로 2번까지(두 번째는 5분 뒤), 방금 떠난 릴리스는 10분 동안 좇지 않는다. 저장소가 없으면 읽지 않는다.
- 음성 대조군: 횟수 상한을 지운 사본은 같은 판정에서 세 번째로 또 읽어야 한다(시나리오가 되풀이를 잡는다는 증거).
- 셸 고리: erp-shell.js 가 조각 응답(200 · 304)의 머리글을 감시에 넘긴다(``erp_shell_release_hook_node_checks.js``).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WATCH_JS = ROOT / "static" / "js" / "runtime" / "foms-release-watch.js"
SHELL_JS = ROOT / "static" / "js" / "runtime" / "erp-shell.js"
WATCH_SIM = ROOT / "tests" / "support" / "foms_release_watch_node_checks.js"
HOOK_SIM = ROOT / "tests" / "support" / "erp_shell_release_hook_node_checks.js"
OVERLAY_SIM = ROOT / "tests" / "support" / "foms_release_watch_overlay_checks.js"
_MAX_TRIES_GUARD = "if (g === undefined || tries >= MAX_TRIES) return;"
_SHELL_HOOK_CALL = "        noteServerRelease(r);\n"


def _node(script: Path, env_key: str | None = None, copy: Path | None = None) -> dict:
    node = shutil.which("node")
    assert node, "node must be on PATH for the release watch simulation"
    env = dict(os.environ)
    if env_key and copy:
        env[env_key] = str(copy)
    proc = subprocess.run([node, str(script)], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
                          timeout=120, env=env)
    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def sim() -> dict:
    return {**_node(WATCH_SIM), **_node(OVERLAY_SIM)}


def test_new_release_reloads_once_when_idle(sim):
    assert sim["idle_new_release"]["reloads"] == 1
    guard = sim["idle_new_release"]["guard"].split("|")
    assert (guard[0], guard[2], guard[3]) == ("R2", "1", "R1"), "표식 = 바라던|시각|횟수|떠난"
    assert sim["served_from_cache"]["reloads"] == 1, "캐시에서 꺼낸 옛 문서는 이벤트 없이도 묻는다"
    assert sim["periodic_check_when_idle"] == {"reloads": 1, "asks": 1, "before": 0}, "보이는 채 한가한 탭은 5분마다 묻는다"


def test_same_release_never_reloads(sim):
    assert sim["same_release"]["reloads"] == 0
    assert sim["passive_same_release"] == {"reloads": 0, "asks": 0}


def test_shell_heartbeat_header_is_enough(sim):
    """셸 응답 머리글로 들으면 따로 묻지 않는다 — 하트비트가 도는 동안 요청이 늘지 않는다."""
    assert sim["passive_heartbeat"] == {"reloads": 1, "asks": 0}
    assert sim["heartbeat_heard_skips_ask"]["at8"] == 0


@pytest.mark.parametrize(
    ("name", "why"),
    [
        ("focused_input", "typing"),
        ("open_modal", "overlay"),
        ("body_open_class", "overlay"),
        ("dirty_text", "unsaved"),
        ("fetch_write_in_flight", "saving"),
        ("xhr_upload_in_flight", "saving"),
        ("busy_shell_nav", "busy"),
        ("printing", "printing"),
    ],
)
def test_unsafe_moment_defers_then_reloads_when_clear(sim, name, why):
    row = sim[name]
    assert row["before"] == {"n": 0, "why": why}, row
    assert row["reloads"] == 1, row


def test_recent_touch_waits_for_quiet(sim):
    assert sim["recent_touch"] == {"reloads": 1, "asks": 1, "at15": 0}


def test_unsaved_rules(sim):
    assert sim["dirty_field_removed"] == {"reloads": 1, "asks": 1, "before": 0}, "사라진 칸은 고친 칸이 아니다"
    assert sim["form_checkbox_is_unsaved"]["reloads"] == 0
    assert sim["form_checkbox_is_unsaved"]["why"] == "unsaved"
    assert sim["search_box_is_unsaved"] == {"reloads": 1, "asks": 1, "before": {"n": 0, "why": "unsaved"}},         "찾을 말을 쳐 둔 검색 칸은 새로 읽기를 막고, 비우면 풀린다(11-22 터치 감사)"
    assert sim["untouched_search_box_does_not_block"]["reloads"] == 1, "서버가 그린 그대로인 검색 칸은 막지 않는다"
    assert sim["closed_overlay_search_does_not_block"]["reloads"] == 1, "닫힌 창 속(그려지지 않은) 검색 칸은 막지 않는다"
    assert sim["instant_checkbox_is_not_unsaved"]["reloads"] == 1
    assert sim["offscreen_sheet_is_closed"]["reloads"] == 1, "화면 밖으로 밀어 둔 닫힌 시트는 열린 창이 아니다"


def test_docked_side_sheet_is_not_an_open_overlay(sim):
    """대시보드 태블릿의 붙박이 도킹 시트(role=dialog · aria-modal=false)는 열린 창이 아니다 — 진짜 창은 그대로 막는다."""
    assert sim["docked_side_sheet_is_not_overlay"] == {"reloads": 1, "asks": 1, "why": ""}
    assert sim["undocked_open_side_sheet_blocks"] == {"reloads": 1, "asks": 1, "before": {"n": 0, "why": "overlay"}},         "도킹 없이 밀려 나와 주문을 보이는 시트는 닫힐 때까지 기다린다"
    assert sim["modal_dialog_role_blocks"] == {"reloads": 1, "asks": 1, "before": {"n": 0, "why": "overlay"}},         "aria-modal=true · alertdialog 는 열린 창, 숨으면(hidden) 아니다"


def test_negative_control_old_rules_block_dashboard_and_drop_search(tmp_path):
    """음성 대조군: 옛 셀렉터(모든 role=dialog) · 옛 검색 칸 규칙이면 도킹 시트가 늘 막고 검색 글은 막지 않는다."""
    src = WATCH_JS.read_text(encoding="utf-8")
    sel_part = """[role="dialog"]:not([aria-modal="false"]), '"""
    sheet_part = """'[role="alertdialog"]:not([aria-modal="false"]), .foms-tablet-sheet.is-open:not(.foms-tablet-sheet--docked)'"""
    search_rule = "if (type === 'search') return el.value !== el.defaultValue && el.getClientRects().length > 0;"
    assert src.count(sel_part) == 1 and src.count(sheet_part) == 1 and src.count(search_rule) == 1
    old = (src.replace(sel_part, """[role="dialog"], '""").replace(sheet_part, """'[role="alertdialog"]'""")
           .replace(search_rule, "if (type === 'search') return false;"))
    copy = tmp_path / "foms-release-watch.js"
    copy.write_text(old, encoding="utf-8")
    out = _node(OVERLAY_SIM, "FOMS_SIM_WATCH_JS", copy)
    assert out["docked_side_sheet_is_not_overlay"]["reloads"] == 0
    assert out["docked_side_sheet_is_not_overlay"]["why"] == "overlay"
    assert out["search_box_is_unsaved"]["before"] == {"n": 1, "why": ""}


def test_hidden_and_offline_wait(sim):
    assert sim["hidden_waits_for_wake"] == {"reloads": 1, "asks": 1, "before": 0}
    assert sim["offline_then_online"] == {"reloads": 1, "asks": 1, "before": {"n": 0, "asks": 0}}
    assert sim["check_fails_keeps_page"] == {"reloads": 0, "asks": 1, "logged": True}


def test_stale_news_is_rechecked_before_reload(sim):
    """오래전에 들은 새 릴리스는 읽기 직전에 다시 묻는다 — 서버가 옛 릴리스로 답하면 읽지 않는다."""
    assert sim["stale_heard_rechecks"] == {"reloads": 0, "asks": 1}


def test_no_release_or_storage_means_no_reload(sim):
    assert sim["no_page_release"] == {"reloads": 0, "asks": 0, "bound": False}
    assert sim["storage_broken"]["reloads"] == 0
    assert sim["storage_broken"]["warns"] == 1


def test_guard_stops_reload_loop(sim):
    loop = sim["guard_stops_loop"]
    assert loop["first"] == 1
    assert loop["second"]["at4"] == 0, "옛 컨테이너에 떨어져도 5분 안에는 다시 읽지 않는다"
    assert loop["second"]["reloads"] == 1
    assert loop["third"] == 0, "같은 릴리스로 세 번째는 없다"
    assert loop["landed"] == {"reloads": 1, "asks": 1}, "바라던 릴리스로 온 뒤 다음 배포는 또 받는다"


def test_does_not_flap_back_to_the_release_it_left(sim):
    """배포 중 옛 · 새 컨테이너가 번갈아 답해도 방금 떠난 릴리스로 되돌아 읽지 않는다. 10분 뒤에는 되돌리기 배포로 따른다."""
    row = sim["no_flapping_back"]
    assert row["at9"] == 0
    assert row["reloads"] == 1


def test_negative_control_without_try_cap_loops(tmp_path):
    src = WATCH_JS.read_text(encoding="utf-8")
    assert src.count(_MAX_TRIES_GUARD) == 1
    copy = tmp_path / "foms-release-watch.js"
    copy.write_text(src.replace(_MAX_TRIES_GUARD, "if (g === undefined) return;"), encoding="utf-8")
    loop = _node(WATCH_SIM, "FOMS_SIM_WATCH_JS", copy)["guard_stops_loop"]
    assert loop["third"] >= 1, "횟수 상한이 없으면 세 번째로 또 읽어야 한다 — 아니면 시나리오가 되풀이를 못 잡는다"


def test_shell_passes_release_header_to_watch(tmp_path):
    hook = _node(HOOK_SIM)
    assert hook == {"seen": ["R9", "R9"], "inm": [False, True], "quietCalls": 1}, "200 · 304 모두 넘기고, 감시가 없어도 셸은 돈다"
    src = SHELL_JS.read_text(encoding="utf-8")
    assert src.count(_SHELL_HOOK_CALL) == 1
    copy = tmp_path / "erp-shell.js"
    copy.write_text(src.replace(_SHELL_HOOK_CALL, ""), encoding="utf-8")
    assert _node(HOOK_SIM, "FOMS_SIM_SHELL_JS", copy)["seen"] == [], "음성 대조군: 고리를 지우면 아무것도 안 넘어간다"


def test_watch_file_is_bound_once_and_deferred():
    """퍼포먼스 가드 G1 · G4 — defer 로 싣고 전역 리스너는 한 번만 묶는다."""
    src = WATCH_JS.read_text(encoding="utf-8")
    assert "if (window.__FOMS_RELEASE_WATCH_BOUND) return;" in src
    layout = (ROOT / "templates" / "partials" / "shared" / "layout_scripts.html").read_text(encoding="utf-8")
    line = next(ln for ln in layout.splitlines() if "foms-release-watch.js" in ln and "<script" in ln)
    assert "asset_url('js/runtime/foms-release-watch.js')" in line and " defer>" in line
