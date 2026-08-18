"""NAVER-INGEST-01 T6: 수집 관리 화면 계약 테스트.

화면이 답해야 할 질문(지금 잘 도나 / 사람 손이 필요한 건이 있나 / 인증이 언제 만료되나)과,
**"지금 수집"이 web 에서 네이버를 직접 부르지 않는다**는 제약을 고정한다.
"""

from __future__ import annotations

from datetime import date, timedelta

from db import db_session
from foms.services.integrations.naver_commerce import app_expiry
from foms.services.integrations.naver_commerce import watermark as wm
from models import ExternalOrderLink, SecurityLog


def _link(external_id: str = "PO-1", status: str = "LINKED", **kwargs) -> ExternalOrderLink:
    kwargs.setdefault("raw_snapshot", {"productOrder": {"productOrderId": external_id}})
    link = ExternalOrderLink(channel="NAVER", external_id=external_id, sync_status=status,
                             **kwargs)
    db_session.add(link)
    db_session.commit()
    return link


def test_dashboard_requires_admin_role(app, client):
    """관리자 전용 — 비로그인은 화면을 못 본다(원본에 실번호·주소가 있다)."""
    response = client.get("/admin/naver-ingest")
    assert response.status_code in (301, 302, 401, 403)


def test_dashboard_lists_links_with_status_counts(auth_client):
    """이력과 상태별 건수가 함께 나와야 '봐야 할 게 있나'를 한눈에 답한다."""
    _link("PO-1", "LINKED")
    _link("PO-2", "PENDING_REVIEW", failure_reason="필수 값 누락: address")
    _link("PO-3", "FAILED", failure_reason="HTTP 500")

    body = auth_client.get("/admin/naver-ingest").get_data(as_text=True)
    assert "PO-1" in body and "PO-2" in body and "PO-3" in body
    assert "확인 필요" in body
    assert "필수 값 누락: address" in body


def test_history_shows_payment_and_claim(auth_client):
    """정산 확인용 결제·할인 칸과 취소 표식(T14-F). 원본에서 읽으니 과거분도 보인다."""
    _link("PO-PAY").raw_snapshot = {
        "order": {"orderId": "N-9", "paymentDate": "2026-08-14T16:27:12.156+09:00",
                  "paymentMeans": "신용카드"},
        "productOrder": {"productOrderId": "PO-PAY", "productName": "붙박이장",
                         "productDiscountAmount": 11000,
                         "claimStatus": "CANCEL_REQUEST"},
    }
    db_session.commit()

    body = auth_client.get("/admin/naver-ingest").get_data(as_text=True)
    assert "2026-08-14T16:27" in body
    assert "신용카드" in body
    assert "11,000" in body
    assert "취소 요청" in body


def test_status_filter_narrows_the_list(auth_client):
    """보류만 골라 보는 경로가 있어야 사람이 처리할 큐가 된다."""
    _link("PO-OK", "LINKED")
    _link("PO-HOLD", "PENDING_REVIEW")
    body = auth_client.get("/admin/naver-ingest?status=PENDING_REVIEW").get_data(as_text=True)
    assert "PO-HOLD" in body and "PO-OK" not in body


def test_unknown_status_filter_is_ignored_not_queried(auth_client):
    """임의 문자열이 그대로 쿼리에 들어가지 않는다(닫힌집합)."""
    _link("PO-1", "LINKED")
    body = auth_client.get("/admin/naver-ingest?status=DROP%20TABLE").get_data(as_text=True)
    assert "PO-1" in body


def test_history_groups_one_household_into_one_row(auth_client):
    """T14-H: 같은 네이버 주문번호는 이력에서도 한 줄로 묶인다."""
    _link("PO-G1", "COLLECTED", external_order_no="N-500",
          raw_snapshot={"order": {"orderId": "N-500"},
                        "productOrder": {"productOrderId": "PO-G1", "productName": "본품",
                                         "totalPaymentAmount": 900000}})
    _link("PO-G2", "COLLECTED", external_order_no="N-500",
          raw_snapshot={"order": {"orderId": "N-500"},
                        "productOrder": {"productOrderId": "PO-G2", "productName": "옵션",
                                         "totalPaymentAmount": 10000}})

    body = auth_client.get("/admin/naver-ingest").get_data(as_text=True)
    assert "외 1건" in body
    # 대표(금액 최대)가 제목이고, 구성은 펼침 영역에 들어간다.
    assert "본품" in body and 'id="naver-hist-' in body
    # 금액은 묶음 합계.
    assert "910,000" in body


def test_history_filter_keeps_sibling_rows_of_the_group(auth_client):
    """상태 필터는 묶음 선정에만 쓴다 — 문제 난 집의 다른 줄도 함께 보여야 맥락이 산다."""
    _link("PO-OK", "LINKED", external_order_no="N-501",
          raw_snapshot={"order": {"orderId": "N-501"},
                        "productOrder": {"productOrderId": "PO-OK", "productName": "정상 본품",
                                         "totalPaymentAmount": 500000}})
    _link("PO-BAD", "FAILED", external_order_no="N-501", failure_reason="HTTP 500",
          raw_snapshot={"order": {"orderId": "N-501"},
                        "productOrder": {"productOrderId": "PO-BAD", "productName": "실패 구성",
                                         "totalPaymentAmount": 1000}})

    body = auth_client.get("/admin/naver-ingest?status=FAILED").get_data(as_text=True)
    assert "PO-BAD" in body
    assert "PO-OK" in body          # 같은 집의 정상 줄도 보인다
    assert "HTTP 500" in body


def test_watermark_and_last_error_are_visible(auth_client):
    """실패했는데 화면이 조용하면 수집이 멈춘 걸 아무도 모른다."""
    wm.record_failure(db_session, error="naver down")
    db_session.commit()
    body = auth_client.get("/admin/naver-ingest").get_data(as_text=True)
    assert "naver down" in body
    assert "워터마크는 전진하지 않았습니다" in body


def test_expiry_warning_shows_when_close(auth_client):
    """만료가 임박하면 화면 상단에서 바로 보여야 한다."""
    app_expiry.set_expiry_date(db_session, date.today() + timedelta(days=3))
    db_session.commit()
    body = auth_client.get("/admin/naver-ingest").get_data(as_text=True)
    assert "D-3" in body and "갱신 필요" in body


def test_missing_expiry_is_called_out(auth_client):
    """만료일을 모르면 경고를 못 보낸다는 사실 자체를 화면이 말해야 한다."""
    body = auth_client.get("/admin/naver-ingest").get_data(as_text=True)
    assert "미등록" in body


def test_run_now_only_enqueues_and_never_calls_naver(auth_client, monkeypatch):
    """"지금 수집" 은 큐에 넣기만 한다 — web 에서 나가면 IP 가 달라 차단된다."""
    calls = []

    def _fake_enqueue(dry_run=False):
        calls.append(dry_run)
        return True

    monkeypatch.setattr("foms.web.admin.naver_ingest.enqueue_naver_order_sync", _fake_enqueue)

    def _explode(*args, **kwargs):  # 클라이언트가 만들어지면 즉시 실패시킨다
        raise AssertionError("web 프로세스에서 네이버 클라이언트를 만들면 안 된다")

    monkeypatch.setattr(
        "foms.services.integrations.naver_commerce.client.NaverCommerceClient.__init__", _explode
    )

    response = auth_client.post("/admin/naver-ingest/run", json={})
    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert calls == [False]


def test_run_now_reports_failure_when_queue_is_unavailable(auth_client, monkeypatch):
    """큐가 없으면 성공한 척하지 않는다(폴백으로 직접 호출하는 경로는 없다)."""
    monkeypatch.setattr("foms.web.admin.naver_ingest.enqueue_naver_order_sync",
                        lambda dry_run=False: False)
    response = auth_client.post("/admin/naver-ingest/run", json={})
    assert response.status_code == 503
    assert response.get_json()["success"] is False


def test_run_now_is_audited(auth_client, monkeypatch):
    """쓰기 라우트는 감사 원장에 남아야 한다(커버리지 게이트 계약)."""
    monkeypatch.setattr("foms.web.admin.naver_ingest.enqueue_naver_order_sync",
                        lambda dry_run=False: True)
    auth_client.post("/admin/naver-ingest/run", json={})
    actions = [row.action for row in db_session.query(SecurityLog).all()]
    assert "NAVER_INGEST_RUN_NOW" in actions


def test_snapshot_returns_raw_payload_and_logs_access(auth_client):
    """원본 열람은 관리자 전용이고, 개인정보라 열람 자체가 기록된다."""
    link = _link("PO-SNAP", "PENDING_REVIEW", failure_reason="필수 값 누락")
    response = auth_client.get(f"/admin/naver-ingest/{link.id}/snapshot")
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["snapshot"]["productOrder"]["productOrderId"] == "PO-SNAP"
    actions = [row.action for row in db_session.query(SecurityLog).all()]
    assert "NAVER_INGEST_SNAPSHOT_VIEW" in actions


def test_snapshot_404_for_unknown_link(auth_client):
    """없는 이력은 조용히 빈 값이 아니라 404 다."""
    response = auth_client.get("/admin/naver-ingest/999999/snapshot")
    assert response.status_code == 404
    assert response.get_json()["success"] is False


def test_snapshot_requires_admin(app, client):
    """비로그인은 원본(실번호·주소)에 접근할 수 없다."""
    link = _link("PO-PRIV")
    response = client.get(f"/admin/naver-ingest/{link.id}/snapshot")
    assert response.status_code in (301, 302, 401, 403)
