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


def test_map_card_inline_chart_wiring():
    """T15d 지도 배선 소스 핀: 카드 클릭=인라인 확장(읽기 전용 fragment)·차트 CSS 로드.

    사용자 확정 ①(카드 인라인 확장)·④(카드 요약 유지, '다음 할 일' 줄 없음)의 코드 증거.
    """
    tpl = (_ROOT / "templates/measurement/map_view.html").read_text(encoding="utf-8")
    assert "toggleAsCardChart" in tpl
    assert "/erp/as/timeline/" in tpl and "readonly=1" in tpl
    assert "foms-as-round-chart.css" in tpl and "foms-as-timeline.css" in tpl
    # 확정 ④: 지도 목록 카드에는 '다음 할 일' 줄을 내지 않는다(차트 안 next 표기와 별개).
    assert "다음 할 일" not in tpl


def test_render_availability_edit_chip(app):
    """상태 카드 가능시간 필드에 편집 칩(erp-as-avail-chip) — 목록 팝오버 위임 재사용(T15f).

    읽기 전용(can_edit=False, 지도 인라인)에서는 칩을 내지 않는다.
    """
    sd = _base_sd()
    sd["schedule"] = {"as_visit": {"availability": {
        "days": "weekend", "time": "pm", "note": "3시 이후"}}}
    view = build_as_round_chart_view(sd, today=_TODAY)
    assert view["state_card"]["availability"]["days"] == "weekend"
    assert view["state_card"]["availability"]["time"] == "pm"

    html = _render_chart(app, view)
    assert "erp-as-avail-chip" in html
    assert 'data-avail-days="weekend"' in html and 'data-avail-time="pm"' in html
    assert 'data-avail-note="3시 이후"' in html

    readonly = _render_chart(app, view, can_edit=False)
    assert "erp-as-avail-chip" not in readonly


def test_render_author_name_is_ellipsis_target(app):
    """작성자 이름은 별도 span(.as-rchart-row__name) — 긴 표시명 우측 잘림 방어(T15f)."""
    sd = _base_sd()
    append_client_log(sd, log_type="memo", text="m", by="Claude 실서버 측정용 계정", by_id=1)
    html = _render_chart(app, build_as_round_chart_view(sd, today=_TODAY))
    assert 'class="as-rchart-row__name"' in html
    assert 'title="Claude 실서버 측정용 계정"' in html


def test_render_can_edit_false_hides_dock(app):
    html = _render_chart(
        app, build_as_round_chart_view(_scenario_sd(), today=_TODAY), can_edit=False)
    assert "as-rchart-dock" not in html and "as-timeline__quick-add" not in html
    assert "as-tl-item__delete" not in html
    assert "as-billing-edit" not in html


def test_render_can_edit_false_hides_attachment_sort_handles(app):
    """지도 카드(readonly)는 순서 핸들·드래그가 없다. 썸네일 자체는 남긴다."""
    sd = _scenario_sd()
    view = build_as_round_chart_view(sd, today=_TODAY)
    log_id = None
    for round_view in view["rounds"]:
        for entry in round_view["entries"]:
            log_id = entry["id"]
            break
        if log_id:
            break
    assert log_id
    files = {log_id: [{
        "id": 7, "filename": "a.jpg", "is_image": True,
        "view_url": "/v/a.jpg", "thumb_url": "/t/a.jpg",
    }]}
    view = build_as_round_chart_view(sd, attachments_by_log_id=files, today=_TODAY)
    readonly = _render_chart(app, view, can_edit=False)
    assert "as-rchart-file" in readonly
    assert "as-attach-nudge" not in readonly
    assert 'draggable="true"' not in readonly
    editable = _render_chart(app, view, can_edit=True)
    assert "as-attach-nudge" in editable
    assert 'draggable="true"' in editable


# --------------------------------------------------------------------------- #
# T2b: 회차 버킷 키 = (cycle_id, round) — 건(cycle)별 묶기
# --------------------------------------------------------------------------- #
def _sd_two_cycles() -> dict:
    """옛 기록(표식 없음) → 1번째 AS(cyc-1, 종결) → 2번째 AS(cyc-2, 진행) 순으로 쌓인 sd.

    두 건 모두 **1차**다(회차 번호는 이 범위에서 재시작하지 않는다 — 미결 판정이 없어
    current_as_round 가 1로 유지된다). 정수 하나로 버킷팅하면 이 둘이 한 통에 섞인다.
    """
    sd = _base_sd()
    # ① 건 표식이 생기기 전 기록 — cycle_id 가 없다(소급 스탬프 금지).
    append_client_log(sd, log_type="memo", text="예전 기록: 서랍 조정", by="김", by_id=1)

    sd["as_lifecycle"] = {
        "current_cycle_id": "cyc-1",
        "cycles": [
            {"cycle_id": "cyc-1", "received_date": "2026-06-02",
             "completed_date": "2026-06-11", "recurrence": False,
             "transitions": [{"seq": 1, "command": "AS_COMPLETE", "to": "COMPLETED"}]},
            {"cycle_id": "cyc-2", "received_date": "2026-08-01", "recurrence": True,
             "transitions": [{"seq": 1, "command": "AS_REGISTER", "to": "RECEIVED"}]},
        ],
    }
    # ② 1번째 AS(6월) — 사람 기록 + 그 건의 방문일 확정
    append_client_log(sd, log_type="memo", text="6월 현장 재접착", by="박", by_id=2)
    append_system_log(sd, text="방문일 확정: 2026-06-06")

    # ③ 2번째 AS(8월) — 현재 건
    sd["as_lifecycle"]["current_cycle_id"] = "cyc-2"
    append_client_log(sd, log_type="plan", text="8월 접착면 연마 후 재부착", by="이", by_id=3)
    return sd


def _texts(rounds: list[dict]) -> list[str]:
    return [e["text"] for r in rounds for e in r["entries"]]


def test_cycle_groups_split_two_cycles_without_mixing():
    """① 두 건이면 cycle_groups 가 2개고, 각 건의 기록이 서로 섞이지 않는다."""
    view = build_as_round_chart_view(_sd_two_cycles(), today=_TODAY)
    groups = view["cycle_groups"]
    assert len(groups) == 2

    cur, past = groups
    # 현재 건이 맨 앞, 그다음 종결 건 최신순
    assert cur["is_current"] is True and past["is_current"] is False
    assert cur["summary"]["cycle_id"] == "cyc-2" and cur["summary"]["ordinal"] == 2
    assert past["summary"]["cycle_id"] == "cyc-1" and past["summary"]["ordinal"] == 1
    # 건 요약은 as_cycle_view 투영 SSOT 그대로(접수일·완료일·재발·이력불명)
    assert past["summary"]["status"] == "COMPLETED"
    assert past["summary"]["received_date"] == "2026-06-02"
    assert past["summary"]["completed_date"] == "2026-06-11"
    assert past["summary"]["history_unknown"] is False
    assert cur["summary"]["recurrence"] is True

    # 두 건 모두 1차인데 기록이 섞이지 않는다
    assert [r["no"] for r in cur["rounds"]] == [1]
    assert [r["no"] for r in past["rounds"]] == [1]
    assert _texts(cur["rounds"]) == ["8월 접착면 연마 후 재부착"]
    assert _texts(past["rounds"]) == ["6월 현장 재접착"]
    # 종결 건 회차는 진행 슬롯을 그리지 않는다(끝난 건에 '다음: 방문'은 거짓말)
    assert past["rounds"][0]["open"] is False and past["rounds"][0]["slots"] == []


def test_unstamped_old_entries_go_to_unassigned_not_guessed():
    """② cycle_id 없는 옛 항목은 unassigned_rounds 로 간다 — 시각 추정 배치 없음."""
    view = build_as_round_chart_view(_sd_two_cycles(), today=_TODAY)
    assert _texts(view["unassigned_rounds"]) == ["예전 기록: 서랍 조정"]
    # 어느 건에도 끼워 넣지 않는다
    for group in view["cycle_groups"]:
        assert "예전 기록: 서랍 조정" not in _texts(group["rounds"])
    # '분류 안 됨' 블록은 진행 회차가 아니다(슬롯·빈 현재 회차 없음)
    assert all(r["open"] is False and r["slots"] == [] for r in view["unassigned_rounds"])


def test_other_cycle_visit_date_does_not_fill_current_slot():
    """③ 한 건의 방문일이 다른 건 같은 번호 슬롯에 찍히지 않는다(목업 3-C '터지는 것 2')."""
    view = build_as_round_chart_view(_sd_two_cycles(), today=_TODAY)
    cur, past = view["cycle_groups"]
    assert past["rounds"][0]["visit_md"] == "6/6"       # 6월 건에만 남는다
    assert cur["rounds"][0]["visit_md"] == ""           # 8월 건 1차로 새지 않는다
    states = {s["key"]: s["state"] for s in cur["rounds"][0]["slots"]}
    assert states["schedule"] != "done" and states["visit"] != "done"
    assert view["verdict_prompt"] is False
    # 현재 건 rounds 가 그대로 최상위 rounds 다(기존 소비자 계약)
    assert view["rounds"] == cur["rounds"]


def test_rounds_key_unchanged_when_no_cycles():
    """④ 회귀 방지 핀 — 건 기록이 없는 주문은 rounds 모양·번호가 지금과 동일하다."""
    view = build_as_round_chart_view(_scenario_sd(), today=_TODAY)
    assert view["cycle_groups"] == [] and view["unassigned_rounds"] == []
    assert [r["no"] for r in view["rounds"]] == [2, 1]
    assert set(view["rounds"][0]) == {
        "no", "open", "verdict", "summary", "visit_md", "slots", "entries", "hidden_count"}
    open_r, closed_r = view["rounds"]
    assert open_r["open"] is True and open_r["visit_md"] == ""
    assert [s["state"] for s in open_r["slots"]] == [
        "done", "done", "next", "wait", "wait", "wait"]
    assert closed_r["open"] is False and closed_r["visit_md"] == "7/30"
    assert [e["type"] for e in closed_r["entries"]] == ["call", "plan"]
    # 반환 키 집합 = 기존 8개 + 신설 2개 (기존 키 제거 금지)
    assert set(view) == {
        "state_card", "symptom_preview", "rounds", "cycle_groups", "unassigned_rounds",
        "reception", "legacy", "current_round", "verdict_prompt", "count"}


# --------------------------------------------------------------------------- #
# R-B: 스탬프 도입 전부터 진행 중이던 AS(배포 당일 실운영 모집단) — 유일해 귀속
# --------------------------------------------------------------------------- #
def _sd_single_cycle_unstamped() -> dict:
    """cycle 은 1개(현재 건)인데 as_log 항목엔 cycle_id 가 없는 주문.

    스탬프(T1) 배포 시점에 **이미 진행 중이던 모든 AS** 가 이 모양이다. 귀속 보정이
    없으면 현재 건은 '이 회차 기록 없음'이 되고 실제 기록은 전부 '예전 기록'으로 빠져
    같은 회차 번호가 화면에 두 번 뜬다.
    """
    sd = _base_sd()
    append_client_log(sd, log_type="plan", text="1차 방안: 경첩 조정", by="김", by_id=1)
    append_verdict_log(sd, verdict="unresolved", text="부품 불량", by="김", by_id=1)
    append_client_log(sd, log_type="plan", text="2차 방안: 부품 교체", by="김", by_id=1)
    append_system_log(sd, text="방문일 확정: 2026-08-05")
    sd["as_lifecycle"] = {
        "current_cycle_id": "cyc-live",
        "cycles": [{"cycle_id": "cyc-live", "received_date": "2026-07-20",
                    "transitions": [{"seq": 1, "command": "AS_REGISTER", "to": "RECEIVED"}]}],
    }
    return sd


def test_single_cycle_absorbs_unstamped_entries():
    """① 건이 하나뿐이면 미스탬프 기록은 그 건 몫이다(유일해 — 추정 아님)."""
    view = build_as_round_chart_view(_sd_single_cycle_unstamped(), today=_TODAY)
    groups = view["cycle_groups"]
    assert len(groups) == 1 and groups[0]["is_current"] is True
    cur = groups[0]["rounds"]
    assert [r["no"] for r in cur] == [2, 1]
    assert _texts(cur) == ["2차 방안: 부품 교체", "1차 방안: 경첩 조정"]
    # 그 건의 방문일도 함께 귀속된다(현재 회차 슬롯 판정 근거)
    assert cur[0]["visit_md"] == "8/5"
    # '예전 기록' 블록은 비어야 한다 — 갈 곳이 정해졌으므로 남길 이유가 없다
    assert view["unassigned_rounds"] == []
    assert view["rounds"] == cur


def test_two_cycles_keep_unstamped_in_unassigned():
    """② 건이 2개 이상이면 미스탬프 기록은 그대로 '예전 기록'이다(어느 건인지 모름)."""
    view = build_as_round_chart_view(_sd_two_cycles(), today=_TODAY)
    assert len(view["cycle_groups"]) == 2
    assert _texts(view["unassigned_rounds"]) == ["예전 기록: 서랍 조정"]
    # 현재 건에는 자기 스탬프 기록만 실린다
    assert _texts(view["cycle_groups"][0]["rounds"]) == ["8월 접착면 연마 후 재부착"]


def test_single_cycle_has_no_duplicate_round_numbers():
    """③ 같은 회차 번호가 현재 건과 '예전 기록'에 동시에 뜨지 않는다."""
    view = build_as_round_chart_view(_sd_single_cycle_unstamped(), today=_TODAY)
    current_nos = {r["no"] for r in view["rounds"]}
    unassigned_nos = {r["no"] for r in view["unassigned_rounds"]}
    assert current_nos == {1, 2}
    assert current_nos & unassigned_nos == set()
    # 기록이 어느 쪽에서도 사라지지 않는다(총 사람 기록 3건 = 방안2 + 판정1)
    assert view["count"] == 3
