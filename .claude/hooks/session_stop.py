"""Claude Code Stop hook: 세션 종료 시 정리 작업.

- SESSION_LOG.md에 종료 기록
- 임시 파일 정리
- EDIT_LOG에서 수정 파일 목록 추출하여 AI_STATUS.md 참조용 출력
"""
import os
import sys
from datetime import datetime

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
from shared_utils import get_project_root, harness_runtime_path  # type: ignore[import-not-found]

# 정리 대상 임시 파일
TEMP_FILES = [
    "commit_msg.txt",
    "commit_msg_deploy.txt",
    "tmp_diff.txt",
    "test_payload.json",
]


def _cleanup_temp(project_root: str):
    """프로젝트 루트의 임시 파일 삭제."""
    for fname in TEMP_FILES:
        fpath = os.path.join(project_root, fname)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception:
                pass


def _log_session_end(project_root: str):
    """SESSION_LOG.md에 세션 종료 기록."""
    log_path = harness_runtime_path("SESSION_LOG.md")
    if not os.path.exists(log_path):
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # EDIT_LOG에서 최근 수정 파일 추출
    edit_log_path = harness_runtime_path("EDIT_LOG.md")
    edited_files = []
    if os.path.exists(edit_log_path):
        with open(edit_log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("| 20") and "`" in line:
                    parts = line.split("`")
                    if len(parts) >= 2:
                        edited_files.append(parts[1])

    # 최근 10개만
    edited_files = list(dict.fromkeys(reversed(edited_files)))[:10]
    files_str = ", ".join(edited_files) if edited_files else "(없음)"

    entry = f"\n| {timestamp} | END (Claude Code) | 수정: {files_str} |"

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry + "\n")


def main():
    project_root = get_project_root()
    _cleanup_temp(project_root)
    _log_session_end(project_root)


if __name__ == "__main__":
    main()
