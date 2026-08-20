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
from models import ExternalOrderLink, User

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
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             sync_status="COLLECTED", external_order_no=order_no,
                             raw_snapshot=snapshot, group_key=group_key_text(snapshot),
                             # 수집 파이프라인은 발주 상태도 컬럼에 복사한다(목록 필터가
                             # JSONB 를 스캔하지 않게 하려고). 픽스처도 같은 모양이어야
                             # '발주확인 전' 탭 모집단 테스트가 실제와 같은 것을 잰다.
                             place_order_status=place_status or None)
    db_session.add(link)
    db_session.commit()
    return link


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

def test_four_tabs_exist_and_work_is_default(client, workbench_on):
    """탭 4개가 한 화면에 있고 기본은 '처리 대기' 다 — 두 URL 왕복을 없앤 자리."""
    _login(client)
    _collected(order_no="N-WB-TAB", product="붙박이장", amount=100000)

    body = client.get(TRIAGE_PATH).get_data(as_text=True)

    for label in ("처리 대기", "발주확인 전", "취소·반품", "전체 이력"):
        assert label in body, label
    assert 'data-tab="work"' in body
    assert 'aria-selected="true"' in body.split('data-tab="work"')[1].split(">")[0] or \
           'aria-selected="true"' in body.split('data-tab="work"')[0].rsplit("<button", 1)[-1]


@pytest.mark.parametrize("tab", ["work", "place", "claim", "all"])
def test_each_tab_responds(client, workbench_on, tab):
    """네 탭 모두 서버 라운드트립으로 열린다(새로고침·북마크가 그냥 된다)."""
    _login(client)
    _collected(order_no=f"N-WB-{tab}", product="붙박이장", amount=100000)

    response = client.get(f"{TRIAGE_PATH}?tab={tab}")

    assert response.status_code == 200
    assert f'data-active-tab="{tab}"' in response.get_data(as_text=True)


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

    assert "1집" in body
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
    """취소·반품 집은 '손대지 않음' 이라고 글자로 말한다."""
    _login(client)
    _collected(order_no="N-WB-CLAIM", product="취소된 붙박이장", amount=100000,
               claim_status="CANCEL_DONE")

    body = client.get(f"{TRIAGE_PATH}?tab=work").get_data(as_text=True)
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

    body = client.get(TRIAGE_PATH).get_data(as_text=True)
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


def test_place_tab_counts_households_in_the_tab_badge(client, workbench_on):
    """탭 배지도 집 단위 — 한 집의 상품주문 3건이 3집으로 읽히면 안 된다."""
    _login(client)
    for idx in range(3):
        _collected(order_no="N-PL-ONE", product=f"구성 {idx}", amount=1000, place_status="")

    body = client.get(f"{TRIAGE_PATH}?tab=place").get_data(as_text=True)
    tab = body.split('data-tab="place"')[1].split("</a>")[0]
    assert "1집" in tab, tab


def test_place_tab_has_a_checkbox_per_household(client, workbench_on):
    """선택은 집 단위다 — 상품주문마다 체크박스가 뜨면 같은 집을 여러 번 고르게 된다."""
    _login(client)
    _collected(order_no="N-PL-A", product="본품", amount=100000, place_status="")
    _collected(order_no="N-PL-A", product="구성", amount=1000, place_status="")
    _collected(order_no="N-PL-B", product="다른 집", amount=50000, place_status="")

    body = client.get(f"{TRIAGE_PATH}?tab=place").get_data(as_text=True)
    assert body.count('class="wb-pick"') == 2


def test_place_button_is_disabled_until_something_is_selected(client, workbench_on):
    """선택이 없으면 버튼이 죽어 있다.

    2026-08-14 일괄 완료처리 AS 증발 사고가 "선택 없이 버튼=전체 대상" 패턴에서 났다.
    되돌릴 수 없는 네이버 호출에 그 패턴을 다시 쓰지 않는다.
    """
    _login(client)
    _collected(order_no="N-PL-GATE", product="붙박이장", amount=100000, place_status="")

    body = client.get(f"{TRIAGE_PATH}?tab=place").get_data(as_text=True)
    button = body.split('id="wb-place-submit"')[1].split(">")[0]
    assert "disabled" in button, button


def test_place_modal_has_the_four_part_warning(client, workbench_on):
    """건수 재진술 + 되돌릴 수 없음 + 사후 경로 — 불가역 액션 4종 세트."""
    _login(client)
    _collected(order_no="N-PL-MODAL", product="붙박이장", amount=100000, place_status="")

    body = client.get(f"{TRIAGE_PATH}?tab=place").get_data(as_text=True)
    modal = body.split('id="wb-modal-place"')[1].split("</div></div></div>")[0]

    assert "되돌릴 수" in modal
    assert "발송처리" in modal, "보낸 뒤 무엇이 열리는지 알려야 한다"
    assert 'id="wb-place-count"' in modal, "건수는 선택에 따라 문장에서 갱신된다"


def test_place_tab_shows_shipping_due_so_urgency_is_visible(client, workbench_on):
    """발송기한이 보여야 '왜 지금인지'를 안다 — 기한을 넘기면 네이버가 자동 취소한다."""
    _login(client)
    link = _collected(order_no="N-PL-DUE", product="붙박이장", amount=100000, place_status="")
    snapshot = dict(link.raw_snapshot)
    snapshot["productOrder"] = dict(snapshot["productOrder"], shippingDueDate="2026-09-08")
    link.raw_snapshot = snapshot
    db_session.commit()

    body = client.get(f"{TRIAGE_PATH}?tab=place").get_data(as_text=True)
    assert "2026-09-08" in body


def test_place_tab_excludes_claimed_households(client, workbench_on):
    """취소·반품 집은 발주확인 대상이 아니다 — 목록에 두면 잘못 눌린다."""
    _login(client)
    _collected(order_no="N-PL-CLAIM", product="취소된 붙박이장", amount=100000,
               place_status="", claim_status="CANCEL_DONE")

    body = client.get(f"{TRIAGE_PATH}?tab=place").get_data(as_text=True)
    assert "취소된 붙박이장" not in body


def test_place_tab_badge_matches_the_list_length(client, workbench_on):
    """배지 숫자와 목록 줄 수가 같아야 한다 — 다르면 사람이 나머지를 찾아 헤맨다.

    실화: 배지는 SQL 로 세느라 취소·반품 집까지 포함했고, 목록은 그것들을 뺐다.
    "4집"이라고 써 놓고 3줄만 보였다. 취소 여부는 raw_snapshot 안에 있어 SQL 이 못
    거르므로, 세는 쪽과 뽑는 쪽이 **같은 함수**를 써야 한다.
    """
    _login(client)
    _collected(order_no="N-PB-1", product="집 하나", amount=100000, place_status="")
    _collected(order_no="N-PB-2", product="집 둘", amount=100000, place_status="")
    _collected(order_no="N-PB-CLAIM", product="취소된 집", amount=100000,
               place_status="", claim_status="CANCEL_DONE")

    body = client.get(f"{TRIAGE_PATH}?tab=place").get_data(as_text=True)

    tab = body.split('data-tab="place"')[1].split("</a>")[0]
    assert "2집" in tab, tab
    assert body.count('class="wb-pick"') == 2
