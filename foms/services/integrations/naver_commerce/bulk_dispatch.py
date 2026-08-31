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

from sqlalchemy import and_, func
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
    "BulkDispatchTarget",
    "build_preview",
    "dispatch_pending_clause",
    "select_targets",
]

#: 실측 일정의 ``OrderScheduleDate.kind``. 실측 대시보드가 쓰는 값과 같아야 한다
#: (`foms/web/measurement/dashboard.py` 의 당일 술어).
MEASUREMENT_KIND = "measurement"

#: 완료 주문 컷오프(일). 실측 대시보드 `Order.dashboard_active_filter(days=60)` 와 맞춘다.
ACTIVE_WINDOW_DAYS = 60


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


def _candidate_links(session: Session, order_ids: list[int]) -> list[ExternalOrderLink]:
    """모집단 주문에 붙은 **발송 전** 네이버 링크.

    ``order_id`` 로 거르는 것이 "네이버 유래" 판정의 전부다 —
    ``structured_data['source']`` 는 쓰지 않는다(2026-08-28 운영 실측에서 오염 의심분이
    남았고 소급 구별이 불가능하다).

    Args:
        session: DB 세션.
        order_ids: 모집단 주문 id.

    Returns:
        후보 링크 목록. 입력이 비면 빈 목록(쿼리하지 않는다).
    """
    if not order_ids:
        return []
    return (
        session.query(ExternalOrderLink)
        .filter(
            ExternalOrderLink.channel == CHANNEL,
            ExternalOrderLink.order_id.in_(order_ids),  # perf-ok: 당일 실측분 batch
            dispatch_pending_clause(),
        )
        .order_by(ExternalOrderLink.id.asc())
        .all()
    )


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


def select_targets(session: Session, *, on_date: str) -> list[BulkDispatchTarget]:
    """그날 실측 스케줄의 네이버 주문을 집 단위로 모은다 — **읽기 전용**.

    보낼 수 없는 집도 :attr:`BulkDispatchTarget.eligible` 거짓으로 **함께 돌려준다**.
    조용히 빼면 화면이 "대상 N집"이라고 말하면서 실제로는 다른 수를 보내게 된다.

    Args:
        session: DB 세션.
        on_date: ``YYYY-MM-DD``.

    Returns:
        집 목록. 정렬은 대표 링크 id 오름차순(재현 가능하도록).
    """
    order_ids = _measurement_order_ids(session, on_date=on_date)
    candidates = _candidate_links(session, order_ids)
    if not candidates:
        return []

    candidate_ids = {row.id for row in candidates}
    groups: dict[tuple[str, str, str], list[ExternalOrderLink]] = {}
    for row in _expand_households(session, candidates):
        groups.setdefault(household_key(row), []).append(row)

    kept: list[tuple[tuple[str, str, str], list[ExternalOrderLink], list[int]]] = []
    for key, links in groups.items():
        pending = [row.id for row in links if row.id in candidate_ids]
        if not pending:
            # 후보가 하나도 없는 집은 애초에 우리 모집단이 아니다(1차 축이 넓게 걷어온
            # 형제 집). 여기서 안 거르면 남의 집이 대상 목록에 뜬다.
            continue
        links.sort(key=lambda row: row.id)
        kept.append((key, links, sorted(pending)))

    display = _order_display(
        session,
        {row.order_id for _, links, _ in kept for row in links if row.order_id},
    )
    targets: list[BulkDispatchTarget] = []
    for key, links, pending in kept:
        order_ids = sorted({row.order_id for row in links if row.order_id})
        seen = [display[oid] for oid in order_ids if oid in display]
        reason = _blocking_reason(links)
        targets.append(
            BulkDispatchTarget(
                link_id=links[0].id,
                household=key,
                external_order_no=(links[0].external_order_no or "").strip(),
                link_ids=[row.id for row in links],
                pending_link_ids=pending,
                order_ids=order_ids,
                customer_names=[name for name, _done in seen if name],
                # 붙은 주문이 하나도 없으면 '완료'라고 말하지 않는다 — all([]) 은 참이다.
                measurement_done=bool(seen) and all(done for _name, done in seen),
                eligible=not reason,
                reason=reason,
            )
        )
    targets.sort(key=lambda target: target.link_id)
    logger.info(
        "[NAVER] 일괄 발송처리 대상 %s: 집 %d(보낼 수 있음 %d)",
        on_date, len(targets), sum(1 for t in targets if t.eligible),
    )
    return targets


def build_preview(session: Session, *, on_date: str) -> dict[str, Any]:
    """미리보기 띠가 그대로 렌더할 값 — **화면 두 곳이 이 함수 하나를 쓴다**.

    워크벤치와 실측 대시보드가 각자 조립하면 두 화면이 다른 수를 말한다. 네이버 집 수가
    45집 vs 43집으로 갈렸던 것이 정확히 그 결함이었다.

    조회 실패는 여기서 삼키고 빈 값을 준다(**failopen — 로그로 남긴다**). 이 띠는 보조
    정보라 화면 전체를 죽일 이유가 없다. 반대로 대상을 **줄여서** 보여주는 일은 없다 —
    실패하면 0집이 되고 띠 자체가 안 뜬다.

    Args:
        session: DB 세션.
        on_date: ``YYYY-MM-DD``.

    Returns:
        ``{"date", "count", "eligible", "blocked", "rows"}``. ``rows`` 는 템플릿이 읽는
        평평한 dict 목록.
    """
    empty: dict[str, Any] = {"date": on_date, "count": 0, "eligible": 0,
                             "blocked": 0, "rows": []}
    try:
        targets = select_targets(session, on_date=on_date)
    except SQLAlchemyError as exc:  # 보조 정보라 화면을 막지 않는다(failopen — 로그로 남긴다)
        logger.warning("[NAVER] 발송 대상 미리보기 조회 실패(띠 생략): %s", exc, exc_info=True)
        return empty
    rows = [
        {
            "link_id": target.link_id,
            "order_no": target.external_order_no,
            "order_ids": target.order_ids,
            "customer": " · ".join(target.customer_names) or "(주문 미생성)",
            "product_orders": len(target.pending_link_ids),
            "measurement_done": target.measurement_done,
            "eligible": target.eligible,
            "reason": target.reason,
        }
        for target in targets
    ]
    eligible = sum(1 for row in rows if row["eligible"])
    return {"date": on_date, "count": len(rows), "eligible": eligible,
            "blocked": len(rows) - eligible, "rows": rows}
