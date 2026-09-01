"""수집 이후에 생긴 취소·반품을 따라간다 (NAVER-INGEST-01 T14-F).

수집은 ``productOrderStatus == PAYED`` 인 순간의 상태만 본다. 고객이 **주문을 받은 뒤에**
취소하면 FOMS 는 영영 모르고, 취소된 집으로 생산·시공이 나갈 수 있었다.

**추가 API 호출을 최소로 한다**: 5분 스윕이 이미 받아오는 변경 목록(``last-changed-statuses``)
에 이미 수집한 상품주문이 뜬 경우에만 그 건의 상세를 다시 부른다. 변경이 없으면 호출 0회다.
변경 목록의 상태 문자열로 바로 판정하지 않는 이유: 취소가 그 목록에 어떤 이름으로 실리는지
실물로 확인되지 않았다. 취소 여부의 정본은 **상세 응답의 ``claimStatus``** 다(실측 확인).

발견 시 동작은 **표시 + 알림**까지다(2026-08-15 사용자 확정). 주문 상태를 자동으로
바꾸지 않는다 — 이미 잡힌 일정·도면이 있으면 자동 변경이 더 큰 혼란을 만든다.

알림 수신자는 **담당자 + 관리자 양쪽**이다(2026-08-26 사용자 확정). 취소는 환불·재고·이미
나간 생산 지시가 얽혀 담당자 혼자 처리하고 끝나는 사건이 아니다. 담당자가 없으면 관리자만
받는다(예전 폴백과 동일).
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.grouping import resolve_group_key
from foms.services.integrations.naver_commerce.mapping import (
    claim_kind,
    claim_reason_text,
    extract_claim,
    extract_claim_holdback,
    extract_external_id,
    extract_place_status,
    group_key_text,
    unwrap_detail,
)
from models import (
    ExternalOrderLink,
    Notification,
    Order,
    OrderAssignment,
    SecurityLog,
    User,
)

logger = logging.getLogger(__name__)

#: 알림 타입. push 를 받으려면 ``push_sender._DEFAULT_P1_TYPES`` 에도 등재돼 있어야 한다
#: (미등재면 enqueue 해도 조용히 no-op — 무음 알림의 유일한 기전).
NOTIFICATION_TYPE = "NAVER_ORDER_CLAIMED"

#: ``triage_state`` 안에서 이 기능이 쓰는 키. 도크 체크(checked·assigned_main)와 다른 축이다.
STATE_KEY = "claim_sync"


def changed_external_ids(entries: list[dict]) -> list[str]:
    """변경 이벤트 목록에서 상품주문번호를 중복 없이 뽑는다(상태 불문).

    수집 후보(:func:`mapping.is_collectible`)와 달리 **상태로 거르지 않는다** — 취소·반품도
    변경 이벤트로 오기 때문이다.

    Args:
        entries: ``last-changed-statuses`` 항목 목록.

    Returns:
        상품주문번호 목록(입력 순서 보존).
    """
    out: list[str] = []
    seen: set[str] = set()
    for entry in entries or []:
        external_id = str((entry or {}).get("productOrderId") or "").strip()
        if external_id and external_id not in seen:
            seen.add(external_id)
            out.append(external_id)
    return out


def _notify_targets(session: Session, link: ExternalOrderLink) -> tuple[list[int], list[int]]:
    """알림 받을 **담당자**와 **관리자**를 따로 준다.

    2026-08-26 사용자 확정: 취소는 담당자만 알아서 되는 사건이 아니다(환불·재고·이미 나간
    생산 지시가 걸린다). 담당자가 있어도 관리자에게 함께 올리고, 담당자가 없으면 관리자만
    받는다. 두 목록을 나눠 주는 이유는 알림 row 종류가 다르기 때문이다 — 담당자는
    ``USER`` 알림, 관리자는 ``ROLE`` 알림 **1건**(NOTIF-ROLE-01, 관리자 수만큼 복제 금지).

    보류함 계정(:data:`constants.OWNER_USERNAME`)이 owner 면 사람이 아니므로 담당자가
    없는 것으로 친다.

    Args:
        session: DB 세션.
        link: 클레임이 감지된 외부 주문 링크.

    Returns:
        ``(holder_ids, admin_ids)`` — 활성 담당자 id 목록과 활성 ADMIN id 목록.
        둘 다 비면 알림 대상이 없다는 뜻이다.
    """
    holder_ids: list[int] = []
    if link.order_id:
        rows = (
            session.query(OrderAssignment)
            .filter(
                OrderAssignment.order_id == int(link.order_id),
                OrderAssignment.domain == "SALES",
                OrderAssignment.active.is_(True),
            )
            .all()
        )
        assigned_ids = [int(row.user_id) for row in rows]
        if assigned_ids:
            holders = (
                session.query(User)
                .filter(User.id.in_(assigned_ids), User.is_active.is_(True))
                .all()
            )
            # 미배정 보류함 계정이 owner 면 사람이 아니다 — 담당자 없음으로 친다.
            from foms.services.integrations.naver_commerce.constants import OWNER_USERNAME

            holder_ids = [int(u.id) for u in holders if u.username != OWNER_USERNAME]
    admins = (
        session.query(User)
        .filter(User.role == "ADMIN", User.is_active.is_(True))
        .all()
    )
    admin_ids = [int(u.id) for u in admins]
    # 담당자가 관리자이기도 하면 ROLE 알림으로 이미 받는다 — 같은 사건을 두 번 주지 않는다.
    admin_set = set(admin_ids)
    holder_ids = [uid for uid in holder_ids if uid not in admin_set]
    return holder_ids, admin_ids


#: 알림 본문에 싣는 상품명 최대 길이. 네이버 상품명은 길다("라홈 무몰딩 붙박이장 로라
#: 시리즈 30cm 푸쉬타입 친환경 E0" — 실물 41자). 통째로 실으면 어느 집인지가 이름에 묻힌다.
_PRODUCT_NAME_MAX = 24


def _snapshot_customer(link: ExternalOrderLink) -> str:
    """원본 스냅샷에서 사람 이름을 꺼낸다(수취인 우선, 없으면 주문자).

    주문으로 만들기 전 수집분은 FOMS 쪽에 이름이 없어 알림이 번호만 남는다.
    :func:`mapping.build_order_kwargs` 와 같은 우선순위를 쓴다(수취인 = 시공 받는 사람).

    Args:
        link: 클레임이 감지된 링크.

    Returns:
        이름(없으면 빈 문자열).
    """
    _order, _po, shipping = unwrap_detail(link.raw_snapshot or {})
    order_part = (link.raw_snapshot or {}).get("order") or {}
    return (str(shipping.get("name") or "").strip()
            or str(order_part.get("ordererName") or "").strip())


def _snapshot_product(link: ExternalOrderLink) -> str:
    """원본 스냅샷의 상품명을 알림용으로 줄인다(없으면 빈 문자열)."""
    _order, product_order, _shipping = unwrap_detail(link.raw_snapshot or {})
    name = str(product_order.get("productName") or "").strip()
    if len(name) > _PRODUCT_NAME_MAX:
        return name[:_PRODUCT_NAME_MAX] + "…"
    return name


def _compose(session: Session, links: list[ExternalOrderLink],
             claim: dict) -> tuple[str, str]:
    """클레임 알림의 제목·본문을 만든다 — 단위는 **집(주문) 1건**이다.

    한 집이 세부옵션(상품주문번호) 여러 건으로 쪼개져 오므로, 링크마다 문안을 만들면
    같은 취소가 알림 4건이 된다(2026-08-25 운영 실사례: 상품주문번호 …391/401/411/421).
    번호는 대표 1개 + "외 N건"으로 적어 사람이 집 하나로 읽게 한다.

    Args:
        session: DB 세션(고객명 조회에만 쓴다).
        links: 같은 집에서 같은 상태로 바뀐 링크들(최소 1건, 입력 순서 보존).
        claim: :func:`mapping.extract_claim` 결과(``label``·``reason`` 사용).

    Returns:
        ``(title, message)`` — title 은 200자로 잘라 둔 상태다.
    """
    head = links[0]
    order_id = next((int(row.order_id) for row in links if row.order_id), None)
    order = session.get(Order, order_id) if order_id else None
    who = getattr(order, "customer_name", None) or _snapshot_customer(head)
    title = f"네이버 {claim['label']} — {who}".strip(" —")
    reason = claim_reason_text(claim["reason"])
    detail = f" · 사유 {reason}" if reason else ""
    where = (f"FOMS 주문 #{order_id}" if order_id
             else "아직 주문으로 만들지 않은 수집분")
    extra = f" 외 {len(links) - 1}건" if len(links) > 1 else ""
    parts = [where]
    # 주문으로 만들기 전 건은 FOMS 안에 이름이 없다 — 원본에서 꺼내 적어야 사람이 찾는다.
    if not order_id and who:
        parts.append(who)
    product = _snapshot_product(head)
    if product:
        parts.append(product)
    parts.append(f"상품주문번호 {head.external_id}{extra}")
    message = (
        f"네이버에서 {claim['label']} 상태로 바뀐 주문이 있습니다{detail}. "
        f"({' · '.join(parts)}) "
        "일정·생산이 잡혀 있으면 진행을 멈추고 네이버 판매자센터에서 확인하세요."
    )
    return title[:200], message


#: 클레임 종류 → **우리가 냈다는 표식**이 남는 자리 ``(버킷, 키)``.
#:
#: 두 자리가 다른 것이 R-3 의 원인이었다. 취소는 ``fulfillment.cancel_order`` 가
#: ``triage_state['fulfillment']['canceled_at']`` 에, 반품은 ``fulfillment.request_return``
#: 이 ``triage_state['return']['requested_at']`` 에 남긴다. 억제 판정이 앞쪽만 읽어서
#: **반품 접수만 경보가 되어 돌아왔다**(2026-08-28).
#:
#: 교환은 우리가 내보내는 경로가 없어서 표식도 없다 — 생기면 여기 한 줄이다.
OUR_CLAIM_MARKERS = {
    "CANCEL": ("fulfillment", "canceled_at"),
    "RETURN": ("return", "requested_at"),
}


def _is_our_claim(link: ExternalOrderLink, claim: dict) -> bool:
    """이 클레임을 **우리가** 냈는가 (판매자 직접 접수 표식).

    표식은 :mod:`fulfillment` 이 집 전체에 남긴다(자리는 :data:`OUR_CLAIM_MARKERS`).
    이 모듈의 상태 키(:data:`STATE_KEY` = ``claim_sync``)와 **다른 축**이라 서로
    덮어쓰지 않는다.

    **종류가 맞을 때만 참이다.** 표식 하나가 모든 클레임을 덮으면, 반품을 한 번 접수한
    링크는 그 뒤 진짜 고객 취소가 나도 영영 조용해진다 — 억제가 사고를 삼키는 쪽으로
    틀리는 것이 이 함수의 유일한 위험이다. 종류를 모르면(빈 문자열) 억제하지 않는다.

    Args:
        link: 클레임이 감지된 링크.
        claim: :func:`mapping.extract_claim` 결과(종류 판정에 쓴다).

    Returns:
        bool: 같은 종류의 우리 표식이 있으면 True.
    """
    marker = OUR_CLAIM_MARKERS.get(claim_kind(claim))
    if not marker:
        return False
    bucket_name, key = marker
    state = link.triage_state if isinstance(link.triage_state, dict) else {}
    bucket = state.get(bucket_name)
    if not isinstance(bucket, dict):
        return False
    return bool(bucket.get(key))


def _pending_groups(
    session: Session, pending: list[tuple[ExternalOrderLink, dict]],
) -> list[tuple[list[ExternalOrderLink], dict, list[int], list[int]]]:
    """알림 대기 링크를 **집 + 상태 + 수신자** 로 묶는다.

    집(:func:`grouping.resolve_group_key`)만으로 묶지 않는 이유: 같은 집이라도 링크가
    서로 다른 FOMS 주문에 붙어 담당자가 갈릴 수 있다(취소 후 재결제로 집이 주문 2건이
    되는 경로). 수신자가 다르면 문안의 "FOMS 주문 #" 도 달라야 하므로 따로 보낸다.
    상태를 키에 넣는 이유: 한 스윕에서 같은 집이 취소 요청과 취소 완료로 갈릴 수 있고,
    두 사건을 한 문장으로 합치면 어느 쪽이 사실인지 알 수 없어진다.

    Args:
        session: DB 세션(담당자 조회).
        pending: ``(link, claim)`` 목록 — 알림이 필요하다고 판정된 것만.

    Returns:
        ``(links, claim, holders, admins)`` 목록. 담당자도 관리자도 없는 링크는 빠진다
        (호출자가 ``notified_status`` 를 안 남겨 다음 스윕에서 다시 시도한다).
    """
    groups: dict[tuple, tuple[list[ExternalOrderLink], dict, list[int], list[int]]] = {}
    for link, claim in pending:
        holders, admins = _notify_targets(session, link)
        if not holders and not admins:
            logger.warning("[NAVER] 클레임 알림 대상이 없다 link=%s", link.id)
            continue
        key = (resolve_group_key(link), claim["status"], tuple(sorted(holders)))
        found = groups.get(key)
        if found is None:
            groups[key] = ([link], claim, list(holders), list(admins))
        else:
            found[0].append(link)
    return list(groups.values())


def _notify(session: Session, links: list[ExternalOrderLink], claim: dict,
            holders: list[int], admins: list[int], *, now: datetime) -> int:
    """취소·반품 발생을 **담당자와 관리자 양쪽**에 알린다.

    담당자에게는 ``target_type='USER'`` 알림을, 관리자에게는 ``target_type='ROLE'`` +
    ``target_role='ADMIN'`` 알림을 **1건만** 만든다 — 관리자 수만큼 Notification 을
    복제하지 않는다(NOTIF-ROLE-01). 담당자가 없으면 ROLE 알림만 남아 예전 폴백 동작과
    같아진다. 수신자별 읽음 상태는 :func:`recipients.fan_out_new_notification` 이
    ``notification_user_states`` 로 만든다. 여기서 "사건 1건"은 **집 1건**이다 —
    세부옵션 수만큼 알림을 만들지 않는다.

    Args:
        session: DB 세션(커밋은 호출자).
        links: 같은 집·같은 상태·같은 담당자인 링크들(:func:`_pending_groups` 산출).
        claim: :func:`mapping.extract_claim` 결과.
        holders: 담당자 사용자 id 목록(관리자와 겹치는 id 는 이미 빠져 있다).
        admins: 활성 ADMIN 사용자 id 목록.
        now: 알림 생성 시각.

    Returns:
        알림이 도달하는 **수신자 수**(대상이 없으면 0). Notification row 수가 아니다 —
        ROLE 알림은 row 1건으로 관리자 전원에게 간다. 호출부 카운터(``notified``)와
        중복 억제(``notified_status``)가 이 값의 "사람 수" 의미에 의존한다.
    """
    from foms.services.notifications.recipients import fan_out_new_notification

    if not holders and not admins:
        return 0

    title, message = _compose(session, links, claim)
    order_id = next((int(row.order_id) for row in links if row.order_id), None)
    common = dict(order_id=order_id, notification_type=NOTIFICATION_TYPE,
                  is_urgent=True, title=title, message=message, created_at=now)
    rows = [Notification(target_type="USER", target_user_id=uid, **common)
            for uid in holders]
    if admins:
        rows.append(Notification(target_type="ROLE", target_role="ADMIN", **common))
    for notification in rows:
        session.add(notification)
        session.flush()
        fan_out_new_notification(session, notification)
    return len(holders) + len(admins)


#: 이력 최대 보관 건수. 5분 스윕이 같은 링크를 계속 다시 읽으므로 상한이 없으면
#: ``triage_state``(JSONB) 한 칸이 끝없이 커지고, 스냅샷을 갱신할 때마다 그 큰 값을
#: 통째로 다시 써야 한다. 클레임 하나가 지나가는 상태는 요청 → 수거중 → 수거완료 →
#: 완료 정도라 20건이면 취소 후 재결제 왕복까지 담고도 남는다.
_HISTORY_MAX = 20


def _append_history(sync: dict, claim: dict, detail: dict, *, stamp: datetime) -> None:
    """클레임 **상태가 바뀐 순간에만** 이력을 1건 덧붙인다(``sync`` 를 제자리 수정).

    지금까지 남는 것은 ``last_status`` **하나**(최신값)뿐이고 ``raw_snapshot`` 은 스윕마다
    통째로 덮어써졌다. 그래서 클레임이 ``RETURN_REQUEST`` → 수거중 → 수거완료 를 지나가면
    **지나간 상태와 그때의 값이 사라진다.** 스테이징에 진짜 반품이 0건이라 실물 1건이
    유일한 관측 기회인데, 그 1건이 와도 증거가 안 남는 상태였다.

    ``last_status`` 는 건드리지 않는다 — 호출자의 ``notified_status`` 중복 억제가 그 값에
    의존해서, 손대면 알림이 두 번 나간다.

    Args:
        sync: ``triage_state[STATE_KEY]`` 사본(이 함수가 ``history`` 키만 바꾼다).
        claim: :func:`mapping.extract_claim` 결과(``status``·``reason`` 사용).
        detail: 네이버 상세 응답 1건(보류·배송비 귀책을 여기서 훑는다).
        stamp: 이번 스윕 시각.

    Returns:
        None — ``sync['history']`` 를 제자리에서 갱신한다.
    """
    history = [row for row in (sync.get("history") or []) if isinstance(row, dict)]
    status = claim["status"]
    if not history and not status:
        # 클레임이 없던 건의 첫 스윕까지 남기면 링크 전부가 빈 항목을 하나씩 갖는다 —
        # 지나간 상태가 없으니 증거도 아니다. 클레임이 붙은 뒤 다시 빈 값이 되는 것
        # (철회)은 진짜 전이라 그때는 남긴다.
        return
    holdback = extract_claim_holdback(detail)
    # **중복 억제 키에 보류·귀책을 함께 넣는다.** `status` 하나로 막으면
    # `claimStatus` 가 `RETURN_REQUEST` 에 머문 채 `holdbackStatus` 만
    # `None` → `HOLDBACK_REQUEST` → `HOLDBACK_RELEASE` 로 가는 전이가 통째로 버려진다.
    # 그런데 그 축이 바로 이 함수가 존재하는 **유일한 이유**다(승인 분기의 입력).
    # 5분 스윕이 같은 모양을 계속 다시 보는 것은 이 키로도 그대로 막힌다.
    fingerprint = (status, holdback["holdback_status"], holdback["fee_pay_method"])
    if history:
        last = history[-1]
        if (last.get("status"), last.get("holdback_status"),
                last.get("fee_pay_method")) == fingerprint:
            return
    row = {
        "at": stamp.isoformat(),
        "status": status,
        "reason": claim["reason"],
        "holdback_status": holdback["holdback_status"],
        "holdback_block": holdback["holdback_block"],
        "fee_pay_method": holdback["fee_pay_method"],
        "fee_block": holdback["fee_block"],
    }
    if not history and sync.get("last_status") is not None:
        # 이 기능이 배포되기 **전부터** 진행 중이던 클레임이다. 첫 행의 `at` 은 전이
        # 시각이 아니라 배포 후 첫 스윕 시각이라, 표식을 안 남기면 나중에 "이 반품이
        # 언제 요청됐나"에 틀린 날짜로 답한다.
        row["backfilled"] = True
    history.append(row)
    if len(history) > _HISTORY_MAX:
        # 캡을 넘으면 오래된 쪽을 버리되 **첫 행 1건은 고정 보존**한다. 첫 행이 그
        # 클레임이 처음 관측된 시점이라, 그것까지 버리면 "증거를 남긴다"는 목적과
        # 방향이 반대가 된다(상태가 진동하면 실제로 잘려 나간다).
        history = history[:1] + history[-(_HISTORY_MAX - 1):]
    sync["history"] = history


def _refresh_link(link: ExternalOrderLink, detail: dict, *, stamp: datetime,
                  result: dict[str, int]) -> tuple[dict, dict, Optional[dict]]:
    """링크 1건에 상세를 반영하고 **알림이 필요한 claim** 을 돌려준다.

    스냅샷·발주상태·묶음키·``last_status`` 갱신은 여기서 끝낸다. 알림만은 호출자가 집
    단위로 묶어 보내야 해서(같은 집의 세부옵션 4건이 알림 4건이 되던 결함) 여기서는
    보내지 않는다.

    Args:
        link: 갱신 대상 링크(스냅샷·컬럼은 이 함수가 바로 쓴다).
        detail: 네이버 상세 응답 1건.
        stamp: 이번 스윕 시각.
        result: 집계 dict — ``refreshed``·``claimed``·``self_claimed`` 를 여기서 올린다.

    Returns:
        ``(state, sync, claim)`` — ``state``·``sync`` 는 **아직 링크에 되쓰지 않은**
        사본이고(``notified_status`` 는 알림 결과를 본 뒤 호출자가 넣는다),
        ``claim`` 이 None 이 아니면 알림 대기다.
    """
    claim = extract_claim(detail)
    # 원본을 최신으로 갈아 끼운다 — 화면(큐·트리아지·도크)이 전부 스냅샷에서 읽으므로
    # 이것만으로 표시가 최신이 된다.
    link.raw_snapshot = copy.deepcopy(detail)
    flag_modified(link, "raw_snapshot")
    # 발주 상태 사본도 같이 갱신한다 — 판매자센터에서 발주확인을 하면 이 스윕이 첫
    # 목격자다. 안 갱신하면 목록 필터만 옛 값에 머문다(T16-B).
    place = extract_place_status(detail)
    link.place_order_status = (place["status"] or "")[:20] or None
    # 묶음키 사본도 같은 이유로 갱신한다 — 확인 큐는 스냅샷에서 매번 다시 계산하므로,
    # 컬럼만 옛 값에 머물면 두 화면의 집 수가 또 갈린다.
    # 값을 못 만들면 기존 값을 지우지 않는다(폴백보다 옛 사본이 정확하다).
    refreshed_group_key = group_key_text(detail)
    if refreshed_group_key:
        link.group_key = refreshed_group_key
    state = copy.deepcopy(link.triage_state) if isinstance(link.triage_state, dict) else {}
    sync = dict(state.get(STATE_KEY) or {})
    sync["last_status"] = claim["status"]
    sync["refreshed_at"] = stamp.isoformat()
    # 지나간 상태를 남긴다 — ``last_status`` 는 최신값 하나뿐이라 전이가 사라진다.
    _append_history(sync, claim, detail, stamp=stamp)
    result["refreshed"] += 1
    if not claim["blocking"]:
        return state, sync, None

    result["claimed"] += 1
    # **우리가 낸 클레임은 알리지 않는다.** 판매자 직접취소(`fulfillment.cancel_order`)나
    # 반품 접수(`fulfillment.request_return`)를 보내면 다음 스윕이 그 결과를 클레임으로
    # 목격하고, 문안이 "일정·생산이 잡혀 있으면 진행을 멈추고 판매자센터에서
    # 확인하세요"인 긴급 알림을 담당자에게 되돌려 보냈다. 방금 자기가 누른 일이 5분 뒤
    # 경보로 돌아온다 — 진짜 고객 클레임과 구분이 안 되니 경보 전체가 무뎌진다
    # (2026-08-24 감사 = 취소, 2026-08-28 R-3 = 반품).
    # 상태 갱신(스냅샷·발주상태·묶음키·last_status)은 그대로 한다. 사실은 사실이고,
    # 화면의 '취소 완료'·'반품 요청' 표시는 이 갱신에서 나온다. 막는 것은 **알림뿐**이다.
    if _is_our_claim(link, claim):
        # 조용히 넘기지 않는다 — 억제도 기록이 남아야 나중에 셀 수 있다.
        logger.info("[NAVER] 우리가 낸 클레임이라 알림을 보내지 않는다 link=%s status=%s",
                    link.id, claim["status"])
        sync["notified_status"] = claim["status"]
        result["self_claimed"] += 1
        return state, sync, None
    # 같은 상태로 두 번 알리지 않는다(5분 폴링이라 중복 방지가 필수).
    if sync.get("notified_status") == claim["status"]:
        return state, sync, None
    return state, sync, claim


def refresh_claims(
    session: Session, *, client: Any, changed: list[dict],
    now: Optional[datetime] = None, notify: bool = True,
) -> dict[str, int]:
    """변경 이벤트가 온 **기존 링크**의 상세를 다시 받아 취소·반품을 반영한다.

    반영은 링크(상품주문번호) 단위지만 **알림은 집 단위**다 — 네이버는 주문 1건을
    세부옵션마다 다른 상품주문번호로 쪼개 주므로, 링크마다 보내면 취소 1건이 알림
    여러 건이 된다(:func:`_pending_groups`).

    Args:
        session: DB 세션(커밋은 호출자).
        client: 네이버 클라이언트(상세 조회만 쓴다).
        changed: 이번 스윕의 변경 이벤트 목록(이미 받아 온 것을 재사용한다).
        now: 알림 생성 시각(테스트 주입).
        notify: False 면 상태만 반영하고 **알림을 만들지 않는다**. 과거 구간 소급 수집
            (백필)이 쓰는 자리다 — 이미 지난 취소·반품으로 알림을 대량 발송하면 사람이
            읽을 수 없는 소음이 되고, 그 소음이 진짜 알림을 덮는다.

    Returns:
        ``{"refreshed", "claimed", "notified", "self_claimed"}`` 집계.
        ``self_claimed`` 는 **우리가 낸 취소·반품이라 알림을 막은 건수**다 — 억제도
        세어야 "알림이 왜 안 왔지"를 나중에 확인할 수 있다.
    """
    stamp = now or now_utc_naive()
    result = {"refreshed": 0, "claimed": 0, "notified": 0, "self_claimed": 0}
    ids = changed_external_ids(changed)
    if not ids:
        return result

    links = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.channel == CHANNEL,
                ExternalOrderLink.external_id.in_(ids))
        .all()
    )
    if not links:
        # 이미 수집한 건이 하나도 안 바뀌었다 — 추가 호출 없이 끝낸다.
        return result

    by_id = {str(link.external_id): link for link in links}
    details = client.get_product_orders(list(by_id.keys()))
    syncs: list[tuple[ExternalOrderLink, dict, dict]] = []
    pending: list[tuple[ExternalOrderLink, dict]] = []
    for detail in details or []:
        link = by_id.get(extract_external_id(detail))
        if link is None:
            continue
        state, sync, claim = _refresh_link(link, detail, stamp=stamp, result=result)
        if claim is not None:
            pending.append((link, claim))
        syncs.append((link, state, sync))

    # 알림은 **집 단위**다 — 루프 안에서 링크마다 보내면 세부옵션 수만큼 알림이 간다.
    notified_status: dict[int, str] = {}
    if not notify and pending:
        # 상태는 위에서 이미 링크에 반영됐다. 여기서 막는 것은 **알림뿐**이다.
        logger.info("[NAVER] 클레임 알림 억제(백필) — 대상 링크 %d건", len(pending))
        pending = []
    for group_links, claim, holders, admins in _pending_groups(session, pending):
        sent = _notify(session, group_links, claim, holders, admins, now=stamp)
        if not sent:
            continue
        result["notified"] += sent
        for link in group_links:
            notified_status[int(link.id)] = claim["status"]
        logger.warning("[NAVER] 수집 후 클레임 감지 집=링크 %d건 status=%s 알림 %d명",
                       len(group_links), claim["status"], sent)

    for link, state, sync in syncs:
        status = notified_status.get(int(link.id))
        if status is not None:
            sync["notified_status"] = status
        state[STATE_KEY] = sync
        link.triage_state = state
        flag_modified(link, "triage_state")
    return result


#: 한 번의 **전체 다시 읽기**가 큐에 넣을 최대 집 수(NVREPAY-03). 넘으면 최신 집부터
#: 자르고 **잘랐다고 말한다** — 조용한 절단은 "전부 읽었다"로 읽힌다. 운영 실측
#: 2026-08-30 기준 전체 58집이라 지금은 캡에 닿지 않는다.
REFRESH_ALL_LIMIT = 200

#: 다시 읽어도 값이 안 바뀌는 **종결** 상품주문 상태(네이버 ``productOrderStatus``).
#: ``PURCHASE_DECIDED``(구매확정)까지 넣는 이유: 구매확정은 클레임 창이 닫혔다는 **네이버
#: 쪽 사실**이다. "수집 후 N일" 같은 나이 기준을 쓰지 않는 이유도 같다 — 나이는 추측이고,
#: 자사 배송·시공이라 ``DELIVERING`` 으로 몇 달을 끄는 집이 정상으로 존재한다(운영 실측
#: 2026-08-30: 58집 중 DELIVERING 23집). 나이로 자르면 그 집들의 진짜 취소를 놓친다.
TERMINAL_ORDER_STATUSES = frozenset({"CANCELED", "RETURNED", "PURCHASE_DECIDED"})

#: 같은 집을 이 시간 안에 두 번 읽지 않는다. 화면이 끝을 안 말하던 시절 사용자가 28초
#: 간격으로 두 번 눌렀고(운영 2026-08-30 04:20:13·04:20:41) 두 번째는 통째로 낭비였다.
REFRESH_ALL_COOLDOWN_SECONDS = 600

#: 감사 원장에서 **전체 다시 읽기 요청**을 찾는 태그. 요청을 쓰는 쪽(라우트)과 읽는 쪽
#: (:func:`running_refresh_all`)이 같은 문자열을 봐야 하므로 상수로 둔다 — 한쪽만 바뀌면
#: 진행 표시가 조용히 빈손이 되고, 그건 "아무도 안 눌렀다"로 읽힌다.
REFRESH_ALL_AUDIT_ACTION = "NAVER_INGEST_REFRESH_ALL_ENQUEUE"

#: 요청 하나를 **지금 돌고 있다**고 볼 창(초). 누른 사람 화면의 폴링 마감
#: (``REFRESH_POLL_TIMEOUT_MS`` = 300000)과 같은 값이다. 두 값을 갈라 두면 한쪽 화면만
#: 영원히 `다시 읽는 중` 으로 남는다.
REFRESH_ALL_RUN_WINDOW_SECONDS = 300

#: 집 하나를 다시 읽는 데 걸리는 시간(초) — 추정이 아니라 **실측**이다.
#: ``claim_sync.refreshed_at`` 스탬프 분포로 쟀다: 운영 45집 42.3초(집당 0.94s, 2026-08-30
#: 23:25 요청), 스테이징 85집 81.7초(집당 0.97s, 2026-08-30 07:13 요청). 두 환경의 기울기가
#: 같고 스탬프가 등간격이라(운영 45집 구간 11·22·32·42초) 집 수에 선형으로 본다.
REFRESH_ALL_SECONDS_PER_HOUSE = 1.0

#: 느린 쪽 실측(초/집). 워커 동시성이 1이라 앞에 다른 일이 서 있으면 그만큼 통째로 밀린다
#: (운영 2026-08-30 04:20 연타 실측: 첫 스탬프가 요청 +40.5초·+69.0초). 사람에게 말하는
#: 시간이 **범위**여야 하는 이유다 — 한 값으로 말하면 밀린 날 화면이 거짓말한 게 된다.
REFRESH_ALL_SECONDS_PER_HOUSE_SLOW = 2.0


def refresh_all_eta_text(count: int) -> str:
    """집 ``count`` 개를 다시 읽는 데 걸릴 시간을 사람이 읽는 한 마디로 (NVREPAY-05 T2).

    왜 필요한가: 버튼은 몇 집인지만 말하고 **얼마나 걸리는지**는 말하지 않았다. 사람은
    그 침묵을 "곧 끝난다"로 읽고, 1분이 지나면 멈춘 걸로 읽는다(2026-08-30 운영에서 28초
    만에 다시 눌린 사건의 절반은 이 침묵이었다).

    한 값이 아니라 **범위**로 말한다. 처리 속도 자체는 두 환경에서 거의 같지만
    (:data:`REFRESH_ALL_SECONDS_PER_HOUSE`), 워커가 하나뿐이라 앞선 작업이 있으면 시작이
    통째로 밀린다(:data:`REFRESH_ALL_SECONDS_PER_HOUSE_SLOW`). 한 값으로 말하면 밀린 날
    화면이 거짓말한 것이 된다.

    Args:
        count: 다시 읽을 집 수.

    Returns:
        ``"약 1~2분"`` 같은 한 마디. 셀 게 없으면 빈 문자열(화면이 아무 말도 안 한다).
    """
    if count <= 0:
        return ""
    low_seconds = count * REFRESH_ALL_SECONDS_PER_HOUSE
    high_seconds = count * REFRESH_ALL_SECONDS_PER_HOUSE_SLOW
    if high_seconds < 60:
        return "약 1분 안"
    # 올림으로 말한다 — 남는 시간은 사람이 견디지만 모자란 예고는 또 "멈췄나" 가 된다.
    low_minutes = max(1, int(-(-low_seconds // 60)))
    high_minutes = int(-(-high_seconds // 60))
    if high_minutes <= low_minutes:
        return f"약 {low_minutes}분"
    return f"약 {low_minutes}~{high_minutes}분"


def refreshed_household_counts(
    session: Session, since: datetime, *,
    order_nos: Optional[list[str]] = None,
) -> tuple[int, int]:
    """``since`` 이후 다시 읽힌 집을 센다 — 진행 표시 두 곳의 **하나뿐인** 판정.

    끝난 집의 정의는 하나다: 그 집의 상품주문이 **전부** ``since`` 이후에 다시 읽혔다.
    대표 링크 하나만 보면 안 되는 이유는 워커가 형제 상품주문을 같이 읽고 스탬프도
    형제마다 찍기 때문이고, 값이 없거나 깨진 스탬프를 **안 읽은 것**으로 세는 이유는
    진행 표시가 실제보다 앞서 가면 사람이 낡은 화면을 최신으로 믿기 때문이다.

    Args:
        session: DB 세션.
        since: 요청이 큐에 들어간 시각(UTC naive).
        order_nos: 셀 집(주문번호) 목록. ``None`` 이면 수집된 네이버 집 **전부**를 센다
            (남이 누른 요청은 어떤 집을 넣었는지 화면이 모르기 때문 — T1).

    Returns:
        ``(끝난 집, 센 집)``.
    """
    refreshed_at = ExternalOrderLink.triage_state[STATE_KEY]["refreshed_at"].as_string()
    query = (session.query(ExternalOrderLink.external_order_no, refreshed_at)
             .filter(ExternalOrderLink.channel == CHANNEL,
                     ExternalOrderLink.external_order_no.isnot(None)))
    if order_nos is not None:
        if not order_nos:
            return 0, 0
        query = query.filter(ExternalOrderLink.external_order_no.in_(order_nos))
    rows = query.all()  # perf-ok: 링크 단위 스칼라 투영(운영 200행), 관리자 전용 폴링

    done_by_house: dict[str, bool] = {}
    for order_no, stamp in rows:
        key = str(order_no)
        done_by_house[key] = done_by_house.get(key, True) and _refreshed_since(stamp, since)
    return sum(1 for value in done_by_house.values() if value), len(done_by_house)


def _refreshed_since(stamp: Optional[str], since: datetime) -> bool:
    """이 상품주문이 ``since`` 이후에 다시 읽혔는가.

    값이 없거나 깨졌으면 **아직 안 읽은 것**으로 본다 — 진행 표시가 실제보다 앞서 가면
    사람이 낡은 화면을 최신으로 믿는다.

    Args:
        stamp: ``claim_sync.refreshed_at`` 문자열(ISO) 또는 ``None``.
        since: 요청이 큐에 들어간 시각.

    Returns:
        ``since`` 이후에 읽혔으면 True.
    """
    if not stamp:
        return False
    try:
        parsed = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return False
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed >= since


def running_refresh_all(
    session: Session, *, now: Optional[datetime] = None,
) -> Optional[dict[str, Any]]:
    """**지금 누가 전체 다시 읽기를 돌리고 있나** — 누구의 브라우저에서든 (NVREPAY-05 T1).

    왜 필요한가: 진행 표시는 누른 브라우저 안에만 있었다. 다른 관리자가 같은 목록을 열면
    돌고 있는 중인데도 `다시 읽기 45주문` 이라 적혀 있고, 그래서 또 누른다 — 2026-08-30
    운영에서 한 사람이 28초 만에 두 번 눌러 낭비된 것과 **같은 낭비를 두 사람이** 낸다.

    **새 상태 저장소를 만들지 않는다.** 요청은 이미 감사 원장에 남고(누가·언제·몇 집),
    처리 진행은 워커가 찍는 ``claim_sync.refreshed_at`` 가 이미 말한다. 둘을 붙이면
    "누가 언제 눌렀고 어디까지 왔나"가 나온다. 판정도 누른 사람 화면과 같은 함수
    (:func:`refreshed_household_counts`)를 쓴다 — 두 벌이면 조용히 갈린다.

    끝난 집 수는 요청이 넣은 집 수를 **넘지 않게 자른다**. 어떤 집을 넣었는지는 감사 행에
    없어서 수집된 집 전부를 세는데, 그 사이 단건 `다시 읽기` 나 자동 스윕이 찍은 스탬프가
    섞이면 진행이 100%를 넘을 수 있다.

    Args:
        session: DB 세션.
        now: 지금 시각(테스트 주입). 생략하면 UTC naive 현재.

    Returns:
        돌고 있으면 ``{"actor", "started_at", "elapsed_seconds", "total", "done",
        "pending", "eta"}``. 아무도 안 돌리고 있거나(창 밖) 이미 끝났으면 ``None``.
    """
    stamp = now or now_utc_naive()
    window_start = stamp - timedelta(seconds=REFRESH_ALL_RUN_WINDOW_SECONDS)
    row = (session.query(SecurityLog.timestamp, SecurityLog.user_id, SecurityLog.detail)
           .filter(SecurityLog.action == REFRESH_ALL_AUDIT_ACTION,
                   SecurityLog.timestamp >= window_start,
                   SecurityLog.timestamp <= stamp)
           .order_by(SecurityLog.timestamp.desc(), SecurityLog.id.desc())
           .first())  # perf-ok: (timestamp, id) 인덱스 + 창 5분
    if row is None:
        return None
    started_at, user_id, detail = row
    total = _audit_queued_count(detail)
    if total <= 0:
        # 대상 0으로 끝난 요청(쿨다운)은 돌고 있는 게 아니다.
        return None

    done = min(refreshed_household_counts(session, started_at)[0], total)
    if done >= total:
        return None
    return {"actor": _actor_name(session, user_id),
            "started_at": started_at.isoformat(),
            "elapsed_seconds": max(0, int((stamp - started_at).total_seconds())),
            "total": total, "done": done, "pending": total - done,
            "eta": refresh_all_eta_text(total)}


def _audit_queued_count(detail: Any) -> int:
    """감사 행의 ``detail`` 에서 큐에 넣은 집 수를 꺼낸다.

    ``detail`` 은 JSONB 라 보통 dict 로 오지만, 상한을 넘겨 잘린 행
    (:func:`audit_writer.normalize_security_detail`)은 ``{"truncated": True}`` 다.
    모양이 다르면 **0** 을 준다 — 모르는 요청을 진행 중이라고 그리지 않는다.

    Args:
        detail: 감사 행의 ``detail`` 값.

    Returns:
        큐에 넣은 집 수(모르면 0).
    """
    if not isinstance(detail, dict):
        return 0
    try:
        return max(0, int(detail.get("queued") or 0))
    except (TypeError, ValueError):
        return 0


def _actor_name(session: Session, user_id: Optional[int]) -> str:
    """요청을 누른 사람 이름. 모르면 빈 문자열(화면이 `다른 관리자` 라고 말한다).

    감사 행에 행위자가 없던 시절(2026-08-31 이전 요청)의 행도 그대로 읽힌다 — 이름이
    없다고 진행 표시를 통째로 접으면 그게 더 나쁘다.

    Args:
        session: DB 세션.
        user_id: 감사 행의 행위자 id(없으면 ``None``).

    Returns:
        사용자 이름 또는 빈 문자열.
    """
    if not user_id:
        return ""
    name = session.query(User.name).filter(User.id == int(user_id)).scalar()
    return str(name or "")


def _is_terminal_link(claim_status: str, order_status: str) -> bool:
    """이 상품주문이 **더 변하지 않는 자리**에 있는가 — 두 축 중 하나라도 종결이면 True.

    두 축을 함께 보는 이유: ``claimStatus`` 는 클레임이 걸린 건에만 있고
    ``productOrderStatus`` 는 클레임 없이 끝난 건(구매확정)까지 말한다. 한 축만 보면
    각각 반대쪽을 통째로 놓친다.

    **모르는 값은 종결이 아니다.** :data:`mapping.CLAIM_PHASES` 규율과 같다 — 모르면
    읽는 쪽으로 기운다(헛읽기는 조회 한 번, 못 읽으면 취소를 놓친다).

    Args:
        claim_status: 스냅샷 동기화가 남긴 ``claim_sync.last_status``.
        order_status: 스냅샷의 ``productOrderStatus``.

    Returns:
        종결이면 True.
    """
    from foms.services.integrations.naver_commerce.mapping import (
        CLAIM_PHASE_DONE,
        CLAIM_PHASES,
    )

    if CLAIM_PHASES.get((claim_status or "").strip().upper()) == CLAIM_PHASE_DONE:
        return True
    return (order_status or "").strip().upper() in TERMINAL_ORDER_STATUSES


def refreshable_household_link_ids(
    session: Session, *,
    limit: int = REFRESH_ALL_LIMIT,
    now: Optional[datetime] = None,
) -> tuple[list[int], int, dict[str, int]]:
    """**다시 읽을 값어치가 있는 집**의 대표 링크 id 를 최신 순으로 준다 (NVREPAY-03).

    `다시 읽기` 는 집 1건짜리라 담당자가 그 집 pane 에 서 있어야 누른다. 그런데 자동
    스윕은 네이버가 **변경 이벤트를 준 건만** 다시 읽으므로(:func:`refresh_claims`),
    이벤트가 안 오는 집은 자동 경로로 영영 안 갱신된다. 화면 전체를 한 번에 최신화하는
    자리가 없어서, 사람이 "지금 이 목록이 진짜인가"를 확인할 방법이 목록을 하나씩 여는
    것뿐이었다.

    집 대표는 **가장 작은 링크 id** 하나면 된다 — :func:`refresh_household` 가 그 링크가
    속한 집 전체(형제 상품주문 전부)를 다시 읽기 때문이다. 집을 주문번호
    (``external_order_no``)로 묶는 규칙은 화면 목록과 같다.

    **집 전부를 읽지는 않는다**(2026-08-30 사용자 지적). 두 가지를 뺀다:

    * **종결** — 집의 **모든** 상품주문이 :func:`_is_terminal_link` 인 집. 다시 읽어도
      값이 안 바뀐다(운영 실측 58집 중 12집). 하나라도 살아 있으면 **읽는다** — 분할
      취소된 집에서 남은 건의 취소를 놓치지 않으려는 방향이다.
    * **쿨다운** — 집의 모든 상품주문을 :data:`REFRESH_ALL_COOLDOWN_SECONDS` 안에 이미
      읽었을 때. 연타가 같은 조회를 곱하는 것을 막는다.

    뺀 수는 **말해야 한다** — 조용히 줄이면 화면의 "전체"가 거짓이 된다.

    Args:
        session: DB 세션.
        limit: 돌려줄 최대 집 수.
        now: 쿨다운 기준 시각(테스트 주입). 생략하면 지금(UTC naive).

    Returns:
        ``(대표 link_id 목록, 대상 집 수, 뺀 수)``. 대상 집 수는 **제외를 거친 뒤**의
        수라 화면 라벨이 그대로 쓸 수 있고, 목록은 ``limit`` 에서 잘렸을 수 있다.
        뺀 수는 ``{"done": 종결로 뺀 집, "recent": 쿨다운으로 뺀 집}``.
    """
    stamp = now or now_utc_naive()
    cutoff = stamp - timedelta(seconds=REFRESH_ALL_COOLDOWN_SECONDS)

    # raw_snapshot 전체를 끌어오지 않는다 — 집 200링크면 스냅샷이 수 MB 다. 필요한
    # 스칼라 두 개만 JSON 경로로 뽑는다(중첩·평평 두 모양 모두 받는다: 응답 변형은
    # ``mapping.extract_*`` 가 이미 겪은 자리다).
    nested = ExternalOrderLink.raw_snapshot["productOrder"]["productOrderStatus"].as_string()
    flat = ExternalOrderLink.raw_snapshot["productOrderStatus"].as_string()
    claim_status = ExternalOrderLink.triage_state[STATE_KEY]["last_status"].as_string()
    refreshed_at = ExternalOrderLink.triage_state[STATE_KEY]["refreshed_at"].as_string()

    rows = (session.query(ExternalOrderLink.id,
                          ExternalOrderLink.external_order_no,
                          ExternalOrderLink.created_at,
                          nested, flat, claim_status, refreshed_at)
            .filter(ExternalOrderLink.channel == CHANNEL,
                    ExternalOrderLink.external_order_no.isnot(None))
            .all())  # perf-ok: 링크 단위 스칼라 투영(운영 200행), 관리자 전용 조작 경로

    households: dict[str, dict[str, Any]] = {}
    for link_id, order_no, created_at, nested_st, flat_st, claim_st, seen_at in rows:
        house = households.setdefault(str(order_no), {
            "link_id": int(link_id), "seen_at": created_at,
            "all_terminal": True, "all_recent": True,
        })
        house["link_id"] = min(house["link_id"], int(link_id))
        if created_at is not None and (house["seen_at"] is None or created_at > house["seen_at"]):
            house["seen_at"] = created_at
        if not _is_terminal_link(claim_st, nested_st or flat_st):
            house["all_terminal"] = False
        if not _is_recent_refresh(seen_at, cutoff):
            house["all_recent"] = False

    skipped = {"done": 0, "recent": 0}
    live: list[dict[str, Any]] = []
    for house in households.values():
        if house["all_terminal"]:
            skipped["done"] += 1
        elif house["all_recent"]:
            skipped["recent"] += 1
        else:
            live.append(house)

    ordered = sorted(live, key=lambda h: (h["seen_at"] is not None, h["seen_at"]), reverse=True)
    return [int(h["link_id"]) for h in ordered[:limit]], len(live), skipped


def _is_recent_refresh(refreshed_at: Optional[str], cutoff: datetime) -> bool:
    """이 상품주문을 쿨다운 안에 이미 읽었는가.

    값이 없으면(한 번도 안 읽음) **최근이 아니다** — 안 읽은 건 반드시 읽는다.
    깨진 값도 같다: 파싱 못 하면 읽는 쪽으로 기운다.

    Args:
        refreshed_at: ``claim_sync.refreshed_at`` 문자열(ISO) 또는 ``None``.
        cutoff: 이 시각보다 뒤면 "최근".

    Returns:
        쿨다운 안에 이미 읽었으면 True.
    """
    if not refreshed_at:
        return False
    try:
        stamp = datetime.fromisoformat(str(refreshed_at))
    except (TypeError, ValueError):
        return False
    if stamp.tzinfo is not None:
        stamp = stamp.replace(tzinfo=None)
    return stamp >= cutoff


def refresh_household(
    session: Session, *, client: Any, link_id: int,
    now: Optional[datetime] = None,
) -> dict[str, int]:
    """**집 1건을 지목해** 네이버에서 최신 상태를 다시 읽는다 — T4(읽기 전용).

    5분 스윕(:func:`refresh_claims`)은 네이버가 **변경 이벤트를 줄 때만** 그 건을 다시
    읽는다. 이벤트가 안 오는 건은 자동 경로로 **영영** 못 잡는다 — 이 모듈 머리말이
    스스로 "취소가 변경 목록에 어떤 이름으로 실리는지 실물로 확인되지 않았다"고 적어
    뒀다. 그 구멍을 사람이 손으로 메우는 자리다.

    **`refresh_claims` 를 한 줄도 고치지 않는다.** 변경 이벤트 모양(``productOrderId``
    만 있는 dict)으로 감싸서 넘기면 알림 묶기(집 단위)·자기취소 억제·같은 상태 중복
    억제·스냅샷/발주상태/묶음키 갱신이 **전부 그대로** 따라온다. 새로 만드는 규칙이
    없으니 자동 경로와 수동 경로가 갈릴 자리도 없다.

    **네이버에 쓰는 것은 없다** — 나가는 호출은 상세 조회 하나뿐이다. 다만 "되돌릴 게
    전혀 없다"는 아니다: 스냅샷·발주상태·묶음키를 최신으로 갈아 끼우고, **새로 발견된
    취소·반품은 담당자·관리자 알림으로 나간다**(:func:`refresh_claims` 가 그렇게 만들어져
    있다). 그게 이 버튼의 **목적**이다 — 변경 이벤트가 안 와서 자동 경로가 놓친 클레임을
    사람이 끌어내는 자리다. 부작용이 아니라 기능이라는 뜻이지, 없다는 뜻이 아니다.

    호출은 **WORKER 에서만** 한다 — 커머스API 에 등록된 호출 IP 가 WORKER 것뿐이다
    (web 에서 부르면 차단된다). web 은 큐에 넣기만 한다.

    Args:
        session: DB 세션(커밋은 호출자).
        client: 네이버 클라이언트(상세 조회만 쓴다).
        link_id: 기준 수집 링크 id — **그 링크가 속한 집 전체**가 대상이다.
        now: 반영 시각(테스트 주입).

    Returns:
        :func:`refresh_claims` 집계에 ``targets``(다시 읽기를 요청한 상품주문 수)를
        더한 dict.

    Raises:
        FulfillmentError: 링크를 찾을 수 없을 때(네이버를 부르기 전에 멈춘다).
    """
    # 집 판정은 발송처리와 **같은 SSOT** 를 쓴다 — 여기서 다시 짜면 화면이 가른 집과
    # 다시 읽는 대상이 어긋난다(분할배송: 같은 주문번호 다른 수취인).
    from foms.services.integrations.naver_commerce.fulfillment import links_of_group

    links = links_of_group(session, int(link_id))
    ids = [str(link.external_id).strip() for link in links
           if str(link.external_id or "").strip()]
    if not ids:
        return {"refreshed": 0, "claimed": 0, "notified": 0, "self_claimed": 0,
                "targets": 0}
    result = refresh_claims(
        session, client=client,
        changed=[{"productOrderId": external_id} for external_id in ids],
        now=now,
    )
    result["targets"] = len(ids)
    return result


__all__ = [
    "NOTIFICATION_TYPE",
    "STATE_KEY",
    "changed_external_ids",
    "refresh_claims",
    "refresh_household",
]
