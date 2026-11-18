/**
 * 문장으로 고치기 — 넣기(설계서 docs/specs/2026-11-18-brain-sentence-change_SPEC.md 4절 · D249).
 *
 * 두 자리에서 같은 길을 쓴다:
 * - 승인 대기 화면 맨 위 한 줄 칸 [data-ds-req-form](templates/brain/ds/partials/request_input.html) — [분석] · Enter.
 * - 물어보기 화면의 [바뀐 내용으로 넣기] [data-ds-ask-change](templates/brain/ds/ask.html) — 묻는 칸의 글을 보낸다. 묻기(form 보내기 ·
 *   Enter)와 섞이지 않게 이 단추를 따로 눌러야만 간다. 글이 비면 단추가 잠긴다.
 * POST /api/brain/change-requests {text} — 분석이 10 ~ 30초 걸릴 수 있어 그동안 칸 · 단추를 잠그고 '분석 중이에요'를 보인다(두 번
 * 눌러도 한 번만 보낸다). 답이 오면 /brain/requests/<번호> 로 간다(분석을 못 한 묶음도 그 화면이 까닭을 보인다). 실패 · 가림 · 꺼짐은
 * 서버가 준 말을 칸 아래 한 줄로. fetch 는 brain-dom.js 한 곳 · 글은 textContent 만 · 전역 듣개는 한 번만.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  if (!dom || window.__FOMS_DS_REQ_START_BOUND) return;
  window.__FOMS_DS_REQ_START_BOUND = true;

  var WAIT = '분석 중이에요 — 10 ~ 30초 걸려요. 이 화면에 그대로 있어 주세요.';
  var EMPTY = '바뀐 내용을 적어 주세요.';

  /** 보내기 — parts: {url, base, text, lock(on), status}. 끝나면 묶음 화면으로 간다. 이미 보내는 중이면 아무것도 안 한다. */
  async function send(parts) {
    if (parts.busy()) return;
    var text = String(parts.text() || '').trim();
    if (!text) {
      dom.setStatus(parts.status, EMPTY, 'error');
      return;
    }
    parts.lock(true);
    dom.setStatus(parts.status, WAIT);
    var res = await dom.postJson(parts.url, { text: text });
    if (!res.ok || !res.data || !res.data.id) {
      parts.lock(false);
      dom.setStatus(parts.status, res.error || '처리하지 못했어요.', 'error');
      return;
    }
    dom.setStatus(parts.status, '분석을 마쳤어요 — 묶음 화면으로 가요.');
    window.location.assign(parts.base + encodeURIComponent(res.data.id));
  }

  /** 승인 대기 화면 맨 위 한 줄 칸. */
  function bindForm(form) {
    var input = form.querySelector('[data-ds-req-text]');
    var submit = form.querySelector('[data-ds-req-submit]');
    var status = form.querySelector('[data-ds-req-status]');
    var busy = false;
    var parts = {
      url: form.getAttribute('data-start-url'), base: form.getAttribute('data-request-base'), status: status,
      busy: function () { return busy; },
      text: function () { return input ? input.value : ''; },
      lock: function (on) {
        busy = on;
        if (input) input.disabled = on;
        if (submit) submit.disabled = on;
        form.setAttribute('aria-busy', on ? 'true' : 'false');
      }
    };
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      send(parts);
    });
  }

  /** 물어보기 화면 [바뀐 내용으로 넣기] — 묻는 칸의 글을 보낸다(묻기 단추 · Enter 와 따로). */
  function bindAsk(button) {
    var form = button.closest('[data-ds-ask-form]');
    var input = form && form.querySelector('[data-ds-ask-input]');
    var status = form && form.querySelector('[data-ds-ask-status]');
    var asks = form && form.querySelector('[data-ds-ask-submit]');
    var busy = false;
    var asksWas = false;  // 묻기 단추의 앞 상태(남은 수가 없으면 ds-ask.js 가 잠가 둔다 — 풀 때 그대로 되돌린다)
    var empty = function () { return !String(input ? input.value : '').trim(); };
    var sync = function () { button.disabled = busy || empty(); };
    var parts = {
      url: button.getAttribute('data-start-url'), base: button.getAttribute('data-request-base'), status: status,
      busy: function () { return busy; },
      text: function () { return input ? input.value : ''; },
      lock: function (on) {
        busy = on;
        if (input) input.disabled = on;
        if (asks) {
          if (on) asksWas = asks.disabled;
          asks.disabled = on ? true : asksWas;
        }
        sync();
      }
    };
    if (input) input.addEventListener('input', sync);
    button.addEventListener('click', function (event) {
      event.preventDefault();
      if (empty()) return;
      send(parts);
    });
    sync();
  }

  function start() {
    var form = document.querySelector('[data-ds-req-form]');
    if (form) bindForm(form);
    var button = document.querySelector('[data-ds-ask-change]');
    if (button) bindAsk(button);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
