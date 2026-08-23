"""워크벤치 v3 통합 리뷰 후속 지적(M-2·M-3·M-4·L-1) 회귀 테스트.

원장 `docs/plans/2026-08-23-naver-workbench-v3-ledger.md` 의 "미처리 지적 후속 처리".
본체 계약은 `test_naver_workbench.py`·`test_naver_workbench_v3_contract.py` 가 문다 —
여기서는 **그 리뷰가 지목한 갈라짐 네 곳**만 좁게 잰다.

픽스처는 본체 파일 것을 그대로 쓴다(모양이 두 벌이 되면 재려던 것과 다른 걸 재게 된다 —
2026-08-23 에 `_link` 헬퍼가 형제를 같은 주문번호로 만들어 실제로 그 일이 났다).
"""

from __future__ import annotations

from datetime import datetime

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink

from tests.services.integrations._markup import has_attribute
from tests.services.integrations.test_naver_workbench import (  # noqa: F401 - fixture 재사용
    TRIAGE_PATH,
    _collected,
    _login,
    _pane,
    _uid,
    workbench_on,
)


def _sibling(base: ExternalOrderLink, *, product: str, amount: int,
             place_status: str = "OK") -> ExternalOrderLink:
    """같은 집(같은 주문번호·수취인 전화·주소)의 형제 상품주문 1건.

    집 판정은 ``group_key`` = (주문번호, 수취인 전화, 주소)다 — 주소·전화를 다르게 주면
    분할배송으로 갈려 **다른 집**이 된다. 그래서 원본을 복사한 뒤 상품주문 축만 바꾼다.
    """
    external_id = f"PO-WB-{_uid()}"
    snapshot = {
        "order": dict(base.raw_snapshot["order"]),
        "productOrder": dict(base.raw_snapshot["productOrder"],
                             productOrderId=external_id,
                             productName=product,
                             totalPaymentAmount=amount,
                             placeOrderStatus=place_status or None),
    }
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             sync_status="COLLECTED",
                             external_order_no=base.external_order_no,
                             raw_snapshot=snapshot, group_key=group_key_text(snapshot),
                             place_order_status=place_status or None)
    db_session.add(link)
    db_session.commit()
    return link


def _modal_of(html: str, modal_id: str) -> str:
    """모달 하나만 잘라 온다 — **다음 모달이 시작하기 전까지**.

    `</div></div></div>` 로 끊으면 안쪽 구조가 조금만 달라도 옆 모달까지 딸려 온다.
    실제로 발송 모달 설명문의 '발송처리 완료'·건수 문장이 주문 만들기 모달 단언에
    섞여 들어왔다.
    """
    tail = html.split(f'id="{modal_id}"')[1]
    return tail.split('<div class="modal fade"')[0]


def _mark_dispatched(link: ExternalOrderLink) -> None:
    """이 상품주문에 발송처리 표식을 찍는다(워커가 건별로 찍는 그 자리)."""
    state = dict(link.triage_state or {})
    state["fulfillment"] = dict(state.get("fulfillment") or {},
                                dispatched_at="2026-08-23T01:00:00")
    link.triage_state = state
    db_session.add(link)
    db_session.commit()


# --------------------------------------------------------------------------- #
# M-4 — 발송 판정 단위 혼재
# --------------------------------------------------------------------------- #

def test_partial_dispatch_closes_cancel_for_every_sibling(client, workbench_on):
    """형제 하나만 발송처리된 집은 **어느 형제로 열어도** 취소가 닫힌다.

    발송 표식은 상품주문마다 찍히고 워커가 건별로 성공/실패한다. pane 이 링크 1건의
    표식만 보면, 안 나간 형제로 열었을 때 취소 버튼이 열려 있다가 서버
    (`cancel_order` 의 발송분 거절)에서 실패한다 — 되돌릴 수 없는 반대 조작 앞에서
    화면과 서버가 다른 말을 하는 자리다(리뷰 M-4).
    """
    _login(client)
    lead = _collected(order_no="N-M4-PART", product="붙박이장 본품", amount=1000000)
    sib = _sibling(lead, product="구성 A", amount=2000)
    _mark_dispatched(sib)

    for opened in (lead, sib):
        pane = _pane(client.get(f"{TRIAGE_PATH}?tab=work&link_id={opened.id}")
                     .get_data(as_text=True))
        assert 'id="wb-cancel"' not in pane, f"link {opened.id}: 부분 발송 집에 취소가 열렸다"
        assert "이미 발송처리" in pane, f"link {opened.id}: 왜 취소가 없는지 화면이 말하지 않는다"


def test_partial_dispatch_keeps_the_dispatch_button_open(client, workbench_on):
    """부분 발송 집은 **발송처리가 아직 남아 있다** — 완료 표시로 덮지 않는다."""
    _login(client)
    lead = _collected(order_no="N-M4-REST", product="붙박이장 본품", amount=1000000)
    sib = _sibling(lead, product="구성 A", amount=2000)
    _mark_dispatched(sib)

    pane = _pane(client.get(f"{TRIAGE_PATH}?tab=work&link_id={lead.id}").get_data(as_text=True))
    assert 'id="wb-dispatch"' in pane, "남은 상품주문이 있는데 발송처리 버튼이 사라졌다"
    # 문구가 아니라 **완료 배지**를 본다 — '발송처리 완료' 라는 글자는 발송 모달 설명에도 나온다.
    done_badge = '<span class="badge bg-success">발송처리 완료</span>'
    assert done_badge not in pane, "일부만 나갔는데 집 전체가 끝난 것으로 표시됐다"


def test_full_dispatch_shows_done_for_every_sibling(client, workbench_on):
    """집 전체가 나가면 어느 형제로 열어도 '발송처리 완료' 다(판정이 집 단위)."""
    _login(client)
    lead = _collected(order_no="N-M4-ALL", product="붙박이장 본품", amount=1000000)
    sib = _sibling(lead, product="구성 A", amount=2000)
    _mark_dispatched(lead)
    _mark_dispatched(sib)

    for opened in (lead, sib):
        pane = _pane(client.get(f"{TRIAGE_PATH}?tab=work&link_id={opened.id}")
                     .get_data(as_text=True))
        done_badge = '<span class="badge bg-success">발송처리 완료</span>'
        assert done_badge in pane, f"link {opened.id}: 집 전체가 나갔는데 완료 표시가 없다"
        assert 'id="wb-cancel"' not in pane, f"link {opened.id}: 발송된 집에 취소가 열렸다"


# --------------------------------------------------------------------------- #
# M-3 — 목록 밖 집을 여는 경로
# --------------------------------------------------------------------------- #

def test_offlist_household_says_it_is_not_in_the_list(client, workbench_on):
    """``?link_id=`` 로 목록 밖 집을 열면 pane 이 그 사실을 말한다.

    이력 탭의 `처리 탭에서 열기` 가 실제로 이 경로다 — **막으면 안 된다**(이력에서 찾은
    집을 처리하러 가는 유일한 길). 대신 왼쪽에 없는 집에 불가역 버튼 4종이 열려 있다는
    사실을 사람이 알아야 한다(리뷰 M-3).
    """
    _login(client)
    listed = _collected(order_no="N-M3-IN", product="목록에 있는 집", amount=100000)
    # 확인이 끝나고 발주확인도 끝난 집은 처리 목록 모집단에서 빠진다(원천 1·2 모두 아님).
    offlist = _collected(order_no="N-M3-OUT", product="목록에 없는 집", amount=100000)
    offlist.reviewed_at = datetime(2026, 8, 23, 0, 0, 0)
    db_session.add(offlist)
    db_session.commit()

    # 문구는 **항상 렌더**되고 `hidden` 으로 접힌다(조각 교체 뒤 JS 가 되살릴 수 있게).
    # 그래서 "글자가 있나" 가 아니라 "접혀 있나" 를 본다.
    body = client.get(f"{TRIAGE_PATH}?tab=work&link_id={offlist.id}").get_data(as_text=True)
    assert "목록에 없는 집" not in body.split('id="wb-pane"')[0], "모집단이 바뀌었다(전제 확인)"
    assert not has_attribute(_pane(body), "wb-offlist", "hidden"), "목록 밖 집인데 경고가 접혀 있다"

    body = client.get(f"{TRIAGE_PATH}?tab=work&link_id={listed.id}").get_data(as_text=True)
    assert has_attribute(_pane(body), "wb-offlist", "hidden"), "목록에 있는 집에 경고가 펼쳐졌다"


def test_pane_fragment_does_not_guess_list_membership(client, workbench_on):
    """pane 프래그먼트는 목록을 모른다 — 모르는 것을 지어내지 않는다.

    프래그먼트는 **목록의 행을 눌러야** 도달하므로 정의상 목록 안이다. 여기서 모집단
    술어를 다시 구현하면 판정이 두 벌이 되어 조용히 갈린다(v3 리뷰 H1 이 그 갈라짐에서
    나왔다).
    """
    _login(client)
    link = _collected(order_no="N-M3-FRAG", product="조각 요청", amount=100000)
    link.reviewed_at = datetime(2026, 8, 23, 0, 0, 0)
    db_session.add(link)
    db_session.commit()

    pane = client.get(f"{TRIAGE_PATH}/pane?link_id={link.id}").get_data(as_text=True)
    assert has_attribute(pane, "wb-offlist", "hidden"),         "프래그먼트가 목록을 모르면서 경고를 펼쳤다"


# --------------------------------------------------------------------------- #
# M-2 — 주문 만들기 재진술
# --------------------------------------------------------------------------- #

def test_create_modal_counts_only_what_promotion_will_move(client, workbench_on):
    """주문 만들기 모달은 **서버가 실제로 옮길** 건수를 말한다.

    ``promote_link_to_order`` 는 ``order_id IS NULL`` + COLLECTED/PENDING_REVIEW 형제만
    옮긴다. 집 전체 수로 재진술하면 "3건을 주문 1건으로" 라고 읽히는데 2건만 옮겨지고,
    남는 형제를 화면이 알리지도 않는다(리뷰 M-2).
    """
    _login(client)
    lead = _collected(order_no="N-M2-MIX", product="붙박이장 본품", amount=1000000)
    _sibling(lead, product="구성 A", amount=2000)
    already = _sibling(lead, product="이미 주문된 구성", amount=3000)
    already.order_id = 999999          # 사람이 부분적으로 먼저 만든 형제
    already.sync_status = "LINKED"
    db_session.add(already)
    db_session.commit()

    pane = _pane(client.get(f"{TRIAGE_PATH}?tab=work&link_id={lead.id}").get_data(as_text=True))
    modal = _modal_of(pane, "wb-modal-create")
    assert "상품주문 2건을" in modal, modal
    assert "상품주문 3건을" not in modal, "집 전체 수로 재진술했다"
    assert "나머지" in modal and "1건" in modal, "남는 형제를 화면이 알리지 않는다"


def test_create_modal_says_nothing_extra_when_nothing_is_left_behind(client, workbench_on):
    """남는 형제가 없으면 군더더기 줄을 붙이지 않는다(문장이 늘면 아무도 안 읽는다)."""
    _login(client)
    lead = _collected(order_no="N-M2-CLEAN", product="붙박이장 본품", amount=1000000)
    _sibling(lead, product="구성 A", amount=2000)

    pane = _pane(client.get(f"{TRIAGE_PATH}?tab=work&link_id={lead.id}").get_data(as_text=True))
    modal = _modal_of(pane, "wb-modal-create")
    assert "상품주문 2건을" in modal, modal
    assert "나머지" not in modal


# --------------------------------------------------------------------------- #
# L-1 — 집 키 폴백 한 벌
# --------------------------------------------------------------------------- #

def test_empty_snapshots_are_counted_one_household_each(client, workbench_on):
    """원본이 비어 키가 통째로 빈 링크는 **각각 한 집**이다.

    워커 쪽 :func:`fulfillment.household_key` 에는 이 폴백이 있었는데 화면 큐에는 없어서,
    빈 원본 두 건이 화면에서만 한 집으로 붙어 보였다(리뷰 L-1). 폴백이 한 벌이면
    화면과 워커가 같은 수를 센다.
    """
    _login(client)
    for _ in range(2):
        link = ExternalOrderLink(channel=CHANNEL, external_id=f"PO-WB-{_uid()}",
                                 sync_status="COLLECTED", external_order_no="",
                                 raw_snapshot={}, group_key="")
        db_session.add(link)
    db_session.commit()

    body = client.get(f"{TRIAGE_PATH}?tab=work").get_data(as_text=True)
    strip = body.split('class="wb-strip__count"')[1].split("</span>")[0]
    assert "2집" in strip, f"빈 원본 2건이 한 집으로 붙었다: {strip}"


# --------------------------------------------------------------------------- #
# CEO 검수 반영 — 모달 재진술 == 서버가 처리할 건수 (계약 §0-2)
# --------------------------------------------------------------------------- #

def test_dispatch_modal_counts_only_what_is_left_to_send(client, workbench_on):
    """발송 모달은 **아직 안 나간 건수**를 말한다.

    서버 `dispatch_order` 의 todo 는 `dispatched_at` 이 찍힌 형제를 뺀다. 집 전체 수로
    재진술하면 부분 발송 집에서 "3건 보냅니다"라고 읽히는데 1건만 나간다.
    """
    _login(client)
    lead = _collected(order_no="N-CEO-DSP", product="붙박이장 본품", amount=1000000)
    sib = _sibling(lead, product="구성 A", amount=2000)
    _sibling(lead, product="구성 B", amount=3000)
    _mark_dispatched(sib)

    pane = _pane(client.get(f"{TRIAGE_PATH}?tab=work&link_id={lead.id}").get_data(as_text=True))
    modal = _modal_of(pane, "wb-modal-dispatch")
    assert "상품주문\n                    2건을" in modal or "2건을 네이버에 발송처리" in modal, modal
    assert "3건을 네이버에 발송처리" not in modal, "집 전체 수로 재진술했다"
    assert "1건</b>은 다시 보내지 않습니다" in modal, "이미 나간 건을 화면이 알리지 않는다"


def test_confirm_modal_counts_only_unconfirmed_siblings(client, workbench_on):
    """발주확인 모달은 **아직 확인 안 된 건수**를 말한다(fulfillment.is_place_pending)."""
    _login(client)
    lead = _collected(order_no="N-CEO-CFM", product="붙박이장 본품", amount=1000000,
                      place_status="")
    _sibling(lead, product="구성 A", amount=2000, place_status="")
    _sibling(lead, product="이미 확인된 구성", amount=3000, place_status="OK")

    pane = _pane(client.get(f"{TRIAGE_PATH}?tab=work&link_id={lead.id}").get_data(as_text=True))
    modal = _modal_of(pane, "wb-modal-confirm")
    assert "2건을" in modal, modal
    assert "3건을" not in modal, "이미 발주확인이 끝난 형제까지 세었다"
    assert "1건</b>은" in modal, "빠지는 건을 화면이 알리지 않는다"


def test_create_button_closes_when_nothing_is_promotable(client, workbench_on):
    """옮길 형제가 없으면 주문 만들기를 열지 않는다.

    열어 두면 모달이 "상품주문 0건을 주문 1건으로 만듭니다" 라고 말하고, 눌러도
    `promote_link_to_order` 가 멱등 반환만 해서 아무 일도 안 난다.
    """
    _login(client)
    lead = _collected(order_no="N-CEO-ZERO", product="붙박이장 본품", amount=1000000)
    lead.order_id = 888001
    lead.sync_status = "LINKED"
    db_session.add(lead)
    db_session.commit()
    sib = _sibling(lead, product="구성 A", amount=2000)
    sib.order_id = 888001
    sib.sync_status = "LINKED"
    db_session.add(sib)
    db_session.commit()

    pane = _pane(client.get(f"{TRIAGE_PATH}?tab=work&link_id={lead.id}").get_data(as_text=True))
    assert has_attribute(pane, "wb-create", "disabled"), "옮길 게 없는데 버튼이 열렸다"
    assert "0건을" not in pane


def test_create_posts_the_promotable_sibling_not_the_lead(client, workbench_on):
    """생성 POST 는 **승격 대상** 형제로 나간다.

    대표(최고금액)가 이미 주문을 가진 집에서 대표 id 로 보내면 서버가 그 주문을 멱등
    반환만 하고 형제는 하나도 안 옮긴다 — 화면은 "1건을 옮깁니다" 라고 말한 뒤 0건이
    움직인다(2026-08-23 CEO 검수).
    """
    _login(client)
    lead = _collected(order_no="N-CEO-LEAD", product="붙박이장 본품", amount=1000000)
    lead.order_id = 888002
    lead.sync_status = "LINKED"
    db_session.add(lead)
    db_session.commit()
    fresh = _sibling(lead, product="나중에 들어온 구성", amount=2000)

    pane = _pane(client.get(f"{TRIAGE_PATH}?tab=work&link_id={fresh.id}").get_data(as_text=True))
    assert not has_attribute(pane, "wb-create", "disabled"), "옮길 형제가 있는데 버튼이 닫혔다"
    modal = _modal_of(pane, "wb-modal-create")
    assert f'data-link-id="{fresh.id}"' in modal, f"대표(id {lead.id}) 로 POST 가 나간다: {modal}"


def test_offlist_is_judged_per_household_not_per_link(client, workbench_on):
    """목록 밖 판정은 **집** 단위다.

    큐 모집단(COLLECTED|LINKED + reviewed_at NULL)에 없는 형제(매핑 실패로
    PENDING_REVIEW)를 열어도, 그 집이 왼쪽에 그려져 있으면 경고를 띄우면 안 된다 —
    왼쪽 행은 심지어 aria-current 로 하이라이트까지 된다(CEO 검수 높음-2).
    """
    _login(client)
    lead = _collected(order_no="N-CEO-HOUSE", product="붙박이장 본품", amount=1000000)
    broken = _sibling(lead, product="매핑 실패 구성", amount=2000)
    broken.sync_status = "PENDING_REVIEW"
    db_session.add(broken)
    db_session.commit()

    body = client.get(f"{TRIAGE_PATH}?tab=work&link_id={broken.id}").get_data(as_text=True)
    assert "붙박이장 본품" in body.split('id="wb-pane"')[0], "전제: 그 집이 목록에 있다"
    assert has_attribute(_pane(body), "wb-offlist", "hidden"), \
        "목록에 있는 집인데 '목록에 없는 집' 경고가 떴다"


def test_bulk_count_excludes_already_confirmed_siblings(client, workbench_on):
    """벌크 재진술 건수도 **서버가 보낼 건수**다.

    행의 `data-count` 를 JS 가 더해 "N집 · 상품주문 M건" 을 만든다. 집 전체 수를 쓰면
    이미 발주확인이 끝난 형제까지 세어 실제보다 크게 말한다(계약 §0-2).
    """
    _login(client)
    lead = _collected(order_no="N-BULK-MIX", product="붙박이장 본품", amount=1000000,
                      place_status="")
    _sibling(lead, product="구성 A", amount=2000, place_status="")
    _sibling(lead, product="이미 확인된 구성", amount=3000, place_status="OK")

    body = client.get(f"{TRIAGE_PATH}?tab=work&f=place").get_data(as_text=True)
    row = body.split('<a class="wb-row')[1].split("</a>")[0]
    assert 'data-count="2"' in row, row
