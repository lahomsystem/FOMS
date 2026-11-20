"""중간 크기 그림(긴 변 640) 화면 — SPEC docs/specs/2026-11-20-mid-size-image_SPEC.md.

칸 ``<img src>`` 만 640(``/api/files/thumb/<원본 key>?w=640``), 눌러 크게 보기 · 링크 · 뷰어는 원본(``/api/files/view/``).
* AS 태블릿 전후 대조 격자 · 도면 작업실 태블릿 갤러리 · PC 대시보드 첨부 창 카드 4곳 · PC 교체 대상 카드.
* 대조군: AS 폰 카드 주소 · 도면 작업실 폰 카드(320) · 첨부 ``small_url``(320)은 그대로.

JS 가 그리는 칸은 Node 로 실제로 돌린다(닫힌 범위 안 함수는 잘라 내어 돌린다). 길 · 워커 시험은 ``test_mid_thumb.py``,
협력사 완공 · AS 사진은 ``tests/security/test_partner_mid_thumb.py``.
"""

from __future__ import annotations

import itertools
import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from db import db_session
from foms.services.files import list_thumb as lt
from models import Order, OrderAttachment, User

ROOT = Path(__file__).resolve().parents[2]
_counter = itertools.count(1)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _thumb(key: str) -> str:
    return f"/api/files/thumb/{key}"


def _mid(key: str) -> str:
    return f"/api/files/thumb/{key}?w=640"


def _view(key: str) -> str:
    return f"/api/files/view/{key}"


def _order() -> Order:
    order = Order(received_date="2026-11-20", customer_name="가짜고객", phone="010-0000-0000",
                  address="가짜시", product="가짜장", status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    return order


def _client(app, user: User | None):
    client = app.test_client()
    if user is not None:
        with client.session_transaction() as sess:
            sess["user_id"] = user.id
    return client


# ----------------------------------------------------------------------- 화면: AS 태블릿 대조 격자
def _as_attach(order_id: int, name: str, *, file_type: str = "image", thumbnail_key: str | None = None,
               created_at: datetime | None = None) -> OrderAttachment:
    att = OrderAttachment(order_id=order_id, filename=name, file_type=file_type, category="as", file_size=10,
                          storage_key=f"orders/{order_id}/as/{name}", thumbnail_key=thumbnail_key)
    if created_at is not None:
        att.created_at = created_at
    db_session.add(att)
    db_session.commit()
    return att


def test_as_compare_grid_thumb_is_640_and_viewer_original(app):
    from foms.services.as_dashboard_display import batch_resolve_as_compare_photos

    order = _order()
    order.as_completed_date = "2026-11-10"
    db_session.commit()
    before = _as_attach(order.id, "before.jpg", thumbnail_key=f"orders/{order.id}/as/thumb_before.jpg",
                        created_at=datetime(2026, 11, 1, 9, 0))
    after = _as_attach(order.id, "20261120_101010_ab12cd34_png", created_at=datetime(2026, 11, 12, 9, 0))
    heic = _as_attach(order.id, "x.heic", thumbnail_key=f"orders/{order.id}/as/thumb_x.jpg",
                      created_at=datetime(2026, 11, 2, 9, 0))
    raw_heic = _as_attach(order.id, "y.heic", created_at=datetime(2026, 11, 3, 9, 0))
    _as_attach(order.id, "plan.pdf", file_type="file", created_at=datetime(2026, 11, 4, 9, 0))

    photos = batch_resolve_as_compare_photos([order], db_session)[order.id]
    by_name = {p["name"]: p for p in photos["before"] + photos["after"]}
    assert set(by_name) == {"before.jpg", "20261120_101010_ab12cd34_png", "x.heic", "y.heic"}
    assert by_name["before.jpg"] == {"thumb": _mid(before.storage_key), "full": _view(before.storage_key),
                                     "name": "before.jpg"}  # 옛 thumb_ 보다 640 이 먼저
    assert by_name["20261120_101010_ab12cd34_png"]["thumb"] == _mid(after.storage_key)
    # 640 을 만들 수 없는 key(HEIC) — 지금처럼 옛 썸네일, 없으면 원본.
    assert by_name["x.heic"]["thumb"] == _view(heic.thumbnail_key)
    assert by_name["y.heic"]["thumb"] == _view(raw_heic.storage_key)
    assert all(p["full"].startswith("/api/files/view/") for p in by_name.values())  # 뷰어 = 원본


def test_as_compare_template_lightbox_reads_full_not_src():
    body = _read("templates/cs/partials/tablet_as_compare_body.html")
    tags = re.findall(r'<img class="foms-as-compare-thumb"[^>]*>', body, flags=re.S)
    assert len(tags) == 2
    for tag in tags:
        assert 'src="{{ p.thumb }}"' in tag and 'loading="lazy"' in tag
        assert 'data-foms-lightbox-src="{{ p.full }}"' in tag and 'data-foms-lightbox-download="{{ p.full }}"' in tag


def test_as_phone_card_thumbnail_unchanged_control(app, monkeypatch):
    """대조군: AS 폰 카드(44px) 주소 · 스위치는 이번 범위 밖 — 원본 보기 길 그대로."""
    import foms.services.as_dashboard_display as asd

    order = _order()
    att = _as_attach(order.id, "card.jpg")
    monkeypatch.setattr(asd, "as_thumb_enabled", lambda **k: True)
    assert asd.batch_resolve_as_thumbnail_urls([order.id], db_session) == {order.id: _view(att.storage_key)}
    src = _read("foms/services/as_dashboard_display.py")
    assert "    if not as_thumb_enabled() or not order_ids:" in src  # 스위치 호출 모양도 그대로


# ----------------------------------------------------------------------- 화면: 도면 작업실 태블릿 갤러리
def test_drawing_gallery_tile_640_phone_card_320_viewer_original(app, monkeypatch):
    from flask import render_template

    import foms.services.drawing_workbench_display as dwd

    monkeypatch.setattr(dwd, "drawing_thumb_enabled", lambda **k: True)
    order = _order()
    png = f"orders/{order.id}/drawing/a.png"
    svg = f"orders/{order.id}/drawing/b"  # 확장자 없는 옛 key — 그림이지만 작은 그림 · 640 대상이 아니다
    files = dwd.resolve_row_image_list(order.id, [{"key": png, "filename": "a.png"},
                                                  {"key": svg, "filename": "b.png"}], db_session)
    assert [(f["thumb_url"] if "thumb_url" in f else None, f["mid_url"]) for f in files] == [
        (_thumb(png), _mid(png)), (None, None)]
    card_thumb = dwd.pick_row_thumbnail_url(files)
    assert card_thumb == _thumb(png)  # 대조군: 폰 카드(76px)는 320 그대로

    def _row(image_files):
        return {"id": order.id, "customer_name": "가짜고객", "drawing_status": "TRANSFERRED", "construction_days": None,
                "construction_date": "", "thumbnail_url": dwd.pick_row_thumbnail_url(image_files),
                "drawing_files": image_files, "file_count": len(image_files)}

    with app.test_request_context():
        html = render_template("drawing/partials/tablet_gallery_body.html",
                               rows=[_row(files), _row(files[1:])], filters={}, pagination=None, stats={}, sort_by="")
    tiles = re.findall(r'<img class="foms-drawing-gallery-card__img" src="([^"]+)"', html)
    assert tiles == [_mid(png), _view(svg)]  # 그림이 아니면 원본
    viewer = re.findall(r"data-foms-drawing-files='([^']+)'", html)
    viewer_files = json.loads(viewer[0].replace("&#34;", '"').replace("&quot;", '"'))
    assert [f["view_url"] for f in viewer_files] == [_view(png), _view(svg)]  # 눌러 크게 보기 = 원본
    review_js = _read("static/js/foms/tablet-drawing-review.js")
    assert "mid_url" not in review_js and "thumb_url" not in review_js  # 뷰어는 view_url 만 읽는다


# ----------------------------------------------------------------------- 화면: 첨부 직렬화 · PC 첨부 창 카드(N7)
def _attach(order_id: int, name: str, *, category: str = "measurement", file_type: str = "image",
            thumbnail_key: str | None = None) -> OrderAttachment:
    att = OrderAttachment(order_id=order_id, filename=name, file_type=file_type, category=category,
                          storage_key=f"orders/{order_id}/{category}/{name}", thumbnail_key=thumbnail_key,
                          file_size=10)
    db_session.add(att)
    db_session.commit()
    return att


def test_serialize_attachment_adds_mid_url_and_keeps_old_fields(app):
    from foms.api.files.common import serialize_attachment

    order = _order()
    img = _attach(order.id, "a.jpg", thumbnail_key=f"orders/{order.id}/measurement/thumb_a.jpg")
    pdf = _attach(order.id, "plan.pdf", file_type="file")
    heic = _attach(order.id, "c.heic")
    data = serialize_attachment(img)
    assert data["mid_url"] == _mid(img.storage_key)
    assert data["small_url"] == _thumb(img.storage_key)  # 대조군: 320 칸 그대로
    assert data["view_url"] == _view(img.storage_key)
    assert data["thumbnail_view_url"] == _view(img.thumbnail_key)
    assert serialize_attachment(pdf)["mid_url"] is None and serialize_attachment(heic)["mid_url"] is None


def test_attachment_list_api_carries_mid_url(app):
    staff = User(username=f"midthumb-api-{next(_counter)}", password="x", role="ADMIN", team="CS", name="가짜직원",
                 is_active=True)
    db_session.add(staff)
    db_session.commit()
    order = _order()
    order.is_erp_order = True
    db_session.commit()
    img = _attach(order.id, "b.png", category="as")
    resp = _client(app, staff).get(f"/api/orders/{order.id}/attachments")
    assert resp.status_code == 200, resp.get_json()
    rows = {a["id"]: a for a in resp.get_json()["attachments"]}
    assert rows[img.id]["mid_url"] == _mid(img.storage_key) and rows[img.id]["view_url"] == _view(img.storage_key)


_NODE_PRELUDE = r"""
const vm = require('vm');
const fs = require('fs');
const noop = function () {};
globalThis.window = globalThis;
globalThis.console = { log: noop, warn: noop, error: noop };
const els = {};
globalThis.__els = els;
globalThis.document = { addEventListener: noop, getElementById: function (id) { return els[id] || null; },
  querySelector: function () { return null; }, querySelectorAll: function () { return []; } };
globalThis.__escape = function (s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
};
globalThis.escapeHtml = globalThis.__escape;
globalThis.__drawingCurrentFilesByOrder = {};
// node -e 는 process.argv = [node, 인자1, 인자2] 다. 소스는 명령줄 길이 상한(Windows) 때문에 파일로 넘긴다.
const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
for (const src of JSON.parse(fs.readFileSync(process.argv[1], 'utf8'))) {
  vm.runInThisContext(fs.readFileSync(src.path, 'utf8'), { filename: src.name });
}
"""


def _node(sources: list[tuple[str, str]], body: str, payload) -> object:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS behaviour checks"
    with tempfile.TemporaryDirectory() as tmp:
        listing = []
        for idx, (name, code) in enumerate(sources):
            path = Path(tmp) / f"src{idx}.js"
            path.write_text(code, encoding="utf-8")
            listing.append({"name": name, "path": str(path)})
        (Path(tmp) / "sources.json").write_text(json.dumps(listing), encoding="utf-8")
        (Path(tmp) / "input.json").write_text(json.dumps(payload), encoding="utf-8")
        proc = subprocess.run([node, "-e", _NODE_PRELUDE + body, str(Path(tmp) / "sources.json"),
                               str(Path(tmp) / "input.json")],
                              cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return json.loads(proc.stdout)


def _function_source(text: str, signature: str) -> str:
    """``signature`` 로 시작하는 함수 한 개를 중괄호 짝으로 잘라 낸다(닫힌 범위 안 함수를 따로 돌리려고)."""
    start = text.index(signature)
    depth = 0
    for idx in range(text.index(") {", start) + 2, len(text)):  # 기본값 ``opts = {}`` 를 건너 몸통 ``{`` 부터
        if text[idx] == "{":
            depth += 1
        elif text[idx] == "}":
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]
    raise AssertionError(f"unbalanced function: {signature}")


_N7_LIST = [
    {"id": 1, "file_type": "image", "filename": "a.jpg", "view_url": _view("orders/9/m/a.jpg"),
     "download_url": "/api/files/download/orders/9/m/a.jpg", "thumbnail_view_url": _view("orders/9/m/thumb_a.jpg"),
     "small_url": _thumb("orders/9/m/a.jpg"), "mid_url": _mid("orders/9/m/a.jpg")},
    {"id": 2, "file_type": "image", "filename": "b.heic", "view_url": _view("orders/9/m/b.heic"),
     "download_url": "/api/files/download/orders/9/m/b.heic", "thumbnail_view_url": _view("orders/9/m/thumb_b.jpg"),
     "small_url": None, "mid_url": None},
]

_N7_BODY = r"""
escapeHtml = __escape;
__els['erp-attachments-category-gallery'] = { innerHTML: '' };
__attachmentsByCategory = { measurement: input };
__activeAttachmentCategory = 'measurement';
renderAttachmentCategoryGallery();
process.stdout.write(JSON.stringify(__els['erp-attachments-category-gallery'].innerHTML));
"""

_N7_SCOPE = r"""
var __attachmentsByCategory = {}; var __activeAttachmentCategory = 'measurement';
function getAttachmentCategoryLabel(c) { return c; }
function esc(s) { return __escape(s); }
function attachmentCanDelete() { return false; }
"""


def _n7_sources(rel: str) -> list[tuple[str, str]]:
    text = _read(rel)
    if rel == "static/js/orders/dashboard/erp-dashboard-core.js":
        return [(rel, text)]  # 맨 윗단 함수 — 파일을 통째로 돌린다
    fn = _function_source(text, "function renderAttachmentCategoryGallery()")
    assert "{{" not in fn and "{%" not in fn  # 템플릿(생산) 안 함수도 Jinja 없이 그대로 JS
    return [("scope.js", _N7_SCOPE), (rel, fn)]


@pytest.mark.parametrize("rel", [
    "static/js/orders/dashboard/erp-dashboard-core.js",
    "static/js/construction/dashboard.js",
    "templates/production/partials/scripts.html",
    "static/js/cs/as-dashboard.js",
])
def test_attachment_modal_cards_640_src_and_viewer_original(rel):
    html = _node(_n7_sources(rel), _N7_BODY, _N7_LIST)
    srcs = re.findall(r'<img src="([^"]+)"', html)
    assert srcs == [_mid("orders/9/m/a.jpg"), _view("orders/9/m/thumb_b.jpg")]  # mid_url 없으면 지금 주소
    # 칸을 누르면 목록 순번으로 뷰어를 연다 — 뷰어는 목록의 view_url(원본)을 읽고 <img src> 를 다시 읽지 않는다.
    clicks = re.findall(r"<img src=\"[^\"]+\"[^>]*?openAttachmentFromCategory\w*\('measurement',\s*(\d)\)", html, re.S)
    assert clicks == ["0", "1"]


@pytest.mark.parametrize("rel,opener", [
    ("static/js/orders/dashboard/erp-dashboard-attachments.js", "function showAttachmentAtIndex(index)"),
    ("static/js/construction/dashboard.js", "function showAttachmentAtIndex(index)"),
    ("templates/production/partials/scripts.html", "function showAttachmentAtIndex(index)"),
    ("static/js/cs/as-dashboard.js", "function showAttachmentAtIndex(index)"),
])
def test_attachment_modal_viewer_opens_list_not_src(rel, opener):
    fn = _function_source(_read(rel), opener)
    assert "__currentAttachmentList" in fn and "mid_url" not in fn and ".src" not in fn
    viewer = _read("static/js/runtime/layout-scripts-core.js")
    assert "const rawViewUrl = f.view_url || f.url || '';" in viewer and "mid_url" not in viewer


# ----------------------------------------------------------------------- 화면: PC 교체 대상 카드(G20)
_GATEWAY_KEYS = [
    "orders/7/drawing/a.png", "orders/7/drawing/A.JPEG", "orders/7/drawing/a.webp",
    "orders/7/drawing/20261120_101010_ab12cd34_png", "orders/7/drawing/x_JPG", "orders/7/drawing/a.pdf",
    "orders/7/drawing/a.svg", "orders/7/drawing/a.heic", "orders/7/drawing/a.b_png",
    "orders/7/drawing/thumb_a.png", "orders/7/drawing/sthumb320_a.png.jpg", "orders/7/drawing/sthumb640_a.png.jpg",
    "orders/7/drawing/noext", "",
]
_GATEWAY = "static/js/orders/dashboard/erp-dashboard-gateway.js"
_ATTACH = "static/js/orders/dashboard/erp-dashboard-attachments.js"


def test_gateway_640_rule_matches_server_and_320_unchanged():
    got = _node([(_GATEWAY, _read(_GATEWAY))],
                "process.stdout.write(JSON.stringify(input.map(function (k) {"
                " return [gatewaySmallUrl(k), gatewaySmallUrl(k, 640)]; })));", _GATEWAY_KEYS)
    expected = [[lt.list_thumb_url(k) or "", lt.mid_thumb_url(k) or ""] for k in _GATEWAY_KEYS]
    assert got == expected
    assert sum(1 for small, _ in expected if small) >= 4 and sum(1 for small, _ in expected if not small) >= 6


def test_replace_target_cards_640_with_original_fallback():
    files = [{"key": "orders/7/drawing/a.png", "filename": "a.png"},
             {"key": "orders/7/drawing/b.heic", "filename": "b.heic"},
             {"key": "orders/7/drawing/c.pdf", "filename": "c.pdf"}]
    html = _node([(_GATEWAY, _read(_GATEWAY)), (_ATTACH, _read(_ATTACH))],
                 "__drawingCurrentFilesByOrder[7] = input;"
                 "process.stdout.write(JSON.stringify(buildDrawingTargetCards(7, 'orders/7/drawing/a.png',"
                 " {role: 'replace', includeNone: true})));", files)
    imgs = re.findall(r"<img [^>]*>", html)
    assert len(imgs) == 2  # PDF 는 그림 칸이 없다
    assert imgs[0].startswith(f'<img src="{_mid("orders/7/drawing/a.png")}" '
                              f'data-full-src="{_view("orders/7/drawing/a.png")}"')
    assert imgs[1].startswith(f'<img src="{_view("orders/7/drawing/b.heic")}"')  # 640 대상 아님 → 원본
    assert all("this.onerror=null" in tag and "this.dataset.fullSrc" in tag for tag in imgs)  # 404 면 원본으로 한 번
    stage = _function_source(_read(_ATTACH), "function buildDrawingTargetCards(")
    assert "gatewaySmallUrl(key, 640)" in stage
    preview = _read(_ATTACH)
    assert 'stage.innerHTML = `<img src="${escapeHtml(viewUrl)}"' in preview  # 큰 무대(미리보기)는 원본 그대로


# ----------------------------------------------------------------------- 핀 · 구문
_PIN = "20261120m"


def test_changed_assets_repinned():
    entry = _read("static/js/orders/erp-dashboard-entry.js")
    for name in ("erp-dashboard-core.js", "erp-dashboard-gateway.js", "erp-dashboard-attachments.js"):
        assert f"{name}?v={_PIN}" in entry, name
    assert f"erp-dashboard-entry.js') }}}}?v={_PIN}" in _read("templates/partials/shared/layout_scripts.html")
    # 뒤 작업이 정당하게 올린다(2026-11-21 시공 완료 창의 남은 시공 한 줄, 20261121b) — "이 작업 핀보다 오래되지 않았다".
    cons_pin = _read("templates/construction/partials/scripts.html").split(
        "js/construction/dashboard.js') }}?v=", 1)[1].split('"', 1)[0]
    assert cons_pin >= _PIN, cons_pin
    assert f"js/cs/as-dashboard.js') }}}}?v={_PIN}" in _read("templates/cs/partials/as_dashboard_body.html")


@pytest.mark.parametrize("rel", [
    "static/js/orders/dashboard/erp-dashboard-core.js", _GATEWAY, _ATTACH,
    "static/js/construction/dashboard.js", "static/js/cs/as-dashboard.js", "static/js/orders/erp-dashboard-entry.js",
])
def test_changed_js_passes_node_check(rel):
    node = shutil.which("node")
    assert node, "node must be on PATH"
    proc = subprocess.run([node, "--check", str(ROOT / rel)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_no_new_db_query_for_mid_urls():
    """주소는 key 에서 계산만 — 화면 함수가 크기 때문에 조회를 더하지 않는다."""
    for rel in ("foms/services/files/list_thumb.py",):
        src = _read(rel)
        assert "db_session" not in src and ".query(" not in src


_PC_TRAPPED_RULES = (".drawing-revision-preview-pane {", ".drawing-revision-preview-pane__stage {",
                     ".drawing-revision-preview-pane__stage img {", ".erp-drawing-gateway-card {",
                     ".erp-drawing-gateway-head {", ".erp-drawing-gateway-actions .btn {", ".erp-drawing-quest-todo {")


def test_replace_target_card_css_applies_on_pc_not_only_under_992():
    """교체 대상 도면 카드 꾸밈은 폭과 상관없이 먹어야 한다(2026-11-20).

    예전엔 ``@media (max-width: 992px)`` 묶음 안에만 있어 PC(993px 이상)에서 카드가 꾸밈 없이 그려지고
    그림이 원본 크기로 나왔다. 규칙이 다시 폭 묶음 안으로 들어가면 빨강.
    """
    from pathlib import Path

    css = (Path(__file__).resolve().parents[2] / "static/css/contexts/orders/dashboard-grid.css").read_text(encoding="utf-8")
    depth, media_stack, found = 0, [], {}
    for line in css.split("\n"):
        text = line.strip()
        if text.startswith("@media") and "{" in text:
            media_stack.append((depth, text))
        for name in (".drawing-target-card {", ".drawing-target-card-thumb {", ".drawing-target-card-thumb img {",
                     ".drawing-target-card-grid {", *_PC_TRAPPED_RULES):
            if text == name:
                found.setdefault(name, []).append([m[1] for m in media_stack])
        depth += line.count("{") - line.count("}")
        while media_stack and depth <= media_stack[-1][0]:
            media_stack.pop()
    for name in (".drawing-target-card {", ".drawing-target-card-thumb {", ".drawing-target-card-thumb img {"):
        assert found.get(name) == [[]], (name, found.get(name))  # 한 번만, 폭 묶음 밖
    # 같은 함정이던 도면 수정 요청 큰 미리보기 · 도면 창구 칸(2026-11-20) — PC 에서 미리보기 원본이 제 크기로 그려져
    # 창 본문이 가로로 1,800px 넘게 넘쳤다.
    for name in _PC_TRAPPED_RULES:
        assert found.get(name) == [[]], (name, found.get(name))
    # 격자는 기본 규칙(묶음 밖) + 768px 이하 두 칸 규칙.
    assert found[".drawing-target-card-grid {"] == [[], ["@media (max-width: 768px) {"]]
