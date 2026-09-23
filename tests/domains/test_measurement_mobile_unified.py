"""실측 모바일 통합 화면(체크리스트 + 주문 카드 → 목록 + 바텀시트) — 화면 계약.

스펙: docs/specs/2026-09-23-measurement-mobile-unified-list_SPEC.md
목업: docs/plans/2026-09-23-measurement-mobile-unified-mockup.html

고정하는 회귀축:
- 담당자 탭 줄·모두 펼치기·담당 띠 접기·줄 → 시트(카드 노드 이동)의 표식
- 옛 카드 칸은 숨은 원본 칸(hidden)이고, 카드 id·실측 완료 버튼 표식은 그대로
- 처음에는 내 묶음만 펼침(없으면 첫 묶음), mine 모드는 탭·모두 펼치기 없음
- 줄의 📷 n = 이미지 미리보기 수(PDF 제외), 넘긴 주문은 "실측 완료" 알약
- CSS 는 덧붙이기만(기존 규칙 원문 해시 고정), 탭·시트 JS 는 await 없이 즉시 동작
- erp-quest-approve.js 는 복원 직전 이벤트 하나만 더 쏜다
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from types import SimpleNamespace

from flask import render_template

from foms.services.measurement.visit_check import build_measurement_glance_groups

from db import db_session
from models import Order, OrderAttachment, OrderScheduleDate
from tests.domains.test_measurement_mobile_glance import (
    _get,
    _glance,
    _prepare,
    _seed_three,
)

ROOT = Path(__file__).resolve().parents[2]

MOBILE_LIST = "templates/measurement/partials/mobile_list.html"
GLANCE_CSS = "static/css/contexts/measurement/measurement-mobile-glance.css"
TABS_JS = "static/js/measurement/mobile-glance-tabs.js"
SHEET_JS = "static/js/measurement/mobile-glance-sheet.js"
PARTS_JS = "static/js/measurement/mobile-glance-sheet-parts.js"
GLANCE_JS = "static/js/measurement/mobile-glance.js"
ENTRY_JS = "static/js/measurement/measurement-entry.js"
MOBILE_JS = "static/js/measurement/mobile.js"
QUEST_JS = "static/js/foms/erp-quest-approve.js"
LAYOUT_SCRIPTS = "templates/partials/shared/layout_scripts.html"
ERP_SHELL_JS = "static/js/runtime/erp-shell.js"

#: 통합 화면 이전 운영 CSS 원문(LF 정규화) — 2026-09-23 deploy 4d4df0baf 기준. 이 앞부분은 한 글자도 안 바뀐다.
GLANCE_CSS_BASE_SHA256 = "ac6115b95466017b047357312ee3401fa4974ce6df58aaa2d1de384265870512"
GLANCE_CSS_APPEND_MARKER = "/* ══ 통합 화면(체크리스트"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _missing(text: str, needles: list[str]) -> list[str]:
    return [n for n in needles if n not in text]


def _group_tags(glance: str) -> list[str]:
    return re.findall(r'<div class="foms-meas-glance__grp[^"]*" data-meas-glance-grp="[^"]*">', glance)


# ------------------------------------------------------------ A. 템플릿 표식

def test_template_has_unified_hooks():
    tpl = _read(MOBILE_LIST)
    required = [
        # 탭 줄
        'role="tablist" aria-label="담당자별 보기" data-meas-glance-tabs',
        'data-meas-glance-tab=""',
        'data-meas-glance-tab="{{ t.name }}"',
        "data-meas-glance-tab-count",
        'aria-controls="meas-glance-panel"',
        # 목록·모두 펼치기
        'id="meas-glance-panel" data-meas-glance-list',
        "data-meas-glance-ctl",
        "data-meas-glance-open-count",
        "data-meas-glance-all=",
        "data-meas-glance-all-label",
        # 담당 띠
        'data-meas-glance-grp="{{ g.manager_name }}"',
        "data-meas-glance-tog aria-expanded=",
        "foms-meas-glance__gchev",
        "foms-meas-glance__me",
        # 줄
        "data-meas-glance-handed",
        "foms-meas-glance__handed",
        'data-meas-glance-photos="{{ _pcn }}"',
        "(o.attachment_preview_items or [])|length",
        "foms-meas-glance__chev",
        # 시트 틀 1개
        'class="foms-meas-sheet" data-meas-sheet hidden',
        'id="meas-sheet" role="dialog" aria-modal="true"',
        "data-meas-sheet-mgr",
        "data-meas-sheet-pos",
        'data-meas-sheet-step="-1"',
        'data-meas-sheet-step="1"',
        "data-meas-sheet-close",
        "data-meas-sheet-check",
        "data-meas-sheet-slot",
        # 숨은 원본 칸 — 카드 표식은 그대로
        "data-meas-card-origin hidden",
        'id="meas-card-{{ o.id }}"',
        'data-measurement-mobile-order-id="{{ o.id }}"',
        "render_queue_card_v2(o,",
        # 이미지 저장은 그대로
        'class="foms-meas-glance__save" data-meas-export-image',
    ]
    assert _missing(tpl, required) == []
    assert tpl.count("data-meas-sheet ") == 1, "시트 틀은 하나만"
    assert "style=" not in tpl
    assert "사진 추가" not in tpl, "ERP 에 등록된 사진만 보여 준다(추가 버튼 없음)"


# ------------------------------------------------------------ B. HTTP 렌더

def test_unified_render_tabs_first_group_open_and_card_origin_hidden(client, monkeypatch):
    today = _prepare(client, monkeypatch)
    ids = _seed_three(today)
    body = _get(client)
    glance = _glance(body)

    assert "data-meas-glance-tabs" in glance
    assert re.search(r'data-meas-glance-tab=""[^>]*>\s*<span class="foms-meas-glance__tab-n">전체</span>\s*'
                     r'<span class="foms-meas-glance__tab-c" data-meas-glance-tab-count>1/3</span>', glance)
    assert re.search(r'data-meas-glance-tab="최진호"[^>]*>.*?data-meas-glance-tab-count>1/2<', glance, re.S)
    assert re.search(r'data-meas-glance-tab="김도윤"[^>]*>.*?data-meas-glance-tab-count>0/1<', glance, re.S)
    assert "담당 <b>2</b>명" in glance
    assert "3곳 · 실측 1 · 넘김 0" in glance

    # 보는 사람이 담당자가 아니면 첫 묶음만 펼친다.
    groups = _group_tags(glance)
    assert len(groups) == 2
    assert "is-closed" not in groups[0]
    assert "is-closed" in groups[1]
    assert "foms-meas-glance__me" not in glance

    # 옛 카드 칸은 숨은 원본 칸으로 남고 카드 id 는 한 번씩만.
    assert re.search(r'<section class="erp-measurement-mobile-list[^"]*"[^>]*data-meas-card-origin hidden>', body)
    for oid in ids.values():
        assert body.count(f'id="meas-card-{oid}"') == 1
    assert body.count("data-meas-sheet ") == 1


def test_unified_viewer_group_expanded_with_me_badge(client, monkeypatch):
    today = _prepare(client, monkeypatch, username="최진호")
    _seed_three(today)
    glance = _glance(_get(client))
    choi = [t for t in _group_tags(glance) if 'data-meas-glance-grp="최진호"' in t][0]
    kim = [t for t in _group_tags(glance) if 'data-meas-glance-grp="김도윤"' in t][0]
    assert "is-closed" not in choi and "is-me" in choi
    assert "is-closed" in kim
    assert '<span class="foms-meas-glance__me">나</span>' in glance


def test_unified_mine_mode_has_no_tabs_and_keeps_own_group_open(client, monkeypatch):
    today = _prepare(client, monkeypatch, username="최진호", role="STAFF", team="SALES")
    _seed_three(today)
    glance = _glance(_get(client, "/erp/measurement?mine=1"))
    assert "내 일정" in glance
    assert "data-meas-glance-tabs" not in glance
    assert "data-meas-glance-ctl" not in glance
    assert "data-meas-glance-tog" not in glance
    groups = _group_tags(glance)
    assert groups and all("is-closed" not in t for t in groups)
    assert "김도윤" not in glance


def test_unified_row_photo_count_is_images_only_and_handed_pill(client, monkeypatch):
    today = _prepare(client, monkeypatch)
    _seed_three(today)
    # 주문을 나중에 고치면 일정 동기 리스너가 손으로 넣은 일정 행을 다시 쓴다 — 처음부터 완료로 만든다.
    order = Order(received_date=today, customer_name="사진고객", phone="010-9999-0000", address="서울 강남구",
                  product="붙박이장", status="MEASURE", manager_name="박실측", is_erp_order=True,
                  measurement_completed=True,
                  structured_data={"parties": {"manager": {"name": "박실측"}},
                                   "items": [{"product_name": "붙박이장", "quantity": 1}]})
    db_session.add(order)
    db_session.flush()
    oid = order.id
    db_session.add(OrderScheduleDate(order_id=oid, kind="measurement", date=today, source="beta_schedule"))
    for name, ftype in (("a.jpg", "image"), ("b.png", "image"), ("c.pdf", "document")):
        db_session.add(OrderAttachment(order_id=oid, filename=name, file_type=ftype, category="measurement",
                                       file_size=1, storage_key=f"orders/{oid}/{name}"))
    db_session.commit()

    glance = _glance(_get(client))
    row = glance.split(f'data-meas-glance-row="{oid}"', 1)[1].split("</a>", 1)[0]
    assert "data-meas-glance-handed" in glance.split(f'data-meas-glance-row="{oid}"', 1)[1][:40]
    assert "foms-meas-glance__handed" in row and "실측 완료" in row
    assert 'data-meas-glance-photos="2"' in row, "사진 수는 이미지 미리보기만 센다(PDF 제외)"
    assert "has-pc" in row
    assert glance.count("data-meas-glance-photos=") == 1, "사진 없는 줄에는 📷 표시가 없다"
    assert "넘김 1" in glance


# ------------------------------------------------------------ C. CSS 덧붙이기만

def test_glance_css_is_append_only():
    css = _read(GLANCE_CSS).replace("\r\n", "\n")
    idx = css.index(GLANCE_CSS_APPEND_MARKER)
    base = css[:idx].rstrip("\n") + "\n"
    assert hashlib.sha256(base.encode("utf-8")).hexdigest() == GLANCE_CSS_BASE_SHA256, (
        "통합 화면 이전 규칙 원문이 바뀌었다 — 새 규칙은 파일 끝에 덧붙이기만 한다"
    )
    added = css[idx:]
    required = [
        ".foms-meas-glance--unified {",
        "overflow: visible;",
        ".foms-meas-glance__tabs {",
        "position: sticky;",
        ".foms-meas-glance__tab[aria-selected=\"true\"]",
        ".foms-meas-glance__panel {",
        "touch-action: pan-y;",
        ".foms-meas-glance__ctl {",
        ".foms-meas-glance__grp.is-closed .foms-meas-glance__rows",
        ".foms-meas-glance__go > .foms-meas-glance__pc",
        ".foms-meas-glance__handed {",
        ".erp-measurement-mobile-list[data-meas-card-origin][hidden]",
        ".foms-meas-sheet {",
        ".foms-meas-sheet__vcheck[aria-pressed=\"true\"]",
        ".foms-meas-sheet__slot .queue-card__attachments.foms-queue-card-v2__attachments",
        "html.foms-meas-sheet-open",
    ]
    assert _missing(added, required) == []
    # 시트는 하단 탭(1030) 위, 주문 진행 오프캔버스(1045)·사진 미리보기(10600) 아래.
    z = int(re.search(r"\.foms-meas-sheet \{[^}]*z-index: (\d+);", added).group(1))
    assert 1030 < z < 1045


# ------------------------------------------------------------ D. JS 계약

def test_tabs_js_contract():
    js = _read(TABS_JS)
    required = [
        "__FOMS_MEAS_GLANCE_TABS_BOUND",
        "SWIPE_MIN = 60",
        "SWIPE_RATIO = 1.5",
        "Math.abs(dx) > SWIPE_MIN && Math.abs(dx) > Math.abs(dy) * SWIPE_RATIO",
        "[data-meas-visit-toggle], .foms-meas-glance__call",
        "searchParams.set('mgr', name)",
        "history.replaceState",
        "localStorage",
        "is-solo",
        "foms:quest-approve:before-restore",
        "__fomsQuestApproveRestore",
        "foms:erp-shell-fragment-swapped",
        "FomsMeasGlance.reveal",
    ]
    assert _missing(js, required) == []
    assert "await" not in js and "jQuery" not in js and "innerHTML" not in js
    # localStorage 는 전부 try 안에서만 만진다.
    for m in re.finditer(r"localStorage\.", js):
        assert "try {" in js[max(0, m.start() - 80):m.start()], js[m.start() - 80:m.start() + 20]
    assert len(js.splitlines()) < 300


def test_sheet_js_contract():
    js = _read(SHEET_JS)
    required = [
        "__FOMS_MEAS_GLANCE_SHEET_BOUND",
        "document.getElementById('meas-card-' + id)",
        "document.createComment(",
        "measSheet",
        "history.pushState(",
        "history.back()",
        "keepBase()",
        "unkeep()",
        "parts().decorate(card, sheet)",
        "parts().setInert(sheet, true)",
        "parts().setInert(sheet, false)",
        "global-image-viewer",
        "GlobalImageViewer.close",
        "foms:meas-glance:visit",
        "focus_order",
        "api.reveal(focus",
        "restoredOrderId",
        "foms-meas-sheet-open",
        "' 담당'",
        "(i + 1) + ' / ' + sibs.length",
    ]
    assert _missing(js, required) == []
    assert "await" not in js and "jQuery" not in js and "innerHTML" not in js
    # 체크는 줄의 체크 칸을 대신 누른다 — 시트가 API 를 따로 부르지 않는다.
    assert "fetch(" not in js and "btn.click()" in js
    assert len(js.splitlines()) < 300


def test_mobile_js_leaves_focus_order_to_unified_sheet():
    js = _read(MOBILE_JS)
    guard = js.index("root.querySelector('[data-meas-glance]')")
    assert guard < js.index("focusCard.scrollIntoView")


def test_quest_approve_announces_before_restore_scroll():
    js = _read(QUEST_JS)
    assert "'foms:quest-approve:before-restore'" in js
    assert "cancelable: true" in js
    assert "window.__fomsQuestApproveRestore = detail" in js
    body = js.split("function restorePlace()", 1)[1].split("\n  }\n", 1)[0]
    assert body.index("announceRestore(saved)") < body.index("card.scrollIntoView")
    assert js.count("dispatchEvent(") == 1
    assert "erp-quest-approve.js') }}?v=20260923e" in _read(LAYOUT_SCRIPTS)


def test_erp_shell_popstate_skips_overlay_entries():
    """셸 popstate 는 겹층(시트) 기록 사이 이동에서 같은 화면을 다시 읽지 않는다.

    window 의 popstate 는 등록 순서대로 불린다(캡처로도 앞지를 수 없음 — 실측 Chromium 149).
    셸이 먼저 등록되므로 시트 쪽에서 막을 수 없고, 셸이 표식을 보고 건너뛰어야 한다.
    """
    js = _read(ERP_SHELL_JS)
    handler = js.split("window.addEventListener('popstate', function (e) {", 1)[1].split("\n  });", 1)[0]
    assert handler.index("shouldKeepOnPop(e && e.state)") < handler.index("navigateByShell(url, { fromPopState: true })")
    assert "js/runtime/erp-shell.js') }}?v=20260923e" in _read(LAYOUT_SCRIPTS)


def test_sheet_parts_js_contract():
    js = _read(PARTS_JS)
    required = [
        "window.FomsMeasSheetParts",
        "att.hidden = !has",
        "'실측 사진'",
        "'사진 ' + n",
        "meta.parentNode.insertBefore(att, head.nextSibling)",
        ".foms-measure-done",
        "#global-image-viewer, .offcanvas, .modal",
        "setAttribute('inert', '')",
        "removeAttribute('inert')",
        "fomsShellKeep",
        "searchParams.delete('focus_order')",
        "syncRenderedUrl",
    ]
    assert _missing(js, required) == []
    assert "await" not in js and "innerHTML" not in js and "jQuery" not in js
    assert len(js.splitlines()) < 300
    entry = _read(ENTRY_JS)
    assert (entry.index("mobile-glance-tabs.js") < entry.index("mobile-glance-sheet-parts.js")
            < entry.index("mobile-glance-sheet.js?"))


def test_review_fixes_in_js():
    sheet = _read(SHEET_JS)
    init = sheet.split("function init()", 1)[1]
    # A3: 복원 표식은 읽은 즉시 지운다(같은 문서의 다음 ?focus_order 를 막지 않게).
    assert init.index("var restored = api.restoredOrderId;") < init.index("delete api.restoredOrderId;")
    # A12: focus_order 는 주소에서 지운 뒤 시트를 연다.
    assert init.index("parts().dropFocusParam();") < init.index("open(focus);")
    # A2: 새로고침 뒤 시트 기록 위면 시트를 되살린다.
    assert "if (show(hs.measSheet)) st.pushed = true;" in init
    # A6: Esc 는 캡처 단계에서, 미리보기가 열려 있으면 시트를 닫지 않는다.
    esc = sheet.split("document.addEventListener('keydown'", 1)[1].split("}, true);", 1)[0]
    assert "viewerOpen()" in esc
    # A7: 닫을 때 그 줄이 보이게 펼친 뒤 초점.
    close = sheet.split("function close(fromPop)", 1)[1].split("\n    }\n", 1)[0]
    assert close.index("api.reveal(id, { scroll: false })") < close.index("go.focus(")
    tabs = _read(TABS_JS)
    # A4: 복원 값은 같은 주소일 때만.
    assert "saved.path !== window.location.pathname + window.location.search" in tabs
    # A13: 새 누름은 클릭 막기를 물려받지 않는다.
    down = tabs.split("document.addEventListener('pointerdown'", 1)[1].split("});", 1)[0]
    assert "suppressUntil = 0;" in down
    # 탭 주소 변경을 셸에 알린다(A1 판정 키).
    assert "shell.syncRenderedUrl()" in tabs
    assert "path: saved.path" in _read(QUEST_JS)
    # A5: 시트가 열려 있으면 실패 안내는 전역 토스트.
    glance = _read(GLANCE_JS)
    msg = glance.split("function showMsg", 1)[1].split("if (!panel) return;", 1)[0]
    assert "foms-meas-sheet-open" in msg and "typeof window.fomsFlashToast === 'function'" in msg


def test_erp_shell_keep_requires_same_rendered_page():
    """A1: 표식만으로 건너뛰면 다른 화면에 갔다 뒤로 와 표식 기록에 닿을 때 화면이 안 바뀐다.

    셸이 마지막으로 그린 화면 키를 기억하고, 표식 + 지금 주소 키 == 그 키일 때만 건너뛴다.
    """
    js = _read(ERP_SHELL_JS)
    keep = js.split("function shouldKeepOnPop(state)", 1)[1].split("\n  }\n", 1)[0]
    assert "state.fomsShellKeep" in keep
    assert "getCacheKey(window.location.href) === lastRenderedKey" in keep
    apply = js.split("function applyFragmentToMain(html, swapUrl)", 1)[1].split("\n  }\n", 1)[0]
    assert "lastRenderedKey = getCacheKey(swapUrl);" in apply
    assert "var lastRenderedKey = getCacheKey(window.location.href);" in js
    assert "window.FOMS_ERP_SHELL.syncRenderedUrl = syncRenderedUrl;" in js
    handler = js.split("window.addEventListener('popstate', function (e) {", 1)[1].split("\n  });", 1)[0]
    assert "shouldKeepOnPop(e && e.state)" in handler
    assert "e.state.fomsShellKeep" not in handler, "표식만 보는 옛 조건이 남으면 A1 이 재발한다"


def _row(i: int, mgr: str, done: bool = False) -> dict:
    return {"id": i, "customer_name": f"고객{i}", "manager_name": mgr, "measurement_visit_done": done,
            "structured_data": {}, "alerts": {}, "attachment_preview_items": [], "attachments_count": 0}


def _render_split(app, *, mine: bool) -> str:
    """같은 담당(최진호)이 두 묶음으로 갈린 목록을 파셜만 직접 그린다(HTTP 는 담당 순 정렬이라 안 갈린다)."""
    rows = [_row(1, "최진호", True), _row(2, "김도윤"), _row(3, "최진호")]
    with app.test_request_context("/erp/measurement"):
        return render_template(
            "measurement/partials/mobile_list.html", mobile_queue_rows=rows,
            mobile_glance_groups=build_measurement_glance_groups(rows), measurement_visit_date="2026-04-08",
            can_mark_measurement_visit=True, selected_date="2026-04-08", today_date="2026-04-08",
            current_user=SimpleNamespace(name="최진호"), erp_mine_only=mine,
        )


def test_split_manager_groups_one_tab_summed_and_both_expanded_for_me(app):
    html = _render_split(app, mine=False)
    groups = _group_tags(html)
    assert [re.search(r'grp="([^"]*)"', t).group(1) for t in groups] == ["최진호", "김도윤", "최진호"]
    assert html.count('data-meas-glance-tab="최진호"') == 1, "한 담당은 탭 하나"
    assert re.search(r'data-meas-glance-tab="최진호"[^>]*>.*?data-meas-glance-tab-count>1/2<', html, re.S)
    choi = [t for t in groups if "최진호" in t]
    assert all("is-closed" not in t and "is-me" in t for t in choi), "내 묶음은 둘 다 펼침"
    assert "is-closed" in [t for t in groups if "김도윤" in t][0]
    # B9: 펼침 수는 서버 렌더에서 센다(담당 이름 기준 — 두 묶음이어도 1명).
    assert "펼침 <b data-meas-glance-open-count>1</b>" in html
    assert 'data-meas-glance-all="open"' in html


def test_split_manager_groups_mine_mode_all_open(app):
    html = _render_split(app, mine=True)
    groups = _group_tags(html)
    assert len(groups) == 3 and all("is-closed" not in t for t in groups)
    assert "data-meas-glance-tabs" not in html and "data-meas-glance-tog" not in html


def test_old_visit_summary_removed():
    """B2: 예전 요약 줄('완료'=넘김)과 새 머리('실측'=체크)는 뜻이 다른 숫자 두 벌 — 목업대로 뺐다."""
    assert 'class="foms-visit-summary"' not in _read(MOBILE_LIST)


def test_review_css_rules_appended():
    added = _read(GLANCE_CSS).replace("\r\n", "\n").split(GLANCE_CSS_APPEND_MARKER, 1)[1]
    fixes = added.split("리뷰 반영", 1)[1]
    required = [
        ".foms-meas-sheet__panel {\n  height: calc(",
        ".foms-meas-sheet__body {\n  flex: 1 1 auto;",
        ".foms-meas-sheet__slot .queue-card__meta a {",
        "min-height: 44px;",
        ".foms-meas-sheet__ph-h {",
        ".queue-card__action > .foms-measure-done",
        "padding-bottom: 88px;",
        ".foms-meas-glance--unified .foms-meas-glance__save {\n  min-height: 44px;",
    ]
    assert _missing(fixes, required) == []


def test_sheet_photo_header_is_moved_with_attachments_not_duplicated():
    """이전·다음으로 같은 카드가 시트에 다시 들어올 때마다 "실측 사진 · 사진 n" 제목이 늘던 회귀(2026-09-23).

    예전에는 사진 칸만 meta 뒤로 옮기고 제목을 남겨, 다음 호출에서 제목을 새로 만들었다(브라우저 재현 1→6개).
    제목과 사진 칸을 함께 옮기고, 사진 칸 바로 앞이 아닌 남은 제목은 지운다.
    """
    js = _read("static/js/measurement/mobile-glance-sheet-parts.js")
    body = js.split("function placePhotos", 1)[1].split("function placeHanded", 1)[0]
    assert "var head = photoHeader(att);" in body
    assert body.index("photoHeader(att)") < body.index("insertBefore(att")
    assert "insertBefore(head, meta.nextSibling)" in body
    assert "removeChild(h)" in body
