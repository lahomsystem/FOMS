"""AI_STATUS 섹션 필터 + COMPACT_CHECKPOINT 본문 조립 SSOT.

`.claude/hooks/pre_compact.py`·`.cursor/hooks/pre_compact.py` 쌍둥이가 같은
`docs/harness/runtime/COMPACT_CHECKPOINT.md`를 쓰므로, 필터뿐 아니라 본문 조립도
여기 한 곳에 둔다(둘 중 어느 쪽이 마지막에 써도 내용이 동일해야 함).

모든 함수는 fail-open: 파일 부재·파싱 실패·git 부재 시 예외 대신 빈 값을 반환한다.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime

# "## 진행 중" 항목 중 이 마커가 본문에 있으면 죽은 항목 → 체크포인트에서 제외
DONE_MARKER = "**종료**"

# Stop 게이트(quality_check)가 소비하는 미검증 .py 상태 파일 (track_edits가 기록)
PENDING_VERIFY_REL = ("docs", "harness", "runtime", ".claude_pending_verify.json")


def read_active_tasks(ai_status_path: str) -> list[str]:
    """AI_STATUS.md "## 진행 중" 섹션에서 살아있는 항목 라인만 반환한다.

    파라미터:
        ai_status_path: docs/AI_STATUS.md 절대 경로.
    반환: 진행 중 작업 라인 리스트(`**종료**` 포함 라인 제외). 실패 시 빈 리스트.
    """
    tasks: list[str] = []
    try:
        with open(ai_status_path, "r", encoding="utf-8") as handle:
            in_progress = False
            for line in handle:
                if "## 진행 중" in line:
                    in_progress = True
                    continue
                if in_progress and line.startswith("## "):
                    break
                stripped = line.strip()
                if not in_progress or not stripped or stripped == "(없음)":
                    continue
                if DONE_MARKER in line:
                    continue
                tasks.append(line.rstrip())
    except (OSError, ValueError):
        return []
    return tasks


def _git(project_root: str, args: list[str]) -> str:
    """git 서브커맨드를 5초 제한으로 실행해 stdout(strip)을 반환한다.

    파라미터:
        project_root: git 명령을 실행할 작업 디렉터리.
        args: `git` 뒤에 붙일 인자 리스트.
    반환: 성공 시 stdout, 실패·타임아웃·git 부재 시 빈 문자열(fail-open).
    """
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def read_git_state(project_root: str) -> tuple[str, list[str]]:
    """현재 브랜치·HEAD SHA 한 줄과 최근 커밋 5건(제목 포함)을 반환한다.

    파라미터:
        project_root: 저장소 루트 절대 경로.
    반환: (브랜치/HEAD 요약 문자열, "- <sha> <제목>" 라인 리스트).
    """
    branch = _git(project_root, ["branch", "--show-current"])
    head = _git(project_root, ["rev-parse", "--short", "HEAD"])
    summary = f"{branch or '(unknown)'} @ {head or '(unknown)'}"
    log = _git(project_root, ["log", "--oneline", "-5"])
    commits = [f"- {line.rstrip()}" for line in log.splitlines() if line.strip()]
    return summary, commits


def read_pending_verify(project_root: str) -> list[str]:
    """Stop 게이트 pending 상태 파일에서 미검증 `.py` 목록을 반환한다.

    파라미터:
        project_root: 저장소 루트 절대 경로.
    반환: "- `경로`" 라인 리스트. 파일 부재·파싱 실패 시 빈 리스트.
    """
    path = os.path.join(project_root, *PENDING_VERIFY_REL)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, ValueError):
        return []
    files = state.get("files") if isinstance(state, dict) else None
    if not isinstance(files, list):
        return []
    return [f"- `{item}`" for item in files if isinstance(item, str)]


def build_compact_checkpoint(
    project_root: str, session_id: str, recent_edits: list[str]
) -> str:
    """COMPACT_CHECKPOINT.md 본문을 조립한다(`.claude`·`.cursor` 공용).

    파라미터:
        project_root: 저장소 루트 절대 경로.
        session_id: 세션 식별자 원본(표시만 앞 8자로 절단).
        recent_edits: EDIT_LOG에서 뽑은 "- `경로`" 라인 리스트.
    반환: 체크포인트 마크다운 문자열.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    branch_summary, commits = read_git_state(project_root)
    pending = read_pending_verify(project_root)
    active_tasks = read_active_tasks(os.path.join(project_root, "docs", "AI_STATUS.md"))
    none = "(없음)"
    return f"""# Context Compact Checkpoint

> **경고**: 컨텍스트 압축이 발생했습니다. 이 파일을 읽어 이전 작업을 복원하세요.
> 생성 시각: {timestamp}
> 세션: {str(session_id)[:8]}

## 압축 직전 상태

### 브랜치 / HEAD
{branch_summary}

### 최근 커밋 (git log --oneline -5)
{chr(10).join(commits) if commits else none}

### 최근 편집된 파일
{chr(10).join(recent_edits) if recent_edits else none}

### 미검증 `.py` (Stop 게이트 pending)
{chr(10).join(pending) if pending else none}

### 진행 중이던 작업
{chr(10).join(active_tasks) if active_tasks else none}

## 복원 지침

이 파일이 압축 복원의 전부다.
AI_STATUS 등 추가 문서를 통째로 재독하지 마라(필요하면 특정 키워드만 grep).
"""
