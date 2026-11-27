"""도면 카드 [작업 시작] → [<파트> 시작] (사장님 2026-11-27 "재단 탭 = 재단 시작, 엣지 탭 = 엣지 시작 ....이런식으로 텍스트 변경해").

* 카드 단추(서버 home_parts.html pp_act · JS crew.render · 크게 보기는 카드 단추를 복사)가 파트 탭마다 [재단 시작] · [엣지 시작] ·
  [조립 시작] · [검수 시작]. 파트 이름은 완료 단추 [<파트> 완료]와 같은 낱말 원본(``PRODUCTION_PART_LABELS`` → 판 ``part_label`` → JS cfg.label).
* 같은 단추가 여는 창: 제목 "엣지 시작할까요?" · 실행 단추 [엣지 시작] · 끝난 뒤 알림 "엣지 시작했어요"(누른 단추 말 그대로).
* 그대로인 것(대조군): [같이 작업] · [시작 취소] · [기본] · 서버 넘김 글 · 작업 시트 바뀐 기록 낱말('작업 시작').
"""
from __future__ import annotations

from pathlib import Path

import pytest

from foms.services.production.part_constants import PRODUCTION_PART_LABELS
from tests.domains.test_production_multi_holder_board import _act, _card, _node, _page, _post, cohort  # noqa: F401
from tests.support.production_factory_seed import HOME_NONE
from tests.support.production_part_claim_seed import make_order, make_user

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "static/js/production"
TPL = ROOT / "templates/production/partials/home_parts.html"
PARTS = (("cut", "재단"), ("edge", "엣지"), ("assemble", "조립"), ("inspect", "검수"))


def test_labels_come_from_the_one_part_name_source():
    assert tuple(PRODUCTION_PART_LABELS.items()) == PARTS  # 새 상수 없이 완료 단추와 같은 원본


@pytest.mark.parametrize("part,label", PARTS)
def test_part_account_board_says_part_start(client, cohort, part, label):
    # 검수는 앞 파트가 모두 끝나야 열린다(검수 전 칸) — 앞 세 칸을 켜 둔 주문으로 잰다
    order = make_order(2, steps_done=("cut", "edge", "assemble") if part == "inspect" else ())
    act = _act(_card(_page(client, make_user(f"가짜{label}", part=part)), order.keys[0]))
    assert f'data-pp-act="take">{label} 시작</button>' in act
    assert ">작업 시작<" not in act  # 옛 글 없음
    others = [lb for _, lb in PARTS if lb != label]
    assert not any(f">{lb} 시작<" in act for lb in others)  # 음성 대조 — 다른 파트 이름을 쓰지 않는다


def test_lead_and_admin_boards_say_picked_part_start(client, cohort):
    order = make_order(2)
    lead = make_user("박반장", lead=True)
    edge = _act(_card(_page(client, lead, HOME_NONE + "&tab=parts&part=edge"), order.keys[0]))
    assert 'data-pp-act="take">엣지 시작</button>' in edge and 'data-pp-act="check">엣지 완료</button>' in edge
    cut = _act(_card(_page(client, make_user("관리", team="CS", role="ADMIN"), HOME_NONE + "&tab=parts&part=cut"), order.keys[0]))
    assert 'data-pp-act="basic">기본</button>' in cut and 'data-pp-act="take">재단 시작</button>' in cut  # [기본]은 그대로
    view = _act(_card(_page(client, make_user("상담", team="CS"), HOME_NONE + "&tab=parts&part=cut"), order.keys[0]))
    assert "<button" not in view  # 보기만 = 단추 없음(그대로)


def test_js_redraw_window_and_notice_use_the_same_word(client, cohort, tmp_path):
    order = make_order(3, run=False)  # 첫 카드 = 제작 시작도 같이
    me = make_user("박엣지", part="edge")
    page = tmp_path / "edge.html"
    page.write_text(_page(client, me), encoding="utf-8")
    took = _post(client, me, {"order_id": order.id, "drawing_key": order.keys[0], "part": "edge", "action": "take",
                              "seen": "none", "seen_me": "none"})
    assert took["success"] is True and took["data"]["run_started"] is True
    res = _node(page, {"posts": [took], "steps": [
        {"do": "parity"}, {"do": "click", "key": order.keys[0], "act": "take"}, {"do": "run"}, {"do": "card", "key": order.keys[1]}]})
    out = res["out"]
    assert out[0]["cards"] == 3 and out[0]["diffs"] == []  # 서버 칸 = JS 가 다시 그린 칸([엣지 시작] 포함)
    w = out[1]["modal"]
    assert (w["title"], w["run"]["text"], w["line"]) == ("엣지 시작할까요?", "엣지 시작", "→ 작업 중 · 박엣지")
    assert w["body"] == "이 주문 첫 도면이라 제작 시작도 같이 돼요."  # 제작 시작 한 줄은 그대로
    assert out[2]["status"] == "엣지 시작했어요 · 제작 시작도 같이 됐어요" and out[2]["modal"]["hidden"] is True
    act = out[3]["card"]["act"]
    assert act == [{"tag": "button", "cls": "foms-prod-home__btn pp-act", "act": "take", "text": "엣지 시작", "kids": []}]


def test_source_contract_start_words_and_untouched_words():
    crew = (JS / "foms-production-parts-crew.js").read_text(encoding="utf-8")
    modal = (JS / "foms-production-parts-modal.js").read_text(encoding="utf-8")
    parts = (JS / "foms-production-parts.js").read_text(encoding="utf-8")
    tpl = TPL.read_text(encoding="utf-8")
    assert tpl.count('data-pp-act="take">{{ pb.part_label }} 시작</button>') == 3 and 'data-pp-act="take">작업 시작<' not in tpl
    assert "LABEL + ' 시작', 'take')" in crew and "'작업 시작', 'take'" not in crew
    assert "title: LABEL + ' 시작할까요?'" in modal and "run: LABEL + ' 시작'" in modal and "작업을 시작할까요" not in modal
    # 알림 = 누른 단추 말 + 했어요("엣지 시작했어요") — 정규식이 '시작'으로 끝나는 단추를 그대로 받는다
    assert "/(완료|시작|취소)$/.test(p.run || '')) ? p.run + '했어요'" in parts
    # 대조군 — 사장님이 말하지 않은 단추 · 글은 그대로
    assert "'같이 작업', 'join'" in crew and 'data-pp-act="release">시작 취소</button>' in tpl
    assert "run: '시작 취소'" in modal and "'같이 작업': '같이 작업 시작했어요'" in parts
    sheet = (JS / "foms-production-sheet-parts.js").read_text(encoding="utf-8")
    assert "take: '작업 시작'" in sheet  # 작업 시트 바뀐 기록 낱말(기록 글)은 그대로
    viewer = (JS / "foms-production-parts-viewer.js").read_text(encoding="utf-8")
    assert "copy = el.cloneNode(true)" in viewer and "시작" not in viewer  # 크게 보기는 카드 단추를 복사(글을 따로 짓지 않음)
