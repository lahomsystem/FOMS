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


def test_work_tab_excludes_claimed_households(client, workbench_on):
    """처리 대기에서는 취소·반품 집을 뺀다 — 손댈 수 없는 줄이 작업 목록을 채우면 안 된다."""
    _login(client)
    _collected(order_no="N-CL-W1", product="정상 붙박이장", amount=100000)
    _collected(order_no="N-CL-W2", product="취소된 붙박이장", amount=100000,
               claim_status="CANCEL_DONE")

    body = client.get(f"{TRIAGE_PATH}?tab=work").get_data(as_text=True)

    assert "정상 붙박이장" in body
    assert "취소된 붙박이장" not in body


def test_tab_badges_match_their_own_lists(client, workbench_on):
    """탭 배지는 그 탭이 실제로 보여줄 줄 수와 같아야 한다(W2 에서 낸 결함의 재발 방지)."""
    _login(client)
    _collected(order_no="N-CL-B1", product="정상 하나", amount=100000)
    _collected(order_no="N-CL-B2", product="정상 둘", amount=100000)
    _collected(order_no="N-CL-B3", product="취소된 하나", amount=100000,
               claim_status="CANCEL_DONE")

    body = client.get(f"{TRIAGE_PATH}?tab=work").get_data(as_text=True)
    work_tab = body.split('data-tab="work"')[1].split("</a>")[0]
    claim_tab = body.split('data-tab="claim"')[1].split("</a>")[0]

    assert "2집" in work_tab, work_tab
    assert "1집" in claim_tab, claim_tab
    assert body.count('class="wb-row wb-row--') == 2, "처리 대기 목록은 2줄"


def test_claim_detail_locks_create_and_place_but_allows_done(client, workbench_on):
    """주문 만들기·발주확인은 잠기고 '확인 완료'만 열린다(선행 결함 #4 의 화면 쪽)."""
    _login(client)
    link = _collected(order_no="N-CL-ACT", product="취소된 붙박이장", amount=100000,
                      claim_status="CANCEL_DONE")

    body = client.get(f"{TRIAGE_PATH}?tab=claim&link_id={link.id}").get_data(as_text=True)

    assert 'id="wb-claim-create"' in body
    assert "disabled" in body.split('id="wb-claim-create"')[1].split(">")[0]
    assert 'id="wb-claim-place"' in body
    assert "disabled" in body.split('id="wb-claim-place"')[1].split(">")[0]
    done = body.split('id="wb-claim-done"')[1].split(">")[0]
    assert "disabled" not in done, done


def test_claim_detail_shows_why_it_is_locked(client, workbench_on):
    """왜 잠겼는지 화면이 말해 준다 — 이유 없이 잠긴 버튼은 사람이 계속 누른다."""
    _login(client)
    link = _collected(order_no="N-CL-WHY", product="취소된 붙박이장", amount=100000,
                      claim_status="CANCEL_DONE")

    body = client.get(f"{TRIAGE_PATH}?tab=claim&link_id={link.id}").get_data(as_text=True)
    assert "취소 완료" in body
    assert "주문을 만들 수 없습니다" in body


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


def test_default_selection_stays_inside_the_active_tab(client, workbench_on):
    """기본 선택은 그 탭 안에서 고른다.

    실화: 큐 전체에서 첫 집을 골랐더니, 처리 대기 탭을 열었는데 오른쪽 상세에
    취소·반품 집이 펼쳐졌다 — 목록에는 없는데 상세만 뜨는 상태였다.
    """
    _login(client)
    # 취소 집이 더 최신이라 큐 전체에서는 이쪽이 먼저 잡힌다.
    _collected(order_no="N-SEL-OK", product="정상 붙박이장", amount=100000)
    _collected(order_no="N-SEL-BAD", product="취소된 붙박이장", amount=100000,
               claim_status="CANCEL_DONE")

    work = client.get(f"{TRIAGE_PATH}?tab=work").get_data(as_text=True)
    assert "취소된 붙박이장" not in work
    assert "정상 붙박이장" in work

    claim = client.get(f"{TRIAGE_PATH}?tab=claim").get_data(as_text=True)
    assert "취소된 붙박이장" in claim
    assert "정상 붙박이장" not in claim


def test_explicit_link_id_is_honoured_even_across_tabs(client, workbench_on):
    """사용자가 링크를 직접 지정했으면 그 뜻을 존중한다 — 조용히 다른 집으로 튀지 않는다."""
    _login(client)
    _collected(order_no="N-SEL-A", product="첫째 집", amount=100000)
    wanted = _collected(order_no="N-SEL-B", product="둘째 집", amount=200000)

    body = client.get(f"{TRIAGE_PATH}?tab=work&link_id={wanted.id}").get_data(as_text=True)
    header = body.split('class="card-header py-2 d-flex')[1].split("</div>")[0]
    assert "둘째 집" in body
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


def test_history_tab_locks_actions_on_claimed_rows(client, workbench_on):
    """회색으로 남기되 액션은 잠근다 — 서버가 400 으로 막는 일을 화면이 열어 두면 헛클릭이다."""
    _login(client)
    _collected(order_no="N-H-LOCK", product="취소된 붙박이장", amount=100000,
               claim_status="CANCEL_DONE")

    body = client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True)
    row = body.split("취소된 붙박이장")[0].rsplit("<tr", 1)[1] + \
        body.split("취소된 붙박이장")[1].split("</tr>")[0]
    assert "disabled" in row, row


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


def test_history_locked_row_says_why_and_looks_locked(client, workbench_on):
    """잠긴 버튼은 잠긴 티가 나야 하고 이유가 옆에 있어야 한다.

    파란 primary 버튼을 그대로 두고 pointer-events 로만 막으면 사람은 계속 누른다.
    기존 이력 화면이 이미 빨간 사유 줄을 붙이고 있었다 — 워크벤치도 같아야 한다.
    """
    _login(client)
    _collected(order_no="N-H-REASON", product="취소된 붙박이장", amount=100000,
               claim_status="CANCEL_DONE")

    body = client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True)
    row = body.split("취소된 붙박이장")[1].split("</tr>")[0]

    assert "btn-outline-secondary" in row, row
    assert "btn-primary" not in row, row
    assert "취소·반품 진행 중" in row, row


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
    assert "실패 2집" in strip, strip[:400]


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
    head = body.split('id="wb-dispatch"')[1].split(">")[0]

    assert "disabled" not in head, head
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
    head = body.split('id="wb-dispatch"')[1].split(">")[0]

    assert "disabled" in head, head
    assert "발주확인" in head, "잠긴 이유를 버튼에 달아 둔다"


def test_dispatch_shows_done_badge_instead_of_button(client, workbench_on):
    """이미 발송처리된 집은 버튼이 아니라 완료 표시다(두 번 부르지 않는다)."""
    _login(client)
    link = _dispatched(_collected(order_no="N-DSP-DONE", product="붙박이장",
                                  amount=100000, place_status="OK"))

    body = client.get(f"{TRIAGE_PATH}?link_id={link.id}").get_data(as_text=True)

    assert "발송처리 완료" in body
    assert 'id="wb-dispatch"' not in body


def test_dispatch_is_absent_for_claimed_household(client, workbench_on):
    """취소·반품 집에는 발송처리가 없다 — 손대지 않는 집이다."""
    _login(client)
    link = _collected(order_no="N-DSP-CLAIM", product="붙박이장", amount=100000,
                      place_status="OK", claim_status="CANCEL_REQUEST")

    body = client.get(f"{TRIAGE_PATH}?tab=claim&link_id={link.id}").get_data(as_text=True)

    assert 'id="wb-dispatch"' not in body


# --------------------------------------------------------------------------- #
# 발주확인 전 탭의 클레임 판정 (리뷰 지적 P4)
#
# 모집단을 '발주확인 전' 링크로 먼저 좁힌 뒤 클레임을 판정하면, 이미 발주확인이 끝난
# 형제의 취소를 못 본다 — 취소가 걸린 집에 발주확인이 나간다.
# --------------------------------------------------------------------------- #

def test_place_tab_drops_household_whose_sibling_is_claimed(client, workbench_on):
    """형제 상품주문이 취소 중이면 그 집은 발주확인 목록에 없다."""
    _login(client)
    _collected(order_no="N-PC-MIX", product="취소된 형제", amount=100000,
               place_status="OK", claim_status="CANCEL_REQUEST")
    _collected(order_no="N-PC-MIX", product="남은 형제", amount=50000, place_status="")

    body = client.get(f"{TRIAGE_PATH}?tab=place").get_data(as_text=True)

    assert "남은 형제" not in body, "취소가 걸린 집이 발주확인 목록에 남아 있다"
    assert "발주확인이 필요한 집이 없습니다" in body


def test_place_tab_badge_matches_the_list_after_the_claim_check(client, workbench_on):
    """배지 숫자도 같이 줄어든다 — '2집' 이라 써 놓고 1줄이면 사람이 나머지를 찾아 헤맨다."""
    _login(client)
    _collected(order_no="N-PC-MIX2", product="취소된 형제", amount=100000,
               place_status="OK", claim_status="CANCEL_REQUEST")
    _collected(order_no="N-PC-MIX2", product="남은 형제", amount=50000, place_status="")
    _collected(order_no="N-PC-OK", product="정상 집", amount=70000, place_status="")

    body = client.get(f"{TRIAGE_PATH}?tab=place").get_data(as_text=True)
    tab = body.split('data-tab="place"')[1].split("</a>")[0]

    assert "1집" in tab, tab
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

    monkeypatch.setattr(mod, "PAGE_SIZE", 1, raising=False)
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


def test_place_tab_drops_household_when_the_claim_is_inside_the_population(client, workbench_on):
    """취소된 형제가 '발주확인 전' 안에 있어도 그 집은 빠진다(모집단 안팎 모두)."""
    _login(client)
    _collected(order_no="N-PC-IN", product="취소된 형제", amount=100000,
               place_status="", claim_status="CANCEL_REQUEST",
               address="대구 수성구 9", tel="010-8888-9999")
    _collected(order_no="N-PC-IN", product="남은 형제", amount=50000, place_status="",
               address="대구 수성구 9", tel="010-8888-9999")

    body = client.get(f"{TRIAGE_PATH}?tab=place").get_data(as_text=True)

    assert "남은 형제" not in body
    assert "발주확인이 필요한 집이 없습니다" in body


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


def test_status_button_points_into_the_workbench_not_the_redirect(client, workbench_on):
    """상단 버튼이 리다이렉트로 되돌아오는 옛 주소를 가리키면 제자리 뛰기가 된다."""
    _login(client)
    _collected(order_no="N-ING-LOOP", product="붙박이장", amount=1000)

    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    strip = body.split('class="wb-strip"')[1].split("</div>")[0]

    assert "/admin/naver-ingest/triage" in strip, strip
    assert 'href="/admin/naver-ingest"' not in strip, strip


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
