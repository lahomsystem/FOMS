from foms.services.channel_wam_view_models import (
    AttachmentGroupVM,
    AttachmentItemVM,
    WamActionVM,
    WamPageVM,
    WamRequestContext,
    WamSectionVM,
    WamStickyActionBarVM,
    vm_to_dict,
)


def test_wam_request_context_permissions_and_public_dict() -> None:
    context = WamRequestContext(
        manager_id="mgr-1",
        order_id=100,
        scopes=("page", "attachments"),
        allowed_sections=("summary",),
        attachment_scope="order",
        issued_at=123.4,
    )

    assert context.allows("page") is True
    assert context.allows("payment") is False
    assert context.allows_section("summary") is True
    assert context.allows_section("timeline") is False
    assert context.allows_attachment_order(100) is True
    assert context.allows_attachment_order(101) is False
    assert context.to_public_dict() == {
        "manager_id": "mgr-1",
        "order_id": 100,
        "issued_at": 123.4,
        "token_type": "wam_launch",
        "scopes": ["page", "attachments"],
        "source": "launch_token",
        "allowed_sections": ["summary"],
        "attachment_scope": "order",
    }


def test_wam_request_context_empty_scopes_allow_everything() -> None:
    context = WamRequestContext(
        manager_id=None,
        order_id=100,
        scopes=(),
        allowed_sections=(),
        attachment_scope="all",
    )

    assert context.allows("page") is True
    assert context.allows("attachments") is True
    assert context.allows_section("timeline") is True
    assert context.allows_attachment_order(999) is True


def test_vm_to_dict_serializes_nested_dataclasses() -> None:
    item = AttachmentItemVM(
        id=1,
        name="도면.png",
        file_type="image",
        category="drawing",
        category_label="Drawing",
        item_index=0,
        created_at_label="2026-04-08 10:00",
        size_label="1.0 MB",
        open_url="/open/1",
        download_url="/download/1",
        thumbnail_url="/thumb/1",
    )
    group = AttachmentGroupVM(
        key="drawing:item-0",
        title="Drawing / Item 1",
        count=1,
        preview_items=[item],
        items=[item],
    )
    section = WamSectionVM(
        key="attachments",
        title="첨부",
        payload={"groups": [group]},
    )
    page = WamPageVM(
        page_state="ready",
        order_id=100,
        header={"title": "주문"},
        summary_strip={"title": "요약"},
        sections=[section],
        sticky_action_bar=WamStickyActionBarVM(
            state="visible",
            primary_action=WamActionVM(key="open", label="열기"),
        ),
    )

    serialized = vm_to_dict(page)

    assert serialized["page_state"] == "ready"
    assert serialized["sections"][0]["payload"]["groups"][0]["items"][0]["name"] == "도면.png"
    assert serialized["sticky_action_bar"]["primary_action"]["key"] == "open"
    assert page.to_dict() == serialized


def test_wam_page_vm_get_section_returns_matching_section() -> None:
    summary = WamSectionVM(key="summary", title="요약")
    timeline = WamSectionVM(key="timeline", title="타임라인")
    page = WamPageVM(
        page_state="ready",
        order_id=100,
        header={"title": "주문"},
        summary_strip={"title": "요약"},
        sections=[summary, timeline],
        sticky_action_bar=None,
    )

    assert page.get_section("timeline") is timeline
    assert page.get_section("attachments") is None
