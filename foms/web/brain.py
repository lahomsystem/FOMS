"""'회사 지식' 화면(설계서 2026-11-02-haud-master-brain 7.5 · D95 · D101 · D103) — 읽기(⑤-2) + 제안 · 결정(⑤-3).

- ``/brain`` 한 곳에 탭 여섯: 찾기(첫 화면) · 지식 표 · 제안함 · 다시 확인 · 판 · 유형 지도. 뼈대와 유형 지도의 HTML 목록(진짜
  화면 — 그림은 돕는 쪽)은 서버가 그리고, 찾기 · 표 · 제안함 · 다시 확인 · 판 값과 지도 그림은 작은 스크립트
  (``static/js/brain/*.js``)가 JSON API(:mod:`foms.api.brain` · :mod:`foms.api.brain_review`)로 읽고 쓴다. 탭 이름 옆 수는
  서버가 센다(보기 범위 · 결정 가능으로 거른 수). 그림 라이브러리는 지도 탭을 열 때만 ``import()`` 한다.
- ``/brain/items/<키>`` 항목 카드 — 서버가 그리고, '고칠 말 제안' · 은퇴 · 지우기 · 옛 판 되돌리기 제안 단추만 스크립트
  (``brain-item-actions.js``)가 단다(탭: 내용 · 이력 · 이웃 지도 · 뇌 보기). 이웃 지도의 1걸음 이웃 목록(진짜 화면 — 그림은
  돕는 쪽)은 서버가 그리고, 그림 · 걸음 · 종류 칩은 ``brain-neighbours.js`` 가 탭을 열 때 Cytoscape 를 ``import()`` 해 단다.
  뇌 보기(7.6)는 ``brain3d-tab.js`` 가 휴대폰 · WebGL 없음 · 소프트웨어 그리기면 탭을 숨기고, 열 때만 three.js 를 ``import()``.
- 여는 사람은 켜진 ADMIN 과 층 승인자 팀 MANAGER 뿐, 그 밖은 404(:func:`foms.services.brain.access.screen_viewer`).
  메뉴 항목은 이 판정(DB 를 읽지 않는다) + 물어보기 화면을 여는 직원(:func:`brain_nav_allowed` — 설정 한 줄을 요청에 한 번만).
- **물어보기 탭**(설계서 10절 · ⑤-5) — 탭은 :func:`foms.services.brain.chat_access.page_viewer` 가 열 때만(ADMIN 은 늘 —
  꺼져 있어도 설정을 보려고 · 층 승인자 MANAGER 는 단계 ``leads`` 이상 · 켬). 회사 지식 화면을 못 여는 직원이 여는 단계 안이면
  ``/brain`` 이 물어보기만 있는 ``/brain/ask`` 로 보낸다(그 밖 404). 답 · 근거 칩 · 피드백은 ``brain-ask.js`` 가 JSON API
  (:mod:`foms.api.brain_chat`)로 읽고 쓴다.
- **새 화면**(설계서 2026-11-14-foms-graft 5.2) — 접목판 ``brain_ui`` 스위치(:mod:`foms.services.graft_flags`)가 켜진 사람만
  ``templates/brain/ds/`` 의 혼자 서는 문서(탭마다 화면 하나 · :data:`DS_SECTIONS`)를 그린다. 꺼진 사람은 옛 화면 그대로.
  권한(404 · 물어보기만 여는 직원 보내기)은 같은 판정이고, AI 직원 탭(``?tab=agents``)만 새로 ADMIN + 화면 여는 MANAGER.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, abort, g, redirect, render_template, request, url_for

from db import get_db
from foms.services.brain import actions
from foms.services.brain.access import can_open_screen, screen_viewer, wide_bins
from foms.services.brain.around import AroundQuery, search_around
from foms.services.brain.browse import CHECKS, SORTS, type_map
from foms.services.brain.card import item_card
from foms.services.brain.chat_access import page_open_without_settings, page_viewer
from foms.services.brain.chat_settings import read_chat_settings
from foms.services.brain.constants import (
    BRANDS, CONFIDENCES, GRADES, LAYERS, LINK_KINDS, MAX_NEIGHBOUR_DEPTH, OBJECT_STATUSES, TYPES,
)
from foms.services.brain.display import (
    BRAND_LABELS, CHECK_LABELS, CONFIDENCE_LABELS, EVIDENCE_LABELS, FIELD_LABELS, GRADE_LABELS, LAYER_LABELS,
    LINK_DISPLAY, SORT_LABELS, STATUS_LABELS, TYPE_DISPLAY, display_table, visibility_label,
)
from foms.services.brain.inbox import inbox_counts
from foms.services.brain.recheck import recheck_counts
from foms.services.brain.scope import ROLE_MANAGER, viewer_of
from foms.services.brain.schemas import payload_props
from foms.services import graft_flags
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.web.auth import login_required

brain_web_bp = Blueprint("brain_web", __name__)

TABS: tuple[str, ...] = ("search", "table", "inbox", "recheck", "releases", "map", "onto", "ask")
#: 새 화면(접목판 ``brain_ui`` 스위치 — 설계서 2026-11-14-foms-graft 5.2)의 탭 — 옛 탭 + AI 직원. 옛 ``TABS`` 는 그대로 둔다.
DS_TABS: tuple[str, ...] = (*TABS, "agents")
#: 새 화면 탭 → 화면(위 줄 · 아래 탭의 자리, 템플릿 ``brain/ds/<화면>.html``) — 설계서 5.2 표.
DS_SECTIONS: dict[str, str] = {
    "inbox": "inbox", "recheck": "inbox", "releases": "inbox", "search": "search", "table": "search",
    "map": "onto", "onto": "onto", "ask": "ask", "agents": "agents",
}
#: 위 줄 탭(키 · 글 · 아이콘)과 폰 아래 탭 셋('나'는 틀이 따로 그린다).
_DS_NAV_TABS: tuple[tuple[str, str, str], ...] = (
    ("inbox", "승인 대기", "inbox"), ("search", "찾기", "search"), ("ask", "물어보기", "chat"),
    ("onto", "온톨로지", "layout-hierarchy"), ("agents", "AI 직원", "predictive-analysis"),
)
_DS_PHONE_TABS: tuple[tuple[str, str, str], ...] = (("inbox", "승인", "inbox"), ("search", "찾기", "search"),
                                                    ("ask", "물어보기", "chat"))
#: 물어보기 화면을 열 수 있나를 요청 하나에 한 번만 판정해 두는 ``flask.g`` 칸 — (사용자 번호, 답).
_G_CHAT_PAGE = "brain_chat_page_open"


@brain_web_bp.app_template_global("brain_nav_allowed")
def brain_nav_allowed() -> bool:
    """메뉴에 '회사 지식'을 보일지 — 화면을 여는 사람(DB 를 읽지 않는다) 또는 물어보기 화면을 여는 직원(F28 · D99 3단계).

    물어보기만 여는 직원도 같은 주소(``/brain``)로 간다 — 그 사람에게는 :func:`index` 가 ``/brain/ask`` 로 보낸다.
    """
    user = getattr(g, "current_user", None)
    return can_open_screen(user) or chat_page_open(user)


def chat_page_open(user: Any) -> bool:
    """물어보기 화면을 열 수 있나 — :func:`page_viewer` 와 같은 판정. 메뉴가 모든 화면에서 부르므로 설정 한 줄
    (:func:`read_chat_settings`)은 답이 설정에 달린 내부 직원일 때만 · 요청에 한 번만(``flask.g``) 읽는다.

    ADMIN · 바깥 역할 · 꺼진 계정 · 로그인 안 함 · 어느 단계에도 없는 역할은 읽지 않는다(:func:`page_open_without_settings`).
    """
    known = page_open_without_settings(user)
    if known is not None:
        return known
    user_id = getattr(user, "id", None)
    memo = g.get(_G_CHAT_PAGE)
    if memo is not None and memo[0] == user_id:
        return memo[1]
    db = get_db()
    with db.no_autoflush:  # 메뉴를 그리다 요청이 아직 안 보낸 변경을 밀어 넣지 않는다(읽기만)
        opened = page_viewer(user, read_chat_settings(db)) is not None
    setattr(g, _G_CHAT_PAGE, (user_id, opened))
    return opened


def _viewer_or_404() -> Any:
    """열 수 있는 사람의 Viewer — 아니면 404(있는지도 알리지 않는다)."""
    viewer = screen_viewer(getattr(g, "current_user", None))
    if viewer is None:
        abort(404)
    return viewer


def _filter_options() -> dict[str, list[tuple[str, str]]]:
    """지식 표 거르기 칸의 (값, 이름) 목록 — 값 목록은 코드 상수 그대로."""
    return {
        "type": [(t, TYPE_DISPLAY[t][0]) for t in TYPES],
        "layer": [(v, LAYER_LABELS[v]) for v in LAYERS],
        "brand": [(v, BRAND_LABELS.get(v, v)) for v in BRANDS],
        "status": [(v, STATUS_LABELS[v]) for v in OBJECT_STATUSES],
        "grade": [(v, GRADE_LABELS[v]) for v in GRADES],
        "confidence": [(v, CONFIDENCE_LABELS[v]) for v in CONFIDENCES],
        "check": [(v, CHECK_LABELS[v]) for v in CHECKS],
        "sort": [(v, SORT_LABELS[v]) for v in SORTS],
    }


def _screen_actions(viewer: Any) -> list[dict[str, Any]]:
    """화면에 싣는 액션 표(이름 있는 액션 — 7.7 · D104). 사장님만 하는 액션은 ADMIN 화면에만."""
    return [a for a in actions.specs() if viewer.is_admin or not a["admin_only"]]


def _chat_open() -> bool:
    """물어보기를 열 수 있나(여는 단계 · 스위치 — 설정 한 줄을 요청에 한 번만, 메뉴와 같은 기억 :func:`chat_page_open`)."""
    db = get_db()
    try:
        return chat_page_open(getattr(g, "current_user", None))
    finally:
        db.rollback()


@brain_web_bp.app_template_global("graft_enabled")
def graft_enabled(name: str) -> bool:
    """템플릿 전역 — 지금 사람에게 접목판 스위치가 켜졌나(:func:`foms.services.graft_flags.enabled`, DB 를 읽지 않는다).

    Args:
        name: 짧은 이름(``brain_ui`` · ``erp_read`` · ``actions`` · ``cell_pc`` · ``cell_tablet`` · ``cell_mobile``).

    Returns:
        켜져 있으면 True.
    """
    return graft_flags.enabled(name, getattr(g, "current_user", None))


def _ds_on() -> bool:
    """이 사람에게 새 화면(``brain_ui``)을 그리나 — 꺼진 사람은 옛 화면 그대로."""
    return graft_flags.enabled("brain_ui", getattr(g, "current_user", None))


def _agents_open(viewer: Any) -> bool:
    """AI 직원 탭을 여나 — 화면을 여는 사람 가운데 ADMIN 과 MANAGER(설계서 5.2)."""
    return viewer is not None and (viewer.is_admin or viewer.role == ROLE_MANAGER)


def _ds_nav(viewer: Any, section: str, *, chat_tab: bool, inbox_count: int | None) -> dict[str, Any]:
    """새 화면 위 줄 · 폰 아래 탭 값 — 탭은 지금 권한 그대로 가린다(화면을 못 여는 직원은 물어보기만).

    Args:
        viewer: 화면을 여는 사람의 Viewer(물어보기만 여는 직원이면 ``None``).
        section: 지금 화면(:data:`DS_SECTIONS` 의 값).
        chat_tab: 물어보기를 여나.
        inbox_count: 승인 대기 수(서버가 센 지식 수 — 세지 않은 화면이면 ``None``, 수를 안 그린다).

    Returns:
        ``{"section", "screen", "tabs": [(키, 글, 아이콘, 주소)], "phone_tabs": […], "inbox_count"}``.
    """
    screen = viewer is not None
    allowed = {"inbox": screen, "search": screen, "ask": chat_tab, "onto": screen, "agents": _agents_open(viewer)}

    def href(key: str) -> str:
        return url_for("brain_web.ask_page") if key == "ask" and not screen else url_for("brain_web.index", tab=key)

    return {
        "section": section, "screen": screen, "inbox_count": inbox_count,
        "tabs": [(k, label, icon, href(k)) for k, label, icon in _DS_NAV_TABS if allowed[k]],
        "phone_tabs": [(k, label, icon, href(k)) for k, label, icon in _DS_PHONE_TABS if allowed[k]],
    }


def _render_ds_index(viewer: Any, tab: str, ctx: dict[str, Any]) -> str:
    """새 화면 — 탭마다 그 화면 템플릿 하나(설계서 5.2 표). 옛 화면과 같은 값 전부 + ``page`` · ``ds_nav``.

    Args:
        viewer: 화면을 여는 사람.
        tab: 주소의 탭(옛 화면과 같은 첫 탭 · 물어보기 판정을 지난 값).
        ctx: 옛 화면에 넘기는 값 그대로.

    Returns:
        그린 HTML. AI 직원 탭을 못 여는 사람은 404.
    """
    tab = tab if tab in DS_TABS else "search"
    if tab == "agents" and not _agents_open(viewer):
        abort(404)
    section = DS_SECTIONS[tab]
    nav = _ds_nav(viewer, section, chat_tab=ctx["chat_tab"], inbox_count=ctx["counts"]["inbox"])
    return render_template(f"brain/ds/{section}.html", **{**ctx, "tab": tab}, page=tab, ds_nav=nav)


@brain_web_bp.route("/brain")
@login_required
def index():
    """회사 지식 — 탭(첫 탭은 내가 결정할 제안이 있으면 '승인 대기', 없으면 찾기 — 설계서 7.9). ``?tab=table&type=<유형>`` 으로
    지식 표를 바로 연다. 화면을 못 열지만 물어보기 단계 안인 직원은 물어보기 화면으로 보낸다."""
    viewer = screen_viewer(getattr(g, "current_user", None))
    if viewer is None:
        if _chat_open():
            return redirect(url_for("brain_web.ask_page"))
        abort(404)
    tab = request.args.get("tab", "")
    db = get_db()
    try:
        tmap = type_map(db, viewer)
        counts = {"inbox": inbox_counts(db, viewer, now_utc_naive())["cards"],
                  "recheck": recheck_counts(db, viewer, today=get_today_kst())["total"]}
        chat_tab = page_viewer(getattr(g, "current_user", None), read_chat_settings(db)) is not None
    finally:
        db.rollback()  # 읽기만
    if not tab:
        tab = "inbox" if counts["inbox"] else "search"
    if tab == "ask" and not chat_tab:
        tab = "search"
    ctx: dict[str, Any] = dict(
        tab=tab if tab in TABS else "search", chat_tab=chat_tab,
        start_type=request.args.get("type", "") if request.args.get("type", "") in TYPES else "",
        start_query=request.args.get("q", "")[:100], tmap=tmap, display=display_table(), options=_filter_options(),
        type_display=TYPE_DISPLAY, link_display=LINK_DISPLAY, layer_labels=LAYER_LABELS, counts=counts,
        is_admin=viewer.is_admin, wide_bins=sorted(wide_bins(viewer)), actions=_screen_actions(viewer))
    if _ds_on():
        return _render_ds_index(viewer, tab, ctx)
    return render_template("brain/index.html", **ctx)


@brain_web_bp.route("/brain/items/<path:key>")
@login_required
def item(key: str):
    """항목 카드 — 볼 수 없거나 없으면 404."""
    viewer = _viewer_or_404()
    db = get_db()
    today = get_today_kst()
    try:
        card = item_card(db, viewer, key[:120], today=today)
        around = search_around(db, viewer, AroundQuery(key=card["item"]["key"]), today=today) if card else None
    finally:
        db.rollback()
    if card is None or around is None:
        abort(404)
    it = card["item"]
    props = payload_props(it["type"])
    current = {"name": it.get("name"), "text": it.get("text"), "valid_from": it.get("valid_from"),
               "valid_to": it.get("valid_to"), **{p.path: card["payload_values"].get(p.path) for p in props}}
    propose = [a for a in actions.specs() if a["stage"] == "propose" and a["name"] != "item_rollback"]
    extra: dict[str, Any] = {}
    template = "brain/item.html"
    if _ds_on():
        template = "brain/ds/item.html"
        extra = {"page": "item", "ds_nav": _ds_nav(viewer, "search", chat_tab=_chat_open(), inbox_count=None)}
    return render_template(
        template, **extra, card=card, current=current, display=display_table(), props=props, propose=propose,
        rollback_label=actions.ACTIONS["item_rollback"].label,
        type_display=TYPE_DISPLAY, link_display=LINK_DISPLAY,
        layer_labels=LAYER_LABELS, brand_labels=BRAND_LABELS, status_labels=STATUS_LABELS,
        confidence_labels=CONFIDENCE_LABELS, grade_labels=GRADE_LABELS, evidence_labels=EVIDENCE_LABELS,
        field_labels=FIELD_LABELS, visibility=visibility_label(card["item"]["visibility"]), around=around,
        link_order=LINK_KINDS, max_depth=MAX_NEIGHBOUR_DEPTH)


@brain_web_bp.route("/brain/ask")
@login_required
def ask_page():
    """물어보기만 있는 화면(여는 단계 안 직원 · ADMIN) — 그 밖 404."""
    if not _chat_open():
        abort(404)
    if _ds_on():
        nav = _ds_nav(screen_viewer(g.current_user), "ask", chat_tab=True, inbox_count=None)
        return render_template("brain/ds/ask.html", display=display_table(), is_admin=viewer_of(g.current_user).is_admin,
                               page="ask", ds_nav=nav)
    return render_template("brain/ask.html", display=display_table(), is_admin=viewer_of(g.current_user).is_admin)
