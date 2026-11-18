"""폰(터치 + 992 미만 창)에서 절대 안 보이는 넓은 창 표면을 서버가 보내지 않는 계약 (2026-11-16).

배경(원장 docs/plans/2026-11-09-tablet-production-ui-ledger.md §29 다음 일): 태블릿 쪽(9eefe36ca —
:func:`feature_flags.wants_desktop_queue_surfaces`)을 고친 뒤에도 폰은 태블릿 가로 화면과 모바일 셸이 끄는
PC 표면을 받아 숨겼다(같은 가짜 자료 감사: 실측 조각 1.2MB 중 986KB · 생산 보드 451KB 중 211KB · 시공 354KB 중 212KB).

설계: 두 표면 모두 창 폭 992 미만이면 안 보인다 — 태블릿 화면은 base ``display:none`` + 표시 식
``(min-width: 992px) and (orientation: landscape) and (pointer: coarse)`` 하나, PC 표면은 모바일 셸
``(max-width: 991.98px)`` 은닉. 서버는 ``foms_ptr=coarse`` + ``foms_vw=narrow`` 로 확인될 때만 뺀다
(:func:`feature_flags.wants_wide_viewport_surfaces`) — 마우스 PC 는 좁힌 창이어도 그대로. 뺀 화면엔
``data-foms-wide-surface-omitted`` 표식과 되돌림 스크립트(foms-wide-surface-recover.js)가 하나 남아, 창이
992 이상이 되면(폴더블 펼침 · 화면 분할 · 작은 태블릿 가로) 지금 화면을 다시 받는다.

폰이 쓰는 것은 남긴다(의존 확인 결과): 실측 PC 표(모바일 [이미지 저장]이 찍는다 — 펼친 줄 속만 뺌) · 도면
.dw-process-map(workbench-dashboard.js 화면 판정) · 주문 dashboard_styles.html(모바일도 쓰는 CSS).
출고 PC 표면(.erp-shipment-desktop-shell — 셸 CSS 가 992 미만 창에서 표면째 숨긴다)은 2026-11-18 부터 껍데기 · 추천 창 ·
지도 창만 남기고 속을 자리표로 바꾼다: 폰 [AS 추천]은 자리표의 표 줄 키(data-ship-as-rec-rows)로, 폰 [저장]은 누른 그때
ship_pc_table=1 로 표를 받아 끼운다(test_shipment_phone_pc_table_deferred.py).
AS PC 표(d-md-block)는 폰 가로(768 이상)에서만 보여 폰엔 자리표만 보내고, 창이 768 이상이면 화면이 as_pc_table=1 로 받아 끼운다
(2026-11-17 — 768 기준 쿠키가 없어 서버 대신 화면이 판정한다. 아래 AS 늦게 받기 시험).

여기서 잠그는 것:
  1. 판정 진리표 — 쿠키가 하나라도 없거나 이상하면 전부 렌더(True).
  2. 폰: 화면별로 뺀 표면 0 · 남길 것 그대로 · 표식 1개 · 되돌림 스크립트 1개.
  3. 대조군(쿠키 없음 · 태블릿 가로 · 큰 태블릿 세로 · 마우스 PC · 좁힌 마우스 창 · 이상값): 표식 0 · 표면 그대로.
  4. 렌더 전 304 키 재료가 폰 ↔ 넓은 창을 가른다(ETag 를 에코해도 넓은 창이 표면 든 본문을 받는다).
  5. 템플릿 표식 ↔ 되돌림 JS 선택자 · 창 폭 식 · 셸 API 배선이 짝으로 있다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services import feature_flags
from models import User

ROOT = Path(__file__).resolve().parents[2]
SHELL_HEADERS = {"X-FOMS-ERP-SHELL": "1"}
MARKER_ATTR = "data-foms-wide-surface-omitted"
RECOVER_JS = "js/runtime/foms-wide-surface-recover.js"
MARKER_TPL = "partials/shared/wide_surface_omitted_marker.html"

PHONE = {"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "915"}
SMALL_TABLET_PORTRAIT = {"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "1180"}

# (경로, 템플릿, 폰에서 빠져야 하는 것, 폰에도 남아야 하는 것)
SCREENS = [
    (
        "/erp/dashboard",
        "templates/orders/partials/dashboard_main.html",
        ('class="foms-split-enabled"', '<header class="erp-pro-header">', "erp-pro-card--process-map",
         '<div class="erp-dashboard-layout">', "foms-tablet-workqueue-wrap", 'class="foms-tdash-top'),
        ("foms-channel-mark.css", "foms-mobile-v2-dashboard", '<div class="foms-shell-desktop-only">'),
    ),
    (
        "/erp/measurement",
        "templates/measurement/partials/dashboard_main.html",
        ('<div class="foms-tablet-measure-split"',),
        ('id="measurement-dashboard-table"', "erp-measurement-mobile-v2"),
    ),
    (
        "/erp/drawing-workbench",
        "templates/drawing/partials/workbench_dashboard_body.html",
        ("erp-drawing-dashboard-desktop-card", '<section class="foms-drawing-workshop"'),
        ("dw-process-map", 'id="batchAssignModal"'),
    ),
    (
        "/erp/production/dashboard",
        "templates/production/partials/dashboard_body.html",
        ('<div class="tablet-prod-board">', '<div class="foms-production-legacy-queue">'),
        ("foms-mobile-v2-dashboard",),
    ),
    (
        "/erp/construction/dashboard",
        "templates/construction/partials/dashboard_body.html",
        ('<section class="foms-construction-workmode"', '<section class="foms-cons-first"',
         '<div class="foms-construction-legacy-queue">'),
        ("foms-mobile-v2-dashboard",),
    ),
    (
        "/erp/shipment",
        "templates/shipment/partials/dashboard_main.html",
        ('<div class="foms-ship-pcbar"', "foms-tablet-shipgrid-wrap", 'id="shipment-dashboard-table"',
         "erp-shipment-desktop-filter", "measurement-panel-item"),
        ("erp-shipment-desktop-shell", "data-shipment-as-recommend-open", 'id="shipmentAsRecommendModal"',
         'id="scheduleMapModal"', "data-ship-pc-table-deferred", 'data-ship-pc-table-src="/erp/shipment?'),
    ),
    (
        "/erp/as",
        "templates/cs/partials/as_dashboard_body.html",
        ('class="foms-as-compare', 'id="as-dashboard-table"'),
        ("data-as-pc-table-deferred", 'data-as-pc-table-src="/erp/as?'),
    ),
]


class _StubRequest:
    def __init__(self, cookies: dict[str, str] | None) -> None:
        self.cookies = cookies


# --- 1. 판정 진리표 -----------------------------------------------------------


@pytest.mark.parametrize(
    ("cookies", "expected", "why"),
    [
        ({}, True, "쿠키 없음 — 첫 요청·쿠키 차단: 전부 렌더"),
        ({"foms_ptr": "coarse"}, True, "창 모름 — 넓을 수 있다"),
        ({"foms_vw": "narrow"}, True, "포인터 모름 — 마우스 PC 일 수 있다"),
        ({"foms_ptr": "coarse", "foms_vw": "narrow"}, False, "폰 · 작은 태블릿 세로 — 넓은 창 표면이 안 보인다"),
        ({"foms_ptr": "coarse", "foms_vw": "wide"}, True, "태블릿 가로 — 태블릿 화면이 보인다"),
        ({"foms_ptr": "coarse", "foms_vw": "tall"}, True, "큰 태블릿 세로 — 992 이상"),
        ({"foms_ptr": "fine", "foms_vw": "narrow"}, True, "좁힌 마우스 창 — 지금 출력 그대로"),
        ({"foms_ptr": "fine", "foms_vw": "wide"}, True, "광폭 마우스 PC"),
        ({"foms_ptr": "coarse", "foms_vw": "NARROW"}, True, "미지의 값 — 전부 렌더"),
        ({"foms_ptr": "coarse", "foms_vw": ""}, True, "빈 값 — 전부 렌더"),
        ({"foms_ptr": "none", "foms_vw": "narrow"}, True, "포인터 없음 — 전부 렌더"),
    ],
)
def test_wants_wide_viewport_surfaces_truth_table(cookies, expected, why) -> None:
    got = feature_flags.wants_wide_viewport_surfaces(_StubRequest(cookies))
    assert got is expected, f"{why}: {cookies} -> {got}"


def test_wants_wide_viewport_surfaces_safe_fallbacks() -> None:
    assert feature_flags.wants_wide_viewport_surfaces(_StubRequest(None)) is True
    assert feature_flags.wants_wide_viewport_surfaces() is True


def test_phone_omission_never_overlaps_tablet_or_pc_omissions() -> None:
    """폰 생략이 걸리는 쿠키에선 태블릿 가로 · 광폭 마우스 생략이 안 걸린다(표식 두 종이 서로 다른 화면에만 남는다)."""
    for ptr in ("coarse", "fine", "", "x"):
        for vw in ("wide", "tall", "narrow", "", "x"):
            req = _StubRequest({"foms_ptr": ptr, "foms_vw": vw})
            if not feature_flags.wants_wide_viewport_surfaces(req):
                assert feature_flags.wants_mobile_width_surfaces(req) is True, (ptr, vw)
                assert feature_flags.wants_desktop_queue_surfaces(req) is True, (ptr, vw)
                assert feature_flags.wants_coarse_pointer_surfaces(req) is True, (ptr, vw)


# --- 2·3. 대시보드 렌더 ----------------------------------------------------------


def _login(client, monkeypatch, username: str, *, cohort: bool = True) -> None:
    user = User(
        username=username,
        password=generate_password_hash("x"),
        role="ADMIN",
        team="CS",
        name=username,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id) if cohort else "9999999")
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _body(client, path: str, cookies: dict[str, str]) -> str:
    for name, value in cookies.items():
        client.set_cookie(name, value, domain="localhost")
    response = client.get(f"{path}?view=fragment", headers=SHELL_HEADERS)
    assert response.status_code == 200, f"{path} -> {response.status_code}"
    return response.get_data(as_text=True)


def _uname(prefix: str, path: str, tag: str) -> str:
    return prefix + path.strip("/").replace("/", "_").replace("-", "_") + "_" + tag


@pytest.mark.parametrize(("path", "_tpl", "gone", "kept"), SCREENS)
@pytest.mark.parametrize(("tag", "cookies"), [("phone", PHONE), ("small-tablet-portrait", SMALL_TABLET_PORTRAIT)])
def test_phone_omits_wide_surfaces_keeps_phone_dependencies(
    client, monkeypatch, path, _tpl, gone, kept, tag, cookies
) -> None:
    _login(client, monkeypatch, _uname("pvs_on_", path, tag))

    body = _body(client, path, cookies)

    for mark in gone:
        assert mark not in body, f"{path} {tag}: 좁은 창에 안 보이는 {mark!r} 가 남았다"
    for mark in kept:
        assert mark in body, f"{path} {tag}: 폰이 쓰는 {mark!r} 가 빠졌다"
    assert body.count(MARKER_ATTR) == 1, f"{path} {tag}: 넓은 창 되돌림 표식이 정확히 1개여야 한다"
    assert body.count(RECOVER_JS) == 1, f"{path} {tag}: 되돌림 스크립트가 정확히 1개여야 한다"
    # <div>/<tr>/<td> 짝이 맞아야 한다(게이트가 여닫는 태그 한쪽만 감싸면 뒤 화면이 무너진다).
    for tag_name in ("div", "tr", "td"):
        assert body.count(f"<{tag_name}") == body.count(f"</{tag_name}>"), (path, tag_name)


#: 대조군 — 폰이 아니면 표식이 없고 빠지는 표면도 지금 판정 그대로다.
CONTROLS = [
    ("no-cookies", {}),
    ("tablet-landscape", {"foms_ptr": "coarse", "foms_vw": "wide", "foms_scr": "1280"}),
    ("big-tablet-portrait", {"foms_ptr": "coarse", "foms_vw": "tall", "foms_scr": "1366"}),
    ("mouse-pc", {"foms_ptr": "fine", "foms_vw": "wide", "foms_scr": "1920"}),
    ("narrow-mouse-window", {"foms_ptr": "fine", "foms_vw": "narrow", "foms_scr": "1920"}),
    ("odd-value", {"foms_ptr": "coarse", "foms_vw": "NARROW", "foms_scr": "915"}),
]


@pytest.mark.parametrize(("path", "_tpl", "_gone", "_kept"), SCREENS)
@pytest.mark.parametrize(("tag", "cookies"), CONTROLS, ids=[c[0] for c in CONTROLS])
def test_controls_have_no_phone_marker(client, monkeypatch, path, _tpl, _gone, _kept, tag, cookies) -> None:
    _login(client, monkeypatch, _uname("pvs_ctl_", path, tag))

    body = _body(client, path, cookies)

    assert MARKER_ATTR not in body, f"{path} {tag}: 폰이 아닌데 넓은 창 생략 표식이 남았다"
    assert RECOVER_JS not in body, f"{path} {tag}: 폰이 아닌데 되돌림 스크립트가 실렸다"


@pytest.mark.parametrize(("path", "_tpl", "gone", "_kept"), SCREENS)
def test_no_cookie_and_odd_value_render_everything_phone_would_lose(
    client, monkeypatch, path, _tpl, gone, _kept
) -> None:
    """안전 폴백: 쿠키가 없거나 이상하면 폰에서 빼는 표면을 전부 그린다(화면이 비지 않고 느려지기만)."""
    _login(client, monkeypatch, _uname("pvs_nc_", path, "nc"))
    nocookie = _body(client, path, {})
    for mark in gone:
        # 시공 첫 화면/작업 모드는 라우트가 하나만 고른다 — 둘 중 하나면 된다.
        if mark.startswith('<section class="foms-construction-workmode"'):
            continue
        if mark == '<section class="foms-cons-first"':
            assert mark in nocookie or '<section class="foms-construction-workmode"' in nocookie, path
            continue
        assert mark in nocookie, f"{path}: 쿠키 없음인데 {mark!r} 가 빠졌다"


@pytest.mark.parametrize(("path", "_tpl", "gone", "_kept"), SCREENS)
def test_legacy_cohort_phone_is_untouched(client, monkeypatch, path, _tpl, gone, _kept) -> None:
    """코호트 밖(legacy)은 모바일 셸 은닉 CSS 가 없다 — 폰 쿠키여도 표식이 없다."""
    _login(client, monkeypatch, _uname("pvs_legacy_", path, "ph"), cohort=False)

    body = _body(client, path, PHONE)

    assert MARKER_ATTR not in body, f"{path}: 코호트 밖 폰에 넓은 창 생략 표식이 남았다"


def test_as_phone_pc_table_comes_back_on_request(client, monkeypatch) -> None:
    """AS 폰: 자리표의 주소(as_pc_table=1)로 다시 받으면 창 구간과 무관하게 PC 표가 오고 자리표는 없다.

    폰 가로(768~991)는 foms_vw=narrow 그대로라 쿠키로는 못 가른다 — 화면(as-dashboard.js)이 이 주소로 받아 표만 끼운다.
    """
    _login(client, monkeypatch, "pvs_as_pc_table")
    body = _body(client, "/erp/as", PHONE)
    m = re.search(r'data-as-pc-table-src="([^"]+)"', body)
    assert m, "폰 AS 에 PC 표 자리표 주소가 없다"
    src = m.group(1).replace("&amp;", "&")
    assert "as_pc_table=1" in src and "foms_shell=fragment" in src, src
    forced = client.get(src, headers=SHELL_HEADERS)
    assert forced.status_code == 200
    html = forced.get_data(as_text=True)
    assert 'id="as-dashboard-table"' in html
    assert "data-as-pc-table-deferred" not in html
    js = (ROOT / "static/js/cs/as-dashboard.js").read_text(encoding="utf-8")
    assert "[data-as-pc-table-deferred]" in js and "(min-width: 768px)" in js
    assert "foms:as-pc-table-loaded" in js
    assert "foms:as-pc-table-loaded" in (ROOT / "static/js/cs/as-dashboard-columns.js").read_text(encoding="utf-8")


# --- 4. 렌더 전 304 키 재료 -------------------------------------------------------


def test_fragment_version_key_material_includes_wide_viewport_bit(app) -> None:
    from foms.services.common import fragment_revalidation as fr

    got = {}
    for bucket in ("narrow", "wide", "tall"):
        with app.test_request_context("/", headers={"Cookie": f"foms_ptr=coarse; foms_vw={bucket}"}):
            got[bucket] = fr._surface_hint_material()
    assert got["narrow"]["wide_viewport"] is False
    assert got["wide"]["wide_viewport"] is True and got["tall"]["wide_viewport"] is True
    with app.test_request_context("/", headers={"Cookie": "foms_ptr=fine; foms_vw=narrow"}):
        assert fr._surface_hint_material()["wide_viewport"] is True


@pytest.mark.parametrize("wide_vw", ["wide", "tall"])
def test_fragment_etag_differs_between_phone_and_wide_window(client, monkeypatch, wide_vw) -> None:
    """좁은 창에서 받은 ETag 를 넓어진 창이 에코해도 304 가 아니라 표면이 든 전체 본문을 받는다."""
    path = "/erp/production/dashboard"
    _login(client, monkeypatch, "pvs_etag_" + wide_vw)
    for name, value in SMALL_TABLET_PORTRAIT.items():
        client.set_cookie(name, value, domain="localhost")
    narrow = client.get(f"{path}?view=fragment", headers=SHELL_HEADERS)
    etag = narrow.headers.get("ETag")
    assert etag and MARKER_ATTR in narrow.get_data(as_text=True)

    client.set_cookie("foms_vw", wide_vw, domain="localhost")
    wide = client.get(f"{path}?view=fragment", headers={**SHELL_HEADERS, "If-None-Match": etag})

    assert wide.status_code == 200
    assert wide.headers.get("ETag") != etag
    body = wide.get_data(as_text=True)
    assert MARKER_ATTR not in body
    if wide_vw == "wide":
        assert '<div class="tablet-prod-board">' in body
    else:
        assert '<div class="foms-production-legacy-queue">' in body


# --- 5. 템플릿 ↔ JS ↔ 셸 배선 -----------------------------------------------------


@pytest.mark.parametrize(("_path", "tpl", "_gone", "_kept"), SCREENS)
def test_each_screen_includes_marker_once(_path, tpl, _gone, _kept) -> None:
    code = re.sub(r"\{#.*?#\}", "", (ROOT / tpl).read_text(encoding="utf-8"), flags=re.S)
    assert code.count(MARKER_TPL) == 1, tpl
    assert (
        "{% if erp_mobile_v2_enabled and not wide_viewport_surfaces %}"
        "{% include '" + MARKER_TPL + "' %}{% endif %}"
    ) in code, tpl


def test_marker_ships_recover_script_run_once() -> None:
    marker = (ROOT / "templates" / MARKER_TPL).read_text(encoding="utf-8")
    assert f"<template {MARKER_ATTR}></template>" in marker
    tag = re.search(r"<script[^>]*foms-wide-surface-recover\.js[^>]*>", marker).group(0)
    assert " defer" in tag and 'data-foms-run-once="wide-surface-recover"' in tag
    assert "?v=" in tag


def test_recover_js_matches_marker_boot_query_and_shell_api() -> None:
    js = (ROOT / "static" / RECOVER_JS).read_text(encoding="utf-8")
    boot = (ROOT / "static/js/runtime/foms-viewport-hint-boot.js").read_text(encoding="utf-8")
    shell = (ROOT / "static/js/runtime/erp-shell.js").read_text(encoding="utf-8")
    assert f"'[{MARKER_ATTR}]'" in js
    # 서버의 narrow = 부트가 쿠키를 쓰는 식과 같은 식이어야 넓어지는 순간과 쿠키가 바뀌는 순간이 같다.
    assert "window.matchMedia('(min-width: 992px)')" in boot
    assert "var WIDE_MQ = '(min-width: 992px)';" in js
    assert "if (window.__FOMS_WIDE_SURFACE_RECOVER_BOUND) return;" in js
    # 셸이 내놓는 API 만 쓴다(그 파일은 다른 작업 몫이라 배선만 잠근다).
    for api in ("navigateByShell", "isShellFragmentSwapUrl", "getCacheKey", "invalidateFragmentCache"):
        assert f"shell.{api}" in js, api
        assert f"window.FOMS_ERP_SHELL.{api} = {api};" in shell, api
    assert "'foms:erp-shell-fragment-swapped'" in js and "'foms:erp-shell-fragment-swapped'" in shell
    assert "RUN_ONCE_ATTR = 'data-foms-run-once'" in shell
    assert "window.__fomsViewportHintSync" in js and "window.__fomsViewportHintSync = sync;" in boot


def test_measurement_detail_rows_keep_shell_for_export() -> None:
    """실측 펼친 줄은 껍데기(tr · td)를 두고 속만 뺀다 — 이미지 저장이 줄 순서를 보고 펼친 줄을 지운다."""
    tpl = (ROOT / "templates/measurement/partials/dashboard_main.html").read_text(encoding="utf-8")
    assert (
        '<td colspan="8" class="erp-measurement-detail-cell">'
        "{% if wide_viewport_surfaces or not erp_mobile_v2_enabled %}"
    ) in tpl
    export = (ROOT / "static/js/measurement/image-export.js").read_text(encoding="utf-8")
    assert "tr.measurement-detail-row" in export and "row.remove()" in export
    assert "document.querySelector('.measurement-table')" in export


# --- 6. 폰엔 빠진 표면의 자료도 만들지 않는다(11-16 후속) ------------------------------

#: (경로, 뷰 모듈, 그 표면만 읽는 자료를 만드는 함수들) — 표면 게이트와 같은 판정을 뷰가 먼저 본다.
DATA_BUILDERS = [
    ("/erp/dashboard", "foms.web.orders.dashboard", ("build_split_master_cards", "build_split_side_items")),
    ("/erp/production/dashboard", "foms.web.production.dashboard", ("_compute_tablet_prod_kpis", "collect_production_tombstones")),
    ("/erp/shipment", "foms.web.shipment.dashboard", ("build_tablet_day_sheet", "collect_shipment_change_alerts",
                                                       "_compute_shipment_team_group_meta", "shipment_pending_requests",
                                                       "build_request_board")),
    ("/erp/measurement", "foms.web.measurement.dashboard", ("compute_measurement_product_items_build",)),
]
#: 생산 칸반은 원래 터치 기기만 그린다 — 대조군은 터치 넓은 창(태블릿 가로 · 큰 태블릿 세로).
TOUCH_WIDE = [c for c in CONTROLS if c[0] in ("tablet-landscape", "big-tablet-portrait")]


def _spy(monkeypatch, module_name: str, names: tuple[str, ...]) -> dict[str, int]:
    import importlib

    from foms.services.common import dashboard_cache

    dashboard_cache.reset_dashboard_cache_runtime_for_tests()  # 실측 제품 칸은 캐시 슬라이스 뒤에 있다
    mod = importlib.import_module(module_name)
    calls = {n: 0 for n in names}
    for name in names:
        real = getattr(mod, name)

        def wrapped(*args, _real=real, _name=name, **kwargs):
            calls[_name] += 1
            return _real(*args, **kwargs)

        monkeypatch.setattr(mod, name, wrapped)
    return calls


@pytest.mark.parametrize(("path", "module_name", "names"), DATA_BUILDERS)
@pytest.mark.parametrize(("tag", "cookies"), [("phone", PHONE), ("small-tablet-portrait", SMALL_TABLET_PORTRAIT)])
def test_phone_skips_data_for_omitted_surfaces(client, monkeypatch, path, module_name, names, tag, cookies) -> None:
    _login(client, monkeypatch, _uname("pvs_data_", path, tag))
    calls = _spy(monkeypatch, module_name, names)

    _body(client, path, cookies)

    assert all(n == 0 for n in calls.values()), f"{path} {tag}: 폰에 안 그리는 표면의 자료를 만들었다 {calls}"


@pytest.mark.parametrize(("path", "module_name", "names"), DATA_BUILDERS)
@pytest.mark.parametrize(("tag", "cookies"), TOUCH_WIDE + [("no-cookies", {}), ("odd-value", CONTROLS[-1][1])],
                         ids=[c[0] for c in TOUCH_WIDE] + ["no-cookies", "odd-value"])
def test_wide_windows_still_build_surface_data(client, monkeypatch, path, module_name, names, tag, cookies) -> None:
    """대조군 — 넓은 창 · 쿠키 없음 · 이상값은 지금처럼 자료를 만든다."""
    _login(client, monkeypatch, _uname("pvs_data_ctl_", path, tag))
    calls = _spy(monkeypatch, module_name, names)

    _body(client, path, cookies)

    for name, n in calls.items():
        assert n >= 1, f"{path} {tag}: 넓은 창인데 {name} 를 건너뛰었다"


@pytest.mark.parametrize(("path", "module_name", "names"), [b for b in DATA_BUILDERS if b[0] in ("/erp/shipment", "/erp/measurement")])
def test_legacy_cohort_phone_still_builds_surface_data(client, monkeypatch, path, module_name, names) -> None:
    """코호트 밖은 템플릿이 `or not erp_mobile_v2_enabled` 로 그 표면을 그린다 — 폰 쿠키여도 자료를 만든다."""
    _login(client, monkeypatch, _uname("pvs_data_legacy_", path, "ph"), cohort=False)
    calls = _spy(monkeypatch, module_name, names)

    _body(client, path, PHONE)

    for name, n in calls.items():
        assert n >= 1, f"{path}: 코호트 밖 폰인데 {name} 를 건너뛰었다"
