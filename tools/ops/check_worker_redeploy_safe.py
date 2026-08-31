"""운영 worker 를 지금 재배포해도 되는지 묻는다 — 읽기 전용 (NVREPAY-05 후속).

**왜 필요한가**: 운영 worker 는 1대다(네이버 커머스API 호출 IP 계약상 단일 서비스). 재배포하면
rq worker 가 내려갔다 올라오는 동안 큐가 **전면 정지**한다. 작업은 유실되지 않지만 그 사이 사용자
화면의 진행 폴링은 마감(300초)에 걸려 접힌다.

2026-08-31 실사례: 자동 조회 주기 변경으로 운영 worker 를 재배포했더니, 01:34 에 실사용자가 넣은
`전체 다시 읽기` 47집이 첫 스탬프 +852초(약 14분)까지 밀렸다. 그때는 "돌고 있는지" 를 물어볼 자리가
사람 기억밖에 없었다 — 이 스크립트가 그 자리다.

판정을 두 벌로 만들지 않는다: 전체 다시 읽기 진행 여부는 화면이 쓰는 것과 **같은 함수**
(:func:`claim_watch.running_refresh_all`)로 묻고, 큐 적체는 rq 에게 직접 묻는다.

사용:
    # 운영 (railway 링크 디렉토리에서 URL 을 뽑아 넘긴다)
    DATABASE_URL=$(railway variables --service Postgres --kv | grep ^DATABASE_PUBLIC_URL= | cut -d= -f2-) \\
    REDIS_URL=$(railway variables --service Redis --kv | grep ^REDIS_PUBLIC_URL= | cut -d= -f2-) \\
    python tools/ops/check_worker_redeploy_safe.py

종료 코드:
    0 = 지금 재배포해도 안전(진행 중인 요청 없음, 큐 비어 있음)
    1 = **재배포하지 마라** — 진행 중인 요청이나 대기 작업이 있다
    2 = 판정 불가(URL 미지정·조회 실패). 모르면 재배포하지 않는 쪽으로 기운다
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Optional

# 저장소 루트를 import 경로에 넣는다 — `python tools/ops/...` 로 직접 부르면 tools/ops 만 들어간다.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def queue_pressure(redis_url: str, *, queue_name: str = "default") -> dict[str, int]:
    """큐에 남아 있는 일을 센다(대기 + 실행 중).

    Args:
        redis_url: rq 가 쓰는 Redis URL.
        queue_name: 큐 이름(운영은 ``default`` 하나다).

    Returns:
        ``{"queued": 대기 작업 수, "started": 실행 중 작업 수}``.

    Raises:
        Exception: 접속·조회 실패는 그대로 올린다 — 삼키면 "비었다"로 읽힌다.
    """
    from redis import Redis
    from rq import Queue

    connection = Redis.from_url(redis_url)
    queue = Queue(queue_name, connection=connection)
    return {"queued": int(queue.count),
            "started": int(len(queue.started_job_registry.get_job_ids()))}


def verdict(running: Optional[dict[str, Any]], pressure: dict[str, int]) -> tuple[int, list[str]]:
    """두 사실을 사람이 읽는 판정 하나로 묶는다.

    Args:
        running: :func:`claim_watch.running_refresh_all` 결과(없으면 ``None``).
        pressure: :func:`queue_pressure` 결과.

    Returns:
        ``(종료 코드, 출력할 줄 목록)``. 하나라도 걸리면 1(재배포 금지)이다.
    """
    lines: list[str] = []
    blocked = False

    if running:
        actor = running.get("actor") or "다른 관리자"
        lines.append(f"[진행 중] 전체 다시 읽기 — {actor} 시작, "
                     f"{running['total']}주문 중 {running['done']}주문 완료 "
                     f"(경과 {running['elapsed_seconds']}초, 예상 {running['eta']})")
        blocked = True
    else:
        lines.append("[없음] 진행 중인 전체 다시 읽기 없음")

    waiting = pressure["queued"] + pressure["started"]
    if waiting:
        lines.append(f"[대기] 큐 작업 {pressure['queued']}건 대기 · {pressure['started']}건 실행 중")
        blocked = True
    else:
        lines.append("[없음] 큐가 비어 있음")

    if blocked:
        lines.append("→ 재배포하지 마라. 끝난 뒤에 다시 물어라(워커 1대라 재시작 = 큐 전면 정지).")
        return 1, lines
    lines.append("→ 지금 재배포해도 된다.")
    return 0, lines


def main(argv: Optional[list[str]] = None) -> int:
    """진입점.

    Args:
        argv: 인자 목록(테스트 주입). 생략하면 ``sys.argv``.

    Returns:
        종료 코드(0 안전 · 1 진행 중 · 2 판정 불가).
    """
    parser = argparse.ArgumentParser(description="운영 worker 재배포 안전 여부(읽기 전용)")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL")
                        or os.environ.get("DATABASE_PUBLIC_URL"))
    parser.add_argument("--redis-url", default=os.environ.get("REDIS_URL")
                        or os.environ.get("REDIS_PUBLIC_URL"))
    args = parser.parse_args(argv)

    if not args.database_url or not args.redis_url:
        print("판정 불가: DATABASE_URL·REDIS_URL 이 모두 필요하다(모르면 재배포하지 않는다).",
              file=sys.stderr)
        return 2

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from foms.services.integrations.naver_commerce.claim_watch import running_refresh_all

    try:
        engine = create_engine(args.database_url)
        session = sessionmaker(bind=engine)()
        try:
            running = running_refresh_all(session)
        finally:
            session.close()
            engine.dispose()
        pressure = queue_pressure(args.redis_url)
    except Exception as exc:  # 조회 실패는 '안전'이 아니다 — 모르면 멈춘다
        print(f"판정 불가: 조회 실패 — {exc}", file=sys.stderr)
        return 2

    code, lines = verdict(running, pressure)
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
