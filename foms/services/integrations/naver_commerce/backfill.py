"""과거 주문 소급 수집(백필) — 워터마크보다 이전 구간을 1회 훑는다 (NAVER-INGEST-BACKFILL).

왜 필요한가: 수집 워터마크는 **앞으로만** 간다(:mod:`~foms.services.integrations.naver_commerce.watermark`).
첫 실행(2026-08-25 00:44)보다 이전에 들어온 네이버 주문은 FOMS 에 원본
(``ExternalOrderLink``)이 아예 없고, 원본이 없으면 붙이기 후보에도 일괄 발송 대상에도
"안 붙은 수집분" 띠에도 **나타날 수 없다**. 붙이기로는 해결되지 않는 구멍이라 과거를
한 번 긁어와야 한다.

설계 규칙 넷:

1. **워터마크를 뒤로 돌리지 않는다.** 되돌리면 정상 스윕이 같은 구간을 다시 훑고
   "성공한 구간 끝까지만 전진" 규율이 깨진다. 백필은 별도 상태 키(:data:`SETTING_KEY`)에만
   기록하고 워터마크는 제자리다.
2. **수집 경로는 정상 스윕과 같다**
   (:func:`~foms.services.integrations.naver_commerce.ingest.sync_naver_orders`).
   집(``group_key``) 묶기·매핑·멱등(사전 조회 + ``UNIQUE (channel, external_id)``)이 한
   코드로 유지된다 — 백필만 다른 길로 만들면 묶음이 어긋난다.
3. **알림은 끈다.** 과거 취소·반품 상태는 반영하되 알림을 만들지 않는다(지난 건으로 대량
   발송하면 진짜 알림이 소음에 덮인다). 사용자 결정 2026-09-01.
4. **창마다 커밋한다.** 중간에 끊겨도 진척(``done_through``)이 남아 이어서 돌릴 수 있다.
5. **상태로 거르지 않는다**(``collect_all=True``). 변경 피드의 ``productOrderStatus`` 는
   이벤트 당시가 아니라 현재 상태다 — 스테이징 실측(2026-09-01) 06-04~08-16 구간은 변경
   이벤트 1,300건에 PAYED 가 **0건**이었다(정상 스윕 필터로는 과거를 한 건도 못 긁는다).
   판정은 상세 조회 결과(정본)에 맡긴다.
6. **처리 큐에 밀어 넣지 않는다**(``mark_reviewed=True``). 백필은 과거 원본을 확보하는
   일이지 지금 처리할 일이 아니다. 표시하지 않으면 90일치가 통째로 처리 탭에 쌓인다
   (스테이징 실측 2026-09-01: 링크 1,560건 = **798집**). 붙이기는 오늘 실측 매칭 띠와
   후보 검색이 맡는다.

**WORKER 프로세스 전용**이다 — 네이버 HTTP 는 등록된 IP 가 WORKER 것뿐이다. web 은 enqueue 만 한다.

조회 규격 근거(2026-09-01, ``apicenter.commerce.naver.com/llms/``): 변경분 조회는
``lastChangedFrom`` 필수·``lastChangedTo`` 생략 시 +24시간, 응답 상한 300건이고 초과분은
``more`` 로 이어받는다(클라이언트가 처리). **과거 조회 상한은 문서에 없다** — 스테이징
실측값을 원장에 적는다.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from foms.services.integrations.naver_commerce.client import KST, MAX_WINDOW, iter_time_windows
from models import SystemSetting

logger = logging.getLogger(__name__)

#: 백필 진행 상태를 담는 ``SystemSetting`` 키. 워터마크(``naver_sync_watermark``)와 **다른**
#: 행이다 — 백필이 정상 수집의 전진 기록을 건드리면 안 된다.
SETTING_KEY = "naver_backfill_state"

#: 한 번의 백필이 훑을 수 있는 최대 길이(사용자 결정 2026-09-01: 90일).
#: 넘겨서 부르면 실행하지 않고 거절한다 — 조용히 잘라 주면 "다 긁었다"로 읽힌다.
MAX_RANGE = timedelta(days=90)

#: 네이버 호출 사이에 두는 간격(초). 자사 스토어 앱은 전 API 2 RPS 고정이고 초과분은
#: 429 로 **처리되지 않고** 실패한다. 초당 2회의 절반인 0.5초를 둔다.
CALL_INTERVAL_SECONDS = 0.5


@dataclass
class BackfillResult:
    """백필 1회 실행 집계(운영 로그·화면 표시용)."""

    windows: int = 0            # 훑은 시간창 수
    changed: int = 0            # 변경분 이벤트 총건수
    candidates: int = 0         # 그중 결제완료(PAYED) 후보
    fetched: int = 0            # 상세를 실제로 받아온 건수
    collected: int = 0          # 새로 보관한 링크 수
    skipped: int = 0            # 이미 있던 건(멱등 skip)
    pending_review: int = 0     # 매핑 실패로 보류한 건
    claims_refreshed: int = 0   # 과거 클레임을 반영한 건
    claims_flagged: int = 0     # 그중 취소·반품 상태인 건
    errors: list[str] = field(default_factory=list)
    done_through: Optional[str] = None  # 성공적으로 끝낸 마지막 창의 끝(ISO)

    def as_dict(self) -> dict[str, Any]:
        """JSON 출력용 dict."""
        return {
            "windows": self.windows,
            "changed": self.changed,
            "candidates": self.candidates,
            "fetched": self.fetched,
            "collected": self.collected,
            "skipped": self.skipped,
            "pending_review": self.pending_review,
            "claims_refreshed": self.claims_refreshed,
            "claims_flagged": self.claims_flagged,
            "errors": list(self.errors),
            "done_through": self.done_through,
        }


class BackfillRangeError(ValueError):
    """요청 구간이 규칙에 맞지 않는다(빈 구간·미래·상한 초과)."""


def read_window_start(session: Session) -> str:
    """마지막 소급 수집이 **어디서부터** 훑었는지(``ISO`` 문자열, 없으면 빈 문자열).

    이 접근자가 따로 있는 이유: 발송 선별 모듈(``bulk_dispatch``)은 화면 필터 상속 금지
    계약 때문에 소스에 ``request`` 라는 글자를 담을 수 없다(계약 테스트가 소스를 훑는다).
    키 문자열은 상태를 소유한 이 모듈에 둔다.

    Args:
        session: DB 세션.

    Returns:
        구간 시작 ISO 문자열 또는 빈 문자열.
    """
    return str((read_state(session) or {}).get("requested_from") or "")


def read_state(session: Session) -> dict[str, Any]:
    """저장된 백필 상태를 준다(없으면 빈 dict).

    Args:
        session: DB 세션.

    Returns:
        상태 dict.
    """
    row = session.get(SystemSetting, SETTING_KEY)
    value = row.setting_value if row is not None else None
    return dict(value) if isinstance(value, dict) else {}


def _write_state(session: Session, state: dict[str, Any]) -> None:
    """백필 상태 행을 만들거나 갱신한다(커밋은 호출자)."""
    row = session.get(SystemSetting, SETTING_KEY)
    if row is None:
        session.add(SystemSetting(
            setting_key=SETTING_KEY, setting_value=state,
            description="네이버 과거 주문 소급 수집(백필) 상태 (NAVER-INGEST-BACKFILL)",
        ))
    else:
        row.setting_value = state
        row.version = int(row.version or 1) + 1
    session.flush()


def _aware(value: datetime) -> datetime:
    """naive 면 KST 로 간주해 aware 로 만든다."""
    return value if value.tzinfo else value.replace(tzinfo=KST)


def validate_range(start: datetime, end: datetime, *, now: datetime) -> tuple[datetime, datetime]:
    """요청 구간을 검사해 ``(시작, 끝)`` 을 돌려준다.

    Args:
        start: 구간 시작.
        end: 구간 끝.
        now: 현재 시각(미래 판정 기준).

    Returns:
        KST aware 로 맞춘 ``(start, end)``.

    Raises:
        BackfillRangeError: 빈 구간·역순·미래 끝·상한(:data:`MAX_RANGE`) 초과.
    """
    begin, finish, current = _aware(start), _aware(end), _aware(now)
    if begin >= finish:
        raise BackfillRangeError("시작이 끝보다 뒤입니다. 날짜를 다시 확인해 주세요.")
    if finish > current:
        raise BackfillRangeError("끝이 미래입니다. 아직 오지 않은 구간은 긁을 수 없습니다.")
    if finish - begin > MAX_RANGE:
        raise BackfillRangeError(
            f"한 번에 훑을 수 있는 최대 기간은 {MAX_RANGE.days}일입니다. "
            "구간을 나눠 실행해 주세요."
        )
    return begin, finish


def run_backfill(
    session: Session, *, start: datetime, end: datetime, client: Any = None,
    dry_run: bool = False, now: Optional[datetime] = None,
    sleep: Callable[[float], Any] = time.sleep,
) -> dict[str, Any]:
    """``[start, end]`` 를 하루 단위 창으로 나눠 소급 수집한다(커밋은 이 함수가 한다).

    창 하나가 끝날 때마다 커밋하고 진행 상태를 남긴다 — 중간에 죽어도 이미 받은 원본은
    남는다. **워터마크는 건드리지 않는다.** 중복은 정상 수집과 같은 두 겹이 막는다.

    Args:
        session: DB 세션.
        start: 구간 시작(보통 90일 전).
        end: 구간 끝.
        client: 미지정이면 환경변수로 만든다(WORKER 전용).
        dry_run: True 면 조회까지만 하고 아무것도 만들지 않는다.
        now: 테스트용 시각 주입(KST aware).
        sleep: 호출 간격 대기 함수(테스트 주입용).

    Returns:
        구간·집계 dict.

    Raises:
        BackfillRangeError: 구간 규칙 위반(네이버 호출 0회).
    """
    from foms.services.integrations.naver_commerce.client import NaverCommerceClient
    from foms.services.integrations.naver_commerce.ingest import sync_naver_orders

    current = _aware(now or datetime.now(KST))
    begin, finish = validate_range(start, end, now=current)
    api = client if client is not None else NaverCommerceClient()

    result = BackfillResult()
    payload: dict[str, Any] = {
        "window": {"from": begin.isoformat(), "to": finish.isoformat()},
        "dry_run": bool(dry_run),
    }
    _mark_running(session, begin=begin, finish=finish, now=current, dry_run=dry_run)
    session.commit()

    for index, (window_start, window_end) in enumerate(
        iter_time_windows(begin, finish, MAX_WINDOW), start=1
    ):
        if index > 1:
            # 창 사이에도 간격을 둔다 — 2 RPS 방벽은 워커 동시성 1 하나뿐이다.
            sleep(CALL_INTERVAL_SECONDS)
        try:
            window_result = sync_naver_orders(
                session, client=api, start=window_start, end=window_end,
                dry_run=dry_run, now=current, notify_claims=False,
                collect_all=True, mark_reviewed=True,
            )
        except Exception as exc:  # noqa: BLE001 - 한 창의 실패가 앞 창의 성과를 지우지 않게
            session.rollback()
            result.errors.append(f"{window_start.isoformat()}~{window_end.isoformat()}: {exc}")
            logger.error("[NAVER][백필] 창 실패 %s ~ %s: %s",
                         window_start.isoformat(), window_end.isoformat(), exc, exc_info=True)
            _record(session, result, begin=begin, finish=finish, now=current,
                    dry_run=dry_run, finished=True, failed=str(exc))
            session.commit()
            payload.update(result.as_dict())
            payload["failed"] = str(exc)
            return payload

        result.windows += 1
        result.changed += window_result.changed
        result.candidates += window_result.candidates
        result.fetched += window_result.fetched
        result.collected += window_result.collected
        result.skipped += window_result.skipped
        result.pending_review += window_result.pending_review
        result.claims_refreshed += window_result.claims_refreshed
        result.claims_flagged += window_result.claims_flagged
        result.errors.extend(window_result.errors)
        result.done_through = window_end.isoformat()
        _record(session, result, begin=begin, finish=finish, now=current,
                dry_run=dry_run, finished=False)
        session.commit()
        logger.info("[NAVER][백필] 창 %d 완료 %s ~ %s — 신규 %d건(누적 %d)",
                    index, window_start.isoformat(), window_end.isoformat(),
                    window_result.collected, result.collected)

    _record(session, result, begin=begin, finish=finish, now=current,
            dry_run=dry_run, finished=True)
    session.commit()
    payload.update(result.as_dict())
    return payload


def _mark_running(session: Session, *, begin: datetime, finish: datetime,
                  now: datetime, dry_run: bool) -> None:
    """시작했다는 사실을 먼저 남긴다 — 화면이 "넣었는데 아무 일도 없다"를 안 겪게."""
    state = read_state(session)
    state.update({
        "running": True,
        "started_at": now.isoformat(),
        "requested_from": begin.isoformat(),
        "requested_to": finish.isoformat(),
        "dry_run": bool(dry_run),
        "done_through": None,
        "last_error": None,
        "last_summary": None,
    })
    state["rev"] = int(state.get("rev") or 0) + 1
    _write_state(session, state)


def _record(session: Session, result: BackfillResult, *, begin: datetime, finish: datetime,
            now: datetime, dry_run: bool, finished: bool, failed: Optional[str] = None) -> None:
    """진행/종료 상태를 기록한다(창마다 1회 — 진척을 잃지 않는다)."""
    state = read_state(session)
    state.update({
        "running": not finished,
        "requested_from": begin.isoformat(),
        "requested_to": finish.isoformat(),
        "dry_run": bool(dry_run),
        "done_through": result.done_through,
        "last_summary": result.as_dict(),
        "updated_at": now.isoformat(),
    })
    if finished:
        state["finished_at"] = now.isoformat()
    if failed is not None:
        state["last_error"] = str(failed)[:2000]
    state["rev"] = int(state.get("rev") or 0) + 1
    _write_state(session, state)


__all__ = [
    "CALL_INTERVAL_SECONDS",
    "MAX_RANGE",
    "SETTING_KEY",
    "BackfillRangeError",
    "BackfillResult",
    "read_window_start",
    "read_state",
    "run_backfill",
    "validate_range",
]
