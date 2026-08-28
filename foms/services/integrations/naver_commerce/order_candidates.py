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
* 이름 + 주소 앞부분 일치 = 60 (전화가 바뀐 재주문 대비)

같은 주문이 여러 규칙에 걸리면 가장 높은 점수만 남긴다.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import or_

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

__all__ = ["find_order_candidates", "household_amount",
           "CANDIDATE_WINDOW_DAYS", "CANDIDATE_LIMIT"]

#: 후보를 찾는 기간(일). 가구는 실측·제작·시공까지 몇 달이 걸려 차액 결제가 늦게 온다.
CANDIDATE_WINDOW_DAYS = 180

#: 화면에 보여줄 최대 후보 수. 더 많으면 사람이 못 고른다.
CANDIDATE_LIMIT = 5

#: 주소 비교에 쓰는 앞부분 길이. 상세주소(동·호)는 빼고 건물까지만 본다.
ADDRESS_PREFIX_LEN = 10

#: 점수 — 값 자체보다 순서가 의미다.
SCORE_RECIPIENT_PHONE = 100
SCORE_ORDERER_PHONE = 80
SCORE_NAME_ADDRESS = 60

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


def _add_alive_row(rows: list[dict[str, Any]], external_order_no: Any, amount: int) -> None:
    """살아 있는 옛 집 하나를 주문번호로 묶어 넣는다(같은 집이면 금액만 더한다).

    Args:
        rows: 누적 목록(제자리 수정).
        external_order_no: 네이버 주문번호.
        amount: 이 상품주문 결제 금액.

    Returns:
        None.
    """
    order_no = str(external_order_no or "").strip()
    if not order_no:
        return
    for row in rows:
        if row["external_order_no"] == order_no:
            row["amount_total"] += int(amount or 0)
            row["product_order_count"] += 1
            return
    rows.append({"external_order_no": order_no, "amount_total": int(amount or 0),
                 "product_order_count": 1})


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


def _naver_facts(session, order_ids: list[int]) -> dict[int, dict[str, Any]]:
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

    Returns:
        ``{order_id: {link_count, canceled, alive, amount_total, claim_label, alive_rows,
        cancel_reasons}}``.
        ``claim_label`` 은 화면 문구다: 전부 취소 / 일부 취소 / 살아 있음 / 빈 문자열(네이버 아님).
        ``alive_rows`` 는 **살아 있는 옛 집**을 주문번호로 묶은 목록이다(R-3 안내용) —
        우리가 취소를 걸지 않으므로 "네이버에서 처리하세요" 를 말할 대상이 필요하다.
        ``cancel_reasons`` 는 중복을 뺀 사유 원문 목록이다(본품·옵션이 같은 문장을 들고 온다).
    """
    facts: dict[int, dict[str, Any]] = {}
    if not order_ids:
        return facts
    rows = (session.query(ExternalOrderLink.order_id, ExternalOrderLink.raw_snapshot,
                          ExternalOrderLink.external_order_no)
            .filter(ExternalOrderLink.order_id.in_(order_ids))  # perf-ok: 후보 5건 batch
            .all())
    for order_id, snapshot, external_order_no in rows:
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
            _add_alive_row(bucket["alive_rows"], external_order_no,
                           amount if isinstance(amount, int) else 0)
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
        # R-3: 살아 있는 옛 집 — 우리가 취소를 걸지 않으므로 "네이버에서 처리하세요" 대상.
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

    if keys["name"] and keys["address"]:
        prefix = keys["address"][:ADDRESS_PREFIX_LEN]
        # 이름으로 좁힌 뒤 주소는 파이썬에서 비교한다 — 주소 LIKE 는 인덱스가 없다.
        rows = (
            base.filter(Order.customer_name == keys["name"])
            .order_by(Order.created_at.desc())
            .limit(NAME_SCAN_CAP)
            .all()
        )
        for order in rows:
            if not (order.address or "").startswith(prefix):
                continue
            if int(order.id) not in scored:
                scored[int(order.id)] = (SCORE_NAME_ADDRESS, "이름·주소 일치")

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
