"""생산 화면 Blueprint(``erp_production_page``)와 템플릿 전역 셋 — 생산 페이지 라우트가 모두 이 Blueprint 에 붙는다.

옛 생산 보드 파일(``dashboard.py``)에 있던 것을 그대로 옮겼다(설계서 2026-11-27-production-legacy-board-removal §6-2).
옛 보드(``/erp/production/dashboard``) · 옛 태블릿 옆 시트는 라우트째 지웠다(§0-1-3, 404).

라우트는 ``home.py``(첫 화면 · 작업 시트 · 인쇄) · ``part_thumb.py``(도면 카드 작은 그림)가 더한다.
``foms/web/production/__init__.py`` 가 두 모듈을 import 해야 라우트가 붙는다.
"""
from __future__ import annotations

from flask import Blueprint, g

from foms.services.production.nav_target import production_nav_href
from foms.services.production.steps import PRODUCTION_FINISHED_STAGE
from foms.services.production.write_access import can_write_production

erp_production_page_bp = Blueprint(
    'erp_production_page', __name__, url_prefix='/erp'
)


@erp_production_page_bp.app_template_global('production_nav_href')
def _production_nav_href() -> str:
    """생산 메뉴 칸 주소(템플릿 전역) — PC 둘째 줄 메뉴 · 폰 아래 메뉴가 부른다. 늘 첫 화면, 판정은 레일 · 바로가기와
    같은 한 곳(:func:`foms.services.production.nav_target.production_nav_href`, 설계서 2026-11-21-production-pc-viewer §9)."""
    return production_nav_href(getattr(g, 'current_user', None))


@erp_production_page_bp.app_template_global('production_work_user')
def _production_work_user() -> bool:
    """지금 사용자가 생산 쓰기 팀(관리자 · 생산팀)인지(템플릿 전역) — 셸 스크립트 태그의 data-foms-production-work.
    erp-shell.js 가 생산 첫 화면 50초 하트비트를 일터인 사람에게만 돌릴 때 쓴다(:func:`can_write_production` 와 같은 판정, 11-22)."""
    return can_write_production(getattr(g, 'current_user', None))


# 첫 화면 큰 글자 '검수 완료'(템플릿 전역 — 날짜 줄 · PC 줄 매크로가 글자 그대로 견준다, 정본 steps.py 한 곳 —
# 설계서 2026-11-25-production-multi-holder §8-2 40). 파이썬 쪽 견주는 곳도 같은 상수를 쓴다.
erp_production_page_bp.add_app_template_global(PRODUCTION_FINISHED_STAGE, 'PRODUCTION_FINISHED_STAGE')

__all__ = ["erp_production_page_bp"]
