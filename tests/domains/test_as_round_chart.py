"""AS 회차 차트(ver7) 뷰 빌더·렌더 계약 테스트 (T15b).

- build_as_round_chart_view: 회차 그룹핑(최신 위)·슬롯 판정·상태 카드 흡수·판정 규약
- system 문구 접두어 핀: 분류 기준이 생성 지점 리터럴과 어긋나면 red
- render_as_round_chart: 기존 as-dashboard.js 위임 계약 클래스 유지
"""

import datetime
from pathlib import Path

from flask import render_template_string

from foms.services.orders.as_log import (
    append_client_log,
    append_system_log,
    append_verdict_log,
)
from foms.services.orders.as_round_chart import build_as_round_chart_view

_ROOT = Path(__file__).resolve().parents[2]
_TODAY = datetime.date(2026, 8, 6)


def _base_sd() -> dict:
    return {"shipment": {}, "schedule": {}}


def _scenario_sd() -> dict:
    """목업 v7 시나리오: 1차(방안→통화→방문확정→미결) → 2차(방안·자재) 진행 중."""
    sd = _base_sd()
    sd["shipment"]["as_content"] = "<div>문 경첩 이격/소음, 부품 교체 요청</div>"
    append_client_log(sd, log_type="reception", text="문 경첩 이격/소음", by="김", by_id=1)
    append_client_log(sd, log_type="plan", text="경첩 조정으로 1차 시도", by="이시영", by_id=2)
    append_client_log(sd, log_type="call", text="7/30 방문 확정 통화", by="이시영", by_id=2)
    append_system_log(sd, text="방문일 확정: 2026-07-30")
    append_system_log(sd, text="가능시간: 주말 · 오후")
    append_system_log(sd, text="유상 확정: 부품비")
    append_system_log(sd, text="AS 접수됨")
    append_verdict_log(sd, verdict="unresolved", text="부품 자체 불량, 교체 필요", by="이시영", by_id=2)
    append_client_log(sd, log_type="plan", text="경첩 부품 교체", by="이시영", by_id=2)
    append_client_log(sd, log_type="material", text="18T 상부 선반 입고", by="이시영", by_id=2)
    return sd


def test_empty_sd_opens_round_one():
    view = build_as_round_chart_view({}, today=_TODAY)
    assert view["current_round"] == 1
    assert len(view["rounds"]) == 1
    r = view["rounds"][0]
    assert r["no"] == 1 and r["open"] is True and r["entries"] == []
    # 첫 미완 슬롯(방안)이 next, 나머지 wait
    assert [s["state"] for s in r["slots"]] == ["next", "wait", "wait", "wait", "wait", "wait"]
    assert view["count"] == 0 and view["verdict_prompt"] is False


def test_scenario_rounds_newest_first_with_verdict_and_slots():
    sd = _scenario_sd()
    view = build_as_round_chart_view(sd, today=_TODAY)
    assert view["current_round"] == 2
    assert [r["no"] for r in view["rounds"]] == [2, 1]

    open_r, closed_r = view["rounds"]
    assert open_r["open"] is True and closed_r["open"] is False
    # 2차: 방안·자재 done, 일정(회차 확정 로그 없음+현재 방문일은 1차 몫 과거) next 아님 —
    # 순서상 일정이 첫 미완이라 next, 컨택/방문/판정 wait
    states = {s["key"]: s["state"] for s in open_r["slots"]}
    assert states["plan"] == "done" and states["material"] == "done"
    assert states["schedule"] == "next"
    assert states["visit"] == "wait" and states["verdict"] == "wait"

    # 1차: 미결 판정 + 요약(첫 방안) + 그 회차 방문일 M/D
    assert closed_r["verdict"]["verdict"] == "unresolved"
    assert closed_r["verdict"]["verdict_label"] == "미결"
    assert "부품 자체 불량" in closed_r["verdict"]["reason_preview"]
    assert closed_r["summary"].startswith("방안: 경첩 조정")
    assert closed_r["visit_md"] == "7/30" and "방문 7/30" in closed_r["summary"]
    # 회차 표는 사람 기록만(시스템은 상태 카드로 흡수)
    assert [e["type"] for e in closed_r["entries"]] == ["call", "plan"]


def test_state_card_absorbs_system_by_prefix():
    view = build_as_round_chart_view(_scenario_sd(), today=_TODAY)
    sc = view["state_card"]
    assert [h["text"] for h in sc["visit"]["history"]] == ["방문일 확정: 2026-07-30"]
    assert [h["text"] for h in sc["availability"]["history"]] == ["가능시간: 주말 · 오후"]
    assert [h["text"] for h in sc["billing"]["history"]] == ["유상 확정: 부품비"]
    assert [h["text"] for h in sc["other_history"]] == ["AS 접수됨"]
    # 현재값: 방문일 지남 라벨(빨강 판정) — 방문일 필드는 sd schedule SSOT
    sd = _scenario_sd()
    sd["schedule"] = {"as_visit": {"date": "2026-07-30", "time": ""}}
    view2 = build_as_round_chart_view(sd, today=_TODAY)
    assert view2["state_card"]["visit"]["md"] == "7/30"
    assert view2["state_card"]["visit"]["overdue"] is True
    assert view2["state_card"]["visit"]["dday_label"] == "7일 지남"
    assert view2["symptom_preview"].startswith("문 경첩 이격/소음")


def test_reception_anchor_and_count():
    view = build_as_round_chart_view(_scenario_sd(), today=_TODAY)
    assert view["reception"]["type"] == "reception"
    # count = 사람 기록(방안2·통화·자재·판정=5) + 접수 1 + legacy 1
    # (as_content 가 최초 append 때 legacy 로 영구화되는 규약 — 셀 배지 수와 동일 기준)
    assert len(view["legacy"]) == 1
    assert view["count"] == 7


def test_lazy_legacy_from_as_content_non_destructive():
    """as_log 미생성 주문: as_content 가 legacy 로 lazy 표시되고 sd 는 불변(타임라인 뷰 계약 동일)."""
    sd = {"shipment": {"as_content": "<div>옛 기록</div>"}}
    view = build_as_round_chart_view(sd, today=_TODAY)
    assert [e["id"] for e in view["legacy"]] == ["al_legacy_as_content"]
    assert "as_log" not in sd["shipment"]  # 영구화는 최초 append 시점
    assert view["count"] == 1


def test_deleted_entries_hidden():
    sd = _scenario_sd()
    sd["shipment"]["as_log"][-1]["deleted"] = True  # 자재 삭제
    view = build_as_round_chart_view(sd, today=_TODAY)
    open_r = view["rounds"][0]
    assert all(e["type"] != "material" for e in open_r["entries"])
    assert {s["key"]: s["state"] for s in open_r["slots"]}["material"] != "done"


def test_multiple_verdicts_same_round_last_wins():
    sd = _base_sd()
    append_verdict_log(sd, verdict="unresolved", text="오판정", by="김", by_id=1)
    # 미결로 2차가 열렸으나, 1차 재판정(정정)은 round 스탬프가 달라 1차가 아닌
    # **현재 회차(2차)** 판정이 된다 — 규약: 정정은 새 판정 append. 여기서는 같은 회차
    # 재판정을 시뮬레이션하기 위해 round 를 수동 고정한다.
    sd["shipment"]["as_log"].append({
        "id": "al_fix", "ts": "2026-08-05T10:00:00", "by": "김", "by_id": 1,
        "type": "verdict", "verdict": "resolved", "text": "정정: 완결", "round": 1,
        "edited_at": None, "edited_by": None,
    })
    view = build_as_round_chart_view(sd, today=_TODAY)
    r1 = next(r for r in view["rounds"] if r["no"] == 1)
    assert r1["verdict"]["verdict"] == "resolved"  # 마지막 판정이 이긴다
    assert any(e["type"] == "verdict" for e in r1["entries"])  # 이전 판정은 표에 남는다


def test_verdict_prompt_when_round_visit_passed():
    sd = _base_sd()
    append_client_log(sd, log_type="plan", text="p", by="김", by_id=1)
    append_system_log(sd, text="방문일 확정: 2026-08-01")  # 1회차 확정, 지남
    view = build_as_round_chart_view(sd, today=_TODAY)
    states = {s["key"]: s["state"] for s in view["rounds"][0]["slots"]}
    assert states["schedule"] == "done" and states["visit"] == "done"
    assert view["verdict_prompt"] is True


def test_stale_past_visit_not_counted_for_new_round():
    """미결 후 새 회차: 이전 회차의 지난 방문일로 '방문 완료' 오판하지 않는다."""
    sd = _base_sd()
    sd["schedule"] = {"as_visit": {"date": "2026-07-30"}}
    append_system_log(sd, text="방문일 확정: 2026-07-30")
    append_verdict_log(sd, verdict="unresolved", text="미결", by="김", by_id=1)
    view = build_as_round_chart_view(sd, today=_TODAY)
    open_r = view["rounds"][0]
    assert open_r["no"] == 2
    states = {s["key"]: s["state"] for s in open_r["slots"]}
    assert states["schedule"] != "done" and states["visit"] != "done"
    assert view["verdict_prompt"] is False


def test_system_prefix_pins_match_write_sites():
    """분류 접두어 SSOT = 생성 지점 리터럴. 문구를 바꾸면 여기와 차트 분류를 함께 바꿔라."""
    field_update = (_ROOT / "foms/api/orders/field_update.py").read_text(encoding="utf-8")
    as_orders = (_ROOT / "foms/api/cs/as_orders.py").read_text(encoding="utf-8")
    assert 'f"방문일 확정: ' in field_update and '"방문일 취소"' in field_update
    assert 'f"가능시간: ' in field_update and '"가능시간 초기화"' in field_update
    assert 'f"방문일 확정: ' in as_orders  # /as/schedule 경로
    for marker in ("무상 확정", "유상 확정", "미정 처리"):
        assert marker in as_orders
    assert "전환" in as_orders  # X→Y 전환 문구


def _render_chart(app, view, can_edit=True):
    tpl = (
        "{% from 'cs/partials/as_round_chart.html' import render_as_round_chart %}"
        "{{ render_as_round_chart(77, view, can_edit, '유상 확정', 'paid', false, '비고문') }}"
    )
    with app.test_request_context():
        return render_template_string(tpl, view=view, can_edit=can_edit)


def test_render_keeps_js_delegation_contract(app):
    """행=.as-tl-item[data-log-id], quick-add=form+숨김 select — 기존 위임이 그대로 받는다."""
    html = _render_chart(app, build_as_round_chart_view(_scenario_sd(), today=_TODAY))
    assert 'class="as-rchart"' in html and 'data-current-round="2"' in html
    assert "as-tl-item" in html and "data-log-id=" in html
    assert 'class="as-timeline__quick-add as-rchart-dock"' in html
    assert "as-timeline__type" in html and "as-timeline__text" in html
    # 세그먼트 4종 = 방안/통화/자재/메모 (퇴역 유형 없음)
    for t in ("plan", "call", "material", "memo"):
        assert f'data-type="{t}"' in html
    assert 'data-type="action"' not in html and 'data-type="schedule"' not in html
    # 상태 카드 3필드 + 회차 표기
    for label in ("방문일", "가능시간", "비용", "1차", "2차 · 진행 중"):
        assert label in html
    # 판정 배지·접힌 회차 details
    assert "as-rchart-verdict-flag--unresolved" in html
    assert "as-rchart-round--closed" in html
    assert "비고문" in html


def test_render_verdict_row_has_no_edit_buttons(app):
    """verdict 행은 수정/삭제 버튼을 내지 않는다(서버 400 계약과 정합).

    이 뷰의 유일한 사람 기록이 verdict 라, can_edit=True 인데도 문서 전체에
    수정/삭제 버튼이 0개면 verdict 행이 버튼을 안 낸 증거다.
    """
    sd = _base_sd()
    append_verdict_log(sd, verdict="resolved", text="마감", by="김", by_id=1)
    html = _render_chart(app, build_as_round_chart_view(sd, today=_TODAY))
    assert "as-rchart-row--verdict" in html
    assert "as-tl-item__delete" not in html and "as-tl-item__edit" not in html


def test_render_verdict_prompt_buttons(app):
    sd = _base_sd()
    append_system_log(sd, text="방문일 확정: 2026-08-01")
    html = _render_chart(app, build_as_round_chart_view(sd, today=_TODAY))
    assert 'data-verdict="resolved"' in html and 'data-verdict="unresolved"' in html

    # 판정 조건 미충족이면 버튼 없음
    html2 = _render_chart(app, build_as_round_chart_view(_base_sd(), today=_TODAY))
    assert 'data-verdict="resolved"' not in html2


def test_render_can_edit_false_hides_dock(app):
    html = _render_chart(
        app, build_as_round_chart_view(_scenario_sd(), today=_TODAY), can_edit=False)
    assert "as-rchart-dock" not in html and "as-timeline__quick-add" not in html
    assert "as-tl-item__delete" not in html
    assert "as-billing-edit" not in html
