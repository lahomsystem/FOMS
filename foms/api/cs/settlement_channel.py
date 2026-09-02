"""채널(네이버) 정산 탭 API — SETTLE-CHANNEL-01 §5.

* ``GET  /api/settlement/channel`` — 탭 한 화면 전체(동기화 상태·KPI·차트·원장).
* ``POST /api/settlement/channel/sync`` — "지금 동기화" enqueue(실행은 WORKER).

조회 커널은 :func:`foms.services.settlement_channel.build_channel_dashboard` 이고 이
모듈은 **파라미터 파싱·권한 판정·응답 포장**만 한다(``foms/api/cs/settlement.py`` 와 같은
역할 분담).

**권한(§1)**: 판정 SSOT 는 :func:`~foms.services.settlement_channel_access.
can_view_channel_settlement` 하나다 — 정책 엔진은 ``role == "MANAGER"`` 를 team 검사보다
먼저 통과시켜 "ADMIN + 회계팀만"을 표현할 수 없기 때문이다. 정책 id 등재
(``SETTLEMENT_CHANNEL_READ``/``SETTLEMENT_CHANNEL_SYNC``)는 route manifest 와
before_request pre-filter 용이고, GET 은 ``_WRITE_METHODS`` 밖이라 애초에 가드에 닿지
않는다. 그래서 **두 핸들러가 각자 게이트 함수를 다시 부른다**.

이 모듈은 도메인 데이터를 쓰지 않는다 — 쓰기는 감사 기록 1행과 큐 enqueue 뿐이다.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from flask import Blueprint, g, jsonify, request

from db import get_db
from foms.services.datetime_kst import get_today_kst
from foms.services.settlement_channel import (
    DEFAULT_PER_PAGE,
    build_channel_dashboard,
)
from foms.services.settlement_channel_access import can_view_channel_settlement
from foms.web.auth import log_access, login_required

#: 조회 기본 구간(오늘 기준). 정산 예정일은 **미래로도 잡히므로** 뒤쪽도 연다.
_DEFAULT_BACK_DAYS = 30
_DEFAULT_FORWARD_DAYS = 14

#: 화면이 다루는 채널 코드. 지금은 네이버 한 곳만 적재된다(코드는 채널 중립).
_ALLOWED_CHANNELS = ("NAVER",)

#: 권한 거부 문구 — 기존 정산 API(``foms/api/cs/settlement.py``)의 관례와 같은 톤.
_DENIED_MESSAGE = "정산 대시보드 열람 권한이 없습니다."

#: 감사 행위 코드. 라벨은 ``foms/services/audit_message_display.py`` ACTION_LABELS 에 등재.
SETTLE_SYNC_AUDIT_ACTION = "NAVER_SETTLE_SYNC_REQUEST"

settlement_channel_api_bp = Blueprint(
    "settlement_channel_api",
    __name__,
    url_prefix="/api/settlement/channel",
)


def _error(message: str, status: int):
    """공통 실패 응답(``{'success': False, 'data': None, 'error': ...}``)."""
    return jsonify({"success": False, "data": None, "error": message}), status


def _parse_day(raw: str, field: str) -> datetime.date:
    """``"YYYY-MM-DD"`` → :class:`datetime.date`. 형식 오류는 한글 사유로 ValueError.

    Args:
        raw: 쿼리 문자열 값.
        field: 사람이 읽을 파라미터 이름(오류 문구에 들어간다).

    Returns:
        파싱된 날짜.

    Raises:
        ValueError: 형식이 ``YYYY-MM-DD`` 가 아닐 때.
    """
    try:
        return datetime.date.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        raise ValueError(f"{field} 는 2026-09-02 형식의 날짜여야 합니다: {raw!r}") from None


def _range_args(today: datetime.date) -> tuple[datetime.date, datetime.date]:
    """``from``/``to`` 파라미터(미지정 시 오늘-30 ~ 오늘+14).

    Args:
        today: KST 오늘. ``get_today_kst()`` 는 ``date`` 를 반환한다 — ``.date()`` 를
            부르면 AttributeError 로 500 이 된다(프로젝트 함정 기록).

    Returns:
        (시작일, 종료일).

    Raises:
        ValueError: 날짜 형식 오류.
    """
    raw_from = (request.args.get("from") or "").strip()
    raw_to = (request.args.get("to") or "").strip()
    date_from = (_parse_day(raw_from, "from") if raw_from
                 else today - datetime.timedelta(days=_DEFAULT_BACK_DAYS))
    date_to = (_parse_day(raw_to, "to") if raw_to
               else today + datetime.timedelta(days=_DEFAULT_FORWARD_DAYS))
    return date_from, date_to


def _channel_arg() -> str:
    """``channel`` 파라미터(기본 NAVER). 허용 집합 밖이면 ValueError."""
    channel = (request.args.get("channel") or "").strip().upper() or _ALLOWED_CHANNELS[0]
    if channel not in _ALLOWED_CHANNELS:
        raise ValueError(
            f"channel 은 {'|'.join(_ALLOWED_CHANNELS)} 중 하나여야 합니다: {channel!r}")
    return channel


@settlement_channel_api_bp.route("", methods=["GET"])
@login_required
def api_settlement_channel():
    """채널 정산 탭 조회(읽기 전용).

    Query Args:
        channel: 채널 코드(기본 ``NAVER``).
        basis: 원장 날짜 축 ``expect``|``complete``|``basis``|``pay``(기본 expect).
        from, to: ``YYYY-MM-DD``(기본 오늘-30 ~ 오늘+14, 최대 폭 400일).
        granularity: ``day``|``week``|``month``(기본 day).
        ledger: ``case``|``commission``|``vat_case``(기본 case).
        page: 원장 페이지(1부터). per_page: 페이지 크기(≤200).
        type: 유형 코드 필터. q: 주문번호·상품주문번호 부분일치 검색.

    Returns:
        200 ``{'success': True, 'data': <build_channel_dashboard 반환값>, 'error': None}``.
        권한 거부 403, 파라미터 오류(날짜 형식·허용 집합·구간 폭) 400.
    """
    if not can_view_channel_settlement(getattr(g, "current_user", None)):
        return _error(_DENIED_MESSAGE, 403)

    today = get_today_kst()
    try:
        date_from, date_to = _range_args(today)
        data = build_channel_dashboard(
            get_db(),
            channel=_channel_arg(),
            basis=(request.args.get("basis") or "").strip() or "expect",
            date_from=date_from,
            date_to=date_to,
            granularity=(request.args.get("granularity") or "").strip() or "day",
            ledger=(request.args.get("ledger") or "").strip() or "case",
            page=request.args.get("page", type=int) or 1,
            per_page=request.args.get("per_page", type=int) or DEFAULT_PER_PAGE,
            filters={"type": request.args.get("type") or "",
                     "q": request.args.get("q") or ""},
            today=today,
        )
    except ValueError as exc:
        # 커널·파서가 사람이 읽는 한글 사유를 담아 던진다(내부 스택 노출 없음).
        return _error(str(exc), 400)

    return jsonify({"success": True, "data": data, "error": None})


def _backfill_arg(payload: dict) -> Optional[str]:
    """``backfill_from`` (선택). 형식 검증만 하고 문자열 그대로 큐에 넘긴다.

    Args:
        payload: 요청 JSON dict.

    Returns:
        ``"YYYY-MM-DD"`` 또는 None.

    Raises:
        ValueError: 형식이 날짜가 아닐 때.
    """
    raw = str(payload.get("backfill_from") or "").strip()
    if not raw:
        return None
    return _parse_day(raw, "backfill_from").isoformat()


def _enqueue(actor_user_id: int, backfill_from: Optional[str]) -> Any:
    """정산 동기화 job 을 큐에 넣는다. 큐 모듈이 아직 없으면 ``None``.

    **지연 import 인 이유**: 큐 헬퍼는 rq/redis 를 끌고 온다. 조회 화면이 그 import 에
    묶이면 안 되고, 배포 순서상 이 라우트가 먼저 올라가는 창도 있다.

    Args:
        actor_user_id: 누른 사람 id(기록용).
        backfill_from: 소급 적재 시작일 또는 None.

    Returns:
        ``True``/``False``(enqueue 결과) 또는 큐 헬퍼 부재 시 ``None``.
    """
    try:
        from foms.services.jobs.queue import enqueue_naver_settle_sync
    except ImportError:
        return None
    return enqueue_naver_settle_sync(actor_user_id=actor_user_id,
                                     backfill_from=backfill_from)


@settlement_channel_api_bp.route("/sync", methods=["POST"])
@login_required
def api_settlement_channel_sync():
    """"지금 동기화" — 큐에 넣기만 한다(네이버 호출은 WORKER 에서만 가능하다).

    Body(JSON, 선택):
        backfill_from: ``YYYY-MM-DD``. 주면 그 날짜부터 소급 적재한다.

    Returns:
        200 ``{'success': True, 'data': {'queued': bool}, 'error': None}``.
        ``queued`` 가 False 면 **이미 같은 job 이 큐에 있다**는 뜻이다(중복 enqueue 방지).
        권한 거부 403, 날짜 형식 오류 400, 큐 모듈 부재 503.
    """
    user = getattr(g, "current_user", None)
    if not can_view_channel_settlement(user):
        return _error(_DENIED_MESSAGE, 403)

    payload = request.get_json(silent=True)
    payload = payload if isinstance(payload, dict) else {}
    try:
        backfill_from = _backfill_arg(payload)
    except ValueError as exc:
        return _error(str(exc), 400)

    queued = _enqueue(int(user.id), backfill_from)
    if queued is None:
        return _error("동기화 큐가 아직 준비되지 않았습니다.", 503)

    log_access(
        "네이버 정산 동기화 요청" + ("" if queued else "(이미 대기 중)"),
        user.id,
        action=SETTLE_SYNC_AUDIT_ACTION,
        target_type="settlement_channel",
        detail={"queued": bool(queued), "backfill_from": backfill_from,
                "channel": _ALLOWED_CHANNELS[0]},
    )
    return jsonify({"success": True, "data": {"queued": bool(queued)}, "error": None})
