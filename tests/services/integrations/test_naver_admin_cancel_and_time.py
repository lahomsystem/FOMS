"""직권취소 인식 + 워크벤치 시각 표기 (2026-09-22 사용자 보고 4건).

배경: 구매확정된 집(이가령 2026090895141851)을 판매자센터 [판매관리 > 구매확정 내역]에서
취소 처리하면 네이버는 ``claimType=ADMIN_CANCEL`` · ``claimStatus=ADMIN_CANCEL_DONE`` 로
돌려준다(공식 답변 commerce-api Discussions #2028·#2168). 우리 코드에는 이 두 값이
**한 글자도 없었다** — 운영 12건이 "살아 있는 결제"로 읽혔고, 옛 주문 정리 띠는 이미 취소된
집에 계속 `반품 접수` 를 내밀었다.

시각 축도 같이 못박는다. 띠의 `마지막으로 읽은 때` 는 naive UTC 를 그대로 찍어 **9시간 전**을
말했다(사용자 실화면: 오후 1시 22분인데 `2026-09-22 04:18`).
"""
from datetime import datetime

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import (
    BLOCKING_CLAIM_STATUSES,
    CLAIM_STATUS_LABELS,
    blocks_irreversible,
    claim_kind,
    extract_claim,
    group_key_text,
    is_money_back_claim,
)
from foms.services.integrations.naver_commerce.order_candidates import (
    pending_origin_cleanup,
)
from models import ExternalOrderLink, Order, User

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"{_SEQ[0]:04d}"


@pytest.fixture()
def workbench_on(monkeypatch):
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


def _login(client, *, role: str = "ADMIN") -> User:
    user = User(username=f"adm_{role.lower()}_{_uid()}", password=generate_password_hash("pw"),
                role=role, team="CS", name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order() -> Order:
    order = Order(received_date="2026-09-08", customer_name=f"직권{_uid()}",
                  phone="010-7300-0001", erp_phone_digits="01073000001",
                  address="경기 화성시 영통로 60 1404호", product="리라 TV 월플렉스",
                  status="MEASURE", payment_amount=0)
    db_session.add(order)
    db_session.commit()
    return order


def _claim(status: str, kind: str = "") -> dict:
    return extract_claim({"productOrder": {"claimStatus": status, "claimType": kind}})


def _link(*, order_no: str, order_id: int, relation: str, claim_status: str = "",
          claim_type: str = "", refreshed_at: str = "",
          collected_at: str = "") -> ExternalOrderLink:
    external_id = f"PO-ADM-{_uid()}"
    snapshot = {
        "order": {"orderId": order_no, "ordererName": "이주문",
                  "ordererTel": "010-7300-0001"},
        "productOrder": {
            "productOrderId": external_id, "productName": "리라 TV 월플렉스",
            "totalPaymentAmount": 2_259_000,
            "claimStatus": claim_status or None,
            "claimType": claim_type or None,
        },
        "delivery": {"deliveryStatus": "DELIVERING",
                     "sendDate": "2026-09-09T16:50:25.446+09:00"},
    }
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id, sync_status="LINKED",
                             external_order_no=order_no, raw_snapshot=snapshot,
                             group_key=group_key_text(snapshot), relation=relation,
                             order_id=order_id,
                             triage_state={"claim_sync": {"refreshed_at": refreshed_at}}
                             if refreshed_at else None)
    if collected_at:
        # ``read_at`` 은 ``max(refreshed_at, created_at)`` 이라 수집 시각도 과거로
        # 못박아야 "언제 읽었나"가 시험된다(옛 정리 띠 테스트와 같은 규율).
        link.created_at = datetime.fromisoformat(collected_at)
    db_session.add(link)
    db_session.commit()
    return link


# ── 직권취소 인식 ────────────────────────────────────────────────────────────

def test_admin_cancel_is_a_finished_money_back_cancel(app):
    """``ADMIN_CANCEL_DONE`` 은 확정된 **취소**다 — 돈이 돌아간 종류로 센다."""
    claim = _claim("ADMIN_CANCEL_DONE", "ADMIN_CANCEL")

    assert claim["phase"] == "done"
    assert claim_kind(claim) == "CANCEL"
    assert is_money_back_claim(claim) is True
    assert blocks_irreversible(claim) is True


def test_admin_cancel_reads_without_claim_type(app):
    """``claimType`` 이 안 실려 와도 상태 이름만으로 같은 판정을 받는다(폴백)."""
    assert claim_kind(_claim("ADMIN_CANCEL_DONE")) == "CANCEL"


def test_admin_cancel_has_a_korean_label_and_locks(app):
    """배지에 영문 상수가 뜨지 않고, 주문 만들기도 막힌다(잠금 표와 라벨 표는 짝이다)."""
    assert CLAIM_STATUS_LABELS["ADMIN_CANCEL_DONE"] == "직권취소 완료"
    assert "ADMIN_CANCEL_DONE" in BLOCKING_CLAIM_STATUSES


def test_admin_canceled_origin_leaves_the_cleanup_strip(app):
    """직권취소된 옛 집은 정리 대기가 아니다 — 띠가 `반품 접수` 를 내밀면 안 된다."""
    order = _order()
    _link(order_no=f"N-ADM-{_uid()}", order_id=int(order.id), relation="NEW",
          claim_status="ADMIN_CANCEL_DONE", claim_type="ADMIN_CANCEL")
    _link(order_no=f"N-ADMREPAY-{_uid()}", order_id=int(order.id), relation="REPAY")

    rows = [row for row in pending_origin_cleanup(db_session)["rows"]
            if row["order_id"] == int(order.id)]

    assert rows == []


def test_alive_origin_still_counted(app):
    """**음성 대조군** — 클레임 없는 옛 집은 그대로 정리 대기다(가드가 띠를 비우면 안 된다)."""
    order = _order()
    _link(order_no=f"N-ALIVE-{_uid()}", order_id=int(order.id), relation="NEW")
    _link(order_no=f"N-ALIVEREPAY-{_uid()}", order_id=int(order.id), relation="REPAY")

    rows = [row for row in pending_origin_cleanup(db_session)["rows"]
            if row["order_id"] == int(order.id)]

    assert len(rows) == 1


# ── 시각 표기 ────────────────────────────────────────────────────────────────

def test_cleanup_strip_prints_kst_not_utc(app, client, workbench_on):
    """띠의 `마지막으로 읽은 때` 는 KST 다 — UTC 원문을 찍으면 9시간 전을 말한다."""
    _login(client)
    order = _order()
    _link(order_no=f"N-KST-{_uid()}", order_id=int(order.id), relation="NEW",
          refreshed_at="2026-09-22T04:18:51", collected_at="2026-09-20T01:00:00")
    _link(order_no=f"N-KSTREPAY-{_uid()}", order_id=int(order.id), relation="REPAY")

    body = client.get("/admin/naver-ingest/triage?tab=work").get_data(as_text=True)

    assert "2026-09-22 13:18" in body, "KST 로 편 시각이 화면에 없다"
    assert "2026-09-22 04:18" not in body, "UTC 원문이 그대로 찍혔다"


def test_cleanup_strip_row_carries_kst_text(app, client, workbench_on):
    """행 자체가 편 값을 들고 있다(템플릿이 슬라이싱으로 다시 만들지 않는다)."""
    from foms.web.admin.naver_ingest import _origin_cleanup_view

    _login(client)
    order = _order()
    _link(order_no=f"N-KST2-{_uid()}", order_id=int(order.id), relation="NEW",
          refreshed_at="2026-09-22T04:18:51", collected_at="2026-09-20T01:00:00")
    _link(order_no=f"N-KST2REPAY-{_uid()}", order_id=int(order.id), relation="REPAY")

    with client.application.test_request_context("/admin/naver-ingest/triage?tab=work"):
        view = _origin_cleanup_view(db_session)

    rows = [row for row in view["rows"] if row["order_id"] == int(order.id)]
    assert rows and rows[0]["read_at_text"] == "2026-09-22 13:18"


def test_watermark_view_carries_human_text(app):
    """워터마크도 사람이 읽는 KST 문자열을 함께 낸다(원문 키는 지문이라 그대로)."""
    from foms.services.integrations.naver_commerce import watermark as wm
    from foms.web.admin.naver_ingest import _watermark_view

    wm._write(db_session, {"last_run_at": "2026-09-22T04:18:51",
                           "last_success_to": "2026-09-22T04:17:51"})
    db_session.commit()

    view = _watermark_view(db_session)

    assert view["last_run_at"] == "2026-09-22T04:18:51", "원문 키는 지문 축이라 안 바뀐다"
    assert view["last_run_at_text"] == "2026-09-22 13:18"
    assert view["last_success_to_text"] == "2026-09-22 13:17"


def test_origin_refresh_all_returns_watch_material(app, client, workbench_on):
    """옛 주문 일괄 다시 읽기 응답에 진행을 따라갈 재료가 실린다(화면 자동 새로고침)."""
    _login(client)

    response = client.post("/admin/naver-ingest/origin-cleanup/refresh", json={})
    data = response.get_json() or {}

    assert response.status_code in (200, 503), response.get_data(as_text=True)
    if response.status_code == 200:
        assert "link_ids" in (data.get("data") or {})
        assert (data.get("data") or {}).get("since")
