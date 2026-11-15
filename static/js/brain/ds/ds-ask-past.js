/**
 * 새 물어보기 화면(판 ⑨) — 지난 질문 다시 보기 · 모름 답의 [○○팀에 묻기](점검 w2-17 · w2-19 · 사용자 결정 D233).
 *
 * - 다시 보기: GET /api/brain/chat/questions/<번호> — **다시 묻지 않는다**(모델 · 기록 · 하루 수 없음). 내 질문이거나 그 질문의
 *   팀 묻기 알림을 받은 사람만 서버가 준다(그 밖 404). 받은 값은 물어보기 답 값과 같은 꼴이라 ds-ask-turn.js 로 그대로 그린다.
 * - 팀에 묻기: POST /api/brain/chat/questions/<번호>/ask-team — 같은 질문은 한 번만(서버가 판정). 보내면 단추가 '보냈어요'.
 * 주소는 '/…/questions/0' 꼴 틀에서 0 을 번호로 바꾼다. 요청은 brain-dom.js 한 곳(try/catch + data.success), 글은 textContent 만.
 * window.FOMS_DS_ASK_PAST.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var dv = window.FOMS_DS_ASK_VIEW;
  var turn = window.FOMS_DS_ASK_TURN;
  if (!dom || !dv || !turn) return;

  /** '/…/questions/0' 또는 '/…/questions/0/ask-team' 의 0 → 번호. */
  function urlFor(template, id) {
    return String(template || '').replace(/\/questions\/0(\/|$)/, '/questions/' + encodeURIComponent(String(id)) + '$1');
  }

  /** 주소 글의 ?question=<번호>(알림이 여는 질문) — 없거나 꼴이 틀리면 null. */
  function questionFromQuery(search) {
    var value = new URLSearchParams(String(search || '').replace(/^\?/, '')).get('question') || '';
    return /^\d{1,12}$/.test(value) ? value : null;
  }

  /** 지난 질문 하나 → {ok, data, error}. */
  function load(template, id) {
    return dom.getJson(urlFor(template, id));
  }

  /** 지난 질문의 물음 · 답 노드 둘 — opts: {display, items, me}. 남의 질문(팀 묻기로 받은 것)은 이름 대신 '받은 질문'. */
  function nodes(data, opts) {
    var when = dv.whenLabel(data.asked_at, false) + ' ' + dv.whenLabel(data.asked_at, true);
    var line = data.mine ? dv.askedLine(opts.me, when.trim()) : '팀에 온 질문 · ' + when.trim();
    var qNode = turn.questionNode(data.question, line, []);
    qNode.setAttribute('data-question-of', data.id);
    var card = turn.answerNode(data, { display: opts.display, items: opts.items, clock: when.trim(), mine: !!data.mine });
    return [qNode, card];
  }

  /** [○○팀에 묻기] — 보내면 '보냈어요'(이미 보낸 질문도 같은 모습), 못 보내면 까닭을 카드 알림 줄에. */
  async function sendTeam(template, card, button) {
    var line = card.querySelector('[data-feedback-status]');
    button.disabled = true;
    dom.setStatus(line, '보내는 중…');
    var res = await dom.postJson(urlFor(template, card.getAttribute('data-question')), {});
    if (!res.ok) {
      button.disabled = false;
      dom.setStatus(line, res.error, 'error');
      return;
    }
    dom.clear(button);
    button.appendChild(turn.icon('tick'));
    button.appendChild(document.createTextNode('보냈어요'));
    dom.setStatus(line, res.data.already ? '이미 ' + res.data.team_label + '에 물었어요.'
                                         : res.data.team_label + ' ' + res.data.sent + '명에게 알림을 보냈어요.');
  }

  window.FOMS_DS_ASK_PAST = { urlFor: urlFor, questionFromQuery: questionFromQuery, load: load, nodes: nodes,
                              sendTeam: sendTeam };
})();
