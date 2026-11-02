"""FOMS 공지 사진 화면(설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §8).

- 받는 사람 화면(본사 /notices · 협력사 /partner/notices · 두 공지 창)과 관리자 쓰기 화면에 썸네일 줄 · 사진 창 훅이 있다.
- 사진 창 스크립트(정적 검사): Esc · 바깥 · X 로 닫기, 좌우 넘기기(단추 · 화살표 · 밀기), window 잡기 단계로 공지 창의 초점
  가두기(document 잡기 단계)보다 먼저 받기, 두 공지 창 스크립트가 열린 사진 창을 보고 가두기를 쉼, 층(z-index) 순서.
- 대조군: 사진 없는 공지는 썸네일 줄을 그리지 않고, 다른 협력사 공지 사진 주소는 협력사 화면에 없다.
"""
from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path

from db import db_session
from models import Notice, User
from tests.security.partner_fixtures import _client, world  # noqa: F401 — pytest fixture 재노출

ROOT = Path(__file__).resolve().parents[2]
GALLERY_JS = ROOT / "static/js/foms/foms-notice-gallery.js"
_IMG = {"key": "notices/images/202611/" + "a" * 32 + ".jpg", "thumb_key": "notices/images/202611/" + "a" * 32 + "_thumb.jpg",
        "name": "현장.jpg", "width": 2000, "height": 1500, "size": 1234}


def _notice(title: str, images=None, **kw) -> int:
    row = Notice(title=title, body=f"{title} 본문", created_by_name="라홈 본사", images=images or [], **kw)
    db_session.add(row)
    db_session.commit()
    return row.id


def _page(app, user_id: int, path: str) -> str:
    resp = _client(app, db_session.get(User, user_id)).get(path)
    assert resp.status_code == 200, (path, resp.status_code)
    return resp.get_data(as_text=True)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_staff_list_renders_thumbs_with_gallery_hook(app, world):
    with_photo = _notice("사진 공지", [_IMG, {**_IMG, "key": _IMG["key"].replace("a" * 32, "b" * 32)}], audience_staff_all=True)
    _notice("사진 없는 공지", audience_staff_all=True)
    html = _page(app, world["staff"], "/notices")
    assert html.count('data-images="') == 1  # 대조군: 사진 없는 공지는 줄을 안 그린다(공지 창 빈 줄은 data-images 없음)
    assert html.count("data-foms-notice-thumb ") == 2 and "foms-notice-gallery.js" in html
    raw = re.search(r'data-images="([^"]*)"', html).group(1)
    items = json.loads(unescape(raw))
    assert [i["url"].split("?")[0] for i in items] == [f"/api/notices/{with_photo}/images/0", f"/api/notices/{with_photo}/images/1"]
    assert all(i["thumb_url"].endswith("&thumb=1") for i in items)
    assert _IMG["key"] not in html  # 저장소 key 는 화면에 싣지 않는다


def test_partner_list_and_popup_carry_only_own_company_photos(app, world):
    mine = _notice("가나 사진 공지", [_IMG], audience_partner_org_ids=[world["org_a"]], display_mode="POPUP")
    other = _notice("다라 사진 공지", [_IMG], audience_partner_org_ids=[world["org_b"]], display_mode="POPUP")
    html = _page(app, world["partner_a"], "/partner/notices")
    assert f"/api/notices/{mine}/images/0" in html and f"/api/notices/{other}/images/" not in html
    assert "foms-notice-gallery.js" in html and "data-foms-notice-thumb" in html

    home = _page(app, world["partner_a"], "/partner")
    queue = json.loads(unescape(re.search(r'data-pp-notice-queue="([^"]*)"', home).group(1)))
    assert [(n["id"], n["images"][0]["url"].split("?")[0]) for n in queue] == [(mine, f"/api/notices/{mine}/images/0")]
    assert "data-foms-notice-images" in home and "foms-notice-gallery.js" in home and "foms-notice.css" in home


def test_staff_popup_and_admin_form_have_photo_hooks(app, world):
    popup = _read("templates/partials/shared/notice_popup.html")
    assert "data-foms-notice-images" in popup
    assert popup.index("asset_url('js/foms/foms-notice-gallery.js')") < popup.index("asset_url('js/foms/foms-notice-popup.js')")
    nid = _notice("고칠 공지", [_IMG], audience_staff_all=True)
    page = _page(app, world["admin"], f"/admin/notices/{nid}/edit")
    assert "data-notice-images-field" in page and 'data-upload-url="/api/admin/notices/images"' in page
    assert 'data-max="5"' in page and page.count("data-preview-images") == 2 and "notices-images.js" in page
    state = json.loads(unescape(re.search(r'data-notice="([^"]*)"', page).group(1)))
    assert state["images"][0]["key"] == _IMG["key"]
    assert state["images"][0]["preview_url"].startswith("/api/admin/notices/images/file?key=")
    assert 'accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif"' in page  # HEIC 원본도 받는다(pillow-heif)
    # 공용 photo-capture.js 가 사진 칸마다 capture="environment" 를 붙여 휴대폰에서 카메라만 열렸다 — 갤러리도 고르게 뺀다.
    tag = re.search(r'<input type="file"[^>]*data-images-input[^>]*>', page).group(0)
    assert "data-foms-no-capture" in tag and "capture=" not in tag
    capture_js = _read("static/js/foms/photo-capture.js")
    assert "if (input.hasAttribute('data-foms-no-capture')) return false;" in capture_js
    # 쓰던 글 맡기기는 사진 · 쓰기 스크립트보다 먼저 실려 data-notice 에 겹친다.
    assert page.index("notices-draft.js") < page.index("notices-images.js") < page.index("notices-form.js")


def test_gallery_script_closes_navigates_and_preempts_popup_trap() -> None:
    js = GALLERY_JS.read_text(encoding="utf-8")
    assert len(js.splitlines()) <= 300 and "innerHTML" not in js
    assert "'Escape'" in js and "ArrowLeft" in js and "ArrowRight" in js
    assert "touchstart" in js and "touchend" in js and "data-gallery-close" in js
    assert "window.addEventListener('keydown', onKeyDown, true)" in js
    assert "window.addEventListener('focusin', onFocusIn, true)" in js
    assert "stopPropagation" in js and "back.focus()" in js  # 닫으면 누른 썸네일로 초점
    assert "if (window.FomsNoticeGallery) return;" in js  # 두 번 실려도 한 벌
    assert "/^\\/(?!\\/)/" in js  # 같은 사이트 주소만 넣는다
    staff = _read("static/js/foms/foms-notice-popup.js")
    assert ".foms-notice-gallery:not([hidden])" in staff and "FomsNoticeGallery.render" in staff
    partner = _read("static/js/partner/partner-notice.js")
    assert ".foms-notice-gallery:not([hidden])" in partner and "galleryOpen()" in partner
    assert "FomsNoticeGallery.render" in partner
    images = _read("static/js/admin/notices-images.js")
    assert len(images.splitlines()) <= 300 and "catch" in images and "data.success" in images
    form = _read("static/js/admin/notices-form.js")
    assert "FomsNoticeImages.payload()" in form and "FomsNoticeImages.busy()" in form


def test_gallery_layer_sits_above_popup_below_drawing_and_urgent() -> None:
    def z(rel: str, selector: str) -> int:
        css = _read(rel)
        block = css[css.index(selector + " {"):]
        return int(re.search(r"z-index:\s*(\d+)", block[:block.index("}")]).group(1))

    popup = z("static/css/components/foms-notice.css", ".foms-notice-popup")
    gallery = z("static/css/components/foms-notice.css", ".foms-notice-gallery")
    drawing = z("static/css/components/foms-drawing-alert.css", ".foms-drawing-alert")
    urgent = z("static/css/components/foms-urgent-alert.css", ".foms-urgent-alert")
    partner = z("static/css/contexts/partner/partner-portal.css", ".pp-notice")
    assert max(popup, partner) < gallery < drawing < urgent
    css = _read("static/css/components/foms-notice.css")
    backdrop = css[css.index(".foms-notice-gallery__backdrop {"):]
    assert "backdrop-filter: blur(" in backdrop[:backdrop.index("}")]


def test_photo_templates_have_no_inline_style() -> None:
    for rel in ("templates/notices/_items.html", "templates/partials/shared/notice_popup.html",
                "templates/partner/partials/notice_modal.html", "templates/admin/notices/form.html"):
        text = _read(rel)
        assert 'style="' not in text and "<style" not in text, rel


def test_draft_survives_trip_to_photo_app() -> None:
    """휴대폰이 갤러리 · 카메라에 다녀오는 사이 화면을 다시 읽어도 제목 · 내용 · 받는 쪽 · 사진이 남는다."""
    draft = _read("static/js/admin/notices-draft.js")
    assert len(draft.splitlines()) <= 300 and "innerHTML" not in draft and "style=" not in draft
    assert "window.sessionStorage.setItem(key" in draft and "TTL_MS = 30 * 60 * 1000" in draft
    assert "'visibilitychange'" in draft and "'pagehide'" in draft
    assert "root.setAttribute('data-notice', JSON.stringify(merged))" in draft and "draft: true" in draft
    assert "FomsNoticeForm.snapshot()" in draft and "FomsNoticeImages.items()" in draft
    assert "closest('a[href]')" in draft  # [공지 목록]으로 일부러 떠나면 버린다
    form = _read("static/js/admin/notices-form.js")
    assert "current.id || current.draft" in form and "window.FomsNoticeForm = { snapshot: payload };" in form
    assert form.index("FomsNoticeDraft.clear()") < form.index("window.location.href = pageBase")
    images = _read("static/js/admin/notices-images.js")
    assert "items: function () { return saved().slice(); }" in images
