/**
 * 협력사 거래명세서 보기(templates/partner/statement_view.html, 설계서 2026-11-03-partner-statement §5.6).
 * "명세서 확인했어요" = POST data-ack-url · "금액 문의" = POST data-ask-url {line_ref, text} · 입금 계좌 복사.
 * 글은 textContent 로만 넣는다.
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-pp-statement]');
  if (!root) return;

  function status(text) { root.querySelector('[data-pp-statement-status]').textContent = text || ''; }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  async function post(url, body) {
    var res;
    try {
      res = await fetch(url, { method: 'POST', credentials: 'same-origin',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
    } catch (_) {
      return { ok: false, error: '보내지 못했습니다. 인터넷 연결을 확인해 주세요.' };
    }
    var data = null;
    try { data = await res.json(); } catch (_) { data = null; }
    if (!data || !data.success) return { ok: false, error: (data && data.error) || '보내지 못했습니다. 잠시 뒤 다시 시도해 주세요.' };
    return { ok: true, data: data.data || {} };
  }

  function drawQuestions(list) {
    var box = root.querySelector('[data-pp-statement-questions]');
    box.replaceChildren();
    list.forEach(function (q) {
      var li = box.appendChild(el('li'));
      li.appendChild(el('div', 'pp-sv__muted', q.line + ' · ' + q.asked_at));
      li.appendChild(el('div', null, q.text));
      li.appendChild(q.answer ? el('div', 'pp-sv__answer', '답: ' + q.answer) : el('div', 'pp-sv__muted', '답을 기다리는 중'));
    });
  }

  var ack = root.querySelector('[data-pp-statement-ack]');
  if (ack) {
    ack.addEventListener('click', async function () {
      ack.disabled = true;
      var res = await post(root.getAttribute('data-ack-url'));
      if (!res.ok) { ack.disabled = false; status(res.error); return; }
      ack.replaceWith(el('span', 'pp-sv__acked', '✓ 확인했습니다'));
    });
  }

  var form = root.querySelector('[data-pp-statement-ask]');
  if (form) {
    form.addEventListener('submit', async function (ev) {
      ev.preventDefault();
      var text = form.elements.text.value.trim();
      if (!text) { status('물어볼 내용을 적어 주세요.'); return; }
      var btn = form.querySelector('button[type=submit]');
      btn.disabled = true;
      var res = await post(root.getAttribute('data-ask-url'), { line_ref: form.elements.line_ref.value, text: text });
      btn.disabled = false;
      if (!res.ok) { status(res.error); return; }
      form.elements.text.value = '';
      drawQuestions(res.data.questions || []);
      status('문의를 보냈습니다. 저희가 답을 달면 여기에 보입니다.');
    });
  }

  root.addEventListener('click', function (ev) {
    var btn = ev.target.closest && ev.target.closest('[data-pp-copy]');
    if (!btn) return;
    var text = btn.getAttribute('data-pp-copy');
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { status('계좌를 복사했습니다.'); }, function () { status(text); });
    } else {
      status(text);
    }
  });
})();
