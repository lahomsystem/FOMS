#!/usr/bin/env python3
"""FOMS 성능 회귀 스캐너 (도구 무관 엔진).

Cursor IDE / Cursor 내 Claude / Codex 어디서든 `python tools/perf/perf_scan.py`로
실행한다. 코드 수정이 FOMS를 느리게 만드는 알려진 안티패턴을 정적 분석으로 잡는다.
배경·해법: docs/guides/PERFORMANCE_GUARDRAILS.md

모드:
  --guard  (기본) 현재 변경분(git diff HEAD, staged+working)만 검사 → 회귀 방지.
  --audit         코드베이스 전체 검사 → 정기 개선 후보.
  --base <ref>    guard 비교 기준(기본: HEAD).
  --json          기계 판독용 JSON 출력.

종료코드: 0=문제 없음, 1=high 발견(머지 전 차단 권장).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = "docs/guides/PERFORMANCE_GUARDRAILS.md"


@dataclass
class Finding:
    severity: str  # high | medium | low
    rule: str
    file: str
    line: int
    snippet: str
    fix: str


# (rule, severity, 적용 경로 glob 접두, 라인 정규식, 제외 정규식 or None, 수정 힌트)
_RULES = [
    (
        "render-blocking-script", "high", ("templates/",),
        re.compile(r"<script\b[^>]*\bsrc\s*=", re.I),
        re.compile(r"\bdefer\b|\basync\b|type\s*=\s*['\"]module", re.I),
        "<script>에 defer 추가(또는 사용 시점 lazy 로드). 렌더 차단 = 탭 로딩 지연.",
    ),
    (
        "cdn-sync-script", "high", ("templates/",),
        re.compile(r"<script\b[^>]*\bsrc\s*=\s*['\"]https?://", re.I),
        re.compile(r"\bdefer\b|\basync\b", re.I),
        "외부 CDN <script>는 defer 또는 동적 로드. CDN 지연 시 페이지 전체 멈춤.",
    ),
    (
        "heavy-lib-global", "high", ("templates/",),
        re.compile(r"<script\b[^>]*\b(html2canvas|pdfmake|xlsx|chart(?:\.min)?\.js|moment|jspdf)\b", re.I),
        re.compile(r"\bdefer\b", re.I),
        "무거운 라이브러리는 사용하는 페이지/시점에만 lazy 로드. 공용 partial 전역 로드 금지.",
    ),
    (
        "sw-no-cache-fetch", "high", ("static/sw.js",),
        re.compile(r"fetch\([^)]*cache\s*:\s*['\"]no-cache", re.I),
        None,
        "서비스워커에서 정적 강제 재검증(no-cache) 금지 → 매 네비 서버 폭주. staticCacheFirst(캐시+TTL) 사용.",
    ),
    (
        "jsonb-text-ilike", "high", ("foms/", "services/", "apps/"),
        re.compile(r"structured_data.*\.ilike\(", re.I),
        re.compile(r"#\s*perf-ok"),
        "JSONB→text ILIKE는 인덱스 못 탐(풀스캔). trigram 인덱스 추가 또는 @>/denormalized 컬럼. EXPLAIN로 확인.",
    ),
    (
        "unbounded-query-all", "medium", ("foms/", "services/", "apps/"),
        re.compile(r"\.query\(.*\)\.(?:filter\([^)]*\)\.)*all\(\)"),
        re.compile(r"\.limit\(|#\s*perf-ok"),
        "리스트 쿼리에 .limit() 없이 .all() → 행 증가 시 폭주. limit/페이지네이션 적용.",
    ),
]


def _run(cmd: list[str]) -> str:
    # Windows 로케일(cp949)이 git diff의 한글(UTF-8)을 못 풀어 stdout=None이 되는 것을 방지.
    try:
        out = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace", timeout=60
        ).stdout
        return out or ""
    except Exception:
        return ""


def _scan_text(path: str, lines: list[tuple[int, str]], findings: list[Finding]) -> None:
    for rule, sev, prefixes, pat, exclude, fix in _RULES:
        if not any(path.startswith(p) for p in prefixes):
            continue
        for lineno, text in lines:
            if pat.search(text) and not (exclude and exclude.search(text)):
                findings.append(Finding(sev, rule, path, lineno, text.strip()[:120], fix))


def guard(base: str) -> list[Finding]:
    """변경분(추가 라인)만 검사."""
    diff = _run(["git", "diff", "--unified=0", base])
    findings: list[Finding] = []
    cur_file = ""
    new_lineno = 0
    for raw in diff.splitlines():
        if raw.startswith("+++ b/"):
            cur_file = raw[6:].strip()
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            new_lineno = int(m.group(1)) if m else 0
        elif raw.startswith("+") and not raw.startswith("+++"):
            _scan_text(cur_file, [(new_lineno, raw[1:])], findings)
            new_lineno += 1
        elif not raw.startswith("-"):
            new_lineno += 1
    return findings


def audit() -> list[Finding]:
    """코드베이스 전체 검사."""
    findings: list[Finding] = []
    globs = ["templates/**/*.html", "static/**/*.js", "foms/**/*.py", "services/**/*.py"]
    seen: set[str] = set()
    for g in globs:
        for fp in ROOT.glob(g):
            rel = str(fp.relative_to(ROOT)).replace("\\", "/")
            if rel in seen or "/__pycache__/" in rel or "/backups/" in rel or "/tests/" in rel:
                continue
            seen.add(rel)
            try:
                text = fp.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            _scan_text(rel, list(enumerate(text.splitlines(), 1)), findings)
    return findings


def main() -> int:
    # Windows cp949 콘솔에서 한글·emoji 출력이 깨지거나 죽지 않도록 UTF-8 강제.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="FOMS 성능 회귀 스캐너")
    ap.add_argument("--guard", action="store_true", help="변경분만 점검(기본)")
    ap.add_argument("--audit", action="store_true", help="전체 코드베이스 점검")
    ap.add_argument("--base", default="HEAD", help="guard 비교 기준 ref")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    findings = audit() if args.audit else guard(args.base)
    findings.sort(key=lambda f: ({"high": 0, "medium": 1, "low": 2}[f.severity], f.file, f.line))

    if args.json:
        print(json.dumps([asdict(f) for f in findings], ensure_ascii=False, indent=1))
    else:
        mode = "AUDIT(전체)" if args.audit else f"GUARD(변경분 vs {args.base})"
        print(f"=== FOMS 성능 스캔 [{mode}] ===")
        if not findings:
            print("문제 없음 ✅")
        for f in findings:
            print(f"[{f.severity.upper()}] {f.rule}  {f.file}:{f.line}")
            print(f"    {f.snippet}")
            print(f"    → {f.fix}")
        highs = sum(1 for f in findings if f.severity == "high")
        meds = sum(1 for f in findings if f.severity == "medium")
        print(f"\n요약: high={highs} medium={meds} 총={len(findings)}  (상세: {GUIDE})")

    # guard(변경분)에서 신규 high면 머지 차단(exit 1). audit는 advisory(항상 0).
    if args.audit:
        return 0
    return 1 if any(f.severity == "high" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
