"""셸 명령 위험도 판정 공유 정책 (Claude/Cursor guard 훅 공통 소비).

핵심 설계 (재작성 배경 = 부분문자열 매칭 오탐/우회 제거):
  - **argv 토큰화 기반** 판정. 부분문자열(substring) 스캔을 폐기해
    `echo 'drop table 메모'` 같은 무해한 명령의 오탐을 차단한다.
  - 복합 명령(`&&`, `||`, `;`, `|`)은 세그먼트로 분해 후 각각 판정하고
    **최고 위험도**를 채택한다.
  - `git push` refspec을 파싱해 `HEAD:production`·`x:production`·plain
    `production` 도달을 감지하고, force 플래그(`-f`/`--force`/
    `--force-with-lease`/`+refspec`)는 위치와 무관하게 감지한다.

공개 API:
    classify_command(command: str) -> tuple[str, str]
        반환 (decision, label). decision ∈ {"deny", "ask", "allow"}.
        label 은 로그/사유 표기용 한글 요약(allow 는 빈 문자열).
"""
from __future__ import annotations

import re
import shlex

# ---------------------------------------------------------------------------
# 상수: 보호 브랜치 · 안전 명령 집합
# ---------------------------------------------------------------------------

#: force push 가 절대 금지되는 보호 브랜치 (도달 시 deny).
PROTECTED_FORCE_BRANCHES: frozenset[str] = frozenset(
    {"main", "master", "deploy", "production"}
)

#: plain push 라도 사용자 명시 승인이 필요한 브랜치 (도달 시 ask).
#: CLAUDE.md 절대규칙: production push 는 사용자 명시 요청 시에만.
APPROVAL_REQUIRED_BRANCHES: frozenset[str] = frozenset({"production"})

#: 인자를 데이터로만 취급하는(실행하지 않는) 명령 — 내용 패턴 미적용.
CONTENT_SAFE_COMMANDS: frozenset[str] = frozenset(
    {
        "echo", "printf", "print",
        "rg", "grep", "egrep", "fgrep", "ag", "ack",
        "cat", "less", "more", "head", "tail",
        "select-string", "write-output", "write-host",
    }
)

#: DB 클라이언트 — SQL 인자 안의 파괴 구문을 컨텍스트로 판정.
DB_CLIENTS: frozenset[str] = frozenset(
    {"psql", "mysql", "mysqldump", "mariadb", "sqlite3", "mongo", "mongosh", "cockroach"}
)

#: git 전역 옵션 중 뒤 토큰을 값으로 소비하는 플래그 (subcommand 위치 보정).
_GIT_GLOBAL_VALUE_FLAGS: frozenset[str] = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix"}
)

_FORCE_FLAGS: frozenset[str] = frozenset({"-f", "--force"})

# 위험도 우선순위 (복합 명령에서 최고 위험 채택용).
_RISK_ORDER = {"allow": 0, "ask": 1, "deny": 2}


# ---------------------------------------------------------------------------
# 저수준 파서
# ---------------------------------------------------------------------------

def _split_segments(command: str) -> list[str]:
    """복합 셸 명령을 연산자(`&&`,`||`,`;`,`|`) 경계로 분해한다.

    따옴표 내부의 연산자 문자는 분해하지 않는다.

    파라미터:
        command: 원본 명령 문자열.
    반환: 공백 정리된 비어있지 않은 세그먼트 리스트.
    """
    segments: list[str] = []
    buf: list[str] = []
    in_single = in_double = False
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if in_single:
            buf.append(ch)
            if ch == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            buf.append(ch)
            if ch == '"':
                in_double = False
            i += 1
            continue
        if ch == "'":
            in_single = True
            buf.append(ch)
            i += 1
            continue
        if ch == '"':
            in_double = True
            buf.append(ch)
            i += 1
            continue
        if ch == ";":
            segments.append("".join(buf))
            buf = []
            i += 1
            continue
        if ch == "&" and i + 1 < n and command[i + 1] == "&":
            segments.append("".join(buf))
            buf = []
            i += 2
            continue
        if ch == "|" and i + 1 < n and command[i + 1] == "|":
            segments.append("".join(buf))
            buf = []
            i += 2
            continue
        if ch == "|":
            segments.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    segments.append("".join(buf))
    return [s.strip() for s in segments if s.strip()]


def _tokenize(segment: str) -> list[str]:
    """세그먼트를 argv 토큰으로 분해한다 (Windows 경로 보존 위해 posix=False).

    posix=False 는 백슬래시를 이스케이프로 취급하지 않아 `C:\\path` 가 보존된다.
    파싱 실패(따옴표 불균형 등) 시 단순 공백 분해로 폴백한다.
    """
    try:
        return shlex.split(segment, posix=False)
    except ValueError:
        return segment.split()


def _strip_quotes(token: str) -> str:
    """토큰을 감싼 짝맞는 따옴표 한 겹을 제거한다."""
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    return token


def _command_name(tokens: list[str]) -> str:
    """첫 토큰에서 실행 파일 이름(경로/확장자 제거, 소문자)을 추출한다."""
    if not tokens:
        return ""
    first = _strip_quotes(tokens[0]).replace("\\", "/")
    base = first.rsplit("/", 1)[-1]
    if base.lower().endswith(".exe"):
        base = base[:-4]
    return base.lower()


def _git_subcommand_index(tokens: list[str]) -> int | None:
    """전역 옵션(`-C dir` 등)을 건너뛰고 git subcommand 토큰 인덱스를 반환."""
    i = 1
    while i < len(tokens):
        tok = _strip_quotes(tokens[i])
        if tok.startswith("-"):
            i += 2 if tok in _GIT_GLOBAL_VALUE_FLAGS else 1
            continue
        return i
    return None


def _refspec_dest(refspec: str) -> str:
    """push refspec(`src:dst`/`dst`/`+dst`/`refs/heads/dst`)에서 목적지 브랜치명 추출."""
    ref = refspec.lstrip("+")
    dst = ref.split(":", 1)[1] if ":" in ref else ref
    if dst.startswith("refs/heads/"):
        dst = dst[len("refs/heads/"):]
    elif dst.startswith("refs/"):
        dst = dst.rsplit("/", 1)[-1]
    return dst.lower()


# ---------------------------------------------------------------------------
# git subcommand 판정기
# ---------------------------------------------------------------------------

def _classify_git_push(tokens: list[str], push_idx: int) -> tuple[str, str]:
    """`git push` 위험도 판정 (force·production 도달 감지).

    파라미터:
        tokens: 따옴표 제거된 argv 토큰.
        push_idx: 'push' 토큰의 인덱스.
    반환: (decision, label).
    """
    rest = tokens[push_idx + 1:]
    has_force = False
    positionals: list[str] = []
    for tok in rest:
        if tok.startswith("-"):
            if tok in _FORCE_FLAGS or tok.startswith("--force"):
                has_force = True
            continue
        if tok.startswith("+"):  # `+refspec` = force push refspec
            has_force = True
        positionals.append(tok)

    # 첫 positional 은 remote, 나머지는 refspec.
    refspecs = positionals[1:] if len(positionals) >= 2 else []
    targets = {_refspec_dest(r) for r in refspecs}

    if has_force:
        if targets & PROTECTED_FORCE_BRANCHES:
            hit = ", ".join(sorted(targets & PROTECTED_FORCE_BRANCHES))
            return "deny", f"보호 브랜치 강제 푸시({hit})"
        return "ask", "강제 푸시(대상 확인 필요)"

    if targets & APPROVAL_REQUIRED_BRANCHES:
        return "ask", "production 푸시(사용자 승인 필요)"
    return "allow", ""


def _classify_git_reset(tokens: list[str], reset_idx: int) -> tuple[str, str]:
    """`git reset` 위험도 판정 (--hard + origin 대상 = 로컬 파괴)."""
    rest = tokens[reset_idx + 1:]
    if not any(t == "--hard" for t in rest):
        return "allow", ""
    for tok in rest:
        low = tok.lower()
        if low == "origin" or low.startswith("origin/"):
            return "deny", "reset --hard origin(로컬 커밋 파괴)"
    return "ask", "reset --hard(로컬 변경 폐기)"


def _classify_git_clean(tokens: list[str], clean_idx: int) -> tuple[str, str]:
    """`git clean` 위험도 판정 (force 플래그 = untracked 파괴 삭제)."""
    for tok in tokens[clean_idx + 1:]:
        if tok == "--force":
            return "deny", "git clean 강제 삭제"
        if re.fullmatch(r"-[a-eg-z]*f[a-eg-z]*", tok):  # 단일 대시 클러스터에 f 포함
            return "deny", "git clean 강제 삭제"
    return "allow", ""


def _classify_git_checkout(tokens: list[str], checkout_idx: int) -> tuple[str, str]:
    """`git checkout -- <path>` (작업트리 변경 폐기) = ask."""
    if any(t == "--" for t in tokens[checkout_idx + 1:]):
        return "ask", "checkout -- (작업 변경 폐기)"
    return "allow", ""


def _classify_git(tokens: list[str]) -> tuple[str, str]:
    """git 명령 디스패처."""
    idx = _git_subcommand_index(tokens)
    if idx is None:
        return "allow", ""
    sub = _strip_quotes(tokens[idx]).lower()
    if sub == "push":
        return _classify_git_push(tokens, idx)
    if sub == "reset":
        return _classify_git_reset(tokens, idx)
    if sub == "clean":
        return _classify_git_clean(tokens, idx)
    if sub == "checkout":
        return _classify_git_checkout(tokens, idx)
    return "allow", ""


# ---------------------------------------------------------------------------
# 비-git 명령 판정기
# ---------------------------------------------------------------------------

def _has_flag(tokens: list[str], *names: str) -> bool:
    """토큰에 지정 플래그(정확 일치)가 존재하는지."""
    lowered = {t.lower() for t in tokens}
    return any(n in lowered for n in names)


def _classify_rm(tokens: list[str]) -> tuple[str, str]:
    """`rm` 위험도 판정 (재귀+강제 + 루트/상위/드라이브 대상 = deny)."""
    recursive_force = False
    for tok in tokens[1:]:
        if tok.startswith("--"):
            continue
        if re.fullmatch(r"-[a-z]*", tok, re.IGNORECASE):
            has_r = bool(re.search(r"r", tok, re.IGNORECASE))
            has_f = "f" in tok
            if has_r and has_f:
                recursive_force = True
    if _has_flag(tokens, "--recursive") and _has_flag(tokens, "--force"):
        recursive_force = True
    if not recursive_force:
        return "allow", ""
    for tok in tokens[1:]:
        target = _strip_quotes(tok)
        if target.startswith("-"):
            continue
        low = target.lower()
        if (
            low in ("/", "\\", "~", ".", "..", "*", "/*")
            or low.startswith(("/", "\\", "../", "..\\", "~/"))
            or low == ".."
            or re.fullmatch(r"[a-z]:[\\/]?", low)
        ):
            return "deny", "rm 재귀 삭제(루트/상위 경로)"
    return "allow", ""


def _classify_powershell_remove(tokens: list[str]) -> tuple[str, str]:
    """PowerShell `Remove-Item -Recurse -Force` = ask, `del /s /q <drive>` = deny."""
    name = _command_name(tokens)
    if name in ("remove-item", "ri", "rmdir", "rd"):
        recurse = _has_flag(tokens, "-recurse", "-r")
        force = _has_flag(tokens, "-force")
        if recurse and force:
            return "ask", "Remove-Item 재귀 강제 삭제"
        return "allow", ""
    if name in ("del", "erase"):
        flags = {t.lower() for t in tokens[1:]}
        if "/s" in flags and "/q" in flags:
            for tok in tokens[1:]:
                if re.fullmatch(r"[a-z]:[\\/]?", _strip_quotes(tok).lower()):
                    return "deny", "재귀 강제 삭제(del /s /q)"
        return "allow", ""
    return "allow", ""


def _classify_db_sql(segment_lower: str) -> tuple[str, str]:
    """SQL 파괴 구문(drop database/table, truncate table, 무조건 DELETE) 판정."""
    if re.search(r"\bdrop\s+(database|table)\b", segment_lower):
        return "deny", "DB 파괴 명령(drop)"
    if re.search(r"\btruncate\s+table\b", segment_lower):
        return "deny", "DB 파괴 명령(truncate)"
    if re.search(r"\bdelete\s+from\s+\w+\s*;?\s*$", segment_lower):
        return "deny", "무조건 DELETE"
    return "allow", ""


def _classify_pip(tokens: list[str]) -> tuple[str, str]:
    """`pip install` (requirements 파일 외) = ask."""
    lowered = [t.lower() for t in tokens]
    if "install" not in lowered:
        return "allow", ""
    if _has_flag(tokens, "-r", "--requirement") or any(
        t.lower().startswith("--requirement=") for t in tokens
    ):
        return "allow", ""
    return "ask", "pip install(requirements 외)"


def _classify_npm(tokens: list[str]) -> tuple[str, str]:
    """`npm install -g` 등 전역 설치 = ask."""
    lowered = [t.lower() for t in tokens]
    if not ({"install", "i", "add"} & set(lowered)):
        return "allow", ""
    if _has_flag(tokens, "-g", "--global"):
        return "ask", "전역 패키지 설치"
    return "allow", ""


# ---------------------------------------------------------------------------
# 세그먼트 · 최상위 판정
# ---------------------------------------------------------------------------

def _classify_segment(segment: str) -> tuple[str, str]:
    """단일 명령 세그먼트의 위험도를 판정한다."""
    tokens_raw = _tokenize(segment)
    if not tokens_raw:
        return "allow", ""
    tokens = [_strip_quotes(t) for t in tokens_raw]
    name = _command_name(tokens_raw)
    segment_lower = segment.lower()

    # 내용-안전 명령(echo/grep 등)은 인자를 데이터로만 취급 → 즉시 allow.
    if name in CONTENT_SAFE_COMMANDS:
        return "allow", ""

    if name == "git":
        return _classify_git(tokens)

    if name == "rm":
        return _classify_rm(tokens)

    if name in ("remove-item", "ri", "rmdir", "rd", "del", "erase"):
        return _classify_powershell_remove(tokens)

    if name in ("pip", "pip3") or (
        name in ("python", "python3", "py") and "pip" in [t.lower() for t in tokens]
    ):
        return _classify_pip(tokens)

    if name in ("npm", "pnpm", "yarn"):
        return _classify_npm(tokens)

    if name == "format":
        for tok in tokens[1:]:
            if re.fullmatch(r"[a-z]:", _strip_quotes(tok).lower()):
                return "deny", "드라이브 포맷"
        return "allow", ""

    # 원시 SQL(첫 토큰이 SQL 동사) 또는 DB 클라이언트 컨텍스트.
    if name in ("drop", "truncate", "delete") or name in DB_CLIENTS:
        decision, label = _classify_db_sql(segment_lower)
        if decision != "allow":
            return decision, label

    return "allow", ""


def classify_command(command: str) -> tuple[str, str]:
    """셸 명령 전체의 위험도를 판정한다.

    복합 명령은 세그먼트로 분해해 각각 판정하고 최고 위험도를 채택한다.

    파라미터:
        command: 판정할 원본 명령 문자열.
    반환:
        (decision, label) 튜플. decision ∈ {"deny","ask","allow"}.
        label 은 로그/사유용 한글 요약(allow 시 빈 문자열).
    """
    if not command or not isinstance(command, str):
        return "allow", ""

    normalized = re.sub(r"\s+", " ", command.replace("\r", " ").replace("\n", " ")).strip()
    if not normalized:
        return "allow", ""

    best_decision, best_label = "allow", ""
    for segment in _split_segments(normalized):
        decision, label = _classify_segment(segment)
        if _RISK_ORDER[decision] > _RISK_ORDER[best_decision]:
            best_decision, best_label = decision, label
            if best_decision == "deny":
                break
    return best_decision, best_label
