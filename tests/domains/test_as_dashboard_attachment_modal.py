from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_as_attachment_modal_exposes_delete_action() -> None:
    """AS 첨부 모달은 기존 DELETE API로 파일 삭제 액션을 제공한다."""
    root = _root()
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
    root = _root()
    template = (root / "templates/cs/partials/as_dashboard_body.html").read_text(encoding="utf-8")
    js = (root / "static/js/cs/as-dashboard.js").read_text(encoding="utf-8")
    confirm_js = (root / "static/js/cs/as-push-confirm.js").read_text(encoding="utf-8")

    assert 'id="as-modal-channel-push-btn"' in template

    start = js.index("var asChannelPushBtn = document.getElementById('as-modal-channel-push-btn');")
    block = js[start:start + 1600]
    assert "fomsConfirmAndSendAsPush" in block
    assert "'/api/channel/push-manual'" not in block

    post_start = confirm_js.index("async function postPush")
    post_block = confirm_js[post_start:post_start + 700]
    assert "'/api/channel/push-manual'" in post_block
    assert "push_kind: 'as'" in post_block
    # 본문은 서버 SSOT — 확인창도 text 를 만들지 않는다.
    assert "text:" not in post_block
    # 재전송이면 서버가 변경 내용을 요구한다 → prompt 후 1회 재시도.
    assert "재전송 시 변경 내용" in confirm_js
    assert "change_note" in confirm_js
    assert "채널톡 메시지 상단에 [수정]으로 표시됩니다." in confirm_js


def test_as_push_confirm_modal_previews_body_and_files() -> None:
    """AS-FRESH-01 T7 / AS-BIND-01: 전송 전 확인창이 나갈 본문·파일을 보여주고 선택을 서버로 넘긴다.

    기본 선택은 서버(select_as_push_attachments)가 정한 ``selected`` 를 그대로 쓴다 —
    클라가 따로 판정하면 미리보기와 실제 전송이 갈린다.
    """
    root = _root()
    dashboard = (root / "templates/cs/partials/as_dashboard_body.html").read_text(encoding="utf-8")
    erp_js = (root / "templates/orders/partials/erp_order_js.html").read_text(encoding="utf-8")
    modal = (root / "templates/cs/partials/as_push_confirm_modal.html").read_text(encoding="utf-8")
    confirm_js = (root / "static/js/cs/as-push-confirm.js").read_text(encoding="utf-8")

    assert "{% include 'cs/partials/as_push_confirm_modal.html' %}" in dashboard
    assert '{% include "cs/partials/as_push_confirm_modal.html" %}' in erp_js

    for anchor in (
        'id="asPushConfirmModal"',
        'id="as-push-confirm-text"',
        'id="as-push-confirm-files"',
        'id="as-push-confirm-send"',
    ):
        assert anchor in modal

    assert "'/api/channel/push-preview?order_id='" in confirm_js
    assert "attachment_ids: attachmentIds" in confirm_js
    assert "f.selected ? ' checked' : ''" in confirm_js or "file.selected ? ' checked' : ''" in confirm_js
    assert "as-push-confirm-selected" in confirm_js
    assert "as-push-confirm__nudge" in confirm_js
    # 인라인 스타일 금지 — 확인창 스킨은 컴포넌트 CSS 소유(대시보드 컨텍스트에도 동일 규칙).
    assert "as-push-confirm__file" in confirm_js
    assert ".as-push-confirm__file" in (
        root / "static/css/components/foms-as-attachment-order.css"
    ).read_text(encoding="utf-8")
    assert "window.__AS_PUSH_CONFIRM_BOUND" in confirm_js
    assert "js/cs/as-push-confirm.js" in dashboard
    assert "js/cs/as-push-confirm.js" in erp_js


def test_as_paperclip_upload_binds_anchor_before_batch() -> None:
    """대시보드 종이클립 'AS 사진 추가'도 차트에 보이도록 앵커에 결합한다."""
    js = (_root() / "static/js/cs/as-dashboard.js").read_text(encoding="utf-8")
    start = js.index("var asUploadInput = document.getElementById('as-modal-upload-input');")
    block = js[start:start + 5000]
    assert "fomsEnsureAsUploadAnchor" in block
    assert "asLogId: anchor.asLogId" in block
    ensure_idx = block.index("fomsEnsureAsUploadAnchor")
    optimistic_idx = block.index("Optimistic UI Start")
    assert ensure_idx < optimistic_idx
