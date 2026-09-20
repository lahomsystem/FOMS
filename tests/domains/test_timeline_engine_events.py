"""타임라인 P2 — 엔진 전이 이벤트·강제 단계 변경을 8단계 도달 시각으로 읽는다(2026-09-20).

예전 `_stage_reach_events` 는 STAGE_CHANGED 만 읽어서, 엔진이 낸 MEASUREMENT_COMPLETED
같은 전이 이벤트는 타임라인에 시각이 붙지 않았다. 또 미상 `to` 값이 RECEIVED 로 접히는
함정이 있었다. 여기서는 SimpleNamespace 이벤트로 build_order_timeline 을 직접 부른다.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

from foms.services.order_event_display import (
    format_timeline_meta,
    generate_change_description,
    translate_event_type_to_korean,
)
from foms.services.order_timeline_v3 import build_order_timeline

_BASE = datetime.datetime(2026, 6, 1, 9, 0, 0)
_USERS = {7: "김실측", 9: "박관리"}


def _order(stage: str = "DRAWING") -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        status=stage,
        received_date="2026-06-01",
        customer_name="타임라인고객",
        structured_data={"workflow": {"stage": stage}},
    )


def _ev(event_type: str, payload: dict, *, days: int = 0, by: int = 7) -> SimpleNamespace:
    return SimpleNamespace(
        event_type=event_type,
        payload=payload,
        created_at=_BASE + datetime.timedelta(days=days),
        created_by_user_id=by,
    )


def _stage(result: dict, code: str) -> dict:
    return next(s for s in result["stages"] if s["code"] == code)


def test_엔진_실측완료_이벤트만_있어도_도면_도달_시각이_채워진다() -> None:
    events = [
        _ev(
            "MEASUREMENT_COMPLETED",
            {"command": "COMPLETE_MEASUREMENT", "axis": "MAIN", "from": "MEASURE", "to": "DRAWING"},
        )
    ]
    result = build_order_timeline(_order("DRAWING"), events, _USERS)

    drawing = _stage(result, "DRAWING")
    assert drawing["when"] is not None
    assert drawing["who"] == "김실측"


def test_강제_단계_변경_이벤트는_그_단계_도달로_읽고_담당은_users_map_이름이다() -> None:
    events = [
        _ev(
            "STAGE_OVERRIDE",
            {"from": "DRAWING", "to": "MEASURE", "mode": "regress", "reason": "원상 복구", "manual": True},
            by=9,
        )
    ]
    result = build_order_timeline(_order("MEASURE"), events, _USERS)

    measure = _stage(result, "MEASURE")
    assert measure["when"] is not None
    assert measure["who"] == "박관리"


def test_같은_단계는_최초_도달_이벤트를_유지한다() -> None:
    events = [
        _ev("STAGE_CHANGED", {"from": "RECEIVED", "to": "MEASURE", "manual": True}, days=0, by=7),
        _ev("STAGE_OVERRIDE", {"from": "DRAWING", "to": "MEASURE", "mode": "regress"}, days=4, by=9),
    ]
    result = build_order_timeline(_order("MEASURE"), events, _USERS)

    measure = _stage(result, "MEASURE")
    assert measure["when"].startswith("2026-06-01")
    assert measure["who"] == "김실측"


def test_대조군_run_only_생산시작_이벤트는_axis_가_없어_생산_도달로_읽지_않는다() -> None:
    run_only = _ev(
        "PRODUCTION_STARTED",
        {"domain": "PRODUCTION", "from": "PRODUCTION", "to": "PRODUCTION", "run_started": True},
        days=3,
    )
    result = build_order_timeline(_order("PRODUCTION"), [run_only], _USERS)
    assert _stage(result, "PRODUCTION")["when"] is None

    confirmed = _ev(
        "CUSTOMER_CONFIRMED",
        {"command": "CONFIRM_CUSTOMER", "axis": "MAIN", "from": "CONFIRM", "to": "PRODUCTION"},
        days=1,
        by=9,
    )
    result = build_order_timeline(_order("PRODUCTION"), [confirmed, run_only], _USERS)
    production = _stage(result, "PRODUCTION")
    assert production["when"].startswith("2026-06-02")
    assert production["who"] == "박관리"


def test_대조군_axis_MAIN_이라도_to_가_미상이거나_없으면_어느_단계도_채우지_않는다() -> None:
    events = [
        _ev("SOMETHING", {"axis": "MAIN", "from": "MEASURE", "to": "FOO"}),
        _ev("SOMETHING_ELSE", {"axis": "MAIN", "from": "MEASURE"}),
        _ev("STAGE_OVERRIDE", {"from": "MEASURE"}),
    ]
    result = build_order_timeline(_order("MEASURE"), events, _USERS)

    # 예전엔 미상 값이 RECEIVED 로 접혀 접수 칸에 이벤트 시각이 붙었다 — 지금은 접수일 폴백만 남는다.
    for stage in result["stages"]:
        assert stage["who"] is None
        if stage["code"] == "RECEIVED":
            assert stage["when"] == "2026-06-01"
        else:
            assert stage["when"] is None


def test_라벨_6종은_계약_문자열이고_죽은_키도_남아_있다() -> None:
    assert translate_event_type_to_korean("STAGE_OVERRIDE") == "단계 강제 변경"
    assert translate_event_type_to_korean("PRODUCTION_REWORK_STARTED") == "수정 제작 시작"
    assert translate_event_type_to_korean("PRODUCTION_COMPLETE_REVERTED") == "제작 완료 취소"
    assert translate_event_type_to_korean("PRODUCTION_HOLD_TOGGLED") == "생산 보류 변경"
    assert translate_event_type_to_korean("ORDER_HELD") == "주문 보류"
    assert translate_event_type_to_korean("CONSTRUCTION_EVIDENCE_ADDED") == "시공 증빙 등록"
    assert translate_event_type_to_korean("ORDER_HOLD_RELEASED") == "주문 보류 해제"
    assert translate_event_type_to_korean("STAGE_MANUAL_OVERRIDE") == "단계 수동 변경"


def test_강제_단계_변경_메타는_한글_단계명만_보인다() -> None:
    meta = format_timeline_meta(
        "STAGE_OVERRIDE",
        {"from": "DRAWING", "to": "MEASURE"},
        actor_name="박관리",
        created_at=datetime.datetime(2026, 6, 2, 10, 30),
    )
    assert "도면" in meta
    assert "실측" in meta
    assert "DRAWING" not in meta
    assert "MEASURE" not in meta


def test_강제_단계_변경_설명_문장에_강제_변경과_사유가_들어간다() -> None:
    with_reason = generate_change_description(
        "STAGE_OVERRIDE", "진행 단계", "도면", "실측", {"from": "DRAWING", "to": "MEASURE", "reason": "원상 복구"}
    )
    assert "강제 변경" in with_reason
    assert "'도면'에서 '실측'로" in with_reason
    assert "(사유: 원상 복구)" in with_reason

    without_reason = generate_change_description(
        "STAGE_OVERRIDE", "진행 단계", "도면", "실측", {"from": "DRAWING", "to": "MEASURE"}
    )
    assert "강제 변경" in without_reason
    assert "사유" not in without_reason
