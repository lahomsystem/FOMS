"""네이버에 **이미 발송이 찍힌** 집에 두 번째 발송처리가 나가지 않는지 (2026-08-26 T5).

발송처리 판정은 지금까지 **우리 표식만** 봤다(``triage_state['fulfillment']['dispatched_at']``).
판매자센터에서 사람이 직접 발송처리한 집은 우리 쪽에 아무 흔적이 없어서, 화면은 버튼을
열어 뒀고 누르면 ``dispatch_product_orders`` 가 **실제로 한 번 더** 나갔다. 그 호출은
되돌릴 수 없다 — 구매자에게 '배송 시작'으로 보이고 구매확정·정산 시계가 돈다. 설계자도
네이버의 400(이미 처리됨)을 안전망으로 삼지 않겠다고 못박아 뒀다(``fulfillment.py`` 첫머리).

방어선은 두 겹이고, 두 겹인 **이유가 곧 이 파일의 단언**이다:

* **화면**(pane) — 판정에 쓸 수 있는 네이버 신호는 pane 이 연 **상품주문 1건**의 원본뿐이다
  (``selected.dispatch.naver_at``). 그래서 화면은 **보이는 증거로 닫는 쪽**만 한다.
* **서버**(``dispatch_order``) — 집의 **형제 전부**의 원본을 읽어 ``delivery.sendDate`` 가
  있는 상품주문만 골라 뺀다. 화면이 못 본 형제(형제만 발송 기록이 있는 집)를 여기서 막는다.

**못을 빼지 않는 것**도 같은 무게로 잰다 — 양쪽 다 기록이 없는 정상 집은 예전 그대로
버튼이 열리고 호출이 그대로 나가야 한다. 잠금이 과하면 사람이 판매자센터로 도망가고,
그러면 이 화면이 존재할 이유가 없어진다.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.integrations.naver_commerce.fulfillment import (
    FulfillmentError,
    dispatch_order,
)
from models import ExternalOrderLink

from tests.services.integrations._markup import is_disabled, open_tag

# 스텁 클라이언트는 **한 벌만** 쓴다 — 두 벌이 되면 payload 모양이 갈려 재려던 것과
# 다른 것을 재게 된다(발송 payload 는 productOrderId 목록이 계약이다).
from tests.services.integrations.test_naver_fulfillment import _StubClient
from tests.services.integrations.test_naver_workbench import (  # noqa: F401 - fixture 재사용
    _collected,
    _login,
    _pane,
    _uid,
    workbench_on,
)
from tests.services.integrations.test_naver_workbench_v3_followup import (
    _modal_of,
    _sibling,
)

PANE_PATH = "/admin/naver-ingest/triage/pane"

#: 네이버가 돌려주는 발송 시각 원문(오프셋이 붙어 온다) = KST 2026-08-25 14:03.
NAVER_SENT_RAW = "2026-08-25T14:03:00.000+09:00"
NAVER_SENT_KST = "2026-08-25 14:03"


def _naver_sent(link: ExternalOrderLink, send_date: str = NAVER_SENT_RAW) -> ExternalOrderLink:
    """수집된 링크의 원본에 **네이버가 말하는 발송**(``delivery``)을 얹는다.

    수집 파이프라인이 그대로 저장하는 모양이라 블록만 더한다 — 픽스처 모양이 두 벌이
    되면 재려던 것과 다른 것을 잰다(JSONB 수정 패턴).

    Args:
        link: 수집된 링크.
        send_date: ``delivery.sendDate`` 원문.

    Returns:
        갱신된 링크 행.
    """
    row = db_session.get(ExternalOrderLink, int(link.id))
    snapshot = dict(row.raw_snapshot or {})
    snapshot["delivery"] = {"deliveryMethod": "DIRECT_DELIVERY",
                            "deliveryStatus": "NOT_TRACKING",
                            "sendDate": send_date}
    row.raw_snapshot = snapshot
    flag_modified(row, "raw_snapshot")
    db_session.commit()
    return row


def _mark_dispatched(link: ExternalOrderLink,
                     stamp: str = "2026-08-25T05:03:00") -> None:
    """워커가 남기는 **우리 쪽** 발송 표식을 써 넣는다(UTC naive isoformat).

    Args:
        link: 링크 행.
        stamp: 우리 표식 시각(기본값은 KST 14:03 = 네이버 원문과 같은 순간).
    """
    row = db_session.get(ExternalOrderLink, int(link.id))
    state = dict(row.triage_state or {})
    state["fulfillment"] = dict(state.get("fulfillment") or {}, dispatched_at=stamp)
    row.triage_state = state
    flag_modified(row, "triage_state")
    db_session.commit()


def _state(link_id: int) -> dict:
    """링크의 fulfillment 상태를 다시 읽는다(요청이 지나가면 앞서 든 객체는 낡는다)."""
    db_session.expire_all()
    row = db_session.get(ExternalOrderLink, int(link_id))
    return (row.triage_state or {}).get("fulfillment") or {}


def _pane_html(client, link_id: int) -> str:
    """상세 pane 조각만 받아 온다(레이아웃·목록 없음)."""
    response = client.get(f"{PANE_PATH}?link_id={link_id}")
    assert response.status_code == 200, response.status_code
    return _pane(response.get_data(as_text=True))


# --------------------------------------------------------------------------- #
# ① 화면 — 네이버가 이미 발송을 말하는 집은 버튼이 잠긴다
# --------------------------------------------------------------------------- #

def test_dispatch_button_is_locked_when_naver_already_sent(client, workbench_on):
    """네이버에 발송 기록이 있고 우리 표식이 없으면 **발송처리 버튼이 잠긴다**.

    이 집은 판매자센터에서 이미 나갔다. 버튼이 열려 있으면 되돌릴 수 없는 두 번째 호출이
    그대로 나간다 — 모달(``#wb-dispatch-confirm``)까지 함께 사라져야 우회로가 없다.
    """
    _login(client)
    link = _collected(order_no="N-T5-LOCK", product="붙박이장", amount=1000000)
    _naver_sent(link)

    pane = _pane_html(client, link.id)

    assert is_disabled(pane, "wb-dispatch"), open_tag(pane, "wb-dispatch")
    assert 'id="wb-dispatch-confirm"' not in pane, "잠긴 집에 발송 모달이 남았다"


def test_locked_reason_names_naver_and_the_time(client, workbench_on):
    """잠근 이유가 **화면에 보인다** — 시각까지, 그리고 발주확인 이야기가 아니어야 한다.

    "지금은 안 됩니다"만으로는 사람이 어디로 가야 할지 모른다. 시각이 있어야 판매자센터에서
    어느 건인지 찾고, 사유가 갈려야 발주확인 탭으로 헛걸음하지 않는다. title 은 마우스가
    없는 기기에서 못 읽으므로 같은 사실을 안내 문구로도 낸다.
    """
    _login(client)
    link = _collected(order_no="N-T5-WHY", product="붙박이장", amount=1000000)
    _naver_sent(link)

    pane = _pane_html(client, link.id)
    head = open_tag(pane, "wb-dispatch")

    assert "네이버에 이미 발송 기록이 있습니다" in head, head
    assert NAVER_SENT_KST in head, f"잠금 사유에 발송 시각이 없다: {head}"
    assert "판매자센터" in head, head
    assert "발주확인이 먼저입니다" not in head, f"사유가 발주확인으로 뒤바뀌었다: {head}"
    # 안내 문구(버튼 **바깥**)에도 같은 사실이 있어야 한다 — title 만으로는 터치 기기에서
    # 못 읽는다. 발송 대조 줄("네이버 원본 | FOMS 현재 값")에도 같은 시각이 찍히므로
    # 글자 수를 세지 않고 **안내 문구 블록을 집어** 확인한다(다른 줄에 속지 않게).
    why_lines = [chunk.split("</div>")[0] for chunk in pane.split('class="wb-acts__why')[1:]]
    lock_line = next((line for line in why_lines if "이미 발송 기록" in line), "")
    assert lock_line, "잠금 사유가 title 에만 있다 — 마우스가 없는 기기에서는 영영 못 읽는다"
    assert NAVER_SENT_KST in lock_line, lock_line
    assert "판매자센터" in lock_line, lock_line


def test_a_clean_household_keeps_its_dispatch_button(client, workbench_on):
    """양쪽 다 발송 기록이 없는 집은 **예전 그대로** 버튼이 열린다(못을 빼면 안 된다).

    잠금이 과하면 정상 집까지 막혀 사람이 판매자센터로 도망간다 — 그 순간 이 화면은
    존재 이유를 잃는다.
    """
    _login(client)
    link = _collected(order_no="N-T5-CLEAN", product="붙박이장", amount=1000000)

    pane = _pane_html(client, link.id)

    assert not is_disabled(pane, "wb-dispatch"), open_tag(pane, "wb-dispatch")
    assert 'id="wb-dispatch-confirm"' in pane, "정상 집에서 발송 모달이 사라졌다"


def test_our_own_record_is_not_a_second_hand_signal(client, workbench_on):
    """우리가 보낸 발송을 네이버가 되읊는 것은 **새 사실이 아니다** — 남은 형제를 막지 않는다.

    양쪽 다 기록이 있는 링크는 우리가 방금 보낸 그 발송이다. 그걸로 집 전체를 잠그면
    부분 발송 집(형제 일부만 나간 집)의 **남은 상품주문이 영영 못 나간다**.
    """
    _login(client)
    lead = _collected(order_no="N-T5-MINE", product="붙박이장 본품", amount=1000000)
    _sibling(lead, product="구성 A", amount=2000)
    _naver_sent(lead)
    _mark_dispatched(lead)

    pane = _pane_html(client, lead.id)

    assert not is_disabled(pane, "wb-dispatch"), open_tag(pane, "wb-dispatch")


def test_partial_dispatch_line_does_not_blame_place_confirmation(client, workbench_on):
    """부분 발송 안내가 잠금 사유를 **발주확인으로 바꿔 말하지 않는다**.

    그 줄은 "지금은 왜 못 보내는지"를 말하는 자리다. 네이버 기록으로 잠긴 집에
    "발주확인이 먼저라"고 적으면 사람이 발주확인 탭으로 헛걸음한다 — 그 집은 발주확인이
    이미 끝나 있어서 거기서도 할 일이 없다.
    """
    _login(client)
    lead = _collected(order_no="N-T5-PARTWHY", product="붙박이장 본품", amount=1000000)
    sib = _sibling(lead, product="구성 A", amount=2000)
    _sibling(lead, product="구성 B", amount=3000)   # 아직 안 나간 형제(진짜 부분 발송)
    _mark_dispatched(sib)          # 형제 1건은 우리가 이미 보냈다
    _naver_sent(lead)              # 열어 본 건은 판매자센터에서 이미 나갔다

    pane = _pane_html(client, lead.id)

    # 나간 건수는 **두 신호**를 센다(2026-09-02) — 우리가 보낸 1건 + 판매자센터 1건.
    # 우리 표식만 세던 옛 식은 여기서 "1건 발송 완료"라고 말해, 판매자센터에서 나간 건을
    # 화면이 없는 것처럼 다뤘다.
    assert "2건 발송 완료" in pane, "부분 발송 안내가 나간 건수를 우리 표식만으로 셌다"
    assert "네이버에 이미 발송 기록이 있어 지금은 보낼 수 없습니다" in pane, pane[-2000:]
    assert "발주확인이 먼저라" not in pane, "잠금 사유가 발주확인으로 뒤바뀌었다"


# --------------------------------------------------------------------------- #
# ② 서버 — 같은 신호로 한 겹 더 (화면이 못 본 형제를 여기서 막는다)
# --------------------------------------------------------------------------- #

def test_dispatch_leaves_out_the_product_order_naver_already_sent(app):
    """네이버가 발송을 말하는 상품주문은 **호출 payload 에서 빠진다**.

    화면이 여는 판정은 pane 이 연 링크 1건의 원본만 본다 — 형제만 발송이 찍힌 집에서는
    버튼이 열린다. 그 집을 여기서 막는다. 남은 형제는 그대로 나가야 한다(과잉 차단 금지).
    """
    lead = _collected(order_no="N-T5-SRV-PART", product="붙박이장 본품", amount=1000000)
    sib = _sibling(lead, product="구성 A", amount=2000)
    _naver_sent(sib)
    client = _StubClient()

    result = dispatch_order(db_session, client, link_id=int(lead.id), actor_user_id=7)
    db_session.commit()

    sent_ids = [row["productOrderId"] for call in client.dispatch_calls for row in call]
    assert sent_ids == [lead.external_id], f"네이버 기록분이 호출에 섞였다: {sent_ids}"
    assert result["dispatched"] == [lead.external_id]
    assert sib.external_id in result["skipped"]
    # 뺀 것이지 실패한 것이 아니다 — 실패 사유를 찍으면 정상 집에 빨간 띠가 남는다.
    assert not _state(sib.id).get("last_error"), "정상 처리된 집에 실패 사유가 찍혔다"


def test_dispatch_calls_naver_zero_times_when_it_already_sent_everything(app):
    """집 전체가 네이버에서 이미 나갔으면 **네이버를 한 번도 부르지 않는다**."""
    lead = _collected(order_no="N-T5-SRV-ALL", product="붙박이장 본품", amount=1000000)
    sib = _sibling(lead, product="구성 A", amount=2000)
    _naver_sent(lead)
    _naver_sent(sib)
    client = _StubClient()

    with pytest.raises(FulfillmentError):
        dispatch_order(db_session, client, link_id=int(lead.id), actor_user_id=7)
    db_session.commit()

    assert client.dispatch_calls == [], "보낼 것이 없는데 네이버를 불렀다"
    assert not _state(lead.id).get("dispatched_at"), "우리가 보내지 않은 발송을 우리 표식으로 지어냈다"


def test_all_skipped_speaks_instead_of_returning_silently(app):
    """전부 빠진 집은 **사유를 남기고 올린다** — 조용한 성공은 재클릭을 부른다.

    web 은 enqueue 만 하고 이미 "요청했습니다"로 답했다. 표식이 하나도 안 바뀌면 화면은
    그대로고, 사람에게는 "눌렀는데 아무 일도 안 났다"로 보여 한 번 더 누른다. 우리 표식으로
    끝난 집은 화면이 '발송처리 완료'라고 이미 말하지만, 이 집은 화면에 아무 말이 없다 —
    그래서 여기만 말한다. 사유는 실패 띠·폴링 응답이 읽는 자리(``last_error``)에 남긴다.
    """
    link = _collected(order_no="N-T5-SRV-SAY", product="붙박이장", amount=1000000)
    _naver_sent(link)
    client = _StubClient()

    with pytest.raises(FulfillmentError) as caught:
        dispatch_order(db_session, client, link_id=int(link.id), actor_user_id=7)
    db_session.commit()

    assert NAVER_SENT_KST in str(caught.value), str(caught.value)
    state = _state(link.id)
    assert "네이버에 이미 발송 기록" in state.get("last_error", ""), state
    # 재시도 버튼이 같은 작업으로 다시 보내려면 어느 작업이 막혔는지가 함께 남아야 한다.
    assert state.get("last_error_action") == "dispatch", state


def test_a_clean_household_still_goes_out(app):
    """양쪽 다 기록이 없는 집은 **예전 그대로** 네이버로 나간다(못을 빼면 안 된다)."""
    lead = _collected(order_no="N-T5-SRV-CLEAN", product="붙박이장 본품", amount=1000000)
    sib = _sibling(lead, product="구성 A", amount=2000)
    client = _StubClient()

    result = dispatch_order(db_session, client, link_id=int(lead.id), actor_user_id=7)
    db_session.commit()

    sent_ids = [row["productOrderId"] for call in client.dispatch_calls for row in call]
    assert sorted(sent_ids) == sorted([lead.external_id, sib.external_id]), sent_ids
    assert sorted(result["dispatched"]) == sorted([lead.external_id, sib.external_id])
    assert _state(lead.id)["dispatched_at"] and _state(sib.id)["dispatched_at"]


# --------------------------------------------------------------------------- #
# ③ 재진술 == 서버가 보낼 건수 (계약 §0-2 · 2026-09-02)
#
# 화면 모달은 지금까지 `집 전체 수 - 우리 표식 수` 로 셌다. 그 식은 판매자센터에서 사람이
# 직접 보낸 형제를 **빼지 않는다** — "3건을 보냅니다"라고 말하고 서버는 1건만 보낸다.
# 불가역 경로의 과대 진술이라 그 자체가 사고다. 두 자리가 이제 술어 한 벌
# (`fulfillment.is_dispatch_pending`)을 쓰고, 아래 단언이 그 한 벌을 잠근다.
# --------------------------------------------------------------------------- #

def _modal_dispatch_count(pane: str) -> int:
    """발송 모달이 재진술한 건수(모달이 없으면 실패시킨다)."""
    modal = _modal_of(pane, "wb-modal-dispatch")
    found = re.search(r"(\d+)건을 네이버에 발송처리로 보냅니다", modal)
    assert found, f"모달 재진술 문장을 못 찾았다: {modal[:800]}"
    return int(found.group(1))


def _server_dispatch_count(link_id: int) -> int:
    """같은 집을 서버가 실제로 보내는 상품주문 수(네이버 호출 payload 로 센다)."""
    client = _StubClient()
    dispatch_order(db_session, client, link_id=int(link_id), actor_user_id=7)
    db_session.commit()
    return sum(len(call) for call in client.dispatch_calls)


def test_modal_does_not_count_the_sibling_naver_already_sent(client, workbench_on):
    """형제가 **판매자센터에서 이미 나갔으면** 모달이 그 건을 빼고 말한다.

    양성 표본이다 — 우리 표식은 하나도 없고 네이버 원본만 발송을 말한다. 옛 식
    (`집 전체 수 - 우리 표식 수`)은 여기서 3을 내놓는데 서버는 2건만 보낸다.
    """
    _login(client)
    lead = _collected(order_no="N-DSPC-NAVER", product="붙박이장 본품", amount=1000000)
    sib = _sibling(lead, product="구성 A", amount=2000)
    _sibling(lead, product="구성 B", amount=3000)
    _naver_sent(sib)

    pane = _pane_html(client, lead.id)
    modal = _modal_of(pane, "wb-modal-dispatch")

    assert _modal_dispatch_count(pane) == 2, modal
    assert "3건을 네이버에 발송처리" not in modal, "네이버가 이미 보낸 형제까지 세었다"
    assert "1건</b>은 다시 보내지 않습니다" in modal, "빠지는 건을 화면이 말하지 않는다"


def test_modal_count_equals_what_the_server_sends(client, workbench_on):
    """**화면 재진술 == 서버 발송 건수** — 두 신호가 섞인 집에서 한 번에 잰다.

    집은 4건이다: 우리가 보낸 1건 · 판매자센터가 보낸 1건 · 남은 2건.
    같은 pane 을 읽고 같은 집을 워커 경로로 보내, 화면이 약속한 수와 네이버로 나간 payload
    건수를 직접 맞대 본다. 이 단언이 없으면 두 식이 다시 갈려도 아무도 모른다.
    """
    _login(client)
    lead = _collected(order_no="N-DSPC-MIX", product="붙박이장 본품", amount=1000000)
    ours = _sibling(lead, product="구성 A", amount=2000)
    naver = _sibling(lead, product="구성 B", amount=3000)
    _sibling(lead, product="구성 C", amount=4000)
    _mark_dispatched(ours)
    _naver_sent(naver)

    promised = _modal_dispatch_count(_pane_html(client, lead.id))
    sent = _server_dispatch_count(lead.id)

    assert promised == 2, f"화면이 약속한 건수가 틀렸다: {promised}"
    assert promised == sent, f"화면 {promised}건 vs 서버 {sent}건 — 재진술이 갈렸다"


def test_a_clean_household_promises_every_product_order(client, workbench_on):
    """음성 대조군 — 양쪽 신호가 **하나도 없는** 집은 집 전체 수를 그대로 말한다.

    같은 모집단(발송처리 버튼이 열리는 집) 안에서 고른 반증축이다. 술어가 과하게 빼면
    화면이 과소 진술을 하고, 사람은 남은 건이 안 나간 줄 알고 판매자센터로 간다.
    """
    _login(client)
    lead = _collected(order_no="N-DSPC-CLEAN", product="붙박이장 본품", amount=1000000)
    _sibling(lead, product="구성 A", amount=2000)
    _sibling(lead, product="구성 B", amount=3000)

    pane = _pane_html(client, lead.id)
    modal = _modal_of(pane, "wb-modal-dispatch")

    assert _modal_dispatch_count(pane) == 3, modal
    assert "다시 보내지 않습니다" not in modal, "뺄 것이 없는데 뺐다고 말한다"
    assert _server_dispatch_count(lead.id) == 3, "정상 집의 발송이 줄었다"


def test_single_link_pane_without_household_counts_both_signals(client, workbench_on):
    """집이 없는 단건 pane 도 **두 신호**로 센다(폴백이 우리 표식만 보면 안 된다).

    큐 밖 단건은 `grp` 가 없어 템플릿 폴백 식이 답한다. 네이버가 이미 보낸 단건은 버튼이
    잠기므로(위 ①) 모달 자체가 없어야 한다 — 폴백이 1건이라고 말할 자리가 아예 없다.
    """
    _login(client)
    link = _collected(order_no="N-DSPC-ONE", product="붙박이장", amount=1000000)
    _naver_sent(link)

    pane = _pane_html(client, link.id)

    assert 'id="wb-modal-dispatch"' not in pane, "네이버가 이미 보낸 단건에 모달이 남았다"
    assert "건을 네이버에 발송처리로 보냅니다" not in pane, pane[-1500:]


def _partial_line(pane: str) -> str:
    """부분 발송 안내 줄(`wb-acts__why` 블록 중 '발송 완료'를 말하는 줄)."""
    lines = [chunk.split("</div>")[0] for chunk in pane.split('class="wb-acts__why')[1:]]
    return next((line for line in lines if "발송 완료" in line), "")


def test_partial_line_counts_the_seller_center_dispatch_too(client, workbench_on):
    """부분 발송 안내가 **판매자센터에서 나간 건도** 나간 것으로 센다.

    우리 표식만 세던 옛 식은 "2건 중 0건 발송 완료"라고 말했다 — 화면이 자기 눈앞의
    발송 기록을 없는 것처럼 다루는 거짓 문장이다.
    """
    _login(client)
    lead = _collected(order_no="N-DSPC-LINE", product="붙박이장 본품", amount=1000000)
    naver = _sibling(lead, product="구성 A", amount=2000)
    _naver_sent(naver)

    line = _partial_line(_pane_html(client, lead.id))

    assert "2건 중 <b>1건 발송 완료</b>" in line, line
    assert "0건 발송 완료" not in line, "판매자센터 발송을 세지 않았다"


def test_nothing_left_line_does_not_invent_a_blocking_reason(client, workbench_on):
    """남은 게 없는 집에는 "왜 못 보내는지"가 아니라 **보낼 게 없다**고 적는다.

    우리가 1건, 판매자센터가 1건 보낸 집이다. 옛 문장은 여기서 "네이버에 이미 발송 기록이
    있어 지금은 보낼 수 없습니다"라고 말했는데, 못 보내는 게 아니라 **보낼 것이 없다**.
    """
    _login(client)
    lead = _collected(order_no="N-DSPC-DONE", product="붙박이장 본품", amount=1000000)
    ours = _sibling(lead, product="구성 A", amount=2000)
    _mark_dispatched(ours)
    _naver_sent(lead)

    line = _partial_line(_pane_html(client, lead.id))

    assert "2건 중 <b>2건 발송 완료</b>" in line, line
    assert "더 보낼 상품주문이 없습니다" in line, line
    assert "지금은 보낼 수 없습니다" not in line, "보낼 것이 없는 집에 잠금 사유를 지어냈다"
