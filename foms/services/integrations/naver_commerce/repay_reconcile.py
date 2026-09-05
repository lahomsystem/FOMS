"""재결제 정리 — 붙이기와 ERP 기존 주문 처리를 **한 트랜잭션**으로 (R-3 · 2026-08-25).

왜 이 모듈이 있나
-----------------
재결제로 판명되면 담당자는 두 가지를 해야 한다: 새 집 **붙이기** · **ERP 기존 주문 처리**.
지금까지 이 둘은 서로 다른 화면·서로 다른 버튼이라, 하나만 하고 멈춘 흔적이 스테이징
실데이터에 4건 남아 있었다(#4462 · #4466 · #4485 · #4467).

2026-08-25 결정으로 **네이버 판매자 직접취소가 이 흐름에서 빠졌다**(불가역이라 시스템이
대신 눌러 줄 일이 아니다). 그 결과 남은 두 동작이 모두 우리 DB 라서 **한 트랜잭션**으로
묶인다 — 반쪽 상태가 원천적으로 안 생긴다.

두 갈래
-------
* ``SUCCEED`` 승계 — 새 집을 기존 주문에 붙이고 **주문은 그대로 둔다**.
  예약금은 **자동 반영하지 않는다**: 화면이 "넣을 금액"을 말하고 입력은 사람이 한다
  (D-1 확정). 재결제는 **바꾸고**, 추가결제는 **더한다**.
* ``DISCARD`` 취소 처리 — 기존 주문을 휴지통으로 보낸다(soft delete).
  **붙이지 않는다**(2026-08-25 사용자 확정). 붙여 놓고 그 주문을 접으면 새 집이
  휴지통에 든 주문에 묶여 ``주문 만들기`` 가 막힌다 — 사람이 되돌리기를 한 번 더
  눌러야 빠져나오는 함정이다. 새 집은 큐에 그대로 남고 사람이 새 주문을 만든다(D-2).

네이버 옛 결제는 **상태만 본다**. 이 모듈에서 네이버로 나가는 호출은 0 이다.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from models import Order

logger = logging.getLogger(__name__)

__all__ = [
    "DISCARDABLE_CLAIM_CODES",
    "RECONCILE_FORKS",
    "UNSETTLED_CLAIM_CODES",
    "ReconcileError",
    "attach_reconcile_plans",
    "build_reconcile_plan",
    "deposit_guidance",
    "discard_policy",
    "run_gate",
    "run_reconcile",
]

#: 갈래 두 개. 승계(주문 유지) / 취소 처리(휴지통).
RECONCILE_FORKS = ("SUCCEED", "DISCARD")


class ReconcileError(ValueError):
    """정리를 진행할 수 없는 상태 — 사유를 사람에게 그대로 보여준다."""


def deposit_guidance(order: Order, *, new_amount: int, relation: str) -> dict[str, Any]:
    """예약금(선금)에 **넣을 금액** — 안내만 한다 (D-1 확정).

    시스템이 넣지 않는 이유: 재결제·추가결제·부분환불이 섞이면 자동 셈이 틀리는 경우가
    생기고, 그 틀림은 ``잔금 = 출고가 − 예약금`` 공식을 타고 고객 청구로 흘러간다.
    출고가·품목은 어느 쪽이든 건드리지 않는다.

    Args:
        order: 후보(기존) 주문.
        new_amount: 새 집 전체 금액(원).
        relation: ``REPAY``(재결제) 또는 ``ADDON``(추가결제).

    Returns:
        ``{"current", "target", "verb", "sentence", "new_amount"}``.
        ``verb`` 는 ``바꾸기``/``더하기``.
    """
    from foms.services.erp_display import erp_deposit_amount_from_structured

    current = erp_deposit_amount_from_structured(order.structured_data or {}) or 0
    amount = int(new_amount or 0)
    if relation == "REPAY":
        # 옛 결제는 환불됐다 — 더하면 이중 계상이다.
        target, verb = amount, "바꾸기"
        sentence = (f"지금 값 {current:,}원 대신 {target:,}원으로 바꾸세요"
                    " (재결제라 옛 돈은 환불됐습니다).")
    else:
        # 옛 결제는 살아 있고 그 위에 더 낸 돈이다.
        target, verb = current + amount, "더하기"
        sentence = (f"지금 값 {current:,}원에 {amount:,}원을 더해"
                    f" {target:,}원으로 고치세요.")
    return {"current": int(current), "target": int(target), "verb": verb,
            "sentence": sentence, "new_amount": amount}


#: 취소 처리를 열어도 되는 **옛 결제 상태**. 유령 주문 띠와 같은 규칙이다 —
#: 붙은 네이버 집이 아예 없거나(수기 접수 주문), 네이버가 취소를 **확정**했을 때만 연다.
#: 확정 전에 접으면 취소가 거부됐을 때 살아 있어야 할 주문이 휴지통에 있다.
DISCARDABLE_CLAIM_CODES = ("", "all_done")

#: 정리 실행 **자체**를 막는 옛 결제 상태 — 네이버가 아직 확정하지 않았다.
#: 화면 i 칸이 예전부터 "확정된 뒤에 정리하세요"라고 적어 놓고도 버튼은 눌렸다
#: (2026-09-04 사용자 결정: 경고만 두지 말고 막는다).
UNSETTLED_CLAIM_CODES = ("all_pending", "all_mixed")


def run_gate(claim_code: str) -> tuple[bool, str]:
    """정리 실행을 지금 해도 되는지 — 갈래와 무관한 **공통 관문**.

    옛 결제가 확정 전이면 승계든 취소 처리든 아직 이르다. 승계도 막는 이유: 확정 전에
    붙여 두면 취소가 거부됐을 때 살아 있는 옛 결제와 새 결제가 같은 주문에 묶인 채
    남는다 — 그 상태를 푸는 경로는 되돌리기뿐이다.

    Args:
        claim_code: :func:`order_candidates.claim_aggregate_code` 가 낸 집 단위 코드.

    Returns:
        ``(실행해도 되는가, 안 되는 이유)``. 되면 이유는 빈 문자열.
    """
    if str(claim_code or "") in UNSETTLED_CLAIM_CODES:
        return False, "네이버가 아직 취소를 확정하지 않았습니다 — 확정된 뒤에 정리하세요"
    return True, ""


def discard_policy(status: str, *, claim_code: str = "") -> dict[str, Any]:
    """취소 처리(soft delete) 갈래 판정 — **유령 주문 띠와 같은 규칙**.

    2026-09-02 사용자 결정(`549a801fb`)은 단계 제한을 없애되 목록 밖은 **관리자가 사유를
    적어야** 접히게 바꿨다. 그 결정이 유령 주문 띠(:mod:`ghost_orders`)에만 반영되고 이
    모듈에는 오지 않아, 같은 상수 :data:`ghost_orders.DISCARDABLE_STATUSES` 가 두 화면에서
    다른 뜻으로 읽혔다 — 이 함수 docstring 이 "두 화면이 서로 다른 단계를 열어 주면
    담당자가 어느 쪽을 믿어야 할지 알 수 없다"고 선언해 놓고 정작 그 선언을 깨고 있었다.
    2026-09-04 사용자 결정으로 규칙을 하나로 맞춘다.

    판정 두 축을 **분리**한다:

    * **열리는가** — 옛 네이버 결제가 확정 취소됐거나 붙은 집이 아예 없을 때만 연다(돈 축).
    * **사유가 필요한가** — 접수 이후 단계는 실측 방문·치수 이력이 붙어 있어 관리자가
      왜 접는지 적어야 한다(이력 축). 잠그지는 않는다.

    Args:
        status: ``Order.status``.
        claim_code: 후보의 집 단위 클레임 코드(``naver_claim_code``).

    Returns:
        ``{"can_discard", "needs_reason", "block"}``. 열리면 ``block`` 은 빈 문자열.
    """
    from foms.services.integrations.naver_commerce.ghost_orders import DISCARDABLE_STATUSES

    code = str(claim_code or "")
    text = str(status or "")
    needs_reason = text not in DISCARDABLE_STATUSES
    if code in DISCARDABLE_CLAIM_CODES:
        return {"can_discard": True, "needs_reason": needs_reason, "block": ""}
    if code in UNSETTLED_CLAIM_CODES:
        block = "네이버가 아직 취소를 확정하지 않았습니다"
    elif code == "partial":
        block = "옛 결제가 일부만 취소됐습니다"
    else:
        block = "옛 결제가 아직 살아 있습니다"
    return {"can_discard": False, "needs_reason": needs_reason, "block": block}


def _alive_rows(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """후보 주문에 붙은 **살아 있는** 옛 네이버 집 목록(표시용).

    Args:
        candidate: 후보 dict.

    Returns:
        살아 있는 집 목록(없으면 빈 목록).
    """
    rows = candidate.get("naver_alive_rows")
    return rows if isinstance(rows, list) else []


def build_reconcile_plan(order: Order, candidate: dict[str, Any], *,
                         relation: str) -> dict[str, Any]:
    """후보 1건 · 관계 1개에 대한 **정리 계획**(화면이 그대로 읽는 사실 묶음).

    Args:
        order: 후보 주문 ORM 인스턴스(예약금·진행 단계를 읽는다).
        candidate: :func:`order_candidates.find_order_candidates` 의 행.
        relation: ``REPAY`` 또는 ``ADDON``.

    Returns:
        ``{"relation", "deposit", "can_discard", "discard_needs_reason", "discard_block",
        "can_run", "run_block", "naver_alive_rows", "naver_claim_code",
        "naver_claim_label"}``.
    """
    claim_code = candidate.get("naver_claim_code") or ""
    policy = discard_policy(candidate.get("status") or "", claim_code=claim_code)
    can_run, run_block = run_gate(claim_code)
    return {
        "relation": relation,
        "deposit": deposit_guidance(order, new_amount=candidate.get("new_amount_total") or 0,
                                    relation=relation),
        "can_discard": policy["can_discard"],
        # 접수 이후 단계는 잠그지 않는다 — 관리자가 **왜 접는지** 적으면 접힌다.
        "discard_needs_reason": policy["needs_reason"],
        "discard_block": policy["block"],
        # 갈래와 무관한 공통 관문 — 확정 전에는 승계도 실행하지 않는다.
        "can_run": can_run,
        "run_block": run_block,
        # i 단계 — 우리가 손대지 않는다. 살아 있으면 판매자센터로 안내만 한다.
        "naver_alive_rows": _alive_rows(candidate),
        # 코드·라벨을 **함께** 싣는다 — 빠뜨리면 이 화면만 옛 축(한국어 문자열 비교)을 본다.
        "naver_claim_code": candidate.get("naver_claim_code") or "",
        "naver_claim_label": candidate.get("naver_claim_label") or "",
    }


def attach_reconcile_plans(session, candidates: list[dict[str, Any]]) -> None:
    """후보 목록 각 행에 두 관계의 정리 계획을 붙인다(제자리 수정).

    관계 두 개를 **미리 다 계산해서** 싣는다 — 관계를 고를 때마다 서버로 왕복하면 상세
    pane 이 통째로 갈리는 v3 규율과 어긋나고 예약금 안내가 한 박자 늦게 뜬다.
    후보는 최대 5건이라 계산 비용이 없다.

    Args:
        session: DB 세션(읽기만 한다).
        candidates: 후보 dict 목록(제자리에서 ``reconcile`` 키가 붙는다).

    Returns:
        None.
    """
    if not candidates:
        return
    order_ids = [int(row["order_id"]) for row in candidates if row.get("order_id")]
    if not order_ids:
        return
    orders = {int(order.id): order
              for order in session.query(Order)
              .filter(Order.id.in_(order_ids)).all()}  # perf-ok: 후보 5건 batch
    for row in candidates:
        order = orders.get(int(row.get("order_id") or 0))
        if order is None:
            continue
        row["reconcile"] = {
            relation: build_reconcile_plan(order, row, relation=relation)
            for relation in ("REPAY", "ADDON")
        }


def run_reconcile(session, *, link_id: int, order_id: int, relation: str, fork: str,
                  actor_user_id: Optional[int] = None, claim_code: str = "",
                  discard_reason: str = "", actor_is_admin: bool = False) -> dict[str, Any]:
    """정리를 **한 트랜잭션 안에서** 실행한다 — 커밋은 호출자가 소유한다.

    갈래별로 무엇을 쓰는지:

    * ``SUCCEED`` — :func:`promotion.attach_link_to_order` (집 단위·멱등). 주문은 그대로.
    * ``DISCARD`` — :func:`orders.soft_delete.soft_delete_order`. **붙이지 않는다.**

    네이버로 나가는 호출은 없다.

    Args:
        session: DB 세션(호출자가 commit/rollback 을 소유한다).
        link_id: 새 집의 기준 링크 id.
        order_id: 정리 대상 기존 주문 id.
        relation: ``REPAY`` 또는 ``ADDON``.
        fork: ``SUCCEED`` 또는 ``DISCARD``.
        actor_user_id: 실행자.
        claim_code: 후보의 집 단위 클레임 코드. 확정 전이면 갈래와 무관하게 거절한다.
        discard_reason: 취소 처리 사유(접수 이후 단계에서 필수). 빈 문자열이면 없음.
        actor_is_admin: 실행자가 관리자인가. 접수 이후 단계를 접을 때만 본다.

    Returns:
        ``{"fork", "relation", "order_id", "attached", "changed", "discarded",
        "discard_reason"}`` — 감사 기록과 화면 문구가 함께 읽는 결과.

    Raises:
        ReconcileError: 갈래·관계값이 잘못됐거나, 옛 결제가 확정 전이거나, 취소 처리에
            필요한 관리자 권한·사유가 없을 때.
        PromotionError: 붙이기가 거절될 때(이미 다른 주문에 붙어 있는 경우 등).
    """
    from foms.services.integrations.naver_commerce.promotion import (
        ATTACHABLE_RELATIONS,
        attach_link_to_order,
    )
    from foms.services.orders.soft_delete import soft_delete_order

    if fork not in RECONCILE_FORKS:
        raise ReconcileError(f"알 수 없는 갈래입니다 ({fork}).")
    if relation not in ATTACHABLE_RELATIONS:
        raise ReconcileError(f"붙일 수 없는 관계입니다 ({relation}).")

    order = session.get(Order, int(order_id))
    if order is None or order.deleted_at is not None:
        raise ReconcileError(f"정리할 주문을 찾을 수 없습니다 (order {order_id}).")

    # 갈래와 무관한 공통 관문 — 화면 i 칸이 말하던 것을 서버가 실제로 막는다.
    can_run, run_block = run_gate(claim_code)
    if not can_run:
        raise ReconcileError(f"{run_block}.")

    if fork == "DISCARD":
        from foms.services.integrations.naver_commerce.ghost_orders import stage_label

        # 화면만 막으면 주소를 아는 사람이 그대로 지운다 — 서버도 같은 판정으로 거절한다.
        policy = discard_policy(order.status or "", claim_code=claim_code)
        if not policy["can_discard"]:
            raise ReconcileError(f"{policy['block']} — 승계로 정리하세요.")
        note = str(discard_reason or "").strip()[:500]
        if policy["needs_reason"]:
            # 유령 주문 띠와 같은 관문이다(2026-09-02 결정 · 2026-09-04 이 화면에 이식).
            if not actor_is_admin:
                raise ReconcileError(
                    f"{stage_label(order.status)} 단계라 실측·도면 이력이 붙어 있습니다 — "
                    "관리자만 사유를 적고 접을 수 있습니다.")
            if not note:
                raise ReconcileError(
                    "왜 접는지 한 줄 적어 주세요 — 접수 이후 단계라 실측·도면 기록이 "
                    "함께 화면에서 사라집니다.")
        reason_text = "재결제 정리 — 기존 주문 취소 처리"
        if note:
            reason_text = f"{reason_text} ({note})"
        soft_delete_order(session, order_id=int(order_id),
                          actor_user_id=int(actor_user_id or 0),
                          reason=reason_text)
        logger.info("[NAVER] 재결제 정리 취소 처리 order=%s link=%s reason=%s",
                    order_id, link_id, note or "-")
        return {"fork": fork, "relation": relation, "order_id": int(order_id),
                "attached": 0, "changed": False, "discarded": True,
                "discard_reason": note}

    attached, target_order_id, changed = attach_link_to_order(
        session, link_id=int(link_id), order_id=int(order_id), relation=relation,
        actor_user_id=actor_user_id)
    logger.info("[NAVER] 재결제 정리 승계 order=%s link=%s relation=%s (+%d)",
                target_order_id, link_id, relation, attached)
    return {"fork": fork, "relation": relation, "order_id": int(target_order_id),
            "attached": int(attached), "changed": bool(changed), "discarded": False,
            "discard_reason": ""}
