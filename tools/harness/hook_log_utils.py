"""공용 훅 로그 유틸리티 — 런타임 로그 포맷·로테이션 단일 SSOT.

`.claude/hooks/*`(Claude Code)와 `.cursor/hooks/*`(Cursor) 양쪽 하네스 훅이
이 모듈을 import 하여 SESSION_LOG / EDIT_LOG / CLAUDE_HOOK_LOG 의 포맷과
로테이션을 공유한다. 두 하네스가 각자 다른 포맷으로 같은 파일에 기록하던
포맷 충돌·로테이션 역전·무한 성장·트리밖 누수를 근본 차단하는 것이 목적이다.

설계 원칙:
- **SESSION_LOG**: `### Session: <id>` 블록 단일 포맷, newest-first, 최신 20블록 유지.
  session_start=블록 신설(prepend), session_stop=자기 블록 종료 필드 갱신(새 행 append 금지).
- **EDIT_LOG**: `| Time | File | Tool |` 테이블 단일 포맷, 최근 50행 유지.
  읽기는 레거시 리스트 포맷("- `file` <- ...")도 관용 파싱(전환기 호환).
- **CLAUDE_HOOK_LOG**: 라인 append + 300행 캡(`append_with_rotation`).
- 트리밖 경로 판정은 `os.path.commonpath` 기반(startswith prefix 매칭 폐기).
- **로그 쓰기는 파일락 + tmp/`os.replace` 원자 교체**: 동일 워킹트리를 공유하는
  다수 하네스 훅 프로세스(Claude Code · Cursor 동시 창)가 무잠금 read-modify-write
  로 서로의 블록을 유실시켰다(12 writer 중 1 유실 실측). 락 획득 실패는
  fail-open(락 없이 진행 + 사유 기록) — 훅을 절대 블로킹하지 않는다.
"""
from __future__ import annotations

import os
import re
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, Iterator, List, Optional

try:  # Windows 운영 환경
    import msvcrt
except ImportError:  # pragma: no cover - POSIX(CI ubuntu)
    msvcrt = None  # type: ignore[assignment]
try:  # POSIX(CI ubuntu)
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

# --- 상수 (SSOT) -----------------------------------------------------------
SESSION_LOG_MAX_BLOCKS = 20
EDIT_LOG_MAX_ROWS = 50
HOOK_LOG_MAX_LINES = 300
LOCK_SUFFIX = ".lock"
LOCK_TIMEOUT_SEC = 2.0

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HOOK_LOG_PATH = os.path.join(_PROJECT_ROOT, "docs", "harness", "logs", "CLAUDE_HOOK_LOG.md")

SESSION_LOG_SECTION_MARKER = "## 최근 세션\n\n"
SESSION_LOG_NOTE = (
    "이 파일은 하네스 Hooks(Claude Code · Cursor)가 자동 관리합니다. "
    f"최신 {SESSION_LOG_MAX_BLOCKS}세션만 유지."
)
EDIT_LOG_HEADER_LINES = [
    "# Edit Log",
    "",
    f"> 하네스 Hook(Edit/Write · afterFileEdit)이 자동 기록합니다. 최근 {EDIT_LOG_MAX_ROWS}행만 유지.",
    "",
    "| Time | File | Tool |",
    "|------|------|------|",
]

_SESSION_BLOCK_SPLIT = re.compile(r"(?m)^(?=### Session: )")
_SESSION_BLOCK_RE = re.compile(
    r"(?ms)(^### Session: (?P<sid>[^\n]+)\n)(?P<body>.*?)(?=^### Session: |\Z)"
)
_SESSION_BLOCK_ID_RE = re.compile(r"^### Session: ([^\n]*)")


def _now() -> str:
    """현재 시각을 `%Y-%m-%d %H:%M:%S` 문자열로 반환한다."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --- 원자 저장 · 파일락 -----------------------------------------------------
def _ensure_parent(path: str) -> None:
    """`path`의 부모 디렉터리를 만든다(부모가 없는 상대 경로는 no-op)."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _warn(message: str) -> None:
    """모듈 내부 fail-open 사유를 CLAUDE_HOOK_LOG에 한 줄 남긴다.

    `shared_utils.hook_log`는 `append_with_rotation`을 호출하므로 그 함수의 실패를
    거쳐 기록하면 무한 재귀가 된다. 여기서는 로테이션·락 없이 plain append 하고
    (캡은 다음 정상 `append_with_rotation` 호출이 복원한다), 그마저 실패하면
    stderr로 폴백해 조용한 삼킴을 피한다.

    파라미터:
        message: 기록할 사유 문자열.
    반환: 없음.
    """
    line = f"- {_now()} [hook_log_utils] {message}\n"
    try:
        _ensure_parent(_HOOK_LOG_PATH)
        with open(_HOOK_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError as exc:
        try:
            sys.stderr.write(f"hook_log_utils warn failed: {exc} | {line}")
        except (OSError, ValueError):  # pragma: no cover - stderr도 죽은 경우
            pass


def _acquire(fd: int) -> None:
    """열린 fd에 비블로킹 배타 락을 건다(실패 시 OSError)."""
    if msvcrt is not None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    elif fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    else:  # pragma: no cover - 락 프리미티브 없는 플랫폼
        raise OSError("no file locking primitive available")


def _release(fd: int) -> None:
    """`_acquire`로 건 락을 해제한다."""
    if msvcrt is not None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    elif fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def _file_lock(path: str, timeout: float = LOCK_TIMEOUT_SEC) -> Iterator[bool]:
    """`<path>.lock` 락파일로 프로세스 간 배타 구간을 연다(fail-open).

    훅은 어떤 경우에도 블로킹되면 안 되므로, `timeout` 안에 못 잡으면 사유를
    기록하고 **락 없이** 본문을 진행한다(최악의 경우 기존 무잠금 동작으로 퇴화).

    파라미터:
        path: 보호 대상 파일 경로.
        timeout: 락 획득 재시도 상한(초).
    반환(yield): 락을 실제로 잡았으면 True, fail-open 진행이면 False.
    """
    lock_path = path + LOCK_SUFFIX
    fd = -1
    locked = False
    try:
        _ensure_parent(lock_path)
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        deadline = time.monotonic() + timeout
        while True:
            try:
                _acquire(fd)
                locked = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    _warn(f"파일락 타임아웃 — 락 없이 진행: {path}")
                    break
                time.sleep(0.02)
    except OSError as exc:
        _warn(f"파일락 실패 — 락 없이 진행: {path} ({exc})")
    try:
        yield locked
    finally:
        if fd >= 0:
            if locked:
                try:
                    _release(fd)
                except OSError:  # pragma: no cover - 해제 실패는 close가 정리
                    pass
            try:
                os.close(fd)
            except OSError:  # pragma: no cover
                pass


def _atomic_write(path: str, content: str) -> None:
    """tmp 파일에 쓴 뒤 `os.replace`로 교체한다(부분 기록·절단 노출 차단).

    파라미터:
        path: 최종 대상 경로.
        content: 파일 전체 내용.
    반환: 없음.
    """
    _ensure_parent(path)
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(content)
    os.replace(tmp, path)


def _read_text(path: str) -> str:
    """파일 내용을 UTF-8로 읽는다(없으면 빈 문자열)."""
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


# --- 트리 멤버십 -----------------------------------------------------------
def is_within_tree(project_root: str, path: str) -> bool:
    """`path`가 `project_root` 서브트리 안이면 True를 반환한다.

    startswith 상대경로 prefix 매칭은 `../../..` 형태의 트리밖 경로를 놓쳐
    전역 메모리·스크래치패드 편집이 로그·게이트를 오염시켰다. `commonpath`
    기반으로 교정한다. 서로 다른 드라이브(Windows)면 `commonpath`가
    `ValueError`를 던지므로 트리밖으로 판정한다.

    파라미터:
        project_root: 저장소 루트(절대/상대 무관).
        path: 검사할 파일 경로(절대/상대 무관).
    반환: 트리 안이면 True, 밖이거나 판정 불가면 False.
    """
    try:
        root = os.path.abspath(project_root)
        target = os.path.abspath(path)
        return os.path.commonpath([root, target]) == root
    except (ValueError, TypeError):
        return False


# --- 범용 로테이션 로그 ----------------------------------------------------
def append_with_rotation(path: str, entry: str, max_lines: int) -> None:
    """`entry`를 한 줄로 append 하고 최신 `max_lines`줄만 유지한다.

    CLAUDE_HOOK_LOG 처럼 헤더 없는 라인 로그의 무한 성장을 차단한다. 여러 훅
    프로세스가 같은 파일을 동시에 갱신하므로 read-modify-write 전 구간을 파일락으로
    감싸고 원자 교체한다(무잠금이면 동시 append가 서로를 덮어썼다).

    파라미터:
        path: 로그 파일 절대 경로.
        entry: 기록할 한 줄(개행 없으면 자동 추가).
        max_lines: 유지할 최대 줄 수(초과분은 오래된 앞줄부터 절단).
    반환: 없음.
    """
    _ensure_parent(path)
    line = entry if entry.endswith("\n") else entry + "\n"
    with _file_lock(path):
        lines = _read_text(path).splitlines(keepends=True)
        lines.append(line)
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
        _atomic_write(path, "".join(lines))


# --- SESSION_LOG 블록 관리 -------------------------------------------------
def build_session_header() -> str:
    """SESSION_LOG의 통일 헤더(마커 `## 최근 세션` 포함)를 반환한다."""
    return f"# Session Log\n\n> {SESSION_LOG_NOTE}\n\n{SESSION_LOG_SECTION_MARKER}"


def format_session_block(session_id: str, timestamp: str) -> str:
    """진행중 상태의 새 세션 블록 문자열을 조립한다.

    파라미터:
        session_id: 세션 식별자(보통 앞 8자).
        timestamp: 시작 시각 문자열.
    반환: `### Session:` 블록(끝에 빈 줄 포함) 문자열.
    """
    return (
        f"### Session: {session_id}\n"
        f"- **시작**: {timestamp}\n"
        f"- **상태**: 진행중\n"
        f"- **편집 파일**: (기록 중)\n"
        f"- **종료**: -\n\n"
    )


def _split_blocks(body: str) -> List[str]:
    """`## 최근 세션` 이후 본문을 개별 `### Session:` 블록 리스트로 분리한다.

    `### Session:`로 시작하지 않는 잔여물(레거시 END 테이블 행 등)은 폐기한다.
    순서(newest-first)는 보존한다.
    """
    parts = _SESSION_BLOCK_SPLIT.split(body)
    return [p for p in parts if p.lstrip().startswith("### Session:")]


def _block_session_id(block: str) -> str:
    """`_split_blocks` 산출 블록 문자열에서 세션 id를 뽑는다(없으면 빈 문자열)."""
    match = _SESSION_BLOCK_ID_RE.match(block.lstrip())
    return match.group(1).strip() if match else ""


def prepend_session_block(
    path: str,
    session_id: str,
    timestamp: Optional[str] = None,
    *,
    max_blocks: int = SESSION_LOG_MAX_BLOCKS,
) -> None:
    """새 세션 블록을 맨 위(newest-first)에 삽입하고 최신 `max_blocks`만 유지한다.

    **동일 session_id의 기존 블록은 흡수(제거 후 재삽입)한다**: resume/clear/compact
    시 SessionStart가 같은 id로 재발화해 블록이 중복 생성되고, Stop은 최신 블록
    하나만 갱신하므로 옛 블록이 영구 "진행중"으로 남던 것이 근본 원인이다.

    헤더는 통일 포맷으로 재작성한다. 기존 파일의 손상된 잔여물(포맷 충돌 행)은
    `_split_blocks`가 폐기하므로 자가 치유된다. 동시 세션 유실 방지를 위해
    읽기-쓰기 전 구간을 파일락으로 감싸고 원자 교체한다.

    파라미터:
        path: SESSION_LOG.md 절대 경로.
        session_id: 세션 식별자.
        timestamp: 시작 시각(None이면 현재 시각).
        max_blocks: 유지할 최대 블록 수.
    반환: 없음.
    """
    timestamp = timestamp or _now()
    with _file_lock(path):
        existing = _read_text(path)
        body = (
            existing.split(SESSION_LOG_SECTION_MARKER, 1)[1]
            if SESSION_LOG_SECTION_MARKER in existing
            else ""
        )
        kept = [b for b in _split_blocks(body) if _block_session_id(b) != session_id]
        blocks = ([format_session_block(session_id, timestamp)] + kept)[:max_blocks]
        _atomic_write(path, build_session_header() + "".join(blocks))


def _replace_field(body: str, label: str, value: str) -> str:
    """세션 블록 본문에서 `- **label**: ...` 줄을 교체하거나 없으면 추가한다."""
    pattern = rf"(?m)^- \*\*{re.escape(label)}\*\*: .*$"
    new_line = f"- **{label}**: {value}"
    if re.search(pattern, body):
        return re.sub(pattern, new_line, body, count=1)
    if not body.endswith("\n"):
        body += "\n"
    return body + new_line + "\n"


def _find_block(content: str, session_id: str) -> Optional[re.Match]:
    """session_id에 **정확히** 해당하는 블록 매치를 찾는다(없으면 None).

    폴백("열린 블록 아무거나" → `matches[0]`)은 제거했다. 여러 창이 같은 워킹트리를
    공유하므로, id 미상/미매치 시 폴백은 **타 세션의 live 블록을 "완료"로 clobber**
    하는 벡터였다(재현 확인). 대상이 없으면 호출측이 no-op 하는 것이 정답이다.

    파라미터:
        content: SESSION_LOG 전체 내용.
        session_id: 찾을 세션 식별자(빈 값·`unknown`이면 항상 None).
    반환: 매칭된 `re.Match` 또는 None.
    """
    if not session_id or session_id == "unknown":
        return None
    for match in _SESSION_BLOCK_RE.finditer(content):
        if match.group("sid").strip() == session_id:
            return match
    return None


def update_session_block(
    path: str, session_id: str, field_updates: Dict[str, str]
) -> bool:
    """자기 세션 블록의 필드를 갱신한다(새 행 append 금지).

    자기 id 블록이 없으면 **no-op + 사유 기록**이다(타 세션 블록으로 폴백 금지 —
    `_find_block` 참조). 읽기-쓰기 전 구간은 파일락 + 원자 교체로 보호한다.

    파라미터:
        path: SESSION_LOG.md 절대 경로.
        session_id: 갱신 대상 세션 식별자.
        field_updates: {라벨: 값} (예: {"상태": "완료", "종료": ts}).
    반환: 갱신 성공 True, 대상 블록/파일 없으면 False.
    """
    if not os.path.exists(path):
        return False
    with _file_lock(path):
        content = _read_text(path)
        match = _find_block(content, session_id)
        if not match:
            _warn(f"세션 블록 없음 — 갱신 no-op: id={session_id!r}")
            return False
        body = match.group("body")
        for label, value in field_updates.items():
            body = _replace_field(body, label, value)
        updated = content[: match.start()] + match.group(1) + body + content[match.end() :]
        _atomic_write(path, updated)
    return True


def find_open_session_id(path: str) -> Optional[str]:
    """열린(진행중/종료 미기록) 첫 세션의 id를 반환한다(없으면 None).

    payload에 세션 id가 없을 때 session_stop 멱등 dedup 정확도를 높이는 데 쓴다.
    `_find_block`의 "열린 블록" 폴백이 clobber 벡터라 제거됐으므로, 조회 전용인
    이 함수가 자체적으로 훑는다(읽기만 하므로 타 세션을 덮어쓰지 않는다).

    파라미터:
        path: SESSION_LOG.md 절대 경로.
    반환: 열린 세션 id 문자열 또는 None.
    """
    if not os.path.exists(path):
        return None
    for match in _SESSION_BLOCK_RE.finditer(_read_text(path)):
        body = match.group("body")
        if "- **종료**: -" in body or "- **상태**: 진행중" in body:
            return match.group("sid").strip() or None
    return None


def regenerate_session_log(path: str) -> None:
    """SESSION_LOG를 통일 헤더 + 빈 상태로 재생성한다(손상 파일 복구용)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(build_session_header())


# --- EDIT_LOG 테이블 관리 --------------------------------------------------
def _extract_file_from_line(line: str) -> Optional[str]:
    """EDIT_LOG 한 줄에서 파일 경로를 추출한다(테이블·레거시 포맷 모두 관용).

    - 테이블: "| <ts> | `file` | <tool> |"
    - 레거시: "- `file` <- ..."
    둘 다 첫 backtick 쌍 안이 파일 경로다.
    """
    stripped = line.strip()
    if "`" not in stripped:
        return None
    if not (stripped.startswith("| 20") or stripped.startswith("- `")):
        return None
    parts = stripped.split("`")
    if len(parts) >= 2 and parts[1].strip():
        return parts[1].strip()
    return None


def read_recent_edited_files(path: str, limit: int = 10) -> List[str]:
    """EDIT_LOG에서 최근 편집 파일 경로를 newest-first, 중복 제거로 반환한다.

    테이블 포맷은 oldest→newest append 순서이므로 역순으로 훑어 최신을 앞에 둔다.
    레거시 리스트 포맷 줄도 관용 파싱한다(전환기 호환·기존 테스트 유지).

    파라미터:
        path: EDIT_LOG.md 절대 경로.
        limit: 반환할 최대 파일 수.
    반환: 최신순 파일 경로 리스트(최대 `limit`개).
    """
    if not os.path.exists(path):
        return []
    ordered: List[str] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            name = _extract_file_from_line(line)
            if name:
                ordered.append(name)
    files: List[str] = []
    seen = set()
    for name in reversed(ordered):
        if name in seen or name == "unknown":
            continue
        seen.add(name)
        files.append(name)
        if len(files) >= limit:
            break
    return files


def append_edit_row(
    path: str,
    rel_path: str,
    tool_name: str,
    *,
    timestamp: Optional[str] = None,
    dedup_window_sec: int = 300,
    max_rows: int = EDIT_LOG_MAX_ROWS,
) -> bool:
    """EDIT_LOG에 편집 행을 append 한다(정확 컬럼 dedup + 50행 캡).

    같은 파일이 `dedup_window_sec` 이내 가장 최근 행에 있으면 스킵한다. 부분문자열
    매칭이 아니라 File 컬럼 정확 비교로 오탐(`a.py`가 `aa.py`에 매칭)을 막는다.

    파라미터:
        path: EDIT_LOG.md 절대 경로.
        rel_path: 프로젝트 상대 경로(트리밖 판정은 호출자 책임).
        tool_name: Tool 컬럼 값(Edit/Write/Cursor 등).
        timestamp: 기록 시각(None이면 현재 시각).
        dedup_window_sec: 동일 파일 중복 억제 윈도(초).
        max_rows: 유지할 최대 데이터 행 수.
    반환: 기록하면 True, dedup으로 스킵하면 False.
    """
    timestamp = timestamp or _now()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing: List[str] = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as handle:
            existing = handle.readlines()
    data_rows = [ln for ln in existing if ln.startswith("| 20")]

    for row in reversed(data_rows):
        cols = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cols) >= 2 and cols[1].strip("`").strip() == rel_path:
            try:
                last = datetime.strptime(cols[0], "%Y-%m-%d %H:%M:%S")
                if (datetime.now() - last).total_seconds() < dedup_window_sec:
                    return False
            except ValueError:
                pass
            break

    data_rows.append(f"| {timestamp} | `{rel_path}` | {tool_name} |\n")
    if len(data_rows) > max_rows:
        data_rows = data_rows[-max_rows:]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(EDIT_LOG_HEADER_LINES) + "\n")
        handle.writelines(data_rows)
    return True
