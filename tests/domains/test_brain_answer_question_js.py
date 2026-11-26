"""③ 질문 카드 답 한 번에 저장 — 화면 스크립트(설계서 2026-11-26 온톨로지 잇기 3.2 · 카드 비평 S4 · S8 · S3) node 시험.

- 새 화면(``ds-inbox-question.js``): 답 하나 = POST ``…/<id>/answer`` 한 번. 결정 시간(view_ms)은 카드를 보인 때부터 누를 때까지의
  실제 값(예전에는 늘 0).
- 금액 알림: 서버가 ``saved`` 거짓 + 알림 한 줄을 주면 그 줄을 보이고 단추를 다시 살린다 — 같은 글로 다시 누르면 ``money_ok`` 를
  싣는다(대조군: 글을 바꾸면 싣지 않는다).
- 옛 화면(``brain-inbox-question.js``)도 같은 한 번 부르기.
가짜 DOM · 가짜 fetch(바깥으로 보내지 않는다) · 합성 자료만.
"""

from __future__ import annotations

from tests.domains.test_brain_ds_inbox_js import NODE, _run, page  # noqa: F401 — page 는 fixture
from tests.domains.test_brain_fix_inbox_js import _card
from tests.domains.test_brain_fix_inbox_js import _run as _old_run
from tests.domains.test_brain_reopen import _question_card

#: 시계 — 몸통이 ``document.body`` 의 data-clock 을 바꾸면 performance.now() 가 그 값을 낸다.
CLOCK = """
  window.performance = { now: function () { return Number(document.body.getAttribute('data-clock') || 1000); } };"""
#: 한 번에 저장 가짜 서버 — money_ok 없이 오면 금액 알림(saved 거짓), 있으면 저장.
MONEY = CLOCK + """
  const plain = fetch;
  fetch = async function (url, init) {
    const res = await plain(url, init);
    if (init && init.method === 'POST' && /\\/answer$/.test(url)) {
      const sent = JSON.parse(init.body);
      const data = sent.money_ok ? { saved: true, change_id: 10, edit: 777 }
                                 : { saved: false, change_id: 10, ask: 'calc_money', message: '합성 금액 알림 한 줄' };
      return { status: 200, json: async () => ({ success: true, data: data }) };
    }
    return res;
  };"""


@NODE
def test_one_post_per_answer_with_the_real_decision_time(page, tmp_path):
    body = """
      api.root.parentNode.setAttribute('data-clock', '4200');
      const box = api.q('[data-ds-inbox-cards] [data-card-id="c1"]');
      await api.click(box.querySelector('[data-ds-answer="knowledge"]'));
      return { posts: api.posts, status: api.text(api.q('[data-ds-inbox-status]')) };"""
    got = _run(page("/brain?tab=inbox&bin=decide"), body, cards=[_question_card(1)], search="?tab=inbox&bin=decide",
               before=CLOCK, tmp=tmp_path)
    assert got["posts"] == [{"url": "/api/brain/proposals/10/answer", "body": {"code": "knowledge_right", "view_ms": 3200}}]
    assert got["status"] == "정했어요 — 회사 지식이 맞아요."


@NODE
def test_money_alert_is_shown_once_and_the_same_text_pressed_again_saves(page, tmp_path):
    body = """
      const box = api.q('[data-ds-inbox-cards] [data-card-id="c1"]');
      const save = () => box.querySelector('[data-ds-answer="outside-save"]');
      const input = () => box.querySelector('[data-ds-answer-text="outside"]');
      await api.click(box.querySelector('[data-ds-answer="outside"]'));
      input().value = '합성 손잡이는 12,345원';
      await api.click(save());
      const first = { status: api.text(box.querySelector('[data-ds-prop-status]')), disabled: save().disabled };
      input().value = '합성 손잡이는 23,456원';  // 글을 바꾸면 다시 묻는다(대조군)
      await api.click(save());
      await api.click(save());
      return { first: first, posts: api.posts, status: api.text(api.q('[data-ds-inbox-status]')) };"""
    got = _run(page("/brain?tab=inbox&bin=decide"), body, cards=[_question_card(1)], search="?tab=inbox&bin=decide",
               before=MONEY, tmp=tmp_path)
    assert got["first"] == {"status": "합성 금액 알림 한 줄", "disabled": False}  # 저장 전에 묻고 단추는 다시 눌린다
    url = "/api/brain/proposals/10/answer"
    base = {"code": "outside_right", "view_ms": 0, "base_version": 3}
    assert got["posts"] == [{"url": url, "body": {**base, "text": "합성 손잡이는 12,345원"}},
                            {"url": url, "body": {**base, "text": "합성 손잡이는 23,456원"}},
                            {"url": url, "body": {**base, "text": "합성 손잡이는 23,456원", "money_ok": True}}]
    assert got["status"] == "정했어요 — 바깥 글이 맞아요."


@NODE
def test_old_screen_question_card_saves_in_one_call_too():
    card = _card(1, "decide")
    card["main"]["about"] = [{"key": "common/door", "title": "여닫이 문짝", "text": "옛 글", "version": 3}]
    body = """
      const box = api.q('[data-card-id="c1"]');
      await api.click(box.querySelector('[data-brain-answer="both"]'));
      box.querySelector('[data-brain-answer-text="both"]').value = ' 벽이 약하면 한 줄 ';
      await api.click(box.querySelector('[data-brain-answer="both-save"]'));
      const first = api.posts.slice();
      await api.click(api.q('[data-card-id="c1"] [data-brain-answer="knowledge"]'));
      return { first: first, all: api.posts };"""
    got = _old_run(body, cards=[card], search="?tab=inbox&bin=decide")
    url = "/api/brain/proposals/10/answer"
    assert got["first"] == [{"url": url, "body": {"code": "both_right", "view_ms": 0, "text": "벽이 약하면 한 줄",
                                                  "base_version": 3}}]
    assert got["all"][1:] == [{"url": url, "body": {"code": "knowledge_right", "view_ms": 0}}]
