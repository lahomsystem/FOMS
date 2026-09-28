"""모바일 v3 셸 삭제(2026-09-28) 회귀 계약.

사용자 결정: "모바일 v3 쓰지 않으니까 아예 삭제". v3 셸(Field OS)의 템플릿·CSS·JS·
쿠키 토글(``foms_shell_pref``)·v3 코호트 게이트(``FOMS_SHELL_V3_*``)를 전부 지웠다.

여기서 잠그는 것:
  1. 옛 v3 조건을 **전부** 갖춘 요청(v3 코호트 env + ``foms_shell_pref=v3`` 쿠키 +
     모바일 UA)도 v2 셸을 받는다 — 서랍·v2 critical CSS 가 있고 v3 마크업·자산은 0.
  2. v2 서랍에 "새 모바일(v3)" 버튼이 없다(헤더 전환 버튼도 없다).
  3. v3 로 빠지면서 v2 CSS 번들 없이 v2 조각만 그려지던 무스타일 화면(claude_master
     모바일 UA 제보 — 회색 검색·알림 버튼, AS '현장 사진 먼저' 바)이 다시 생기지 않는다.
  4. 저장소에 v3 셸 파일이 되살아나지 않는다.

``FOMS_V3_SHELL_COHORT`` 는 이름과 달리 **v2 모바일 코호트 키**다(Railway 환경변수).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import User

ROOT = Path(__file__).resolve().parents[2]

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

V2_CRITICAL_CSS = 'id="foms-mobile-v2-critical-css"'
V2_SURFACES_CSS = "css/foundation/foms-mobile-surfaces.css"
V2_DRAWER = 'id="erp-mobile-menu-drawer"'

# 옛 v3 셸이 남기던 흔적들 — 응답 어디에도 있으면 안 된다.
V3_MARKERS = (
    "css/v3/foms-mobile-v3.css",
    "js/v3/foms-mobile-v3.js",
    "js/v3/foms-shell-toggle.js",
    "data-foms-app-shell-v3",
    "fos-shell-v3",
    "fos-v3-mobile-scope",
    "fos-v3-desktop-fallback",
    "data-foms-shell-toggle",
    "erp-mobile-shell-header__switch",
    "has-v3switch",
    "새 모바일(v3)",
    "기존 화면",
)

# 도메인 대시보드 6종 — 예전엔 전부 v3 분기가 있었다. v2 모바일 표면 표식은
# 각 섹션 aria-label(도메인마다 유일).
DOMAIN_V2_SURFACES = [
    ("/erp/dashboard", ("모바일 홈 대시보드", "모바일 홈 컨트롤 타워")),
    ("/erp/measurement", ("실측 모바일 대시보드",)),
    ("/erp/drawing-workbench", ("도면 작업 큐",)),
    ("/erp/production/dashboard", ("생산 모바일 대시보드",)),
    ("/erp/construction/dashboard", ("시공 모바일 대시보드",)),
    ("/erp/shipment", ("출고 모바일 대시보드",)),
]


def _login_admin(client, username: str) -> User:
    """ADMIN(team=CS) 사용자를 만들고 로그인 세션을 심는다."""
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="셸 회귀 관리자",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _enable_old_v3_conditions(client, monkeypatch, user_id: int) -> None:
    """예전이면 v3 를 받았을 조건을 모두 켠다(v2 코호트 + v3 코호트 + v3 쿠키)."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user_id))
    monkeypatch.setenv("FOMS_SHELL_V3_ENABLED", "true")
    monkeypatch.setenv("FOMS_SHELL_V3_COHORT", str(user_id))
    client.set_cookie("foms_shell_pref", "v3")


def _assert_no_v3(body: str, where: str) -> None:
    for marker in V3_MARKERS:
        assert marker not in body, f"{where}: v3 흔적 {marker!r} 이 남아 있다"


def test_v3_쿠키와_v3_코호트가_있어도_v2_셸과_서랍을_받는다(client, monkeypatch) -> None:
    user = _login_admin(client, "shell_v3_gone_home")
    _enable_old_v3_conditions(client, monkeypatch, user.id)

    response = client.get("/erp/dashboard", headers={"User-Agent": MOBILE_UA})

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert V2_CRITICAL_CSS in body
    assert V2_SURFACES_CSS in body
    assert V2_DRAWER in body
    assert 'class="erp-mobile-shell-header' in body
    _assert_no_v3(body, "/erp/dashboard")


@pytest.mark.parametrize("cookie", ["v3", "v2", None])
def test_v2_서랍에_새_모바일_v3_버튼이_없다(client, monkeypatch, cookie) -> None:
    """예전엔 v3 자격자가 v2 로 돌아와 있으면(쿠키 ``v2``) 서랍에 "새 모바일(v3)" 이 떴다."""
    user = _login_admin(client, f"shell_v3_gone_drawer_{cookie}")
    _enable_old_v3_conditions(client, monkeypatch, user.id)
    if cookie is None:
        client.delete_cookie("foms_shell_pref")
    else:
        client.set_cookie("foms_shell_pref", cookie)

    body = client.get("/erp/dashboard").get_data(as_text=True)

    start = body.index(V2_DRAWER)
    drawer = body[start:start + 20000]
    assert "새 모바일(v3)" not in drawer
    assert "erp-mobile-menu-drawer__link--v3" not in drawer
    assert "data-foms-shell-toggle" not in drawer
    # 서랍 자체는 멀쩡하다 — 계정 영역까지 그려진다.
    assert "erp-mobile-menu-drawer__account" in drawer


@pytest.mark.parametrize(("path", "markers"), DOMAIN_V2_SURFACES)
def test_도메인_대시보드는_옛_v3_조건에서도_v2_모바일_표면을_그린다(
    client, monkeypatch, path, markers
) -> None:
    username = "shell_v3_gone_" + path.strip("/").replace("/", "_")
    user = _login_admin(client, username)
    _enable_old_v3_conditions(client, monkeypatch, user.id)

    response = client.get(path, headers={"User-Agent": MOBILE_UA})

    assert response.status_code == 200, f"{path} -> {response.status_code}"
    body = response.get_data(as_text=True)
    assert any(m in body for m in markers), f"{path} 에 v2 모바일 표면이 없다({markers})"
    assert V2_CRITICAL_CSS in body, f"{path} 에 v2 critical CSS 가 없다"
    _assert_no_v3(body, path)


def test_AS_대시보드_v2_조각은_v2_CSS_번들과_함께_온다(client, monkeypatch) -> None:
    """claude_master 모바일 UA 제보: v3 로 판정되면 v2 CSS 번들이 빠진 채 AS 카메라 바
    같은 v2 조각만 그려져 회색 무스타일 버튼이 됐다. 이제 조각과 번들이 항상 같이 온다."""
    user = _login_admin(client, "shell_v3_gone_as")
    _enable_old_v3_conditions(client, monkeypatch, user.id)

    response = client.get("/erp/as", headers={"User-Agent": MOBILE_UA})

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert V2_SURFACES_CSS in body
    assert V2_CRITICAL_CSS in body
    _assert_no_v3(body, "/erp/as")


def test_v2_코호트_밖이면_v3_쿠키가_있어도_legacy_다(client, monkeypatch) -> None:
    _login_admin(client, "shell_v3_gone_legacy")
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "9999999")
    monkeypatch.setenv("FOMS_SHELL_V3_ENABLED", "true")
    monkeypatch.setenv("FOMS_SHELL_V3_COHORT", "all")
    client.set_cookie("foms_shell_pref", "v3")

    body = client.get("/erp/dashboard").get_data(as_text=True)

    assert V2_CRITICAL_CSS not in body
    _assert_no_v3(body, "/erp/dashboard(legacy)")


def test_resolve_shell_variant_는_v3_를_돌려주지_않는다(app, monkeypatch) -> None:
    from foms.services import feature_flags

    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "3")
    monkeypatch.setenv("FOMS_SHELL_V3_ENABLED", "true")
    monkeypatch.setenv("FOMS_SHELL_V3_COHORT", "3")
    with app.test_request_context("/", headers={"Cookie": "foms_shell_pref=v3"}):
        assert feature_flags.resolve_shell_variant(3) == "v2"
        assert feature_flags.resolve_shell_variant_cached(3) == "v2"
    assert feature_flags.resolve_shell_variant(99) == "legacy"
    assert not hasattr(feature_flags, "is_shell_v3_eligible")
    assert not hasattr(feature_flags, "note_shell_v3_view")


def test_v3_셸_파일이_저장소에_없다() -> None:
    for rel in (
        "templates/partials/v3",
        "static/css/v3",
        "static/js/v3",
    ):
        assert not (ROOT / rel).exists(), f"{rel} 가 되살아났다"
    offenders = []
    for base in ("templates", "static/js", "static/css", "foms"):
        for path in (ROOT / base).rglob("*"):
            if path.suffix not in {".html", ".js", ".css", ".py"} or not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(t in text for t in ("partials/v3/", "shell_v3_eligible", "data-foms-shell-toggle")):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], f"v3 셸 참조가 남았다: {offenders}"
