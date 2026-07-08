"""Claude Code Stop hook: 세션 종료 시 정리 작업.

- SESSION_LOG.md의 **자기 세션 블록** 종료 필드를 갱신(새 행 append 금지).
- 임시 파일 정리.
- 실패해도 fail-open(exit 0)하되 사유를 CLAUDE_HOOK_LOG에 남긴다.
"""
import os
import sys
from datetime import datetime

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
from shared_utils import (  # type: ignore[import-not-found]  # noqa: E402
    get_project_root,
    harness_runtime_path,
    hook_log,
    read_recent_edited_files,
    read_stdin_json,
    update_session_block,
)

# 정리 대상 임시 파일
TEMP_FILES = [
    "commit_msg.txt",
    "commit_msg_deploy.txt",
    "tmp_diff.txt",
    "test_payload.json",
]


def _cleanup_temp(project_root: str) -> None:
    """프로젝트 루트의 임시 파일 삭제(개별 실패는 로그 후 계속)."""
    for fname in TEMP_FILES:
        fpath = os.path.join(project_root, fname)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except OSError as exc:
                hook_log(f"temp 파일 삭제 실패 {fname}: {exc}", tag="session_stop")


def _log_session_end(session_id: str) -> None:
    """SESSION_LOG.md의 자기 세션 블록을 종료 상태로 갱신한다.

    EDIT_LOG(테이블 포맷)에서 최근 편집 파일을 뽑아 편집 파일 필드에 반영한다.
    기존 구현은 `| END |` 테이블 행을 append 해 session_start 블록 포맷과
    충돌·무한 성장했으므로, 블록 필드 갱신으로 교체했다.

    파라미터:
        session_id: 갱신 대상 세션 식별자 앞 8자.
    반환: 없음.
    """
    log_path = harness_runtime_path("SESSION_LOG.md")
    if not os.path.exists(log_path):
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    edited = read_recent_edited_files(harness_runtime_path("EDIT_LOG.md"), limit=10)
    files_str = ", ".join(edited) if edited else "(없음)"
    update_session_block(
        log_path,
        session_id,
        {"상태": "완료", "편집 파일": files_str, "종료": timestamp},
    )


def main() -> None:
    """Stop 페이로드를 처리하고 세션 종료를 기록한다. 실패해도 fail-open."""
    payload = read_stdin_json()
    try:
        session_id = str(payload.get("session_id") or "unknown")[:8]
        project_root = get_project_root()
        _cleanup_temp(project_root)
        _log_session_end(session_id)
    except Exception as exc:  # noqa: BLE001 - fail-open + 로그
        hook_log(f"session_stop fail-open: {type(exc).__name__}: {exc}", tag="session_stop")
    sys.exit(0)


if __name__ == "__main__":
    main()
