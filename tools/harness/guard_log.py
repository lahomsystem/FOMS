"""SHELL_GUARD_LOG writer — Claude·Cursor 가드 훅 공용 (ablation v2 §5, 2026-09-10).

- 캡 3,000행(이전 300행 = 관측창 사흘 → 가드 실효 판정 불가).
- 캡에서 밀려난 행은 그 행의 월 기준 `SHELL_GUARD_LOG.archive-YYYY-MM.md` 에 append — 잃지 않는다.
- 로그 디렉토리는 `FOMS_HARNESS_LOG_DIR` env 가 있으면 그 경로(테스트 격리), 없으면
  `<project_root>/docs/harness/logs`.
- I/O 실패는 예외로 올린다 — 호출 훅이 자기 fail-open 로그로 남긴다(묵시 삼킴 금지).
"""
from __future__ import annotations

import os
import re
from datetime import datetime

LOG_FILE = "SHELL_GUARD_LOG.md"
LOG_CAP = 3000
LOG_HEADER = [
    "# Shell Guard Log",
    "",
    "> 하네스 가드 훅(Claude `PreToolUse:Bash` · Cursor `beforeShellExecution`)이 자동 기록합니다. "
    "(ask/deny 판정만, 최근 3,000행 — 밀려난 행은 `SHELL_GUARD_LOG.archive-YYYY-MM.md`)",
    "",
    "| Time | Decision | Label | Command |",
    "|------|----------|-------|---------|",
]
_ARCHIVE_HEADER = [
    "| Time | Decision | Label | Command |",
    "|------|----------|-------|---------|",
]
_ROW_MONTH = re.compile(r"^\| (\d{4}-\d{2})-")


def resolve_log_dir(project_root: str) -> str:
    """로그 디렉토리 — env `FOMS_HARNESS_LOG_DIR` 우선, 없으면 `<project_root>/docs/harness/logs`.

    파라미터:
        project_root: 저장소(또는 worktree) 루트.
    반환: 절대 디렉토리 경로.
    """
    override = os.environ.get("FOMS_HARNESS_LOG_DIR")
    if override:
        return override
    return os.path.join(project_root, "docs", "harness", "logs")


def _archive_rows(log_dir: str, rows: list[str]) -> None:
    """캡에서 밀려난 행을 행의 월별 보관 파일에 append 한다.

    파라미터:
        log_dir: 로그 디렉토리.
        rows: 밀려난 행(개행 포함).
    반환: 없음.
    """
    by_month: dict[str, list[str]] = {}
    for row in rows:
        m = _ROW_MONTH.match(row)
        by_month.setdefault(m.group(1) if m else "unknown", []).append(row)
    for month, month_rows in by_month.items():
        path = os.path.join(log_dir, f"SHELL_GUARD_LOG.archive-{month}.md")
        fresh = not os.path.exists(path)
        with open(path, "a", encoding="utf-8") as handle:
            if fresh:
                handle.write(f"# Shell Guard Log archive {month}\n\n" + "\n".join(_ARCHIVE_HEADER) + "\n")
            handle.writelines(month_rows)


def append_guard_row(log_dir: str, decision: str, label: str, command: str) -> None:
    """ask/deny 판정 1행을 SHELL_GUARD_LOG.md 에 기록한다(캡 초과분은 월별 보관).

    파라미터:
        log_dir: 로그 디렉토리(`resolve_log_dir` 결과).
        decision: "ask" 또는 "deny".
        label: 판정 사유 요약.
        command: 정규화된 명령 문자열(160자로 잘라 기록).
    반환: 없음. I/O 실패는 예외로 전파한다.
    """
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, LOG_FILE)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = f"| {timestamp} | {decision} | `{label or '-'}` | `{command[:160]}` |\n"

    data_rows: list[str] = []
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as handle:
            data_rows = [ln for ln in handle.readlines() if ln.startswith("| 20")]
    data_rows.append(row)
    overflow = len(data_rows) - LOG_CAP
    if overflow > 0:
        _archive_rows(log_dir, data_rows[:overflow])
        data_rows = data_rows[overflow:]

    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(LOG_HEADER) + "\n")
        handle.writelines(data_rows)
