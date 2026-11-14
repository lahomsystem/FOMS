"""태블릿 가로에서 절대 안 보이는 PC 작업 큐를 서버가 보내지 않는 계약 (2026-11-14).

배경(원장 docs/plans/2026-11-09-tablet-production-ui-ledger.md §29): 태블릿(갤럭시 탭 가로 1280×800)은
터치이면서 화면이 넓다. 서버가 폰 표면 · PC 작업 큐 · 태블릿 화면 셋을 다 그려 보내고, CSS 가 둘을
숨겼다(주문 대시보드 DOM 75% 숨김 · 숨은 작업 큐 안에서 그림 101장 받기).

설계: PC 작업 큐의 은닉 규칙은 모두 ``body.erp-mobile-v2-layout`` 아래
``(min-width: 992px) and (orientation: landscape) and (pointer: coarse)`` 한 식이다. 서버는 그 세 조건이
쿠키로 확인될 때만(``foms_ptr=coarse`` + ``foms_vw=wide``) 큐를 뺀다
(:func:`foms.services.feature_flags.wants_desktop_queue_surfaces`). 같은 조건에서 모바일 표면 생략 표식이
늘 함께 남으므로, 세로로 돌리면 ``erp-shell.js`` 가 그 표식을 보고 화면을 다시 받아 큐도 되살아난다.

여기서 잠그는 것:
  1. 판정 진리표 — 쿠키가 하나라도 없거나 이상하면 전부 렌더(True).
  2. 태블릿 가로: PC 큐 마크업 0 · 보이는 태블릿 화면은 그대로 · 되돌림 표식 1개.
  3. 대조군(쿠키 없음 · 폰 · 마우스 PC · 태블릿 세로 · 큰 태블릿 세로 · 코호트 밖): PC 큐 출력 그대로.
  4. 템플릿 게이트 ↔ 은닉 CSS 식 ↔ 되돌림 표식이 짝으로 있다.
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
MARKER_ATTR = "data-foms-mobile-surface-omitted"
GATE = "desktop_queue_surfaces or not erp_mobile_v2_enabled"
TABLET_MQ = "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)"

# (경로, 템플릿, PC 큐 마크업, 태블릿 화면 마크업 후보, 은닉 CSS, 은닉 선택자)
TABS = [
    (
        "/erp/dashboard",
        "templates/orders/partials/dashboard_main.html",
        '<div class="erp-dashboard-workqueue"',
        ('<div class="foms-tablet-workqueue-wrap"',),
        "static/css/foundation/foms-tablet-landscape.css",
        "body.erp-mobile-v2-layout .erp-dashboard-orders .erp-dashboard-workqueue",
    ),
    (
        "/erp/construction/dashboard",
        "templates/construction/partials/dashboard_body.html",
        '<div class="foms-construction-legacy-queue">',
        ('<section class="foms-construction-workmode"', '<section class="foms-cons-first"'),
        "static/css/foundation/foms-tablet-construction.css",
        "body.erp-mobile-v2-layout .foms-construction-legacy-queue",
    ),
    (
        "/erp/production/dashboard",
        "templates/production/partials/dashboard_body.html",
        '<div class="foms-production-legacy-queue">',
        ('<div class="tablet-prod-board">',),
        "static/css/foundation/foms-tablet-production-kanban.css",
        "body.erp-mobile-v2-layout .foms-production-legacy-queue",
    ),
    (
        "/erp/measurement",
        "templates/measurement/partials/dashboard_main.html",
        '<div class="erp-measurement-desktop-shell">',
        ('<div class="foms-tablet-measure-split"',),
        "static/css/foundation/foms-tablet-measurement.css",
        "body.erp-mobile-v2-layout .erp-measurement-dashboard .erp-measurement-desktop-shell",
    ),
]

TABLET_LANDSCAPE = {"foms_ptr": "coarse", "foms_vw": "wide", "foms_scr": "1280"}


class _StubRequest:
    def __init__(self, cookies: dict[str, str] | None) -> None:
        self.cookies = cookies


# --- 1. 판정 진리표 -----------------------------------------------------------


@pytest.mark.parametrize(
    ("cookies", "expected", "why"),
    [
        ({}, True, "쿠키 없음 — 첫 요청·쿠키 차단: 전부 렌더"),
        ({"foms_ptr": "coarse"}, True, "창 모름 — 세로일 수 있다"),
        ({"foms_vw": "wide"}, True, "포인터 모름 — 마우스 PC 일 수 있다"),
        ({"foms_ptr": "coarse", "foms_vw": "wide"}, False, "태블릿 가로 — PC 큐가 CSS 로 꺼진다"),
        ({"foms_ptr": "coarse", "foms_vw": "tall"}, True, "큰 태블릿 세로 — 은닉 식(landscape) 밖"),
        ({"foms_ptr": "coarse", "foms_vw": "narrow"}, True, "폰 · 태블릿 세로"),
        ({"foms_ptr": "fine", "foms_vw": "wide"}, True, "광폭 마우스 PC — PC 큐가 보인다"),
        ({"foms_ptr": "fine", "foms_vw": "tall"}, True, "세로 모니터 — PC 큐가 보인다"),
        ({"foms_ptr": "coarse", "foms_vw": "WIDE"}, True, "미지의 값 — 전부 렌더"),
        ({"foms_ptr": "coarse", "foms_vw": ""}, True, "빈 값 — 전부 렌더"),
    ],
)
def test_wants_desktop_queue_surfaces_truth_table(cookies, expected, why) -> None:
    got = feature_flags.wants_desktop_queue_surfaces(_StubRequest(cookies))
    assert got is expected, f"{why}: {cookies} -> {got}"


def test_wants_desktop_queue_surfaces_safe_fallbacks() -> None:
    assert feature_flags.wants_desktop_queue_surfaces(_StubRequest(None)) is True
    assert feature_flags.wants_desktop_queue_surfaces() is True


def test_desktop_queue_omission_implies_mobile_omission() -> None:
    """PC 큐를 뺀 화면엔 반드시 모바일 생략 표식도 남아야 되돌림 길(erp-shell.js)이 돈다."""
    for ptr in ("coarse", "fine", "", "x"):
        for vw in ("wide", "tall", "narrow", "", "x"):
            req = _StubRequest({"foms_ptr": ptr, "foms_vw": vw})
            if not feature_flags.wants_desktop_queue_surfaces(req):
                assert feature_flags.wants_mobile_width_surfaces(req) is False, (ptr, vw)


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


@pytest.mark.parametrize(("path", "_tpl", "pc_mark", "tablet_marks", "_css", "_sel"), TABS)
def test_tablet_landscape_omits_desktop_queue_keeps_tablet_surface(
    client, monkeypatch, path, _tpl, pc_mark, tablet_marks, _css, _sel
) -> None:
    _login(client, monkeypatch, _uname("tls_on_", path, "land"))

    body = _body(client, path, TABLET_LANDSCAPE)

    assert pc_mark not in body, f"{path}: 태블릿 가로에 숨은 PC 큐가 남았다"
    assert any(m in body for m in tablet_marks), f"{path}: 보이는 태블릿 화면이 사라졌다"
    assert body.count(MARKER_ATTR) == 1, f"{path}: 세로 회전 되돌림 표식이 정확히 1개여야 한다"


#: 대조군 — 지금 출력 그대로여야 한다. 값 = PC 큐가 있어야 하는가(경로별 예외는 아래에서).
CONTROLS = [
    ("no-cookies", {}, True),
    ("phone", {"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "844"}, "wide_only"),
    ("mouse-pc", {"foms_ptr": "fine", "foms_vw": "wide", "foms_scr": "1920"}, True),
    ("tablet-portrait", {"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "1280"}, True),
    ("big-tablet-portrait", {"foms_ptr": "coarse", "foms_vw": "tall", "foms_scr": "1366"}, True),
]


@pytest.mark.parametrize(("path", "_tpl", "pc_mark", "tablet_marks", "_css", "_sel"), TABS)
@pytest.mark.parametrize(("tag", "cookies", "expect_pc"), CONTROLS, ids=[c[0] for c in CONTROLS])
def test_controls_keep_current_output(
    client, monkeypatch, path, _tpl, pc_mark, tablet_marks, _css, _sel, tag, cookies, expect_pc
) -> None:
    _login(client, monkeypatch, _uname("tls_ctl_", path, tag))

    body = _body(client, path, cookies)

    if expect_pc == "wide_only":
        # 폰(긴 변 <992)은 원래부터 광폭 전용 큐를 받지 않는다(wants_wide_only_surfaces) —
        # 실측 PC 표만 그 판정 밖이라 폰에도 그대로 간다.
        expect_pc = path == "/erp/measurement"
    assert (pc_mark in body) is expect_pc, f"{path} {tag}: PC 큐 출력이 바뀌었다"
    # 태블릿 화면은 터치 판정(coarse_pointer_surfaces)만 따르므로 이 변경과 무관 — 마우스 PC 만 빠진다.
    if tag != "mouse-pc" or path == "/erp/measurement":
        assert any(m in body for m in tablet_marks), f"{path} {tag}: 태블릿 화면 출력이 바뀌었다"


@pytest.mark.parametrize(("path", "_tpl", "pc_mark", "_tablet_marks", "_css", "_sel"), TABS)
def test_legacy_cohort_keeps_desktop_queue_on_tablet_landscape(
    client, monkeypatch, path, _tpl, pc_mark, _tablet_marks, _css, _sel
) -> None:
    """코호트 밖(legacy)은 태블릿 은닉 CSS 자체를 싣지 않는다 — 가로 태블릿이어도 PC 큐가 보인다."""
    _login(client, monkeypatch, _uname("tls_legacy_", path, "land"), cohort=False)

    body = _body(client, path, TABLET_LANDSCAPE)

    assert pc_mark in body, f"{path}: 코호트 밖 태블릿 가로에서 PC 큐가 빠졌다(화면이 빈다)"


def test_fragment_etag_differs_between_tablet_landscape_and_portrait(client, monkeypatch) -> None:
    """가로에서 받은 ETag 를 세로가 에코해도 304 가 아니라 PC 큐가 든 전체 본문을 받는다."""
    path = "/erp/construction/dashboard"
    _login(client, monkeypatch, "tls_etag")
    for name, value in TABLET_LANDSCAPE.items():
        client.set_cookie(name, value, domain="localhost")
    land = client.get(f"{path}?view=fragment", headers=SHELL_HEADERS)
    etag = land.headers.get("ETag")
    assert etag

    client.set_cookie("foms_vw", "narrow", domain="localhost")
    port = client.get(f"{path}?view=fragment", headers={**SHELL_HEADERS, "If-None-Match": etag})

    assert port.status_code == 200
    assert port.headers.get("ETag") != etag
    assert '<div class="foms-construction-legacy-queue">' in port.get_data(as_text=True)


# --- 4. 템플릿 게이트 ↔ 은닉 CSS ↔ 되돌림 표식 -------------------------------------


@pytest.mark.parametrize(("_path", "tpl", "pc_mark", "_tablet_marks", "css", "selector"), TABS)
def test_gate_matches_hiding_css_and_recovery_marker(_path, tpl, pc_mark, _tablet_marks, css, selector) -> None:
    text = (ROOT / tpl).read_text(encoding="utf-8")
    code = re.sub(r"\{#.*?#\}", "", text, flags=re.S)
    # 게이트가 PC 큐 마크업(또는 그 include) 바로 앞에 있다.
    gate_at = code.index(GATE)
    nxt = code[gate_at:]
    first_tag = re.search(r"<div class=\"[^\"]+\"|\{% include '[^']+' %\}", nxt).group(0)
    assert first_tag in (pc_mark.rstrip(">"), pc_mark) or "dashboard_grid.html" in first_tag, first_tag
    # 같은 템플릿에 되돌림 표식(모바일 표면 생략)이 짝으로 있다.
    assert "partials/shared/mobile_surface_omitted_marker.html" in code
    # 은닉 CSS 는 코호트 · 태블릿 가로 식 하나 아래에서 PC 큐를 끈다.
    css_text = (ROOT / css).read_text(encoding="utf-8")
    block_start = css_text.index(f"@media {TABLET_MQ}")
    assert css_text.index(selector, block_start) > block_start


def test_erp_shell_recovery_fires_on_tablet_rotation() -> None:
    """은닉 식에 landscape 갈래가 있어야 coarse 태블릿을 세로로 돌릴 때 change 가 와서 다시 받는다.
    (erp-shell.js 는 다른 작업 몫이라 고치지 않고 배선만 잠근다.)"""
    js = (ROOT / "static/js/runtime/erp-shell.js").read_text(encoding="utf-8")
    decl = re.search(r"var MOBILE_SURFACE_HIDDEN_MQ =\s*(.*?);", js, flags=re.S).group(1)
    assert "((min-width: 992px) and (orientation: landscape))" in decl
    assert "mobileSurfaceHiddenMql.addEventListener('change', onMobileSurfaceVisibilityChange)" in js
    # 포인터로 거르지 않는다 — 마우스 전용이었다면 태블릿 회전에서 안 돈다.
    body = js.split("function recoverOmittedMobileSurface() {", 1)[1].split("\n  }\n", 1)[0]
    assert "pointer" not in body
