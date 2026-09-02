# -*- coding: utf-8 -*-
"""NVCLAIM-ORDER-01 **2차 배** — `확인함` 의 범위와 라인별 클레임 칸.

1차 배(``555cfe8d7``)는 호출 순서·부분 실패·가드 스코프·집 배지를 고쳤지만 두 자리를
버티기로 남겼다:

* ``clear_failure`` 가 **집 전체** ``last_error`` 를 지운다 → 실패 띠는 집당 한 줄이고
  그 줄은 작업 하나만 말하므로, 사람은 발주확인 실패를 확인하면서 **본 적도 없는 반품
  실패**를 함께 지우고 있었다. 반품 접수에 실패한 라인에는 ``return`` 축 기록이 아예
  없어서(기록은 성공분만 받는다) 그 사유가 "이 본품은 환불되지 않았다"의 유일한 증거다.
* 상품주문 표에 **클레임 칸이 없다** → 어느 화면도 "이 집 4건 중 무엇이 반품됐고 무엇이
  안 됐나"를 답하지 못했다. 황민철 집(ERP 5026)이 추가상품 3건만 환불된 채로
  `반품 완료` 로 읽힌 자리다.

픽스처 규율: 한 집 안에 **작업이 다른 실패 둘**을 반드시 둔다. 같은 작업만 있는 집은
집 단위로 지워도 통과해서 동어반복이 된다.
"""
from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.constants import ADDON_PRODUCT_CLASS, CHANNEL
from foms.services.integrations.naver_commerce.fulfillment import (
    clear_failure,
    failure_action,
)
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink, User

TRIAGE_PATH = "/admin/naver-ingest/triage"

MAIN_PRODUCT_CLASS = "조합형옵션상품"

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


@pytest.fixture()
def workbench_on(monkeypatch):
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


def _login(client) -> User:
    user = User(username=f"wb_ack_{_uid()}", password=generate_password_hash("pw"),
                role="ADMIN", team="CS", name="관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _link(*, order_no: str, addon: bool = False, product: str = "붙박이장",
          claim: str = "", dispatched: bool = False, returned: bool = False,
          failure: str = "", failure_action_name: str | None = "confirm",
          ) -> ExternalOrderLink:
    """상품주문 1건. ``addon`` 이 ``productClass``(호출 순서 판별 정본)를 가른다.

    ``failure_action_name=None`` 이면 ``last_error_action`` 자체를 안 적는다 — 옛 기록
    모양이다(화면과 서비스가 같은 기본값으로 읽어야 하는 자리).
    """
    external_id = f"PO-ACK-{_uid()}"
    product_order = {
        "productOrderId": external_id, "productName": product,
        "totalPaymentAmount": 594000, "placeOrderStatus": "OK", "quantity": 1,
        "productClass": ADDON_PRODUCT_CLASS if addon else MAIN_PRODUCT_CLASS,
        "shippingAddress": {"name": "황수취", "tel1": "010-3333-4444",
                            "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
    }
    if claim:
        product_order["claimStatus"] = claim
        product_order["claimType"] = "RETURN"
    if dispatched or claim:
        product_order["delivery"] = {"sendDate": "2026-08-31T10:00:00.0+09:00"}
    snapshot = {"order": {"orderId": order_no, "ordererName": "황민철"},
                "productOrder": product_order}
    state: dict = {}
    if failure:
        state["fulfillment"] = {"last_error": failure,
                                "last_error_at": "2026-09-01T23:33:44"}
        if failure_action_name is not None:
            state["fulfillment"]["last_error_action"] = failure_action_name
    if dispatched:
        state.setdefault("fulfillment", {})["dispatched_at"] = "2026-08-31T01:00:00"
    if returned:
        state["return"] = {"requested_at": "2026-09-01T14:33:00"}
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             sync_status="COLLECTED", external_order_no=order_no,
                             raw_snapshot=snapshot, group_key=group_key_text(snapshot),
                             place_order_status="OK", triage_state=state or None)
    db_session.add(link)
    db_session.commit()
    return link


def _error(link: "ExternalOrderLink | int") -> str:
    """그 링크의 실패 사유를 **DB 에서 다시 읽는다**.

    라우트는 자기 세션(``get_db``)으로 쓰므로 테스트 세션의 객체는 낡아 있다 —
    요청 뒤에는 detach 되어 ``refresh`` 도 속성 접근도 못 한다. 라우트를 지나는
    테스트는 **id 를 미리 집어** 여기에 넘긴다.
    """
    link_id = link if isinstance(link, int) else int(link.id)
    db_session.expire_all()
    row = db_session.get(ExternalOrderLink, link_id)
    return str(((row.triage_state or {}).get("fulfillment") or {}).get("last_error") or "")


# ───────────────────────────────────── T1 `확인함` 범위 = 사람이 본 그 작업


def test_ack_clears_every_line_that_failed_the_same_way(app):
    """같은 작업으로 실패한 형제는 **함께** 지워진다 — 띠가 한 줄로 접혀 있기 때문이다.

    좁히기가 "한 링크만"이었다면 3건이 같은 이유로 실패한 집에서 사람이 세 번 눌러야
    하고, 두 번째 클릭까지의 화면은 자기가 방금 닫은 실패를 다시 보여준다.
    """
    order_no = f"N-ACK-SAME-{_uid()}"
    first = _link(order_no=order_no, failure="커머스API 인증 만료")
    second = _link(order_no=order_no, addon=True, failure="커머스API 인증 만료")

    result = clear_failure(db_session, link_id=int(first.id), actor_user_id=7)
    db_session.commit()

    assert result["cleared"] == 2
    assert result["kept"] == 0
    assert result["action"] == "confirm"
    assert _error(first) == ""
    assert _error(second) == ""


def test_ack_does_not_erase_a_return_failure_the_operator_never_saw(app):
    """**핵심 회귀** — 발주확인 실패를 확인해도 형제의 반품 실패는 남는다.

    황민철 사고(ERP 5026)의 모양이다: 반품 접수에 실패한 본품에는 ``return`` 축 기록이
    아예 없어서 그 ``last_error`` 가 "환불되지 않았다"의 유일한 DB 흔적이다. 집 전체를
    지우던 시절에는 사람이 **다른 줄**을 닫는 것만으로 그 흔적이 사라졌다.
    """
    order_no = f"N-ACK-MIX-{_uid()}"
    confirm_failed = _link(order_no=order_no, addon=True,
                           failure="커머스API 인증 만료", failure_action_name="confirm")
    return_failed = _link(order_no=order_no, dispatched=True,
                          failure="추가상품 반품진행 후, 본 상품 반품진행을 할 수 있습니다.",
                          failure_action_name="return")

    result = clear_failure(db_session, link_id=int(confirm_failed.id), actor_user_id=7)
    db_session.commit()

    assert result["cleared"] == 1
    assert result["kept"] == 1, "안 본 실패를 남겼다고 말해야 원장이 그 사실을 안다"
    assert _error(confirm_failed) == ""
    assert "본 상품 반품진행" in _error(return_failed), \
        "사람이 본 적 없는 반품 실패가 지워졌다 — RC5 그 자체다"
    assert failure_action(return_failed) == "return"


def test_ack_demotes_the_reason_instead_of_destroying_it(app):
    """지운 사유는 ``last_error_cleared`` 로 내려간다 — 띠는 닫히되 기록은 남는다."""
    order_no = f"N-ACK-KEEP-{_uid()}"
    link = _link(order_no=order_no, failure="판매자센터에서 처리함",
                 failure_action_name="dispatch")

    clear_failure(db_session, link_id=int(link.id), actor_user_id=11)
    db_session.commit()

    state = (link.triage_state or {}).get("fulfillment") or {}
    assert state["last_error"] == ""
    assert state["last_error_cleared"] == "판매자센터에서 처리함"
    assert state["last_error_cleared_action"] == "dispatch"
    assert state["failure_cleared_by"] == 11


def test_ack_reads_old_records_the_same_way_the_screen_does(app):
    """``last_error_action`` 이 없는 옛 기록은 **발주확인**으로 읽는다(화면과 같은 기본값).

    두 곳이 갈리면 띠에 보이는 줄과 지워지는 줄이 어긋난다.
    """
    order_no = f"N-ACK-OLD-{_uid()}"
    legacy = _link(order_no=order_no, failure="옛 실패", failure_action_name=None)
    fresh = _link(order_no=order_no, addon=True, failure="새 실패",
                  failure_action_name="confirm")

    assert failure_action(legacy) == "confirm"
    result = clear_failure(db_session, link_id=int(legacy.id))
    db_session.commit()

    assert result["cleared"] == 2
    assert _error(fresh) == ""


def test_ack_does_nothing_when_the_anchor_failure_is_already_gone(app):
    """다른 탭이 먼저 닫았으면 아무것도 안 지운다 — 안 본 실패를 대신 지우지 않는다."""
    order_no = f"N-ACK-RACE-{_uid()}"
    clean = _link(order_no=order_no)
    other = _link(order_no=order_no, addon=True, dispatched=True,
                  failure="반품 접수 실패", failure_action_name="return")

    result = clear_failure(db_session, link_id=int(clean.id))
    db_session.commit()

    assert result["cleared"] == 0
    assert result["action"] == ""
    assert result["kept"] == 1
    assert _error(other) == "반품 접수 실패"


def test_ack_route_reports_what_it_kept(app, client, workbench_on):
    """라우트 응답이 ``{'success','data','error'}`` 를 지키고 남긴 실패 수를 말한다."""
    _login(client)
    order_no = f"N-ACK-ROUTE-{_uid()}"
    anchor_id = int(_link(order_no=order_no, failure="커머스API 인증 만료").id)
    kept_id = int(_link(order_no=order_no, addon=True, dispatched=True,
                        failure="반품 접수 실패", failure_action_name="return").id)

    res = client.post(f"/admin/naver-ingest/{anchor_id}/fulfillment-clear", json={})

    assert res.status_code == 200, res.get_data(as_text=True)
    body = res.get_json()
    assert set(body) == {"success", "data", "error"}
    assert body["success"] is True
    assert body["data"]["cleared"] == 1
    assert body["data"]["kept"] == 1
    assert body["data"]["action"] == "confirm"
    assert _error(kept_id) == "반품 접수 실패"


def test_the_ack_button_is_no_longer_locked_once_the_failure_is_recorded(app, client,
                                                                         workbench_on):
    """T3 가 들어오면 임시 잠금은 걷는다 — 근거가 사라졌기 때문이다.

    **이 단언은 2026-09-02 에 뒤집혔다.** 1차 배는 ``확인함`` 을 잠갔는데, 그 이유는
    반품 접수에 실패한 라인에 ``return`` 축 기록이 아예 없어서(기록은 성공분만 받았다)
    ``last_error`` 가 "이 본품은 환불되지 않았다"의 **유일한 흔적**이었기 때문이다
    (황민철 집, ERP 5026).

    T3 로 실패 라인이 ``failed_at``/``failed_reason`` 을 받고 그 값은 ``확인함`` 이
    지우지 않는다. 근거가 사라졌으니 잠금도 사라진다 — 남겨 두면 실패 띠를 못 닫는
    불편만 남는다. 잠금을 되살리려는 다음 사람은 **그 전에 T3 기록이 살아 있는지**부터
    확인해야 한다.
    """
    _login(client)
    order_no = f"N-ACK-LOCK-{_uid()}"
    _link(order_no=order_no, dispatched=True,
          failure="추가상품 반품진행 후, 본 상품 반품진행을 할 수 있습니다.",
          failure_action_name="return")

    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    strip = body.split('id="wb-result"')[1].split("</section>")[0]

    assert "wb-ack" in strip
    assert "disabled" not in strip, strip[:800]
    assert "아직 보내지 않은 반품 접수" not in strip


# ─────────────────────────────── T2 상품주문 표가 라인별로 말한다


def test_member_rows_say_which_line_is_returned_and_which_is_not(app):
    """사고 재현 집 — 추가상품 3건은 `반품 완료`, 본품 1건은 **아무 기록도 없다**.

    이 대비가 화면에 없어서 집이 통째로 끝난 것처럼 읽혔다.
    """
    from foms.web.admin.naver_ingest import _group_of_link, _member_rows

    order_no = f"N-ACK-MEMBER-{_uid()}"
    main = _link(order_no=order_no, dispatched=True)
    for _ in range(3):
        _link(order_no=order_no, addon=True, claim="RETURN_DONE", returned=True)

    group = _group_of_link(db_session, main)
    rows = _member_rows(db_session, group)

    assert len(rows) == 4
    by_addon = {True: [], False: []}
    for row in rows:
        by_addon[row["is_addon"]].append(row)

    assert len(by_addon[True]) == 3 and len(by_addon[False]) == 1
    for row in by_addon[True]:
        assert row["claim_code"] == "RETURN_DONE"
        assert row["claim_label"] == "반품 완료"
        assert row["claim_blocking"] is True
        assert row["claim_pending"] is False
        assert row["return_requested_at"], "우리 접수 표식이 있어야 한다"
    lonely = by_addon[False][0]
    assert lonely["claim_code"] == ""
    assert lonely["claim_label"] == ""
    assert lonely["return_requested_at"] == "", \
        "미반품 본품이 '접수했다'로 읽히면 사고가 그대로 재현된다"


@pytest.mark.parametrize(("status", "blocking", "pending"), [
    ("", False, False),
    ("RETURN_REQUEST", True, True),
    ("COLLECTING", True, True),
    ("RETURN_DONE", True, False),
    ("RETURN_REJECT", False, False),
])
def test_member_claim_view_decides_on_the_code_not_the_label(app, status, blocking,
                                                             pending):
    """판정 축은 **코드**다 — 라벨(한국어)은 표시 축이라 낱말이 바뀌어도 분기가 안 죽는다.

    음성 대조군을 함께 돈다: 클레임이 없는 줄과 거부된 줄은 둘 다 `막힘 아님`인데
    **뜻이 다르다**(안 걸렸다 vs 걸렸다 풀렸다) — 라벨로 갈랐다면 여기서 어긋난다.
    """
    from foms.web.admin.naver_ingest import _member_claim_view

    link = _link(order_no=f"N-ACK-CODE-{_uid()}", claim=status, dispatched=True)
    view = _member_claim_view(link)

    assert view["claim_code"] == status
    assert view["claim_blocking"] is blocking
    assert view["claim_pending"] is pending
    if status:
        assert view["claim_label"], "라벨이 비면 화면에 영문 상수가 뜬다"


def test_pane_renders_the_per_line_claim_column(app, client, workbench_on):
    """pane 이 라인별 칸을 실제로 그린다 — 넓어진 표는 **자기 컨테이너 안에서** 스크롤한다."""
    _login(client)
    order_no = f"N-ACK-PANE-{_uid()}"
    _link(order_no=order_no, dispatched=True, product="3연동 슬라이딩 도어")
    _link(order_no=order_no, addon=True, claim="RETURN_DONE", returned=True,
          product="타공 서비스")

    body = client.get(TRIAGE_PATH).get_data(as_text=True)

    assert "클레임 · 반품" in body, "라인별 칸 머리글이 없다"
    assert "추가구성상품" in body and "본품" in body
    assert "반품 완료" in body
    assert "클레임 없음" in body
    assert "우리 접수 없음" in body
    # 표는 페이지를 옆으로 밀지 않는다 — 넘치는 만큼은 자기 컨테이너가 받는다.
    # (`wb-cmp` 표는 이 화면에 여럿이라 **상품주문 표**로 좁혀서 본다.)
    section = body.split('data-cmp-section="product-orders"')[1]
    head = section.split('<table class="wb-cmp">')[0]
    assert '<div class="table-responsive">' in head, head[-400:]
