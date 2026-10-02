"""광폭 마우스 PC 에 모바일 v2 대시보드 표면을 보내지 않는 계약 (2026-09-28).

배경: 모바일 v3 셸 삭제(3261d2083)가 대시보드 6곳의 ``shell_variant != 'v3'`` 생략을 함께
지우면서, v2 코호트 PC 의 모든 요청이 광폭에서 CSS 가 ``display:none`` 으로 끄는 모바일 표면을
다시 렌더하게 됐다(시공 fragment 약 128KB). 스테이징 perf gate(pc-wide-fine)가 TTFB·wire 로
잡았다.

설계: 서버는 ``foms_ptr=fine`` **그리고** ``foms_vw=wide`` 일 때만 표면을 빼고 표식을 남긴다
(:func:`foms.services.feature_flags.wants_mobile_width_surfaces`). 창 폭은 바뀌므로 창이
좁아지면 ``erp-shell.js`` 가 표식을 보고 화면을 다시 받는다.

여기서 잠그는 것:
  1. 판정 진리표 — 쿠키가 하나라도 없거나 이상하면 전부 렌더(True).
  2. 대시보드 6곳 — 쿠키 없음/좁은 창/터치는 표면을 그리고, 광폭 마우스 PC 는 표식만 남긴다.
  3. 표면이 빠진 본문과 전체 본문은 ETag·프래그먼트 버전 키가 다르다(낡은 304 금지).
  4. 부트 인라인 사본 == SSOT 사본, 되돌림 JS 배선(표식·은닉 식·되풀이 방지).
  5. 표면에만 쓰이는 데이터(주문 타워·실측/출고 모바일 큐 행)도 같은 판정으로 건너뛴다.
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

LAYOUT_HEAD = ROOT / "templates/partials/shared/layout_head.html"
BOOT_JS = ROOT / "static/js/runtime/foms-viewport-hint-boot.js"
ERP_SHELL_JS = ROOT / "static/js/runtime/erp-shell.js"
HIDE_CSS = ROOT / "static/css/foundation/foms-mobile-v2-surfaces-hide.css"
MARKER_PARTIAL = "partials/shared/mobile_surface_omitted_marker.html"
MARKER_ATTR = "data-foms-mobile-surface-omitted"

SHELL_HEADERS = {"X-FOMS-ERP-SHELL": "1"}

# (경로, 대시보드 body 템플릿, 표면 표식 = 섹션 aria-label — 도메인마다 유일)
DASHBOARDS = [
    ("/erp/dashboard", "templates/orders/partials/dashboard_main.html",
     ("모바일 홈 대시보드", "모바일 홈 컨트롤 타워")),
    ("/erp/measurement", "templates/measurement/partials/dashboard_main.html",
     ("실측 모바일 대시보드",)),
    ("/erp/drawing-workbench", "templates/drawing/partials/workbench_dashboard_body.html",
     ("도면 작업 큐",)),
    ("/erp/production/dashboard", "templates/production/partials/dashboard_body.html",
     ("생산 모바일 대시보드",)),
    ("/erp/construction/dashboard", "templates/construction/partials/dashboard_body.html",
     ("시공 모바일 대시보드",)),
    ("/erp/shipment", "templates/shipment/partials/dashboard_main.html",
     ("출고 모바일 대시보드",)),
    ("/erp/as", "templates/cs/partials/as_dashboard_body.html",
     ("AS 모바일 대시보드",)),
]


class _StubRequest:
    """cookies 만 갖는 최소 request 스텁."""

    def __init__(self, cookies: dict[str, str] | None) -> None:
        self.cookies = cookies


# --- 1. 판정 진리표 -----------------------------------------------------------


@pytest.mark.parametrize(
    ("cookies", "expected", "why"),
    [
        ({}, True, "쿠키 없음 — 첫 요청·쿠키 차단: 전부 렌더"),
        ({"foms_ptr": "fine"}, True, "창 폭 모름 — 좁은 창일 수 있다"),
        ({"foms_vw": "wide"}, True, "포인터 모름 — 태블릿 세로일 수 있다"),
        ({"foms_ptr": "fine", "foms_vw": "wide"}, False, "광폭 마우스 PC — 표면이 CSS 로 꺼진다"),
        ({"foms_ptr": "fine", "foms_vw": "narrow"}, True, "좁힌 PC 창 — 모바일 셸이 보인다"),
        ({"foms_ptr": "coarse", "foms_vw": "wide"}, True, "태블릿 — 세로로 돌리면 표면이 보인다"),
        ({"foms_ptr": "coarse", "foms_vw": "narrow"}, True, "폰"),
        ({"foms_ptr": "fine", "foms_vw": "WIDE"}, True, "미지의 값 — 전부 렌더"),
        ({"foms_ptr": "fine", "foms_vw": ""}, True, "빈 값 — 전부 렌더"),
    ],
)
def test_wants_mobile_width_surfaces_truth_table(cookies, expected, why) -> None:
    got = feature_flags.wants_mobile_width_surfaces(_StubRequest(cookies))
    assert got is expected, f"{why}: {cookies} -> {got}"


def test_wants_mobile_width_surfaces_safe_fallbacks() -> None:
    """cookies 속성 없음 · request context 밖 = 전부 렌더."""
    assert feature_flags.wants_mobile_width_surfaces(_StubRequest(None)) is True
    assert feature_flags.wants_mobile_width_surfaces() is True


# --- 2. 대시보드 6곳 렌더 ------------------------------------------------------


def _login_v2_cohort(client, monkeypatch, username: str) -> None:
    """v2 모바일 코호트 ADMIN 으로 로그인한다(FOMS_V3_SHELL_COHORT = v2 코호트 키)."""
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
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _set_hints(client, **cookies: str) -> None:
    for name, value in cookies.items():
        client.set_cookie(name, value, domain="localhost")


def _fragment(client, path: str, headers: dict[str, str] | None = None):
    response = client.get(f"{path}?view=fragment", headers={**SHELL_HEADERS, **(headers or {})})
    assert response.status_code == 200, f"{path} -> {response.status_code}"
    return response


def _username(prefix: str, path: str) -> str:
    return prefix + path.strip("/").replace("/", "_").replace("-", "_")


@pytest.mark.parametrize(("path", "_tpl", "markers"), DASHBOARDS)
@pytest.mark.parametrize(
    "hints",
    [
        {},
        {"foms_ptr": "fine", "foms_vw": "narrow"},
        {"foms_ptr": "coarse", "foms_vw": "wide"},
    ],
    ids=["no-cookies", "fine-narrow", "coarse-wide"],
)
def test_dashboard_renders_mobile_surface_unless_wide_mouse_pc(
    client, monkeypatch, path, _tpl, markers, hints
) -> None:
    _login_v2_cohort(client, monkeypatch, _username("mws_on_", path) + "_" + "_".join(hints.values()))
    _set_hints(client, **hints)

    body = _fragment(client, path).get_data(as_text=True)

    assert any(m in body for m in markers), f"{path} {hints}: 모바일 표면이 없다"
    assert MARKER_ATTR not in body, f"{path} {hints}: 표면을 그렸는데 생략 표식이 있다"


@pytest.mark.parametrize(("path", "_tpl", "markers"), DASHBOARDS)
def test_dashboard_omits_mobile_surface_for_wide_mouse_pc(
    client, monkeypatch, path, _tpl, markers
) -> None:
    _login_v2_cohort(client, monkeypatch, _username("mws_off_", path))
    _set_hints(client, foms_ptr="fine", foms_vw="wide")

    body = _fragment(client, path).get_data(as_text=True)

    assert not any(m in body for m in markers), f"{path}: 광폭 마우스 PC 에 모바일 표면이 남았다"
    assert body.count(MARKER_ATTR) == 1, f"{path}: 생략 표식이 정확히 1개여야 한다"


def test_legacy_cohort_has_neither_surface_nor_marker(client, monkeypatch) -> None:
    """v2 코호트 밖(legacy)은 원래 표면이 없다 — 표식도 남기지 않는다(되돌릴 것이 없다)."""
    _login_v2_cohort(client, monkeypatch, "mws_legacy")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "9999999")
    _set_hints(client, foms_ptr="fine", foms_vw="wide")

    body = _fragment(client, "/erp/construction/dashboard").get_data(as_text=True)

    assert "시공 모바일 대시보드" not in body
    assert MARKER_ATTR not in body


@pytest.mark.parametrize(("_path", "tpl", "_markers"), DASHBOARDS)
def test_dashboard_template_gates_surface_and_leaves_marker(_path, tpl, _markers) -> None:
    """표면 게이트와 표식 include 가 짝으로 있어야 한다(표식 없이 빼면 되돌릴 수 없다)."""
    text = (ROOT / tpl).read_text(encoding="utf-8")
    assert "erp_mobile_v2_enabled and mobile_width_surfaces" in text
    gate = text.index("erp_mobile_v2_enabled and mobile_width_surfaces")
    tail = text[gate:]
    assert tail.index("{% elif erp_mobile_v2_enabled %}") < tail.index(MARKER_PARTIAL)


def test_marker_partial_emits_inert_marker() -> None:
    text = (ROOT / "templates" / MARKER_PARTIAL).read_text(encoding="utf-8")
    code = re.sub(r"\{#.*?#\}", "", text, flags=re.S).strip()
    assert code == f"<template {MARKER_ATTR}></template>"


# --- 3. ETag · 프래그먼트 버전 키 ------------------------------------------------


def test_fragment_etag_differs_by_viewport_bucket_and_never_304s_across(client, monkeypatch) -> None:
    """광폭 창에서 받은 ETag 를 좁은 창이 에코해도 304 가 아니라 전체 본문을 받는다."""
    path = "/erp/construction/dashboard"
    _login_v2_cohort(client, monkeypatch, "mws_etag")
    _set_hints(client, foms_ptr="fine", foms_vw="wide")
    wide = _fragment(client, path)
    wide_etag = wide.headers.get("ETag")
    assert wide_etag

    _set_hints(client, foms_vw="narrow")
    narrow = client.get(
        f"{path}?view=fragment", headers={**SHELL_HEADERS, "If-None-Match": wide_etag}
    )

    assert narrow.status_code == 200
    assert narrow.headers.get("ETag") != wide_etag
    assert "시공 모바일 대시보드" in narrow.get_data(as_text=True)


def test_fragment_version_key_material_includes_mobile_width_bit(app) -> None:
    """렌더 전 304(HB-S2) 키 재료에 창 폭 판정이 들어가야 낡은 본문이 되살아나지 않는다."""
    from foms.services.common import fragment_revalidation as fr

    got = {}
    for bucket in ("wide", "narrow"):
        with app.test_request_context("/", headers={"Cookie": f"foms_ptr=fine; foms_vw={bucket}"}):
            got[bucket] = fr._surface_hint_material()
    assert got["wide"]["mobile_width"] is False
    assert got["narrow"]["mobile_width"] is True

    src = Path(fr.__file__).read_text(encoding="utf-8")
    assert '"surfaces": _surface_hint_material()' in src


# --- 4. 부트 · 되돌림 JS 배선 ---------------------------------------------------


def _strip_js_comments(code: str) -> str:
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    code = re.sub(r"^\s*//[^\n]*\n", "", code, flags=re.M)
    return code


def _normalize(code: str) -> list[str]:
    return [ln.strip() for ln in code.splitlines() if ln.strip()]


def test_viewport_boot_inline_matches_ssot() -> None:
    """layout_head 인라인 사본과 SSOT 파일의 실행 코드가 글자 그대로 같다."""
    head = LAYOUT_HEAD.read_text(encoding="utf-8")
    blocks = re.findall(r"<script>\s*(\(function \(\) \{.*?\}\)\(\);)\s*</script>", head, flags=re.S)
    inline = [b for b in blocks if "'foms_vw'" in b]
    assert len(inline) == 1, "foms_vw 인라인 부트가 정확히 1개여야 한다"
    ssot = _strip_js_comments(BOOT_JS.read_text(encoding="utf-8"))
    assert _normalize(inline[0]) == _normalize(ssot)
    assert "foms-viewport-hint-boot.js" not in re.sub(r"\{#.*?#\}", "", head, flags=re.S), (
        "G1: 부트는 src 가 아니라 인라인 사본으로만 싣는다"
    )


def test_viewport_boot_uses_css_breakpoint_and_session_cookie() -> None:
    code = _strip_js_comments(BOOT_JS.read_text(encoding="utf-8"))
    assert "window.matchMedia('(min-width: 992px)')" in code
    assert "'wide' : 'narrow'" in code
    assert "max-age" not in code, "창 폭은 낡으므로 세션 쿠키로 둔다"
    assert "addEventListener('change', sync)" in code
    assert "window.__fomsViewportHintSync = sync" in code


def test_erp_shell_hidden_mq_matches_surface_hide_css() -> None:
    """되돌림 판정의 은닉 식은 CSS 은닉 규칙과 같은 조건이어야 한다."""
    css = HIDE_CSS.read_text(encoding="utf-8")
    css_mq = re.search(r"@media\s+(.*?)\s*\{", css, flags=re.S).group(1)
    js = ERP_SHELL_JS.read_text(encoding="utf-8")
    decl = re.search(r"var MOBILE_SURFACE_HIDDEN_MQ =\s*(.*?);", js, flags=re.S).group(1)
    js_mq = "".join(re.findall(r"'([^']*)'", decl))
    squash = lambda s: re.sub(r"\s+", "", s)  # noqa: E731
    assert squash(js_mq) == squash(css_mq)


def test_erp_shell_recovery_wiring_and_loop_guard() -> None:
    js = ERP_SHELL_JS.read_text(encoding="utf-8")
    assert f"'[{MARKER_ATTR}]'" in js
    body = js.split("function recoverOmittedMobileSurface() {", 1)[1].split("\n  }\n", 1)[0]
    # 다시 받기 직전에 이 창의 폭 구간으로 쿠키를 맞춘다(창 여러 개가 쿠키 하나를 공유).
    assert body.index("__fomsViewportHintSync()") < body.index("navigateByShell(here")
    # 1단계: 같은 주소에서 셸 다시 받기 1회(기록은 쌓지 않는다).
    assert "navigateByShell(here, { bypassCache: true, replaceHistory: true })" in body
    assert "mobileSurfaceRefetchKey = key" in body
    # 2단계: 새로고침은 sessionStorage 되풀이 표식을 먼저 확인·기록한 뒤에만.
    assert body.index("mobileSurfaceReloadedRecently(guard, key)") < body.index("window.location.reload()")
    assert body.index("mobileSurfaceReloadGuard('set'") < body.index("window.location.reload()")
    # 저장소를 못 쓰면(undefined) 새로고침하지 않는다 — 되풀이를 막을 수 없으니까.
    assert "if (guard === undefined) {" in body
    # 표면이 필요 없거나 그려져 있으면 되풀이 표식을 지운다.
    assert "mobileSurfaceRefetchKey = null" in body
    # 발화 지점: 경계 넘김 · 셸 스왑 · bfcache 복귀 · 첫 문서.
    assert "document.addEventListener('foms:erp-shell-fragment-swapped', recoverOmittedMobileSurface)" in js
    assert "window.setTimeout(recoverOmittedMobileSurface, 0)" in js
    assert "replaceState(window.history.state, '', target)" in js


def test_erp_shell_drops_warm_cache_when_surface_becomes_visible() -> None:
    """광폭에서 받아 둔 warm 캐시(표면 빠진 본문)는 표면이 보여야 하는 순간 통째로 버린다."""
    js = ERP_SHELL_JS.read_text(encoding="utf-8")
    handler = js.split("var onMobileSurfaceVisibilityChange = function () {", 1)[1].split("};", 1)[0]
    assert "if (!mobileSurfaceHiddenMql.matches)" in handler
    assert "invalidateFragmentCache();" in handler


# --- 5. 표면 전용 데이터 조립도 같은 판정으로 건너뛴다 -----------------------------

#: (경로, 스파이를 심을 모듈, 속성) — 소비처가 생략되는 모바일 표면뿐인 데이터 조립.
MOBILE_ONLY_BUILDERS = [
    ("/erp/dashboard", "foms.web.orders.dashboard", "build_mobile_control_tower"),
    ("/erp/measurement", "foms.services.erp_mobile_order_display", "build_mobile_queue_batch_context"),
    ("/erp/shipment", "foms.web.shipment.dashboard", "build_shipment_mobile_queue_rows"),
    # 생산 태블릿 칸반은 폭이 아니라 포인터(coarse) 판정이다 — 광폭 마우스 PC 는 fine 이라
    # 같은 대조가 성립한다. 전량 조회·가공 상세 계약은 test_production_kanban_full_window.py.
    ("/erp/production/dashboard", "foms.web.production.dashboard", "collect_production_tombstones"),
]


@pytest.mark.parametrize(("path", "module", "attr"), MOBILE_ONLY_BUILDERS)
@pytest.mark.parametrize(
    ("hints", "expect_called"),
    [({}, True), ({"foms_ptr": "fine", "foms_vw": "wide"}, False)],
    ids=["no-cookies", "wide-mouse-pc"],
)
def test_mobile_only_data_is_built_only_when_surface_renders(
    client, monkeypatch, path, module, attr, hints, expect_called
) -> None:
    import importlib

    from foms.services.common import dashboard_cache as dc

    dc.reset_dashboard_cache_runtime_for_tests()
    target = importlib.import_module(module)
    original = getattr(target, attr)
    calls: list[int] = []

    def _spy(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(target, attr, _spy)
    _login_v2_cohort(client, monkeypatch, _username("mws_data_", path) + "_" + "_".join(hints.values()))
    _set_hints(client, **hints)

    _fragment(client, path)

    assert bool(calls) is expect_called, f"{path} {hints}: {attr} 호출 {len(calls)}회"


def test_complete_gate_reads_customer_name_from_pc_row_when_mobile_card_is_omitted():
    """광폭 마우스 PC 는 모바일 큐 카드가 없다 — 완료 준비 시트가 고객명 대신 '#번호' 를
    보이지 않도록 PC 표 '고객' 칸에서도 이름을 읽는다."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    js = (root / "static/js/construction/foms-complete-gate.js").read_text(encoding="utf-8")
    assert "tr.erp-main-row[data-order-id=" in js and 'td[data-label="고객"]' in js
    tpl = (root / "templates/construction/dashboard.html").read_text(encoding="utf-8")
    assert "foms-complete-gate.js') }}?v=20260928a" in tpl
