from __future__ import annotations

from pathlib import Path

import foms.api.files.routes as file_routes


ROOT = Path(__file__).resolve().parents[2]


class FakeR2Storage:
    storage_type = "r2"

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def get_download_url(
        self,
        storage_key: str,
        expires_in: int = 3600,
        response_content_disposition: str | None = None,
    ) -> str:
        self.calls.append(
            {
                "storage_key": storage_key,
                "expires_in": expires_in,
                "response_content_disposition": response_content_disposition,
            }
        )
        return f"https://account.r2.cloudflarestorage.com/{storage_key}?X-Amz-Signature=fresh"


def _assert_no_store(resp) -> None:
    cc = resp.headers.get("Cache-Control", "")
    assert "no-store" in cc
    assert "max-age=0" in cc
    assert resp.headers.get("Pragma") == "no-cache"
    assert resp.headers.get("Expires") == "0"


def test_presigned_url_json_is_not_cacheable(auth_client, monkeypatch) -> None:
    storage = FakeR2Storage()
    monkeypatch.setattr(file_routes, "get_storage", lambda: storage)

    resp = auth_client.get("/api/files/presigned-urls/orders/1/photo.png")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["view_url"].startswith("https://account.r2.cloudflarestorage.com/")
    _assert_no_store(resp)


def test_r2_file_redirects_are_not_cacheable(auth_client, monkeypatch) -> None:
    storage = FakeR2Storage()
    monkeypatch.setattr(file_routes, "get_storage", lambda: storage)

    view_resp = auth_client.get("/api/files/view/orders/1/photo.png", follow_redirects=False)
    download_resp = auth_client.get("/api/files/download/orders/1/photo.png", follow_redirects=False)

    assert view_resp.status_code == 302
    assert view_resp.headers["Location"].startswith("https://account.r2.cloudflarestorage.com/")
    _assert_no_store(view_resp)
    assert download_resp.status_code == 302
    assert download_resp.headers["Location"].startswith("https://account.r2.cloudflarestorage.com/")
    _assert_no_store(download_resp)
    assert storage.calls[-1]["response_content_disposition"] == 'attachment; filename="photo.png"'


def test_long_lived_image_viewers_keep_stable_file_routes() -> None:
    layout = (ROOT / "templates/partials/shared/layout_scripts.html").read_text(encoding="utf-8")
    order_shared = (ROOT / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    chat_lightbox = (ROOT / "templates/partials/chat_scripts_lightbox.html").read_text(encoding="utf-8")

    assert "fetch('/api/files/presigned-urls/'" not in layout
    assert "/api/files/presigned-urls/" not in order_shared
    assert "/api/files/presigned-urls/" not in chat_lightbox
    assert "Direct R2 signed URLs expire" in layout
    assert "isSignedStorageUrl(a.view_url)" in order_shared
    assert "stable app routes" in order_shared
    assert "stable app routes" in chat_lightbox


def test_service_worker_bypasses_file_delivery_requests() -> None:
    sw = (ROOT / "static/sw.js").read_text(encoding="utf-8")

    assert "isFileDeliveryRequest(url)" in sw
    assert 'url.pathname.indexOf("/api/files/") === 0' in sw
    assert "cloudflarestorage\\.com" in sw
    assert 'url.searchParams.has("X-Amz-Signature")' in sw
    assert 'url.searchParams.has("Signature")' in sw
