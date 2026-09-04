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

import os
import re
import shlex
import subprocess
import sys

# ---------------------------------------------------------------------------
# 상수: 보호 브랜치 · 안전 명령 집합
# ---------------------------------------------------------------------------

#: force push 가 절대 금지되는 보호 브랜치 (도달 시 deny).
PROTECTED_FORCE_BRANCHES: frozenset[str] = frozenset(
    {"main", "master", "deploy", "production"}
)

#: 세션 worktree 브랜치 프리픽스 (session_worktree.py BRANCH_PREFIX 와 동일).
SESSION_BRANCH_PREFIX = "session/"

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

# classify_command 호출 동안 deploy scope 검사용 컨텍스트(재귀 언랩 공유).
_ctx_project_root: str | None = None
_ctx_session_id: str | None = None

#: 선행 환경변수 할당 토큰(`KEY=VAL`) 패턴 — 실제 명령 앞에서 스킵한다.
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

#: timeout 지속시간 인자(`60`, `1.5s`, `2m`, `1h` 등) 패턴.
_DURATION_RE = re.compile(r"^\d+(?:\.\d+)?[smhd]?$", re.IGNORECASE)

#: 다음 토큰(들)을 그대로 실행하는 단순 래퍼 — 실제 명령까지 토큰을 전진시킨다.
_SIMPLE_WRAPPERS: frozenset[str] = frozenset({"nohup", "xargs"})

#: `-c`/`-lc`/`-Command` 뒤 문자열을 하위 셸로 실행하는 인터프리터.
_SHELL_INTERPRETERS: frozenset[str] = frozenset(
    {"bash", "sh", "zsh", "dash", "ash", "ksh", "pwsh", "powershell"}
)

#: 인터프리터의 "다음 인자를 명령 문자열로 실행" 플래그(소문자 비교).
_SHELL_C_FLAGS: frozenset[str] = frozenset({"-c", "-lc", "-lic", "-ic", "-command"})

#: 래퍼/서브셸/`shell -c` 재귀 언랩 최대 깊이 (무한 재귀 방지).
_MAX_UNWRAP_DEPTH = 5


# ---------------------------------------------------------------------------
# 저수준 파서
# ---------------------------------------------------------------------------

def _split_segments(command: str) -> list[str]:
    """복합 셸 명령을 연산자(`&&`,`||`,`;`,`|`) 및 개행(`\\n`) 경계로 분해한다.

    개행은 `;` 와 동급의 세그먼트 경계다(다줄 명령의 2번째 줄부터 위험 명령이
    첫 명령의 인자로 흡수되는 우회를 차단). 따옴표 내부의 연산자/개행은
    분해하지 않는다.

    파라미터:
        command: 원본 명령 문자열(호출자가 `\\r\\n`/`\\r`→`\\n` 정규화 후 전달).
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
        if ch == ";" or ch == "\n":
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

def _git_out(project_root: str, *args: str) -> str | None:
    """git 명령의 stdout(strip). 실패하거나 출력이 비면 None."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip() or None


def _current_branch(project_root: str) -> str | None:
    """현재 체크아웃 브랜치 이름. 실패 시 None."""
    return _git_out(project_root, "rev-parse", "--abbrev-ref", "HEAD")


def _push_dest_branch(project_root: str) -> str | None:
    """타깃 없는 `git push`가 실제로 갱신할 원격 브랜치명(마지막 컴포넌트, 소문자).

    브랜치 이름만 보면 `session/*` worktree에서 `git push`가 deploy를 갱신하는
    경로(upstream=`origin/deploy` + `push.default=upstream`)를 놓친다.
    `@{push}`(push.default 반영)를 우선 보고 없으면 `@{u}`로 폴백한다.

    파라미터:
        project_root: 저장소(또는 worktree) 루트.
    반환:
        `origin/deploy` → `"deploy"`. upstream 미설정·조회 실패 시 None.
    """
    for ref in ("@{push}", "@{u}"):
        out = _git_out(project_root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", ref)
        if out:
            return out.rsplit("/", 1)[-1].lower()
    return None


def _classify_deploy_push_scope(
    project_root: str | None,
    session_id: str | None,
) -> tuple[str, str]:
    """deploy push 세션 범위 판정. 실패 시 ask(묵시 allow 금지)."""
    if not project_root:
        return "ask", "deploy 푸시(세션 범위 확인 필요)"
    try:
        harness_dir = os.path.dirname(os.path.abspath(__file__))
        if harness_dir not in sys.path:
            sys.path.insert(0, harness_dir)
        from deploy_push_scope import classify_deploy_scope  # type: ignore[import-not-found]

        result = classify_deploy_scope(project_root, session_id)
    except Exception as exc:  # noqa: BLE001 - 판정 실패는 ask 격상
        return "ask", f"deploy 푸시 범위 판정 실패({type(exc).__name__})"
    if result.kind in ("empty", "own"):
        return "allow", ""
    return "ask", result.label or "deploy 푸시(세션 확인 필요)"


def _classify_git_push(
    tokens: list[str],
    push_idx: int,
    *,
    project_root: str | None = None,
    session_id: str | None = None,
) -> tuple[str, str]:
    """`git push` 위험도 판정 (force·production·deploy 세션 범위).

    파라미터:
        tokens: 따옴표 제거된 argv 토큰.
        push_idx: 'push' 토큰의 인덱스.
        project_root: 저장소 루트(deploy scope 검사용, 선택).
        session_id: 현재 세션 id(선택).
    반환: (decision, label).
    """
    rest = tokens[push_idx + 1:]
    has_force = False
    dry_run = False
    positionals: list[str] = []
    for tok in rest:
        if tok.startswith("-"):
            if tok in _FORCE_FLAGS or tok.startswith("--force"):
                has_force = True
            if tok in ("--dry-run", "-n"):
                dry_run = True
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

    if dry_run:
        return "allow", ""

    targets_lower = {t.lower() for t in targets if t}
    if "deploy" in targets_lower:
        return _classify_deploy_push_scope(project_root, session_id)

    if not targets:
        # `git push` / `git push origin` — 현재 브랜치 푸시
        if project_root is None:
            return "ask", "deploy 푸시(세션 범위 확인 필요)"
        branch = _current_branch(project_root)
        if branch is None or branch.lower() == "deploy":
            return _classify_deploy_push_scope(project_root, session_id)
        dest = _push_dest_branch(project_root)
        if dest == "deploy":
            # 브랜치명이 deploy가 아니어도 실효 push 대상이 origin/deploy면 분류 대상.
            return _classify_deploy_push_scope(project_root, session_id)
        if dest is None and branch.lower().startswith(SESSION_BRANCH_PREFIX):
            # 세션 worktree인데 push 대상을 못 읽음 → deploy 도달 가능성 배제 불가.
            return "ask", "세션 브랜치 무refspec 푸시(대상 확인 불가)"
        return "allow", ""

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
        return _classify_git_push(
            tokens,
            idx,
            project_root=_ctx_project_root,
            session_id=_ctx_session_id,
        )
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


#: Remove-Item 파라미터 중 값이 삭제 대상 경로인 플래그.
_PS_REMOVE_PATH_FLAGS: frozenset[str] = frozenset({"-path", "-literalpath"})

#: Remove-Item 파라미터 중 다음 토큰을 값으로 소비하지만 경로가 아닌 플래그.
_PS_REMOVE_VALUE_FLAGS: frozenset[str] = frozenset(
    {
        "-filter", "-include", "-exclude", "-stream",
        "-erroraction", "-warningaction", "-informationaction",
        "-errorvariable", "-warningvariable", "-informationvariable",
        "-outvariable", "-outbuffer", "-pipelinevariable",
    }
)


def _temp_roots() -> frozenset[str]:
    """임시폴더 루트 집합(소문자·슬래시 정규화) — `c:/tmp` + %TEMP%/%TMP%.

    반환: 정규화된 루트 경로 frozenset. 호출 시점 환경변수를 읽는다.
    """
    roots = {"c:/tmp"}
    for var in ("TEMP", "TMP"):
        val = os.environ.get(var, "")
        if val:
            roots.add(val.replace("\\", "/").rstrip("/").lower())
    return frozenset(roots)


def _is_temp_path(target: str) -> bool:
    """대상 경로가 임시폴더 루트의 '하위'인지 판정한다.

    파라미터:
        target: 삭제 대상 경로 토큰(따옴표 포함 가능).
    반환: 루트 하위면 True. 루트 자체·`..` 포함(상위 탈출)·미확정 경로는 False.
    """
    low = _strip_quotes(target).replace("\\", "/").rstrip("/").lower()
    if ".." in low.split("/"):
        return False
    return any(low.startswith(root + "/") for root in _temp_roots())


def _ps_remove_targets(tokens: list[str]) -> list[str]:
    """Remove-Item argv 에서 삭제 대상 경로 토큰만 추출한다.

    파라미터:
        tokens: `Remove-Item ...` argv (첫 토큰 = 명령).
    반환: 대상 경로 리스트(쉼표 다중 지정 분해·따옴표 제거). 스위치 플래그와
        비경로 값 플래그(`-ErrorAction` 등)의 값은 제외한다.
    """
    targets: list[str] = []

    def _add(value: str) -> None:
        for part in value.split(","):
            cleaned = _strip_quotes(part.strip())
            if cleaned:
                targets.append(cleaned)

    i = 1
    while i < len(tokens):
        tok = _strip_quotes(tokens[i])
        low = tok.lower()
        if low in _PS_REMOVE_PATH_FLAGS:
            if i + 1 < len(tokens):
                _add(_strip_quotes(tokens[i + 1]))
            i += 2
            continue
        if low in _PS_REMOVE_VALUE_FLAGS:
            i += 2
            continue
        if tok.startswith("-"):
            i += 1
            continue
        _add(tok)
        i += 1
    return targets


def _classify_powershell_remove(tokens: list[str]) -> tuple[str, str]:
    """PowerShell `Remove-Item -Recurse -Force` = ask, `del /s /q <drive>` = deny.

    예외: 삭제 대상 전부가 임시폴더(`c:/tmp`·%TEMP%·%TMP%) 하위면 allow
    (세션 worktree 청소 등 반복 케이스 — 루트 자체 삭제는 여전히 ask).
    """
    name = _command_name(tokens)
    if name in ("remove-item", "ri", "rmdir", "rd"):
        recurse = _has_flag(tokens, "-recurse", "-r")
        force = _has_flag(tokens, "-force")
        if recurse and force:
            targets = _ps_remove_targets(tokens)
            if targets and all(_is_temp_path(t) for t in targets):
                return "allow", ""
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

def _strip_shell_grouping(segment: str) -> str | None:
    """서브셸 `(...)`·명령치환 `$(...)`·백틱 그룹 문자를 세그먼트 선두/말미에서 제거한다.

    제거가 발생하면 내부 명령 문자열을, 아니면 None 을 반환한다. 그룹 안의
    위험 명령(`(git push --force origin production)` 등)이 첫 토큰 디스패치를
    우회하지 못하도록 재귀 판정 대상으로 되돌린다.
    """
    inner = segment
    changed = False
    while inner.startswith("$("):
        inner, changed = inner[2:], True
    while inner and inner[0] in "(`":
        inner, changed = inner[1:], True
    while inner and inner[-1] in ")`":
        inner, changed = inner[:-1], True
    inner = inner.strip()
    return inner if (changed and inner) else None


def _skip_env_opts(tokens: list[str], i: int) -> int:
    """`env` 의 옵션(`-i`, `-u NAME` 등)을 건너뛴 다음 토큰 인덱스를 반환한다.

    파라미터:
        tokens: argv 토큰(따옴표 포함 원본).
        i: `env` 다음 토큰의 시작 인덱스.
    반환: 옵션을 소비한 뒤의 인덱스(후속 KEY=VAL 은 상위 루프가 처리).
    """
    n = len(tokens)
    while i < n:
        tok = _strip_quotes(tokens[i]).lower()
        if tok in ("-u", "--unset"):
            i += 2
            continue
        if tok.startswith("-"):
            i += 1
            continue
        break
    return i


def _skip_timeout_opts(tokens: list[str], i: int) -> int:
    """`timeout` 의 옵션(`-s SIG`, `-k DUR`, `--preserve-status`)과 지속시간 인자를 건너뛴다.

    파라미터:
        tokens: argv 토큰(따옴표 포함 원본).
        i: `timeout` 다음 토큰의 시작 인덱스.
    반환: 옵션·지속시간을 소비한 뒤의 실제 명령 시작 인덱스.
    """
    n = len(tokens)
    while i < n:
        tok = _strip_quotes(tokens[i]).lower()
        if tok in ("-s", "--signal", "-k", "--kill-after"):
            i += 2
            continue
        if tok.startswith("-"):
            i += 1
            continue
        if _DURATION_RE.match(tok):
            i += 1
            continue
        break
    return i


def _reduce_wrappers(tokens_raw: list[str]) -> list[str] | None:
    """선행 `KEY=VAL` 할당과 실행 래퍼(`env`/`nohup`/`timeout`/`xargs`)를 벗긴다.

    벗겨낸 뒤 남은 '실제 실행 명령' 토큰 리스트를 반환한다. 벗길 래핑이
    없으면(일반 명령) None 을 반환해 호출자가 정상 디스패치하도록 한다.
    """
    i, n, changed = 0, len(tokens_raw), False
    while i < n:
        tok = _strip_quotes(tokens_raw[i])
        if _ENV_ASSIGN_RE.match(tok):
            i, changed = i + 1, True
            continue
        name = _command_name([tokens_raw[i]])
        if name == "env":
            i, changed = _skip_env_opts(tokens_raw, i + 1), True
            continue
        if name == "timeout":
            i, changed = _skip_timeout_opts(tokens_raw, i + 1), True
            continue
        if name in _SIMPLE_WRAPPERS:
            i, changed = i + 1, True
            continue
        break
    if changed and 0 < i < n:
        return tokens_raw[i:]
    return None


def _shell_c_payload(tokens_raw: list[str]) -> str | None:
    """`bash|sh|zsh|pwsh|powershell -c/-lc/-Command "<문자열>"` 의 내부 명령 문자열을 반환한다.

    해당 패턴이 아니거나 뒤따르는 문자열이 없으면 None 을 반환한다. 내부
    문자열은 재귀 분류 대상이 되어 하위 셸에 숨은 위험 명령을 드러낸다.
    """
    if not tokens_raw:
        return None
    if _command_name([tokens_raw[0]]) not in _SHELL_INTERPRETERS:
        return None
    for j in range(1, len(tokens_raw)):
        tok = _strip_quotes(tokens_raw[j])
        if tok.lower() in _SHELL_C_FLAGS:
            return _strip_quotes(tokens_raw[j + 1]) if j + 1 < len(tokens_raw) else None
        if not tok.startswith("-"):
            return None
    return None


def _unwrap_segment(segment: str, depth: int) -> tuple[str, str] | None:
    """서브셸/명령치환/실행 래퍼/`shell -c` 를 벗겨 내부 명령을 재귀 판정한다.

    벗길 래핑이 있으면 (decision, label) 을, 없으면 None(일반 디스패치)을 반환한다.
    """
    grouped = _strip_shell_grouping(segment)
    if grouped is not None:
        return _classify_command(grouped, depth + 1)
    tokens_raw = _tokenize(segment)
    if not tokens_raw:
        return None
    reduced = _reduce_wrappers(tokens_raw)
    if reduced is not None:
        return _classify_command(" ".join(reduced), depth + 1)
    payload = _shell_c_payload(tokens_raw)
    if payload is not None:
        return _classify_command(payload, depth + 1)
    return None


def _classify_segment(segment: str, depth: int = 0) -> tuple[str, str]:
    """단일 명령 세그먼트의 위험도를 판정한다(래퍼/서브셸/`shell -c` 언랩 포함)."""
    unwrapped = _unwrap_segment(segment, depth)
    if unwrapped is not None:
        return unwrapped
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


def _classify_command(command: str, depth: int) -> tuple[str, str]:
    """`classify_command` 의 재귀 본체(래퍼 언랩 깊이 추적).

    개행/연산자로 세그먼트를 분해해 각각 판정하고 최고 위험도를 채택한다.

    파라미터:
        command: 판정할 명령 문자열(래퍼 언랩 시 하위 명령).
        depth: 재귀 언랩 깊이(_MAX_UNWRAP_DEPTH 초과 시 보수적으로 ask).
    반환: (decision, label).
    """
    if not command or not isinstance(command, str):
        return "allow", ""
    if depth > _MAX_UNWRAP_DEPTH:
        return "ask", "언랩 깊이 상한 초과(의심 명령)"

    unified = command.replace("\r\n", "\n").replace("\r", "\n")
    best_decision, best_label = "allow", ""
    for raw_segment in _split_segments(unified):
        segment = re.sub(r"\s+", " ", raw_segment).strip()
        if not segment:
            continue
        decision, label = _classify_segment(segment, depth)
        if _RISK_ORDER[decision] > _RISK_ORDER[best_decision]:
            best_decision, best_label = decision, label
            if best_decision == "deny":
                break
    return best_decision, best_label


def classify_command(
    command: str,
    *,
    project_root: str | None = None,
    session_id: str | None = None,
) -> tuple[str, str]:
    """셸 명령 전체의 위험도를 판정한다(공개 API).

    복합 명령은 세그먼트(연산자·개행 경계)로 분해해 각각 판정하고 최고 위험도를
    채택한다. 선행 환경변수 할당(`KEY=VAL`)·실행 래퍼(`env`/`nohup`/`timeout`/
    `xargs`)·`shell -c "<문자열>"`·서브셸/명령치환(`(...)`,`$(...)`)은 벗겨 내부
    명령을 재귀 판정하므로 첫 토큰 디스패치 우회를 차단한다.

    파라미터:
        command: 판정할 원본 명령 문자열.
        project_root: 저장소 루트(deploy 세션 범위 검사용, 선택).
        session_id: 현재 에이전트 세션 id(선택).
    반환:
        (decision, label) 튜플. decision ∈ {"deny","ask","allow"}.
        label 은 로그/사유용 한글 요약(allow 시 빈 문자열).
    """
    global _ctx_project_root, _ctx_session_id
    prev_root, prev_sid = _ctx_project_root, _ctx_session_id
    _ctx_project_root, _ctx_session_id = project_root, session_id
    try:
        return _classify_command(command, 0)
    finally:
        _ctx_project_root, _ctx_session_id = prev_root, prev_sid


# ---------------------------------------------------------------------------
# push 세그먼트 식별 (post_push_watch 등 하네스 도구가 재사용)
# ---------------------------------------------------------------------------

def _git_push_info(tokens_raw: list[str], push_idx: int) -> dict:
    """`git push` 세그먼트의 대상 브랜치와 dry-run 여부를 추출한다.

    파라미터:
        tokens_raw: argv 토큰(따옴표 포함).
        push_idx: 'push' 서브커맨드 토큰 인덱스.
    반환: {"kind":"git_push","targets":[브랜치...],"dry_run":bool}.
    """
    rest = [_strip_quotes(t) for t in tokens_raw[push_idx + 1:]]
    dry_run = any(t in ("--dry-run", "-n") for t in rest)
    positionals = [t for t in rest if not t.startswith("-")]
    refspecs = positionals[1:] if len(positionals) >= 2 else []
    return {
        "kind": "git_push",
        "targets": [_refspec_dest(r) for r in refspecs],
        "dry_run": dry_run,
    }


def _gh_merge_info(tokens_raw: list[str]) -> dict | None:
    """`gh pr merge ...` 세그먼트면 병합 정보를, 아니면 None 을 반환한다."""
    subs = [_strip_quotes(t).lower() for t in tokens_raw[1:]]
    if len(subs) >= 2 and subs[0] == "pr" and subs[1] == "merge":
        return {"kind": "gh_merge", "targets": [], "dry_run": False}
    return None


def _segment_push_info(tokens_raw: list[str]) -> dict | None:
    """세그먼트 토큰이 실제 push 명령(git push / gh pr merge)이면 정보를, 아니면 None."""
    if not tokens_raw:
        return None
    name = _command_name(tokens_raw)
    if name == "git":
        idx = _git_subcommand_index(tokens_raw)
        if idx is not None and _strip_quotes(tokens_raw[idx]).lower() == "push":
            return _git_push_info(tokens_raw, idx)
        return None
    if name == "gh":
        return _gh_merge_info(tokens_raw)
    return None


def find_push_segments(command: str) -> list[dict]:
    """명령의 '실제 실행 세그먼트' 중 push 성격(git push / gh pr merge)만 찾아 반환한다(공개 API).

    부분문자열 매칭 대신 argv 토큰 위치 기반이라 `echo '...git push...'` 같은
    인용 페이로드나 `python -c "..."` 를 push 로 오탐하지 않는다.

    파라미터:
        command: 원본 명령 문자열.
    반환:
        각 push 세그먼트별 {"kind","targets","dry_run"} 딕셔너리 리스트.
        push 세그먼트가 없으면 빈 리스트.
    """
    if not command or not isinstance(command, str):
        return []
    unified = command.replace("\r\n", "\n").replace("\r", "\n")
    results: list[dict] = []
    for raw_segment in _split_segments(unified):
        segment = re.sub(r"\s+", " ", raw_segment).strip()
        if not segment:
            continue
        info = _segment_push_info(_tokenize(segment))
        if info is not None:
            results.append(info)
    return results
