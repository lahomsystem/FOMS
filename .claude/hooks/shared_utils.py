"""Claude Code hooks 공용 유틸리티."""
import json
import os
import sys
from datetime import datetime


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
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(f"- {timestamp} [{tag}] {message}\n")
    except Exception as exc:  # noqa: BLE001 - 로거 최후 폴백
        try:
            sys.stderr.write(f"hook_log failed [{tag}]: {exc}\n")
        except Exception:  # noqa: BLE001 - stderr도 실패 시 포기
            pass
