"""domain side-effect worker readiness checker (SIDEFX-WORKER-01, fail-closed).

``side_effect_worker_heartbeats`` 와 ``domain_side_effect_outbox`` 를 읽어 delivery/expiry/
retention worker 가 건강한지 **fail-closed**(nonzero)로 판정한다:

* 판정 대상 worker_kind heartbeat 존재·신선도(``--max-heartbeat-age``) — 기본은 outbox
  3종(DELIVERY/EXPIRY_SCAN/RETENTION), ``--kinds`` 로 다른 loop kind 를 고른다,
* expiry scan lag(``--max-expiry-scan-lag``)·retention scan lag(``--max-retention-scan-lag``),
* 처리 가능한 가장 오래된 PENDING 지연(``--max-oldest-pending-lag``),
* DEAD 행 수(``--max-dead``).

하나라도 위반/미관측이면 not-ready 다. Flask app 을 import 하지 않고 직접 엔진을 만든다.
read-only 이며 approval token 을 요구하지 않는다.

exit code: 0 ready, 1 not-ready(판정 실패), 2 오류(DB/엔진 조회 불가 — 역시 fail-closed).

배포 예(§8.2 registry command template)::

    python tools/ops/check_sidefx_readiness.py --max-heartbeat-age 30 \\
        --max-oldest-pending-lag 60 --max-expiry-scan-lag 360 \\
        --max-retention-scan-lag 90000 --max-dead 0

outbox 밖 loop(``NAVER_AUTO_DISPATCH``·``GEOCODE_SWEEP``)은 tick 이 달라 자기 예산
(:data:`foms.services.sidefx_worker.WORKER_KIND_SPECS`)으로 판정한다. PENDING lag·DEAD 는
outbox kind 를 하나라도 골랐을 때만 센다::

    python tools/ops/check_sidefx_readiness.py --kinds NAVER_AUTO_DISPATCH,GEOCODE_SWEEP
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from foms.services.sidefx_worker import (  # noqa: E402
    WORKER_KIND_SPECS,
    WORKER_KINDS,
    ReadinessThresholds,
    collect_readiness_observations,
    evaluate_readiness,
    make_engine_from_env,
)
from sqlalchemy.orm import sessionmaker  # noqa: E402

_LOGGER = logging.getLogger("check_sidefx_readiness")


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Domain side-effect worker readiness checker (fail-closed)."
    )
    p.add_argument("--max-heartbeat-age", type=int, default=30,
                   help="heartbeat 최대 신선도(초). 초과하거나 미존재면 not-ready.")
    p.add_argument("--max-oldest-pending-lag", type=int, default=60,
                   help="처리 가능한 가장 오래된 PENDING 최대 지연(초).")
    p.add_argument("--max-expiry-scan-lag", type=int, default=360,
                   help="마지막 expiry scan 이후 최대 경과(초).")
    p.add_argument("--max-retention-scan-lag", type=int, default=90000,
                   help="마지막 retention scan 이후 최대 경과(초).")
    p.add_argument("--max-dead", type=int, default=0,
                   help="허용 DEAD 행 수(초과면 not-ready).")
    p.add_argument("--kinds", default=None,
                   help="판정할 worker_kind 쉼표 목록(생략 시 outbox 3종 "
                        f"{','.join(WORKER_KINDS)}). 등록된 kind: "
                        f"{','.join(sorted(WORKER_KIND_SPECS))}.")
    p.add_argument("--json", action="store_true", help="기계 판독용 JSON 리포트 출력.")
    return p.parse_args(argv)


def _parse_kinds(raw: Optional[str]) -> Optional[list[str]]:
    """``--kinds`` 문자열을 kind 목록으로 푼다(빈 항목은 버린다).

    Args:
        raw: 쉼표로 이은 worker_kind 목록. ``None`` 이면 기본(outbox 3종)을 뜻한다.

    Returns:
        kind 목록, 또는 기본을 쓰라는 뜻의 ``None``.

    Raises:
        ValueError: 항목이 하나도 남지 않은 경우(빈 판정은 무조건 ready 라 fail-open 이다).
    """
    if raw is None:
        return None
    kinds = [k.strip() for k in raw.split(",") if k.strip()]
    if not kinds:
        raise ValueError("--kinds 에 판정할 worker_kind 가 하나도 없다")
    return kinds


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args(argv)
    try:
        kinds = _parse_kinds(args.kinds)
    except ValueError as exc:  # 잘못된 선택 = 판정 불가 = fail-closed
        _LOGGER.error("[sidefx-readiness] %s", exc)
        return 2
    thresholds = ReadinessThresholds(
        max_heartbeat_age=args.max_heartbeat_age,
        max_oldest_pending_lag=args.max_oldest_pending_lag,
        max_expiry_scan_lag=args.max_expiry_scan_lag,
        max_retention_scan_lag=args.max_retention_scan_lag,
        max_dead=args.max_dead,
    )
    try:
        engine = make_engine_from_env()
        try:
            session_local = sessionmaker(bind=engine)
            s = session_local()
            try:
                observations = collect_readiness_observations(s)
            finally:
                s.close()
        finally:
            engine.dispose()
    except Exception:  # DB/엔진 조회 불가 = fail-closed(readiness 를 green 으로 보지 않는다)
        _LOGGER.exception("[sidefx-readiness] observation failed (fail-closed)")
        return 2

    try:
        report = evaluate_readiness(observations, thresholds, kinds=kinds)
    except ValueError as exc:  # 등록부에 없는 kind = 판정 불가 = fail-closed
        _LOGGER.error("[sidefx-readiness] %s", exc)
        return 2
    payload = {"ready": report.ready, "failures": report.failures,
               "observations": report.observations}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False), flush=True)
    else:
        status = "READY" if report.ready else "NOT-READY"
        _LOGGER.info("[sidefx-readiness] %s failures=%d", status, len(report.failures))
        for f in report.failures:
            _LOGGER.info("  - %s", f)
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
