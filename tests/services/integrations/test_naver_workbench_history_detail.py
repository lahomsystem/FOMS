"""이력 표에서 여는 **읽기 전용 원본 상세** (2026-08-26).

왜 필요했나
-----------
큐에서 빠진 집(주문이 생긴 집)은 처리 목록에 없다. 그래서 지금까지 네이버 원본을 보려면
ERP 주문 편집기를 새 탭으로 여는 길뿐이었는데, **거기에는 원본이 없다** — 옵션 원문·
배송메모·클레임 사유·발송 결과는 수집 스냅샷에만 있다.

이 파일이 무는 규율
-------------------
* **이력에는 처리 버튼이 없다**(이력 절대 규칙 3). 이미 끝난 집에 발주확인·발송처리·
  취소 같은 되돌릴 수 없는 호출이 나갈 수 있으면 안 된다. 그래서 pane 을 재사용하지 않고
  읽기 전용 조각을 따로 둔다 — 이 단언이 그 결정을 잠근다.
* **조각에 id 가 없다**(절대 규칙 1). pane 을 한 문서에 두 번 그리면 ``wb-cancel`` 같은
  id 가 두 벌이 되어 "5번째 행의 취소가 1번째 집으로" 나간다.
* 값은 pane 과 **같은 함수**가 만든다 — 같은 집을 두 화면이 다르게 말하면 안 된다.
"""

from __future__ import annotations

import pathlib
import re

from db import db_session
from models import ExternalOrderLink, Order

from tests.services.integrations.test_naver_workbench import (  # noqa: F401 - fixture 재사용
    _collected,
    _login,
    _uid,
    workbench_on,
)
from tests.services.integrations.test_naver_workbench_snapshot_facts import _patch

DETAIL_PATH = "/admin/naver-ingest/triage/detail"
TRIAGE_PATH = "/admin/naver-ingest/triage"
SHELL_TEMPLATE = pathlib.Path("templates/admin/naver_workbench.html")
DETAIL_TEMPLATE = pathlib.Path("templates/admin/partials/naver_workbench_detail.html")
WORKBENCH_JS = pathlib.Path("static/js/admin/naver-workbench.js")

#: pane 이 무장하는 불가역 버튼 id — 이력 조각에 **하나도** 있으면 안 된다.
ACTION_IDS = ("wb-create", "wb-confirm", "wb-dispatch", "wb-cancel", "wb-review-done")


def _detail(client, link_id: int):
    return client.get(DETAIL_PATH, query_string={"link_id": link_id})


def _linked(order_no: str, **kwargs) -> ExternalOrderLink:
    """주문이 이미 생겨 **큐에서 빠진** 집 1건."""
    order = Order(received_date="2026-08-01", customer_name="이수취",
                  phone="010-3333-4444", address="서울 강남구 1 101호",
                  product="붙박이장", status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    link = _collected(order_no=order_no, **kwargs)
    row = db_session.get(ExternalOrderLink, int(link.id))
    row.order_id = int(order.id)
    row.sync_status = "LINKED"
    db_session.commit()
    return row


# --------------------------------------------------------------------------- #
# 조각이 원본을 말한다
# --------------------------------------------------------------------------- #

def test_detail_shows_the_naver_original_for_a_household_out_of_the_queue(client, workbench_on):
    """큐에서 빠진 집도 **그 자리에서** 네이버 원본을 볼 수 있다."""
    _login(client)
    link = _linked(order_no="N-HIST-DET", product="붙박이장", amount=1_200_000)

    response = _detail(client, link.id)

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "붙박이장" in body, "제품이 안 보인다"
    assert "네이버 원본" in body and "FOMS 현재 값" in body, "대조표가 없다"
    assert "이수취" in body, "FOMS 쪽 값이 안 붙었다"


def test_detail_carries_the_fields_erp_screen_cannot_show(client, workbench_on):
    """ERP 편집기에 **없는** 값들이 이 조각에는 있다 — 그게 이 조각의 존재 이유다."""
    _login(client)
    link = _linked(order_no="N-HIST-FIELDS", product="붙박이장", amount=900_000)
    _patch(link,
           product_order={"shippingMemo": "동 뒤편 주차장으로"},
           cancel={"claimStatus": "CANCEL_REQUEST",
                   "cancelDetailedReason": "일시불 재결제 예정"},
           delivery={"deliveryStatus": "NOT_TRACKING",
                     "sendDate": "2026-08-25T14:03:00.000+09:00"})

    body = _detail(client, link.id).get_data(as_text=True)

    assert "동 뒤편 주차장으로" in body, "배송메모(실위치)가 안 보인다"
    assert "일시불 재결제 예정" in body, "고객이 쓴 사유가 안 보인다"
    assert "발송처리 2026-08-25 14:03" in body, "발송 결과 시각이 안 보인다"


def test_detail_has_no_action_buttons(client, workbench_on):
    """**이력에는 처리 버튼이 없다.** 끝난 집에 되돌릴 수 없는 호출이 나가면 안 된다."""
    _login(client)
    link = _linked(order_no="N-HIST-NOBTN", product="붙박이장", amount=500_000)

    body = _detail(client, link.id).get_data(as_text=True)

    for action_id in ACTION_IDS:
        assert action_id not in body, f"이력 조각에 {action_id} 버튼이 들어왔다"
    assert "발주확인</button>" not in body
    assert "취소처리" not in body
    assert "읽기 전용" in body, "버튼이 없는 것이 설계라는 사실을 화면이 말하지 않는다"


def test_detail_fragment_declares_no_ids(client, workbench_on):
    """조각에 id 가 **하나도 없다** — pane 과 겹치면 다른 집으로 요청이 나간다(절대 규칙 1)."""
    _login(client)
    link = _linked(order_no="N-HIST-NOID", product="붙박이장", amount=500_000)

    body = _detail(client, link.id).get_data(as_text=True)

    assert not re.findall(r'\sid="[^"]+"', body), re.findall(r'\sid="[^"]+"', body)


def test_detail_says_nothing_it_was_not_told(client, workbench_on):
    """원본이 말한 적 없는 값은 **줄 자체를 내지 않는다** — 빈 칸은 거짓말이다."""
    _login(client)
    link = _linked(order_no="N-HIST-QUIET", product="붙박이장", amount=500_000)

    body = _detail(client, link.id).get_data(as_text=True)

    assert "고객이 쓴 사유" not in body, "사유가 없는데 사유 줄이 났다"
    assert "배송메모" not in body, "배송메모가 없는데 줄이 났다"
    assert "wb-sendline" not in body, "발송 기록이 없는데 줄이 났다"


# --------------------------------------------------------------------------- #
# 경로 계약
# --------------------------------------------------------------------------- #

def test_detail_requires_a_link_id(client, workbench_on):
    """``link_id`` 없이 부르면 400 — 조용히 빈 조각을 주지 않는다."""
    _login(client)
    assert client.get(DETAIL_PATH).status_code == 400


def test_detail_of_a_missing_link_is_404(client, workbench_on):
    """없는 링크는 404."""
    _login(client)
    assert _detail(client, 999_999).status_code == 404


def test_detail_is_absent_when_the_gate_is_off(client):
    """게이트 OFF 인 사용자에게는 **그 경로가 없다**(404) — pane 과 같은 규칙."""
    _login(client)
    link = _linked(order_no="N-HIST-GATEOFF", product="붙박이장", amount=500_000)

    assert _detail(client, link.id).status_code == 404


def test_detail_route_is_read_only(client, workbench_on):
    """POST 로는 못 부른다 — 읽기 전용 GET 이라 mutation 계약 대상이 아니다."""
    _login(client)
    link = _linked(order_no="N-HIST-GETONLY", product="붙박이장", amount=500_000)

    assert client.post(DETAIL_PATH, query_string={"link_id": link.id}).status_code == 405


# --------------------------------------------------------------------------- #
# 화면 배선 — 버튼이 실제로 이력 표에 있고, JS 가 그 경로를 문다
# --------------------------------------------------------------------------- #

def test_history_table_offers_the_detail_link(client, workbench_on):
    """이력 표의 **모든 행**에 원본 보기 링크가 있다(주문이 있든 없든 원본은 봐야 한다)."""
    _login(client)
    _linked(order_no="N-HIST-BTN-LINKED", product="붙박이장", amount=500_000)
    _collected(order_no="N-HIST-BTN-PENDING", product="붙박이장", amount=300_000)

    body = client.get(TRIAGE_PATH, query_string={"tab": "all"}).get_data(as_text=True)

    assert body.count("wb-hist-detail") >= 2, "일부 이력 행에 원본 보기 링크가 없다"
    assert 'id="wb-modal-detail"' in body, "상세 모달 껍데기가 셸에 없다"


def test_detail_trigger_stays_a_plain_link(client, workbench_on):
    """트리거는 **평범한 링크**다 — 이력 절대 규칙 3 이 허용하는 유일한 모양.

    버튼이나 ``data-link-id`` 를 두면 그 자리가 곧 과거 주문 전체에 대한 취소·발송
    조작면이 된다(불가역 mutation 라우트는 STAFF 까지 열려 있다). 그래서 뷰어에는
    **다른 이름의 속성**(``data-detail-id``)을 쓴다 — 기존 금지가 글자 그대로 유지된다.
    """
    _login(client)
    _linked(order_no="N-HIST-PLAIN", product="붙박이장", amount=500_000)

    body = client.get(TRIAGE_PATH, query_string={"tab": "all"}).get_data(as_text=True)
    tbody = body.split("<tbody>")[-1].split("</tbody>")[0]

    assert "wb-hist-detail" in tbody
    assert "<button" not in tbody, tbody
    assert "data-link-id" not in tbody, tbody
    assert 'class="btn' not in tbody, tbody


def test_detail_trigger_is_bound_by_class_not_id() -> None:
    """트리거는 행 수만큼 나온다 — id 로 물면 문서에 중복 id 가 생긴다(절대 규칙 1)."""
    shell = SHELL_TEMPLATE.read_text(encoding="utf-8")
    js = WORKBENCH_JS.read_text(encoding="utf-8")

    assert 'class="wb-hist-detail"' in shell
    assert 'id="wb-hist-detail"' not in shell
    assert "closest('a.wb-hist-detail')" in js, "JS 가 클래스로 물지 않는다"
    assert "/admin/naver-ingest/triage/detail" in js, "JS 가 상세 경로를 모른다"


def test_detail_template_keeps_styles_in_the_workbench_css() -> None:
    """새 요소 스타일은 전용 CSS 에 — 인라인 style 로 새지 않는다."""
    markup = DETAIL_TEMPLATE.read_text(encoding="utf-8")
    css = pathlib.Path("static/css/admin/naver-workbench.css").read_text(encoding="utf-8")

    assert 'style="' not in markup, "상세 조각에 인라인 스타일이 들어왔다"
    for selector in (".wb-detail__head", ".wb-detail__note", ".wb-detail__links"):
        assert selector in css, f"{selector} 스타일이 없다"


def test_failed_detail_load_does_not_leave_an_empty_modal() -> None:
    """불러오기 실패는 **말한다** — 빈 모달은 "원본이 없다"로 읽힌다."""
    js = WORKBENCH_JS.read_text(encoding="utf-8")

    assert "원본을 불러오지 못했습니다" in js
