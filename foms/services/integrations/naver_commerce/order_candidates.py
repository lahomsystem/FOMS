"""수집분에 대응하는 **기존 주문 후보**를 찾는다 (NAVER-INGEST-02 T16-C).

왜 필요한가
-----------
수집 판정은 ``productOrderStatus == PAYED`` 하나뿐이라 세 가지가 전부 "새 집"으로 들어온다:
신규 주문 / 취소 후 **재결제** / 기존 주문의 **차액 결제**(30cm·1cm 상품을 금액 맞춰 구매).
셋을 구분하지 못하면 CS 가 "주문 만들기"를 눌러 **중복 주문**을 만든다(스테이징 실데이터에
같은 고객 2회 4명, 소액 단독 집 2개가 이미 있다).

**자동으로 붙이지 않는다.** 돈과 시공이 걸린 판단이라 시스템은 후보와 근거만 제시하고,
확정은 사람이 한다(2026-08-19 사용자 확정: 옵션 귀속과 같은 원칙).

매칭 규칙
---------
전화번호는 digits 로 정규화해서 본다(``erp_phone_digits`` 는 P1-02 검색용 인덱스 컬럼이라
그대로 재사용한다). 주문자와 수취인이 다른 대리주문이 실재하므로 **둘 다** 본다.

점수는 신뢰도 순이다:

* 수취인 전화 일치 = 100 (가장 강한 단서)
* 주문자 전화 일치 = 80
* 이름 + 주소 일치 = 60 (전화가 바뀐 재주문 대비)
* 수령인명만 일치 = 40 (주소까지 바뀐 재주문 대비 — 동명이인 가능, 사람이 고른다)

주소는 글자 그대로 견주지 않는다. 네이버는 ``서울특별시 성북구 화랑로48길 16 (석관동,
두산아파트) 110동 2403호`` 처럼 공식 전체 표기를 주고 사람은 ``성북구 화랑로48길 16,
두산아파트 110동 2403호`` 로 입력해서, 같은 집인데 글자가 다르다.
:func:`foms.services.common.address_query.match_key` 로 양쪽을 접어 견준다(공용 SSOT —
두 벌로 두면 한쪽만 고쳐지는 날 두 화면이 다른 집을 짚는다).

같은 주문이 여러 규칙에 걸리면 가장 높은 점수만 남긴다.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import or_

from foms.services.common.address_query import match_key as address_match_key
from foms.services.datetime_kst import now_utc_naive
from foms.services.integrations.naver_commerce.mapping import (
    CLAIM_PHASE_DONE,
    CLAIM_PHASE_PROGRESS,
    CLAIM_PHASE_REQUESTED,
    MONEY_BACK_CLAIM_KINDS,
)
from foms.services.phone_search import normalize_phone_digits
from models import ExternalOrderLink, Order

logger = logging.getLogger(__name__)

__all__ = ["find_order_candidates", "household_amount", "origin_facts",
           "pending_origin_cleanup", "search_orders_for_attach",
           "CANDIDATE_WINDOW_DAYS", "CANDIDATE_LIMIT", "ORIGIN_CLEANUP_LIMIT",
           "SEARCH_LIMIT", "SEARCH_MIN_LEN"]

#: 후보를 찾는 기간(일). 가구는 실측·제작·시공까지 몇 달이 걸려 차액 결제가 늦게 온다.
CANDIDATE_WINDOW_DAYS = 180

#: 화면에 보여줄 최대 후보 수. 더 많으면 사람이 못 고른다.
CANDIDATE_LIMIT = 5

#: 주소 비교는 :func:`foms.services.common.address_query.match_key` 로 접어서 견준다.
#: 앞 10자 ``startswith`` 를 쓰던 시절의 결함: 네이버는 ``서울특별시 …`` 전체 표기를 주고
#: 사람은 ``성북구 …`` 로 입력해, 같은 집인데 접두가 통째로 어긋났다(운영 링크 243건 중
#: 수령인명이 맞는 224건에서 119건만 통과 — 2026-09-01 진단).

#: 정리 대기 띠에 실을 최대 집 수(NVREPAY-02). 넘으면 잘라내고 **잘랐다고 말한다** —
#: 조용한 절단은 "이게 전부"로 읽힌다.
ORIGIN_CLEANUP_LIMIT = 20

#: 찾아서 붙이기(T2) 검색 결과 상한. 후보 표(5)보다 넓다 — 사람이 낱말로 좁힐 수 있으니
#: 조금 더 보여 주고, 넘치면 **넘쳤다고 말한다**(조용한 절단은 "이게 전부"로 읽힌다).
SEARCH_LIMIT = 10

#: 검색어 최소 길이. 한 글자(성씨 `김`)는 주문 전체를 훑는 것과 같다.
SEARCH_MIN_LEN = 2

#: SQL 후보 상한. 화면은 ``SEARCH_LIMIT`` 만 보지만, 잘렸는지 알려면 한 건 더 읽어야 한다.
SEARCH_SCAN_CAP = 60

#: 점수 — 값 자체보다 순서가 의미다.
SCORE_RECIPIENT_PHONE = 100
SCORE_ORDERER_PHONE = 80
SCORE_NAME_ADDRESS = 60
#: 수령인명만 맞고 주소는 다른 경우. 동명이인을 만날 수 있어 **가장 약한 단서**다 —
#: 그래도 보여 준다: 안 보여 주면 사람이 "기존 주문 없음"으로 읽고 중복 주문을 만든다.
SCORE_NAME_ONLY = 40

#: 후보 스캔 상한. 이름+주소 규칙은 인덱스가 이름까지만 걸려 후보가 많아질 수 있다.
NAME_SCAN_CAP = 200


def _snapshot_keys(raw_snapshot: Any) -> dict[str, str]:
    """원본에서 매칭 키(수취인/주문자 전화·이름·주소)를 뽑는다.

    Args:
        raw_snapshot: ``ExternalOrderLink.raw_snapshot``.

    Returns:
        ``{"recipient_phone", "orderer_phone", "name", "address"}`` — digits 정규화 완료.
        읽을 수 없으면 전부 빈 문자열.
    """
    empty = {"recipient_phone": "", "orderer_phone": "", "name": "", "address": ""}
    if not isinstance(raw_snapshot, dict) or not raw_snapshot:
        return empty
    try:
        from foms.services.integrations.naver_commerce.mapping import (
            build_address,
            unwrap_detail,
        )

        order, _product_order, shipping = unwrap_detail(raw_snapshot)
    except (ValueError, TypeError, AttributeError) as exc:  # 표시용 보조라 흐름을 막지 않는다
        logger.warning("[NAVER] 후보 매칭 키 추출 실패: %s", exc)
        return empty
    return {
        "recipient_phone": normalize_phone_digits(shipping.get("tel1")) or "",
        "orderer_phone": normalize_phone_digits((order or {}).get("ordererTel")) or "",
        "name": str(shipping.get("name") or "").strip(),
        "address": build_address(shipping or {}),
    }


def household_amount(session, link: ExternalOrderLink) -> int:
    """이 집(같은 ``group_key``)의 상품주문 금액 합 — 후보와 견줄 **새 금액**.

    네이버는 본품과 옵션을 각각 다른 상품주문으로 주므로 링크 한 건의 금액으로 견주면
    항상 작게 나온다(실데이터: 재결제 집 6건 중 대표 1건만 보면 1,022,900 vs 실제 1,610,780).

    Args:
        session: DB 세션.
        link: 기준 수집 링크.

    Returns:
        집 전체 금액 합(원). 원본이 없으면 0.
    """
    key = link.group_key or link.external_order_no
    if not key:
        return 0
    column = ExternalOrderLink.group_key if link.group_key else ExternalOrderLink.external_order_no
    rows = (session.query(ExternalOrderLink.raw_snapshot)
            .filter(ExternalOrderLink.channel == link.channel, column == key)
            .all())
    total = 0
    for (snapshot,) in rows:
        if not isinstance(snapshot, dict):
            continue
        product_order = snapshot.get("productOrder")
        if not isinstance(product_order, dict):
            continue
        amount = product_order.get("totalPaymentAmount")
        if isinstance(amount, int):
            total += amount
    return total


def _merge_read_at(current: str, incoming: str) -> str:
    """집 안에서 **가장 오래된** 조회 시각을 남긴다.

    화면이 이 값으로 "이 상태는 언제 읽은 것"이라고 말한다. 낙관적으로 고르면 안 된다 —
    형제 중 한 건만 최근에 읽혔어도 집 전체가 최신인 것처럼 보이면, 정작 취소가 나갈
    다른 건은 낡은 값 위에서 나간다.

    Args:
        current: 지금까지 누적된 값(빈 문자열이면 없음).
        incoming: 새로 합칠 값(빈 문자열이면 없음).

    Returns:
        둘 다 있으면 더 이른 쪽, 하나만 있으면 그것.
    """
    if not current:
        return incoming
    if not incoming:
        return current
    return min(current, incoming)


def _return_pending(raw_snapshot: Any, triage_state: Any) -> bool:
    """이 상품주문에 **반품 접수가 실제로 나갈** 것인가 — 서버 술어를 그대로 부른다.

    띠는 ORM 인스턴스가 아니라 투영 행(스냅샷·상태 두 칸)만 들고 있다. 그렇다고 조건을
    여기 손으로 다시 적으면 `request_return` 과 갈린다 — 갈리는 순간 띠 모달이
    "상품주문 2건을 반품 접수합니다"라고 말하고 서버는 1건만 보낸다(불가역 경로의 과대
    진술). 술어는 :func:`fulfillment.is_return_pending` 한 벌이고, 그 함수가 읽는 것은
    ``raw_snapshot``·``triage_state`` 두 속성뿐이라 얇은 대역 객체로 그대로 통과한다
    (`naver_ingest._ThinLink` 와 같은 수법).

    Args:
        raw_snapshot: ``ExternalOrderLink.raw_snapshot``.
        triage_state: ``ExternalOrderLink.triage_state``.

    Returns:
        반품 접수 대상이면 True.
    """
    from types import SimpleNamespace

    from .fulfillment import is_return_pending

    return is_return_pending(SimpleNamespace(raw_snapshot=raw_snapshot,
                                             triage_state=triage_state))


def _add_alive_row(rows: list[dict[str, Any]], *, link_id: int, external_order_no: Any,
                   external_id: Any, amount: int, dispatched: bool,
                   return_pending: bool, read_at: str) -> None:
    """살아 있는 옛 집 하나를 주문번호로 묶어 넣는다(같은 집이면 금액만 더한다).

    **식별자를 함께 싣는다**(2026-08-28 NVREPAY-01). 예전에는 주문번호·금액·건수만 남기고
    ``link_id`` 와 ``external_id`` 를 버렸다. 그런데 취소·반품 라우트는 ``link_id`` 로만
    주소를 잡아서, 화면이 "옛 주문이 살아 있습니다"라고 말하면서 **그 주문을 가리킬 수는
    없었다** — 담당자는 판매자센터를 따로 열어 주문번호로 찾아 들어가고 있었다.
    ``link_id`` 는 집 대표 1건이면 충분하다. 옛 집 pane 이 ``_group_of_link`` 로 형제
    전체를 다시 모으기 때문이다.

    ``dispatched`` 는 **취소냐 반품이냐**를 가른다(발송 전은 취소, 발송 후는 반품).
    집 안에서 하나라도 나갔으면 집 전체를 발송으로 본다 — 서버 가드가 부분 발송 집의
    취소를 집 단위로 거절하므로(``fulfillment.cancel_order``) 화면이 그와 같은 축으로
    말해야 한다.

    Args:
        rows: 누적 목록(제자리 수정).
        link_id: 이 상품주문의 링크 id(집 대표로 첫 건만 남는다).
        external_order_no: 네이버 주문번호(집 키).
        external_id: 네이버 상품주문번호(productOrderId).
        amount: 이 상품주문 결제 금액.
        dispatched: 이 상품주문이 발송 처리됐는가.
        return_pending: 이 상품주문에 **반품 접수가 실제로 나갈** 것인가
            (:func:`fulfillment.is_return_pending` — 나갔고 아직 우리가 접수 안 한 건).
            띠 모달이 "몇 건이 나가는가"를 이 수로만 말한다.
        read_at: 이 링크를 네이버에서 **마지막으로 읽은** 시각(ISO, naive UTC).

    Returns:
        None.
    """
    order_no = str(external_order_no or "").strip()
    if not order_no:
        return
    product_order_id = str(external_id or "").strip()
    for row in rows:
        if row["external_order_no"] == order_no:
            row["amount_total"] += int(amount or 0)
            row["product_order_count"] += 1
            if product_order_id and product_order_id not in row["product_order_ids"]:
                row["product_order_ids"].append(product_order_id)
            row["dispatched"] = row["dispatched"] or bool(dispatched)
            row["return_pending_count"] += 1 if return_pending else 0
            row["read_at"] = _merge_read_at(row["read_at"], read_at)
            return
    rows.append({
        "link_id": int(link_id),
        "external_order_no": order_no,
        "product_order_ids": [product_order_id] if product_order_id else [],
        "amount_total": int(amount or 0),
        "product_order_count": 1,
        "dispatched": bool(dispatched),
        # 집 전체 수와 **다른 축**이다 — 분할 발송 집에서 반품이 나갈 수는 이쪽뿐이다.
        "return_pending_count": 1 if return_pending else 0,
        "read_at": read_at,
    })


#: ``claim_code`` → 화면 글자. **코드가 판정 축이고 라벨은 표시 축이다** — 템플릿이
#: 한국어 문자열을 ``==`` 로 비교하던 시절에는 라벨 한 낱말만 바꿔도 분기가 조용히 죽어
#: 취소 건이 전부 `살아 있음` 으로 떨어졌다(2026-08-28).
CLAIM_CODE_LABELS = {
    "alive": "살아 있음",
    "partial": "일부 취소",
    "all_done": "전부 취소 완료",
    "all_pending": "전부 취소 요청 — 확정 전",
    "all_mixed": "전부 취소 — 확정 전 포함",
}


def _claim_facts(raw_snapshot: Any) -> dict[str, str]:
    """스냅샷 1건에서 **클레임 단계와 사유 원문**을 꺼낸다.

    추출 규칙은 :func:`mapping.extract_claim` 한 곳에만 둔다 — 같은 값을 두 벌로 읽으면
    pane 위쪽(F-1)과 후보 표가 서로 다른 문장을 말하게 된다. 예전에는 이 함수가 사유
    원문만 꺼내고 ``phase``·``status`` 를 버려서, 정작 판정은 "claimStatus 가 비어 있지
    않은가" 한 비트로 따로 돌았다(2026-08-28 결함).

    Args:
        raw_snapshot: ``ExternalOrderLink.raw_snapshot``.

    Returns:
        ``{"phase": 단계, "kind": 종류, "detailed_reason": 사유 원문}``. 읽을 수 없으면
        전부 빈 문자열 (**빈 값은 화면이 줄을 안 내고, 빈 단계는 취소로 세지 않는다**).
    """
    empty = {"phase": "", "kind": "", "detailed_reason": ""}
    if not isinstance(raw_snapshot, dict) or not raw_snapshot:
        return empty
    try:
        from foms.services.integrations.naver_commerce.mapping import (
            claim_kind, extract_claim,
        )

        claim = extract_claim(raw_snapshot)
        return {
            "phase": str(claim.get("phase") or ""),
            "kind": claim_kind(claim),
            "detailed_reason": str(claim.get("detailed_reason") or "").strip(),
        }
    except (ValueError, TypeError, AttributeError) as exc:  # 표시용 보조라 흐름을 막지 않는다
        logger.warning("[NAVER] 후보 클레임 추출 실패: %s", exc)
        return empty


def _dispatch_facts(raw_snapshot: Any, triage_state: Any, created_at: Any) -> dict[str, Any]:
    """링크 1건의 **발송 여부와 마지막 조회 시각**을 꺼낸다 (2026-08-28 NVREPAY-01).

    발송 신호를 **둘** 본다. 우리 표식(``triage_state['fulfillment']['dispatched_at']``)은
    우리가 눌러서 나간 발송만 알고, 판매자센터에서 사람이 직접 발송처리한 집은 우리 쪽에
    흔적이 없다. 그래서 네이버 원본의 ``delivery.sendDate`` 도 함께 본다 — 서버 가드가
    이미 같은 두 신호를 보므로(:func:`fulfillment._naver_dispatched_at`), 화면이 다른 축으로
    말하면 "취소 버튼이 열려 있는데 눌렀더니 거절"이 된다.

    추출은 :func:`mapping.extract_delivery` 한 곳에만 맡긴다 — 같은 값을 두 벌로 읽으면
    화면과 서버가 갈린다.

    **``read_at`` 은 ``claim_sync.refreshed_at`` 하나가 아니다.** 그 값은 ``claim_watch`` 가
    이 링크를 **다시** 읽었을 때만 찍힌다(:mod:`claim_watch`) — 방금 수집된 링크에는 아예
    없다. 그런데 수집도 네이버를 읽은 것이고 그 시각이 ``created_at`` 이다. 둘 중 **늦은**
    쪽이 "우리가 마지막으로 네이버를 본 시각"이다. 이 구분을 놓치면 "읽은 기록 없음"이
    정상 신규 건에도 붙어서, 담당자가 그 경고를 아무 데서나 보고 무시하게 된다.
    재수집으로 스냅샷이 갱신된 경우 ``created_at`` 은 실제보다 **이르게** 잡히는데,
    신선도를 과소평가하는 방향이라 안전하다.

    Args:
        raw_snapshot: ``ExternalOrderLink.raw_snapshot``.
        triage_state: ``ExternalOrderLink.triage_state``.
        created_at: ``ExternalOrderLink.created_at`` (수집 시각).

    Returns:
        ``{"dispatched": bool, "read_at": str}``. ``read_at`` 은 ISO(naive UTC) 문자열.
    """
    state = triage_state if isinstance(triage_state, dict) else {}
    fulfillment_state = state.get("fulfillment")
    ours = ""
    if isinstance(fulfillment_state, dict):
        ours = str(fulfillment_state.get("dispatched_at") or "").strip()
    claim_state = state.get("claim_sync")
    refreshed_at = ""
    if isinstance(claim_state, dict):
        refreshed_at = str(claim_state.get("refreshed_at") or "").strip()
    collected_at = created_at.isoformat() if hasattr(created_at, "isoformat") else ""
    read_at = max(refreshed_at, collected_at) if (refreshed_at and collected_at) \
        else (refreshed_at or collected_at)

    theirs = ""
    if isinstance(raw_snapshot, dict) and raw_snapshot:
        try:
            from foms.services.integrations.naver_commerce.mapping import extract_delivery

            theirs = str(extract_delivery(raw_snapshot).get("send_date") or "").strip()
        except (ValueError, TypeError, AttributeError) as exc:  # 표시용 보조라 흐름을 막지 않는다
            logger.warning("[NAVER] 후보 발송 추출 실패: %s", exc)
    return {"dispatched": bool(ours or theirs), "read_at": read_at}


def _naver_facts(session, order_ids: list[int], *,
                 exclude_link_ids: Optional[set[int]] = None,
                 relations: Optional[tuple[str, ...]] = None) -> dict[int, dict[str, Any]]:
    """후보 주문마다 **붙어 있는 네이버 집의 사실**을 모은다 (2026-08-25 R-1).

    지금까지 화면은 링크 **개수**만 냈다. 그런데 재결제·추가결제를 가르는 결정적 신호는
    개수가 아니라 **그 결제가 취소됐는가**다(취소됐으면 재결제, 살아 있으면 추가결제).
    담당자는 그걸 확인하려고 네이버를 따로 열고 있었다.

    ``cancel_reasons`` 는 **고객이 직접 쓴 취소·반품 사유 원문**이다 (2026-08-26). 클레임
    라벨(`전부 취소`)은 *무엇이* 일어났는지만 말하고 *왜* 를 말하지 못한다. 그런데 이 표는
    재결제냐 추가결제냐를 가르는 자리이고, 실데이터의 사유 원문이 바로 그 답을 적고 있다 —
    스테이징 실측: `일시불 재결제 예정` · `취소 재결제` · `재주문예정` · `재결제` 는 재결제,
    `사이즈 재측정후 주문할께요` 는 아니다. pane 위쪽(F-1)은 **지금 수집분**의 사유를 내는데,
    판정이 실제로 일어나는 자리는 **옛 집**을 놓고 고르는 이 표라 여기까지 올린다.

    Args:
        session: DB 세션.
        order_ids: 후보 주문 id 목록.
        exclude_link_ids: 셈에서 뺄 링크 id. **지금 보고 있는 집을 빼고 옛 집만 보려고**
            쓴다(:func:`origin_facts`) — 재결제로 붙인 뒤에는 새 집도 같은 주문에 달려
            있어서, 빼지 않으면 "옛 주문이 살아 있다"가 자기 자신을 가리킨다.
        relations: 셈에 넣을 ``relation`` 값. 주면 그 값만 본다(:func:`origin_facts` 가
            ``NEW`` 만 쓴다). 후보 표는 관계를 가리지 않으므로 기본은 None 이다.

    Returns:
        ``{order_id: {link_count, canceled, alive, amount_total, claim_label, alive_rows,
        cancel_reasons}}``.
        ``claim_label`` 은 화면 문구다: 전부 취소 / 일부 취소 / 살아 있음 / 빈 문자열(네이버 아님).
        ``alive_rows`` 는 **살아 있는 옛 집**을 주문번호로 묶은 목록이다. 각 행은
        ``{link_id, external_order_no, product_order_ids, amount_total,
        product_order_count, dispatched, read_at}`` 이다 — 화면이 그 집을
        **가리키고**(``link_id``), **취소냐 반품이냐를 가르고**(``dispatched``),
        **언제 읽은 값인지 말하기**(``read_at``) 위해서다(2026-08-28 NVREPAY-01).
        ``cancel_reasons`` 는 중복을 뺀 사유 원문 목록이다(본품·옵션이 같은 문장을 들고 온다).
    """
    facts: dict[int, dict[str, Any]] = {}
    if not order_ids:
        return facts
    query = (session.query(ExternalOrderLink.order_id, ExternalOrderLink.raw_snapshot,
                           ExternalOrderLink.external_order_no, ExternalOrderLink.id,
                           ExternalOrderLink.external_id, ExternalOrderLink.triage_state,
                           ExternalOrderLink.created_at)
             .filter(ExternalOrderLink.order_id.in_(order_ids)))  # perf-ok: 후보 5건 batch
    if relations:
        query = query.filter(ExternalOrderLink.relation.in_(relations))
    rows = query.all()
    skip = exclude_link_ids or set()
    for (order_id, snapshot, external_order_no, link_id, external_id, triage_state,
         created_at) in rows:
        if int(link_id) in skip:
            continue
        bucket = facts.setdefault(int(order_id), {
            "link_count": 0, "canceled": 0, "pending": 0, "alive": 0, "amount_total": 0,
            "claim_label": "", "claim_code": "", "alive_rows": [], "cancel_reasons": [],
        })
        bucket["link_count"] += 1
        product_order = snapshot.get("productOrder") if isinstance(snapshot, dict) else None
        if not isinstance(product_order, dict):
            continue
        amount = product_order.get("totalPaymentAmount")
        if isinstance(amount, int):
            bucket["amount_total"] += amount
        # 클레임 **단계**로 가른다. 예전에는 "claimStatus 가 비어 있지 않은가" 한 비트라
        # 승인 전 취소(CANCEL_REQUEST)와 취소 **거부**(CANCEL_REJECT — 주문은 살아 있다)가
        # 확정 취소와 같은 칸에 들어갔다(2026-08-28).
        # 종류도 본다. 교환은 **돈이 되돌아가지 않는다** — 대체품을 보내야 하는 살아 있는
        # 결제인데 `EXCHANGE_DONE` 이 `done` 이라는 이유로 `전부 취소 완료` 로 세어졌다
        # (R-2, 2026-08-28). 유령 목록과 **같은 술어**를 쓴다.
        phase = _claim_facts(snapshot)
        if (phase["phase"] in (CLAIM_PHASE_DONE, CLAIM_PHASE_REQUESTED, CLAIM_PHASE_PROGRESS)
                and phase["kind"] in MONEY_BACK_CLAIM_KINDS):
            if phase["phase"] == CLAIM_PHASE_DONE:
                bucket["canceled"] += 1
            else:
                bucket["pending"] += 1
            # 왜 취소했는지는 고객이 써 놨다. 본품·옵션이 같은 문장을 각각 들고 오므로
            # 중복은 뺀다 — 같은 말을 세 번 늘어놓으면 표가 읽히지 않는다.
            reason = phase["detailed_reason"]
            if reason and reason not in bucket["cancel_reasons"]:
                bucket["cancel_reasons"].append(reason)
        else:
            # 거부·철회·클레임 없음은 전부 **살아 있는 결제**다.
            bucket["alive"] += 1
            # 상품주문 단위가 아니라 **집** 단위로 말한다 — 본품·옵션이 따로 들어와
            # 건별로 늘어놓으면 담당자가 같은 집을 여러 건으로 읽는다.
            dispatch = _dispatch_facts(snapshot, triage_state, created_at)
            _add_alive_row(bucket["alive_rows"], link_id=int(link_id),
                           external_order_no=external_order_no, external_id=external_id,
                           amount=amount if isinstance(amount, int) else 0,
                           dispatched=dispatch["dispatched"],
                           return_pending=_return_pending(snapshot, triage_state),
                           read_at=dispatch["read_at"])
    for bucket in facts.values():
        if not bucket["link_count"]:
            continue
        done, pending, alive = bucket["canceled"], bucket["pending"], bucket["alive"]
        if alive and (done or pending):
            code = "partial"
        elif not done and not pending:
            code = "alive"
        elif done and pending:
            code = "all_mixed"
        elif pending:
            code = "all_pending"
        else:
            code = "all_done"
        bucket["claim_code"] = code
        bucket["claim_label"] = CLAIM_CODE_LABELS[code]
    return facts


def origin_facts(session, order_id: Any, *, exclude_link_ids: set[int],
                 since_at: Any = None) -> dict[str, Any]:
    """붙인 뒤에도 **옛 네이버 주문**의 사실을 낸다 (2026-08-28 NVREPAY-01).

    재결제를 주문에 붙이고 나면 화면에서 옛 결제 정보가 통째로 사라졌다 — 후보 표는
    `아직 안 붙은 집` 갈래에서만 렌더되기 때문이다. 그런데 담당자가 옛 주문을 취소·반품해야
    하는 시점은 **붙인 다음**이다. 그래서 같은 사실을 관계 블록에서 다시 쓸 수 있게 연다.

    지금 보고 있는 집은 빼고 센다. 빼지 않으면 "옛 주문이 살아 있습니다"가 방금 붙인
    새 결제 자신을 가리킨다.

    **``NEW`` 집만 본다**(2026-08-28 운영 실데이터에서 잡은 결함). 한 주문에는 재결제
    말고 **추가결제(ADDON)** 도 함께 붙어 있을 수 있다. 그건 차액만 더 받은 살아 있는
    결제이지 **대체된 옛 주문이 아니다.** 관계를 안 가렸더니 운영 주문 #4854 에서
    배송 중인 25,000원 추가결제를 "옛 주문이 살아 있습니다 — 반품으로 처리하세요"로
    지목했다. 판정 축은 도크와 같다 — ``superseded = has_repay and relation == "NEW"``
    (:func:`dock._household_facts`).

    Args:
        session: DB 세션.
        order_id: 이 수집분이 붙어 있는 FOMS 주문 id.
        exclude_link_ids: 지금 집의 링크 id 전부(형제 포함).
        since_at: 이 수집분의 수집 시각. 주면 각 행에 ``stale`` 을 채운다 —
            **새 결제를 받은 뒤로 옛 주문을 한 번도 안 읽었는가**(SPEC §5.4 R2′).

    Returns:
        ``{"link_count", "claim_code", "claim_label", "alive_rows", "stale_any"}``.
        붙은 주문이 없거나 **``NEW`` 집이 없으면** ``link_count == 0`` — 화면은 그때
        "네이버 주문 확인 안 됨"이라고 말한다(**"없습니다"라고 말하지 않는다**).
        추가결제만 함께 붙어 있는 주문도 여기 해당하며, 그게 맞다: 대체된 옛 주문이 없다.
    """
    empty = {"link_count": 0, "claim_code": "", "claim_label": "",
             "alive_rows": [], "stale_any": False}
    try:
        oid = int(order_id)
    except (TypeError, ValueError):
        return empty
    facts = _naver_facts(session, [oid], exclude_link_ids=set(exclude_link_ids or set()),
                         relations=("NEW",))
    bucket = facts.get(oid)
    if not bucket:
        return empty
    since = since_at.isoformat() if hasattr(since_at, "isoformat") else ""
    rows = list(bucket.get("alive_rows") or [])
    stale_any = False
    for row in rows:
        # 읽은 시각이 새 결제 수집보다 이르면, 그 뒤로 이 옛 주문을 본 적이 없다는 뜻이다.
        row["stale"] = bool(since and row.get("read_at") and row["read_at"] < since)
        stale_any = stale_any or row["stale"]
    return {
        "link_count": int(bucket.get("link_count") or 0),
        "claim_code": bucket.get("claim_code") or "",
        "claim_label": bucket.get("claim_label") or "",
        "alive_rows": rows,
        "stale_any": stale_any,
    }


def pending_origin_cleanup(session, *, limit: int = ORIGIN_CLEANUP_LIMIT) -> dict[str, Any]:
    """재결제를 붙인 뒤 **아직 네이버에서 정리 안 된 옛 주문**을 전수로 모은다 (NVREPAY-02).

    :func:`origin_facts` 는 담당자가 **그 주문 pane 을 열었을 때만** 말한다. 그런데 옛
    주문을 취소·반품하지 않으면 고객은 같은 물건값을 두 번 낸 상태로 남고, 옛 주문은
    네이버에서 정산·발송이 그대로 돈다. **아무도 pane 을 안 열면 아무도 모른다** — 목록
    어디에도 그 수가 없었다. 이 함수는 그 수를 화면이 늘 말할 수 있게 한다.

    판정 술어는 pane 과 **같은 것**을 쓴다(:func:`_naver_facts` 의 ``relations=("NEW",)``).
    한 벌 더 쓰면 띠와 pane 이 다른 말을 한다. 재결제 집 자체는 관계 필터가 이미 걷어내므로
    ``exclude_link_ids`` 를 따로 넘기지 않는다.

    ``stale`` 은 **새 결제를 받은 뒤로 그 옛 주문을 한 번도 안 읽었는가**다(SPEC §5.4 R2′).
    기준 시각은 그 주문에 붙은 재결제 링크 중 **가장 늦게 수집된** 것이다 — 여러 번 붙였으면
    마지막 결제 이후를 봐야 한다.

    Args:
        session: DB 세션.
        limit: 돌려줄 최대 집 수.

    Returns:
        ``{"count", "rows", "truncated"}``. ``count`` 는 **자르기 전 전체 수**이고
        ``rows`` 는 ``{order_id, customer_name, status, link_id, external_order_no,
        amount_total, product_order_count, return_pending_count, dispatched, read_at,
        stale}`` 목록이다.
        재결제가 붙은 주문이 없거나 옛 주문이 전부 정리됐으면 ``count == 0``.
    """
    repay_rows = (session.query(ExternalOrderLink.order_id, ExternalOrderLink.created_at)
                  .filter(ExternalOrderLink.relation == "REPAY",
                          ExternalOrderLink.order_id.isnot(None))
                  .all())
    if not repay_rows:
        return {"count": 0, "rows": [], "truncated": False}
    since_by_order: dict[int, str] = {}
    for order_id, created_at in repay_rows:
        stamp = created_at.isoformat() if hasattr(created_at, "isoformat") else ""
        key = int(order_id)
        if stamp > since_by_order.get(key, ""):
            since_by_order[key] = stamp
    order_ids = sorted(since_by_order)

    facts = _naver_facts(session, order_ids, relations=("NEW",))  # perf-ok: 재결제 붙은 주문만
    pending: list[tuple[int, dict[str, Any]]] = []
    for order_id in order_ids:
        bucket = facts.get(order_id)
        if not bucket:
            continue
        since = since_by_order.get(order_id, "")
        for row in bucket.get("alive_rows") or []:
            row = dict(row)
            row["stale"] = bool(since and row.get("read_at") and row["read_at"] < since)
            pending.append((order_id, row))
    if not pending:
        return {"count": 0, "rows": [], "truncated": False}

    orders = {order.id: order for order in session.query(Order)
              .filter(Order.id.in_({oid for oid, _row in pending})).all()}  # perf-ok: 소수 batch
    rows = []
    # 손이 급한 것부터 — 미확인(stale)이 위, 그다음 최근 주문.
    for order_id, row in sorted(pending, key=lambda item: (not item[1]["stale"], -item[0])):
        order = orders.get(order_id)
        rows.append({
            "order_id": order_id,
            "customer_name": getattr(order, "customer_name", "") or "",
            "status": getattr(order, "status", "") or "",
            "link_id": row.get("link_id"),
            "external_order_no": row.get("external_order_no"),
            "amount_total": int(row.get("amount_total") or 0),
            "product_order_count": int(row.get("product_order_count") or 0),
            # 반품이 **실제로 나갈** 건수(2026-09-02). 집 전체 수로 모달을 쓰면 분할 발송
            # 집에서 과대 진술이 된다 — 술어는 서버와 한 벌(`is_return_pending`).
            "return_pending_count": int(row.get("return_pending_count") or 0),
            "dispatched": bool(row.get("dispatched")),
            "read_at": row.get("read_at") or "",
            "stale": bool(row.get("stale")),
        })
    return {"count": len(rows), "rows": rows[:limit], "truncated": len(rows) > limit}


def _order_view(order: Order, *, score: int, reason: str,
                link_count: int, facts: Optional[dict[str, Any]] = None,
                new_amount: int = 0) -> dict[str, Any]:
    """후보 1건을 화면용 dict 로 편다."""
    facts = facts or {}
    old_amount = int(facts.get("amount_total") or 0)
    return {
        "order_id": int(order.id),
        "customer_name": order.customer_name,
        "phone": order.phone,
        "address": order.address,
        "product": order.product,
        "received_date": order.received_date,
        "status": order.status,
        "payment_amount": order.payment_amount,
        "score": score,
        "reason": reason,
        # 이미 네이버 수집분이 붙어 있는 주문인지(재결제·추가결제 판단에 쓰인다).
        "naver_link_count": link_count,
        # --- R-1(2026-08-25): 판정 근거 2열 ---
        # ② 이 주문에 붙은 네이버 집이 취소됐는가 — 재결제/추가결제를 가르는 결정 신호.
        # **코드가 판정 축이고 라벨은 표시 축이다** — 템플릿은 코드로만 분기한다.
        "naver_claim_code": facts.get("claim_code") or "",
        "naver_claim_label": facts.get("claim_label") or "",
        "naver_canceled_count": int(facts.get("canceled") or 0),
        # 네이버가 아직 확정하지 않은 클레임(취소 요청·처리중) 건수.
        "naver_pending_count": int(facts.get("pending") or 0),
        "naver_alive_count": int(facts.get("alive") or 0),
        # 살아 있는 옛 집 — 재결제로 붙인 뒤 **네이버에서 정리해야 할 대상**이다.
        # 행마다 ``link_id`` 를 실어 화면이 그 집 pane 으로 보낼 수 있게 한다(NVREPAY-01).
        "naver_alive_rows": list(facts.get("alive_rows") or []),
        # 고객이 쓴 사유 원문 — 라벨이 못 말하는 **왜** 를 말한다(2026-08-26).
        "naver_cancel_reasons": list(facts.get("cancel_reasons") or []),
        # ③ 금액 관계 — 집 전체끼리 견준다(대표 1건끼리 견주면 항상 작게 나온다).
        "naver_amount_total": old_amount,
        "new_amount_total": int(new_amount or 0),
        "amount_delta": int(new_amount or 0) - old_amount,
    }


def find_order_candidates(session, link: ExternalOrderLink, *,
                          limit: int = CANDIDATE_LIMIT,
                          window_days: int = CANDIDATE_WINDOW_DAYS) -> list[dict[str, Any]]:
    """이 수집분이 붙을 만한 **기존 주문 후보**를 점수순으로 돌려준다.

    자동 판정이 아니다 — 사람이 고르라고 근거와 함께 늘어놓는 것이다.

    Args:
        session: DB 세션.
        link: 기준 수집 링크(원본 스냅샷에서 매칭 키를 뽑는다).
        limit: 최대 후보 수.
        window_days: 최근 며칠 안에 접수된 주문만 볼지.

    Returns:
        후보 dict 목록(점수 내림차순, 같으면 최근 주문 먼저). 단서가 없으면 빈 목록.
    """
    keys = _snapshot_keys(link.raw_snapshot)
    if not any(keys.values()):
        return []

    since = (now_utc_naive() - timedelta(days=window_days))
    base = session.query(Order).filter(
        Order.not_deleted_filter(),
        Order.created_at >= since,
    )
    if link.order_id:
        # 이미 이 링크가 붙은 주문은 후보가 아니다(자기 자신).
        base = base.filter(Order.id != int(link.order_id))

    scored: dict[int, tuple[int, str]] = {}

    phone_terms = []
    if keys["recipient_phone"]:
        phone_terms.append((keys["recipient_phone"], SCORE_RECIPIENT_PHONE, "수취인 전화 일치"))
    if keys["orderer_phone"] and keys["orderer_phone"] != keys["recipient_phone"]:
        phone_terms.append((keys["orderer_phone"], SCORE_ORDERER_PHONE, "주문자 전화 일치"))

    for digits, score, reason in phone_terms:
        # erp_phone_digits 는 인덱스 컬럼(P1-02). phone 원문은 형식이 제각각이라 보조로만 본다.
        rows = (
            base.filter(or_(Order.erp_phone_digits == digits,
                            Order.phone == digits))
            .order_by(Order.created_at.desc())
            .limit(limit * 2)
            .all()
        )
        for order in rows:
            current = scored.get(int(order.id))
            if current is None or score > current[0]:
                scored[int(order.id)] = (score, reason)

    if keys["name"]:
        # 이름으로 좁힌 뒤 주소는 파이썬에서 비교한다 — 주소 LIKE 는 인덱스가 없다.
        rows = (
            base.filter(Order.customer_name == keys["name"])
            .order_by(Order.created_at.desc())
            .limit(NAME_SCAN_CAP)
            .all()
        )
        if len(rows) >= NAME_SCAN_CAP:
            # 캡에 닿았다 = 이 뒤로 더 있는데 안 봤다. 조용히 자르면 "이게 전부"로 읽힌다.
            logger.warning("[NAVER] 후보 이름 스캔 캡(%d) 도달 — link_id=%s name=%s",
                           NAME_SCAN_CAP, getattr(link, "id", None), keys["name"])
        link_key = address_match_key(keys["address"])
        for order in rows:
            if int(order.id) in scored:
                continue
            order_key = address_match_key(order.address)
            if link_key and order_key and link_key == order_key:
                scored[int(order.id)] = (SCORE_NAME_ADDRESS, "이름·주소 일치")
            else:
                # 주소까지 바뀐 재주문(시공지 변경·가족 대리주문)이 실재한다. 이름만으로는
                # 동명이인을 만날 수 있으므로 **점수를 낮추고 근거를 그대로 적어** 사람이
                # 고르게 한다 — 일괄 발송처리 매칭이 이미 같은 축을 쓴다
                # (:func:`bulk_dispatch.find_unlinked_matches`, 운영 규칙 2026-09-01).
                scored[int(order.id)] = (SCORE_NAME_ONLY, "수령인명만 일치")

    if not scored:
        return []

    orders = {
        int(order.id): order
        for order in session.query(Order).filter(Order.id.in_(list(scored.keys()))).all()
    }
    # 링크 개수만 세던 조회를 **사실 수집**으로 바꾼다(R-1) — 같은 1회 조회로 개수·취소
    # 여부·금액을 함께 얻는다. 후보는 최대 5건이라 스냅샷을 읽어도 부하가 늘지 않는다.
    facts = _naver_facts(session, list(scored.keys()))
    new_amount = household_amount(session, link)

    views = [
        _order_view(orders[order_id], score=score, reason=reason,
                    link_count=int(facts.get(order_id, {}).get("link_count") or 0),
                    facts=facts.get(order_id), new_amount=new_amount)
        for order_id, (score, reason) in scored.items()
        if order_id in orders
    ]
    views.sort(key=lambda row: (-row["score"], -row["order_id"]))
    return views[:limit]


def _search_reason(order: Order, *, text: str, digits: str) -> str:
    """검색 결과 1건이 **무엇으로 걸렸는지** 한 낱말로 말한다.

    자동 매칭(:func:`find_order_candidates`)의 ``reason`` 과 같은 자리를 채운다 — 표가
    같은 열을 쓰므로 값도 같은 축이어야 한다. 근거를 안 적으면 담당자가 "왜 이 주문이
    떴는지" 를 확인하려고 주문을 하나씩 열어 본다.

    Args:
        order: 검색에 걸린 주문.
        text: 사람이 입력한 낱말(공백 제거 전 원문 trim).
        digits: 그 입력에서 뽑은 숫자열(없으면 빈 문자열).

    Returns:
        ``주문번호 일치``/``전화 일치``/``이름 일치``/``주소 일치``/``검색 일치``.
    """
    if digits and str(order.id) == digits:
        return "주문번호 일치"
    order_digits = (order.erp_phone_digits or normalize_phone_digits(order.phone) or "")
    if digits and digits in order_digits:
        return "전화 일치"
    needle = text.casefold()
    if needle and needle in (order.customer_name or "").casefold():
        return "이름 일치"
    if needle and needle in (order.address or "").casefold():
        return "주소 일치"
    # 고객명·주소가 structured_data 쪽에만 있는 주문이다(ERP 주문). 억지로 축을 만들지
    # 않는다 — 어느 칸이 걸렸는지 모르면서 "이름 일치"라고 적으면 그게 거짓말이다.
    return "검색 일치"


def _search_clauses(text: str) -> tuple[list[Any], str, bool]:
    """검색어 하나에서 **SQL 술어·숫자열·너무 짧음** 판정을 만든다.

    술어는 ERP 대시보드 검색과 **같은 것**을 쓴다
    (:func:`erp_order_dashboard_search_predicate`, ``customer_contact_only=True``) —
    고객명·전화·주소만 본다. 담당자 이름·품목까지 열면 "박 대리가 담당한 주문 200건"이
    붙이기 후보로 떠서 사람이 그중 하나를 고르게 된다.

    Args:
        text: 사람이 입력한 낱말(trim 완료).

    Returns:
        ``(clauses, digits, too_short)``. ``too_short`` 면 ``clauses`` 는 비어 있고
        호출자는 **조회하지 않는다**(빈 결과와 다른 말이다).
    """
    from foms.services.erp_dashboard_search import erp_order_dashboard_search_predicate

    # 주문번호 직검색. 전화 자릿수 경로가 4자리 이상 숫자를 먼저 가로채므로(P1-02),
    # 따로 더하지 않으면 `4434` 가 자기 주문을 못 찾는다(통합검색이 같은 자리에서 데인
    # 결함이다 — foms_unified_search._order_id_prefilter). 화면이 `#1234` 로 보여 주므로
    # `#` 을 그대로 쳐도 같게 읽는다.
    bare = text.lstrip("#").strip()
    order_no = int(bare) if bare.isdigit() and len(bare) <= 10 else 0
    if not 0 < order_no <= 2_000_000_000:
        order_no = 0
    if len(text) < SEARCH_MIN_LEN and not order_no:
        # 한 글자 이름은 주문 전체를 훑는 것과 같다. **번호 한 자리는 다르다** —
        # 그건 정확 일치라 id 술어 하나로만 나간다.
        return [], "", True

    clauses: list[Any] = []
    if len(text) >= SEARCH_MIN_LEN:
        clauses.append(erp_order_dashboard_search_predicate(f"%{text}%",
                                                            customer_contact_only=True,
                                                            raw_query=text))
    if order_no:
        clauses.append(Order.id == order_no)
    return clauses, (normalize_phone_digits(text) or ""), False


def _search_views(session, link: ExternalOrderLink, orders: list[Order], *,
                  text: str, digits: str) -> list[dict[str, Any]]:
    """검색 결과 주문들을 **후보 표와 같은 모양**으로 편다.

    Args:
        session: DB 세션.
        link: 기준 수집 링크(금액 견주기의 새 금액).
        orders: 화면에 낼 주문(이미 상한만큼 잘려 있다).
        text: 사람이 친 낱말(근거 문구용).
        digits: 그 낱말의 숫자열(근거 문구용).

    Returns:
        :func:`_order_view` 결과 목록 — 각 행에 ``deposit`` 이 더 붙는다.
    """
    from foms.services.integrations.naver_commerce.repay_reconcile import deposit_guidance

    facts = _naver_facts(session, [int(order.id) for order in orders])  # perf-ok: 화면 상한만큼
    new_amount = household_amount(session, link)
    views = []
    for order in orders:
        view = _order_view(order, score=0,
                           reason=_search_reason(order, text=text, digits=digits),
                           link_count=int(facts.get(int(order.id), {}).get("link_count") or 0),
                           facts=facts.get(int(order.id)), new_amount=new_amount)
        # 예약금 안내를 **여기서도** 싣는다(D-1: 시스템이 넣지 않고 사람이 옮겨 적는다).
        # 후보 표는 정리 계획 카드가 이 숫자를 말해 주는데, 검색으로 붙이면 그 카드를
        # 안 거친다 — 안 실으면 검색 경로만 그 숫자를 잃는다. DB 조회는 없다(순수 계산).
        view["deposit"] = {
            relation: deposit_guidance(order, new_amount=new_amount, relation=relation)
            for relation in ("REPAY", "ADDON")
        }
        views.append(view)
    return views


def search_orders_for_attach(session, link: ExternalOrderLink, *, query: str,
                             limit: int = SEARCH_LIMIT) -> dict[str, Any]:
    """붙일 주문을 **사람이 직접 찾는다** — 후보 0건일 때의 진입점 (T2).

    자동 매칭은 세 축뿐이다(수취인 전화·주문자 전화·이름+주소). 재결제·추가결제가
    **다른 이름·다른 전화·다른 주소**로 들어오면 — 가족이 대신 결제했거나 시공지가
    바뀌었거나 새 번호로 샀거나 — 후보가 0건이고, 그러면 붙이기 버튼이 화면에 아예
    없다. 담당자는 새 주문을 만들고 **옛 주문은 유령이 된다**.

    막힌 것은 서버가 아니라 화면이었다: ``POST .../attach`` 는 후보 목록과 무관하게
    ``order_id`` 를 받는다. 그래서 이 함수는 **읽기 전용**이다 — 찾아서 늘어놓기만 하고,
    붙이는 것은 기존 라우트가 한다.

    Args:
        session: DB 세션.
        link: 붙일 대상 수집 링크(금액 견주기의 **새 금액** 기준).
        query: 사람이 입력한 낱말 — 이름·전화·주문번호.
        limit: 돌려줄 최대 건수.

    Returns:
        ``{"query", "rows", "truncated", "too_short"}``.
        ``rows`` 는 후보 표와 **같은 모양**이다(:func:`_order_view`) — 화면이 같은 열을
        쓰고, 같은 판정 근거(옛 결제 상태·금액 견주기)를 보여 준다.
        ``too_short`` 는 검색어가 짧아 **아예 조회하지 않았다**는 뜻이다(빈 결과와 다르다).
    """
    text = str(query or "").strip()
    empty = {"query": text, "rows": [], "truncated": False, "too_short": False}
    clauses, digits, too_short = _search_clauses(text)
    if too_short:
        empty["too_short"] = True
        return empty

    # **초안은 후보가 아니다.** 승격 전 draft 행에 집을 묶으면 주문 화면이 그 행을
    # 되살리는 레이스에 걸린다(2026-08 유령 주문 사고). 자동 후보(not_deleted)보다 좁은
    # 필터를 쓰는 이유가 이것이다 — 사람이 검색으로 부르면 draft 도 이름으로 걸린다.
    base = session.query(Order).filter(Order.active_filter(), or_(*clauses))
    if link.order_id:
        # 이미 이 링크가 붙은 주문은 붙일 대상이 아니다(자기 자신).
        base = base.filter(Order.id != int(link.order_id))
    rows = (base.order_by(Order.id.desc())
            .limit(SEARCH_SCAN_CAP)  # perf-ok: 사람이 누른 1회 검색(admin cold path)
            .all())
    if not rows:
        return empty

    # 주문번호를 그대로 친 사람에게는 **그 주문**이 첫 줄이어야 한다. 나머지는 최근 순이다
    # (검색은 점수 축이 없다 — 점수를 지어내면 자동 매칭의 100/80/60 과 뜻이 갈린다).
    exact_ids = {int(order.id) for order in rows if digits and str(order.id) == digits}
    ordered = ([order for order in rows if int(order.id) in exact_ids]
               + [order for order in rows if int(order.id) not in exact_ids])[:limit]
    return {"query": text, "rows": _search_views(session, link, ordered,
                                                 text=text, digits=digits),
            "truncated": len(rows) > len(ordered), "too_short": False}
