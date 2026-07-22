"""Claude Code hooks 공용 유틸리티."""
import json
import os
import sys
from datetime import datetime

# 로그 포맷·로테이션 SSOT (tools/harness/hook_log_utils.py) 공유.
_TOOLS_HARNESS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tools",
    "harness",
)
if _TOOLS_HARNESS not in sys.path:
    sys.path.append(_TOOLS_HARNESS)
from hook_log_utils import (  # noqa: E402  # type: ignore[import-not-found]
    HOOK_LOG_MAX_LINES,
    append_edit_row,
    append_with_rotation,
    build_session_header,
    find_open_session_id,
    format_session_block,
    is_within_tree,
    prepend_session_block,
    read_recent_edited_files,
    regenerate_session_log,
    update_session_block,
)


def find_key_recursive(
    data: object, target_keys: list[str], default: str | None = "unknown"
) -> str | None:
    """중첩 dict/list에서 target_keys 중 하나라도 있으면 해당 값을 반환."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key in target_keys and value:
                return str(value)
            found = find_key_recursive(value, target_keys, default=None)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = find_key_recursive(item, target_keys, default=None)
            if found is not None:
                return found
    return default


def read_stdin_json() -> dict:
    """stdin에서 Claude Code hook payload(JSON, UTF-8)를 읽어 dict로 반환.

    Claude Code는 UTF-8 페이로드를 stdin으로 전달한다. Windows 로케일(cp949)에서
    텍스트 모드로 읽으면 한글이 깨져 다운스트림 분류가 오작동하므로, 바이너리
    버퍼에서 UTF-8로 디코드한다. 비어 있거나 JSON이 아니면 {}를 반환한다.
    """
    try:
        buffer = getattr(sys.stdin, "buffer", None)
        raw = buffer.read() if buffer is not None else sys.stdin.read()
        if not raw:
            return {}
        text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        return json.loads(text)
    except (ValueError, OSError):
        return {}


def get_project_root() -> str:
    """프로젝트 루트 경로 반환."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def harness_docs_path(*parts: str) -> str:
    """Return an absolute path under `docs/harness/`."""
    return os.path.join(get_project_root(), "docs", "harness", *parts)


def harness_policy_path(*parts: str) -> str:
    """Return an absolute path under `docs/harness/policy/`."""
    return harness_docs_path("policy", *parts)


def harness_runtime_path(*parts: str) -> str:
    """Return an absolute path under `docs/harness/runtime/`."""
    return harness_docs_path("runtime", *parts)


def harness_log_path(*parts: str) -> str:
    """Return an absolute path under `docs/harness/logs/`."""
    return harness_docs_path("logs", *parts)


def write_stdout_json(data: dict):
    """결과 JSON을 UTF-8로 stdout에 출력.

    Claude Code는 훅 stdout을 UTF-8로 해석한다. Windows 로케일(cp949) 텍스트
    스트림으로 한글을 쓰면 깨지므로 바이너리 버퍼에 UTF-8 바이트로 기록한다.
    """
    payload = json.dumps(data, ensure_ascii=False)
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(payload.encode("utf-8"))
        buffer.flush()
    else:
        sys.stdout.write(payload)


def ensure_dir(path: str):
    """디렉토리가 없으면 생성."""
    os.makedirs(os.path.dirname(path), exist_ok=True)


def hook_log(message: str, tag: str = "hook") -> None:
    """훅 fail-open 사유를 CLAUDE_HOOK_LOG.md에 한 줄 append (묵시적 삼킴 금지용).

    파라미터:
        message: 기록할 사유 문자열.
        tag: 로그를 남긴 훅 식별 태그.
    반환: 없음. 로거 자체 실패 시 stderr로 폴백해 조용한 삼킴을 피한다.
    """
    try:
        log_path = harness_log_path("CLAUDE_HOOK_LOG.md")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        append_with_rotation(log_path, f"- {timestamp} [{tag}] {message}", HOOK_LOG_MAX_LINES)
    except Exception as exc:  # noqa: BLE001 - 로거 최후 폴백
        try:
            sys.stderr.write(f"hook_log failed [{tag}]: {exc}\n")
        except Exception:  # noqa: BLE001 - stderr도 실패 시 포기
            pass
