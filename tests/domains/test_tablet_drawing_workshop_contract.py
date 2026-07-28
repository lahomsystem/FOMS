"""W-DRAWING 프레임 03 태블릿 도면 작업실 계약 (2026-07-13).

목업 v8 프레임 03 인벤토리를 잠근다: 상단 바(제목·N건·크기 토글·일괄 배정·마법사) +
필터 바(정렬·D-3·전달 대기·검색·초기화) + KPI 타일 4 + 시트 썸네일 카드 갤러리 +
관리 시트 fragment(썸네일 스트립·자동 채움·버전 이력·시트 전달/마법사 열기).

정적 파일 계약(파일 읽기)만으로 앱 부팅 없이 회귀를 잡는다. 기존 W-DRAWING 계약
(test_tablet_t2_contract.py)이 갤러리 기본형을 잠그고, 이 파일이 프레임 03 확장을 잠근다.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

GALLERY_PARTIAL = "templates/drawing/partials/tablet_gallery_body.html"
SHEET_PARTIAL = "templates/drawing/partials/tablet_sheet_body.html"
GALLERY_CSS = "static/css/foundation/foms-tablet-drawing-gallery.css"
GALLERY_JS = "static/js/foms/tablet-drawing-gallery.js"
REVIEW_JS = "static/js/foms/tablet-drawing-review.js"
SIDE_SHEET_JS = "static/js/foms/tablet-side-sheet.js"
SHEET_ROUTE = "foms/web/drawing/tablet_sheet.py"
DRAWING_INIT = "foms/web/drawing/__init__.py"
WORKBENCH = "foms/web/drawing/workbench.py"

CORE_MEDIA_QUERY = (
    "@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


# --- 상단 바 -----------------------------------------------------------------


def test_workshop_top_bar_has_title_count_sizes_bulk_wizard() -> None:
    body = _read(GALLERY_PARTIAL)
    assert "foms-drawing-workshop" in body
    assert "도면 작업실" in body
    assert "total_count" in body or "rows|length" in body  # sub "N건"
    assert "건</span>" in body
    # 크기 토글 3단.
    for size in ("sm", "md", "lg"):
        assert f'data-foms-gallery-size="{size}"' in body, f"missing size toggle: {size}"
    for label in ("작게", "보통", "크게"):
        assert label in body, f"missing size label: {label}"
    # 일괄 배정(ghost) + 마법사(pri).
    assert "data-foms-drawing-bulk-assign" in body
    assert "도면공 일괄 배정" in body
    assert "erp_drawing_workbench.erp_drawing_workbench_wizard" in body
    assert "도면 마법사" in body


# --- 필터 바 -----------------------------------------------------------------


def test_workshop_filter_bar_sort_dday3_pending_search_reset() -> None:
    body = _read(GALLERY_PARTIAL)
    assert 'name="sort"' in body
    assert "시공일 임박순" in body
    assert 'value="schedule"' in body
    assert 'name="dday3"' in body
    assert "D-3 이내만" in body
    assert 'name="pending"' in body
    assert "전달 대기만" in body
    assert 'name="q"' in body
    assert "초기화" in body


# --- KPI 타일 4 --------------------------------------------------------------


def test_workshop_kpi_tiles_four_with_stats_fields() -> None:
    body = _read(GALLERY_PARTIAL)
    assert "foms-drawing-workshop__kpis" in body
    assert body.count("foms-drawing-kpi__value") == 4, "KPI 타일은 정확히 4개여야 함"
    for token in ("stats.total", "stats.d3", "stats.pending_transfer", "stats.RETURNED"):
        assert token in body, f"missing KPI stat: {token}"
    for label in ("전체", "D-3 이내", "전달 대기", "수정 요청"):
        assert label in body, f"missing KPI label: {label}"


# --- 갤러리 카드 확장 --------------------------------------------------------


def test_gallery_card_carries_sheet_url_and_order_id() -> None:
    body = _read(GALLERY_PARTIAL)
    # 시트 인터페이스 계약: data-foms-sheet-url + data-order-id (side-sheet 로 로드).
    assert 'data-foms-sheet-url="{{ url_for(' in body
    assert "erp_drawing_workbench.erp_drawing_workbench_tablet_sheet" in body
    assert 'data-order-id="{{ r.id }}"' in body
    # 상세 앵커(비-코호트/무 JS fallback) 보존.
    assert "erp_drawing_workbench.erp_drawing_workbench_detail" in body
    assert "tab=timeline" in body
    # tlabel 버전 인지(프레임 03): 시트 N · v{전달회차} · 전달본/전달 대기/상태.
    assert "시트 {{ r.file_count }}" in body
    assert "· v{{ r.transfer_round }}" in body
    assert "in ('TRANSFERRED', 'CONFIRMED') %}전달본" in body
    assert "{% elif r.pending_count %}전달 대기" in body
    assert "{{ r.drawing_status_label }}" in body
    # 전달완료 dim 폐지(2026-07-27): 카드 클래스에 is-dim 조건 없음, tlabel 텍스트로만 구분.
    assert "is-dim" not in body
    assert "'TRANSFERRED', 'CONFIRMED'" in body
    # 다음 페이지 카드.
    assert "foms-drawing-gallery-card--more" in body
    assert "다음 페이지" in body
    assert "pagination.total_count" in body


def test_gallery_wires_workshop_js_deferred_with_cachebuster() -> None:
    body = _read(GALLERY_PARTIAL)
    m = re.search(r"<script[^>]*tablet-drawing-gallery\.js[^>]*>", body)
    assert m is not None, "tablet-drawing-gallery.js not wired in gallery partial"
    tag = m.group(0)
    assert "defer" in tag, "gallery script must be defer (perf G1)"
    assert "?v=20260713b" in tag, "modified file must carry bumped ?v=20260713b"


# --- 관리 시트 fragment ------------------------------------------------------


def test_sheet_fragment_has_head_three_cards_and_foot() -> None:
    body = _read(SHEET_PARTIAL)
    assert "foms-drawing-sheet" in body
    # m-head 고객명 + m-count(#id · 시공) + 원 주문 링크.
    assert "customer_name" in body
    assert "#{{ order_id }}" in body
    assert "construction_md" in body
    assert "원 주문 열기" in body
    # 카드 3: 시트 N·PNG 자동 저장 / 자동 채움(시공일·자수·로고) / 버전 이력.
    assert "PNG 자동 저장" in body
    assert "sheet_count" in body and "sheet_strip" in body
    assert "자동 채움" in body
    for fill in ("시공일", "자수", "로고"):
        assert fill in body, f"missing autofill field: {fill}"
    assert "버전 이력" in body
    assert "timeline" in body
    # m-foot: 시트 전달 + 마법사 열기 ↗.
    assert "data-foms-drawing-transfer" in body
    assert "시트 전달" in body
    assert "마법사 열기" in body
    assert "wizard_url" in body


# --- 관리 시트 라우트 --------------------------------------------------------


def test_sheet_route_registered_and_reuses_wizard_state() -> None:
    route = _read(SHEET_ROUTE)
    assert "@erp_drawing_workbench_bp.route('/drawing-workbench/tablet-sheet/<int:order_id>')" in route
    assert "def erp_drawing_workbench_tablet_sheet" in route
    # 신규 스키마 금지 — 마법사 상태·자동채움 SSOT 재사용.
    assert "_pending_list" in route
    assert "build_wizard_defaults" in route
    assert "drawing/partials/tablet_sheet_body.html" in route
    # 모듈이 __init__ 에서 import 되어 라우트가 등록된다.
    init = _read(DRAWING_INIT)
    assert "from foms.web.drawing import tablet_sheet" in init


# --- 워크벤치 라우트 집계/필터/정렬 확장 (서버 무신규 스키마) ----------------


def test_workbench_route_adds_dday_aggregation_filters_and_sort() -> None:
    route = _read(WORKBENCH)
    # 행 파생 필드.
    assert "'construction_days': alerts.get('construction_days')" in route
    assert "'construction_d3': bool(alerts.get('construction_d3'))" in route
    assert "'product_summary': product_summary" in route
    # KPI 집계.
    assert "stats['d3']" in route
    assert "stats['pending_transfer']" in route
    # 쿼리스트링 필터.
    assert "dday3_only" in route
    assert "pending_only" in route
    # 시공일 임박순 정렬. (정렬 분기 키는 sort_key — sort_by 원본은 my_todo 핀 게이트가 소비)
    assert "sort_key == 'schedule'" in route


# --- JS 계약 ----------------------------------------------------------------


def test_gallery_js_singleton_size_toggle_bulk_and_transfer() -> None:
    js = _read(GALLERY_JS)
    assert "window.__FOMS_DRAWING_GALLERY_BOUND" in js  # 싱글턴 가드(perf G4)
    # 크기 토글 + 지속.
    assert "data-foms-gallery-size" in js
    assert "localStorage" in js
    assert "is-size-" in js
    # 일괄 배정 = 기존 벌크 UI 재사용.
    assert "openBatchAssignModal" in js
    assert "data-foms-drawing-bulk-assign" in js
    # 시트 전달 = 기존 transfer-pending API.
    assert "data-foms-drawing-transfer" in js
    assert "/drawing-wizard/transfer-pending" in js
    # fragment swap 재적용.
    assert "foms:erp-shell-fragment-swapped" in js


# --- CSS 계약 (배타·크기 3단·landscape 전용) --------------------------------


def test_gallery_css_workshop_shell_size_variants_and_landscape_only() -> None:
    css = _norm(_read(GALLERY_CSS))
    # 셸 기본 은닉(코호트 opt-in 앞) — blank 금지 순서 계약.
    base_idx = css.index(".foms-drawing-workshop { display: none")
    show_idx = css.index("body.erp-mobile-v2-layout .foms-drawing-workshop { display: flex")
    assert base_idx < show_idx, "작업실 셸 base-hide 가 opt-in 뒤에 있음(순서 계약 위반)"
    assert CORE_MEDIA_QUERY in css
    # 크기 3단 (220/260/320).
    assert ".foms-drawing-gallery.is-size-sm { grid-template-columns: repeat(auto-fill, minmax(220px" in css
    assert ".foms-drawing-gallery.is-size-md { grid-template-columns: repeat(auto-fill, minmax(260px" in css
    assert ".foms-drawing-gallery.is-size-lg { grid-template-columns: repeat(auto-fill, minmax(320px" in css
    # KPI + 시트 썸네일 120×84.
    assert "grid-template-columns: repeat(4, 1fr)" in css
    assert "width: 120px" in css
    assert "height: 84px" in css
    # 갤러리 카드 썸네일 비율(2026-07-27): 고정 132px → aspect-ratio 4/3 + max-height 180px,
    # object-fit contain(레터박스, 원본 비율 왜곡 금지). 전달완료 dim 폐지.
    assert ".foms-drawing-gallery-card__thumb { position: relative; aspect-ratio: 4 / 3; max-height: 180px" in css
    assert ".foms-drawing-gallery-card__img { display: block; width: 100%; height: 100%; object-fit: contain" in css
    assert "is-dim" not in css
    # landscape 전용(portrait 토큰 금지, split-view 가드 정합).
    assert "orientation: portrait" not in css


# --- long-press 다중 선택 (프레임 03 note2) ----------------------------------


def test_gallery_js_longpress_multiselect_reuses_batch_modal() -> None:
    js = _read(GALLERY_JS)
    # long-press(~500ms) 진입 + 이동 취소(스크롤 구분).
    assert "pointerdown" in js
    assert "LONG_PRESS_MS = 500" in js
    assert "MOVE_CANCEL_PX" in js
    # 포인터/선택 배선 코호트 게이트 = MQ + CSS 마커(--foms-tablet-ui) 파생(비코호트 무동작).
    assert "orientation: landscape) and (pointer: coarse)" in js
    assert "--foms-tablet-ui" in js
    # 선택 상태 = 카드 클래스 + 기존 PC 벌크 체크박스(.order-checkbox) 구동 → 모달 재사용.
    assert "is-selected" in js
    assert "is-selecting" in js
    assert ".order-checkbox" in js
    assert "openBatchAssignModal" in js
    # contextual bar = 공용 .foms-tablet-bulk-bar 재사용 + [일괄 배정]/[선택 해제].
    assert "foms-tablet-bulk-bar" in js
    assert "일괄 배정" in js
    assert "선택 해제" in js
    # 사이드 시트 억제(capture stopPropagation) + long-press 후속 click 소비.
    assert "stopPropagation" in js
    assert "consumeNextClick" in js


# --- E2 전체화면 도면 뷰어 배선 (2026-07-27) ---------------------------------


def test_viewer_marker_present_in_gallery_and_sheet_partials() -> None:
    """썸네일 탭 진입점 계약: 갤러리 카드 thumb + 시트 스트립 img 양쪽에 마커."""
    gallery = _read(GALLERY_PARTIAL)
    # 이미지 도면이 있는 카드만 마커(+서버 JSON 파일 목록). role/tabindex 부여 금지.
    assert "data-foms-drawing-viewer" in gallery
    assert "data-foms-drawing-files='{{ r.drawing_files|tojson }}'" in gallery
    assert 'role="button"' not in gallery
    # 이미지 0장 카드는 마커 대신 "도면 없음" 플레이스홀더.
    assert "foms-drawing-gallery-card__thumb-empty" in gallery
    assert "도면 없음" in gallery

    sheet = _read(SHEET_PARTIAL)
    assert "data-foms-drawing-viewer" in sheet
    assert 'data-view-url="{{ s.thumb_url }}"' in sheet
    assert 'data-filename="{{ s.sheet_name }}"' in sheet


def test_gallery_wires_review_js_deferred_with_cachebuster() -> None:
    body = _read(GALLERY_PARTIAL)
    m = re.search(r"<script[^>]*tablet-drawing-review\.js[^>]*>", body)
    assert m is not None, "tablet-drawing-review.js not wired in gallery partial"
    tag = m.group(0)
    assert "defer" in tag, "review script must be defer (perf G1)"
    assert "?v=20260727b" in tag, "판정·연속리뷰 확장 반영 범프"


def test_review_js_singleton_guard_mq_gate_and_preventdefault() -> None:
    js = _read(REVIEW_JS)
    assert "window.__FOMS_DRAWING_REVIEW_BOUND" in js  # 싱글턴 가드(perf G4)
    # 코호트 게이트 = 태블릿 가로 coarse MQ(SSOT 문자열 side-sheet 와 동일).
    assert "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)" in js
    # 카드 <a> 네비 + 시트 열기 차단 책임이 이 핸들러에 있다.
    assert "ev.preventDefault()" in js
    assert "ev.stopPropagation()" in js
    # document 위임 1개(시트 aside 는 런타임 생성이라 컨테이너 바인딩 불가).
    assert js.count("document.addEventListener") == 1
    # 전역 뷰어 위임 + 부재 시 무음 금지.
    assert "window.GlobalImageViewer.open(files, idx)" in js
    assert "console.warn" in js


def test_side_sheet_defers_drawing_viewer_marker() -> None:
    """side-sheet 클릭 핸들러가 뷰어 마커를 만나면 시트를 열지 않는다(early-return)."""
    js = _read(SIDE_SHEET_JS)
    assert 'if (target.closest("[data-foms-drawing-viewer]")) return;' in js
    # 가드는 row 처리보다 앞이어야 한다(시트 개방·preventDefault 전).
    assert js.index("data-foms-drawing-viewer") < js.index("var row = target.closest(ROW_SELECTOR)")


# --- E3 판정 오버레이 · E5 연속 리뷰 · E6 딜라이트 (2026-07-27) ---------------


def test_gallery_card_carries_review_context_data_attrs() -> None:
    """액션바 노출 조건·컨텍스트 스트립이 읽는 카드 data-* 계약."""
    body = _read(GALLERY_PARTIAL)
    for attr in (
        'data-foms-drawing-status="{{ r.drawing_status }}"',
        "data-foms-can-confirm=",
        "data-foms-can-revise=",
        "data-foms-order-change=",
        'data-foms-customer="{{ r.customer_name }}"',
        "data-foms-dday=",
        "data-foms-install=",
    ):
        assert attr in body, f"missing review data attr: {attr}"
    assert "r.can_confirm_receipt_perm" in body
    assert "r.can_request_revision" in body
    # E6 ①: 시공 D-1 이하 앰버 테두리 + ④ 검색 inputmode.
    assert "r.construction_days <= 1" in body
    assert "is-due-soon" in body
    assert 'inputmode="search"' in body


def test_review_js_action_bar_uses_viewer_extra_and_textcontent() -> None:
    js = _read(REVIEW_JS)
    # append 패턴 마운트 지점 + 코어 리셋이 잡아가는 마커.
    assert "data-viewer-extra" in js
    assert 'document.getElementById("global-viewer-footer")' in js
    assert "foms-viewer-actions" in js
    assert "foms-viewer-context" in js
    # 사용자 유래 문자열은 textContent/createElement 로만 — 전역 뷰어 오염 금지.
    assert "innerHTML" not in js
    assert "createElement" in js
    assert "textContent" in js
    # 주문변경 미확인 경고 배지.
    assert "주문변경 미확인" in js


def test_review_js_judgement_api_contract() -> None:
    js = _read(REVIEW_JS)
    assert "/confirm-drawing-receipt" in js
    assert "/request-revision" in js
    # 판정 대상 = 현재 뷰어 인덱스의 파일 key(열 때 인덱스 아님 — 코어 getIndex 필수).
    assert "getIndex" in js
    assert "target_drawing_keys" in js
    # 기존 실행판 판정 fetch 와 동일한 헤더 패턴.
    assert '"Content-Type": "application/json"' in js
    # 응답 필드는 message(error 아님) + success 검증 + 상태코드별 문구.
    assert "data.success" in js
    assert "권한이 없습니다" in js
    assert "이미 처리된 도면입니다" in js
    assert "전송 실패 — 다시 시도" in js
    # 이중 탭 방지 + 실패 시 컨텍스트 로그.
    assert "disabled = busy" in js
    assert 'console.error("[foms-drawing-review]"' in js


def test_review_js_revision_reason_chips_preset() -> None:
    js = _read(REVIEW_JS)
    for chip in ("치수 확인", "재실측 필요", "마감/색상 확인", "설치 간섭"):
        assert chip in js, f"missing revision reason chip: {chip}"


def test_review_js_continuous_review_counter_and_next() -> None:
    js = _read(REVIEW_JS)
    # 카운터 모수 = 현재 DOM 목록의 TRANSFERRED 카드(서버 stats 아님).
    assert "이 목록 확정 대기 " in js
    assert 'data-foms-drawing-status="TRANSFERRED"' in js
    # 확정 = 카드 제거 / 수정요청 = RETURNED 잔존 + 수정 요청 칩.
    assert "card.remove()" in js
    assert 'card.setAttribute("data-foms-drawing-status", "RETURNED")' in js
    assert "foms-drawing-gallery-chip is-urgent" in js
    # 목록 소진 안내 + 건너뛰기.
    assert "이 목록의 확정 대기 도면을 모두 검토했습니다" in js
    assert "다음 ▸" in js
    # 신규 document 리스너 금지 — 액션바는 자체 노드 위임.
    assert js.count("document.addEventListener") == 1
    assert "bar.addEventListener" in js


def test_review_js_longpress_hint_once_via_localstorage() -> None:
    js = _read(REVIEW_JS)
    assert "fomsDrawingLongpressHintSeen" in js
    assert "카드를 길게 누르면 여러 건을 선택할 수 있습니다" in js
    assert "foms-drawing-gallery-hint" in js


def test_gallery_css_viewer_action_bar_touch_targets() -> None:
    css = _norm(_read(GALLERY_CSS))
    # 뷰어 오버레이는 body 직속 — 코호트 접두 없이 자체 클래스로만 스코프.
    assert ".foms-viewer-actions {" in css
    assert ".foms-viewer-context {" in css
    assert "body.erp-mobile-v2-layout .foms-viewer-actions" not in css
    # 터치 타깃 44px(버튼·칩).
    assert ".foms-viewer-actions__btn { min-height: 44px" in css
    assert ".foms-viewer-actions__chip { min-height: 44px" in css
    # E6 ① 앰버 테두리는 하드코딩 색이 아니라 팔레트 변수.
    assert ".foms-drawing-gallery-card.is-due-soon" in css
    assert "var(--foms-color-warning-500" in css


def test_gallery_css_longpress_selection_affordance() -> None:
    css = _norm(_read(GALLERY_CSS))
    # 선택 모드 체크 원 + 선택 카드 primary 링.
    assert ".foms-drawing-gallery.is-selecting" in css
    assert ".foms-drawing-gallery-card.is-selected" in css
    # long-press 콜아웃/텍스트 선택 억제(카드가 <a>).
    assert "-webkit-touch-callout: none" in css
    # landscape 전용 계약 유지.
    assert "orientation: portrait" not in css
