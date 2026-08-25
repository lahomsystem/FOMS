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
    "RECONCILE_FORKS",
    "ReconcileError",
    "attach_reconcile_plans",
    "build_reconcile_plan",
    "deposit_guidance",
    "discard_gate",
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


def discard_gate(status: str) -> tuple[bool, str]:
    """취소 처리(soft delete) 갈래를 열지 판정한다 (스펙 근거 ④).

    실측 이후 단계는 방문 기록·치수가 붙어 있어 접으면 그 이력이 화면에서 사라진다.
    판정 기준은 유령 주문 띠(R-2)와 **같은 상수**를 쓴다 — 두 화면이 서로 다른 단계를
    열어 주면 담당자가 어느 쪽을 믿어야 할지 알 수 없다.

    Args:
        status: ``Order.status``.

    Returns:
        ``(열 수 있는가, 못 여는 이유)``. 열 수 있으면 이유는 빈 문자열.
    """
    from foms.services.integrations.naver_commerce.ghost_orders import DISCARDABLE_STATUSES

    text = str(status or "")
    if text in DISCARDABLE_STATUSES:
        return True, ""
    return False, f"{text} 단계라 실측·도면 이력이 붙어 있습니다"


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
        ``{"relation", "deposit", "can_discard", "discard_block", "naver_alive_rows",
        "naver_claim_label"}``.
    """
    can_discard, block = discard_gate(candidate.get("status") or "")
    return {
        "relation": relation,
        "deposit": deposit_guidance(order, new_amount=candidate.get("new_amount_total") or 0,
                                    relation=relation),
        "can_discard": can_discard,
        "discard_block": block,
        # i 단계 — 우리가 손대지 않는다. 살아 있으면 판매자센터로 안내만 한다.
        "naver_alive_rows": _alive_rows(candidate),
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
                  actor_user_id: Optional[int] = None) -> dict[str, Any]:
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

    Returns:
        ``{"fork", "relation", "order_id", "attached", "changed", "discarded"}`` —
        감사 기록과 화면 문구가 함께 읽는 결과.

    Raises:
        ReconcileError: 갈래·관계값이 잘못됐거나 취소 처리가 잠긴 단계일 때.
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

    if fork == "DISCARD":
        # 화면만 막으면 주소를 아는 사람이 그대로 지운다 — 서버도 같은 상수로 거절한다.
        can_discard, block = discard_gate(order.status or "")
        if not can_discard:
            raise ReconcileError(f"{block} — 승계로 정리하세요.")
        soft_delete_order(session, order_id=int(order_id),
                          actor_user_id=int(actor_user_id or 0),
                          reason="재결제 정리 — 기존 주문 취소 처리")
        logger.info("[NAVER] 재결제 정리 취소 처리 order=%s link=%s", order_id, link_id)
        return {"fork": fork, "relation": relation, "order_id": int(order_id),
                "attached": 0, "changed": False, "discarded": True}

    attached, target_order_id, changed = attach_link_to_order(
        session, link_id=int(link_id), order_id=int(order_id), relation=relation,
        actor_user_id=actor_user_id)
    logger.info("[NAVER] 재결제 정리 승계 order=%s link=%s relation=%s (+%d)",
                target_order_id, link_id, relation, attached)
    return {"fork": fork, "relation": relation, "order_id": int(target_order_id),
            "attached": int(attached), "changed": bool(changed), "discarded": False}
