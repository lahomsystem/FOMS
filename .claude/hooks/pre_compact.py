"""Claude Code PreCompact hook: 컨텍스트 압축 직전 복원 체크포인트 생성.

stdin으로 {"trigger": "manual"|"auto", "custom_instructions": ..., ...} 페이로드를
받아 docs/harness/runtime/COMPACT_CHECKPOINT.md를 갱신한다. 브랜치/HEAD, 최근 커밋
5건, 최근 편집 파일(EDIT_LOG), 미검증 `.py`(Stop 게이트 pending), AI_STATUS
"## 진행 중" 생존 항목을 기록한다. 본문 조립·필터는 tools/harness/status_sections.py
(`.cursor` 쌍둥이와 공유)에 위임한다. PreCompact는 컨텍스트 주입이 없으므로 파일
부수효과만 남긴다. 실패해도 fail-open(exit 0).
"""
import os
import sys

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
from shared_utils import (  # type: ignore[import-not-found]  # noqa: E402
    get_project_root,
    harness_runtime_path,
    hook_log,
    read_recent_edited_files,
    read_stdin_json,
)

_TOOLS_HARNESS = os.path.join(get_project_root(), "tools", "harness")
if _TOOLS_HARNESS not in sys.path:
    sys.path.append(_TOOLS_HARNESS)
from status_sections import (  # type: ignore[import-not-found]  # noqa: E402
    build_compact_checkpoint,
)


def _recent_edits() -> list[str]:
    """EDIT_LOG.md 테이블에서 최근 편집 파일 경로를 최대 10개 반환한다.

    파싱·순서(newest-first)는 공용 유틸(`read_recent_edited_files`)에 위임한다.

    반환: "- `경로`" 형태 문자열 리스트(가장 최근 10개).
    """
    files = read_recent_edited_files(harness_runtime_path("EDIT_LOG.md"), limit=10)
    return [f"- `{name}`" for name in files]


def main() -> None:
    """PreCompact 페이로드를 처리하고 복원 체크포인트를 기록한다."""
    payload = read_stdin_json()
    try:
        # 원본 session_id 보관(절단은 표시 시점에만 — 다른 조회에 8자가 새지 않게).
        session_id = str(payload.get("session_id") or "unknown")
        project_root = get_project_root()
        checkpoint_file = harness_runtime_path("COMPACT_CHECKPOINT.md")
        os.makedirs(os.path.dirname(checkpoint_file), exist_ok=True)
        content = build_compact_checkpoint(project_root, session_id, _recent_edits())
        with open(checkpoint_file, "w", encoding="utf-8") as handle:
            handle.write(content)
    except Exception as exc:  # noqa: BLE001 - fail-open + 로그
        hook_log(f"pre_compact fail-open: {type(exc).__name__}: {exc}", tag="pre_compact")
    sys.exit(0)


if __name__ == "__main__":
    main()
