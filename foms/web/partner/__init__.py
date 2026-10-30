"""PARTNER-02: 협력사 화면(HTML) — 주문 목록 · 새 주문 등록 · 주문 화면.

공용 레이아웃(내부 메뉴 · 배지 · 알림 스크립트)을 쓰지 않는 단독 화면이다(``partner/layout.html``).
금액 · 원가 · 내부 메모 · 다른 협력사 주문은 보여 주지 않는다 — 주문 화면은 협력사 투영
(:func:`build_partner_order_view`)만 받는다.
스펙: docs/specs/2026-10-08-partner-portal_SPEC.md §5.1 · docs/specs/2026-10-19-partner-foms-mode_SPEC.md §12
"""
from __future__ import annotations

from flask import Blueprint, abort, g, render_template, request, url_for

from db import get_db
from foms.api.files.routes import build_file_download_url, build_file_view_url
from foms.api.wdcalculator.blueprint import load_products
from foms.services.auth.partner_scope import partner_can_read_order, partner_required
from foms.services.order_attachment_permissions import is_partner_original_key
from foms.services.orders.as_cycle_service import AS_IN_PROGRESS, AS_RECEIVED, current_cycle, cycle_status
from foms.services.datetime_kst import format_datetime_kst, get_today_kst
from foms.services.orders.confirm_drawing_gate import confirm_exit_block
from foms.services.orders.drawing_customer_send import drawing_round_info, round_text
from foms.services.orders.upload_ticket import _file_type as attachment_file_type  # 확장자→image/video/file (첨부 정본과 같은 규칙)
from foms.services.partners.as_intake import AS_OPEN_STAGES
from foms.services.partners.completion import as_progress_for_partner, construction_photos_for_partner
from foms.services.partners.channel_push import push_state
from foms.services.partners.construction_calendar import partner_construction_calendar
from foms.services.partners.drawing_tab import build_partner_drawing_tab
from foms.services.partners.drawing_confirm import final_drawings_for_partner
from foms.services.partners.history import partner_order_history
from foms.services.partners.items_edit import partner_edit_open
from foms.services.partners.manager import org_member_choices
from foms.services.partners.order_list import partner_list_filters, partner_order_board, partner_turn_count
from foms.services.partners.revision import pending_revision_for_partner
from foms.services.partners.view import build_partner_order_view, partner_steps
from models import Order, OrderAttachment, PartnerOrg

partner_portal_bp = Blueprint("partner_portal", __name__, url_prefix="/partner")

MAX_PRODUCT_NAMES = 500


def _org() -> PartnerOrg:
    return get_db().query(PartnerOrg).filter(PartnerOrg.id == g.current_user.partner_org_id).first()


def _item_name(items: list, item_index: int | None) -> str:
    """품목 실측 사진이 묶인 품목 이름(공통 사진이면 빈 문자열)."""
    if item_index is None or not isinstance(items, list) or not 0 <= item_index < len(items):
        return ""
    item = items[item_index]
    return str(item.get("product_name") or "") if isinstance(item, dict) else ""


def _product_names() -> list[str]:
    """제품명 ▾ 목록 — 우리 제품 목록의 **이름만**(단가 · 쿠폰 · 옵션 값은 협력사에게 싣지 않는다, §17)."""
    names: set[str] = set()
    for product in load_products() or []:
        name = str(product.get("name") or "").strip() if isinstance(product, dict) else ""
        if name:
            names.add(name[:100])
    return sorted(names)[:MAX_PRODUCT_NAMES]


@partner_portal_bp.context_processor
def _partner_nav():
    """머리 메뉴 "도면 확인 N"(협력사 차례 수). 협력사 화면을 그릴 때만 센다."""
    user = getattr(g, "current_user", None)
    if user is None or not getattr(user, "partner_org_id", None):
        return {}
    return {"partner_turn_count": partner_turn_count(get_db(), user.partner_org_id)}


@partner_portal_bp.route("")
@partner_required
def home():
    db = get_db()
    org = _org()
    members = org_member_choices(db, org.id)
    filters = partner_list_filters(request.args)
    board = partner_order_board(db, org.id, g.current_user.id, filters, {u.id: u.name for u in members})
    return render_template(
        "partner/home.html",
        org=org,
        me=g.current_user,
        members=members,
        filters=filters,
        # 달력은 걸러 보지 않는 "주문" 첫 화면에만 — 탭(도면 확인 · 완공 · AS) · 칩으로 거르면 달력이 휴대폰
        # 화면을 다 덮어 목록이 바뀐 게 안 보였다(사용자 2026-10-28).
        cal=None if any(filters.values()) else partner_construction_calendar(db, org.id, request.args.get("cal")),
        cal_url=url_for("partner_portal.home"),
        **board,
    )


@partner_portal_bp.route("/orders/new")
@partner_required
def new_order():
    return render_template(
        "partner/new_order.html",
        org=_org(),
        me=g.current_user,
        today=get_today_kst().isoformat(),
        steps=partner_steps("DRAWING"),  # 보내면 바로 "도면 작업 중" — 주문 화면과 같은 진행 칸
        product_names=_product_names(),
    )


@partner_portal_bp.route("/orders/<int:order_id>")
@partner_required
def order_detail(order_id: int):
    db = get_db()
    order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
    if not partner_can_read_order(g.current_user, order):
        abort(404)
    view = build_partner_order_view(order)
    partner_files, item_photos = _partner_files(db, order, view["items"])
    stage = view["stage_code"]
    cycle = current_cycle(order.structured_data or {})
    as_open = cycle is not None and cycle_status(cycle) in (AS_RECEIVED, AS_IN_PROGRESS)
    finals = _final_drawings(order)
    # 도면 확인 차례(CONFIRM)이고 도면이 확정됐을 때만 버튼을 연다(서버가 다시 판정한다).
    can_approve = stage == "CONFIRM" and bool(finals) and confirm_exit_block(order.structured_data or {}) is None
    # 저희가 보낸 도면을 협력사가 확인(받음) — FOMS 영업 "도면 수령 확인"과 같은 자리(사용자 2026-10-28).
    can_receive = (stage == "DRAWING" and bool(finals)
                   and (order.structured_data or {}).get("drawing_status") == "TRANSFERRED")
    return render_template(
        "partner/order_detail.html",
        org=_org(),
        view=view,
        partner_files=partner_files,
        item_photos=item_photos,
        can_upload=partner_edit_open(order),
        final_drawings=finals,
        can_approve=can_approve,
        can_receive=can_receive,
        can_revise=stage in ("DRAWING", "CONFIRM") and bool(finals)
        and (order.structured_data or {}).get("drawing_status") in ("TRANSFERRED", "CONFIRMED"),
        can_as=stage in AS_OPEN_STAGES and not as_open,
        as_open=as_open,
        drawing_cards=[f for f in finals if f["is_image"]],
        drawing_files=[f for f in finals if not f["is_image"]],
        drawing_round=_drawing_round(order),
        revision_pending=pending_revision_for_partner(order) if stage in ("DRAWING", "CONFIRM") else None,
        drawing_tab=_drawing_tab(order, finals, can_receive, can_approve),
        history=partner_order_history(db, order),
        active_tab="drawing" if (can_approve or can_receive) else "order",
        manager_choices=org_member_choices(db, order.partner_org_id),
        channel_push=push_state(order),
        measure_file_count=_measurement_push_count(db, order.id),
        product_names=_product_names() if view["items_editable"] else [],
        **_completion_context(db, order, stage),
    )


def _measurement_push_count(db, order_id: int) -> int:
    """영발 PUSH에 실릴 실측 첨부 수. 저장 키가 있는 measurement만. 없으면 글만 나간다."""
    return (
        db.query(OrderAttachment)
        .filter(
            OrderAttachment.order_id == order_id,
            OrderAttachment.category == "measurement",
            OrderAttachment.storage_key.isnot(None),
            OrderAttachment.storage_key != "",
        )
        .count()
    )


def _final_drawings(order: Order) -> list[dict]:
    """최종 도면 — 그림은 고객 공유 화면과 같은 갤러리 카드(``url`` · ``label`` · ``download_url``), 그 밖은 파일 줄."""
    rows = []
    for no, f in enumerate(final_drawings_for_partner(order), start=1):
        name = f.get("filename") or f.get("key", "").rsplit("/", 1)[-1]
        rows.append({
            "filename": name,
            "label": f"{no}번 · {name}",  # 우리 도면 작업실처럼 번호로 부른다(수정 요청 때 "2번 도면")
            "url": build_file_view_url(f["key"]),
            "download_url": build_file_download_url(f["key"]),
            "is_image": attachment_file_type(name) == "image",
        })
    return rows


def _drawing_tab(order: Order, finals: list[dict], can_receive: bool, can_approve: bool) -> dict:
    """도면 탭 차례 띠 · 단계 · 주고받은 기록(우리 도면 작업실 휴대폰 화면 모양). 참고 사진 주소는 여기서 key 로."""
    tab = build_partner_drawing_tab(order, finals, can_receive=can_receive, can_approve=can_approve)
    for event in tab["thread"]:
        for ref in event["refs"]:
            ref["url"] = build_file_view_url(ref["key"])
    return tab


def _drawing_round(order: Order) -> str:
    """도면 탭 제목 옆 "2차 · 10-20 14:05 올라옴"(올린 적이 없으면 빈 문자열)."""
    info = drawing_round_info(order.structured_data or {})
    if not info.round:
        return ""
    at = format_datetime_kst(info.round_at, "%m-%d %H:%M") if info.round_at else None
    return f"{round_text(info.round)} · {at} 올라옴" if at else round_text(info.round)


def _partner_files(db, order: Order, items: list) -> tuple[list[dict], dict[int, list[dict]]]:
    """협력사가 낸 파일(공통 첨부 목록)과 품목별 실측 사진(품목 카드). 우리 작업 파일은 넣지 않는다."""
    rows = (
        db.query(OrderAttachment)
        .filter(OrderAttachment.order_id == order.id)
        .order_by(OrderAttachment.id)
        .all()
    )
    files: list[dict] = []
    by_item: dict[int, list[dict]] = {}
    for a in rows:
        if not is_partner_original_key(a.storage_key):
            continue
        entry = {
            "filename": a.filename,
            "id": a.id,
            "item_index": a.item_index,
            # 제품 연결 · 해제는 협력사가 보낸 실측 사진만(5-3, partner_api.link_attachment 와 같은 판정).
            "linkable": a.category == "measurement",
            "kind": "초안 도면" if "/partner_draft/" in (a.storage_key or "") else "실측 사진",
            "item_name": _item_name(items, a.item_index),
            "url": build_file_view_url(a.storage_key),
            "thumb_url": build_file_view_url(a.thumbnail_key or a.storage_key),
            "is_image": (a.file_type or "") == "image",
        }
        files.append(entry)
        if entry["item_name"]:
            by_item.setdefault(a.item_index, []).append(entry)
    return files, by_item


def _with_urls(photos: list[dict]) -> list[dict]:
    """서비스가 돌려준 key 로 보기 주소를 붙인다(주소 만들기는 웹 층 몫 — 층 의존 규칙)."""
    return [
        {**p, "url": build_file_view_url(p["storage_key"]), "thumb_url": build_file_view_url(p["thumbnail_key"])}
        for p in photos
    ]


def _completion_context(db, order: Order, stage: str) -> dict:
    """완공 사진 탭(시공이 시작된 뒤만) · AS 진행 상황. 설계서 2026-10-19 §3.6."""
    show = stage in AS_OPEN_STAGES
    progress = as_progress_for_partner(db, order) if show else None
    if progress is not None:
        progress = {**progress, "photos": _with_urls(progress["photos"])}
    return {
        "show_completion": show,
        "construction_photos": _with_urls(construction_photos_for_partner(db, order)) if show else [],
        "as_progress": progress,
    }
