"""Claude Code UserPromptSubmit hook: 프롬프트를 분류해 하네스 preflight 컨텍스트 주입.

stdin으로 {"prompt": "...", ...} 페이로드를 받아 tools/harness/task_classifier.py의
classify_payload로 분류한 뒤 level/route/RPI 안내를 additionalContext로 주입한다.
짧은 프롬프트나 저위험(low·RPI 불필요·방향확인 불필요)이면 주입을 생략한다.
실패해도 fail-open(exit 0).
"""
import os
import sys

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
from shared_utils import (  # type: ignore[import-not-found]  # noqa: E402
    get_project_root,
    hook_log,
    read_stdin_json,
    write_stdout_json,
)


def _classify(prompt: str, project_root: str):
    """task_classifier.classify_payload로 프롬프트를 분류한다.

    파라미터:
        prompt: 사용자 프롬프트 문자열.
        project_root: 저장소 루트 절대 경로.
    반환: TaskClassification 인스턴스.
    """
    from pathlib import Path

    harness_dir = os.path.join(project_root, "tools", "harness")
    if harness_dir not in sys.path:
        sys.path.insert(0, harness_dir)
    from task_classifier import classify_payload  # type: ignore[import-not-found]

    return classify_payload({"prompt": prompt}, Path(project_root))


def _should_skip(prompt: str, result) -> bool:
    """노이즈 방지: 주입을 생략할지 판정한다.

    파라미터:
        prompt: 사용자 프롬프트 문자열.
        result: TaskClassification 인스턴스.
    반환: 생략하면 True.
    """
    if len(prompt) < 10:
        return True
    return result.level == "low" and not result.needs_rpi and not result.needs_user_direction


def _build_context(result) -> str:
    """분류 결과를 preflight additionalContext 텍스트로 조립한다.

    파라미터:
        result: TaskClassification 인스턴스.
    반환: 주입할 안내 문자열.
    """
    lines = [
        f"[HARNESS PREFLIGHT] level={result.level} route={result.route_kind} "
        f"rpi={result.needs_rpi} reason={result.reason}"
    ]
    for line in result.prompt_lines:
        lines.append(f"- {line}")
    if result.needs_rpi:
        lines.append("- 핵심 코어 변경 — Spec 승인 전 구현 금지 (RPI: 조사→계획→실행)")
    if result.needs_user_direction and result.user_direction_reason:
        lines.append(f"- 사용자 방향 확인 필요: {result.user_direction_reason}")
    if result.level in ("high", "top"):
        lines.append(f"- 컨텍스트 필요 시 {result.claude_bundle_path} 참조")
    return "\n".join(lines)


def main() -> None:
    """UserPromptSubmit 페이로드를 처리하고 필요 시 컨텍스트를 주입한다."""
    payload = read_stdin_json()
    try:
        prompt = str(payload.get("prompt") or "").strip()
        result = _classify(prompt, get_project_root())
        if _should_skip(prompt, result):
            sys.exit(0)
        write_stdout_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": _build_context(result),
                }
            }
        )
    except Exception as exc:  # noqa: BLE001 - fail-open + 로그
        hook_log(
            f"user_prompt_submit fail-open: {type(exc).__name__}: {exc}",
            tag="user_prompt_submit",
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
