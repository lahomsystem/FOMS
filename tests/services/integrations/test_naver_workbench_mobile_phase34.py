# -*- coding: utf-8 -*-
"""네이버 수집 워크벤치 폰 3·4단계(2026-09-29 목업) 계약.

폰(≤767.98px)에서만 바꾸고 **데스크톱 화면은 그대로**다. 여기서 무는 것:

* 3단계 — 행을 누르면 상세가 목록 아래가 아니라 **전체 화면 층**(#wb-layer, fixed · 자기 스크롤 ·
  body 잠금)으로 열린다. 위 막대 `‹ 목록 · 이름 · 상태 · N / M · 이전/다음`, 아래 막대 주 버튼 하나 +
  더보기 시트. 막대·시트의 버튼은 pane 원래 버튼을 **대신 누르는** 대리 버튼이다(id 는 원래 버튼
  한 벌). 뒤로 가기 = 목록(이전/다음은 기록을 바꾸고 쌓지 않는다).
* 4단계 — 이력 탭 ADMIN 수집 상태: 한 줄 카드 + [관리] 시트(같은 카드를 시트로 옮긴다), 워터마크
  사람 말 시각, 지금 수집 보조 모양, 과거 소급 확인 줄.

대조표의 "다른 값 먼저 · 같은 값 접기" 는 만들지 않았다 — pane 마크업에 행별 차이 표식이 없고
(발송 줄의 `wb-sendline--gap` 하나뿐) 비교 규칙을 화면에서 새로 만들지 않는다는 결정이다.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

from foms.web.admin import naver_ingest
from tests.services.integrations.test_naver_dock_width_live import _extract_function, _needs_node
from tests.services.integrations.test_naver_workbench_mobile import (
    CSS,
    JS,
    PHONE_MEDIA,
    TEMPLATE,
    TRIAGE_PATH,
    _empty_strips,
    _media_block,
    _outside_media,
    _rule,
)
from tests.services.integrations.test_naver_workbench_v3_contract import (  # noqa: F401
    _login,
    workbench_on,
)

PANE_PATH = "/admin/naver-ingest/triage/pane"
#: pane 액션 줄의 원래 버튼 — 대리 버튼이 누르는 대상이라 문서에 **한 번씩만** 있어야 한다.
ACTION_IDS = ("wb-create", "wb-confirm", "wb-dispatch", "wb-cancel", "wb-refresh", "wb-review-done")


def _css() -> tuple[str, str]:
    """(폰 미디어 블록, 미디어 쿼리 밖 규칙)."""
    css = CSS.read_text(encoding="utf-8").replace("\r\n", "\n")
    return _media_block(css, PHONE_MEDIA), _outside_media(css)


def _js() -> str:
    return JS.read_text(encoding="utf-8").replace("\r\n", "\n")


def _body(js: str, name: str) -> str:
    return _extract_function(js, name)


def _seed_rows():
    """처리 목록 줄 둘 — 발주확인 전 하나, 주문이 붙어 값이 다른 하나."""
    from db import db_session
    from models import Order
    from tests.services.integrations.test_naver_workbench import _collected

    first = _collected(order_no="N-P34-1", product="층 붙박이장", amount=1284000, place_status="")
    linked = _collected(order_no="N-P34-2", product="층 서랍장", amount=342000,
                        address="경기 성남시 12", tel="010-5555-5821")
    order = Order(received_date="2026-09-28", customer_name="이수취", phone="010-5555-5812",
                  address="경기 성남시 12 (다른 동)", product="서랍장", status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    linked.order_id = order.id
    linked.sync_status = "LINKED"
    db_session.commit()
    return first, linked


def _patch_ingest(monkeypatch, *, success_to="2026-09-29T08:25:57.924513+09:00", error=None,
                  expires_on="2027-02-23", days_left=148) -> None:
    monkeypatch.setattr(naver_ingest, "_watermark_view", lambda db: {
        "last_success_to": success_to, "last_run_at": "2026-09-29T08:26:00+09:00",
        "last_success_to_text": "", "last_run_at_text": "2026-09-29 08:26",
        "last_error": error, "last_summary": {"collected": 3, "skipped": 1, "pending_review": 0}})
    monkeypatch.setattr(naver_ingest, "_expiry_view",
                        lambda db: {"expires_on": expires_on, "days_left": days_left})


# --------------------------------------------------------------------------- #
# 3단계 — 전체 화면 상세 층
# --------------------------------------------------------------------------- #

def test_phone_layer_is_full_screen_with_its_own_scroll_and_body_lock():
    """폰: 층은 닫혀 있으면 없다. 열리면(body.wb-detail-open) 화면 전체 · 자기 스크롤 · body 잠금.
    z-index 는 모달 백드롭(1050) 위 — 층이 만든 쌓임 맥락 안의 pane 모달이 백드롭에 덮이지 않는다."""
    phone, _ = _css()

    assert "    .wb-layer { display: none; }" in phone
    assert "body.wb-detail-open { overflow: hidden; }" in phone
    layer = _rule(phone, "    body.wb-detail-open .wb-layer")
    for decl in ("position: fixed;", "inset: 0;", "overflow-y: auto;", "overscroll-behavior: contain;",
                 "display: flex;"):
        assert decl in layer, decl
    assert int(re.search(r"z-index: (\d+);", layer).group(1)) > 1050
    assert "background: rgba(20, 23, 28, .55);" in _rule(phone, "    .wb-layer .modal.show")
    assert "transform" not in layer, "transform 은 안쪽 fixed 모달의 기준을 층으로 바꾼다"
    # 위·아래 막대는 층 안에서 붙어 다닌다. 누르는 곳 44px 이상.
    assert "position: sticky;" in _rule(phone, "    .wb-layer__bar")
    acts = _rule(phone, "    .wb-layer__acts")
    assert "position: sticky;" in acts and "bottom: 0;" in acts and "safe-area-inset-bottom" in acts
    assert "min-height: 52px;" in _rule(phone, "    .naver-workbench .wb-layer__primary")
    assert "min-height: 48px;" in _rule(phone, "    .wb-layer__step")
    # 원래 액션 버튼은 폰에서 숨기만 한다(대리 버튼이 누른다) — `.btn` 규칙(inline-flex)보다 세야 한다.
    assert "#wb-pane .wb-acts > button.btn { display: none; }" in phone


def test_desktop_keeps_the_pane_in_the_grid_and_hides_every_phone_part():
    """데스크톱: 층은 `contents` 라 pane 이 예전처럼 격자 둘째 칸이다. 폰 부품은 숨기기만 한다."""
    _, everywhere = _css()

    assert ".wb-layer { display: contents; }" in everywhere
    assert ".wb-layer__bar,\n.wb-layer__acts { display: none; }" in everywhere
    assert ".wb-icard { display: none; }" in everywhere
    assert ".wb-ingest__phone { display: none; }" in everywhere
    for phone_only in ("wb-detail-open", ".wb-more__", "#wb-run-now", ".wb-asheet",
                       "#wb-pane .wb-acts > button", "#wb-ingest-status {"):
        assert phone_only not in everywhere, phone_only


def test_layer_wraps_the_swapped_pane_and_keeps_bars_outside_it(client, workbench_on, monkeypatch):
    """층 = 위 막대 → #wb-pane(응답으로 통째로 갈리는 조각) → 아래 막대 → 더보기 시트.
    막대는 조각 **바깥**이라 교체에도 남는다. 원래 액션 버튼 id 는 문서에 한 번씩만 있다."""
    _empty_strips(monkeypatch)
    _, linked = _seed_rows()
    _login(client)

    body = client.get(TRIAGE_PATH, query_string={"tab": "work", "link_id": linked.id}).get_data(as_text=True)

    marks = ['id="wb-layer"', 'class="wb-layer__bar"', 'id="wb-pane-back"', 'id="wb-layer-name"',
             'id="wb-layer-prev"', 'id="wb-layer-next"', '<div id="wb-pane"', 'class="wb-layer__acts"',
             'id="wb-layer-primary"', 'id="wb-more-open"', 'id="wb-more"']
    at = [body.index(mark) for mark in marks]
    assert at == sorted(at), dict(zip(marks, at))
    bar = body[body.index('class="wb-layer__bar"'):body.index('<div id="wb-pane"')]
    for step, label in (("wb-layer-prev", "이전 주문"), ("wb-layer-next", "다음 주문")):
        tag = bar[bar.index(f'id="{step}"'):]
        tag = tag[:tag.index(">")]
        assert f'aria-label="{label}"' in tag and 'aria-disabled="true"' in tag, tag
    assert 'aria-label="목록으로 돌아가기"' in bar and "목록" in bar
    assert 'id="wb-layer-state"' in bar and 'id="wb-layer-pos"' in bar, "상태 · N / M 자리"
    assert '<h2 class="wb-layer__name" id="wb-layer-name" tabindex="-1">' in bar
    for action in ACTION_IDS:
        assert body.count(f'id="{action}"') == 1, action
    assert "data-proxy-for" not in body, "대리 버튼은 JS 가 지금 pane 에서 만든다(서버는 안 심는다)"
    # 조각 계약 그대로 — /triage/pane 의 루트는 여전히 #wb-pane 하나이고 막대를 싣지 않는다.
    frag = client.get(PANE_PATH, query_string={"link_id": linked.id}).get_data(as_text=True)
    assert frag.lstrip().startswith('<div id="wb-pane"')
    assert "wb-layer" not in frag and 'id="wb-more"' not in frag


def test_more_sheet_is_a_modal_dialog_like_the_status_sheet(client, workbench_on, monkeypatch):
    """더 할 일 시트 = 2단계 상태 시트와 같은 꼴의 네이티브 dialog(열 때 제목, 닫기 44px)."""
    _empty_strips(monkeypatch)
    _seed_rows()
    _login(client)

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)
    opener = body[body.index('<button type="button" class="wb-layer__more"'):]
    opener = opener[:opener.index("</button>")]
    for attr in ('aria-haspopup="dialog"', 'aria-expanded="false"', 'aria-controls="wb-more"'):
        assert attr in opener, attr
    sheet = body[body.index('<dialog class="wb-hsheet wb-more"'):]
    sheet = sheet[:sheet.index("</dialog>")]
    assert 'id="wb-more" aria-labelledby="wb-more-title" aria-modal="true"' in sheet
    assert 'id="wb-more-title" tabindex="-1"' in sheet and 'id="wb-more-close" aria-label="닫기"' in sheet
    assert '<ul class="wb-more__list" id="wb-more-list"></ul>' in sheet


def test_phase34_markup_adds_no_inline_style():
    """3·4단계로 더한 마크업(층·막대·시트·한 줄 카드·관리 시트·폰 전용 줄)에 인라인 스타일이 없다."""
    markup = TEMPLATE.read_text(encoding="utf-8")
    regions = [
        markup[markup.index('<div class="wb-layer" id="wb-layer">'):markup.index("{# 결정 6: 불가역 액션")],
        markup[markup.index("{% set wm = ingest_status.watermark %}"):markup.index("</section>",
                                                                                    markup.index("wb-backfill__confirm"))],
    ]
    for region in regions:
        assert region and 'style="' not in region, region[:80]


# --------------------------------------------------------------------------- #
# 3단계 JS — 배선(문자열) + 순수 함수(Node 로 실제 실행)
# --------------------------------------------------------------------------- #

def test_js_wires_open_close_step_and_proxy():
    js = _js()

    for entry in ("'wb-pane-back': backToList", "'wb-layer-prev': function (btn) { stepLayer(btn); }",
                  "'wb-layer-next': function (btn) { stepLayer(btn); }", "'wb-more-open': openMoreSheet",
                  "'wb-asheet-open': openAdminSheet"):
        assert entry in js, entry
    # 행 열기: 폰이면 층 기록을 쌓고 층을 연다(행 열기 길 = markCurrent → loadPane → pushPaneState).
    row = _body(js, "onRowClick")
    assert "pushPaneState(id, href, isPhone());" in row and "revealPaneOnPhone();" in row
    assert "openLayer();" in _body(js, "revealPaneOnPhone")
    opener = _body(js, "openLayer")
    assert "document.body.classList.add('wb-detail-open');" in opener and "setBackgroundInert(true);" in opener
    # 이전/다음: 같은 길로 열되 기록은 바꾼다(뒤로 가기 = 목록).
    step = _body(js, "stepLayer")
    assert "markCurrent(row);" in step and "loadPane(id, href)" in step
    assert "replacePaneState(id, href, true);" in step and "pushPaneState" not in step
    # 닫기: 층 기록이 맨 위면 뒤로 가기와 같은 길, 초점은 방금 연 행으로.
    back = _body(js, "backToList")
    assert "window.history.back();" in back and "leaveLayer();" in back
    leave = _body(js, "leaveLayer")
    assert "classList.remove('wb-detail-open')" in leave and "setBackgroundInert(false);" in leave
    assert "focusQuietly(row);" in leave
    pop = _body(js, "onPopState")
    assert "layerPopAction(state)" in pop and "leaveLayer();" in pop and "openLayer();" in pop
    # 조각 교체 · 통째 다시 그리기 · 잠금 뒤 막대를 다시 채운다.
    assert "syncLayer();" in _body(js, "swapPane")
    assert "syncLayer();" in _body(js, "lockPaneActions")
    refresh = _body(js, "softRefresh")
    assert "afterRefreshLayer(layerScroll);" in refresh and "openAdminSheet();" in refresh
    # 대리 버튼: 원래 버튼의 click 을 부른다. 시트 안이면 시트부터 닫는다(Bootstrap 모달이 inert 밑에 뜬다).
    proxy = _body(js, "proxyClick")
    assert "target.click();" in proxy and "closeSheet('wb-more');" in proxy
    assert "if (btn.hasAttribute('data-proxy-for')) {" in _body(js, "onClick")
    assert "document.addEventListener('hidden.bs.modal', onProxyModalHidden);" in js
    assert "document.addEventListener('close', onSheetClose, true);" in js
    # 시트 줄: 못 누르는 것은 숨기지 않는다 — aria-disabled + 이유(aria-describedby).
    item = _body(js, "moreItem")
    assert "btn.setAttribute('aria-disabled', 'true');" in item
    assert "btn.setAttribute('aria-describedby', fxRef + line.id);" in item and "innerHTML" not in item


def test_js_phase34_state_is_declared_before_init_runs():
    """defer 스크립트라 init() 이 곧바로 돈다 — 폰에서 상세를 연 채 들어오면 init 이 층을 열며
    PRIMARY_ORDER·SHEETS 를 읽는다. 대입이 init 호출 아래 있으면 undefined 다(FONT_STEPS 와 같은 함정)."""
    js = _js()
    first_call = js.index("        init();\n")
    for name in ("var PRIMARY_ORDER = ['wb-confirm', 'wb-create', 'wb-dispatch'];", "var SHEETS = {",
                 "var proxyReturn = null;"):
        assert js.index(name) < first_call, name


def _run_node(names: tuple[str, ...], scenario: str) -> dict:
    js = _js()
    head = js[js.index("var PRIMARY_ORDER"):js.index("];", js.index("var PRIMARY_ORDER")) + 2]
    script = "\n".join([head] + [_extract_function(js, name) for name in names] + [scenario])
    with tempfile.TemporaryDirectory(prefix="naver-wb-p34-") as tmp:
        path = pathlib.Path(tmp) / "p34.js"
        path.write_text(script, encoding="utf-8")
        proc = subprocess.run([shutil.which("node"), str(path)], capture_output=True, text=True,
                              encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@_needs_node
def test_primary_is_the_first_open_of_confirm_create_dispatch():
    """주 버튼 = 발주확인 → 주문 만들기 → 발송처리 중 **열린**(disabled 아닌) 첫 번째. 전부 잠기면 ''
    (주 버튼 없이 더보기만 — 음성 대조군). 판정은 원래 버튼의 disabled 만 읽는다."""
    result = _run_node(("pickPrimaryId",), """
function look(map) { return function (id) { return map.hasOwnProperty(id) ? map[id] : null; }; }
process.stdout.write(JSON.stringify({
  confirm: pickPrimaryId(look({'wb-confirm': {disabled: false}, 'wb-create': {disabled: false}})),
  create: pickPrimaryId(look({'wb-confirm': {disabled: true}, 'wb-create': {disabled: false},
                              'wb-dispatch': {disabled: false}})),
  dispatch: pickPrimaryId(look({'wb-confirm': {disabled: true}, 'wb-create': {disabled: true},
                                'wb-dispatch': {disabled: false}})),
  missing: pickPrimaryId(look({'wb-dispatch': {disabled: false}})),
  none: pickPrimaryId(look({'wb-confirm': {disabled: true}, 'wb-create': {disabled: true},
                            'wb-dispatch': {disabled: true}, 'wb-refresh': {disabled: false}}))
}));""")
    assert result == {"confirm": "wb-confirm", "create": "wb-create", "dispatch": "wb-dispatch",
                      "missing": "wb-dispatch", "none": ""}


@_needs_node
def test_step_counter_follows_the_visible_list_order():
    """N / M 와 앞뒤는 지금 보이는 줄 순서다. 목록 밖 집은 자리가 없다(-1 · 앞뒤 없음)."""
    result = _run_node(("layerStep",), """
var a = {n: 'a'}, b = {n: 'b'}, c = {n: 'c'}, other = {n: 'x'};
function view(s) { return {at: s.at, total: s.total, prev: s.prev && s.prev.n, next: s.next && s.next.n}; }
process.stdout.write(JSON.stringify({
  first: view(layerStep([a, b, c], a)), mid: view(layerStep([a, b, c], b)),
  last: view(layerStep([a, b, c], c)), off: view(layerStep([a, b, c], other)),
  none: view(layerStep([a, b, c], null))
}));""")
    assert result["first"] == {"at": 0, "total": 3, "prev": None, "next": "b"}
    assert result["mid"] == {"at": 1, "total": 3, "prev": "a", "next": "c"}
    assert result["last"] == {"at": 2, "total": 3, "prev": "b", "next": None}
    assert result["off"] == result["none"] == {"at": -1, "total": 3, "prev": None, "next": None}


@_needs_node
def test_back_from_detail_goes_to_the_list():
    """폰 뒤로/앞으로: 층 기록 → 열기, 우리 목록 기록(선택 있든 없든) → 닫기, 남의 기록 → 예전 길."""
    result = _run_node(("safeId", "layerPopAction"), """
process.stdout.write(JSON.stringify({
  layer: layerPopAction({wbLinkId: '12', wbLayer: true}),
  list: layerPopAction({wbLinkId: null}),
  listWithRow: layerPopAction({wbLinkId: '12'}),
  layerNoId: layerPopAction({wbLinkId: null, wbLayer: true}),
  foreign: layerPopAction(null),
  foreignObj: layerPopAction({other: 1})
}));""")
    assert result == {"layer": "open", "list": "close", "listWithRow": "close", "layerNoId": "close",
                      "foreign": "legacy", "foreignObj": "legacy"}


# --------------------------------------------------------------------------- #
# 4단계 — ADMIN 수집 상태 한 줄 카드 + 관리 시트
# --------------------------------------------------------------------------- #

def _history(client, monkeypatch, **patch) -> str:
    _empty_strips(monkeypatch)
    _patch_ingest(monkeypatch, **patch)
    _login(client)
    return client.get(TRIAGE_PATH, query_string={"tab": "all"}).get_data(as_text=True)


def _card(body: str) -> str:
    start = body.index('<div class="wb-icard')
    return body[start:body.index("</div>", start)]


def test_admin_card_is_one_row_with_manage_sheet(client, workbench_on, monkeypatch):
    """한 줄 카드 = 상태 · 마지막 수집 · 인증 만료(남은 일) + [관리]. 관리 시트는 같은 카드를 담을 빈 자리다.
    카드·시트는 수집 상태 카드(#wb-ingest-status) **앞**이다 — 그 카드를 자르는 기존 계약이 그대로 선다."""
    body = _history(client, monkeypatch)

    card = _card(body)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", card)).strip()
    assert text == "정상 마지막 수집 09-29 08:26 인증 만료 2027-02-23 (148일) 관리", text
    manage = card[card.index('<button type="button" class="wb-icard__manage"'):]
    for attr in ('id="wb-asheet-open"', 'aria-haspopup="dialog"', 'aria-expanded="false"',
                 'aria-controls="wb-asheet"'):
        assert attr in manage, attr
    sheet = body[body.index('<dialog class="wb-hsheet wb-asheet"'):]
    sheet = sheet[:sheet.index("</dialog>")]
    assert 'id="wb-asheet" aria-labelledby="wb-asheet-title" aria-modal="true"' in sheet
    assert 'id="wb-asheet-close" aria-label="닫기"' in sheet
    assert '<div class="wb-asheet__slot" id="wb-asheet-slot"></div>' in sheet
    assert body.index('class="wb-icard') < body.index('id="wb-asheet"') < body.index('id="wb-ingest-status"')
    for control in ("wb-run-now", "wb-backfill-from", "wb-backfill-to", "wb-backfill-run", "wb-expiry-edit",
                    "wb-expiry-input", "wb-run-result", "wb-backfill-note", "wb-expiry-note"):
        assert body.count(f'id="{control}"') == 1, control


def test_admin_card_says_failure_unregistered_and_due(client, workbench_on, monkeypatch):
    """실패면 빨간 `실패`, 만료일이 없으면 `미등록`, 7일 이하면 경고 색. 정상 카드에는 셋 다 없다."""
    card = _card(_history(client, monkeypatch, error="네이버 401", expires_on=None, days_left=None))
    assert "wb-icard--err" in card and ">실패<" in card and "인증 만료일 미등록" in card
    assert "wb-icard--due" not in card

    _patch_ingest(monkeypatch, days_left=5, expires_on="2026-10-04")
    due = _card(client.get(TRIAGE_PATH, query_string={"tab": "all"}).get_data(as_text=True))
    assert "wb-icard--due" in due and "(5일)" in due and "wb-icard--err" not in due


@pytest.mark.parametrize("raw", ["2026-09-29T08:25:57.924513+09:00", "2026-09-28T23:25:57+00:00"])
def test_watermark_reads_as_human_kst_time(client, workbench_on, monkeypatch, raw):
    """워터마크 원문(ISO) → `9월 29일 08:25:57까지 받음`. 다른 오프셋이어도 KST 로 바꿔 읽는다
    (원문 문자열을 자르면 UTC 값에서 날짜·시각이 틀린다). 조회는 늘지 않는다 — 같은 값의 꼴만 바꾼다."""
    body = _history(client, monkeypatch, success_to=raw)
    section = body[body.index('id="wb-ingest-status"'):body.index("</section>", body.index('id="wb-ingest-status"'))]

    assert '<div class="wb-ingest__v wb-ingest__phone wb-ingest__human">9월 29일 08:25:57까지 받았어요</div>' in section
    assert "9월 29일 08:25:57 뒤에 들어온 주문을 바로 받아와요." in section
    assert f'<div class="wb-ingest__v wb-ingest__desk">{raw}</div>' in section, "데스크톱 원문 줄은 그대로"


def test_watermark_missing_says_not_yet(client, workbench_on, monkeypatch):
    body = _history(client, monkeypatch, success_to=None)
    assert "wb-ingest__human\">아직 없음</div>" in body
    assert "뒤에 들어온 주문을 바로 받아와요" not in body, "시각을 모르면 약속을 말하지 않는다"


def test_backfill_confirm_line_matches_the_code(client, workbench_on, monkeypatch):
    """확인 줄의 세 사실은 코드가 지킨다 — 상한 = backfill.MAX_RANGE, 이미 받은 건 멱등 skip, 워터마크 불변."""
    from foms.services.integrations.naver_commerce import backfill

    body = _history(client, monkeypatch)
    line = body[body.index('wb-backfill__confirm">'):]
    line = line[len('wb-backfill__confirm">'):line.index("</div>")]
    assert line == (f"최대 {backfill.MAX_RANGE.days}일 · 이미 받은 주문은 건너뜀 · "
                    "‘받아온 시각’은 바뀌지 않아요")
    assert body.index("wb-backfill__confirm") < body.index('id="wb-backfill-run"'), "날짜 칸 아래 · 버튼 위"
    assert "skipped: int = 0            # 이미 있던 건(멱등 skip)" in pathlib.Path(backfill.__file__).read_text(
        encoding="utf-8")


def test_history_viewers_without_admin_get_no_card_or_sheet(client, workbench_on, monkeypatch):
    """음성 대조군 — 이력을 여는 회계팀은 수집 상태 카드가 없으니 한 줄 카드·관리 시트도 없다."""
    from tests.services.integrations.test_naver_workbench import _login as _team_login

    _empty_strips(monkeypatch)
    _patch_ingest(monkeypatch)
    _team_login(client, role="MANAGER", team="ACCOUNTING")
    body = client.get(TRIAGE_PATH, query_string={"tab": "all"}).get_data(as_text=True)

    assert 'data-active-tab="all"' in body
    for absent in ('class="wb-icard', 'id="wb-asheet"', 'id="wb-ingest-status"'):
        assert absent not in body, absent


def test_phone_admin_sheet_css_moves_the_card_and_softens_run_now():
    """폰: 카드는 제자리에서 숨고 시트 안에서만 보인다. 지금 수집은 큰 초록이 아니라 연한 보라 테두리.
    날짜 칸 16px(아이폰 확대 방지) · 누르는 곳 44px."""
    phone, _ = _css()

    assert "    #wb-ingest-status { display: none; }" in phone
    assert "display: block;" in _rule(phone, "    .wb-asheet #wb-ingest-status")
    run = _rule(phone, "    .wb-asheet #wb-run-now")
    assert "background: #f3f4ff;" in run and "border: 1px solid #4a55b8;" in run and "min-height: 44px;" in run
    assert ".wb-asheet .wb-ingest__desk { display: none; }" in phone
    assert ".wb-asheet .wb-ingest__phone { display: block; }" in phone
    dates = phone.split("    .wb-asheet .wb-backfill__input,\n    .wb-asheet .wb-expiry__input {")[1].split("}")[0]
    assert "font-size: calc(16px * var(--wb-fs, 1));" in dates and "min-height: 44px;" in dates
    assert "min-height: 44px;" in _rule(phone, "    .wb-icard__manage")
