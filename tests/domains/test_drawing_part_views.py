"""도면 마법사 — 탑뷰 · 사이드뷰 분류(node 로 돌린다 · 서버 검사).

사용자 요청(2026-10-28): '탑뷰, 사이드뷰 등의 분류도 만들어'(종류 확인 칸에 들어간 위에서 본 그림). 같은 날 질문 창 결정:
탑뷰는 새로 만들어 시트의 '평면·상판' 칸에 같이, 사이드뷰는 정면 그림 칸에 같은 배율로, 둘만 먼저.
AI 머리(part-head.json)는 아직 두 분류를 몰라 숫자키 없이 종류 칸 · '그 밖 ▾'에서 고르고, 고른 그림은 기억(part-memory)이 따른다.
"""
from __future__ import annotations

from foms.api.drawing import wizard as wizard_api
from tests.domains.test_drawing_wizard_v2_layout import ARRANGE
from tests.domains.test_drawing_wizard_v2_layout import _run as _run_layout


def test_server_accepts_top_and_side_views_only_from_the_closed_list():
    for label in ("탑뷰", "사이드뷰"):
        assert wizard_api._validate_part({"label": label, "src": "user"}) is None
        assert wizard_api._validate_part({"label": "미분류", "src": "ai", "ai": label, "conf": 0.4}) is None
    assert wizard_api._validate_part({"label": "옆면", "src": "user"}) == "그림 종류 값이 올바르지 않습니다."


def test_v2_puts_side_view_with_fronts_at_same_scale_and_top_view_in_plan_cell():
    out = _run_layout(ARRANGE + r"""
require(dir + '/v2-check.js');
const sh = { id: 's1', form: {}, objects: [upload('f1', '정면·내부', 1600, 1100, 0), upload('s1', '사이드뷰', 700, 1100, 1),
  upload('t1', '탑뷰', 1500, 600, 2), upload('d1', '서랍 단면', 500, 400, 3), upload('p1', '평면·상판', 1300, 500, 4)] };
const r = arrange(sh), g = r.plan.g, sc = id => find(sh, id).h / find(sh, id).natural_h;
out.slots = { main: g.main.map(o => o.id).sort(), plan: g.plan.map(o => o.id).sort() };
out.same = Math.abs(sc('f1') - sc('s1')) < 0.01;
out.titles = [S.title('main', g, false), S.title('plan', g, false)];
out.kitchen = [S.slotOf('사이드뷰', true), S.slotOf('탑뷰', true)];
out.overlaps = overlaps(sh);
const c = window.FomsV2Check.choices({ id: 'x', part: { label: '미분류', src: 'ai', ai: '평면·상판', conf: 0.4 } }, { guess: {} }, false);
out.choices = [c.quick, c.rest];
const G = window.FomsPartLayout.groups([{ id: 't', label: '탑뷰', nw: 1500, nh: 600 }, { id: 's', label: '사이드뷰', nw: 700, nh: 1100 },
  { id: 'f', label: '정면·내부', nw: 1600, nh: 1100 }]);
out.v1 = { plan: G.plan.map(i => i.id), main: G.main.map(i => [i.id, i.kind]) };
""")
    assert out["slots"] == {"main": ["f1", "s1"], "plan": ["p1", "t1"]}
    assert out["same"] and out["overlaps"] == []                         # 사이드뷰는 정면과 같은 배율(높이를 바로 견준다)
    assert out["titles"] == ["정면 · 사이드뷰", "탑뷰 · 평면 · 상판"]    # 칸 이름은 든 그림 종류로
    assert out["kitchen"] == ["main", "plan"]                            # 주방도 사이드뷰는 정면 칸
    quick, rest = out["choices"]
    assert quick[:2] == ["평면·상판", "탑뷰"] and "사이드뷰" in rest      # AI 가 평면·상판이라 짐작하면 탑뷰를 바로 옆에
    assert out["v1"] == {"plan": ["t"], "main": [["s", "front"], ["f", "front"]]}   # 예전 화면 자동 배치도 같은 칸
