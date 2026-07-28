"""PC 도면 작업실 대시보드(legacy 테이블) 계약 (2026-07-28).

도면팀 persona 개선 P1×5 + P2×2 를 정적 텍스트 계약으로 잠근다:
최근 이벤트 재변환·타입 칩·지연 타일 필터 정합·미확인 0건 숨김·다음 액션 톤·
대기중/작업중 분리 집계·시공일 기반 SLA.

앱 부팅 없이 파일 읽기만으로 회귀를 잡는다(기존 test_tablet_* 계약 파일 관례).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

WORKBENCH = "foms/web/drawing/workbench.py"
BODY = "templates/drawing/partials/workbench_dashboard_body.html"
STYLES = "templates/drawing/partials/workbench_dashboard_styles.html"
DASHBOARD_JS = "static/js/drawing/workbench-dashboard.js"
ORDER_CHANGE = "foms/services/notifications/drawing_order_change.py"
ERP_DISPLAY = "foms/services/erp_display.py"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# --- P1-1 최근 이벤트 렌더 시 재변환 -----------------------------------------


def test_dashboard_rows_rehumanize_order_change_note() -> None:
    """write-time 박제 note 대신 렌더마다 changes 를 재변환한다."""
    route = _read(WORKBENCH)
    assert "humanize_order_change_changes" in route
    assert "join_changes_text" in route
    assert "summarize_changes" in route
    assert "h_action == 'ERP_ORDER_CHANGED'" in route
    assert "latest_event_note = summarize_changes(_last_changes)" in route
    assert "latest_event_note_full = join_changes_text(_last_changes)" in route
    # 비변경 이벤트는 기존 note 를 그대로 쓴다(full = note).
    assert "latest_event_note_full = latest_event_note" in route
    # 행 필드 노출.
    assert "'latest_event_note': latest_event_note," in route
    assert "'latest_event_note_full': latest_event_note_full," in route


def test_join_changes_text_shares_assembly_with_summarize() -> None:
    """전문 조립은 summarize_changes 와 동일 SSOT(_change_parts) 를 재사용한다."""
    src = _read(ORDER_CHANGE)
    assert "def _change_parts(" in src
    assert "def join_changes_text(" in src
    assert 'return " · ".join(_change_parts(changes))' in src
    # summarize_changes 가 조립을 중복하지 않고 헬퍼를 소비한다.
    summarize = src.split("def summarize_changes(")[1]
    assert "parts = _change_parts(changes)" in summarize
    assert "for ch in humanize_order_change_changes(changes)" not in summarize


def test_template_note_carries_full_text_tooltip() -> None:
    body = _read(BODY)
    assert 'title="{{ r.latest_event_note_full }}"' in body


# --- P1-2 최근 이벤트 타입 칩 -------------------------------------------------


def test_rows_expose_latest_event_action() -> None:
    assert "'latest_event_action': h_action," in _read(WORKBENCH)


def test_template_renders_event_chip_by_action() -> None:
    body = _read(BODY)
    assert "dw-event-chip" in body
    assert "r.latest_event_action" in body
    for action, cls in (
        ("ERP_ORDER_CHANGED", "is-order-change"),
        ("REQUEST_REVISION", "is-revision"),
        ("TRANSFER", "is-transfer"),
    ):
        assert action in body, f"missing chip action: {action}"
        assert cls in body, f"missing chip class: {cls}"
    assert "{{ r.latest_event_label }}</span>" in body


def test_event_chip_css_four_variants_use_palette_tokens() -> None:
    css = _read(STYLES)
    assert ".dw-event-chip {" in css
    for cls in (".dw-event-chip.is-order-change", ".dw-event-chip.is-revision", ".dw-event-chip.is-transfer"):
        assert cls in css, f"missing chip rule: {cls}"
    # 하드코딩 색상 지양 — 팔레트 토큰(fallback 허용).
    assert "var(--foms-color-warning-" in css
    assert "var(--foms-color-danger-" in css
    assert "var(--foms-color-info-" in css


# --- P1-3 지연 타일 클릭 필터 정합 -------------------------------------------


def test_quick_filter_overdue_sets_overdue_param_not_due_today() -> None:
    js = _read(DASHBOARD_JS)
    quick_fn = js.split("function navigatePipelineQuickFilter(filterType)")[1].split(
        "function bindPipelineDelegationOnce"
    )[0]
    assert "params.set('overdue', '1')" in quick_fn
    assert "params.set('due_today', '1')" not in quick_fn
    # overdue/unread/due_today 상호 배타 정리.
    for param in ("unread", "due_today", "overdue"):
        assert f"params.delete('{param}')" in quick_fn, f"quick filter must clear {param}"
    status_fn = js.split("function navigatePipelineStatus(status)")[1].split(
        "function navigatePipelineQuickFilter"
    )[0]
    assert "params.delete('overdue')" in status_fn


def test_route_supports_overdue_filter() -> None:
    route = _read(WORKBENCH)
    assert "overdue_only = (request.args.get('overdue') or '').strip() == '1'" in route
    assert "if overdue_only:" in route
    assert "rows = [r for r in rows if r.get('is_overdue')]" in route
    # 기존 due_today 토글은 유지.
    assert "due_today_only = (request.args.get('due_today') or '').strip() == '1'" in route


def test_dashboard_js_tag_carries_version_bump() -> None:
    body = _read(BODY)
    m = re.search(r"<script[^>]*workbench-dashboard\.js[^>]*>", body)
    assert m is not None, "workbench-dashboard.js not wired in dashboard body"
    tag = m.group(0)
    assert "?v=20260728a" in tag, "수정된 JS 는 SW staticCacheFirst 회피용 ?v 범프 필수"
    assert "defer" in tag, "렌더 차단 동기 스크립트 금지(perf G1)"


# --- P1-4 미확인 0건 배지 숨김 -----------------------------------------------


def test_unread_zero_renders_dash_not_badge() -> None:
    body = _read(BODY)
    assert "{% if r.unread_count > 0 %}" in body
    assert '<span class="badge bg-danger">{{ r.unread_count }}건</span>' in body
    assert '<span class="text-muted small">-</span>' in body
    assert '<span class="badge bg-light text-dark border">0건</span>' not in body


# --- P1-5 다음 액션 재문구 + 턴 시각화 ---------------------------------------


def test_next_action_transferred_copy_is_drawing_team_perspective() -> None:
    src = _read(ERP_DISPLAY)
    assert "return '주문 담당 확정 대기'" in src
    assert "주문 담당 수령 확정 또는 수정 요청" not in src
    # 그 외 분기 문구는 유지.
    assert "return '도면 담당자 지정 필요'" in src
    assert "return '도면 담당 수정본 재전달 필요'" in src


def test_rows_expose_next_action_tone_and_template_applies_class() -> None:
    route = _read(WORKBENCH)
    assert "def _drawing_next_action_tone(" in route
    assert "'next_action_tone': _drawing_next_action_tone(drawing_status, has_assignee)," in route
    assert "return 'assign'" in route
    assert "'mine' if (drawing_status or 'PENDING').upper() in ('PENDING', 'RETURNED') else 'other'" in route
    body = _read(BODY)
    assert "dw-next-action is-{{ r.next_action_tone" in body
    css = _read(STYLES)
    for cls in (".dw-next-action.is-mine", ".dw-next-action.is-other", ".dw-next-action.is-assign"):
        assert cls in css, f"missing tone rule: {cls}"


# --- P2-6 작업중 버킷 부활 ---------------------------------------------------


def test_pending_split_into_waiting_and_in_progress_labels() -> None:
    route = _read(WORKBENCH)
    assert "def _drawing_row_status_label(" in route
    assert "return '작업중' if has_assignee else '대기중'" in route
    # 전역 _drawing_status_label 은 무변경(행 레벨 오버라이드만).
    assert "'drawing_status_label': _drawing_row_status_label(drawing_status, has_assignee)," in route
    display = _read(ERP_DISPLAY)
    assert "'PENDING': '작업중'," in display


def test_stats_split_waiting_and_in_progress() -> None:
    route = _read(WORKBENCH)
    assert "status = 'WAITING' if r.get('no_assignee') else 'IN_PROGRESS'" in route
    assert "'WAITING': 0, 'IN_PROGRESS': 0" in route


def test_status_filter_matches_split_buckets() -> None:
    route = _read(WORKBENCH)
    assert "if status_filter == 'WAITING':" in route
    assert "return s == 'WAITING' or (s == 'PENDING' and bool(row.get('no_assignee')))" in route
    assert "if status_filter == 'IN_PROGRESS':" in route
    assert "return s == 'IN_PROGRESS' or (s == 'PENDING' and not row.get('no_assignee'))" in route


def test_pipeline_tiles_keep_waiting_and_in_progress_data_status() -> None:
    body = _read(BODY)
    assert 'data-status="WAITING"' in body
    assert 'data-status="IN_PROGRESS"' in body
    assert "대기중" in body and "작업중" in body


# --- P2-7 SLA 시공일 기반 재정의 ---------------------------------------------


def test_sla_level_redefined_on_construction_days_at_row_level() -> None:
    route = _read(WORKBENCH)
    assert "def _drawing_row_sla_level(" in route
    assert "sla_level = _drawing_row_sla_level(alerts.get('construction_days'), drawing_status)" in route
    # 지연 = 시공일 경과 && 미전달 / 임박 = D-3 이내 && 미전달.
    assert "if construction_days < 0:" in route
    assert "return '지연'" in route
    assert "if construction_days <= 3:" in route
    assert "return '임박'" in route
    assert "in ('PENDING', 'RETURNED')" in route
    # is_overdue 는 새 정의와 자동 정합(스테이지 48h drawing_overdue 폐기).
    assert "'is_overdue': sla_level == '지연'," in route
    assert "alerts.get('drawing_overdue')" not in route
    # _erp_alerts 전역은 무변경.
    assert "drawing_overdue = False" in _read(ERP_DISPLAY)


def test_template_sla_cell_renders_imminent_level() -> None:
    body = _read(BODY)
    assert "{% if r.sla_level == '지연' %}" in body
    assert '<span class="badge bg-danger">지연</span>' in body
    assert "{% elif r.sla_level == '임박' %}" in body
    assert '<span class="badge bg-warning text-dark">임박</span>' in body
    assert '<span class="badge bg-success">정상</span>' in body


# --- PC2-1 시공일 뱃지 3단 ---------------------------------------------------


def test_construction_badge_level_has_four_level_contract() -> None:
    """시공일 뱃지: 미정=none / D-2 이내·경과=danger / D-4 이내=warn / 그 외=info."""
    route = _read(WORKBENCH)
    fn = route.split("def _construction_badge_level(")[1].split("\ndef ")[0]
    assert "if construction_days is None:" in fn
    assert "return 'none'" in fn
    assert "if construction_days <= 2:" in fn
    assert "return 'danger'" in fn
    assert "if construction_days <= 4:" in fn
    assert "return 'warn'" in fn
    assert "return 'info'" in fn
    # 기본색이 회색(none)이 아니라 파랑(info) 이어야 한다 — none 은 무일정 전용.
    assert fn.rstrip().endswith("return 'info'")
    assert (
        "'construction_badge_level': _construction_badge_level(alerts.get('construction_days')),"
        in route
    )


def test_template_construction_cell_uses_badge_level_class() -> None:
    body = _read(BODY)
    assert "r.construction_badge_level" in body
    assert 'class="badge dw-cdate-badge is-{{ _clevel }} me-1"' in body
    # bg-secondary 고정색 폐기 + 인라인 스타일 → 클래스 이관.
    assert '<span class="badge bg-secondary me-1">' not in body
    assert 'style="font-size: 1rem; color: #495057;"' not in body
    assert "dw-cdate-cell" in body


def test_construction_badge_css_four_variants_use_palette_tokens() -> None:
    css = _read(STYLES)
    assert ".dw-cdate-badge {" in css
    for cls in (
        ".dw-cdate-badge.is-none",
        ".dw-cdate-badge.is-danger",
        ".dw-cdate-badge.is-warn",
        ".dw-cdate-badge.is-info",
    ):
        assert cls in css, f"missing cdate badge rule: {cls}"
    assert ".dw-cdate-cell {" in css


# --- PC2-2 최근 이벤트 세로 스택 + 접기 --------------------------------------


def test_rows_expose_latest_event_parts_reusing_change_parts() -> None:
    """조각 리스트는 join_changes_text 와 같은 SSOT(_change_parts) 를 재사용한다."""
    route = _read(WORKBENCH)
    assert "_change_parts," in route, "_change_parts 를 import 해 조립을 중복하지 않는다"
    assert "latest_event_parts = _change_parts(_last_changes)" in route
    # 비변경 이벤트는 빈 리스트 → 템플릿이 note 1줄로 폴백.
    assert "latest_event_parts = []" in route
    assert "'latest_event_parts': latest_event_parts," in route


def test_template_stacks_event_parts_and_folds_overflow() -> None:
    body = _read(BODY)
    assert "{% if r.latest_event_parts %}" in body
    # 첫 2개는 항상 표시, 나머지는 네이티브 details 로 접기(JS 불요).
    assert "r.latest_event_parts[:2]" in body
    assert "r.latest_event_parts[2:]" in body
    assert "{% if r.latest_event_parts|length > 2 %}" in body
    assert '<details class="dw-event-more"' in body
    assert "외 {{ r.latest_event_parts|length - 2 }}건 펼치기" in body
    assert '<div class="dw-event-part">{{ _p }}</div>' in body
    # 폴백(note 1줄)과 풀텍스트 툴팁 유지.
    assert "{% elif r.latest_event_note %}" in body
    assert 'title="{{ r.latest_event_note_full }}"' in body
    # 행 클릭 내비게이션(문서 위임)이 summary 클릭을 가로채면 안 된다.
    assert 'onclick="event.stopPropagation();"' in body.split('<details class="dw-event-more"')[1][:80]


def test_event_part_css_present() -> None:
    css = _read(STYLES)
    assert ".dw-event-part {" in css
    assert ".dw-event-more > summary {" in css
    assert "cursor: pointer;" in css.split(".dw-event-more > summary {")[1].split("}")[0]


# --- PC2-3 정렬·컬럼 폭 -------------------------------------------------------


def test_sla_sort_ranks_display_level_with_schedule_tiebreak() -> None:
    """SLA 정렬은 표시 뱃지(sla_level)와 같은 축 + 동급은 시공일 임박순."""
    route = _read(WORKBENCH)
    assert "sla_rank = {'지연': 0, '임박': 1, '정상': 2}" in route
    assert "sla_rank.get(r.get('sla_level'), 9)" in route
    assert "r.get('construction_days') if r.get('construction_days') is not None else 9999" in route
    # due_today 기반 구 정렬키 폐기(뱃지와 축이 달라 첫 클릭이 무의미했다).
    assert "0 if r.get('is_overdue') else (1 if r.get('due_today') else 2)" not in route


def test_status_sort_map_covers_pending() -> None:
    """drawing_status 원본은 PENDING — 맵 누락 시 99로 밀려 정렬이 죽는다."""
    route = _read(WORKBENCH)
    assert "'IN_PROGRESS': 3, 'PENDING': 3," in route
    assert "'WAITING': 4, 'CONFIRMED': 5}" in route


def test_my_todo_pin_is_gated_on_explicit_sort() -> None:
    """명시 정렬(?sort=)이 있으면 my_todo 핀이 사용자 선택을 덮지 않는다."""
    route = _read(WORKBENCH)
    tail = route.split("    if sort_by:")[1]
    assert "    if not sort_by:\n        rows.sort(key=lambda r: 0 if r.get('my_todo') else 1)" in tail
    # 게이트 판정용 원본 보존 — 접두사 제거는 별도 변수(sort_key)로.
    assert "sort_key = sort_by[1:] if reverse else sort_by" in route
    assert "sort_by = sort_by[1:] if reverse else sort_by" not in route


def test_narrow_columns_have_fixed_width_without_table_layout_fixed() -> None:
    """필터·정렬 시 컬럼 흔들림 제거. table-layout: fixed 는 금지(이벤트 셀 깨짐)."""
    css = _read(STYLES)
    assert "table-layout: fixed" not in css
    for nth, width in (
        (3, "110px"),  # 시공일
        (5, "90px"),   # 도면 담당
        (6, "110px"),  # 상태
        (7, "70px"),   # 대상 번호
        (9, "80px"),   # SLA
        (10, "70px"),  # 미확인
        (11, "100px"),  # 열기
    ):
        rule = f".erp-drawing-workbench-table-wrap td:nth-child({nth}) {{"
        assert rule in css, f"missing width rule for column {nth}"
        assert width in css.split(rule)[1].split("}")[0], f"column {nth} width != {width}"
    # 가변 유지: 주문/고객(2)·다음 액션(4)·최근 이벤트(8) 는 폭 고정 금지.
    for nth in (2, 4, 8):
        assert f"td:nth-child({nth})" not in css, f"column {nth} must stay fluid"


def test_no_new_db_query_in_row_loop() -> None:
    """행 파생 필드는 이미 로드된 sd/alerts/history 재사용 — 신규 쿼리 금지."""
    route = _read(WORKBENCH)
    loop = route.split("    for o in orders:")[1].split("    # 프로세스 맵 카운트는")[0]
    for banned in ("db.query(", ".first()", ".all()"):
        assert banned not in loop, f"행 루프에 신규 DB 조회 유입: {banned}"
