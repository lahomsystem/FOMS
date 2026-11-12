"""능력 질문(설계서 2026-11-12 온톨로지 부록 A)이 더한 속성 틀 칸 — 공정 단계 일정 · 정책 갈래 · 권역 · 옵션 갈래.

S05 · S06(걸리는 날 · 요일 · 시간대) · P04 · P05 · P08 · A03(결제 · 환불 · AS 보증) · D01(권역) · S10 · S11 · O12 · D02(서비스).
틀만 본다(합성 값 · DB 없음).
"""

from __future__ import annotations

from foms.services.brain.schemas import (
    CHOICE_LABELS, OPTION_KINDS, POLICY_KINDS, TYPE_SCHEMAS, WEEKDAYS, brain_payload_keys, schema_problems,
)

DOC = {"doc_id": "p", "approved_by": "합성", "approved_at": "2026-10-20"}
STEP = {"erp_stage": "MEASURE", "step_order": 2}


def _shape(item_type, **vals):
    return schema_problems({"status": "active", "text": "합성", **vals}, item_type)


def test_process_step_carries_schedule_answers():
    full = {**STEP, "days_to_next": 14, "duration_hours": 2.5, "weekdays": ["mon", "sat"],
            "time_windows": ["09-12", "13-18"], "closed_days": ["공휴일", "명절"]}
    assert _shape("process_step", payload=full) == []
    assert _shape("process_step", payload=STEP) == []  # 새 칸은 다 고를 칸 — 옛 항목은 그대로 통과
    for bad in ({"days_to_next": 400}, {"duration_hours": 30}, {"weekdays": ["holiday"]},
                {"time_windows": ["x" * 21]}, {"closed_days": ["a"] * 11}):
        key = next(iter(bad))
        assert any(p.startswith(f"payload.{key}") for p in _shape("process_step", payload={**STEP, **bad})), bad


def test_policy_kinds_cover_payment_refund_and_warranty_with_regions():
    for kind in ("payment", "refund", "as_warranty", "shipping"):
        assert _shape("policy", checked_at="2026-10-20", payload={**DOC, "policy_kind": kind}) == []
    assert _shape("policy", checked_at="2026-10-20",
                  payload={**DOC, "policy_kind": "shipping", "regions": ["합성 권역 가", "합성 권역 나"]}) == []
    assert any(p.startswith("payload.regions") for p in _shape(
        "policy", checked_at="2026-10-20", payload={**DOC, "regions": ["x" * 31]}))
    assert _shape("price_rule", checked_at="2026-10-20", payload={**DOC, "regions": ["합성 권역"]}) == []


def test_option_kind_marks_services():
    base = {"price_kind": "extra", "unit": "개", "category": "합성 묶음"}
    assert _shape("option", payload={**base, "option_kind": "service"}) == []
    assert any(p.startswith("payload.option_kind") for p in _shape("option", payload={**base, "option_kind": "labor"}))


def test_new_choices_have_korean_labels_and_stay_out_of_the_cs_document():
    assert set(POLICY_KINDS) <= set(CHOICE_LABELS["payload.policy_kind"])
    assert set(OPTION_KINDS) == set(CHOICE_LABELS["payload.option_kind"])
    assert set(WEEKDAYS) == set(CHOICE_LABELS["payload.weekdays"])
    paths = {prop.path for prop in TYPE_SCHEMAS["process_step"]}
    assert {"payload.days_to_next", "payload.weekdays", "payload.time_windows"} <= paths
    # 정책 · 가격 규칙의 권역은 brain 만의 칸 — 상담 지식 문서로는 나가지 않는다
    assert "regions" in brain_payload_keys("policy") and "regions" in brain_payload_keys("price_rule")
