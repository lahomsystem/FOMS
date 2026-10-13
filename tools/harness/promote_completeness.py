"""production 승격 baseline 완전성 사전검사 (patch-id 인식).

사용:
  python tools/harness/promote_completeness.py --shas <sha1,sha2>
  python tools/harness/promote_completeness.py --session-id <id>
  python tools/harness/promote_completeness.py --shas <sha> --json

알고리즘:
  1) 승격 SHA가 건드린 파일 집합
  2) 파일 단위 바탕 비교: ``base_ref:F`` 와 ``<가장 오래된 pending>~1:F``
     → same(blob 동일) / pin_only(자산 핀 ``?v=`` 만 다름) / differs
  3) differs 파일에 대해서만 ``base_ref..<sha> -- <files>`` 커밋을 후보로
  4) ``git cherry base_ref <tip>`` 에서 ``-``(동등 패치) 제외, ``+``만 missing
  5) same/pin_only 파일만 건드린 후보는 already_equivalent(사유 content_same)
  6) promote 집합 자체는 missing에서 제외

exit: 0=complete, 2=incomplete, 1=error
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from typing import Sequence

from promote_file_compare import (  # noqa: F401 — PIN_RE·normalize_pins 는 승격 도구가 여기서 가져간다
    FILE_DIFFERS,
    FILE_PIN_ONLY,
    FILE_SAME,
    PIN_RE,
    classify_file,
    normalize_pins,
)
from session_commit_ledger import session_shas, sha_in_list


@dataclass(frozen=True)
class MissingCommit:
    """승격에 필요하지만 production에 동등 패치가 없는 커밋."""

    sha: str
    subject: str
    files: tuple[str, ...]


@dataclass(frozen=True)
class CompletenessResult:
    """완전성 분석 결과."""

    complete: bool
    promote_shas: tuple[str, ...]
    files: tuple[str, ...]
    missing: tuple[MissingCommit, ...]
    already_equivalent: tuple[str, ...]
    base_ref: str
    error: str | None = None
    # 파일별 바탕 비교 {path: same|pin_only|differs} — 기본값으로 기존 호출 호환.
    files_status: dict[str, str] = field(default_factory=dict)
    # already_equivalent 사유 {sha: patch_id|content_same}.
    equivalent_reasons: dict[str, str] = field(default_factory=dict)


def _run(cwd: str, *args: str) -> subprocess.CompletedProcess[str]:
    """git 서브프로세스 실행."""
    return subprocess.run(
        list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _normalize_shas(shas: Sequence[str]) -> tuple[str, ...]:
    """소문자 trim SHA 튜플."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in shas:
        s = (raw or "").strip().lower()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return tuple(out)


def files_touched(project_root: str, sha: str) -> tuple[str, ...]:
    """커밋이 변경한 경로 목록 (merge 포함: ``-m --first-parent``)."""
    proc = _run(
        project_root,
        "git",
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        "-m",
        "--first-parent",
        sha,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or f"diff-tree failed for {sha}")
    return tuple(ln.strip() for ln in proc.stdout.splitlines() if ln.strip())


def _commit_subject(project_root: str, sha: str) -> str:
    """커밋 제목 한 줄."""
    proc = _run(project_root, "git", "log", "-1", "--format=%s", sha)
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def _cherry_marks(
    project_root: str, base_ref: str, tip: str
) -> dict[str, str]:
    """``git cherry -v base tip`` → {sha: '+'|'-'}."""
    proc = _run(project_root, "git", "cherry", "-v", base_ref, tip)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or "git cherry failed")
    marks: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or line[0] not in "+-":
            continue
        mark = line[0]
        rest = line[1:].strip()
        if not rest:
            continue
        sha = rest.split(None, 1)[0].lower()
        marks[sha] = mark
    return marks


def _file_range_shas(
    project_root: str, base_ref: str, tip: str, files: Sequence[str]
) -> tuple[str, ...]:
    """base..tip 중 files를 건드린 커밋(오래된 순)."""
    if not files:
        return ()
    proc = _run(
        project_root,
        "git",
        "log",
        "--reverse",
        "--format=%H",
        f"{base_ref}..{tip}",
        "--",
        *files,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or "git log failed")
    return tuple(ln.strip().lower() for ln in proc.stdout.splitlines() if ln.strip())


def _oldest_pending(project_root: str, pending: Sequence[str]) -> str:
    """pending 중 topo 순으로 가장 오래된 SHA."""
    proc = _run(project_root, "git", "rev-list", "--topo-order", "--reverse", *pending)
    if proc.returncode == 0:
        for ln in proc.stdout.splitlines():
            sha = ln.strip().lower()
            if sha and sha_in_list(sha, list(pending)):
                return sha
    return pending[0]


def analyze_promote_completeness(
    project_root: str,
    shas: Sequence[str],
    *,
    base_ref: str = "origin/production",
) -> CompletenessResult:
    """승격 SHA 집합의 baseline 완전성을 분석한다.

    파라미터:
        project_root: 저장소 루트.
        shas: 승격 대상 커밋.
        base_ref: production 정본 ref.
    반환:
        CompletenessResult.
    """
    promote = _normalize_shas(shas)
    if not promote:
        return CompletenessResult(
            complete=True,
            promote_shas=(),
            files=(),
            missing=(),
            already_equivalent=(),
            base_ref=base_ref,
            error=None,
        )

    verify = _run(project_root, "git", "rev-parse", "--verify", base_ref)
    if verify.returncode != 0:
        return CompletenessResult(
            complete=False,
            promote_shas=promote,
            files=(),
            missing=(),
            already_equivalent=(),
            base_ref=base_ref,
            error=verify.stderr or f"missing ref {base_ref}",
        )

    try:
        already_landed: list[str] = []
        pending: list[str] = []
        for sha in promote:
            anc = _run(
                project_root,
                "git",
                "merge-base",
                "--is-ancestor",
                sha,
                base_ref,
            )
            if anc.returncode == 0:
                already_landed.append(sha)
                continue
            marks = _cherry_marks(project_root, base_ref, sha)
            if marks.get(sha) == "-":
                already_landed.append(sha)
            else:
                pending.append(sha)

        file_set: list[str] = []
        seen_files: set[str] = set()
        scan_shas = tuple(pending) if pending else promote
        for sha in scan_shas:
            for path in files_touched(project_root, sha):
                if path not in seen_files:
                    seen_files.add(path)
                    file_set.append(path)
        files = tuple(file_set)

        if not pending:
            return CompletenessResult(
                complete=True,
                promote_shas=promote,
                files=files,
                missing=(),
                already_equivalent=tuple(already_landed),
                base_ref=base_ref,
                error=None,
            )

        # 파일 단위 바탕 비교 — 승격 직전 deploy 바탕(가장 오래된 pending~1)과 production.
        bottom = f"{_oldest_pending(project_root, pending)}~1"
        files_status = {
            path: classify_file(project_root, base_ref, bottom, path) for path in files
        }
        differs_files = tuple(p for p in files if files_status[p] == FILE_DIFFERS)
        same_files = tuple(p for p in files if files_status[p] != FILE_DIFFERS)

        missing_map: dict[str, MissingCommit] = {}
        already: list[str] = list(already_landed)
        already_seen: set[str] = set(already_landed)
        reasons: dict[str, str] = {s: "patch_id" for s in already_landed}

        equiv: set[str] = set()
        candidates: list[str] = []
        cand_seen: set[str] = set()

        for tip in pending:
            marks = _cherry_marks(project_root, base_ref, tip)
            for sha, mark in marks.items():
                if mark == "-":
                    equiv.add(sha)
            for cand in _file_range_shas(project_root, base_ref, tip, differs_files):
                if sha_in_list(cand, list(promote)):
                    continue
                if cand not in cand_seen:
                    cand_seen.add(cand)
                    candidates.append(cand)

        for cand in candidates:
            if cand in equiv:
                if cand not in already_seen:
                    already_seen.add(cand)
                    already.append(cand)
                    reasons[cand] = "patch_id"
                continue
            overlap = tuple(
                f
                for f in files_touched(project_root, cand)
                if f in differs_files
            )
            missing_map[cand] = MissingCommit(
                sha=cand,
                subject=_commit_subject(project_root, cand),
                files=overlap,
            )

        # same/pin_only 파일만 건드린 후보 — 바탕이 같으니 누락이 아니다.
        for tip in pending:
            for cand in _file_range_shas(project_root, base_ref, tip, same_files):
                if sha_in_list(cand, list(promote)):
                    continue
                if cand in missing_map or cand in already_seen:
                    continue
                already_seen.add(cand)
                already.append(cand)
                reasons[cand] = "content_same"

        missing = tuple(missing_map.values())
        return CompletenessResult(
            complete=len(missing) == 0,
            promote_shas=promote,
            files=files,
            missing=missing,
            already_equivalent=tuple(already),
            base_ref=base_ref,
            error=None,
            files_status=files_status,
            equivalent_reasons=reasons,
        )
    except RuntimeError as exc:
        return CompletenessResult(
            complete=False,
            promote_shas=promote,
            files=(),
            missing=(),
            already_equivalent=(),
            base_ref=base_ref,
            error=str(exc),
        )


def result_to_dict(result: CompletenessResult) -> dict:
    """JSON 직렬화용 dict."""
    data = asdict(result)
    return data


def verdict_line(result: CompletenessResult) -> str:
    """텍스트 출력 첫 줄 판정 한 줄."""
    if result.complete:
        vals = [result.files_status.get(p) for p in result.files]
        same = sum(1 for v in vals if v == FILE_SAME)
        pin = sum(1 for v in vals if v == FILE_PIN_ONLY)
        diff = sum(1 for v in vals if v == FILE_DIFFERS)
        return (
            f"판정: 올려도 됨 — 대상 {len(result.files)}파일 중 "
            f"바탕 같음 {same} · 핀만 다름 {pin} · 내용 다름 {diff}"
        )
    differs = [p for p in result.files if result.files_status.get(p) == FILE_DIFFERS]
    return (
        f"판정: 진짜 누락 {len(result.missing)}개 — 내용 다른 파일: "
        + (", ".join(differs) if differs else "-")
    )


def main(argv: list[str] | None = None) -> int:
    """CLI 진입점."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 — console 재설정 실패 시 print 경로 유지
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=os.getcwd())
    parser.add_argument("--session-id", default="")
    parser.add_argument("--shas", default="", help="쉼표 구분 SHA")
    parser.add_argument(
        "--base-ref",
        default="origin/production",
        help="production 정본 (기본 origin/production)",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="분석 전 git fetch origin production",
    )
    args = parser.parse_args(argv)
    root = os.path.abspath(args.project_root)

    if args.fetch:
        fetch = _run(root, "git", "fetch", "origin", "production")
        if fetch.returncode != 0:
            print(fetch.stderr or "git fetch failed", file=sys.stderr)
            return 1

    if args.shas.strip():
        shas = [s.strip() for s in args.shas.split(",") if s.strip()]
    else:
        shas = session_shas(root, args.session_id or "unknown")

    if not shas:
        msg = "검사할 SHA 없음 (session-id/레저 또는 --shas 확인)."
        if args.json:
            print(
                json.dumps(
                    {
                        "complete": False,
                        "promote_shas": [],
                        "files": [],
                        "missing": [],
                        "already_equivalent": [],
                        "base_ref": args.base_ref,
                        "error": msg,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(msg, file=sys.stderr)
        return 2

    result = analyze_promote_completeness(root, shas, base_ref=args.base_ref)
    if result.error:
        if args.json:
            print(json.dumps(result_to_dict(result), ensure_ascii=False, indent=2))
        else:
            print(result.error, file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result_to_dict(result), ensure_ascii=False, indent=2))
    else:
        print(verdict_line(result))
        print(f"base={result.base_ref}")
        print(f"promote={len(result.promote_shas)} files={len(result.files)}")
        for path in result.files:
            status = result.files_status.get(path)
            if status:
                print(f"  [{status}] {path}")
        if result.already_equivalent:
            print(f"already_equivalent={len(result.already_equivalent)}")
        if result.complete:
            print("COMPLETE: missing baseline deps = 0")
        else:
            print(f"INCOMPLETE: missing={len(result.missing)}")
            for m in result.missing:
                print(f"  + {m.sha[:8]} {m.subject}")
                if m.files:
                    print(f"    files: {', '.join(m.files[:8])}")

    if not result.complete:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
