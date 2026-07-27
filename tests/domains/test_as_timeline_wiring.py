"""T10 계약: 구 리치에디터(툴바·2탭·contenteditable autosave) 퇴역 + 타임라인 상호작용 배선.

구 D1b 툴바 hydrate 계약(`test_as_toolbar_hydrate.py`)을 대체한다. 툴바·탭·contenteditable 은
타임라인 전환으로 사라졌으므로 계약의 의도가 뒤집혔다 — "1개만 렌더" 가 아니라 "0개".

1) 서버 렌더: 리치툴바 template·content-tabs 매크로·contenteditable 입력이 어느 표면에도 없다.
2) sales_delivery 토글: 툴바에서 타임라인 헤더(PC 확장 fragment·모바일 상세)로 이전됐고
   주문별 활성 상태를 서버가 직접 싣는다(구 hydrate 주입 대체).
3) 클라이언트: 구 경로(hydrate·탭 전환·리치 command·as_content autosave) 제거 +
   신규 위임(확장 행 lazy fetch·quick-add·더보기·정적 하이라이트)이 싱글톤 가드로 1회만 등록.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User

_ROOT = Path(__file__).resolve().parents[2]


def _js() -> str:
    return (_ROOT / "static/js/cs/as-dashboard.js").read_text(encoding="utf-8")


def _macros() -> str:
    return (_ROOT / "templates/cs/partials/as_card_macros.html").read_text(encoding="utf-8")


def _timeline_block(js: str) -> str:
    """싱글톤 가드로 감싼 타임라인 위임 블록만 잘라낸다.

    파일 전역 카운트로 단언하면 무관한 핸들러의 동일 토큰(`await res.json()` 등)이
    세는 수를 흐려 계약이 무력해진다.
    """
    start = js.index("window.__FOMS_AS_TIMELINE_BOUND")
    end = js.index("e.target.closest('.as-sales-delivery-btn')", start)
    return js[start:end]


def _entry_chunks(body: str) -> dict[str, str]:
    """렌더된 타임라인 HTML을 data-log-id 기준으로 항목별 조각으로 쪼갠다."""
    chunks: dict[str, str] = {}
    for part in body.split('data-log-id="')[1:]:
        log_id, rest = part.split('"', 1)
        chunks[log_id] = rest.split('data-log-id="', 1)[0]
    return chunks


def _login_as_admin(client, username="as_timeline_wiring_admin"):
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="AS Timeline Wiring Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _create_as_order(name, *, shipment_extra=None, notes=None):
    today = date.today().strftime("%Y-%m-%d")
    order = Order(
        received_date=today,
        customer_name=name,
        phone="010-1111-2222",
        address="Seoul",
        product="붙박이장",
        status="AS_RECEIVED",
        manager_name="Alice",
        as_received_date=today,
        is_erp_order=True,
        notes=notes,
        structured_data={"shipment": dict(shipment_extra or {})},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


# ---------------------------------------------------------------------------
# 1) 서버 렌더 — 구 에디터 표면 퇴역
# ---------------------------------------------------------------------------


def test_rich_editor_surfaces_are_retired_from_dashboard(client, monkeypatch):
    """대시보드 fragment 에 툴바 template·탭·contenteditable 이 하나도 남지 않는다."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = _login_as_admin(client)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    for i in range(3):
        _create_as_order(f"툴바 AS {i}")

    resp = client.get(
        "/erp/as?tab=incomplete&view=fragment",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)

    for token in (
        "as-rich-toolbar-template",
        "as-rich-toolbar",
        "as-rich-editor",
        "as-rich-command-btn",
        "as-tabbed-editor",
        "as-content-tab-btn",
        "as-content-input",
        'contenteditable="true"',
    ):
        assert token not in body, token


def test_content_tabs_macros_are_deleted():
    """매크로 정의 자체가 사라져야 재유입이 불가능하다(정의 0 + 호출/import 0).

    이름 언급 자체는 퇴역 사유를 적은 주석에도 남으므로, 정의(`{% macro X`)와
    호출/import 형태(`X(`)만 금지한다.
    """
    macros = _macros()
    body = (_ROOT / "templates/cs/partials/as_dashboard_body.html").read_text(encoding="utf-8")
    for name in ("render_as_content_tabs", "render_as_rich_toolbar_template"):
        assert "{%% macro %s" % name not in macros, name
        assert "%s(" % name not in macros, name
        assert name not in body, name  # import 줄·호출 모두 제거
    assert "contenteditable" not in macros


# ---------------------------------------------------------------------------
# 2) sales_delivery 토글 이전
# ---------------------------------------------------------------------------


def test_sales_delivery_toggle_moved_to_timeline_header(client):
    """토글은 타임라인 헤더에 있고, 주문별 활성 상태를 서버가 싣는다(구 hydrate 주입 대체)."""
    _login_as_admin(client, username="as_sales_toggle_admin")
    off_id = _create_as_order("영업 미지정")
    on_id = _create_as_order("영업 지정", shipment_extra={"sales_delivery": True})

    macros = _macros()
    assert "as-timeline__header" in macros

    off_body = client.get(f"/erp/as/timeline/{off_id}").get_data(as_text=True)
    assert "as-timeline__header" in off_body
    assert 'data-sales-delivery-active="0"' in off_body
    assert f'data-order-id="{off_id}"' in off_body
    assert "☐ 영업/전달" in off_body

    on_body = client.get(f"/erp/as/timeline/{on_id}").get_data(as_text=True)
    assert 'data-sales-delivery-active="1"' in on_body
    assert "☑ 영업/전달" in on_body

    # 모바일 상세도 같은 토글을 싣는다
    detail = client.get(f"/erp/as/card-detail/{on_id}").get_data(as_text=True)
    assert "as-sales-delivery-btn" in detail
    assert 'data-sales-delivery-active="1"' in detail


def test_sales_delivery_toggle_hidden_without_edit_permission(client):
    """읽기 전용 사용자에게는 토글이 렌더되지 않는다(quick-add 와 같은 게이트)."""
    user = User(
        username="as_timeline_viewer",
        password=generate_password_hash("pw"),
        role="STAFF",
        # ERP_EDIT_ALLOWED_TEAMS("CS","SALES") 밖 → can_edit_erp False.
        # CONSTRUCTION 은 안 된다 — platform/http.py 가 /erp/as 자체를 리다이렉트해
        # 단언이 빈 리다이렉트 페이지를 보고 vacuous pass 한다.
        team="DRAWING",
        name="뷰어",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    order_id = _create_as_order("권한 없는 조회", shipment_extra={"as_log": [
        {"id": "al_m", "ts": "2026-07-24T01:00:00", "by": "김", "by_id": None,
         "type": "memo", "text": "읽기만 가능한 메모"},
    ]})
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    body = client.get(f"/erp/as/timeline/{order_id}").get_data(as_text=True)
    assert "읽기만 가능한 메모" in body  # 리다이렉트가 아니라 실제 타임라인을 봤다
    assert "as-sales-delivery-btn" not in body
    assert "as-timeline__quick-add" not in body


# ---------------------------------------------------------------------------
# 3) 클라이언트 배선
# ---------------------------------------------------------------------------


def test_retired_editor_js_paths_are_gone():
    """구 contenteditable/툴바/탭 경로가 JS 에서 완전히 제거됐다."""
    js = _js()
    for token in (
        "hydrateAsRichToolbar",
        "as-rich-toolbar-template",
        "__FOMS_AS_TOOLBAR_BOUND",
        "as-content-tab-btn",
        "as-rich-command-btn",
        "setAsContentActiveTab",
        "syncAsContentSearchTabs",
        "bindAsContentAutosaveInputs",
        "bindAsContentEditableInputs",
        "flushAsContentIfNeeded",
        "getAsEditorContext",
        "contenteditable",
        "execCommand",
    ):
        assert token not in js, token


def test_timeline_expand_row_is_wired_with_singleton_guard():
    """확장 행: document 위임 1회 등록 + colspan=12(테이블 열 수) + 토글 + 실패 표시."""
    js = _js()
    assert "window.__FOMS_AS_TIMELINE_BOUND" in js
    assert ".as-tl-cell__expand" in js
    assert "as-tl-expand-row" in js
    assert 'colspan="12"' in js
    assert "/erp/as/timeline/" in js
    assert "타임라인을 불러오지 못했습니다." in js
    # 빈 셀(기록 0건)도 같은 위임으로 열려야 첫 기록 입력이 가능하다
    assert ".as-tl-cell__empty" in js


def test_quick_add_is_wired_with_ime_safe_shortcut():
    """quick-add: submit 위임 + Ctrl/⌘+Enter(IME 조합 중 오발화 금지) + optimistic prepend."""
    js = _js()
    assert ".as-timeline__quick-add" in js
    assert "/as/log" in js
    assert "!e.isComposing && e.keyCode !== 229" in js
    assert "stream.insertAdjacentHTML('afterbegin', data.html)" in js
    assert "if (!data.success) throw new Error" in js
    # 첫 기록 삽입 후 "기록 없음" 안내가 새 항목 옆에 남으면 안 된다
    assert ".as-timeline__empty" in js
    assert "if (empty) empty.remove();" in js


def test_write_paths_guard_against_double_submit():
    """append/patch 둘 다 재진입 가드가 있어야 한다.

    버튼 disabled 는 Ctrl/⌘+Enter 경로를 막지 못한다. as_log 는 append-only + 삭제 API가
    없으므로 단축키 연타 한 번이 영구 중복 기록이 된다(PATCH 는 마지막 값이 이겨 무해하지만
    같은 가드를 쓰는 편이 갈라지지 않는다).
    """
    js = _js()
    assert js.count("form.dataset.busy === '1'") == 2  # submitQuickAdd + submitLogEdit
    assert js.count("form.dataset.busy = '1';") == 2
    assert js.count("form.dataset.busy = '';") == 2


def test_write_paths_do_not_leak_json_parse_errors():
    """비-JSON 응답(로그인 리다이렉트 HTML·502)은 사람이 읽을 문구로 바뀐다."""
    js = _js()
    block = _timeline_block(js)
    assert "async function readTimelineJson(res)" in block
    assert block.count("await readTimelineJson(res)") == 2  # append + patch
    assert block.count("await res.json()") == 1  # 원시 파싱은 헬퍼 안에서만
    assert "세션이 만료되었거나 서버 오류가 발생했습니다" in block
    assert "권한이 없거나 세션이 만료되었습니다" in block


def test_log_edit_patch_is_wired():
    """항목 수정: 인라인 폼 → PATCH → 응답 html로 그 항목만 교체 + 하이라이트 재적용."""
    js = _js()
    assert "async function submitLogEdit(form)" in js
    assert "'/as/log/' + encodeURIComponent(logId)" in js
    assert "method: 'PATCH'" in js
    assert "item.outerHTML = data.html;" in js
    assert "highlightTimelineStatic(parent);" in js
    # 인라인 폼도 셸 GET submit 가로채기에서 빠져야 한다
    assert "form.setAttribute('data-foms-erp-no-shell', '');" in js
    # 취소 경로: 폼 제거 + 원본 본문 복원
    assert ".as-tl-item__edit-cancel" in js
    assert "if (body) body.hidden = false;" in js
    # 서식 손실 방지: 본문은 sanitize를 통과한 rich HTML이라 textContent 로 읽으면 안 된다
    assert "textEl.value = seed.innerHTML.trim();" in js
    # 단 검색 하이라이트 <mark>는 화면 장식 — 사본에서 벗겨 시드해야 편집 대상에 안 섞인다
    assert "const seed = body.cloneNode(true);" in js
    assert "seed.querySelectorAll('mark.as-search-highlight')" in js
    assert "mark.replaceWith(...mark.childNodes)" in js


def test_more_button_preserves_unsent_draft():
    """더보기의 innerHTML 교체가 미전송 원고를 말없이 지우면 안 된다.

    quick-add 초안은 값을 옮겨 자동 복원한다. 수정 폼은 JS가 만든 것이라 재렌더로 되살릴 수
    없으므로 대신 확인을 받는다(둘 다 없으면 조용히 날아간다).
    """
    js = _js()
    assert "const draft = draftEl ? draftEl.value : '';" in js
    assert "if (nextDraftEl && draft) nextDraftEl.value = draft;" in js
    block = _timeline_block(js)
    more = block[block.index(".as-timeline__more"):]
    assert "body.querySelector('.as-tl-item__edit-form')" in more
    assert "window.confirm(" in more


def test_quick_add_form_opts_out_of_shell_navigation(client):
    """quick-add 폼은 erp-shell 의 method=get submit 가로채기에서 빠져야 한다.

    erp-shell.js 는 document capture 단계에서 GET 폼 submit을 프래그먼트 스왑으로 바꾼다
    (`data-foms-erp-no-shell` 이 유일한 opt-out). 이 폼은 JS 가 fetch 로 보내므로 스왑 대상이
    아니다 — 빠지지 않으면 기록은 저장되는데 화면이 통째로 다시 그려져 낙관적 삽입과
    열려 있던 확장 행이 사라진다(실브라우저 스모크에서 실제로 재현됨).
    """
    _login_as_admin(client, username="as_quickadd_shell_admin")
    order_id = _create_as_order("셸 우회 확인")

    body = client.get(f"/erp/as/timeline/{order_id}").get_data(as_text=True)
    assert "as-timeline__quick-add" in body
    form_tag = body.split("as-timeline__quick-add", 1)[1].split(">", 1)[0]
    assert "data-foms-erp-no-shell" in form_tag

    shell = (_ROOT / "static/js/runtime/erp-shell.js").read_text(encoding="utf-8")
    assert "data-foms-erp-no-shell" in shell  # opt-out 계약이 셸에 실재


def test_more_button_requests_full_timeline():
    js = _js()
    assert ".as-timeline__more" in js
    assert "?full=1" in js


def test_static_highlight_replaces_contenteditable_highlight():
    """하이라이트는 정적 텍스트(타임라인 본문·셀 요약) 대상으로 축약되고 주입 후 재적용된다."""
    js = _js()
    assert "function applyStaticHighlight" in js
    assert "function highlightTimelineStatic" in js
    assert ".as-tl-item__body, .as-tl-cell__anchor, .as-tl-cell__recent" in js
    assert "as-search-highlight" in js
    # 확장 주입·더보기 교체·optimistic prepend·초기 렌더에서 각각 재적용
    assert js.count("highlightTimelineStatic(") >= 5


def test_edit_button_only_on_editable_entries(client):
    """수정 버튼은 수기 항목에만. system/legacy 는 PATCH 가 400으로 거부하므로 버튼도 없다."""
    _login_as_admin(client, username="as_log_edit_admin")
    order_id = _create_as_order("수정 버튼 확인", shipment_extra={"as_log": [
        {"id": "al_m", "ts": "2026-07-24T01:00:00", "by": "김", "by_id": None,
         "type": "memo", "text": "수정 가능 메모"},
        {"id": "al_s", "ts": "2026-07-24T02:00:00", "by": "", "by_id": None,
         "type": "system", "text": "AS 접수 처리"},
    ]})
    # legacy 앵커는 as_log 가 아직 없는(영구화 전) 주문에서만 나온다
    legacy_id = _create_as_order("legacy 앵커", shipment_extra={"as_content": "옛 기록"})

    chunks = _entry_chunks(client.get(f"/erp/as/timeline/{order_id}").get_data(as_text=True))
    assert set(chunks) == {"al_m", "al_s"}
    assert "as-tl-item__edit" in chunks["al_m"]
    assert "as-tl-item__edit" not in chunks["al_s"]

    legacy_chunks = _entry_chunks(
        client.get(f"/erp/as/timeline/{legacy_id}").get_data(as_text=True)
    )
    assert set(legacy_chunks) == {"al_legacy_as_content"}
    assert "as-tl-item__edit" not in legacy_chunks["al_legacy_as_content"]


def test_edit_button_hidden_without_edit_permission(client):
    """읽기 전용 사용자에겐 수정 버튼도 미렌더(서버 403 이 진짜 경계, 버튼은 UX)."""
    user = User(
        username="as_log_edit_viewer",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="DRAWING",  # CONSTRUCTION 은 /erp/as 자체가 리다이렉트라 vacuous pass 가 된다
        name="뷰어",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    order_id = _create_as_order("권한 없는 수정", shipment_extra={"as_log": [
        {"id": "al_m", "ts": "2026-07-24T01:00:00", "by": "김", "by_id": None,
         "type": "memo", "text": "메모"},
    ]})
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    body = client.get(f"/erp/as/timeline/{order_id}").get_data(as_text=True)
    assert "as-tl-item" in body  # 항목 자체는 보인다
    assert "as-tl-item__edit" not in body


def test_log_patch_response_html_carries_edit_button(client):
    """PATCH 응답 html도 목록과 같은 마크업(수정 버튼 + (수정됨))이어야 재편집이 이어진다."""
    _login_as_admin(client, username="as_log_patch_html_admin")
    order_id = _create_as_order("PATCH html", shipment_extra={"as_log": [
        {"id": "al_m", "ts": "2026-07-24T01:00:00", "by": "김", "by_id": None,
         "type": "memo", "text": "원본"},
    ]})

    res = client.patch(f"/api/orders/{order_id}/as/log/al_m", json={"text": "수정본"})
    assert res.status_code == 200, res.get_data(as_text=True)
    data = res.get_json()
    assert data["success"] is True
    assert "as-tl-item__edit" in data["html"]
    assert "(수정됨)" in data["html"]
    assert "수정본" in data["html"]


def test_sales_delivery_handler_uses_order_id_dataset():
    """핸들러는 contenteditable 대신 버튼 dataset 의 order_id 로 동작한다(계약 보존).

    구 경로는 `.as-rich-editor` 안 contenteditable 에서 order_id 를 캐냈다. 버튼이 타임라인
    헤더로 옮겨져 그 조상이 사라졌으므로, 핸들러 블록 안에서 dataset 을 직접 읽어야 한다.
    """
    js = _js()
    anchor = js.find("e.target.closest('.as-sales-delivery-btn')")
    assert anchor != -1
    handler = js[anchor:anchor + 1600]
    assert "const orderId = btn.dataset.orderId" in handler
    assert "saveOrderFieldDirect(orderId, 'sales_delivery', nextActive)" in handler
    assert "btn.dataset.salesDeliveryActive === '1'" in handler
    assert "getDateInputsForOrder(orderId, 'as_completed_date')" in handler
    assert "buildAsDashboardUrl({" in handler
