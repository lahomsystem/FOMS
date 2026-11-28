"""옛 생산 보드 없애기 ④ 지우기 확인(설계서 2026-11-27-production-legacy-board-removal §0-1-3 · §6 · §7-3).

* 옛 주소 둘(``/erp/production/dashboard`` · ``/erp/production/tablet-sheet/<id>``)은 라우트째 지웠다 — 넘겨주기(302) 없음.
  로그인한 직원 · 관리자 · 팀 없는 직원 = 404. 그 밖 계정은 각자 문지기의 답 그대로(시공팀 = 출고 302,
  협력사 = 협력사 첫 화면 302, 켜진 프리랜서 = 프리랜서 홈 302, 로그인 없음 = 404 — 길이 없으니 로그인 문도 없다).
* 생산 Blueprint(``erp_production_page``)의 길은 넷뿐(첫 화면 · 작업 시트 · 인쇄 · 도면 카드 그림). Blueprint 와 템플릿 전역 셋은
  ``foms/web/production/blueprint.py`` 에 있다(옛 ``dashboard.py`` 없음).
* 옛 템플릿 14개 · 옛 JS 둘 · 옛 CSS 하나 · 옛 서비스 둘 · 시험 준비물 하나가 없고, ``templates`` · ``static`` · ``foms`` 어디에도
  그 이름 · 옛 endpoint 를 부르는 곳이 없다(되살아남 막기). 예외는 아래 표에 이유와 함께 적었다.
* 공용 파일에 남은 몫: tablet-domain-sheets.js 의 생산 쓰기 · 보류 · change-ack · 출고 저장, 확인 창 꼴 CSS.
* 시공팀은 새 첫 화면 · 작업 시트를 지금처럼 연다(이동 제한의 옛 보드 갈래 정리 뒤에도).

이름 · 번호는 가짜 값이다.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from db import db_session
from models import PartnerOrg
from tests.support.freelancer_production_home_seed import client_for, designate, named_user
from tests.support.production_access_support import login, make_order, make_user

ROOT = Path(__file__).resolve().parents[2]
OLD_BOARD = "/erp/production/dashboard"
OLD_SHEET = "/erp/production/tablet-sheet"
_MISSING = 99_999_999

_OLD_PARTIALS = (
    "dashboard_fragment", "dashboard_body", "filters", "filters_grid", "mobile_filters", "mobile_queue", "modals",
    "admin_override_sheet", "production_steps_sheet", "scripts", "styles", "tablet_kanban_body", "tablet_sheet",
)

#: 지운 파일 — 하나라도 다시 생기면 빨강.
DELETED_FILES = (
    "foms/web/production/dashboard.py",
    "templates/production/dashboard.html",
    *(f"templates/production/partials/{name}.html" for name in _OLD_PARTIALS),
    "static/js/production/foms-production-steps.js",
    "static/js/foms/tablet-production-kanban.js",
    "static/css/components/foms-production-steps.css",
    "foms/services/production_dashboard_filters.py",
    "foms/services/production_fragment_version.py",
    "tests/support/production_prerender_board.py",
)

#: 어디에도 없어야 할 글자 — 지운 파일의 경로(폴더까지 — 다른 화면에 같은 이름 파일이 있다: shipment/partials/tablet_sheet.html 등),
#: 다른 곳에 같은 이름이 없는 파일 이름, 옛 모듈 import 경로, 옛 endpoint 이름 · 옛 옆 시트 주소.
FORBIDDEN = (
    "production/dashboard.html",
    *(f"production/partials/{name}.html" for name in _OLD_PARTIALS),
    "tablet_kanban_body.html", "production_steps_sheet.html", "admin_override_sheet.html",
    "foms-production-steps.js", "foms-production-steps.css", "tablet-production-kanban.js",
    "production_dashboard_filters", "production_fragment_version", "production_prerender_board",
    "foms.web.production.dashboard", "production.dashboard import",
    "erp_production_page.erp_production_dashboard", "erp_production_page.erp_production_tablet_sheet",
    "erp_production_tablet_sheet", OLD_SHEET,
)

#: 예외(파일 → 그 파일에서 Jinja 주석 안에서만 허용하는 글자). 지금은 비었다 — 작업 시트 주석도 2026-11-27 고쳤다.
#: 못 고치는 파일이 생기면 여기 적고, 주석 밖에 생기면 빨강.
_COMMENT_ONLY: dict[str, tuple[str, ...]] = {}

#: 옛 endpoint 글자 ``erp_production_dashboard`` 가 남아도 되는 곳 — 부르는 것이 아니라 값이다.
_OLD_ENDPOINT_TEXT_OK = {
    # 감사 기록 값(옛 기록과 같은 글자여야 한다 — 바꾸지 않는다)
    "foms/services/production/order_write_helpers.py": '"source_screen": "erp_production_dashboard"',
    # 돌아가기 열쇠(옛 링크 · 즐겨찾기에 실려 올 수 있어 글자만 받고 첫 화면 endpoint 로 보낸다)
    "foms/services/erp_order_deeplink.py": '"erp_production_dashboard": PRODUCTION_HOME_ENDPOINT',
}
_CALLS_OLD_ENDPOINT = re.compile(r"url_for\([^)]*erp_production_dashboard|['\"]erp_production_dashboard['\"]")


def _sources() -> list[Path]:
    out: list[Path] = []
    for top in ("templates", "static", "foms"):
        for path in (ROOT / top).rglob("*"):
            if path.is_file() and path.suffix in (".html", ".js", ".css", ".py", ".json") and "__pycache__" not in path.parts:
                out.append(path)
    return out


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _without_jinja_comments(text: str) -> str:
    return re.sub(r"\{#.*?#\}", "", text, flags=re.S)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _plain(user) -> SimpleNamespace:
    """요청이 끝나면 세션이 닫힌다 — 로그인에 쓸 값만 담는다."""
    return SimpleNamespace(id=user.id, username=user.username, role=user.role)


def _old_paths(order_id: int) -> list[str]:
    return [OLD_BOARD, f"{OLD_BOARD}?focus_order={order_id}", f"{OLD_BOARD}?view=fragment",
            f"{OLD_SHEET}/{order_id}", f"{OLD_SHEET}/{_MISSING}"]


# --------------------------------------------------------------------------- #
# 1. 옛 주소 둘 — 라우트 없음. 계정마다 답을 고정한다
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("role, team", [
    ("ADMIN", None), ("ADMIN", "SALES"), ("STAFF", "PRODUCTION"), ("MANAGER", "PRODUCTION"), ("STAFF", "SALES"),
    ("STAFF", "CS"), ("STAFF", "DRAWING"), ("STAFF", "SHIPMENT"), ("VIEWER", "PRODUCTION"), ("STAFF", None),
], ids=lambda v: str(v))
def test_로그인한_직원_관리자에게_옛_주소_둘은_404(app, role, team) -> None:
    order_id = make_order("가짜옛길고객가").id
    client = app.test_client()
    login(client, _plain(make_user(f"old1127_{role}_{team}".lower(), role, team)))
    for path in _old_paths(order_id):
        resp = client.get(path)
        assert resp.status_code == 404, (path, resp.status_code, resp.headers.get("Location"))
        assert "가짜옛길고객가" not in resp.get_data(as_text=True), path


def test_시공팀은_옛_주소에서_지금처럼_출고로_간다(app) -> None:
    """시공팀 화면 이동 제한(``foms/platform/http.py``) — 보기 화면 목록 밖 /erp/ 주소는 출고로(없는 주소와 같은 답)."""
    order_id = make_order("가짜옛길고객나").id
    client = app.test_client()
    login(client, _plain(make_user("old1127_cons", "STAFF", "CONSTRUCTION")))
    for path in _old_paths(order_id):
        resp = client.get(path)
        assert resp.status_code == 302 and resp.headers["Location"].startswith("/erp/shipment"), (path, resp.status_code)


def test_시공팀은_새_첫_화면과_작업_시트를_지금처럼_연다(app) -> None:
    order_id = make_order("가짜옛길고객다").id
    client = app.test_client()
    login(client, _plain(make_user("old1127_cons_view", "STAFF", "CONSTRUCTION")))
    for path in ("/erp/production/home", f"/erp/production/sheet/{order_id}", f"/erp/production/print/{order_id}"):
        resp = client.get(path)
        assert resp.status_code == 200, (path, resp.status_code, resp.headers.get("Location"))


def test_협력사는_옛_주소에서_협력사_첫_화면으로(app) -> None:
    order_id = make_order("가짜옛길고객라").id
    org = PartnerOrg(name="가짜옛길협력사")
    db_session.add(org)
    db_session.commit()
    client = app.test_client()
    login(client, _plain(make_user("old1127_partner", "PARTNER", None, partner_org_id=org.id)))
    for path in _old_paths(order_id):
        resp = client.get(path)
        assert resp.status_code == 302 and resp.headers["Location"].endswith("/partner"), (path, resp.status_code)


def test_켜진_프리랜서는_옛_주소에서_프리랜서_홈으로(app) -> None:
    order_id = make_order("가짜옛길고객마").id
    fl = named_user("STAFF", "SALES", "가짜옛길프리")
    designate(fl, "가짜옛길프리매치")
    client = client_for(app, fl)
    for path in _old_paths(order_id):
        resp = client.get(path)
        assert resp.status_code == 302 and resp.headers["Location"].endswith("/erp/dashboard"), (path, resp.status_code)
        assert "가짜옛길고객마" not in resp.get_data(as_text=True), path


def test_로그인_없으면_옛_주소는_404(app) -> None:
    """길이 없으니 로그인 문(``login_required``)도 없다 — 로그인 화면으로 보내지 않고 없는 주소로 답한다."""
    order_id = make_order("가짜옛길고객바").id
    client = app.test_client()
    for path in _old_paths(order_id):
        for headers in ({}, {"Accept": "application/json"}):
            resp = client.get(path, headers=headers)
            assert resp.status_code == 404, (path, headers, resp.status_code, resp.headers.get("Location"))


# --------------------------------------------------------------------------- #
# 2. 생산 Blueprint — 길 넷 · 새 자리
# --------------------------------------------------------------------------- #
def test_생산_Blueprint_길은_넷뿐(app) -> None:
    rules = {rule.endpoint: rule.rule for rule in app.url_map.iter_rules()
             if rule.endpoint.startswith("erp_production_page.")}
    assert rules == {
        "erp_production_page.erp_production_home": "/erp/production/home",
        "erp_production_page.erp_production_sheet_page": "/erp/production/sheet/<int:order_id>",
        "erp_production_page.erp_production_print_sheet": "/erp/production/print/<int:order_id>",
        "erp_production_page.erp_production_part_thumb": "/erp/production/parts/thumb/<int:order_id>",
    }
    stray = [r.rule for r in app.url_map.iter_rules()
             if r.rule.startswith((OLD_BOARD, OLD_SHEET))
             or r.endpoint.endswith((".erp_production_dashboard", ".erp_production_tablet_sheet"))]
    assert stray == []


def test_Blueprint_와_템플릿_전역_셋은_blueprint_모듈에(app) -> None:
    import foms.web.production as pkg
    from foms.services.production.steps import PRODUCTION_FINISHED_STAGE
    from foms.web.production import blueprint, home, part_thumb

    assert pkg.erp_production_page_bp is blueprint.erp_production_page_bp
    assert home.erp_production_page_bp is blueprint.erp_production_page_bp
    assert part_thumb.erp_production_page_bp is blueprint.erp_production_page_bp
    for name in ("production_nav_href", "production_work_user", "PRODUCTION_FINISHED_STAGE"):
        assert name in app.jinja_env.globals, name
    assert app.jinja_env.globals["PRODUCTION_FINISHED_STAGE"] == PRODUCTION_FINISHED_STAGE


# --------------------------------------------------------------------------- #
# 3. 지운 파일 · 이름 — 되살아남 막기
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("rel", DELETED_FILES)
def test_지운_파일이_없다(rel) -> None:
    assert not (ROOT / rel).exists(), rel


def test_어디에도_지운_이름과_옛_endpoint_부르기가_없다() -> None:
    found: list[tuple[str, str]] = []
    for path in _sources():
        rel = _rel(path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        comment_only = _COMMENT_ONLY.get(rel, ())
        bare = _without_jinja_comments(text)
        for word in FORBIDDEN:
            if word in (bare if word in comment_only else text):
                found.append((rel, word))
        if "erp_production_dashboard" in text:
            ok = _OLD_ENDPOINT_TEXT_OK.get(rel)
            if _CALLS_OLD_ENDPOINT.search(text.replace(ok, "") if ok else text):
                found.append((rel, "erp_production_dashboard"))
    assert found == [], found


def test_예외_표는_실제로_있는_글자만_허락한다() -> None:
    """음성 대조: 예외 표가 낡으면(그 줄이 없어지면) 여기서 잡힌다."""
    for rel, text in _OLD_ENDPOINT_TEXT_OK.items():
        assert text in _read(rel), rel


def test_검사가_일을_한다_음성_대조() -> None:
    """지운 이름을 넣은 글 · 옛 endpoint 를 부르는 글은 잡힌다(검사 식이 비어 있지 않다)."""
    assert any(word in "{% include 'production/partials/tablet_kanban_body.html' %}" for word in FORBIDDEN)
    assert any(word in "<script src=\"/static/js/foms/tablet-production-kanban.js\"></script>" for word in FORBIDDEN)
    assert _CALLS_OLD_ENDPOINT.search("url_for('erp_production_page.erp_production_dashboard')")
    assert "tablet_kanban_body.html" not in _without_jinja_comments("{# 칸반 tablet_kanban_body.html 과 같은 #}")


# --------------------------------------------------------------------------- #
# 4. 공용 파일에 남은 몫
# --------------------------------------------------------------------------- #
def test_도메인_시트_JS는_쓰기_보류_확인_출고_저장만_남는다() -> None:
    js = _read("static/js/foms/tablet-domain-sheets.js")
    for keep in ('"/production/start"', '"/production/complete"', '"/production/rework"', '"/production/cancel"',
                 '"/production/uncomplete"', "/production/hold", "/production/change-ack", "/api/erp/shipment/update/",
                 "removeInboxRow", "FomsReasonSheet", "FomsAdminOverride", "HOLD_ACTIVE", '"sheet-cancel"',
                 "data-kanban-action='change-ack'", "data-production-split-note"):
        assert keep in js, keep
    for gone in ("foms-kanban", "data-tablet-prod-", "tablet-prod-board", "foms-prod-change-modal", "data-prod-change-",
                 "applyProdFilter", "foms_tablet_prod_fullscreen", "maybeShowChangeModal"):
        assert gone not in js, gone
    assert "foms-kanban" not in _read("static/js/foms/tablet-side-sheet.js")


def test_확인_창_꼴_CSS는_남고_칸반_선택자는_없다() -> None:
    body = re.sub(r"/\*.*?\*/", "", _read("static/css/foundation/foms-tablet-production-kanban.css"), flags=re.S)
    assert ".foms-prod-change-modal__dialog" in body and ".foms-prod-change-modal.is-open" in body
    for gone in (".foms-kanban", ".tablet-prod-", ".foms-production-legacy-queue", ".foms-prod-sheet", ".foms-prod-pcbar"):
        assert gone not in body, gone
    bundle = _read("static/css/foundation/foms-tablet-bundle.css")
    head = _read("templates/partials/shared/layout_head.html")
    assert '@import url("foms-tablet-production-kanban.css?v=20261127p")' in bundle
    assert "foms-tablet-bundle.css') }}?v=20261127p" in head  # 자식 핀만 올리면 기기에 안 닿는다 — 부모 핀도 같이


def test_도메인_시트_JS_핀은_싣는_곳이_같은_값() -> None:
    """싣는 곳 셋(첫 화면 · 작업 시트 · 출고 CHAIN) + 출고 진입 핀."""
    for rel in ("templates/production/partials/home_body.html", "templates/production/sheet.html"):
        assert "tablet-domain-sheets.js') }}?v=20261128b" in _read(rel), rel
    assert "/static/js/foms/tablet-domain-sheets.js?v=20261128b" in _read("static/js/shipment/shipment-entry.js")
    assert "shipment-entry.js') }}?v=20261128b" in _read("templates/shipment/partials/dashboard_scripts.html")
