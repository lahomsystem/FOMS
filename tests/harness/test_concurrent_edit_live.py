"""EDIT_LOG Session 컬럼 + 편집 시점 동시 세션 감지(디바운스) 계약 테스트.

커버:
  - append_edit_row 4컬럼 기록 / 구세대 3컬럼 행 혼재 시 기존 소비자 파싱 무손상
  - dedup: 같은 파일·같은 세션은 skip 유지, 같은 파일·다른 세션은 기록(감지 가능 조건)
  - find_other_session_edits 필터: own·미상("-")·윈도우 밖·docs//.md 제외
  - 디바운스: 새 상대 세션 1회, 동일 파일 충돌 파일당 1회
  - 상태 파일 세션 키 20개 캡
  - EDIT_LOG 부재·깨진 행 → 크래시·경고 없음
  - PostToolUse stdout JSON(additionalContext) 주입 경로

모든 파일 I/O는 tmp_path 안에서만 일어난다(실 EDIT_LOG·상태 파일 불가침).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

NOW = datetime(2026, 7, 29, 12, 0, 0)
LEGACY_HEADER = "# Edit Log\n\n| Time | File | Tool |\n|------|------|------|\n"

# hook_log_utils를 sys.path 오염 없이 격리 로드 (고유 모듈명 사용).
_HLU_PATH = REPO_ROOT / "tools" / "harness" / "hook_log_utils.py"
_spec = importlib.util.spec_from_file_location("hook_log_utils_concurrent_test", _HLU_PATH)
assert _spec is not None and _spec.loader is not None
hlu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hlu)


def _load_hook(module_name: str, relative_path: str = ".claude/hooks/track_edits.py"):
    """`.claude/hooks/*` 모듈을 fresh 로드하고 sys.path/shared_utils를 복원한다."""
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    saved_path = list(sys.path)
    saved_shared = sys.modules.get("shared_utils")
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved_path
        if saved_shared is not None:
            sys.modules["shared_utils"] = saved_shared
        else:
            sys.modules.pop("shared_utils", None)
    return module


def _row(minutes_ago: int, rel_path: str, session: str | None = None, tool: str = "Edit") -> str:
    """NOW 기준 `minutes_ago`분 전 EDIT_LOG 행(session=None이면 구세대 3컬럼)."""
    stamp = (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%d %H:%M:%S")
    if session is None:
        return f"| {stamp} | `{rel_path}` | {tool} |\n"
    return f"| {stamp} | `{rel_path}` | {tool} | {session} |\n"


def _write_log(tmp_path: Path, rows: list[str], *, legacy_header: bool = False) -> Path:
    """헤더 + 주어진 행으로 EDIT_LOG를 만들고 경로를 반환한다."""
    path = tmp_path / "EDIT_LOG.md"
    header = LEGACY_HEADER if legacy_header else "\n".join(hlu.EDIT_LOG_HEADER_LINES) + "\n"
    path.write_text(header + "".join(rows), encoding="utf-8")
    return path


def _notice(
    module,
    log: Path,
    state: Path,
    rel_path: str,
    *,
    own: str = "s1aaaaaa",
    window: int = 30,
) -> str:
    """track_edits 감지 로직을 주입 경로로 호출한다."""
    return module.concurrent_edit_notice(
        rel_path,
        own,
        edit_log_path=str(log),
        state_path=str(state),
        window_min=window,
        now=NOW,
    )


# --- 1. 4컬럼 기록 · 구세대 행 혼재 시 소비자 무손상 -----------------------
def test_append_adds_session_column_and_keeps_consumers_intact(tmp_path: Path) -> None:
    """새 행은 4컬럼, 구세대 3컬럼 행과 혼재해도 기존 파서가 그대로 동작한다."""
    log = _write_log(tmp_path, [_row(5, "legacy/old.py")], legacy_header=True)
    stamp = (NOW - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")

    assert hlu.append_edit_row(
        str(log), "apps/api/new.py", "Edit", timestamp=stamp, session="s2bbbbbb"
    ) is True

    content = log.read_text(encoding="utf-8")
    assert "| Time | File | Tool | Session |" in content, "헤더에 Session 컬럼이 없다"
    assert f"| {stamp} | `apps/api/new.py` | Edit | s2bbbbbb |" in content
    # cols[0]/cols[1]만 쓰는 기존 소비자(guard_shell·quality_check 계열) 무손상
    assert hlu.read_recent_edited_files(str(log)) == ["apps/api/new.py", "legacy/old.py"]
    # 구세대 3컬럼 행은 세션 미상 → 타 세션으로 세지 않는다
    rows = content.splitlines(keepends=True)
    assert hlu.find_other_session_edits(rows, "s1aaaaaa", 30, NOW) == [
        ("s2bbbbbb", "apps/api/new.py")
    ]


def test_session_start_note_still_parses_four_column_rows(tmp_path: Path) -> None:
    """session_start의 세션 시작 감지(3컬럼 prefix 파서)가 4컬럼 행도 읽는다."""
    module = _load_hook("session_start_4col", ".claude/hooks/session_start.py")
    log = _write_log(tmp_path, [_row(5, "apps/api/orders.py", "s2bbbbbb")])

    note = module._concurrent_edit_note("startup", edit_log_path=str(log), now=NOW)

    assert "[CONCURRENT-EDIT]" in note
    assert "orders.py" in note


# --- 2. dedup: 세션이 다르면 기록돼야 감지가 가능하다 ----------------------
def test_dedup_skips_same_session_but_records_other_session(tmp_path: Path) -> None:
    """같은 파일 300초 내: 같은 세션은 skip, 다른 세션은 기록(감지 전제 조건)."""
    log = tmp_path / "EDIT_LOG.md"

    assert hlu.append_edit_row(str(log), "app.py", "Edit", session="s1aaaaaa") is True
    assert hlu.append_edit_row(str(log), "app.py", "Edit", session="s1aaaaaa") is False
    assert hlu.append_edit_row(str(log), "app.py", "Edit", session="s2bbbbbb") is True

    rows = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.startswith("| 20")]
    assert len(rows) == 2, f"세션별 1행씩 남아야 한다: {rows}"


def test_dedup_treats_legacy_row_as_dash_session(tmp_path: Path) -> None:
    """세션 컬럼 없는 구세대 행은 "-" 세션으로 간주해 기본 호출과 dedup된다."""
    log = tmp_path / "EDIT_LOG.md"
    log.write_text(
        "\n".join(hlu.EDIT_LOG_HEADER_LINES) + "\n" + f"| {hlu._now()} | `app.py` | Cursor |\n",
        encoding="utf-8",
    )

    assert hlu.append_edit_row(str(log), "app.py", "Edit") is False


# --- 3. find_other_session_edits 필터 --------------------------------------
def test_find_other_session_edits_filters(tmp_path: Path) -> None:
    """own·미상·윈도우 밖·문서 편집은 타 세션 편집으로 세지 않는다."""
    rows = [
        _row(5, "mine/own.py", "s1aaaaaa"),        # 자기 세션 → 제외
        _row(5, "legacy/none.py"),                 # 구세대 3컬럼(미상) → 제외
        _row(5, "unk/dash.py", "-"),               # 명시 미상 → 제외
        _row(99, "old/far.py", "s2bbbbbb"),        # 윈도우 밖 → 제외
        _row(5, "docs/AI_STATUS.md", "s2bbbbbb"),  # docs/ → 제외
        _row(5, "README.md", "s2bbbbbb"),          # .md → 제외
        _row(5, "apps/api/orders.py", "s2bbbbbb"),  # 유일한 유효 감지
    ]

    found = hlu.find_other_session_edits(rows, "s1aaaaaa", 30, NOW)

    assert found == [("s2bbbbbb", "apps/api/orders.py")], found


# --- 4. 디바운스: 새 상대 세션 1회 -----------------------------------------
def test_live_notice_debounced_until_new_session_appears(tmp_path: Path) -> None:
    """첫 감지만 경고, 같은 상대 재편집은 무경고, 새 세션 등장 시 재경고."""
    module = _load_hook("track_edits_debounce")
    state = tmp_path / "concurrent_notice_state.json"
    log = _write_log(tmp_path, [_row(5, "other/a.py", "s2bbbbbb")])

    first = _notice(module, log, state, "mine/b.py")
    assert "[CONCURRENT-EDIT-LIVE]" in first
    assert "s2bbbbbb" in first
    assert "session_worktree.py create" in first

    assert _notice(module, log, state, "mine/b.py") == "", "같은 상대 반복 주입 = 토큰 낭비"

    _write_log(tmp_path, [_row(5, "other/a.py", "s2bbbbbb"), _row(2, "other/c.py", "s3cccccc")])
    third = _notice(module, log, state, "mine/b.py")
    assert "[CONCURRENT-EDIT-LIVE]" in third, "새 세션 등장 시에는 다시 경고해야 한다"
    assert "s3cccccc" in third
    assert "s2bbbbbb" not in third, "이미 안내한 세션은 다시 나열하지 않는다"


# --- 5. 동일 파일 충돌: 파일당 1회 ----------------------------------------
def test_collision_notice_once_per_file(tmp_path: Path) -> None:
    """동일 rel_path 타 세션 편집이면 COLLISION, 같은 파일 재발은 무경고."""
    module = _load_hook("track_edits_collision")
    state = tmp_path / "concurrent_notice_state.json"
    log = _write_log(tmp_path, [_row(3, "apps/api/orders.py", "s2bbbbbb")])

    first = _notice(module, log, state, "apps/api/orders.py")
    assert "[CONCURRENT-EDIT-COLLISION]" in first
    assert "apps/api/orders.py" in first
    assert "[CONCURRENT-EDIT-LIVE]" in first, "첫 감지면 LIVE와 합쳐 1회 주입"

    assert _notice(module, log, state, "apps/api/orders.py") == ""

    # 세션은 이미 안내됨 → 새 충돌 파일만 경고
    log = _write_log(
        tmp_path,
        [_row(3, "apps/api/orders.py", "s2bbbbbb"), _row(1, "services/policy.py", "s2bbbbbb")],
    )
    third = _notice(module, log, state, "services/policy.py")
    assert "[CONCURRENT-EDIT-COLLISION]" in third
    assert "services/policy.py" in third
    assert "[CONCURRENT-EDIT-LIVE]" not in third


# --- 6. 상태 파일 세션 키 캡 ----------------------------------------------
def test_state_file_caps_session_keys(tmp_path: Path) -> None:
    """세션 키 20개 초과 시 오래된 것부터 제거되고 자기 세션은 유지된다."""
    module = _load_hook("track_edits_cap")
    state = tmp_path / "concurrent_notice_state.json"
    seeded = {f"old{i:04d}": {"warned_sessions": [], "warned_files": []} for i in range(25)}
    state.write_text(json.dumps(seeded), encoding="utf-8")
    log = _write_log(tmp_path, [_row(5, "other/a.py", "s2bbbbbb")])

    assert "[CONCURRENT-EDIT-LIVE]" in _notice(module, log, state, "mine/b.py")

    saved = json.loads(state.read_text(encoding="utf-8"))
    assert len(saved) == module.CONCURRENT_STATE_MAX_SESSIONS == 20, saved.keys()
    assert "s1aaaaaa" in saved, "자기 세션 항목이 캡에 밀려나면 디바운스가 무력화된다"
    assert "old0000" not in saved, "오래된 키부터 제거돼야 한다"


# --- 7. 부재·깨진 입력 ----------------------------------------------------
def test_missing_log_and_broken_rows_are_silent(tmp_path: Path) -> None:
    """EDIT_LOG 부재·깨진 행에서 크래시 없이 경고 없음."""
    module = _load_hook("track_edits_broken")
    state = tmp_path / "concurrent_notice_state.json"

    assert _notice(module, tmp_path / "missing.md", state, "mine/b.py") == ""
    assert not state.exists(), "감지 실패 시 상태 파일을 만들지 않는다"

    broken = _write_log(
        tmp_path,
        [
            "| 2026-13-45 99:99:99 | `x.py` | Edit | s2bbbbbb |\n",
            "쓰레기 줄\n",
            "| 20 truncated row\n",
        ],
    )
    assert _notice(module, broken, state, "mine/b.py") == ""


def test_session_tag_maps_missing_id_to_dash() -> None:
    """session_id 부재/unknown은 "-"(미상)으로 기록해 타 세션 오탐을 막는다."""
    module = _load_hook("track_edits_tag")

    assert module._session_tag({}) == "-"
    assert module._session_tag({"session_id": "unknown"}) == "-"
    assert module._session_tag({"session_id": "abcdef0123456789"}) == "abcdef01"


# --- PostToolUse 주입 경로 -------------------------------------------------
def test_hook_main_injects_additional_context(tmp_path: Path, monkeypatch, capsys) -> None:
    """타 세션 편집이 있는 EDIT_LOG에서 훅 main이 additionalContext를 출력한다."""
    module = _load_hook("track_edits_stdout")
    proj = tmp_path / "proj"
    runtime = proj / "docs" / "harness" / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    target = proj / "apps" / "api" / "orders.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x = 1", encoding="utf-8")
    stamp = hlu._now()
    (runtime / "EDIT_LOG.md").write_text(
        "\n".join(hlu.EDIT_LOG_HEADER_LINES)
        + "\n"
        + f"| {stamp} | `apps/api/orders.py` | Edit | s2bbbbbb |\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "get_project_root", lambda: str(proj))
    monkeypatch.setattr(module, "harness_runtime_path", lambda *p: str(runtime.joinpath(*p)))
    monkeypatch.setattr(
        module,
        "read_stdin_json",
        lambda: {
            "tool_name": "Edit",
            "session_id": "s1aaaaaa-full-id",
            "tool_input": {"file_path": str(target)},
        },
    )

    module.main()

    payload = json.loads(capsys.readouterr().out)
    context = payload["hookSpecificOutput"]["additionalContext"]
    assert payload["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "[CONCURRENT-EDIT-LIVE]" in context
    assert "[CONCURRENT-EDIT-COLLISION]" in context
    assert "s1aaaaaa" in json.loads(
        (runtime / "concurrent_notice_state.json").read_text(encoding="utf-8")
    )
