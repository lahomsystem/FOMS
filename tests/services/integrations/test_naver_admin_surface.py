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


#: 행 배지 식별자. 필터 버튼과 문구가 같아 title 로 가른다.
PENDING_BADGE_TITLE = "네이버 판매자센터에서 발주확인이 아직 안 된 상품주문이 있습니다"


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


def test_status_counts_are_group_units_not_link_rows(auth_client):
    """필터 숫자는 표 총계와 같은 **묶음(집)** 단위여야 한다.

    링크 행으로 세면 "전체 2집 · 수집됨 4" 처럼 부분이 전체보다 커 보인다
    (2026-08-19 스테이징 실화면: 전체 36 · 수집됨 102).
    """
    for idx in range(3):
        _link(f"PO-G1-{idx}", "COLLECTED", external_order_no="N-G1")
    _link("PO-G2", "COLLECTED", external_order_no="N-G2")

    body = auth_client.get("/admin/naver-ingest").get_data(as_text=True)
    assert "수집됨(주문 전) 2주문" in body
    assert "전체 2주문" in body


def test_cancelled_group_cannot_be_promoted_from_history(auth_client):
    """취소·반품 건은 서버가 400 으로 막는다 — 목록 버튼도 같이 잠근다(헛클릭 제거)."""
    link = _link("PO-CLAIM", "COLLECTED", external_order_no="N-CLAIM")
    link.raw_snapshot = {
        "order": {"orderId": "N-CLAIM"},
        "productOrder": {"productOrderId": "PO-CLAIM", "productName": "붙박이장",
                         "claimStatus": "CANCEL_DONE"},
    }
    db_session.commit()

    body = auth_client.get("/admin/naver-ingest").get_data(as_text=True)
    assert "취소·반품 진행 중 — 주문을 만들 수 없습니다." in body
    assert "disabled" in body.split('naver-create-order-btn')[1].split('</button>')[0]


def test_normal_collected_group_keeps_create_button_enabled(auth_client):
    """정상 수집분은 그대로 만들 수 있어야 한다(차단이 과녁을 넘지 않는다)."""
    _link("PO-OKBTN", "COLLECTED", external_order_no="N-OKBTN")

    body = auth_client.get("/admin/naver-ingest").get_data(as_text=True)
    button = body.split('naver-create-order-btn')[1].split('</button>')[0]
    assert "disabled" not in button
    assert "취소·반품 진행 중" not in body


def test_place_order_status_shows_pending_badge(auth_client):
    """발주확인 전인 집은 목록에서 바로 알아볼 수 있어야 한다 (T16-A).

    ``placeOrderStatus`` 는 수집 원본에 이미 들어온다 — 네이버에 아무것도 쓰지 않고 표시한다.
    """
    link = _link("PO-PLACE", "COLLECTED", external_order_no="N-PLACE")
    link.raw_snapshot = {
        "order": {"orderId": "N-PLACE"},
        "productOrder": {"productOrderId": "PO-PLACE", "productName": "붙박이장",
                         "placeOrderStatus": "NOT_YET",
                         "shippingDueDate": "2026-09-08T23:59:59.000+09:00"},
    }
    db_session.commit()

    body = auth_client.get("/admin/naver-ingest").get_data(as_text=True)
    # 필터 버튼에도 같은 문구가 있으므로 **행 배지**(title 로 구분)를 본다.
    assert PENDING_BADGE_TITLE in body


def test_confirmed_place_order_has_no_pending_badge(auth_client):
    """발주확인이 끝난 집에는 표식이 없어야 한다(과표시 금지)."""
    link = _link("PO-PLACE-OK", "COLLECTED", external_order_no="N-PLACE-OK")
    link.raw_snapshot = {
        "order": {"orderId": "N-PLACE-OK"},
        "productOrder": {"productOrderId": "PO-PLACE-OK", "productName": "붙박이장",
                         "placeOrderStatus": "OK"},
    }
    db_session.commit()

    body = auth_client.get("/admin/naver-ingest").get_data(as_text=True)
    assert PENDING_BADGE_TITLE not in body


def test_place_pending_filter_narrows_to_unconfirmed_groups(auth_client):
    """'발주확인 전' 필터는 컬럼으로 건다 — JSONB 스캔 금지(T16-B)."""
    done = _link("PO-PF-OK", "COLLECTED", external_order_no="N-PF-OK",
                 place_order_status="OK")
    done.raw_snapshot = {"order": {"orderId": "N-PF-OK"},
                         "productOrder": {"productOrderId": "PO-PF-OK",
                                          "productName": "확인된집",
                                          "placeOrderStatus": "OK"}}
    todo = _link("PO-PF-NY", "COLLECTED", external_order_no="N-PF-NY",
                 place_order_status="NOT_YET")
    todo.raw_snapshot = {"order": {"orderId": "N-PF-NY"},
                         "productOrder": {"productOrderId": "PO-PF-NY",
                                          "productName": "아직인집",
                                          "placeOrderStatus": "NOT_YET"}}
    db_session.commit()

    body = auth_client.get("/admin/naver-ingest?place=PENDING").get_data(as_text=True)
    assert "PO-PF-NY" in body
    assert "PO-PF-OK" not in body


def test_place_pending_filter_counts_unknown_as_pending(auth_client):
    """발주 상태를 모르는(NULL) 건은 '아직'으로 센다 — 놓치는 쪽보다 낫다."""
    _link("PO-PF-NULL", "COLLECTED", external_order_no="N-PF-NULL")
    db_session.commit()

    body = auth_client.get("/admin/naver-ingest?place=PENDING").get_data(as_text=True)
    assert "PO-PF-NULL" in body


def test_place_filter_combines_with_status_filter(auth_client):
    """두 축은 겹쳐 걸 수 있어야 한다(수집 상태 × 발주 상태)."""
    _link("PO-PF-MIX", "PENDING_REVIEW", external_order_no="N-PF-MIX",
          place_order_status="NOT_YET")
    _link("PO-PF-OTHER", "COLLECTED", external_order_no="N-PF-OTHER",
          place_order_status="NOT_YET")
    db_session.commit()

    body = auth_client.get(
        "/admin/naver-ingest?status=PENDING_REVIEW&place=PENDING").get_data(as_text=True)
    assert "PO-PF-MIX" in body
    assert "PO-PF-OTHER" not in body


def test_relation_defaults_to_new(auth_client):
    """관계 축 기본값은 NEW — 기존 흐름이 그대로 새 주문 경로를 탄다."""
    link = _link("PO-REL", "COLLECTED", external_order_no="N-REL")
    db_session.refresh(link)
    assert link.relation == "NEW"


def test_run_result_alert_is_not_auto_dismissed(auth_client):
    """수집 실행 결과 문구는 5초 뒤에 사라지면 안 된다(03 감사 결함 #5).

    전역 스크립트가 ``.alert`` 을 5초 뒤 제거한다. 실패 사유가 그렇게 증발하면 사람이
    무엇이 왜 실패했는지 영영 못 읽는다 — 실행 결과 칸은 opt-out 해야 한다.
    triage 화면은 ``ecc484cb`` 에서 이미 처리됐고, 이력 화면이 남아 있었다.
    """
    body = auth_client.get("/admin/naver-ingest").get_data(as_text=True)

    marker = 'id="naver-run-result"'
    assert marker in body
    tag = body[body.index(marker) - 60:body.index(marker) + 200]
    assert "data-foms-no-autodismiss" in tag, tag


def test_pagination_links_keep_place_filter(auth_client, monkeypatch):
    """페이지를 넘겨도 걸어 둔 필터가 풀리면 안 된다(03 감사 결함 #8).

    라우트는 ``place`` 를 읽는데(`naver_ingest.py:364`) 페이지 링크는 ``status`` 만
    넘겼다. '발주확인 전'으로 거른 뒤 2페이지로 가면 필터 없는 전체 목록이 나온다.
    """
    from foms.web.admin import naver_ingest as mod

    monkeypatch.setattr(mod, "PAGE_SIZE", 1, raising=False)
    for idx in range(3):
        _link(f"PO-PG-{idx}", "COLLECTED", external_order_no=f"N-PG-{idx}",
              place_order_status="NOT_YET")
    db_session.commit()

    body = auth_client.get("/admin/naver-ingest?place=PENDING").get_data(as_text=True)
    nav = body[body.index("pagination"):]
    nav = nav[:nav.index("</nav>")]
    assert "page=2" in nav, nav
    assert "place=PENDING" in nav, nav


def _split_shipment_link(external_id: str, *, order_no: str, address: str,
                         tel: str = "010-1111-2222") -> ExternalOrderLink:
    """같은 네이버 주문번호인데 배송지가 다른 링크(분할배송).

    수집 파이프라인이 만드는 모양 그대로 — ``group_key`` 컬럼까지 채운다
    (수집이 실제로 그 컬럼을 채우는지는 `test_naver_ingest` 쪽에서 따로 고정한다).
    """
    from foms.services.integrations.naver_commerce.mapping import group_key_text

    link = _link(external_id, "COLLECTED", external_order_no=order_no)
    link.raw_snapshot = {
        "order": {"orderId": order_no},
        "productOrder": {
            "productOrderId": external_id, "productName": "붙박이장",
            "shippingAddress": {"name": "이수취", "tel1": tel,
                                "baseAddress": address, "detailedAddress": "101호"},
        },
    }
    link.group_key = group_key_text(link.raw_snapshot)
    db_session.commit()
    return link


def test_history_falls_back_to_order_no_when_group_key_missing(auth_client):
    """묶음키 컬럼이 비어 있어도(옛 행·backfill 전) 화면은 예전처럼 동작한다.

    폴백이 없으면 링크마다 ``link:<id>`` 로 흩어져 집 수가 폭증한다.
    """
    _link("PO-NOGK-A", "COLLECTED", external_order_no="N-NOGK")
    _link("PO-NOGK-B", "COLLECTED", external_order_no="N-NOGK")

    body = auth_client.get("/admin/naver-ingest").get_data(as_text=True)
    assert "전체 1주문" in body


def test_history_splits_by_address_like_the_triage_queue(auth_client):
    """이력과 확인 큐의 '집' 정의가 같아야 한다(03 감사 결함 #1).

    확인 큐는 (주문번호·수취인 전화·주소)로 가른다 — 분할배송에서 두 집을 하나로 합치면
    남의 주소로 시공을 나가는 사고가 된다. 이력은 주문번호만 봐서 같은 데이터를
    1집으로 셌고, 두 화면 숫자가 영구히 어긋났다(45집 vs 43집).
    """
    _split_shipment_link("PO-SPLIT-A", order_no="N-SPLIT", address="서울 강남구 1")
    _split_shipment_link("PO-SPLIT-B", order_no="N-SPLIT", address="부산 해운대구 9")

    body = auth_client.get("/admin/naver-ingest").get_data(as_text=True)
    assert "전체 2주문" in body, "배송지가 다르면 이력에서도 두 집이어야 한다"


def test_history_still_groups_same_address_into_one(auth_client):
    """같은 집은 여전히 한 집이다 — 가르는 규칙이 과녁을 넘지 않는다."""
    _split_shipment_link("PO-SAME-A", order_no="N-SAME", address="서울 강남구 1")
    _split_shipment_link("PO-SAME-B", order_no="N-SAME", address="서울 강남구 1")

    body = auth_client.get("/admin/naver-ingest").get_data(as_text=True)
    assert "전체 1주문" in body
