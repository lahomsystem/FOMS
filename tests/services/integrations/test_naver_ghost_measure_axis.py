"""유령 주문 목록의 **실측 축** — 실측 전 취소인가 실측 후 취소인가 (2026-09-07).

가구는 실측을 나가면 사람·차·시간이 이미 나간 것이다. 실측 전 취소와 실측 후 취소는
회수·정산·고객 응대가 전부 다르다. 그런데 유령 띠의 `진행` 칸은 단계 한 낱말만 말해서,
담당자가 그 주문을 따로 열기 전에는 실측을 마친 건인지 알 수 없었다.

여기서 못박는 것 둘:

1. 행에 `실측 후` / `실측 전` / `실측일 없음` 세 낱말 중 하나가 나온다. 모르면
   **모른다고 말하고 날짜를 지어내지 않는다**.
2. 이번 변경은 **표시 축 추가**다 — 모집단(전부 취소만 유령)·`can_discard`·
   `discard_needs_reason`·`discard_block` 은 한 글자도 안 바뀐다. 판정이 흔들리면
   확정 전 취소 주문이 접히는 사고가 난다.
"""
import datetime

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.ghost_orders import find_ghost_orders
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink, Order, OrderScheduleDate, User

TRIAGE_PATH = "/admin/naver-ingest/triage?tab=work"

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"{_SEQ[0]:04d}"


def _iso(delta_days: int) -> str:
    """오늘 기준 상대 날짜(YYYY-MM-DD) — 고정 날짜를 박으면 언젠가 과거가 된다."""
    from foms.services.datetime_kst import get_today_kst

    return (get_today_kst() + datetime.timedelta(days=delta_days)).isoformat()


@pytest.fixture()
def workbench_on(monkeypatch):
    """워크벤치 게이트를 켠다(전역 on + 코호트 all)."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


def _login(client, *, role: str = "ADMIN") -> User:
    user = User(username=f"gmeas_{role.lower()}_{_uid()}", password=generate_password_hash("pw"),
                role=role, team="CS", name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order(*, tel: str, status: str = "RECEIVED", measurement_date: str | None = None) -> Order:
    """유령 후보 주문 하나. 실측일은 `order_schedule_dates` 정본 테이블에 넣는다."""
    order = Order(received_date="2026-08-13", customer_name=f"실측{_uid()}", phone=tel,
                  erp_phone_digits=tel.replace("-", ""), address="서울 강남구 1 101호",
                  product="붙박이장", status=status, payment_amount=0)
    db_session.add(order)
    db_session.commit()
    if measurement_date:
        db_session.add(OrderScheduleDate(order_id=int(order.id), kind="measurement",
                                         date=measurement_date, source="beta_schedule"))
        db_session.commit()
    return order


def _link(*, order_no: str, amount: int, tel: str, claim: str = "",
          order_id: int | None = None) -> ExternalOrderLink:
    """주문에 붙은 네이버 상품주문 링크 하나(클레임 상태는 선택)."""
    product_order = {
        "productOrderId": f"PO-GM-{_uid()}",
        "productName": "붙박이장",
        "totalPaymentAmount": amount,
        "shippingAddress": {"name": "이수취", "tel1": tel,
                            "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
    }
    if claim:
        product_order["claimStatus"] = claim
    snapshot = {"order": {"orderId": order_no, "ordererTel": tel}, "productOrder": product_order}
    link = ExternalOrderLink(channel=CHANNEL, external_id=product_order["productOrderId"],
                             external_order_no=order_no, raw_snapshot=snapshot,
                             group_key=group_key_text(snapshot),
                             sync_status="LINKED" if order_id else "COLLECTED",
                             relation="NEW", order_id=order_id)
    db_session.add(link)
    db_session.commit()
    return link


def _row_for(order_id: int) -> dict:
    """유령 목록에서 그 주문의 행 하나를 꺼낸다(없으면 바로 터뜨린다)."""
    rows = [row for row in find_ghost_orders(db_session)["rows"] if row["order_id"] == order_id]
    assert rows, f"주문 #{order_id} 가 유령 목록에 없다"
    return rows[0]


def test_past_measurement_date_reads_as_after(app):
    """실측일이 지난 유령은 `실측 후`다 — 사람·차가 이미 나갔다."""
    tel = "010-7400-0001"
    past = _iso(-5)
    order = _order(tel=tel, measurement_date=past)
    _link(order_no="N-GM-1", amount=667_600, claim="CANCEL_DONE", tel=tel, order_id=int(order.id))

    row = _row_for(int(order.id))

    assert row["measure"].code == "after"
    assert row["measure"].label == "실측 후"
    assert row["measure"].text == f"실측 후 · {past[5:]}", "화면 날짜는 MM-DD 다"


def test_future_measurement_date_reads_as_before(app):
    """실측일이 아직 안 왔으면 `실측 전`이다 — 나간 비용이 없다."""
    tel = "010-7400-0002"
    upcoming = _iso(5)
    order = _order(tel=tel, measurement_date=upcoming)
    _link(order_no="N-GM-2", amount=310_000, claim="CANCEL_DONE", tel=tel, order_id=int(order.id))

    row = _row_for(int(order.id))

    assert row["measure"].code == "before"
    assert row["measure"].text == f"실측 전 · {upcoming[5:]} 예정"


def test_missing_measurement_date_says_it_does_not_know(app):
    """실측일이 없으면 **모른다고 말한다** — 날짜를 지어내지 않는다."""
    tel = "010-7400-0003"
    order = _order(tel=tel)
    _link(order_no="N-GM-3", amount=120_000, claim="CANCEL_DONE", tel=tel, order_id=int(order.id))

    row = _row_for(int(order.id))

    assert row["measure"].code == "none"
    assert row["measure"].text == "실측일 없음"
    assert row["measure"].date == ""
    assert "·" not in row["measure"].text, "근거가 없는데 날짜 칸을 그렸다"


def test_partially_canceled_order_has_no_measure_line(app):
    """음성 대조군 — 부분 취소는 애초에 유령이 아니라 이 줄도 없다.

    살아 있는 결제가 섞인 주문은 정상 진행 중일 수 있다. 모집단이 그대로라는 뜻이기도 하다.
    """
    tel = "010-7400-0004"
    order = _order(tel=tel, measurement_date=_iso(-3))
    _link(order_no="N-GM-4", amount=200_000, claim="CANCEL_DONE", tel=tel, order_id=int(order.id))
    _link(order_no="N-GM-4", amount=150_000, tel=tel, order_id=int(order.id))

    ids = [row["order_id"] for row in find_ghost_orders(db_session)["rows"]]

    assert int(order.id) not in ids


def test_measure_axis_does_not_move_the_discard_verdict(app):
    """판정 불변 회귀 — 실측 축을 뺀 나머지 키가 변경 전과 같다.

    실측일이 지났든 안 지났든, 확정 전 취소는 잠기고 확정 취소는 열린다. 실측 축은
    표시일 뿐이라 폐기 판정에 한 글자도 못 끼어든다.
    """
    done_tel = "010-7400-0005"
    done = _order(tel=done_tel, status="MEASURE", measurement_date=_iso(-2))
    _link(order_no="N-GM-5", amount=579_200, claim="CANCEL_DONE", tel=done_tel,
          order_id=int(done.id))
    pending_tel = "010-7400-0006"
    pending = _order(tel=pending_tel, measurement_date=_iso(9))
    _link(order_no="N-GM-6", amount=667_600, claim="CANCEL_REQUEST", tel=pending_tel,
          order_id=int(pending.id))

    done_row = _row_for(int(done.id))
    pending_row = _row_for(int(pending.id))

    assert done_row["measure"].code == "after"
    assert done_row["can_discard"] is True
    assert done_row["discard_needs_reason"] is True
    assert done_row["discard_block"] == ""
    assert done_row["status_label"] == "실측"
    assert pending_row["measure"].code == "before"
    assert pending_row["can_discard"] is False
    assert pending_row["discard_needs_reason"] is False
    assert pending_row["discard_block"] == (
        "네이버가 아직 취소를 확정하지 않았습니다 — 확정 후에 접으세요")


def test_ghost_strip_renders_the_measure_line(app, client, workbench_on):
    """화면에 실제로 나온다 — 서버 렌더 Jinja 라 JS 없이 마크업으로 잰다."""
    _login(client)
    after_tel = "010-7400-0007"
    past = _iso(-4)
    after_order = _order(tel=after_tel, measurement_date=past)
    after_id = int(after_order.id)
    _link(order_no="N-GM-7", amount=900_000, claim="CANCEL_DONE", tel=after_tel,
          order_id=after_id)
    before_tel = "010-7400-0008"
    before_order = _order(tel=before_tel, measurement_date=_iso(6))
    before_id = int(before_order.id)
    _link(order_no="N-GM-8", amount=400_000, claim="CANCEL_DONE", tel=before_tel,
          order_id=before_id)

    body = client.get(TRIAGE_PATH).get_data(as_text=True)

    assert f'data-ghost-order-id="{after_id}"' in body
    assert f'data-ghost-order-id="{before_id}"' in body
    assert 'class="wb-ghost__meas wb-ghost__meas--after"' in body
    assert f"실측 후 · {past[5:]}" in body
    assert 'class="wb-ghost__meas wb-ghost__meas--before"' in body
    assert "실측 일정" in body, "근거(basis_text)를 안 적었다"


def test_ghost_strip_says_unknown_without_inventing_a_date(app, client, workbench_on):
    """실측일이 없는 유령 행은 화면에서도 모른다고만 말한다."""
    _login(client)
    tel = "010-7400-0009"
    order = _order(tel=tel)
    order_id = int(order.id)
    _link(order_no="N-GM-9", amount=250_000, claim="CANCEL_DONE", tel=tel, order_id=order_id)

    body = client.get(TRIAGE_PATH).get_data(as_text=True)

    assert f'data-ghost-order-id="{order_id}"' in body
    assert 'class="wb-ghost__meas wb-ghost__meas--none">실측일 없음</div>' in body
