"""Claude Code Stop hook: 결정적 검증 게이트 + 품질 체크 리마인더.

track_edits.py가 기록한 pending `.py` 편집이 있으면 `import app`을 실제 실행해
앱이 정상 import되는지 검증한다. 실패하면 exit 2 + stderr로 턴 종료를 차단하고,
성공하면 pending을 클리어한다. pending이 없으면 무출력 통과한다.

훅 자체 오류(subprocess timeout, JSON 깨짐 등)는 fail-open 하되 로그를 남긴다.
"""
import json
import os
import subprocess
import sys
from datetime import datetime

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
from shared_utils import (  # type: ignore[import-not-found]
    get_project_root,
    harness_log_path,
    harness_runtime_path,
    read_stdin_json,
    write_stdout_json,
)

PENDING_VERIFY_FILE = ".claude_pending_verify.json"
HOOK_LOG_FILE = "CLAUDE_HOOK_LOG.md"
IMPORT_TIMEOUT_SEC = 120


def _force_utf8_streams() -> None:
    """stdout/stderr를 UTF-8로 강제한다.

    Windows 기본 콘솔 코드페이지(cp949)에서는 한글/em-dash 등 비-cp949 문자를
    stdout/stderr에 쓸 때 UnicodeEncodeError가 발생한다. Claude Code로 전달되는
    메시지는 UTF-8이어야 하므로 스트림 인코딩을 재구성한다.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def _log_hook_error(reason: str) -> None:
    """훅 자체 오류를 CLAUDE_HOOK_LOG.md에 append (fail-open + 기록).

    Args:
        reason: 로그에 남길 오류 설명 문자열.
    """
    log_path = harness_log_path(HOOK_LOG_FILE)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"- {timestamp} [quality_check Stop gate] {reason}\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)


def _read_pending_files() -> list:
    """pending 상태 파일에서 검증 대상 .py 목록을 반환 (없으면 빈 리스트)."""
    pending_path = harness_runtime_path(PENDING_VERIFY_FILE)
    if not os.path.exists(pending_path):
        return []
    with open(pending_path, "r", encoding="utf-8") as f:
        state = json.load(f)
    files = state.get("files", []) if isinstance(state, dict) else []
    return [f for f in files if isinstance(f, str)]


def _clear_pending() -> None:
    """pending 상태 파일을 삭제한다 (검증 통과 후)."""
    pending_path = harness_runtime_path(PENDING_VERIFY_FILE)
    if os.path.exists(pending_path):
        os.remove(pending_path)


def _run_import_gate(pending_files: list, project_root: str) -> None:
    """pending .py가 있으면 `import app`을 실행해 통과/차단을 결정한다.

    성공 시 pending 클리어 후 exit 0, 실패 시 stderr에 원인 기록 후 exit 2.

    Args:
        pending_files: 검증 대상 .py 상대 경로 목록.
        project_root: `import app`을 실행할 저장소 루트(cwd).
    """
    result = subprocess.run(
        [sys.executable, "-c", "import app; print('APP_OK')"],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=IMPORT_TIMEOUT_SEC,
    )
    files_str = ", ".join(pending_files)
    if result.returncode == 0 and "APP_OK" in (result.stdout or ""):
        _clear_pending()
        write_stdout_json(
            {"message": f"[STOP GATE] app import 통과 (APP_OK) — 검증 파일: {files_str}"}
        )
        sys.exit(0)

    tail = "\n".join((result.stderr or "").splitlines()[-30:])
    sys.stderr.write(
        f"[STOP GATE] app import 실패 — 편집된 .py: {files_str}\n"
        f"{tail}\n"
        "근본 원인 수정 후 다시 종료하라."
    )
    sys.exit(2)


def main() -> None:
    """Stop 훅 진입점: pending .py가 있으면 게이트, 없으면 리마인더."""
    _force_utf8_streams()
    read_stdin_json()  # 계약상 stdin 소비 (session_id/stop_hook_active 등)
    project_root = get_project_root()

    try:
        pending_files = _read_pending_files()
    except (OSError, ValueError) as exc:
        _log_hook_error(f"pending 파일 읽기 실패 (fail-open): {exc}")
        return

    if not pending_files:
        # 체크리스트 리마인더는 CLAUDE.md "작업 완료 체크리스트"와 중복이라
        # 제거했다(2026-08-03 하네스 ablation). pending 없으면 무출력 통과.
        return

    try:
        _run_import_gate(pending_files, project_root)
    except subprocess.TimeoutExpired:
        _log_hook_error(
            f"import app 검증 timeout({IMPORT_TIMEOUT_SEC}s) (fail-open, 차단 아님)"
        )
        return
    except OSError as exc:
        _log_hook_error(f"import app 서브프로세스 실행 오류 (fail-open): {exc}")
        return


if __name__ == "__main__":
    main()
