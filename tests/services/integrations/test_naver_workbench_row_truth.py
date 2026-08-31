"""행이 말하는 건수·상태가 사실인가 (2026-08-24 감사 ①②).

**① 'N건 묶음'**: 행 배지는 화면 모집단 안의 수(``group.count``)를 썼다. 확인이 끝났거나
매핑 실패로 큐에서 빠진 형제는 안 센다. 그래서 담당자는 "2건 묶음"을 읽고 체크한 뒤
벌크 모달에서 "상품주문 4건"을 봤다 — 한 화면 안에서 건수가 두 개라 어느 쪽이 진짜인지
알 수 없다. 배지는 **집 전체 수**(``household_count``)를 말해야 한다.

**② 발주확인 완료 표시**: 끝난 집에는 아무 표시가 없어서 '발주확인 전' 배지가 **없다는
사실**로만 읽어야 했다. 화면 규칙을 외운 사람만 읽는다. 게다가 그 행의 체크박스는 회색인데
이유가 hover 전용 title 에만 있었다.

두 값은 여전히 **다른 뜻**이다(집 크기 vs 실제로 나갈 건수). 그래서 같아지는지가 아니라
각자 무엇을 말하는지를 잰다.
"""
from __future__ import annotations

import datetime

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import ExternalOrderLink, User

TRIAGE_PATH = "/admin/naver-ingest/triage?tab=work&f=all"
_SEQ = [0]


@pytest.fixture()
def workbench_on(monkeypatch):
    """워크벤치 게이트를 켠다(전역 on + 코호트 all)."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


def _login(client) -> User:
    """ADMIN 으로 로그인한다(이력 탭까지 보이는 최대 권한)."""
    _SEQ[0] += 1
    user = User(username=f"wbrow_{_SEQ[0]}", password=generate_password_hash("pw"),
                role="ADMIN", team="CS", name="검수자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
    return user

_REVIEWED = datetime.datetime(2026, 8, 24, 0, 0, 0)


def _link(db, *, external_id: str, order_no: str, name: str, tel: str,
          place: str = "NOT_YET", reviewed_at=None) -> ExternalOrderLink:
    """한 집(주문번호·전화·주소가 같으면 같은 집)의 상품주문 1건."""
    row = ExternalOrderLink(
        channel="NAVER", external_id=external_id, external_order_no=order_no,
        sync_status="COLLECTED" if reviewed_at is None else "LINKED",
        place_order_status=place, reviewed_at=reviewed_at,
        raw_snapshot={
            "order": {"orderId": order_no},
            "productOrder": {
                "productOrderId": external_id, "productName": f"{name} 상품",
                "totalPaymentAmount": 100000, "placeOrderStatus": place,
                "shippingAddress": {"name": name, "tel1": tel,
                                    "baseAddress": f"서울 {name}로 1",
                                    "detailedAddress": "101호"},
            },
        },
    )
    db.add(row)
    db.commit()
    return row


def _mixed_household(db) -> None:
    """상품주문 4건짜리 집 — 2건은 확인이 끝나 큐에서 빠져 있다.

    화면 모집단(큐)에는 2건만 있고 집 전체는 4건이다. 예전 배지는 2를, 워커는 4를 봤다.
    """
    for index in range(2):
        _link(db, external_id=f"2026082470000{index}", order_no="N-MIX",
              name="섞인집", tel="010-7000-0001")
    for index in range(2, 4):
        _link(db, external_id=f"2026082470000{index}", order_no="N-MIX",
              name="섞인집", tel="010-7000-0001", place="OK", reviewed_at=_REVIEWED)


def test_row_badge_counts_the_whole_household(app):
    """행이 말하는 건수는 **집 전체**다 — 화면 모집단 수가 아니다."""
    from db import db_session
    from foms.web.admin.naver_ingest import _work_groups

    _mixed_household(db_session)
    groups, _truncated = _work_groups(db_session)

    assert len(groups) == 1
    group = groups[0]
    assert group["household_count"] == 4, "집 전체 수가 틀렸다"
    assert group["count"] == 2, "사전 조건: 화면 모집단은 2건이다(이 둘이 달라야 의미가 있다)"


def test_bulk_restates_what_actually_goes_out(app):
    """벌크가 재진술하는 건수는 **실제로 나갈 건수**다(계약 §0-2).

    집 전체(4건)가 아니라 아직 발주확인이 안 된 2건이다. 배지와 모달이 다른 수를 말하는
    것은 옳다 — 다른 사실이기 때문이다. 화면은 그 차이를 문구로 설명한다.
    """
    from db import db_session
    from foms.web.admin.naver_ingest import _work_groups

    _mixed_household(db_session)
    groups, _truncated = _work_groups(db_session)

    assert groups[0]["household_place_pending"] == 2


@pytest.mark.parametrize("place,expect_done", [("NOT_YET", False), ("OK", True)])
def test_finished_household_is_marked_not_merely_unmarked(client, workbench_on, place, expect_done):
    """발주확인이 끝난 집은 **글자로** 그렇게 말한다 — 배지 부재로 읽게 두지 않는다."""
    _login(client)
    _link(db_session, external_id="20260824710001", order_no="N-DONE",
          name="완료집", tel="010-7000-0002", place=place)

    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    if expect_done:
        assert "발주확인 완료" in body, "끝난 집에 아무 표시가 없다"
    else:
        assert "발주확인 할 차례" in body


def test_list_header_does_not_reuse_the_strip_wording(client, workbench_on):
    """목록 헤더는 '보이는 줄 수'다 — 스트립의 '손댈 수 있는 집'과 같은 말로 읽히면 안 된다."""
    _login(client)
    _link(db_session, external_id="20260824720001", order_no="N-HEAD",
          name="머리집", tel="010-7000-0003")

    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    assert "보이는" in body.split("한 주문이 한 줄")[1][:40]
