"""협력사 화면 작은 칸 — 320px 작은 그림 길(SPEC 2026-11-19, 조사 G22~G28).

* 작은 칸 ``<img src>`` = ``/api/files/thumb/<원본 key>``, 확대 창(``lightbox.js``)이 읽는
  ``data-foms-lightbox-src`` = ``/api/files/view/<원본 key>``(원본). 확대 창은 이 속성이 없으면 ``src`` 로 떨어진다.
* 범위: 작은 그림 길의 문지기는 원본 보기와 같다 — 자기 회사 주문 파일(협력사 원본 폴더 ``orders/<id>/partner_*`` 포함)은
  열리고, 다른 회사 주문 파일은 막힌다(대조군).
* 일부러 그대로 둔 칸: G27 완공 · AS 사진(폰 두 칸 격자 약 175px — 2배 화면에서 320px 가 모자란다).
"""

from __future__ import annotations

import re

from sqlalchemy.orm.attributes import flag_modified

import foms.api.files.routes as file_routes
import foms.services.files.list_thumb_schedule as schedule_mod
from db import db_session
from models import Order, OrderAttachment, User
from tests.security.partner_fixtures import _client, world  # noqa: F401 — pytest fixture 재노출
from tests.security.test_partner_list_sort import _order


def _thumb(key: str) -> str:
    return f"/api/files/thumb/{key}"


def _view(key: str) -> str:
    return f"/api/files/view/{key}"


def _partner(world, key="partner_a"):
    return db_session.get(User, world[key])


def _attach(order_id: int, folder: str, name: str, *, category="measurement", file_type="image",
            item_index=None, thumbnail_key=None) -> OrderAttachment:
    att = OrderAttachment(order_id=order_id, filename=name, file_type=file_type, category=category,
                          storage_key=f"orders/{order_id}/{folder}/{name}", thumbnail_key=thumbnail_key,
                          item_index=item_index, file_size=10)
    db_session.add(att)
    db_session.commit()
    return att


def _set_sd(order_id: int, **values) -> None:
    order = db_session.get(Order, order_id)
    sd = dict(order.structured_data or {})
    sd.update(values)
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def _img_tag(html: str, src: str) -> str:
    match = re.search(r'<img[^>]*src="' + re.escape(src) + r'"[^>]*>', html)
    assert match, src
    return match.group(0)


# ----------------------------------------------------------------------- G22 차례 보드
def test_turn_board_strip_small_and_lightbox_original(app, world):
    oid = _order(app, world["partner_a"], "turnA", drawing_at="2026-10-30 01:00:00", status="TRANSFERRED")
    key = f"orders/{oid}/drawing/turnA.png"
    html = _client(app, _partner(world)).get("/partner?turn=1").get_data(as_text=True)
    sheet = re.search(r'<button type="button" class="pp-tcard__sheet"[^>]*>\s*<img[^>]*>', html)
    assert sheet, "차례 카드 그림 칸이 없다"
    assert f'data-foms-lightbox-src="{_view(key)}"' in sheet.group(0)  # 확대 = 원본
    assert f'<img src="{_thumb(key)}"' in sheet.group(0)  # 칸 = 작은 그림


# ----------------------------------------------------------------------- G23~G26 주문 상세(파일 · 도면 · 품목 · 참고 사진)
def test_order_detail_small_slots_and_lightbox_original(app, world):
    oid = _order(app, world["partner_a"], "detailA", drawing_at="2026-10-30 01:00:00", status="TRANSFERRED",
                 stage="DRAWING")
    loose = _attach(oid, "partner_measurement", "20261119_x_a.jpg",
                    thumbnail_key=f"orders/{oid}/partner_measurement/thumb_20261119_x_a.jpg")
    kor = _attach(oid, "partner_measurement", "20261119_101010_ab12cd34_png", item_index=0)
    pdf = _attach(oid, "partner_measurement", "20261119_x_plan.pdf", file_type="file")
    final_key = f"orders/{oid}/drawing/detailA.png"
    ref_key = f"orders/{oid}/drawing_gateway/ref1.jpg"
    order = db_session.get(Order, oid)
    history = list((order.structured_data or {}).get("drawing_transfer_history") or [])
    history.append({"action": "REQUEST_REVISION", "at": "2026-10-30 02:00:00", "note": "가짜 요청",
                    "partner_org_id": order.partner_org_id, "files": [{"key": ref_key, "filename": "ref1.jpg"}]})
    _set_sd(oid, drawing_transfer_history=history)

    html = _client(app, _partner(world)).get(f"/partner/orders/{oid}").get_data(as_text=True)
    # G25 공통 실측 40px · G24 파일 갤러리 72px — 둘 다 작은 그림, 확대는 원본.
    assert html.count(f'src="{_thumb(loose.storage_key)}"') >= 1
    assert f'data-foms-lightbox-src="{_view(loose.storage_key)}"' in html
    assert f'src="{_view(loose.thumbnail_key)}"' not in html  # 옛 300px thumb_ 는 이제 안 쓴다
    # G26 제품 카드 보낸 사진(한글 이름 key) — 작은 그림 + 확대 원본.
    assert f'src="{_thumb(kor.storage_key)}"' in html
    assert f'data-foms-lightbox-src="{_view(kor.storage_key)}"' in html
    # 그림 아닌 파일은 <img> 도, 작은 그림 길도 없다.
    assert _thumb(pdf.storage_key) not in html
    # 파일 탭 '도면' 72px 칸 = 작은 그림, 도면 탭 16:9 큰 카드 = 원본(N3 그대로).
    assert f'src="{_thumb(final_key)}"' in html
    assert re.search(r'<img src="' + re.escape(_view(final_key)) + r'"[^>]*class="foms-drawing-card__img"', html)
    # G23 수정 요청 참고 사진 56px = 작은 그림, 링크 · 확대 = 원본.
    ref = re.search(r'<a class="pp-dthread__ref"[^>]*>\s*<img[^>]*>', html)
    assert ref, "참고 사진 칸이 없다"
    assert f'href="{_view(ref_key)}"' in ref.group(0) and f'data-foms-lightbox-src="{_view(ref_key)}"' in ref.group(0)
    assert f'<img src="{_thumb(ref_key)}"' in ref.group(0)


# ----------------------------------------------------------------------- G28 AS 접수 창 사진 고르기
def test_as_intake_pick_photos_small(app, world, monkeypatch):
    import foms.api.partner.as_intake as as_api

    oid = _order(app, world["partner_a"], "asA")
    img = _attach(oid, "construction", "c1.jpg", category="construction",
                  thumbnail_key=f"orders/{oid}/construction/thumb_c1.jpg")
    monkeypatch.setattr(as_api.svc, "form_view", lambda order: {"mode": as_api.svc.MODE_NEW})
    monkeypatch.setattr(as_api, "construction_photos_for_partner", lambda db, order: [
        {"id": img.id, "filename": img.filename, "is_image": True, "storage_key": img.storage_key,
         "thumbnail_key": img.thumbnail_key}])
    resp = _client(app, _partner(world)).get(f"/api/partner/orders/{oid}/as")
    assert resp.status_code == 200, resp.get_json()
    photo = resp.get_json()["data"]["construction_photos"][0]
    assert photo["thumb_url"] == _thumb(img.storage_key)
    assert photo["url"] == _view(img.storage_key)


def test_completion_photos_left_on_old_path(app, world):
    """G27 은 일부러 그대로 — 칸이 커서(폰 약 175px) 320px 가 2배 화면에 모자란다."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2] / "foms/web/partner/__init__.py").read_text(encoding="utf-8")
    assert '"thumb_url": build_file_view_url(p["thumbnail_key"])' in src


# ----------------------------------------------------------------------- 범위: 작은 그림 길의 문지기
class _FakeR2:
    storage_type = "r2"

    def object_exists(self, key):
        return False

    def read_file_bytes(self, key):
        return None

    def get_download_url(self, key, expires_in=3600, response_content_disposition=None):
        return f"https://r2.invalid/{key}?sig=1"


def test_thumb_route_scope_own_company_ok_other_company_blocked(app, world, monkeypatch):
    monkeypatch.setattr(file_routes, "get_storage", lambda: _FakeR2())
    monkeypatch.setattr(file_routes, "schedule_list_thumb", lambda key: None, raising=False)
    monkeypatch.setattr(schedule_mod, "schedule_list_thumb", lambda key: None)
    own = _order(app, world["partner_a"], "scopeA", drawing_at="2026-10-30 01:00:00", status="TRANSFERRED")
    other = _order(app, world["partner_b"], "scopeB", drawing_at="2026-10-30 01:00:00", status="TRANSFERRED")
    own_partner = _attach(own, "partner_measurement", "20261119_x_own.jpg").storage_key
    other_partner = _attach(other, "partner_measurement", "20261119_x_other.jpg").storage_key
    own_drawing = f"orders/{own}/drawing/scopeA.png"
    other_drawing = f"orders/{other}/drawing/scopeB.png"

    client = _client(app, _partner(world))
    for key in (own_partner, own_drawing):
        resp = client.get(_thumb(key))
        assert resp.status_code == 302, (key, resp.status_code)  # 작은 그림 아직 없음 → 원본으로
        assert resp.headers["Location"].startswith("https://r2.invalid/")
    for key in (other_partner, other_drawing):
        resp = client.get(_thumb(key))
        assert resp.status_code in (403, 404), (key, resp.status_code)  # 다른 회사 주문 = 막힘
        assert resp.status_code == client.get(_view(key)).status_code  # 원본 보기와 같은 답
    # 대조군: 그 회사 직원은 자기 주문 것을 연다.
    other_client = _client(app, _partner(world, "partner_b"))
    assert other_client.get(_thumb(other_partner)).status_code == 302
