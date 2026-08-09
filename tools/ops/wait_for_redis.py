"""Redis 준비 대기 유틸 — 워커 컨테이너 부팅 레이스 방지.

배경(2026-08-07 운영 사고):
    Railway 프라이빗 네트워크(redis.railway.internal)는 컨테이너 기동 직후 몇 초간
    라우팅되지 않을 수 있고, Redis 서비스 자체가 재시작 중일 수도 있다. 이때
    `rq worker`는 부팅 첫 명령(is_suspended)에서 redis TimeoutError로 즉사한다.
    Railway 재시작 정책이 ON_FAILURE(최대 10회)라 ~11초 간격의 즉사가 2분 만에
    재시도 예산을 소진하고 서비스가 CRASHED 상태로 고착됐다(13시간 무중단 정지).

해결:
    워커 기동 전 이 스크립트로 Redis PING 성공까지 대기한다. 대기 예산을 넘기면
    비정상 종료(exit 1)하여 Railway 재시작에 맡기되, 한 번의 재시작이 수 분을
    커버하므로 재시도 예산이 순식간에 마르지 않는다.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

import redis


def mask_url(url: str) -> str:
    """Redis URL 에서 비밀번호를 가린 문자열을 만든다.

    Args:
        url: 원본 Redis 접속 URL.

    Returns:
        비밀번호가 ``***`` 로 치환된 URL (파싱 실패 시 스킴만 노출).
    """
    try:
        parts = urlsplit(url)
        if parts.password:
            user = parts.username or ""
            netloc = f"{user}:***@{parts.hostname}"
            if parts.port:
                netloc = f"{netloc}:{parts.port}"
            parts = parts._replace(netloc=netloc)
        return urlunsplit(parts)
    except ValueError:
        return "<unparsable redis url>"


def wait_for_redis(
    url: str,
    timeout_seconds: float,
    interval_seconds: float = 3.0,
    connect_timeout_seconds: float = 5.0,
) -> bool:
    """Redis 가 PING 에 응답할 때까지 대기한다.

    Args:
        url: Redis 접속 URL.
        timeout_seconds: 전체 대기 예산(초). 초과하면 False 반환.
        interval_seconds: 재시도 간격(초).
        connect_timeout_seconds: 시도 1회당 소켓 연결/응답 타임아웃(초).

    Returns:
        PING 성공 시 True, 예산 소진 시 False.
    """
    deadline = time.monotonic() + timeout_seconds
    attempt = 0
    last_error = "unknown"

    while True:
        attempt += 1
        client: Optional[redis.Redis] = None
        try:
            client = redis.Redis.from_url(
                url,
                socket_connect_timeout=connect_timeout_seconds,
                socket_timeout=connect_timeout_seconds,
            )
            client.ping()
            print(f"[wait-redis] ready after {attempt} attempt(s): {mask_url(url)}", flush=True)
            return True
        except (redis.exceptions.RedisError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        finally:
            if client is not None:
                try:
                    client.close()
                except (redis.exceptions.RedisError, OSError):
                    pass

        if time.monotonic() + interval_seconds >= deadline:
            print(
                f"[wait-redis] NOT ready after {attempt} attempt(s) "
                f"({timeout_seconds:.0f}s budget): {last_error}",
                file=sys.stderr,
                flush=True,
            )
            return False

        print(
            f"[wait-redis] attempt {attempt} failed ({last_error}); retry in {interval_seconds:.0f}s",
            flush=True,
        )
        time.sleep(interval_seconds)


def main() -> int:
    """CLI 진입점.

    Returns:
        종료 코드 (0=Redis 준비 완료, 1=대기 예산 초과 또는 URL 미지정).
    """
    parser = argparse.ArgumentParser(description="Redis 준비 상태를 기다린다.")
    parser.add_argument("--url", required=True, help="Redis 접속 URL")
    parser.add_argument("--timeout", type=float, default=300.0, help="전체 대기 예산(초)")
    parser.add_argument("--interval", type=float, default=3.0, help="재시도 간격(초)")
    parser.add_argument(
        "--connect-timeout", type=float, default=5.0, help="시도 1회당 연결 타임아웃(초)"
    )
    args = parser.parse_args()

    if not args.url:
        print("[wait-redis] REDIS_URL 이 비어 있다", file=sys.stderr, flush=True)
        return 1

    ok = wait_for_redis(
        args.url,
        timeout_seconds=args.timeout,
        interval_seconds=args.interval,
        connect_timeout_seconds=args.connect_timeout,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
