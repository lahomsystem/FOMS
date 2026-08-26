#!/usr/bin/env python
"""CI 감시·자동 복구 게이트 (크로스플랫폼 정본).

`scripts/ops/ci_watch_recover.sh` 로직을 Python 으로 이식해 3-도구(Claude Code·
Cursor·기타 CLI) 공통으로 결정적 배선한다. push 후 대상 커밋의 모든 GitHub
Actions 워크플로 완료를 폴링하고, 실패를 분류해 자동 복구하거나 코드 실패
로그를 출력한다.

실패 분류·대응:
  - perf-gate "wait_staging_deploy 타임아웃": Railway 배포가 CI 대기보다 느렸던 것
    → healthz commit==SHA 확인되면 자동 재실행(배포 완료 후 통과)
  - perf-gate TTFB/render tail flaky(근소 초과): 네트워크 tail → 자동 재실행 1회
  - perf-gate bytes 초과: 데이터 가변 탭이면 코드 회귀 아님 → perf_budgets.json
    관측×1.3 보정값을 "제안"(적용은 사람 확인 — 무한 자동 상향은 회귀 은폐라 금지)
  - Harness/FOMS CI 실패: 코드 문제 → 실패 스텝·로그 tail 출력(사람/에이전트 수정)

종료 코드 계약(--until-final, 기본 = 블로킹 감시):
    0  전부 green
    1  코드 실패(에이전트가 근본 수정 후 재푸시 필요) — 실패 워크플로/잡/로그 tail 출력.
       자동 재실행/배포 대기 라운드 상한(MAX_RERUN_ROUNDS) 초과로 수렴 실패 시에도 1
       (무한 재폴링 대신 코드 조사 필요로 승격 — 구 2 반환은 계약(0/1 수렴) 위반이었음).
    3  gh CLI 부재/미인증 — 게이트 불가 사유 출력(fail-open 아님)
    4  폴링 상한(MAX_POLLS) 내 CI 미완료(진행 중) — false-green 방지, 재폴링/재시도 필요.
    (2 는 --no-until-final 단발 모드에서만 반환: 자동 재실행/배포 대기 발동 → 호출자가 재폴링)

종료 코드 계약(--quick, 단발 조회 = 논블로킹 루프용):
    0  전부 green
    1  코드 실패 — 실패 워크플로 + 로그 tail 출력
    3  gh CLI 부재/미인증
    4  진행 중(pending 워크플로명 + 경과 초 출력). perf-gate 자동 재실행을
       트리거한 경우도 4(재실행 중복은 상태 파일로 방지).

사용:
    python tools/harness/ci_watch.py [SHA] [BRANCH] [--quick] [--no-until-final] [--healthz URL]
      SHA      기본 = 현재 HEAD
      BRANCH   기본 = deploy
      --quick  폴링 없이 현재 상태만 1회 조회하고 즉시 종료(exit 0/1/3/4, 블로킹 금지)
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

DEFAULT_BRANCH = "deploy"
DEFAULT_HEALTHZ = "https://lahom-dev.up.railway.app/healthz"

# 폴링 파라미터: 고정 초기 대기 없이 즉시 1차 조회 → 워크플로 등록까지 5s 간격 재시도
# (최대 60s) → 등록 후 10s 간격 × 최대 240회(≈ 40분 상한). 반응속도 개선(구 30s 초기 대기 제거).
REGISTER_RETRY_INTERVAL_SEC = 5
REGISTER_MAX_WAIT_SEC = 60
POLL_INTERVAL_SEC = 10
MAX_POLLS = 240

# --quick 재실행 중복 방지 상태 파일(gitignore 대상 — 저장소 docs/harness/runtime 하위)
RERUN_STATE_FILE = "docs/harness/runtime/.ci_watch_rerun_state.json"

# --until-final 안전 상한: 자동 재실행/배포 대기 라운드 최대치(무한 루프 차단)
MAX_RERUN_ROUNDS = 3

# gh subprocess sentinel 반환 코드
_GH_NOT_FOUND = 127
_GH_TIMEOUT = 124

# 분류 액션 → 종료 코드 매핑용 버킷
_ACTION_NEEDS_FIX = frozenset({"code_fail", "budget", "unclassified"})
_ACTION_RERUN = frozenset({"rerun", "wait_deploy"})


# ---------------------------------------------------------------------------
# subprocess seam (테스트에서 monkeypatch 하는 유일한 외부 호출 지점)
# ---------------------------------------------------------------------------
def run_gh(args: list[str], timeout: int = 90) -> tuple[int, str, str]:
    """`gh` CLI 를 실행해 (returncode, stdout, stderr) 를 반환한다.

    파라미터:
        args: `gh` 뒤에 붙일 인자 리스트.
        timeout: 초 단위 타임아웃.
    반환: (returncode, stdout, stderr). gh 미설치는 (127, "", ...),
          타임아웃은 (124, "", ...) 로 정규화한다(예외를 밖으로 던지지 않음).
    """
    try:
        proc = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return _GH_NOT_FOUND, "", "gh CLI not found on PATH"
    except subprocess.TimeoutExpired:
        return _GH_TIMEOUT, "", f"gh timed out after {timeout}s"


def resolve_ref(ref: str) -> str:
    """`git rev-parse` 로 리터럴 ref(HEAD/브랜치명/짧은 SHA)를 full commit SHA 로 정규화한다.

    파라미터:
        ref: 해석할 git ref 문자열(예: "HEAD", "deploy", 짧은/전체 SHA).
    반환: 40자 full commit SHA. 잘못된 ref·git 부재·타임아웃 시 빈 문자열.
          `--verify --quiet ... ^{commit}` 이라 유효하지 않은 ref 는 stdout 없이 실패한다.
          (리터럴 "HEAD" 를 정규화 없이 조회해 "워크플로 없음 → green" 오판하는 false-green 차단.)
    """
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def current_head_sha() -> str:
    """현재 HEAD 를 full commit SHA 로 반환한다(실패 시 빈 문자열)."""
    return resolve_ref("HEAD")


def check_healthz(url: str, sha_short: str, timeout: int = 10) -> bool:
    """healthz 엔드포인트의 commit 이 sha_short 로 시작하면 True(배포 완료 확인)."""
    import urllib.request  # 지연 import: 폴링 hot path 밖

    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - 고정 내부 URL
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return str(data.get("commit", "")).startswith(sha_short)
    except Exception:  # noqa: BLE001 - 네트워크/파싱 실패는 "미완"으로 안전 처리
        return False


# ---------------------------------------------------------------------------
# 전제 조건: gh 준비 상태 (fail-open 아님 — 게이트 불가 사유를 명시)
# ---------------------------------------------------------------------------
def gh_ready() -> tuple[bool, str]:
    """gh CLI 설치·인증 상태를 확인한다.

    반환: (준비됨, 사유). 준비 안 됨이면 사유 문자열에 해결 안내를 담는다.
    """
    rc, _out, _err = run_gh(["auth", "status"], timeout=25)
    if rc == _GH_NOT_FOUND:
        return False, "gh CLI 미설치 — https://cli.github.com 설치 후 `gh auth login`"
    if rc == _GH_TIMEOUT:
        return False, "gh CLI 응답 타임아웃 — 네트워크 확인 후 재시도"
    if rc != 0:
        return False, "gh CLI 미인증 — `gh auth login` 후 재시도"
    return True, ""


# ---------------------------------------------------------------------------
# 워크플로 조회·폴링
# ---------------------------------------------------------------------------
def list_runs(branch: str, sha_short: str) -> list[dict]:
    """대상 브랜치의 최근 run 중 headSha 가 sha_short 로 시작하는 것만 반환한다.

    --limit 은 20(구 8) — 연속 푸시로 최근 목록이 다른 커밋 run 으로 채워질 때
    대상 SHA run 이 조회창 밖으로 밀려 "워크플로 없음 → green" 오판하는 것을 막는다.
    """
    rc, out, _err = run_gh(
        [
            "run", "list", "--branch", branch, "--limit", "20",
            "--json", "headSha,status,conclusion,databaseId,workflowName,createdAt",
        ]
    )
    if rc != 0 or not out.strip():
        return []
    try:
        data = json.loads(out)
    except ValueError:
        return []
    if not isinstance(data, list):
        return []
    return [r for r in data if str(r.get("headSha", "")).startswith(sha_short)]


def all_completed(runs: list[dict]) -> bool:
    """대상 run 이 1개 이상이고 전부 completed 이면 True."""
    return bool(runs) and all(r.get("status") == "completed" for r in runs)


# CI-CONCLUSION-01: green 은 success 하나뿐이다.
#
# 예전에는 conclusion == "failure" 인 run 만 실패로 셌다. 그래서 cancelled /
# timed_out / startup_failure / action_required 는 전부 조용히 green 으로 통과했다.
# 실제로 perf-gate 에서 cancelled 4 건이 그렇게 통과했고, AGENTS.md 의 "CI green
# 까지가 push 완료" 계약이 아무도 모르게 네 번 깨졌다.
#
# 판정은 fail-closed 다. success 가 아닌 종료 상태는 "검증되지 않았다" 는 뜻이고,
# 검증되지 않은 것을 green 이라 부르지 않는다.
_GREEN_CONCLUSIONS = frozenset({"success"})


def failures(runs: list[dict]) -> list[dict]:
    """완료됐지만 success 가 아닌 run 을 전부 반환한다(cancelled 포함)."""
    out = []
    for r in runs:
        conclusion = r.get("conclusion")
        if conclusion is None:  # 아직 진행 중 — all_completed 가 따로 본다
            continue
        if conclusion in _GREEN_CONCLUSIONS:
            continue
        out.append(r)
    return out


def poll_completion(
    branch: str,
    sha_short: str,
    *,
    sleep_fn: Callable[[float], None] = time.sleep,
    interval: int = POLL_INTERVAL_SEC,
    max_polls: int = MAX_POLLS,
    register_retry_interval: int = REGISTER_RETRY_INTERVAL_SEC,
    register_max_wait: int = REGISTER_MAX_WAIT_SEC,
) -> list[dict]:
    """워크플로가 전부 completed 될 때까지 폴링하고 최종 run 목록을 반환한다.

    고정 초기 대기 없이 즉시 1차 조회한다(반응속도 개선). 워크플로가 아직
    미등록(runs 비어 있음)이면 register_retry_interval 간격으로 register_max_wait 까지
    재시도하고, 등록 후에는 interval 간격으로 전부 완료될 때까지 폴링한다.
    """
    runs = list_runs(branch, sha_short)
    waited = 0
    while not runs and waited < register_max_wait:
        sleep_fn(register_retry_interval)
        waited += register_retry_interval
        runs = list_runs(branch, sha_short)
    for _ in range(max_polls):
        if not runs or all_completed(runs):
            break
        sleep_fn(interval)
        runs = list_runs(branch, sha_short)
    return runs


# ---------------------------------------------------------------------------
# 실패 분류 (순수 함수 — 테스트 대상)
# ---------------------------------------------------------------------------
def classify_perf_gate(log: str) -> tuple[str, dict]:
    """perf-gate 실패 로그를 카테고리로 분류한다(순수 함수).

    반환: (category, info). category ∈
      {"deploy_timeout", "flaky", "bytes", "unknown"}.
      bytes 는 info={"obs", "budget", "suggest", "path"} 를 채운다.
    """
    if re.search(r"wait-deploy.*타임아웃|Wait for staging deploy", log):
        return "deploy_timeout", {}
    # flaky 는 'ms' 로 bytes 초과와 구분한다(bytes 도 '> budget' 을 포함하므로 순서 중요).
    if re.search(r"> budget.*ms|render \d+ms > budget", log):
        return "flaky", {}
    m = re.search(r"bytes (\d+) > budget (\d+)", log)
    if m:
        obs = int(m.group(1))
        budget = int(m.group(2))
        path_match = re.search(r"/erp/[a-z/]+\?view=fragment", log)
        return "bytes", {
            "obs": obs,
            "budget": budget,
            "suggest": int(obs * 1.3),
            "path": path_match.group(0) if path_match else "(경로 미상)",
        }
    return "unknown", {}


def exit_code_for(actions: list[str]) -> int:
    """분류 액션 목록으로 최종 종료 코드를 계산한다.

    우선순위: 에이전트 조치 필요(1) > 자동 재실행/대기(2) > green(0).
    """
    if any(a in _ACTION_NEEDS_FIX for a in actions):
        return 1
    if any(a in _ACTION_RERUN for a in actions):
        return 2
    return 0


# ---------------------------------------------------------------------------
# 실패별 대응
# ---------------------------------------------------------------------------
def handle_perf_gate(
    run_id: int,
    log: str,
    sha_short: str,
    healthz: str,
    already_rerun: set,
) -> tuple[str, str]:
    """perf-gate 실패 1건을 분류·복구한다. 반환: (action, message)."""
    category, info = classify_perf_gate(log)

    if category == "deploy_timeout":
        if run_id in already_rerun:
            return "code_fail", "  원인=배포 타임아웃 재발(재실행 후에도) — 수동 확인 필요"
        if check_healthz(healthz, sha_short):
            rc, _out, _err = run_gh(["run", "rerun", str(run_id)])
            if rc == 0:
                already_rerun.add(run_id)
                return "rerun", f"  원인=배포 대기 타임아웃, healthz={sha_short} 배포 완료 → 재실행 요청됨"
            return "unclassified", "  배포는 완료됐으나 rerun 요청 실패 — 수동 재실행 필요"
        return "wait_deploy", f"  배포 미완(healthz≠{sha_short}) — 재폴링 대기"

    if category == "flaky":
        if run_id in already_rerun:
            return "code_fail", "  원인=TTFB/render tail 재발(재실행 후에도) — 네트워크 아닌 코드 회귀 조사 필요"
        rc, _out, _err = run_gh(["run", "rerun", str(run_id)])
        if rc == 0:
            already_rerun.add(run_id)
            return "rerun", "  원인=TTFB/render tail flaky(근소 초과) → 재실행 요청됨"
        return "unclassified", "  flaky 판정했으나 rerun 요청 실패 — 수동 재실행 필요"

    if category == "bytes":
        return "budget", (
            f"  원인=bytes 초과(관측 {info['obs']} > budget {info['budget']}). 데이터 가변 탭이면 코드 회귀 아님.\n"
            f"  ▶ 수정 제안: perf_budgets.json '{info['path']}' body_bytes_max → {info['suggest']} (관측×1.3)\n"
            f"    (데이터 가변 확인 후 적용. 코드성 비만이면 dTTFB/쿼리 계약이 별도로 잡음)"
        )

    return "unclassified", f"  원인 미분류 — 로그 확인 필요: gh run view {run_id} --log"


def handle_code_fail(run_id: int) -> tuple[str, str]:
    """비-perf-gate(코드 CI) 실패 1건의 실패 스텝·로그 tail 을 수집한다."""
    lines = ["  코드 CI 실패 → 실패 스텝/로그(수정 필요):"]
    _rc, steps_out, _err = run_gh(
        [
            "run", "view", str(run_id), "--json", "jobs", "--jq",
            '.jobs[].steps[]|select(.conclusion=="failure")|"    step: "+.name',
        ]
    )
    if steps_out.strip():
        lines.append(steps_out.rstrip("\n"))
    _rc2, log_out, _err2 = run_gh(["run", "view", str(run_id), "--log-failed"])
    tail = [ln for ln in log_out.splitlines() if re.search(r"error|assert|failed|fail", ln, re.I)][:8]
    lines.extend("    " + ln.strip() for ln in tail)
    return "code_fail", "\n".join(lines)


def handle_failures(
    fails: list[dict],
    sha_short: str,
    healthz: str,
    already_rerun: set,
    printer: Callable[[str], None] = print,
) -> int:
    """실패 워크플로들을 분류·대응하고 종료 코드를 반환한다."""
    actions: list[str] = []
    for run in fails:
        run_id = run.get("databaseId")
        workflow = run.get("workflowName", "")
        printer(f"----- {workflow} ({run_id}) -----")
        conclusion = str(run.get("conclusion") or "")
        if conclusion != "failure":
            # 코드가 틀려서 실패한 게 아니라 아예 완주하지 못한 run. 로그를 뒤져도
            # 실패 스텝이 없으므로 분류만 하고 넘긴다 — 다만 green 은 아니다.
            actions.append("unclassified")
            printer(
                f"  종료 상태 '{conclusion}' — 이 커밋은 검증되지 않았다. "
                "재실행하거나 취소 사유를 확인하라(green 아님)."
            )
            continue
        if "perf-gate" in str(workflow).lower():
            _rc, log, _err = run_gh(["run", "view", str(run_id), "--log"])
            action, message = handle_perf_gate(run_id, log, sha_short, healthz, already_rerun)
        else:
            action, message = handle_code_fail(run_id)
        printer(message)
        actions.append(action)
    return exit_code_for(actions)


# ---------------------------------------------------------------------------
# 감시 루프
# ---------------------------------------------------------------------------
def watch_once(
    sha: str,
    branch: str,
    healthz: str,
    already_rerun: set,
    *,
    sleep_fn: Callable[[float], None] = time.sleep,
    printer: Callable[[str], None] = print,
) -> int:
    """폴링 1회전을 수행하고 종료 코드를 반환한다(0/1/2/4; 재폴링은 watch 가 담당).

    폴링 상한(MAX_POLLS) 내에 completed 되지 못한 run 이 남았으면 실패 집계로
    넘어가지 않고 exit 4(진행 중)를 반환해 false-green(구 exit 0 오판)을 막는다.
    """
    sha_short = sha[:8]
    printer(f"[ci-watch] target={sha_short} branch={branch}")
    runs = poll_completion(branch, sha_short, sleep_fn=sleep_fn)
    if not runs:
        printer("[ci-watch] 대상 커밋의 워크플로 없음(paths-ignore 등) — green 취급")
        return 0
    if not all_completed(runs):
        pending = [r for r in runs if r.get("status") != "completed"]
        names = ", ".join(sorted({str(r.get("workflowName", "?")) for r in pending})) or "(이름 미상)"
        printer(f"[ci-watch] 폴링 상한 내 미완료(진행 중): {names} — 재폴링/재시도 필요")
        return 4
    fails = failures(runs)
    if not fails:
        printer("[ci-watch] ALL GREEN ✓")
        return 0
    printer(f"[ci-watch] {len(fails)} failed workflow(s):")
    for run in fails:
        printer(f" - {run.get('workflowName')}")
    return handle_failures(fails, sha_short, healthz, already_rerun, printer)


def watch(
    sha: str,
    branch: str,
    healthz: str,
    *,
    until_final: bool = True,
    sleep_fn: Callable[[float], None] = time.sleep,
    printer: Callable[[str], None] = print,
    max_rounds: int = MAX_RERUN_ROUNDS,
) -> int:
    """감시 진입점. until_final 이면 exit 2(재실행/대기)를 자체 재폴링해 0/1/4 로 수렴한다.

    라운드 상한(max_rounds) 초과 시에는 구현상 2 를 그대로 흘리지 않고 exit 1(수렴 실패=
    코드 조사 필요)로 승격한다 — docstring 계약("0/1 로 수렴")과 일치시키기 위함이다.
    exit 4(폴링 상한 내 미완)는 재폴링해도 같은 상한에 다시 걸리므로 그대로 전파한다.
    """
    already_rerun: set = set()
    rounds = 0
    while True:
        code = watch_once(sha, branch, healthz, already_rerun, sleep_fn=sleep_fn, printer=printer)
        if code != 2 or not until_final:
            return code
        rounds += 1
        if rounds > max_rounds:
            printer(f"[ci-watch] 자동 재실행/배포 대기 {max_rounds}회 초과 — 수렴 실패, 코드 조사 필요(exit 1)")
            return 1
        printer(f"[ci-watch] 재실행/배포 대기 발동 → 재폴링(round {rounds})")
        sleep_fn(POLL_INTERVAL_SEC)


# ---------------------------------------------------------------------------
# --quick: 단발 상태 조회(폴링 없음 — 논블로킹 루프용)
# ---------------------------------------------------------------------------
def _default_rerun_state_path() -> str:
    """--quick 재실행 상태 파일의 기본 경로(저장소 docs/harness/runtime 하위)."""
    return str(Path(__file__).resolve().parents[2] / RERUN_STATE_FILE)


def _load_rerun_state(path: str, sha_short: str) -> set:
    """상태 파일에서 sha_short 에 해당하는 '재실행 완료' run_id 집합을 읽는다.

    파일이 없거나 다른 SHA(직전 커밋)면 빈 집합을 반환한다(신규 커밋마다 초기화).
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            state = json.load(handle)
        if str(state.get("sha", "")) != sha_short:
            return set()
        return {int(x) for x in state.get("rerun_ids", []) if isinstance(x, (int, str)) and str(x).lstrip("-").isdigit()}
    except (OSError, ValueError, TypeError, AttributeError):
        return set()  # 파일 없음/손상 → 초기화(중복 재실행 방지 상태만 잃음, 치명적 아님)


def _save_rerun_state(
    path: str, sha_short: str, rerun_ids: set, printer: Callable[[str], None] = print
) -> None:
    """재실행 완료 run_id 집합을 상태 파일에 저장한다(실패는 경고만 — 치명적 아님)."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"sha": sha_short, "rerun_ids": sorted(rerun_ids)}, handle)
    except OSError as exc:
        printer(f"[ci-watch:quick] 재실행 상태 저장 실패(무시): {exc}")


def _elapsed_seconds(runs: list[dict]) -> int:
    """run 목록의 가장 이른 createdAt 이후 경과 초를 반환한다(파싱 실패 시 0)."""
    stamps: list[datetime.datetime] = []
    for run in runs:
        raw = run.get("createdAt")
        if not raw:
            continue
        try:
            stamps.append(datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00")))
        except ValueError:
            continue
    if not stamps:
        return 0
    now = datetime.datetime.now(datetime.timezone.utc)
    return max(0, int((now - min(stamps)).total_seconds()))


def watch_quick(
    sha: str,
    branch: str,
    healthz: str,
    *,
    printer: Callable[[str], None] = print,
    state_path: str | None = None,
) -> int:
    """폴링 없이 현재 CI 상태를 1회 조회하고 즉시 종료한다(논블로킹 루프용).

    반환: 0=전부 green / 1=코드 실패 / 4=진행 중(자동 재실행 트리거 포함).
    perf-gate 자동 재실행은 여기서도 발동하되, 상태 파일로 중복 재실행을 막는다
    (이미 재실행한 run 이 또 실패로 보이면 handle_perf_gate 가 code_fail 로 승격 → exit 1).
    """
    sha_short = sha[:8]
    printer(f"[ci-watch:quick] target={sha_short} branch={branch}")
    runs = list_runs(branch, sha_short)
    if not runs:
        printer("[ci-watch:quick] 대상 커밋의 워크플로 없음/미등록 — green 취급")
        return 0
    if not all_completed(runs):
        pending = [r for r in runs if r.get("status") != "completed"]
        names = ", ".join(sorted({str(r.get("workflowName", "?")) for r in pending})) or "(이름 미상)"
        printer(f"[ci-watch:quick] 진행 중: {names} (경과 {_elapsed_seconds(runs)}s)")
        return 4
    fails = failures(runs)
    if not fails:
        printer("[ci-watch:quick] ALL GREEN ✓")
        return 0
    printer(f"[ci-watch:quick] {len(fails)} failed workflow(s):")
    resolved_state_path = state_path or _default_rerun_state_path()
    already_rerun = _load_rerun_state(resolved_state_path, sha_short)
    code = handle_failures(fails, sha_short, healthz, already_rerun, printer)
    _save_rerun_state(resolved_state_path, sha_short, already_rerun, printer)
    if code == 2:
        printer("[ci-watch:quick] 자동 재실행/배포 대기 발동 — 진행 중 취급(다음 확인에서 결과 반영)")
        return 4
    return code


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _force_utf8_streams() -> None:
    """Windows 콘솔(cp949)에서 한글·✓·▶ 출력 시 UnicodeEncodeError 를 막는다."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """CLI 인자를 파싱한다(위치 인자 SHA/BRANCH + --until-final 토글)."""
    parser = argparse.ArgumentParser(
        prog="ci_watch.py",
        description="push 후 GitHub Actions CI 완료를 감시하고 실패를 분류·자동 복구한다.",
    )
    parser.add_argument("sha", nargs="?", default=None, help="대상 커밋 SHA (기본: 현재 HEAD)")
    parser.add_argument("branch", nargs="?", default=DEFAULT_BRANCH, help="브랜치 (기본: deploy)")
    parser.add_argument(
        "--until-final",
        dest="until_final",
        action="store_true",
        default=True,
        help="exit 2(재실행/대기)를 자체 재폴링해 최종 0/1 로 수렴 (기본 활성)",
    )
    parser.add_argument(
        "--no-until-final",
        dest="until_final",
        action="store_false",
        help="1회전만 수행하고 exit 0/1/2 를 그대로 반환",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="폴링 없이 현재 상태만 1회 조회하고 즉시 종료 (exit 0/1/3/4, 논블로킹 루프용)",
    )
    parser.add_argument("--healthz", default=DEFAULT_HEALTHZ, help="배포 확인용 healthz URL")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """진입점. gh 준비 확인(불가 시 exit 3) → SHA 결정 → 감시 → 종료 코드 반환."""
    _force_utf8_streams()
    args = _parse_args(argv)

    ready, reason = gh_ready()
    if not ready:
        print(f"[ci-watch] 게이트 불가: {reason}")
        return 3

    if args.sha:
        sha = resolve_ref(args.sha)
        if not sha:
            print(f"[ci-watch] 게이트 불가: ref 해석 실패: {args.sha}(유효한 git ref 아님)")
            return 3
    else:
        sha = current_head_sha()
        if not sha:
            print("[ci-watch] 게이트 불가: HEAD SHA 확인 실패(git 저장소가 아닌 듯)")
            return 3

    if args.quick:
        return watch_quick(sha, args.branch, args.healthz)
    return watch(sha, args.branch, args.healthz, until_final=args.until_final)


if __name__ == "__main__":
    sys.exit(main())
