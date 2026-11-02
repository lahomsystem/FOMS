"""'회사 지식' JSON API(설계서 2026-11-02-haud-master-brain 7.5 'API' · 화면 1 · 2 · 3 · 6 · 7) — **읽기만**(⑤-2).

접두 ``/api/brain`` — 모두 GET:

- ``/search?q=`` 찾기 — 유형별 묶음(PostgreSQL pg_trgm · SQLite 부분 일치).
- ``/table?type=&layer=&brand=&status=&grade=&confidence=&check=&sort=&page=&per_page=`` 지식 표(유형 하나 · 쪽).
- ``/items/<키>`` 항목 카드(링크 · 바깥 정본 칩 · 사본 · 이력).
- ``/type-map`` 유형 지도(유형 · 링크 종류 · 허용 짝 · 유형별 수).
- ``/releases?page=`` 판 목록 · ``/releases/<번호>`` 판 차이 요약.
- ``/around?key=&kinds=a,b&depth=1|2&limit=`` 이웃 찾기(Search Around — 7.7 · D105) — 이웃 지도 · 뇌 보기 탭(점 · 선 · 종류별 수).
- ``/points`` 뇌 보기 바탕 점(키 · 유형 · 상태 표시 · 쓰인 횟수 — 이름 없음 · 상한 5,000).
- ``/quality`` 연결 개수 규칙 품질 수(최소 미달 · 최대 넘음 — D105).

여는 사람은 켜진 ADMIN 과 층 승인자 팀 MANAGER 뿐(D101 — :func:`foms.services.brain.access.screen_viewer`). 로그인 안 함 401,
그 밖(다른 역할 · 협력사 직원)은 **404**(있는지도 알리지 않는다). PARTNER 세션은 이 핸들러 앞에서 협력사 문지기
(:func:`foms.services.auth.partner_scope.partner_gate`)가 없는 주소와 같은 답(403)으로 막는다. 모든 질의 · 수는 보는 사람의
보기 범위로 질의 단계에서 거른다. 응답은 ``{"success", "data", "error"}``, 오류 글은 이 모듈이 정한 글만. 쓰기(제안 · 결정 ·
되돌리기)는 다음 단계라 여기 없다 — 쓰기가 생기면 공용 CSRF · Origin 가드와 쓰기 정책 manifest 뒤에 둔다.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from flask import Blueprint, g, jsonify, request

from db import get_db
from foms.services.brain.access import screen_viewer
from foms.services.brain.around import AroundQueryError, brain_points, parse_around, search_around
from foms.services.brain.browse import TableQueryError, parse_table_query, search_grouped, table_page, type_map
from foms.services.brain.card import item_card
from foms.services.brain.quality import quality_counts
from foms.services.brain.release_view import release_diff, release_page
from foms.services.brain.scope import Viewer
from foms.services.datetime_kst import get_today_kst

brain_api_bp = Blueprint("brain_api", __name__, url_prefix="/api/brain")

NOT_FOUND = "찾을 수 없습니다."
BAD_QUERY = "고르기 값이 맞지 않습니다."


def _ok(data: Any) -> tuple[Any, int]:
    """성공 응답 — 사람마다 보이는 것이 달라 캐시하지 않는다."""
    response = jsonify({"success": True, "data": data, "error": None})
    response.headers["Cache-Control"] = "private, no-store"
    return response, 200


def _fail(status: int, error: str) -> tuple[Any, int]:
    """실패 응답(정한 글만)."""
    response = jsonify({"success": False, "data": None, "error": error})
    response.headers["Cache-Control"] = "private, no-store"
    return response, status


def _viewer() -> tuple[Optional[Viewer], Optional[tuple[Any, int]]]:
    """로그인 안 함 401 · 열 수 없는 사람 404 · 열 수 있으면 (Viewer, None)."""
    user = getattr(g, "current_user", None)
    if user is None:
        return None, _fail(401, "로그인이 필요합니다.")
    viewer = screen_viewer(user)
    if viewer is None:
        return None, _fail(404, NOT_FOUND)
    return viewer, None


def _read(build: Callable[[Any, Viewer], Any]) -> tuple[Any, int]:
    """권한 확인 → 읽기 → 읽기 트랜잭션 닫기. ``build`` 가 ``None`` 을 돌려주면 404."""
    viewer, denied = _viewer()
    if denied:
        return denied
    db = get_db()
    try:
        data = build(db, viewer)
    finally:
        db.rollback()  # 읽기만 — 트랜잭션을 닫는다
    return _ok(data) if data is not None else _fail(404, NOT_FOUND)


@brain_api_bp.route("/search", methods=["GET"])
def brain_search() -> tuple[Any, int]:
    """찾기(화면 1) — 유형별 묶음."""
    query = request.args.get("q", "")
    return _read(lambda db, viewer: search_grouped(db, viewer, query, today=get_today_kst()))


@brain_api_bp.route("/table", methods=["GET"])
def brain_table() -> tuple[Any, int]:
    """지식 표(화면 2) — 목록 밖 고르기 값은 400."""
    try:
        query = parse_table_query(request.args)
    except TableQueryError:
        viewer, denied = _viewer()  # 권한 없는 사람에게는 400 대신 404 · 401 그대로
        return denied if denied else _fail(400, BAD_QUERY)
    return _read(lambda db, viewer: table_page(db, viewer, query, today=get_today_kst()))


@brain_api_bp.route("/items/<path:key>", methods=["GET"])
def brain_item(key: str) -> tuple[Any, int]:
    """항목 카드(화면 3) — 볼 수 없거나 없으면 404(둘을 가르지 않는다)."""
    return _read(lambda db, viewer: item_card(db, viewer, key[:120], today=get_today_kst()))


@brain_api_bp.route("/type-map", methods=["GET"])
def brain_type_map() -> tuple[Any, int]:
    """유형 지도(화면 7)."""
    return _read(type_map)


@brain_api_bp.route("/releases", methods=["GET"])
def brain_releases() -> tuple[Any, int]:
    """판 목록(화면 6)."""
    page = request.args.get("page", type=int) or 1
    return _read(lambda db, viewer: release_page(db, viewer, page=page))


@brain_api_bp.route("/releases/<int:number>", methods=["GET"])
def brain_release_diff(number: int) -> tuple[Any, int]:
    """판 차이 요약(화면 6) — 볼 수 있는 바뀜이 없으면 404."""
    return _read(lambda db, viewer: release_diff(db, viewer, number))


@brain_api_bp.route("/around", methods=["GET"])
def brain_around() -> tuple[Any, int]:
    """이웃 찾기(화면 9 · 뇌 보기) — 꼴 밖 물음은 400(권한 없는 사람에게는 404 · 401 그대로)."""
    try:
        query = parse_around(request.args)
    except AroundQueryError:
        viewer, denied = _viewer()
        return denied if denied else _fail(400, BAD_QUERY)
    return _read(lambda db, viewer: search_around(db, viewer, query, today=get_today_kst()))


@brain_api_bp.route("/points", methods=["GET"])
def brain_points_api() -> tuple[Any, int]:
    """뇌 보기 바탕 점 — 볼 수 있는 · 유효 기간 안 항목만."""
    return _read(lambda db, viewer: brain_points(db, viewer, today=get_today_kst()))


@brain_api_bp.route("/quality", methods=["GET"])
def brain_quality() -> tuple[Any, int]:
    """연결 개수 규칙 품질 수 — 볼 수 있는 것만 센다."""
    return _read(lambda db, viewer: quality_counts(db, viewer, today=get_today_kst()))
