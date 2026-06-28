from pathlib import Path


def test_as_attachment_modal_exposes_delete_action() -> None:
    """AS 첨부 모달은 기존 DELETE API로 파일 삭제 액션을 제공한다."""
    root = Path(__file__).resolve().parents[2]
    # Batch 5: inline JS가 static/js/cs/as-dashboard.js로 이동 → 표면(템플릿+모듈) 합본 검사
    text = (
        (root / "templates/cs/partials/as_dashboard_body.html").read_text(encoding="utf-8")
        + "\n"
        + (root / "static/js/cs/as-dashboard.js").read_text(encoding="utf-8")
    )

    assert "window.deleteAttachmentFromCategoryAs = deleteAttachmentFromCategory;" in text
    assert "async function deleteAttachmentFromCategory(category, index, attachmentId)" in text
    assert "method: 'DELETE'" in text
    assert "'/api/orders/' + encodeURIComponent(orderId) + '/attachments/' + encodeURIComponent(id)" in text
    assert 'title="삭제"' in text
    assert "fa-trash" in text
    assert "await refreshAsModalAttachments();" in text
