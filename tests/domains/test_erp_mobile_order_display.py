"""ERP mobile v2 display helpers — attachment URL strategy."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from foms.services import erp_mobile_order_display as display

ROOT = Path(__file__).resolve().parents[2]


def test_batch_resolve_queue_attachment_preview_items_splits_thumb_and_view() -> None:
    att = SimpleNamespace(
        order_id=42,
        filename="photo.jpg",
        file_type="image",
        category="measurement",
        storage_key="orders/1/photo.jpg",
        thumbnail_key="orders/1/thumb_photo.jpg",
        created_at=None,
    )
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        att
    ]

    with patch.object(display, "build_file_view_url", side_effect=lambda k: f"/view/{k}"):
        with patch.object(display, "build_file_download_url", return_value="/dl/photo.jpg"):
            items_by_order = display.batch_resolve_queue_attachment_preview_items(mock_db, [42])

    items = items_by_order[42]
    assert len(items) == 1
    assert items[0]["thumb"] == "/view/orders/1/thumb_photo.jpg"
    assert items[0]["view"] == "/view/orders/1/photo.jpg"
    assert items[0]["download"] == "/dl/photo.jpg"
    assert items[0]["label"] == "photo.jpg"

    with patch.object(display, "build_file_view_url", side_effect=lambda k: f"/view/{k}"):
        urls = display.batch_resolve_queue_attachment_urls(mock_db, [42])
    assert urls[42] == ["/view/orders/1/photo.jpg"]


def test_batch_resolve_queue_attachment_preview_items_drawing_categories_only() -> None:
    """categories=drawing 이면 measurement 첨부 제외."""
    draw = SimpleNamespace(
        order_id=7,
        filename="draw.png",
        file_type="image",
        category="drawing",
        storage_key="orders/7/draw.png",
        thumbnail_key="orders/7/thumb_draw.png",
        created_at=None,
    )
    measure = SimpleNamespace(
        order_id=7,
        filename="photo.jpg",
        file_type="image",
        category="measurement",
        storage_key="orders/7/photo.jpg",
        thumbnail_key="orders/7/thumb_photo.jpg",
        created_at=None,
    )
    mock_db = MagicMock()
    filtered = mock_db.query.return_value.filter.return_value
    filtered.filter.return_value.order_by.return_value.all.return_value = [draw, measure]
    filtered.order_by.return_value.all.return_value = [draw, measure]

    with patch.object(display, "build_file_view_url", side_effect=lambda k: f"/view/{k}"):
        with patch.object(display, "build_file_download_url", return_value="/dl/x"):
            items_by_order = display.batch_resolve_queue_attachment_preview_items(
                mock_db, [7], categories=display._QUEUE_DRAWING_CATEGORIES
            )

    items = items_by_order[7]
    assert len(items) == 1
    assert items[0]["label"] == "draw.png"
    assert items[0]["view"] == "/view/orders/7/draw.png"


def test_attachment_urls_split_thumb_and_full_view() -> None:
    att = SimpleNamespace(
        storage_key="orders/1/photo.jpg",
        thumbnail_key="orders/1/thumb_photo.jpg",
        file_type="image",
        filename="photo.jpg",
    )
    with patch.object(display, "build_file_view_url", side_effect=lambda k: f"/view/{k}"):
        assert display._attachment_thumbnail_url(att) == "/view/orders/1/thumb_photo.jpg"
        assert display._attachment_full_view_url(att) == "/view/orders/1/photo.jpg"
        assert display._attachment_image_url(att) == "/view/orders/1/thumb_photo.jpg"


def test_mobile_attachment_items_splits_thumb_and_full_view() -> None:
    att = SimpleNamespace(
        id=7,
        order_id=1,
        filename="photo.jpg",
        file_type="image",
        category="measurement",
        storage_key="orders/1/photo.jpg",
        thumbnail_key="orders/1/thumb_photo.jpg",
        created_at=None,
    )
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        att
    ]

    with patch.object(display, "build_file_view_url", side_effect=lambda k: f"/view/{k}"):
        with patch.object(display, "build_file_download_url", return_value="/dl/photo.jpg"):
            items = display.mobile_attachment_items(mock_db, 1, limit=8)

    assert len(items) == 1
    assert items[0]["thumb_url"] == "/view/orders/1/thumb_photo.jpg"
    assert items[0]["view_url"] == "/view/orders/1/photo.jpg"
    assert items[0]["thumb_url"] != items[0]["view_url"]
    assert items[0]["item_index"] is None


def test_mobile_product_items_collapse_all_when_multiple() -> None:
    sd = {
        "items": [
            {"product_name": "A", "price": 1000},
            {"product_name": "B", "price": 2000},
        ]
    }
    rows = display.mobile_product_items(sd)
    assert len(rows) == 2
    assert all(row["collapsed_default"] is True for row in rows)


def test_mobile_product_items_single_item_expanded_by_default() -> None:
    sd = {"items": [{"product_name": "A", "price": 1000}]}
    rows = display.mobile_product_items(sd)
    assert len(rows) == 1
    assert rows[0]["collapsed_default"] is False


def test_mobile_product_items_groups_attachments_by_item_index() -> None:
    sd = {
        "items": [
            {"product_name": "A"},
            {"product_name": "B"},
        ]
    }
    attachments = [
        {"id": 1, "item_index": 0, "label": "a0"},
        {"id": 2, "item_index": 1, "label": "b1"},
        {"id": 3, "item_index": None, "label": "common"},
    ]
    rows = display.mobile_product_items(sd, attachments)
    assert [a["label"] for a in rows[0]["attachments"]] == ["a0"]
    assert [a["label"] for a in rows[1]["attachments"]] == ["b1"]
    _, common = display._group_attachments_by_item_index(attachments, item_count=2)
    assert [a["label"] for a in common] == ["common"]


def test_mobile_product_items_merges_common_attachments_for_single_item() -> None:
    sd = {"items": [{"product_name": "Only"}]}
    attachments = [
        {"id": 1, "item_index": None, "label": "common", "category": "measurement"},
        {"id": 2, "item_index": 0, "label": "linked", "category": "drawing"},
    ]
    rows = display.mobile_product_items(sd, attachments)
    assert sorted(a["label"] for a in rows[0]["attachments"]) == ["common", "linked"]
    _, common = display._group_attachments_by_item_index(attachments, item_count=1)
    assert common == []


def test_mobile_attachment_categories_omit_empty_tabs() -> None:
    attachments = [
        {"id": 1, "category": "measurement", "label": "m1"},
        {"id": 2, "category": "measurement", "label": "m2"},
        {"id": 3, "category": "drawing", "label": "d1"},
    ]
    categories = display.mobile_attachment_categories(attachments)
    assert [c["key"] for c in categories] == ["measurement", "drawing"]
    assert len(categories[0]["items"]) == 2
    assert "construction" not in [c["key"] for c in categories]
    assert "as" not in [c["key"] for c in categories]


def test_mobile_product_items_exposes_attachment_categories() -> None:
    sd = {"items": [{"product_name": "A"}]}
    attachments = [
        {"id": 1, "item_index": 0, "category": "measurement", "label": "m"},
        {"id": 2, "item_index": 0, "category": "as", "label": "a"},
    ]
    rows = display.mobile_product_items(sd, attachments)
    assert [c["key"] for c in rows[0]["attachment_categories"]] == ["measurement", "as"]


def test_mobile_detail_partial_per_item_attachments_and_common_section() -> None:
    partial = (
        ROOT / "templates" / "orders" / "partials" / "order_detail_mobile_v2.html"
    ).read_text(encoding="utf-8")
    assert "item.attachment_categories" in partial
    assert "foms-mobile-attach-panel--collapsed" in partial
    assert "data-foms-mobile-attach-tab" in partial
    assert "order.common_attachment_categories" in partial
    assert "공통 첨부" in partial
    assert "data-foms-product-item" in partial
    assert "data-foms-product-toggle" in partial


def test_mobile_detail_attach_js_binds_category_tabs() -> None:
    js = (ROOT / "static/js/foms/mobile-detail-attachments.js").read_text(encoding="utf-8")
    assert "data-foms-mobile-attach-panel" in js
    assert "data-foms-mobile-attach-tab" in js
    assert "foms-mobile-attach-panel--collapsed" in js


def test_mobile_detail_products_js_binds_v2_selectors() -> None:
    js = (ROOT / "static/js/foms/mobile-detail-products.js").read_text(encoding="utf-8")
    assert "data-foms-product-item" in js
    assert "data-foms-product-toggle" in js
    assert "data-foms-mobile-product" in js


def test_mobile_detail_partial_prefers_view_url_for_grid_img() -> None:
    partial = (
        ROOT / "templates" / "orders" / "partials" / "order_detail_mobile_v2.html"
    ).read_text(encoding="utf-8")
    assert 'src="{{ att.view_url or att.thumb_url }}"' in partial
    assert 'data-foms-attachment-view-url="{{ att.view_url or att.thumb_url }}"' in partial


def test_erp_mobile_tile_prefers_view_url_for_grid_src() -> None:
    shared_js = (ROOT / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    assert "const gridImageSrc =" in shared_js
    assert "isMobileLayout" in shared_js
    assert "(a.view_url || a.thumbnail_view_url || '')" in shared_js


def test_resolve_manager_phone_for_queue_prefers_measurement_settings(monkeypatch) -> None:
    monkeypatch.setattr(
        display,
        "resolve_manager_phone_from_measurement_settings",
        lambda name: "010-9999-8888" if name == "안중훈" else "",
    )
    parties = {"manager": {"name": "안중훈", "phone": "01011112222"}}
    assert display.resolve_manager_phone_for_queue(parties) == "010-9999-8888"


def test_resolve_manager_phone_for_queue_falls_back_to_structured_phone(monkeypatch) -> None:
    monkeypatch.setattr(
        display,
        "resolve_manager_phone_from_measurement_settings",
        lambda _name: "",
    )
    parties = {"manager": {"name": "Bob", "phone": "01033334444"}}
    assert display.resolve_manager_phone_for_queue(parties) == "01033334444"


def test_build_mobile_queue_order_row_includes_manager_phone(monkeypatch) -> None:
    order = SimpleNamespace(
        id=3994,
        structured_data={
            "parties": {"manager": {"name": "안중훈"}, "customer": {"name": "정성민", "phone": "01032267222"}},
            "site": {"address_full": "광명 광오로 14-1"},
            "schedule": {"measurement": {"date": "2026-06-12"}},
        },
        received_date=None,
    )
    monkeypatch.setattr(display, "_attachment_count", lambda _db, _oid: 0)
    monkeypatch.setattr(display, "batch_resolve_queue_attachment_urls", lambda _db, _ids: {})
    monkeypatch.setattr(display, "resolve_manager_phone_for_queue", lambda _p, **kw: "01055556666")
    row = display.build_mobile_queue_order_row(MagicMock(), order)
    assert row["manager_name"] == "안중훈"
    assert row["manager_phone"] == "01055556666"


def test_mobile_amount_summary_applies_discount_to_balance() -> None:
    sd = {
        "items": [{"price": 500000}],
        "payment": {"deposit": 100000, "discount": 50000},
        "totals": {"items_total": 500000, "deposit_amount": 100000, "discount_amount": 50000, "final_amount": 350000},
    }
    summary = display.mobile_amount_summary(sd)
    assert summary["deposit_label"] == "100,000원"
    # 출고가 재정의(568c9a90): 할인은 출고가에 흡수 → 별도 할인 라벨 숨김(None). 잔금은 불변.
    assert summary["discount_label"] is None
    assert summary["balance_label"] == "350,000원"


def test_mobile_amount_summary_clamps_balance_when_only_deposit_present() -> None:
    """품목금액 0 · 예약금만 있는 주문의 모바일 잔금 라벨은 0원이다(음수 금지).

    네이버 승격 주문은 실결제 총액을 예약금에만 담고 항목금액은 비운다 → 출고가 0.
    저장 totals 나 legacy 값이 음수여도 읽기 표면은 서버 파생식
    (structured_form_projection.recompute_totals 의 max(0, ...))과 같게 0에서 자른다.
    """
    sd = {
        "items": [{"price": 0}],
        "payment": {"deposit": 1229000},
        "totals": {"items_total": 0, "final_amount": -1229000},
    }
    summary = display.mobile_amount_summary(sd)
    assert summary["items_total_label"] == "0원"
    assert summary["deposit_label"] == "1,229,000원"
    assert summary["balance_label"] == "0원"


def test_mobile_amount_summary_clamps_legacy_negative_balance() -> None:
    """totals 가 없고 legacy pricing.balance 만 음수로 남은 건도 0원으로 자른다."""
    sd = {
        "payment": {"deposit": 1229000},
        "pricing": {"balance": -1229000},
    }
    summary = display.mobile_amount_summary(sd)
    assert summary["balance_label"] == "0원"


def test_mobile_amount_summary_clamps_legacy_negative_balance_string() -> None:
    """legacy 잔금이 **문자열** 음수("-1,229,000")로 남아도 화면엔 음수가 안 뜬다(T2, CEO L-2).

    ``float()`` 는 콤마를 못 읽어 예전엔 파싱이 실패하는 즉시 ``str(value)`` 원문이
    부호까지 그대로 나갔다 — 숫자 버전(위 테스트)은 클램프를 타는데 문자열 버전만
    클램프를 통째로 빠져나가는 구멍이었다.
    """
    sd = {
        "payment": {"deposit": 1229000},
        "pricing": {"balance": "-1,229,000"},
    }
    summary = display.mobile_amount_summary(sd)
    assert summary["balance_label"] == "0원"


def test_mobile_amount_summary_reads_comma_won_legacy_balance_without_losing_value() -> None:
    """콤마·"원" 이 붙은 legacy 잔금 문자열은 숫자로 읽혀 값을 잃지 않는다(T2).

    수정 전에는 ``float()`` 파싱 실패로 원문이 그대로 나가 이 케이스는 우연히
    값이 맞았다 — 하지만 그건 "파싱을 못 해서 운 좋게 안 틀린 것"이라 같은 경로의
    음수 문자열(위 테스트)은 뚫렸다. 여기서는 실제로 숫자로 파싱해 같은 포맷·같은
    클램프를 통과시킨다는 것을 확인한다(재파싱 후에도 값 손실이 없어야 한다).
    """
    sd = {
        "payment": {"deposit": 100000},
        "pricing": {"balance": "1,229,000원"},
    }
    summary = display.mobile_amount_summary(sd)
    assert summary["balance_label"] == "1,229,000원"


def test_mobile_amount_summary_preserves_unparseable_legacy_balance_text() -> None:
    """끝내 숫자로 못 읽는 legacy 잔금("미정")은 0원을 지어내지 않고 원문을 그대로 낸다(T2).

    0원이라고 말하면 "잔금이 없다"는 거짓 정보가 화면에 뜬다 — 모르는 값은 모른다고
    보여주는 게 맞다. 다만 이 함수의 존재 이유는 "음수가 그대로 찍히지 않는다"이므로,
    그 전제가 깨지지 않는지도 같이 확인한다(이 값엔 부호가 없어 원문 그대로 나간다).
    """
    sd = {
        "payment": {"deposit": 1229000},
        "pricing": {"balance": "미정"},
    }
    summary = display.mobile_amount_summary(sd)
    assert summary["balance_label"] == "미정"


def test_mobile_overpayment_is_named_not_swallowed_by_the_clamp() -> None:
    """**과입금이 화면에 남는다** (2026-08-26 CEO L-1).

    잔금은 어느 표면에서나 ``max(0, …)`` 이라, 예약금이 출고가를 넘으면 화면은
    "잔금 0원"이라고만 말하고 넘친 금액은 어디에도 안 나온다 — 돌려줄 돈이 있다는
    사실이 화면에서 사라진다. 넘친 만큼을 따로 낸다.
    """
    sd = {
        "items": [{"price": 500000}],
        "payment": {"deposit": 600000},
        "totals": {"items_total": 500000, "deposit_amount": 600000, "final_amount": -100000},
    }
    summary = display.mobile_amount_summary(sd)
    assert summary["balance_label"] == "0원", "잔금 클램프 규칙은 그대로다"
    assert summary["overpaid_label"] == "100,000원", "넘친 금액이 화면에서 사라졌다"


def test_measure_pending_order_is_not_called_overpaid() -> None:
    """**실측 전 주문은 과입금이 아니다** — 총액이 아직 안 정해진 것이다.

    네이버 승격분은 실결제 총액을 예약금에만 담고 항목금액은 비운다(출고가 0). 그 상태를
    과입금이라 부르면 승격된 주문이 **전부** 과입금으로 보인다.
    """
    sd = {
        "items": [{"price": 0}],
        "payment": {"deposit": 1229000},
        "totals": {"items_total": 0, "final_amount": -1229000},
    }
    summary = display.mobile_amount_summary(sd)
    assert summary["balance_label"] == "0원"
    assert summary["overpaid_label"] is None, "총액 미확정을 과입금이라 불렀다"


def test_exactly_paid_order_says_nothing_about_overpayment() -> None:
    """딱 맞게 낸 주문에는 과입금 줄이 없다 — 0원 표기는 없는 사실을 그리는 것이다."""
    sd = {
        "items": [{"price": 500000}],
        "payment": {"deposit": 500000},
        "totals": {"items_total": 500000, "final_amount": 0},
    }
    assert display.mobile_amount_summary(sd)["overpaid_label"] is None


def test_mobile_detail_renders_the_overpaid_row() -> None:
    """모바일 상세 금액 블록이 과입금 라벨을 실제로 그린다(있을 때만)."""
    partial = (
        ROOT / "templates" / "orders" / "partials" / "order_detail_mobile_v2.html"
    ).read_text(encoding="utf-8")
    assert "amount.overpaid_label" in partial
    assert "'과입금'" in partial


def test_mobile_detail_quest_section_has_deep_link_anchor() -> None:
    """카드의 '퀘스트 승인' deep-link 대상 앵커가 상세 퀘스트 섹션에 존재한다."""
    partial = (
        ROOT / "templates" / "orders" / "partials" / "order_detail_mobile_v2.html"
    ).read_text(encoding="utf-8")
    assert 'id="foms-detail-quest"' in partial
    assert "erp-mobile-quest-approve-team" in partial


def test_mobile_detail_assignee_approve_button_rendered_once() -> None:
    """담당자 승인 CTA는 하단 고정바 1곳만 — 섹션 중복 렌더는 화면에 버튼 2개로 보인다."""
    partial = (
        ROOT / "templates" / "orders" / "partials" / "order_detail_mobile_v2.html"
    ).read_text(encoding="utf-8")
    # 섹션 버튼은 고정바가 같은 버튼을 그리는 조건(sticky_quest_approve)일 때 렌더되지 않는다.
    assert "{% set sticky_quest_approve" in partial
    assert "{% elif sticky_quest_approve %}" in partial
    # 고정바도 같은 플래그를 쓴다 — 조건이 갈라지면 다시 중복/누락이 생긴다.
    assert "{% if sticky_quest_approve %}" in partial
    section = partial.split('id="mobile-quest-approvals-', 1)[1].split("</section>", 1)[0]
    assert section.count("erp-mobile-quest-approve-assignee") == 1
    assert section.index("{% elif sticky_quest_approve %}") < section.index(
        "erp-mobile-quest-approve-assignee"
    )


def test_mobile_detail_sticky_cta_is_single_row_and_reserves_space() -> None:
    """고정 CTA는 한 줄(flex) + 본문 하단 여백에 CTA 높이 포함(주문 진행 카드 가림 방지)."""
    css = (
        ROOT / "static" / "css" / "components" / "foms-detail-hero.css"
    ).read_text(encoding="utf-8")
    sticky = css.split(".foms-detail-sticky-cta {", 1)[1].split("}", 1)[0]
    assert "display: flex;" in sticky
    assert "display: grid;" not in sticky
    assert "--foms-detail-cta-h" in css
    assert "var(--foms-detail-cta-h, 78px)" in css


def test_mobile_queue_row_separates_orderer_and_buyer() -> None:
    """ORDERER-AXIS-01: 발주사(orderer)와 주문한 사람(buyer)이 각자 자리로 나온다."""
    order = SimpleNamespace(
        id=1, structured_data={
            "parties": {"orderer": {"name": "라홈"},
                        "buyer": {"name": "김주문", "phone": "010-6279-1403"}},
        },
        customer_name="이수취", phone="010-3333-4444", address="서울 강남구 1",
        status="RECEIVED", received_date="2026-08-20", manager_name="담당",
        is_erp_order=True, deleted_at=None,
    )
    with patch.object(display, "_erp_has_media", return_value=False), \
         patch.object(display, "_attachment_count", return_value=0):
        row = display.build_mobile_queue_order_row(MagicMock(), order)

    assert row["orderer_name"] == "라홈"
    assert row["buyer_name"] == "김주문"
    assert row["buyer_phone"] == "010-6279-1403"


def test_detail_templates_render_buyer_row_only_when_present() -> None:
    """주문자 행은 값이 있을 때만 나온다 — 기존 주문 상세는 그대로다."""
    root = Path(__file__).resolve().parents[2]
    for rel, guard in (
        ("templates/drawing/partials/workbench_detail_body.html", "sd_buyer"),
        ("templates/measurement/partials/dashboard_main.html", "rsd_buyer"),
    ):
        source = (root / rel).read_text(encoding="utf-8")
        assert "주문자:" in source, rel
        assert f"{{%- if {guard}.get('name') or {guard}.get('phone') %}}" in source, rel
