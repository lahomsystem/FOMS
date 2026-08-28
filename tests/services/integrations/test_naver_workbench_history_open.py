"""이력 탭 → 워크벤치 처리 pane 으로 가는 길 (2026-08-28).

왜 필요했나
-----------
`확인 완료 — 큐에서 빼기` 를 누르면 그 집은 처리 목록의 두 원천에서 모두 빠진다. 그때부터
발주확인·발송처리·취소 버튼에 닿는 길은 **ERP 주문 편집기 도크**(ADMIN·MANAGER 전용)
하나뿐이었다 — 주문이 아직 없는 집(취소·반품으로 승격이 막힌 집)은 그 도크조차 없어서
주소를 손으로 치는 것 말고는 길이 없었다.

이력 표는 그 집들이 **전부 모여 있는 유일한 목록**이다. 그래서 행마다 처리 탭으로 가는
평범한 링크를 둔다.

이 파일이 무는 규율
-------------------
* 링크는 **모든 행**에 있다. 조건을 붙이면(예: 미생성 건만) 이 결함이 그대로 되돌아온다.
* 그래도 이력 표에는 **버튼이 없다**(이력 절대 규칙 3). 여기서 나가는 것은 주소 이동뿐이다.
* 미생성 링크가 있는 집은 **그 링크**를 연다 — 다음 할 일이 '주문 만들기'이고 pane 대조표가
  그 링크 기준으로 그려진다.
"""

from __future__ import annotations

from datetime import datetime

from db import db_session
from models import ExternalOrderLink, Order

from tests.services.integrations.test_naver_workbench import (  # noqa: F401 - fixture 재사용
    _collected,
    _login,
    _uid,
    workbench_on,
)

TRIAGE_PATH = "/admin/naver-ingest/triage"


def _history_tbody(body: str) -> str:
    return body.split('class="wb-cmp wb-hist"')[1].split("<tbody>")[1].split("</tbody>")[0]


def _rows_of(tbody: str) -> list[str]:
    return [chunk for chunk in tbody.split("<tr")[1:]]


def _reviewed_linked(order_no: str, **kwargs) -> ExternalOrderLink:
    """주문이 생기고 `확인 완료` 까지 끝나 **큐에서 빠진** 집 1건."""
    order = Order(received_date="2026-08-01", customer_name="이수취", phone="010-3333-4444",
                  address="서울 강남구 1 101호", product="붙박이장", status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    link = _collected(order_no=order_no, **kwargs)
    row = db_session.get(ExternalOrderLink, int(link.id))
    row.order_id = int(order.id)
    row.sync_status = "LINKED"
    row.reviewed_at = datetime(2026, 8, 20, 1, 2, 3)
    db_session.commit()
    return row


def test_every_history_row_offers_the_work_tab_link(client, workbench_on):
    """세 갈래(큐에서 뺀 집·미생성 집·취소 집) **전부** 처리 탭으로 가는 길이 있다."""
    _login(client)
    gone = _reviewed_linked("N-HOPEN-DONE", product="큐에서 뺀 집", amount=500_000)
    pending = _collected(order_no="N-HOPEN-PEND", product="미생성 집", amount=300_000,
                         address="대구 수성구 7", tel="010-7777-0007")
    claim = _collected(order_no="N-HOPEN-CLAIM", product="취소 집", amount=200_000,
                       claim_status="CANCEL_REQUEST",
                       address="광주 서구 6", tel="010-6666-0006")

    tbody = _history_tbody(client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True))
    rows = _rows_of(tbody)

    assert len(rows) == 3, "세 줄이 다 있어야 세 갈래를 다 문 것이다"
    for row in rows:
        assert "tab=work" in row and "link_id=" in row, row
        # 글자도 못박는다 — 칸 이름이 '열기'라 링크는 이름만 말한다(`원본 보기` · `워크벤치`).
        assert "워크벤치</a>" in row, row
    for link in (gone, pending, claim):
        assert f"tab=work&amp;link_id={link.id}" in tbody, f"link {link.id} 로 가는 길이 없다"


def test_the_link_opens_the_household_of_a_row_that_left_the_queue(client, workbench_on):
    """링크를 따라가면 **큐에서 뺀 그 집**이 완전무장 pane 으로 열린다."""
    _login(client)
    link = _reviewed_linked("N-HOPEN-FOLLOW", product="큐에서 뺀 집", amount=500_000)

    response = client.get(TRIAGE_PATH, query_string={"tab": "work", "link_id": link.id})
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "큐에서 뺀 집" in body, "그 집이 상세에 안 떴다"
    assert "wb-dispatch" in body and "wb-cancel" in body, "처리 버튼이 없으면 갈 이유가 없다"
    # 목록에는 없는 집이라는 사실을 pane 이 말한다(리뷰 M-3) — 막지는 않는다.
    assert "목록에 없는" in body


def test_history_rows_stay_read_only(client, workbench_on):
    """길이 생겨도 이력 표는 여전히 **버튼 0**이다(이력 절대 규칙 3)."""
    _login(client)
    _reviewed_linked("N-HOPEN-RO", product="큐에서 뺀 집", amount=500_000)
    _collected(order_no="N-HOPEN-RO2", product="미생성 집", amount=300_000,
               address="대구 수성구 7", tel="010-7777-0007")

    tbody = _history_tbody(client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True))

    assert "<button" not in tbody, tbody
    assert "data-link-id" not in tbody, tbody
    assert 'class="btn' not in tbody, tbody


def test_pending_household_still_opens_its_uncreated_link(client, workbench_on):
    """미생성 링크가 있으면 **그 링크**를 연다 — 다음 할 일이 '주문 만들기'다."""
    _login(client)
    pending = _collected(order_no="N-HOPEN-KEEP", product="미생성 집", amount=300_000)

    tbody = _history_tbody(client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True))

    assert f"tab=work&amp;link_id={pending.id}" in tbody


def test_claim_row_keeps_its_reason_next_to_the_new_link(client, workbench_on):
    """취소 집: 길은 생기되 '주문을 만들 수 없다'는 사실은 그대로 적힌다."""
    _login(client)
    claim = _collected(order_no="N-HOPEN-WHY", product="취소 집", amount=200_000,
                       claim_status="CANCEL_REQUEST")

    tbody = _history_tbody(client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True))

    assert "취소·반품 진행 중 — 주문을 만들 수 없습니다." in tbody
    assert f"tab=work&amp;link_id={claim.id}" in tbody
