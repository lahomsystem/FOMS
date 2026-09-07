"""후보 표 ②열 — **쌍 판정**(지금 집 × 후보 주문) 계약 (2026-09-07).

왜 이 파일이 있는가
-------------------
후보 표 ②열은 오랫동안 **후보 주문에 붙은 집** 하나만 보고 신호를 적었다. 그래서 지금
붙이려는 집이 전부 취소된 옛 결제인데도, 후보 쪽이 살아 있기만 하면
`살아 있음 · 추가결제 신호` 라고 권했다. 실제 관계는 **재결제**다 — 지금 집이 옛 결제이고
후보 주문에 붙은 수집분이 새 결제다.

**두 축의 단위가 다르다.** 지금 집 쪽(``household_facts``)은 ``channel`` + ``group_key`` 로
접은 진짜 집이고, 후보 쪽(``_naver_facts``)은 ``order_id`` 로만 접은 **주문 단위 집계**다
— ``group_key`` 축이 없다. 그래서 이 파일은 후보 쪽을 '집'이라 부르지 않는다(재결제가 이미
붙은 주문은 옛 수집분과 새 수집분이 섞여 주문 단위로는 ``partial`` 로 나온다).

운영 실데이터(production, 2026-09-07 read-only 조회 · 확정 사실)
    고객 **이광헌** / 010-3380-7500 / 경기도 성남시 분당구 백현로 206 410동 1203호.

    * 집 ``2026090658033751`` — 링크 2203~2208(6건) 전부 ``CANCEL_DONE``, 아직 안 붙음
      (``order_id`` NULL · ``COLLECTED``) → 화면이 열고 있던 **지금 집**.
    * 집 ``2026090758601671`` — 링크 2209~2214(6건) 전부 ``PAYED``, 주문 **#5168** 에 붙음
      → 후보로 뜬 집(칩은 `살아 있음` 이 맞다).

    화면은 `살아 있음 · 추가결제 신호` 를 권했다. 그 권고는
    :func:`repay_reconcile.deposit_guidance` 의 '바꾸기/더하기' 로 갈려 **고객 청구액**까지
    흘러간다 — 잘못 고르면 예약금 안내 숫자가 틀린다.

여기서 못박는 것 다섯
---------------------
① 판정은 **쌍**이다 —
   ``recommended_relation(current_claim_code=…, candidate_claim_code=…)``.
② 칩(후보 쪽의 사실)과 신호(쌍 판정)는 **다른 축**이다 — 칩이 `살아 있음` 이어도 신호는
   재결제일 수 있다. 둘을 한 낱말로 뭉개면 이번 결함이 그대로 돌아온다.
③ 판정은 전부 **코드**다. 한국어 라벨을 ``==`` 로 견주지 않는다(2026-08-28 회귀 재발 방지).
   라벨 대조는 표시 축을 볼 때만 쓴다.
④ 화면이 실제로 따라오는지는 **렌더 결과**로 본다 — dict 만 보면 화면이 안 따라와도
   green 이 된다(파일 텍스트 검사는 다른 목적이라
   ``test_naver_candidate_evidence.py`` 가 이미 따로 한다).
⑤ **권고 축과 실행 축은 같은 칸에서 어긋나면 안 된다** — ``repay_reconcile.run_gate`` 가
   막는 칸(후보 ``all_pending``·``all_mixed``)과 사람이 봐야 하는 칸(``partial``)은 권고
   자체를 내지 않는다(10절).
"""

from __future__ import annotations

import re

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import group_key_text
from foms.services.integrations.naver_commerce.order_candidates import (
    find_order_candidates,
    recommended_relation,
    search_orders_for_attach,
)
from foms.services.integrations.naver_commerce.repay_reconcile import (
    attach_reconcile_plans,
)
from models import ExternalOrderLink, Order, User

TRIAGE_PATH = "/admin/naver-ingest/triage"
SEARCH_PATH = "/admin/naver-ingest/{link_id}/order-search"

#: ②열 신호 문구의 두 낱말. **판정 축이 아니라 표시 축**이다 — 화면이 실제로 그 말을
#: 적는지(그리고 반대말을 안 적는지)를 보는 음성 대조군에만 쓴다.
REPAY_TEXT = "재결제 신호"
ADDON_TEXT = "추가결제 신호"

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"{_SEQ[0]:04d}"


@pytest.fixture()
def workbench_on(monkeypatch):
    """워크벤치 게이트를 켠다 — 후보 표는 이 게이트 안에서만 산다."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


def _login(client) -> User:
    """관리자 1명으로 로그인한다(후보 표는 개인정보를 연다)."""
    user = User(username=f"wbpair_{_uid()}", password=generate_password_hash("pw"),
                role="ADMIN", team="CS", name="관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order(*, tel: str, name: str = "쌍판정고객") -> int:
    """후보로 잡힐 기존 ERP 주문 1건 — **id 를 돌려준다**.

    요청이 끝나면 세션이 걷히므로(``db_session.remove``) ORM 인스턴스는 detach 된다.
    요청 뒤에도 쓰는 값은 처음부터 정수로 들고 다닌다.
    """
    order = Order(received_date="2026-09-01", customer_name=name, phone=tel,
                  erp_phone_digits=tel.replace("-", ""),
                  address="경기 성남 분당 백현로 206 410동 1203호",
                  product="붙박이장", status="RECEIVED", payment_amount=0)
    db_session.add(order)
    db_session.commit()
    return int(order.id)


def _link(*, order_no: str, tel: str, amount: int, claim: str = "",
          order_id: int | None = None, name: str = "쌍판정고객") -> ExternalOrderLink:
    """수집 링크 1건. ``order_id`` 를 주면 그 주문에 이미 붙은 **후보 쪽 수집분**이 된다.

    ``claim`` 은 상품주문 단위 ``claimStatus`` 원문이다 — 집계는 ``aggregate_claim``(SSOT)
    이 하므로 여기서 코드를 손으로 만들지 않는다.
    """
    external_id = f"PO-PAIR-{_uid()}"
    product_order = {
        "productOrderId": external_id,
        "productName": "붙박이장",
        "totalPaymentAmount": amount,
        "shippingAddress": {"name": name, "tel1": tel,
                            "baseAddress": "경기 성남 분당 백현로 206",
                            "detailedAddress": "410동 1203호"},
    }
    if claim:
        product_order["claimStatus"] = claim
    snapshot = {"order": {"orderId": order_no, "ordererName": name, "ordererTel": tel},
                "productOrder": product_order}
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             external_order_no=order_no, raw_snapshot=snapshot,
                             group_key=group_key_text(snapshot),
                             sync_status="LINKED" if order_id else "COLLECTED",
                             order_id=order_id)
    db_session.add(link)
    db_session.commit()
    return link


def _candidate_row(link: ExternalOrderLink, order_id: int) -> dict:
    """그 후보 1건의 행만 뽑는다(다른 후보와 안 섞이게)."""
    rows = find_order_candidates(db_session, link)
    row = next((item for item in rows if item["order_id"] == order_id), None)
    assert row is not None, f"주문 #{order_id} 가 후보 표에 없다 — 전제가 깨졌다"
    return row


def _pane(client, *, link_id: int) -> str:
    """상세 pane 본문(HTTP). **렌더 결과**로 봐야 화면이 따라온 것을 증명한다."""
    response = client.get(TRIAGE_PATH, query_string={"tab": "work", "link_id": link_id})
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _seek(client, *, link_id: int, query: str) -> str:
    """찾아서 붙이기 결과 조각 본문(HTTP)."""
    response = client.get(SEARCH_PATH.format(link_id=link_id), query_string={"q": query})
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _attach_buttons(body: str) -> list[str]:
    """후보 표의 붙이기 버튼 여는 태그만 잘라 낸다(강조색 확인용)."""
    return re.findall(r"<button[^>]*wb-attach[^>]*>", body)


def _seek_buttons(body: str) -> list[str]:
    """검색 결과 조각의 붙이기 버튼 여는 태그(순서 그대로)."""
    return re.findall(r"<button[^>]*wb-seek-attach[^>]*>", body)


def _button_relation(button: str) -> str:
    """버튼 태그에서 관계 한 낱말을 뽑는다 — 순서 대조용."""
    match = re.search(r'data-relation="([A-Z]+)"', button)
    assert match, f"관계 없는 붙이기 버튼: {button}"
    return match.group(1)


def _reconcile_plans(link: ExternalOrderLink, order_id: int) -> dict:
    """그 후보 행의 정리 계획 — 템플릿이 ``cand.reconcile`` 로 읽는 바로 그 값이다."""
    rows = find_order_candidates(db_session, link)
    attach_reconcile_plans(db_session, rows)
    row = next(item for item in rows if item["order_id"] == order_id)
    return row["reconcile"]


# --------------------------------------------------------------------------- #
# 1. 운영 사고 재현 — 지금 집이 전부 취소면 후보 쪽이 살아 있어도 재결제다
# --------------------------------------------------------------------------- #

def test_all_canceled_current_household_recommends_repay(app):
    """지금 집 ``all_done`` × 후보 주문 ``alive`` → ``REPAY``. 칩은 그대로 `살아 있음`.

    운영 실데이터 그대로다(이광헌 / 지금 집 ``2026090658033751`` 전부 ``CANCEL_DONE`` ×
    후보 주문 **#5168** 의 수집분 ``2026090758601671`` 전부 ``PAYED``). 예전 판정은 후보 쪽만
    봐서 `추가결제 신호` 를 권했다.

    **칩과 신호는 다른 축**이라는 것도 여기서 못박는다 — ``naver_claim_code`` 는 여전히
    ``alive`` 여야 한다(후보 쪽의 사실은 바뀌지 않았다).
    """
    tel = "010-3380-7500"
    order_id = _order(tel=tel)
    # 후보 주문 #5168 자리 — 살아 있는 집(클레임 없음) 2건.
    _link(order_no="N-PAIR-1-CAND", tel=tel, amount=1_022_900, order_id=order_id)
    _link(order_no="N-PAIR-1-CAND", tel=tel, amount=587_880, order_id=order_id)
    # 지금 집 — 전부 취소 확정, 아직 안 붙음.
    current = _link(order_no="N-PAIR-1-CUR", tel=tel, amount=1_191_900, claim="CANCEL_DONE")
    _link(order_no="N-PAIR-1-CUR", tel=tel, amount=170_000, claim="CANCEL_DONE")

    row = _candidate_row(current, order_id)

    assert row["current_claim_code"] == "all_done", "지금 집이 판정 축에 없다"
    assert row["naver_claim_code"] == "alive", "후보 쪽의 사실(칩)까지 바뀌면 안 된다"
    assert row["recommended_relation"] == "REPAY", "권고 축이 쌍 판정을 안 읽는다"


# --------------------------------------------------------------------------- #
# 2. 음성 대조군 — 화면이 실제로 따라오는가 (렌더 결과)
# --------------------------------------------------------------------------- #

def test_pane_prints_the_repay_signal_and_never_the_addon_one(client, workbench_on):
    """같은 상황의 pane 본문에 `재결제 신호` 가 있고 `추가결제 신호` 는 **없다**.

    dict 만 보면 판정만 고치고 템플릿이 옛 축(``naver_claim_code``)으로 남아 있어도
    green 이 된다 — 그때 담당자 화면은 여전히 `추가결제 신호` 다. 그래서 본문을 본다.
    """
    _login(client)
    tel = "010-3380-7501"
    order_id = _order(tel=tel)
    _link(order_no="N-PAIR-2-CAND", tel=tel, amount=1_610_780, order_id=order_id)
    current = _link(order_no="N-PAIR-2-CUR", tel=tel, amount=1_191_900, claim="CANCEL_DONE")

    body = _pane(client, link_id=int(current.id))

    assert f"#{order_id}" in body, "후보 표에 그 주문이 없다 — 전제가 깨졌다"
    assert REPAY_TEXT in body, "지금 집이 옛 결제인데 재결제 신호를 안 적는다"
    assert ADDON_TEXT not in body, "후보 쪽만 보고 추가결제를 권한다(2026-09-07 운영 사고)"
    # 칩은 후보 쪽의 사실 그대로다 — 신호가 재결제라고 칩까지 죽은 낱말로 바꾸면
    # 담당자가 후보 주문의 수집분이 취소된 것으로 읽는다.
    assert "wb-cand__claim--alive" in body, "칩이 후보 쪽의 사실을 버렸다"
    # 눈이 가는 쪽도 권고를 따라간다(관계 오선택 → deposit_guidance → 고객 청구액).
    buttons = _attach_buttons(body)
    assert len(buttons) == 2, "붙이기 버튼이 두 개가 아니다"
    highlighted = [btn for btn in buttons if "btn-outline-primary" in btn]
    assert len(highlighted) == 1 and 'data-relation="REPAY"' in highlighted[0], \
        "권장 관계(재결제)가 강조색이 아니다"


# --------------------------------------------------------------------------- #
# 3~4. 회귀 아님 — 옛 동작 두 칸은 그대로다
# --------------------------------------------------------------------------- #

def test_both_households_alive_stays_addon(client, workbench_on):
    """지금 집 ``alive`` × 후보 주문 ``alive`` → ``ADDON`` (기존 동작 유지).

    쌍 판정이 들어왔다고 차액 결제까지 재결제로 뒤집히면 예약금이 '바꾸기'로 갈려
    고객이 낸 예약금이 화면에서 사라진다.
    """
    _login(client)
    tel = "010-3380-7502"
    order_id = _order(tel=tel)
    _link(order_no="N-PAIR-3-CAND", tel=tel, amount=1_191_900, order_id=order_id)
    current = _link(order_no="N-PAIR-3-CUR", tel=tel, amount=17_880)

    row = _candidate_row(current, order_id)
    body = _pane(client, link_id=int(current.id))

    assert row["current_claim_code"] == "alive"
    assert row["naver_claim_code"] == "alive"
    assert row["recommended_relation"] == "ADDON"
    assert ADDON_TEXT in body
    assert REPAY_TEXT not in body, "둘 다 살아 있는데 재결제를 권한다"


def test_canceled_candidate_still_repays_when_current_lives(client, workbench_on):
    """지금 집 ``alive`` × 후보 주문 ``all_done`` → ``REPAY`` (기존 동작 유지).

    이 칸은 쌍 판정 이전에도 재결제였다. 새 표가 옛 칸을 밟지 않았다는 음성 대조군이다.
    """
    _login(client)
    tel = "010-3380-7503"
    order_id = _order(tel=tel)
    _link(order_no="N-PAIR-4-CAND", tel=tel, amount=1_191_900, claim="CANCEL_DONE",
          order_id=order_id)
    current = _link(order_no="N-PAIR-4-CUR", tel=tel, amount=1_610_780)

    row = _candidate_row(current, order_id)
    body = _pane(client, link_id=int(current.id))

    assert row["current_claim_code"] == "alive"
    assert row["naver_claim_code"] == "all_done"
    assert row["recommended_relation"] == "REPAY"
    assert REPAY_TEXT in body
    assert ADDON_TEXT not in body


# --------------------------------------------------------------------------- #
# 5. 권하지 않음 — 사람이 봐야 하는 칸은 신호 줄 자체가 없다
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("tel, current_claims, expected_code", [
    ("010-3380-7511", ("CANCEL_DONE", ""), "partial"),
    ("010-3380-7512", ("CANCEL_REQUEST", "CANCEL_REQUEST"), "all_pending"),
])
def test_partial_or_pending_current_recommends_nothing(client, workbench_on,
                                                       tel, current_claims, expected_code):
    """지금 집이 ``partial``·``all_pending`` 이면 권고는 빈 문자열이다.

    일부만 취소됐거나 네이버가 아직 확정하지 않은 집이라 사람이 봐야 한다. 화면은
    **신호 줄을 아예 내지 않고** 버튼도 어느 쪽도 강조하지 않는다 — 강조가 곧 권고다.
    """
    _login(client)
    order_id = _order(tel=tel)
    _link(order_no=f"N-PAIR-5-CAND-{expected_code}", tel=tel, amount=1_191_900,
          order_id=order_id)
    current = None
    for index, claim in enumerate(current_claims):
        link = _link(order_no=f"N-PAIR-5-CUR-{expected_code}", tel=tel,
                     amount=500_000 + index, claim=claim)
        current = current or link

    row = _candidate_row(current, order_id)
    body = _pane(client, link_id=int(current.id))

    assert row["current_claim_code"] == expected_code, "지금 집 집계가 전제와 다르다"
    assert row["recommended_relation"] == "", "사람이 봐야 하는 칸인데 권고가 나왔다"
    assert REPAY_TEXT not in body and ADDON_TEXT not in body, "신호 줄이 남아 있다"
    buttons = _attach_buttons(body)
    assert len(buttons) == 2, "붙이기 버튼이 두 개가 아니다"
    assert not [btn for btn in buttons if "btn-outline-primary" in btn], \
        "아무 쪽도 권하지 않는데 한쪽이 강조색이다"


# --------------------------------------------------------------------------- #
# 6. 카브아웃 — 후보에 네이버 집이 아예 없으면 권하지 않는다
# --------------------------------------------------------------------------- #

def test_candidate_without_a_naver_household_recommends_nothing(client, workbench_on):
    """후보가 ERP 수기 주문(``naver_link_count == 0``)이면 지금 집이 무엇이든 권고는 없다.

    없는 집에 재결제를 권하면 ``deposit_guidance`` 가 '바꾸기'로 갈려 고객 청구액을
    건드린다. 화면은 `네이버 수집분 없음` 한 줄만 낸다(지금과 같다).
    """
    _login(client)
    tel = "010-3380-7520"
    order_id = _order(tel=tel)
    current = _link(order_no="N-PAIR-6-CUR", tel=tel, amount=800_000, claim="CANCEL_DONE")

    row = _candidate_row(current, order_id)
    body = _pane(client, link_id=int(current.id))

    assert row["current_claim_code"] == "all_done"
    assert row["naver_link_count"] == 0
    assert row["naver_claim_code"] == ""
    assert row["recommended_relation"] == ""
    assert "네이버 수집분 없음" in body
    assert REPAY_TEXT not in body and ADDON_TEXT not in body


# --------------------------------------------------------------------------- #
# 7. 문구와 버튼 강조는 **같은 키**를 읽는다
# --------------------------------------------------------------------------- #

#: 신호 문구 → 그 문구가 뜰 때 강조돼야 하는 버튼의 관계.
SIGNAL_TEXT_BY_RELATION = {"REPAY": REPAY_TEXT, "ADDON": ADDON_TEXT}


@pytest.mark.parametrize("current_claim, candidate_claim, expected", [
    ("CANCEL_DONE", "", "REPAY"),             # all_done x alive
    ("CANCEL_DONE", "CANCEL_DONE", "REPAY"),  # all_done x all_done
    ("", "", "ADDON"),                        # alive x alive
    ("", "CANCEL_DONE", "REPAY"),             # alive x all_done
    ("CANCEL_REQUEST", "", ""),               # all_pending x alive - 권하지 않음
])
def test_signal_text_and_button_highlight_read_the_same_key(
        client, workbench_on, current_claim, candidate_claim, expected):
    """②열 문구와 오른쪽 버튼 강조가 **한 판정**에서 나온다 — 렌더 결과로 본다.

    예전에는 payload 에 값이 똑같은 키가 둘 있었다(``relation_signal_code`` 는 문구가,
    ``recommended_relation`` 은 버튼이 읽었다). 이름이 둘이면 **한쪽만 고치는 경로**가
    열린다 — 표는 `재결제 신호` 라고 적어 놓고 강조된 버튼은 추가결제였던 2026-09-04
    결함이 바로 그 모양이다. 키를 하나로 줄였으니, 화면 두 층이 실제로 같은 답을 내는지
    를 dict 가 아니라 **본문**으로 못박는다.
    """
    _login(client)
    tel = f"010-3383-{_uid()}"
    order_id = _order(tel=tel)
    _link(order_no="N-PAIR-7-CAND", tel=tel, amount=900_000, claim=candidate_claim,
          order_id=order_id)
    current = _link(order_no="N-PAIR-7-CUR", tel=tel, amount=1_000_000, claim=current_claim)

    row = _candidate_row(current, order_id)
    body = _pane(client, link_id=int(current.id))

    assert row["recommended_relation"] == expected, "쌍 판정이 표와 다르다"
    assert "relation_signal_code" not in row,         "값이 같은 키에 이름을 둘 두면 한쪽만 고치는 경로가 다시 열린다"

    buttons = _attach_buttons(body)
    assert len(buttons) == 2, "붙이기 버튼이 두 개가 아니다"
    highlighted = [btn for btn in buttons if "btn-outline-primary" in btn]
    for relation, text in SIGNAL_TEXT_BY_RELATION.items():
        printed = text in body
        emphasized = any(f'data-relation="{relation}"' in btn for btn in highlighted)
        assert printed == emphasized,             f"{relation}: 문구({printed})와 버튼 강조({emphasized})가 갈렸다"
        assert printed == (relation == expected),             f"{relation}: 화면이 권고({expected!r})와 다른 말을 한다"


# --------------------------------------------------------------------------- #
# 8. 검색 경로도 같은 규칙이다
# --------------------------------------------------------------------------- #

def test_search_path_carries_the_same_pair_rule(client, workbench_on):
    """``search_orders_for_attach`` 행에도 쌍 판정이 같은 규칙으로 실린다.

    검색은 후보 0건일 때의 유일한 붙이기 경로다. 여기만 옛 축으로 남으면 자동 매칭이
    못 잡는 조합(가족 대리결제·시공지 변경·번호 변경) — 즉 **재결제가 가장 많은 자리** —
    에서 화면이 그대로 추가결제를 권한다.
    """
    _login(client)
    tel = "010-3382-7000"
    name = f"검색쌍판정{_uid()}"
    order_id = _order(tel=tel, name=name)
    _link(order_no="N-PAIR-8-CAND", tel=tel, amount=1_610_780, order_id=order_id, name=name)
    current = _link(order_no="N-PAIR-8-CUR", tel=tel, amount=1_191_900,
                    claim="CANCEL_DONE", name=name)

    result = search_orders_for_attach(db_session, current, query=name)
    row = next(item for item in result["rows"] if item["order_id"] == order_id)

    assert row["current_claim_code"] == "all_done"
    assert row["naver_claim_code"] == "alive", "칩은 후보 쪽의 사실 그대로다"
    assert row["recommended_relation"] == "REPAY"

    body = _seek(client, link_id=int(current.id), query=name)

    assert REPAY_TEXT in body
    assert ADDON_TEXT not in body, "검색 경로가 옛 축으로 남았다"
    repay_at = body.find('data-relation="REPAY"')
    addon_at = body.find('data-relation="ADDON"')
    assert repay_at > 0 and addon_at > 0, "붙이기 버튼이 없다"
    assert repay_at < addon_at, "재결제 신호인데 추가결제 버튼이 먼저 나온다"
    repay_btn = body[body.rfind("<button", 0, repay_at):repay_at]
    assert "btn-outline-primary" in repay_btn, "권장 관계가 강조색이 아니다"


# --------------------------------------------------------------------------- #
# 9. 표 자체의 전수 확인 — 어느 칸도 우연히 REPAY 가 되지 않게
# --------------------------------------------------------------------------- #

#: 판정 표를 손으로 옮긴 것이다(줄 = 지금 집, 칸 = **후보 주문**). 구현이 아니라 **계약**을
#: 적은 것이므로, 여기와 구현이 갈리면 구현을 고친다. 빈 문자열 키는 셀 것이 아예 없는
#: 쪽이다(후보 ``link_count == 0`` 또는 지금 집을 못 읽음) — 못 읽었다고 재결제를 권하지
#: 않는다.
#:
#: ``all_done`` 줄에서 ``partial``·``all_pending``·``all_mixed`` 칸이 비어 있는 이유:
#: 지금 집이 옛 결제라도 후보 쪽이 확정 전이거나 일부만 취소됐으면 **실행 축**
#: (``repay_reconcile.run_gate``)이 막거나 사람이 봐야 하는 칸이다. 권고 축과 실행 축이
#: 같은 칸에서 어긋나면 화면이 자기 말을 안 지킨다(10절이 렌더로 못박는다).
DECISION_GRID = {
    "": {"": "", "alive": "", "partial": "", "all_done": "",
         "all_pending": "", "all_mixed": ""},
    "alive": {"": "", "alive": "ADDON", "partial": "", "all_done": "REPAY",
              "all_pending": "", "all_mixed": ""},
    "partial": {"": "", "alive": "", "partial": "", "all_done": "",
                "all_pending": "", "all_mixed": ""},
    "all_done": {"": "", "alive": "REPAY", "partial": "", "all_done": "REPAY",
                 "all_pending": "", "all_mixed": ""},
    "all_pending": {"": "", "alive": "", "partial": "", "all_done": "",
                    "all_pending": "", "all_mixed": ""},
    "all_mixed": {"": "", "alive": "", "partial": "", "all_done": "",
                  "all_pending": "", "all_mixed": ""},
}


@pytest.mark.parametrize("current_code", sorted(DECISION_GRID))
def test_recommended_relation_matches_the_decision_table(current_code):
    """지금 집 코드 한 줄을 후보 코드 6칸과 **한 칸씩** 대조한다.

    ``claim_aggregate_code`` 가 내는 5종에 '수집분 없음'(빈 문자열)까지 넣어 6×6 = 36칸을
    전수로 본다. 표에 없는 칸이 우연히 REPAY 로 떨어지면 그 칸에서 예약금 안내가
    '바꾸기'로 갈린다.
    """
    actual = {candidate_code: recommended_relation(current_claim_code=current_code,
                                                   candidate_claim_code=candidate_code)
              for candidate_code in DECISION_GRID}

    assert actual == DECISION_GRID[current_code]


# --------------------------------------------------------------------------- #
# 10. 실행이 막히거나 사람이 봐야 하는 칸은 **권하지도 않는다** (렌더 계약 3칸)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("candidate_claims, expected_code, can_run", [
    (("CANCEL_REQUEST", "CANCEL_REQUEST"), "all_pending", False),
    (("CANCEL_DONE", "CANCEL_REQUEST"), "all_mixed", False),
    (("CANCEL_DONE", ""), "partial", True),
])
def test_all_done_current_never_recommends_an_unsettled_candidate(
        client, workbench_on, candidate_claims, expected_code, can_run):
    """지금 집 ``all_done`` × 후보 ``all_pending``/``all_mixed``/``partial`` → 권고 없음.

    지금 집이 옛 결제라는 것만으로 재결제를 권하면 **권고 축과 실행 축이 같은 칸에서
    어긋난다**. 확정 전 칸은 ``repay_reconcile.run_gate`` 가 실행 자체를 막으므로, 화면은
    ②열 한 칸 안에서 `네이버가 아직 확정하지 않았습니다`(칩 층)와 `재결제 신호`(신호 층)
    를 동시에 적고, 강조된 버튼이 여는 정리 계획의 `정리 실행` 은 애초에 눌리지 않는다.
    더 나쁜 쪽은 검색 경로의 붙이기 라우트다 — 거기엔 ``run_gate`` 가 없어 화면이 권한
    재결제가 그대로 실행된다. 그래서 이 세 칸은 **권고 자체를 내지 않는다**.

    ``partial`` 은 실행이 막히지는 않는다(``can_run`` 이 True 다). 그래도 권하지 않는
    이유는 다르다 — 후보 축은 집이 아니라 **주문 단위 집계**라, 재결제가 이미 한 번 붙은
    주문은 옛 수집분과 새 수집분이 섞여 ``partial`` 로 나온다. 사람이 봐야 하는 칸이다.
    """
    _login(client)
    tel = "010-3384-7000"
    name = f"막힌칸{_uid()}"
    order_id = _order(tel=tel, name=name)
    for index, claim in enumerate(candidate_claims):
        _link(order_no="N-PAIR-10-CAND", tel=tel, amount=900_000 + index, claim=claim,
              order_id=order_id, name=name)
    current = _link(order_no="N-PAIR-10-CUR", tel=tel, amount=1_191_900,
                    claim="CANCEL_DONE", name=name)

    row = _candidate_row(current, order_id)
    body = _pane(client, link_id=int(current.id))

    assert row["current_claim_code"] == "all_done", "지금 집 전제가 깨졌다"
    assert row["naver_claim_code"] == expected_code, "후보 쪽 집계 전제가 깨졌다"
    assert row["recommended_relation"] == ""

    # (a) 두 신호 문구 어느 쪽도 화면에 없다.
    assert REPAY_TEXT not in body, "실행이 막히거나 사람이 봐야 하는 칸에 재결제를 권한다"
    assert ADDON_TEXT not in body

    # (b) 어느 버튼도 강조되지 않는다 — 강조가 곧 권고다.
    buttons = _attach_buttons(body)
    assert len(buttons) == 2, "붙이기 버튼이 두 개가 아니다"
    assert not [btn for btn in buttons if "btn-outline-primary" in btn],         "아무 쪽도 권하지 않는데 한쪽이 강조색이다"

    # (c) 확정 전 칸은 실행 축도 막혀 있다(템플릿이 `정리 실행` 을 disabled 로 만드는 값).
    assert _reconcile_plans(current, order_id)["REPAY"]["can_run"] is can_run,         "실행 축 전제가 깨졌다 — 권고 축을 이 값과 견주는 것이 이 테스트의 뜻이다"

    # 검색 경로도 같은 3칸을 본다. 여기엔 실행 관문이 아예 없어 화면이 곧 실행이다.
    seek_row = next(item for item in
                    search_orders_for_attach(db_session, current, query=name)["rows"]
                    if item["order_id"] == order_id)
    assert seek_row["recommended_relation"] == ""

    seek_body = _seek(client, link_id=int(current.id), query=name)

    assert REPAY_TEXT not in seek_body, "검색 경로가 막힌 칸에 재결제를 권한다"
    assert ADDON_TEXT not in seek_body
    seek_buttons = _seek_buttons(seek_body)
    assert [_button_relation(btn) for btn in seek_buttons] == ["ADDON", "REPAY"],         "권고가 없으면 버튼 순서는 기본값 그대로다"
    assert not [btn for btn in seek_buttons if "btn-outline-primary" in btn],         "권고가 없는데 검색 경로가 한쪽을 강조한다"
