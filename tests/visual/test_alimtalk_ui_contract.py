"""알림톡 수동 발송 UI 3표면 배선 계약 (v1 T5).

PC/모바일/태블릿 어느 한 표면만 배선하고 나머지를 빠뜨리는 것이 이 기능의 대표 회귀라
(스펙 §6.5 H5 — "자동 커버" 아님), 세 표면의 버튼·모달·JS 로드 체인을 소스 문자열로
고정한다. 렌더 파이프라인이 아니라 파일 내용을 보므로 DB/브라우저 없이 즉시 실패한다.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BUTTON_CLASS = "erp-alimtalk-send-btn"
MODAL_PARTIAL = "orders/partials/erp_alimtalk_modal.html"
PICKER_PARTIAL = "orders/partials/erp_alimtalk_picker_modal.html"
SEND_JS = "js/orders/erp-alimtalk-send.js"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_pc_tab_has_alimtalk_button_and_status_line() -> None:
    """PC: 채널톡 PUSH 버튼 옆 알림톡 버튼 + 상태 한 줄."""
    html = _read("templates/orders/partials/erp_order_tab.html")
    assert BUTTON_CLASS in html
    assert 'id="erp-alimtalk-send-btn"' in html
    assert "erp-alimtalk-status" in html
    # 채널톡 버튼 묶음 안(= 변환/PUSH 카드 헤더)에 있어야 한다.
    assert html.index("erp-channeltalk-push-as-btn") < html.index(BUTTON_CLASS)


def test_mobile_tab_has_alimtalk_button_in_sticky_footer() -> None:
    """모바일: sticky action bar 에 foms-btn 체계로 노출(PUSH 와 같은 선택 시트 트리거)."""
    html = _read("templates/orders/partials/erp_order_tab_mobile.html")
    footer = html[html.index("erp-mobile-sticky-action-bar"):]
    button = footer[: footer.index("</footer>")]
    assert 'id="erp-alimtalk-picker-btn"' in button, "알림톡 버튼이 sticky footer 밖에 있다"
    assert "foms-btn" in button
    # dropdown 은 좁은 폭에서 액션바를 덮어 터치가 막힌다 — 시트로만 연다.
    assert "erp-alimtalk-menu-mobile" not in html
    assert PICKER_PARTIAL in html


def test_mobile_alimtalk_picker_sheet_reuses_push_sheet_markup() -> None:
    """모바일 알림톡 선택 시트: PUSH 시트와 같은 클래스 + PC 드롭다운과 같은 3항목."""
    sheet = _read("templates/orders/partials/erp_alimtalk_picker_modal.html")
    assert 'id="erpAlimtalkPickerModal"' in sheet
    # PUSH 시트 CSS(erp-channel-push.css)를 그대로 물려받는다.
    assert "erp-channel-push-picker-modal" in sheet
    assert "erp-channel-push-picker-options" in sheet
    # 선택지는 기존 위임 핸들러가 그대로 처리하는 클래스를 단다.
    assert BUTTON_CLASS in sheet
    # 알림톡 발송 3종(도면·계약서·둘 다) + 내 문자로 보내기 2종.
    assert sheet.count('class="foms-btn foms-btn--secondary erp-share-alimtalk-quick-btn"') == 3
    assert sheet.count("data-share-kind=") == 5
    assert 'data-share-kind="drawing"' in sheet
    assert 'data-share-kind="estimate"' in sheet
    assert 'data-share-kind="bundle"' in sheet

    js = _read("static/js/orders/erp-alimtalk-send.js")
    assert "erpOpenAlimtalkPicker" in js
    assert "erpAlimtalkReplay" in js


def test_tablet_measure_form_renders_alimtalk_button_and_handler() -> None:
    """태블릿: 채널톡 섹션에 data-tmf-* 버튼 + 위임 핸들러 분기."""
    js = _read("static/js/foms/tablet-measure-form.js")
    assert "data-tmf-alimtalk-send" in js
    assert BUTTON_CLASS in js
    assert 'closest("[data-tmf-alimtalk-send]")' in js
    assert "/api/kakao/alimtalk/preview/" in js
    assert "/api/kakao/alimtalk/send-manual/" in js


def test_modal_partial_included_on_both_html_surfaces() -> None:
    """미리보기 모달 partial 은 PC/모바일 두 표면 모두에 include 된다(코호트 게이트가 한쪽 제거)."""
    assert MODAL_PARTIAL in _read("templates/orders/partials/erp_order_tab.html")
    assert MODAL_PARTIAL in _read("templates/orders/partials/erp_order_tab_mobile.html")

    modal = _read("templates/orders/partials/erp_alimtalk_modal.html")
    assert 'id="erpAlimtalkModal"' in modal
    assert 'id="erp-alimtalk-preview"' in modal
    assert 'id="erp-alimtalk-confirm-btn"' in modal
    assert 'id="erp-alimtalk-last"' in modal
    assert "style=" not in modal, "인라인 스타일 금지 — erp-pro/erp-channel-push.css 사용"


def test_send_js_wired_in_erp_order_script_chain_with_version() -> None:
    """erp-channel-push-confirm.js 와 같은 체인에서 defer + ?v 로 로드된다(perf G1)."""
    chain = _read("templates/orders/partials/erp_order_js.html")
    line = next(ln for ln in chain.splitlines() if SEND_JS in ln)
    assert "defer" in line
    assert "?v=" in line
    assert chain.index("js/orders/erp-channel-push-confirm.js") < chain.index(SEND_JS)


def test_send_js_singleton_guard_and_click_time_fetch() -> None:
    """전역 리스너 싱글톤(perf G4) + preview 는 클릭 시점 fetch(전역 프리페치 없음)."""
    js = _read("static/js/orders/erp-alimtalk-send.js")
    assert "window.__FOMS_ALIMTALK_BOUND" in js
    assert "document.addEventListener('click'" in js
    assert "/api/kakao/alimtalk/preview/" in js
    assert "/api/kakao/alimtalk/send-manual/" in js
    # dirty 가드: 미저장 편집이 있으면 발송 차단.
    assert "fomsErpAutosave" in js and "isDirty" in js
    # 태블릿 버튼은 자체 핸들러 소유 — 이중 처리 방지 제외 선택자.
    assert ":not([data-tmf-alimtalk-send])" in js


def test_send_js_autosaves_dirty_form_before_preview() -> None:
    """T13: 미저장 입력은 preview 전에 기존 통합 저장으로 반영한다(화면값 직접 조립 금지)."""
    js = _read("static/js/orders/erp-alimtalk-send.js")
    assert "erpAlimtalkEnsureSaved" in js
    # 저장 SSOT = 기존 ERP 통합 저장(리다이렉트 없이 호출).
    assert "window.erpSaveStructured" in js
    assert "redirect: false" in js
    # 저장 실패 시 발송 중단 + 문구 표면화(조용한 통과 금지).
    assert "저장 실패 — 저장 후 다시 시도해주세요." in js
    # 공유 링크(erp-share.js)가 재사용하는 전역 헬퍼.
    assert "window.fomsErpEnsureSavedForSend" in js


def test_send_js_persists_new_and_draft_orders_like_channel_push() -> None:
    """저장 안 한 주문도 **저장(승격)한 뒤** 발송한다 — 채널 PUSH 와 같은 규칙.

    예전에는 draft 백업 주문이면 저장을 건너뛰고 서버의 ``not_eligible`` 을 그대로
    보여줬다. 사용자에게는 "입력해 놨는데 발송이 안 된다"로만 읽혔다(2026-08-24 보고).
    이제 미저장 변경뿐 아니라 **주문 id 가 없거나 draft 인 경우에도** 저장한다.
    """
    js = _read("static/js/orders/erp-alimtalk-send.js")
    # 저장 조건 = dirty ∨ (id 없음 ∨ draft) — 채널 PUSH(_isDirty || _needsPersist) 미러.
    assert "needsPersist" in js
    assert "erpAlimtalkOrderId()" in js
    assert "erpIsDraftBackedOrder" in js
    assert "if (!dirty && !needsPersist) return true;" in js
    # draft 를 그냥 통과시키던 옛 분기가 되살아나면 같은 사고가 난다.
    assert "window.erpIsDraftBackedOrder()) {\n            return true;" not in js
    # id 는 저장 **뒤에** 읽는다(저장이 주문을 만들거나 승격하므로).
    open_body = js.split("async function erpOpenAlimtalkModal()", 1)[1]
    assert open_body.index("erpAlimtalkEnsureSaved()") < open_body.index("erpAlimtalkOrderId()")


def test_tablet_form_saves_before_alimtalk_and_share() -> None:
    """태블릿 실측 폼도 저장 뒤에 발송한다 — PC 와 같은 규칙(본문 = 저장본 SSOT).

    이 화면은 디바운스 자동저장을 쓰지만 마지막 입력 직후에는 아직 저장 전인 창이 남는다.
    그 창에서 알림톡·공유를 누르면 화면과 다른 내용이 고객에게 나간다.
    """
    js = _read("static/js/foms/tablet-measure-form.js")
    assert "function ensureSavedForSend()" in js
    # 저장 SSOT = 이 화면의 명시 저장(saveNow) — 판정 경로를 새로 만들지 않는다.
    assert "saveNow({ explicit: true })" in js
    # 저장 실패 시 발송 중단 + 문구 표면화(조용한 통과 금지).
    assert "저장 실패 — 저장 후 다시 시도해주세요." in js
    # 두 진입점 모두 가드를 먼저 탄다 — 각 진입점 본문은 다음 function 선언 전까지.
    def _entry_body(name: str) -> str:
        rest = js.split(name, 1)[1]
        return rest[: rest.index("\n  function ")]

    for entry in ("function requestAlimtalk()", "function requestShare()"):
        assert "ensureSavedForSend()" in _entry_body(entry), entry
    # preview·발급 fetch 는 저장 뒤 단계로 분리돼 있다(가드를 건너뛰는 경로 없음).
    assert "function _requestAlimtalkSaved()" in js
    assert "function _requestShareSaved()" in js
    assert "/api/kakao/alimtalk/preview/" not in _entry_body("function requestAlimtalk()")
    assert "/api/share/create/" not in _entry_body("function requestShare()")


def test_share_js_saves_before_reading_order_id() -> None:
    """공유 발급·내 문자 보내기도 저장 뒤에 주문 id 를 읽는다(같은 사고 자리)."""
    js = _read("static/js/orders/erp-share.js")
    for entry in ("async function _create()", "async function _selfSms(kind)"):
        body = js.split(entry, 1)[1][:1200]
        assert body.index("_ensureSaved(") < body.index("_orderId()"), entry


def test_share_js_reuses_alimtalk_autosave_guard() -> None:
    """T13(공유): 링크 발급·원클릭 알림톡도 저장본을 보여주므로 같은 dirty 가드를 탄다."""
    js = _read("static/js/orders/erp-share.js")
    assert "fomsErpEnsureSavedForSend" in js
    # 헬퍼 정의 1 + 발급/원클릭 호출 2.
    assert js.count("_ensureSaved(") >= 3


# --- T15 발송 흔적 칩 ------------------------------------------------------------

TRACE_JS = "js/orders/erp-alimtalk-trace.js"
TRACE_PARTIAL = "orders/partials/erp_alimtalk_trace_modal.html"


def test_pc_tab_has_trace_slot_under_alimtalk_button() -> None:
    """PC: 흔적 칩 자리가 알림톡 버튼 **아래**에 있다(0클릭 확인의 전제)."""
    html = _read("templates/orders/partials/erp_order_tab.html")
    assert "data-erp-alimtalk-trace" in html
    assert html.index(BUTTON_CLASS) < html.index("data-erp-alimtalk-trace")


def test_mobile_tab_has_compact_trace_slot_in_action_bar() -> None:
    """모바일: 액션바 안에서 한 줄을 차지하는 축약형 칩(보낸 사람 없음)."""
    html = _read("templates/orders/partials/erp_order_tab_mobile.html")
    footer = html[html.index("erp-mobile-sticky-action-bar"):]
    bar = footer[: footer.index("</footer>")]
    assert 'data-erp-alimtalk-trace="compact"' in bar, "칩이 액션바 밖에 있다"
    assert "erp-alimtalk-trace-slot--mobile" in bar


def test_trace_modal_included_on_both_html_surfaces() -> None:
    """이력 패널 partial 은 PC/모바일 두 표면 모두에 include 된다."""
    assert TRACE_PARTIAL in _read("templates/orders/partials/erp_order_tab.html")
    assert TRACE_PARTIAL in _read("templates/orders/partials/erp_order_tab_mobile.html")

    modal = _read("templates/" + TRACE_PARTIAL)
    assert 'id="erpAlimtalkTraceModal"' in modal
    assert 'id="erp-alimtalk-trace-log"' in modal
    assert 'id="erp-alimtalk-trace-count"' in modal
    assert "style=" not in modal, "인라인 스타일 금지 — erp-channel-push.css 사용"


def test_trace_js_loaded_globally_exactly_once() -> None:
    """칩 스크립트는 전역 1곳에서만 싣는다.

    태블릿 실측 대시보드는 셸 변형에 따라 페이지 스크립트 블록이 통째로 빠지는 경로가 있어
    페이지 스코프로 실으면 그 표면에서만 칩이 조용히 사라진다(스테이징 실측). 반대로 두 곳에
    실으면 같은 파일이 두 번 실행된다.
    """
    layout = _read("templates/partials/shared/layout_scripts.html")
    line = next(ln for ln in layout.splitlines() if TRACE_JS in ln)
    assert "defer" in line and "?v=" in line
    # 태블릿 폼과 같은 자리 — 두 표면이 같은 로드 경로를 탄다.
    assert layout.index("js/foms/tablet-measure-form.js") < layout.index(TRACE_JS)
    for page_scope in ("templates/orders/partials/erp_order_js.html",
                       "templates/measurement/partials/dashboard_scripts.html"):
        assert TRACE_JS not in _read(page_scope), page_scope


def test_trace_js_renders_from_loaded_structured_data_only() -> None:
    """칩은 이미 화면에 있는 구조화 데이터로 그린다 — 렌더에 서버 왕복이 없다."""
    js = _read("static/js/orders/" + TRACE_JS.split("/")[-1])
    assert "window.__FOMS_ALIMTALK_TRACE_BOUND" in js
    assert "window.__erpLastStructuredData" in js
    assert "alimtalk_measurement" in js
    # 렌더 경로가 preview 를 부르면 '추가 요청 0' 계약이 깨진다.
    assert "/api/kakao/alimtalk/preview/" not in js


def test_trace_js_reuses_reason_labels_instead_of_copying() -> None:
    """사유 문구는 발송 모듈 맵 재사용 — 3벌째 사본이 생기면 문구가 갈린다."""
    js = _read("static/js/orders/" + TRACE_JS.split("/")[-1])
    assert "window.erpAlimtalkReasonLabel" in js
    assert "invalid_phone" not in js, "사유 맵을 복사했다"


def test_trace_js_covers_four_chip_states() -> None:
    """보냄·문자로 보냄·실패·미발송 네 상태 — 빈 자리는 '확인 못 함'으로 읽힌다."""
    js = _read("static/js/orders/" + TRACE_JS.split("/")[-1])
    for label in ("예약 안내 보냄", "문자로 보냄", "발송 실패", "아직 안 보냄"):
        assert label in js, label
    for state in ("--sent", "--text", "--failed", "--none"):
        assert "erp-alimtalk-trace" + state in _read("static/css/orders/erp-alimtalk-trace.css")


def test_trace_js_probes_channel_once_after_delay() -> None:
    """채널 확정은 발송 1분 뒤 1회 — 웹훅 아님, 이미 확정된 건은 다시 묻지 않는다."""
    js = _read("static/js/orders/" + TRACE_JS.split("/")[-1])
    assert "/api/kakao/alimtalk/confirm-channel/" in js
    assert "channel_checked_at" in js
    assert "setTimeout" in js and "60 * 1000" in js


def test_trace_history_panel_uses_filtered_event_stream() -> None:
    """이력 패널은 알림톡 이벤트만 받아온다(200건 받아 클라이언트에서 거르지 않는다)."""
    js = _read("static/js/orders/" + TRACE_JS.split("/")[-1])
    assert "event_type=" in js
    assert "ALIMTALK_SENT,ALIMTALK_FAILED" in js
    assert "created_by_name" in js


def test_send_js_publishes_trace_update() -> None:
    """발송 직후 칩 갱신은 응답에 실려 온 이력으로 한다(추가 조회 없음)."""
    js = _read("static/js/orders/erp-alimtalk-send.js")
    assert "foms:alimtalk-trace-update" in js
    assert "body.data.last" in js


def test_structured_load_announces_itself_for_late_renderers() -> None:
    """구조화 데이터 도착 신호가 있어야 칩이 로드 순서와 무관하게 그려진다."""
    js = _read("static/js/orders/erp-order-shared.js")
    assert "foms:erp-structured-loaded" in js


def test_trace_css_is_shared_by_both_surfaces() -> None:
    """칩 CSS 는 파일 하나 — ERP 번들과 태블릿 번들이 서로 다르다고 사본을 두면 색이 갈린다."""
    assert "erp-alimtalk-trace" not in _read("static/css/orders/erp-channel-push.css")
    for surface in (
        "templates/orders/partials/erp_order_js.html",
        "templates/measurement/dashboard.html",
        "templates/measurement/partials/dashboard_fragment.html",
    ):
        assert "css/orders/erp-alimtalk-trace.css" in _read(surface), surface


def test_tablet_measure_form_renders_trace_slot_and_publishes_record() -> None:
    """태블릿: 같은 칩(축약형) + 주문 로드·발송 직후 갱신. 칩 마크업은 칩 모듈이 소유한다."""
    js = _read("static/js/foms/tablet-measure-form.js")
    assert 'data-erp-alimtalk-trace="compact"' in js
    assert "data-erp-alimtalk-trace-order" in js
    assert "foms:alimtalk-trace-update" in js
    # 탭 재렌더가 칩 자리를 새로 만들므로 다시 그리라고 알려야 한다.
    assert "window.erpAlimtalkTraceRender" in js
    # 실패 사유 문구는 태블릿 맵을 같은 이름으로 내줘 칩과 갈리지 않게 한다.
    assert "window.erpAlimtalkReasonLabel" in js
    # 칩 CSS 는 실측 대시보드(풀페이지·fragment 양쪽)에 실린다.
    for surface in ("templates/measurement/dashboard.html",
                    "templates/measurement/partials/dashboard_fragment.html"):
        assert "css/orders/erp-alimtalk-trace.css" in _read(surface), surface


def test_trace_chip_is_display_only_without_history_panel() -> None:
    """이력 패널이 없는 표면에서는 눌러도 아무 일이 없는 버튼을 만들지 않는다."""
    js = _read("static/js/orders/" + TRACE_JS.split("/")[-1])
    assert "erpAlimtalkTraceModal" in js
    assert "createElement(clickable ? 'button' : 'span')" in js


def test_trace_update_with_no_record_clears_stale_chip() -> None:
    """태블릿은 한 화면에서 주문을 갈아끼운다 — 빈 이력은 이전 주문의 칩을 지워야 한다."""
    js = _read("static/js/orders/" + TRACE_JS.split("/")[-1])
    assert "delete window.__erpLastStructuredData.alimtalk_measurement" in js
    # 반대로, 이력이 없는 발송 응답이 멀쩡한 칩을 지우면 안 된다.
    send = _read("static/js/orders/erp-alimtalk-send.js")
    assert "if (body && body.data && body.data.last) _publishTrace(body.data.last);" in send


def test_bundle_share_offered_on_both_alimtalk_surfaces() -> None:
    """도면+계약서 한 링크 항목은 PC 드롭다운·모바일 시트 양쪽에 있어야 한다."""
    for surface in ("templates/orders/partials/erp_order_tab.html",
                    "templates/orders/partials/erp_alimtalk_picker_modal.html"):
        assert 'data-share-kind="bundle"' in _read(surface), surface
    # 발송 흐름은 kind 를 그대로 서버에 넘긴다 — 종류별 분기를 JS 에 두지 않는다.
    js = _read("static/js/orders/erp-share.js")
    assert "bundle: '도면·계약서'" in js


# --- 공유 링크 발송 흔적 칩 (2026-09-01) -----------------------------------------


def test_share_trace_chip_rendered_from_structured_data() -> None:
    """공유 칩도 예약 안내 칩과 같은 원리 — sd 만 읽고 서버 왕복 0."""
    js = _read("static/js/orders/" + TRACE_JS.split("/")[-1])
    assert "sd.alimtalk_share" in js
    assert "function _buildShareChip(" in js
    assert "slot.appendChild(shareChip)" in js


def test_share_trace_chip_hidden_when_never_sent() -> None:
    """공유 링크는 모든 주문에 보내지 않는다 — 미발송이면 칩 자체를 만들지 않는다."""
    js = _read("static/js/orders/" + TRACE_JS.split("/")[-1])
    assert "if (!record || (!record.sent_at && !record.error)) return null;" in js
    # 'none' 변형을 쓰지 않는다는 사실을 CSS 쪽에서도 못박는다.
    css = _read("static/css/orders/erp-alimtalk-trace.css")
    assert ".erp-alimtalk-trace--share {" in css


def test_share_send_publishes_trace_without_extra_fetch() -> None:
    """세 발송 경로(원클릭·모달 알림톡·모달 문자)가 모두 응답의 last_share 를 흘려보낸다."""
    js = _read("static/js/orders/erp-share.js")
    assert js.count("_publishShareTrace(body.data.last_share)") == 3
    assert "foms:share-trace-update" in js
    trace = _read("static/js/orders/" + TRACE_JS.split("/")[-1])
    assert "foms:share-trace-update" in trace


def test_share_trace_assets_pinned_together() -> None:
    """SW staticCacheFirst — 바뀐 자산은 핀을 함께 올려야 옛 코드가 안 산다."""
    pin = "?v=20260901b"

    def _pinned(body: str, asset: str) -> bool:
        """자산 이름 바로 뒤에 이 핀이 붙어 있는지. 개수로 세면 같은 날짜를 쓰는
        남의 자산이 하나 늘 때마다 이 테스트가 깨진다(실제로 CI 에서 깨졌다)."""
        return "filename='" + asset + "') }}" + pin in body

    layout = _read("templates/partials/shared/layout_scripts.html")
    assert _pinned(layout, "js/orders/erp-alimtalk-trace.js")
    order_js = _read("templates/orders/partials/erp_order_js.html")
    assert _pinned(order_js, "css/orders/erp-alimtalk-trace.css")
    assert _pinned(order_js, "js/orders/erp-share.js")
    for surface in ("templates/measurement/dashboard.html",
                    "templates/measurement/partials/dashboard_fragment.html"):
        assert _pinned(_read(surface), "css/orders/erp-alimtalk-trace.css"), surface
