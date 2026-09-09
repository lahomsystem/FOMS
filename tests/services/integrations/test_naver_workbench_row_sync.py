"""워크벤치 처리 탭 — 왼쪽 줄이 pane 과 **같은 말**을 하는가 (2026-09-09 신고).

담당자가 본 화면: 추가결제 3건 묶음이 발송처리까지 끝났는데(pane 은 `발송처리 완료`)
왼쪽 큐 줄은 여전히 `규격 입력할 차례` 였다. 원인은 판정이 두 벌이었다는 것 —
서버는 이미 `spec_filled`·`dispatched` 를 알고 있었는데 목록 템플릿만 `group.order_id`
하나로 다시 판정했다(:func:`_attach_row_flags` docstring 의 H1 과 같은 부류).

이 파일이 무는 것은 두 겹이다.

* **결함 A(서버 판정 한 벌)**: 목록 줄의 라벨이 그 집의 실제 상태를 따른다.
  판정부는 :func:`foms.web.admin.naver_ingest._row_view` 하나뿐이다.
* **결함 B(pane → 줄 옮기기)**: pane 프래그먼트 루트가 표시값 3종을 실어 오고,
  JS 순수 함수 세 벌이 그 값을 왼쪽 줄로 옮긴다.

**음성 대조군을 같은 화면에 함께 시드한다.** 세 집을 한 번의 요청으로 받아 줄마다
잘라 보지 않으면 "판정이 통째로 죽었다"가 green 으로 샌다 — 발송·규격 집만 보면
라벨을 전부 `지금 처리 가능` 으로 만들어도 통과한다.
"""

from __future__ import annotations

import json
import pathlib

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from models import ExternalOrderLink, Order
from tests.services.integrations.test_naver_workbench import (  # noqa: F401
    TRIAGE_PATH,
    _collected,
    _login,
    _row_of,
    workbench_on,
)

#: pane 프래그먼트 경로 — JS 가 `#wb-pane` 만 갈아 끼울 때 부르는 그 주소.
PANE_PATH = "/admin/naver-ingest/triage/pane"



# --------------------------------------------------------------------------- #
# 픽스처 보조 — 규격·발송 표식
# --------------------------------------------------------------------------- #

def _link_order(link: ExternalOrderLink, *, spec: bool,
                customer_name: str = "임선경") -> Order:
    """링크에 FOMS 주문을 붙인다.

    규격 SSOT 는 ``structured_data['items'][*]['spec_rows']`` 다 — **품목 안**이고
    최상위 ``spec_rows`` 가 아니다(:func:`naver_ingest.order_has_spec_rows`).
    최상위에 넣으면 판정부가 늘 "규격 없음"으로 읽어 이 파일이 아무것도 재현하지 못한다.

    Args:
        link: 주문을 붙일 링크.
        spec: True 면 규격 행을 한 줄 넣는다.
        customer_name: 붙는 주문의 고객명(목록 이름 칸이 이 값을 쓴다).

    Returns:
        만들어 붙인 :class:`models.Order`.
    """
    rows = [{"width": "1200", "height": "2400"}] if spec else []
    order = Order(received_date="2026-09-09", customer_name=customer_name,
                  phone="010-7777-8888", address="서울 강남구 1 101호",
                  product="붙박이장", status="RECEIVED",
                  structured_data={"items": [{"name": "붙박이장", "spec_rows": rows}]})
    db_session.add(order)
    db_session.commit()
    row = db_session.get(ExternalOrderLink, int(link.id))
    row.order_id = int(order.id)
    row.sync_status = "LINKED"
    db_session.commit()
    return order


def _mark_dispatched(link: ExternalOrderLink,
                     stamp: str = "2026-09-09T01:53:00") -> None:
    """워커가 남기는 **우리 쪽** 발송 표식을 써 넣는다(UTC naive isoformat).

    ``dispatched`` 는 집 전체가 나갔을 때만 True 라, 형제가 있으면 형제에도 찍어야 한다.

    Args:
        link: 링크 행.
        stamp: 발송 시각 문자열.
    """
    row = db_session.get(ExternalOrderLink, int(link.id))
    state = dict(row.triage_state or {})
    state["fulfillment"] = dict(state.get("fulfillment") or {}, dispatched_at=stamp)
    row.triage_state = state
    flag_modified(row, "triage_state")
    db_session.commit()


def _work_body(client) -> str:
    """처리 탭 전체 렌더 마크업."""
    response = client.get(f"{TRIAGE_PATH}?f=all")
    assert response.status_code == 200, response.status_code
    return response.get_data(as_text=True)


# --------------------------------------------------------------------------- #
# 결함 A — 목록 줄의 라벨이 그 집의 실제 상태를 따른다
# --------------------------------------------------------------------------- #

def test_row_labels_follow_the_real_state_of_each_household(client, workbench_on):
    """한 화면 안에서 네 집이 **각각 다른** 말을 한다(음성 대조군 포함).

    · 발송까지 끝난 집 → `발송까지 끝남` (`규격 입력할 차례` 가 아니다 — 신고 본문)
    · 규격이 이미 들어간 집 → `발송할 차례`
    · **주문은 있고 규격은 없고 발송 전인 집 → 여전히 `규격 입력할 차례`** (음성 대조군)
    · 주문이 아직 없는 집 → `지금 처리 가능` + `주문 만들기` 배지(배지 억제의 양성 대조군)

    네 줄을 **한 번의 요청**으로 함께 본다. 라벨 갈래를 통째로 한 값으로 굳혀도
    대조군 두 줄이 곧바로 빨개진다.
    """
    _login(client)
    done = _collected(order_no="N-ROWSYNC-DONE", product="발송끝 붙박이장", amount=300000)
    _link_order(done, spec=False, customer_name="발송끝 고객")
    _mark_dispatched(done)

    filled = _collected(order_no="N-ROWSYNC-SPEC", product="규격완료 붙박이장", amount=300000)
    _link_order(filled, spec=True, customer_name="규격완료 고객")

    plain = _collected(order_no="N-ROWSYNC-PLAIN", product="규격전 붙박이장", amount=300000)
    _link_order(plain, spec=False, customer_name="규격전 고객")

    _collected(order_no="N-ROWSYNC-FRESH", product="주문전 붙박이장", amount=300000)

    body = _work_body(client)

    done_row = _row_of(body, "발송끝 붙박이장")
    assert "발송까지 끝남" in done_row, done_row
    assert "규격 입력할 차례" not in done_row, "발송이 끝난 집이 규격을 입력하라고 말한다"
    assert "badge bg-primary" not in done_row, "라벨과 정면으로 부딪히는 `규격 입력` 배지가 남았다"

    filled_row = _row_of(body, "규격완료 붙박이장")
    assert "발송할 차례" in filled_row, filled_row
    assert "규격 입력할 차례" not in filled_row, "규격이 이미 들어간 집이다"

    # 음성 대조군 — 같은 모집단, 같은 화면. 이 줄까지 바뀌면 판정이 죽은 것이다.
    plain_row = _row_of(body, "규격전 붙박이장")
    assert "규격 입력할 차례" in plain_row, plain_row
    assert "발송까지 끝남" not in plain_row, plain_row
    assert "발송할 차례" not in plain_row, plain_row

    # 양성 대조군 — 배지 억제 조건이 통째로 꺼진 것이 아님을 이 줄이 증명한다.
    fresh_row = _row_of(body, "주문전 붙박이장")
    assert "지금 처리 가능" in fresh_row, fresh_row
    assert '<span class="badge bg-primary">주문 만들기</span>' in fresh_row, fresh_row


def test_a_claimed_household_reads_as_locked_even_after_dispatch(client, workbench_on):
    """클레임 잠금이 발송보다 **위**다 — 손대지 않을 집을 `발송까지 끝남` 이라 부르지 않는다.

    사다리에서 잠금이 아래로 내려가면, 취소가 확정된 집이 "다 끝났다"로 읽혀
    담당자가 그냥 지나친다. 발송 표식과 클레임을 한 집에 함께 놓고 순서를 못박는다.
    """
    _login(client)
    link = _collected(order_no="N-ROWSYNC-CLAIM", product="취소된 붙박이장",
                      amount=300000, claim_status="CANCEL_DONE")
    _link_order(link, spec=False, customer_name="취소 고객")
    _mark_dispatched(link)

    row = _row_of(_work_body(client), "취소된 붙박이장")

    assert "손대지 않음" in row, row
    assert "발송까지 끝남" not in row, "잠긴 집이 발송 갈래로 떨어졌다"
    assert "규격 입력할 차례" not in row, row


# --------------------------------------------------------------------------- #
# 결함 B ① 서버 — pane 프래그먼트가 줄 표시값을 실어 온다
# --------------------------------------------------------------------------- #

def test_the_pane_fragment_carries_the_same_row_view_as_the_list(client, workbench_on):
    """pane 루트의 표시값 3종이 같은 집의 목록 줄과 **글자까지** 같다.

    ``data-row-link-ids`` 는 집 형제를 전부 담아야 한다 — 목록 줄의 ``data-link-id`` 는
    화면 모집단 안 최대금액 링크라 pane 의 대표와 갈릴 수 있고, 그때 JS 가 맞출 줄을
    못 찾는다(계약 §행 매칭 함정).
    """
    _login(client)
    lead = _collected(order_no="N-ROWSYNC-PANE", product="pane 붙박이장", amount=300000)
    sibling = _collected(order_no="N-ROWSYNC-PANE", product="pane 구성옵션", amount=0)
    _link_order(lead, spec=False, customer_name="pane 고객")
    _mark_dispatched(lead)
    _mark_dispatched(sibling)

    row = _row_of(_work_body(client), "pane 붙박이장")
    assert "발송까지 끝남" in row, row

    fragment = client.get(f"{PANE_PATH}?link_id={lead.id}").get_data(as_text=True)
    head = fragment.strip().split(">")[0]

    assert 'data-row-kind="done"' in head, head
    assert 'data-row-can="발송까지 끝남"' in head, head
    ids = head.split('data-row-link-ids="')[1].split('"')[0].split(",")
    assert sorted(ids) == sorted([str(lead.id), str(sibling.id)]), head


def test_the_pane_fragment_omits_the_row_view_when_nothing_is_open(client, workbench_on):
    """연 집이 없으면 세 속성을 **아예 안 낸다**(음성 대조군).

    빈 값이라도 실어 보내면 JS 가 그 값으로 왼쪽 줄을 덮어쓴다 — 라벨이 빈 칸이 된다.
    link_id 없이 부르는 프래그먼트는 400 이므로, 빈 pane 은 전체 렌더 첫 화면에서 본다.
    """
    _login(client)

    assert client.get(PANE_PATH).status_code == 400

    pane_head = _work_body(client).split('<div id="wb-pane')[1].split(">")[0]

    assert "data-row-kind=" not in pane_head, pane_head
    assert "data-row-link-ids=" not in pane_head, pane_head
