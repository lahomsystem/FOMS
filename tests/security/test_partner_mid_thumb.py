"""협력사 완공 · AS 사진 칸 — 640 중간 크기 그림(SPEC docs/specs/2026-11-20-mid-size-image_SPEC.md, 조사 G27).

* 칸 ``<img src>`` = ``/api/files/thumb/<원본 key>?w=640``(정사각 120px~ · 폰 두 칸 약 175px — 320 은 2배 화면에 모자람).
  만들 수 없는 key(HEIC · 확장자 없음)면 지금처럼 옛 썸네일 · 원본.
* 확대 창(``lightbox.js``)이 읽는 ``data-foms-lightbox-src`` = ``/api/files/view/<원본 key>``(원본).
* 범위: 640 길의 문지기는 원본 보기 · 320 과 같다 — 쿼리 인자(``?w=``)는 협력사 허용 판정(endpoint 이름)에 영향이 없다.
  자기 회사 주문은 열리고, 다른 회사 주문은 막힌다(대조군: 그 회사 직원은 연다).
"""

from __future__ import annotations

import re

import foms.api.files.routes as file_routes
from db import db_session
from models import OrderAttachment, User
from tests.security.partner_fixtures import _client, _create, _to_stage, world  # noqa: F401 — pytest fixture 재노출


def _mid(key: str) -> str:
    return f"/api/files/thumb/{key}?w=640"


def _thumb(key: str) -> str:
    return f"/api/files/thumb/{key}"


def _view(key: str) -> str:
    return f"/api/files/view/{key}"


def _partner(world, key="partner_a"):
    return db_session.get(User, world[key])


def _order(app, partner_id) -> int:
    return _create(app, partner_id).get_json()["data"]["order_id"]


def _attach(order_id: int, name: str, *, category="construction", file_type="image", thumbnail_key=None):
    att = OrderAttachment(order_id=order_id, filename=name, file_type=file_type, category=category, file_size=10,
                          storage_key=f"orders/{order_id}/{category}/{name}", thumbnail_key=thumbnail_key)
    db_session.add(att)
    db_session.commit()
    return att.storage_key, att.thumbnail_key


def _photo_li(html: str, alt: str) -> str:
    match = re.search(r'<li class="pp-photo">(?:(?!</li>).)*alt="' + re.escape(alt) + r'"(?:(?!</li>).)*</li>',
                      html, flags=re.S)
    assert match, alt
    return match.group(0)


def test_completion_photo_tile_640_and_lightbox_original(app, world):
    oid = _order(app, world["partner_a"])
    jpg, _ = _attach(oid, "front.jpg")
    legacy, legacy_thumb = _attach(oid, "side.jpg", thumbnail_key=f"orders/{oid}/construction/thumb_side.jpg")
    heic, _ = _attach(oid, "back.heic")
    _to_stage(oid, "COMPLETED")

    html = _client(app, _partner(world)).get(f"/partner/orders/{oid}").get_data(as_text=True)
    front = _photo_li(html, "front.jpg")
    assert f'<img src="{_mid(jpg)}"' in front and 'loading="lazy"' in front
    assert f'data-foms-lightbox-src="{_view(jpg)}"' in front and f'href="{_view(jpg)}"' in front  # 확대 = 원본
    side = _photo_li(html, "side.jpg")
    assert f'<img src="{_mid(legacy)}"' in side  # 옛 300px thumb_ 보다 640 이 먼저
    assert legacy_thumb not in side
    back = _photo_li(html, "back.heic")
    assert f'<img src="{_view(heic)}"' in back  # 640 대상 아님 → 지금처럼(옛 썸네일 없으면 원본)
    # 320 길로는 가지 않는다(320 은 이 칸에 흐리다).
    assert f'src="{_thumb(jpg)}"' not in html


def test_as_photo_lists_use_same_640_builder(app):
    """AS 진행 · AS 내역(접수 · 처리 사진)도 같은 ``_with_urls`` 를 지난다 — 칸 640, 확대 원본."""
    from foms.web.partner import _with_urls

    photos = [{"id": 1, "filename": "a.jpg", "storage_key": "orders/5/as/a.jpg", "thumbnail_key": "orders/5/as/a.jpg",
               "is_image": True},
              {"id": 2, "filename": "b.heic", "storage_key": "orders/5/as/b.heic",
               "thumbnail_key": "orders/5/as/thumb_b.jpg", "is_image": True}]
    out = _with_urls(photos)
    assert [(p["thumb_url"], p["url"]) for p in out] == [
        (_mid("orders/5/as/a.jpg"), _view("orders/5/as/a.jpg")),
        (_view("orders/5/as/thumb_b.jpg"), _view("orders/5/as/b.heic")),
    ]
    template = open("templates/partner/partials/order_completion.html", encoding="utf-8").read()
    assert '<img src="{{ p.thumb_url }}"' in template and 'data-foms-lightbox-src="{{ p.url }}"' in template


class _FakeR2:
    storage_type = "r2"

    def object_exists(self, key):
        return False

    def read_file_bytes(self, key):
        return None

    def get_download_url(self, key, expires_in=3600, response_content_disposition=None):
        return f"https://r2.invalid/{key}?sig=1"


def test_640_route_scope_own_company_ok_other_company_blocked(app, world, monkeypatch):
    seen: list[tuple] = []
    monkeypatch.setattr(file_routes, "get_storage", lambda: _FakeR2())
    monkeypatch.setattr(file_routes, "schedule_list_thumb", lambda key, size=320: seen.append((key, size)))
    own = _order(app, world["partner_a"])
    other = _order(app, world["partner_b"])
    own_key, _ = _attach(own, "own.jpg")
    other_key, _ = _attach(other, "other.jpg")
    _to_stage(own, "COMPLETED")
    _to_stage(other, "COMPLETED")

    client = _client(app, _partner(world))
    resp = client.get(_mid(own_key))
    assert resp.status_code == 302 and resp.headers["Location"].startswith("https://r2.invalid/")
    assert seen == [(own_key, 640)]
    for url in (_mid(other_key), _thumb(other_key)):
        resp = client.get(url)
        assert resp.status_code in (403, 404), (url, resp.status_code)  # 다른 회사 주문 = 막힘
        assert resp.status_code == client.get(_view(other_key)).status_code  # 원본 보기와 같은 답
    assert seen == [(own_key, 640)]  # 막힌 요청은 예약도 안 한다
    # 허용 크기 밖은 협력사에게도 400(파생 파일이 쌓이지 않는다).
    assert client.get(f"/api/files/thumb/{own_key}?w=1280").status_code == 400
    # 대조군: 그 회사 직원은 자기 주문 것을 연다.
    assert _client(app, _partner(world, "partner_b")).get(_mid(other_key)).status_code == 302
