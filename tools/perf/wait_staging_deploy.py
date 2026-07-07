#!/usr/bin/env python3
"""배포 완료 대기 — ``/healthz`` 의 commit 이 대상 SHA 와 일치할 때까지 폴링.

perf-gate CI 는 새 커밋을 스테이징에 배포한 뒤, 게이트 측정을 시작하기 전에
"새 컨테이너가 실제로 트래픽을 받는지"를 이 스크립트로 확인한다. 확인 없이 바로
측정하면 아직 구버전 컨테이너를 재는 레이스가 생겨 게이트 판정이 무의미해진다.

판정: ``healthz`` JSON 의 ``commit``(= Railway ``RAILWAY_GIT_COMMIT_SHA``)이 ``--sha``
로 시작(short/full SHA 관용 매칭)하면 exit 0. 타임아웃까지 불일치면 exit 1. ``commit``
이 빈 값이면(env 미주입 or 구버전 배포 진행 중) 폴링을 계속한다.

의존: requests 만(앱/DB import 없음 — CI 설치 최소).
"""

from __future__ import annotations

import argparse
import sys
import time

import requests

DEFAULT_BASE = "https://lahom-dev.up.railway.app"
POLL_INTERVAL_S = 15


def _fetch_commit(base: str, timeout: float = 10.0) -> str | None:
    """``GET {base}/healthz`` → commit 문자열. 네트워크/파싱 오류·비200 은 None."""
    try:
        resp = requests.get(base.rstrip("/") + "/healthz", timeout=timeout)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except (requests.RequestException, ValueError):
        return None
    commit = data.get("commit") if isinstance(data, dict) else None
    return commit if isinstance(commit, str) else None


def matches(deployed: str, target: str) -> bool:
    """배포 commit 이 target SHA 로 시작하면 일치(short↔full SHA 관용)."""
    if not deployed or not target:
        return False
    d = deployed.strip().lower()
    t = target.strip().lower()
    return d.startswith(t) or t.startswith(d)


def wait_for_deploy(
    base: str, sha: str, timeout: int, interval: int = POLL_INTERVAL_S
) -> int:
    """배포 완료 폴링. 일치 시 0, 타임아웃 시 1 반환.

    Args:
        base: 스테이징 origin.
        sha: 대상 커밋 SHA(GITHUB_SHA).
        timeout: 최대 대기(초).
        interval: 폴링 간격(초).

    Returns:
        exit code (0=일치, 1=타임아웃).
    """
    deadline = time.monotonic() + timeout
    target = sha.strip()
    last_seen: str | None = ""  # 상태 변화 시에만 로그(폴링 스팸 방지). 초기값은 미측정.
    while True:
        deployed = _fetch_commit(base)
        if deployed and matches(deployed, target):
            print(f"[wait-deploy] 배포 확인: commit={deployed} == target={target}")
            return 0
        if deployed != last_seen:
            state = deployed or "(빈 commit — env 미주입/구버전 배포 중)"
            print(f"[wait-deploy] 대기: 현재 {state} != target {target}")
            last_seen = deployed
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print(
                f"[wait-deploy] 타임아웃({timeout}s): "
                f"마지막 commit={deployed or '(none)'} != target={target}",
                file=sys.stderr,
            )
            return 1
        time.sleep(min(interval, remaining))


def main() -> int:
    # Win 콘솔 cp949 에서 한글·em dash 출력 크래시 방지(staging_perf_gate 동일 관례).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        description="스테이징 배포 완료(healthz commit == SHA) 대기."
    )
    parser.add_argument("--base", default=DEFAULT_BASE, help="스테이징 origin")
    parser.add_argument("--sha", required=True, help="대상 커밋 SHA(GITHUB_SHA)")
    parser.add_argument("--timeout", type=int, default=600, help="최대 대기(초, 기본 600)")
    parser.add_argument(
        "--interval", type=int, default=POLL_INTERVAL_S, help="폴링 간격(초, 기본 15)"
    )
    args = parser.parse_args()
    return wait_for_deploy(args.base, args.sha, args.timeout, args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
