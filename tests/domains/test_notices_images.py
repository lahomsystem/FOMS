"""FOMS 공지 사진(설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §8) — 받기 · 페이로드 · 업로드 API · 사진 주소 권한.

저장소는 가짜(:class:`FakeStore`)로 바꾼다 — 실서버 · R2 를 부르지 않는다.
권한 대조군: 받는 본사 직원 · 받는 협력사 · 관리자는 열고, 받지 않는 본사 직원 · 다른 협력사는 404(있는지도 알리지 않는다).
관리자는 지운 · 예약 공지 사진도 연다. 페이로드는 업로드 API 가 만든 ``notices/images/...`` key 만 받는다.
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta

import pytest
from PIL import Image

import foms.services.notices.images as images_mod
from db import db_session
from foms.services.notices.images import KEY_RE, MAX_BYTES, NoticeImageError, redraw, store_image, thumb_key_for
from foms.services.notices.payload import NoticeInputError, clean_images
from foms.services.notices.service import notice_summary, visible_notices
from models import Notice, SecurityLog, User
from tests.security.partner_fixtures import _client, world  # noqa: F401 — pytest fixture 재노출


class FakeStore:
    """R2 흉내 — 올린 바이트를 dict 에 담고 서명 주소는 가짜 주소."""

    storage_type = "r2"

    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, str]] = {}
        self.signed: list[tuple[str, int]] = []

    def put_private_bytes(self, key: str, data: bytes, content_type: str) -> bool:
        self.files[key] = (data, content_type)
        return True

    def get_download_url(self, key: str, expires_in: int = 3600, **_kw) -> str:
        self.signed.append((key, expires_in))
        return f"https://r2.example.test/{key}?sig=1"

    def read_file_bytes(self, key: str):
        return self.files.get(key, (None, ""))[0]

    def delete_file(self, key: str) -> bool:
        self.files.pop(key, None)
        return True


@pytest.fixture
def store(monkeypatch):
    fake = FakeStore()
    monkeypatch.setattr(images_mod, "get_storage", lambda: fake)
    return fake


def _jpeg(size=(3000, 1500), color=(200, 30, 30)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format="JPEG", quality=90)
    return out.getvalue()


def _png_alpha(size=(400, 300)) -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", size, (0, 120, 200, 128)).save(out, format="PNG")
    return out.getvalue()


def _entry(store_obj) -> dict:
    return store_image(_jpeg(), "현장 사진.jpg", store=store_obj)


# ---- 받기 · 다시 그리기 ----------------------------------------------------------------------
def test_redraw_shrinks_long_edge_and_makes_thumb():
    drawn = redraw(_jpeg(), "a.jpg")
    assert drawn["ext"] == "jpg" and drawn["content_type"] == "image/jpeg"
    assert max(drawn["width"], drawn["height"]) == 2000 and drawn["width"] == 2000
    with Image.open(io.BytesIO(drawn["thumb"])) as thumb:
        assert max(thumb.size) == 480


def test_redraw_keeps_transparency_as_png():
    drawn = redraw(_png_alpha(), "logo.png")
    assert drawn["ext"] == "png" and (drawn["width"], drawn["height"]) == (400, 300)


@pytest.mark.parametrize("data, name, needle", [
    (b"", "a.jpg", "비어"),
    (b"%PDF-1.4 not an image", "a.jpg", "JPG"),
    (b"\x00\x00\x00\x18ftypheic" + b"0" * 64, "IMG_0001.HEIC", "HEIC"),
], ids=["empty", "pdf", "broken_heic"])
def test_redraw_rejects_bad_files(data, name, needle):
    with pytest.raises(NoticeImageError) as err:
        redraw(data, name)
    assert needle in str(err.value)


def _heic(size=(3000, 2000), color=(91, 103, 216)) -> bytes:
    import pillow_heif

    out = io.BytesIO()
    pillow_heif.from_pillow(Image.new("RGB", size, color)).save(out, quality=60)
    return out.getvalue()


def test_redraw_accepts_iphone_heic_as_jpeg():
    """아이폰 원본 HEIC 도 받아 JPEG 로 다시 그린다(사용자 요청 2026-11-02)."""
    drawn = redraw(_heic(), "IMG_0001.HEIC")
    assert drawn["ext"] == "jpg" and drawn["content_type"] == "image/jpeg"
    assert (drawn["width"], drawn["height"]) == (2000, 1333)
    with Image.open(io.BytesIO(drawn["main"])) as main:
        assert main.format == "JPEG"
    with Image.open(io.BytesIO(drawn["thumb"])) as thumb:
        assert max(thumb.size) == 480


def test_heic_support_stays_inside_notices():
    """공지 사진만 HEIC 를 연다 — Pillow 전체 등록을 하지 않아 다른 업로드의 받는 형식 규칙은 그대로다."""
    from PIL import UnidentifiedImageError

    with pytest.raises(UnidentifiedImageError):
        Image.open(io.BytesIO(_heic((64, 48))))


def test_redraw_rejects_over_15mb():
    with pytest.raises(NoticeImageError) as err:
        redraw(b"0" * (MAX_BYTES + 1), "big.jpg")
    assert "15MB" in str(err.value)


def test_store_image_puts_main_and_thumb_privately(store):
    entry = _entry(store)
    assert KEY_RE.fullmatch(entry["key"]) and entry["thumb_key"] == thumb_key_for(entry["key"])
    assert set(store.files) == {entry["key"], entry["thumb_key"]}
    assert entry["name"] == "현장 사진.jpg" and entry["width"] == 2000 and entry["size"] > 0
    assert "현장" not in entry["key"]  # 파일 이름을 key 에 넣지 않는다


# ---- 페이로드 ----------------------------------------------------------------------------
def _good(n: int = 1) -> list[dict]:
    return [{"key": f"notices/images/202611/{i:032x}.jpg", "name": f"{i}.jpg", "width": 10, "height": 5, "size": 9}
            for i in range(n)]


def test_clean_images_rebuilds_thumb_key_and_keeps_order():
    out = clean_images(list(reversed(_good(3))))
    assert [o["key"][-6:] for o in out] == ["02.jpg", "01.jpg", "00.jpg"]
    assert all(o["thumb_key"] == thumb_key_for(o["key"]) for o in out)


@pytest.mark.parametrize("raw", [
    [{"key": "orders/12/secret.pdf"}],  # 남의 파일 key
    [{"key": "notices/images/202611/../../orders/1/a.jpg"}],
    [{"key": "notices/images/202611/" + "a" * 32 + ".jpg", "thumb_key": "orders/12/thumb_x.jpg"}],
    [{"key": "notices/images/202611/" + "a" * 32 + ".gif"}],
    "notices/images/x.jpg",
    _good(2) + _good(1),  # 같은 사진 두 번
    _good(6),  # 5장 넘음
])
def test_clean_images_rejects_foreign_keys_and_too_many(raw):
    with pytest.raises(NoticeInputError):
        clean_images(raw)


# ---- 업로드 API ---------------------------------------------------------------------------
def _upload(client, data: bytes, name: str = "a.jpg"):
    return client.post("/api/admin/notices/images", data={"image": (io.BytesIO(data), name)},
                       content_type="multipart/form-data")


@pytest.mark.parametrize("who", ["staff", "sales", "partner_a"])
def test_upload_forbidden_for_non_admin(app, world, store, who):
    resp = _upload(_client(app, db_session.get(User, world[who])), _jpeg())
    assert resp.status_code == 403 and store.files == {}
    assert _upload(_client(app, None), _jpeg()).status_code == 401


def test_upload_returns_entry_and_admin_preview(app, world, store):
    admin = _client(app, db_session.get(User, world["admin"]))
    resp = _upload(admin, _jpeg(), "현장.jpg")
    assert resp.status_code == 201, resp.get_json()
    data = resp.get_json()["data"]
    assert KEY_RE.fullmatch(data["key"]) and data["name"] == "현장.jpg"
    audit = db_session.query(SecurityLog).filter(SecurityLog.action == "NOTICE_IMAGE_UPLOADED").one()
    assert audit.detail["key"] == data["key"] and audit.user_id == world["admin"]
    assert data["preview_url"].startswith("/api/admin/notices/images/file?key=")
    view = admin.get(data["thumb_url"])
    assert view.status_code == 302 and view.headers["Location"].endswith(f"{data['thumb_key']}?sig=1")
    assert "no-store" in view.headers["Cache-Control"]
    # 관리자 보기도 공지 사진 key 꼴만 연다(다른 저장소 파일 금지) · 관리자 아니면 403.
    assert admin.get("/api/admin/notices/images/file?key=orders/1/a.jpg").status_code == 404
    staff = _client(app, db_session.get(User, world["staff"]))
    assert staff.get(data["preview_url"]).status_code == 403


@pytest.mark.parametrize("data, name", [(b"%PDF-1.4", "a.pdf"), (b"0" * (MAX_BYTES + 1), "big.jpg"), (b"", "a.jpg")],
                         ids=["pdf", "over-15mb", "empty"])
def test_upload_rejects_bad_format_and_size(app, world, store, data, name):
    resp = _upload(_client(app, db_session.get(User, world["admin"])), data, name)
    assert resp.status_code in (400, 413) and store.files == {}


def test_upload_body_cap_allows_15mb_photo():
    from foms.platform.request_limits import resolve_body_cap

    cap = resolve_body_cap("/api/admin/notices/images")
    assert cap is not None and cap.category == "notice_image" and cap.max_body_bytes > MAX_BYTES


# ---- 공지에 붙이기 · 사진 주소 권한 ---------------------------------------------------------
def _payload(images: list, **audience) -> dict:
    return {"title": "사진 공지", "body": "본문", "audience": audience, "display_mode": "POPUP", "pinned": False,
            "starts_at": "", "ends_at": "", "images": images}


def _create(app, world, images, **audience) -> int:
    admin = _client(app, db_session.get(User, world["admin"]))
    resp = admin.post("/api/admin/notices", json=_payload(images, **audience))
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["data"]["id"]


def test_create_rejects_foreign_key(app, world, store):
    admin = _client(app, db_session.get(User, world["admin"]))
    resp = admin.post("/api/admin/notices", json=_payload([{"key": "orders/7/drawing/final.pdf"}], staff_all=True))
    assert resp.status_code == 400 and db_session.query(Notice).count() == 0


def test_recipient_image_access(app, world, store):
    one, two = _entry(store), _entry(store)
    nid = _create(app, world, [one, two], staff_teams=["CS"], partner_org_ids=[world["org_a"]])
    url = f"/api/notices/{nid}/images"
    for who in ("staff", "partner_a", "admin"):  # 받는 본사 직원(CS) · 받는 협력사 · 관리자
        client = _client(app, db_session.get(User, world[who]))
        full = client.get(f"{url}/1")
        assert full.status_code == 302 and full.headers["Location"].endswith(f"{two['key']}?sig=1"), who
        thumb = client.get(f"{url}/0?thumb=1")
        assert thumb.status_code == 302 and one["thumb_key"] in thumb.headers["Location"], who
    for who in ("sales", "partner_b"):  # 받지 않는 본사 직원(영업) · 다른 협력사
        client = _client(app, db_session.get(User, world[who]))
        assert client.get(f"{url}/0").status_code == 404, who
        assert client.get(f"{url}/0?thumb=1").status_code == 404, who
    staff = _client(app, db_session.get(User, world["staff"]))
    assert staff.get(f"{url}/2").status_code == 404  # 없는 차례
    assert _client(app, None).get(f"{url}/0").status_code == 401


def test_admin_sees_deleted_and_scheduled_notice_images(app, world, store):
    nid = _create(app, world, [_entry(store)], staff_all=True)
    notice = db_session.get(Notice, nid)
    notice.starts_at = datetime.utcnow() + timedelta(days=3)
    db_session.commit()
    staff = _client(app, db_session.get(User, world["staff"]))
    admin = _client(app, db_session.get(User, world["admin"]))
    assert staff.get(f"/api/notices/{nid}/images/0").status_code == 404  # 예약 — 아직 게시 전
    assert admin.get(f"/api/notices/{nid}/images/0").status_code == 302
    assert admin.delete(f"/api/admin/notices/{nid}").status_code == 200
    assert admin.get(f"/api/notices/{nid}/images/0?thumb=1").status_code == 302


def test_update_reorders_removes_and_keeps_images_when_field_missing(app, world, store):
    one, two = _entry(store), _entry(store)
    nid = _create(app, world, [one, two], staff_all=True)
    admin = _client(app, db_session.get(User, world["admin"]))
    detail = admin.get(f"/api/admin/notices/{nid}").get_json()["data"]
    assert [i["key"] for i in detail["images"]] == [one["key"], two["key"]]
    assert detail["images"][0]["thumb_url"].startswith("/api/admin/notices/images/file?key=")

    resp = admin.put(f"/api/admin/notices/{nid}", json=_payload([two], staff_all=True))
    assert resp.status_code == 200
    db_session.expire_all()
    assert [i["key"] for i in db_session.get(Notice, nid).images] == [two["key"]]
    payload = _payload([], staff_all=True)
    payload.pop("images")
    payload["title"] = "제목만 고침"
    assert admin.put(f"/api/admin/notices/{nid}", json=payload).status_code == 200
    db_session.expire_all()
    assert [i["key"] for i in db_session.get(Notice, nid).images] == [two["key"]]  # 칸이 없으면 그대로
    logs = db_session.query(SecurityLog).filter(SecurityLog.action == "NOTICE_UPDATED").order_by(SecurityLog.id).all()
    assert "images" in logs[0].detail["changed"] and "images" not in logs[1].detail["changed"]


def test_popup_summary_and_list_carry_image_urls_only(app, world, store):
    entry = _entry(store)
    nid = _create(app, world, [entry], partner_all=True, staff_all=True)
    for who in ("staff", "partner_a"):
        user = db_session.get(User, world[who])
        pending = notice_summary(db_session, user)["pending"]
        assert [p["id"] for p in pending] == [nid]
        image = pending[0]["images"][0]
        assert image["url"].startswith(f"/api/notices/{nid}/images/0?v=") and image["thumb_url"].endswith("&thumb=1")
        assert entry["key"] not in str(pending)  # 저장소 key 는 싣지 않는다
        assert visible_notices(db_session, user)[0]["images"] == pending[0]["images"]


def test_partner_gate_allows_notice_image(app, world, store):
    from foms.services.auth.partner_scope import PARTNER_ALLOWED_ENDPOINTS

    assert "notices_api.notice_image" in PARTNER_ALLOWED_ENDPOINTS
    assert "notices_admin_api.upload_image" not in PARTNER_ALLOWED_ENDPOINTS


def test_upload_passes_policy_engine_for_admin_only(app, world, store):
    """운영처럼 쓰기 정책 엔진(MANAGER_MUTATION)을 켜도 관리자 업로드는 지나가고 직원은 막힌다."""
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = True
    try:
        ok = _upload(_client(app, db_session.get(User, world["admin"])), _jpeg((800, 600)))
        assert ok.status_code == 201, ok.get_json()
        denied = _upload(_client(app, db_session.get(User, world["staff"])), _jpeg((800, 600)))
        assert denied.status_code == 403
    finally:
        if prev is sentinel:
            app.config.pop("AUTH_POLICY_ENABLED", None)
        else:
            app.config["AUTH_POLICY_ENABLED"] = prev
