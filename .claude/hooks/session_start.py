"""Claude Code SessionStart hook: SESSION_LOG 기록 + compact 재개 포인터 주입.

stdin으로 {"session_id": ..., "source": "startup"|"resume"|"clear"|"compact"|"fork", ...}
형태의 페이로드를 받아 SESSION_LOG.md에 세션 시작을 기록하고, compact 재개일 때만
additionalContext로 체크포인트 포인터를 주입한다. 실패해도 fail-open(exit 0).

2026-09-10 ablation v2: MEMORY-GATE(160줄 권고)·CONCURRENT-EDIT(타 창 편집 감지)·
ctx_gate baseline 기록을 제거했다 — 각각 드리프트 가드 테스트(MEMORY.md 상한)로 이관,
워크트리 격리 뒤 발화 0, 발화 뒤 원장 갱신 0 이 근거다(원장 H-03·H-04·H-05~H-08).
"""
import os
import subprocess
import sys
from datetime import datetime

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
from shared_utils import (  # type: ignore[import-not-found]  # noqa: E402
    harness_runtime_path,
    hook_log,
    prepend_session_block,
    read_stdin_json,
    write_stdout_json,
)


def _record_session(session_id: str) -> None:
    """SESSION_LOG.md 맨 위에 새 세션 블록을 삽입하고 최신 20블록만 유지한다.

    포맷·로테이션은 공용 유틸(`hook_log_utils.prepend_session_block`)에 위임한다.

    파라미터:
        session_id: 세션 식별자 앞 8자.
    반환: 없음.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prepend_session_block(harness_runtime_path("SESSION_LOG.md"), session_id, timestamp)


_DRIFT_TIMEOUT_S = 10


def _deploy_drift_note() -> str:
    """머지됐는데 Railway 가 배포하지 않은 커밋이 있으면 한 줄로 알린다.

    2026-09-22: PR #414 머지 이벤트를 Railway 가 흘려 1시간 13분간 운영이 옛 코드로
    돌았다. CI 는 green, 브랜치는 정상, 실패는 없었다 — **저장소에는 아무 신호가 없다.**
    push 훅은 `git push`·`gh pr merge` 만 잡으므로 **브라우저 Merge 버튼으로 머지하면
    아무도 안 본다.** 세션 시작에 한 번 대조해 그 구멍을 덮는다.

    예약 작업(GitHub Actions)으로 만들지 않은 이유: Railway 토큰은 배포·환경변수 변경
    권한까지 있어 DB 비번보다 세고, 이 저장소는 "운영 접속 정보를 GitHub 에 두지 않는다"를
    이미 결정했다(drift-audit-daily.yml 주석). 로컬 토큰으로 세션 시작에 한 번 보는 쪽이
    자격증명을 옮기지 않고 대부분을 덮는다. 재발이 확인되면 그때 예약을 따로 결정한다.

    판정 불가(토큰 없음·오프라인·CLI 없음)는 **조용히 넘긴다** — 세션마다 잡음을 내면
    사람이 훅 전체를 무시하게 된다. 침묵은 "배포가 일치한다"는 주장이 아니며, 사유는
    hook_log 에 남긴다. 실패는 전부 fail-open.
    """
    root = os.path.dirname(os.path.dirname(_dir))
    tool = os.path.join(root, "tools", "ops", "check_deploy_drift.py")
    if not os.path.exists(tool):
        return ""
    try:
        proc = subprocess.run(
            [sys.executable, tool],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_DRIFT_TIMEOUT_S,
        )
    except Exception as exc:  # noqa: BLE001 - fail-open
        hook_log(f"deploy drift 건너뜀: {type(exc).__name__}: {exc}", tag="session_start")
        return ""
    if proc.returncode == 0:
        return ""
    if proc.returncode != 1:
        hook_log(f"deploy drift 판정 불가(exit {proc.returncode}): {proc.stderr.strip()[:200]}", tag="session_start")
        return ""
    detail = " / ".join(line.strip() for line in proc.stdout.splitlines() if line.strip())[:600]
    return (
        "[DEPLOY-DRIFT] 머지됐는데 Railway 가 배포하지 않은 커밋이 있다 — "
        f"{detail}. 사용자에게 알리고, 먼저 처리할지 물어라. "
        "재확인: `python tools/ops/check_deploy_drift.py`."
    )


def _build_context(source: str) -> str:
    """SessionStart additionalContext 텍스트를 조립한다.

    정적 RPI/AI_STATUS 안내는 CLAUDE.md와 중복이라 제거했다(2026-08-03 하네스
    ablation). compact 재개 시점의 체크포인트 포인터만 조건부로 주입한다.

    파라미터:
        source: "startup"|"resume"|"clear"|"compact" 중 하나.
    반환: 주입할 안내 문자열(없으면 빈 문자열).
    """
    if source == "compact":
        return (
            "[SYSTEM] 컨텍스트 압축 후 재개입니다 — 먼저 "
            "docs/harness/runtime/COMPACT_CHECKPOINT.md를 읽어 직전 작업을 복원하세요."
        )
    if source in ("startup", "resume"):
        return _deploy_drift_note()
    return ""


def main() -> None:
    """SessionStart 페이로드를 처리하고 additionalContext를 주입한다."""
    payload = read_stdin_json()
    try:
        session_id = str(payload.get("session_id") or "unknown")[:8]
        source = str(payload.get("source") or "startup")
        _record_session(session_id)
        context = _build_context(source)
        if context:
            write_stdout_json(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": context,
                    }
                }
            )
    except Exception as exc:  # noqa: BLE001 - fail-open + 로그
        hook_log(f"session_start fail-open: {type(exc).__name__}: {exc}", tag="session_start")
    sys.exit(0)


if __name__ == "__main__":
    main()
