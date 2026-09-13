"""모바일 v2 표면 봉쇄 계약 — 렌더된 DOM 을 실제로 파싱해서 검사한다.

2026-09-13 dashboard_mobile_v2_body.html:52 의 짝 없는 </div> 가 section+.erp-dashboard 를
조기 종료시켜 PC 대시보드에 모바일 큐가 누출됐다. 당시 기존 게이트 45개가 전부 초록이었다 —
전부 문자열 인덱스 검사였기 때문이다.

왜 이 파일이 따로 있는가:
    ``tests/visual/test_p1_mockup_*.py`` 는 ``html.find()`` 로 바이트 위치만 비교한다.
    짝 없는 ``</div>`` 는 바이트를 하나도 지우지 않고 **조상 관계만** 바꾸므로 그런 게이트는
    영원히 초록이다. 그래서 여기서는 파서에게 조상 사슬을 물어본다.

봉쇄 불변식:
    모바일 v2 마커는 전부 ``.foms-mobile-v2-dashboard`` 의 자손이어야 한다. 그래야 은닉 CSS
    (``static/css/foundation/foms-mobile-v2-surfaces-hide.css:27-31`` 의
    ``display:none !important``)가 데스크톱에서 발화한다. 마커가 섹션 밖으로 빠져나가면
    은닉 규칙이 겨냥하는 클래스가 아니게 되어 PC 표 아래에 그대로 보인다.

예외:
    ``.foms-shell-fab`` 은 주문 대시보드 타워 분기에서 **섹션의 형제**로 두는 것이 설계다
    (``foms-mobile-v2-surfaces-hide.css:4`` 주석 "타워 섹션의 형제 노드"). 그래서 주문
    대시보드 봉쇄 목록에는 넣지 않는다. 반대로 시공·생산·출고·실측·이력 표면은 FAB 이
    섹션 **안**이 설계라 그쪽에서는 봉쇄 대상이다.

파서:
    ``beautifulsoup4``(``requirements.txt:110``) + 표준 ``html.parser``. lxml 은
    requirements 에 선언돼 있지 않으므로 쓰지 않는다.
"""

from __future__ import annotations

import datetime

import pytest
from bs4 import BeautifulSoup

from foms.services.datetime_kst import get_today_kst
from werkzeug.security import generate_password_hash

ORDERS_QUEUE_URL = "/erp/dashboard?view=queue"
ORDERS_TOWER_URL = "/erp/dashboard"

#: 주문 큐 분기에서 반드시 ``.foms-mobile-v2-dashboard`` 안에 있어야 하는 마커.
#: ``[data-foms-mobile-queue-sentinel]`` 은 ``{% if page < total_pages %}``
#: (dashboard_mobile_v2_body.html:123) 라 소량 시드에서는 0건이므로 존재를 강제하지 않는다.
ORDERS_QUEUE_MARKERS = (
    "[data-foms-mobile-queue-chunk]",
    "[data-foms-mobile-queue-list]",
    ".foms-queue-card-v2",
)

#: 같은 봉쇄 계약을 태우는 다른 모바일 v2 표면.
#: (테스트 id, URL, 섹션 선택자, 마커들) — 이 표면들은 FAB 이 섹션 안이 설계다.
CROSS_SURFACE_CASES = (
    pytest.param(
        "/erp/construction/dashboard",
        ".foms-mobile-v2-dashboard.erp-construction-mobile-v2",
        (".foms-shell-fab",),
        id="construction",
    ),
    pytest.param(
        "/erp/production/dashboard",
        ".foms-mobile-v2-dashboard.erp-production-mobile-v2",
        (".foms-shell-fab",),
        id="production",
    ),
    pytest.param(
        "/erp/shipment",
        ".foms-mobile-v2-dashboard.erp-shipment-mobile-v2",
        (".foms-shell-fab",),
        id="shipment",
    ),
    pytest.param(
        "/erp/measurement",
        ".foms-mobile-v2-dashboard.erp-measurement-mobile-v2",
        (".foms-shell-fab",),
        id="measurement",
    ),
    pytest.param(
        "/erp/history/?stage=RECEIVED",
        ".foms-mobile-v2-dashboard.erp-history-mobile-v2",
        (".foms-shell-fab",),
        id="history",
    ),
)


# ---------------------------------------------------------------------------
# 시드 / 로그인
# ---------------------------------------------------------------------------
def _seed_admin(app, username: str = "containment_admin") -> int:
    """ADMIN 사용자 1명을 만들고 id 를 돌려준다."""
    from db import db_session
    from models import User

    with app.app_context():
        row = db_session.query(User).filter_by(username=username).first()
        if row is None:
            row = User(
                username=username,
                password=generate_password_hash("admin"),
                role="ADMIN",
                team="CS",
                name=username,
            )
            db_session.add(row)
            db_session.commit()
        return int(row.id)


def _seed_orders(app, count: int = 3) -> list[int]:
    """큐 카드가 실제로 렌더되도록 주문을 심는다.

    ``dashboard_mobile_v2_body.html:116`` 이 ``{% if orders %}`` 라서, 주문을 심지 않으면
    마커가 0건이고 봉쇄 검사가 **공허하게 초록**이 된다. 그래서 아래 계약은
    ``present >= 1`` 존재 assert 를 함께 건다.
    """
    from db import db_session
    from models import Order

    # CI 는 UTC 로 돌아 date.today() 는 한국 밤에 하루 어긋난다(프로젝트 규약).
    today = get_today_kst().isoformat()
    ids: list[int] = []
    with app.app_context():
        for i in range(count):
            order = Order(
                received_date=today,
                customer_name=f"봉쇄시드{i}",
                phone=f"010-0000-000{i}",
                address="서울 중구 동호로14길 35",
                product="부엌가구",
                status="RECEIVED",
                is_erp_order=True,
                structured_data={},
            )
            db_session.add(order)
        db_session.commit()
        ids = [
            int(row.id)
            for row in db_session.query(Order).order_by(Order.id.asc()).all()
        ]
    return ids


def _login(client, username: str = "containment_admin") -> None:
    client.post(
        "/login",
        data={"username": username, "password": "admin"},
        follow_redirects=True,
    )


@pytest.fixture
def v2_client(app, client, monkeypatch: pytest.MonkeyPatch):
    """v2 셸 코호트로 로그인한 테스트 클라이언트 + 주문 60건 시드.

    60건인 이유: 큐 한 페이지가 50장이라 그보다 적게 심으면
    ``dashboard_mobile_v2_body.html:123`` 의 ``{% if page < total_pages %}`` 이 거짓이 되어
    **센티넬이 0건**이고, 아래 센티넬 봉쇄 테스트가 0 == 0 으로 공허하게 초록이 된다.

    ``resolve_shell_variant``(foms/services/feature_flags.py:257)는 v3 자격이 있으면
    v3 를 돌려주고, v3 에서는 모바일 v2 바디가 애초에 include 되지 않는다
    (``dashboard_main.html:194`` 의 ``shell_variant != 'v3'``). 그래서 v3 를 명시적으로 끈다.
    """
    uid = _seed_admin(app)
    _seed_orders(app, 60)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(uid))
    monkeypatch.delenv("FOMS_SHELL_V3_ENABLED", raising=False)
    monkeypatch.delenv("FOMS_SHELL_V3_COHORT", raising=False)
    _login(client)
    return client


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------
def _soup(client, url: str) -> BeautifulSoup:
    """URL 을 받아 파싱한다(로그인 리다이렉트면 즉시 실패)."""
    res = client.get(url)
    assert res.status_code == 200, f"{url} -> HTTP {res.status_code}"
    html = res.data.decode("utf-8")
    assert "/login" not in (res.headers.get("Location") or ""), f"{url} 로그인 실패"
    return BeautifulSoup(html, "html.parser")


def _containment_report(
    soup: BeautifulSoup, markers, section_selector: str
) -> list[tuple[str, int, int]]:
    """(마커, 전체 개수, 섹션 안 개수) 삼중항 목록."""
    report: list[tuple[str, int, int]] = []
    for marker in markers:
        present = len(soup.select(marker))
        contained = len(soup.select(f"{section_selector} {marker}"))
        report.append((marker, present, contained))
    return report


# ---------------------------------------------------------------------------
# 계약 A — 모바일 v2 마커 봉쇄 (주문 큐 분기)
# ---------------------------------------------------------------------------
def test_orders_queue_markers_stay_inside_mobile_v2_section(v2_client):
    """큐 분기 마커가 전부 ``.foms-mobile-v2-dashboard`` 자손이어야 한다."""
    soup = _soup(v2_client, ORDERS_QUEUE_URL)
    report = _containment_report(
        soup, ORDERS_QUEUE_MARKERS, ".foms-mobile-v2-dashboard"
    )

    missing = [row for row in report if row[1] < 1]
    assert not missing, (
        "마커가 아예 렌더되지 않았다 — 시드/코호트가 깨져 테스트가 공허하게 초록이 된다. "
        f"CONTAINMENT REPORT: {report}"
    )

    escaped = [row for row in report if row[1] != row[2]]
    assert not escaped, (
        "모바일 v2 마커가 .foms-mobile-v2-dashboard 밖으로 탈출했다 — 데스크톱 은닉 CSS 가 "
        "발화하지 못해 PC 화면에 모바일 큐가 보인다. "
        f"CONTAINMENT REPORT: {report}"
    )


def test_orders_queue_sentinel_when_present_stays_inside(v2_client):
    """센티넬은 존재를 강제하지 않되(조건부 렌더), 있으면 반드시 섹션 안이다."""
    soup = _soup(v2_client, ORDERS_QUEUE_URL)
    marker = "[data-foms-mobile-queue-sentinel]"
    present = len(soup.select(marker))
    contained = len(soup.select(f".foms-mobile-v2-dashboard {marker}"))
    assert present >= 1, (
        "센티넬이 아예 렌더되지 않았다 — 시드가 한 페이지(50장)보다 적으면 이 테스트가 "
        "0 == 0 으로 공허하게 초록이 된다. v2_client 시드 수를 확인하라."
    )
    assert present == contained, (
        "무한스크롤 센티넬이 섹션 밖으로 탈출했다 — mobile-queue-scroll.js:12 의 "
        "root.querySelector 가 null 을 받아 폰 무한스크롤이 죽는다. "
        f"CONTAINMENT REPORT: [({marker!r}, {present}, {contained})]"
    )


def test_orders_tower_branch_markers_stay_inside(app, client, monkeypatch):
    """타워 분기(드릴 없음)도 같은 봉쇄를 지킨다.

    FAB 은 타워에서 섹션의 **형제**가 설계라 봉쇄 대상이 아니다.
    """
    uid = _seed_admin(app)
    _seed_orders(app, 60)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(uid))
    monkeypatch.delenv("FOMS_SHELL_V3_ENABLED", raising=False)
    monkeypatch.delenv("FOMS_SHELL_V3_COHORT", raising=False)
    _login(client)

    soup = _soup(client, ORDERS_TOWER_URL)
    section = soup.select_one(".foms-mobile-v2-dashboard")
    assert section is not None, "타워 분기에서 모바일 v2 섹션이 아예 없다"

    report = _containment_report(
        soup, ("[data-foms-tower]",), ".erp-dashboard"
    )
    escaped = [row for row in report if row[1] != row[2]]
    assert not escaped, f"타워 섹션이 .erp-dashboard 밖으로 탈출했다: {report}"


# ---------------------------------------------------------------------------
# 계약 B — 데스크톱 컨테이너 봉쇄
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "descendant",
    ["#erp-dashboard-config", "#erpAttachmentsCategoryModal"],
)
def test_desktop_container_keeps_trailing_nodes(v2_client, descendant):
    """모바일 v2 바디 **뒤에** 오는 노드가 ``.erp-dashboard`` 안에 남아 있어야 한다.

    섹션이 조기 종료되면 조상 ``.erp-dashboard`` 까지 함께 닫혀서 이후 전부가
    ``main`` 직속으로 탈출한다(모달 전체 + 대시보드 설정 노드).
    """
    soup = _soup(v2_client, ORDERS_QUEUE_URL)
    assert soup.select_one(descendant) is not None, (
        f"{descendant} 가 응답에 아예 없다 — 오라클이 성립하지 않는다"
    )
    assert soup.select_one(f".erp-dashboard {descendant}") is not None, (
        f"{descendant} 가 .erp-dashboard 밖으로 탈출했다 — 모바일 v2 섹션이 조기 종료되면서 "
        "조상 컨테이너까지 함께 닫혔다"
    )


def test_desktop_container_intact_on_tower_branch(app, client, monkeypatch):
    """음성 대조군 — 타워 분기(정상)에서는 같은 노드가 컨테이너 안이다."""
    uid = _seed_admin(app)
    _seed_orders(app, 60)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(uid))
    monkeypatch.delenv("FOMS_SHELL_V3_ENABLED", raising=False)
    monkeypatch.delenv("FOMS_SHELL_V3_COHORT", raising=False)
    _login(client)

    soup = _soup(client, ORDERS_TOWER_URL)
    for descendant in ("#erp-dashboard-config", "#erpAttachmentsCategoryModal"):
        assert soup.select_one(f".erp-dashboard {descendant}") is not None, (
            f"타워 분기에서도 {descendant} 가 탈출했다"
        )


# ---------------------------------------------------------------------------
# 계약 C — 횡단 확산 차단 (다른 모바일 v2 표면)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("url,section_selector,markers", CROSS_SURFACE_CASES)
def test_other_mobile_v2_surfaces_keep_containment(
    v2_client, url, section_selector, markers
):
    """시공·생산·출고·실측·이력 표면도 같은 봉쇄 계약을 지킨다.

    정적 태그 계수를 게이트로 쓰지 않는 이유: 조건부 렌더(``{% if %}``)가 있어서 소스
    균형과 렌더 결과가 일치하지 않는다. 반드시 렌더 후 파싱이다.
    """
    soup = _soup(v2_client, url)
    section = soup.select_one(section_selector)
    assert section is not None, (
        f"{url} 에 모바일 v2 섹션({section_selector})이 없다 — 코호트/플래그가 깨졌다"
    )

    report = _containment_report(soup, markers, section_selector)
    missing = [row for row in report if row[1] < 1]
    assert not missing, f"{url}: 마커가 렌더되지 않았다. CONTAINMENT REPORT: {report}"

    escaped = [row for row in report if row[1] != row[2]]
    assert not escaped, (
        f"{url}: 모바일 v2 마커가 섹션 밖으로 탈출했다. CONTAINMENT REPORT: {report}"
    )
