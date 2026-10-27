/**
 * AI 도면팀원 노트 화면 — 질문에 답하기(도면팀 · 관리자, data-can-answer="1" 일 때만).
 *
 * 설계 정본: docs/plans/2026-10-27-drawing-ai-teammate-spec.md §2 A3
 * - 답 단추 → POST /api/drawing-agent/notes/<노트>/answer {qid, choice}. CSRF 는 csrf_bootstrap 이 fetch 에 싣는다.
 * - 고른 답은 aria-pressed 로 표시하고, 다른 답을 누르면 바꾼다(서버가 앞 답이 바꾼 기억 이름표를 되돌린다).
 * - 실패하면 그 질문 칸에 알리고 단추를 다시 켠다.
 */
(function () {
  'use strict';
  var root = document.querySelector('.dan-page');
  if (!root || root.getAttribute('data-can-answer') !== '1') { return; }

  function buttons(card) { return Array.prototype.slice.call(card.querySelectorAll('.dan-btn[data-choice]')); }

  function busy(card, on) { buttons(card).forEach(function (b) { b.disabled = on; }); }

  function paint(card, question) {
    var ans = question && question.answer;
    buttons(card).forEach(function (b) { b.setAttribute('aria-pressed', String(!!ans && b.getAttribute('data-choice') === ans.choice)); });
    var out = card.querySelector('.dan-q-answer');
    if (out) { out.textContent = ans ? '답: ' + ans.text + (ans.name ? ' — ' + ans.name : '') : ''; }
    card.classList.remove('dan-q-failed');
  }

  function fail(card, message) {
    var out = card.querySelector('.dan-q-answer');
    if (out) { out.textContent = message; }
    card.classList.add('dan-q-failed');
  }

  async function answer(card, choice) {
    busy(card, true);
    try {
      var r = await fetch('/api/drawing-agent/notes/' + encodeURIComponent(card.getAttribute('data-note')) + '/answer', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ qid: card.getAttribute('data-q'), choice: choice })
      });
      var data = await r.json();
      if (!r.ok || !data || !data.success) { throw new Error((data && data.message) || '답을 남기지 못했어요.'); }
      paint(card, data.data && data.data.question);
    } catch (e) {
      fail(card, (e && e.message) || '답을 남기지 못했어요. 잠시 뒤 다시 눌러 주세요.');
    } finally {
      busy(card, false);
    }
  }

  root.addEventListener('click', function (e) {
    var btn = e.target.closest ? e.target.closest('.dan-btn[data-choice]') : null;
    var card = btn ? btn.closest('.dan-q') : null;
    if (card) { answer(card, btn.getAttribute('data-choice')); }
  });
})();
