"""③ 사장님이 정해 주실 것 — 답 칸의 '바뀌는 곳'(설계서 docs/specs/2026-11-23-brain-learning-upgrade_SPEC.md 5.1) node 시험.

- 순수 계산(``ds-inbox-view.js`` textDiff): 같은 글 · 한 문장 덧붙임 · 가운데 문장 바꿈 · 통째 바꿈 · 크기 한도 · 빈칸과 줄 바꿈을
  지켜 'del' 을 뺀 조각을 이으면 저장할 글, 'add' 를 뺀 조각을 이으면 지금 글(여러 쌍).
- 화면(``test_brain_ds_inbox_js`` 의 가짜 DOM + 실제 새 템플릿): '바깥 글이 맞아요' 를 열면 바뀌는 곳이 보이고, 적으면 바뀌고,
  '둘 다 맞아요' 는 적은 한 줄을 들어가는 글로 보인다. 보내는 글(제안 → 승인 → 닫기)은 그대로다.
합성 자료만.
"""

from __future__ import annotations

from tests.domains.test_brain_ds_inbox_js import NODE, _node, _run, page  # noqa: F401 — page 는 fixture
from tests.domains.test_brain_fix_inbox_js import _card

NOW = "합성 선반 깊이는 350mm 입니다."
EXTRA = " 합성 손잡이는 없습니다."


def _parts(before: str, after: str) -> list[list[str]]:
    return [[p["kind"], p["text"]] for p in _node("v.textDiff(data[0], data[1])", [before, after])]


# ── 순수 계산 ─────────────────────────────────────────────────────────────
@NODE
def test_text_diff_marks_only_what_changes():
    assert _parts(NOW, NOW) == [["same", NOW]]
    assert _parts(NOW, NOW + "\n합성 벽 붙임은 두 줄이에요.") == [["same", NOW], ["add", "\n합성 벽 붙임은 두 줄이에요."]]
    before = "합성 상판은 한 장입니다. 합성 받침은 한 줄입니다. 합성 문짝은 둘입니다."
    after = "합성 상판은 한 장입니다. 합성 받침은 두 줄로 놓습니다. 합성 문짝은 둘입니다."
    assert _parts(before, after) == [["same", "합성 상판은 한 장입니다. 합성 받침은 "], ["del", "한 줄입니다."],
                                     ["add", "두 줄로 놓습니다."], ["same", " 합성 문짝은 둘입니다."]]
    # 바뀐 낱말 사이 빈칸은 바뀐 쪽에 넣어 한 덩어리로(빠짐 하나 + 들어감 하나)
    assert _parts("가나 다라 마바", "사아 자차 카타") == [["del", "가나 다라 마바"], ["add", "사아 자차 카타"]]
    assert _parts("", "새 글") == [["add", "새 글"]] and _parts("옛 글", "") == [["del", "옛 글"]] and _parts("", "") == []


@NODE
def test_text_diff_shows_a_moved_sentence_once_not_as_removed_and_added():
    """어긋난 문장을 빼고 뒤에 붙인 글(outsideDraft 의 꼴) — 그대로 남는 문장이 '빠짐 + 들어감'으로 두 번 보이지 않는다.
    빈칸 조각을 낱말처럼 세면 빈칸이 많이 겹치는 쪽으로 맞춰 남는 문장까지 바뀐 것으로 보였다(11-23 실화면)."""
    head = "합성 선반 깊이는 350mm 입니다. 합성 "
    got = _parts(head + "받침은 한 줄로 넣습니다. 합성 손잡이는 푸쉬가 기본입니다.",
                head + "손잡이는 푸쉬가 기본입니다. 합성 받침은 두 줄로 넣어 드립니다.")
    assert got == [["same", head], ["del", "받침은 한 줄로 넣습니다. 합성 "], ["same", "손잡이는 푸쉬가 기본입니다."],
                   ["add", " 합성 받침은 두 줄로 넣어 드립니다."]]


@NODE
def test_text_diff_size_guard_falls_back_to_whole_text_but_keeps_shared_ends():
    limit = _node("v.DIFF_MAX")
    many = " ".join(f"합성{i}" for i in range(limit + 50))
    flipped = " ".join(f"합성{i}" for i in reversed(range(limit + 50)))
    assert _parts(many, flipped) == [["del", many], ["add", flipped]]  # 한도를 넘으면 낱말을 견주지 않는다
    # 앞뒤가 같은 긴 글은 같은 곳을 떼고 견준다 — 긴 지식 글에 한 줄 덧붙여도 들어가는 줄만 보인다
    assert _parts(many, many + "\n덧붙인 줄") == [["same", many], ["add", "\n덧붙인 줄"]]
    middle = many.replace("합성300 ", "합성삼백 ")
    assert _parts(many, middle) == [["same", many[:many.index("합성300 ")]], ["del", "합성300"], ["add", "합성삼백"],
                                    ["same", many[many.index("합성300 ") + len("합성300"):]]]


@NODE
def test_text_diff_keeps_every_space_and_line_break():
    pairs = [
        (NOW, NOW + EXTRA),
        ("  앞 빈칸\n\n두 줄 띄움  ", "앞 빈칸\n한 줄 띄움 끝\t"),
        ("첫 줄\r\n둘째 줄\n", "첫 줄\n둘째 줄\r\n셋째 줄"),
        ("가 나 다 라 마", "마 라 다 나 가"),
        ("같은 말 같은 말 같은 말", "같은 말 다른 말 같은 말 같은 말"),
        ("", "  \n"), ("\n", ""),
    ]
    got = _node("data.map(p => { const d = v.textDiff(p[0], p[1]);"
                " return [d.filter(x => x.kind !== 'del').map(x => x.text).join(''),"
                " d.filter(x => x.kind !== 'add').map(x => x.text).join(''),"
                " d.every((x, i) => x.text && (!i || d[i - 1].kind !== x.kind))]; })", [list(p) for p in pairs])
    for (before, after), (joined_after, joined_before, tidy) in zip(pairs, got):
        assert joined_after == after and joined_before == before and tidy, (before, after)


# ── 화면 ──────────────────────────────────────────────────────────────────
#: 적는 동안 기다림은 바로 부른다 · 고침 제안에 번호를 돌려준다(바탕 가짜 fetch 는 번호를 주지 않는다).
BEFORE = """
  window.setTimeout = function (fn) { fn(); return 1; };
  window.clearTimeout = function () {};
  const plain = fetch;
  fetch = async function (url, init) {
    const res = await plain(url, init);
    if (init && init.method === 'POST' && url === '/api/brain/proposals') {
      return { status: 200, json: async () => ({ success: true, data: { change_id: 777 } }) };
    }
    return res;
  };"""
LOOK = """
  const card = api.q('[data-ds-inbox-cards] [data-card-id="c1"]');
  const look = kind => {
    const area = card.querySelector('[data-ds-answer-change="' + kind + '"]');
    const line = area.querySelector('.fb-change__text');
    return { shown: api.shown(area), text: api.text(area),
             parts: line ? line.children.map(n => [n.tagName, n.className, n.textContent]) : [] };
  };
  const type = (kind, value) => {
    const input = card.querySelector('[data-ds-answer-text="' + kind + '"]');
    input.value = value;
    input.dispatchEvent({ type: 'input' });
  };"""
LEGEND = "바뀌는 곳 — 빨간 줄 그은 글은 빠지고, 초록 밑줄 글이 들어가요"


def _question(sentence: str) -> dict:
    card = _card(1, "decide")
    card["main"]["sentence"] = sentence
    card["main"]["about"] = [{"key": "common/shelf", "title": "합성 선반", "text": NOW, "version": 3}]
    return card


def _answer(page, tmp_path, body: str) -> dict:
    return _run(page("/brain?tab=inbox&bin=decide"), LOOK + body, cards=[_question(NOW + EXTRA)],
                search="?tab=inbox&bin=decide", before=BEFORE, tmp=tmp_path)


@NODE
def test_outside_box_shows_what_changes_and_follows_typing(page, tmp_path):
    body = """
      const closed = look('outside').shown;
      await api.click(card.querySelector('[data-ds-answer="outside"]'));
      const opened = look('outside');
      type('outside', '합성 선반 깊이는 400mm 입니다. 합성 손잡이는 없습니다.');
      const typed = look('outside');
      type('outside', '""" + NOW + """');
      const same = look('outside');
      type('outside', '합성 선반 깊이는 400mm 입니다.');
      await api.click(card.querySelector('[data-ds-answer="outside-save"]'));
      return { closed: closed, opened: opened, typed: typed, same: same, posts: api.posts };"""
    got = _answer(page, tmp_path, body)
    assert got["closed"] is False
    assert got["opened"]["shown"] is True and got["opened"]["text"].startswith(LEGEND)
    assert got["opened"]["parts"] == [["SPAN", "fb-change__same", NOW], ["INS", "fb-change__add", EXTRA]]
    assert got["typed"]["parts"] == [
        ["SPAN", "fb-change__same", "합성 선반 깊이는 "], ["DEL", "fb-change__del", "350mm"], ["INS", "fb-change__add", "400mm"],
        ["SPAN", "fb-change__same", " 입니다."], ["INS", "fb-change__add", EXTRA]]
    assert got["same"] == {"shown": True, "text": "아직 바뀌는 곳이 없어요.", "parts": []}
    new = "합성 선반 깊이는 400mm 입니다."
    assert got["posts"] == [  # 보내는 글은 지금과 같다 — 고침 제안 → 바로 승인 → 질문 닫기
        {"url": "/api/brain/proposals", "body": {"action": "propose_edit", "key": "common/shelf", "base_version": 3,
                                                  "after": {"text": new}, "reason": "사장님 답 — 바깥 글이 맞아요"}},
        {"url": "/api/brain/proposals/777/apply",
         "body": {"base_version": 3, "view_ms": 0, "confirm": {"field": "text", "value": new}}},
        {"url": "/api/brain/proposals/10/reject", "body": {"code": "outside_right", "view_ms": 0}}]


@NODE
def test_both_box_shows_the_new_line_as_added_at_the_end(page, tmp_path):
    body = """
      await api.click(card.querySelector('[data-ds-answer="both"]'));
      const label = api.text(card.querySelector('[data-ds-answer-box="both"] .f-label'));
      const empty = look('both');
      type('both', '  합성 벽 붙임은 두 줄이에요. ');
      const typed = look('both');
      const other = look('outside').shown;
      await api.click(card.querySelector('[data-ds-answer="both-save"]'));
      return { label: label, empty: empty, typed: typed, other: other, posts: api.posts };"""
    got = _answer(page, tmp_path, body)
    assert got["label"] == "손님에게 안내할 문장으로 적어요 — 지식 글 끝에 붙어요"
    assert got["empty"] == {"shown": True, "text": "아직 바뀌는 곳이 없어요.", "parts": []}
    assert got["typed"]["parts"] == [["SPAN", "fb-change__same", NOW], ["INS", "fb-change__add", "\n합성 벽 붙임은 두 줄이에요."]]
    assert got["other"] is False  # 고른 답의 칸만
    new = NOW + "\n합성 벽 붙임은 두 줄이에요."
    assert got["posts"] == [
        {"url": "/api/brain/proposals", "body": {"action": "propose_edit", "key": "common/shelf", "base_version": 3,
                                                  "after": {"text": new}, "reason": "사장님 답 — 둘 다 맞아요"}},
        {"url": "/api/brain/proposals/777/apply",
         "body": {"base_version": 3, "view_ms": 0, "confirm": {"field": "text", "value": new}}},
        {"url": "/api/brain/proposals/10/reject", "body": {"code": "both_right", "view_ms": 0}}]
