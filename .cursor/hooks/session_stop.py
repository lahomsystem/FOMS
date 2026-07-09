import json
import os
import sys
import time
from datetime import datetime

def _load_debug():
    try:
        d = os.path.dirname(os.path.abspath(__file__))
        if d not in sys.path:
            sys.path.insert(0, d)
        from hook_payload_debug import maybe_log_payload, get_payload
        return maybe_log_payload, get_payload
    except Exception as e:
        try:
            from shared_utils import hook_runtime_log
            hook_runtime_log(f"_load_debug failed: {e}", tag="session_stop")
        except Exception:
            try:
                sys.stderr.write(f"session_stop _load_debug: {e}\n")
            except Exception:
                return lambda *a, **k: None, lambda: {}
        return lambda *a, **k: None, lambda: {}
maybe_log_payload, get_payload = _load_debug()

from shared_utils import (
    extract_project_root,
    find_key_recursive,
    find_open_session_id,
    harness_runtime_path,
    hook_runtime_log,
    read_recent_edited_files,
    safe_except_log,
    update_session_block,
)

_IDEMP_TTL_SEC = 18.0
_IDEMP_FILE = ".session_stop_idempotency.json"


def _infer_hook_source() -> str:
    """sessionEnd vs stop 구분(환경·argv). 없으면 unknown."""
    if len(sys.argv) > 1 and sys.argv[1]:
        return str(sys.argv[1]).strip()[:80]
    for key in ("CURSOR_HOOK_NAME", "CURSOR_HOOK_EVENT", "CURSOR_HOOK"):
        v = os.environ.get(key)
        if v:
            return str(v).strip()[:80]
    return "unknown"


def _idempotency_path(project_root: str) -> str:
    return harness_runtime_path(project_root, _IDEMP_FILE)


def _should_skip_duplicate_run(project_root: str, conv_id: str) -> bool:
    """짧은 시간 내 동일 conv_id 재시작(sessionEnd+stop 중복)이면 본문 작업 스킵."""
    path = _idempotency_path(project_root)
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        prev_ts = float(data.get("ts", 0))
        prev_cid = str(data.get("conv_id", ""))
        if conv_id and prev_cid == conv_id and (time.time() - prev_ts) < _IDEMP_TTL_SEC:
            return True
    except Exception as e:
        hook_runtime_log(f"idempotency read fail-open: {e}", project_root=project_root, tag="session_stop")
    return False


def _mark_idempotency_done(project_root: str, conv_id: str) -> None:
    path = _idempotency_path(project_root)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {"ts": time.time(), "conv_id": conv_id, "source": _infer_hook_source()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=0)
    except Exception as e:
        safe_except_log(e, "idempotency write", project_root)


def _resolve_effective_conv_id(project_root: str, conv_id: str) -> str:
    """payload id가 없으면 SESSION_LOG의 열린 세션 id를 사용해 dedupe 정확도를 높인다."""
    if conv_id and conv_id != "unknown":
        return conv_id

    session_log = harness_runtime_path(project_root, "SESSION_LOG.md")
    try:
        sid = find_open_session_id(session_log)
        return sid or conv_id
    except Exception as e:
        safe_except_log(e, "resolve effective conv_id", project_root)
        return conv_id

def _run_session_body(project_root: str, conv_id: str, payload: dict) -> None:
    status = find_key_recursive(payload, ["status"], default="unknown")
    ended_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # SESSION_LOG 블록 갱신은 공용 유틸에 위임(새 행 append 금지, Claude 훅과 단일 포맷).
    session_log = harness_runtime_path(project_root, "SESSION_LOG.md")
    edited_files = read_recent_edited_files(harness_runtime_path(project_root, "EDIT_LOG.md"))
    files_text = ", ".join(f"`{x}`" for x in edited_files) if edited_files else "(없음)"
    update_session_block(
        session_log,
        conv_id,
        {"상태": status, "종료": ended_at, "편집 파일": files_text},
    )

    try:
        from auto_memory import run as auto_memory_run
        auto_memory_run(project_root)
    except Exception as e:
        safe_except_log(e, "auto_memory.run", project_root)

    try:
        from cleanup_temp import cleanup_temp_files
        cleanup_temp_files(project_root)
    except Exception as e:
        safe_except_log(e, "cleanup_temp_files", project_root)


def main():
    payload = get_payload()
    if not isinstance(payload, dict):
        payload = {}

    project_root = extract_project_root(payload)
    src = _infer_hook_source()

    maybe_log_payload(f"stop:{src}", payload, project_root)

    conv_id = find_key_recursive(payload, [
        "conversation_id", "conversationId", "session_id", "sessionId", "id",
        "chatId", "chat_id", "threadId", "thread_id", "conversationId"
    ])
    if isinstance(conv_id, list): conv_id = conv_id[0]
    if isinstance(conv_id, dict): conv_id = conv_id.get("id") or str(conv_id)
    conv_id = str(conv_id)[:8] if conv_id and str(conv_id) != "unknown" else "unknown"
    effective_conv_id = _resolve_effective_conv_id(project_root, conv_id)

    hook_runtime_log(
        f"session_stop begin conv_id={conv_id} effective_conv_id={effective_conv_id} source={src}",
        project_root=project_root,
        tag="session_stop",
    )

    if _should_skip_duplicate_run(project_root, effective_conv_id):
        hook_runtime_log(
            f"session_stop idempotent skip (duplicate sessionEnd/stop) conv_id={effective_conv_id}",
            project_root=project_root,
            tag="session_stop",
        )
        sys.stdout.write(json.dumps({"continue": True}))
        return

    _run_session_body(project_root, conv_id, payload)
    _mark_idempotency_done(project_root, effective_conv_id)

    sys.stdout.write(json.dumps({"continue": True}))

if __name__ == "__main__":
    main()
