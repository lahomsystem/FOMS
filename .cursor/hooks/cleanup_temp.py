"""
작업 후 임시/테스트 파일 자동 삭제.
session_stop 훅에서 호출 — 프로젝트 루트의 허용 목록에 있는 파일만 삭제.
"""
from __future__ import annotations
import os
import sys

# 프로젝트 루트에서 삭제해도 되는 파일명 (대소문자 구분 없이 매칭)
TEMP_FILES_WHITELIST = frozenset({
    "commit_msg.txt",
    "commit_msg_deploy.txt",
    "tmp_diff.txt",
    "test_payload.json",
})


def _log(project_root: str | None, message: str) -> None:
    try:
        d = os.path.dirname(os.path.abspath(__file__))
        if d not in sys.path:
            sys.path.insert(0, d)
        from shared_utils import hook_runtime_log
        hook_runtime_log(message, project_root=project_root, tag="cleanup_temp")
    except Exception:
        try:
            sys.stderr.write(f"cleanup_temp: {message}\n")
        except Exception:
            try:
                os.write(2, (f"cleanup_temp: {message}\n").encode("utf-8", "replace"))
            except Exception:
                return


def cleanup_temp_files(project_root: str) -> list[str]:
    """project_root 직하의 임시 파일만 삭제. 삭제된 경로 목록 반환."""
    if not project_root or not os.path.isdir(project_root):
        return []
    removed = []
    try:
        for name in os.listdir(project_root):
            if name in TEMP_FILES_WHITELIST or name.lower() in {s.lower() for s in TEMP_FILES_WHITELIST}:
                path = os.path.join(project_root, name)
                if os.path.isfile(path):
                    try:
                        os.remove(path)
                        removed.append(path)
                    except OSError as e:
                        _log(project_root, f"remove failed {path}: {e}")
    except OSError as e:
        _log(project_root, f"listdir failed: {e}")
    return removed


def main():
    # payload 없이 실행될 수 있으므로 __file__ 기준: .cursor/hooks/ → 프로젝트 루트
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if len(sys.argv) > 1:
        root = os.path.abspath(sys.argv[1])
    removed = cleanup_temp_files(root)
    if removed:
        sys.stdout.write("cleanup_temp: removed " + ", ".join(removed) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
