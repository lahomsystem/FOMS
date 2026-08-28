"""네이버 수집 워크벤치 **v3** 계약 테스트 — 탭 2개 + 필터 칩 + pane 프래그먼트.

계약: `docs/specs/2026-08-23-naver-workbench-v3_CONTRACT.md` §7 의 8종.
원장: `docs/plans/2026-08-23-naver-workbench-v3-ledger.md`.

v3 가 바꾼 것은 화면 배치가 아니라 **모집단과 권한 경계**다. 그래서 여기서 무는 것도
글자가 아니라 그 둘이다:

* 숫자가 한 화면 안에서 갈리지 않는가 (목록 길이 = 스트립 = 탭 배지 = 칩 '전체')
* 칩이 거른 결과가 계약 §2.2 술어와 같은가
* pane 이 재진술하는 건수가 **서버가 실제로 처리할 건수**인가 (절대 규칙 2 — 어긋나면
  사람이 못 본 상품주문에 환불이 나간다, 2026-08-23 리뷰 F5)
* 손댈 수 없는 집에서 불가역 버튼 4종이 전부 닫혀 있는가 (절대 규칙 6)
* 이력 행이 조작면이 되지 않는가 (절대 규칙 3 — mutation 라우트는 STAFF 까지 열려 있다)
* 문서 안에 `id="wb-` 가 중복되지 않는가 (절대 규칙 1 — 중복되면 5번째 행 취소가
  1번째 집으로 나간다)
"""

from __future__ import annotations

import re
from collections import Counter

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import now_utc_naive
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink, Order, User
from tests.services.integrations._markup import has_attribute, is_disabled, open_tag

TRIAGE_PATH = "/admin/naver-ingest/triage"
PANE_PATH = "/admin/naver-ingest/triage/pane"

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
    user = User(username=f"wb3_{role.lower()}_{_uid()}", password=generate_password_hash("pw"),
                role=role, team="CS", name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order(*, name: str = "이수취", address: str = "서울 강남구 1 101호") -> Order:
    """붙일 만한 기존 주문 1건."""
    order = Order(received_date="2026-08-01", customer_name=name, phone="010-3333-4444",
                  address=address, product="붙박이장", status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    return order


def _collected(*, order_no: str, product: str, amount: int = 100000, option: str = "",
               address: str = "서울 강남구 1", tel: str = "010-3333-4444",
               claim_status: str = "", place_status: str = "OK",
               relation: str = "", order_id: int | None = None) -> ExternalOrderLink:
    """수집 링크 1건 — 수집 파이프라인이 만드는 모양(묶음키·발주 상태 컬럼 포함)."""
    external_id = f"PO-V3-{_uid()}"
    snapshot = {
        "order": {"orderId": order_no, "ordererName": "김주문",
                  "ordererTel": "010-1111-2222"},
        "productOrder": {
            "productOrderId": external_id, "productName": product,
            "productOption": option, "totalPaymentAmount": amount,
            "claimStatus": claim_status or None,
            "placeOrderStatus": place_status or None,
            "shippingAddress": {"name": "이수취", "tel1": tel,
                                "baseAddress": address, "detailedAddress": "101호"},
        },
    }
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             sync_status="LINKED" if order_id else "COLLECTED",
                             external_order_no=order_no, raw_snapshot=snapshot,
                             group_key=group_key_text(snapshot),
                             place_order_status=place_status or None,
                             relation=relation or None, order_id=order_id)
    db_session.add(link)
    db_session.commit()
    return link


def _mark_canceled(link: ExternalOrderLink) -> ExternalOrderLink:
    """우리가 취소를 보낸 뒤의 상태(워커 기록)."""
    link.triage_state = {"fulfillment": {"canceled_at": "2026-08-22T01:00:00",
                                         "cancel_reason": "SOLD_OUT"}}
    db_session.commit()
    return link


def _reviewed(link: ExternalOrderLink) -> ExternalOrderLink:
    """확인 완료 — 큐에서 빠진다(하지만 워커는 이 집을 통째로 처리한다)."""
    link.reviewed_at = now_utc_naive()
    db_session.commit()
    return link


# --------------------------------------------------------------------------- #
# 마크업 조각
# --------------------------------------------------------------------------- #

_ROW_RE = re.compile(r'<a class="wb-row.*?</a>', re.S)
_WB_ID_RE = re.compile(r'id="(wb-[^"]+)"')


def _rows_html(body: str) -> list[str]:
    """목록에 뜬 집 줄들(`<a class="wb-row" …</a>`)."""
    return _ROW_RE.findall(body)


def _pane(body: str) -> str:
    """상세 pane(`#wb-pane`) 안쪽 — 목록 글자와 섞이지 않게."""
    return body.split('id="wb-pane"')[1]


def _chip(body: str, name: str) -> str:
    """필터 칩 하나."""
    return body.split(f'data-filter="{name}"')[1].split("</a>")[0]


def _shown(body: str, names: tuple[str, ...]) -> set[str]:
    """목록 줄에 실제로 뜬 제품 이름 집합(pane·이력은 제외)."""
    rows = _rows_html(body)
    return {name for name in names if any(name in row for row in rows)}


def _duplicate_wb_ids(html: str) -> list[str]:
    """문서 안에서 두 번 이상 나온 `id="wb-…"` 목록."""
    return [name for name, count in Counter(_WB_ID_RE.findall(html)).items() if count > 1]


# --------------------------------------------------------------------------- #
# ① 처리 탭 목록 길이 == 스트립 == 탭 배지 == filter_counts["all"]
#
# v2 는 목록이 둘(확인 큐 · 발주확인 전)이라 같은 집이 화면마다 다르게 세어졌다
# (nav 67 · 탭 45). 하나로 합쳤으니 한 화면 안의 네 숫자가 같아야 한다.
# --------------------------------------------------------------------------- #

def test_list_length_matches_strip_tab_badge_and_all_chip(client, workbench_on):
    """네 자리의 숫자가 같다 — 집 단위로, 상품주문 건수와 섞이지 않게."""
    _login(client)
    # 집 3개. 첫 집만 상품주문 2건 → 집 3 · 상품주문 4 가 되어야 단위 혼동이 드러난다.
    _collected(order_no="N-V3-C1-A", product="집 A 본품", amount=500000)
    _collected(order_no="N-V3-C1-A", product="집 A 구성", amount=1000)
    _collected(order_no="N-V3-C1-B", product="집 B", place_status="",
               address="부산 해운대구 2", tel="010-2222-0002")
    _collected(order_no="N-V3-C1-C", product="집 C", claim_status="CANCEL_REQUEST",
               address="대구 수성구 3", tel="010-3333-0003")

    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    strip = body.split("wb-bar__fact")[1].split("</span>")[0]
    work_tab = body.split('data-tab="work"')[1].split("</a>")[0]

    # 2026-08-24 개정: 스트립·탭 배지는 **손댈 수 있는 집**을 말한다. 집 C 는 취소요청이라
    # 어떤 액션도 되지 않으므로 2집이고, 그 차이는 스트립의 '손대지 않음'이 말한다.
    # 칩 '전체'는 목록 길이(3집) 그대로다 — 2 + 1 = 3 이 화면에서 맞아떨어져야 한다.
    locked = body.split("wb-bar__locked")[1].split("</span>")[0]
    assert len(_rows_html(body)) == 3, "목록이 3줄이 아니다(잠긴 집도 목록에는 남는다)"
    # 2026-08-24 머리줄 통합: 집 수는 **탭 배지 한 곳**이 말한다. 스트립은 탭 배지가
    # 말할 수 없는 사실(상품주문 건수·손대지 않음)만 든다 — 같은 수를 두 번 쓰지 않는다.
    assert "4" in strip and "건" in strip, strip
    assert "주문" not in strip.replace("상품주문", ""), f"주문 수를 스트립이 또 말한다: {strip}"
    assert "1주문" in locked, locked
    assert "2주문" in work_tab, work_tab
    assert "3주문" in _chip(body, "all"), _chip(body, "all")


def test_strip_and_tab_keep_the_total_while_a_chip_filters(client, workbench_on):
    """칩을 눌러도 총량(스트립·탭 배지·칩 숫자)은 안 변한다 — 목록만 좁아진다.

    거른 뒤에 세면 지금 고른 칩만 제 숫자를 갖고 나머지가 0이 된다. 사람은 다른 칩에
    몇 집이 남았는지 보려고 칩을 본다.
    """
    _login(client)
    _collected(order_no="N-V3-C1F-A", product="정상 집")
    _collected(order_no="N-V3-C1F-B", product="취소 집", claim_status="CANCEL_REQUEST",
               address="광주 서구 4", tel="010-4444-0004")

    body = client.get(f"{TRIAGE_PATH}?tab=work&f=claim").get_data(as_text=True)

    assert len(_rows_html(body)) == 1, "칩이 목록을 좁히지 않았다"
    # 총량은 칩과 무관하게 그대로다. 스트립·탭은 손댈 수 있는 집(1집), 칩 '전체'는 목록
    # 길이(2집) — 둘의 차이는 '손대지 않음 1집'이 화면에서 메운다(계약 §2.4, 08-24 개정).
    assert "1주문" in body.split("wb-bar__locked")[1].split("</span>")[0]
    assert "1주문" in body.split('data-tab="work"')[1].split("</a>")[0]
    assert "2주문" in _chip(body, "all")
    assert "1주문" in _chip(body, "claim")


# --------------------------------------------------------------------------- #
# ② 칩 4종의 결과가 계약 §2.2 술어와 일치
#
# 술어를 여기서 **다시 적는다**(서버 함수를 불러 비교하면 동어반복이 된다).
#   all   : 전부
#   place : place_pending and not claim_blocking and not canceled
#   rel   : relation in (ADDON, REPAY)
#   claim : claim_blocking or canceled
# --------------------------------------------------------------------------- #

_FILTER_NAMES = ("신규 발주완료", "신규 발주전", "추가결제 발주완료", "추가결제 발주전",
                 "취소요청 집", "우리취소 집")


def _filter_fixture() -> None:
    """칩 술어 4종을 모두 가르는 최소 모집단 6집."""
    order = _order()
    _collected(order_no="N-V3-F1", product="신규 발주완료")
    _collected(order_no="N-V3-F2", product="신규 발주전", place_status="",
               address="부산 해운대구 2", tel="010-2222-0002")
    _collected(order_no="N-V3-F3", product="추가결제 발주완료", relation="ADDON",
               order_id=int(order.id), address="대구 수성구 3", tel="010-3333-0003")
    _collected(order_no="N-V3-F4", product="추가결제 발주전", relation="ADDON",
               order_id=int(order.id), place_status="",
               address="광주 서구 4", tel="010-4444-0004")
    _collected(order_no="N-V3-F5", product="취소요청 집", claim_status="CANCEL_REQUEST",
               address="울산 남구 5", tel="010-5555-0005")
    # 우리가 취소한 집은 **발주확인 전이어도** 발주확인 대상이 아니다 — 그 자리가
    # "전부 선택 → 취소한 집으로 발주확인" 사고의 입구다.
    _mark_canceled(_collected(order_no="N-V3-F6", product="우리취소 집", place_status="",
                              address="제주 제주시 6", tel="010-6666-0006"))


@pytest.mark.parametrize("name,expected", [
    ("all", set(_FILTER_NAMES)),
    ("place", {"신규 발주전", "추가결제 발주전"}),
    ("rel", {"추가결제 발주완료", "추가결제 발주전"}),
    ("claim", {"취소요청 집", "우리취소 집"}),
])
def test_each_chip_matches_its_predicate(client, workbench_on, name, expected):
    """칩이 거른 목록 == 계약 §2.2 술어의 결과. 칩 숫자도 그 길이와 같다."""
    _login(client)
    _filter_fixture()

    body = client.get(f"{TRIAGE_PATH}?tab=work&f={name}").get_data(as_text=True)

    assert _shown(body, _FILTER_NAMES) == expected
    assert len(_rows_html(body)) == len(expected)
    assert f"{len(expected)}주문" in _chip(body, name), _chip(body, name)


# --------------------------------------------------------------------------- #
# ③ STAFF 응답에 이력 데이터·"전체 이력" 문자열 0
#
# 탭을 숨기는 게 아니라 **컨텍스트를 만들지 않는다**. 숨기기만 하면 주소를 아는 사람이
# 그대로 본다(절대 규칙 4).
# --------------------------------------------------------------------------- #

def test_staff_never_receives_history_context_on_any_url(client, workbench_on):
    """STAFF 는 어느 주소로 들어와도 이력·수집 상태를 못 받는다(v3 의 새 주소 포함)."""
    _login(client, role="STAFF")
    link = _collected(order_no="N-V3-PERM", product="권한 붙박이장")
    link.sync_status = "FAILED"
    link.failure_reason = "커머스API 인증 만료"
    db_session.commit()

    for url in (TRIAGE_PATH,
                f"{TRIAGE_PATH}?tab=all",
                f"{TRIAGE_PATH}?tab=all&status=FAILED",
                f"{TRIAGE_PATH}?tab=work&f=claim",
                f"{TRIAGE_PATH}?tab=place"):
        body = client.get(url).get_data(as_text=True)

        assert 'data-active-tab="work"' in body, url
        assert "전체 이력" not in body, url
        assert "커머스API 인증 만료" not in body, url
        assert 'id="wb-ingest-status"' not in body, url
        assert 'id="wb-run-now"' not in body, url
        assert 'data-tab="all"' not in body, "열 수 없는 탭은 아예 보이지 않는다"


# --------------------------------------------------------------------------- #
# ④ pane 프래그먼트 — 조각이다 / 게이트 OFF 404 / link_id 없으면 400 / 없는 링크 404
# --------------------------------------------------------------------------- #

def test_pane_route_returns_only_the_fragment(client, workbench_on):
    """레이아웃 없는 조각이어야 JS 가 `#wb-pane` 을 그대로 갈아 끼운다."""
    _login(client)
    link = _collected(order_no="N-V3-PANE", product="붙박이장")

    response = client.get(f"{PANE_PATH}?link_id={link.id}")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/html")
    assert "<html" not in body.lower(), "전체 페이지가 왔다"
    assert "<!doctype" not in body.lower()
    assert body.strip().startswith('<div id="wb-pane">'), body[:200]
    assert "붙박이장" in body


def test_pane_route_is_absent_when_the_gate_is_off(client):
    """게이트 OFF 사용자의 화면에는 이 경로가 없다 — 404 다(403 이 아니라)."""
    _login(client)
    link = _collected(order_no="N-V3-PANE-OFF", product="붙박이장")

    assert client.get(f"{PANE_PATH}?link_id={link.id}").status_code == 404


def test_pane_route_requires_a_link_id(client, workbench_on):
    """어느 집인지 없이 부르면 400 — 조용히 아무 집이나 열지 않는다."""
    _login(client)

    assert client.get(PANE_PATH).status_code == 400
    assert client.get(f"{PANE_PATH}?link_id=").status_code == 400


def test_pane_route_404s_for_an_unknown_link(client, workbench_on):
    """없는 링크는 404 — 빈 pane 을 200 으로 돌려주면 JS 가 성공으로 읽는다."""
    _login(client)

    assert client.get(f"{PANE_PATH}?link_id=99999999").status_code == 404


# --------------------------------------------------------------------------- #
# ⑤ pane 의 집 == `_group_of_link` 결과  ← **가장 중요**
#
# 모달 재진술 건수와 서버가 처리할 건수가 갈리면, 사람이 못 본 상품주문에 환불·발송이
# 나간다(2026-08-23 리뷰 F5). 큐 모집단은 `COLLECTED|LINKED` + `reviewed_at IS NULL` 로
# 좁혀져 있는데 워커는 **집 전체**를 처리한다 — 그 차이를 재현해 둔다.
# --------------------------------------------------------------------------- #

def _product_order_table(pane: str) -> str:
    """pane 의 상품주문(행 단위) 표만."""
    return pane.split('data-cmp-section="product-orders"')[1].split("</table>")[0]


def test_pane_household_is_the_group_the_server_will_touch(client, workbench_on):
    """pane 의 집 = `_group_of_link` 결과. 큐 기준으로 세면 1건이라 말하고 3건이 나간다."""
    from foms.web.admin import naver_ingest as mod

    _login(client)
    lead = _collected(order_no="N-V3-F5X", product="본품", amount=900000)
    sib1 = _reviewed(_collected(order_no="N-V3-F5X", product="구성 A", amount=2000))
    sib2 = _reviewed(_collected(order_no="N-V3-F5X", product="구성 B", amount=1000))

    household = mod._group_of_link(db_session, lead)
    queue_groups, _ = mod._work_groups(db_session)

    # 전제 확인 — 두 모집단이 실제로 다르다(안 다르면 이 테스트가 아무것도 안 지킨다).
    assert household is not None
    assert household["count"] == 3
    assert set(household["link_ids"]) == {lead.id, sib1.id, sib2.id}
    assert [g["count"] for g in queue_groups] == [1], "큐 기준이면 1건으로 읽힌다"

    full = client.get(f"{TRIAGE_PATH}?link_id={lead.id}").get_data(as_text=True)
    fragment = client.get(f"{PANE_PATH}?link_id={lead.id}").get_data(as_text=True)

    for pane in (_pane(full), fragment):
        # ① 표 제목이 집 전체를 말한다.
        assert f"상품주문 {household['count']}건" in pane, pane[:400]
        # ② 불가역 모달이 **같은 숫자**를 재진술한다.
        assert f"상품주문 {household['count']}건을" in pane, pane[:400]
        # ③ 표에 실제로 그 상품주문들이 다 있다(숫자만 맞고 표는 반쪽인 경우 차단).
        table = _product_order_table(pane)
        for link in (lead, sib1, sib2):
            assert link.external_id in table, link.external_id
        assert table.count('class="wb-cmp__k"') == household["count"]


def test_pane_household_survives_the_queue_fetch_limit(client, workbench_on, monkeypatch):
    """조회 상한 밖 집을 열어도 재진술 건수는 집 전체다 — 상한은 목록의 사정일 뿐이다."""
    from foms.web.admin import naver_ingest as mod

    monkeypatch.setattr(mod, "QUEUE_LINK_FETCH_LIMIT", 1, raising=False)
    _login(client)
    lead = _collected(order_no="N-V3-LIMIT", product="본품", amount=800000)
    _collected(order_no="N-V3-LIMIT", product="구성", amount=1000)

    household = mod._group_of_link(db_session, lead)
    fragment = client.get(f"{PANE_PATH}?link_id={lead.id}").get_data(as_text=True)

    assert household["count"] == 2
    assert "상품주문 2건" in fragment
    assert "상품주문 2건을" in fragment


# --------------------------------------------------------------------------- #
# ⑥ 잠긴 집: 불가역 4종 disabled, `#wb-review-done` 만 열림 (계약 §3.3)
# --------------------------------------------------------------------------- #

_LOCKED_ACTIONS = ("wb-create", "wb-confirm", "wb-dispatch", "wb-cancel")
_LOCKED_MODALS = ("wb-modal-create", "wb-modal-confirm", "wb-modal-dispatch", "wb-modal-cancel")


@pytest.mark.parametrize("kind", ["claim", "canceled"])
def test_locked_household_closes_every_irreversible_action(client, workbench_on, kind):
    """취소·반품 집과 우리가 취소한 집 — 둘 다 4버튼이 닫히고 '확인 완료'만 열린다.

    잠긴 집도 **큐에서는 뺄 수 있어야 한다**(v2 감사 결함 #4). 버튼을 지우지 않고
    잠그는 이유는 이유(title)를 보여주기 위해서다 — 사라진 버튼은 아무 말도 못 한다.
    """
    _login(client)
    link = _collected(order_no=f"N-V3-LOCK-{kind}", product="잠긴 집", place_status="",
                      claim_status="CANCEL_REQUEST" if kind == "claim" else "")
    if kind == "canceled":
        _mark_canceled(link)

    full = client.get(f"{TRIAGE_PATH}?link_id={link.id}").get_data(as_text=True)
    fragment = client.get(f"{PANE_PATH}?link_id={link.id}").get_data(as_text=True)

    for pane in (_pane(full), fragment):
        for action in _LOCKED_ACTIONS:
            assert f'id="{action}"' in pane, action
            head = open_tag(pane, action)
            assert is_disabled(pane, action), f"{action}: {head}"
            assert has_attribute(pane, action, "title"), f"{action} 에 잠긴 이유가 없다: {head}"
        for modal in _LOCKED_MODALS:
            assert f'id="{modal}"' not in pane, f"{modal} 이 열려 있다"
        done = open_tag(pane, "wb-review-done")
        assert not is_disabled(pane, "wb-review-done"), done
        assert "발주확인·발송처리·주문 만들기가 모두 닫혀 있습니다" in pane


def test_locked_row_cannot_be_bulk_selected(client, workbench_on):
    """잠긴 집은 목록에서도 못 고른다 — 벌크 대상은 화면 체크박스에서만 나온다(규칙 5)."""
    _login(client)
    _collected(order_no="N-V3-LOCKROW", product="잠긴 집", place_status="",
               claim_status="CANCEL_REQUEST")
    _collected(order_no="N-V3-OPENROW", product="열린 집", place_status="",
               address="부산 해운대구 9", tel="010-9999-0009")

    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    locked = next(row for row in _rows_html(body) if "잠긴 집" in row)
    open_row = next(row for row in _rows_html(body) if "열린 집" in row)

    assert "disabled" in locked, locked
    assert "wb-row--locked" in locked
    assert "disabled" not in open_row, open_row


# --------------------------------------------------------------------------- #
# ⑦ 문서 전체에서 `id="wb-` 중복 0 (절대 규칙 1)
# --------------------------------------------------------------------------- #

def test_no_duplicate_wb_ids_anywhere_in_the_document(client, workbench_on):
    """셸 + pane 파셜을 합친 결과에 같은 id 가 두 번 있으면 안 된다.

    실화 급 위험: 상세 액션 id 가 문서에 하나뿐이라는 전제가 JS 전반에 있다. 중복되면
    5번째 행에서 누른 취소가 1번째 집으로 나간다.
    """
    _login(client)
    order = _order()
    lead = _collected(order_no="N-V3-DUP", product="본품", amount=700000, place_status="")
    _collected(order_no="N-V3-DUP", product="구성", amount=1000, place_status="")
    # 후보(붙이기 버튼 2개/행) · 실패 띠 · 다른 줄까지 함께 렌더되는 가장 시끄러운 화면.
    sibling = _collected(order_no="N-V3-DUP-2", product="다른 집",
                         address="부산 해운대구 8", tel="010-8888-0008")
    sibling.triage_state = {"fulfillment": {"last_error": "이미 발주확인된 주문입니다",
                                            "last_error_action": "confirm",
                                            "last_error_at": "2026-08-22T01:00:00"}}
    db_session.commit()
    assert order.id  # 후보가 잡히도록 주문이 실제로 있어야 한다

    work = client.get(f"{TRIAGE_PATH}?link_id={lead.id}").get_data(as_text=True)
    history = client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True)
    fragment = client.get(f"{PANE_PATH}?link_id={lead.id}").get_data(as_text=True)

    assert "wb-attach" in work, "후보가 없으면 가장 시끄러운 화면이 아니다"
    for name, html in (("work", work), ("all", history), ("fragment", fragment)):
        assert _duplicate_wb_ids(html) == [], f"{name}: {_duplicate_wb_ids(html)}"


def test_fragment_ids_never_collide_with_the_shell_that_stays(client, workbench_on):
    """프래그먼트를 갈아 끼워도 문서에 새 중복이 생기지 않는다.

    pane 은 통째로 교체된다. 조각이 셸 쪽 id(벌크 바·모달·목록)를 들고 오면 교체 직후
    문서에 중복이 생긴다 — 모달이 두 벌이 되는 자리다. 그래서 **교체돼도 남아 있는
    셸의 id 집합**(pane 이 빈 화면)과 조각의 id 집합은 `#wb-pane` 말고 겹치면 안 된다.
    """
    _login(client)
    lead = _collected(order_no="N-V3-DUP-SWAP", product="본품", amount=500000, place_status="")

    # 관계 칩에는 이 집이 없다 → pane 이 빈 껍데기 = 교체 후에도 남는 셸 쪽 id 전부.
    shell_only = client.get(f"{TRIAGE_PATH}?tab=work&f=rel").get_data(as_text=True)
    fragment = client.get(f"{PANE_PATH}?link_id={lead.id}").get_data(as_text=True)
    shell_ids = set(_WB_ID_RE.findall(shell_only))
    fragment_ids = set(_WB_ID_RE.findall(fragment))

    assert _duplicate_wb_ids(fragment) == [], _duplicate_wb_ids(fragment)
    assert "wb-pane" in shell_ids and "wb-pane" in fragment_ids, "교체 대상이 사라졌다"
    assert fragment_ids & shell_ids == {"wb-pane"}, fragment_ids & shell_ids
    assert "wb-modal-bulk" in shell_ids, "벌크 모달은 셸 쪽에 남아 있어야 한다"


# --------------------------------------------------------------------------- #
# ⑧ 이력 탭 행에 `data-link-id`·액션 버튼 0 (절대 규칙 3)
#
# 불가역 mutation 라우트는 전부 STAFF 까지 열려 있다. 이력 행을 누를 수 있게 만들면
# 과거 주문 **전체**에 취소·발송 버튼을 주는 셈이다.
# --------------------------------------------------------------------------- #

def _history_tbody(body: str) -> str:
    return body.split('class="wb-cmp wb-hist"')[1].split("<tbody>")[1].split("</tbody>")[0]


def test_history_rows_are_read_only(client, workbench_on):
    """이력 표 본문에 버튼·`data-link-id`·`class="btn` 이 하나도 없어야 한다."""
    _login(client)
    order = _order()
    _collected(order_no="N-V3-H1", product="주문 전 집")
    _collected(order_no="N-V3-H2", product="취소 집", claim_status="CANCEL_REQUEST",
               address="대구 수성구 7", tel="010-7777-0007")
    # 주문이 붙은 집은 이력 표에서 FOMS 값(주문의 제품명)을 보여준다 — 그 줄도 함께 문다.
    _collected(order_no="N-V3-H3", product="붙은 집", order_id=int(order.id),
               address="광주 서구 6", tel="010-6666-0006")

    body = client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True)
    tbody = _history_tbody(body)

    assert "주문 전 집" in tbody and "취소 집" in tbody
    assert tbody.count("<tr") == 3, "세 줄이 다 있어야 세 갈래를 다 문 것이다"
    assert "data-link-id" not in tbody, tbody
    assert "<button" not in tbody, tbody
    assert 'class="btn' not in tbody, tbody
    # 기능은 안 죽는다 — 평범한 링크는 남는다(주문 열기 · 처리 탭의 그 집 열기).
    assert "워크벤치" in tbody
    assert "open=erp-order" in tbody


# --------------------------------------------------------------------------- #
# 옛 주소 호환 — `?tab=place` · `?tab=claim` 은 처리 탭 + 그 필터로 살아난다
#
# 없어진 탭 주소를 열어 둔 사람·북마크가 빈 화면으로 떨어지면 안 된다(계약 §2.1).
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("legacy,expected", [
    ("place", {"신규 발주전", "추가결제 발주전"}),
    ("claim", {"취소요청 집", "우리취소 집"}),
])
def test_legacy_tab_urls_land_on_the_matching_filter(client, workbench_on, legacy, expected):
    """옛 탭 주소 = 처리 탭 + 같은 뜻의 필터. 목록도 그 술어대로다."""
    _login(client)
    _filter_fixture()

    response = client.get(f"{TRIAGE_PATH}?tab={legacy}")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-active-tab="work"' in body
    assert f'data-active-filter="{legacy}"' in body
    assert 'aria-pressed="true"' in _chip(body, legacy)
    assert _shown(body, _FILTER_NAMES) == expected
    assert len(_rows_html(body)) == len(expected)


def test_legacy_tab_url_beats_a_stale_f_parameter(client, workbench_on):
    """옛 주소에 `f=` 가 섞여 있어도 탭이 뜻하던 갈래가 이긴다 — 빈 목록으로 떨어지지 않게."""
    _login(client)
    _filter_fixture()

    body = client.get(f"{TRIAGE_PATH}?tab=claim&f=all").get_data(as_text=True)

    assert 'data-active-filter="claim"' in body
    assert _shown(body, _FILTER_NAMES) == {"취소요청 집", "우리취소 집"}


def test_unknown_filter_falls_back_to_all(client, workbench_on):
    """모르는 `f=` 값은 조용히 전체로 — 주소를 손으로 고쳐도 목록이 비지 않는다."""
    _login(client)
    _filter_fixture()

    body = client.get(f"{TRIAGE_PATH}?tab=work&f=nonsense").get_data(as_text=True)

    assert 'data-active-filter="all"' in body
    assert _shown(body, _FILTER_NAMES) == set(_FILTER_NAMES)


def test_pane_fragment_never_leaks_history_to_staff(client, workbench_on):
    """§0.4 그물이 **새 라우트**도 덮는다 (리뷰 M-6).

    프래그먼트는 나중에 생긴 경로라, 이력 누출 계약이 본 라우트만 돌면 여기서 새는
    회귀를 아무도 못 잡는다. pane 은 셸 컨텍스트를 쓰지 않는다는 규약의 회귀 그물이다.
    """
    _login(client, role="STAFF")
    link = _collected(order_no="N-V3-PANE-PERM", product="권한 pane 붙박이장")
    link.sync_status = "FAILED"
    link.failure_reason = "커머스API 인증 만료"
    db_session.commit()

    body = client.get(f"{PANE_PATH}?link_id={link.id}").get_data(as_text=True)

    assert "커머스API 인증 만료" not in body
    assert "전체 이력" not in body
    assert 'id="wb-ingest-status"' not in body
    assert 'id="wb-run-now"' not in body
    # 셸 조각이 프래그먼트에 섞여 나오면 pane 교체가 화면을 이중으로 만든다.
    assert 'id="wb-queue"' not in body
    assert 'class="wb-chips"' not in body
