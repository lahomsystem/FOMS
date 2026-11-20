"""목록 화면 작은 그림 주소 계약 — SPEC docs/specs/2026-11-19-list-drawing-small-image_SPEC.md §3-3.

화면마다 **작은 칸 = 320px 작은 그림 길**(``/api/files/thumb/<원본 key>``, key 에서 계산 — 조회 없음),
**눌러 크게 보기 · 큰 무대 = 원본**(``/api/files/view/<원본 key>``)인지 본다. 저장 URL 은 믿지 않는다(늘 key 에서).
도면 전달이 커밋 뒤 새 key 마다 작은 그림 만들기를 예약하는지, 예약이 실패해도 전달이 깨지지 않는지도 본다.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from werkzeug.security import generate_password_hash

import foms.api.drawing.erp_orders_drawing as transfer_api
from db import db_session
from foms.services import construction_dashboard_display as cons
from foms.services import erp_mobile_order_display as mob
from foms.services.partners.drawing_list_thumbs import saved_drawing_thumbs
from foms.services.production_sheet_view import _prod_sheet_drawing_files, _prod_sheet_drawing_thumb
from models import Order, User

ROOT = Path(__file__).resolve().parents[2]
_KEY = "orders/41/drawing_wizard/exports/sheet-1.png"
_THUMB = f"/api/files/thumb/{_KEY}"
_VIEW = f"/api/files/view/{_KEY}"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _att(**kw):
    base = {"storage_key": _KEY, "thumbnail_key": None, "file_type": "image", "filename": "sheet-1.png",
            "category": "drawing", "id": 1, "item_index": None}
    base.update(kw)
    return SimpleNamespace(**base)


# ----------------------------------------------------------------------- 시공 폰 카드 · 태블릿 무대
def test_construction_card_thumb_is_small_and_view_is_original():
    item = cons._preview_item_from_file_entry({"key": _KEY, "filename": "sheet-1.png",
                                               "view_url": "https://elsewhere.invalid/x.png"})
    assert item == {"thumb": _THUMB, "view": _VIEW, "label": "sheet-1.png"}  # 저장 URL 불신
    assert cons._preview_item_from_file_entry({"key": "orders/41/drawing/plan.pdf", "filename": "plan.pdf"}) is None
    from_row = cons._preview_item_from_attachment(_att())
    assert from_row["thumb"] == _THUMB and from_row["view"] == _VIEW
    legacy = cons._preview_item_from_attachment(_att(thumbnail_key="orders/41/drawing_wizard/exports/thumb_s.png"))
    assert legacy["thumb"] == _THUMB  # 옛 300px 썸네일이 있어도 작은 그림 길 우선(no-store 302 는 캐시가 안 된다)


def test_tablet_workmode_stage_uses_original_view():
    body = _read("templates/construction/partials/tablet_workmode_body.html")
    stage = body[body.index("data-cwork-stage-img"):body.index("</div>", body.index("data-cwork-stage-img"))]
    assert 'src="{{ _items[0].view }}"' in stage and "_items[0].thumb" not in stage
    js = _read("static/js/foms/tablet-construction-workmode.js")
    swap = js[js.index('var stage = panel.querySelector("[data-cwork-stage-img]");'):]
    swap = swap[:swap.index('stage.setAttribute("data-cwork-active-idx"')]
    assert swap.index('"data-foms-erp-attachment-view-url"') < swap.index('getAttribute("src")')  # 무대 = 원본 먼저
    pin = re.search(r"js/foms/tablet-construction-workmode\.js'\) \}\}\?v=(\d{8}[a-z])",
                    _read("templates/construction/partials/dashboard_body.html"))
    assert pin and pin.group(1) >= "20261119a"


def test_queue_card_viewer_opens_view_not_thumb():
    card = _read("templates/partials/shared/erp_mobile_queue_card_v2.html")
    assert 'src="{{ item.thumb }}"' in card
    assert 'data-foms-erp-attachment-view-url="{{ item.view }}"' in card


# ----------------------------------------------------------------------- 출고 · 생산 목록 · 주문 대시보드 큐 카드
def test_queue_preview_item_uses_small_route_without_thumbnail_key():
    item = mob._queue_preview_item_from_attachment(_att())
    assert item["thumb"] == _THUMB and item["view"] == _VIEW
    assert item["download"] == f"/api/files/download/{_KEY}"
    legacy = mob._queue_preview_item_from_attachment(_att(thumbnail_key="orders/41/x/thumb_a.png"))
    assert legacy["thumb"] == _THUMB  # 옛 300px 썸네일이 있어도 작은 그림 길 우선(no-store 302 는 캐시가 안 된다)
    pdf = _att(storage_key="orders/41/drawing/plan.pdf", file_type="file", filename="plan.pdf")
    assert mob._queue_preview_item_from_attachment(pdf) is None
    heic = _att(storage_key="orders/41/attachments/p.heic", filename="p.heic")
    assert mob._queue_preview_item_from_attachment(heic)["thumb"] == "/api/files/view/orders/41/attachments/p.heic"


def test_orders_tablet_sheet_strip_uses_thumb():
    assert 'src="{{ it.thumb }}"' in _read("templates/orders/partials/tablet_dashboard_sheet.html")


# ----------------------------------------------------------------------- 주문 상세 폰 첨부 칸
def test_order_detail_tile_is_small_and_viewer_original():
    plain = mob._mobile_attachment_item_dict(_att())
    assert plain["tile_url"] == _THUMB and plain["view_url"] == _VIEW and plain["thumb_url"] is None
    legacy = mob._mobile_attachment_item_dict(_att(thumbnail_key="orders/41/x/thumb_a.png"))
    # 옛 300px 썸네일이 있어도 칸은 새 작은 그림 길(투명 PNG 검정 · 누운 사진 회피) — thumb_url 은 그대로 둔다.
    assert legacy["tile_url"] == _THUMB and legacy["thumb_url"] == "/api/files/view/orders/41/x/thumb_a.png"
    video = mob._mobile_attachment_item_dict(_att(storage_key="orders/41/attachments/v.mp4", file_type="video",
                                                  filename="v.mp4"))
    assert video["tile_url"] is None and video["view_url"] is None
    partial = _read("templates/orders/partials/order_detail_mobile_v2.html")
    assert 'src="{{ att.tile_url or att.view_url or att.thumb_url }}"' in partial
    assert 'data-foms-attachment-view-url="{{ att.view_url or att.thumb_url }}"' in partial


# ----------------------------------------------------------------------- 생산 태블릿 시트 · 생산 시트 페이지
def test_production_sheet_strip_small_and_main_original():
    files = _prod_sheet_drawing_files({"drawing_current_files": [
        {"key": _KEY, "filename": "sheet-1.png", "view_url": "https://elsewhere.invalid/x.png"},
        {"key": "orders/41/drawing/plan.pdf", "filename": "plan.pdf"},
    ]})
    assert files[0]["kind"] == "image" and files[0]["thumb"] == _THUMB and files[0]["view"] == _VIEW
    assert files[1]["kind"] == "file" and files[1]["thumb"] == files[1]["view"]
    first = _prod_sheet_drawing_thumb({"drawing_current_files": [{"key": _KEY, "filename": "sheet-1.png"}]})
    assert first["thumb"] == _THUMB and first["view"] == _VIEW
    strip = _read("templates/production/partials/tablet_sheet.html")
    assert 'src="{{ f.thumb or f.view }}"' in strip and 'data-foms-erp-attachment-view-url="{{ f.view }}"' in strip
    page = _read("templates/production/sheet.html")
    assert 'data-foms-sheet-dwg-main src="{{ _imgs[0].view }}"' in page  # 큰 그림 = 원본
    assert '<img src="{{ f.thumb or f.view }}"' in page  # 작은 줄
    js = _read("static/js/production/foms-production-sheet-page.js")
    assert "mainImg.src = t.getAttribute('data-foms-erp-attachment-view-url')" in js  # 넘기기도 원본


# ----------------------------------------------------------------------- 도면 작업실 폰 카드 · 태블릿 갤러리
def test_drawing_workbench_card_small_and_gallery_mid():
    card = _read("templates/drawing/partials/workbench_mobile_queue_card.html")
    assert '<img src="{{ r.thumbnail_url }}"' in card  # 76px 칸 = 작은 그림(pick_row_thumbnail_url)
    gallery = _read("templates/drawing/partials/tablet_gallery_body.html")
    # 갤러리 칸 = 640 중간 크기 그림(SPEC 2026-11-20-mid-size-image), 그림이 아니면 원본. 실제 렌더는 test_mid_thumb_screens.py.
    assert ('src="{{ (r.drawing_files[0].mid_url or r.drawing_files[0].view_url) if r.drawing_files '
            'else r.thumbnail_url }}"') in gallery


# ----------------------------------------------------------------------- 협력사 포털 목록
def test_partner_list_thumbs_small_and_lightbox_original():
    thumbs, more = saved_drawing_thumbs(41, {"pending": {"s1": {"key": _KEY, "sheet_name": "몰딩"}},
                                             "files": [{"key": "orders/41/drawing/plan.pdf", "filename": "x.png"}]})
    assert more == 0
    assert thumbs[0] == {"url": _VIEW, "thumb": _THUMB, "label": "몰딩"}
    assert thumbs[1]["thumb"] == thumbs[1]["url"] == "/api/files/view/orders/41/drawing/plan.pdf"
    tile = _read("templates/partner/partials/drawing_thumbs.html")
    assert 'data-foms-lightbox-src="{{ t.url }}"' in tile and 'src="{{ t.thumb or t.url }}"' in tile
    row = _read("templates/partner/partials/order_rows.html")
    assert 'src="{{ o.drawing_thumbs[0].thumb or o.drawing_thumbs[0].url }}"' in row


# ----------------------------------------------------------------------- 도면 전달 뒤 예약
def _user(name, role, team):
    u = User(username=name, password=generate_password_hash("pw"), role=role, team=team, name=name, is_active=True)
    db_session.add(u)
    db_session.commit()
    return {"id": u.id, "username": u.username, "role": u.role}


def _drawing_order(sales, drafter):
    sd = {"parties": {"customer": {"name": "작은그림고객"}, "manager": {"name": "lts"}},
          "workflow": {"stage": "DRAWING"}, "drawing_status": "PENDING",
          "assignments": {"sales_assignee_user_ids": [sales["id"]], "drawing_assignee_user_ids": [drafter["id"]]}}
    o = Order(received_date=date.today().strftime("%Y-%m-%d"), customer_name="작은그림고객", phone="010-7",
              address="가짜시", product="붙박이장", status="DRAWING", manager_name="lts", is_erp_order=True,
              erp_stage_code="DRAWING", structured_data=sd)
    db_session.add(o)
    db_session.commit()
    return o.id


def _login(client, who):
    with client.session_transaction() as s:
        s["user_id"], s["username"], s["role"] = who["id"], who["username"], who["role"]


@pytest.mark.parametrize("broken", [False, True])
def test_transfer_schedules_new_keys_after_commit(client, monkeypatch, broken):
    calls = []

    def _schedule(keys):
        calls.append(list(keys))
        if broken:
            raise ConnectionError("queue down")
        return len(keys)

    monkeypatch.setattr(transfer_api, "schedule_list_thumbs", _schedule)
    sales, drafter = _user(f"lts{int(broken)}", "STAFF", "SALES"), _user(f"ltd{int(broken)}", "STAFF", "DRAWING")
    oid = _drawing_order(sales, drafter)
    _login(client, drafter)
    keys = [f"orders/{oid}/drawing/a.png", f"orders/{oid}/drawing/b.pdf"]
    res = client.post(f"/api/orders/{oid}/transfer-drawing", json={"files": [{"key": k} for k in keys]})
    assert res.status_code == 200, res.get_json()  # 예약이 깨져도 전달은 그대로
    assert calls == [keys]
    db_session.expire_all()
    saved = [f["key"] for f in db_session.get(Order, oid).structured_data["drawing_current_files"]]
    assert saved == keys
