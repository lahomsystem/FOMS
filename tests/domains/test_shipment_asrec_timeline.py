"""출고 AS 일정추천 payload 의 AS 타임라인 HTML 주입 계약(T3).

추천 카드 본문은 legacy ``as_content`` 가 아니라 ``shipment.as_log`` 타임라인이 SSOT다.
렌더는 API 계층 ``_enrich_recommendations`` 가 담당하며, 실제 추천된 AS 만 배치 1회 조회 후
id 당 1회 렌더한다(prewarm 경로는 전부 스킵).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from werkzeug.security import generate_password_hash

import foms.api.shipment.recommendations as shipment_rec_api
from db import db_session
from foms.services.orders.as_log import build_as_log_entry
from models import Order, OrderScheduleDate, User

_TIMELINE_TEMPLATE = "shipment/partials/asrec_timeline_partial.html"


def _login_cs_staff(client, username: str) -> User:
    """STAFF + CS 계정으로 로그인(출고 추천 API 호출 권한)."""
    user = User(
        username=username,
        password=generate_password_hash("secret"),
        role="STAFF",
        team="CS",
        name="ASRec Timeline Tester",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _make_shipment_target(customer_name: str) -> int:
    """시공일이 있는 출고 대상 주문을 만들고 id 를 돌려준다."""
    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name=customer_name,
        phone="010-3333-4444",
        address="Seoul Gangnam",
        product="장",
        status="IN_CONSTRUCTION",
        is_erp_order=True,
        structured_data={
            "schedule": {"construction": {"date": today}},
            "shipment": {"construction_workers": ["A"]},
        },
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderScheduleDate(
            order_id=order.id, kind="construction", date=today, source="beta_schedule"
        )
    )
    db_session.commit()
    return order.id


def _make_as_order(shipment: dict[str, Any]) -> int:
    """``sd.shipment`` 를 지정한 AS 주문을 만들고 id 를 돌려준다."""
    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name="AS 추천 후보",
        phone="010-1111-2222",
        address="Seoul AS",
        product="AS",
        status="AS_RECEIVED",
        is_erp_order=True,
        structured_data={
            "workflow": {"stage": "CS"},
            "shipment": shipment,
            "as_info": [{"id": 3, "status": "OPEN"}],
        },
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _stub_pool(monkeypatch) -> None:
    """후보 풀·타깃 캐시를 무력화한다(지오코딩/경로 네트워크 차단 + 캐시 hit 오염 방지)."""
    monkeypatch.setattr(
        shipment_rec_api,
        "get_or_compute_candidate_pool",
        lambda *a, **k: (
            {"candidates": [], "link_as_to_shipment": {}, "pool_version": "test-pool"},
            {"candidate_pool_hit": True, "candidate_count": 0},
        ),
    )
    monkeypatch.setattr(shipment_rec_api, "get_cached_target", lambda _ck: None)
    monkeypatch.setattr(shipment_rec_api, "set_cached_target", lambda _ck, _row: None)


def _stub_recommend(monkeypatch, as_order_id: int) -> None:
    """모든 출고 타깃이 같은 AS 를 추천하도록 recommend 결과를 고정한다.

    rec 에 legacy ``as_content_*`` 를 실어 API 계층이 그 키를 떼는지도 함께 검증한다.
    """

    def fake_recommend(**kwargs):
        targets = []
        for tgt in kwargs.get("targets") or []:
            targets.append(
                {
                    "order_id": tgt["order_id"],
                    "customer_name": tgt.get("customer_name", ""),
                    "address": tgt.get("address", ""),
                    "target_date": tgt.get("target_date", ""),
                    "workers": [],
                    "message": "",
                    "recommendations": [
                        {
                            "as_order_id": as_order_id,
                            "customer_name": "AS 추천 후보",
                            "address": "Seoul AS",
                            "current_visit_date": "",
                            "as_info_id": 3,
                            "as_content_text": "LEGACY_TEXT_MARK",
                            "as_content_html": "<div>LEGACY_HTML_MARK</div>",
                        }
                    ],
                }
            )
        return {"targets": targets, "partial": False, "warnings": []}

    monkeypatch.setattr(
        shipment_rec_api, "recommend_nearby_schedules_for_targets", fake_recommend
    )


def _spy_renders(monkeypatch) -> list[str]:
    """render_template 호출 템플릿명을 순서대로 수집한다(실제 렌더는 유지)."""
    calls: list[str] = []
    real = shipment_rec_api.render_template

    def spy(template_name: str, **ctx):
        calls.append(template_name)
        return real(template_name, **ctx)

    monkeypatch.setattr(shipment_rec_api, "render_template", spy)
    return calls


def _post_recommendations(client, order_ids: list[int]) -> dict[str, Any]:
    response = client.post(
        "/api/erp/shipment/as-recommendations", json={"order_ids": order_ids}
    )
    assert response.status_code == 200, response.data
    payload = response.get_json()
    assert payload["success"] is True
    return payload


def test_asrec_payload_carries_readonly_as_timeline_html(client, monkeypatch) -> None:
    """as_log 기록이 타임라인 마크업으로 실리고, 편집 컨트롤은 렌더되지 않는다."""
    _login_cs_staff(client, "asrec-timeline-readonly")
    _stub_pool(monkeypatch)
    as_id = _make_as_order(
        {
            "as_log": [
                build_as_log_entry(
                    log_type="call", text="힌지 교체 완료 확인", by="테스터", by_id=1
                )
            ]
        }
    )
    _stub_recommend(monkeypatch, as_id)
    ship_id = _make_shipment_target("출고 타임라인 대상")

    rec = _post_recommendations(client, [ship_id])["targets"][0]["recommendations"][0]

    html = rec["as_timeline_html"]
    assert "as-tl-item" in html
    assert "힌지 교체 완료 확인" in html
    # 읽기 전용: 항목 수정/삭제 버튼과 quick-add 폼이 없어야 한다.
    assert "as-tl-item__edit" not in html
    assert "as-tl-item__delete" not in html
    assert "as-timeline__quick-add" not in html


def test_asrec_payload_drops_legacy_as_content_keys(client, monkeypatch) -> None:
    """타임라인 legacy 앵커가 본문을 이미 담으므로 as_content_* 키는 payload 에서 빠진다."""
    _login_cs_staff(client, "asrec-timeline-nokeys")
    _stub_pool(monkeypatch)
    as_id = _make_as_order(
        {"as_log": [build_as_log_entry(log_type="memo", text="메모", by="t", by_id=1)]}
    )
    _stub_recommend(monkeypatch, as_id)
    ship_id = _make_shipment_target("출고 키제거 대상")

    rec = _post_recommendations(client, [ship_id])["targets"][0]["recommendations"][0]

    assert "as_content_html" not in rec
    assert "as_content_text" not in rec
    assert "LEGACY_HTML_MARK" not in rec["as_timeline_html"]


def test_asrec_payload_renders_legacy_anchor_for_as_content_only(client, monkeypatch) -> None:
    """as_log 없이 legacy as_content 만 있는 AS 도 legacy 앵커로 본문이 나온다."""
    _login_cs_staff(client, "asrec-timeline-legacy")
    _stub_pool(monkeypatch)
    as_id = _make_as_order({"as_content": "<div>상부 레일 불량</div>"})
    _stub_recommend(monkeypatch, as_id)
    ship_id = _make_shipment_target("출고 legacy 대상")

    rec = _post_recommendations(client, [ship_id])["targets"][0]["recommendations"][0]

    html = rec["as_timeline_html"]
    assert "상부 레일 불량" in html
    assert "as-tl-item--legacy" in html


def test_asrec_timeline_rendered_once_for_shared_as(client, monkeypatch) -> None:
    """같은 AS 가 두 출고 타깃에 추천되면 렌더는 1회, 문자열은 재사용된다."""
    _login_cs_staff(client, "asrec-timeline-shared")
    _stub_pool(monkeypatch)
    as_id = _make_as_order(
        {"as_log": [build_as_log_entry(log_type="action", text="공용 기록", by="t", by_id=1)]}
    )
    _stub_recommend(monkeypatch, as_id)
    ship_a = _make_shipment_target("출고 공용 A")
    ship_b = _make_shipment_target("출고 공용 B")
    renders = _spy_renders(monkeypatch)

    targets = _post_recommendations(client, [ship_a, ship_b])["targets"]

    assert len(targets) == 2
    html_a = targets[0]["recommendations"][0]["as_timeline_html"]
    html_b = targets[1]["recommendations"][0]["as_timeline_html"]
    assert "공용 기록" in html_a
    assert html_a == html_b
    assert renders.count(_TIMELINE_TEMPLATE) == 1


def test_asrec_timeline_empty_for_missing_as_order(client, monkeypatch) -> None:
    """조회 실패(삭제/미존재) AS 는 빈 문자열이며 렌더를 시도하지 않는다."""
    _login_cs_staff(client, "asrec-timeline-missing")
    _stub_pool(monkeypatch)
    _stub_recommend(monkeypatch, 999_000_111)
    ship_id = _make_shipment_target("출고 미존재 AS")
    renders = _spy_renders(monkeypatch)

    rec = _post_recommendations(client, [ship_id])["targets"][0]["recommendations"][0]

    assert rec["as_timeline_html"] == ""
    assert renders.count(_TIMELINE_TEMPLATE) == 0


def test_asrec_prewarm_skips_timeline_render(client, monkeypatch) -> None:
    """prewarm(return_targets=False) 은 타임라인 조회·렌더를 전부 건너뛴다."""
    _login_cs_staff(client, "asrec-timeline-prewarm")
    _stub_pool(monkeypatch)
    as_id = _make_as_order(
        {"as_log": [build_as_log_entry(log_type="memo", text="prewarm", by="t", by_id=1)]}
    )
    _stub_recommend(monkeypatch, as_id)
    ship_id = _make_shipment_target("출고 prewarm 대상")
    renders = _spy_renders(monkeypatch)

    response = client.post(
        "/api/erp/shipment/as-recommendations/prewarm", json={"order_ids": [ship_id]}
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["warmed_targets"] == 1
    assert "targets" not in payload
    assert renders.count(_TIMELINE_TEMPLATE) == 0
