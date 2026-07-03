#!/usr/bin/env python3
"""FOMS 성능 회귀 스캐너 (도구 무관 엔진).

배경: docs/guides/PERFORMANCE_GUARDRAILS.md · docs/guides/ERP_SLOWDOWN_RADAR.md

모드:
  --guard  (기본) git diff 변경분 → deploy veto (신규 high면 exit 1)
  --audit         전체 코드베이스 → ERP slowdown radar (advisory, exit 0)
  --radar         audit findings 8차원 요약 (--audit 암시)
  --base <ref>    guard 비교 기준 (기본 HEAD)
  --json          JSON 출력
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = "docs/guides/PERFORMANCE_GUARDRAILS.md"
RADAR_GUIDE = "docs/guides/ERP_SLOWDOWN_RADAR.md"
BASELINE_DEBT = Path(__file__).resolve().parent / "baseline_debt.json"

# SSOT: tests/performance/test_perf_regression_guard.py SYNC_SCRIPT_ALLOWLIST 와 동기
SYNC_SCRIPT_ALLOWLIST: frozenset[str] = frozenset()

DIMENSIONS = (
    "amplifier",
    "render-block",
    "interaction-debt",
    "sw-cache",
    "query-scale",
    "payload",
    "hot-compute",
    "io-bound",
)

HOT_PATH_PREFIXES = (
    "templates/partials/shared/",
    "templates/partials/erp_order_js",
    "templates/partials/shared/foms_app_shell",
    "templates/partials/shared/erp_mobile_shell",
    "static/sw.js",
    "services/dashboard/",
    "services/search/",
    "foms/api/",
)

# rule, audit_sev, dimension, path prefixes, line regex, exclude regex, fix
_LINE_RULES: list[tuple] = [
    (
        "render-blocking-script",
        "high",
        "render-block",
        ("templates/",),
        re.compile(r"<script\b[^>]*\bsrc\s*=", re.I),
        re.compile(r"\bdefer\b|\basync\b|type\s*=\s*['\"]module", re.I),
        "<script>에 defer 추가(또는 lazy 로드). 렌더 차단 = 탭 로딩 지연.",
    ),
    (
        "cdn-sync-script",
        "high",
        "render-block",
        ("templates/",),
        re.compile(r"<script\b[^>]*\bsrc\s*=\s*['\"]https?://", re.I),
        re.compile(r"\bdefer\b|\basync\b", re.I),
        "외부 CDN <script>는 defer 또는 동적 로드.",
    ),
    (
        "heavy-lib-global",
        "high",
        "amplifier",
        ("templates/",),
        re.compile(r"<script\b[^>]*\b(html2canvas|pdfmake|xlsx|chart(?:\.min)?\.js|moment|jspdf)\b", re.I),
        re.compile(r"\bdefer\b|\basync\b|type\s*=\s*['\"]module", re.I),
        "무거운 lib는 사용 시점 lazy. 공용 partial 전역 로드 금지.",
    ),
    (
        "sw-no-cache-fetch",
        "high",
        "sw-cache",
        ("static/sw.js",),
        re.compile(r"fetch\([^)]*cache\s*:\s*['\"]no-cache", re.I),
        None,
        "SW 정적 no-cache 재검증 금지 → staticCacheFirst.",
    ),
    (
        "jsonb-text-ilike",
        "high",
        "query-scale",
        ("foms/", "services/", "apps/"),
        re.compile(r"structured_data.*\.ilike\(", re.I),
        re.compile(r"#\s*perf-ok"),
        "JSONB→text ILIKE 풀스캔. trigram/@> + EXPLAIN.",
    ),
    (
        "general-ilike",
        "medium",
        "query-scale",
        ("foms/", "services/", "apps/"),
        re.compile(r"\.ilike\(", re.I),
        re.compile(r"structured_data.*\.ilike\(|#\s*perf-ok"),
        "ILIKE hot path — trigram 인덱스 또는 @> 확인.",
    ),
    (
        "unbounded-query-all",
        "medium",
        "payload",
        ("foms/", "services/", "apps/"),
        re.compile(r"\.query\(.*\)\.(?:filter\([^)]*\)\.)*all\(\)"),
        re.compile(r"\.limit\(|#\s*perf-ok"),
        "리스트 .all() 무 limit → 페이지네이션.",
    ),
]

_B_LAYER_HOT_HIGH = frozenset(
    {"general-ilike", "loop-db-query", "shell-polling", "shared-inline-script", "broad-cache-invalidation"}
)

# --- 2026-07-03 초정밀 감사 이식 규칙 ---------------------------------------
# ① fragment-multi-script: 셸 스왑마다 재파싱·재실행되는 fragment 다중 <script src>
_FRAGMENT_MULTI_SCRIPT_RULE = "fragment-multi-script"
_FRAGMENT_SCRIPTS_GLOB = "templates/**/partials/*scripts*.html"
_SCRIPT_SRC_RE = re.compile(r"<script\b[^>]*\bsrc\s*=", re.I)
# layout_*는 페이지당 1회 렌더되는 임계경로(zero-RTT)라 fragment 스왑 재실행 대상 아님 → 제외.
# (_LAYOUT_INLINE_DELIVERY_FILES는 이 지점 이후에 정의되므로 직접 나열한다.)
_FRAGMENT_MULTI_SCRIPT_EXCLUDE: frozenset[str] = frozenset(
    {
        "templates/partials/shared/layout_head.html",
        "templates/partials/shared/layout_scripts.html",
    }
)

# ② broad-cache-invalidation: invalidate_all_dashboard_slice_caches() 통무효화
_BROAD_INVALIDATE_RULE = "broad-cache-invalidation"
_BROAD_INVALIDATE_RE = re.compile(r"invalidate_all_dashboard_slice_caches\s*\(")
# 정의부 + Tier A(stage 전환 등 전 탭 영향) 의도 파일 allowlist → veto 제외.
_BROAD_INVALIDATE_ALLOWLIST: frozenset[str] = frozenset(
    {
        "foms/services/common/dashboard_cache.py",  # 정의부
        "foms/api/quest.py",
        "foms/api/erp_orders_structured.py",
        "foms/api/cs/as_orders.py",
        "foms/api/drawing/erp_orders_draftsman.py",
        "foms/api/orders/field_update.py",
        "foms/services/orders/mobile_queue_action.py",  # 폴백 경유
    }
)

# ③ jsonb-path-filter: structured_data[...] 무인덱스 path 필터
_JSONB_PATH_FILTER_RULE = "jsonb-path-filter"
_JSONB_PATH_ACCESS_RE = re.compile(r"structured_data\[")
_JSONB_PATH_QUERY_RE = re.compile(r"\.filter\(|\.in_\(|cast\(")
_JSONB_PATH_ILIKE_RE = re.compile(r"\.ilike\(", re.I)  # 기존 jsonb-text-ilike 와 중복 회피

# ④ mobile-queue-row-no-batch: build_mobile_queue_order_row 를 batch_ctx 없이 호출
_MOBILE_ROW_NO_BATCH_RULE = "mobile-queue-row-no-batch"
_MOBILE_ROW_CALL_RE = re.compile(r"build_mobile_queue_order_row\s*\(")


def _is_fragment_scripts_partial(path: str) -> bool:
    """`templates/**/partials/*scripts*.html` glob 매칭(guard 터치 파일용)."""
    p = path.replace("\\", "/")
    return (
        p.startswith("templates/")
        and "/partials/" in p
        and p.endswith(".html")
        and "scripts" in p.rsplit("/", 1)[-1]
    )

_GLOBAL_REPLAYED_EVENT_RE = re.compile(
    r"^(?: {0,2}|\t?)(?:document(?:\.body)?|window)\.addEventListener\s*\(",
    re.M,
)
_SET_INTERVAL_RE = re.compile(r"\bsetInterval\s*\(")
_SHELL_REPLAYED_SCRIPT_RULE = "fragment-replayed-global-listener"
_LOOP_DB_RULE = "loop-db-query"
_SHELL_POLLING_RULE = "shell-polling"
_SHARED_INLINE_RULE = "shared-inline-script"
_SW_TIMEOUT_RULE = "sw-network-first-no-timeout"
_STATIC_FILENAME_RE = re.compile(r"filename\s*=\s*['\"]([^'\"]+\.js)['\"]")
_INCLUDE_RE = re.compile(r"{%\s*include\s+['\"]([^'\"]+)['\"]")
_FRAGMENT_REPLAY_ENTRY_TEMPLATES = (
    "templates/partials/shared/erp_mobile_shell.html",
    "templates/partials/shared/foms_app_shell.html",
    "templates/partials/shared/foms_p2_surface_bundle.html",
    "templates/partials/shared/foms_mobile_queue_attachment_preview_bundle.html",
)
_SHARED_PARTIAL_PREFIX = "templates/partials/shared/"
# Production-parity: layout critical path stays inline (zero RTT). Edit SSOT under static/js/runtime/layout-*.js.
_LAYOUT_INLINE_DELIVERY_FILES: frozenset[str] = frozenset(
    {
        "templates/partials/shared/layout_head.html",
        "templates/partials/shared/layout_scripts.html",
    }
)
_LOOP_QUERY_RE = re.compile(r"(?:\.query\s*\(|db\.session\.|session\.query\s*\()")
_REPLAYED_TEMPLATES_CACHE: set[str] | None = None
_REPLAYED_JS_CACHE: set[str] | None = None


@dataclass
class Finding:
    severity: str
    rule: str
    dimension: str
    file: str
    line: int
    snippet: str
    fix: str

    @property
    def fid(self) -> str:
        return f"{self.rule}|{self.file}|{self.line}"


@dataclass
class RadarReport:
    dimensions: dict = field(default_factory=dict)
    hot_paths_unmeasured: list[str] = field(default_factory=list)
    deploy_risk_summary: str = ""
    total_high: int = 0
    total_medium: int = 0


def _is_hot_path(path: str) -> bool:
    return any(path.startswith(p) or p in path for p in HOT_PATH_PREFIXES)


def _load_baseline_debt() -> set[str]:
    if not BASELINE_DEBT.exists():
        return set()
    try:
        data = json.loads(BASELINE_DEBT.read_text(encoding="utf-8"))
        return set(data.get("finding_ids", []))
    except Exception:
        return set()


def _guard_severity(rule: str, audit_sev: str, path: str) -> str:
    """Map audit severity to guard blocking severity."""
    if audit_sev == "high" and rule not in _B_LAYER_HOT_HIGH:
        return "high"
    if rule in _B_LAYER_HOT_HIGH and _is_hot_path(path):
        return "high"
    return "medium"


def _append_finding(
    findings: list[Finding],
    rule: str,
    audit_sev: str,
    dimension: str,
    path: str,
    lineno: int,
    text: str,
    fix: str,
    *,
    guard_mode: bool,
) -> None:
    sev = _guard_severity(rule, audit_sev, path) if guard_mode else audit_sev
    findings.append(
        Finding(
            sev,
            rule,
            dimension,
            path,
            lineno,
            text.strip()[:120],
            fix,
        )
    )


def _has_global_init_guard(text: str) -> bool:
    return bool(
        re.search(
            r"window\.__[A-Za-z0-9_$]*(?:BOUND|INIT|INITIALIZED|LOADED|MOUNTED)",
            text,
        )
    )


def _read_repo_text(rel: str) -> str:
    try:
        return (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _collect_replayed_template_paths() -> set[str]:
    global _REPLAYED_TEMPLATES_CACHE
    if _REPLAYED_TEMPLATES_CACHE is not None:
        return _REPLAYED_TEMPLATES_CACHE
    seen: set[str] = set()

    def visit(rel: str) -> None:
        if rel in seen:
            return
        seen.add(rel)
        for inc in _INCLUDE_RE.findall(_read_repo_text(rel)):
            visit("templates/" + inc)

    for entry in _FRAGMENT_REPLAY_ENTRY_TEMPLATES:
        visit(entry)
    _REPLAYED_TEMPLATES_CACHE = seen
    return seen


def _collect_fragment_replayed_js_paths() -> set[str]:
    global _REPLAYED_JS_CACHE
    if _REPLAYED_JS_CACHE is not None:
        return _REPLAYED_JS_CACHE
    scripts: set[str] = set()
    for rel in _collect_replayed_template_paths():
        for js in _STATIC_FILENAME_RE.findall(_read_repo_text(rel)):
            scripts.add(js.replace("\\", "/"))
    _REPLAYED_JS_CACHE = scripts
    return scripts


def _js_from_template_line(text: str) -> str | None:
    match = _STATIC_FILENAME_RE.search(text)
    return match.group(1).replace("\\", "/") if match else None


def _unsafe_replayed_js(js_rel: str) -> bool:
    if js_rel.startswith("js/vendor/"):
        return False
    text = _read_repo_text("static/" + js_rel)
    if not text or _has_global_init_guard(text):
        return False
    return bool(_GLOBAL_REPLAYED_EVENT_RE.search(text))


def _scan_line_rules(
    path: str,
    lines: list[tuple[int, str]],
    findings: list[Finding],
    *,
    guard_mode: bool,
) -> None:
    for rule, audit_sev, dimension, prefixes, pat, exclude, fix in _LINE_RULES:
        if not any(path.startswith(p) for p in prefixes):
            continue
        dim = "amplifier" if rule == "heavy-lib-global" and _SHARED_PARTIAL_PREFIX in path else dimension
        for lineno, text in lines:
            if pat.search(text) and not (exclude and exclude.search(text)):
                if rule == "render-blocking-script" and any(
                    name in text for name in SYNC_SCRIPT_ALLOWLIST
                ):
                    continue
                _append_finding(findings, rule, audit_sev, dim, path, lineno, text, fix, guard_mode=guard_mode)


def _scan_broad_cache_invalidation(
    path: str,
    lines: list[tuple[int, str]],
    findings: list[Finding],
    *,
    guard_mode: bool,
) -> None:
    """통무효화(invalidate_all_dashboard_slice_caches) 호출 flag — 의도 파일 allowlist 제외."""
    if not path.endswith(".py") or path in _BROAD_INVALIDATE_ALLOWLIST:
        return
    if not any(path.startswith(p) for p in ("foms/", "services/", "apps/")):
        return
    if path.startswith("tests/") or "/tests/" in path:
        return
    for lineno, text in lines:
        if _BROAD_INVALIDATE_RE.search(text) and "# perf-ok" not in text:
            _append_finding(
                findings,
                _BROAD_INVALIDATE_RULE,
                "medium",
                "hot-compute",
                path,
                lineno,
                text,
                "stage 전환이 아닌 mutation은 티어 무효화(invalidate_order_dashboard_families/"
                "invalidate_dashboard_families) 사용. 통무효화=전 탭 slice miss 폭풍(2026-07 사건, 22곳).",
                guard_mode=guard_mode,
            )


def _scan_jsonb_path_filter(
    path: str,
    lines: list[tuple[int, str]],
    findings: list[Finding],
    *,
    guard_mode: bool,
) -> None:
    """structured_data[...] 무인덱스 path 필터 flag — 기존 jsonb-text-ilike 와 중복 회피."""
    if not path.endswith(".py"):
        return
    if not any(path.startswith(p) for p in ("foms/", "services/", "apps/")):
        return
    for lineno, text in lines:
        if not _JSONB_PATH_ACCESS_RE.search(text):
            continue
        if not _JSONB_PATH_QUERY_RE.search(text):
            continue
        if _JSONB_PATH_ILIKE_RE.search(text):  # jsonb-text-ilike 규칙 담당
            continue
        if "# perf-ok" in text or "`" in text:  # backtick=docstring 코드 참조(실행 코드 아님)
            continue
        _append_finding(
            findings,
            _JSONB_PATH_FILTER_RULE,
            "medium",
            "query-scale",
            path,
            lineno,
            text,
            "JSONB path 비교는 무인덱스 풀스캔. flat sync 컬럼(erp_stage_code 패턴)+인덱스 검토, "
            "EXPLAIN 확인(생산탭 1,894행→59행 사건).",
            guard_mode=guard_mode,
        )


def _scan_mobile_queue_row_no_batch(
    path: str,
    lines: list[tuple[int, str]],
    findings: list[Finding],
    *,
    guard_mode: bool,
) -> None:
    """build_mobile_queue_order_row(...) 를 batch_ctx 없이 호출하면 flag(행당 N+1)."""
    if not path.endswith(".py"):
        return
    if not any(path.startswith(p) for p in ("foms/", "services/", "apps/")):
        return
    for lineno, text in lines:
        if not _MOBILE_ROW_CALL_RE.search(text):
            continue
        if "batch_ctx" in text or "def build_mobile_queue_order_row" in text or "# perf-ok" in text:
            continue
        _append_finding(
            findings,
            _MOBILE_ROW_NO_BATCH_RULE,
            "medium",
            "query-scale",
            path,
            lineno,
            text,
            "batch_ctx 미전달=행당 ~5쿼리 N+1(실측 1,500쿼리 사건). "
            "build_mobile_queue_batch_context 후 batch_ctx 전달.",
            guard_mode=guard_mode,
        )


def _scan_fragment_multi_script(path: str, text: str, findings: list[Finding], *, guard_mode: bool) -> None:
    """fragment scripts partial 에 <script src> 2개 이상이면 flag(셸 스왑마다 전부 재실행)."""
    if path in _FRAGMENT_MULTI_SCRIPT_EXCLUDE:
        return
    lines = text.splitlines()
    src_linenos = [i + 1 for i, ln in enumerate(lines) if _SCRIPT_SRC_RE.search(ln)]
    if len(src_linenos) < 2:
        return
    _append_finding(
        findings,
        _FRAGMENT_MULTI_SCRIPT_RULE,
        "high",
        "interaction-debt",
        path,
        src_linenos[0],
        f"fragment scripts partial <script src> x{len(src_linenos)}",
        f"fragment 내 다중 <script src>({len(src_linenos)}개) = 셸 스왑마다 전부 재파싱·재실행"
        "(실측탭 5.8s 사건). entry singleton 1개로 통합(erp-dashboard-entry.js 패턴).",
        guard_mode=guard_mode,
    )


def _scan_loop_db_added_lines(
    path: str,
    added: list[tuple[int, str]],
    findings: list[Finding],
    *,
    guard_mode: bool,
) -> None:
    """Flag loop+query only when both appear in the same diff-added hunk."""
    if not path.endswith(".py") or not added:
        return
    if guard_mode and not _is_hot_path(path):
        return
    if not any(path.startswith(p) for p in ("foms/", "services/", "apps/")):
        return
    for i, (start_lineno, line) in enumerate(added):
        if not re.match(r"^\s*for\b", line) or line.strip().endswith("# perf-ok"):
            continue
        base_indent = len(line) - len(line.lstrip())
        for j in range(i + 1, len(added)):
            inner_lineno, inner = added[j]
            if not inner.strip() or inner.strip().startswith("#"):
                continue
            indent = len(inner) - len(inner.lstrip())
            if indent <= base_indent:
                break
            if _LOOP_QUERY_RE.search(inner) and "# perf-ok" not in inner:
                _append_finding(
                    findings,
                    _LOOP_DB_RULE,
                    "medium",
                    "query-scale",
                    path,
                    inner_lineno,
                    inner,
                    "루프 안 DB 쿼리 → in_(ids) 배치 로드.",
                    guard_mode=guard_mode,
                )
                break


def _scan_loop_db_queries(path: str, lines: list[str], findings: list[Finding], *, guard_mode: bool) -> None:
    """Full-file loop scan for audit mode."""
    if guard_mode:
        return
    added = [(i + 1, ln) for i, ln in enumerate(lines)]
    _scan_loop_db_added_lines(path, added, findings, guard_mode=False)


def _scan_shell_polling(path: str, text: str, findings: list[Finding], replayed_js: set[str], *, guard_mode: bool) -> None:
    if not path.startswith("static/") or not path.endswith(".js"):
        return
    js_rel = path[len("static/") :].replace("\\", "/")
    if js_rel.startswith("js/vendor/") or js_rel not in replayed_js:
        return
    if not _SET_INTERVAL_RE.search(text) or _has_global_init_guard(text):
        return
    for m in _SET_INTERVAL_RE.finditer(text):
        lineno = text.count("\n", 0, m.start()) + 1
        _append_finding(
            findings,
            _SHELL_POLLING_RULE,
            "medium",
            "interaction-debt",
            path,
            lineno,
            text.splitlines()[lineno - 1],
            "shell fragment JS polling → singleton guard + cleanup.",
            guard_mode=guard_mode,
        )
        break


def _scan_shared_inline_scripts(path: str, text: str, findings: list[Finding], *, guard_mode: bool) -> None:
    if path in _LAYOUT_INLINE_DELIVERY_FILES:
        return
    if not path.startswith(_SHARED_PARTIAL_PREFIX) or not path.endswith(".html"):
        return
    # Root fix (2026-07 사건): 대형 inline은 **fragment-replay 체인**(탭 스왑마다 재실행)에서만
    # amplifier다. layout 등 페이지당 1회 렌더되는 임계경로 partial의 inline은 zero-RTT라 오히려
    # 최적 — 단일 리전(Railway SG) 고지연 경로에서 external+defer로 분리하면 RTT 워터폴 →
    # DCL 회귀(과거 cb0bf873가 이 규칙 처방대로 분리 → DCL 10s 회귀, 797c52da로 인라인 복원).
    # 따라서 replay 체인 밖 partial의 inline은 flag하지 않는다. 처방도 "분리+defer"가 아니라
    # 이미 로드된 번들 내 idempotency 가드로 바꾼다.
    if path not in _collect_replayed_template_paths():
        return
    for m in re.finditer(r"<script(?![^>]*\bsrc\s*=)([^>]*)>(.*?)</script>", text, re.I | re.S):
        block = m.group(2)
        line_count = len([ln for ln in block.splitlines() if ln.strip()])
        if line_count <= 20:
            continue
        lineno = text.count("\n", 0, m.start()) + 1
        _append_finding(
            findings,
            _SHARED_INLINE_RULE,
            "medium",
            "amplifier",
            path,
            lineno,
            f"replayed inline script ~{line_count} lines",
            "재실행 fragment 대형 inline → window.__*_BOUND idempotency 가드(기존 로드 번들 내). "
            "external 분리+defer 금지(단일리전 RTT 워터폴 = DCL 회귀). 먼저 TTFB/DCL 실측.",
            guard_mode=guard_mode,
        )


def _scan_sw_network_first_timeout(findings: list[Finding], *, guard_mode: bool) -> None:
    sw_path = "static/sw.js"
    text = _read_repo_text(sw_path)
    if not text or "networkFirst" not in text:
        return
    if "NETWORK_FIRST_TIMEOUT_MS" in text and "setTimeout" in text:
        return
    _append_finding(
        findings,
        _SW_TIMEOUT_RULE,
        "high",
        "sw-cache",
        sw_path,
        1,
        "networkFirst without timeout guard",
        "NETWORK_FIRST_TIMEOUT_MS + setTimeout 폴백 필수.",
        guard_mode=guard_mode,
    )


def _scan_fragment_replayed_listener(
    path: str,
    lineno: int,
    text: str,
    replayed_js: set[str],
    findings: list[Finding],
    *,
    guard_mode: bool,
) -> None:
    if path.startswith("static/"):
        js_rel = path[len("static/") :].replace("\\", "/")
        if js_rel in replayed_js and _GLOBAL_REPLAYED_EVENT_RE.search(text):
            full = _read_repo_text(path)
            if not _has_global_init_guard(full):
                _append_finding(
                    findings,
                    _SHELL_REPLAYED_SCRIPT_RULE,
                    "high",
                    "interaction-debt",
                    path,
                    lineno,
                    text,
                    "fragment JS listener → window.__*_BOUND singleton guard.",
                    guard_mode=guard_mode,
                )
        return
    if not path.startswith("templates/"):
        return
    if path not in _collect_replayed_template_paths():
        return
    js_rel = _js_from_template_line(text)
    if js_rel and js_rel in replayed_js and _unsafe_replayed_js(js_rel):
        _append_finding(
            findings,
            _SHELL_REPLAYED_SCRIPT_RULE,
            "high",
            "interaction-debt",
            path,
            lineno,
            text,
            f"static/{js_rel} fragment 재실행 → singleton guard.",
            guard_mode=guard_mode,
        )


def _scan_file_full(path: str, findings: list[Finding], replayed_js: set[str], *, guard_mode: bool) -> None:
    text = _read_repo_text(path)
    if not text:
        return
    lines = text.splitlines()
    numbered = list(enumerate(lines, 1))
    _scan_line_rules(path, numbered, findings, guard_mode=guard_mode)
    _scan_broad_cache_invalidation(path, numbered, findings, guard_mode=guard_mode)
    _scan_jsonb_path_filter(path, numbered, findings, guard_mode=guard_mode)
    _scan_mobile_queue_row_no_batch(path, numbered, findings, guard_mode=guard_mode)
    _scan_loop_db_queries(path, lines, findings, guard_mode=guard_mode)
    _scan_shell_polling(path, text, findings, replayed_js, guard_mode=guard_mode)
    _scan_shared_inline_scripts(path, text, findings, guard_mode=guard_mode)
    if path.startswith("static/"):
        js_rel = path[len("static/") :].replace("\\", "/")
        if js_rel in replayed_js and _unsafe_replayed_js(js_rel):
            for m in _GLOBAL_REPLAYED_EVENT_RE.finditer(text):
                lineno = text.count("\n", 0, m.start()) + 1
                _append_finding(
                    findings,
                    _SHELL_REPLAYED_SCRIPT_RULE,
                    "high",
                    "interaction-debt",
                    path,
                    lineno,
                    lines[lineno - 1] if lineno <= len(lines) else "",
                    "fragment JS listener → window.__*_BOUND singleton guard.",
                    guard_mode=guard_mode,
                )
                break
        return
    if path.startswith("templates/") and path in _collect_replayed_template_paths():
        for lineno, line in enumerate(lines, 1):
            js_rel = _js_from_template_line(line)
            if js_rel and js_rel in replayed_js and _unsafe_replayed_js(js_rel):
                _append_finding(
                    findings,
                    _SHELL_REPLAYED_SCRIPT_RULE,
                    "high",
                    "interaction-debt",
                    path,
                    lineno,
                    line,
                    f"static/{js_rel} fragment 재실행 → singleton guard.",
                    guard_mode=guard_mode,
                )


def _filter_baseline(findings: list[Finding], baseline: set[str], *, guard_mode: bool) -> list[Finding]:
    if not guard_mode or not baseline:
        return findings
    return [f for f in findings if f.fid not in baseline]


def _run(cmd: list[str]) -> str:
    try:
        out = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace", timeout=120
        ).stdout
        return out or ""
    except Exception:
        return ""


def guard(base: str) -> list[Finding]:
    diff = _run(["git", "diff", "--unified=0", base])
    findings: list[Finding] = []
    replayed_js = _collect_fragment_replayed_js_paths()
    baseline = _load_baseline_debt()
    cur_file = ""
    new_lineno = 0
    added_chunk: list[tuple[int, str]] = []
    touched_files: set[str] = set()

    def flush_chunk() -> None:
        nonlocal added_chunk
        if cur_file and added_chunk:
            _scan_loop_db_added_lines(cur_file, added_chunk, findings, guard_mode=True)
        added_chunk = []

    for raw in diff.splitlines():
        if raw.startswith("+++ b/"):
            flush_chunk()
            cur_file = raw[6:].strip()
            touched_files.add(cur_file)
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            new_lineno = int(m.group(1)) if m else 0
        elif raw.startswith("+") and not raw.startswith("+++"):
            line = raw[1:]
            added_line = [(new_lineno, line)]
            _scan_line_rules(cur_file, added_line, findings, guard_mode=True)
            _scan_broad_cache_invalidation(cur_file, added_line, findings, guard_mode=True)
            _scan_jsonb_path_filter(cur_file, added_line, findings, guard_mode=True)
            _scan_mobile_queue_row_no_batch(cur_file, added_line, findings, guard_mode=True)
            _scan_fragment_replayed_listener(cur_file, new_lineno, line, replayed_js, findings, guard_mode=True)
            added_chunk.append((new_lineno, line))
            new_lineno += 1
        elif not raw.startswith("-"):
            new_lineno += 1
    flush_chunk()
    for path in touched_files:
        text = _read_repo_text(path)
        if not text:
            continue
        _scan_shell_polling(path, text, findings, replayed_js, guard_mode=True)
        _scan_shared_inline_scripts(path, text, findings, guard_mode=True)
        if _is_fragment_scripts_partial(path):
            _scan_fragment_multi_script(path, text, findings, guard_mode=True)
    _scan_sw_network_first_timeout(findings, guard_mode=True)
    return _filter_baseline(findings, baseline, guard_mode=True)


def audit() -> list[Finding]:
    findings: list[Finding] = []
    replayed_js = _collect_fragment_replayed_js_paths()
    globs = ["templates/**/*.html", "static/**/*.js", "foms/**/*.py", "services/**/*.py", "apps/**/*.py"]
    seen: set[str] = set()
    for g in globs:
        for fp in ROOT.glob(g):
            rel = str(fp.relative_to(ROOT)).replace("\\", "/")
            if rel in seen or "/__pycache__/" in rel or "/backups/" in rel or "/tests/" in rel:
                continue
            seen.add(rel)
            _scan_file_full(rel, findings, replayed_js, guard_mode=False)
    for fp in ROOT.glob(_FRAGMENT_SCRIPTS_GLOB):
        rel = str(fp.relative_to(ROOT)).replace("\\", "/")
        if "/backups/" in rel:
            continue
        _scan_fragment_multi_script(rel, _read_repo_text(rel), findings, guard_mode=False)
    _scan_sw_network_first_timeout(findings, guard_mode=False)
    return findings


def build_radar(findings: list[Finding]) -> RadarReport:
    report = RadarReport()
    for dim in DIMENSIONS:
        report.dimensions[dim] = {"high": 0, "medium": 0, "low": 0, "top_files": []}

    file_counts: dict[str, dict[str, int]] = {d: {} for d in DIMENSIONS}
    for f in findings:
        bucket = report.dimensions.setdefault(
            f.dimension, {"high": 0, "medium": 0, "low": 0, "top_files": []}
        )
        bucket[f.severity] = bucket.get(f.severity, 0) + 1
        file_counts.setdefault(f.dimension, {})[f.file] = file_counts[f.dimension].get(f.file, 0) + 1
        if f.severity == "high":
            report.total_high += 1
        elif f.severity == "medium":
            report.total_medium += 1

    for dim in report.dimensions:
        ranked = sorted(file_counts.get(dim, {}).items(), key=lambda x: -x[1])[:5]
        report.dimensions[dim]["top_files"] = [f"{p} ({n})" for p, n in ranked]

    shared_kb = 0
    for fp in ROOT.glob("templates/partials/shared/**/*.html"):
        try:
            shared_kb += fp.stat().st_size
        except OSError:
            pass
    report.dimensions.setdefault("amplifier", {})["shared_partial_kb"] = round(shared_kb / 1024, 1)

    report.hot_paths_unmeasured = [
        "/erp/dashboard",
        "/erp/measurement",
        "mobile shell tab swap",
    ]
    if report.total_high:
        report.deploy_risk_summary = (
            f"high={report.total_high} — production 승격 전 수정·실측 필수. "
            f"상세: {RADAR_GUIDE}"
        )
    else:
        report.deploy_risk_summary = (
            f"high=0 medium={report.total_medium} — 잔여 medium은 주간 정리. "
            f"production 전 staging TTFB/EXPLAIN/SW 필수."
        )
    return report


def save_baseline(findings: list[Finding]) -> None:
    payload = {
        "version": 1,
        "finding_ids": sorted({f.fid for f in findings}),
    }
    BASELINE_DEBT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="FOMS ERP slowdown scanner")
    ap.add_argument("--guard", action="store_true", help="diff guard (default)")
    ap.add_argument("--audit", action="store_true", help="full codebase audit")
    ap.add_argument("--radar", action="store_true", help="8-dimension summary (runs audit)")
    ap.add_argument("--seed-baseline", action="store_true", help="write baseline_debt.json from audit")
    ap.add_argument("--base", default="HEAD", help="guard diff base ref")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.radar or args.seed_baseline:
        args.audit = True

    if args.audit:
        findings = audit()
        guard_mode = False
    else:
        findings = guard(args.base)
        guard_mode = True

    if args.seed_baseline:
        save_baseline(findings)
        print(f"baseline saved: {len(findings)} findings → {BASELINE_DEBT.relative_to(ROOT)}")
        return 0

    findings.sort(key=lambda f: ({"high": 0, "medium": 1, "low": 2}[f.severity], f.file, f.line))

    if args.radar:
        radar = build_radar(findings)
        if args.json:
            out = asdict(radar)
            out["findings_count"] = len(findings)
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print("=== FOMS ERP Slowdown Radar ===")
            print(radar.deploy_risk_summary)
            for dim, stats in radar.dimensions.items():
                h, m = stats.get("high", 0), stats.get("medium", 0)
                if h or m:
                    print(f"  [{dim}] high={h} medium={m} top={stats.get('top_files', [])[:2]}")
            print(f"\n총 findings={len(findings)}  ({RADAR_GUIDE})")
        return 0

    if args.json:
        print(json.dumps([asdict(f) for f in findings], ensure_ascii=False, indent=1))
    else:
        mode = "AUDIT" if args.audit else f"GUARD vs {args.base}"
        print(f"=== FOMS 성능 스캔 [{mode}] ===")
        if not findings:
            print("문제 없음 ✅")
        for f in findings:
            print(f"[{f.severity.upper()}] {f.rule}/{f.dimension}  {f.file}:{f.line}")
            print(f"    {f.snippet}")
            print(f"    → {f.fix}")
        highs = sum(1 for f in findings if f.severity == "high")
        meds = sum(1 for f in findings if f.severity == "medium")
        print(f"\n요약: high={highs} medium={meds} 총={len(findings)}  ({GUIDE})")

    if args.audit:
        return 0
    return 1 if any(f.severity == "high" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
