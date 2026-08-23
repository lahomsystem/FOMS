"""발주확인·발송처리 실행 (NAVER-INGEST-02 T16-G) — **WORKER 전용**.

네이버 HTTP 는 WORKER 에서만 나간다(커머스API 호출 IP 3슬롯 = Railway static IP 3개, 여유 0).
web 은 :func:`foms.services.jobs.queue.enqueue_naver_fulfillment` 로 enqueue 만 한다.

되돌릴 수 없는 조작이다
-----------------------
발송처리는 구매자에게 "물건이 출발했다"로 보이고 정산·구매확정 시계를 돌린다. 그래서:

* **멱등** — 링크의 ``triage_state['fulfillment']`` 에 처리 시각을 남기고, 값이 있으면
  네이버를 다시 부르지 않는다. 네이버의 400(이미 처리됨)을 정상 흐름으로 삼지 않는다.
* **실패는 조용히 넘기지 않는다** — 사유 문장을 상태에 남겨 화면이 그대로 보여준다.
* 배송방법은 자사 배송이라 ``DIRECT_DELIVERY``(직접 전달). 택배사·송장이 없다.
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import CONFIRMED_PLACE_STATUSES
from models import ExternalOrderLink

logger = logging.getLogger(__name__)

__all__ = [
    "FulfillmentError",
    "household_key",
    "STATE_KEY",
    "DIRECT_DELIVERY",
    "clear_failure",
    "confirm_place_order",
    "dispatch_order",
    "cancel_order",
    "record_task_failure",
    "CANCEL_REASONS",
    "CLOSE_NOW_RELATIONS",
]

#: ``triage_state`` 안에서 이 기능이 쓰는 키. 도크 체크·클레임 동기화와 다른 축이다.
STATE_KEY = "fulfillment"

#: 자사 배송(택배사·송장 없음)의 배송방법 코드.
DIRECT_DELIVERY = "DIRECT_DELIVERY"

#: 발주확인 없이도 바로 발송처리로 닫는 관계(2026-08-22 사용자 결정 D1).
#: 추가결제·재결제는 물건이 따로 나가지 않아 "배송 시작"이 사실을 왜곡하지 않는다.
#: 신규(NEW·빈값)는 그대로 발주확인이 먼저다.
CLOSE_NOW_RELATIONS = ("ADDON", "REPAY")

#: 판매자 직접취소 사유 코드 → 사람이 읽는 라벨 (커머스API 2.86.0 "취소 요청").
#: 네이버가 아는 값만 보낸다 — 목록 밖 코드는 400 이고, 되돌릴 수 없는 경로라 미리 막는다.
CANCEL_REASONS = {
    "INTENT_CHANGED": "구매 의사 취소",
    "COLOR_AND_SIZE": "색상 및 사이즈 변경",
    "WRONG_ORDER": "다른 상품 잘못 주문",
    "PRODUCT_UNSATISFIED": "서비스 불만족",
    "DELAYED_DELIVERY": "배송 지연",
    "SOLD_OUT": "상품 품절",
    "INCORRECT_INFO": "상품 정보 상이",
}

#: KST — 네이버는 발송일에 타임존이 붙은 ISO8601 을 요구한다.
KST = timezone(timedelta(hours=9))


class FulfillmentError(RuntimeError):
    """발주확인·발송처리 실패. 사유 문장을 그대로 사람에게 보여준다."""


def household_key(link: ExternalOrderLink) -> tuple[str, str, str]:
    """이 링크가 속한 '집' 키 — 화면이 집을 가르는 것과 **같은 규칙**.

    화면 큐(:func:`foms.web.admin.naver_ingest._group_queue`)는
    :func:`mapping.group_key` ``(주문번호, 수취인 전화, 주소)`` 로 집을 가른다.
    여기서 주문번호만 보면 **분할배송**(같은 주문번호·다른 주소)에서 화면이 두 줄로
    보여준 것을 워커가 한 번에 처리한다 — A집만 골랐는데 B집까지 네이버로 나가고,
    그 호출은 되돌릴 수 없다.

    Args:
        link: ``ExternalOrderLink`` 행.

    Returns:
        같은 값이면 같은 집. 원본이 깨져 키를 못 만들면 그 링크 혼자인 집으로 본다
        (화면과 같은 폴백 — 큐에서 조용히 사라지는 것보다 낫다).
    """
    from foms.services.integrations.naver_commerce.mapping import group_key

    try:
        key = group_key(link.raw_snapshot or {})
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        logger.warning("[NAVER] 집 키 계산 실패(link %s): %s", link.id, exc)
        return ("__ungrouped__", str(link.id), "")
    if not any(part for part in key):
        # 원본이 비어 키가 통째로 빈 경우(예외는 안 난다) — 서로 다른 주문이 같은 키로
        # 붙어 한 집처럼 읽힌다. 그럴 땐 링크 단독으로 센다.
        return ("__ungrouped__", str(link.id), "")
    return key


def _links_of_group(session: Session, link_id: int) -> list[ExternalOrderLink]:
    """같은 **집**의 링크 전부(한 집은 통째로 처리한다).

    1차로 같은 네이버 주문번호를 모으고(인덱스 있는 축), 그중 :func:`household_key` 가
    같은 것만 남긴다. 분할배송에서 화면이 가른 집과 서버가 처리하는 대상이 어긋나지 않게
    하는 자리다.
    """
    link = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.id == link_id, ExternalOrderLink.channel == CHANNEL)
        .first()
    )
    if link is None:
        raise FulfillmentError(f"수집 기록을 찾을 수 없습니다 (link {link_id}).")
    order_no = (link.external_order_no or "").strip()
    if not order_no:
        return [link]
    rows = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.channel == CHANNEL,
                ExternalOrderLink.external_order_no == order_no)
        .order_by(ExternalOrderLink.id.asc())
        .all()
    )
    base_key = household_key(link)
    same_house = [row for row in rows if household_key(row) == base_key]
    return same_house or [link]


def _claim_guard(session: Session, links: list[ExternalOrderLink], *,
                 action: str, stamp: datetime) -> None:
    """집 안에 취소·반품이 하나라도 있으면 네이버를 부르지 않는다.

    화면은 클레임 집을 잠그지만(집 단위), 화면만 믿으면 링크 id 를 아는 요청이 그대로
    통과한다. 발송처리는 구매자에게 "배송 시작"으로 보이고 되돌릴 수 없다 — 마지막 문을
    서버가 닫는다. 판정 기준은 화면과 같은 :func:`mapping.extract_claim` 이다.

    **거절 사유를 상태에 남긴다.** web 은 enqueue 만 하고 즉시 "요청했습니다"로 답하므로,
    워커가 조용히 거절하면 사람은 보냈다고 믿는다 — 실패 띠가 유일한 통로다.

    Args:
        session: DB 세션.
        links: 한 집의 링크들.
        action: ``confirm`` / ``dispatch`` (화면 재시도가 이 값을 본다).
        stamp: 기록 시각.

    Raises:
        FulfillmentError: 클레임이 걸린 상품주문이 있을 때.
    """
    from foms.services.integrations.naver_commerce.mapping import extract_claim

    for row in links:
        claim = extract_claim(row.raw_snapshot or {})
        if not claim.get("blocking"):
            continue
        reason = (f"취소·반품이 진행 중인 집입니다({claim.get('label') or '클레임'}) — "
                  "판매자센터에서 처리하세요.")
        _mark_failures({str(r.external_id): r for r in links},
                       {str(r.external_id): reason for r in links},
                       action=action, stamp=stamp)
        session.flush()
        raise FulfillmentError(reason)


def _cancel_guard(session: Session, links: list[ExternalOrderLink], *,
                  action: str, stamp: datetime) -> None:
    """집 안에 **우리가 취소한** 상품주문이 있으면 발주확인·발송처리를 보내지 않는다.

    :func:`_claim_guard` 로는 못 막는다 — 그건 ``raw_snapshot`` 의 네이버 클레임을 읽는데,
    우리가 방금 낸 취소는 **다음 수집 스윕 전까지 스냅샷에 없다**. 그 사이 발송처리를 누르면
    취소한 상품주문에 되돌릴 수 없는 호출이 나간다(2026-08-23 리뷰 [치명]).

    한 건이라도 취소됐으면 **집 전체**를 막는다. 부분 취소 실패는 남은 건을 발송할 상황이
    아니라 취소를 다시 보낼 상황이다.

    Args:
        session: DB 세션.
        links: 한 집의 링크들.
        action: ``confirm`` / ``dispatch`` (화면 재시도가 이 값을 본다).
        stamp: 기록 시각.

    Raises:
        FulfillmentError: 취소된 상품주문이 있을 때.
    """
    canceled = [row for row in links if _state(row).get("canceled_at")]
    if not canceled:
        return
    reason = ("취소한 집입니다 — 발주확인·발송처리를 보내지 않습니다"
              f"(취소된 상품주문 {len(canceled)}건).")
    _mark_failures({str(row.external_id): row for row in links},
                   {str(row.external_id): reason for row in links},
                   action=action, stamp=stamp)
    session.flush()
    raise FulfillmentError(reason)


def _state(link: ExternalOrderLink) -> dict[str, Any]:
    """링크의 fulfillment 상태(없으면 빈 dict)."""
    state = link.triage_state if isinstance(link.triage_state, dict) else {}
    value = state.get(STATE_KEY)
    return dict(value) if isinstance(value, dict) else {}


def _write_state(link: ExternalOrderLink, patch: dict[str, Any]) -> None:
    """fulfillment 상태를 병합 저장한다(다른 축은 건드리지 않는다)."""
    state = copy.deepcopy(link.triage_state) if isinstance(link.triage_state, dict) else {}
    current = dict(state.get(STATE_KEY) or {})
    current.update(patch)
    state[STATE_KEY] = current
    link.triage_state = state
    flag_modified(link, "triage_state")


def _dispatch_timestamp(now: datetime) -> str:
    """네이버가 요구하는 발송일 형식(ISO8601 밀리초 + 타임존)."""
    kst = now.replace(tzinfo=timezone.utc).astimezone(KST) if now.tzinfo is None else now.astimezone(KST)
    return kst.strftime("%Y-%m-%dT%H:%M:%S.") + f"{kst.microsecond // 1000:03d}" + kst.strftime("%z")[:3] + ":" + kst.strftime("%z")[3:]


def _split_result(payload: Any, ids: list[str]) -> tuple[list[str], dict[str, str]]:
    """네이버 200 응답을 **건별 성공/실패**로 가른다.

    커머스API 는 HTTP 200 을 주면서 body 안에 건별 실패를 담는다
    (``failProductOrderInfos``). 그걸 안 보면 실패한 상품주문에도 성공 도장이 찍히고,
    멱등 규칙 때문에 **다시는 보내지지 않는다** — 조용한 미발송이 된다.

    모르는 모양의 응답(성공 목록 키도 실패 목록 키도 없는 body)은 예전처럼 전부 성공으로
    본다. 판단 근거가 없는데 실패로 몰면 이미 나간 호출을 사람이 다시 보내게 된다.

    Args:
        payload: 클라이언트가 돌려준 응답 payload.
        ids: 이번 호출로 보낸 상품주문번호 목록.

    Returns:
        ``(성공한 id 목록, {실패한 id: 사유})``.
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        data = payload if isinstance(payload, dict) else {}

    failures: dict[str, str] = {}
    #: 상품주문번호가 없어 어느 건인지 모르는 실패 항목의 사유. 버리면 "실패 목록이 없다"가
    #: 되어 전부 성공 도장이 찍히고, 멱등 규칙 때문에 영영 재발송되지 않는다.
    unattributed: list[str] = []
    for row in (data.get("failProductOrderInfos") or []):
        if not isinstance(row, dict):
            continue
        reason = str(row.get("message") or row.get("failMessage")
                     or row.get("reason") or "네이버가 실패로 처리했습니다.")[:500]
        pid = str(row.get("productOrderId") or "").strip()
        if not pid:
            unattributed.append(reason)
            continue
        failures[pid] = reason

    raw_success = data.get("successProductOrderIds")
    if raw_success is None:
        infos = data.get("successProductOrderInfos")
        if isinstance(infos, list):
            raw_success = [row.get("productOrderId") for row in infos if isinstance(row, dict)]
    if isinstance(raw_success, list):
        reported_ok = {str(x) for x in raw_success if x}
        for pid in ids:
            # 성공 목록에도 실패 목록에도 없는 건 = 네이버가 처리했다고 말하지 않은 건.
            if pid not in reported_ok and pid not in failures:
                # 무기명 실패 사유가 함께 왔으면 그걸 붙인다 — 네이버가 준 진단을 버리면
                # 사람이 무엇을 고쳐야 하는지 알 수 없다.
                extra = ("; ".join(unattributed))[:400]
                failures[pid] = ("네이버가 성공 목록에 넣지 않았습니다."
                                 + (f" 사유: {extra}" if extra else ""))
    elif unattributed:
        # 실패는 왔는데 어느 건인지 모르고 성공 목록도 없다 — 누가 됐는지 알 수 없으므로
        # 아무에게도 성공 도장을 찍지 않는다(사람이 사유를 보고 다시 보낸다).
        # 무엇이 처리됐는지 알 수 없다. 성공 도장을 찍으면 진짜 안 나간 건이 영영 묻히고,
        # 안 찍으면 재시도가 이미 나간 건을 다시 부를 수 있다. 되돌릴 수 없는 쪽(미발송)을
        # 피하는 대신, 재시도 전에 판매자센터를 확인하라고 사유에 적는다.
        detail = "; ".join(unattributed)[:400]
        for pid in ids:
            if pid not in failures:
                failures[pid] = (f"네이버가 실패를 알렸으나 상품주문번호가 없습니다: {detail} "
                                 "— 다시 보내기 전에 판매자센터에서 처리 상태를 확인하세요.")
    elif not failures:
        return list(ids), {}

    return [pid for pid in ids if pid not in failures], failures


def _mark_failures(rows: dict[str, ExternalOrderLink], failures: dict[str, str],
                   *, action: str, stamp: datetime) -> None:
    """실패한 상품주문에 사유를 남긴다 — **어느 작업**이 실패했는지 함께.

    화면의 '실패한 집만 다시 시도' 가 이 값을 보고 같은 작업으로 재시도한다. 없으면
    발송처리 실패를 발주확인으로 재시도하게 되고, 그건 멱등 규칙에 걸려 조용히 넘어간 뒤
    실패 띠만 영원히 남는다.
    """
    for pid, reason in failures.items():
        row = rows.get(pid)
        if row is None:
            continue
        _write_state(row, {"last_error": reason, "last_error_at": stamp.isoformat(),
                           "last_error_action": action})


def confirm_place_order(session: Session, client: Any, *, link_id: int,
                        actor_user_id: Optional[int] = None,
                        now: Optional[datetime] = None) -> dict[str, Any]:
    """한 집을 발주확인 처리한다 (WORKER 실행).

    Args:
        session: DB 세션(호출자가 commit 을 소유한다).
        client: :class:`~...client.NaverCommerceClient`.
        link_id: 기준 링크 id.
        actor_user_id: 누른 사람(기록용).
        now: 시각 주입(테스트).

    Returns:
        ``{"confirmed": [...], "skipped": [...]}`` — 이미 처리된 건은 skipped.

    Raises:
        FulfillmentError: 링크가 없거나 네이버 호출이 실패했을 때.
    """
    stamp = now or now_utc_naive()
    links = _links_of_group(session, link_id)
    _claim_guard(session, links, action="confirm", stamp=stamp)
    _cancel_guard(session, links, action="confirm", stamp=stamp)
    # 컬럼(place_order_status)도 함께 본다 — 판매자센터에서 손으로 발주확인한 형제를
    # 다시 보내면 네이버가 그 건을 실패로 돌려주고, 정상인데 빨간 띠가 남는다.
    # (발송처리 쪽 not_confirmed 판정은 이미 둘을 함께 본다.)
    todo = [row for row in links
            if not (_state(row).get("place_confirmed_at")
                    or (row.place_order_status or "").strip().upper()
                    in CONFIRMED_PLACE_STATUSES)]
    # 이미 발주확인이 끝난 건에 낡은 실패 사유가 남아 있으면 지운다. 판매자센터에서 손으로
    # 처리한 집은 우리 재전송이 성공할 일이 없어, 안 지우면 빨간 띠가 영구히 남는다
    # (예전에는 재전송 성공이 지워 주던 자가치유 경로다).
    healed = False
    for row in links:
        if row in todo:
            continue
        if str(_state(row).get("last_error") or "").strip():
            _write_state(row, {"last_error": "", "last_error_at": "", "last_error_action": ""})
            healed = True
    if healed:
        session.flush()
    if not todo:
        return {"confirmed": [], "skipped": [row.external_id for row in links]}

    ids = [str(row.external_id) for row in todo]
    by_id = {str(row.external_id): row for row in todo}
    try:
        response = client.confirm_place_orders(ids)
    except Exception as exc:  # noqa: BLE001 - 사유를 상태에 남기고 그대로 올린다
        _mark_failures(by_id, {pid: str(exc)[:500] for pid in ids},
                       action="confirm", stamp=stamp)
        session.flush()
        logger.warning("[NAVER] 발주확인 실패 link=%s: %s", link_id, exc)
        raise FulfillmentError(f"발주확인에 실패했습니다: {exc}") from exc

    ok_ids, failures = _split_result(response, ids)
    _mark_failures(by_id, failures, action="confirm", stamp=stamp)
    for pid in ok_ids:
        row = by_id[pid]
        _write_state(row, {"place_confirmed_at": stamp.isoformat(),
                           "place_confirmed_by": actor_user_id,
                           "last_error": "", "last_error_at": "", "last_error_action": ""})
        # 화면 필터가 보는 사본도 같이 올린다(다음 스윕을 기다리지 않게).
        row.place_order_status = "OK"
    session.flush()
    if failures:
        # 성공분은 위에서 확정했다 — 워커가 이 예외에서 commit 하므로 그 표식은 남고,
        # 재시도는 실패한 상품주문만 다시 보낸다.
        logger.warning("[NAVER] 발주확인 부분 실패 link=%s 실패=%d", link_id, len(failures))
        detail = "; ".join(f"{pid}: {reason}" for pid, reason in failures.items())
        raise FulfillmentError(f"발주확인 일부가 실패했습니다: {detail}")
    logger.info("[NAVER] 발주확인 완료 link=%s 건수=%d", link_id, len(ok_ids))
    return {"confirmed": ok_ids, "skipped": [row.external_id for row in links if row not in todo]}


def clear_failure(session: Session, *, link_id: int,
                  actor_user_id: Optional[int] = None,
                  now: Optional[datetime] = None) -> dict[str, Any]:
    """한 집의 **실패 사유만** 지운다 (네이버를 부르지 않는다 — web 에서 돌아도 된다).

    실패 사유는 성공한 재시도가 지운다. 그런데 사람이 판매자센터에서 손으로 해결하거나
    네이버가 "이미 처리됨"으로 답하면 우리 쪽 기록은 영원히 남아, 화면 위 빨간 띠가
    모든 탭·모든 사용자에게 고정된다. 그 띠를 사람이 닫는 자리가 여기다.

    **성공 표식(``place_confirmed_at``·``dispatched_at``)은 건드리지 않는다** — 지우면
    멱등이 깨져 네이버를 두 번 부르게 된다. 누가 언제 닫았는지는 상태에 남긴다.

    Args:
        session: DB 세션(호출자가 commit 을 소유한다).
        link_id: 기준 링크 id(같은 집 전체가 함께 지워진다 — 형제가 남으면 띠가 다시 뜬다).
        actor_user_id: 닫은 사람(기록용).
        now: 시각 주입(테스트).

    Returns:
        ``{"cleared": 지운 상품주문 수, "link_ids": [...]}``.

    Raises:
        FulfillmentError: 링크를 찾을 수 없을 때.
    """
    stamp = now or now_utc_naive()
    links = _links_of_group(session, link_id)
    cleared = 0
    for row in links:
        if not str(_state(row).get("last_error") or "").strip():
            continue
        _write_state(row, {"last_error": "", "last_error_at": "", "last_error_action": "",
                           "failure_cleared_at": stamp.isoformat(),
                           "failure_cleared_by": actor_user_id})
        cleared += 1
    session.flush()
    logger.info("[NAVER] 실패 기록 지움 link=%s 건수=%d", link_id, cleared)
    return {"cleared": cleared, "link_ids": [row.id for row in links]}


def dispatch_order(session: Session, client: Any, *, link_id: int,
                   delivery_method: str = DIRECT_DELIVERY,
                   actor_user_id: Optional[int] = None,
                   now: Optional[datetime] = None) -> dict[str, Any]:
    """한 집을 발송처리한다 (WORKER 실행).

    Args:
        session: DB 세션(호출자가 commit 을 소유한다).
        client: 커머스API 클라이언트.
        link_id: 기준 링크 id.
        delivery_method: 배송방법 코드(기본 자사 직접 전달).
        actor_user_id: 누른 사람(기록용).
        now: 시각 주입(테스트).

    Returns:
        ``{"dispatched": [...], "skipped": [...]}``.

    Raises:
        FulfillmentError: 링크가 없거나 (신규 집인데) 발주확인 전이거나 네이버 호출이
            실패했을 때.
    """
    stamp = now or now_utc_naive()
    links = _links_of_group(session, link_id)
    _claim_guard(session, links, action="dispatch", stamp=stamp)
    _cancel_guard(session, links, action="dispatch", stamp=stamp)
    # 관계 판정은 **집 단위**다(화면 배지와 같은 규칙). 붙이기가 집 전체를 함께 붙이지만
    # 백필 전 데이터는 형제 일부만 값이 있어, 한 건만 보면 화면과 서버가 갈린다.
    # **all** 이다: attach 이후 수집된 형제는 server_default 'NEW' 로 들어와 관계가 섞인다.
    # any 로 두면 그 NEW 형제까지 발주확인 없이 발송된다(2026-08-23 리뷰 F7).
    close_now = bool(links) and all(
        (row.relation or "").upper() in CLOSE_NOW_RELATIONS for row in links)
    # 신규 주문은 발주확인이 먼저다 — 실제 출고 전 발송처리는 구매자에게 "배송 시작"으로
    # 보이고 구매확정·정산 시계를 먼저 돌린다. 추가결제·재결제는 물건이 따로 나가지 않아
    # 확인 뒤 바로 닫는다(D1) — 네이버도 발송처리에서 발주확인을 함께 처리한다.
    not_confirmed = [] if close_now else [
        row for row in links
        if not (_state(row).get("place_confirmed_at")
                or (row.place_order_status or "").upper() == "OK")]
    if not_confirmed:
        # 거절도 화면에 닿아야 한다 — web 은 enqueue 만 하고 이미 "요청했습니다"로 답했다.
        # 사유는 **막힌 건에만** 찍는다. 집 전체에 찍으면 이미 발주확인이 끝난 형제까지
        # 실패 목록에 집혀(_failure_rows) 멀쩡한 건이 빨갛게 뜬다.
        reason = "발주확인이 먼저입니다(발주확인 전 상품주문이 있습니다)."
        _mark_failures({str(row.external_id): row for row in not_confirmed},
                       {str(row.external_id): reason for row in not_confirmed},
                       action="dispatch", stamp=stamp)
        session.flush()
        raise FulfillmentError(reason)

    todo = [row for row in links if not _state(row).get("dispatched_at")]
    if not todo:
        return {"dispatched": [], "skipped": [row.external_id for row in links]}

    ids = [str(row.external_id) for row in todo]
    by_id = {str(row.external_id): row for row in todo}
    payload = [{"productOrderId": pid,
                "deliveryMethod": delivery_method,
                "dispatchDate": _dispatch_timestamp(stamp)}
               for pid in ids]
    try:
        response = client.dispatch_product_orders(payload)
    except Exception as exc:  # noqa: BLE001
        _mark_failures(by_id, {pid: str(exc)[:500] for pid in ids},
                       action="dispatch", stamp=stamp)
        session.flush()
        logger.warning("[NAVER] 발송처리 실패 link=%s: %s", link_id, exc)
        raise FulfillmentError(f"발송처리에 실패했습니다: {exc}") from exc

    ok_ids, failures = _split_result(response, ids)
    _mark_failures(by_id, failures, action="dispatch", stamp=stamp)
    for pid in ok_ids:
        _write_state(by_id[pid], {"dispatched_at": stamp.isoformat(),
                                  "dispatched_by": actor_user_id,
                                  "delivery_method": delivery_method,
                                  "last_error": "", "last_error_at": "",
                                  "last_error_action": ""})
    session.flush()
    if failures:
        logger.warning("[NAVER] 발송처리 부분 실패 link=%s 실패=%d", link_id, len(failures))
        detail = "; ".join(f"{pid}: {reason}" for pid, reason in failures.items())
        raise FulfillmentError(f"발송처리 일부가 실패했습니다: {detail}")
    logger.info("[NAVER] 발송처리 완료 link=%s 건수=%d", link_id, len(ok_ids))
    return {"dispatched": ok_ids,
            "skipped": [row.external_id for row in links if row not in todo]}


def record_task_failure(session: Session, *, link_id: int, action: str, reason: str,
                        now: Optional[datetime] = None) -> None:
    """워커가 서비스 **바깥에서** 죽었을 때 사유를 남긴다(클라이언트 생성 실패·인증 만료 등).

    web 은 enqueue 뒤 즉시 "요청했습니다"로 답한다. 서비스가 남기는 실패 사유가 유일한
    통지 경로인데, `FulfillmentError` 가 아닌 예외는 워커가 rollback 해서 아무 흔적이
    없었다 — 특히 취소는 재시도 버튼도 없다(2026-08-23 리뷰). 실패해도 조용하지 않게 한다.

    Args:
        session: DB 세션(호출자가 commit 을 소유한다).
        link_id: 기준 링크 id.
        action: ``confirm`` / ``dispatch`` / ``cancel``.
        reason: 사람에게 그대로 보여줄 사유 문장.
        now: 시각 주입(테스트).
    """
    stamp = now or now_utc_naive()
    try:
        links = _links_of_group(session, link_id)
    except FulfillmentError:
        return
    _mark_failures({str(row.external_id): row for row in links},
                   {str(row.external_id): str(reason)[:500] for row in links},
                   action=action, stamp=stamp)


def cancel_order(session: Session, client: Any, *, link_id: int, reason: str,
                 detail: Optional[str] = None, actor_user_id: Optional[int] = None,
                 now: Optional[datetime] = None) -> dict[str, Any]:
    """한 집을 **판매자 직접취소** 한다 (WORKER 실행, 스펙 §3.4).

    네이버 취소는 상품주문 1건씩이라(배치 없음) 집을 돌며 부른다. 한 건이 실패해도 나머지는
    계속 부른다 — 반쪽만 취소된 채 사람이 사유를 못 보는 상태가 제일 나쁘다.

    **FOMS 주문은 건드리지 않는다.** 네이버 쪽만 취소한다. 주문 취소는 주문 화면의 일이고,
    두 곳에서 상태를 쓰면 SSOT 가 갈린다.

    Args:
        session: DB 세션(호출자가 commit 을 소유한다).
        client: 커머스API 클라이언트.
        link_id: 기준 링크 id(같은 집 전체가 함께 처리된다).
        reason: 취소 사유 코드(:data:`CANCEL_REASONS` 안의 값).
        detail: 취소 상세 사유(선택, 500자).
        actor_user_id: 누른 사람(기록용).
        now: 시각 주입(테스트).

    Returns:
        ``{"canceled": [...], "skipped": [...]}``.

    Raises:
        FulfillmentError: 링크가 없거나, 사유 코드가 목록 밖이거나, 이미 발송처리한
            집이거나, 클레임이 도는 집이거나, 네이버 호출이 실패했을 때.
    """
    stamp = now or now_utc_naive()
    code = str(reason or "").strip().upper()
    if code not in CANCEL_REASONS:
        # 네이버가 모르는 코드는 400 으로 돌아온다. 되돌릴 수 없는 경로라 호출 전에 막는다.
        raise FulfillmentError(f"취소 사유 코드가 올바르지 않습니다 ({reason}).")

    links = _links_of_group(session, link_id)
    _claim_guard(session, links, action="cancel", stamp=stamp)

    # 발송처리가 나간 집은 취소가 아니라 반품 흐름이다(네이버도 거절한다).
    dispatched = [row for row in links if _state(row).get("dispatched_at")]
    if dispatched:
        reason_text = ("이미 발송처리한 집입니다 — 취소가 아니라 반품으로 처리해야 합니다"
                       "(판매자센터).")
        _mark_failures({str(row.external_id): row for row in dispatched},
                       {str(row.external_id): reason_text for row in dispatched},
                       action="cancel", stamp=stamp)
        session.flush()
        raise FulfillmentError(reason_text)

    todo = [row for row in links if not _state(row).get("canceled_at")]
    if not todo:
        return {"canceled": [], "skipped": [row.external_id for row in links]}

    ok_ids: list[str] = []
    failures: dict[str, str] = {}
    by_id = {str(row.external_id): row for row in todo}
    for pid, row in by_id.items():
        try:
            response = client.request_cancel_product_order(pid, reason=code, detail=detail)
        except Exception as exc:  # noqa: BLE001 - 사유 문장을 그대로 사람에게 보여준다
            logger.warning("[NAVER] 취소 실패 link=%s po=%s: %s", link_id, pid, exc)
            failures[pid] = str(exc)[:500]
            continue
        # 커머스API 는 HTTP 200 안에 건별 실패를 담는다 — 발주확인·발송처리와 같은 파서를 쓴다.
        succeeded, failed = _split_result(response, [pid])
        failures.update(failed)
        ok_ids.extend(succeeded)

    for pid in ok_ids:
        _write_state(by_id[pid], {"canceled_at": stamp.isoformat(),
                                  "canceled_by": actor_user_id,
                                  "cancel_reason": code,
                                  "cancel_detail": (detail or "")[:500],
                                  "last_error": "", "last_error_at": "",
                                  "last_error_action": ""})
    _mark_failures(by_id, failures, action="cancel", stamp=stamp)
    session.flush()
    if failures:
        logger.warning("[NAVER] 취소 부분 실패 link=%s 실패=%d", link_id, len(failures))
        detail_text = "; ".join(f"{pid}: {why}" for pid, why in failures.items())
        raise FulfillmentError(f"취소 일부가 실패했습니다: {detail_text}")
    logger.info("[NAVER] 취소 완료 link=%s 건수=%d", link_id, len(ok_ids))
    return {"canceled": ok_ids,
            "skipped": [row.external_id for row in links if row not in todo]}
