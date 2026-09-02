"""네이버 수집 워크벤치(UI 개편 본체) 계약 테스트 — 게이트 on 경로.

스펙 `docs/specs/2026-08-20-naver-ingest-workbench_SPEC.md`.

**왜 파일을 따로 두는가**: 기존 네이버 계약 테스트 79건 중 22건이 정확 마크업을 문다.
개편을 게이트 뒤에 두고 off 경로를 green 으로 유지해야, 개편 도중 들어오는 다른 회귀를
감지할 수 있다. 이 파일은 게이트를 켠 클라이언트로만 돈다.
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink, Order, User
from tests.services.integrations._markup import is_disabled, open_tag

TRIAGE_PATH = "/admin/naver-ingest/triage"

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


@pytest.fixture()
def workbench_on(monkeypatch):
    """워크벤치 게이트를 켠다(전역 on + 코호트 all)."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


def _login(client, *, role: str = "ADMIN") -> User:
    user = User(username=f"wb_{role.lower()}_{_uid()}", password=generate_password_hash("pw"),
                role=role, team="CS", name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _collected(*, order_no: str, product: str, amount: int, option: str = "",
               address: str = "서울 강남구 1", tel: str = "010-3333-4444",
               claim_status: str = "", place_status: str = "OK") -> ExternalOrderLink:
    """수집만 된 링크 1건 — 수집 파이프라인이 만드는 모양(묶음키 포함)."""
    external_id = f"PO-WB-{_uid()}"
    snapshot = {
        "order": {"orderId": order_no, "ordererName": "김주문",
                  "ordererTel": "010-1111-2222"},
        "productOrder": {
            "productOrderId": external_id, "productName": product,
            "productOption": option, "totalPaymentAmount": amount,
            "claimStatus": claim_status or None,
            # 기본은 발주확인 완료(OK) — 안 주면 코드가 '발주확인 전'으로 본다(정상 동작).
            "placeOrderStatus": place_status or None,
            "shippingAddress": {"name": "이수취", "tel1": tel,
                                "baseAddress": address, "detailedAddress": "101호"},
        },
    }
    # 매칭 축 사본 — 수집 파이프라인이 채우는 컬럼이다(`ingest._match_key_values`).
    # 이력 탭 서버 찾기가 이 컬럼을 보므로, 픽스처가 비워 두면 테스트만 실제와 다르게
    # 동작한다(주문이 아직 없는 수집분은 이름으로 찾을 길이 이 컬럼뿐이다).
    from foms.services.integrations.naver_commerce.ingest import _match_key_values

    match_keys = _match_key_values(snapshot)
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             sync_status="COLLECTED", external_order_no=order_no,
                             raw_snapshot=snapshot, group_key=group_key_text(snapshot),
                             recipient_name=match_keys["recipient_name"],
                             recipient_phone_digits=match_keys["recipient_phone_digits"],
                             orderer_phone_digits=match_keys["orderer_phone_digits"],
                             # 수집 파이프라인은 발주 상태도 컬럼에 복사한다(목록 필터가
                             # JSONB 를 스캔하지 않게 하려고). 픽스처도 같은 모양이어야
                             # '발주확인 전' 탭 모집단 테스트가 실제와 같은 것을 잰다.
                             place_order_status=place_status or None)
    db_session.add(link)
    db_session.commit()
    return link


# --------------------------------------------------------------------------- #
# 마크업 조각 뽑기
#
# v3 는 목록·상세·이력이 **한 문서**에 함께 있다. "화면에 그 글자가 있다" 만으로는
# 뜻이 안 지켜진다 — 목록에 있는지 상세에 있는지가 곧 계약이다(예: 관계 배지 vs 필터 칩).
# --------------------------------------------------------------------------- #

def _row_of(body: str, needle: str) -> str:
    """목록에서 그 글자가 든 집 한 줄(``<a class="wb-row" …</a>``)을 통째로 잘라 준다.

    **글자의 첫 등장 위치로 자르지 않는다.** 같은 글자가 한 줄 안에서 두 번 나오면
    (예: 제품명이 ``title`` 속성과 본문에 함께 들어간다) 첫 등장 기준으로 자른 꼬리가
    두 번째 등장 직전에서 끊겨, 뒤쪽 배지·라벨이 통째로 사라진 조각을 단언하게 된다.
    줄을 먼저 나누고 그 안에 글자가 있는지 보는 순서라야 마크업 순서에 안 묶인다.
    """
    for chunk in body.split('<a class="wb-row')[1:]:
        row = '<a class="wb-row' + chunk.split("</a>")[0]
        if needle in row:
            return row
    raise AssertionError(f"목록에 '{needle}' 이(가) 든 줄이 없다")


def _hist_row(body: str, needle: str) -> str:
    """이력 표에서 그 글자가 든 행(``<tr>…</tr>``)을 통째로 잘라 준다.

    **행을 먼저 통째로 자르고 그 다음에 고른다** — 낱말이 나온 자리에서 자르면 안 된다.
    같은 낱말이 한 행에 두 번 나오면(제품명은 ``data-find`` 속성과 제품 셀에 둘 다 있다)
    그 **두 자리 사이**만 잘려, 뒤쪽 액션 칸이 빠진 조각이 나온다. 그러면 "버튼이 없다"
    류 단언이 없는 자리를 보며 조용히 green 이 된다(2026-08-27 이력 행 ``data-find``
    도입 때 실제로 그렇게 무너졌다).
    """
    tbody = body.split('class="wb-cmp wb-hist"')[1].split("<tbody>")[1].split("</tbody>")[0]
    for chunk in tbody.split("<tr")[1:]:
        row = "<tr" + chunk.split("</tr>")[0]
        if needle in row:
            return row
    raise AssertionError(f"이력 표에 '{needle}' 이(가) 든 행이 없다")


def _pane(body: str) -> str:
    """상세 pane(``#wb-pane``) 안쪽만."""
    return body.split('id="wb-pane"')[1]


def _chip(body: str, name: str) -> str:
    """필터 칩 하나(``data-filter="…"`` 링크) — v2 의 탭 배지 자리."""
    return body.split(f'data-filter="{name}"')[1].split("</a>")[0]


def _row_count(body: str) -> int:
    """지금 목록에 뜬 집의 줄 수."""
    return body.count('<a class="wb-row')


# --------------------------------------------------------------------------- #
# 게이트
# --------------------------------------------------------------------------- #

def test_gate_off_keeps_the_old_screen(client):
    """게이트가 꺼져 있으면 지금 화면 그대로다 — 기본값은 off."""
    _login(client)
    _collected(order_no="N-WB-OFF", product="붙박이장", amount=100000)

    body = client.get(TRIAGE_PATH).get_data(as_text=True)

    assert "naver-workbench" not in body
    assert "수집 주문 확인" in body, "옛 화면 헤더가 그대로 있어야 한다"


def test_gate_on_renders_the_workbench(client, workbench_on):
    """게이트를 켠 사용자만 워크벤치를 본다."""
    _login(client)
    _collected(order_no="N-WB-ON", product="붙박이장", amount=100000)

    body = client.get(TRIAGE_PATH).get_data(as_text=True)

    assert "naver-workbench" in body


# --------------------------------------------------------------------------- #
# 탭 (결정 1) — 서버 ?tab= 라운드트립
# --------------------------------------------------------------------------- #

def test_two_tabs_and_four_chips_with_work_as_default(client, workbench_on):
    """v2 의 탭 4개는 **탭 2개 + 필터 칩 4개**가 됐다 — 한 집 처리하려고 탭을 오가던 자리.

    옛 뜻(네 갈래가 한 화면에서 손에 닿고 기본은 처리 탭)은 그대로다. 표현만
    탭 → 칩으로 내려왔다(계약 §1). `place`·`claim` 은 더 이상 탭이 아니다.
    """
    _login(client)
    _collected(order_no="N-WB-TAB", product="붙박이장", amount=100000)

    body = client.get(TRIAGE_PATH).get_data(as_text=True)

    assert 'data-tab="work"' in body
    assert 'data-tab="all"' in body
    assert 'data-tab="place"' not in body, "발주확인 전은 탭이 아니라 칩이다"
    assert 'data-tab="claim"' not in body, "취소·반품은 탭이 아니라 칩이다"
    # 네 갈래는 같은 목록의 필터 칩으로 남는다 — 라벨도 그대로 읽힌다.
    for key, label in (("all", "전체"), ("place", "발주확인 할 차례"),
                       ("rel", "추가결제·재결제"), ("claim", "취소·반품")):
        assert f'data-filter="{key}"' in body, key
        assert label in _chip(body, key), key
    assert "이력" in body, "이력 탭은 ADMIN 에게 그대로 있다"
    assert 'data-active-tab="work"' in body
    assert 'aria-selected="true"' in body.split('data-tab="work"')[1].split(">")[0]
    assert 'aria-pressed="true"' in _chip(body, "all"), "기본 필터는 전체다"


@pytest.mark.parametrize("tab", ["work", "all"])
def test_each_tab_responds(client, workbench_on, tab):
    """두 탭 모두 서버 라운드트립으로 열린다(새로고침·북마크가 그냥 된다)."""
    _login(client)
    _collected(order_no=f"N-WB-{tab}", product="붙박이장", amount=100000)

    response = client.get(f"{TRIAGE_PATH}?tab={tab}")

    assert response.status_code == 200
    assert f'data-active-tab="{tab}"' in response.get_data(as_text=True)


@pytest.mark.parametrize("f", ["all", "place", "rel", "claim"])
def test_each_filter_responds(client, workbench_on, f):
    """칩 4종도 서버 라운드트립이다 — 칩은 평범한 링크라 북마크·새로고침이 그냥 된다."""
    _login(client)
    _collected(order_no=f"N-WB-F-{f}", product="붙박이장", amount=100000, place_status="")

    response = client.get(f"{TRIAGE_PATH}?tab=work&f={f}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert f'data-active-filter="{f}"' in body
    assert 'aria-pressed="true"' in _chip(body, f)


def test_unknown_tab_falls_back_to_work(client, workbench_on):
    """이상한 tab 값은 조용히 기본 탭으로 — 주소를 손으로 고쳐도 화면이 안 죽는다."""
    _login(client)
    _collected(order_no="N-WB-BAD", product="붙박이장", amount=100000)

    body = client.get(f"{TRIAGE_PATH}?tab=nonsense").get_data(as_text=True)
    assert 'data-active-tab="work"' in body


# --------------------------------------------------------------------------- #
# 숫자 이중 표기 (결정 3)
# --------------------------------------------------------------------------- #

def test_header_shows_both_units_once(client, workbench_on):
    """헤더 한 곳에서만 집·상품주문을 함께 보여준다 — 단위 혼선의 해소 지점."""
    _login(client)
    # 한 집(같은 주문번호·주소)의 상품주문 3건.
    for idx in range(3):
        _collected(order_no="N-WB-DUAL", product=f"구성 {idx}", amount=1000)

    body = client.get(TRIAGE_PATH).get_data(as_text=True)

    assert "1주문" in body
    assert "상품주문 3건" in body


# --------------------------------------------------------------------------- #
# 상태 3층 (결정 4) — 색띠 + 글자 라벨
# --------------------------------------------------------------------------- #

def test_ready_row_says_it_can_be_handled_now(client, workbench_on):
    """색만으로 구분하면 색맹 사용자가 못 읽는다 — 글자 라벨을 함께 둔다."""
    _login(client)
    _collected(order_no="N-WB-READY", product="붙박이장", amount=100000)

    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    assert "지금 처리 가능" in body


def test_row_waiting_for_place_order_says_so_first(client, workbench_on):
    """발주확인이 안 끝난 집은 '발주확인 먼저' 다 — 순서를 화면이 말해 준다."""
    _login(client)
    _collected(order_no="N-WB-WAIT", product="붙박이장", amount=100000, place_status="")

    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    assert "발주확인 먼저" in body
    assert "지금 처리 가능" not in body


def test_claimed_row_says_do_not_touch(client, workbench_on):
    """취소·반품 집은 '손대지 않음' 이라고 글자로 말한다.

    W3 에서 이 집들은 전용 탭으로 옮겼다 — 처리 대기에는 더 이상 뜨지 않는다.
    """
    _login(client)
    _collected(order_no="N-WB-CLAIM", product="취소된 붙박이장", amount=100000,
               claim_status="CANCEL_DONE")

    body = client.get(f"{TRIAGE_PATH}?tab=claim").get_data(as_text=True)
    assert "손대지 않음" in body


# --------------------------------------------------------------------------- #
# 상품주문 펼침 + 2단 대조표 (결정 5·7)
# --------------------------------------------------------------------------- #

def test_detail_lists_every_product_order_of_the_household(client, workbench_on):
    """한 집의 상품주문 n건을 그 자리에서 다 읽는다 — 페이지를 n번 열지 않는다."""
    _login(client)
    first = _collected(order_no="N-WB-MULTI", product="붙박이장 본품", amount=800000,
                       option="색상: 화이트 / 폭: 2400")
    _collected(order_no="N-WB-MULTI", product="길이추가(1cm)", amount=12000,
               option="길이추가(1cm): 보테가 슬라이딩 1cm")

    body = client.get(f"{TRIAGE_PATH}?link_id={first.id}").get_data(as_text=True)

    assert "붙박이장 본품" in body
    assert "길이추가(1cm)" in body
    # 옵션 원문은 잘리지 않고 전문이 나온다(규격을 이걸 보고 채운다).
    assert "길이추가(1cm): 보테가 슬라이딩 1cm" in body


def test_comparison_is_two_sections_not_one_mixed_table(client, workbench_on):
    """집 단위 값과 상품주문 행 단위 값을 한 표에 섞지 않는다(감사 결함 #7)."""
    _login(client)
    link = _collected(order_no="N-WB-CMP", product="붙박이장", amount=500000)

    body = client.get(f"{TRIAGE_PATH}?link_id={link.id}").get_data(as_text=True)

    assert 'data-cmp-section="household"' in body
    assert 'data-cmp-section="product-orders"' in body


# --------------------------------------------------------------------------- #
# 불가역 액션 4종 세트 (결정 6)
# --------------------------------------------------------------------------- #

def test_create_order_modal_restates_the_count_and_warns(client, workbench_on):
    """건수 재진술 + 되돌릴 수 없음 + 사후 경로 — 셋 다 있어야 한다."""
    _login(client)
    first = _collected(order_no="N-WB-MODAL", product="붙박이장 본품", amount=800000)
    _collected(order_no="N-WB-MODAL", product="구성 A", amount=30000)

    body = client.get(f"{TRIAGE_PATH}?link_id={first.id}").get_data(as_text=True)

    modal = body.split('id="wb-modal-create"')[1].split("</div></div></div>")[0]
    assert "2건" in modal, "대상 건수가 문장으로 다시 나와야 한다"
    assert "되돌릴 수" in modal
    assert "규격" in modal, "누른 다음 무엇이 열리는지 알려야 한다"


def test_household_section_actually_shows_the_naver_values(client, workbench_on):
    """대조표에 **값이 들어 있어야** 한다 — 칸만 있고 비면 대조를 못 한다.

    실화: 템플릿이 `selected.naver.customer_name` 을 읽었는데 정본 키는
    `recipient_name` 이라 수취인·연락처 칸이 조용히 빈 채로 렌더됐다. 섹션 존재만
    확인하던 테스트는 이걸 못 잡았다.
    """
    _login(client)
    link = _collected(order_no="N-WB-VAL", product="붙박이장", amount=500000,
                      address="경기도 성남시 중원구 사기막골로150번길 10",
                      tel="010-9107-6677")

    body = client.get(f"{TRIAGE_PATH}?link_id={link.id}").get_data(as_text=True)
    section = body.split('data-cmp-section="household"')[1].split("</table>")[0]

    assert "이수취" in section, section[:400]
    assert "010-9107-6677" in section, section[:400]
    assert "경기도 성남시 중원구 사기막골로150번길 10" in section, section[:400]


def test_untouchable_row_does_not_also_say_create_order(client, workbench_on):
    """'손대지 않음' 줄이 동시에 '주문 만들기' 라고 말하면 안 된다.

    다음 할 일 배지(next_step)는 취소·반품 여부를 모른다. 그대로 찍으면 한 줄에서
    두 지시가 충돌해, 사람이 잠긴 버튼을 찾아 헤맨다.
    """
    _login(client)
    _collected(order_no="N-WB-CONTRA", product="취소된 붙박이장", amount=100000,
               claim_status="CANCEL_DONE")

    body = client.get(f"{TRIAGE_PATH}?tab=claim").get_data(as_text=True)
    row = body.split('wb-row--stop')[1].split("</a>")[0]

    assert "손대지 않음" in row
    assert "주문 만들기" not in row, row


# --------------------------------------------------------------------------- #
# 발주확인 전 탭 (W2)
# --------------------------------------------------------------------------- #

def test_place_tab_lists_only_households_awaiting_confirmation(client, workbench_on):
    """탭 모집단은 '발주확인이 아직인 집' 이다 — 끝난 집이 섞이면 헛클릭이 난다."""
    _login(client)
    _collected(order_no="N-PL-WAIT", product="기다리는 붙박이장", amount=100000, place_status="")
    _collected(order_no="N-PL-DONE", product="끝난 붙박이장", amount=100000, place_status="OK")

    body = client.get(f"{TRIAGE_PATH}?tab=place").get_data(as_text=True)

    assert "기다리는 붙박이장" in body
    assert "끝난 붙박이장" not in body


def test_place_chip_counts_households(client, workbench_on):
    """칩 숫자도 집 단위 — 한 집의 상품주문 3건이 3집으로 읽히면 안 된다(옛 탭 배지 자리)."""
    _login(client)
    for idx in range(3):
        _collected(order_no="N-PL-ONE", product=f"구성 {idx}", amount=1000, place_status="")

    body = client.get(f"{TRIAGE_PATH}?tab=work&f=place").get_data(as_text=True)
    assert "1주문" in _chip(body, "place"), _chip(body, "place")


def test_place_tab_has_a_checkbox_per_household(client, workbench_on):
    """선택은 집 단위다 — 상품주문마다 체크박스가 뜨면 같은 집을 여러 번 고르게 된다."""
    _login(client)
    _collected(order_no="N-PL-A", product="본품", amount=100000, place_status="")
    _collected(order_no="N-PL-A", product="구성", amount=1000, place_status="")
    _collected(order_no="N-PL-B", product="다른 집", amount=50000, place_status="")

    body = client.get(f"{TRIAGE_PATH}?tab=place").get_data(as_text=True)
    assert body.count('class="wb-pick"') == 2


def test_bulk_send_is_out_of_reach_until_something_is_selected(client, workbench_on):
    """선택이 없으면 발주확인 보내기에 손이 닿지 않는다.

    2026-08-14 일괄 완료처리 AS 증발 사고가 "선택 없이 버튼=전체 대상" 패턴에서 났다.
    되돌릴 수 없는 네이버 호출에 그 패턴을 다시 쓰지 않는다.

    v3 에서 표현이 바뀌었다: 옛 `#wb-place-submit` 의 서버 렌더 `disabled` 대신
    **벌크 바 자체가 접혀 있고**(`#wb-bulk` 는 `on` 없이 렌더 → CSS `display:none`),
    JS 가 선택 0집이면 보내기 버튼을 `disabled` 로 유지한다. 두 층을 함께 문다 —
    한 층만 보면 다른 층이 조용히 빠져도 테스트가 green 이다.
    """
    import pathlib

    _login(client)
    _collected(order_no="N-PL-GATE", product="붙박이장", amount=100000, place_status="")

    body = client.get(f"{TRIAGE_PATH}?tab=work&f=place").get_data(as_text=True)

    # ① 서버는 벌크 바를 **접힌 채로** 낸다(선택 0집).
    assert 'class="wb-bulk" id="wb-bulk"' in body, "벌크 바가 없거나 클래스가 바뀌었다"
    assert 'class="wb-bulk on"' not in body, "선택이 없는데 벌크 바가 펼쳐져 있다"
    assert 'id="wb-bulk-submit"' in body

    root = pathlib.Path(__file__).resolve().parents[3]
    # ② CSS 가 접는 층 — `on` 이 붙어야만 보인다.
    css = (root / "static/css/admin/naver-workbench.css").read_text(encoding="utf-8")
    bulk_block = css.split("#wb-bulk {")[1].split("}")[0]
    assert "display: none" in bulk_block, bulk_block
    assert "#wb-bulk.on" in css, "펼치는 규칙이 없으면 벌크가 영영 안 뜬다"
    # ③ JS 가 잠그는 층 — 0집이면 보내기 버튼이 죽어 있다.
    js = (root / "static/js/admin/naver-workbench.js").read_text(encoding="utf-8")
    assert "submit.disabled = chosen.length === 0" in js, "선택 0집에서 버튼이 살아 있다"


def test_bulk_modal_has_the_four_part_warning(client, workbench_on):
    """건수 재진술 + 되돌릴 수 없음 + 사후 경로 — 불가역 액션 4종 세트.

    v3 에서 `#wb-modal-place` 는 벌크 모달 `#wb-modal-bulk` 로 옮겨졌다(계약 §3.2).
    건수 재진술은 **집 수와 상품주문 건수 둘 다** 갱신된다 — 집 수만 읽히면 "2집" 이
    실제로 상품주문 9건인 걸 모른다.
    """
    _login(client)
    _collected(order_no="N-PL-MODAL", product="붙박이장", amount=100000, place_status="")

    body = client.get(f"{TRIAGE_PATH}?tab=work&f=place").get_data(as_text=True)
    modal = body.split('id="wb-modal-bulk"')[1].split("</div></div></div>")[0]

    assert "되돌릴 수" in modal
    assert "발송처리" in modal, "보낸 뒤 무엇이 열리는지 알려야 한다"
    assert 'id="wb-bulk-count"' in modal, "집 수는 선택에 따라 문장에서 갱신된다"
    assert 'id="wb-bulk-items"' in modal, "상품주문 건수도 함께 재진술한다"


def test_place_tab_shows_shipping_due_so_urgency_is_visible(client, workbench_on):
    """발송기한이 보여야 '왜 지금인지'를 안다 — 기한을 넘기면 네이버가 자동 취소한다."""
    _login(client)
    link = _collected(order_no="N-PL-DUE", product="붙박이장", amount=100000, place_status="")
    snapshot = dict(link.raw_snapshot)
    snapshot["productOrder"] = dict(snapshot["productOrder"], shippingDueDate="2026-09-08")
    link.raw_snapshot = snapshot
    db_session.commit()

    body = client.get(f"{TRIAGE_PATH}?tab=place").get_data(as_text=True)
    # 목록 배지는 **연도를 떼고** 보여준다(월-일). 기한은 전부 같은 해라 연도가 아무 결정도
    # 바꾸지 않는데, 19자를 그대로 쓰면 배지 줄이 접혀 행 높이가 튄다(2026-08-23 스테이징
    # 실측: 이 손질을 포함한 셋으로 58행이 같은 높이가 됐다). 상세·모달은 전체 날짜 그대로다.
    row = _row_of(body, "붙박이장")
    assert "발송기한 09-08" in row, row
    assert "2026-09-08" not in row, "목록 배지에 연도가 남았다"


def test_household_due_is_the_earliest_one_not_the_first_member(client, workbench_on):
    """집의 발송기한은 멤버 중 **가장 이른 값**이다 — 이력 탭과 같은 규칙(계약 §2.2).

    멤버 순서는 대표(최고금액) 우선이라 기한과 아무 상관이 없다. 첫 값을 그대로 쓰면
    같은 집이 처리 탭과 이력 탭에서 다른 날짜를 말하고, `임박순` 정렬이 이 값을 키로
    쓰므로 **더 급한 집이 아래로 내려간다**. 기한을 넘기면 네이버가 자동 취소하는 축이라
    그 어긋남이 그대로 손실이다.
    """
    _login(client)
    order_no = "N-PL-DUEMIN"
    lead = _collected(order_no=order_no, product="본품", amount=100000, place_status="")
    late = _collected(order_no=order_no, product="구성", amount=1000, place_status="")
    for link, due in ((lead, "2026-09-20"), (late, "2026-09-08")):
        snapshot = dict(link.raw_snapshot)
        snapshot["productOrder"] = dict(snapshot["productOrder"], shippingDueDate=due)
        link.raw_snapshot = snapshot
    db_session.commit()

    body = client.get(f"{TRIAGE_PATH}?tab=place").get_data(as_text=True)
    row = _row_of(body, "본품")

    assert "발송기한 09-08" in row, f"가장 이른 기한이 아니다: {row}"
    assert "09-20" not in row, "대표 멤버의 늦은 기한이 집을 대표했다"


def test_place_tab_excludes_claimed_households(client, workbench_on):
    """취소·반품 집은 발주확인 대상이 아니다 — 목록에 두면 잘못 눌린다."""
    _login(client)
    _collected(order_no="N-PL-CLAIM", product="취소된 붙박이장", amount=100000,
               place_status="", claim_status="CANCEL_DONE")

    body = client.get(f"{TRIAGE_PATH}?tab=place").get_data(as_text=True)
    assert "취소된 붙박이장" not in body


def test_place_chip_count_matches_the_list_length(client, workbench_on):
    """칩 숫자와 목록 줄 수가 같아야 한다 — 다르면 사람이 나머지를 찾아 헤맨다.

    실화: 배지는 SQL 로 세느라 취소·반품 집까지 포함했고, 목록은 그것들을 뺐다.
    "4집"이라고 써 놓고 3줄만 보였다. 취소 여부는 raw_snapshot 안에 있어 SQL 이 못
    거르므로, 세는 쪽과 뽑는 쪽이 **같은 술어**(`_group_matches_filter`)를 써야 한다.
    """
    _login(client)
    _collected(order_no="N-PB-1", product="집 하나", amount=100000, place_status="")
    _collected(order_no="N-PB-2", product="집 둘", amount=100000, place_status="")
    _collected(order_no="N-PB-CLAIM", product="취소된 집", amount=100000,
               place_status="", claim_status="CANCEL_DONE")

    body = client.get(f"{TRIAGE_PATH}?tab=work&f=place").get_data(as_text=True)

    assert "2주문" in _chip(body, "place"), _chip(body, "place")
    assert _row_count(body) == 2
    assert body.count('class="wb-pick"') == 2


# --------------------------------------------------------------------------- #
# 취소·반품 탭 (W3)
# --------------------------------------------------------------------------- #

def test_claim_tab_lists_only_claimed_households(client, workbench_on):
    """탭 모집단은 취소·반품 집이다."""
    _login(client)
    _collected(order_no="N-CL-OK", product="정상 붙박이장", amount=100000)
    _collected(order_no="N-CL-BAD", product="취소된 붙박이장", amount=100000,
               claim_status="CANCEL_DONE")

    body = client.get(f"{TRIAGE_PATH}?tab=claim").get_data(as_text=True)

    assert "취소된 붙박이장" in body
    assert "정상 붙박이장" not in body


def test_work_list_keeps_claimed_households_but_locks_the_row(client, workbench_on):
    """취소·반품 집은 목록에서 **빠지지 않고 잠긴 줄로 남는다**(v3 절대 규칙 6).

    v2 는 전용 탭으로 옮겨 처리 목록에서 뺐다. 그러면 "그 주문 어디 갔지" 가 되고,
    한 집을 확인하려고 탭을 오가게 된다 — 이 개편의 출발점이다. 대신 손댈 수 없다는
    사실을 줄에서 못 박는다: 체크박스 disabled + 잠금 클래스 + 글자 라벨.
    """
    _login(client)
    _collected(order_no="N-CL-W1", product="정상 붙박이장", amount=100000)
    _collected(order_no="N-CL-W2", product="취소된 붙박이장", amount=100000,
               claim_status="CANCEL_DONE")

    body = client.get(f"{TRIAGE_PATH}?tab=work").get_data(as_text=True)

    assert "정상 붙박이장" in body
    assert "취소된 붙박이장" in body, "잠글지언정 목록에서 없애지 않는다"
    locked = _row_of(body, "취소된 붙박이장")
    assert "wb-row--locked" in locked, locked
    assert "disabled" in locked, "잠긴 집이 벌크로 선택된다"
    assert "손대지 않음" in locked, "색만으로는 못 읽는다 — 글자 라벨이 함께 있어야 한다"
    # 멀쩡한 집은 그대로 고를 수 있다(잠금이 목록 전체로 번지지 않는다).
    assert "wb-row--locked" not in _row_of(body, "정상 붙박이장")


def test_chip_counts_match_their_own_filtered_lists(client, workbench_on):
    """칩 숫자는 그 칩이 실제로 보여줄 줄 수와 같아야 한다(W2 에서 낸 결함의 재발 방지)."""
    _login(client)
    _collected(order_no="N-CL-B1", product="정상 하나", amount=100000)
    _collected(order_no="N-CL-B2", product="정상 둘", amount=100000)
    _collected(order_no="N-CL-B3", product="취소된 하나", amount=100000,
               claim_status="CANCEL_DONE")

    body = client.get(f"{TRIAGE_PATH}?tab=work").get_data(as_text=True)

    # 칩 숫자(필터 전 전체에서 센다)
    assert "3주문" in _chip(body, "all"), _chip(body, "all")
    assert "1주문" in _chip(body, "claim"), _chip(body, "claim")
    # 목록은 하나다 — 취소 집도 잠긴 줄로 함께 있다.
    assert _row_count(body) == 3, "처리 목록은 3줄(취소 집 포함)"
    claim_only = client.get(f"{TRIAGE_PATH}?tab=work&f=claim").get_data(as_text=True)
    assert _row_count(claim_only) == 1, "취소·반품 칩은 1줄"


def test_claim_detail_locks_the_four_actions_but_allows_done(client, workbench_on):
    """주문 만들기·발주확인은 잠기고 '확인 완료'만 열린다(선행 결함 #4 의 화면 쪽).

    v3 에서 id 가 바뀌었다: `#wb-claim-create`→`#wb-create`, `#wb-claim-place`→`#wb-confirm`,
    `#wb-claim-done`→`#wb-review-done`(모든 집에 낸다). 뜻은 그대로 —
    **손댈 수 없는 집이라도 큐에서는 뺄 수 있어야 한다.**
    """
    _login(client)
    link = _collected(order_no="N-CL-ACT", product="취소된 붙박이장", amount=100000,
                      claim_status="CANCEL_DONE")

    body = client.get(f"{TRIAGE_PATH}?tab=work&f=claim&link_id={link.id}").get_data(as_text=True)

    assert 'id="wb-create"' in body
    assert is_disabled(body, "wb-create"), open_tag(body, "wb-create")
    assert 'id="wb-confirm"' in body
    assert is_disabled(body, "wb-confirm"), open_tag(body, "wb-confirm")
    done = open_tag(body, "wb-review-done")
    assert not is_disabled(body, "wb-review-done"), done


def test_claim_detail_shows_why_it_is_locked(client, workbench_on):
    """왜 잠겼는지 화면이 말해 준다 — 이유 없이 잠긴 버튼은 사람이 계속 누른다."""
    _login(client)
    link = _collected(order_no="N-CL-WHY", product="취소된 붙박이장", amount=100000,
                      claim_status="CANCEL_DONE")

    body = client.get(f"{TRIAGE_PATH}?tab=work&f=claim&link_id={link.id}").get_data(as_text=True)
    pane = _pane(body)

    # ① 상태를 사람 말로 — 클레임 라벨 그대로.
    assert "취소 완료" in pane
    # ② 무엇이 닫혔는지 한 줄로(계약 §3.3 목업 문장).
    assert "발주확인·발송처리·주문 만들기가 모두 닫혀 있습니다" in pane, pane[:800]
    # ③ 잠긴 버튼마다 이유가 붙는다 — title 이 없으면 사람은 계속 누른다.
    assert "판매자센터를 따릅니다" in open_tag(pane, "wb-create")


def test_marking_a_claimed_household_done_removes_it_from_the_tab(client, workbench_on):
    """버튼만 있고 서버가 안 받으면 큐에서 안 빠진다 — 라우트까지 확인한다."""
    _login(client)
    link = _collected(order_no="N-CL-DONE", product="취소된 붙박이장", amount=100000,
                      claim_status="CANCEL_DONE")
    link_id = link.id

    response = client.post(f"/admin/naver-ingest/{link_id}/review", json={})
    assert response.status_code == 200 and response.get_json()["success"] is True

    body = client.get(f"{TRIAGE_PATH}?tab=claim").get_data(as_text=True)
    assert "취소된 붙박이장" not in body


def test_default_selection_stays_inside_the_active_filter(client, workbench_on):
    """기본 선택은 **지금 보이는 목록 안에서** 고른다.

    실화: 큐 전체에서 첫 집을 골랐더니, 목록에는 없는 집이 오른쪽 상세에 펼쳐졌다.
    v3 에서 갈래를 정하는 건 탭이 아니라 필터 칩이다 — 판정 대상만 바뀌고 뜻은 같다.
    """
    _login(client)
    # 취소 집을 **먼저** 만들어 목록 둘째 줄로 보낸다(정렬은 수집 최신순).
    _collected(order_no="N-SEL-BAD", product="취소된 붙박이장", amount=100000,
               claim_status="CANCEL_DONE")
    _collected(order_no="N-SEL-OK", product="정상 붙박이장", amount=100000)

    everything = client.get(f"{TRIAGE_PATH}?tab=work").get_data(as_text=True)
    assert "정상 붙박이장" in _pane(everything), "목록 첫 줄이 펼쳐져야 한다"

    claim = client.get(f"{TRIAGE_PATH}?tab=work&f=claim").get_data(as_text=True)
    assert _row_count(claim) == 1
    assert "정상 붙박이장" not in claim, "필터에 맞지 않는 집이 목록에 남았다"
    assert "취소된 붙박이장" in _pane(claim), "목록에 없는 집이 오른쪽에 펼쳐졌다"


def test_explicit_link_id_is_honoured_even_across_filters(client, workbench_on):
    """사용자가 링크를 직접 지정했으면 그 뜻을 존중한다 — 조용히 다른 집으로 튀지 않는다.

    필터가 그 집을 가려도 마찬가지다(주소를 받아 연 사람은 그 집을 보러 온 것이다).
    """
    _login(client)
    _collected(order_no="N-SEL-A", product="첫째 집", amount=100000)
    wanted = _collected(order_no="N-SEL-B", product="둘째 집", amount=200000)

    body = client.get(
        f"{TRIAGE_PATH}?tab=work&f=claim&link_id={wanted.id}").get_data(as_text=True)
    pane = _pane(body)
    header = pane.split("wb-detail__title")[1].split("</div>")[0]

    assert _row_count(body) == 0, "취소·반품 칩이라 목록은 비어 있다"
    assert "둘째 집" in pane
    assert str(wanted.external_id) in header, header


# --------------------------------------------------------------------------- #
# 전체 이력 탭 (W4)
# --------------------------------------------------------------------------- #

def test_history_tab_keeps_claimed_rows_greyed_instead_of_dropping_them(client, workbench_on):
    """결정 2: 취소·반품은 탭으로 분리하되 이력에서 **빼지 않는다**.

    빼면 "그 주문 어디 갔지" 가 되고, 남기면 같은 자리에서 사실을 확인할 수 있다.
    Linnworks(Parked)·Amazon(Pending grayed out)이 독립적으로 같은 답을 냈다.
    """
    _login(client)
    _collected(order_no="N-H-OK", product="정상 붙박이장", amount=100000)
    _collected(order_no="N-H-BAD", product="취소된 붙박이장", amount=100000,
               claim_status="CANCEL_DONE")

    body = client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True)

    assert "정상 붙박이장" in body
    assert "취소된 붙박이장" in body, "이력에서 빼면 안 된다"
    row = body.split("취소된 붙박이장")[0].rsplit("<tr", 1)[1]
    assert "wb-hist--muted" in row, row


def test_history_rows_carry_no_actions_at_all(client, workbench_on):
    """회색으로 남기되 **액션 자체를 두지 않는다**(v3 절대 규칙 3).

    v2 는 잠긴 버튼(`disabled`)을 남겼다. 불가역 mutation 라우트는 전부 STAFF 까지
    열려 있어서, 이력 행에 버튼·`data-link-id` 를 두면 그 자리가 곧 과거 주문 전체에
    대한 취소·발송 조작면이 된다. 그래서 잠그는 게 아니라 **만들지 않는다**.
    """
    _login(client)
    _collected(order_no="N-H-LOCK", product="취소된 붙박이장", amount=100000,
               claim_status="CANCEL_DONE")

    body = client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True)
    row = _hist_row(body, "취소된 붙박이장")

    assert "<button" not in row, row
    assert "data-link-id" not in row, row
    assert "wb-hist--muted" in row, "취소·반품 줄은 회색으로 남는다"


def test_history_tab_filters_by_status(client, workbench_on):
    """상태 필터가 목록을 실제로 좁힌다."""
    _login(client)
    link = _collected(order_no="N-H-FAIL", product="실패한 수집", amount=100000)
    link.sync_status = "FAILED"
    link.failure_reason = "HTTP 500"
    db_session.commit()
    _collected(order_no="N-H-NORMAL", product="정상 수집", amount=100000)

    body = client.get(f"{TRIAGE_PATH}?tab=all&status=FAILED").get_data(as_text=True)

    assert "실패한 수집" in body
    assert "정상 수집" not in body


def test_history_pagination_keeps_tab_and_filter(client, workbench_on, monkeypatch):
    """페이지를 넘겨도 탭과 필터가 유지된다 — 선행 결함 #8 의 워크벤치 쪽."""
    from foms.web.admin import naver_ingest as mod

    # 이력 탭 페이징은 PAGE_SIZE 를 쓴다(처리 목록 상한 WORK_GROUP_LIMIT 과 별개다).
    monkeypatch.setattr(mod, "PAGE_SIZE", 1, raising=False)
    _login(client)
    for idx in range(3):
        _collected(order_no=f"N-H-PG-{idx}", product=f"집 {idx}", amount=1000, place_status="")

    body = client.get(f"{TRIAGE_PATH}?tab=all&place=PENDING").get_data(as_text=True)
    pager = body.split('class="wb-pager"')[1].split("</div>")[0]

    assert "tab=all" in pager, pager
    assert "place=PENDING" in pager, pager
    assert "page=2" in pager, pager


def test_history_tab_shows_the_failure_reason(client, workbench_on):
    """실패는 사유까지 보여야 한다 — 카운터만 있으면 무엇을 고쳐야 할지 모른다."""
    _login(client)
    link = _collected(order_no="N-H-WHY", product="실패한 수집", amount=100000)
    link.sync_status = "FAILED"
    link.failure_reason = "커머스API 인증 만료"
    db_session.commit()

    body = client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True)
    assert "커머스API 인증 만료" in body


def test_history_locked_row_says_why_instead_of_an_action(client, workbench_on):
    """왜 손댈 수 없는지 이유가 그 줄에 있어야 한다.

    v2 는 회색 버튼(`btn-outline-secondary`)으로 표현했다. v3 는 버튼을 아예 안 두므로
    (절대 규칙 3) **문장이 그 자리를 대신한다** — 이유 없이 아무것도 없으면 사람은
    "왜 여기만 링크가 없지" 하고 헤맨다.
    """
    _login(client)
    _collected(order_no="N-H-REASON", product="취소된 붙박이장", amount=100000,
               claim_status="CANCEL_DONE")

    body = client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True)
    row = _hist_row(body, "취소된 붙박이장")

    assert "취소·반품 진행 중 — 주문을 만들 수 없습니다." in row, row
    assert 'class="btn' not in row, row
    assert "btn-primary" not in row, row


# --------------------------------------------------------------------------- #
# 실패 4단계 결과 띠 (W5)
# --------------------------------------------------------------------------- #

def _with_failure(link, reason="커머스API 인증 만료", at="2026-08-20T10:44:00",
                  action="confirm"):
    """워커가 남긴 실패 기록을 붙인다(fulfillment.last_error)."""
    link.triage_state = {"fulfillment": {"last_error": reason, "last_error_at": at,
                                         "last_error_action": action}}
    db_session.commit()
    return link


def _with_dock_state(link):
    """실패와 무관한 다른 축의 triage_state(도크 체크) — 실패 목록에 끼면 안 된다."""
    link.triage_state = {"dock": {"checked": True}}
    db_session.commit()
    return link


def test_result_strip_is_absent_when_nothing_failed(client, workbench_on):
    """실패가 없으면 띠 자체가 뜨지 않는다 — 빈 경고는 사람이 안 읽게 만든다."""
    _login(client)
    _collected(order_no="N-R-OK", product="정상 붙박이장", amount=100000)

    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    assert 'id="wb-result"' not in body


def test_result_strip_counts_failures(client, workbench_on):
    """① 카운터 — 몇 집이 실패했는지 먼저 말한다."""
    _login(client)
    _with_failure(_collected(order_no="N-R-F1", product="실패 하나", amount=100000))
    _with_failure(_collected(order_no="N-R-F2", product="실패 둘", amount=100000))
    _collected(order_no="N-R-OK2", product="정상", amount=100000)

    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    strip = body.split('id="wb-result"')[1].split("</section>")[0]
    assert "실패 2주문" in strip, strip[:400]


def test_result_strip_lists_each_failure_with_its_reason(client, workbench_on):
    """②③ 실패 전용 목록 + 건별 사유 — 카운터만 있으면 무엇을 고칠지 모른다."""
    _login(client)
    _with_failure(_collected(order_no="N-R-WHY", product="실패 건", amount=100000),
                  reason="이미 발주확인된 주문입니다")

    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    strip = body.split('id="wb-result"')[1].split("</section>")[0]
    assert "이미 발주확인된 주문입니다" in strip, strip[:400]


def test_result_strip_offers_retry_for_failed_only(client, workbench_on):
    """④ 실패건만 재시도 — 성공한 집을 다시 보내지 않는다."""
    _login(client)
    failed = _with_failure(_collected(order_no="N-R-RETRY", product="실패 건", amount=100000))
    _collected(order_no="N-R-DONE", product="성공 건", amount=100000)

    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    strip = body.split('id="wb-result"')[1].split("</section>")[0]
    ids = strip.split('id="wb-retry-failed"')[1].split('data-link-ids="')[1].split('"')[0]
    assert str(failed.id) in ids
    assert len(ids.split(",")) == 1, ids


def test_result_strip_is_not_auto_dismissed(client, workbench_on):
    """5초 자동닫힘이 실패 문구를 지우면 안 된다(03 감사 결함 #5 와 같은 함정)."""
    _login(client)
    _with_failure(_collected(order_no="N-R-KEEP", product="실패 건", amount=100000))

    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    strip = body.split('id="wb-result"')[1].split("</section>")[0]
    assert "data-foms-no-autodismiss" in strip, strip[:300]


def test_result_strip_shows_on_every_tab(client, workbench_on):
    """실패는 어느 탭에 있든 보여야 한다 — 탭을 옮겼다고 사고가 사라지지 않는다."""
    _login(client)
    _with_failure(_collected(order_no="N-R-TABS", product="실패 건", amount=100000))

    for tab in ("work", "place", "claim", "all"):
        body = client.get(f"{TRIAGE_PATH}?tab={tab}").get_data(as_text=True)
        assert 'id="wb-result"' in body, tab


# --------------------------------------------------------------------------- #
# 리다이렉트 (W6)
# --------------------------------------------------------------------------- #

def test_ingest_dashboard_redirects_to_the_workbench_when_gate_is_on(client, workbench_on):
    """게이트가 켜지면 두 URL 왕복이 끝난다 — 옛 주소는 본진으로 보낸다."""
    _login(client)

    response = client.get("/admin/naver-ingest")

    assert response.status_code in (301, 302)
    assert "/admin/naver-ingest/triage" in response.headers["Location"]


def test_ingest_dashboard_keeps_working_when_gate_is_off(client):
    """게이트가 꺼져 있으면 옛 관리 화면이 그대로다 — 롤백이 실제로 된다."""
    _login(client)

    response = client.get("/admin/naver-ingest")

    assert response.status_code == 200
    assert "네이버 주문 수집" in response.get_data(as_text=True)


def test_redirect_carries_the_history_filter_over(client, workbench_on):
    """필터를 걸어 둔 채 옛 주소로 들어와도 그 조건이 살아남는다."""
    _login(client)

    response = client.get("/admin/naver-ingest?status=FAILED&place=PENDING")
    location = response.headers["Location"]

    assert "tab=all" in location, location
    assert "status=FAILED" in location, location
    assert "place=PENDING" in location, location


# --------------------------------------------------------------------------- #
# 전체 이력 탭의 권한 경계 (리뷰 지적 P1)
#
# `naver_ingest_dashboard`(수집 이력·상태 집계·실패 사유)는 ADMIN 전용인데,
# 워크벤치는 STAFF 도 여는 라우트 안에 그 데이터를 다시 냈다. 회귀가 아니라 **신규 노출**이다.
# --------------------------------------------------------------------------- #

def test_history_tab_is_admin_only(client, workbench_on):
    """STAFF 가 ?tab=all 을 열어도 수집 이력이 나오면 안 된다 — 작업 탭으로 떨어진다."""
    _login(client, role="STAFF")
    link = _collected(order_no="N-PERM-HIST", product="권한 붙박이장", amount=100000)
    link.sync_status = "FAILED"
    link.failure_reason = "커머스API 인증 만료"
    db_session.commit()

    body = client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True)

    assert 'data-active-tab="work"' in body, "비 ADMIN 은 이력 탭을 열 수 없다"
    assert "커머스API 인증 만료" not in body, "수집 실패 사유가 STAFF 에게 새면 안 된다"
    assert "전체 이력" not in body, "열 수 없는 탭은 아예 보이지 않는다"


def test_history_tab_stays_open_for_admin(client, workbench_on):
    """ADMIN 에게는 그대로 열린다 — 권한을 좁히다 기능을 죽이지 않는다."""
    _login(client, role="ADMIN")
    link = _collected(order_no="N-PERM-ADMIN", product="관리자 붙박이장", amount=100000)
    link.sync_status = "FAILED"
    link.failure_reason = "커머스API 인증 만료"
    db_session.commit()

    body = client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True)

    assert 'data-active-tab="all"' in body
    assert "커머스API 인증 만료" in body
    assert "전체 이력" in body


def test_manager_also_cannot_open_history_tab(client, workbench_on):
    """MANAGER 도 마찬가지다 — 기준은 기존 수집 관리 화면(`ADMIN` 전용)과 같아야 한다."""
    _login(client, role="MANAGER")
    _collected(order_no="N-PERM-MGR", product="매니저 붙박이장", amount=100000)

    body = client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True)

    assert 'data-active-tab="work"' in body
    assert "전체 이력" not in body


# --------------------------------------------------------------------------- #
# 결과 띠의 재시도 대상·조회 창 (리뷰 지적 P4)
# --------------------------------------------------------------------------- #

def test_retry_uses_the_action_that_actually_failed(client, workbench_on):
    """발송처리가 실패한 집은 **발송처리**로 다시 시도한다.

    항상 발주확인으로 보내면 이미 발주확인이 끝난 집이라 멱등 규칙에 걸려 조용히
    넘어가고, 실패 사유는 지워지지 않아 띠가 영원히 남는다.
    """
    _login(client)
    confirmed = _with_failure(_collected(order_no="N-RA-C", product="발주확인 실패", amount=1000),
                              reason="처리권한이 없는 상품주문번호", action="confirm")
    dispatched = _with_failure(_collected(order_no="N-RA-D", product="발송처리 실패", amount=1000),
                               reason="발송 가능 상태가 아닙니다", action="dispatch")

    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    strip = body.split('id="wb-result"')[1].split("</section>")[0]
    ids = strip.split('id="wb-retry-failed"')[1].split('data-link-ids="')[1].split('"')[0]

    assert f"{confirmed.id}:confirm" in ids, ids
    assert f"{dispatched.id}:dispatch" in ids, ids


def test_failure_row_says_which_action_failed(client, workbench_on):
    """사유 옆에 어느 작업이 실패했는지 적는다 — 같은 사유라도 대응이 다르다."""
    _login(client)
    _with_failure(_collected(order_no="N-RA-LABEL", product="발송처리 실패", amount=1000),
                  reason="발송 가능 상태가 아닙니다", action="dispatch")

    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    strip = body.split('id="wb-result"')[1].split("</section>")[0]
    row = strip.split("발송 가능 상태가 아닙니다")[0].rsplit("<tr", 1)[1]

    assert "발송처리" in row, row


def test_failure_strip_finds_failures_outside_the_recent_window(client, workbench_on, monkeypatch):
    """오래 전에 수집된 집이 오늘 실패해도 띠에 뜬다.

    최근 수집분 N건만 읽어 파이썬으로 거르면, 그 뒤로 수집이 많이 쌓인 집의 실패는
    창 밖으로 밀려 화면에서 사라진다 — 실패는 수집 시각이 아니라 실패했다는 사실로 찾아야 한다.
    """
    from foms.web.admin import naver_ingest as mod

    monkeypatch.setattr(mod, "QUEUE_LINK_FETCH_LIMIT", 2, raising=False)
    _login(client)
    old_failure = _with_failure(_collected(order_no="N-RW-OLD", product="옛 수집 실패", amount=1000),
                                reason="이미 발주확인된 주문입니다")
    for idx in range(3):
        _with_dock_state(_collected(order_no=f"N-RW-NEW-{idx}", product=f"새 수집 {idx}", amount=1000))

    body = client.get(TRIAGE_PATH).get_data(as_text=True)

    assert 'id="wb-result"' in body, "실패가 있는데 띠가 없다"
    strip = body.split('id="wb-result"')[1].split("</section>")[0]
    assert "이미 발주확인된 주문입니다" in strip, strip[:400]
    assert str(old_failure.id) in strip


# --------------------------------------------------------------------------- #
# 발송처리 (리뷰 지적 P4 — 게이트를 켜면 옛 화면에 있던 기능이 사라졌다)
#
# 네이버에 "물건이 나갔다"를 알리는 불가역 호출이다. 발주확인이 끝난 집에만 연다.
# --------------------------------------------------------------------------- #

def _dispatched(link, at="2026-08-20T11:00:00"):
    """이미 발송처리된 집(워커의 멱등 기록)."""
    link.triage_state = {"fulfillment": {"place_confirmed_at": "2026-08-20T10:00:00",
                                         "dispatched_at": at}}
    db_session.commit()
    return link


def test_dispatch_button_opens_for_a_confirmed_household(client, workbench_on):
    """발주확인이 끝난 집에는 발송처리 버튼이 열린다."""
    _login(client)
    link = _collected(order_no="N-DSP-OK", product="붙박이장", amount=100000, place_status="OK")

    body = client.get(f"{TRIAGE_PATH}?link_id={link.id}").get_data(as_text=True)
    head = open_tag(body, "wb-dispatch")

    assert not is_disabled(body, "wb-dispatch"), head
    assert 'id="wb-modal-dispatch"' in body, "불가역 호출은 확인 모달을 거친다"


def test_dispatch_modal_restates_the_count_and_says_it_is_irreversible(client, workbench_on):
    """결정 6 불가역 4종 세트 — 건수 재진술·되돌릴 수 없음·사후 경로."""
    _login(client)
    link = _collected(order_no="N-DSP-MODAL", product="붙박이장", amount=100000, place_status="OK")
    _collected(order_no="N-DSP-MODAL", product="상판 추가", amount=10000, place_status="OK")

    body = client.get(f"{TRIAGE_PATH}?link_id={link.id}").get_data(as_text=True)
    modal = body.split('id="wb-modal-dispatch"')[1].split('id="wb-dispatch-confirm"')[0]

    assert "2건" in modal, modal[:600]
    assert "되돌릴 수 없" in modal, modal[:600]
    assert "data-foms-no-autodismiss" in modal, modal[:600]


def test_dispatch_button_is_locked_before_place_confirm(client, workbench_on):
    """발주확인 전에는 잠근다 — 네이버가 거절하는 호출을 화면이 열어 두면 헛클릭이다."""
    _login(client)
    link = _collected(order_no="N-DSP-WAIT", product="붙박이장", amount=100000, place_status="")

    body = client.get(f"{TRIAGE_PATH}?link_id={link.id}").get_data(as_text=True)
    head = open_tag(body, "wb-dispatch")

    assert is_disabled(body, "wb-dispatch"), head
    assert "발주확인" in head, "잠긴 이유를 버튼에 달아 둔다"


def test_dispatch_shows_done_badge_instead_of_button(client, workbench_on):
    """이미 발송처리된 집은 버튼이 아니라 완료 표시다(두 번 부르지 않는다)."""
    _login(client)
    link = _dispatched(_collected(order_no="N-DSP-DONE", product="붙박이장",
                                  amount=100000, place_status="OK"))

    body = client.get(f"{TRIAGE_PATH}?link_id={link.id}").get_data(as_text=True)

    assert "발송처리 완료" in body
    assert 'id="wb-dispatch"' not in body


def test_dispatch_is_locked_for_claimed_household(client, workbench_on):
    """취소·반품 집에는 발송처리를 보낼 수 없다 — 손대지 않는 집이다.

    v2 는 버튼을 **안 냈다**. v3 는 **잠가서 낸다**(계약 §3.3): 버튼이 통째로 사라지면
    사람은 "왜 없지"를 화면 밖에서 추측한다 — 이유를 붙인 잠긴 버튼이 낫다.
    보내는 길(모달·확인 버튼)은 그대로 없다.
    """
    _login(client)
    link = _collected(order_no="N-DSP-CLAIM", product="붙박이장", amount=100000,
                      place_status="OK", claim_status="CANCEL_REQUEST")

    body = client.get(f"{TRIAGE_PATH}?tab=work&f=claim&link_id={link.id}").get_data(as_text=True)

    head = open_tag(body, "wb-dispatch")
    assert is_disabled(body, "wb-dispatch"), head
    assert 'id="wb-modal-dispatch"' not in body, "잠긴 집에 발송처리 모달이 열려 있다"
    assert 'id="wb-dispatch-confirm"' not in body


# --------------------------------------------------------------------------- #
# 발주확인 전 탭의 클레임 판정 (리뷰 지적 P4)
#
# 모집단을 '발주확인 전' 링크로 먼저 좁힌 뒤 클레임을 판정하면, 이미 발주확인이 끝난
# 형제의 취소를 못 본다 — 취소가 걸린 집에 발주확인이 나간다.
# --------------------------------------------------------------------------- #

def test_place_filter_drops_household_whose_sibling_is_claimed(client, workbench_on):
    """형제 상품주문이 취소 중이면 그 집은 발주확인 대상이 아니다.

    v3 에서 그 집은 화면에서 사라지지 않는다 — **취소·반품 칩**으로 옮겨가 잠긴 줄로
    남는다(절대 규칙 6). 발주확인 칩에서 빠지는 것이 지켜야 할 뜻이다.
    """
    _login(client)
    _collected(order_no="N-PC-MIX", product="취소된 형제", amount=100000,
               place_status="OK", claim_status="CANCEL_REQUEST")
    _collected(order_no="N-PC-MIX", product="남은 형제", amount=50000, place_status="")

    body = client.get(f"{TRIAGE_PATH}?tab=work&f=place").get_data(as_text=True)

    assert _row_count(body) == 0, "취소가 걸린 집이 발주확인 목록에 남아 있다"
    assert "0주문" in _chip(body, "place"), _chip(body, "place")
    assert "이 필터에 해당하는 주문이 없습니다" in body
    # 사라지지는 않는다 — 취소·반품 칩에 잠긴 줄로 있다.
    claim = client.get(f"{TRIAGE_PATH}?tab=work&f=claim").get_data(as_text=True)
    assert _row_count(claim) == 1
    assert "wb-row--locked" in claim


def test_place_chip_count_matches_the_list_after_the_claim_check(client, workbench_on):
    """칩 숫자도 같이 줄어든다 — '2집' 이라 써 놓고 1줄이면 사람이 나머지를 찾아 헤맨다."""
    _login(client)
    _collected(order_no="N-PC-MIX2", product="취소된 형제", amount=100000,
               place_status="OK", claim_status="CANCEL_REQUEST")
    _collected(order_no="N-PC-MIX2", product="남은 형제", amount=50000, place_status="")
    _collected(order_no="N-PC-OK", product="정상 집", amount=70000, place_status="")

    body = client.get(f"{TRIAGE_PATH}?tab=work&f=place").get_data(as_text=True)

    assert "1주문" in _chip(body, "place"), _chip(body, "place")
    assert _row_count(body) == 1
    assert "정상 집" in body


# --------------------------------------------------------------------------- #
# 큐 밖 링크를 열었을 때 (2차 리뷰)
#
# 확인 완료된 집·조회 상한 밖 집도 pane 은 열 수 있다(발주확인·발송처리가 거기 있다).
# 그때 selected_group 이 없어 ① 모달이 "1건" 이라 거짓말하고 ② 상품주문 표가 빈 표가 됐다.
# --------------------------------------------------------------------------- #

def _reviewed(link, at="2026-08-20T09:00:00"):
    """확인 완료 처리(큐에서 빠진다)."""
    import datetime as _dt

    link.reviewed_at = _dt.datetime.fromisoformat(at)
    db_session.commit()
    return link


def test_out_of_queue_link_still_shows_its_product_orders(client, workbench_on):
    """큐에서 빠진 집을 열어도 상품주문 표가 채워진다 — 옛 화면에는 있던 값이다."""
    _login(client)
    lead = _collected(order_no="N-OOQ", product="붙박이장 3600", amount=1800000,
                      option="색상: 화이트")
    sibling = _collected(order_no="N-OOQ", product="상판 추가", amount=120000)
    _reviewed(lead)
    _reviewed(sibling)

    body = client.get(f"{TRIAGE_PATH}?link_id={lead.id}").get_data(as_text=True)

    assert "상품주문 2건" in body, "묶음 건수를 표 제목이 말해야 한다"
    assert "붙박이장 3600" in body
    assert "상판 추가" in body, "형제 상품주문이 표에서 빠졌다"


def test_out_of_queue_create_modal_states_the_real_count(client, workbench_on):
    """불가역 모달이 실제로 만들 건수를 말한다 — 1건이라 해 놓고 2건을 합치면 안 된다."""
    _login(client)
    lead = _collected(order_no="N-OOQ-M", product="붙박이장 3600", amount=1800000)
    sibling = _collected(order_no="N-OOQ-M", product="상판 추가", amount=120000)
    _reviewed(lead)
    _reviewed(sibling)

    body = client.get(f"{TRIAGE_PATH}?link_id={lead.id}").get_data(as_text=True)
    modal = body.split('id="wb-modal-create"')[1].split('id="wb-create-order"')[0]

    assert "상품주문\n                                2건" in modal or "2건" in modal, modal[:500]
    assert "1건을" not in modal, modal[:500]


# --------------------------------------------------------------------------- #
# '발주확인 전' 탭의 조회 상한·클레임 판정 (2차 리뷰)
# --------------------------------------------------------------------------- #

def test_place_tab_says_when_the_list_is_truncated(client, workbench_on, monkeypatch):
    """상한에 걸려 잘렸으면 잘렸다고 말한다 — 조용히 자르면 나머지를 찾아 헤맨다."""
    from foms.web.admin import naver_ingest as mod

    # 목록 상한의 SSOT 는 WORK_GROUP_LIMIT 다(2026-08-24: 캡을 원천별이 아니라
    # **병합 뒤 한 곳**으로 옮겼다). PAGE_SIZE 는 이력 페이징용이라 여기선 안 문다.
    monkeypatch.setattr(mod, "WORK_GROUP_LIMIT", 1, raising=False)
    _login(client)
    for idx in range(3):
        _collected(order_no=f"N-TRUNC-{idx}", product=f"집 {idx}", amount=1000,
                   place_status="", address=f"서울 강남구 {idx}", tel=f"010-7777-000{idx}")

    body = client.get(f"{TRIAGE_PATH}?tab=place").get_data(as_text=True)

    assert "먼저 처리" in body or "더 있습니다" in body, "잘림 안내가 없다"
    assert body.count('class="wb-pick"') == 1, "상한만큼만 보여야 한다"


def test_place_tab_has_no_truncation_notice_when_everything_fits(client, workbench_on):
    """다 보이면 안내를 띄우지 않는다 — 빈 경고는 사람이 안 읽게 만든다."""
    _login(client)
    _collected(order_no="N-FITS", product="집 하나", amount=1000, place_status="")

    body = client.get(f"{TRIAGE_PATH}?tab=place").get_data(as_text=True)

    assert "더 있습니다" not in body


def test_place_filter_drops_household_when_the_claim_is_inside_the_population(client, workbench_on):
    """취소된 형제가 '발주확인 전' 안에 있어도 그 집은 빠진다(모집단 안팎 모두)."""
    _login(client)
    _collected(order_no="N-PC-IN", product="취소된 형제", amount=100000,
               place_status="", claim_status="CANCEL_REQUEST",
               address="대구 수성구 9", tel="010-8888-9999")
    _collected(order_no="N-PC-IN", product="남은 형제", amount=50000, place_status="",
               address="대구 수성구 9", tel="010-8888-9999")

    body = client.get(f"{TRIAGE_PATH}?tab=work&f=place").get_data(as_text=True)

    assert _row_count(body) == 0
    assert "0주문" in _chip(body, "place"), _chip(body, "place")
    assert "이 필터에 해당하는 주문이 없습니다" in body


# --------------------------------------------------------------------------- #
# 수집 상태 (2차 리뷰) — 게이트가 켜지면 옛 화면이 리다이렉트로 닫힌다.
# 워터마크·인증 만료일·"지금 수집" 이 도달 불가가 되면 수집이 멈춰도 아무도 모른다.
# --------------------------------------------------------------------------- #

def test_history_tab_carries_the_ingest_status(client, workbench_on):
    """전체 이력 탭이 마지막 수집·인증 만료일·지금 수집을 함께 보여준다."""
    _login(client)
    _collected(order_no="N-ING-ST", product="붙박이장", amount=1000)

    body = client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True)

    assert 'id="wb-ingest-status"' in body
    assert "마지막 성공 구간 끝" in body
    assert "커머스API 인증 만료일" in body
    assert 'id="wb-run-now"' in body, "'지금 수집' 이 어디에도 없으면 수집을 못 돌린다"


def test_ingest_status_is_admin_only(client, workbench_on):
    """수집 상태는 ADMIN 것이다 — STAFF 화면에는 없다(수집 관리 화면과 같은 기준)."""
    _login(client, role="STAFF")
    _collected(order_no="N-ING-STAFF", product="붙박이장", amount=1000)

    body = client.get(TRIAGE_PATH).get_data(as_text=True)

    assert 'id="wb-ingest-status"' not in body
    assert 'id="wb-run-now"' not in body


def test_strip_has_no_link_that_bounces_back_to_itself(client, workbench_on):
    """상단 스트립이 리다이렉트로 되돌아오는 옛 주소를 가리키면 제자리 뛰기가 된다.

    v3 는 그 '수집 상태' 버튼을 아예 없앴다(계약 §1 — 바로 아래 이력 탭과 같은 곳을
    가리키던 중복이었다). 도달 경로가 사라지면 안 되므로 이력 탭이 그 자리를 대신하는지
    함께 확인한다.
    """
    _login(client)
    _collected(order_no="N-ING-LOOP", product="붙박이장", amount=1000)

    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    # 2026-08-24: 탭이 머리줄 안으로 들어왔다(4줄 → 2줄). 탭 링크는 정당한 진입구이므로
    # 검사 범위를 **탭 밖**으로 좁힌다 — 막으려던 것은 이력 탭과 중복되던 '수집 상태' 버튼이다.
    head = body.split('class="wb-bar wb-bar--head"')[1].split("</div>")[0]
    outside_tabs = head.split("</nav>")[-1]

    assert 'href="/admin/naver-ingest"' not in outside_tabs, outside_tabs
    assert "<a " not in outside_tabs, "머리줄에는 탭 말고 진입구를 두지 않는다(이력 탭과 중복)"
    assert 'data-tab="all"' in body, "수집 상태로 가는 길(이력 탭)은 남아 있어야 한다"


# --------------------------------------------------------------------------- #
# 실패 띠 지우기 (2차 리뷰)
# --------------------------------------------------------------------------- #

def test_failure_row_offers_an_acknowledge_button(client, workbench_on):
    """판매자센터에서 손으로 해결한 실패를 사람이 닫을 수 있어야 한다."""
    _login(client)
    failed = _with_failure(_collected(order_no="N-ACK", product="실패 건", amount=1000))

    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    strip = body.split('id="wb-result"')[1].split("</section>")[0]

    assert "wb-ack" in strip, strip[:500]
    assert f'data-link-id="{failed.id}"' in strip, strip[:500]


def test_acknowledge_route_clears_the_failure(client, workbench_on):
    """라우트가 실제로 기록을 지운다 — 지운 뒤에는 띠가 사라진다."""
    _login(client)
    failed = _with_failure(_collected(order_no="N-ACK-GO", product="실패 건", amount=1000))

    response = client.post(f"/admin/naver-ingest/{failed.id}/fulfillment-clear", json={})

    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["success"] is True
    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    assert 'id="wb-result"' not in body, "지웠는데 띠가 남아 있다"


def test_acknowledge_action_has_an_audit_label(client, workbench_on):
    """새 감사 행위는 라벨을 등재해야 한다(미등재면 FOMS CI red)."""
    from foms.services.audit_message_display import ACTION_LABELS

    assert "NAVER_INGEST_FULFILLMENT_CLEAR" in ACTION_LABELS


# --------------------------------------------------------------------------- #
# 3차 리뷰 — 집 단위 클레임 잠금 / 잘림 감지 순서 / 실패 띠 묶음 규칙
# --------------------------------------------------------------------------- #

def test_dispatch_is_locked_when_a_sibling_is_claimed(client, workbench_on):
    """형제가 취소된 집은 대표를 열어도 발송처리를 보낼 수 없다 — 판정은 집 단위다."""
    _login(client)
    _collected(order_no="N-DSP-SIB", product="취소된 형제", amount=100000,
               place_status="OK", claim_status="CANCEL_REQUEST",
               address="광주 서구 7", tel="010-6666-7777")
    clean = _collected(order_no="N-DSP-SIB", product="멀쩡한 형제", amount=50000,
                       place_status="OK", address="광주 서구 7", tel="010-6666-7777")

    body = client.get(f"{TRIAGE_PATH}?link_id={clean.id}").get_data(as_text=True)

    head = open_tag(body, "wb-dispatch")
    assert is_disabled(body, "wb-dispatch"), "취소가 걸린 집에 발송처리 버튼이 열렸다"
    assert 'id="wb-modal-dispatch"' not in body
    assert 'id="wb-dispatch-confirm"' not in body


def test_truncation_is_measured_after_the_claim_filter(client, workbench_on, monkeypatch):
    """클레임으로 빠진 집이 상한을 먹어 '잘림'이 숨겨지면 안 된다."""
    from foms.web.admin import naver_ingest as mod

    # 목록 상한의 SSOT 는 WORK_GROUP_LIMIT 다(2026-08-24: 캡을 원천별이 아니라
    # **병합 뒤 한 곳**으로 옮겼다). PAGE_SIZE 는 이력 페이징용이라 여기선 안 문다.
    monkeypatch.setattr(mod, "WORK_GROUP_LIMIT", 1, raising=False)
    _login(client)
    _collected(order_no="N-TR-A", product="정상 하나", amount=1000, place_status="",
               address="서울 종로구 1", tel="010-4444-0001")
    _collected(order_no="N-TR-CLAIM", product="취소 집", amount=1000, place_status="",
               claim_status="CANCEL_REQUEST", address="서울 종로구 2", tel="010-4444-0002")
    _collected(order_no="N-TR-B", product="정상 둘", amount=1000, place_status="",
               address="서울 종로구 3", tel="010-4444-0003")

    body = client.get(f"{TRIAGE_PATH}?tab=place").get_data(as_text=True)

    assert "먼저 처리" in body, "잘렸는데 안내가 없다"


def test_failure_strip_folds_by_the_same_rule_the_actions_use(client, workbench_on):
    """실패 띠의 한 줄 = 재시도가 처리하는 한 집이어야 한다(백필 전에도).

    띠가 group_key 컬럼으로 접고 재시도는 원본 3-튜플로 처리하면, 분할배송에서 두 집이
    한 줄로 접혀 건수가 낮게 뜨고 한 번에 한 집만 처리된다.
    """
    _login(client)
    first = _with_failure(_collected(order_no="N-FOLD", product="A집 실패", amount=1000,
                                     address="서울 강남구 1", tel="010-1111-0001"))
    second = _with_failure(_collected(order_no="N-FOLD", product="B집 실패", amount=1000,
                                      address="부산 해운대구 2", tel="010-2222-0002"))
    # 백필 전 상태 재현: 묶음키 컬럼이 비어 주문번호로 폴백된다.
    for link in (first, second):
        link.group_key = None
    db_session.commit()

    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    strip = body.split('id="wb-result"')[1].split("</section>")[0]

    assert "실패 2주문" in strip, strip[:400]
    ids = strip.split('id="wb-retry-failed"')[1].split('data-link-ids="')[1].split('"')[0]
    assert len(ids.split(",")) == 2, ids


# --------------------------------------------------------------------------- #
# 4차 리뷰 — 큐 밖 형제의 클레임 / 실패 띠 묶음 경계
# --------------------------------------------------------------------------- #

def test_dispatch_is_locked_when_the_claimed_sibling_left_the_queue(client, workbench_on):
    """확인 완료돼 큐에서 빠진 형제가 취소 중이어도 발송처리는 잠긴다.

    큐 모집단 안에서만 클레임을 보면 그 형제가 안 보인다 — 집 전체를 봐야 한다.
    """
    _login(client)
    claimed = _collected(order_no="N-DSP-GONE", product="취소된 형제", amount=100000,
                         place_status="OK", claim_status="CANCEL_REQUEST",
                         address="울산 남구 3", tel="010-3333-1111")
    _reviewed(claimed)
    clean = _collected(order_no="N-DSP-GONE", product="멀쩡한 형제", amount=50000,
                       place_status="OK", address="울산 남구 3", tel="010-3333-1111")

    body = client.get(f"{TRIAGE_PATH}?link_id={clean.id}").get_data(as_text=True)

    head = open_tag(body, "wb-dispatch")
    assert is_disabled(body, "wb-dispatch"), "큐 밖 형제의 취소를 못 봤다"
    assert 'id="wb-modal-dispatch"' not in body
    assert 'id="wb-dispatch-confirm"' not in body


def test_failure_strip_does_not_merge_different_orders(client, workbench_on):
    """원본이 비어 키를 못 만드는 링크들이 한 줄로 붙으면 안 된다(주문이 다르다)."""
    _login(client)
    first = _with_failure(_collected(order_no="N-BLANK-A", product="빈 원본 A", amount=1000))
    second = _with_failure(_collected(order_no="N-BLANK-B", product="빈 원본 B", amount=1000))
    for link in (first, second):
        link.raw_snapshot = {}
        link.group_key = None
        db_session.commit()

    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    strip = body.split('id="wb-result"')[1].split("</section>")[0]

    assert "실패 2주문" in strip, strip[:400]


# --------------------------------------------------------------------------- #
# 5차 리뷰 — 판정 대상은 '화면에 뜬 집' / 필터 걸린 총계 / 같은 라벨 다른 숫자
# --------------------------------------------------------------------------- #

def test_claim_check_follows_the_household_actually_shown(client, workbench_on):
    """클레임 판정은 pane 에 **실제로 뜬 집**을 봐야 한다.

    탭 기본 선택이 큐 첫 줄과 다를 수 있다(취소 집은 처리 대기 탭에서 빠진다).
    그때 큐 첫 줄로 판정하면 멀쩡한 집의 발송처리가 잠긴다.
    """
    _login(client)
    # 큐는 최신순이라 **취소 집을 나중에** 만들어 큐 첫 줄로 오게 한다 —
    # 처리 대기 탭은 그 줄을 빼므로 pane 에는 멀쩡한 집이 뜬다.
    _collected(order_no="N-SEL-OK", product="멀쩡한 집", amount=50000, place_status="OK",
               address="제주 제주시 2", tel="010-9090-2222")
    _collected(order_no="N-SEL-CLAIM", product="취소 집", amount=100000, place_status="OK",
               claim_status="CANCEL_REQUEST", address="제주 서귀포 1", tel="010-9090-1111")

    body = client.get(f"{TRIAGE_PATH}?tab=work").get_data(as_text=True)

    assert "멀쩡한 집" in body
    assert 'id="wb-dispatch"' in body, "pane 에 뜬 집은 멀쩡한데 발송처리가 잠겼다"


def test_history_total_chip_does_not_claim_a_filtered_number(client, workbench_on):
    """필터가 걸린 상태에서 '전체 N집' 은 거짓말이다 — 옛 화면은 숫자를 뺐다."""
    _login(client)
    link = _collected(order_no="N-TOT", product="실패 수집", amount=1000)
    link.sync_status = "FAILED"
    db_session.commit()
    _collected(order_no="N-TOT-2", product="정상 수집", amount=1000)

    body = client.get(f"{TRIAGE_PATH}?tab=all&status=FAILED").get_data(as_text=True)
    chip = body.split('class="wb-filters"')[1].split("</a>")[0]

    assert "전체" in chip
    assert "1주문" not in chip, chip


def test_place_pending_labels_say_which_population_they_count(client, workbench_on):
    """탭 배지(작업 대상)와 이력 칩(취소 포함)이 같은 라벨로 다른 숫자를 내면 안 된다."""
    _login(client)
    _collected(order_no="N-LBL-CLAIM", product="취소 집", amount=1000, place_status="",
               claim_status="CANCEL_REQUEST", address="강원 춘천 1", tel="010-7070-1111")
    _collected(order_no="N-LBL-OK", product="정상 집", amount=1000, place_status="",
               address="강원 원주 2", tel="010-7070-2222")

    body = client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True)
    chips = body.split('class="wb-filters"')[1].split("</div>")[0]

    assert "취소 포함" in chips, chips


def test_history_prose_the_user_deleted_stays_deleted(client, workbench_on):
    """사용자가 지운 이력 카드 안내문은 다시 돌아오지 않는다 (2026-08-27).

    이 자리에는 원래 "카드 헤더도 필터를 알아야 한다"는 계약이 있었다. 그런데 그 헤더 문구
    자체를 사용자가 지웠다(카운트 span 을 숫자까지 통째로) — 그대로 두면 **지운 글자를
    되살려야 green 이 되는 테스트**가 된다. 그래서 자리는 지우지 않고 부활 금지 가드로
    바꿔 둔다.

    원래 뜻(필터 걸린 총계를 '전체' 라고 부르지 않는다)은 :1417
    ``test_history_total_chip_does_not_claim_a_filtered_number`` 가 그대로 이어받는다 —
    칩이 같은 화면에서 같은 숫자를 더 정확한 라벨로 말하므로 계약이 비지 않는다.

    지운 3줄 중 "큐에 넣기만 합니다" 만 여기서 안 잰다: 그 줄은 ``ingest_status`` 가 있을
    때만 나오는 블록 안이라, 블록이 통째로 빠진 응답에서는 무엇을 지우든 green 이 되어
    단언이 공허해진다. 그 줄은 템플릿 소스에서 잡는다
    (``test_naver_workbench_async_result.py`` 의 안내문 부재 테스트).
    """
    _login(client)
    link = _collected(order_no="N-HDR", product="실패 수집", amount=1000)
    link.sync_status = "FAILED"
    db_session.commit()
    _collected(order_no="N-HDR-2", product="정상 수집", amount=1000)

    # 필터가 걸린 화면 — 지운 문구가 가장 되살아나기 쉬운 상태에서 잰다.
    body = client.get(f"{TRIAGE_PATH}?tab=all&status=FAILED").get_data(as_text=True)

    assert "숫자는 모두 주문 단위" not in body, "지운 카운트 문구가 돌아왔다"
    assert "읽기 전용 — 처리는" not in body, "지운 읽기 전용 고지가 돌아왔다"


# --------------------------------------------------------------------------- #
# 이력 탭 찾기 칸 (2026-08-27) — 문구를 뺀 자리에 도구를 놓는다
# --------------------------------------------------------------------------- #

def test_history_tab_has_a_find_box_over_its_own_rows(client, workbench_on):
    """이력 탭에도 찾기 칸이 있고, **칩 줄 안**에 있어야 한다.

    처리 탭이 이미 "칩 + 찾기 한 줄" 이라 자리를 그대로 맞춘다. 표 위에 새 도구줄을 만들면
    밴드 1줄·경계선 1개가 늘어, 문구를 빼서 조용하게 만든 이번 변경과 정면으로 어긋난다.

    이 칸은 **서버로 나간다**(2026-09-02). 화면 필터였을 때는 닿는 범위가 지금 쪽
    50집뿐이라, 16쪽짜리 이력에서 이름을 쳐도 "0주문"이 나왔다(사용자 실화면 보고).
    그래서 placeholder 도 '이 목록에서' 가 아니라 '이력 전체에서' 라고 말한다 —
    범위를 좁게 약속해 놓고 넓게 찾으면 그 반대만큼이나 오해가 난다.
    """
    _login(client)
    _collected(order_no="N-FINDBOX", product="붙박이장", amount=100000)

    body = client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True)

    assert 'id="wb-find"' in body, "이력 탭에 찾기 칸이 없다"
    assert 'class="wb-find__input"' in body, "처리 탭과 같은 부품을 써야 생김새가 갈리지 않는다"
    assert 'id="wb-find-note"' in body, "좁힌 뒤 몇 주문이 남았는지 말할 자리가 있어야 한다"
    assert "이력 전체에서 · 고객명 · 주문번호 · 전화" in body, "범위를 말하는 placeholder"
    assert 'name="q"' in body, "찾기 낱말은 쿼리스트링 q 로 서버에 나가야 한다"
    assert 'method="get"' in body, "찾기는 읽기다 — GET 이어야 뒤로가기·주소 공유가 산다"

    # 자리 계약: `.wb-filters` 가 닫히기 **전**에 있어야 한다(칩 줄 오른쪽 끝).
    # 이 슬라이스는 `.wb-filters` 안에 `<div>` 가 없다는 전제로 첫 `</div>` 까지 자른다 —
    # 찾기 블록을 div 로 감싸면 이 단언이 먼저 깨진다(의도된 가드).
    chips = body.split('class="wb-filters"')[1].split("</div>")[0]
    assert 'id="wb-find"' in chips, chips


def test_history_rows_carry_the_same_find_text_as_work_rows(client, workbench_on):
    """이력 행도 찾을 문자열을 **행이 직접** 들고 있다.

    처리 탭 행과 같은 식을 쓴다(``group.`` → ``row.``). JS 가 자식 셀을 훑어 조립하는 쪽을
    택하면 표 마크업이 바뀔 때마다 조용히 안 걸린다. 특히 네이버 주문번호는 이력 행 어디에도
    글자로 나오지 않아서, 이 속성이 있어야만 주문번호로 찾을 수 있다.

    빈 안내 행에는 달지 않는다 — 달면 수집 0건 화면에서 아무 낱말이나 쳤을 때
    "0주문 / 1주문" 이 되어, 있지도 않은 한 줄이 분모에 남는다.
    """
    _login(client)
    _collected(order_no="N-FIND-ROW", product="찾기 붙박이장", amount=100000)

    body = client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True)
    tbody = body.split('class="wb-cmp wb-hist"')[1].split("<tbody>")[1].split("</tbody>")[0]
    # 여는 `<tr …>` 태그만 — 셀 안 어딘가가 아니라 **행**이 들고 있어야 한다.
    tr_open = tbody.split("<tr")[1].split(">")[0]

    assert "data-find=" in tr_open, tr_open
    value = tr_open.split('data-find="')[1].split('"')[0]
    assert "이수취" in value, value  # 이력 표의 고객명 = 수취인 이름(summarize_snapshot)
    assert "n-find-row" in value, "주문번호가 대문자면 |lower 가 빠진 것 — JS 는 소문자로 비교한다"
    assert "찾기 붙박이장" in value, value

    # 수집 0건 화면: 빈 안내 행은 있지만 검색 모집단에는 들어오지 않는다.
    empty = client.get(f"{TRIAGE_PATH}?tab=all&status=FAILED").get_data(as_text=True)
    empty_tbody = empty.split('class="wb-cmp wb-hist"')[1].split("<tbody>")[1].split("</tbody>")[0]

    assert "wb-empty" in empty_tbody, empty_tbody
    assert "data-find" not in empty_tbody, "빈 안내 행이 분모에 섞이면 0건 화면이 '1주문' 이 된다"


# --------------------------------------------------------------------------- #
# 이력 탭 찾기 = 서버가 한다 (2026-09-02)
#
# 이 칸은 원래 화면 필터였다. 이력 표는 서버가 50집씩 잘라 보내므로 칸이 닿는 데가
# **지금 쪽**뿐이었고, 800주문·16쪽짜리 운영 화면에서 사람이 고객명을 쳤을 때
# "0주문 / 이 페이지 50주문" 이 나왔다(2026-09-02 사용자 보고). 아래 테스트는 그
# 실패를 모집단으로 재현한다 — 찾는 집이 **1쪽에 없을 때** 찾히는가.
# --------------------------------------------------------------------------- #

def _page_of_noise(count: int) -> None:
    """1쪽을 채울 딴 집들 — 찾는 집을 뒤쪽 쪽으로 밀어낸다."""
    for index in range(count):
        _collected(order_no=f"N-NOISE-{index}", product="딴 제품", amount=1000,
                   tel=f"010-9{index:03d}-0000")


def _history_rows(client, query: str) -> str:
    """이력 표 tbody 만 잘라 돌려준다(칩·헤더 글자가 단언에 섞이지 않게)."""
    body = client.get(f"{TRIAGE_PATH}?tab=all&{query}").get_data(as_text=True)
    return body.split('class="wb-cmp wb-hist"')[1].split("<tbody>")[1].split("</tbody>")[0]


def test_history_find_reaches_rows_that_are_not_on_the_first_page(client, workbench_on):
    """찾는 집이 **1쪽에 없어도** 찾힌다 — 이 결함의 본체다.

    모집단을 PAGE_SIZE 보다 크게 만들고(1쪽 = 50집), 찾을 집을 가장 오래된 쪽으로
    민다. 화면 필터였다면 여기서 0줄이 나온다(그게 사용자가 본 화면이다).
    """
    from foms.web.admin.naver_ingest import PAGE_SIZE

    _login(client)
    # 가장 먼저 만든 집이 가장 오래된 집 — 정렬이 최신순이라 뒤쪽 쪽으로 간다.
    target = _collected(order_no="N-FIND-DEEP", product="깊은 붙박이장",
                        amount=100000, tel="010-7777-8888")
    _page_of_noise(PAGE_SIZE + 5)

    first_page = _history_rows(client, "")
    assert "N-FIND-DEEP".lower() not in first_page.lower(), \
        "찾을 집이 1쪽에 있으면 이 테스트는 아무것도 재현하지 못한다(음성 대조군)"

    found = _history_rows(client, "q=N-FIND-DEEP")

    assert "깊은 붙박이장" in found, "1쪽 밖의 집을 주문번호로 못 찾았다"
    assert "딴 제품" not in found, "찾기가 안 걸리고 전체 목록이 그대로 왔다"
    assert target.id  # 픽스처가 살아 있음을 명시


def test_history_find_matches_customer_name_of_a_linked_order(client, workbench_on):
    """붙은 FOMS 주문의 **고객명**으로도 찾힌다(사용자가 실제로 친 낱말).

    이력 표 고객 칸은 주문이 있으면 ``orders.customer_name`` 을 보여 준다 —
    화면에 보이는 그 글자로 찾아지지 않으면 사람은 "검색이 고장났다" 고 읽는다.
    """
    _login(client)
    order = Order(received_date="2026-08-01", customer_name="김유리",
                  phone="010-5555-6666", address="서울 강남구 2 202호",
                  product="붙박이장", status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    link = _collected(order_no="N-FIND-NAME", product="이름 붙박이장", amount=100000)
    row = db_session.get(ExternalOrderLink, int(link.id))
    row.order_id = int(order.id)
    row.sync_status = "LINKED"
    db_session.commit()
    _page_of_noise(3)

    found = _history_rows(client, "q=김유리")

    # 제품 칸은 붙은 주문 값을 보여 준다(`order.product`) — 그래서 스냅샷 제품명이 아니라
    # 고객명과 주문번호로 잰다.
    assert "김유리" in found, "고객명으로 못 찾았다"
    assert "n-find-name" in found.lower(), "찾힌 줄이 그 집이 아니다"
    assert "딴 제품" not in found, "찾기가 안 걸렸다"


def test_history_find_matches_recipient_name_when_no_order_exists_yet(client, workbench_on):
    """주문이 아직 없는 수집분은 **수취인 이름 컬럼**으로 찾힌다.

    그 집의 이름은 ``raw_snapshot`` 안에만 있고 SQL 이 닿지 못한다 — 그래서 수집
    파이프라인이 복사해 두는 ``recipient_name`` 컬럼을 본다. 이 컬럼이 비면
    (옛 행) 이름으로는 못 찾는다는 사실 자체가 이 테스트가 지키는 계약이다.
    """
    _login(client)
    _collected(order_no="N-FIND-RECIP", product="수취인 붙박이장", amount=100000)
    _page_of_noise(3)

    found = _history_rows(client, "q=이수취")

    assert "수취인 붙박이장" in found, "수취인 이름으로 못 찾았다"


def test_history_find_narrows_total_and_pages_and_chip_counts(client, workbench_on):
    """좁힌 뒤에는 총계·쪽수·칩 숫자가 **같은 모집단**을 말한다.

    목록만 좁히고 총계가 800주문이면, 사람은 화면에 없는 797주문을 찾아 헤맨다
    (캡 뒤 파이썬 분류 함정과 같은 실패 모양 — 숫자가 목록과 다른 말을 한다).
    """
    from foms.web.admin.naver_ingest import PAGE_SIZE

    _login(client)
    _collected(order_no="N-FIND-COUNT", product="계수 붙박이장", amount=100000,
               tel="010-4444-5555")
    _page_of_noise(PAGE_SIZE + 5)

    body = client.get(f"{TRIAGE_PATH}?tab=all&q=N-FIND-COUNT").get_data(as_text=True)

    assert "1주문 — 이력 전체에서 찾음" in body, "좁힌 결과를 말하지 않는다"
    assert "다른 쪽에 있을 수 있습니다" not in body, \
        "전체를 찾는 칸이 '다른 쪽에 있을 수 있다' 고 말하면 거짓말이다"
    assert 'class="wb-pager"' not in body, "1집으로 좁혔는데 쪽수가 남아 있다"


def test_history_find_says_nothing_found_instead_of_an_empty_screen(client, workbench_on):
    """못 찾으면 **못 찾았다고 말한다** — 빈 표만 남기면 "사라졌다" 가 된다."""
    _login(client)
    _collected(order_no="N-FIND-NONE", product="붙박이장", amount=100000)

    body = client.get(f"{TRIAGE_PATH}?tab=all&q=없는이름zzz").get_data(as_text=True)

    assert "찾은 주문 없음" in body, body[:0] or "0건 고지가 없다"


def test_history_find_survives_chips_and_pager(client, workbench_on):
    """칩·페이저 링크가 찾기 낱말을 들고 간다 — 빠지면 누른 순간 조용히 풀린다."""
    _login(client)
    _collected(order_no="N-FIND-KEEP", product="붙박이장", amount=100000)

    body = client.get(f"{TRIAGE_PATH}?tab=all&q=N-FIND-KEEP").get_data(as_text=True)
    chips = body.split('class="wb-filters"')[1].split("</div>")[0]

    assert chips.count("q=N-FIND-KEEP") >= 7, \
        f"칩 8개가 전부 찾기 낱말을 들고 가야 한다: {chips.count('q=N-FIND-KEEP')}"
