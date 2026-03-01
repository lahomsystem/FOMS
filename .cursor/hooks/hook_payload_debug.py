"""
훅 payload 디버그 기록. CURSOR_HOOK_DEBUG=1 일 때 docs/context/HOOK_PAYLOAD_DEBUG.jsonl 에 한 줄씩 기록.
CURSOR_HOOK_DEBUG_ONCE=1 이면 훅별 1회만 기록(기본 권장).
RAW dump: CURSOR_HOOK_RAW_DUMP=1 일 때만 docs/context/HOOK_RAW_DUMP.txt 에 append.
"""
import json
import os
import sys
import tempfile

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
    try:
        root = project_root or _project_root_from_payload(payload)
        if not root:
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        log_path = os.path.join(root, "docs", "context", "HOOK_PAYLOAD_DEBUG.jsonl")
        once_file = os.path.join(root, "docs", "context", ".hook_debug_once")
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
    except Exception:
        pass

def _fallback_err_path(name: str) -> str:
    """에러 fallback 파일 경로: 프로젝트 docs/context 또는 temp 디렉터리."""
    try:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ctx = os.path.join(root, "docs", "context")
        os.makedirs(ctx, exist_ok=True)
        return os.path.join(ctx, name)
    except Exception:
        return os.path.join(tempfile.gettempdir(), name)

def get_payload():
    """Cursor 훅 payload: env CURSOR_PAYLOAD → stdin → argv 순으로 파싱."""
    raw_input_eval = ""
    try:
        if not sys.stdin.isatty():
            raw_bytes = sys.stdin.buffer.read()
            raw_input_eval = raw_bytes.decode("utf-8-sig", "replace").strip()
    except Exception as e:
        try:
            with open(_fallback_err_path("hook_stdin_err.txt"), "a", encoding="utf-8") as errf:
                errf.write(str(e) + "\n")
        except Exception:
            pass

    # RAW dump: 훅별 1회씩 raw 입력 캡처 (디스크 무한 증가 방지)
    try:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        once_file = os.path.join(root, "docs", "context", ".hook_raw_once")
        hook_id = os.path.basename(sys.argv[0]) if sys.argv else "unknown"
        already_dumped = set()
        if os.path.exists(once_file):
            with open(once_file, "r", encoding="utf-8") as f:
                already_dumped = set(f.read().splitlines())
        if hook_id not in already_dumped:
            log_path = os.path.join(root, "docs", "context", "HOOK_RAW_DUMP.txt")
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
    except Exception:
        pass

    # 2. Try parsing what we captured
    payload_str = os.environ.get("CURSOR_PAYLOAD")
    if payload_str:
        try:
            return json.loads(payload_str)
        except Exception:
            pass

    if raw_input_eval:
        
        try:
            return json.loads(raw_input_eval)
        except Exception:
            pass
    # 3. Try sys.argv
    if len(sys.argv) > 1:
        try:
            return json.loads(sys.argv[1])
        except Exception:
            pass
        
        try:
            joined = " ".join(sys.argv[1:])
            return json.loads(joined)
        except Exception:
            pass

    return {}
