"""도면 탭 고객 보내기 — 목록 카드·태블릿 갤러리 "N차" 와 고객 링크 화면 제목(S3, 설계서 2026-09-29 §4.5 C15 · Q3).

서버 값(`round_text` · `latest_request_is_customer` · `share_round_label`)은 S1 이 채운다. 여기서는
직접 채운 값으로 템플릿이 그리는 모양만 고정한다(값이 아직 없는 응답도 "vN" 이 아니라 "N차").
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

import foms.api.share as share_routes

ROOT = Path(__file__).resolve().parents[2]

# ── 목록 카드 · 태블릿 갤러리 'N차' · '고객 요청' 칩 ──────────────────────────


def _render_partial(app, template: str, **ctx) -> BeautifulSoup:
    from flask import render_template

    with app.test_request_context("/"):
        return BeautifulSoup(render_template(template, **ctx), "html.parser")


def _row(**overrides) -> dict:
    row = {"id": 77, "customer_name": "카드 고객", "turn_tone": "mine", "turn_label": "내 차례", "assignee_text": "-",
           "drawing_status": "RETURNED", "drawing_status_label": "수정 요청", "transfer_round": 2, "file_count": 2,
           "unread_count": 0, "construction_days": None, "construction_date": "", "drawing_files": []}
    row.update(overrides)
    return row


def test_queue_card_shows_round_text_and_customer_chip(app):
    soup = _render_partial(app, "drawing/partials/workbench_mobile_queue_card.html",
                           r=_row(round_text="2차", latest_request_is_customer=True), drawing_thumb_enabled=False)
    chips = [c.get_text(" ", strip=True) for c in soup.select(".foms-drawing-queue-card__chip")]
    assert "2차" in chips and "고객 요청" in chips
    assert not any(re.fullmatch(r"v\d+", c) for c in chips)
    customer = soup.select_one(".foms-drawing-queue-card__chip.is-customer")
    assert customer is not None and "is-warn" in customer["class"]


def test_queue_card_without_customer_request_has_no_customer_chip(app):
    soup = _render_partial(app, "drawing/partials/workbench_mobile_queue_card.html",
                           r=_row(round_text="1차", latest_request_is_customer=False), drawing_thumb_enabled=False)
    assert soup.select(".foms-drawing-queue-card__chip.is-customer") == []
    assert "1차" in [c.get_text(strip=True) for c in soup.select(".foms-drawing-queue-card__chip")]


def test_queue_card_before_server_round_text_still_says_n_cha(app):
    """S1 값이 아직 없을 때(round_text 없음)도 'vN' 이 아니라 'N차' 로 읽힌다."""
    soup = _render_partial(app, "drawing/partials/workbench_mobile_queue_card.html",
                           r=_row(), drawing_thumb_enabled=False)
    chips = [c.get_text(strip=True) for c in soup.select(".foms-drawing-queue-card__chip")]
    assert "2차" in chips and "v2" not in chips


def test_tablet_gallery_label_uses_round_text(app):
    soup = _render_partial(app, "drawing/partials/tablet_gallery_body.html", rows=[_row(round_text="3차")],
                           filters={}, stats={}, pagination=None, sort_by="")
    label = soup.select_one(".foms-drawing-gallery-card__thumb-label").get_text(" ", strip=True)
    assert "· 3차 ·" in label and not re.search(r"\bv\d", label)


def test_no_vn_round_notation_left_in_drawing_templates():
    for path in (ROOT / "templates/drawing").rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert "v{{ r.transfer_round" not in text, path


# ── 고객 링크 화면 제목(Q3) ────────────────────────────────────────────────────


@pytest.fixture
def share_r2(monkeypatch):
    from tests.domains.test_order_share_view import FakeR2Storage

    stub = FakeR2Storage()
    monkeypatch.setattr(share_routes, "get_storage", lambda: stub)
    return stub


def _inject_share_label(monkeypatch, label: str) -> None:
    real = share_routes.render_template

    def fake(template_name, **ctx):
        if template_name in ("orders/share_view.html", "orders/share_bundle_view.html"):
            ctx["share_round_label"] = label
        return real(template_name, **ctx)

    monkeypatch.setattr(share_routes, "render_template", fake)


def _titles(body: str) -> tuple[str, str]:
    soup = BeautifulSoup(body, "html.parser")
    return soup.title.get_text(strip=True), soup.select_one(".foms-share-view__title").get_text(strip=True)


def test_share_view_title_shows_round_from_second(app, client, share_r2, monkeypatch):
    from tests.domains.test_order_share_view import _add_drawing_attachment, _mk_order, _mk_share

    order = _mk_order()
    _add_drawing_attachment(order, "plan-r2.png")
    _, token = _mk_share(order)
    assert _titles(client.get(f"/s/{token}").get_data(as_text=True)) == ("도면 확인", "도면 확인")
    _inject_share_label(monkeypatch, "2차")
    assert _titles(client.get(f"/s/{token}").get_data(as_text=True)) == ("2차 도면 확인", "2차 도면 확인")


def test_share_bundle_title_shows_round_from_second(app, client, share_r2, monkeypatch):
    import copy

    from tests.domains.test_order_share_view import _EST_SD, _add_drawing_attachment, _mk_bundle_share, _mk_order

    order = _mk_order(structured_data=copy.deepcopy(_EST_SD))
    _add_drawing_attachment(order, "plan-b2.png")
    _, token = _mk_bundle_share(order)
    assert _titles(client.get(f"/s/{token}").get_data(as_text=True)) == ("도면·계약서 확인", "도면·계약서 확인")
    _inject_share_label(monkeypatch, "2차")
    assert _titles(client.get(f"/s/{token}").get_data(as_text=True)) == (
        "2차 도면·계약서 확인", "2차 도면·계약서 확인")
