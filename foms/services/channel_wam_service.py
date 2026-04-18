"""WAM page/bootstrap orchestration helpers for the Channel API."""

from __future__ import annotations

import os
from typing import Any

from flask import url_for

from foms.services.channel_wam_attachments import list_attachment_groups
from foms.services.channel_wam_read_model import load_wam_order_read_model
from foms.services.channel_wam_view_models import (
    WamActionVM,
    WamPageVM,
    WamRequestContext,
    WamSectionVM,
)
from foms.services.channel_quick_actions import get_order_attachments_for_wam, get_order_summary_for_wam

__all__ = [
    "get_wam_feature_flags",
    "build_wam_request_context",
    "build_wam_page",
    "build_wam_bootstrap",
    "build_legacy_wam_context",
    "build_legacy_summary",
    "build_legacy_attachments",
]


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def get_wam_feature_flags() -> dict[str, bool]:
    """Return the WAM feature-flag snapshot derived from environment variables."""
    wam_enabled = _env_flag("CHANNEL_WAM_ENABLED", True)
    wam_v2_enabled = _env_flag("CHANNEL_WAM_V2_ENABLED", True)
    attachments_enabled = _env_flag("CHANNEL_WAM_ATTACHMENTS_ENABLED", True)
    attachments_lazy_enabled = _env_flag("CHANNEL_WAM_ATTACHMENTS_LAZY_ENABLED", True)
    timeline_enabled = _env_flag("CHANNEL_WAM_TIMELINE_ENABLED", False)
    telemetry_enabled = _env_flag("CHANNEL_WAM_TELEMETRY_ENABLED", False)
    payment_enabled = _env_flag("CHANNEL_WAM_PAYMENT_ENABLED", False)

    return {
        "wam_enabled": wam_enabled,
        "wam_v2_enabled": wam_v2_enabled,
        "attachments_enabled": attachments_enabled,
        "attachments_lazy_enabled": attachments_lazy_enabled,
        "timeline_enabled": timeline_enabled,
        "telemetry_enabled": telemetry_enabled,
        "payment_enabled": payment_enabled,
        "wam_v2": wam_v2_enabled,
        "attachments": attachments_enabled,
        "attachments_lazy": attachments_lazy_enabled,
        "timeline": timeline_enabled,
        "telemetry": telemetry_enabled,
    }


def build_wam_request_context(payload: dict[str, Any], request_token: str) -> WamRequestContext | None:
    """Build a WAM request context from verified token payload data."""
    if not isinstance(payload, dict):
        return None

    order_id = payload.get("order_id")
    if order_id in (None, ""):
        return None

    scopes = payload.get("scopes") or ["page", "attachments"]
    if isinstance(scopes, str):
        scopes = [scopes]
    allowed_sections = payload.get("allowed_sections") or []
    if isinstance(allowed_sections, str):
        allowed_sections = [allowed_sections]

    return WamRequestContext(
        manager_id=payload.get("manager_id"),
        order_id=int(order_id),
        request_token=request_token,
        issued_at=payload.get("iat"),
        token_type=str(payload.get("token_type") or "wam_launch"),
        scopes=tuple(str(scope) for scope in scopes if scope),
        source=str(payload.get("source") or "launch_token"),
        mapped_foms_user_id=payload.get("mapped_foms_user_id"),
        allowed_sections=tuple(str(section) for section in allowed_sections if section),
        attachment_scope=str(payload.get("attachment_scope") or ("order" if "attachments" in scopes else "none")),
        nonce=str(payload.get("nonce")) if payload.get("nonce") else None,
    )


def _api_url(endpoint: str, **kwargs: Any) -> str:
    return url_for(endpoint, **kwargs)


def _row(
    label: str,
    value: str,
    *,
    tone: str = "default",
    href: str | None = None,
    href_label: str | None = None,
    copy_value: str | None = None,
    external: bool = False,
    muted: bool = False,
) -> dict[str, Any]:
    return {
        "label": label,
        "value": value,
        "tone": tone,
        "href": href,
        "href_label": href_label,
        "copy_value": copy_value,
        "external": external,
        "muted": muted,
    }


def _combine_date_time(date_value: Any, time_value: Any) -> str:
    def _normalize(value: Any) -> str:
        if value in (None, ""):
            return "-"
        return str(value)

    date_text = _normalize(date_value)
    time_text = _normalize(time_value)

    if date_text == "-" and time_text == "-":
        return "-"
    if date_text == "-":
        return time_text
    if time_text == "-":
        return date_text
    return f"{date_text} / {time_text}"


def _build_header(read_model, actions: list[WamActionVM]) -> dict[str, Any]:
    badges = [{"label": "읽기 전용", "tone": "neutral"}]
    if read_model.owner_team not in (None, "", "-"):
        badges.append({"label": read_model.owner_team, "tone": "info"})
    if read_model.urgent:
        badges.append({"label": "긴급", "tone": "danger"})

    return {
        "order_label": f"주문 #{read_model.order_id}",
        "status_label": read_model.status_label,
        "status_tone": "danger" if read_model.urgent else "info",
        "customer_name": read_model.customer_name,
        "badges": badges,
        "actions": actions,
    }


def _build_summary_strip(read_model) -> dict[str, Any]:
    return {
        "title": "핵심 요약",
        "items": [
            {
                "key": "measurement_date",
                "label": "실측일",
                "value": read_model.measurement_date,
            },
            {
                "key": "construction_date",
                "label": "시공일",
                "value": read_model.construction_date,
            },
            {
                "key": "address",
                "label": "주소",
                "value": read_model.address,
                "copy_value": read_model.address if read_model.address != "-" else None,
            },
            {
                "key": "product",
                "label": "제품",
                "value": read_model.product,
            },
        ],
    }


def _serialize_attachment_groups(context: WamRequestContext, enabled: bool) -> tuple[list[dict[str, Any]], int]:
    if not enabled:
        return [], 0

    payload_groups: list[dict[str, Any]] = []
    total_count = 0

    for group in list_attachment_groups(context):
        group_dict = group.to_dict()
        preview = [
            {
                "id": item["id"],
                "label": item["name"],
                "name": item["name"],
                "kind_label": "IMAGE" if item["file_type"] == "image" else "FILE",
                "file_type": item["file_type"],
                "category": item["category"],
                "open_url": item["open_url"],
                "download_url": item["download_url"],
                "thumbnail_url": item.get("thumbnail_url"),
                "size_label": item.get("size_label"),
                "created_at_label": item.get("created_at_label"),
            }
            for item in group_dict.get("preview_items") or []
        ]
        items = [
            {
                "id": item["id"],
                "label": item["name"],
                "name": item["name"],
                "url": item["open_url"],
                "file_type": item["file_type"],
                "category": item["category_label"],
                "open_url": item["open_url"],
                "download_url": item["download_url"],
                "thumbnail_url": item.get("thumbnail_url"),
                "size_label": item.get("size_label"),
                "created_at_label": item.get("created_at_label"),
            }
            for item in group_dict.get("items") or []
        ]
        total_count += group_dict.get("count", 0)
        payload_groups.append(
            {
                "key": group_dict.get("key"),
                "title": group_dict.get("title"),
                "label": group_dict.get("title"),
                "count": group_dict.get("count", 0),
                "preview": preview,
                "preview_items": preview,
                "items": items,
            }
        )

    return payload_groups, total_count


def _build_customer_section(read_model) -> WamSectionVM:
    left_rows = [
        _row("고객명", read_model.customer["customer_name"]),
        _row("연락처", read_model.customer["phone"], copy_value=read_model.customer["phone"]),
        _row("발주처", read_model.customer["orderer_name"]),
    ]
    right_rows = [
        _row("담당 매니저", read_model.customer["manager_name"]),
        _row("도면 담당", read_model.people["drawing_manager"]),
        _row(
            "시공 담당",
            ", ".join(read_model.people["construction_workers"]) if read_model.people["construction_workers"] else "-",
        ),
        _row("시공 구분", read_model.people["construction_type"]),
    ]
    return WamSectionVM(
        key="customer",
        title="고객 / 발주",
        eyebrow="기본 정보",
        payload={
            "rows": left_rows + right_rows,
            "columns": [
                {"key": "customer", "rows": left_rows},
                {"key": "people", "rows": right_rows},
            ],
        },
    )


def _build_schedule_section(read_model) -> WamSectionVM:
    return WamSectionVM(
        key="schedule",
        title="일정",
        payload={
            "rows": [
                _row("접수일", read_model.schedule["received_date"]),
                _row(
                    "실측일 / 실측시간",
                    _combine_date_time(
                        read_model.schedule["measurement_date"],
                        read_model.schedule["measurement_time"],
                    ),
                ),
                _row(
                    "시공일 / 시공시간",
                    _combine_date_time(
                        read_model.schedule["construction_date"],
                        read_model.schedule["construction_time"],
                    ),
                ),
                _row("AS 방문일", read_model.schedule["as_visit_date"]),
            ]
        },
    )


def _build_items_section(read_model) -> WamSectionVM:
    items = []
    for index, item in enumerate(read_model.items, start=1):
        parts = [
            f"규격 {item['spec']}",
            f"내부 {item['inside']}",
            f"색상 {item['color']}",
            f"옵션 {item['option']}",
            f"손잡이 {item['handle']}",
            f"기타 {item['extra']}",
        ]
        items.append(
            {
                "eyebrow": f"품목 {index}",
                "title": item["product_name"],
                "description": " · ".join(parts),
            }
        )

    return WamSectionVM(
        key="items",
        title="품목",
        state="ready" if items else "empty",
        folded=True,
        group="heavy",
        payload={"items": items, "count": len(items)},
        empty_title="품목 정보 없음",
        empty_message="표시할 품목 정보가 없습니다.",
    )


def _build_payment_section(read_model) -> WamSectionVM:
    return WamSectionVM(
        key="payment",
        title="결제 / 금액",
        payload={
            "rows": [
                _row("결제금액", read_model.payment["total_label"]),
                _row("배송비", read_model.payment["shipping_fee_label"]),
            ]
        },
    )


def _build_attachments_section(context: WamRequestContext, flags: dict[str, bool]) -> WamSectionVM:
    groups, total_count = _serialize_attachment_groups(context, flags["attachments_enabled"])
    preview_items: list[dict[str, Any]] = []
    all_items: list[dict[str, Any]] = []
    for group in groups:
        preview_items.extend(group.get("preview_items") or group.get("preview") or [])
        all_items.extend(group.get("items") or [])

    preview_items = preview_items[:3]
    return WamSectionVM(
        key="attachments",
        title="첨부파일",
        state="ready" if total_count else "empty",
        folded=True,
        group="heavy",
        payload={
            "count": total_count,
            "preview_items": preview_items,
            "items": all_items,
            "groups": groups,
            "list_url": _api_url("channel_wam_api.wam_attachments"),
            "empty_title": "첨부 없음",
            "empty_message": "첨부파일이 없습니다.",
        },
        empty_title="첨부 없음",
        empty_message="첨부파일이 없습니다.",
        lazy=flags["attachments_lazy_enabled"],
    )


def _build_timeline_section(read_model, timeline_enabled: bool) -> WamSectionVM:
    items = [
        {
            "badge_label": event.label,
            "badge_tone": "info",
            "title": event.description,
            "meta": event.created_at_label or "-",
        }
        for event in read_model.timeline
    ]
    return WamSectionVM(
        key="timeline",
        title="최근 변경",
        state="hidden" if not timeline_enabled else ("ready" if items else "empty"),
        folded=True,
        group="heavy",
        payload={"items": items, "count": len(items)},
        empty_title="변경 이력 없음",
        empty_message="최근 변경 이력이 없습니다.",
    )


def _build_header_actions(read_model) -> list[WamActionVM]:
    actions = [
        WamActionVM(
            key="copy-address",
            label="주소 복사",
            copy_value=read_model.address if read_model.address != "-" else None,
            copy_label="주소",
            aria_label="주소 복사",
            visible=read_model.address not in (None, "", "-"),
            icon="copy",
            icon_only=True,
            tone="secondary",
        ),
        WamActionVM(
            key="open-attachments",
            label="첨부 열기",
            open_section="attachments",
            aria_label="첨부 섹션 열기",
            icon="attachment",
            icon_only=True,
            tone="secondary",
        ),
    ]

    if read_model.phone not in (None, "", "-"):
        actions.insert(
            0,
            WamActionVM(
                key="call-phone",
                label="전화",
                href=f"tel:{read_model.phone}",
                aria_label="연락처로 전화 걸기",
                icon="phone",
                icon_only=True,
                tone="secondary",
            ),
        )

    map_url = read_model.site.get("map_url")
    if map_url:
        actions.append(
            WamActionVM(
                key="open-map",
                label="지도",
                href=map_url,
                external=True,
                target="_blank",
                aria_label="지도 열기",
                icon="map",
                icon_only=True,
                tone="secondary",
            )
        )

    actions.append(
        WamActionVM(
            key="open-foms",
            label="FOMS",
            href=url_for("order_edit.edit_order", order_id=read_model.order_id, open="erp-order"),
            target="_blank",
            external=True,
            aria_label="FOMS 상세 화면 열기",
            icon="external",
            tone="primary",
        )
    )
    return actions


def build_wam_page(context: WamRequestContext) -> WamPageVM | None:
    """Build the full WAM page view-model for a scoped order request."""
    read_model = load_wam_order_read_model(context.order_id)
    if not read_model:
        return None

    flags = get_wam_feature_flags()
    header_actions = _build_header_actions(read_model)
    sections = [
        _build_customer_section(read_model),
        _build_schedule_section(read_model),
        _build_items_section(read_model),
        _build_attachments_section(context, flags),
        _build_timeline_section(read_model, flags["timeline_enabled"]),
    ]
    if flags["payment_enabled"]:
        sections.insert(5, _build_payment_section(read_model))
    sections = [
        section
        for section in sections
        if section.state != "hidden" and context.allows_section(section.key)
    ]
    primary_sections = [section for section in sections if not section.folded]
    folded_sections = [section for section in sections if section.folded]
    attachments_section = next((section for section in sections if section.key == "attachments"), None)
    attachment_count = (attachments_section.payload or {}).get("count", 0) if attachments_section else 0

    telemetry = {
        "page_opened_event": "wam_page_opened",
        "bootstrap_success_event": "wam_bootstrap_succeeded",
        "bootstrap_failure_event": "wam_bootstrap_failed",
        "attachments_opened_event": "wam_attachments_opened",
        "attachment_clicked_event": "wam_attachment_clicked",
        "section_opened_event": "wam_section_opened",
        "timeline_opened_event": "wam_timeline_opened",
        "section_count": len(sections),
        "attachment_count": attachment_count,
    }

    return WamPageVM(
        page_state="ready",
        order_id=read_model.order_id,
        title=f"주문 #{read_model.order_id} | FOMS WAM",
        header=_build_header(read_model, header_actions),
        summary_strip=_build_summary_strip(read_model),
        sections=sections,
        primary_sections=primary_sections,
        folded_sections=folded_sections,
        sticky_action_bar=None,
        flags=flags,
        info_banner=read_model.info_banner,
        telemetry=telemetry,
    )


def build_wam_bootstrap(context: WamRequestContext, page_vm: WamPageVM) -> dict[str, Any]:
    """Serialize a WAM page view-model into the bootstrap payload contract."""
    page_dict = page_vm.to_dict()
    attachments_section = next((section for section in page_dict["sections"] if section["key"] == "attachments"), None)
    attachments_payload = (attachments_section or {}).get("payload") or {"items": [], "count": 0}
    telemetry_payload = dict(page_vm.telemetry)
    telemetry_payload["latency_budget_ms"] = 1500

    return {
        "ok": True,
        "view_key": "order-detail",
        "page": page_dict,
        "attachments": attachments_payload,
        "flags": page_vm.flags,
        "api": {
            "bootstrap_url": _api_url("channel_wam_api.wam_bootstrap"),
            "attachments_url": _api_url("channel_wam_api.wam_attachments"),
            "telemetry_url": _api_url("channel_wam_api.wam_telemetry"),
        },
        "telemetry": telemetry_payload,
        "context": context.to_public_dict(),
    }


def build_legacy_wam_context(context: WamRequestContext) -> dict[str, Any] | None:
    """Build the legacy template context used by the non-v2 WAM page."""
    summary = get_order_summary_for_wam(context.order_id)
    if not summary:
        return None

    flags = get_wam_feature_flags()
    attachments = (
        get_order_attachments_for_wam(context.order_id)
        if flags.get("attachments_enabled", False)
        and context.allows("attachments")
        and context.allows_attachment_order(context.order_id)
        else []
    )

    return {
        "summary": summary,
        "attachments": attachments,
        "flags": flags,
    }


def build_legacy_summary(page_vm: WamPageVM) -> dict[str, Any]:
    """Project a WAM page view-model into the legacy summary contract."""
    header = page_vm.header
    return {
        "order_id": page_vm.order_id,
        "customer_name": header.get("customer_name"),
        "phone": next(
            (
                row.get("value")
                for section in page_vm.primary_sections
                if section.key == "customer"
                for row in section.payload.get("rows", [])
                if row.get("label") == "연락처"
            ),
            "-",
        ),
        "address": next(
            (
                item.get("value")
                for item in page_vm.summary_strip.get("items", [])
                if item.get("key") == "address"
            ),
            "-",
        ),
        "status_kr": header.get("status_label"),
        "product": next(
            (item.get("title") for item in page_vm.get_section("items").payload.get("items", [])[:1]),
            "-",
        ) if page_vm.get_section("items") else "-",
        "measurement_date": next(
            (
                item.get("value")
                for item in page_vm.summary_strip.get("items", [])
                if item.get("key") == "measurement_date"
            ),
            "-",
        ),
        "construction_date": next(
            (
                item.get("value")
                for item in page_vm.summary_strip.get("items", [])
                if item.get("key") == "construction_date"
            ),
            "-",
        ),
        "manager_name": next(
            (
                row.get("value")
                for section in page_vm.primary_sections
                if section.key == "customer"
                for row in section.payload.get("rows", [])
                if row.get("label") == "담당 매니저"
            ),
            "-",
        ),
    }


def build_legacy_attachments(page_vm: WamPageVM) -> list[dict[str, Any]]:
    """Project attachment items from the WAM page view-model into the legacy schema."""
    attachments_section = page_vm.get_section("attachments")
    if not attachments_section:
        return []

    return [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "type": item.get("file_type"),
            "url": item.get("open_url"),
            "category": item.get("category"),
        }
        for item in attachments_section.payload.get("items") or []
    ]
