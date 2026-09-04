"""재결제 정리(R-3) — **서비스 계층** 계약 테스트 (2026-08-25).

왜 이 테스트가 있나
-------------------
재결제로 판명된 새 집을 정리하려면 담당자가 두 가지를 해야 했다: 새 집 **붙이기** ·
**기존 ERP 주문 처리**. 둘이 서로 다른 화면·서로 다른 버튼이라 하나만 하고 멈춘 반쪽
상태가 스테이징 실데이터에 4건 남아 있었다(#4462 · #4466 · #4485 · #4467).
:mod:`foms.services.integrations.naver_commerce.repay_reconcile` 이 그 둘을 **한
트랜잭션**으로 묶었다. 이 파일은 그 묶음이 말한 대로만 움직이는지를 **서비스 함수
수준**에서 못박는다(HTTP 라우트 계약은 별도 파일이 본다 — 여기서는 요청을 쏘지 않는다).

여기서 못박는 것 다섯:

1. **재결제는 바꾸고, 추가결제는 더한다.** 관계마다 예약금 셈이 다르다. 섞이면
   ``잔금 = 출고가 − 예약금`` 공식을 타고 고객 청구 금액이 틀어진다.
2. **예약금은 시스템이 쓰지 않는다.** 실행 전후로 ``structured_data['payment']['deposit']``
   이 글자 하나 안 바뀐다(D-1 확정: 화면은 "넣을 금액"을 말하고 입력은 사람이 한다).
3. **DISCARD 는 붙이지 않는다.** 붙여 놓고 그 주문을 접으면 새 집이 휴지통에 든 주문에
   묶여 ``주문 만들기`` 가 막힌다 — 사람이 되돌리기를 한 번 더 눌러야 빠져나오는
   함정이다(2026-08-25 D-2 확정). 이번 설계의 핵심 결정이라 회귀하면 안 된다.
4. **취소 처리는 접수(RECEIVED) 단계에서만** 열린다. 화면뿐 아니라 서버도 거절한다.
5. **커밋은 호출자 소유다.** 서비스는 flush 까지만 하므로, 호출 뒤 ``rollback()`` 이면
   아무것도 남지 않는다(라우트가 커밋 1회를 책임진다 = 반쪽 상태 원천 차단).
"""

from __future__ import annotations

from typing import Any, Optional

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_display import erp_deposit_amount_from_structured
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import group_key_text
from foms.services.integrations.naver_commerce.order_candidates import find_order_candidates
from foms.services.integrations.naver_commerce.repay_reconcile import (
    ReconcileError,
    attach_reconcile_plans,
    deposit_guidance,
    discard_policy,
    run_gate,
    run_reconcile,
)
from models import ExternalOrderLink, Order, User

_SEQ = [0]


def _uid() -> str:
    """테스트 안에서만 유일한 짧은 일련번호(``external_id`` 유니크 제약용)."""
    _SEQ[0] += 1
    return f"{_SEQ[0]:04d}"


def _actor() -> int:
    """실행자 계정 1개를 만든다.

    ``actor_user_id`` 는 REV-00 receipt 의 ``users.id`` FK 로 흘러간다 — 0 같은 가짜 id 는
    SQLite 에서만 통과하고 PG 레인에서 터진다. 항상 실제 행을 만들어 쓴다.
    """
    user = User(username=f"recon_{_uid()}", password=generate_password_hash("pw"),
                role="ADMIN", team="CS", name="정리 담당", is_active=True)
    db_session.add(user)
    db_session.commit()
    return int(user.id)


def _order(*, tel: str, status: str = "RECEIVED",
           deposit: Optional[int] = None,
           address: str = "서울 강남구 테헤란로 152 101동 1001호") -> Order:
    """후보(기존) 주문 1건. ``deposit`` 을 주면 예약금이 이미 들어간 주문이 된다."""
    structured: dict[str, Any] = {}
    if deposit is not None:
        structured = {"payment": {"deposit": deposit}}
    order = Order(received_date="2026-08-01", customer_name=f"김고객{_uid()}", phone=tel,
                  erp_phone_digits=tel.replace("-", ""), address=address,
                  product="붙박이장", status=status, payment_amount=0,
                  structured_data=structured)
    db_session.add(order)
    db_session.commit()
    return order


def _link(*, order_no: str, amount: int, tel: str, claim: str = "",
          order_id: Optional[int] = None,
          base: str = "서울 강남구 테헤란로 152",
          detail: str = "101동 1001호") -> ExternalOrderLink:
    """수집 링크 1건.

    ``order_no``/``tel``/주소가 같으면 **한 집**이다(``group_key`` 규칙과 동일) — 붙이기가
    형제까지 통째로 움직이는지 보려면 이 셋을 맞춰야 한다.
    """
    external_id = f"PO-RC-{_uid()}"
    product_order: dict[str, Any] = {
        "productOrderId": external_id,
        "productName": "로라 무몰딩 1cm",
        "totalPaymentAmount": amount,
        "shippingAddress": {"name": "이수취", "tel1": tel,
                            "baseAddress": base, "detailedAddress": detail},
    }
    if claim:
        product_order["claimStatus"] = claim
    snapshot = {"order": {"orderId": order_no, "ordererTel": tel},
                "productOrder": product_order}
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             external_order_no=order_no, raw_snapshot=snapshot,
                             group_key=group_key_text(snapshot),
                             sync_status="LINKED" if order_id else "COLLECTED",
                             order_id=order_id)
    db_session.add(link)
    db_session.commit()
    return link


def _candidate_for(link: ExternalOrderLink, order_id: int) -> dict[str, Any]:
    """이 링크의 후보 목록에서 대상 주문 행을 집어 온다."""
    rows = [row for row in find_order_candidates(db_session, link)
            if row["order_id"] == order_id]
    assert rows, "후보 매칭이 안 됐다 — 전화번호가 어긋났는지 확인하라"
    return rows[0]


# --------------------------------------------------------------------------------------
# ① 예약금 안내 — 재결제는 바꾸고, 추가결제는 더한다
# --------------------------------------------------------------------------------------

def test_repay_replaces_the_current_deposit(app):
    """재결제는 **바꾸기**다 — 옛 돈은 환불됐으니 더하면 이중 계상이다."""
    order = _order(tel="010-7310-0001", deposit=500_000)

    guide = deposit_guidance(order, new_amount=1_610_780, relation="REPAY")

    assert guide["current"] == 500_000
    assert guide["target"] == 1_610_780, "재결제인데 옛 예약금이 더해졌다(이중 계상)"
    assert guide["verb"] == "바꾸기"
    assert guide["new_amount"] == 1_610_780
    assert "1,610,780" in guide["sentence"]


def test_addon_adds_on_top_of_the_current_deposit(app):
    """추가결제는 **더하기**다 — 옛 결제는 살아 있고 그 위에 더 낸 돈이다."""
    order = _order(tel="010-7310-0002", deposit=500_000)

    guide = deposit_guidance(order, new_amount=120_000, relation="ADDON")

    assert guide["current"] == 500_000
    assert guide["target"] == 620_000, "추가결제인데 새 금액으로 덮어썼다(옛 결제 증발)"
    assert guide["verb"] == "더하기"
    assert "620,000" in guide["sentence"]


def test_deposit_guidance_reads_zero_when_the_order_has_none(app):
    """예약금이 아직 없는 주문은 현재값 0 이다 — 안내 문장이 ``None`` 으로 깨지면 안 된다."""
    order = _order(tel="010-7310-0003")  # structured_data = {}

    repay = deposit_guidance(order, new_amount=300_000, relation="REPAY")
    addon = deposit_guidance(order, new_amount=300_000, relation="ADDON")

    assert repay["current"] == 0 and addon["current"] == 0
    assert repay["target"] == 300_000
    assert addon["target"] == 300_000
    assert repay["verb"] == "바꾸기" and addon["verb"] == "더하기"


# --------------------------------------------------------------------------------------
# ② 취소 처리 갈래 — 유령 주문 띠와 **같은 규칙**(2026-09-04 정책 동기화)
# --------------------------------------------------------------------------------------

def test_discard_opens_when_no_naver_household_is_linked(app):
    """붙은 네이버 집이 아예 없으면 연다 — 수기 접수 주문을 재결제로 갈아탈 때다."""
    policy = discard_policy("RECEIVED", claim_code="")

    assert policy["can_discard"] is True
    assert policy["needs_reason"] is False
    assert policy["block"] == ""


def test_discard_opens_when_naver_cancel_is_settled(app):
    """네이버가 취소를 확정했으면 연다."""
    policy = discard_policy("RECEIVED", claim_code="all_done")

    assert policy["can_discard"] is True
    assert policy["block"] == ""


@pytest.mark.parametrize("code", ["all_pending", "all_mixed", "partial", "alive"])
def test_discard_closes_until_the_old_payment_is_settled(app, code):
    """옛 결제가 확정 취소되기 전에는 잠근다 — **돈이 걸린 축**이라 단계보다 위다.

    확정 전에 접으면 취소가 거부됐을 때 살아 있어야 할 주문이 휴지통에 있다.
    """
    policy = discard_policy("RECEIVED", claim_code=code)

    assert policy["can_discard"] is False
    assert policy["block"], "왜 못 접는지 화면이 말할 문장이 없다"


@pytest.mark.parametrize("status", ["MEASURE", "DRAWING", "PRODUCTION", "COMPLETED"])
def test_stage_no_longer_locks_but_demands_a_reason(app, status):
    """접수 이후 단계는 **잠기지 않고 사유를 요구한다**(2026-09-02 결정을 이 화면에 이식).

    예전에는 이 단계들이 완전 잠금이었다. 그 결과 유령 주문 띠는 사유를 적으면 접히는데
    정리 계획 카드는 아예 못 접어, 같은 상수가 두 화면에서 다른 뜻으로 읽혔다.
    """
    policy = discard_policy(status, claim_code="all_done")

    assert policy["can_discard"] is True, "단계가 아직도 잠금 축이다"
    assert policy["needs_reason"] is True, "이력이 붙은 단계인데 사유를 안 받는다"


# --------------------------------------------------------------------------------------
# ②' 정리 실행 공통 관문 — 확정 전에는 승계도 막는다
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("code", ["all_pending", "all_mixed"])
def test_run_gate_blocks_until_naver_settles(app, code):
    """확정 전에는 갈래와 무관하게 막는다 — 화면 i 칸이 하던 말을 서버가 지킨다."""
    can_run, block = run_gate(code)

    assert can_run is False
    assert "확정" in block


@pytest.mark.parametrize("code", ["", "alive", "partial", "all_done"])
def test_run_gate_allows_the_rest(app, code):
    """확정 전이 아닌 상태는 실행을 막지 않는다 — 승계는 되돌릴 수 있다."""
    can_run, block = run_gate(code)

    assert can_run is True
    assert block == ""


# --------------------------------------------------------------------------------------
# ③ 후보에 붙는 정리 계획 — 관계 두 개를 미리 다 싣는다
# --------------------------------------------------------------------------------------

def test_reconcile_plans_carry_both_relations(app):
    """후보 행 하나에 REPAY·ADDON 계획이 **둘 다** 실린다.

    관계를 고를 때마다 서버로 왕복하면 상세 pane 이 통째로 갈리고 예약금 안내가 한 박자
    늦게 뜬다 — 그래서 미리 두 벌을 계산해 싣는다.
    """
    order = _order(tel="010-7310-0010", deposit=500_000)
    fresh = _link(order_no="N-RC-PLAN", amount=1_610_780, tel="010-7310-0010")

    candidates = find_order_candidates(db_session, fresh)
    attach_reconcile_plans(db_session, candidates)

    row = next(item for item in candidates if item["order_id"] == int(order.id))
    plans = row["reconcile"]
    assert set(plans) == {"REPAY", "ADDON"}
    assert plans["REPAY"]["relation"] == "REPAY"
    assert plans["ADDON"]["relation"] == "ADDON"
    assert plans["REPAY"]["can_discard"] is True, "접수 단계인데 취소 처리가 잠겼다"
    assert plans["REPAY"]["discard_block"] == ""


def test_the_two_plans_do_not_collapse_into_one_number(app):
    """두 관계의 ``deposit.target`` 이 서로 달라야 한다.

    같아지면 화면에서 **관계 구분이 사라진다** — 담당자가 무엇을 고르든 같은 숫자를 보고
    넣게 되고, 재결제/추가결제 판정이 무의미해진다.
    """
    order = _order(tel="010-7310-0011", deposit=500_000)
    fresh = _link(order_no="N-RC-DIFF", amount=1_610_780, tel="010-7310-0011")

    candidates = find_order_candidates(db_session, fresh)
    attach_reconcile_plans(db_session, candidates)

    plans = next(item for item in candidates
                 if item["order_id"] == int(order.id))["reconcile"]
    assert plans["REPAY"]["deposit"]["target"] == 1_610_780
    assert plans["ADDON"]["deposit"]["target"] == 2_110_780
    assert (plans["REPAY"]["deposit"]["target"]
            != plans["ADDON"]["deposit"]["target"]), "관계 구분이 사라졌다"


def test_reconcile_plans_ask_for_a_reason_after_measure(app):
    """실측 단계 후보는 계획에 **사유 요구 표식**을 달고 실린다(화면 재진술의 근거).

    잠기지는 않는다 — 2026-09-04 정책 동기화로 단계는 잠금 축에서 빠졌다.
    """
    order = _order(tel="010-7310-0012", status="MEASURE", deposit=200_000)
    fresh = _link(order_no="N-RC-LOCK", amount=400_000, tel="010-7310-0012")

    candidates = find_order_candidates(db_session, fresh)
    attach_reconcile_plans(db_session, candidates)

    plan = next(item for item in candidates
                if item["order_id"] == int(order.id))["reconcile"]["REPAY"]
    assert plan["can_discard"] is True, "단계가 아직도 잠금 축이다"
    assert plan["discard_needs_reason"] is True
    assert plan["can_run"] is True, "붙은 집이 없는데 실행이 막혔다"


# --------------------------------------------------------------------------------------
# ④ 승계(SUCCEED) — 집 통째로 붙이고, 커밋은 하지 않는다
# --------------------------------------------------------------------------------------

def test_succeed_attaches_the_whole_household(app):
    """한 집은 통째로 움직인다 — 대표 1건만 붙으면 형제(옵션)가 미아가 된다."""
    actor = _actor()
    order = _order(tel="010-7310-0020", deposit=300_000)
    order_id = int(order.id)
    main = _link(order_no="N-RC-HOUSE", amount=1_022_900, tel="010-7310-0020")
    sibling = _link(order_no="N-RC-HOUSE", amount=587_880, tel="010-7310-0020")
    main_id, sibling_id = int(main.id), int(sibling.id)

    result = run_reconcile(db_session, link_id=main_id, order_id=order_id,
                           relation="REPAY", fork="SUCCEED", actor_user_id=actor)

    assert result["fork"] == "SUCCEED"
    assert result["discarded"] is False
    assert result["attached"] == 2, "형제 링크가 안 따라왔다(미아 발생)"
    assert result["changed"] is True
    assert db_session.get(ExternalOrderLink, main_id).order_id == order_id
    assert db_session.get(ExternalOrderLink, sibling_id).order_id == order_id
    assert db_session.get(ExternalOrderLink, sibling_id).relation == "REPAY"


def test_run_reconcile_does_not_commit(app):
    """커밋은 호출자(라우트) 소유다 — 서비스가 커밋하면 반쪽 상태가 다시 생긴다.

    호출 뒤 ``rollback()`` 만으로 붙이기가 통째로 되돌아가야 한다.
    """
    actor = _actor()
    order = _order(tel="010-7310-0021", deposit=300_000)
    order_id = int(order.id)
    link = _link(order_no="N-RC-NOCOMMIT", amount=770_000, tel="010-7310-0021")
    link_id = int(link.id)

    run_reconcile(db_session, link_id=link_id, order_id=order_id,
                  relation="REPAY", fork="SUCCEED", actor_user_id=actor)
    assert db_session.get(ExternalOrderLink, link_id).order_id == order_id

    db_session.rollback()

    assert db_session.get(ExternalOrderLink, link_id).order_id is None, \
        "서비스가 스스로 커밋했다 — 롤백이 붙이기를 못 걷어낸다"


def test_succeed_never_writes_the_deposit(app):
    """붙이기가 예약금을 자동 반영하지 않는다 (D-1).

    붙이기는 ``structured_data`` 를 건드린다(출처 표식·추가결제 기록). 그 김에 예약금까지
    건드리면 잔금 = 출고가 − 예약금 을 타고 고객 청구가 틀어진다 — 숫자는 **안내만** 한다.
    """
    actor = _actor()
    order = _order(tel="010-7310-0022", deposit=500_000)
    order_id = int(order.id)
    link = _link(order_no="N-RC-DEPOSIT", amount=1_610_780, tel="010-7310-0022")
    before = erp_deposit_amount_from_structured(order.structured_data or {})
    assert before == 500_000

    run_reconcile(db_session, link_id=int(link.id), order_id=order_id,
                  relation="REPAY", fork="SUCCEED", actor_user_id=actor)

    refreshed = db_session.get(Order, order_id)
    # 붙이기가 JSONB 를 **실제로 다시 썼다**는 것부터 확인한다 — 아무것도 안 쓰였다면
    # 아래 예약금 검증이 저절로 참이 돼 계약을 못 지킨다.
    assert refreshed.structured_data["pricing"]["extra_payments"], \
        "추가결제 기록이 안 남았다 — 이 테스트가 헛돌고 있다"
    assert refreshed.structured_data["payment"]["deposit"] == 500_000, \
        "서비스가 예약금을 자동으로 고쳤다 — 사람 입력 원칙(D-1) 위반"
    assert erp_deposit_amount_from_structured(refreshed.structured_data) == before


# --------------------------------------------------------------------------------------
# ⑤ 취소 처리(DISCARD) — soft delete 하고 **붙이지 않는다**
# --------------------------------------------------------------------------------------

def test_discard_soft_deletes_the_order(app):
    """취소 처리는 soft delete 다 — 행은 남고 ``deleted_at`` 만 찍힌다(휴지통 복구)."""
    actor = _actor()
    order = _order(tel="010-7310-0030", deposit=400_000)
    order_id = int(order.id)
    link = _link(order_no="N-RC-DISCARD", amount=980_000, tel="010-7310-0030")

    result = run_reconcile(db_session, link_id=int(link.id), order_id=order_id,
                           relation="REPAY", fork="DISCARD", actor_user_id=actor)

    assert result["discarded"] is True
    assert result["attached"] == 0
    refreshed = db_session.get(Order, order_id)
    assert refreshed is not None, "hard delete 됐다 — 휴지통 복구가 불가능해진다"
    assert refreshed.deleted_at, "deleted_at 이 안 찍혔다"


def test_discard_never_attaches_the_link(app):
    """**이번 설계의 핵심 결정** — 취소 처리 갈래는 링크를 붙이지 않는다 (D-2).

    붙여 놓고 그 주문을 접으면 새 집이 휴지통에 든 주문에 묶여 ``주문 만들기`` 가 막힌다.
    사람이 되돌리기를 한 번 더 눌러야 빠져나오는 함정이라, 새 집은 큐에 그대로 남긴다.
    """
    actor = _actor()
    order = _order(tel="010-7310-0031", deposit=400_000)
    order_id = int(order.id)
    link = _link(order_no="N-RC-KEEPQ", amount=980_000, tel="010-7310-0031")
    sibling = _link(order_no="N-RC-KEEPQ", amount=120_000, tel="010-7310-0031")
    link_id, sibling_id = int(link.id), int(sibling.id)

    run_reconcile(db_session, link_id=link_id, order_id=order_id,
                  relation="REPAY", fork="DISCARD", actor_user_id=actor)

    assert db_session.get(ExternalOrderLink, link_id).order_id is None, \
        "취소 처리인데 링크가 붙었다 — 휴지통 주문에 묶여 큐에서 사라진다"
    assert db_session.get(ExternalOrderLink, sibling_id).order_id is None
    assert db_session.get(ExternalOrderLink, link_id).sync_status == "COLLECTED"


def test_discard_never_writes_the_deposit(app):
    """취소 처리 갈래도 예약금을 건드리지 않는다 — 접힌 주문의 숫자를 바꿀 이유가 없다."""
    actor = _actor()
    order = _order(tel="010-7310-0032", deposit=750_000)
    order_id = int(order.id)
    link = _link(order_no="N-RC-DDEP", amount=1_200_000, tel="010-7310-0032")

    run_reconcile(db_session, link_id=int(link.id), order_id=order_id,
                  relation="REPAY", fork="DISCARD", actor_user_id=actor)

    refreshed = db_session.get(Order, order_id)
    assert refreshed.structured_data["payment"]["deposit"] == 750_000


# --------------------------------------------------------------------------------------
# ⑥ 거절 — 잘못된 입력·잠긴 단계
# --------------------------------------------------------------------------------------

def test_unknown_fork_is_refused(app):
    """모르는 갈래는 실행 전에 막는다 — 오타 하나가 주문을 지우면 안 된다."""
    actor = _actor()
    order = _order(tel="010-7310-0040")
    link = _link(order_no="N-RC-FORK", amount=100_000, tel="010-7310-0040")

    with pytest.raises(ReconcileError) as caught:
        run_reconcile(db_session, link_id=int(link.id), order_id=int(order.id),
                      relation="REPAY", fork="DELETE", actor_user_id=actor)

    assert "DELETE" in str(caught.value)
    assert db_session.get(ExternalOrderLink, int(link.id)).order_id is None


def test_unattachable_relation_is_refused(app):
    """``NEW`` 는 붙이기가 아니라 주문 생성 경로다 — 이 함수로 들어오면 거절한다."""
    actor = _actor()
    order = _order(tel="010-7310-0041")
    link = _link(order_no="N-RC-REL", amount=100_000, tel="010-7310-0041")

    with pytest.raises(ReconcileError) as caught:
        run_reconcile(db_session, link_id=int(link.id), order_id=int(order.id),
                      relation="NEW", fork="SUCCEED", actor_user_id=actor)

    assert "NEW" in str(caught.value)
    assert db_session.get(ExternalOrderLink, int(link.id)).order_id is None


def test_discard_is_refused_after_measure(app):
    """화면만 막으면 주소를 아는 사람이 그대로 지운다 — 서버도 같은 상수로 거절한다."""
    actor = _actor()
    order = _order(tel="010-7310-0042", status="MEASURE", deposit=200_000)
    order_id = int(order.id)
    link = _link(order_no="N-RC-LOCKED", amount=300_000, tel="010-7310-0042")

    with pytest.raises(ReconcileError) as caught:
        run_reconcile(db_session, link_id=int(link.id), order_id=order_id,
                      relation="REPAY", fork="DISCARD", actor_user_id=actor)

    assert "MEASURE" in str(caught.value)
    assert not db_session.get(Order, order_id).deleted_at


# --------------------------------------------------------------------------------------
# ⑦ 살아 있는 옛 집 — 우리가 취소를 걸지 않으므로 "네이버에서 처리하세요" 대상
# --------------------------------------------------------------------------------------

def test_alive_rows_group_one_house_into_one_line(app):
    """본품·옵션이 따로 들어와도 **집 하나 = 한 줄**이고 금액은 합산된다.

    상품주문 단위로 늘어놓으면 담당자가 같은 집을 여러 건으로 읽고, 네이버 판매자센터에서
    무엇을 취소해야 하는지 못 고른다.
    """
    order = _order(tel="010-7310-0050", deposit=100_000)
    order_id = int(order.id)
    _link(order_no="N-RC-OLD-A", amount=1_022_900, tel="010-7310-0050", order_id=order_id)
    _link(order_no="N-RC-OLD-A", amount=587_880, tel="010-7310-0050", order_id=order_id)
    fresh = _link(order_no="N-RC-NEW-A", amount=1_610_780, tel="010-7310-0050")

    rows = _candidate_for(fresh, order_id)["naver_alive_rows"]

    assert len(rows) == 1, "집 하나가 두 줄로 갈라졌다"
    assert rows[0]["external_order_no"] == "N-RC-OLD-A"
    assert rows[0]["amount_total"] == 1_610_780
    assert rows[0]["product_order_count"] == 2
    # 행은 그 집을 **가리킬 수 있어야** 한다 — 화면이 취소·반품을 그 집 pane 으로 보낸다
    # (NVREPAY-01). 예전에는 주문번호·금액·건수만 남기고 식별자를 버렸다.
    assert rows[0]["link_id"], "옛 집을 가리킬 link_id 가 없다"
    assert len(rows[0]["product_order_ids"]) == 2


def test_canceled_links_are_not_alive_rows(app):
    """취소된 옛 집은 **살아 있는 목록에 들어오지 않는다**.

    이미 죽은 결제를 "네이버에서 취소하세요" 대상으로 내밀면 담당자가 판매자센터에서
    헛걸음한다 — 재결제 판정의 근거(옛 결제가 취소됐는가)와도 어긋난다.
    """
    order = _order(tel="010-7310-0051", deposit=100_000)
    order_id = int(order.id)
    _link(order_no="N-RC-DEAD", amount=900_000, tel="010-7310-0051",
          claim="CANCEL_DONE", order_id=order_id)
    _link(order_no="N-RC-LIVE", amount=250_000, tel="010-7310-0051", order_id=order_id)
    fresh = _link(order_no="N-RC-NEW-B", amount=1_150_000, tel="010-7310-0051")

    candidate = _candidate_for(fresh, order_id)
    numbers = [row["external_order_no"] for row in candidate["naver_alive_rows"]]

    assert numbers == ["N-RC-LIVE"], "취소된 집이 '살아 있음'으로 새어 들어왔다"
    assert candidate["naver_claim_label"] == "일부 취소"
