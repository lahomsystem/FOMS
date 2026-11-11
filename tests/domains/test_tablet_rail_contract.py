"""T2 tablet-landscape global rail contracts (2026-07-12 목업 정합 공사).

Locks the wiring for the always-on 72px left rail that replaces the three-tier
legacy/ERP chrome (global brand header + global text nav + erp_sub_nav icon nav)
on every /erp page (dashboard split excepted) at the tablet-landscape surface:

  - the include gate in ``layout_nav.html`` (v2 cohort ∩ /erp ∩ not /erp/dashboard),
  - the partial root class ``foms-tablet-rail``,
  - the rail CSS show/hide contract (base hidden, coarse-landscape media,
    rail-show + #main-content padding co-located in one @supports :has block),
  - the tablet bundle @import,
  - the cache-chain ?v bumps (bundle → 20260712c, erp-pro.css bumped, bridge
    @import 20260712a),
  - the lazy Jinja global registration, and
  - the active-tab-id path resolver.

These strings are not pinned by the broader T0 / T2 / mockup-parity suites, so a
future edit that regresses the rail wiring fails fast here.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from foms.services.foms_split_view import (
    build_tablet_rail_items,
    resolve_tablet_rail_active_id,
)

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


LAYOUT_NAV = "templates/partials/shared/layout_nav.html"
RAIL_PARTIAL = "templates/partials/shared/foms_tablet_rail.html"
RAIL_CSS = "static/css/foundation/foms-tablet-rail.css"
RAIL_NAV_JS = "static/js/foms/tablet-rail-nav.js"
SPLIT_CSS = "static/css/foundation/foms-split-view.css"
BUNDLE_CSS = "static/css/foundation/foms-tablet-bundle.css"
LAYOUT_HEAD = "templates/partials/shared/layout_head.html"
ERP_PRO_CSS = "static/css/foundation/erp-pro.css"
CONTEXT_PROCESSORS = "foms/services/context_processors.py"


# --- ① include gate --------------------------------------------------------


def test_layout_nav_includes_rail_with_correct_gate() -> None:
    """layout_nav.html includes the rail partial gated on v2 cohort ∩ (/erp ∪
    /wdcalculator). The old /erp/dashboard exclusion is GONE (2026-07-12 목업 v5 정합:
    split no longer shows at the tablet-landscape surface, so the dashboard carries the
    global rail there without a double rail — at fine/none windows the rail is coarse-only
    CSS and stays hidden, and the split shell's own rail owns that case)."""
    nav = _read(LAYOUT_NAV)
    assert "partials/shared/foms_tablet_rail.html" in nav
    assert "erp_mobile_v2_enabled" in nav
    assert "request.path.startswith('/erp')" in nav
    assert "request.path.startswith('/wdcalculator')" in nav
    assert "not request.path.startswith('/erp/dashboard')" not in nav


def test_rail_nav_js_defer_singleton_and_events() -> None:
    """The rail active-sync script exists, is loaded deferred from layout_nav (perf G1),
    guards against double-binding (perf G4), and listens for the ERP fragment-swap +
    popstate events to re-apply .is-active / aria-current to the matching rail item."""
    js = _read(RAIL_NAV_JS)
    assert "__FOMS_TABLET_RAIL_NAV_BOUND" in js
    assert "foms:erp-shell-fragment-swapped" in js
    assert "popstate" in js
    assert "is-active" in js
    assert "aria-current" in js
    nav = _read(LAYOUT_NAV)
    assert "js/foms/tablet-rail-nav.js" in nav
    # Deferred load (render-blocking sync script is banned by perf guard G1).
    assert re.search(r"tablet-rail-nav\.js[^>]*\bdefer\b", nav) is not None, (
        "rail nav script must be loaded with defer"
    )


# --- ② partial root class --------------------------------------------------


def test_rail_partial_root_class_and_lazy_call() -> None:
    """The partial root is ``<nav class="foms-tablet-rail">`` and its items come from
    the lazy Jinja global ``foms_tablet_rail_items()`` (computed only on render)."""
    partial = _read(RAIL_PARTIAL)
    assert 'class="foms-tablet-rail"' in partial
    assert "foms-tablet-rail__item" in partial
    assert "foms_tablet_rail_items()" in partial
    # Namespace isolation: the markup must not USE the split rail classes (comments may
    # mention them for context; we only forbid actual class attributes).
    assert 'class="foms-split-side-tab' not in partial


# --- ③ rail CSS show/hide contract -----------------------------------------


def test_rail_css_base_hidden_and_supports_colocated() -> None:
    """Rail CSS: base ``display: none``; coarse-landscape ≥992 media; rail-show AND
    the #main-content push (padding-left) live in the SAME ``@supports selector(:has(*))``
    block so a no-:has browser drops both (rail never overlaps content)."""
    css = _read(RAIL_CSS)
    norm = " ".join(css.split())
    # Base hidden (all conditions) — the bare rule sets display:none.
    assert ".foms-tablet-rail { display: none; }" in norm
    # Enumerated tablet-landscape media (no `not`, landscape only).
    assert "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)" in css
    # The @supports :has gate wraps BOTH the rail-show and the #main-content push, so a
    # no-:has browser drops both. Anchor on the full @supports token (the prose comment
    # only says "@supports 블록", never the full selector form).
    assert "@supports selector(:has(*))" in css
    supports_block = css.split("@supports selector(:has(*))", 1)[1]
    assert ".foms-tablet-rail" in supports_block
    assert (
        "body:has(.foms-tablet-rail) #main-content" in supports_block
    )
    assert "padding-left: 72px" in supports_block
    assert "width: 72px" in supports_block


def test_rail_and_split_display_media_are_mutually_exclusive() -> None:
    """String-level exclusivity (2026-07-12 목업 v5 정합): the global rail shows only on
    coarse-landscape ≥992, while the split surface shows only on fine/none 992–1365.98
    windows. The two are pointer-exclusive (coarse ⊥ fine/none), so they never display
    together — the dashboard, which carries BOTH the split markup and the rail, can never
    render a double rail."""
    rail_css = _read(RAIL_CSS)
    split_css = _read(SPLIT_CSS)
    # Rail: coarse landscape only.
    assert (
        "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)" in rail_css
    )
    # Split-show: fine/none only …
    assert "(min-width: 992px) and (max-width: 1365.98px) and (pointer: fine)" in split_css
    assert "(min-width: 992px) and (max-width: 1365.98px) and (pointer: none)" in split_css
    # … and NO coarse-pointer media anywhere in the split file (no overlap with the rail).
    assert "(pointer: coarse)" not in split_css


# --- ④ bundle @import ------------------------------------------------------


def test_bundle_imports_rail_css() -> None:
    """foms-tablet-bundle.css @imports the rail stylesheet (versioned)."""
    bundle = _read(BUNDLE_CSS)
    assert '@import url("foms-tablet-rail.css?v=' in bundle


# --- ⑤ cache chain ---------------------------------------------------------


def test_cache_chain_versions_bumped() -> None:
    """Cache-chain contract: 자산 내용이 바뀌면 **@import 핀과 부모 링크 핀이 함께** 올라야 한다.

    @import 만 올리면 부모(erp-pro.css)가 캐시에 남아 새 @import URL 을 아무도 못 본다 —
    "배포는 됐는데 화면은 그대로"의 전형이다. 2026-08-25: 브리지에 nav 채널 표식(.foms-nav-mark)
    을 더해 두 핀을 함께 20260825a 로 올렸다.
    """
    head = _read(LAYOUT_HEAD)
    assert "foms-tablet-bundle.css') }}?v=20261111a" in head
    # erp-pro.css link bumped (old value gone, a fresh value present).
    assert "?v=20260711ad" not in head

    # 두 핀을 **리터럴로** 못 박으면 정당한 상향마다 이 테스트가 빨개지고(2026-09-15 실제로
    # deploy CI 가 그렇게 멈췄다), 사람이 값만 고쳐 초록을 만들면서 계약이 형해화된다.
    # 진짜 위험은 **자식(@import)만 올리는 것**이다 — 부모가 캐시에 남아 새 @import URL 을
    # 아무도 못 본다. 부모만 올리는 것은 안전하다. 그래서 "부모 핀이 자식 핀보다 오래되지
    # 않았다"로 검사한다(핀은 YYYYMMDD+접미사라 문자열 비교가 곧 시간 비교다).
    parent_pin = head.split("erp-pro.css') }}?v=", 1)[1].split('"', 1)[0]
    erp_pro = _read(ERP_PRO_CSS)
    child_pin = erp_pro.split("13-foms-shell-bridge.css?v=", 1)[1].split('"', 1)[0]
    assert parent_pin >= child_pin, (
        f"자식 @import 핀({child_pin})이 부모 링크 핀({parent_pin})보다 새롭다 — "
        "부모가 캐시에 남아 새 @import 를 아무도 못 본다"
    )


# --- ⑥ Jinja global registration -------------------------------------------


def test_jinja_global_registered() -> None:
    """The lazy ``foms_tablet_rail_items`` global is defined and registered as a
    context processor (added, not replacing any existing injector)."""
    src = _read(CONTEXT_PROCESSORS)
    assert "def inject_tablet_rail_helper" in src
    assert "app.context_processor(inject_tablet_rail_helper)" in src
    assert '"foms_tablet_rail_items"' in src


# --- ⑦ active-id resolver unit tests ---------------------------------------


def test_resolve_active_id_maps_paths() -> None:
    """Path → active tab id via longest segment-prefix match."""
    assert resolve_tablet_rail_active_id("/erp/as") == "as"
    assert resolve_tablet_rail_active_id("/erp/measurement") == "measurement"
    assert resolve_tablet_rail_active_id("/erp/drawing-workbench") == "drawing_workbench"
    assert resolve_tablet_rail_active_id("/erp/production/dashboard") == "production"
    assert resolve_tablet_rail_active_id("/erp/shipment") == "shipment"
    assert resolve_tablet_rail_active_id("/erp/construction/dashboard") == "construction"
    assert resolve_tablet_rail_active_id("/erp/completion") == "completion"
    assert resolve_tablet_rail_active_id("/erp/history/") == "history"
    assert resolve_tablet_rail_active_id("/erp/dashboard") == "dashboard"


def test_resolve_active_id_matches_on_segment_boundary() -> None:
    """Sub-paths match the parent tab; a name that merely shares a string prefix does
    NOT falsely match (e.g. /erp/ashley must not resolve to ``as``)."""
    assert resolve_tablet_rail_active_id("/erp/measurement/42") == "measurement"
    assert resolve_tablet_rail_active_id("/erp/ashley") == ""
    assert resolve_tablet_rail_active_id("/not/erp") == ""
    assert resolve_tablet_rail_active_id("") == ""


def test_build_tablet_rail_items_highlights_current_path() -> None:
    """build_tablet_rail_items highlights exactly the tab matching the request path."""
    user = SimpleNamespace(team="SALES", role="STAFF")
    items = build_tablet_rail_items(user, "/erp/shipment")
    active = [it for it in items if it["active"]]
    assert [it["id"] for it in active] == ["shipment"]


def test_build_tablet_rail_items_no_false_active_when_unmatched() -> None:
    """An unmatched path yields no highlighted tab (not a false dashboard highlight)."""
    user = SimpleNamespace(team="SALES", role="STAFF")
    items = build_tablet_rail_items(user, "/erp/ashley")
    assert all(not it["active"] for it in items)


def test_resolve_active_id_maps_calculator() -> None:
    """The calculator page (/wdcalculator, outside the ERP nav contract) resolves to the
    explicit ``calculator`` id so the global rail highlights 계산기; a mere string prefix
    (/wdcalculatorx) does NOT match (segment boundary)."""
    assert resolve_tablet_rail_active_id("/wdcalculator") == "calculator"
    assert resolve_tablet_rail_active_id("/wdcalculator/") == "calculator"
    assert resolve_tablet_rail_active_id("/wdcalculator/embedded") == "calculator"
    assert resolve_tablet_rail_active_id("/wdcalculatorx") == ""


def test_build_tablet_rail_items_highlights_calculator() -> None:
    """On /wdcalculator the calculator rail item is the highlighted one (non-construction
    users get a calculator item; its href is /wdcalculator)."""
    user = SimpleNamespace(team="SALES", role="STAFF")
    items = build_tablet_rail_items(user, "/wdcalculator")
    active = [it for it in items if it["active"]]
    assert [it["id"] for it in active] == ["calculator"]


# --- ⑧ D19(2026-11-10): 태블릿 레일 '생산' = 새 첫 화면(볼 수 있는 사람만) ---------------

_HOME = "/erp/production/home"
_BOARD = "/erp/production/dashboard"


def _rail_production(user) -> dict:
    items = build_tablet_rail_items(user, "/erp/shipment")
    return next(it for it in items if it["id"] == "production")


def test_레일_생산_주소는_첫_화면을_볼_수_있는_사람이면_홈() -> None:
    """관리자 · CS · 영업 · 생산(별칭 회계=CS · 옛 실측=영업 포함)은 첫 화면, 그 밖 팀 · 협력사는 보드(403 화면으로 안 보낸다)."""
    for user in (
        SimpleNamespace(team=None, role="ADMIN"),
        SimpleNamespace(team="DRAWING", role="ADMIN"),
        SimpleNamespace(team="CS", role="STAFF"),
        SimpleNamespace(team="ACCOUNTING", role="STAFF"),
        SimpleNamespace(team="SALES", role="STAFF"),
        SimpleNamespace(team="MEASURE", role="STAFF"),  # 옛 실측팀 = 영업(normalize_team)
        SimpleNamespace(team="PRODUCTION", role="STAFF"),
    ):
        assert _rail_production(user)["href"] == _HOME, user
    for user in (
        SimpleNamespace(team="DRAWING", role="STAFF"),
        SimpleNamespace(team=None, role="STAFF"),
        SimpleNamespace(team="PRODUCTION", role="STAFF", partner_org_id=3),
        None,
    ):
        assert _rail_production(user)["href"] == _BOARD, user
    # 강조 접두어는 누구든 같다 — 보드로 조각 이동한 뒤에도 생산이 강조된다(tablet-rail-nav.js).
    assert _rail_production(SimpleNamespace(team="DRAWING", role="STAFF"))["match"] == "/erp/production"


def test_레일_규칙은_첫_화면_문지기와_한_곳() -> None:
    """레일과 home.py 문지기가 같은 판정 함수를 쓴다(어긋나면 레일이 403 으로 보낸다). 주소 상수 = 라우트."""
    from foms.services.production import home_access

    home_src = _read("foms/web/production/home.py")
    assert "can_view_production_home(user)" in home_src and "team_has_capability" not in home_src
    assert "can_view_production_home" in _read("foms/services/foms_split_view.py")
    assert home_access.PRODUCTION_HOME_PATH == _HOME


def test_시공팀_레일에는_생산_단추가_없다() -> None:
    items = build_tablet_rail_items(SimpleNamespace(team="CONSTRUCTION", role="STAFF"), "/erp/shipment")
    assert [it["id"] for it in items] == ["shipment", "construction", "completion", "history"]


def test_첫_화면과_전체_화면_시트도_생산이_강조된다() -> None:
    for path in (_HOME, "/erp/production/sheet/1", "/erp/production/print/1", _BOARD, "/erp/production"):
        assert resolve_tablet_rail_active_id(path) == "production", path
    # 접두어가 비슷한 다른 경로는 생산이 아니다(구간 경계)
    assert resolve_tablet_rail_active_id("/erp/productionx") == ""
    assert resolve_tablet_rail_active_id("/erp/construction/dashboard") == "construction"
    items = build_tablet_rail_items(SimpleNamespace(team="PRODUCTION", role="STAFF"), "/erp/production/sheet/1")
    assert [it["id"] for it in items if it["active"]] == ["production"]


def test_split_셸_레일은_그대로_보드() -> None:
    """split 셸(/erp/dashboard, PC 마우스 좁은 창 전용)은 D19 범위 밖 — 생산은 계약 경로(보드) 그대로."""
    from foms.services.foms_split_view import build_split_side_items

    items = build_split_side_items(SimpleNamespace(team="PRODUCTION", role="STAFF"))
    assert next(it for it in items if it["id"] == "production")["href"] == _BOARD


def test_레일_동기_JS는_강조_접두어를_먼저_본다() -> None:
    js = _read(RAIL_NAV_JS)
    assert "getAttribute('data-foms-rail-match') || items[i].pathname" in js
    assert 'data-foms-rail-match="{{ item.match }}"' in _read(RAIL_PARTIAL)
    assert "js/foms/tablet-rail-nav.js') }}?v=20261110a" in _read(LAYOUT_NAV)
