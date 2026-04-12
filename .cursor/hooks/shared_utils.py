"""
Cursor 훅 공용 유틸. find_key_recursive 등 payload 추출 로직 공유.
"""
from __future__ import annotations
import os
import re
import tempfile
import time
from typing import Any


def find_key_recursive(data: object, target_keys: list[str], default: str | None = "unknown") -> str | None:
    """중첩 dict/list에서 target_keys 중 하나라도 있으면 해당 값을 반환. 없으면 default."""
    if isinstance(data, dict):
        for k, v in data.items():
            if k in target_keys and v:
                return v
            res = find_key_recursive(v, target_keys, default=None)
            if res is not None:
                return res
    elif isinstance(data, list):
        for item in data:
            res = find_key_recursive(item, target_keys, default=None)
            if res is not None:
                return res
    return default


def normalize_win_path(path_str: str | None) -> str | None:
    """Cursor workspace_roots의 '/c:/...' 형식을 Windows 호환 'c:/...'로 변환.

    Cursor 2.5+ 는 workspace_roots를 URI 스타일('/c:/Users/...')로 전달함.
    Windows Python에서 os.path.abspath('/c:/...') → 'C:\\c:\\...'가 되므로
    선행 '/'를 제거해야 올바른 경로가 됨.
    """
    if not path_str or not isinstance(path_str, str):
        return path_str
    s = path_str.strip()
    if re.match(r"^/[A-Za-z]:/", s):
        s = s[1:]
    return s


def extract_project_root(payload: dict) -> str:
    """payload에서 project_root 추출 + Windows 경로 정규화. fallback: __file__ 기준."""
    raw = find_key_recursive(payload, ["workspace_roots", "workspaceRoots"], default=None)
    if isinstance(raw, list) and len(raw) > 0:
        root = normalize_win_path(str(raw[0]))
    elif raw is not None:
        root = normalize_win_path(str(raw))
    else:
        root = None

    if not root or root.lower() == "none" or root == "unknown":
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return root


def _resolve_project_root(project_root: str | None = None) -> str:
    """Return an existing project root or fall back to the repo root."""
    root = project_root
    if not root or not os.path.isdir(root):
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return root


def harness_docs_path(project_root: str | None = None, *parts: str) -> str:
    """Return an absolute path under `docs/harness/`."""
    return os.path.join(_resolve_project_root(project_root), "docs", "harness", *parts)


def harness_policy_path(project_root: str | None = None, *parts: str) -> str:
    """Return an absolute path under `docs/harness/policy/`."""
    return harness_docs_path(project_root, "policy", *parts)


def harness_runtime_path(project_root: str | None = None, *parts: str) -> str:
    """Return an absolute path under `docs/harness/runtime/`."""
    return harness_docs_path(project_root, "runtime", *parts)


def harness_log_path(project_root: str | None = None, *parts: str) -> str:
    """Return an absolute path under `docs/harness/logs/`."""
    return harness_docs_path(project_root, "logs", *parts)


def hook_runtime_log(message: str, project_root: str | None = None, *, tag: str = "hook") -> None:
    """훅 런타임 로그( fail-open ). `docs/harness/logs/HOOK_RUNTIME_LOG.txt` 또는 temp 폴백. 예외 없음."""
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{tag}] {message}\n"

    def _stderr_fallback(text: str) -> None:
        """파일 로그가 모두 실패해도 최소한 stderr에는 남긴다."""
        try:
            os.write(2, text.encode("utf-8", errors="replace"))
        except Exception:
            return

    path: str | None = None
    try:
        path = harness_log_path(project_root, "HOOK_RUNTIME_LOG.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        path = None
    if not path:
        try:
            path = os.path.join(tempfile.gettempdir(), "foms_hook_runtime.log")
        except Exception:
            _stderr_fallback(line)
            return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        _stderr_fallback(line)
        return


def safe_except_log(exc: BaseException, context: str, project_root: str | None = None) -> None:
    """예외를 삼키되 HOOK_RUNTIME_LOG에 남김."""
    hook_runtime_log(f"{context}: {type(exc).__name__}: {exc}", project_root=project_root, tag="except")
