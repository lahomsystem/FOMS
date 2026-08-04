"""RQ 실패 잡 조회·선택적 재큐잉 CLI (RQ-FAILED-01, fail-open).

RQ 는 실패한 job 을 ``FailedJobRegistry`` 에 기본 1년 보관하며 **자동 재시도하지 않는다.**
이 저장소에는 그 registry 를 들여다보는 경로가 없어 썸네일 미생성·좌표 미부여·채널톡
인바운드 보류·푸시 미발송이 조용히 쌓인다. 이 CLI 가 그 관측 경로다.

    python tools/ops/rq_failed_jobs.py                       # 요약(읽기 전용)
    python tools/ops/rq_failed_jobs.py --json                # 기계 판독용
    python tools/ops/rq_failed_jobs.py --requeue geocode_order_address          # dry-run
    python tools/ops/rq_failed_jobs.py --requeue geocode_order_address --apply  # 실제 재큐잉

``--requeue`` 는 **기본 dry-run** 이고 실제 재큐잉은 ``--apply`` 가 있어야 한다.
전량 재큐잉은 RQ 기본 CLI 로 충분하므로 여기서 다시 만들지 않는다::

    rq requeue --all --queue default --url "$REDIS_URL"

다만 ``rq requeue --all`` 은 dry-run 도 필터도 없어 최대 1년치 stale job(예: 한참 지난
푸시 발송)을 한 번에 재생한다. 그래서 **이름 필터 + dry-run** 만 이 CLI 에 얹었다.

읽기 전용 기본 동작이며 approval token 을 요구하지 않는다. Flask app 을 import 하지 않는다.

exit code:
    0  실패 잡 없음(또는 ``--apply`` 후 잔여 0건)
    1  실패 잡 존재 — 조치 필요
    2  Redis 도달 실패(``REDIS_URL`` 은 있으나 연결/ping 불가)
    3  ``REDIS_URL`` 미설정 — RQ 비활성 환경(트레이스백 없이 종료)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from redis.exceptions import RedisError  # noqa: E402

EXIT_CLEAN = 0
EXIT_FAILURES = 1
EXIT_UNREACHABLE = 2
EXIT_DISABLED = 3

_QUEUE_NAME = "default"
_DEFAULT_LIMIT = 200
_ERROR_MAX_LEN = 300


def _utf8_stdio() -> None:
    """Windows cp949 콘솔에서 한글/기호 출력이 UnicodeEncodeError 로 죽는 것을 막는다.

    Redis 예외 메시지는 OS 로케일 문자열이라 콘솔 코드페이지 밖 문자가 섞일 수 있다.
    이 CLI 는 '깨끗한 메시지 + exit code' 가 계약이므로 출력 인코딩으로 절대 죽으면 안 된다.
    (``tools/harness/session_worktree.py`` 와 동일 패턴)
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def _last_error_line(exc_info: Optional[str]) -> Optional[str]:
    """트레이스백 문자열에서 마지막 의미 있는 줄(예외 요약)만 잘라 반환한다.

    Args:
        exc_info: RQ job 의 ``exc_info`` 트레이스백 문자열(없을 수 있다).

    Returns:
        예외 요약 한 줄(최대 ``_ERROR_MAX_LEN`` 자). 정보가 없으면 ``None``.
    """
    if not exc_info:
        return None
    lines = [ln.strip() for ln in str(exc_info).strip().splitlines() if ln.strip()]
    if not lines:
        return None
    return lines[-1][:_ERROR_MAX_LEN]


def _stamp(value: Any) -> Optional[str]:
    """datetime 을 ISO 문자열로 정규화한다(없거나 datetime 이 아니면 ``None``)."""
    return value.isoformat() if hasattr(value, "isoformat") else None


def summarize_failed_jobs(jobs: Sequence[Any]) -> list[dict]:
    """실패 job 들을 함수 이름별로 집계한다.

    Args:
        jobs: ``func_name``/``ended_at``/``exc_info``/``id`` 를 가진 RQ Job 들.
              registry 만료로 사라진 항목(``None``)은 건너뛴다.

    Returns:
        ``{"job_name", "count", "last_failed_at", "sample_job_id", "sample_error"}``
        dict 리스트. 실패 수 내림차순, 동수면 이름 오름차순. 대표 에러는 **가장 최근**
        실패 건에서 뽑는다.
    """
    grouped: dict[str, dict] = {}
    for job in jobs:
        if job is None:
            continue
        name = getattr(job, "func_name", None) or "<unknown>"
        entry = grouped.setdefault(name, {
            "job_name": name, "count": 0, "last_failed_at": None,
            "sample_job_id": None, "sample_error": None,
        })
        entry["count"] += 1
        stamp = _stamp(getattr(job, "ended_at", None))
        newest = entry["last_failed_at"] is None or (stamp is not None and stamp > entry["last_failed_at"])
        if newest or entry["sample_job_id"] is None:
            entry["last_failed_at"] = stamp or entry["last_failed_at"]
            entry["sample_job_id"] = getattr(job, "id", None)
            entry["sample_error"] = _last_error_line(getattr(job, "exc_info", None))
    return sorted(grouped.values(), key=lambda e: (-e["count"], e["job_name"]))


def select_requeue_targets(jobs: Sequence[Any], job_name: str) -> list:
    """재큐잉 대상 job 을 이름으로 고른다.

    Args:
        jobs: 실패 job 리스트.
        job_name: 짧은 함수명(``geocode_order_address``) 또는 전체 경로. ``all`` 이면 전부.

    Returns:
        선택된 job 리스트(입력 순서 유지).
    """
    if job_name == "all":
        return [j for j in jobs if j is not None]
    suffix = "." + job_name
    selected = []
    for job in jobs:
        if job is None:
            continue
        func_name = getattr(job, "func_name", "") or ""
        if func_name == job_name or func_name.endswith(suffix):
            selected.append(job)
    return selected


def open_failed_registry(redis_url: str) -> Any:
    """``default`` 큐의 ``FailedJobRegistry`` 를 열고 ping 으로 도달성을 확인한다.

    Args:
        redis_url: Redis 접속 URL(env ``REDIS_URL``).

    Returns:
        연결이 검증된 ``FailedJobRegistry``.

    Raises:
        RedisError / OSError / ValueError: URL 불량 또는 Redis 도달 실패 시.
    """
    from redis import Redis
    from rq import Queue
    from rq.registry import FailedJobRegistry

    conn = Redis.from_url(redis_url, socket_connect_timeout=5, socket_timeout=5)
    conn.ping()
    return FailedJobRegistry(queue=Queue(_QUEUE_NAME, connection=conn))


def fetch_failed_jobs(registry: Any, limit: int) -> tuple[list, int]:
    """registry 에서 **가장 최근** 실패 job 을 최대 ``limit`` 개 가져온다.

    Args:
        registry: RQ ``FailedJobRegistry``.
        limit: 조회 상한(0 이하면 전체).

    Returns:
        ``(job 리스트, registry 전체 실패 수)``. 만료된 항목은 제외된다.
    """
    total = int(registry.count)
    job_ids = list(registry.get_job_ids())
    if limit > 0:
        job_ids = job_ids[-limit:]
    jobs = registry.job_class.fetch_many(
        job_ids, connection=registry.connection, serializer=registry.serializer
    )
    return [j for j in jobs if j is not None], total


def _print_report(summary: list[dict], total: int, sampled: int, as_json: bool) -> None:
    """요약을 사람/기계 판독용으로 출력한다(반환값 없음)."""
    if as_json:
        print(json.dumps(
            {"queue": _QUEUE_NAME, "failed_count": total, "sampled": sampled, "jobs": summary},
            ensure_ascii=False,
        ), flush=True)
        return
    print(f"[rq-failed] queue={_QUEUE_NAME} 실패 잡 {total}건 (조회 {sampled}건)")
    for row in summary:
        print(f"  - {row['job_name']}  count={row['count']}  "
              f"last={row['last_failed_at']}  job={row['sample_job_id']}")
        if row["sample_error"]:
            print(f"      {row['sample_error']}")


def _run_requeue(registry: Any, jobs: Sequence[Any], job_name: str, apply: bool) -> int:
    """선택된 실패 job 을 재큐잉한다(``apply`` 가 False 면 dry-run).

    Args:
        registry: RQ ``FailedJobRegistry``.
        jobs: 조회된 실패 job 리스트.
        job_name: 대상 함수명 또는 ``all``.
        apply: True 여야 실제 재큐잉한다.

    Returns:
        실제 재큐잉된 건수(dry-run 이면 0).
    """
    targets = select_requeue_targets(jobs, job_name)
    if not apply:
        print(f"[rq-failed] dry-run: {job_name} 대상 {len(targets)}건. 실제 재큐잉은 --apply 필요")
        for job in targets[:20]:
            print(f"  - {job.id}  {job.func_name}")
        return 0
    for job in targets:
        registry.requeue(job.id)
    print(f"[rq-failed] 재큐잉 완료: {job_name} {len(targets)}건")
    return len(targets)


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """CLI 인자를 파싱한다."""
    p = argparse.ArgumentParser(description="RQ 실패 잡 조회·선택적 재큐잉 (기본 읽기 전용).")
    p.add_argument("--limit", type=int, default=_DEFAULT_LIMIT,
                   help=f"조회할 최근 실패 잡 상한(0=전체, 기본 {_DEFAULT_LIMIT}).")
    p.add_argument("--json", action="store_true", help="기계 판독용 JSON 리포트 출력.")
    p.add_argument("--requeue", metavar="JOB_NAME",
                   help="재큐잉 대상 함수명(예: geocode_order_address) 또는 all. 기본 dry-run.")
    p.add_argument("--apply", action="store_true",
                   help="--requeue 를 실제로 실행(없으면 dry-run).")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    """CLI 진입점. exit code 는 모듈 docstring 참조."""
    _utf8_stdio()
    args = _parse_args(argv)
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not redis_url:
        print("[rq-failed] REDIS_URL 미설정: RQ 비활성 환경입니다. 실패 잡 조회를 건너뜁니다.")
        return EXIT_DISABLED
    try:
        registry = open_failed_registry(redis_url)
        jobs, total = fetch_failed_jobs(registry, args.limit)
    except (RedisError, OSError, ValueError) as exc:
        print(f"[rq-failed] Redis 도달 실패: {type(exc).__name__}: {exc}")
        return EXIT_UNREACHABLE

    requeued = 0
    if args.requeue:
        requeued = _run_requeue(registry, jobs, args.requeue, args.apply)
    else:
        _print_report(summarize_failed_jobs(jobs), total, len(jobs), args.json)
    return EXIT_FAILURES if (total - requeued) > 0 else EXIT_CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
