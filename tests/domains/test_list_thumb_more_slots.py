"""목록 작은 그림 — 남은 작은 칸들(SPEC docs/specs/2026-11-19-list-drawing-small-image_SPEC.md, 조사 G5 · G13~G31).

칸마다 두 가지를 본다.
* **작은 칸 ``<img src>`` = 320px 작은 그림 길**(``/api/files/thumb/<원본 key>``, key 에서 계산만 — 조회 없음).
  그림이 아닌 key(PDF · 확장자 없음)는 지금 주소 그대로(작은 그림 길은 404 라 깨진 그림이 된다).
  한글 이름 파일(점 없이 ``_png`` 로 끝나는 key)도 그림이다.
* **눌러 크게 보기 · 링크 · 뷰어 = 원본**(``/api/files/view/<원본 key>``) — 뷰어가 실제로 읽는 속성으로 본다
  (``data-view-url`` · ``href`` · ``view_url`` 목록).

JS 가 주소를 만드는 칸은 Node 로 실제로 돌려 본다(문자열 존재 단언만으로는 갈래를 꺼도 초록이다).
협력사 화면(G22~G28)은 ``tests/security/test_partner_list_thumb_more_slots.py``.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.files.list_thumb import is_list_thumb_source
from models import Order, OrderAttachment, User

ROOT = Path(__file__).resolve().parents[2]
PIN = "20261119s"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _thumb(key: str) -> str:
    return f"/api/files/thumb/{key}"


def _view(key: str) -> str:
    return f"/api/files/view/{key}"


def _user(username: str, role: str = "STAFF", team: str = "CS") -> User:
    user = User(username=username, password=generate_password_hash("pw"), role=role, team=team,
                name=f"{username}-이름", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User):
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role
    return client


def _order(sd: dict | None = None, *, stage: str = "COMPLETED") -> Order:
    order = Order(received_date=date.today().strftime("%Y-%m-%d"), customer_name="가짜고객", phone="010-0000-0000",
                  address="가짜시", product="가짜장", status=stage, is_erp_order=True, erp_stage_code=stage,
                  structured_data=sd or {"workflow": {"stage": stage}, "items": [{"product_name": "가짜장"}]})
    db_session.add(order)
    db_session.commit()
    return order


def _attach(order_id: int, name: str, *, category: str = "measurement", file_type: str = "image",
            thumbnail_key: str | None = None) -> OrderAttachment:
    att = OrderAttachment(order_id=order_id, filename=name, file_type=file_type, category=category,
                          storage_key=f"orders/{order_id}/{category}/{name}", thumbnail_key=thumbnail_key,
                          file_size=10)
    db_session.add(att)
    db_session.commit()
    return att


# ----------------------------------------------------------------------- Node 로 JS 돌리기
_NODE_PRELUDE = r"""
const vm = require('vm');
const fs = require('fs');
const noop = function () {};
globalThis.window = globalThis;
globalThis.console = { log: noop, warn: noop, error: noop };
globalThis.document = { addEventListener: noop, getElementById: function () { return null; },
  querySelector: function () { return null; }, querySelectorAll: function () { return []; } };
globalThis.escapeHtml = function (s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
};
// node -e 는 process.argv = [node, 인자1, 인자2] 다(스크립트 이름 자리가 없다).
for (const rel of JSON.parse(process.argv[1])) { vm.runInThisContext(fs.readFileSync(rel, 'utf8'), { filename: rel }); }
const input = JSON.parse(process.argv[2]);
"""


def _node(sources: list[str], body: str, payload) -> object:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS behaviour checks"
    script = _NODE_PRELUDE + body
    proc = subprocess.run([node, "-e", script, json.dumps(sources), json.dumps(payload)], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return json.loads(proc.stdout)


# ----------------------------------------------------------------------- 첨부 직렬화(G17 · G18 · G21 의 근원)
def test_serialize_attachment_adds_small_url_and_keeps_old_fields(app):
    from foms.api.files.common import serialize_attachment

    order = _order()
    img = _attach(order.id, "a.jpg", thumbnail_key=f"orders/{order.id}/measurement/thumb_a.jpg")
    kor = _attach(order.id, "20261119_101010_ab12cd34_png")
    pdf = _attach(order.id, "plan.pdf", file_type="file")
    video = _attach(order.id, "clip.mp4", file_type="video")

    data = serialize_attachment(img)
    assert data["small_url"] == _thumb(img.storage_key)
    assert data["view_url"] == _view(img.storage_key)  # 원본 — 뷰어 · 큰 자리가 그대로 쓴다
    assert data["thumbnail_view_url"] == _view(img.thumbnail_key)  # 옛 칸 뜻 그대로
    assert serialize_attachment(kor)["small_url"] == _thumb(kor.storage_key)  # 한글 이름 key
    assert serialize_attachment(pdf)["small_url"] is None
    assert serialize_attachment(video)["small_url"] is None


def test_attachment_list_api_carries_small_url(client):
    staff = _user("lt-more-list")
    order = _order()
    img = _attach(order.id, "b.png")
    _login(client, staff)
    resp = client.get(f"/api/orders/{order.id}/attachments?category=measurement")
    assert resp.status_code == 200, resp.get_json()
    rows = {a["id"]: a for a in resp.get_json()["attachments"]}
    assert rows[img.id]["small_url"] == _thumb(img.storage_key)
    assert rows[img.id]["view_url"] == _view(img.storage_key)


def test_order_edit_tiles_use_small_url_first_and_preview_original():
    """G17 — 폰 타일(76px~) · PC 40px 칸 = small_url 먼저. 눌러 크게 보기는 __erpAttachments 의 view_url."""
    js = _read("static/js/orders/erp-order-shared.js")
    tile = js[js.index("function erpBuildAttachmentMediaTile(a)"):js.index("function erpBuildAttachmentTile(a")]
    assert "const gridImageSrc = a.small_url || (" in tile
    # 그림 아닐 때(small_url 없음) 옛 갈래 그대로 — 폰 원본 · PC 옛 썸네일.
    assert "(a.view_url || a.thumbnail_view_url || '')" in tile
    assert "const thumb = a.small_url || a.thumbnail_view_url || a.view_url || '';" in js
    preview = js[js.index("function erpOpenAttachmentPreview("):]
    preview = preview[:preview.index("\n}\n")]
    assert "erpStableAttachmentUrls(a)" in preview and "small_url" not in preview
    stable = js[js.index("function erpStableAttachmentUrls("):]
    stable = stable[:stable.index("\n}\n")]
    assert "viewUrl: isSignedStorageUrl(a.view_url) ? stableViewUrl : (a.view_url || stableViewUrl)" in stable


def test_dashboard_attach_strip_small_src_and_original_viewer():
    """G18 — PC 대시보드 펼친 줄 80x60 칸. 실제로 돌려 img src 와 data-view-url 을 본다."""
    out = _node(["static/js/orders/order-detail-fragment.js"],
                "process.stdout.write(JSON.stringify(buildMainAttachThumbsHtml(7, input)));",
                [
                    {"id": 1, "filename": "a.jpg", "file_type": "image", "view_url": _view("orders/7/m/a.jpg"),
                     "thumbnail_view_url": _view("orders/7/m/thumb_a.jpg"), "small_url": _thumb("orders/7/m/a.jpg")},
                    {"id": 2, "filename": "b.jpg", "file_type": "image", "view_url": _view("orders/7/m/b.jpg"),
                     "thumbnail_view_url": _view("orders/7/m/thumb_b.jpg"), "small_url": None},
                ])
    html = str(out)
    assert f"src='{_thumb('orders/7/m/a.jpg')}'" in html
    assert f'data-view-url="{_view("orders/7/m/a.jpg")}"' in html  # 뷰어 = 원본
    assert f"src='{_view('orders/7/m/thumb_b.jpg')}'" in html  # small_url 없으면 옛 갈래
    assert "/api/files/thumb/" not in html.split('data-att-id="2"', 1)[1]


def test_tablet_measure_photos_small_src_and_original_open():
    """G21 — 실측 태블릿 폼 사진 칸 = small_url, 누르면(openPhoto) state.photos 의 view_url 원본."""
    js = _read("static/js/foms/tablet-measure-form.js")
    assert "'<img src=\"' + escapeHtml(att.small_url || url) + '\"" in js
    opener = js[js.index("view_url: att.view_url || att.url"):][:200]
    assert "small_url" not in opener


def test_changed_dashboard_and_tablet_scripts_are_repinned():
    entry = _read("static/js/orders/erp-dashboard-entry.js")
    # 게이트웨이 · entry 는 뒤 작업(2026-11-20 중간 크기 그림 640, 20261120m)이 정당하게 올린다 — "이 작업 핀보다 오래되지 않았다".
    gateway_pin = entry.split("erp-dashboard-gateway.js?v=", 1)[1].split("'", 1)[0]
    assert f"order-detail-fragment.js?v={PIN}" in entry and gateway_pin >= PIN, gateway_pin
    layout = _read("templates/partials/shared/layout_scripts.html")
    entry_pin = layout.split("erp-dashboard-entry.js') }}?v=", 1)[1].split('"', 1)[0]
    assert entry_pin >= PIN, entry_pin
    assert f"tablet-measure-form.js') }}}}?v={PIN}" in layout
    for rel in ("templates/construction/partials/dashboard_body.html", "templates/production/partials/dashboard_body.html"):
        assert f"order-detail-fragment.js') }}}}?v={PIN}" in _read(rel), rel


# ----------------------------------------------------------------------- G19 PC 대시보드 도면 창구
_GATEWAY_KEYS = [
    "orders/7/drawing/a.png", "orders/7/drawing/A.JPEG", "orders/7/drawing/a.webp", "orders/7/drawing/a.bmp",
    "orders/7/drawing/a.gif", "orders/7/drawing/20261119_101010_ab12cd34_png", "orders/7/drawing/png",
    "orders/7/drawing/x_JPG", "orders/7/drawing/a.pdf", "orders/7/drawing/a.svg", "orders/7/drawing/a.heic",
    "orders/7/drawing/20261119_101010_ab12cd34_pdf", "orders/7/drawing/a.b_png", "orders/7/drawing/thumb_a.png",
    "orders/7/drawing/sthumb320_a.png.jpg", "orders/7/drawing/pthumb720_a.png.jpg", "orders/7/drawing/noext", "",
]


def test_gateway_small_url_rule_matches_server():
    """JS 판정이 서버 ``is_list_thumb_source`` 와 어긋나면 404 → 깨진 그림이다. 같은 key 묶음으로 둘을 맞춘다."""
    got = _node(["static/js/orders/dashboard/erp-dashboard-gateway.js"],
                "process.stdout.write(JSON.stringify(input.map(function (k) { return gatewaySmallUrl(k); })));",
                _GATEWAY_KEYS)
    expected = [(_thumb(k) if is_list_thumb_source(k) else "") for k in _GATEWAY_KEYS]
    assert got == expected
    assert sum(1 for v in expected if v) >= 6 and sum(1 for v in expected if not v) >= 6  # 양쪽 대조군


def test_gateway_thumb_small_with_original_fallback_and_viewer():
    out = _node(["static/js/orders/dashboard/erp-dashboard-gateway.js"],
                "var html = renderGatewayFiles(input, 'g1');"
                "process.stdout.write(JSON.stringify({html: html, group: __drawingGatewayImageGroups['g1'].map(gatewayViewUrl)}));",
                [{"key": "orders/7/drawing/a.png", "filename": "a.png"},
                 {"key": "orders/7/drawing/b.heic", "filename": "b.heic"}])
    html = out["html"]
    assert f'<img src="{_thumb("orders/7/drawing/a.png")}" data-full-src="{_view("orders/7/drawing/a.png")}"' in html
    assert f'<img src="{_view("orders/7/drawing/b.heic")}"' in html  # 작은 그림 대상 아님 → 원본
    assert "this.onerror=null" in html and "this.dataset.fullSrc" in html  # 어긋나도 원본으로 한 번 되돌림
    assert out["group"] == [_view("orders/7/drawing/a.png"), _view("orders/7/drawing/b.heic")]  # 뷰어 = 원본


# ----------------------------------------------------------------------- G16 완공 사진 목록
def test_completion_photos_small_url_and_viewer_original(app):
    from foms.api.cs.dashboard import _serialize_completion_orders

    order = _order({"workflow": {"stage": "COMPLETED"}, "parties": {"customer": {"name": "가짜고객"}}})
    img = _attach(order.id, "c.jpg", category="construction")
    pdf = _attach(order.id, "c.pdf", category="construction", file_type="file")
    rows = _serialize_completion_orders(db_session, [order])
    photos = {p["id"]: p for p in rows[0]["construction_photos"]}
    assert photos[img.id]["small_url"] == _thumb(img.storage_key)
    assert photos[img.id]["view_url"] == _view(img.storage_key)
    assert photos[pdf.id]["small_url"] is None
    script = _read("templates/cs/partials/completion_scripts.html")
    assert "escapeAttr(photo.small_url || photo.view_url || '#')" in script
    assert "return { url: photo.view_url, filename: photo.filename, key: photo.storage_key };" in script


# ----------------------------------------------------------------------- G15 마법사 실측 사진 판
def test_wizard_measure_photos_thumb_is_small_route(app):
    from foms.api.drawing.wizard import _build_measure_photos

    order = _order({"workflow": {"stage": "DRAWING"}, "items": [{"product_name": "가짜장"}]}, stage="DRAWING")
    legacy = _attach(order.id, "m.jpg", thumbnail_key=f"orders/{order.id}/measurement/thumb_m.jpg")
    kor = _attach(order.id, "20261119_101010_ab12cd34_jpg")
    heic = _attach(order.id, "m.heic", thumbnail_key=f"orders/{order.id}/measurement/thumb_m.jpg")
    photos = {p["key"]: p for p in _build_measure_photos(db_session, order)}
    assert photos[legacy.storage_key]["thumb_url"] == _thumb(legacy.storage_key)  # 옛 thumb_ 보다 먼저
    assert photos[kor.storage_key]["thumb_url"] == _thumb(kor.storage_key)
    assert photos[heic.storage_key]["thumb_url"] == _view(heic.thumbnail_key)  # 작은 그림 대상 아님 → 옛 길
    js = _read("static/js/drawing/wizard.js")
    assert "if (!photo || !photo.key" in js  # 누르면 key(원본)로 넣는다 — thumb_url 을 넣지 않는다


# ----------------------------------------------------------------------- G13 도면 태블릿 시트 줄
def test_tablet_sheet_strip_small_src_and_original_viewer(client):
    order = _order({"workflow": {"stage": "DRAWING"}, "items": [{"product_name": "가짜장"}]}, stage="DRAWING")
    png = f"orders/{order.id}/drawing_wizard/exports/s1.png"
    kor = f"orders/{order.id}/drawing_wizard/exports/20261119_101010_ab12cd34_png"
    sd = copy.deepcopy(order.structured_data)
    sd["drawing_wizard"] = {"sheets": [{"id": "s1"}, {"id": "s2"}], "pending": {
        "s1": {"key": png, "filename": "s1.png", "sheet_name": "가짜시트1", "at": "2026-11-19 10:00"},
        "s2": {"key": kor, "filename": "s2.png", "sheet_name": "가짜시트2", "at": "2026-11-19 10:01"},
    }}
    order.structured_data = sd
    db_session.commit()
    _login(client, _user("lt-more-sheet", team="DRAWING"))
    html = client.get(f"/erp/drawing-workbench/tablet-sheet/{order.id}").get_data(as_text=True)
    for key in (png, kor):
        tag = re.search(r'<img class="foms-drawing-sheet__sheet-thumb"[^>]*' + re.escape(_thumb(key)) + r'"[^>]*>', html)
        assert tag, key
        assert f'data-view-url="{_view(key)}"' in tag.group(0)  # 뷰어(tablet-drawing-review.js) = 원본
    body = _read("templates/drawing/partials/tablet_sheet_body.html")
    assert 'src="{{ s.thumb_url }}"' in body and 'data-view-url="{{ s.view_url }}"' in body
    review = _read("static/js/foms/tablet-drawing-review.js")
    assert 'node.getAttribute("data-view-url")' in review


# ----------------------------------------------------------------------- G5 주문 화면 AS 도면 판
def test_as_drawing_panel_small_img_and_original_link(client):
    from foms.services.orders import as_drawing as asd

    order = _order()
    png = f"orders/{order.id}/as_drawing/r1.png"
    pdf = f"orders/{order.id}/as_drawing/r1.pdf"
    sd = copy.deepcopy(order.structured_data)
    sd[asd.AS_DRAWING_KEY] = {"rounds": [{"round_id": "asd_1", "status": asd.STATUS_CONFIRMED,
                                          "files": [{"key": png, "name": "r1.png"}, {"key": pdf, "name": "r1.pdf"}]}]}
    order.structured_data = sd
    db_session.commit()
    _login(client, _user("lt-more-as", team="DRAWING"))
    resp = client.get(f"/api/orders/{order.id}/drawing/as")
    assert resp.status_code == 200, resp.get_json()
    files = resp.get_json()["data"]["rounds"][0]["files"]
    assert files[0]["small_url"] == _thumb(png) and files[0]["view_url"] == _view(png)
    assert files[1]["small_url"] is None and files[1]["view_url"] == _view(pdf)
    js = _read("static/js/orders/erp-as-drawing-panel.js")
    assert "a.href = f.view_url;" in js and "img.src = f.small_url || f.view_url;" in js


# ----------------------------------------------------------------------- G29 영업 수수료 확정 도면
def test_my_commission_drawings_small_and_viewer_original():
    from foms.services.sales_commission.statement_detail import build_order_detail

    png = "orders/9/drawing/final.png"
    kor = "orders/9/drawing/20261119_101010_ab12cd34_png"
    detail = build_order_detail({"drawing_current_files": [
        {"key": png, "filename": "final.png"}, {"key": kor, "filename": "최종.png"},
        {"key": "orders/9/drawing/final.pdf", "filename": "final.pdf"}]})
    by_key = {d["key"]: d for d in detail["drawings"]}
    assert by_key[png]["thumb_url"] == _thumb(png) and by_key[png]["view_url"] == _view(png)
    assert by_key[kor]["thumb_url"] == _thumb(kor)
    assert by_key["orders/9/drawing/final.pdf"]["thumb_url"] == _view("orders/9/drawing/final.pdf")
    tpl = _read("templates/sales_commission/my_commission.html")
    assert '<img src="{{ f.thumb_url or f.view_url }}"' in tpl
    assert 'data-view-url="{{ f.view_url }}"' in tpl  # 크게 보기(my-commission-drawings.js) = 원본


# ----------------------------------------------------------------------- G30 거래명세서 작성 도면 띠
def test_partner_statement_drawing_strip_small_and_big_original():
    from foms.api.partner_statements_staff import drawing_card

    card = drawing_card(1, {"key": "orders/9/drawing/final.png", "filename": "final.png"})
    assert card["thumb_url"] == _thumb("orders/9/drawing/final.png")
    assert card["url"] == _view("orders/9/drawing/final.png")
    pdf = drawing_card(2, {"key": "orders/9/drawing/final.pdf", "filename": "final.pdf"})
    assert pdf["thumb_url"] == pdf["url"] and pdf["is_image"] is False
    js = _read("static/js/cs/partner-statement-edit.js")
    strip = js[js.index("function thumb(strip, i)"):js.index("function drawDrawings()")]
    assert "img.src = d.thumb_url || d.url;" in strip
    big = js[js.index("function drawDrawings()"):]
    big = big[:big.index("if (list.length < 2")]
    assert "a.href = d.url;" in big and "img.src = d.url;" in big and "thumb_url" not in big


# ----------------------------------------------------------------------- G31 AS 발송 확인 창
class _SignedStorage:
    storage_type = "r2"

    def get_download_url(self, key, expires_in=3600, **_):
        return f"https://signed.invalid/{key}?e={expires_in}"


def test_as_push_preview_image_uses_app_small_route(client, monkeypatch):
    import foms.api.channel.channel_integration as ci

    monkeypatch.setattr(ci, "get_storage", lambda: _SignedStorage())
    order = _order()
    img = _attach(order.id, "as1.jpg", category="as", thumbnail_key=f"orders/{order.id}/as/thumb_as1.jpg")
    pdf = _attach(order.id, "as1.pdf", category="as", file_type="file")
    _login(client, _user("lt-more-push"))
    resp = client.get(f"/api/channel/push-preview?order_id={order.id}&push_kind=as")
    assert resp.status_code == 200, resp.get_json()
    files = {f["id"]: f for f in resp.get_json()["files"]}
    assert files[img.id]["url"] == _thumb(img.storage_key)  # 같은 출처 · 원본과 같은 문지기 · 30일 캐시
    assert files[pdf.id]["url"] == f"https://signed.invalid/{pdf.storage_key}?e=3600"  # 그림 아님 → 지금 그대로


def test_left_unchanged_slots_stay_original():
    """일부러 그대로 둔 칸(보고 목록) — 바꾸면 이 시험과 보고를 같이 고친다.

    * (G14 도면 확인 범위 창은 합친 뒤 바꿨다 — 56px 칸 = ``small_url``, 없으면 원본.)
    * (G20 PC 대시보드 교체 대상 카드 · G27 협력사 완공 · AS 사진은 320 이 모자라 남겼다가 640 중간 크기 그림으로
      바꿨다 — SPEC 2026-11-20-mid-size-image, 시험 ``test_mid_thumb_screens.py`` · ``tests/security/test_partner_mid_thumb.py``.)
    """
    assert "img.src = d.small_url || d.view_url;" in _read("static/js/foms/drawing-ok-scope.js")
    att = _read("static/js/orders/dashboard/erp-dashboard-attachments.js")
    assert "gatewaySmallUrl(key, 640)" in att and "gatewaySmallUrl(key)" not in att  # 교체 대상 카드는 320 이 아니라 640


@pytest.mark.parametrize("rel", [
    "static/js/orders/dashboard/erp-dashboard-gateway.js",
    "static/js/orders/order-detail-fragment.js",
    "static/js/orders/erp-order-shared.js",
    "static/js/foms/tablet-measure-form.js",
    "static/js/orders/erp-as-drawing-panel.js",
    "static/js/cs/partner-statement-edit.js",
])
def test_changed_js_passes_node_check(rel):
    node = shutil.which("node")
    assert node, "node must be on PATH"
    proc = subprocess.run([node, "--check", str(ROOT / rel)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr or proc.stdout

