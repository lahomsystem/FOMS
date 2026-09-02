"""일괄 발송처리 **대상 선별** (NAVER-BULKDISPATCH-01 T1) — 읽기 전용.

당일 실측 스케줄에 잡힌 네이버 주문을 집(household) 단위로 모아 준다. 네이버로 나가는
호출은 여기 없다 — 이 모듈은 "무엇을 보낼 것인가"만 답하고, 실제 발송은
:func:`fulfillment.dispatch_order` 가 WORKER 에서 한다.

**왜 화면 술어를 재사용하지 않는가** (2026-08-31 조사):

* 워크벤치 큐(``_dispatched_count``)는 **우리 표식만** 센다. 판매자센터에서 사람이 직접
  발송한 집은 큐에 "미발송"으로 보이고, 실행하면 ``FulfillmentError`` 로 떨어진다. 단건은
  실패 1건이지만 일괄에서는 대량 실패 띠가 된다. 그래서 :func:`dispatch_pending_clause`
  (두 신호)를 쓴다.
* :func:`fulfillment._broken_collection_guard` 는 **발주확인에서만** 불린다. 깨진 수집분도
  발송처리는 그대로 나간다. 단건은 사람이 그 집을 보고 누르지만 일괄은 아무도 안 본 채로
  나가므로, **선별이 대신** :data:`fulfillment.HEALTHY_SYNC_STATUSES` 를 요구한다.
* 화면 필터(검색어·담당자·mine)와 표시 캡은 **상속하지 않는다**. 상속하면 누가 눌렀느냐에
  따라 나가는 주문이 달라진다 — 되돌릴 수 없는 조작에서 있을 수 없다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import and_, false, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from models import ExternalOrderLink, Order, OrderScheduleDate

from . import mapping
from .constants import CHANNEL
from .fulfillment import (
    CLOSE_NOW_RELATIONS,
    HEALTHY_SYNC_STATUSES,
    household_key,
)

logger = logging.getLogger(__name__)

__all__ = [
    "BULK_DISPATCH_LIMIT",
    "BulkDispatchTarget",
    "build_day_summary",
    "build_preview",
    "dispatch_pending_clause",
    "select_sendable",
    "select_targets",
]

#: 실측 일정의 ``OrderScheduleDate.kind``. 실측 대시보드가 쓰는 값과 같아야 한다
#: (`foms/web/measurement/dashboard.py` 의 당일 술어).
MEASUREMENT_KIND = "measurement"

#: 완료 주문 컷오프(일). 실측 대시보드 `Order.dashboard_active_filter(days=60)` 와 맞춘다.
ACTIVE_WINDOW_DAYS = 60

#: 한 번에 보낼 수 있는 집 수 상한 (2026-08-31 운영 실측으로 확정).
#:
#: 관측된 하루 최대는 **7집**이고 50 은 그 7배다 — "평소엔 안 닿는 안전장치" 조건을
#: 만족한다. 이 값에 **닿는 것 자체가 경보다**: 술어가 틀렸거나 데이터가 이상하다는 뜻이라
#: 사람이 봐야 한다. 그래서 잘렸을 때 응답·로그·화면 문구 **셋 다** 에 남긴다(옛 주문 정리
#: 라우트가 20건만 넣으면서 count 는 전체를 줘 화면과 어긋났던 실수를 반복하지 않는다).
BULK_DISPATCH_LIMIT = 50


def dispatch_pending_clause():
    """'발송처리 전' 조건 — 우리 표식도 네이버 ``sendDate`` 도 없는 링크.

    부분 인덱스 ``ix_external_order_link_dispatch_pending`` 의 조건식과 **글자까지 같아야**
    한다. 조건식이 어긋나면 PostgreSQL 이 부분 인덱스를 증명하지 못해 통째로 무시하고,
    그때 나오는 Seq Scan 은 "선택도가 낮아서"로 오독된다(2026-08-30 CEO 지적 1).

    :data:`models.JSONColumn` 의 베이스 타입이 ``JSON`` 이라(``JSON().with_variant(JSONB,…)``)
    ``.as_string()`` 이 ``CAST(… AS VARCHAR)`` 를 붙인다 — 인덱스 조건식도 **그 모양**이어야
    한다. 마이그레이션에 손으로 적지 말고 아래 렌더 결과를 그대로 붙인다::

        coalesce(CAST(((external_order_links.triage_state -> 'fulfillment')
                       ->> 'dispatched_at') AS VARCHAR), '') = ''
        AND coalesce(CAST(((external_order_links.raw_snapshot -> 'delivery')
                       ->> 'sendDate') AS VARCHAR), '') = ''

    **알려진 어긋남 1개(수용)**: :func:`mapping.extract_delivery` 는 최상위 ``delivery`` 가
    없으면 ``productOrder.delivery`` → ``order.delivery`` 로 내려가지만 이 SQL 은 최상위만
    본다. 수집 파이프라인이 저장하는 모양은 최상위라 실데이터는 같다.

    이 함수가 **정본**이다. `foms/web/admin/naver_ingest.py` 의 동명 함수는 여기로 위임한다 —
    같은 축의 술어를 두 벌 두면 §4.4가 지적한 어긋남이 그대로 재생산된다.

    Returns:
        SQLAlchemy 불리언 식(``and_`` 두 조각).
    """
    ours = ExternalOrderLink.triage_state["fulfillment"]["dispatched_at"].as_string()
    naver = ExternalOrderLink.raw_snapshot["delivery"]["sendDate"].as_string()
    return and_(func.coalesce(ours, "") == "", func.coalesce(naver, "") == "")


@dataclass
class BulkDispatchTarget:
    """일괄 발송처리 대상 집 1개.

    Attributes:
        link_id: 대표 링크 id. 집 안에서는 어느 링크를 넘겨도
            :func:`fulfillment.dispatch_order` 가 같은 집합을 되찾으므로 대표 선정이 결과를
            바꾸지 않는다(`dock.py` 의 같은 규칙). 재현 가능하도록 **최소 id** 로 고정한다.
        household: :func:`fulfillment.household_key` 결과(주문번호·전화·주소).
        external_order_no: 네이버 묶음 주문번호(표시·묶기용).
        link_ids: 집에 속한 전체 링크 id.
        pending_link_ids: 그중 아직 발송 전인 링크 id(양쪽 신호 모두 빈 것).
        sent_link_ids: 이미 발송된 링크 id — **우리가 보낸 것과 판매자센터에서 사람이
            보낸 것을 함께** 센다. 우리 표식만 보면 손으로 보낸 집이 영원히 "남음"으로
            뜬다(화면 큐가 이미 그 실수를 하고 있다).
        sent_at: 그 집의 마지막 발송 시각(KST ``YYYY-MM-DD HH:MM``). 없으면 빈 문자열 —
            **없는 값을 지어내지 않는다**.
        sent_by_naver: 발송된 건이 **전부** 네이버 원본 기록뿐인가(= 판매자센터 수동 발송).
            우리가 한 일과 사람이 한 일을 화면이 구별해서 말하기 위한 값이다.
        failure_reason: 마지막 발송처리 실패 사유. **아직 보낼 게 남은 집에만** 채운다 —
            전부 나간 집의 옛 실패 기록은 지금 사실이 아니고, 그걸 빨갛게 띄우면 화면이
            "발송됐는데 실패"라고 말한다.
        state: ``"sent"``(다 나감) · ``"superseded"``(취소 확정 뒤 재결제 집으로 나감) ·
            ``"failed"``(남았고 실패 기록 있음) · ``"blocked"``(남았고 지금 못 보냄) ·
            ``"pending"``(남았고 보낼 수 있음).
        all_canceled: 집의 상품주문이 **전부** 취소·반품 확정인가. 재결제 짝 판정의 재료다.
        superseded_by: 이 집을 대신해 실제로 나간 **재결제 집**의 네이버 주문번호.
            비어 있으면 그런 집이 없다.
        superseded_at: 그 재결제 집이 나간 시각(KST ``YYYY-MM-DD HH:MM``).
        order_ids: 이 집이 붙은 FOMS 주문 id(0개일 수 있다 — 주문 미생성 수집분).
        customer_names: 붙은 주문의 고객명(화면이 집을 알아보게 — 표시 전용).
        measurement_done: 붙은 주문이 **모두** 실측완료로 찍혀 있는가. **표시 전용이고
            대상을 거르지 않는다** — 실측 '일정'과 실측 '완료'는 다른 축이고, 방문 취소·부재
            건을 자동으로 빼는 것은 사람의 결정이지 이 함수의 결정이 아니다.
        eligible: 지금 발송처리를 보낼 수 있는가.
        reason: ``eligible`` 이 거짓일 때 사람이 읽는 사유. 참이면 빈 문자열.
    """

    link_id: int
    household: tuple[str, str, str]
    external_order_no: str
    link_ids: list[int] = field(default_factory=list)
    pending_link_ids: list[int] = field(default_factory=list)
    order_ids: list[int] = field(default_factory=list)
    customer_names: list[str] = field(default_factory=list)
    measurement_done: bool = False
    eligible: bool = True
    reason: str = ""
    sent_link_ids: list[int] = field(default_factory=list)
    sent_at: str = ""
    sent_by_naver: bool = False
    failure_reason: str = ""
    state: str = "pending"
    all_canceled: bool = False
    superseded_by: str = ""
    superseded_at: str = ""


def _measurement_order_ids(session: Session, *, on_date: str) -> list[int]:
    """그날 실측 일정이 잡힌 주문 id — 실측 대시보드와 **같은 술어**.

    상속: 일정 조인(``kind='measurement'``)·``dashboard_active_filter``·대시보드 scope.
    버림: 검색어·담당자·mine 필터·표시 캡. 화면 필터를 상속하면 누가 눌렀느냐에 따라
    나가는 주문이 달라진다.

    Args:
        session: DB 세션.
        on_date: ``YYYY-MM-DD`` (KST 기준 날짜 문자열 — 일정 테이블이 문자열로 들고 있다).

    Returns:
        주문 id 목록(중복 제거).
    """
    from foms.services.measurement_read_model import (
        apply_measurement_dashboard_order_scope,
    )

    query = session.query(Order.id).filter(
        Order.dashboard_active_filter(days=ACTIVE_WINDOW_DAYS)
    )
    query = apply_measurement_dashboard_order_scope(query)
    query = query.join(OrderScheduleDate, Order.id == OrderScheduleDate.order_id).filter(
        OrderScheduleDate.kind == MEASUREMENT_KIND,
        OrderScheduleDate.date == on_date,
    )
    return [row[0] for row in query.distinct().all()]


def _day_links(session: Session, order_ids: list[int]) -> list[ExternalOrderLink]:
    """모집단 주문에 붙은 네이버 링크 **전부** — 발송 전도 발송 후도 함께.

    발송 전만 걷으면 "다 나갔다"와 "애초에 대상이 없었다"를 구별할 수 없다. 그 둘이 화면에서
    같은 모양(띠 사라짐)으로 보인 것이 2026-08-31 운영 1회차의 결함이다 — 되돌릴 수 없는
    조작에서 결과가 안 보이면 사람이 판매자센터를 다시 열게 되고, 이 기능이 없앤 일이
    되살아난다.

    ``order_id`` 로 거르는 것이 "네이버 유래" 판정의 전부다 —
    ``structured_data['source']`` 는 쓰지 않는다(2026-08-28 운영 실측에서 오염 의심분이
    남았고 소급 구별이 불가능하다).

    Args:
        session: DB 세션.
        order_ids: 모집단 주문 id.

    Returns:
        링크 목록. 입력이 비면 빈 목록(쿼리하지 않는다).
    """
    if not order_ids:
        return []
    return (
        session.query(ExternalOrderLink)
        .filter(
            ExternalOrderLink.channel == CHANNEL,
            ExternalOrderLink.order_id.in_(order_ids),  # perf-ok: 당일 실측분 batch
        )
        .order_by(ExternalOrderLink.id.asc())
        .all()
    )


def _naver_send_date(link: ExternalOrderLink) -> str:
    """네이버 **원본이 말하는** 발송 시각 원문 — 없으면 빈 문자열.

    :func:`fulfillment._naver_dispatched_at` 과 **같은 자리**를 읽는다(``extract_delivery``).
    워커가 멱등 판정에 쓰는 그 신호와 어긋나면, 선별이 "보낼 수 있다"고 말한 집을 워커가
    ``FulfillmentError`` 로 되돌려보낸다.

    :func:`dispatch_pending_clause` 의 SQL 은 최상위 ``delivery`` 만 보는 반면 이쪽은
    ``productOrder``·``order`` 아래까지 내려간다 — **더 넓게 '발송됨'으로 세는 쪽**이라
    어긋나도 안전한 방향이다(안 보낸 것을 보냈다고 하지, 보낸 것을 안 보냈다고 하지 않는다).

    Args:
        link: 링크 1건.

    Returns:
        ``delivery.sendDate`` 원문(공백 제거).
    """
    return str(mapping.extract_delivery(link.raw_snapshot or {}).get("send_date") or "").strip()


def _is_dispatched(link: ExternalOrderLink) -> bool:
    """이 상품주문이 이미 발송처리됐는가 — **신호 두 벌**.

    ①우리 표식(``triage_state.fulfillment.dispatched_at``) ②네이버 원본(``delivery.sendDate``).
    ②를 빼면 판매자센터에서 사람이 보낸 집이 영원히 "남음"으로 뜬다.

    판정은 워커가 쓰는 술어 :func:`fulfillment.is_dispatch_pending` 를 그대로 뒤집는다 —
    선별과 워커가 다른 식을 쓰면 "보낼 수 있다"고 고른 집을 워커가 ``FulfillmentError``
    로 되돌려보낸다(일괄에서는 대량 실패 띠가 된다).

    Args:
        link: 링크 1건.

    Returns:
        둘 중 하나라도 있으면 참.
    """
    from .fulfillment import is_dispatch_pending

    return not is_dispatch_pending(link)


def _sent_stamp(link: ExternalOrderLink) -> tuple[str, bool]:
    """발송된 링크 1건의 시각과 출처.

    Args:
        link: 이미 발송된 링크.

    Returns:
        ``(KST 'YYYY-MM-DD HH:MM' 문자열, 네이버 원본에서만 온 값인가)``.
        시각을 못 읽으면 첫 값이 빈 문자열이다 — 없는 값을 지어내지 않는다.
    """
    from foms.services.datetime_kst import format_datetime_kst

    ours = str(_fulfillment_state(link).get("dispatched_at") or "").strip()
    raw = ours or _naver_send_date(link)
    text = (format_datetime_kst(raw, "%Y-%m-%d %H:%M") or "") if raw else ""
    return text, not ours


def _dispatch_failure(link: ExternalOrderLink) -> str:
    """이 링크에 남은 **발송처리** 실패 사유 — 다른 작업의 실패는 세지 않는다.

    ``last_error_action`` 을 안 보면 발주확인 실패가 발송 실패 줄에 뜬다. 화면의
    '실패한 집만 다시 시도' 가 같은 값을 보고 작업을 고른다.

    Args:
        link: 링크 1건.

    Returns:
        사유 문장. 없으면 ``""``.
    """
    state = _fulfillment_state(link)
    if str(state.get("last_error_action") or "").strip() != "dispatch":
        return ""
    return str(state.get("last_error") or "").strip()


def _expand_households(
    session: Session, candidates: list[ExternalOrderLink]
) -> list[ExternalOrderLink]:
    """후보 링크가 속한 **집 전체**를 한 번에 읽는다 (N+1 금지).

    :func:`fulfillment._links_of_group` 을 링크마다 부르면 집 수만큼 쿼리가 곱해진다.
    1차 축(``external_order_no``)으로 한 번에 걷고 2차 판정(:func:`household_key`)은
    파이썬에서 한다 — 서비스가 쓰는 것과 같은 2단 규칙이다.

    Args:
        session: DB 세션.
        candidates: 후보 링크.

    Returns:
        후보가 속한 집들의 전체 링크(후보 포함).
    """
    order_nos = {
        (row.external_order_no or "").strip()
        for row in candidates
        if (row.external_order_no or "").strip()
    }
    rows = list(candidates)
    if order_nos:
        rows = (
            session.query(ExternalOrderLink)
            .filter(
                ExternalOrderLink.channel == CHANNEL,
                ExternalOrderLink.external_order_no.in_(sorted(order_nos)),  # perf-ok: batch
            )
            .order_by(ExternalOrderLink.id.asc())
            .all()
        )
        seen = {row.id for row in rows}
        rows.extend(row for row in candidates if row.id not in seen)
    return rows


def _blocking_reason(links: list[ExternalOrderLink]) -> str:
    """집이 지금 발송처리를 못 받는 사유 — 없으면 빈 문자열.

    :func:`fulfillment.dispatch_order` 의 가드와 **같은 순서**로 본다. 다만 마지막 항목
    (수집 상태)은 서비스에 없는 조건이다 — 모듈 docstring 참조.

    Args:
        links: 집 전체 링크.

    Returns:
        사람이 읽는 사유 문장. 보낼 수 있으면 ``""``.
    """
    for row in links:
        claim = mapping.extract_claim(row.raw_snapshot or {})
        if mapping.blocks_irreversible(claim):
            return "취소·반품·교환이 걸린 주문입니다 — 판매자센터에서 처리하세요."
    canceled = [row for row in links if _fulfillment_state(row).get("canceled_at")]
    if canceled:
        return f"취소한 주문입니다(취소된 상품주문 {len(canceled)}건)."
    broken = [
        row for row in links
        if (row.sync_status or "").strip().upper() not in HEALTHY_SYNC_STATUSES
    ]
    if broken:
        return f"수집이 완전하지 않습니다(상태 이상 {len(broken)}건) — 다시 읽은 뒤 처리하세요."
    return _place_pending_reason(links)


def _place_pending_reason(links: list[ExternalOrderLink]) -> str:
    """발주확인 선행 규칙 — 막히면 사유, 아니면 빈 문자열.

    ``close_now``(집 전체가 :data:`fulfillment.CLOSE_NOW_RELATIONS`)면 발주확인 없이 닫는다.
    ``all()`` 인 이유는 attach 이후 수집된 형제가 ``NEW`` 로 들어와 관계가 섞이기 때문이다 —
    ``any()`` 로 두면 그 형제까지 발주확인 없이 나간다.

    Args:
        links: 집 전체 링크.

    Returns:
        사유 문장 또는 ``""``.
    """
    close_now = bool(links) and all(
        (row.relation or "").upper() in CLOSE_NOW_RELATIONS for row in links
    )
    if close_now:
        return ""
    pending = [row for row in links if _is_place_pending(row)]
    if pending:
        return f"발주확인이 먼저입니다(발주확인 전 상품주문 {len(pending)}건)."
    return ""


def _is_place_pending(link: ExternalOrderLink) -> bool:
    """이 링크가 발주확인 전인가.

    Args:
        link: 링크 1건.

    Returns:
        우리 표식도 원본 ``placeOrderStatus`` 도 확정을 말하지 않으면 참.
    """
    if _fulfillment_state(link).get("place_confirmed_at"):
        return False
    return (link.place_order_status or "").strip().upper() != "OK"


def _fulfillment_state(link: ExternalOrderLink) -> dict[str, Any]:
    """``triage_state.fulfillment`` 를 dict 로 꺼낸다(없으면 빈 dict).

    Args:
        link: 링크 1건.

    Returns:
        발송처리 표식 dict.
    """
    return ((link.triage_state or {}).get("fulfillment") or {})


def _order_display(session: Session, order_ids: set[int]) -> dict[int, tuple[str, bool]]:
    """대상 주문의 표시용 값을 한 번에 읽는다 (N+1 금지).

    Args:
        session: DB 세션.
        order_ids: 대상 주문 id 전체.

    Returns:
        ``{order_id: (고객명, 실측완료)}``. 입력이 비면 빈 dict(쿼리하지 않는다).
    """
    if not order_ids:
        return {}
    rows = (
        session.query(Order.id, Order.customer_name, Order.measurement_completed)
        .filter(Order.id.in_(sorted(order_ids)))  # perf-ok: 당일 대상 batch
        .all()
    )
    return {int(row[0]): (str(row[1] or ""), bool(row[2])) for row in rows}


def build_day_summary(session: Session, *, on_date: str) -> list[BulkDispatchTarget]:
    """그날 실측 스케줄의 네이버 주문을 집 단위로 **전부** 모은다 — **읽기 전용**.

    :func:`select_targets` 와 달리 **이미 발송된 집도 함께** 돌려준다. 그게 이 함수가
    있는 이유다 — "다 나갔다"와 "애초에 대상이 없었다"는 다른 사실인데, 발송 전만 세면
    둘 다 0집이 되어 화면이 그 둘을 구별해 말할 수 없다.

    보낼 수 없는 집도 :attr:`BulkDispatchTarget.eligible` 거짓으로 **함께 돌려준다**.
    조용히 빼면 화면이 "대상 N집"이라고 말하면서 실제로는 다른 수를 보내게 된다.

    Args:
        session: DB 세션.
        on_date: ``YYYY-MM-DD``.

    Returns:
        집 목록(발송 완료분 포함). 정렬은 대표 링크 id 오름차순(재현 가능하도록).
    """
    order_ids = _measurement_order_ids(session, on_date=on_date)
    day_links = _day_links(session, order_ids)
    if not day_links:
        return []

    day_ids = {row.id for row in day_links}
    groups: dict[tuple[str, str, str], list[ExternalOrderLink]] = {}
    for row in _expand_households(session, day_links):
        groups.setdefault(household_key(row), []).append(row)

    kept: list[tuple[tuple[str, str, str], list[ExternalOrderLink], list[int]]] = []
    for key, links in groups.items():
        mine = [row.id for row in links if row.id in day_ids]
        if not mine:
            # 그날 모집단 링크가 하나도 없는 집은 애초에 우리 대상이 아니다(1차 축이
            # 넓게 걷어온 형제 집). 여기서 안 거르면 남의 집이 목록에 뜬다.
            continue
        links.sort(key=lambda row: row.id)
        kept.append((key, links, sorted(mine)))

    display = _order_display(
        session,
        {row.order_id for _, links, _ in kept for row in links if row.order_id},
    )
    targets = [_build_target(key, links, mine, display) for key, links, mine in kept]
    _mark_repay_superseded(targets)
    targets.sort(key=lambda target: target.link_id)
    logger.info(
        "[NAVER] 일괄 발송처리 %s: 오늘 네이버 집 %d(보낼 수 있음 %d · 이미 나감 %d "
        "· 재결제로 나감 %d)",
        on_date, len(targets),
        sum(1 for t in targets if t.eligible),
        sum(1 for t in targets if t.state == "sent"),
        sum(1 for t in targets if t.state == "superseded"),
    )
    return targets


def _mark_repay_superseded(targets: list[BulkDispatchTarget]) -> None:
    """취소 확정 뒤 **재결제 집으로 이미 나간** 집을 `superseded` 로 바꾼다 (2026-09-02).

    고객이 취소하고 다시 결제하면 같은 ERP 주문에 집이 둘 붙는다. 발송은 재결제 집으로
    나가는데, 옛 집은 보낼 게 남은 채 취소가 걸려 있어 `보낼 수 없음` 빨간 줄로 **매일**
    남는다(운영 #5087 문영미 — 옛 집 ``2026090197104651`` 취소 확정 5건, 재결제 집
    ``2026090230890571`` 이 2026-09-02 발송 완료). 사람이 매일 같은 줄을 다시 판단한다.

    조건 셋을 **모두** 만족할 때만 내린다:

    * 옛 집의 상품주문이 **전부 취소·반품 확정**이고(확정 전은 아직 살아 있을 수 있다),
    * 아직 보낼 게 남아 있고(이미 나간 집은 그냥 ``sent`` 다),
    * **같은 ERP 주문**에 붙은 **다른 집**이 이미 전부 나갔다.

    목록에서 빼지 않는다 — 조용히 빼면 화면이 "대상 N집"이라 말하면서 다른 수를 센다.
    어느 집으로 나갔는지를 함께 싣는 이유도 같다: 사람이 그 사실을 화면에서 확인할 수
    있어야 한다.

    Args:
        targets: 같은 날의 집 전체(제자리에서 고친다).

    Returns:
        None.
    """
    sent_by_order: dict[int, tuple[str, str]] = {}
    for target in targets:
        if target.state != "sent":
            continue
        for order_id in target.order_ids:
            # 여러 집이 나갔으면 **가장 최근에** 나간 집을 말한다.
            prev = sent_by_order.get(order_id)
            if prev is None or (target.sent_at or "") >= prev[1]:
                sent_by_order[order_id] = (target.external_order_no, target.sent_at or "")
    if not sent_by_order:
        return
    for target in targets:
        if target.state == "sent" or not target.all_canceled or not target.pending_link_ids:
            continue
        for order_id in target.order_ids:
            pair = sent_by_order.get(order_id)
            # 자기 자신은 짝이 아니다(같은 주문번호면 같은 집이다).
            if not pair or pair[0] == target.external_order_no:
                continue
            target.state = "superseded"
            target.eligible = False
            target.superseded_by, target.superseded_at = pair
            # 사유 칸은 비운다 — 이제 이 줄은 막힌 줄이 아니라 끝난 줄이다.
            target.reason = ""
            target.failure_reason = ""
            break


def all_money_back_settled(snapshots: list[Any]) -> bool:
    """이 집이 **전부 취소·반품 확정**인가 — 집 단위 클레임 판정의 SSOT.

    판정 축은 :func:`mapping.extract_claim` 이 뽑은 ``phase`` 가
    :data:`mapping.CLAIM_PHASE_DONE` 이고 :func:`mapping.is_money_back_claim` 인 것 —
    돈이 되돌아간 클레임이 **확정**된 상태다. 이웃 모듈
    :data:`ghost_orders.GHOST_CLAIM_PHASES` 는 요청·진행 단계까지 담는데, 그쪽은 "유령
    후보로 볼 것인가"라 안전측으로 넓힌 축이다. 여기서 그 축을 쓰면 거부되면 되살아날
    **확정 전** 클레임 집까지 화면에서 지워 버린다 — 그래서 확정만 본다.

    ``all`` 이다: 형제 상품주문 하나라도 살아 있으면 그 집은 아직 살아 있다(부분 취소).

    Args:
        snapshots: 그 집 링크들의 ``raw_snapshot`` 목록.

    Returns:
        bool: 비어 있지 않고 전부 확정 취소·반품이면 True(``all([])`` 은 참이라 빈 집은
        False 로 답한다 — 근거 없이 "취소된 집"이라 말하지 않는다).
    """
    claims = [mapping.extract_claim(snapshot or {}) for snapshot in snapshots]
    return bool(claims) and all(
        (claim.get("phase") or "") == mapping.CLAIM_PHASE_DONE
        and mapping.is_money_back_claim(claim)
        for claim in claims
    )


def _build_target(key: tuple[str, str, str], links: list[ExternalOrderLink],
                  day_link_ids: list[int],
                  display: dict[int, tuple[str, bool]]) -> BulkDispatchTarget:
    """집 1개의 상태를 조립한다.

    Args:
        key: :func:`fulfillment.household_key` 결과.
        links: 집 전체 링크(id 오름차순).
        day_link_ids: 그중 그날 모집단에 속한 링크 id.
        display: :func:`_order_display` 결과.

    Returns:
        조립된 집 1개.
    """
    by_id = {row.id: row for row in links}
    pending = [lid for lid in day_link_ids if not _is_dispatched(by_id[lid])]
    sent = [lid for lid in day_link_ids if lid not in set(pending)]
    order_ids = sorted({row.order_id for row in links if row.order_id})
    seen = [display[oid] for oid in order_ids if oid in display]

    stamps = [_sent_stamp(by_id[lid]) for lid in sent]
    times = sorted(text for text, _naver in stamps if text)
    # 실패는 **아직 보낼 게 남은 집에만** 말한다. 전부 나간 집의 옛 실패 기록을 빨갛게
    # 띄우면 화면이 "발송됐는데 실패했다"고 말한다 — 판매자센터 수동 발송분이 정확히
    # 그 모양으로 실패 표식을 남긴다(워커가 "이미 발송 기록이 있습니다"로 되돌려보낸다).
    failure = ""
    if pending:
        for lid in day_link_ids:
            failure = _dispatch_failure(by_id[lid])
            if failure:
                break
    reason = _blocking_reason(links) if pending else ""
    # 순서가 뜻이다: **막힘이 실패를 이긴다.** 둘 다인 집에 "실패"라고 쓰면 화면이 다시
    # 보내기를 권하게 되고, 그 재시도는 서버 가드에 그대로 막힌다(발주확인이 먼저다).
    # 이 순서 덕에 ``state == "failed"`` 인 집은 **항상** 보낼 수 있는 집이고, 그래서
    # 줄마다 붙는 재시도 버튼이 언제나 뜻이 있다.
    if not pending:
        state = "sent"
    elif reason:
        state = "blocked"
    elif failure:
        state = "failed"
    else:
        state = "pending"
    # 집 전체가 취소·반품 **확정**인가 — 재결제 짝 판정의 재료(2026-09-02).
    # 확정 전 클레임은 아직 살아 있을 수 있어 여기 넣지 않는다.
    all_canceled = all_money_back_settled([row.raw_snapshot for row in links])
    return BulkDispatchTarget(
        link_id=links[0].id,
        household=key,
        external_order_no=(links[0].external_order_no or "").strip(),
        link_ids=[row.id for row in links],
        pending_link_ids=pending,
        order_ids=order_ids,
        customer_names=[name for name, _done in seen if name],
        # 붙은 주문이 하나도 없으면 '완료'라고 말하지 않는다 — all([]) 은 참이다.
        measurement_done=bool(seen) and all(done for _name, done in seen),
        eligible=bool(pending) and not reason,
        reason=reason,
        sent_link_ids=sent,
        sent_at=times[-1] if times else "",
        sent_by_naver=bool(stamps) and all(is_naver for _text, is_naver in stamps),
        failure_reason=failure,
        state=state,
        all_canceled=all_canceled,
    )


def select_targets(session: Session, *, on_date: str) -> list[BulkDispatchTarget]:
    """그날 **아직 보낼 게 남은** 집만 — :func:`build_day_summary` 위의 얇은 필터.

    술어를 여기서 다시 짜지 않는다. 같은 축의 판정을 두 벌 두면 두 화면이 다른 수를
    말하게 되고, 그게 화면 큐와 워커가 갈렸던 결함의 모양이다.

    Args:
        session: DB 세션.
        on_date: ``YYYY-MM-DD``.

    Returns:
        보낼 게 남은 집 목록(막힌 집도 사유와 함께 **포함**).
    """
    return [target for target in build_day_summary(session, on_date=on_date)
            if target.pending_link_ids]


#: 안 붙은 수집분을 얼마나 뒤로 훑을지(일). 이보다 오래된 미연결분은 오늘 실측 건의
#: 짝일 가능성이 낮고, 훑는 값이 커지면 대시보드 렌더가 그만큼 느려진다.
UNLINKED_WINDOW_DAYS = 60

#: 한 번에 훑을 미연결 수집분 상한. **닿으면 로그로 말한다** — 조용히 자르면 화면이
#: "붙일 게 없다"고 거짓말한다.
UNLINKED_SCAN_CAP = 300


class UnlinkedMatchList(list):
    """짚은 집 목록 + **뺀 집 수**를 함께 나르는 목록.

    목록 계약(``list[dict]``)은 종전 그대로다 — 읽는 쪽을 깨지 않으려고 목록을 물려받는다.
    거기에 ``excluded_claims`` 하나를 얹어, 취소·반품 확정이라 뺀 집이 **몇 집인지 화면이
    말할 수 있게** 한다. 조용히 줄이면 "짚을 게 없다"와 "빼서 없다"가 구분되지 않고,
    그 구분이 안 되는 것이 이 저장소가 이미 밟은 실패 모양이다
    (:data:`UNLINKED_SCAN_CAP` 주석 참고).

    슬라이스·복사하면 이 값은 따라가지 않는다(파이썬 목록 규칙). 세는 쪽은
    :func:`build_preview` 하나뿐이고 받은 자리에서 바로 읽는다.
    """

    #: 취소·반품 확정이라 후보에서 뺀 집 수.
    excluded_claims: int = 0


def _settled_claim_order_nos(session: Session, order_nos: set[str]) -> set[str]:
    """그 주문번호들 중 **집 전체가 취소·반품 확정**인 것만 골라낸다.

    판정 재료는 그 집의 **모든** 링크다 — 매칭에 걸린 링크만 보면 형제가 살아 있는 부분
    취소 집을 통째로 취소된 집으로 오독한다.

    Args:
        session: DB 세션.
        order_nos: 네이버 묶음 주문번호 집합.

    Returns:
        전부 확정 취소·반품인 주문번호 집합.
    """
    if not order_nos:
        return set()
    rows = (
        session.query(ExternalOrderLink.external_order_no,
                      ExternalOrderLink.raw_snapshot)
        .filter(ExternalOrderLink.channel == CHANNEL,
                ExternalOrderLink.external_order_no.in_(sorted(order_nos)))  # perf-ok: 후보 집 수만큼
        .all()
    )
    by_no: dict[str, list[Any]] = {}
    for order_no, snapshot in rows:
        by_no.setdefault(str(order_no or "").strip(), []).append(snapshot)
    return {order_no for order_no, snapshots in by_no.items()
            if all_money_back_settled(snapshots)}


def find_unlinked_matches(session: Session, *, on_date: str) -> UnlinkedMatchList:
    """오늘 실측 주문에 **아직 안 붙은** 네이버 수집분을 전화로 짚어 준다 — 읽기 전용.

    2026-09-01 운영에서 실제로 밟은 자리다: 주문 #5054(천화진)는 오늘 실측인데 발송 대상에
    없었다. 수집은 08-28 에 끝나 있었고(링크 5행) **주문에 붙지 않았을 뿐**이다. 발송 대상
    판정의 유일한 축이 "링크가 그 주문에 붙어 있는가" 라서, 안 붙은 집은 화면 어디에도
    나타나지 않는다 — 사람은 그 집이 빠진 줄도 모른다.

    **자동으로 붙이지 않는다.** 붙이기는 사람이 워크벤치에서 후보를 보고 고르는 일이고
    (:func:`order_candidates.find_order_candidates`), 이 함수는 그 자리로 가라고 말할 뿐이다.

    판정 축은 둘이다:

    1. **전화**(수취인 → 주문자 순).
    2. **네이버 수령인명 == ERP 고객명** — 수집분을 ERP에 입력할 때 고객명을 네이버
       **수령인명**으로 넣는 것이 운영 규칙이다(사용자 확정 2026-09-01). 주문자명은 축이
       아니다: 운영 실데이터에 ``문기범/문유주``·``김유리/김병준`` 처럼 둘이 갈리는 집이
       있고, ERP에 들어간 이름은 **수령인명 쪽**이었다.

    어느 축으로 걸렸는지 ``reason`` 에 적어 함께 돌려준다. 사람이 붙이기 전에 근거를 보고
    판단해야 하기 때문이다 — 이름 축은 동명이인을 만날 수 있다.

    **취소·반품이 확정된 집은 짚지 않는다**(2026-09-02). 축은 전화·이름 둘뿐이라 같은
    고객의 옛 취소 집이 살아 있는 주문의 짝으로 권해졌다 — 붙이면 그 주문은 링크가 전부
    취소가 되어 유령으로 분류되고 **폐기(soft delete) 버튼이 열린다**. 판정은
    :func:`all_money_back_settled` 를 그대로 쓴다(집 요약 ``all_canceled`` 와 같은 축).
    뺀 집은 :attr:`UnlinkedMatchList.excluded_claims` 로 세어 화면이 말한다 — 조용히
    줄이면 사람은 뺀 줄도 모른다.

    Args:
        session: DB 세션.
        on_date: ``YYYY-MM-DD``.

    Returns:
        집 단위 dict 목록(:class:`UnlinkedMatchList`) —
        ``{"order_no", "link_id", "links", "order_id", "customer", "reason"}``.
        짚을 게 없으면 빈 목록. ``excluded_claims`` 에 취소·반품 확정이라 뺀 집 수.
    """
    from datetime import timedelta

    from foms.services.datetime_kst import now_utc_naive
    from foms.services.phone_search import normalize_phone_digits

    # 키 뽑기는 붙이기 후보 화면과 **같은 함수**를 쓴다. 정규화 규칙을 두 벌 두면 한쪽만
    # 고쳐지는 날 두 화면이 다른 집을 짚는다.
    from .order_candidates import _snapshot_keys

    order_ids = _measurement_order_ids(session, on_date=on_date)
    if not order_ids:
        return UnlinkedMatchList()
    linked = {
        row[0] for row in session.query(ExternalOrderLink.order_id)
        .filter(ExternalOrderLink.channel == CHANNEL,
                ExternalOrderLink.order_id.in_(order_ids))  # perf-ok: 당일 실측분 batch
        .distinct().all()
    }
    waiting = [oid for oid in order_ids if oid not in linked]
    if not waiting:
        return UnlinkedMatchList()

    rows = (
        session.query(Order.id, Order.customer_name, Order.erp_phone_digits, Order.phone)
        .filter(Order.id.in_(waiting))  # perf-ok: 당일 실측분 batch
        .all()
    )
    by_digits: dict[str, tuple[int, str]] = {}
    by_name: dict[str, tuple[int, str]] = {}
    for oid, name, erp_digits, phone in rows:
        for value in (erp_digits, normalize_phone_digits(phone)):
            if value:
                by_digits.setdefault(str(value), (int(oid), str(name or "")))
        label = str(name or "").strip()
        if label:
            by_name.setdefault(label, (int(oid), label))
    if not by_digits and not by_name:
        return UnlinkedMatchList()

    since = now_utc_naive() - timedelta(days=UNLINKED_WINDOW_DAYS)
    base = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.channel == CHANNEL,
                ExternalOrderLink.order_id.is_(None),
                ExternalOrderLink.created_at >= since)
    )
    # 축 사본이 있는 행은 **SQL 이 직접 좁힌다**(부분 인덱스). 예전에는 미연결 링크를 최신
    # 300행만 훑었는데, 과거 소급 수집으로 미연결이 1,500행대가 되면 그 300칸을 소급분이
    # 다 차지해 띠가 조용히 잘렸다 — 잘린 자리는 "짚을 게 없다"와 구분되지 않는다.
    digits = [value for value in by_digits if value]
    names = [value for value in by_name if value]
    narrowed = (
        base.filter(or_(
            ExternalOrderLink.recipient_phone_digits.in_(digits) if digits else false(),
            ExternalOrderLink.orderer_phone_digits.in_(digits) if digits else false(),
            ExternalOrderLink.recipient_name.in_(names) if names else false(),
        )).all()  # perf-ok: 오늘 실측 미연결 주문 수만큼의 IN 목록 + 부분 인덱스
        if (digits or names) else []
    )
    # 사본이 없는 옛 행(컬럼이 생기기 전 수집분)은 종전 스캔으로 폴백한다. 채움 스크립트
    # (``tools/ops/backfill_link_match_keys.py``)가 돌고 나면 이 갈래는 비어 간다.
    legacy = (
        base.filter(ExternalOrderLink.recipient_name.is_(None),
                    ExternalOrderLink.recipient_phone_digits.is_(None),
                    ExternalOrderLink.orderer_phone_digits.is_(None))
        .order_by(ExternalOrderLink.id.desc())
        .limit(UNLINKED_SCAN_CAP)
        .all()
    )
    if len(legacy) >= UNLINKED_SCAN_CAP:
        logger.warning("[NAVER] 사본 없는 옛 수집분이 상한 %d행에 닿았다 — 채움 스크립트를 "
                       "돌려야 한다 (%s)", UNLINKED_SCAN_CAP, on_date)
    seen_link_ids: set[int] = set()
    loose = []
    for link in list(narrowed) + list(legacy):
        if int(link.id) in seen_link_ids:
            continue
        seen_link_ids.add(int(link.id))
        loose.append(link)

    found: dict[str, dict[str, Any]] = {}
    for link in loose:
        keys = _snapshot_keys(link.raw_snapshot)
        hit, why = None, ""
        for axis in ("recipient_phone", "orderer_phone"):
            hit = by_digits.get(str(keys.get(axis) or ""))
            if hit:
                why = "전화 일치"
                break
        if not hit:
            # 수령인명 축(운영 규칙). 주문자명은 안 본다 — 둘이 갈리는 집에서 ERP 에
            # 들어간 이름은 수령인명 쪽이었다.
            hit = by_name.get(str(keys.get("name") or "").strip())
            why = "수령인명 일치" if hit else ""
        if not hit:
            continue
        order_no = (link.external_order_no or "").strip()
        row = found.setdefault(order_no, {"order_no": order_no, "link_id": link.id,
                                          "links": 0, "order_id": hit[0],
                                          "customer": hit[1], "reason": why})
        row["links"] += 1
        row["link_id"] = min(row["link_id"], link.id)
        # 한 집 안에서 축이 갈리면 **더 강한 축**을 남긴다(전화가 이름을 이긴다).
        if why == "전화 일치":
            row["reason"] = why
            row["order_id"], row["customer"] = hit[0], hit[1]
    # 취소·반품이 **확정**된 집은 붙일 짝이 아니다 — 붙이면 살아 있는 주문이 유령으로
    # 분류되고 폐기 버튼이 열린다(2026-09-02 운영에서 실제로 권유가 떴다). 판정은
    # :func:`all_money_back_settled` 하나로 한다(집 요약의 ``all_canceled`` 와 같은 축).
    settled = _settled_claim_order_nos(session, set(found))
    out = UnlinkedMatchList(sorted((row for order_no, row in found.items()
                                    if order_no not in settled),
                                   key=lambda row: row["link_id"]))
    out.excluded_claims = len(settled)
    if settled:
        logger.info("[NAVER] %s 안 붙은 수집분 중 취소·반품 확정 %d집은 후보에서 뺐다 (%s)",
                    on_date, len(settled), ", ".join(sorted(settled)))
    if out:
        logger.info("[NAVER] %s 실측분 중 안 붙은 수집분 %d집 — 붙이면 발송 대상이 된다",
                    on_date, len(out))
    return out


#: 수집 커버리지 시작에 두는 안전 여유(일). ERP 접수일은 네이버 주문일보다 **뒤**일 수
#: 있어(며칠 뒤 입력), 접수일이 커버리지 안이어도 원본은 커버리지 밖일 수 있다. 경계
#: 근처는 "네이버 주문이 아니다"로 단정하지 않고 모른다고 말한다.
COVERAGE_MARGIN_DAYS = 14


def coverage_start(session: Session) -> Optional[str]:
    """수집이 실제로 훑은 구간의 시작(``YYYY-MM-DD``) — 모르면 None.

    소급 수집(백필)을 돌렸으면 그 요청 시작이 커버리지 시작이다. 안 돌렸으면 워터마크
    이후만 있으므로 **모른다**고 답한다 — 모름을 아는 척하면 화면이 "네이버 주문이 아니다"를
    틀리게 단정하고, 진짜 네이버 건을 판매자센터로 떠넘기게 된다.

    Args:
        session: DB 세션.

    Returns:
        ``YYYY-MM-DD`` 또는 None.
    """
    from foms.services.integrations.naver_commerce import backfill as bf

    raw = bf.read_window_start(session)
    return raw[:10] or None


def _is_lahom_orderer(sd: Any) -> bool:
    """발주사가 라홈인가 — ``parties.orderer.name`` 에 '라홈' 포함 여부.

    판정 규칙은 브랜드 판정(:func:`foms.services.kakao_alimtalk.resolve_brand`)·도면 로고
    (``drawing_wizard_defaults._resolve_logo``)와 같다. 발주사가 비어 있으면 라홈이 아니다 —
    네이버 수집분은 발주사를 항상 채워서 만든다(:data:`DEFAULT_ORDERER_NAME`).

    Args:
        sd: 주문 ``structured_data``.

    Returns:
        라홈이면 True.
    """
    if not isinstance(sd, dict):
        return False
    parties = sd.get("parties")
    if not isinstance(parties, dict):
        return False
    orderer = parties.get("orderer")
    if not isinstance(orderer, dict):
        return False
    return "라홈" in str(orderer.get("name") or "")


def classify_unsendable(session: Session, *, on_date: str,
                        matched_order_ids: Optional[set[int]] = None) -> dict[str, Any]:
    """그날 실측인데 **여기서는 보낼 수 없는** 주문을 갈래로 나눈다 — 읽기 전용.

    화면은 "네이버 원본이 없는 건"과 "네이버 주문이 아닌 건"을 구별하지 못했다 — 둘 다
    링크가 없을 뿐이다. ``structured_data['source']`` 는 오염분이 있어 축이 못 된다.

    소급 수집을 돌린 뒤에는 **가를 수 있다**: 접수일이 수집이 훑은 구간 안인데 두 축
    (전화·수령인명) 모두 원본에 없으면 이 스토어 네이버 주문이 아니다(운영 실측
    2026-09-01: 오늘 실측 13건 중 링크 없는 11건이 정확히 그랬다 — 이름·전화 모두 0행).
    구간 밖이면 여전히 **모른다**.

    **발주사가 라홈이 아닌 주문은 두 갈래 어디에도 넣지 않는다** — 네이버 스마트스토어가
    라홈 스토어라 이 스토어 주문이 될 수 없다. 여기서 보낼 이유가 없는 건을 세우면 매일
    뜨는 목록이 길어지고, 길어진 목록은 읽히지 않는다.

    Args:
        session: DB 세션.
        on_date: ``YYYY-MM-DD``.
        matched_order_ids: :func:`find_unlinked_matches` 가 이미 짚은 주문 id(제외한다 —
            두 줄이 같은 집을 두고 다른 말을 하면 사람이 어느 쪽을 믿을지 모른다).

    Returns:
        ``{"foreign": [...], "unknown": [...], "coverage_from": "YYYY-MM-DD"|""}``.
        각 행은 ``{"order_id", "customer", "received_date"}``.
    """
    from datetime import date, timedelta

    start = coverage_start(session)
    blank = {"foreign": [], "unknown": [], "coverage_from": start or ""}
    matched = set(matched_order_ids or set())
    order_ids = [oid for oid in _measurement_order_ids(session, on_date=on_date)
                 if oid not in matched]
    if not order_ids:
        return blank
    linked = {
        row[0] for row in session.query(ExternalOrderLink.order_id)
        .filter(ExternalOrderLink.channel == CHANNEL,
                ExternalOrderLink.order_id.in_(order_ids))  # perf-ok: 당일 실측분 batch
        .all() if row[0]
    }
    waiting = [oid for oid in order_ids if oid not in linked]
    if not waiting:
        return blank

    boundary = ""
    if start:
        try:
            boundary = (date.fromisoformat(start)
                        + timedelta(days=COVERAGE_MARGIN_DAYS)).isoformat()
        except ValueError:  # 저장된 값이 깨졌으면 모른다고 답한다(추측 금지)
            logger.warning("[NAVER] 커버리지 시작 파싱 실패(무시): %r", start)
            boundary = ""

    rows = (
        session.query(Order.id, Order.customer_name, Order.received_date,
                      Order.structured_data)
        .filter(Order.id.in_(waiting))  # perf-ok: 당일 실측분 batch
        .all()
    )
    foreign: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
    skipped = 0
    for oid, name, received, sd in rows:
        # 발주사가 라홈이 아니면 애초에 이 스토어 주문일 수 없다 — 네이버 스마트스토어가
        # 라홈 스토어라 수집분 발주사는 항상 라홈이다(:data:`DEFAULT_ORDERER_NAME`).
        # 하우드 등 다른 발주사 건까지 "못 보내는 건"에 세우면, 여기서 보낼 이유가 없는
        # 주문을 매일 읽히는 목록에 올려 진짜 확인할 건을 묻어 버린다.
        if not _is_lahom_orderer(sd):
            skipped += 1
            continue
        row = {"order_id": int(oid), "customer": str(name or ""),
               "received_date": str(received or "")}
        # 접수일이 커버리지(+여유) 안이면 원본이 있어야 한다 — 없으니 네이버 건이 아니다.
        if boundary and row["received_date"] and row["received_date"] >= boundary:
            foreign.append(row)
        else:
            unknown.append(row)
    logger.info("[NAVER] %s 실측분 중 여기서 못 보내는 건 — 네이버 아님 %d · 모름 %d "
                "(발주사 라홈 아님 %d집 제외)",
                on_date, len(foreign), len(unknown), skipped)
    return {"foreign": foreign, "unknown": unknown, "coverage_from": start or ""}


def _row_of(target: BulkDispatchTarget) -> dict[str, Any]:
    """집 1개를 템플릿이 읽는 평평한 dict 로 편다.

    Args:
        target: 집 1개.

    Returns:
        렌더 값 dict.
    """
    return {
        "link_id": target.link_id,
        "order_no": target.external_order_no,
        "order_ids": target.order_ids,
        "customer": " · ".join(target.customer_names) or "(주문 미생성)",
        "product_orders": len(target.pending_link_ids),
        "sent_orders": len(target.sent_link_ids),
        "measurement_done": target.measurement_done,
        "eligible": target.eligible,
        "reason": target.reason,
        "state": target.state,
        "sent_at": target.sent_at,
        "sent_by_naver": target.sent_by_naver,
        "failure_reason": target.failure_reason,
        "superseded_by": target.superseded_by,
        "superseded_at": target.superseded_at,
    }


def build_preview(session: Session, *, on_date: str) -> dict[str, Any]:
    """띠가 그대로 렌더할 값 — **화면 두 곳이 이 함수 하나를 쓴다**.

    워크벤치와 실측 대시보드가 각자 조립하면 두 화면이 다른 수를 말한다. 네이버 집 수가
    45집 vs 43집으로 갈렸던 것이 정확히 그 결함이었다.

    **기존 키 넷(``count``·``eligible``·``blocked``·``rows``)의 뜻은 바뀌지 않는다** —
    지금도 앞으로도 "지금 보낼 대상"이다. 결과 표시는 새 키로만 온다. 뜻을 조용히 바꾸면
    이 값을 읽는 두 화면이 각각 다르게 틀린다.

    조회 실패는 여기서 삼키고 빈 값을 준다(**failopen — 로그로 남긴다**). 이 띠는 보조
    정보라 화면 전체를 죽일 이유가 없다. 반대로 대상을 **줄여서** 보여주는 일은 없다 —
    실패하면 0집이 되고 띠 자체가 안 뜬다.

    Args:
        session: DB 세션.
        on_date: ``YYYY-MM-DD``.

    Returns:
        ``{"date", "count", "eligible", "blocked", "rows", "day_total", "sent",
        "failed", "last_sent_at", "state", "day_rows", "show", "unlinked_excluded"}``.

        * ``count``/``rows``: **보낼 게 남은** 집(막힌 집 포함 · 재결제 집으로 이미
          나간 집은 제외).
        * ``superseded``: 취소 확정 뒤 재결제 집으로 나간 집 수.
        * ``day_total``/``day_rows``: 오늘 네이버 집 **전체**(이미 나간 집 포함).
        * ``state``: ``"none"``(오늘 대상 자체가 없음 — 띠를 띄우지 않는다) ·
          ``"done"``(전부 나감) · ``"partial"``(일부 나감) · ``"pending"``(아직 안 나감).
        * ``unlinked_excluded``: 취소·반품 확정이라 "붙이면 대상" 후보에서 뺀 집 수.
          **0집이어도 실린다** — 화면이 "짚을 게 없다"와 "빼서 없다"를 갈라 말해야 한다.
        * ``show``: 띠를 띄울지. **"다 나갔다"와 "대상이 없었다"를 가르는 값이다.**
          뺀 집만 있는 날에도 띄운다 — 뺐다는 사실을 말할 자리가 이 띠뿐이다.
    """
    empty: dict[str, Any] = {"date": on_date, "count": 0, "eligible": 0, "blocked": 0,
                             "rows": [], "day_total": 0, "sent": 0, "failed": 0,
                             "last_sent_at": "", "last_sent_time": "", "state": "none",
                             "superseded": 0,
                             "day_rows": [], "show": False, "unlinked": 0,
                             "unlinked_rows": [], "unlinked_excluded": 0,
                             "foreign": [], "unknown": [],
                             "coverage_from": ""}
    try:
        targets = build_day_summary(session, on_date=on_date)
        # 안 붙은 수집분은 **대상이 0인 날에도** 말해야 한다 — 오늘 네이버 집이 하나도
        # 안 잡히는 이유가 바로 그것일 수 있다(2026-09-01 천화진 건이 그랬다).
        unlinked = find_unlinked_matches(session, on_date=on_date)
        # 붙일 짝조차 없는 건은 **왜 없는지**를 말해야 한다. 침묵하면 사람은 빠진 줄도
        # 모르고, "붙이면 된다"로 오해하면 없는 수집분을 찾아 헤맨다.
        unsendable = classify_unsendable(
            session, on_date=on_date,
            matched_order_ids={int(row["order_id"]) for row in unlinked},
        )
    except SQLAlchemyError as exc:  # 보조 정보라 화면을 막지 않는다(failopen — 로그로 남긴다)
        logger.warning("[NAVER] 발송 대상 미리보기 조회 실패(띠 생략): %s", exc, exc_info=True)
        return empty
    # 뺀 집 수는 **줄이 0집이어도** 실어 보낸다 — 화면이 "짚을 게 없다"와 "취소 확정이라
    # 뺐다"를 구분해 말할 수 있어야 한다.
    excluded = int(getattr(unlinked, "excluded_claims", 0))
    extra = {"foreign": unsendable["foreign"], "unknown": unsendable["unknown"],
             "coverage_from": unsendable["coverage_from"],
             "unlinked_excluded": excluded}
    # 띄우는 조건은 **종전 그대로**다(대상이 있거나, 붙일 짝이 있을 때). "못 보내는 건"은
    # 곁들이는 정보라, 그것만으로 띠를 띄우면 네이버와 무관한 날에도 화면이 떠든다 —
    # 매일 뜨는 안내는 읽히지 않고, 읽히지 않는 안내는 없는 것과 같다.
    if not targets:
        if unlinked or excluded:
            return {**empty, **extra, "show": True, "unlinked": len(unlinked),
                    "unlinked_rows": list(unlinked)}
        # 값은 싣되 띄우지 않는다 — 값이 비면 읽는 쪽이 "센 적 없다"와 "0건"을 못 가른다.
        return {**empty, **extra}

    day_rows = [_row_of(target) for target in targets]
    # `superseded` 도 뺀다 — 재결제 집으로 이미 나간 집이라 오늘 보낼 대상이 아니다.
    # 여기 남기면 "보낼 대상 N집"이 매일 그 집을 세고, 띠 상태가 영영 `partial` 이다.
    rows = [row for row in day_rows if row["state"] not in ("sent", "superseded")]
    eligible = sum(1 for row in rows if row["eligible"])
    sent_times = sorted(row["sent_at"] for row in day_rows if row["sent_at"])
    sent = sum(1 for row in day_rows if row["state"] == "sent")
    superseded = sum(1 for row in day_rows if row["state"] == "superseded")
    if not rows:
        state = "done"
    elif sent or superseded:
        state = "partial"
    else:
        state = "pending"
    last_sent_at = sent_times[-1] if sent_times else ""
    return {"date": on_date, "count": len(rows), "eligible": eligible,
            "blocked": len(rows) - eligible, "rows": rows,
            "day_total": len(day_rows), "sent": sent, "superseded": superseded,
            "failed": sum(1 for row in day_rows if row["state"] == "failed"),
            "last_sent_at": last_sent_at,
            # 머리말은 "오늘"을 말하고 있으니 시:분만 쓴다. 날짜를 붙여 자르는 일을
            # 템플릿에 시키면 두 화면이 각자 자르다 한쪽이 어긋난다.
            "last_sent_time": last_sent_at[11:] if len(last_sent_at) >= 16 else "",
            "state": state, "day_rows": day_rows, "show": True,
            "unlinked": len(unlinked), "unlinked_rows": list(unlinked), **extra}


def select_sendable(session: Session, *, on_date: str,
                    limit: Optional[int] = None) -> tuple[list[BulkDispatchTarget], int]:
    """지금 **보낼 수 있는** 집만 상한까지 골라 준다 — 실행 경로 전용.

    화면이 보낸 목록을 믿지 않고 서버가 **다시 계산**한다. 되돌릴 수 없는 조작의 대상을
    화면이 정하게 두면, 화면이 낡았거나 조작됐을 때 그대로 네이버로 나간다.

    Args:
        session: DB 세션.
        on_date: ``YYYY-MM-DD``.
        limit: 상한. ``None`` 이면 :data:`BULK_DISPATCH_LIMIT` 를 **호출 시점에** 읽는다
            (기본 인자로 묶으면 def 시점에 값이 굳어 상한을 바꿔도 안 먹는다).

    Returns:
        ``(보낼 집 목록, 상한 전 전체 수)``. 두 번째 값이 목록보다 크면 잘린 것이다 —
        부르는 쪽이 그 사실을 사람에게 **반드시** 말해야 한다.
    """
    limit = BULK_DISPATCH_LIMIT if limit is None else limit
    sendable = [target for target in select_targets(session, on_date=on_date)
                if target.eligible]
    total = len(sendable)
    if total > limit:
        logger.warning("[NAVER] 일괄 발송처리 대상 %d집이 상한 %d집을 넘어 잘렸다 (%s)",
                       total, limit, on_date)
    return sendable[:limit], total
