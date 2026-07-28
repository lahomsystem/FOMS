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


def _css(rel_path: str) -> str:
    """주석을 걷어낸 CSS 본문.

    퇴역 선택자 이름은 "왜 지웠는지" 주석에도 남는다 — 주석까지 세면 삭제 계약이
    자기 문서화 때문에 실패한다. 규칙 본문만 남겨서 단언한다.
    """
    import re

    return re.sub(r"/\*.*?\*/", "", (_ROOT / rel_path).read_text(encoding="utf-8"), flags=re.S)


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
    # submitQuickAdd + submitLogEdit + submitBillingDecision
    assert js.count("form.dataset.busy === '1'") == 3
    assert js.count("form.dataset.busy = '1';") == 3
    assert js.count("form.dataset.busy = '';") == 3


def test_write_paths_do_not_leak_json_parse_errors():
    """비-JSON 응답(로그인 리다이렉트 HTML·502)은 사람이 읽을 문구로 바뀐다."""
    js = _js()
    block = _timeline_block(js)
    assert "async function readTimelineJson(res)" in block
    assert block.count("await readTimelineJson(res)") == 4  # append + patch + billing + delete
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


def test_cell_summary_updates_locally_after_write():
    """쓰기 성공 후 접힘 셀 요약을 응답 데이터로 로컬 갱신한다(재조회 금지 — T10 U1).

    확장 행에서 기록을 추가·수정해도 같은 행의 `.as-tl-cell` 은 서버 렌더값 그대로라,
    접는 순간 옛 최근줄과 실제보다 작은 배지 숫자만 남는다.
    """
    block = _timeline_block(_js())
    assert "function updateAsCellSummary(orderId, html, opts)" in block
    assert ".as-tl-cell[data-order-id=" in block
    # quick-add = 최근줄 교체 + 배지 +1 / 항목 수정 = 텍스트만(배지 불변)
    assert "updateAsCellSummary(orderId, data.html, { line: 'recent', countDelta: 1 });" in block
    assert block.count("updateAsCellSummary(") == 4  # 정의 1 + append/patch/billing 호출 3
    # 하이라이트 dataset 가드를 지우지 않으면 갱신된 줄에 검색어가 다시 안 칠해진다
    assert "delete line.dataset.highlightApplied;" in block

    helper = block[block.index("function updateAsCellSummary"):]
    helper = helper[: helper.index("\n      }")]
    assert "fetch(" not in helper, "셀 갱신은 응답 데이터만 쓴다 — 재조회 금지"
    # 서버 요약과 같은 블록 경계 처리(textContent 만 읽으면 <div> 두 줄이 한 단어로 붙는다)
    assert "querySelectorAll('div, p, li, br').forEach((el) => el.after(' '))" in helper


def test_billing_decision_ui_is_rendered_in_timeline_header(client):
    """비용 판정 표시 + 변경 버튼이 타임라인 헤더에 실재한다.

    접수 모달은 "판정 변경은 AS 대시보드에서 하세요"라고 안내하는데, T14 이전에는
    `POST /as/billing` 을 부르는 UI 가 어디에도 없어 그 안내가 막다른 길이었다.
    """
    _login_as_admin(client, username="as_billing_ui_admin")
    order_id = _create_as_order("판정 UI", shipment_extra={
        "as_billing": {"type": "paid", "confirmed": True, "amount": 150000},
    })

    body = client.get(f"/erp/as/timeline/{order_id}").get_data(as_text=True)
    assert "as-billing-edit" in body
    assert 'data-billing-type="paid"' in body
    assert "유상 확정 · 150,000원" in body  # 금액까지 표기(as_billing_state_text SSOT)

    detail = client.get(f"/erp/as/card-detail/{order_id}").get_data(as_text=True)
    assert "as-billing-edit" in detail  # 모바일 상세도 같은 헤더


def test_billing_decision_ui_hidden_without_edit_permission(client):
    """읽기 전용 사용자에겐 판정 변경 진입점이 없다(quick-add 와 같은 게이트)."""
    user = User(
        username="as_billing_ui_viewer",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="DRAWING",  # CONSTRUCTION 은 /erp/as 자체가 리다이렉트라 vacuous pass 가 된다
        name="뷰어",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    order_id = _create_as_order("판정 UI 권한", shipment_extra={"as_log": [
        {"id": "al_m", "ts": "2026-07-24T01:00:00", "by": "김", "by_id": None,
         "type": "memo", "text": "메모"},
    ]})
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    body = client.get(f"/erp/as/timeline/{order_id}").get_data(as_text=True)
    assert "메모" in body  # 리다이렉트가 아니라 실제 타임라인
    assert "as-billing-edit" not in body


def test_billing_decision_is_wired_without_refetch():
    """판정 폼: POST → 표기·배지·타임라인·셀을 응답 데이터로 갱신(목록 재조회 금지)."""
    block = _timeline_block(_js())
    assert "async function submitBillingDecision(form)" in block
    assert "'/as/billing'" in block
    assert "data.state_text" in block
    assert "updateAsBillingBadge(orderId, data.badge_html);" in block
    # 빈 금액을 실어 보내면 서버가 명시적 삭제로 읽어 확정 청구액이 지워진다
    assert "if (payload.type === 'paid' && amountRaw !== '') payload.amount = Number(amountRaw);" in block
    # 인라인 폼도 셸 GET submit 가로채기에서 빠져야 한다
    assert block.count("setAttribute('data-foms-erp-no-shell', '')") == 2  # 항목 수정 + 판정


def test_billing_badge_markup_is_single_sourced(client):
    """상태 셀 배지는 목록과 API 응답이 같은 매크로를 쓴다 — 마크업이 갈리면 낙관적 교체가 튄다."""
    macros = _macros()
    body = (_ROOT / "templates/cs/partials/as_dashboard_body.html").read_text(encoding="utf-8")
    assert "{% macro render_as_billing_badge(kind)" in macros
    assert "render_as_billing_badge(r.as_billing_badge)" in body
    assert "erp-as-billing-badge--" not in body  # 인라인 중복 마크업 잔재 0

    _login_as_admin(client, username="as_billing_badge_admin")
    order_id = _create_as_order("배지 SSOT", shipment_extra={
        "as_billing": {"type": "free", "confirmed": False},
    })
    res = client.post(f"/api/orders/{order_id}/as/billing", json={"type": "paid", "amount": 1000})

    assert res.status_code == 200
    data = res.get_json()
    assert 'erp-as-billing-badge--paid"' in data["badge_html"] and "유상" in data["badge_html"]
    assert data["state_text"] == "유상 확정 · 1,000원"
    assert "유상 확정" in data["html"]  # 타임라인 낙관적 삽입용 항목도 함께


def test_billing_form_classes_are_styled():
    """판정 UI 신규 클래스에 스타일이 실재한다(인라인 스타일 금지 규약)."""
    css = _css(_BODY_CSS)
    for selector in (".as-billing-state", ".as-billing-edit", ".as-billing-form", ".as-billing-cancel"):
        assert selector in css, selector


def test_cell_badge_label_matches_macro():
    """배지 문구가 매크로와 JS 두 곳에 산다 — 갈리면 접기 전후로 라벨이 바뀐다."""
    assert "타임라인 {{ v.count }}" in _macros()
    assert "'타임라인 ' + " in _js()


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


# ---------------------------------------------------------------------------
# 4) T11 — 타임라인 CSS + 구 리치에디터 스타일 퇴역 + 셀 요약 줄 경계
# ---------------------------------------------------------------------------

_BODY_CSS = "static/css/contexts/cs/as-dashboard-body.css"
_CARD_CSS = "static/css/components/foms-as-mobile-card.css"


def test_retired_editor_styles_are_deleted():
    """구 리치에디터/탭/contenteditable 스타일이 두 CSS 어디에도 남지 않는다(소비자 0)."""
    css = _css(_BODY_CSS) + _css(_CARD_CSS)
    for selector in (
        ".as-rich-editor",
        ".as-rich-toolbar",
        ".as-rich-command-btn",
        ".as-content-tab-buttons",
        ".as-content-tab-btn",
        ".as-content-tab-panel",
        ".as-content-input",
    ):
        assert selector not in css, selector
    # 반면 살아있는 두 규칙은 유지돼야 한다(토글은 헤더로 이전, 하이라이트는 정적 재사용)
    assert ".as-sales-delivery-btn" in css
    assert "mark.as-search-highlight" in css


def _relative_luminance(hex_color: str) -> float:
    """WCAG 상대 휘도."""
    channels = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _chip_colors() -> dict[str, str]:
    """CSS 에서 유형별 칩 배경색을 뽑는다."""
    css = _css(_BODY_CSS)
    out: dict[str, str] = {}
    for chunk in css.split(".as-tl-chip--")[1:]:
        name = chunk.split(" ", 1)[0].split("{", 1)[0].strip()
        block = chunk.split("{", 1)[1].split("}", 1)[0]
        out[name] = block.split("background:", 1)[1].split(";", 1)[0].strip()
    return out


def test_timeline_type_chip_colors_match_spec():
    """유형 칩 색 = 스펙 §5.5 색상군 + system 폴백.

    action·material 은 스펙의 원래 값(#16a34a·#f59e0b)이 흰 글자 대비 AA 미달이라
    같은 색상군의 진한 단계로 내렸다(아래 대비 테스트가 근거).
    """
    colors = _chip_colors()
    assert colors == {
        "reception": "#1e3a8a",
        "call": "#2563eb",
        "action": "#15803d",
        "material": "#b45309",
        "schedule": "#7c3aed",
        "memo": "#6b7280",
        "system": "#64748b",
    }


def test_timeline_chips_meet_wcag_aa_on_white_text():
    """칩 글자는 0.7rem 굵게 — large-text 완화(3:1) 대상이 아니라 4.5:1 을 넘겨야 한다."""
    white = _relative_luminance("#ffffff")
    for name, color in _chip_colors().items():
        bg = _relative_luminance(color)
        ratio = (max(white, bg) + 0.05) / (min(white, bg) + 0.05)
        assert ratio >= 4.5, f"{name} {color} = {ratio:.2f}:1"


def test_chip_has_fallback_background():
    """미지 type 이 와도 투명 칩(흰 배경 + 흰 글자)이 되지 않아야 한다."""
    block = _css(_BODY_CSS).split(".as-tl-chip {", 1)[1].split("}", 1)[0]
    assert "background:" in block
    assert "color: #fff" in block


def test_timeline_new_classes_are_styled():
    """T9/T10이 새로 만든 클래스에 스타일이 실재한다(버튼 리셋·폼 레이아웃 포함)."""
    css = _css(_BODY_CSS)
    for selector in (
        ".as-timeline__header",
        ".as-timeline__notes",
        ".as-timeline__notes-body",
        ".as-tl-cell__empty",
        ".as-tl-item__edit ",
        ".as-tl-item__edit-form",
        ".as-tl-item__edit-cancel",
        ".as-tl-item__delete",
    ):
        assert selector in css, selector
    # <button> 기본 장식 리셋: 빈 셀·수정·삭제 버튼은 텍스트/아이콘처럼 보여야 한다.
    # 수정·삭제는 같은 리셋을 쓰므로 그룹 선택자 한 블록이 소유한다.
    for selector in (".as-tl-cell__empty", ".as-tl-item__edit,\n  .as-tl-item__delete"):
        block = css.split(selector, 1)[1].split("}", 1)[0]
        assert "border: 0" in block, selector
        assert "background: none" in block, selector


def test_notes_body_preserves_line_breaks():
    """비고는 평문 그대로 저장된다 — pre-wrap 없이는 여러 줄 메모가 한 줄로 뭉친다."""
    css = _css(_BODY_CSS)
    block = css.split(".as-timeline__notes-body", 1)[1].split("}", 1)[0]
    assert "white-space: pre-wrap" in block


def test_item_body_hidden_attribute_wins():
    """수정 폼 열림 시 본문 숨김은 `hidden` 속성에 의존한다 — display 규칙이 이를 이기면 안 된다."""
    css = _css(_BODY_CSS)
    body_rule = css.split(".as-tl-item__body {", 1)[1].split("}", 1)[0]
    assert "display" not in body_rule  # 애초에 display 를 주지 않는다
    assert ".as-tl-item__body[hidden]" in css  # 나중에 추가돼도 숨김이 깨지지 않는 가드


def test_dashboard_css_links_are_version_pinned():
    """SW staticCacheFirst 함정 — 두 CSS 링크 모두 `?v=` 캐시 버스트를 달고 있어야 한다."""
    body = (_ROOT / "templates/cs/partials/as_dashboard_body.html").read_text(encoding="utf-8")
    for name in ("as-dashboard-body.css", "foms-as-mobile-card.css"):
        link = [line for line in body.splitlines() if name in line and "<link" in line]
        assert len(link) == 1, name
        assert "?v=" in link[0], name


def test_cell_summary_keeps_block_boundaries(client):
    """셀 요약이 <div> 경계를 잃어 서로 다른 기록이 한 단어로 붙으면 안 된다(T9 리뷰 M2).

    striptags 는 태그를 지우기만 해 `<div>첫줄</div><div>둘째줄</div>` 이 "첫줄둘째줄" 이 됐다.
    display 계층이 as_content_html_to_text 로 미리 텍스트화한 값을 템플릿이 소비한다.
    """
    _login_as_admin(client, username="as_cell_boundary_admin")
    _create_as_order("셀 줄경계", shipment_extra={"as_log": [
        {"id": "al_r", "ts": "2026-07-24T01:00:00", "by": "김", "by_id": None,
         "type": "reception", "text": "<div>접수앞줄</div><div>접수뒷줄</div>"},
        {"id": "al_m", "ts": "2026-07-24T02:00:00", "by": "김", "by_id": None,
         "type": "memo", "text": "<div>최근앞줄</div><div>최근뒷줄</div>"},
    ]})

    body = client.get("/erp/as").get_data(as_text=True)
    cell = body.split('class="as-tl-cell"', 1)[1].split("</table>", 1)[0]
    assert "접수앞줄 접수뒷줄" in cell
    assert "접수앞줄접수뒷줄" not in cell
    assert "최근앞줄 최근뒷줄" in cell
    assert "최근앞줄최근뒷줄" not in cell


def test_cell_recent_mirrors_system_icon_branch(client):
    """셀 요약의 최근 1건이 시스템이면 칩이 아니라 아이콘 — 전체 매크로와 표기가 갈리면 안 된다."""
    _login_as_admin(client, username="as_cell_system_admin")
    _create_as_order("셀 시스템", shipment_extra={"as_log": [
        {"id": "al_m", "ts": "2026-07-24T01:00:00", "by": "김", "by_id": None,
         "type": "memo", "text": "수기 메모"},
        {"id": "al_s", "ts": "2026-07-24T09:00:00", "by": "시스템", "by_id": None,
         "type": "system", "text": "AS 방문일이 확정되었습니다."},
    ]})

    body = client.get("/erp/as").get_data(as_text=True)
    cell = body.split('class="as-tl-cell"', 1)[1].split("</table>", 1)[0]
    assert "as-tl-item__sysicon" in cell
    assert "as-tl-chip--system" not in cell  # 아이콘 분기를 탔으면 칩은 안 나온다


def test_plain_text_entries_skip_html_parsing():
    """평문 기록은 BeautifulSoup 없이 처리되고, 결과는 파싱 경로와 완전히 같아야 한다."""
    import foms.services.as_content_safety as safety

    calls = []
    original = safety.BeautifulSoup

    def counting(*args, **kwargs):
        calls.append(args[0] if args else "")
        return original(*args, **kwargs)

    safety.BeautifulSoup = counting
    try:
        # 평문: 파싱 0회
        assert safety.as_content_html_to_text("평문 기록", already_sanitized=True) == "평문 기록"
        assert calls == []
        # 개행 보존은 fast path 에서도 동일
        assert safety.as_content_html_to_text("앞줄\n뒷줄", already_sanitized=True) == "앞줄\n뒷줄"
        assert calls == []
        # 태그·엔티티가 있으면 fast path 를 타지 않는다
        assert safety.as_content_html_to_text(
            "<div>앞</div><div>뒤</div>", already_sanitized=True) == "앞\n뒤"
        assert len(calls) == 1
        assert safety.as_content_html_to_text("a &amp; b", already_sanitized=True) == "a & b"
        assert len(calls) == 2
        # already_sanitized=False 는 언제나 sanitize+파싱 경로
        calls.clear()
        assert safety.as_content_html_to_text("평문 기록") == "평문 기록"
        assert calls, "원본 입력은 `<`가 없어도 sanitize 를 건너뛰면 안 된다"
    finally:
        safety.BeautifulSoup = original


# ---------------------------------------------------------------------------
# 5) T15 — 모바일 원탭 프리셋 4종 + 과도기 힌트 배너
# ---------------------------------------------------------------------------

_PRESETS = [
    ("call", "고객 부재중, 재연락 예정", "부재중"),
    ("action", "방문 조치 완료", "조치 완료"),
    ("schedule", "재방문 필요", "재방문 필요"),
    ("material", "자재 발주 필요", "자재 필요"),
]


def test_mobile_presets_render_above_quick_add(client):
    """프리셋 4종은 모바일 표면(d-md-none)에서 quick-add 폼 **위**에 스펙 순서대로 나온다.

    부재중이 첫 버튼인 이유는 현장 빈도다(스펙 §5.5) — 순서가 뒤집히면 엄지 위치가 어긋난다.
    """
    _login_as_admin(client, username="as_preset_admin")
    order_id = _create_as_order("프리셋")

    body = client.get(f"/erp/as/card-detail/{order_id}").get_data(as_text=True)
    presets = body.split('class="as-timeline__presets', 1)[1].split("</div>", 1)[0]
    assert "d-md-none" in presets
    # aria-label 은 role 없는 generic div 에서 무시된다 — 스크린리더에 묶음으로 읽히려면 둘 다
    assert 'role="group"' in presets
    assert 'aria-label="빠른 기록"' in presets
    assert [
        (chunk.split('data-type="', 1)[1].split('"', 1)[0],
         chunk.split('data-text="', 1)[1].split('"', 1)[0],
         chunk.split(">", 1)[1].split("<", 1)[0])
        for chunk in presets.split("<button")[1:]
    ] == _PRESETS
    # 초안 주입 대상(quick-add)보다 먼저 와야 엄지 동선이 위→아래로 이어진다
    assert body.index("as-timeline__presets") < body.index("as-timeline__quick-add")


def test_presets_hidden_without_edit_permission(client):
    """읽기 전용 사용자에겐 프리셋도 미렌더 — 주입 대상 quick-add 자체가 없다."""
    user = User(
        username="as_preset_viewer",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="DRAWING",
        name="뷰어",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    order_id = _create_as_order("프리셋 권한")
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    body = client.get(f"/erp/as/card-detail/{order_id}").get_data(as_text=True)
    assert "as-timeline__presets" not in body
    assert "as-timeline__quick-add" not in body


def test_preset_click_injects_draft_without_autosubmit():
    """프리셋은 초안 주입 + 유형 설정 + focus 까지만. 자동 전송은 수기 입력 원칙 위반이다."""
    js = _js()
    block = _timeline_block(js)
    anchor = block.index("e.target.closest('.as-tl-preset')")
    handler = block[anchor:block.index("});", anchor)]
    assert "typeEl.value = preset.dataset.type" in handler
    assert "textEl.focus()" in handler
    # 자동 전송 금지: 핸들러가 전송 경로를 건드리면 안 된다
    assert "submitQuickAdd" not in handler
    assert "fetch(" not in handler
    assert "requestSubmit" not in handler


def test_preset_injection_is_non_destructive():
    """타이핑 중이던 원고를 덮지 않고 뒤에 잇는다 — 무경고 value 대입은 입력 손실이다."""
    js = _js()
    block = _timeline_block(js)
    anchor = block.index("e.target.closest('.as-tl-preset')")
    handler = block[anchor:block.index("});", anchor)]
    assert "const prev = textEl.value.trim();" in handler
    assert "prev + ' ' + (preset.dataset.text || '')" in handler
    # 조건 없는 통째 덮어쓰기 재도입 금지
    assert "textEl.value = preset.dataset.text" not in handler


def test_preset_handler_guards_missing_timeline_ancestor():
    """`.as-timeline` 조상이 없으면 조용히 끝난다 — closest() null 에 .querySelector 하면 TypeError."""
    js = _js()
    block = _timeline_block(js)
    anchor = block.index("e.target.closest('.as-tl-preset')")
    handler = block[anchor:block.index("});", anchor)]
    assert "const timeline = preset.closest('.as-timeline');" in handler
    assert "timeline && timeline.querySelector('.as-timeline__quick-add')" in handler


def test_preset_types_match_quick_add_select_options():
    """프리셋 data-type 은 quick-add <select> 가 실제로 가진 값이어야 한다(무음 memo 폴백 방지)."""
    macros = _macros()
    select = macros.split('class="as-timeline__type', 1)[1].split("</select>", 1)[0]
    options = {chunk.split('"', 1)[0] for chunk in select.split('<option value="')[1:]}
    assert {log_type for log_type, _, _ in _PRESETS} <= options


def test_hint_banner_is_dismissed_once_via_localstorage(client):
    """과도기 배너: 서버는 숨긴 채 렌더하고, JS 가 localStorage 로 1회만 노출한다."""
    _login_as_admin(client, username="as_hint_admin")
    body = client.get("/erp/as").get_data(as_text=True)
    banner = body.split('id="as-timeline-hint"', 1)[1].split("</div>", 1)[0]
    assert "d-none" in banner  # 재방문자에게 깜빡임 없이 사라지려면 숨김 상태로 렌더
    assert "as-timeline-hint__dismiss" in body
    assert "AS 내용이 이력 형식으로 바뀌었습니다. 기존 내용은 '이전 기록'에 그대로 있습니다." in body

    js = _js()
    assert "foms_as_timeline_hint_dismissed" in js
    hint = js[js.index("as-timeline-hint"):]
    hint = hint[:hint.index("})();")]
    assert "localStorage.getItem('foms_as_timeline_hint_dismissed') === '1'" in hint
    assert "localStorage.setItem('foms_as_timeline_hint_dismissed', '1')" in hint
    assert hint.count("banner.remove()") == 2  # 이미 닫음 + 방금 닫음


def test_hint_banner_survives_blocked_storage():
    """사생활 모드 SecurityError 가 initAsDashboard 전체를 죽이면 안 된다(대시보드 JS 전멸).

    읽기/쓰기 **양쪽** 이 try 안에 있어야 한다. 폴백은 읽기 실패=미닫힘(배너 노출),
    쓰기 실패=세션 내 제거 유지 — 배너 제거는 catch 밖이라 저장 성공 여부와 무관하다.
    """
    js = _js()
    hint = js[js.index("as-timeline-hint"):]
    hint = hint[:hint.index("})();")]
    assert hint.count("try {") == 2
    assert hint.count("catch (storageErr)") == 2
    for call in ("localStorage.getItem(", "localStorage.setItem("):
        head = hint[:hint.index(call)]
        # 직전 `try {` 가 직전 `catch` 보다 가까워야 = 이 호출이 try 블록 안이다
        last_catch = head.rfind("catch (storageErr)")
        assert head.rfind("try {") > last_catch, call
    # 배너 제거는 catch 밖 — 저장 실패해도 이번 세션에서는 사라진다
    assert "}\n        banner.remove();" in hint


def test_preset_and_banner_styles_exist():
    """신규 클래스에 스타일 실재. 배너는 **클래스** 선택자여야 한다.

    id 특이도(100)로 스타일하면 유틸리티/테마 오버라이드가 이기지 못한다 —
    `#as-timeline-hint` 는 JS getElementById 훅으로만 남긴다.
    """
    css = _css(_CARD_CSS)
    for selector in (".as-timeline__presets", ".as-tl-preset", ".as-timeline-hint"):
        assert selector in css, selector
    assert "#as-timeline-hint" not in css


def test_dashboard_js_link_is_version_pinned():
    """SW staticCacheFirst — as-dashboard.js 링크도 `?v=` 없이는 실기기가 구버전을 계속 쓴다."""
    body = (_ROOT / "templates/cs/partials/as_dashboard_body.html").read_text(encoding="utf-8")
    link = [line for line in body.splitlines() if "js/cs/as-dashboard.js" in line]
    assert len(link) == 1
    assert "?v=" in link[0]


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


# ---------------------------------------------------------------------------
# 6) PC 테이블 레이아웃 붕괴 회귀 가드 (2026-07-28 실화면 핫픽스)
# ---------------------------------------------------------------------------
#
# 증상: /erp/as?tab=incomplete 에서 주소가 한 글자씩 세로로 흘러내리고(행 높이 810px)
# 확장 행의 입력 폼·제출 버튼이 통짜로 늘어나 라벨이 화면 밖으로 밀렸다.
# 원인: 셀 요약 두 줄이 .text-truncate(white-space:nowrap)라 AS 내용 셀의 내재
# 최대폭 = 기록 전문 한 줄 길이가 됐고, auto table-layout 이 여유폭을
# (max-content − min-content) 비율로 나눠주는 탓에 그 열 하나가 여유를 전부 흡수했다
# (실측 AS 내용 1342px / 테이블 2578px). 남은 열은 min-content 로 떨어지는데
# 주소는 break-word 라 min-content 가 '한 글자'다.
# 확장 행 colspan 은 원인이 아니다 — 열고 닫아도 열 폭이 변하지 않는 것을 실측 확인했다.


_COL_KEYS = (
    "order", "received", "visit", "completed", "manager", "workers",
    "customer", "address", "attach", "blueprint", "content", "status",
)


def test_table_layout_is_fixed_with_colgroup_widths():
    """열 폭 재분배 자체를 없앤 구조 — table-layout:fixed + colgroup 이 SSOT.

    auto 레이아웃이었을 때 AS 내용 셀의 nowrap 요약이 여유폭을 통째로 먹고
    나머지 열이 min-content 로 주저앉아 주소가 1글자씩 세로로 흘렀다.
    fixed 는 한 열의 내용이 다른 열 폭에 영향을 줄 경로 자체가 없다.
    """
    css = _css(_BODY_CSS)
    fixed = css.split("#as-dashboard-table {", 1)
    assert len(fixed) == 2, "#as-dashboard-table 레이아웃 규칙이 없다"
    assert "table-layout: fixed" in fixed[1].split("}", 1)[0]
    body = (_ROOT / "templates/cs/partials/as_dashboard_body.html").read_text(encoding="utf-8")
    for key in _COL_KEYS:
        assert '<col data-col-key="%s">' % key in body, key
        # 기본 폭은 CSS 가 소유(인라인 style 금지 규약 + JS 미실행 시 12등분 붕괴 방지)
        assert '#as-dashboard-table col[data-col-key="%s"]' % key in css, key
    # 구 인라인 폭 힌트는 남아 있으면 안 된다(두 SSOT 금지)
    thead = body.split("<thead>", 1)[1].split("</thead>", 1)[0]
    assert "style=" not in thead


def _min_widths() -> dict[str, int]:
    """리사이저 열별 하한 맵을 파싱한다."""
    js = (_ROOT / "static/js/cs/as-dashboard-columns.js").read_text(encoding="utf-8")
    schema = js.split("MIN_WIDTHS = {", 1)[1].split("}", 1)[0]
    out: dict[str, int] = {}
    for line in schema.splitlines():
        line = line.strip().rstrip(",")
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        out[key.strip()] = int(value.strip())
    return out


def test_column_floors_are_per_column_and_content_sized():
    """하한은 전역 일괄이 아니라 열별이고, 값은 그 열의 실제 표시 내용 기준이다.

    시공자(이름 2~3자)에 콘텐츠 열과 같은 하한을 주면 "안 줄어든다"는 실사용 불만이 된다
    — 실제로 workers 가 150 이었던 근거는 표시 내용이 아니라 편집 위젯 min-width 였다.
    """
    floors = _min_widths()
    assert set(floors) == set(_COL_KEYS), floors
    # 짧은 텍스트/컨트롤 열: 넉넉히 잡아도 100px 미만이어야 한다
    for key in ("order", "manager", "workers", "attach", "blueprint", "customer", "status"):
        assert floors[key] < 100, (key, floors[key])
    assert floors["workers"] <= 80
    # 콘텐츠 열: 2026-07-28 붕괴(주소 1글자 세로 흐름) 재발 방지선은 낮추지 않는다
    assert floors["address"] >= 180
    assert floors["content"] >= 200
    # 하한은 기본 폭(colgroup)을 넘지 않아야 한다 — 넘으면 기본 상태가 이미 하한 위반이다
    css = _css(_BODY_CSS)
    for key, floor in floors.items():
        rule = '#as-dashboard-table col[data-col-key="%s"] { width: ' % key
        default = int(css.split(rule, 1)[1].split("px", 1)[0])
        assert default >= floor, (key, default, floor)


def test_worker_widget_does_not_pin_the_column_width():
    """시공자 편집 위젯의 min-width 가 열 하한을 결정하면 안 된다.

    보기 모드는 열 폭을 따르고(min-width:0), 조작 폭은 편집 중에만 셀 밖으로 넘쳐 확보한다.
    """
    css = _css(_BODY_CSS)
    lst = css.split(".as-construction-worker-list {", 1)[1].split("}", 1)[0]
    assert "min-width: 0" in lst
    inp = css.split(".as-construction-worker-input {", 1)[1].split("}", 1)[0]
    assert "min-width: 0" in inp
    editing = css.split(".as-construction-worker-row.editing .as-construction-worker-edit {", 1)
    assert len(editing) == 2, "편집 중 조작 폭 확보 규칙이 없다"
    block = editing[1].split("}", 1)[0]
    assert "min-width" in block
    assert "z-index" in block  # 없으면 DOM 상 뒤에 오는 옆 셀이 덮는다


def test_expand_body_is_width_bounded():
    """확장 본문 상한 — 없으면 폼/버튼이 테이블 폭(≈1.8k)만큼 늘어나 라벨이 밀려난다."""
    css = _css(_BODY_CSS)
    rule = css.split(".as-tl-expand-body {", 1)
    assert len(rule) == 2, ".as-tl-expand-body 폭 상한 규칙이 없다"
    assert "max-width" in rule[1].split("}", 1)[0]


def test_quick_add_desktop_layout_is_scoped_to_expand_row():
    """PC 입력부 가로 배치는 확장 행 스코프 전용.

    베이스(.as-timeline__quick-add)의 세로 스택 + 전폭 버튼은 모바일 44px 터치 규약이라
    전역으로 풀면 모바일 카드 상세가 함께 깨진다.
    """
    css = _css(_BODY_CSS)
    assert ".as-tl-expand-body .as-timeline__submit" in css
    assert ".as-tl-expand-body .as-timeline__type" in css
    # 베이스 규칙은 세로 스택 그대로
    base = css.split(".as-timeline__quick-add {", 1)[1].split("}", 1)[0]
    assert "flex-direction: column" in base


def test_body_css_link_is_version_pinned():
    """CSS 도 SW staticCacheFirst 대상 — `?v=` 없이는 실기기가 구버전 스타일을 계속 쓴다."""
    body = (_ROOT / "templates/cs/partials/as_dashboard_body.html").read_text(encoding="utf-8")
    link = [line for line in body.splitlines() if "css/contexts/cs/as-dashboard-body.css" in line]
    assert len(link) == 1
    assert "?v=" in link[0]


# ---------------------------------------------------------------------------
# 7) 실사용 피드백 5건 (2026-07-28) — 확장 위치·배지 크기·비용 필터·리사이저·헤드 고정
# ---------------------------------------------------------------------------


def test_expand_body_sticks_to_the_right_edge():
    """확장 본문은 가로 스크롤포트 **오른쪽**에 고정된다(사용자 지정 방향).

    진입점('타임라인 N')이 표 오른쪽 끝 AS 내용 열이라 클릭 지점과 같은 쪽에 떠야 한다.
    margin-left:auto(셀 안 우측 배치) + sticky right:0(스크롤포트 우측 고정) 조합이며
    둘 중 하나만으론 부족하다 — margin 만 쓰면 scrollLeft 0 에서 화면 밖, sticky 만 쓰면
    셀 왼쪽에 붙는다. left 를 함께 주면 LTR 에서 left 가 이겨 우측 고정이 죽는다.
    """
    css = _css(_BODY_CSS)
    rule = css.split(".as-tl-expand-body {", 1)
    assert len(rule) == 2
    block = rule[1].split("}", 1)[0]
    assert "position: sticky" in block
    assert "right: 0" in block
    assert "margin-left: auto" in block
    assert "left:" not in block.replace("margin-left:", "")
    assert "max-width" in block


def _font_size(css: str, selector: str) -> float:
    """선택자 블록의 font-size(rem) 값."""
    block = css.split(selector + " {", 1)[1].split("}", 1)[0]
    return float(block.split("font-size:", 1)[1].split("rem", 1)[0].strip())


def test_badges_are_legible_sized():
    """배지/칩 글자 크기 하한 — "작아서 안 읽힌다" 피드백의 회귀 가드.

    0.75rem(12px) 미만으로 다시 줄면 실패한다. 상태 배지는 전역 .erp-pro-badge 가
    아니라 페이지 스코프 오버라이드여야 타 대시보드에 파급되지 않는다.
    """
    css = _css(_BODY_CSS)
    for selector in (".as-tl-chip", ".erp-as-billing-badge", ".as-billing-state",
                     ".as-tl-cell__anchor", ".as-tl-cell__recent"):
        assert _font_size(css, selector) >= 0.75, selector
    assert ".erp-as-dashboard .erp-pro-badge" in css


def test_billing_badge_is_a_filter_entrypoint():
    """상태 셀 비용 배지 클릭 = 그 비용 상태로 필터(발견성 보강).

    URL 조립을 매크로가 아니라 위임 핸들러가 하는 게 계약이다 — 같은 배지를
    판정 변경 API 응답도 렌더하는데 그쪽엔 탭/검색어 컨텍스트가 없다.
    """
    macros = _macros()
    assert "data-billing-filter=\"{{ 'undecided' if kind == 'undecided' else 'paid' }}\"" in macros
    assert 'role="button"' in macros and 'tabindex="0"' in macros
    js = _js()
    assert ".erp-as-billing-badge[data-billing-filter]" in js
    assert "buildAsDashboardUrl({ billing:" in js
    # role="button" 은 키보드 동작을 공짜로 주지 않는다
    assert "e.key !== 'Enter' && e.key !== ' '" in js


def test_column_resizer_is_wired():
    """리사이저 — DOM 계약(핸들)·저장소·G4 싱글톤·모바일 조기 반환·초기화 버튼."""
    body = (_ROOT / "templates/cs/partials/as_dashboard_body.html").read_text(encoding="utf-8")
    assert body.count('class="col-resize-handle"') == 11  # 마지막 열(상태)은 핸들 없음
    assert 'id="as-btn-reset-column-widths"' in body
    link = [ln for ln in body.splitlines() if "js/cs/as-dashboard-columns.js" in ln]
    assert len(link) == 1 and "?v=" in link[0]
    js = (_ROOT / "static/js/cs/as-dashboard-columns.js").read_text(encoding="utf-8")
    assert "window.__FOMS_AS_COLUMNS_BOUND" in js          # perf 가드 G4
    assert "foms:erp-shell-fragment-swapped" in js          # 스왑 재초기화
    assert "foms.asDashboard.columnWidths.v1" in js
    assert "setPointerCapture" in js                        # 표 밖으로 나가도 드래그 유지
    assert "DESKTOP_MIN_WIDTH = 768" in js                  # 모바일 무동작
    css = _css(_BODY_CSS)
    assert "#as-dashboard-table .col-resize-handle" in css
    assert "right: 0" in css.split("#as-dashboard-table .col-resize-handle {", 1)[1].split("}", 1)[0]


def test_sticky_thead_needs_a_scrollport_and_own_border():
    """헤드 고정 — 래퍼가 세로 스크롤포트가 돼야 sticky 가 붙을 자리가 생긴다.

    .erp-pro-table-wrapper 는 overflow-x:auto 라 세로축도 auto 지만 높이가
    콘텐츠만큼 자라 세로로 스크롤될 일이 없었다(= sticky 무동작). 또 collapse
    테이블에서 th 의 border-bottom 은 고정 중 사라지므로 inset 그림자로 대체한다.
    """
    css = _css(_BODY_CSS)
    wrapper = css.split(".erp-as-table-wrapper {", 1)
    assert len(wrapper) == 2, "래퍼 높이 상한 규칙이 없다"
    block = wrapper[1].split("}", 1)[0]
    assert "max-height" in block and "overflow-y: auto" in block
    # thead 가 아니라 th 에 걸려야 한다 — 두 개의 `#as-dashboard-table thead th` 블록 중
    # sticky 를 가진 쪽(핸들 앵커용 relative 블록이 아닌 쪽)을 골라 단언한다.
    th_blocks = [
        chunk.split("}", 1)[0]
        for chunk in css.split("#as-dashboard-table thead th {")[1:]
    ]
    sticky = [b for b in th_blocks if "position: sticky" in b]
    assert len(sticky) == 1, "th sticky 규칙이 없다(thead 가 아니라 th 여야 한다)"
    th_block = sticky[0]
    assert "top: 0" in th_block
    assert "background:" in th_block          # 투명하면 아래 행이 비쳐 보인다
    assert "box-shadow: inset 0 -2px 0" in th_block
    body = (_ROOT / "templates/cs/partials/as_dashboard_body.html").read_text(encoding="utf-8")
    assert "erp-pro-table-wrapper erp-as-table-wrapper" in body


def test_whole_content_cell_is_the_expand_target():
    """히트 영역 = 셀 전체(.as-tl-cell) — 앵커 줄·최근 줄 텍스트를 눌러도 열린다(스펙 §5.2).

    버튼만 대상이면 텍스트를 눌러도 반응이 없어 "안 열린다"로 읽힌다.
    셀 안 다른 인터랙티브 요소는 closest 가드로 가로채지 않는다. 컨테이너에
    role="button" 은 주지 않는다 — 안쪽에 실제 <button> 이 있어 인터랙티브 중첩(ARIA 위반)이다.
    """
    js = _js()
    block = js.split("window.__FOMS_AS_TIMELINE_BOUND = true;", 1)[1][:3000]
    handler = block.split("const cell = e.target.closest('.as-tl-cell');", 1)
    assert len(handler) == 2, "셀 전체 위임 셀렉터가 없다"
    guard = handler[1].split("const orderId", 1)[0]
    assert "e.target.closest('a, input, select, textarea')" in guard
    assert ".as-tl-cell__expand, .as-tl-cell__empty" in guard  # 두 버튼은 통과시킨다
    assert "cell.dataset.orderId" in handler[1] or "const orderId = cell.dataset.orderId" in js
    css = _css(_BODY_CSS)
    cursor = css.split(".as-tl-cell {", 1)[1].split("}", 1)[0]
    assert "cursor: pointer" in cursor
    macros = _macros()
    assert 'role="button"' not in macros.split("macro render_as_timeline_cell", 1)[1]


# ---------------------------------------------------------------------------
# 8) 기록 삭제(소프트) 배선 — 2026-07-28 사용자 요청(스펙 §8 YAGNI 해제)
# ---------------------------------------------------------------------------


def test_delete_button_renders_next_to_edit_with_same_gate():
    """휴지통은 연필과 **같은 노출 조건** — 수정 가능한 항목만 삭제 가능해야 계약이 맞다."""
    macros = _macros()
    entry = macros.split("macro render_as_timeline_entry", 1)[1].split("endmacro", 1)[0]
    gate = "{% if can_edit and not e.is_system and not e.is_legacy %}"
    assert gate in entry
    tail = entry.split(gate, 1)[1]
    assert 'class="as-tl-item__edit"' in tail
    assert 'class="as-tl-item__delete"' in tail
    assert 'aria-label="기록 삭제"' in tail


def test_delete_is_soft_and_hidden_in_one_place():
    """감추기는 build_as_timeline_view 한 곳 — 표면마다 거르면 배지 수와 노출이 갈린다."""
    src = (_ROOT / "foms/services/orders/as_log.py").read_text(encoding="utf-8")
    view = src.split("def build_as_timeline_view", 1)[1]
    assert 'if e.get("deleted") is True:' in view
    api = (_ROOT / "foms/api/cs/as_orders.py").read_text(encoding="utf-8")
    route = api.split("def api_as_log_delete", 1)[1].split("__all__", 1)[0]
    # 소프트 삭제: 플래그만 쓰고 항목을 리스트에서 빼지 않는다.
    # 쓰기는 _run_sd_mutation 이 잠근 사본(locked) 위에서 일어난다(append·patch 와 동일 계층).
    assert 'locked["deleted"] = True' in route
    assert 'locked["deleted_at"]' in route and 'locked["deleted_by"]' in route
    assert ".remove(" not in route and "del " not in route
    # 상태축을 안 건드리므로 cycle 전이가 아니라 sd mutation 으로 감싼다
    assert "policy_id=POLICY_AS_LOG_DELETE" in route
    assert "_run_sd_mutation(" in route
    # POST 라우트(DELETE 메서드 아님)
    assert 'methods=["POST"]' in api.split('as/log/<log_id>/delete"', 1)[1][:80]


def test_delete_and_patch_share_one_permission_guard():
    """수정·삭제 권한 매트릭스는 한 함수가 소유한다(각자 판정하면 갈린다)."""
    api = (_ROOT / "foms/api/cs/as_orders.py").read_text(encoding="utf-8")
    assert "def _resolve_as_log_entry(" in api
    for route in ("api_as_log_patch", "api_as_log_delete"):
        body = api.split("def %s(" % route, 1)[1].split("@erp_orders_as_bp.route", 1)[0]
        assert "_resolve_as_log_entry(log, log_id, user" in body, route
    guard = api.split("def _resolve_as_log_entry(", 1)[1].split("\ndef ", 1)[0]
    assert '"항목을 찾을 수 없습니다.", 404' in guard
    assert "400" in guard and "403" in guard


def test_delete_client_wiring_is_singleton_and_confirms():
    """클라: 싱글톤 위임 + confirm 1회 + 재진입 가드 + 셀 요약 통째 교체."""
    js = _js()
    block = js.split("window.__FOMS_AS_TIMELINE_BOUND = true;", 1)[1]
    handler = block.split(".as-tl-item__delete'", 1)
    assert len(handler) == 2, "삭제 위임 핸들러가 없다"
    body = handler[1].split("/** quick-add", 1)[0]
    assert "window.confirm(" in body
    assert "btn.dataset.busy === '1'" in body or "dataset.busy" in body
    assert "/as/log/' + encodeURIComponent(logId) + '/delete'" in body
    assert "item.remove();" in body
    assert "replaceAsCellSummary(orderId, data.cell_html)" in body
    # 증분 갱신(updateAsCellSummary)을 쓰면 지운 본문이 '최근 1줄'에 남는다
    assert "function replaceAsCellSummary" in block
    assert "cell.outerHTML = html" in block


def test_delete_cell_partial_reuses_the_list_macro():
    """응답 셀 HTML 은 목록과 같은 매크로 — 서버·클라 마크업이 갈라지지 않게."""
    partial = (_ROOT / "templates/cs/partials/as_timeline_cell_partial.html").read_text(
        encoding="utf-8")
    assert "render_as_timeline_cell" in partial
    api = (_ROOT / "foms/api/cs/as_orders.py").read_text(encoding="utf-8")
    assert "cs/partials/as_timeline_cell_partial.html" in api
