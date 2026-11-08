"""FCOMM-01 D31 — "내 수수료" 명세서 줄을 펼치면 보이는 주문 세부내역 + 확정 도면.

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.6 D31 · 목업
docs/design/mockups/freelancer-commission-statement-detail.html 안 A(사용자 11-08 결정: 품목 금액 보이기 · 조정 줄도 같은
세부내역 · 마감 뒤 바뀐 품목 알림 줄 · 회사 직원 "프리랜서 화면 보기"도 같게 · 도면은 FOMS 전역 모달).
이름 · 금액 · 요율은 모두 가짜 값이다(저장소 공개).
"""
from __future__ import annotations

import re
from pathlib import Path

from db import db_session
from foms.services.auth import freelancer_orders
from models import Order, OrderFreelancerLink, SalesCommissionInput
from tests.domains.test_auth_finance import _make_user
from tests.domains.test_my_commission_page import (  # noqa: F401 — closing_today 는 fixture
    MATCH,
    _client,
    _close,
    _content,
    _html,
    _seed,
    closing_today,
)

ROOT = Path(__file__).resolve().parents[2]

_ITEMS = [
    {"product_name": "가짜 안방장", "spec": "2400x2300", "color": "화이트", "quantity": 1, "price": 3_200_000},
    {"product_name": "가짜 신발장", "price": 900_000},
    {"product_name": "가짜 선반", "spec": "900", "price": 350_000, "cancel": {"at": "2030-03-01", "by": "가짜"}},
]
_DRAWINGS = [
    {"key": "orders/drawings/fake-front.png", "filename": "fake-front.png"},
    {"key": "orders/drawings/fake-inside.jpg", "filename": "fake-inside.jpg"},
    {"key": "orders/drawings/fake-sheet.pdf", "filename": "fake-sheet.pdf"},
]


def _detail_order(*, customer: str = "세부고객", drawings: list | None = None, items: list | None = None,
                  install_cost: int = 1_000_000, link_user_id: int | None = None) -> int:
    """세부내역용 주문 — 품목 3(1 취소) · 추가 50,000 · 할인 150,000 → 출고가 4,000,000."""
    sd = {
        "parties": {"manager": {"name": MATCH}, "orderer": {"name": "라홈 가짜점"}, "customer": {"name": customer}},
        "schedule": {"construction": {"date": "2030-03-12"}, "measurement": {"date": "2030-01-05"}},
        "items": items if items is not None else _ITEMS,
        "totals": {"free_input_amount": 50_000},
        "payment": {"free_input": "배송", "discount": 150_000},
        "workflow": {"stage": "CS"},
    }
    if drawings is not None:
        sd["drawing_current_files"] = drawings
    order = Order(
        received_date="2030-01-01", customer_name=customer, phone="010-0000-0000", address="가짜시",
        product="가짜 안방장", status="COMPLETED", manager_name=MATCH, is_erp_order=True, structured_data=sd,
        erp_stage_code="CS", erp_construction_date="2030-03-12", erp_measurement_date="2030-01-05",
    )
    db_session.add(order)
    db_session.commit()
    db_session.add(SalesCommissionInput(order_id=order.id, install_cost=install_cost, version=1))
    if link_user_id is not None and not db_session.query(OrderFreelancerLink).filter_by(
            order_id=order.id, user_id=link_user_id).first():
        db_session.add(OrderFreelancerLink(order_id=order.id, user_id=link_user_id, relation="MANAGER"))
    db_session.commit()
    return order.id


def _row(content: str, customer: str) -> str:
    """고객 이름이 든 줄(<li class="foms-mc__row"> … </li>) 하나."""
    start = content.index(customer)
    start = content.rindex('<li class="foms-mc__row">', 0, start)
    return content[start:content.index("</details>", start)]


def _link_all(user_id: int) -> None:
    """시드 주문을 모두 이 프리랜서와 잇는다(실제로는 저장 훅이 잇는다 — 여기서는 판정만 본다)."""
    for (oid,) in db_session.query(Order.id).all():
        if not db_session.query(OrderFreelancerLink).filter_by(order_id=oid, user_id=user_id).first():
            db_session.add(OrderFreelancerLink(order_id=oid, user_id=user_id, relation="MANAGER"))
    db_session.commit()


# --------------------------------------------------------------------------
# 품목 · 금액 · 출고가
# --------------------------------------------------------------------------
def test_expanded_row_lists_items_extras_and_shipping(app):
    world = _seed()
    fl = world["fl"]
    oid = _detail_order(drawings=_DRAWINGS, link_user_id=fl.id)
    row = _row(_content(_html(_client(app, fl))), "세부고객")

    # 품목 — 규격 · 색 · 수량 한 줄, 금액
    assert "가짜 안방장" in row and "2400x2300 · 화이트 · 1개" in row and "3,200,000" in row
    assert "가짜 신발장" in row and "900,000" in row
    # 취소 품목은 줄을 그어 남긴다
    assert "<s>가짜 선반</s>" in row and "<s>350,000</s>" in row and "900 · 취소한 품목이라 빠져요" in row
    # 추가 금액(자유 입력 글) · 할인 · 출고가 = 3,200,000 + 900,000 + 50,000 − 150,000
    assert "추가 금액" in row and "배송" in row and "+50,000" in row
    assert "할인" in row and "−150,000" in row
    assert re.search(r'is-sum"><span class="foms-mc__it-name">출고가</span><span class="foms-mc__it-won">4,000,000<', row)
    # 계산 줄은 그대로, 품목 합이 계산 줄 첫 숫자와 같다
    assert "출고가 4,000,000 − 시공비 1,000,000 − 차감 0 = 3,000,000 × 4% = 120,000원" in row
    assert f'href="/edit/{oid}"' in row and "주문 열기" in row


def test_drawings_open_in_global_viewer_and_files_in_new_tab(app):
    world = _seed()
    fl = world["fl"]
    _detail_order(drawings=_DRAWINGS, link_user_id=fl.id)
    row = _row(_content(_html(_client(app, fl))), "세부고객")

    assert 'class="foms-mc__body has-drawings"' in row
    gallery = row[row.index("data-foms-mc-drawings"):]
    pictures = re.findall(r"<a class=\"foms-mc__dw\"[^>]*data-foms-mc-drawing[^>]*>", gallery)
    assert len(pictures) == 2  # png · jpg 는 그림 → 전역 모달
    assert 'data-view-url="/api/files/view/orders/drawings/fake-front.png"' in pictures[0]
    assert 'data-download-url="/api/files/download/orders/drawings/fake-front.png"' in pictures[0]
    assert 'target="_blank"' in pictures[0]  # 모달이 없으면 새 탭으로 열린다
    assert 'loading="lazy"' in gallery  # 닫힌 줄의 그림은 펼칠 때만 받는다
    # PDF 는 파일 칸(새 탭) — 모달로 보내지 않는다
    pdf = re.search(r'<a class="foms-mc__dw is-file"[^>]*>', gallery).group(0)
    assert "fake-sheet.pdf" in pdf and "data-foms-mc-drawing" not in pdf
    assert "도면이 아직 없어요." not in row


def test_row_without_final_drawing_says_so(app):
    world = _seed()
    fl = world["fl"]
    _detail_order(drawings=None, link_user_id=fl.id)
    row = _row(_content(_html(_client(app, fl))), "세부고객")
    assert "도면이 아직 없어요." in row
    assert "has-drawings" not in row and "data-foms-mc-drawings" not in row


def test_order_the_freelancer_cannot_read_shows_no_detail(app):
    """대조군: 연결 줄이 없어 주문 화면을 못 여는 주문은 줄(수수료)만 있고 세부내역 · 도면 · 주문 열기는 없다."""
    world = _seed()
    fl = world["fl"]
    _detail_order(customer="연결없는고객", drawings=_DRAWINGS)
    db_session.query(OrderFreelancerLink).filter_by(user_id=fl.id).delete()
    db_session.commit()
    row = _row(_content(_html(_client(app, fl))), "연결없는고객")
    assert "출고가 4,000,000" in row  # 계산 줄은 그대로(수수료 주인은 이름으로 정해진다)
    for absent in ("foms-mc__items", "data-foms-mc-drawings", "주문 열기", "가짜 안방장", "도면이 아직 없어요."):
        assert absent not in row, absent


def test_accounting_on_behalf_sees_the_same_detail(app):
    world = _seed()
    fl = world["fl"]
    _detail_order(drawings=_DRAWINGS, link_user_id=fl.id)
    client = _client(app, _make_user("STAFF", "ACCOUNTING"))
    row = _row(_content(_html(client, f"month=2030-03&user_id={fl.id}")), "세부고객")
    assert "가짜 안방장" in row and "data-foms-mc-drawings" in row and "주문 열기" in row


# --------------------------------------------------------------------------
# 마감한 달 — 굳힌 줄 + 지금 품목, 바뀌었으면 한 줄
# --------------------------------------------------------------------------
def test_closed_month_row_has_detail_and_flags_changed_items(app, closing_today):
    world = _seed()
    fl = world["fl"]
    oid = _detail_order(drawings=_DRAWINGS, link_user_id=fl.id)
    _close(fl.id)

    row = _row(_content(_html(_client(app, fl))), "세부고객")
    assert "가짜 안방장" in row and "마감 뒤 품목이 바뀌었어요" not in row

    # 마감 뒤 품목 금액이 바뀌면(출고가 4,000,000 → 4,100,000) 굳힌 줄은 그대로, 알림 한 줄 + "지금 출고가"
    order = db_session.get(Order, oid)
    sd = dict(order.structured_data)
    sd["items"] = [dict(_ITEMS[0], price=3_300_000), *_ITEMS[1:]]
    order.structured_data = sd
    db_session.commit()
    row = _row(_content(_html(_client(app, fl))), "세부고객")
    assert "출고가 4,000,000 − 시공비 1,000,000" in row  # 굳힌 계산 줄
    assert "지금 출고가" in row and "4,100,000" in row
    assert "마감 뒤 품목이 바뀌었어요. 바뀐 몫은 다음 달 조정 줄에 들어가요." in row


# --------------------------------------------------------------------------
# 조회 · 권한 판정 횟수 — 줄이 늘어도 주문 읽기는 한 번, 연결 판정도 한 번
# --------------------------------------------------------------------------
def test_detail_reads_orders_once_and_links_once(app, monkeypatch):
    world = _seed()
    fl = world["fl"]
    for i in range(5):
        _detail_order(customer=f"여러고객{i}", drawings=_DRAWINGS)
    _link_all(fl.id)
    calls = {"one_by_one": 0}
    real = freelancer_orders._access_query

    def counting(db, user_id, order_id):
        calls["one_by_one"] += 1
        return real(db, user_id, order_id)

    monkeypatch.setattr(freelancer_orders, "_access_query", counting)
    content = _content(_html(_client(app, fl)))
    assert content.count("data-foms-mc-drawings") >= 5
    assert calls["one_by_one"] == 0, "연결 줄을 주문마다 따로 읽었다(한 번에 채우는 길이 안 탔다)"


def test_prime_fills_only_linked_orders():
    """연결 줄이 있는 주문만 참으로 채우고, 없는 주문은 비워 두어 하나씩 판정하게 한다(초안 규칙까지 같은 답)."""
    from flask import Flask

    fl = _make_user("STAFF", "SALES")
    linked = _detail_order(customer="연결고객", link_user_id=fl.id)
    unlinked = _detail_order(customer="미연결고객")
    db_session.query(OrderFreelancerLink).filter_by(order_id=unlinked).delete()
    db_session.commit()
    with Flask(__name__).test_request_context("/"):
        freelancer_orders.prime_freelancer_access(db_session, fl, [linked, unlinked, "x", None, -1])
        cache = freelancer_orders._request_cache()
        assert cache == {(fl.id, linked): True}
        assert freelancer_orders.freelancer_can_access_order(db_session, fl, unlinked) is False


# --------------------------------------------------------------------------
# 스크립트 — 전역 모달로 연다(새 보기 창 없음)
# --------------------------------------------------------------------------
def test_drawing_script_uses_the_global_viewer_once():
    src = (ROOT / "static/js/sales_commission/my-commission-drawings.js").read_text(encoding="utf-8")
    assert "window.GlobalImageViewer" in src and "viewer.open(files" in src
    assert "__FOMS_MC_DRAWINGS_BOUND" in src  # 아래 탭 조각 바꾸기로 다시 실행돼도 한 번만 건다
    assert "[data-foms-mc-drawings]" in src and "[data-foms-mc-drawing]" in src
    assert "fetch(" not in src and "innerHTML" not in src
    assert 'if (!viewer || typeof viewer.open !== "function") return;' in src  # 모달이 없으면 새 탭
