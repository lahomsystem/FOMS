"""도면 작업실 상세 — 작은 칸은 320px 작은 그림 길, 크게 보기 · 링크는 원본(설계서 2026-11-19-list-drawing-small-image).

조사(G3 · G4 · G6~G12 · N5): 폰 상세는 보이는 칸이 56px 도면 줄뿐인데 숨은 PC 칸 그림까지 원본으로 다 받았다
(로컬 15,951KB). 규칙:

* 작은 칸 ``<img src>`` 만 ``/api/files/thumb/<key>``. 감싸는 칸의 ``data-view-url`` · ``href`` · ``data-handoff-view-url``
  (뷰어 · 링크가 읽는 값)은 원본 ``/api/files/view/<key>``.
* 그림 판정은 정본 ``list_thumb.is_list_thumb_source`` 하나 — 템플릿은 필터 ``list_thumb_url`` 을 쓴다.
  svg · heic · 확장자 없는 옛 key 는 새 길이 404 라 원본 유지, pdf 는 미리보기 없음. 한글 이름 key(점 없이 ``_png``)는 그림.
* 폰에서 숨은 PC 칸 · 닫힌 창 안 그림은 ``loading="lazy"`` — 크롬은 ``display:none`` 아래 lazy 그림을 받지 않는다.
* 전달 · 수정 창 대상 카드(폭 232~345px · 높이 80) · 고객 발송 창 칸(약 330x236)은 320 으로 모자라 원본 유지 + lazy.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from bs4 import BeautifulSoup
from flask import render_template
from werkzeug.security import generate_password_hash

import foms.services.drawing_workbench_as_rows as as_rows
import foms.services.drawing_workbench_display as wb_display
from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.files.list_thumb import list_thumb_url
from foms.web.drawing.workbench import _build_handoff_files
from models import Order, OrderAttachment, User

ROOT = Path(__file__).resolve().parents[2]
THUMB = "/api/files/thumb/"
VIEW = "/api/files/view/"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _user(username: str) -> dict:
    user = User(username=username, password=generate_password_hash("pw"), role="STAFF", team="DRAWING",
                name="도면담당WB", is_active=True)
    db_session.add(user)
    db_session.commit()
    return {"id": user.id, "username": user.username, "role": user.role}


def _login(client, who: dict) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = who["id"]
        sess["username"] = who["username"]
        sess["role"] = who["role"]


def _keys(oid: int) -> dict[str, str]:
    base = f"orders/{oid}/drawing"
    return {
        "png": f"{base}/20261119_101010_ab12cd34_plan.png",
        "korean": f"{base}/20261119_101011_cd34ef56_png",   # secure_filename("도면.png") → "png"
        "svg": f"{base}/20261119_101012_ef56ab78_line.svg",
        "heic": f"{base}/20261119_101013_ab78cd90_site.heic",
        "pdf": f"{base}/20261119_101014_cd90ef12_spec.pdf",
    }


def _seed_order(drafter_id: int) -> tuple[int, dict[str, str]]:
    order = Order(received_date=get_today_kst().strftime("%Y-%m-%d"), customer_name="작은그림 고객",
                  phone="010-0000-0000", address="서울 어딘가", product="붙박이장", status="DRAWING",
                  manager_name="영업담당WB", is_erp_order=True, structured_data={})
    db_session.add(order)
    db_session.commit()
    keys = _keys(order.id)
    files = [
        {"key": keys["png"], "filename": "plan.png"},
        {"key": keys["korean"], "filename": "도면.png"},
        {"key": keys["svg"], "filename": "line.svg"},
        {"key": keys["heic"], "filename": "site.heic"},
        {"key": keys["pdf"], "filename": "spec.pdf"},
    ]
    gateway_ref = f"orders/{order.id}/drawing_gateway/revisions/20261119_101015_ef12ab34_ref.jpg"
    keys["ref"] = gateway_ref
    order.structured_data = {
        "parties": {"customer": {"name": "작은그림 고객"}, "manager": {"name": "영업담당WB"}},
        "workflow": {"stage": "DRAWING"},
        "drawing_status": "RETURNED",
        "assignments": {"drawing_assignee_user_ids": [drafter_id]},
        "drawing_current_files": files,
        "drawing_transfer_history": [
            {"action": "TRANSFER", "by_user_id": drafter_id, "by_user_name": "도면담당WB",
             "at": "2026-11-18 01:00:00", "note": "1차 전달", "files": files},
            {"action": "REQUEST_REVISION", "by_user_name": "영업담당WB", "at": "2026-11-18 02:00:00",
             "note": "손잡이 위치", "target_drawing_keys": [keys["png"], keys["korean"]],
             "target_drawing_numbers": [1, 2],
             "files": [{"key": gateway_ref, "filename": "ref.jpg"}], "files_count": 1},
        ],
    }
    db_session.commit()
    return order.id, keys


def _page(client, monkeypatch, who: dict, oid: int, *, phone: bool, query: dict | None = None) -> BeautifulSoup:
    _login(client, who)
    if phone:
        monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
        monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(who["id"]))
    else:
        monkeypatch.delenv("ERP_MOBILE_V2_ENABLED", raising=False)
    res = client.get(f"/erp/drawing-workbench/{oid}", query_string=query or {})
    assert res.status_code == 200, res.get_data(as_text=True)[:400]
    return BeautifulSoup(res.get_data(as_text=True), "html.parser")


def _gallery_tile(soup: BeautifulSoup, key: str):
    tiles = soup.select(f'.drawing-gateway-thumb[data-key="{key}"]')
    assert tiles, f"갤러리 칸 없음: {key}"
    return tiles


# --------------------------------------------------------------------------- 정본 필터


def test_template_filter_is_canonical_list_thumb_url(app):
    """템플릿이 그림 판정을 흉내 내지 않게 — 필터가 곧 정본 함수다."""
    assert app.jinja_env.filters["list_thumb_url"] is list_thumb_url


# --------------------------------------------------------------------------- PC 상세 (G8 · G9 · G11 · N5)


def test_pc_gallery_and_chips_small_viewer_original(client, monkeypatch):
    drafter = _user("wb_thumb_pc")
    oid, keys = _seed_order(drafter["id"])
    soup = _page(client, monkeypatch, drafter, oid, phone=False)

    for name in ("png", "korean"):
        key = keys[name]
        for tile in _gallery_tile(soup, key):
            assert tile["data-view-url"] == VIEW + key            # 뷰어가 읽는 값 = 원본
            img = tile.select_one("img")
            assert img["src"] == THUMB + key                       # 칸 = 작은 그림
            assert img.get("loading") == "lazy"

    # 새 길이 404 인 svg · heic 는 원본 그대로, pdf 는 미리보기 없음(아이콘).
    for name in ("svg", "heic"):
        for tile in _gallery_tile(soup, keys[name]):
            assert tile.select_one("img")["src"] == VIEW + keys[name]
    assert not soup.select(f'.drawing-gateway-thumb[data-key="{keys["pdf"]}"]')
    markup = str(soup)
    for name in ("svg", "heic", "pdf"):
        assert THUMB + keys[name] not in markup, f"새 길이 404 인 key 를 작은 그림 길로 보냄: {name}"

    # 창구 참고 사진(수정요청 갤러리)도 작은 그림 + 원본 뷰어.
    ref_tiles = _gallery_tile(soup, keys["ref"])
    assert all(t.select_one("img")["src"] == THUMB + keys["ref"] for t in ref_tiles)
    assert all(t["data-view-url"] == VIEW + keys["ref"] for t in ref_tiles)

    # 대상 칩(G9): 칩 그림 = 작은 그림, 버튼 data-view-url = 원본.
    chips = soup.select("button.dw-target-chip")
    assert chips
    chip_keys = set()
    for chip in chips:
        view = chip["data-view-url"]
        assert view.startswith(VIEW)
        key = view[len(VIEW):]
        chip_keys.add(key)
        assert chip.select_one("img")["src"] == THUMB + key
    assert chip_keys == {keys["png"], keys["korean"]}


def test_pc_modal_target_cards_keep_original_but_lazy(client, monkeypatch):
    """전달 · 수정 창 대상 카드(폭 약 340px)는 320 으로 모자라 원본 — 닫힌 창이라 lazy 로 열 때만 받는다."""
    drafter = _user("wb_thumb_modal")
    oid, keys = _seed_order(drafter["id"])
    soup = _page(client, monkeypatch, drafter, oid, phone=False)
    for wrap_id in ("dw-transfer-target-cards", "dw-revision-target-cards"):
        imgs = soup.select(f"#{wrap_id} .drawing-target-preview img")
        assert imgs, wrap_id
        for img in imgs:
            assert img["src"].startswith(VIEW), img
            assert img.get("loading") == "lazy"
    rev_card = soup.select_one(f'#dw-revision-target-cards .drawing-target-card[data-key="{keys["png"]}"]')
    assert rev_card["data-view-url"] == VIEW + keys["png"]       # 무대(previewRevisionTargetCard) = 원본


def test_every_static_img_in_detail_body_is_lazy():
    """숨은 PC 칸 · 닫힌 창 그림이 폰에서 받히지 않게 — 상세 본문의 서버 그림은 모두 lazy(N5 실측 사진 포함)."""
    src = _read("templates/drawing/partials/workbench_detail_body.html")
    html_part = src.split("<script>", 1)[0]
    tags = re.findall(r"<img\b[^>]*>", html_part, flags=re.S)
    assert len(tags) >= 8
    missing = [t for t in tags if 'loading="lazy"' not in t]
    assert not missing, missing
    # 수정 창 무대(JS 가 페이지 뜰 때 미리 채움)도 lazy — 창이 닫혀 있는 동안(폰은 늘) 원본을 받지 않는다.
    js_part = src.split("function previewRevisionTargetCard", 1)[1].split("function previewFirstSelectedRevisionCard", 1)[0]
    assert js_part.index("img.loading = 'lazy'") < js_part.index("img.src = viewUrl")
    # 실측 사진(N5)은 큰 칸이라 크기는 그대로(원본) — lazy 만.
    assert html_part.count('<img src="{{ photo.view_url }}" alt="{{ photo.filename }}" loading="lazy" decoding="async">') == 2


# --------------------------------------------------------------------------- 폰 전달 화면 (G6 · G7)


def test_phone_handoff_rows_small_and_stage_original(client, monkeypatch):
    drafter = _user("wb_thumb_phone")
    oid, keys = _seed_order(drafter["id"])
    soup = _page(client, monkeypatch, drafter, oid, phone=True)
    handoff = soup.select_one(".erp-mobile-shell.foms-drawing-handoff")
    assert handoff is not None

    rows = handoff.select("a.foms-drawing-sheet-row")
    by_key = {}
    for row in rows:
        img = row.select_one(".foms-drawing-sheet-row__thumb img")
        if img is not None:
            by_key[img["src"]] = row
    assert THUMB + keys["png"] in by_key and THUMB + keys["korean"] in by_key
    assert VIEW + keys["svg"] in by_key and VIEW + keys["heic"] in by_key   # 새 길 404 → 원본 유지
    assert len(by_key) == 4                                                  # pdf 는 아이콘

    # 도면 한 장을 고른 화면(줄을 누른 뒤): 큰 그림 무대 + 대화 스레드 참고 사진.
    detail = _page(client, monkeypatch, drafter, oid, phone=True, query={"drawing_key": keys["png"]})
    handoff = detail.select_one(".erp-mobile-shell.foms-drawing-handoff")
    stage = handoff.select_one(".foms-drawing-viewer__canvas")
    assert stage is not None
    stage_img = stage.select_one("img")
    assert stage_img["src"].startswith(VIEW)                                  # 큰 그림 = 원본
    assert stage["data-handoff-view-url"] == stage_img["src"]

    ref = handoff.select_one('[data-drawing-handoff-open="reference"]')
    assert ref is not None
    assert ref["data-handoff-view-url"] == VIEW + keys["ref"]
    assert ref.select_one("img")["src"] == THUMB + keys["ref"]

    # 폰에서 숨은 PC 칸: 래퍼가 d-none 이고 그 안 그림은 모두 lazy(받지 않는다).
    legacy = soup.select_one(".dw-legacy-detail")
    assert "d-none" in legacy["class"]
    hidden_imgs = legacy.select("img")
    assert hidden_imgs and all(i.get("loading") == "lazy" for i in hidden_imgs)


def test_handoff_rows_unit_foreign_key_and_korean_name():
    files = [
        {"key": "orders/7/drawing/a_png", "filename": "도면.png"},
        {"key": "orders/8/drawing/b.png", "filename": "b.png"},           # 남의 주문 key
        {"key": "orders/7/drawing/c.heic", "filename": "c.heic"},
    ]
    from app import app as flask_app
    with flask_app.test_request_context("/"):
        rows = _build_handoff_files(7, files, [], "")
    assert rows[0]["thumb_url"] == THUMB + "orders/7/drawing/a_png"
    assert rows[0]["view_url"] == VIEW + "orders/7/drawing/a_png"
    assert rows[1]["thumb_url"] == "" and rows[1]["view_url"] == ""
    assert rows[2]["thumb_url"] == "" and rows[2]["view_url"] == VIEW + "orders/7/drawing/c.heic"


# --------------------------------------------------------------------------- 고객 발송 창 (G12)


def test_customer_send_modal_tiles_keep_original_lazy(app):
    """발송 창 도면 칸은 height=64 속성이 전역 CSS 에 밀려 실제 약 330x236 으로 그려진다(로컬 실측 2026-11-19) —
    320 으로 모자라 원본 유지. 닫힌 창이라 lazy 로 열 때만 받는다."""
    files = [
        {"key": "orders/3/drawing/a.png", "filename": "a.png"},
        {"key": "orders/3/drawing/c.pdf", "filename": "c.pdf"},
    ]
    order = SimpleNamespace(id=3, structured_updated_at=None)
    with app.test_request_context("/"):
        html = render_template(
            "drawing/partials/workbench_customer_send_modals.html",
            customer_send={"bar": [{"key": "send"}]}, order=order, drawing_files=files, customer_name="고객",
        )
    soup = BeautifulSoup(html, "html.parser")
    imgs = soup.select("#dwCustomerSendModal img.img-thumbnail")
    assert [i["src"] for i in imgs] == [VIEW + "orders/3/drawing/a.png"]
    assert all(i.get("loading") == "lazy" for i in imgs)


# --------------------------------------------------------------------------- 따로 올라온 파일 (G10)


def test_stray_files_small_and_link_original(monkeypatch):
    rows = [
        SimpleNamespace(id=1, storage_key="orders/5/drawing/x.png", thumbnail_key="orders/5/drawing/thumb_x.png",
                        filename="x.png", user_id=None, created_at=None),
        SimpleNamespace(id=2, storage_key="orders/5/drawing/y.pdf", thumbnail_key="", filename="y.pdf",
                        user_id=None, created_at=None),
        SimpleNamespace(id=3, storage_key="orders/5/drawing/z.heic", thumbnail_key="", filename="z.heic",
                        user_id=None, created_at=None),
    ]
    monkeypatch.setattr(wb_display, "stray_drawing_rows", lambda db, oid, sd: rows)
    out = wb_display.build_stray_drawing_files(None, SimpleNamespace(id=5), {}, None)
    assert out[0]["thumb_url"] == THUMB + "orders/5/drawing/x.png"
    assert out[0]["view_url"] == VIEW + "orders/5/drawing/x.png"
    assert out[1]["thumb_url"] == ""                                      # pdf = 아이콘
    assert out[2]["thumb_url"] == ""                                      # heic = 지금처럼 미리보기 없음(새 길 안 씀)


# --------------------------------------------------------------------------- 작업실 AS 카드 (G3 · G4)


def test_as_card_round_files_small_and_link_original():
    out = as_rows._files_view([
        {"key": "orders/9/drawing_wizard/exports/a.png", "name": "AS 1"},
        {"key": "orders/9/drawing_wizard/exports/b_png", "name": "AS 2"},
        {"key": "orders/9/drawing/c.pdf", "name": "AS 3"},
    ])
    assert out[0]["view_url"] == VIEW + "orders/9/drawing_wizard/exports/a.png"
    assert out[0]["thumb_url"] == THUMB + "orders/9/drawing_wizard/exports/a.png"
    assert out[1]["thumb_url"] == THUMB + "orders/9/drawing_wizard/exports/b_png"
    assert out[2]["thumb_url"] == ""
    src = _read("templates/drawing/partials/workbench_as_card.html")
    # 링크(href)는 원본, 칸 그림만 작은 그림(같은 주소를 쓰던 함정 — 조사 G3).
    assert ('<a href="{{ f.view_url }}" target="_blank" rel="noopener"><img loading="lazy" decoding="async" '
            'src="{{ f.thumb_url or f.view_url }}"') in src
    assert 'data-view-url="{{ m.view_url }}"' in src and 'src="{{ m.thumb_url }}"' in src


def test_as_card_media_small_and_viewer_original(monkeypatch):
    order = Order(received_date=get_today_kst().strftime("%Y-%m-%d"), customer_name="AS 고객", phone="010-0000-0001",
                  address="서울", product="붙박이장", status="COMPLETED", is_erp_order=True, structured_data={})
    db_session.add(order)
    db_session.commit()
    oid = order.id
    img_key = f"orders/{oid}/as/20261119_101010_ab12cd34_photo.jpg"
    heic_key = f"orders/{oid}/as/20261119_101011_cd34ef56_photo.heic"
    for key, thumb in ((img_key, f"orders/{oid}/as/thumb_photo.jpg"), (heic_key, None)):
        db_session.add(OrderAttachment(order_id=oid, filename=key.rsplit("/", 1)[-1], file_type="image",
                                       file_size=1, storage_key=key, thumbnail_key=thumb, category="as",
                                       as_log_id="req-1"))
    db_session.commit()
    monkeypatch.setattr(as_rows, "current_round", lambda sd: {"request_log_id": "req-1"})
    monkeypatch.setattr(as_rows, "current_reception_entry", lambda sd: {})
    media = as_rows.build_as_media(db_session, oid, {})
    items = {i["key"]: i for g in media["groups"] for i in g["items"]}
    assert items[img_key]["thumb_url"] == THUMB + img_key               # 옛 thumb_ 보다 작은 그림 길이 먼저
    assert items[img_key]["view_url"] == VIEW + img_key
    assert items[heic_key]["thumb_url"] == VIEW + heic_key              # 새 길 404 → 원본
