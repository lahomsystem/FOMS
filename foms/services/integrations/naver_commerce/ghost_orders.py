"""네이버 결제가 **전부 취소된** ERP 주문 찾기 — 유령 주문 (R-2 · 2026-08-25).

왜 필요한가
-----------
고객이 네이버 주문을 취소하면 ``claim_watch`` 가 그 사실을 목격해 링크에 표시하고 담당자에게
알린다. 그런데 **그 결제로 만들어진 ERP 주문은 아무도 건드리지 않는다** — 주문 상태를 자동으로
바꾸지 않는 것이 규율이기 때문이다(그 자체는 옳다: 취소가 곧 주문 폐기는 아니다).

문제는 그 다음이다. 취소 뒤 재결제가 들어오면 담당자가 새 집을 붙이지만, **재결제가 안 오면**
그 ERP 주문은 살아 있는 채로 남는다. 결제는 취소됐는데 주문은 접수 상태다.
2026-08-25 스테이징 실조회에서 그런 주문이 **3건** 나왔다(#4467 원주현 2,451,500원 ·
#4462 박선미 · #4466 강재상). **어떤 화면도 이 사실을 말하지 않는다.**

판정 기준(스펙 D-3)
-------------------
* 붙어 있는 네이버 링크가 **1건 이상**이고
* 그 링크가 **전부** 클레임(취소·반품) 상태이며
* 주문이 아직 살아 있다(``deleted_at IS NULL``).

부분 취소는 제외한다 — 일부만 취소된 주문은 정상 진행 중일 수 있고, 그걸 유령이라 부르면
띠가 거짓말을 한다.

확정 전 클레임 (2026-08-28)
---------------------------
예전에는 판정이 "``claimStatus`` 가 비어 있지 않은가" 한 비트였다. 그래서 **승인 전 취소
요청**(``CANCEL_REQUEST``)이 확정 취소와 같은 칸에 들어갔고, 템플릿이 `" 완료"` 를 덧붙여
화면은 `취소 완료` 라고 말했다. 그 목록이 곧 폐기(soft delete) 허가증이라, 아직 살아 있을
수 있는 주문에 폐기 버튼이 열렸다(운영 ``link 79`` / 주문 ``#4998``).

이제 단계(:data:`mapping.CLAIM_PHASES`)를 본다:

* ``done`` — 네이버가 확정. 폐기 버튼을 연다.
* ``requested``·``in_progress`` — 확정 전. **목록에는 남기고**(담당자가 알아야 한다)
  버튼은 잠근다.
* ``rejected`` — 거부·철회는 **주문이 살아 있다는 뜻**이라 클레임으로 세지 않는다.

**자동으로 지우지 않는다.** 목록과 근거를 내놓고 사람이 고른다.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from foms.services.integrations.naver_commerce.grouping import resolve_group_key
from foms.services.integrations.naver_commerce.mapping import (
    CLAIM_KIND_LABELS,
    CLAIM_PHASE_DONE,
    CLAIM_PHASE_PROGRESS,
    CLAIM_PHASE_REQUESTED,
    MONEY_BACK_CLAIM_KINDS,
    RELATION_LABELS,
    claim_kind,
    extract_claim,
)
from foms.services.orders.erp_policy_constants import STAGE_LABELS
from models import ExternalOrderLink, Order

logger = logging.getLogger(__name__)

__all__ = ["find_ghost_orders", "judge_order_discard", "stage_label",
           "GHOST_LIST_LIMIT", "DISCARDABLE_STATUSES", "GHOST_CLAIM_KINDS"]

#: 유령 모집단에 넣는 단계. ``rejected``(거부·철회)는 주문이 살아 있다는 뜻이라 뺀다.
GHOST_CLAIM_PHASES = (CLAIM_PHASE_DONE, CLAIM_PHASE_REQUESTED, CLAIM_PHASE_PROGRESS)

#: 유령 모집단에 넣는 **종류**. 단계만 보면 ``EXCHANGE_DONE`` 이 확정 취소와 같은 칸에
#: 들어가 살아 있는 주문에 폐기 버튼이 열린다(R-2, 2026-08-28). 이 모듈 docstring 이
#: 모집단을 "취소·반품"이라 적어 놓고 코드는 종류를 안 본 자리다.
GHOST_CLAIM_KINDS = MONEY_BACK_CLAIM_KINDS

#: 띠에서 펼쳐 보여줄 최대 건수. 더 많으면 사람이 못 훑는다(수는 배지가 말한다).
GHOST_LIST_LIMIT = 20

#: `취소 처리`(soft delete) 를 **사유 없이** 바로 열어 주는 진행 단계.
#:
#: 실측 이후 단계는 방문 기록·치수가 붙어 있어 접으면 그 이력이 화면에서 사라진다.
#: 그래서 예전에는 이 목록 **밖이면 아예 못 접게** 막았는데, 그러면 결제가 확정 취소된
#: 죽은 주문이 실측·도면 대시보드에 영원히 남는다(#5088 이 그 사례다). 재결제 짝이
#: 없으면 승계할 곳도 없다.
#:
#: **사용자 결정 2026-09-02**: 단계 제한을 없애되, 이 목록 밖은 **관리자가 사유 문장을
#: 적어야** 접힌다. 휴지통은 복구되므로 잃는 것은 없고, 남는 것은 "왜 접었나"다.
DISCARDABLE_STATUSES = ("RECEIVED",)


def _claim_of(snapshot: Any) -> tuple[str, str, str]:
    """상품주문 스냅샷의 클레임 **상태·단계·종류**.

    판정 규칙은 :func:`mapping.extract_claim` 한 곳에만 둔다 — 예전에는 이 파일이
    "비어 있지 않은가"를 따로 판정해 SSOT 밖에 술어가 한 벌 더 있었다(2026-08-28).

    Args:
        snapshot: ``ExternalOrderLink.raw_snapshot``.

    Returns:
        ``(상태 원문, 단계, 종류)``. 클레임이 없으면 전부 빈 문자열. 모르는 상태면 단계가 빈
        문자열이고, **빈 단계는 ``done`` 이 아니다**(모르면 폐기 버튼을 열지 않는다).
        종류도 같은 규율이다 — 모르는 종류는 모집단에 넣지 않는다.
    """
    if not isinstance(snapshot, dict) or not snapshot:
        return "", "", ""
    try:
        claim = extract_claim(snapshot)
    except (ValueError, TypeError, AttributeError) as exc:  # 목록 보조라 흐름을 막지 않는다
        logger.warning("[NAVER] 유령 판정 클레임 추출 실패: %s", exc)
        return "", "", ""
    return (str(claim.get("status") or "").strip(), str(claim.get("phase") or ""),
            claim_kind(claim))


def stage_label(status: Any) -> str:
    """진행 단계 코드를 **사람이 읽는 한글**로 (:data:`STAGE_LABELS` 가 정본).

    화면과 라우트 오류 문장이 ``MEASURE`` 같은 enum 을 그대로 찍어 왔다. 담당자에게
    그 낱말은 코드지 단계가 아니다 — 사용자 결정 2026-09-04.

    Args:
        status: ``Order.status``.

    Returns:
        한글 라벨. 모르는 코드는 원문 그대로(빈 값이면 빈 문자열).
    """
    text = str(status or "")
    return STAGE_LABELS.get(text, text)


def _new_bucket() -> dict[str, Any]:
    """주문 하나의 링크를 접어 담을 빈 버킷.

    Returns:
        빈 버킷 dict.
    """
    return {
        "link_count": 0, "canceled": 0, "amount_total": 0,
        "order_nos": [], "claim_labels": set(), "phases": set(), "kinds": set(),
        # 워크벤치 pane 으로 보낼 대표 링크. 띠에서 불가역 버튼을 누르게 하지
        # 않는 대신(같은 행에 휴지통 버튼과 환불 버튼이 나란히 서면 사고
        # 대기다), **판단 재료가 있는 자리로 보낸다**.
        "lead_link_id": None,
    }


def _fold_link(bucket: dict[str, Any], *, snapshot: Any, order_no: Any,
               link_id: Any) -> tuple[str, str, str]:
    """링크 한 줄을 버킷에 접는다 — 모집단 판정의 **유일한 셈법**.

    :func:`find_ghost_orders`(전 링크 스캔)와 :func:`judge_order_discard`(주문 1건)가
    이 함수 하나를 쓴다. 셈법이 두 벌이 되면 띠와 pane 이 같은 주문을 다르게 판정한다 —
    이 기능의 안전(살아 있는 추가결제 집이 있으면 모집단에서 빠진다)이 바로 그 셈법이다.

    Args:
        bucket: :func:`_new_bucket` 이 만든 버킷(제자리 수정).
        snapshot: ``ExternalOrderLink.raw_snapshot``.
        order_no: ``ExternalOrderLink.external_order_no``.
        link_id: ``ExternalOrderLink.id``.

    Returns:
        그 링크의 ``(클레임 상태 원문, 단계, 종류)``.
    """
    bucket["link_count"] += 1
    if bucket["lead_link_id"] is None:
        bucket["lead_link_id"] = int(link_id)
    claim, phase, kind = _claim_of(snapshot)
    if phase in GHOST_CLAIM_PHASES and kind in GHOST_CLAIM_KINDS:
        bucket["canceled"] += 1
        bucket["claim_labels"].add(claim)
        bucket["phases"].add(phase)
        bucket["kinds"].add(kind)
    product_order = snapshot.get("productOrder") if isinstance(snapshot, dict) else None
    if isinstance(product_order, dict):
        amount = product_order.get("totalPaymentAmount")
        if isinstance(amount, int):
            bucket["amount_total"] += amount
    text = str(order_no or "").strip()
    if text and text not in bucket["order_nos"]:
        bucket["order_nos"].append(text)
    return claim, phase, kind


def _discard_verdict(bucket: dict[str, Any], status: str) -> dict[str, Any]:
    """버킷 + 진행 단계 → **판정 3종과 표시 문구**.

    띠(:func:`find_ghost_orders`)와 pane(:func:`judge_order_discard`)이 같은 함수를 쓴다.

    판정 두 축을 분리한다(사용자 결정 2026-09-02·2026-09-04):

    * **열리는가** — 붙은 링크가 **전부** 확정 취소·반품일 때만 연다(돈 축).
    * **사유가 필요한가** — 접수 이후 단계는 관리자가 왜 접는지 적어야 한다(이력 축).
      잠그지는 않는다.

    Args:
        bucket: :func:`_fold_link` 로 접은 버킷.
        status: ``Order.status``.

    Returns:
        ``claim_kind``·``claim_phase``·``claim_text``·``can_discard``·
        ``discard_needs_reason``·``discard_block``·``status_label``.
    """
    # 반품과 취소를 한 낱말로 뭉치지 않는다 — 사람이 보는 사실이 다르다.
    # 판정 축은 ``claimType``(:func:`mapping.claim_kind`)이다. 예전에는 상태 이름
    # 접두어를 봐서 ``COLLECTING``·``COLLECT_DONE`` 이 **취소**로 떨어졌다(R-1).
    kind = CLAIM_KIND_LABELS.get(
        "RETURN" if "RETURN" in bucket["kinds"] else "CANCEL", "취소")
    phases = bucket["phases"]
    if phases == {CLAIM_PHASE_DONE}:
        claim_phase, claim_text = "done", f"{kind} 완료"
    elif CLAIM_PHASE_DONE in phases:
        claim_phase, claim_text = "mixed", f"{kind} — 확정 전 포함"
    elif phases:
        claim_phase, claim_text = "pending", f"{kind} 요청 — 확정 전"
    else:
        # 클레임이 하나도 없는 주문 — 띠에는 오지 않고 pane 에서만 온다.
        claim_phase, claim_text = "", ""
    # 붙은 링크가 **전부** 클레임일 때만 유령이다. 부분 취소는 정상 진행 중일 수 있고,
    # 살아 있는 추가결제 집이 붙어 있는 주문도 여기서 걸러진다 — 이 기능의 안전이다.
    whole = bool(bucket["link_count"]) and bucket["canceled"] == bucket["link_count"]
    # **확정된 취소에만** 폐기 버튼을 연다. 확정 전에 접으면 취소가 거부됐을 때
    # 살아 있어야 할 주문이 휴지통에 있다. 이 조건은 돈의 문제라 바뀌지 않는다.
    can_discard = whole and claim_phase == "done"
    if not whole:
        # 문장은 부르는 쪽이 사실(건수·살아 있는 집)로 다시 쓴다. 여기서는 축만 말한다.
        discard_block = "이 주문에는 아직 살아 있는 결제가 있습니다"
    elif claim_phase != "done":
        discard_block = "네이버가 아직 취소를 확정하지 않았습니다 — 확정 후에 접으세요"
    else:
        discard_block = ""
    return {
        "claim_kind": kind,
        # 단계와 **완성 문구**를 함께 낸다. 템플릿이 `" 완료"` 를 덧붙이던 시절에는
        # 확정 전 취소가 화면에서 `취소 완료` 로 읽혔다(2026-08-28).
        "claim_phase": claim_phase,
        "claim_text": claim_text,
        "can_discard": can_discard,
        # 접수 이후 단계는 접히긴 하되 **관리자가 사유를 적어야** 한다(2026-09-02).
        # 실측 방문·치수 같은 이력이 붙은 주문을 조용히 지우지 않게 하는 관문이다.
        "discard_needs_reason": status not in DISCARDABLE_STATUSES,
        "discard_block": discard_block,
        "status_label": stage_label(status),
    }


def find_ghost_orders(session, *, limit: int = GHOST_LIST_LIMIT) -> dict[str, Any]:
    """네이버 결제가 전부 취소된 살아 있는 주문 목록 (R-2).

    Args:
        session: 요청 스코프 DB 세션.
        limit: 목록에 담을 최대 건수(수는 전체를 센다).

    Returns:
        ``{"count": 전체 건수, "rows": [...]}``. 각 행은 주문 요약 + 네이버 사실 +
        ``can_discard``(취소 처리 버튼을 열지) + ``discard_block``(못 여는 이유) +
        ``discard_needs_reason``(접으려면 관리자 사유 문장이 필요한지).
    """
    rows = (
        session.query(ExternalOrderLink.order_id, ExternalOrderLink.raw_snapshot,
                      ExternalOrderLink.external_order_no, ExternalOrderLink.id)
        .filter(ExternalOrderLink.order_id.isnot(None))
        .all()
    )
    buckets: dict[int, dict[str, Any]] = {}
    for order_id, snapshot, order_no, link_id in rows:
        bucket = buckets.setdefault(int(order_id), _new_bucket())
        _fold_link(bucket, snapshot=snapshot, order_no=order_no, link_id=link_id)

    # 전부 취소된 것만 남긴다(부분 취소 제외 — 정상 진행 중일 수 있다).
    ghost_ids = [order_id for order_id, bucket in buckets.items()
                 if bucket["link_count"] and bucket["canceled"] == bucket["link_count"]]
    if not ghost_ids:
        return {"count": 0, "rows": []}

    orders = (
        session.query(Order)
        .filter(Order.id.in_(ghost_ids), Order.not_deleted_filter())  # perf-ok: id batch
        .all()
    )
    if not orders:
        return {"count": 0, "rows": []}

    views: list[dict[str, Any]] = []
    for order in orders:
        bucket = buckets[int(order.id)]
        status = str(order.status or "")
        views.append({
            "order_id": int(order.id),
            "customer_name": order.customer_name or "",
            "phone": order.phone or "",
            "status": status,
            "received_date": order.received_date or "",
            "payment_amount": order.payment_amount or 0,
            "naver_order_nos": bucket["order_nos"],
            "naver_link_count": bucket["link_count"],
            "lead_link_id": bucket["lead_link_id"],
            "naver_amount_total": bucket["amount_total"],
            **_discard_verdict(bucket, status),
        })

    # 금액 큰 것부터 — 돈이 큰 유령이 더 급하다.
    views.sort(key=lambda row: (-int(row["naver_amount_total"] or 0), -row["order_id"]))
    return {"count": len(views), "rows": views[:limit]}


def find_repay_candidate_links(session, phones: list[str]) -> dict[str, list[dict[str, Any]]]:
    """유령 주문의 전화번호로 **아직 아무 주문에도 안 붙은 집**을 찾는다 (재결제 짝 후보).

    유령 주문 옆에 "8/24 집이 큐에 대기 중" 이 함께 보이면 담당자가 그 자리에서
    재결제로 정리할지 판단할 수 있다. 실데이터 3건 중 2건(#4462·#4466)에 짝이 있었다.

    Args:
        session: DB 세션.
        phones: 유령 주문의 전화번호 목록.

    Returns:
        ``{전화번호: [{external_order_no, created_at, link_id}]}``.
    """
    from foms.services.phone_search import normalize_phone_digits

    wanted = {normalize_phone_digits(phone) for phone in phones if phone}
    wanted.discard("")
    if not wanted:
        return {}

    pairs: dict[str, list[dict[str, Any]]] = {}
    rows = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.order_id.is_(None),
                ExternalOrderLink.sync_status == "COLLECTED")
        .order_by(ExternalOrderLink.id.desc())
        .limit(500)  # perf-ok: 미연결 집만, 최신 우선
        .all()
    )
    for link in rows:
        snapshot = link.raw_snapshot if isinstance(link.raw_snapshot, dict) else {}
        product_order = snapshot.get("productOrder")
        if not isinstance(product_order, dict):
            continue
        shipping = product_order.get("shippingAddress")
        tel = normalize_phone_digits((shipping or {}).get("tel1")) if isinstance(shipping, dict) else ""
        if not tel or tel not in wanted:
            continue
        # 이미 취소된 집은 재결제 짝이 아니다 — 그것도 유령이다. 확정 전 취소도 같이
        # 뺀다(동작 불변). 거부·철회는 살아 있는 집이라 이제 후보에 남는다.
        if _claim_of(snapshot)[1] in GHOST_CLAIM_PHASES:
            continue
        seen = pairs.setdefault(tel, [])
        order_no = str(link.external_order_no or "")
        if any(row["external_order_no"] == order_no for row in seen):
            continue
        seen.append({
            "external_order_no": order_no,
            "link_id": int(link.id),
            "created_at": link.created_at,
        })
    return pairs


def attach_repay_candidates(session, ghosts: dict[str, Any]) -> None:
    """유령 목록 각 행에 재결제 짝 후보를 붙인다(제자리 수정).

    Args:
        session: DB 세션.
        ghosts: :func:`find_ghost_orders` 결과.

    Returns:
        None.
    """
    from foms.services.phone_search import normalize_phone_digits

    rows = ghosts.get("rows") or []
    if not rows:
        return
    pairs = find_repay_candidate_links(session, [row["phone"] for row in rows])
    for row in rows:
        digits = normalize_phone_digits(row["phone"]) or ""
        row["repay_candidates"] = pairs.get(digits, [])
def _alive_house_text(houses: list[dict[str, Any]]) -> str:
    """살아 있는 집 목록 → 사람이 읽는 한 토막(최대 2집 + 나머지 건수).

    Args:
        houses: ``external_order_no``·``relation``·``amount`` 를 가진 집 목록.

    Returns:
        ``"추가결제 2026...(1,082,140원)"`` 꼴. 목록이 비면 빈 문자열.
    """
    if not houses:
        return ""
    shown = [
        f"{RELATION_LABELS.get(house['relation'], '결제')} {house['external_order_no']}"
        f"({house['amount']:,}원)"
        for house in houses[:2]
    ]
    text = ", ".join(shown)
    if len(houses) > 2:
        text = f"{text} 외 {len(houses) - 2}집"
    return text


def _pair_amounts(session, order_nos: list[str]) -> dict[str, int]:
    """재결제 짝 후보 집의 **정확한 금액 합계**.

    :func:`find_repay_candidate_links` 는 최신 500행만 훑고 주문번호로 중복을 접는다 —
    거기서 금액을 세면 집이 상한에 걸려 잘렸을 때 화면이 **틀린 돈**을 말한다. 후보로
    뽑힌 주문번호만 다시 정확히 센다(후보는 많아야 몇 건이다).

    Args:
        session: DB 세션.
        order_nos: 후보 집의 네이버 주문번호 목록.

    Returns:
        ``{주문번호: 합계}``.
    """
    if not order_nos:
        return {}
    rows = (
        session.query(ExternalOrderLink.external_order_no, ExternalOrderLink.raw_snapshot)
        .filter(ExternalOrderLink.external_order_no.in_(order_nos),  # perf-ok: 후보 몇 건
                ExternalOrderLink.order_id.is_(None))
        .all()
    )
    totals: dict[str, int] = {}
    for order_no, snapshot in rows:
        product_order = snapshot.get("productOrder") if isinstance(snapshot, dict) else None
        amount = product_order.get("totalPaymentAmount") if isinstance(product_order, dict) else None
        totals[str(order_no or "")] = totals.get(str(order_no or ""), 0) + (
            amount if isinstance(amount, int) else 0)
    return totals


def judge_order_discard(session, order_id: int, *, group_key: str = "") -> dict[str, Any]:
    """**주문 하나**만 판정한다 — 워크벤치 집 pane 의 휴지통 버튼용.

    왜 따로 두는가
    --------------
    pane 은 '집' 화면이지만 휴지통은 **주문**을 접는다. pane 이 자기 축(집 단위)으로
    판정식을 새로 만들면 :func:`find_ghost_orders` 가 지키던 안전 —
    ``canceled == link_count`` 라서 살아 있는 추가결제 집이 붙어 있는 주문은 모집단에서
    자동으로 빠진다 — 이 사라진다. 그래서 셈법(:func:`_fold_link`)과 판정
    (:func:`_discard_verdict`)은 띠와 **같은 함수**를 쓰고, 이 함수가 바꾸는 것은
    조회 범위뿐이다(전 링크 스캔은 pane 마다 돌리기 무겁다).

    Args:
        session: 요청 스코프 DB 세션.
        order_id: 판정할 ERP 주문 id.
        group_key: pane 이 지금 열고 있는 집의 묶음키. **판정에는 쓰지 않는다** —
            닫힌 사유 문장이 '부분 취소'인지 '살아 있는 집 동거'인지 가르는 데만 쓴다.

    Returns:
        ``applicable``(이 주문에 클레임이 하나라도 있어 이 블록을 그릴지) ·
        ``can_discard`` · ``discard_needs_reason`` · ``discard_block`` 과
        화면이 재진술할 사실(``status_label``·``link_count``·``canceled_count``·
        ``claim_kind``·``repay_candidates``).
    """
    rows = (
        session.query(ExternalOrderLink.id, ExternalOrderLink.raw_snapshot,
                      ExternalOrderLink.external_order_no, ExternalOrderLink.group_key,
                      ExternalOrderLink.relation)
        .filter(ExternalOrderLink.order_id == int(order_id))  # perf-ok: 주문 1건
        .all()
    )
    blank = {"applicable": False, "can_discard": False, "discard_needs_reason": False,
             "discard_block": "", "repay_candidates": []}
    if not rows:
        return blank

    bucket = _new_bucket()
    alive: dict[str, dict[str, Any]] = {}
    for link in rows:
        _, phase, kind = _fold_link(bucket, snapshot=link.raw_snapshot,
                                    order_no=link.external_order_no, link_id=link.id)
        if phase in GHOST_CLAIM_PHASES and kind in GHOST_CLAIM_KINDS:
            continue
        # 살아 있는 링크(클레임이 없거나 거부·철회)는 **집 단위로** 모은다. 문장이
        # 상품주문마다 한 줄씩 나오면 사람이 몇 집인지 못 읽는다.
        house = alive.setdefault(resolve_group_key(link), {
            "external_order_no": str(link.external_order_no or ""),
            "relation": str(link.relation or "NEW"),
            "amount": 0,
        })
        product_order = (link.raw_snapshot.get("productOrder")
                         if isinstance(link.raw_snapshot, dict) else None)
        amount = product_order.get("totalPaymentAmount") if isinstance(product_order, dict) else None
        if isinstance(amount, int):
            house["amount"] += amount

    order = session.get(Order, int(order_id))
    if order is None or order.deleted_at is not None or not bucket["canceled"]:
        # 클레임이 하나도 없는 주문에는 이 블록을 그리지 않는다 — pane 마다
        # `지금은 안 됨` 버튼이 상시로 서 있으면 그 자리는 아무도 안 읽는다.
        return blank

    status = str(order.status or "")
    verdict = _discard_verdict(bucket, status)
    whole = bucket["canceled"] == bucket["link_count"]
    if not whole:
        # 여기서만 문장을 사실로 다시 쓴다. **판정은 바꾸지 않는다.**
        here = [key for key in alive if key == group_key]
        if group_key and not here:
            verdict["discard_block"] = (
                "이 주문에는 살아 있는 결제가 함께 붙어 있습니다 — 이 집만 취소됐고, "
                f"{_alive_house_text(list(alive.values()))}은 살아 있습니다")
        else:
            verdict["discard_block"] = (
                f"이 주문에는 아직 살아 있는 결제가 있습니다 — {bucket['link_count']}건 중 "
                f"{bucket['canceled']}건만 취소됐습니다. 전부 취소된 뒤에 접습니다")

    # 재결제 짝은 **열린 버튼에만** 경고로 붙인다(사용자 결정: 잠그지 않는다).
    # 닫힌 상태에서는 그릴 자리가 없으므로 조회도 하지 않는다.
    candidates: list[dict[str, Any]] = []
    if verdict["can_discard"]:
        from foms.services.phone_search import normalize_phone_digits

        pairs = find_repay_candidate_links(session, [order.phone or ""])
        candidates = pairs.get(normalize_phone_digits(order.phone or "") or "", [])
        totals = _pair_amounts(session, [row["external_order_no"] for row in candidates])
        for row in candidates:
            row["amount"] = totals.get(row["external_order_no"], 0)

    return {
        "applicable": True,
        "order_id": int(order.id),
        "customer_name": order.customer_name or "",
        "status": status,
        "link_count": bucket["link_count"],
        "canceled_count": bucket["canceled"],
        "repay_candidates": candidates,
        **verdict,
    }
