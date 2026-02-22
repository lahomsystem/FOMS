#!/usr/bin/env python3
"""
Phase C 7.3: 지도 API 동시 40명 부하 테스트
- 목표: 동시 40명 접속 시 응답 2초 이내, 오류 0%
- 실행: python scripts/load_test_map.py
- 환경변수: BASE_URL(기본 http://localhost:5000), LOAD_TEST_USER, LOAD_TEST_PASS
"""
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    print("requests 필요: pip install requests")
    sys.exit(1)

BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000").rstrip("/")
CONCURRENT = int(os.environ.get("LOAD_TEST_CONCURRENT", "40"))
TIMEOUT = 10


def _login(session: requests.Session) -> bool:
    user = os.environ.get("LOAD_TEST_USER", "admin")
    pwd = os.environ.get("LOAD_TEST_PASS", "admin")
    try:
        r = session.post(f"{BASE_URL}/login", data={"username": user, "password": pwd}, timeout=TIMEOUT, allow_redirects=True)
        return r.status_code in (200, 302)
    except Exception as e:
        print(f"[LOGIN] 실패: {e}")
        return False


def _hit_map_data(session: requests.Session) -> tuple[float, int, str | None]:
    start = time.perf_counter()
    err = None
    status = 0
    try:
        r = session.get(f"{BASE_URL}/api/map_data?limit=50", timeout=TIMEOUT)
        status = r.status_code
        if status != 200:
            err = f"HTTP {status}"
    except Exception as e:
        err = str(e)
    elapsed = time.perf_counter() - start
    return elapsed, status, err


def _hit_generate_map(session: requests.Session) -> tuple[float, int, str | None]:
    start = time.perf_counter()
    err = None
    status = 0
    try:
        r = session.get(f"{BASE_URL}/api/generate_map?limit=50", timeout=TIMEOUT)
        status = r.status_code
        if status != 200:
            err = f"HTTP {status}"
    except Exception as e:
        err = str(e)
    elapsed = time.perf_counter() - start
    return elapsed, status, err


def main():
    print(f"Phase C 7.3: 지도 API 부하 테스트")
    print(f"  BASE_URL={BASE_URL}, 동시 요청={CONCURRENT}")
    print()

    session = requests.Session()
    session.headers["User-Agent"] = "FOMS-LoadTest/1.0"
    if not _login(session):
        print("[FAIL] 로그인 실패. LOAD_TEST_USER, LOAD_TEST_PASS 확인.")
        sys.exit(1)
    print("[OK] 로그인 성공")

    endpoints = [
        ("/api/map_data", _hit_map_data),
        ("/api/generate_map", _hit_generate_map),
    ]

    for name, fn in endpoints:
        print(f"\n--- {name} 동시 {CONCURRENT} 요청 ---")
        results: list[tuple[float, int, str | None]] = []
        with ThreadPoolExecutor(max_workers=CONCURRENT) as ex:
            futures = [ex.submit(fn, session) for _ in range(CONCURRENT)]
            for f in as_completed(futures):
                try:
                    results.append(f.result())
                except Exception as e:
                    results.append((0.0, 0, str(e)))

        ok = sum(1 for _, st, e in results if st == 200 and e is None)
        fails = [(t, s, e) for t, s, e in results if s != 200 or e]
        times = [t for t, _, e in results if e is None and t > 0]

        print(f"  성공: {ok}/{CONCURRENT}")
        if fails:
            print(f"  실패: {len(fails)} 건")
            for t, s, e in fails[:5]:
                print(f"    - {t:.2f}s, status={s}, err={e}")
        if times:
            times.sort()
            p50 = times[len(times) // 2]
            p95 = times[int(len(times) * 0.95)] if len(times) > 20 else times[-1]
            print(f"  응답시간 p50={p50:.2f}s, p95={p95:.2f}s")
            if p95 > 2.0:
                print(f"  [WARN] p95 2초 초과 (목표: 2초 이내)")
        if ok < CONCURRENT or (times and times[-1] > 2.0):
            print(f"  [FAIL] 목표 미달")
        else:
            print(f"  [PASS] 동시 40명 부하 테스트 통과")

    print("\n완료.")


if __name__ == "__main__":
    main()
