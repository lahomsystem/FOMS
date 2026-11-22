"""옛 보드(태블릿 칸반 · 옆 시트) 단추 = 생산 API 와 같은 두 함수(설계서 2026-11-21-production-pc-viewer §13 결정 2 · 5).

- 열 이동 단추 · 옆 시트 쓰기 단추(공정 칸 · 불량 알리기 · 보류 · 제작 시작/취소/완료 · 완료 취소 · 수정 제작)는 쓰기 팀
  (관리자 · 생산팀, ``can_write_production``)에게만. CS · 영업 · 도면은 누르면 403 이 될 단추를 받지 않는다.
- [확인](change-ack — 묘비 카드 · 변경 브리핑 줄 · 옆 시트 [변경 확인])은 생산 화면을 보는 사람 모두(``can_ack_production_change``).
  음성 대조 = 팀 없는 직원 · 조회 전용(VIEWER)은 [확인]도 없다.
- 쓰기 팀 출력은 판정 태그가 생기기 전 템플릿(판정 태그만 뗀 것)과 바이트까지 같다.
모든 이름 · 번호는 가짜 값이다.
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path

import pytest
from jinja2 import ChoiceLoader, DictLoader
from werkzeug.security import generate_password_hash

from db import db_session
from models import ProductionRun, User
from tests.domains.test_confirm_to_production_board import _make_order as _board_order
from tests.domains.test_production_home_changes import _date_changed
from tests.domains.test_production_home_changes import _order as _changed_order
from tests.domains.test_production_home_tabs import _add_order
from tests.support.production_home_step_panel_seed import TABLET, set_cookies

ROOT = Path(__file__).resolve().parents[2]
BOARD = "/erp/production/dashboard"
KANBAN_TPL = "production/partials/tablet_kanban_body.html"
SHEET_TPL = "production/partials/tablet_sheet.html"

#: 판정 태그를 떼는 표(구체적인 것 먼저). 이 표로 뗀 글 = 판정이 생기기 전 템플릿(주석 밖 글자가 같다).
_UNGATE = {
    KANBAN_TPL: (
        ("{% if can_ack_production %}", ""),
        ("{% if can_act_production %}", ""),
        ("</button>{% endif %}", "</button>"),
    ),
    SHEET_TPL: (
        ('>{% else %}<div class="foms-prod-page__step is-view{% if s.done %} is-done{% elif s.now %} is-now{% endif %}">'
         "{% endif %}", ">"),
        ("{% if can_act_production %}</button>{% else %}</div>{% endif %}", "</button>"),
        ("{% if can_ack_production %}", ""),
        ("{% if can_act_production %}", ""),
        ("</button>{% endif %}", "</button>"),
        ("</div>{% endif %}\n    </div>", "</div>\n    </div>"),
        ("</div>{% endif %}\n</div>", "</div>\n</div>"),
    ),
}
#: 판정 태그 수 — (can_act_production, can_ack_production). 태그를 더하거나 빼면 이 표와 _UNGATE 를 같이 고친다.
_GATE_COUNTS = {KANBAN_TPL: (3, 3), SHEET_TPL: (4, 1)}


def _source(name: str) -> str:
    return (ROOT / "templates" / name).read_text(encoding="utf-8")


def ungate(src: str, name: str = SHEET_TPL) -> str:
    """판정 태그(can_act_production · can_ack_production)를 뗀 템플릿 글 — 쓰기 팀이 받던 옛 출력의 템플릿."""
    for old, new in _UNGATE[name]:
        src = src.replace(old, new)
    return src


def _code(src: str) -> str:
    return re.sub(r"\{#.*?#\}", "", src, flags=re.S)


@pytest.fixture
def board(monkeypatch):
    """태블릿 가로(칸반이 그려지는 조건) + 칸 셋(제작 시작 · 제작 완료 · 수정 제작) + 바뀐 주문 + 묘비."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")
    wait = _add_order("PRODUCTION", "가짜대기", 4)  # 생산 단계 · 회차 없음 = 제작 대기(승인 끝 · 도면 막힘 없음)
    making = _add_order("PRODUCTION", "가짜만드는중", 2, steps_done=("cut",), with_run=True)
    done = _board_order("CONSTRUCTION")
    changed = _changed_order("PRODUCTION", "가짜바뀜", 3, run=True)
    _date_changed(changed, datetime.timedelta(hours=2), None)
    _add_order("PRODUCTION", "가짜취소됨", 2, deleted=True)
    return {"wait": wait.id, "making": making.id, "done": done.id, "changed": changed.id}


def _login(client, role: str, team: str | None, name: str) -> None:
    user = User(username=f"ob_{name}", password=generate_password_hash("pw"), role=role, team=team, name=f"가짜{name}",
                is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, user.role
    set_cookies(client, TABLET)


def _get(client, path: str) -> str:
    resp = client.get(path)
    assert resp.status_code == 200, (path, resp.status_code)
    return resp.get_data(as_text=True)


def _kanban(html: str) -> str:
    """칸반 몸통(열 · 카드 · 변경 브리핑 · 단추 배선 묶음) — 페이지 머리 · 시각 글은 뺀다."""
    start = html.index('<section class="foms-kanban"')
    return html[start:html.index("foms-admin-override.js", start)]


def _pages(client, ids: dict) -> dict[str, str]:
    pages = {"board": _kanban(_get(client, BOARD))}
    for key, oid in ids.items():
        pages[key] = _get(client, f"/erp/production/tablet-sheet/{oid}")
    return pages


# --------------------------------------------------------------------------- #
# 판정 태그 표 — 뗀 글에 판정 이름이 남지 않는다
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", [KANBAN_TPL, SHEET_TPL])
def test_판정_태그_수와_뗀_글(name) -> None:
    src = _code(_source(name))
    act, ack = _GATE_COUNTS[name]
    assert src.count("{% if can_act_production %}") == act and src.count("{% if can_ack_production %}") == ack
    plain = ungate(src, name)
    assert "can_act_production" not in plain and "can_ack_production" not in plain and "is-view" not in plain


# --------------------------------------------------------------------------- #
# 쓰기 팀 — 바이트까지 그대로
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("role,team", [("ADMIN", "CS"), ("STAFF", "PRODUCTION"), ("MANAGER", "PRODUCTION")])
def test_쓰기_팀_출력은_판정_태그를_뗀_템플릿과_바이트까지_같다(app, client, monkeypatch, board, role, team) -> None:
    _login(client, role, team, f"w_{role}_{team}")
    now = _pages(client, board)
    assert now == _pages(client, board)  # 같은 요청 두 번 = 같은 바이트(대조가 뜻이 있다)
    # 양성 대조 — 쓰기 단추 · [확인]이 실제로 그려진 화면을 견준다
    assert all(f'data-kanban-action="{a}"' in now["board"] for a in ("start", "complete", "rework", "change-ack"))
    assert "data-prod-change-row-ack" in now["board"]
    assert 'data-tablet-sheet-action="production-start"' in now["wait"]
    assert 'data-tablet-sheet-action="production-complete"' in now["making"]
    assert 'data-tablet-sheet-action="production-rework"' in now["done"]
    assert 'data-foms-sheet-step="cut"' in now["making"] and "data-foms-sheet-defect-toggle" in now["making"]
    assert "변경 확인</button>" in now["changed"]

    plain = {name: ungate(_source(name), name) for name in (KANBAN_TPL, SHEET_TPL)}
    monkeypatch.setattr(app.jinja_env, "loader", ChoiceLoader([DictLoader(plain), app.jinja_env.loader]))
    app.jinja_env.cache.clear()
    try:
        before = _pages(client, board)
    finally:
        app.jinja_env.cache.clear()
    for key in now:
        assert now[key] == before[key], key


# --------------------------------------------------------------------------- #
# 보기 팀 — 쓰기 단추 없음, [확인]은 있음
# --------------------------------------------------------------------------- #
WRITE_MARKS = ('data-kanban-action="start"', 'data-kanban-action="complete"', 'data-kanban-action="rework"',
               "data-tablet-sheet-action=", "data-foms-sheet-step=", "data-foms-sheet-defect-toggle",
               "data-foms-sheet-defect-reason=", 'class="foms-prod-sheet__foot"')


@pytest.mark.parametrize("team", ["CS", "ACCOUNTING", "SALES", "DRAWING", "SHIPMENT"])
def test_보기_팀은_쓰기_단추가_없고_확인은_있다(client, board, team) -> None:
    _login(client, "STAFF", team, f"v_{team}")
    pages = _pages(client, board)
    for key, html in pages.items():
        for mark in WRITE_MARKS:
            assert mark not in html, (team, key, mark)
    # [확인] — 묘비 카드 · 변경 브리핑 줄 · 옆 시트 [변경 확인](§13 결정 5)
    assert 'data-kanban-action="change-ack"' in pages["board"] and "data-prod-change-row-ack" in pages["board"]
    assert "변경 확인</button>" in pages["changed"]
    # 공정 칸은 보기만으로(누가 · 언제 글은 그대로)
    assert pages["making"].count('<div class="foms-prod-page__step is-view') == 4
    assert '<div class="foms-prod-page__step is-view is-done">' in pages["making"]
    # 칸반 카드 · 시공일 칩 · 막힘 이유 같은 보기 글은 그대로
    assert pages["board"].count('class="foms-kanban-card"') + pages["board"].count('class="foms-kanban-card ') >= 3


@pytest.mark.parametrize("role,team", [("STAFF", None), ("VIEWER", "CS")])
def test_생산_화면을_못_보는_사람은_확인도_없다(client, board, role, team) -> None:
    """음성 대조 — 옛 보드는 로그인만 되면 열리지만, 팀 없는 직원 · 조회 전용은 [확인]을 누르면 403 이라 안 그린다."""
    _login(client, role, team, f"n_{role}_{team}")
    pages = _pages(client, board)
    for key, html in pages.items():
        assert not any(mark in html for mark in WRITE_MARKS), (role, key)
        assert 'data-kanban-action="change-ack"' not in html and "data-prod-change-row-ack" not in html, (role, key)
    assert "변경 확인</button>" not in pages["changed"]
    run = db_session.query(ProductionRun).filter_by(order_id=board["making"]).count()
    assert run == 1  # 보기만 — 아무것도 바뀌지 않았다
