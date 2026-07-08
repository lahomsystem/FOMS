"""Claude Code PreCompact hook: 컨텍스트 압축 직전 복원 체크포인트 생성.

stdin으로 {"trigger": "manual"|"auto", "custom_instructions": ..., ...} 페이로드를
받아 docs/harness/runtime/COMPACT_CHECKPOINT.md를 갱신한다. 최근 편집 파일(EDIT_LOG),
AI_STATUS "## 진행 중" 섹션, 복원 지침 6단계를 기록한다. PreCompact는 컨텍스트 주입이
없으므로 파일 부수효과만 남긴다. 실패해도 fail-open(exit 0).
"""
import os
import sys
from datetime import datetime

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
from shared_utils import (  # type: ignore[import-not-found]  # noqa: E402
    get_project_root,
    harness_runtime_path,
    hook_log,
    read_recent_edited_files,
    read_stdin_json,
)


def _recent_edits(project_root: str) -> list[str]:
    """EDIT_LOG.md 테이블에서 최근 편집 파일 경로를 최대 10개 반환한다.

    파싱·순서(newest-first)는 공용 유틸(`read_recent_edited_files`)에 위임한다.

    파라미터:
        project_root: 저장소 루트 절대 경로.
    반환: "- `경로`" 형태 문자열 리스트(가장 최근 10개).
    """
    files = read_recent_edited_files(harness_runtime_path("EDIT_LOG.md"), limit=10)
    return [f"- `{name}`" for name in files]


def _active_tasks(project_root: str) -> list[str]:
    """AI_STATUS.md의 "## 진행 중" 섹션 항목을 반환한다.

    파라미터:
        project_root: 저장소 루트 절대 경로.
    반환: 진행 중 작업 라인 리스트.
    """
    ai_status_path = os.path.join(project_root, "docs", "AI_STATUS.md")
    tasks: list[str] = []
    if not os.path.exists(ai_status_path):
        return tasks
    in_progress = False
    with open(ai_status_path, "r", encoding="utf-8") as handle:
        for line in handle:
            if "## 진행 중" in line:
                in_progress = True
                continue
            if in_progress and line.startswith("## "):
                break
            if in_progress and line.strip() and line.strip() != "(없음)":
                tasks.append(line.rstrip())
    return tasks


def _build_checkpoint(session_id: str, recent_edits: list[str], active_tasks: list[str]) -> str:
    """COMPACT_CHECKPOINT.md 본문을 조립한다.

    파라미터:
        session_id: 세션 식별자 앞 8자.
        recent_edits: 최근 편집 파일 라인.
        active_tasks: 진행 중 작업 라인.
    반환: 체크포인트 마크다운 문자열.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""# Context Compact Checkpoint

> **경고**: 컨텍스트 압축이 발생했습니다. 이 파일을 읽어 이전 작업을 복원하세요.
> 생성 시각: {timestamp}
> 세션: {session_id}

## 압축 직전 상태

### 최근 편집된 파일
{chr(10).join(recent_edits) if recent_edits else '(없음)'}

### 진행 중이던 작업
{chr(10).join(active_tasks) if active_tasks else '(없음)'}

## 복원 지침

1. `docs/AI_STATUS.md` 읽기 → 전체 프로젝트 상태 파악 (50줄)
2. `docs/AI_CHANGELOG.md` 읽기 → 최근 작업 이력 확인
3. `docs/harness/policy/DECISIONS.md` 읽기 → 이전 결정사항 확인
4. `docs/ARCHIVE_INDEX.md` 읽기 → 과거 장애/분석 기록 검색 (키워드 기반)
5. `docs/harness/runtime/EDIT_LOG.md` 읽기 → 최근 편집 파일 확인
6. 핵심 코어 변경 작업이면 RPI 프로토콜(조사→계획→실행)을 따를 것
"""


def main() -> None:
    """PreCompact 페이로드를 처리하고 복원 체크포인트를 기록한다."""
    payload = read_stdin_json()
    try:
        session_id = str(payload.get("session_id") or "unknown")[:8]
        project_root = get_project_root()
        checkpoint_file = harness_runtime_path("COMPACT_CHECKPOINT.md")
        os.makedirs(os.path.dirname(checkpoint_file), exist_ok=True)
        content = _build_checkpoint(
            session_id,
            _recent_edits(project_root),
            _active_tasks(project_root),
        )
        with open(checkpoint_file, "w", encoding="utf-8") as handle:
            handle.write(content)
    except Exception as exc:  # noqa: BLE001 - fail-open + 로그
        hook_log(f"pre_compact fail-open: {type(exc).__name__}: {exc}", tag="pre_compact")
    sys.exit(0)


if __name__ == "__main__":
    main()
