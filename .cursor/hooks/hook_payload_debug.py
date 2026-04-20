"""
훅 payload 디버그 기록.

- payload 구조는 훅별 1회 자동 캡처: `docs/harness/logs/HOOK_PAYLOAD_DEBUG.jsonl`
- raw 입력은 훅별 1회 자동 캡처: `docs/harness/logs/HOOK_RAW_DUMP.txt`
- 디버그/파싱 실패는 fail-open 하되 런타임 로그 또는 stderr/fd2에 남긴다.
"""
import json
import os
import sys
import tempfile

def _log_fail(context: str, exc: BaseException, project_root: str | None = None) -> None:
    try:
        d = os.path.dirname(os.path.abspath(__file__))
        if d not in sys.path:
            sys.path.insert(0, d)
        from shared_utils import hook_runtime_log
        hook_runtime_log(f"{context}: {type(exc).__name__}: {exc}", project_root=project_root, tag="payload_debug")
    except Exception:
        try:
            sys.stderr.write(f"hook_payload_debug {context}: {exc}\n")
        except Exception:
            try:
                os.write(2, f"hook_payload_debug {context}: {exc}\n".encode("utf-8", "replace"))
            except Exception:
                return

def _normalize_win_path(path_str):
    """'/c:/...' → 'c:/...' Windows 경로 정규화."""
    if not path_str or not isinstance(path_str, str):
        return path_str
    import re as _re
    s = path_str.strip()
    if _re.match(r"^/[A-Za-z]:/", s):
        s = s[1:]
    return s

def _project_root_from_payload(payload):
    if not isinstance(payload, dict):
        return None
    roots = payload.get("workspace_roots") or payload.get("workspaceRoots")
    if isinstance(roots, list) and roots:
        return _normalize_win_path(str(roots[0]))
    for key in ("workspace", "workspaceFolder", "cwd"):
        v = payload.get(key)
        if v:
            return _normalize_win_path(str(v))
    return None

def maybe_log_payload(hook_name, payload, project_root=None):
    """훅별 1회씩 payload 구조를 자동 캡처 (환경변수 불필요)."""
    root = project_root or _project_root_from_payload(payload)
    try:
        if not root:
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from shared_utils import harness_log_path

        log_path = harness_log_path(root, "HOOK_PAYLOAD_DEBUG.jsonl")
        once_file = harness_log_path(root, ".hook_debug_once")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        if os.path.exists(once_file):
            with open(once_file, "r", encoding="utf-8") as f:
                done = set(f.read().splitlines())
            if hook_name in done:
                return
        line = json.dumps({"hook": hook_name, "payload_keys": list(payload.keys()) if isinstance(payload, dict) else [], "payload": payload}, ensure_ascii=False) + "\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)
        with open(once_file, "a", encoding="utf-8") as f:
            f.write(hook_name + "\n")
    except Exception as e:
        _log_fail("maybe_log_payload", e, root)

def _fallback_err_path(name: str) -> str:
    """에러 fallback 파일 경로: 프로젝트 `docs/harness/logs` 또는 temp 디렉터리."""
    try:
        from shared_utils import harness_log_path

        path = harness_log_path(None, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path
    except Exception:
        return os.path.join(tempfile.gettempdir(), name)

def get_payload():
    """Cursor 훅 payload: env CURSOR_PAYLOAD → stdin → argv 순으로 파싱."""
    raw_input_eval = ""
    root_hint = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        if not sys.stdin.isatty():
            raw_bytes = sys.stdin.buffer.read()
            raw_input_eval = raw_bytes.decode("utf-8-sig", "replace").strip()
    except Exception as e:
        try:
            with open(_fallback_err_path("hook_stdin_err.txt"), "a", encoding="utf-8") as errf:
                errf.write(str(e) + "\n")
        except Exception as e2:
            _log_fail("stdin_err_fallback", e2, root_hint)

    # RAW dump: 훅별 1회씩 raw 입력 캡처 (디스크 무한 증가 방지)
    try:
        root = root_hint
        from shared_utils import harness_log_path

        once_file = harness_log_path(root, ".hook_raw_once")
        hook_id = os.path.basename(sys.argv[0]) if sys.argv else "unknown"
        already_dumped = set()
        if os.path.exists(once_file):
            with open(once_file, "r", encoding="utf-8") as f:
                already_dumped = set(f.read().splitlines())
        if hook_id not in already_dumped:
            log_path = harness_log_path(root, "HOOK_RAW_DUMP.txt")
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                from datetime import datetime as _dt
                f.write(f"--- {hook_id} @ {_dt.now().isoformat()} ---\n")
                f.write(f"args: {sys.argv}\n")
                f.write(f"stdin_len: {len(raw_input_eval)}\n")
                f.write(f"stdin: {repr(raw_input_eval)[:2000]}\n")
                f.write(f"cursor_payload_env: {repr(os.environ.get('CURSOR_PAYLOAD', ''))[:500]}\n\n")
            with open(once_file, "a", encoding="utf-8") as f:
                f.write(hook_id + "\n")
    except Exception as e:
        _log_fail("raw_dump_block", e, root_hint)

    payload_str = os.environ.get("CURSOR_PAYLOAD")
    if payload_str:
        try:
            return json.loads(payload_str)
        except Exception as e:
            _log_fail("json.loads CURSOR_PAYLOAD", e, root_hint)

    if raw_input_eval:
        try:
            return json.loads(raw_input_eval)
        except Exception as e:
            _log_fail("json.loads stdin", e, root_hint)

    if len(sys.argv) > 1:
        try:
            return json.loads(sys.argv[1])
        except Exception as e:
            _log_fail("json.loads argv[1]", e, root_hint)

        try:
            joined = " ".join(sys.argv[1:])
            return json.loads(joined)
        except Exception as e:
            _log_fail("json.loads argv joined", e, root_hint)

    return {}
