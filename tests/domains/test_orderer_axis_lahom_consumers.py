"""수집 주문이 라홈 경로를 타는지 고정 (ORDERER-AXIS-01 T6).

`parties.orderer.name` 에 사람 이름이 들어 있던 동안 수집 주문은 발주사 판정이 전부
'라홈 아님'으로 떨어졌다 — 알림톡이 하우드 프로필로 나가고, 도면에 하우드 로고가 찍히고,
퀘스트 CS 팀이 안 붙고, 실측일을 지워도 접수로 돌아오지 않았다.

이 파일은 **수집 매핑이 만든 structured_data 그대로**를 각 소비자에 먹여 라홈 경로를
확인한다. 매핑이 발주사 자리를 다시 사람으로 되돌리면 여기서 red 가 난다.
"""
from __future__ import annotations

from foms.api.erp_orders_structured import _is_lahom_like_orderer
from foms.services.drawing_wizard_defaults import _resolve_logo
from foms.services.integrations.naver_commerce.mapping import build_structured_data
from foms.services.kakao_alimtalk import resolve_brand


def _ingested_sd() -> dict:
    """네이버 수집 매핑이 만드는 structured_data (값은 가상)."""
    return build_structured_data({
        "order": {
            "orderId": "N-1", "ordererName": "김주문", "ordererTel": "010-6279-1403",
            "orderDate": "2026-08-14T10:00:00.000+09:00",
        },
        "productOrder": {
            "productOrderId": "PO-1", "productOrderStatus": "PAYED",
            "productName": "붙박이장", "quantity": 1, "totalPaymentAmount": 100000,
            "shippingAddress": {
                "name": "이수취", "tel1": "010-3333-4444",
                "baseAddress": "서울 강남구 1", "detailedAddress": "101호",
            },
        },
    })


def _orderer_name(sd: dict) -> str:
    return sd["parties"]["orderer"]["name"]


def test_ingested_order_is_lahom_not_person():
    """수집 주문의 발주사는 라홈이고, 사람은 buyer 로 간다."""
    sd = _ingested_sd()
    assert _orderer_name(sd) == "라홈"
    assert sd["parties"]["buyer"] == {"name": "김주문", "phone": "010-6279-1403"}


def test_alimtalk_brand_is_lahom():
    """알림톡 발신 브랜드 프로필이 라홈으로 잡힌다(하우드로 나가면 안 된다)."""
    assert resolve_brand(_ingested_sd()) == "LAHOM"


def test_drawing_logo_is_lahom():
    """도면 양식 로고가 라홈이다."""
    assert _resolve_logo(_orderer_name(_ingested_sd())) == "lahom"


def test_quest_cs_override_applies():
    """실측 단계 퀘스트가 CS 팀 override 를 받는다."""
    from foms.services.erp_quest_display import _apply_lahom_cs_override

    quest: dict = {"owner_team": "SALES", "team_approvals": {}}
    required = _apply_lahom_cs_override(quest, _ingested_sd(), "실측")

    assert quest["owner_team"] == "CS"
    assert required == ["CS"]


def test_measure_date_clear_returns_to_received():
    """실측일을 지우면 접수로 되돌아오는 대상(라홈)으로 판정된다."""
    assert _is_lahom_like_orderer(_ingested_sd()) is True
