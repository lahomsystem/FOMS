"""N2: 도크가 **이전 주문 / 이번 주문**을 갈라 말하는지 (2026-08-26).

결함(사용자 실화면): 재결제로 집이 둘 붙은 주문에서 ``본품 1`` 과 ``본품 2`` 가 같은
톤으로 나란히 섰다. 둘은 서로 다른 네이버 주문번호에서 온 **다른 날 접수분**인데 화면은
그걸 말하지 않았고, 귀속 드롭다운의 본품 두 개는 **이름이 완전히 같아** 고르는 사람이
어느 쪽인지 분간할 근거가 없었다.

여기서 못박는 것:

* 행이 **어느 집(네이버 주문번호)** 에서 왔는지가 payload 에 **행 단위 사실**로 실린다.
* 관계(``ExternalOrderLink.relation`` — ``NEW``/``ADDON``/``REPAY`` 가 정본,
  ``models.py`` ``ExternalOrderLink.relation``)에 따라 **문구가 다르다**:
  재결제는 옛 집이 **대체**되고(옛 결제 환불 — ``repay_reconcile.deposit_guidance``),
  추가결제는 옛 집이 **살아 있다**(그 위에 더 낸 돈). 두 관계를 같게 다루면 담당자가
  살아 있는 원 주문을 죽은 것으로 읽는다.
* 집이 **하나뿐이면** 화면에 무게를 더하지 않는다(라벨 없음).
* 이름이 겹치는 본품끼리는 드롭다운에서 갈라 말한다(집 라벨 + 주문번호 뒤 4자리).
"""

from __future__ import annotations

import pathlib
import re

from db import db_session
from foms.services.integrations.naver_commerce.dock import build_dock_payload
from foms.services.orders.order_create import create_order
from models import ExternalOrderLink, Order, User
from werkzeug.security import generate_password_hash

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_DOCK_JS = _REPO_ROOT / "static" / "js" / "orders" / "erp-naver-dock.js"
_DOCK_CSS = _REPO_ROOT / "static" / "css" / "orders" / "erp-naver-dock.css"
_ORDER_JS_TPL = _REPO_ROOT / "templates" / "orders" / "partials" / "erp_order_js.html"

#: 실화면과 같은 조건 — 두 집의 본품 이름이 **완전히 같다**.
_SAME_NAME = "라홈 무몰딩 붙박이장 로라 시리즈 30cm 푸쉬타입 친환경 E0"
_OLD_NO = "2026082545684381"
_NEW_NO = "2026082615627581"

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"hh{_SEQ[0]}"


def _squash(text: str) -> str:
    """줄바꿈·들여쓰기를 공백 하나로 눌러 소스 문구를 한 줄로 비교한다."""
    return re.sub(r"\s+", " ", text)


def _owner() -> User:
    user = User(username=f"dock_hh_{_uid()}", password=generate_password_hash("pw"),
                role="STAFF", team="CS", name="접수 담당", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _snapshot(*, product_name: str, option: str = "사이즈: 3000 / 색상: 화이트",
              product_class: str = "조합형옵션상품", amount: int = 100000,
              order_no: str = _OLD_NO) -> dict:
    return {
        "order": {"orderId": order_no, "ordererName": "이수취",
                  "ordererTel": "010-1111-2222"},
        "productOrder": {
            "productOrderId": f"PO-{_uid()}",
            "productName": product_name,
            "productOption": option,
            "productClass": product_class,
            "totalPaymentAmount": amount,
            "quantity": 1,
            "shippingAddress": {"name": "이수취", "tel1": "010-3333-4444",
                                "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
        },
    }


def _naver_order(owner: User) -> Order:
    order = create_order(
        db_session,
        actor_user_id=owner.id, owner_user_id=owner.id,
        order_fields=dict(received_date="2026-08-25", customer_name="이수취",
                          phone="010-3333-4444", address="서울 강남구 1 101호",
                          product="붙박이장", options="색상: 화이트", status="RECEIVED"),
        structured_data={"source": "NAVER_SMARTSTORE"},
        is_erp_order=True,
    )
    db_session.flush()
    return order


def _link(order: Order, snapshot: dict, *, order_no: str,
          relation: str = "NEW") -> ExternalOrderLink:
    """집 번호와 **관계**를 직접 찍은 수집 링크 하나.

    ``relation`` 은 붙이기(:func:`promotion.attach_link_to_order`)가 새로 붙는 집의
    형제 전부에 찍는 값이다 — 원 주문 집은 ``NEW`` 로 남는다.
    """
    link = ExternalOrderLink(
        channel="NAVER",
        external_id=snapshot["productOrder"]["productOrderId"],
        order_id=order.id,
        external_order_no=order_no,
        sync_status="LINKED",
        relation=relation,
        raw_snapshot=snapshot,
    )
    db_session.add(link)
    db_session.commit()
    return link


def _two_households(relation: str) -> Order:
    """이름이 같은 본품 두 개 — 원 주문 집(NEW) + 나중에 붙은 집(``relation``)."""
    order = _naver_order(_owner())
    _link(order, _snapshot(product_name=_SAME_NAME, order_no=_OLD_NO),
          order_no=_OLD_NO, relation="NEW")
    _link(order, _snapshot(product_name=_SAME_NAME, order_no=_NEW_NO),
          order_no=_NEW_NO, relation=relation)
    return order


# --------------------------------------------------------------------------- #
# (1) 행 단위 사실 — 어느 집에서 왔는가
# --------------------------------------------------------------------------- #

def test_every_row_says_which_household_it_came_from(app):
    """행마다 **자기 집 주문번호와 관계**가 실린다 — 화면이 추측하지 않게.

    지금까지 행에는 ``external_id``(상품주문번호)만 있었고 ``external_order_no``
    (집 주문번호)는 payload 최상위에만 있었다. 그래서 화면은 "이 행이 어느 집 것인가"를
    말할 방법이 없었다(``dock.py`` ``build_dock_payload`` rows 조립부).
    """
    order = _two_households("REPAY")

    payload = build_dock_payload(db_session, order)

    assert [row["external_order_no"] for row in payload["rows"]] == [_OLD_NO, _NEW_NO]
    assert [row["relation"] for row in payload["rows"]] == ["NEW", "REPAY"]


# --------------------------------------------------------------------------- #
# (2) 재결제 — 옛 집은 대체됐다
# --------------------------------------------------------------------------- #

def test_repay_marks_the_original_household_as_previous(app):
    """재결제 집이 붙으면 원 주문 집이 **이전 주문**으로 내려앉는다.

    근거: ``repay_reconcile.deposit_guidance`` — REPAY 는 "옛 결제는 환불됐다 —
    더하면 이중 계상"이라 예약금을 **바꾼다**. 즉 옛 집의 돈은 죽었다. 화면이 두 집을
    같은 톤으로 세우면 담당자가 죽은 집의 규격을 새 규격으로 읽는다.
    """
    order = _two_households("REPAY")

    payload = build_dock_payload(db_session, order)

    old, new = payload["households"]
    assert old["order_no"] == _OLD_NO
    assert old["relation"] == "NEW"
    assert old["superseded"] is True
    assert old["label"] == "이전 주문"
    assert "재결제" in old["note"]
    assert new["order_no"] == _NEW_NO
    assert new["relation"] == "REPAY"
    assert new["superseded"] is False
    assert new["label"] == "이번 주문(재결제)"
    # 행에도 같은 사실이 실린다 — 화면은 행 단위로 흐린다(귀속이 집을 넘나들 수 있다).
    assert [row["superseded"] for row in payload["rows"]] == [True, False]


def test_repay_keeps_the_previous_rows_and_their_copy_chips(app):
    """이전 주문 행을 **지우거나 비우지 않는다** — 규격이 그대로일 수 있다.

    재결제는 "같은 주문을 다시 결제"라 옛 옵션 원문이 여전히 유효한 규격일 수 있고,
    담당자가 새 집과 **비교**해야 무엇이 바뀌었는지 안다. 그래서 접지 않고 흐린다.
    """
    order = _two_households("REPAY")

    payload = build_dock_payload(db_session, order)

    previous = payload["rows"][0]
    assert previous["option_text"] == "사이즈: 3000 / 색상: 화이트"
    assert previous["copies"] == ["3000", "화이트"]


# --------------------------------------------------------------------------- #
# (3) 추가결제 — 옛 집은 살아 있다
# --------------------------------------------------------------------------- #

def test_addon_does_not_bury_the_original_household(app):
    """추가결제는 원 주문을 **죽이지 않는다** — 흐리게 하면 거짓말이다.

    근거: ``repay_reconcile.deposit_guidance`` ADDON 갈래 — "옛 결제는 살아 있고 그
    위에 더 낸 돈"이라 예약금을 **더한다**. 원 주문 집의 규격이 여전히 이번 시공 대상이다.
    """
    order = _two_households("ADDON")

    payload = build_dock_payload(db_session, order)

    old, new = payload["households"]
    assert old["superseded"] is False
    assert old["label"] == "원 주문"
    assert old["note"] == ""
    assert new["relation"] == "ADDON"
    assert new["superseded"] is False
    assert new["label"] == "추가결제분"
    assert not any(row["superseded"] for row in payload["rows"])


# --------------------------------------------------------------------------- #
# (4) 집이 하나면 오늘과 같다
# --------------------------------------------------------------------------- #

def test_single_household_gets_no_household_label(app):
    """집이 하나뿐인 보통 주문에는 라벨을 만들지 않는다(화면 무게 0)."""
    order = _naver_order(_owner())
    _link(order, _snapshot(product_name=_SAME_NAME, order_no=_OLD_NO), order_no=_OLD_NO)

    payload = build_dock_payload(db_session, order)

    assert len(payload["households"]) == 1
    assert payload["households"][0]["label"] == ""
    assert payload["households"][0]["superseded"] is False
    assert payload["rows"][0]["superseded"] is False
    assert payload["mains"][0]["qualifier"] == ""


def test_two_plain_households_are_not_called_previous(app):
    """관계가 둘 다 ``NEW`` 면 어느 쪽도 '이전 주문'이 아니다 — 근거가 없다.

    옛 데이터(관계 컬럼이 생기기 전 붙은 집)가 여기로 온다. 재결제로 **추정**해 흐리게
    하면 살아 있는 집을 죽은 것으로 그린다.
    """
    order = _two_households("NEW")

    payload = build_dock_payload(db_session, order)

    assert [hh["label"] for hh in payload["households"]] == ["", ""]
    assert not any(hh["superseded"] for hh in payload["households"])
    assert not any(row["superseded"] for row in payload["rows"])


# --------------------------------------------------------------------------- #
# (5) 동명이인 본품 — 귀속 드롭다운이 갈라 말한다
# --------------------------------------------------------------------------- #

def test_same_named_mains_get_a_distinguishing_qualifier(app):
    """이름이 똑같은 본품 두 개는 **집 라벨 + 주문번호 뒤 4자리**로 갈린다.

    실화면 결함: 드롭다운 선택지 두 개가 글자 하나까지 같아서 고를 근거가 없었다.
    """
    order = _two_households("REPAY")

    payload = build_dock_payload(db_session, order)

    qualifiers = [main["qualifier"] for main in payload["mains"]]
    assert qualifiers == ["이전 주문 …4381", "이번 주문(재결제) …7581"]
    assert len(set(qualifiers)) == 2, "같은 이름 본품이 여전히 구분되지 않는다"
    # 이름 자체는 원문 그대로 둔다 — 복사·검색이 깨지면 안 된다.
    assert {main["label"] for main in payload["mains"]} == {_SAME_NAME}


def test_distinct_main_names_need_no_qualifier(app):
    """이름이 다르면 굳이 덧붙이지 않는다 — 이미 이름이 구분한다."""
    order = _naver_order(_owner())
    _link(order, _snapshot(product_name="붙박이장 A", order_no=_OLD_NO),
          order_no=_OLD_NO, relation="NEW")
    _link(order, _snapshot(product_name="붙박이장 B", order_no=_NEW_NO),
          order_no=_NEW_NO, relation="REPAY")

    payload = build_dock_payload(db_session, order)

    assert [main["qualifier"] for main in payload["mains"]] == ["", ""]


def test_mains_carry_their_household_facts(app):
    """본품 항목이 자기 집·관계·대체 여부를 들고 있다(화면 머리말이 읽는 자리)."""
    order = _two_households("REPAY")

    payload = build_dock_payload(db_session, order)

    assert payload["mains"][0]["order_no"] == _OLD_NO
    assert payload["mains"][0]["superseded"] is True
    assert payload["mains"][1]["order_no"] == _NEW_NO
    assert payload["mains"][1]["relation"] == "REPAY"


# --------------------------------------------------------------------------- #
# (6) 화면 — 인라인 스타일 금지, ?v 핀 범프
# --------------------------------------------------------------------------- #

def test_dock_js_dims_previous_rows_by_class_not_inline_style():
    """이전 주문 행은 **CSS 클래스**로 흐려진다(인라인 스타일 금지 — 프로젝트 규칙)."""
    source = _squash(_DOCK_JS.read_text(encoding="utf-8"))
    assert "row.superseded ? ' is-superseded' : ''" in source
    assert "naver-dock-hh" in source, "집 표식 부품이 없다"
    assert "main.qualifier" in source, "드롭다운이 동명이인을 갈라 말하지 않는다"


def test_dock_css_has_the_previous_household_treatment():
    """CSS 에 이전 주문 처리(흐림)와 집 표식 규칙이 있다."""
    css = _DOCK_CSS.read_text(encoding="utf-8")
    assert ".naver-dock-row.is-superseded" in css
    assert ".naver-dock-hh" in css


def test_dock_asset_pin_moved_for_household_split():
    """CSS·JS 를 고쳤으니 ``?v`` 핀이 움직였다.

    SW 가 ``staticCacheFirst`` 라 핀을 안 올리면 옛 자산이 계속 서빙되어 배포해도
    사람 화면은 그대로다.
    """
    tpl = _ORDER_JS_TPL.read_text(encoding="utf-8")
    assert "js/orders/erp-naver-dock.js') }}?v=20260902b" in tpl
    assert "css/orders/erp-naver-dock.css') }}?v=20260902a" in tpl


# ------------------------------------------- 확인 완료 게이트가 죽은 주문을 안 센다


def test_dock_gate_counts_only_live_rows():
    """`확인 완료` 게이트는 **살아 있는 주문 행만** 센다.

    재결제로 주문이 둘 붙으면 옛 주문은 이미 취소·환불된 죽은 것이다. 그런데 게이트가
    `state.rows.length` 를 그대로 세서 **죽은 행에도 "반영함" 체크를 찍어야** 버튼이
    열렸다(스테이징 order 4485 실화면: `0 / 10 반영`, 그중 4행이 이전 주문).

    담당자에게 "이 죽은 주문을 확인했다"고 찍으라고 요구하는 것은 거짓 확인을
    강요하는 것이다 — 흐리게 그려 놓고 체크는 받는 모순이기도 하다.
    """
    source = _squash(_DOCK_JS.read_text(encoding="utf-8"))
    assert "function liveRows()" in source, "살아 있는 행만 고르는 함수가 없다"
    # 분자·분모가 같은 모집단이어야 한다 — 한쪽만 바꾸면 checked > total 이 된다.
    assert "liveRows().length" in source, "총계가 여전히 전체 행 수다"
    assert source.count("liveRows()") >= 4, (
        "총계·체크수·귀속미정·완료판정 넷이 같은 모집단을 써야 한다")


def test_dock_gate_does_not_claim_done_when_every_row_is_dead():
    """행이 **전부** 죽은 경우엔 옛 판정으로 되돌린다(빈 `every` 는 true 라 위험).

    `[].every(...)` 는 true 다 — 살아 있는 행이 0개면 게이트가 아무 확인 없이
    "확인 완료됨"이라고 말한다. 실데이터에 그런 주문은 없지만, 없는 것을 근거로
    안전장치를 빼지 않는다.
    """
    source = _squash(_DOCK_JS.read_text(encoding="utf-8"))
    assert "live.length ? live : state.rows" in source, "전멸 시 폴백이 없다"
