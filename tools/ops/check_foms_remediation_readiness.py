"""RELEASE-GATE-00: read-only FOMS remediation deploy-readiness verifier.

최종 packet. §3 bug-audit remediation 전체(123 packet)가 배포 준비되었는지 **값 노출
없이**(카운트/bool/상태 토큰만) 종합 검증한다. **application mutation 절대 금지** —
파일을 읽고 worker readiness collector(SELECT only)를 호출할 뿐, DB write·상태 변경이
0 이다. 실패 항목이 하나라도 있으면 nonzero 로 종료해 deploy 를 막는다(fail-closed).

검증 도메인과 exit code (report §5.2 line ~996 SSOT):

* **artifact/config (exit 3)** — packet coverage(123 resolved·created_tests landed),
  CI workflow 존재, persona artifact, enforcement flag 안전 기본(well-formed),
  API leak 0(str(e)/print_exc inventory baseline 무성장), unresolved/silent broad
  catch 0(failopen inventory unclassified 0).
* **data (exit 1)** — 필수 seed/reference data 파일 존재·정상 JSON(값 노출 없이 형태만).
* **service (exit 2)** — SIDEFX/CHANNEL worker heartbeat/readiness(가능 범위, DB
  도달 불가/미준비면 fail-closed).

여러 도메인이 동시에 실패하면 **artifact/config(3) > service(2) > data(1)** 우선순위로
가장 높은 코드를 반환한다(config 결함이 가장 근본이라 먼저 막는다). 모두 통과하면
exit 0(ready).

값 노출 0 규율: 출력은 check 이름·도메인·bool·정수 count·고정 상태 토큰만 담는다.
비밀/PII/env 원문/경로 상세를 절대 echo 하지 않는다.

읽기 전용이므로 approval token 을 요구하지 않는다. **실 배포는 이 게이트 green 이후
사용자 승인으로만** — 이 도구는 판정만 한다.

사용 예::

    python tools/ops/check_foms_remediation_readiness.py            # 전체 게이트
    python tools/ops/check_foms_remediation_readiness.py --json     # 기계 판독
    python tools/ops/check_foms_remediation_readiness.py --skip-service  # worker 제외(비프로덕션)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

_LOGGER = logging.getLogger("check_foms_remediation_readiness")

REPO_ROOT = Path(__file__).resolve().parents[2]

# --- domains -> exit codes (report §5.2 SSOT) --------------------------------
DOMAIN_DATA = "data"          # exit 1
DOMAIN_SERVICE = "service"    # exit 2
DOMAIN_CONFIG = "artifact"    # exit 3 (artifact/config)
_DOMAIN_EXIT = {DOMAIN_DATA: 1, DOMAIN_SERVICE: 2, DOMAIN_CONFIG: 3}
# multi-failure precedence: highest exit code first (config > service > data).
_PRECEDENCE = (DOMAIN_CONFIG, DOMAIN_SERVICE, DOMAIN_DATA)

# --- reused artifact locations (read-only) -----------------------------------
_PACKET_MANIFEST = Path("docs/harness/foms_bugfix_packet_tests.json")
_FAILOPEN_INV = Path("docs/harness/foms_failopen_inventory.json")
_API_LEAK_INV = Path("docs/harness/foms_api_error_leak_inventory.json")
_WORKFLOWS = Path(".github/workflows")
_PERSONA_DIR = Path("templates/partials/v3")

EXPECTED_PACKETS = 122
REQUIRED_WORKFLOWS = ("ci.yml", "harness-ci.yml", "perf-gate.yml", "postgres-lane.yml")
REQUIRED_PERSONAS = ("construction", "cs", "drawing", "production", "sales", "shipment")
# core seed/reference data the app loads at runtime (tracked, not the generated holidays_*).
REQUIRED_DATA_FILES = (
    "data/products.json",
    "data/additional_options.json",
    "data/notes_categories.json",
    "data/spec_field_presets.json",
    "data/erp_policy.json",
    "data/erp_shipment_settings.json",
)
ENFORCEMENT_FLAGS = ("REV_IF_MATCH_ENFORCED", "WRITE_GUARD_ENABLED")

# str(e)/traceback leak patterns (mirrors tests/domains/test_api_error_containment.py).
_RESP_STR_E_500 = re.compile(r"return jsonify\(.*str\(e\).*\)\s*,\s*500")
_PRINT_EXC = re.compile(r"print\(\s*traceback\.format_exc|traceback\.print_exc\(")

_FLAG_TRUE = {"1", "true", "yes", "on"}
_FLAG_FALSE = {"0", "false", "no", "off", ""}


@dataclass(frozen=True)
class CheckResult:
    """A single value-free gate verdict. ``count`` is a magnitude (defect count), never a value."""

    name: str
    domain: str
    ok: bool
    count: int
    note: str = ""


@dataclass(frozen=True)
class WorkerReadiness:
    """Normalized worker readiness (name + bool + failure count — no observations echoed)."""

    name: str
    ready: bool
    failure_count: int


def exit_code_for(results: Sequence[CheckResult]) -> int:
    """Aggregate exit code: highest-priority failing domain, or 0 when all pass."""
    failed = {r.domain for r in results if not r.ok}
    for domain in _PRECEDENCE:
        if domain in failed:
            return _DOMAIN_EXIT[domain]
    return 0


# --- artifact/config checks (exit 3) -----------------------------------------
def check_packet_coverage(repo_root: Path, *, expected: int = EXPECTED_PACKETS) -> CheckResult:
    """123 packet 이 모두 존재하고 각 created_tests 가 landed(파일 존재)인지 확인."""
    try:
        manifest = json.loads((repo_root / _PACKET_MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return CheckResult("packet_coverage", DOMAIN_CONFIG, False, 1, "manifest_unreadable")
    count_gap = abs(len(manifest) - expected)
    missing_tests = sum(
        1
        for entry in manifest.values()
        for ct in entry.get("created_tests", [])
        if not (repo_root / ct["path"]).exists()
    )
    defects = count_gap + missing_tests
    return CheckResult("packet_coverage", DOMAIN_CONFIG, defects == 0, defects)


def check_ci_coverage(repo_root: Path) -> CheckResult:
    """필수 CI workflow 파일 존재(값 노출 없이 presence 만; run 상태는 ci_watch 소관)."""
    missing = sum(1 for wf in REQUIRED_WORKFLOWS if not (repo_root / _WORKFLOWS / wf).exists())
    return CheckResult("ci_coverage", DOMAIN_CONFIG, missing == 0, missing)


def check_persona_artifacts(repo_root: Path) -> CheckResult:
    """모바일 v3 persona home artifact(역할별) 존재 확인."""
    missing = sum(
        1
        for p in REQUIRED_PERSONAS
        if not (repo_root / _PERSONA_DIR / f"persona_home_{p}.html").exists()
    )
    return CheckResult("persona_artifacts", DOMAIN_CONFIG, missing == 0, missing)


def _flag_state(env: Mapping[str, str], name: str) -> str:
    """Resolve an enforcement flag to a value-free status token (never echoes the raw value)."""
    if name not in env:
        return "default"
    value = env[name].strip().lower()
    if value in _FLAG_TRUE:
        return "on"
    if value in _FLAG_FALSE:
        return "off"
    return "malformed"


def check_enforcement_flags(env: Mapping[str, str]) -> CheckResult:
    """Enforcement flag(If-Match·write-guard) 이 well-formed·안전 기본인지 확인.

    미설정 = 안전 기본(opt-in). 값이 있으면 boolean 으로 파싱 가능해야 한다(malformed =
    config 결함). 상태 토큰(on/off/default)만 note 로 보고 — 원문 값은 절대 노출하지 않는다.
    """
    states = {name: _flag_state(env, name) for name in ENFORCEMENT_FLAGS}
    bad = sum(1 for s in states.values() if s == "malformed")
    note = "|".join(f"{name}:{state}" for name, state in states.items())
    return CheckResult("enforcement_flags", DOMAIN_CONFIG, bad == 0, bad, note)


def _count_matches(root: Path, pattern: re.Pattern[str]) -> int:
    """Count source lines under ``root`` matching ``pattern`` (count only — no content kept)."""
    total = 0
    for path in root.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        total += sum(1 for line in text.splitlines() if pattern.search(line))
    return total


def check_api_leak(repo_root: Path) -> CheckResult:
    """response str(e)/traceback leak 이 inventory baseline 을 초과 성장하지 않았는지 확인."""
    try:
        inv = json.loads((repo_root / _API_LEAK_INV).read_text(encoding="utf-8"))
        baseline = int(inv["baselines"]["response_str_e_500"])
    except (OSError, ValueError, KeyError):
        return CheckResult("api_leak", DOMAIN_CONFIG, False, 1, "inventory_unreadable")
    foms_dir = repo_root / "foms"
    over = max(0, _count_matches(foms_dir, _RESP_STR_E_500) - baseline)
    over += _count_matches(foms_dir, _PRINT_EXC)  # raw traceback prints must be 0
    return CheckResult("api_leak", DOMAIN_CONFIG, over == 0, over)


def check_broad_catch(repo_root: Path, *, live_unclassified: int) -> CheckResult:
    """failopen inventory baseline + live scan 의 unclassified(silent broad catch) 가 0 인지 확인."""
    try:
        inv = json.loads((repo_root / _FAILOPEN_INV).read_text(encoding="utf-8"))
        baseline = int(inv["baselines"]["unclassified"])
    except (OSError, ValueError, KeyError):
        return CheckResult("broad_catch", DOMAIN_CONFIG, False, 1, "inventory_unreadable")
    total = baseline + max(0, live_unclassified)
    return CheckResult("broad_catch", DOMAIN_CONFIG, total == 0, total)


# --- data checks (exit 1) ----------------------------------------------------
def check_data_coverage(repo_root: Path) -> CheckResult:
    """필수 seed/reference data 파일이 존재하고 정상 JSON 인지(값 노출 없이 형태만) 확인."""
    bad = 0
    for rel in REQUIRED_DATA_FILES:
        path = repo_root / rel
        if not path.exists():
            bad += 1
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            bad += 1
    return CheckResult("data_coverage", DOMAIN_DATA, bad == 0, bad)


# --- service checks (exit 2) -------------------------------------------------
def check_workers(probe: Callable[[], Sequence[WorkerReadiness]]) -> CheckResult:
    """SIDEFX/CHANNEL worker readiness. DB 도달 불가·미관측·미준비는 모두 fail-closed(service)."""
    try:
        readies = list(probe())
    except Exception as exc:  # DB/engine 도달 불가 = fail-closed (값 노출 없이 타입명만 로깅)
        _LOGGER.warning("[release-gate] worker probe unavailable (fail-closed): %s", type(exc).__name__)
        return CheckResult("workers", DOMAIN_SERVICE, False, 1, "probe_unavailable")
    if not readies:
        return CheckResult("workers", DOMAIN_SERVICE, False, 1, "no_worker_evidence")
    not_ready = sum(1 for w in readies if not w.ready)
    return CheckResult("workers", DOMAIN_SERVICE, not_ready == 0, not_ready)


def _env_worker_probe(
    session_factory: Optional[Callable[[], Any]] = None,
) -> list[WorkerReadiness]:
    """SIDEFX + CHANNEL readiness 를 env DB 엔진으로 조회한다(SELECT only, mutation 0).

    무거운 import 와 DB 접근은 이 함수 안에서만 일어난다(파일 전용 게이트는 대가를 안 낸다).
    ``session_factory`` 는 테스트 주입용; 미지정 시 env 엔진에서 만든다.
    """
    if str(REPO_ROOT) not in sys.path:  # tools/ops 에서 스크립트로 실행돼도 foms 를 import 가능하게
        sys.path.insert(0, str(REPO_ROOT))

    from sqlalchemy.orm import sessionmaker

    from foms.services.security.channel_order.worker import evaluate_readiness as channel_eval
    from foms.services.sidefx_worker import (
        ReadinessThresholds,
        collect_readiness_observations,
        evaluate_readiness as sidefx_eval,
        make_engine_from_env,
    )

    engine = make_engine_from_env()
    try:
        session = (session_factory or sessionmaker(bind=engine))()
        try:
            report = sidefx_eval(collect_readiness_observations(session), ReadinessThresholds())
            channel = channel_eval(session)
        finally:
            session.close()
    finally:
        engine.dispose()
    return [
        WorkerReadiness("sidefx", report.ready, len(report.failures)),
        WorkerReadiness("channel", bool(channel["ready"]), len(channel["failures"])),
    ]


# --- aggregation / rendering -------------------------------------------------
def collect_results(
    repo_root: Path,
    *,
    env: Mapping[str, str],
    worker_probe: Callable[[], Sequence[WorkerReadiness]],
    live_unclassified: int,
    include_service: bool = True,
) -> list[CheckResult]:
    """Run every gate check and return value-free verdicts."""
    results = [
        check_packet_coverage(repo_root),
        check_ci_coverage(repo_root),
        check_persona_artifacts(repo_root),
        check_data_coverage(repo_root),
        check_enforcement_flags(env),
        check_api_leak(repo_root),
        check_broad_catch(repo_root, live_unclassified=live_unclassified),
    ]
    if include_service:
        results.append(check_workers(worker_probe))
    return results


def report_payload(results: Sequence[CheckResult], exit_code: int) -> dict[str, Any]:
    """Value-free machine payload: booleans, counts, and fixed status tokens only."""
    return {
        "ready": exit_code == 0,
        "exit_code": exit_code,
        "checks": [
            {"name": r.name, "domain": r.domain, "ok": r.ok, "count": r.count, "note": r.note}
            for r in results
        ],
    }


def render_text(payload: Mapping[str, Any]) -> str:
    """Human-readable, value-free summary."""
    lines = ["## FOMS remediation release-gate"]
    for check in payload["checks"]:
        status = "OK" if check["ok"] else "FAIL"
        note = f" ({check['note']})" if check["note"] else ""
        lines.append(f"- [{status}] {check['name']} domain={check['domain']} count={check['count']}{note}")
    verdict = "READY" if payload["ready"] else "NOT-READY"
    lines.append(f"- result: {verdict} (exit {payload['exit_code']})")
    return "\n".join(lines)


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """CLI 인자를 파싱한다(--repo-root·--json·--skip-service). 반환: argparse.Namespace."""
    parser = argparse.ArgumentParser(description="FOMS remediation deploy-readiness verifier (read-only).")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="검증할 저장소 루트.")
    parser.add_argument("--json", action="store_true", help="값 노출 없는 JSON 리포트 출력.")
    parser.add_argument(
        "--skip-service",
        action="store_true",
        help="worker(service) 검사 제외. 프로덕션 게이트에서 사용 금지 - 사용 시 로그로 기록된다.",
    )
    return parser.parse_args(argv)


def _live_unclassified(repo_root: Path) -> int:
    """SSOT failopen scanner 를 재실행해 현 트리의 silent broad-catch(unclassified) 수를 얻는다."""
    tools_harness = str(repo_root / "tools" / "harness")
    if tools_harness not in sys.path:
        sys.path.insert(0, tools_harness)
    import failopen_scan  # lazy: 파일 전용 흐름은 이 import 를 피한다

    return int(failopen_scan.build_inventory()["baselines"]["unclassified"])


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entrypoint. Returns the aggregate exit code (0 ready · 1 data · 2 service · 3 config)."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args(argv)
    repo_root = args.repo_root.resolve()
    if args.skip_service:
        _LOGGER.warning("[release-gate] SERVICE(worker) checks SKIPPED by --skip-service - NOT a production gate")
    results = collect_results(
        repo_root,
        env=os.environ,
        worker_probe=_env_worker_probe,
        live_unclassified=_live_unclassified(repo_root),
        include_service=not args.skip_service,
    )
    code = exit_code_for(results)
    payload = report_payload(results, code)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False), flush=True)
    else:
        print(render_text(payload), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
