"""'회사 지식' 화면(설계서 2026-11-02-haud-master-brain 7.5 · D95 · D101) — 읽기만(⑤-2).

- ``/brain`` 한 곳에 탭 넷: 찾기(첫 화면) · 지식 표 · 판 · 유형 지도. 뼈대와 유형 지도의 HTML 목록(진짜 화면 — 그림은 돕는 쪽)은
  서버가 그리고, 찾기 · 표 · 판 값과 지도 그림은 작은 스크립트(``static/js/brain/*.js``)가 JSON API(:mod:`foms.api.brain`)로
  읽는다. 그림 라이브러리(Cytoscape.js · cytoscape-dagre)는 지도 탭을 열 때만 ``import()`` 한다.
- ``/brain/items/<키>`` 항목 카드 — 서버가 다 그린다(탭: 내용 · 이력 · 이웃 지도 · 뇌 보기 — 뒤 둘은 다음 단계 빈 자리).
- 여는 사람은 켜진 ADMIN 과 층 승인자 팀 MANAGER 뿐, 그 밖은 404(:func:`foms.services.brain.access.screen_viewer`).
  메뉴 항목도 같은 판정(:func:`brain_nav_allowed` — DB 를 읽지 않는다).
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, abort, g, render_template, request

from db import get_db
from foms.services.brain.access import can_open_screen, screen_viewer
from foms.services.brain.browse import CHECKS, SORTS, type_map
from foms.services.brain.card import item_card
from foms.services.brain.constants import BRANDS, CONFIDENCES, GRADES, LAYERS, OBJECT_STATUSES, TYPES
from foms.services.brain.display import (
    BRAND_LABELS, CHECK_LABELS, CONFIDENCE_LABELS, EVIDENCE_LABELS, FIELD_LABELS, GRADE_LABELS, LAYER_LABELS,
    LINK_DISPLAY, SORT_LABELS, STATUS_LABELS, TYPE_DISPLAY, display_table, visibility_label,
)
from foms.services.datetime_kst import get_today_kst
from foms.web.auth import login_required

brain_web_bp = Blueprint("brain_web", __name__)

TABS: tuple[str, ...] = ("search", "table", "releases", "map")


@brain_web_bp.app_template_global("brain_nav_allowed")
def brain_nav_allowed() -> bool:
    """메뉴에 '회사 지식'을 보일지(로그인 사용자 · 같은 판정)."""
    return can_open_screen(getattr(g, "current_user", None))


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


@brain_web_bp.route("/brain")
@login_required
def index():
    """회사 지식 — 탭 넷(첫 탭 찾기). ``?tab=table&type=<유형>`` 으로 지식 표를 바로 연다."""
    viewer = _viewer_or_404()
    tab = request.args.get("tab", "search")
    db = get_db()
    try:
        tmap = type_map(db, viewer)
    finally:
        db.rollback()  # 읽기만
    return render_template(
        "brain/index.html", tab=tab if tab in TABS else "search",
        start_type=request.args.get("type", "") if request.args.get("type", "") in TYPES else "",
        start_query=request.args.get("q", "")[:100], tmap=tmap, display=display_table(), options=_filter_options(),
        type_display=TYPE_DISPLAY, link_display=LINK_DISPLAY, layer_labels=LAYER_LABELS)


@brain_web_bp.route("/brain/items/<path:key>")
@login_required
def item(key: str):
    """항목 카드 — 볼 수 없거나 없으면 404."""
    viewer = _viewer_or_404()
    db = get_db()
    try:
        card = item_card(db, viewer, key[:120], today=get_today_kst())
    finally:
        db.rollback()
    if card is None:
        abort(404)
    return render_template(
        "brain/item.html", card=card, type_display=TYPE_DISPLAY, link_display=LINK_DISPLAY,
        layer_labels=LAYER_LABELS, brand_labels=BRAND_LABELS, status_labels=STATUS_LABELS,
        confidence_labels=CONFIDENCE_LABELS, grade_labels=GRADE_LABELS, evidence_labels=EVIDENCE_LABELS,
        field_labels=FIELD_LABELS, visibility=visibility_label(card["item"]["visibility"]))
