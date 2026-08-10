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


def test_as_attachment_modal_offers_as_channel_push() -> None:
    """AS 첨부 모달에서 AS PUSH 전송 — 본문은 서버 조립이라 text 를 보내지 않는다."""
    root = Path(__file__).resolve().parents[2]
    template = (root / "templates/cs/partials/as_dashboard_body.html").read_text(encoding="utf-8")
    js = (root / "static/js/cs/as-dashboard.js").read_text(encoding="utf-8")

    assert 'id="as-modal-channel-push-btn"' in template

    start = js.index("var asChannelPushBtn = document.getElementById('as-modal-channel-push-btn');")
    block = js[start:start + 2200]
    assert "'/api/channel/push-manual'" in block
    assert "push_kind: 'as'" in block
    # 본문은 서버 SSOT — 이 화면은 주문 폼이 없어 text 를 만들 수 없다.
    assert "text:" not in block
    # 재전송이면 서버가 변경 내용을 요구한다 → prompt 후 1회 재시도.
    assert "재전송 시 변경 내용" in block
    assert "change_note" in block
