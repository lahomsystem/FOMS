"""채널(네이버) 정산 탭 API — SETTLE-CHANNEL-01 §5.

* ``GET  /api/settlement/channel`` — 탭 한 화면 전체(동기화 상태·KPI·차트·원장).
  ``?view=strip`` 이면 요약 탭 크로스 스트립 1줄이 필요한 최소 한 벌만 낸다(v1.1 T12).
  **새 라우트를 만들지 않는 이유**: 권한 판정·날짜 파싱·채널 검증이 완전히 같기 때문이다 —
  두 라우트로 갈라 두면 그 셋 중 하나가 조용히 어긋나는 날이 온다.
* ``GET  /api/settlement/channel/export.csv`` — 적재 원본 CSV 5종 스트리밍(v1.1 T14).
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

from flask import Blueprint, Response, g, jsonify, request, stream_with_context

from db import get_db
from foms.services.datetime_kst import get_today_kst
from foms.services.settlement_channel import (
    BASES,
    DEFAULT_BASIS,
    DEFAULT_PER_PAGE,
    build_channel_dashboard,
    build_channel_strip,
)
from foms.services.settlement_channel_access import can_view_channel_settlement
from foms.services.settlement_channel_export import (
    effective_basis,
    export_filename,
    iter_csv_lines,
    normalize_kind,
)
from foms.web.auth import log_access, login_required

#: 조회 기본 구간(오늘 기준). 정산 예정일은 **미래로도 잡히므로** 뒤쪽도 연다.
_DEFAULT_BACK_DAYS = 30
_DEFAULT_FORWARD_DAYS = 14

#: 화면이 다루는 채널 코드. 지금은 네이버 한 곳만 적재된다(코드는 채널 중립).
_ALLOWED_CHANNELS = ("NAVER",)

#: 권한 거부 문구 — 기존 정산 API(``foms/api/cs/settlement.py``)의 관례와 같은 톤.
_DENIED_MESSAGE = "정산 대시보드 열람 권한이 없습니다."

#: 큐 부재·장애 시 503 본문(CFO 감사 F-02). 큐 docstring·JS 헤더 문구와 같은 뜻이다 —
#: 큐 모듈 부재(ImportError)에만 붙던 옛 별도 문구는 같은 사실을 다른 말로 하던 것이라 뺐다.
SYNC_UNAVAILABLE_MESSAGE = "지금은 동기화할 수 없습니다. 잠시 뒤 다시 시도하세요."

#: ``enqueue_naver_settle_sync`` 3상태 리터럴(``foms.services.jobs.queue.SETTLE_ENQUEUE_*`` 와 같은 값).
#: 이 모듈 상단에서 큐 모듈을 import 하지 않기 위해(rq/redis 를 조회 화면에 끌어오지 않는 기존 결정)
#: 문자열을 한 번 더 적는다 — 값이 갈리면 ``test_api_state_literals_equal_the_queue_constants`` 가 잡는다.
_STATE_QUEUED = "queued"
_STATE_DUPLICATE = "duplicate"
_STATE_UNAVAILABLE = "unavailable"

#: 감사 메시지 꼬리 — reason 별. 큐 부재에 "(이미 대기 중)"이 붙던 결함이 F-02 다.
_SYNC_AUDIT_SUFFIX = {_STATE_QUEUED: "", _STATE_DUPLICATE: "(이미 대기 중)",
                      _STATE_UNAVAILABLE: "(큐 연결 불가)"}

#: 감사 행위 코드. 라벨은 ``foms/services/audit_message_display.py`` ACTION_LABELS 에 등재.
SETTLE_SYNC_AUDIT_ACTION = "NAVER_SETTLE_SYNC_REQUEST"

#: CSV 내보내기 감사 행위 코드. 파일에 구매자 성명이 실려 나가므로 **다운로드 1회 = 감사
#: 1행**이다(계약 §1.3 C5). 라벨 등재 역시 ACTION_LABELS 에 있어야 한다 — 없으면 감사
#: 화면에 영문 코드가 그대로 뜨고 CI 가 red 다.
SETTLE_EXPORT_AUDIT_ACTION = "NAVER_SETTLE_EXPORT_CSV"

#: 감사 대상 종류. ``target_id`` 는 **쓰지 않는다** — 그 컬럼은 ``Integer`` 라 CSV 종류
#: 같은 문자열을 넣으면 PostgreSQL 이 거절하고, ``log_access`` 는 fail-open 이라 감사 행이
#: **조용히 사라진다**(SQLite 로컬에서는 통과해 안 보인다). 종류는 ``detail`` 로 남긴다.
_EXPORT_TARGET_TYPE = "naver_settle_export"

#: ``view`` 허용 집합. 기본은 탭 한 벌, ``strip`` 은 요약 탭 크로스 스트립 1줄이다.
FULL_VIEW = "full"
STRIP_VIEW = "strip"
_ALLOWED_VIEWS = (FULL_VIEW, STRIP_VIEW)

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


def _view_arg() -> str:
    """``view`` 파라미터(기본 ``full``). 허용 집합 밖이면 ValueError.

    조용한 full 폴백을 하지 않는 이유: 오타 하나로 스트립을 요청한 화면이 탭 한 벌을
    받으면 **비용이 몇 배인 조회가 요약 탭 첫 화면에서 매번 돈다**. 틀린 요청은 틀렸다고
    말한다.

    Returns:
        ``"full"`` 또는 ``"strip"``.

    Raises:
        ValueError: 허용 집합 밖(사람이 읽는 한글 사유).
    """
    raw = (request.args.get("view") or "").strip().lower() or FULL_VIEW
    if raw not in _ALLOWED_VIEWS:
        raise ValueError(
            f"view 는 {'|'.join(_ALLOWED_VIEWS)} 중 하나여야 합니다: "
            f"{request.args.get('view')!r}")
    return raw


def _basis_arg() -> str:
    """``basis`` 파라미터(기본 ``expect``). 허용 집합 밖이면 ValueError."""
    basis = (request.args.get("basis") or "").strip() or DEFAULT_BASIS
    if basis not in BASES:
        raise ValueError(f"basis 는 {'|'.join(BASES)} 중 하나여야 합니다: {basis!r}")
    return basis


def _full_view(today: datetime.date, channel: str,
               date_from: datetime.date, date_to: datetime.date) -> dict:
    """탭 한 벌(KPI·차트·원장·예외). 파라미터를 커널 인자로 옮기기만 한다.

    Args:
        today: KST 오늘.
        channel: 채널 코드.
        date_from: 조회 시작일.
        date_to: 조회 종료일.

    Returns:
        :func:`build_channel_dashboard` 반환값.

    Raises:
        ValueError: 허용 집합·구간 폭 위반(커널이 던진다).
    """
    return build_channel_dashboard(
        get_db(),
        channel=channel,
        basis=(request.args.get("basis") or "").strip() or DEFAULT_BASIS,
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


@settlement_channel_api_bp.route("", methods=["GET"])
@login_required
def api_settlement_channel():
    """채널 정산 탭 조회(읽기 전용).

    Query Args:
        view: ``full``(기본, 탭 한 벌) 또는 ``strip``(요약 탭 크로스 스트립 1줄).
        channel: 채널 코드(기본 ``NAVER``).
        basis: 원장 날짜 축 ``expect``|``complete``|``basis``|``pay``(기본 expect).
        from, to: ``YYYY-MM-DD``(기본 오늘-30 ~ 오늘+14, 최대 폭 400일).
        granularity: ``day``|``week``|``month``(기본 day).
        ledger: ``case``|``commission``|``vat_case``(기본 case).
        page: 원장 페이지(1부터). per_page: 페이지 크기(≤200).
        type: 유형 코드 필터. q: 주문번호·상품주문번호 부분일치 검색.

    Returns:
        200 ``{'success': True, 'data': <커널 반환값>, 'error': None}``.
        ``view=strip`` 이면 :func:`build_channel_strip` 의 최소 한 벌이고, 그 밖에는
        예전과 똑같은 탭 한 벌이다(기존 화면 무회귀).
        권한 거부 403, 파라미터 오류(날짜 형식·허용 집합·구간 폭) 400.
    """
    if not can_view_channel_settlement(getattr(g, "current_user", None)):
        return _error(_DENIED_MESSAGE, 403)

    today = get_today_kst()
    try:
        view = _view_arg()
        channel = _channel_arg()
        date_from, date_to = _range_args(today)
        if view == STRIP_VIEW:
            # 스트립은 전기 구간·원장·수수료·부가세를 조회하지 않는다(요약 탭 TTFB 보호).
            data = build_channel_strip(get_db(), channel=channel, date_from=date_from,
                                       date_to=date_to, today=today)
        else:
            data = _full_view(today, channel, date_from, date_to)
    except ValueError as exc:
        # 커널·파서가 사람이 읽는 한글 사유를 담아 던진다(내부 스택 노출 없음).
        return _error(str(exc), 400)

    resp = jsonify({"success": True, "data": data, "error": None})
    # 응답에 구매자명이 실린다. 서비스 워커의 PII 게이트(``static/sw.js`` responseForbidsStore)는
    # 이 헤더로만 판정하므로, 나중에 ``/api/`` 캐시 분기가 생겨도 이 응답은 캐시에 남지 않는다(F-06).
    resp.headers["Cache-Control"] = "no-store"
    return resp


#: 소급 적재 하한(오늘 기준 일수). 조회 화면 상한(``MAX_RANGE_DAYS``)과 같은 폭 — 화면에서 고를 수 있는
#: 구간보다 더 옛날을 받아오라는 요청은 오타이거나 오선택이라 워커 호출(하루 60건)을 태우기 전에 막는다.
_BACKFILL_MAX_DAYS_BACK = 400


def _backfill_arg(payload: dict, today: datetime.date) -> Optional[str]:
    """``backfill_from`` (선택). 형식과 하한(오늘-400일)·상한(오늘)을 검사하고 문자열로 큐에 넘긴다.

    Args:
        payload: 요청 JSON dict.
        today: KST 오늘.

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
    day = _parse_day(raw, "backfill_from")
    floor = today - datetime.timedelta(days=_BACKFILL_MAX_DAYS_BACK)
    if day < floor:
        raise ValueError(
            f"backfill_from 은 {floor.isoformat()} 이후여야 합니다(최대 {_BACKFILL_MAX_DAYS_BACK}일 소급).")
    if day > today:
        raise ValueError("backfill_from 은 오늘 이전이어야 합니다.")
    return day.isoformat()


def _enqueue(actor_user_id: int,
             backfill_from: Optional[str]) -> tuple[str, Optional[str]]:
    """정산 동기화 job 을 큐에 넣고 ``(state, job_id)`` 를 돌려준다(F-02 3상태).

    **지연 import 인 이유**: 큐 헬퍼는 rq/redis 를 끌고 온다. 조회 화면이 그 import 에
    묶이면 안 되고, 배포 순서상 이 라우트가 먼저 올라가는 창도 있다. 그 창(큐 모듈 부재)도
    "큐를 쓸 수 없다"는 같은 사실이라 ``unavailable`` 로 접는다 — 별도 문구를 두지 않는다.

    Args:
        actor_user_id: 누른 사람 id(기록용).
        backfill_from: 소급 적재 시작일 또는 None.

    Returns:
        ``("queued"|"duplicate"|"unavailable", job_id)`` — ``job_id`` 는 실제로 큐에 들어갔을
        때만 값이 있고 그 밖은 None.
    """
    try:
        # 큐가 실제로 쓴 dedupe id 를 감사 행에 적어야 그 행이 rq 큐(job 해시)와 대조된다(감사 E-02).
        from foms.services.jobs.queue import (
            SETTLE_ENQUEUE_QUEUED,
            _SETTLE_SYNC_JOB_ID,
            enqueue_naver_settle_sync,
        )
    except ImportError:
        return _STATE_UNAVAILABLE, None
    state = enqueue_naver_settle_sync(actor_user_id=actor_user_id,
                                      backfill_from=backfill_from)
    return state, (_SETTLE_SYNC_JOB_ID if state == SETTLE_ENQUEUE_QUEUED else None)


def _sync_window(today: datetime.date, backfill_from: Optional[str]) -> tuple[str, str]:
    """요청 시점에 계산된 실행 창 ``(from, to)`` — 워커 ``default_sync_window`` 와 **같은 함수**.

    감사 행이 "무엇을 받아오라고 했는가"를 말하려면 기본 창을 그 자리에서 적어야 한다 — 워커
    식이 나중에 바뀌면 옛 감사 행을 되짚을 수 없다(감사 E-02). 식을 베끼지 않고 워커 함수를 부르는
    이유: 상수가 같아도 식(클램프·보정)이 갈리는 날 감사 행이 조용히 거짓이 된다. 아래
    ``_DEFAULT_BACK_DAYS``/``_DEFAULT_FORWARD_DAYS`` 는 조회 기본 창이라 값이 같아도 뜻이 다르다.

    **지연 import 인 이유**: ``settle_sync`` 는 네이버 클라이언트(requests·bcrypt)를 끌고 온다.
    조회 커널이 적재 모듈에 의존하지 않는 방향(``foms/services/settlement_channel.py`` 모듈
    docstring)을 이 API 모듈도 지킨다 — ``_enqueue`` 와 같은 사유다.

    Args:
        today: KST 오늘.
        backfill_from: 소급 적재 시작일(``YYYY-MM-DD``) 또는 None.

    Returns:
        ISO 날짜 문자열 두 개: ``backfill_from`` 또는 오늘-``DEFAULT_ROLLING_DAYS``, 그리고
        오늘+``DEFAULT_FUTURE_DAYS``.
    """
    from foms.services.integrations.naver_commerce.settle_sync import default_sync_window

    start, end = default_sync_window(
        today, datetime.date.fromisoformat(backfill_from) if backfill_from else None)
    return start.isoformat(), end.isoformat()


@settlement_channel_api_bp.route("/sync", methods=["POST"])
@login_required
def api_settlement_channel_sync():
    """"지금 동기화" — 큐에 넣기만 한다(네이버 호출은 WORKER 에서만 가능하다).

    Body(JSON, 선택):
        backfill_from: ``YYYY-MM-DD``. 주면 그 날짜부터 소급 적재한다.

    Returns:
        큐 결과 3상태(F-02) 그대로 —
        ``queued`` → 200 ``{'success': True, 'data': {'queued': True, 'reason': 'queued',
        'job_id': 'naver_settle_sync'}, 'error': None}`` /
        ``duplicate``(이미 같은 job 이 큐에 있다) → 200 ``data={'queued': False,
        'reason': 'duplicate', 'job_id': None}`` /
        ``unavailable``(큐 부재·Redis 장애·enqueue 실패) → **503**
        ``{'success': False, 'data': None, 'error': SYNC_UNAVAILABLE_MESSAGE}``.
        세 경우 모두 감사 행 1건(``detail.reason``)을 먼저 남긴다 — 장애 뒤 "누가 눌렀는데 왜
        안 돌았나"를 감사로 되짚을 수 있어야 한다. 권한 거부 403, 날짜 형식 오류 400.
    """
    user = getattr(g, "current_user", None)
    if not can_view_channel_settlement(user):
        return _error(_DENIED_MESSAGE, 403)

    payload = request.get_json(silent=True)
    payload = payload if isinstance(payload, dict) else {}
    today = get_today_kst()
    try:
        backfill_from = _backfill_arg(payload, today)
    except ValueError as exc:
        return _error(str(exc), 400)

    state, job_id = _enqueue(int(user.id), backfill_from)
    window_from, window_to = _sync_window(today, backfill_from)
    log_access(
        "네이버 정산 동기화 요청" + _SYNC_AUDIT_SUFFIX[state],
        user.id,
        action=SETTLE_SYNC_AUDIT_ACTION,
        target_type="settlement_channel",
        # job_id·from·to: 감사 행이 rq 큐와 실행 이력(scope) 양쪽에 닿게 한다(감사 E-02).
        # reason: 큐 부재와 중복을 감사에서 구분한다(F-02) — 7키 정확 일치가 계약이다.
        detail={"queued": state == _STATE_QUEUED, "reason": state,
                "backfill_from": backfill_from, "channel": _ALLOWED_CHANNELS[0],
                "job_id": job_id, "from": window_from, "to": window_to},
    )
    if state == _STATE_UNAVAILABLE:
        return _error(SYNC_UNAVAILABLE_MESSAGE, 503)
    return jsonify({"success": True, "error": None,
                    "data": {"queued": state == _STATE_QUEUED, "reason": state,
                             "job_id": job_id}})


@settlement_channel_api_bp.route("/sync/progress", methods=["GET"])
@login_required
def api_settlement_channel_sync_progress():
    """진행 중인 동기화가 지금 어디까지 왔는지.

    화면이 [지금 동기화] 를 누른 뒤 2초마다 이 자리를 읽는다. 지금까지는 결과가 반영될
    때까지 화면이 아무 말도 못 했다 — 60초 동안 "확인하는 중" 한 줄뿐이라, 워커가 죽어
    있어도(2026-09-08 사고) 실패해도(run 28·29) 사용자는 버튼을 계속 눌렀다.

    **감사 행을 남기지 않는다** — 2초마다 읽는 조회라 남기면 감사가 이 한 종류로 덮인다.

    Returns:
        200 ``{'success': True, 'data': {...}, 'error': None}``. ``data`` 는 —
        ``run_id``·``status``(RUNNING/OK/FAILED/ABORTED_QUOTA)·``trigger``·
        ``started_at``·``finished_at``(UTC ISO)·``elapsed_seconds``·``error``(실패 사유)·
        ``progress``(``{phase, done_days, total_days, percent, current_date, calls, rows}``
        또는 None). 실행 이력이 아예 없으면 ``data=None``. 권한 거부 403.
    """
    user = getattr(g, "current_user", None)
    if not can_view_channel_settlement(user):
        return _error(_DENIED_MESSAGE, 403)

    from models import NaverSettleSyncRun

    row = (get_db().query(NaverSettleSyncRun)
           .filter(NaverSettleSyncRun.channel == _ALLOWED_CHANNELS[0])
           .order_by(NaverSettleSyncRun.id.desc())
           .first())
    if row is None:
        return jsonify({"success": True, "error": None, "data": None})

    stats = row.stats if isinstance(row.stats, dict) else {}
    progress = stats.get("progress") if isinstance(stats.get("progress"), dict) else None
    finished = row.finished_at
    elapsed = ((finished or datetime.datetime.utcnow()) - row.started_at).total_seconds()
    return jsonify({"success": True, "error": None, "data": {
        "run_id": int(row.id),
        "status": row.status,
        "trigger": row.trigger,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": finished.isoformat() if finished else None,
        "elapsed_seconds": int(max(0, elapsed)),
        "error": row.error,
        "progress": progress,
    }})


def _export_filters() -> dict:
    """CSV 내보내기의 유형·검색 조건. **빈 값은 키째 뺀다.**

    일별 정산·부가세 일별은 조건을 받지 않는 표라(:data:`~foms.services.
    settlement_channel_export.FILTER_FIELDS` 가 빈 튜플) 값이 있으면 커널이 400 으로
    거절한다. 화면이 안 보내면 그만이고, 손으로 붙인 URL 은 조용히 무시되지 않고 사유를
    받는다 — 조건을 말없이 버리면 화면과 다른 파일이 내려간다.

    Returns:
        ``{'type': ..., 'q': ...}`` 중 값이 있는 키만.
    """
    filters = {}
    for key in ("type", "q"):
        value = (request.args.get(key) or "").strip()
        if value:
            filters[key] = value
    return filters


def _log_export(user: Any, kind: str, channel: str,
                date_from: datetime.date, date_to: datetime.date,
                basis: str = DEFAULT_BASIS, *, filters: dict, filename: str) -> None:
    """CSV 다운로드 1회를 감사 원장에 남긴다(계약 §1.3 C5).

    **응답을 만들기 전에** 기록한다. 스트리밍이 중간에 끊겨도 "받아 갔다"는 사실은 남아야
    하고, 반대로 응답 생성 뒤에 기록하면 제너레이터가 소진되기 전에는 아직 안 도는 코드가
    된다. 행수는 이 시점에 모르므로 ``detail`` 에 넣지 않는다(모르는 것을 적지 않는다).
    조건과 파일명은 이 시점에 안다 — 없으면 **None 으로 키를 남긴다**(키를 빼면 "조건 없이
    받았다"와 "기록이 옛 형식이다"를 구분할 수 없다, 감사 E-06).

    Args:
        user: 내려받는 사람.
        kind: CSV 종류(정본 이름).
        channel: 채널 코드.
        date_from: 구간 시작일.
        date_to: 구간 종료일.
        basis: 요청이 고른 기준일 축. 기록에는 **실효 축**(되돌림 뒤)을 남긴다 — 요청값을
            적으면 나중에 그 기록으로 같은 파일을 다시 만들려는 사람이 다른 행 집합을 받는다.
        filters: 파일에 실제로 걸린 ``{'type', 'q'}`` (빈 값은 키 없음).
        filename: ``Content-Disposition`` 에 실리는 파일명과 **같은 문자열** — 내려받은 파일과
            감사 행이 서로를 찾을 수 있어야 한다(감사 G-06).
    """
    log_access(
        "네이버 정산 CSV 내보내기",
        getattr(user, "id", None),
        action=SETTLE_EXPORT_AUDIT_ACTION,
        target_type=_EXPORT_TARGET_TYPE,
        detail={"kind": kind, "channel": channel,
                "from": date_from.isoformat(), "to": date_to.isoformat(),
                "basis": effective_basis(kind, basis),
                "type": filters.get("type") or None, "q": filters.get("q") or None,
                "filename": filename},
    )


@settlement_channel_api_bp.route("/export.csv", methods=["GET"])
@login_required
def api_settlement_channel_export_csv():
    """적재된 원본 CSV 를 줄 단위로 흘려 보낸다(읽기 전용, v1.1 T14).

    화면 원장은 41필드지만 이 파일은 적재 원본 전량이다("적재 100% · CSV 100% · 화면 41").
    표 계산 프로그램이 한글을 깨지 않도록 첫 줄에 UTF-8 BOM 이 붙고 줄바꿈은 CRLF 다.

    Query Args:
        kind: CSV 종류(필수) — ``settle_daily``|``settle_case``|``commission``|
            ``vat_daily``|``vat_case``(짧은 별칭 ``daily``·``case`` 허용) +
            회계 제출용 7열 큐레이션 표 ``settle_case_sheet``(별칭 ``sheet``·``case_sheet``).
        channel: 채널 코드(기본 ``NAVER``).
        from, to: ``YYYY-MM-DD``(기본 오늘-30 ~ 오늘+14, 최대 폭 400일 — 탭과 같은 상한).
        basis: 기준일 축(건별 정산·수수료·큐레이션 표에만 뜻이 있다). 실효 축이 예정일이
            아니면 파일명에 축 조각이 붙는다(같은 기간을 축만 바꿔 받아도 안 덮어쓴다).
        type, q: 유형·검색 조건. 조건을 받지 않는 종류에 주면 400 이다.

    Returns:
        200 ``text/csv; charset=utf-8`` 스트리밍 + ASCII 파일명 ``Content-Disposition``.
        권한 거부는 **JSON 403**(빈 CSV·오류 CSV 를 파일 자리에 주지 않는다),
        종류·구간·조건 오류는 JSON 400.
    """
    user = getattr(g, "current_user", None)
    if not can_view_channel_settlement(user):
        return _error(_DENIED_MESSAGE, 403)

    today = get_today_kst()
    try:
        kind = normalize_kind(request.args.get("kind"))
        channel = _channel_arg()
        basis = _basis_arg()
        date_from, date_to = _range_args(today)
        filters = _export_filters()
        # 커널은 종류·구간·조건을 **호출 시점에** 검증한다. 스트림이 시작된 뒤에 터지면
        # 반쪽 파일이 200 으로 내려가 사람이 그걸 정상 파일로 읽는다.
        lines = iter_csv_lines(get_db(), kind=kind, date_from=date_from, date_to=date_to,
                               channel=channel, basis=basis, filters=filters)
    except ValueError as exc:
        return _error(str(exc), 400)

    # 파일명은 한 번만 만들어 감사 행과 응답 헤더가 **같은 문자열**을 쓴다(감사 G-06·E-06).
    filename = export_filename(kind, date_from, date_to, basis=basis,
                               type_code=filters.get("type"), q=filters.get("q"))
    _log_export(user, kind, channel, date_from, date_to, basis,
                filters=filters, filename=filename)
    return Response(
        stream_with_context(lines),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
