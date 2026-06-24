"""P1-02: unified search service + overlay wiring."""

from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[2]


def test_chosung_query_detection() -> None:
    from foms.services.foms_unified_search import is_chosung_query

    assert is_chosung_query("ㄱㅁㅇ") is True
    assert is_chosung_query("고명") is False


def test_matches_query_chosung_prefix() -> None:
    from foms.services.foms_unified_search import matches_query

    assert matches_query("고명옥", "ㄱㅁㅇ") is True
    assert matches_query("고명옥", "ㄱㅅ") is False


def test_search_overlay_template_contract() -> None:
    overlay = (ROOT / "templates/partials/shared/foms_search_overlay.html").read_text(
        encoding="utf-8"
    )
    assert 'id="foms-search-overlay"' in overlay
    assert "hx-trigger" in overlay
    assert "delay:200ms" in overlay
    assert "data-foms-search-open" not in overlay
    header = (ROOT / "templates/partials/shared/erp_mobile_shell_header.html").read_text(
        encoding="utf-8"
    )
    assert "data-foms-search-open" in header
    app_shell = (ROOT / "templates/partials/shared/foms_app_shell.html").read_text(
        encoding="utf-8"
    )
    shell = (ROOT / "templates/partials/shared/erp_mobile_shell.html").read_text(
        encoding="utf-8"
    )
    assert "foms_app_shell.html" in shell
    assert "foms_search_overlay.html" in app_shell
    assert "js/foms/search.js" in app_shell


def test_search_assets_imported() -> None:
    surfaces = (ROOT / "static/css/foundation/foms-mobile-surfaces.css").read_text(encoding="utf-8")
    js = (ROOT / "static/js/foms/search.js").read_text(encoding="utf-8")
    app_shell = (ROOT / "templates/partials/shared/foms_app_shell.html").read_text(encoding="utf-8")
    assert "foms-search-overlay.css" in surfaces
    assert "foms.search.recent.v1" in js
    assert "ArrowDown" in js
    assert "navigateToResult" in js
    assert "beginShellNavigationPending" in js
    assert "bypassCache" in js
    assert "clearSearchResults" in js
    shell_branch = js.split("function navigateToResult(link)")[1].split("function highlightIndex")[0]
    assert shell_branch.index("beginShellNavigationPending") < shell_branch.index("closeDialog()")
    assert "bypassCache: true" in shell_branch
    assert shell_branch.index("navigateByShell") < shell_branch.index("window.location.assign(href)")
    assert "mobile-queue-focus.js" in app_shell


def test_unified_search_finds_customer(app) -> None:
    from db import db_session
    from foms.services.foms_unified_search import search_unified
    from models import Order, User

    with app.app_context():
        user = User(
            username="search_overlay_user",
            password=generate_password_hash("admin"),
            role="ADMIN",
            team="CS",
            name="Search User",
        )
        db_session.add(user)
        db_session.commit()

        order = Order(
            received_date="2026-05-30",
            customer_name="고명옥",
            phone="010-2690-2242",
            address="Seoul",
            product="거실장",
            status="RECEIVED",
            is_erp_order=True,
            structured_data={
                "parties": {"customer": {"name": "고명옥", "phone": "010-2690-2242"}}
            },
        )
        db_session.add(order)
        db_session.commit()

        by_name = search_unified(db_session, "고명")
        assert by_name["customer"]
        href = by_name["customer"][0]["href"]
        assert f"focus_order={order.id}" in href
        assert "open=erp-order" not in href
        assert "view=queue" in href or "/erp/" in href
        by_chosung = search_unified(db_session, "ㄱㅁㅇ")
        assert by_chosung["customer"]


def test_unified_search_drawing_href_uses_workbench(app) -> None:
    from db import db_session
    from foms.services.foms_unified_search import search_unified
    from models import Order

    with app.app_context():
        order = Order(
            received_date="2026-05-30",
            customer_name="도면고객",
            phone="010-1111-2222",
            address="Seoul",
            product="붙박이",
            status="DRAWING",
            erp_stage_code="DRAWING",
            is_erp_order=True,
            blueprint_image_url="https://example.com/plan.png",
            structured_data={
                "parties": {"customer": {"name": "도면고객"}},
                "workflow": {"stage": "DRAWING"},
            },
        )
        db_session.add(order)
        db_session.commit()

        hits = search_unified(db_session, "도면고객", group="drawing")
        assert hits["drawing"]
        href = hits["drawing"][0]["href"]
        assert href.startswith("/erp/drawing-workbench?")
        assert f"focus_order={order.id}" in href
        assert "open=erp-order" not in href


def test_search_api_json(client, app) -> None:
    from db import db_session
    from models import User
    from werkzeug.security import generate_password_hash

    with app.app_context():
        user = User(
            username="search_api_user",
            password=generate_password_hash("admin"),
            role="ADMIN",
            team="CS",
            name="API User",
        )
        db_session.add(user)
        db_session.commit()

    client.post(
        "/login",
        data={"username": "search_api_user", "password": "admin"},
        follow_redirects=True,
    )
    response = client.get("/api/foms/search?q=고명&group=customer")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert "customer" in payload["data"]


def test_search_fragment_route(client, app) -> None:
    from db import db_session
    from models import User
    from werkzeug.security import generate_password_hash

    with app.app_context():
        user = User(
            username="search_frag_user",
            password=generate_password_hash("admin"),
            role="ADMIN",
            team="CS",
            name="Frag User",
        )
        db_session.add(user)
        db_session.commit()

    client.post(
        "/login",
        data={"username": "search_frag_user", "password": "admin"},
        follow_redirects=True,
    )
    response = client.get("/api/foms/search/fragment?q=test&group=all")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "foms-search-overlay" in body or "foms-search-overlay__empty" in body
    partial = (ROOT / "templates/partials/shared/foms_search_results_partial.html").read_text(
        encoding="utf-8"
    )
    assert "data-foms-erp-no-shell" in partial
    assert "foms-search-overlay__link-meta" in partial
    assert "item.stage_label" in partial
    assert "item.order_id" in partial
    assert "item.schedule_summary" in partial


def test_unified_search_customer_hit_includes_phone_and_address(app) -> None:
    from db import db_session
    from foms.services.foms_unified_search import search_unified
    from models import Order

    with app.app_context():
        order = Order(
            received_date="2026-05-30",
            customer_name="소마디자인(가평)",
            phone="010-3377-5193",
            address="Legacy column",
            product="인테리어",
            status="CONSTRUCTION",
            is_erp_order=True,
            structured_data={
                "parties": {
                    "customer": {"name": "소마디자인(가평)", "phone": "010-3377-5193"},
                },
                "site": {"address_full": "경기 가평군 청평면"},
            },
        )
        db_session.add(order)
        db_session.commit()

        hits = search_unified(db_session, "소마")
        assert hits["customer"]
        hit = hits["customer"][0]
        assert hit["title"] == "소마디자인(가평)"
        assert hit["phone"] == "010-3377-5193"
        assert hit["address"] == "경기 가평군 청평면"
        assert hit["stage_label"] == "시공"
        assert hit["order_id"] == order.id
        assert "010-3377-5193" in hit["subtitle"]
        assert "경기 가평군 청평면" in hit["subtitle"]


def test_unified_search_includes_construction_schedule_summary(app) -> None:
    """CONSTRUCTION stage hit exposes 시공일 in schedule_summary for overlay."""
    from db import db_session
    from foms.services.foms_unified_search import search_unified
    from models import Order

    with app.app_context():
        order = Order(
            received_date="2026-06-01",
            customer_name="신현순",
            phone="010-2566-2973",
            address="Incheon",
            product="붙박이",
            status="CONSTRUCTION",
            erp_stage_code="CONSTRUCTION",
            is_erp_order=True,
            structured_data={
                "parties": {"customer": {"name": "신현순", "phone": "010-2566-2973"}},
                "workflow": {"stage": "CONSTRUCTION"},
                "schedule": {
                    "measurement": {"date": "2026-06-16"},
                    "construction": {"date": "2026-06-20"},
                },
            },
        )
        db_session.add(order)
        db_session.commit()

        hits = search_unified(db_session, "신현")
        assert hits["customer"]
        hit = hits["customer"][0]
        assert hit["schedule_summary"] == "시공 2026-06-20"


def test_unified_search_duplicate_customer_hits_show_stage_and_order_id(app) -> None:
    """동명·동주소 다건 — stage_label + order_id로 구분."""
    from db import db_session
    from foms.services.foms_unified_search import search_unified
    from models import Order

    with app.app_context():
        completed = Order(
            received_date="2024-01-01",
            customer_name="에잇포인트",
            phone="010-9102-8202",
            address="Seoul",
            product="책장",
            status="COMPLETED",
            is_erp_order=True,
            structured_data={
                "parties": {"customer": {"name": "에잇포인트", "phone": "010-9102-8202"}},
                "site": {"address_full": "서울 강남구"},
            },
        )
        construction = Order(
            received_date="2024-06-01",
            customer_name="에잇포인트",
            phone="010-9102-8202",
            address="Seoul",
            product="책장",
            status="CONSTRUCTION",
            is_erp_order=True,
            structured_data={
                "parties": {"customer": {"name": "에잇포인트", "phone": "010-9102-8202"}},
                "site": {"address_full": "서울 강남구"},
                "workflow": {"stage": "CONSTRUCTION"},
            },
        )
        db_session.add(completed)
        db_session.add(construction)
        db_session.commit()
        completed_id = completed.id
        construction_id = construction.id

        hits = search_unified(db_session, "에잇")
        assert len(hits["customer"]) == 2
        stage_by_id = {hit["order_id"]: hit["stage_label"] for hit in hits["customer"]}
        assert stage_by_id[completed_id] == "완료"
        assert stage_by_id[construction_id] == "시공"
        hrefs = {hit["order_id"]: hit["href"] for hit in hits["customer"]}
        assert f"focus_order={completed_id}" in hrefs[completed_id]
        assert "/erp/completion" in hrefs[completed_id]
        assert f"focus_order={construction_id}" in hrefs[construction_id]
        assert "/erp/construction/dashboard" in hrefs[construction_id]


def test_unified_search_history_fallback_finds_non_erp_order(app) -> None:
    """ERP pass skips non-ERP rows; history pass finds them (PC history parity)."""
    from db import db_session
    from foms.services.foms_unified_search import search_unified
    from models import Order

    with app.app_context():
        order = Order(
            received_date="2024-01-01",
            customer_name="장성민",
            phone="010-4781-6447",
            address="Seoul",
            product="주방",
            status="COMPLETED",
            is_erp_order=False,
        )
        db_session.add(order)
        db_session.commit()

        hits = search_unified(db_session, "장성민")
        assert hits["customer"]
        assert hits["customer"][0]["order_id"] == order.id
        assert hits["customer"][0]["href"].startswith(f"/edit/{order.id}")


def test_relevance_rank_orders_exact_before_partial() -> None:
    """관련도 정렬(A4): 고객명 정확 > 접두 > 부분 > 기타."""
    from foms.services.foms_unified_search import _relevance_rank
    from models import Order

    def mk(name: str) -> Order:
        order = Order(
            customer_name=name,
            structured_data={"parties": {"customer": {"name": name}}},
        )
        order.id = 1
        return order

    assert _relevance_rank(mk("김수"), "김수")[0] == 0      # exact
    assert _relevance_rank(mk("김수민"), "김수")[0] == 1    # prefix
    assert _relevance_rank(mk("강김수"), "김수")[0] == 2    # substring
    assert _relevance_rank(mk("박영희"), "김수")[0] == 3    # other field only


def test_unified_search_exact_match_survives_partial_flood(app) -> None:
    """부분일치 신규 주문이 많아도 정확일치 과거 주문이 8칸에서 밀려나지 않는다(A4)."""
    from db import db_session
    from foms.services.foms_unified_search import search_unified
    from models import Order

    with app.app_context():
        exact = Order(
            received_date="2020-01-01",
            customer_name="라온",
            phone="010-0000-0001",
            address="Seoul",
            product="장",
            status="RECEIVED",
            is_erp_order=True,
            structured_data={"parties": {"customer": {"name": "라온"}}},
        )
        db_session.add(exact)
        db_session.commit()
        exact_id = exact.id

        # 정확일치 이후 더 새로운 부분일치 주문 12건(라온 접두) — newest 캡/슬롯을 점유.
        for i in range(12):
            db_session.add(
                Order(
                    received_date="2026-06-01",
                    customer_name=f"라온하우스{i}",
                    phone="010-0000-0000",
                    address="Seoul",
                    product="장",
                    status="RECEIVED",
                    is_erp_order=True,
                    structured_data={"parties": {"customer": {"name": f"라온하우스{i}"}}},
                )
            )
        db_session.commit()

        hits = search_unified(db_session, "라온")
        ids = {h["order_id"] for h in hits["customer"]}
        assert exact_id in ids


def test_order_id_prefilter_finds_id_even_when_phone_like(app) -> None:
    """순수 숫자 쿼리는 폰 경로에 가로채이기 전에 Order.id 단건을 직접 조회한다(A1)."""
    from db import db_session
    from foms.services.foms_unified_search import _order_id_prefilter
    from models import Order

    with app.app_context():
        order = Order(
            received_date="2026-05-30",
            customer_name="번호직검색 고객",
            phone="010-0000-0000",
            address="Seoul",
            product="장",
            status="RECEIVED",
            is_erp_order=True,
            structured_data={"parties": {"customer": {"name": "번호직검색 고객"}}},
        )
        db_session.add(order)
        db_session.commit()

        by_id = _order_id_prefilter(db_session, str(order.id))
        assert by_id and by_id[0].id == order.id
        with_hash = _order_id_prefilter(db_session, f"#{order.id}")
        assert with_hash and with_hash[0].id == order.id
        assert _order_id_prefilter(db_session, "고객") is None
        assert _order_id_prefilter(db_session, "010-1234") is None


def test_unified_search_finds_order_by_id(app) -> None:
    """주문번호 검색이 통합 검색 결과에 단건으로 잡힌다(A1 end-to-end)."""
    from db import db_session
    from foms.services.foms_unified_search import search_unified
    from models import Order

    with app.app_context():
        order = Order(
            received_date="2026-05-30",
            customer_name="아이디검색 고객",
            phone="010-9999-8888",
            address="Seoul",
            product="장",
            status="RECEIVED",
            is_erp_order=True,
            structured_data={"parties": {"customer": {"name": "아이디검색 고객"}}},
        )
        db_session.add(order)
        db_session.commit()

        hits = search_unified(db_session, str(order.id))
        found = {h["order_id"] for bucket in hits.values() for h in bucket}
        assert order.id in found


def test_unified_search_matches_structured_data_only_fields(app) -> None:
    """레거시 컬럼이 비고 structured_data에만 값이 있는 매치도 분류기가 살린다(A2)."""
    from db import db_session
    from foms.services.foms_unified_search import search_unified
    from models import Order

    with app.app_context():
        order = Order(
            received_date="2026-05-30",
            customer_name="무관한 고객명",
            phone="010-0000-0000",
            address="Legacy column addr",
            product="레거시 제품",
            manager_name=None,
            status="RECEIVED",
            is_erp_order=True,
            structured_data={
                "parties": {
                    "customer": {"name": "무관한 고객명"},
                    "manager": {"name": "홍반장매니저"},
                    "orderer": {"name": "주문자김씨"},
                },
                "site": {"address_full": "경기 구조화주소동"},
                "items": [{"product_name": "구조화전용상품"}],
            },
        )
        db_session.add(order)
        db_session.commit()

        for query in ("홍반장매니저", "주문자김씨", "구조화주소동", "구조화전용상품"):
            hits = search_unified(db_session, query)
            found = {h["order_id"] for bucket in hits.values() for h in bucket}
            assert order.id in found, f"structured-only match dropped for {query}"


def test_unified_search_merges_legacy_when_erp_hit_exists(app) -> None:
    """ERP 히트가 있어도 동일 검색어의 레거시(비-ERP) 주문이 병합된다(A3)."""
    from db import db_session
    from foms.services.foms_unified_search import search_unified
    from models import Order

    with app.app_context():
        erp = Order(
            received_date="2026-05-30",
            customer_name="공통검색명 ERP",
            phone="010-1111-1111",
            address="Seoul",
            product="장",
            status="RECEIVED",
            is_erp_order=True,
            structured_data={"parties": {"customer": {"name": "공통검색명 ERP"}}},
        )
        legacy = Order(
            received_date="2024-01-01",
            customer_name="공통검색명 레거시",
            phone="010-2222-2222",
            address="Seoul",
            product="장",
            status="COMPLETED",
            is_erp_order=False,
        )
        db_session.add(erp)
        db_session.add(legacy)
        db_session.commit()

        hits = search_unified(db_session, "공통검색명")
        ids = {h["order_id"] for h in hits["customer"]}
        assert erp.id in ids
        assert legacy.id in ids


def test_search_fragment_shows_history_fallback_link(client, app) -> None:
    from db import db_session
    from models import User
    from werkzeug.security import generate_password_hash

    with app.app_context():
        user = User(
            username="search_hist_user",
            password=generate_password_hash("admin"),
            role="ADMIN",
            team="CS",
            name="Hist User",
        )
        db_session.add(user)
        db_session.commit()

    client.post(
        "/login",
        data={"username": "search_hist_user", "password": "admin"},
        follow_redirects=True,
    )
    response = client.get("/api/foms/search/fragment?q=missing-customer-xyz&group=all")
    body = response.get_data(as_text=True)
    assert "과거 이력에서 검색" in body
    assert "from_search=1" in body


def test_history_from_search_banner(client, app) -> None:
    from db import db_session
    from models import User
    from werkzeug.security import generate_password_hash

    with app.app_context():
        user = User(
            username="history_from_search_user",
            password=generate_password_hash("admin"),
            role="ADMIN",
            team="CS",
            name="Banner User",
        )
        db_session.add(user)
        db_session.commit()

    client.post(
        "/login",
        data={"username": "history_from_search_user", "password": "admin"},
        follow_redirects=True,
    )
    response = client.get("/erp/history/?q=test&from_search=1")
    body = response.get_data(as_text=True)
    assert "통합 검색에서 운영 큐 결과가 없어" in body
