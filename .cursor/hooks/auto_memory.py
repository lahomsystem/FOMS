"""
AI 자동 메모리: 세션 종료 시 docs/AI_STATUS.md와 docs/AI_CHANGELOG.md를 자동 업데이트.
Cursor Hook (stop) 에서 호출됩니다.

핵심 로직:
1. .cursor/hooks/track_edits.py 가 기록한 EDIT_LOG.md에서 이번 세션 편집 파일 수집
2. AI_STATUS.md의 "자동 업데이트" 날짜를 오늘로 갱신
3. AI_CHANGELOG.md에 편집 파일 목록 추가 (20개 FIFO)
"""
import os
import re
from datetime import datetime

from shared_utils import harness_runtime_path


def get_project_root():
    """프로젝트 루트 경로 반환"""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read_file(path):
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def get_recent_edited_files(project_root, limit=5):
    """EDIT_LOG.md에서 최근 편집 파일 목록 추출"""
    edit_log = harness_runtime_path(project_root, "EDIT_LOG.md")
    if not os.path.exists(edit_log):
        return []
    files = []
    seen = set()
    with open(edit_log, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("- `"):
                continue
            try:
                fname = line.split("`")[1]
            except IndexError:
                continue
            if fname in seen or fname == "unknown":
                continue
            # docs/, .cursor/ 등 메타파일 제외
            if any(fname.startswith(p) for p in ("docs/", ".cursor/", ".agents/", ".git/")):
                continue
            seen.add(fname)
            files.append(fname)
            if len(files) >= limit:
                break
    return files


def get_last_commit_hash(project_root):
    """최근 커밋 해시 앞 7자리"""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "log", "-1", "--format=%h"],
            cwd=project_root,
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() or "-"
    except Exception:
        return "-"


def update_ai_status(project_root, edited_files):
    """docs/AI_STATUS.md의 날짜와 마지막 작업 정보 갱신"""
    status_path = os.path.join(project_root, "docs", "AI_STATUS.md")
    content = read_file(status_path)
    if not content:
        return

    today = datetime.now().strftime("%Y-%m-%d")

    # 헤더의 자동 업데이트 날짜 갱신
    content = re.sub(
        r"(> 자동 업데이트: )\S+",
        rf"\g<1>{today}",
        content,
        count=1
    )

    write_file(status_path, content)


def update_ai_changelog(project_root, edited_files):
    """docs/AI_CHANGELOG.md에 이번 세션 편집 이력 추가 (20개 FIFO)"""
    changelog_path = os.path.join(project_root, "docs", "AI_CHANGELOG.md")
    content = read_file(changelog_path)
    if not content:
        return

    if not edited_files:
        return

    today = datetime.now().strftime("%Y-%m-%d")
    commit_hash = get_last_commit_hash(project_root)
    files_str = ", ".join(os.path.basename(f) for f in edited_files[:3])
    if len(edited_files) > 3:
        files_str += f" 외 {len(edited_files) - 3}개"

    new_row = f"| {today} | 세션 자동 기록 | {files_str} | {commit_hash} |"

    lines = content.split("\n")
    table_start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("| 날짜"):
            table_start = i
            break
    if table_start is None:
        return

    sep_idx = table_start + 1
    if sep_idx >= len(lines) or not lines[sep_idx].strip().startswith("|-"):
        return

    prefix = lines[:table_start]
    header_block = lines[table_start : sep_idx + 1]
    row_idx = sep_idx + 1
    table_rows: list[str] = []
    j = row_idx
    while j < len(lines):
        stripped = lines[j].strip()
        if stripped.startswith("|"):
            table_rows.append(lines[j])
            j += 1
        else:
            break
    suffix = lines[j:]

    # 중복 방지: 오늘 날짜 + 동일 파일 조합이면 스킵
    for row in table_rows:
        if today in row and files_str in row:
            return

    table_rows.insert(0, new_row)
    table_rows = table_rows[:20]

    parts: list[str] = []
    if prefix:
        parts.append("\n".join(prefix))
    parts.append("\n".join(header_block))
    parts.append("\n".join(table_rows))
    if suffix:
        parts.append("\n".join(suffix))
    result = "\n".join(parts)
    if not result.endswith("\n"):
        result += "\n"
    write_file(changelog_path, result)


def run(project_root=None):
    """메인 실행"""
    if not project_root:
        project_root = get_project_root()

    edited_files = get_recent_edited_files(project_root)
    update_ai_status(project_root, edited_files)
    update_ai_changelog(project_root, edited_files)


if __name__ == "__main__":
    run()
