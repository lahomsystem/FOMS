"""③ 질문 카드 — 카드가 생긴 뒤 지식이 바뀌었으면 바깥 글을 미리 붙이지 않는다(결함 2026-11-27) node 시험.

엇갈림 카드의 바깥 글은 카드가 생긴 밤의 글 그대로다. 그 뒤 지식이 고쳐졌는데 '바깥 글이 맞아요' 칸에 바깥 글을 붙여 미리 채우면
걷어낸 옛 내용이 다시 들어간다(운영 — 한 지식 안에 다른 값 문장 둘).

- (가) 서버가 ``about.changed_since`` 참을 주면 칸에는 지금 지식 글만 · 칸 위 도움 글 자리에 알림 한 줄(새 칩 · 상자 · 단추 없음).
  고치지 않고 누르면 '바뀐 글이 없어요'(그대로 저장하지 않는다).
- (나) 거짓 · 칸 없음(옛 서버)이면 예전 그대로 — 미리 채운 글이 ``outsideDraft`` 와 글자까지 같다 · 어긋난 구절을 못 찾은
  경우의 도움 글도 그대로.
- '둘 다 맞아요' 칸은 비어서 열리고 서버가 지금 글 끝에 붙이므로 옛 내용이 저절로 들어가지 않는다 — 알림 줄을 넣지 않는다.
합성 자료만.
"""

from __future__ import annotations

import pytest

from tests.domains.test_brain_ds_inbox_change_js import BEFORE
from tests.domains.test_brain_ds_inbox_js import NODE, _node, _run, page  # noqa: F401 — page 는 fixture
from tests.domains.test_brain_fix_inbox_js import _card

NOW_TEXT = "합성 선반 깊이는 350mm 입니다. 합성 손잡이는 없습니다."
CLASH = "어긋남 — 회사 지식 「350mm」 ↔ 직원 「400mm」\n합성 선반 깊이는 400mm 입니다."
LOST = "합성 선반 깊이는 400mm 입니다."  # 머리줄 없음 — 어긋난 구절을 못 찾는다(mixed)
STALE = "이 카드가 생긴 뒤 지식이 바뀌었어요 — 지금 글을 보고 고칠 곳만 고쳐 주세요."
MIXED = "지금 글 뒤에 바깥 글을 붙였어요 — 틀린 옛 문장은 지워 주세요."
LOOK = """
  const card = api.q('[data-ds-inbox-cards] [data-card-id="c1"]');
  const helps = kind => card.querySelector('[data-ds-answer-box="' + kind + '"]').children
    .filter(n => n.className === 'f-help').map(n => n.textContent);
  await api.click(card.querySelector('[data-ds-answer="outside"]'));
  const outside = { value: card.querySelector('[data-ds-answer-text="outside"]').value, helps: helps('outside') };
  await api.click(card.querySelector('[data-ds-answer="both"]'));
  const both = { value: card.querySelector('[data-ds-answer-text="both"]').value, helps: helps('both'),
                 text: api.text(card.querySelector('[data-ds-answer-box="both"]')) };"""


def _question(sentence: str, changed) -> dict:
    card = _card(1, "decide")
    card["main"]["sentence"] = sentence
    about = {"key": "common/shelf", "title": "합성 선반", "text": NOW_TEXT, "version": 3}
    if changed is not None:
        about["changed_since"] = changed
    card["main"]["about"] = [about]
    return card


def _open(page, tmp_path, sentence: str, changed, extra: str = "") -> dict:
    body = LOOK + extra + "\n  return { outside: outside, both: both, posts: api.posts, status: api.text(card.querySelector('[data-ds-prop-status]')) };"
    return _run(page("/brain?tab=inbox&bin=decide"), body, cards=[_question(sentence, changed)],
                search="?tab=inbox&bin=decide", before=BEFORE, tmp=tmp_path)


@NODE
@pytest.mark.parametrize("sentence", [CLASH, LOST])
def test_changed_card_fills_only_the_current_text_and_says_so(page, tmp_path, sentence):
    save = """
  await api.click(card.querySelector('[data-ds-answer="outside"]'));
  await api.click(card.querySelector('[data-ds-answer="outside-save"]'));"""
    got = _open(page, tmp_path, sentence, True, save)
    assert got["outside"] == {"value": NOW_TEXT, "helps": [STALE]}  # 바깥 글을 붙이지 않는다 · 섞음 알림 대신 이 한 줄
    assert "400mm" not in got["outside"]["value"]
    assert got["both"]["value"] == "" and STALE not in got["both"]["text"]  # '둘 다 맞아요' 칸은 그대로
    assert got["posts"] == [] and got["status"] == "바뀐 글이 없어요 — 글을 적어 주세요."  # 고치지 않으면 저장하지 않는다


@NODE
@pytest.mark.parametrize("changed", [False, None])
def test_unchanged_card_fills_exactly_as_before(page, tmp_path, changed):
    want_clash, want_lost = _node("[v.outsideDraft(data[0], data[2]), v.outsideDraft(data[1], data[2])]",
                                  [CLASH, LOST, NOW_TEXT])
    assert want_clash == {"text": "합성 손잡이는 없습니다. 합성 선반 깊이는 400mm 입니다.", "mixed": False}
    assert want_lost["mixed"] is True
    clash = _open(page, tmp_path, CLASH, changed)
    assert clash["outside"] == {"value": want_clash["text"], "helps": []}  # 글자까지 같다
    lost = _open(page, tmp_path, LOST, changed)
    assert lost["outside"] == {"value": want_lost["text"], "helps": [MIXED]}
    assert STALE not in clash["both"]["text"] and STALE not in lost["both"]["text"]
