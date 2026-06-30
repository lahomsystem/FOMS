from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


UPLOAD_SURFACES = [
    ROOT / "static/js/orders/erp-order-shared.js",
    ROOT / "static/js/cs/as-dashboard.js",
    ROOT / "templates/construction/partials/scripts.html",
    ROOT / "templates/drawing/partials/workbench_detail_body.html",
    ROOT / "static/js/orders/dashboard/erp-dashboard-drawing.js",
    ROOT / "templates/orders/partials/dashboard_scripts_drawing.html",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_mobile_safe_upload_surfaces_do_not_use_legacy_filename_session_mapping() -> None:
    """Migrated upload surfaces must not map presigned sessions by filename."""
    for path in UPLOAD_SURFACES:
        text = _read(path)
        assert "sessionMap[file.name]" not in text, path
        assert "sessionMap[f.name]" not in text, path
        assert "sessionMap[s.filename]" not in text, path


def test_mobile_safe_upload_surfaces_do_not_use_legacy_ten_way_upload_batches() -> None:
    """File upload paths must use bounded runtime queue policy, not hard-coded 10-way batches."""
    for path in UPLOAD_SURFACES:
        text = _read(path)
        assert "CONCURRENCY = 10" not in text, path
        assert "Promise.all(uploadPromises)" not in text, path
        assert "uploadPromises = fileList.map" not in text, path
        assert "Promise.all(fileList.map" not in text, path
        assert "Promise.all(chunk.map(f => uploadOne" not in text, path


def test_shared_upload_runtime_exposes_mobile_safe_helpers() -> None:
    text = _read(ROOT / "static/js/runtime/upload-progress.js")
    for token in (
        "window.fomsGetUploadQueuePolicy",
        "window.fomsPrepareUploadFiles",
        "window.fomsRunLimitedQueue",
        "window.fomsRequestUploadSessions",
        "window.fomsUploadOrderAttachmentsBatch",
        "image/jpeg",
        "image/png",
        "image/webp",
        "blob.type !== mimeType",
        "bitmap.close()",
    ):
        assert token in text


def test_batch_session_payloads_use_client_ids_after_prepare() -> None:
    for path in UPLOAD_SURFACES:
        text = _read(path)
        if "/api/upload/session/batch" not in text:
            continue
        assert "client_id" in text, path
        assert "entry.clientId" in text or "clientId" in text, path
