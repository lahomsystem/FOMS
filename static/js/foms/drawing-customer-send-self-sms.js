/**
 * 도면 탭 고객에게 보내기 — [내 폰 문자]의 PC 화면(사용자 2026-10-25).
 *
 * 휴대폰에서는 drawing-customer-send.js 가 sms: 링크로 문자 앱을 바로 연다. PC 에는 문자 앱이
 * 없는 경우가 많아, 같은 문자를 창 안([data-self-sms-box])에 보여 주고 [문자 내용 복사]와
 * [문자 앱 열기](PC '휴대폰과 연결' 앱이 있으면 열린다)를 준다. 본체가 보내는 'foms:self-sms'
 * 이벤트를 받아 preventDefault 하면 본체는 sms: 로 넘기지 않는다.
 */
(function () {
  'use strict';

  var MODAL_ID = 'dwCustomerSendModal';
  var WIDE = '(min-width: 992px)';

  function modal() { return document.getElementById(MODAL_ID); }
  function wide() { return !!(window.matchMedia && window.matchMedia(WIDE).matches); }

  document.addEventListener('foms:self-sms', function (e) {
    var root = modal();
    var box = root && root.querySelector('[data-self-sms-box]');
    if (!box || !wide()) return; // 휴대폰 — 본체가 문자 앱을 연다
    e.preventDefault();
    var d = e.detail || {};
    var to = root.querySelector('[data-self-sms-to]');
    var text = root.querySelector('#dw-self-sms-text');
    var open = root.querySelector('[data-self-sms-open]');
    if (to) to.textContent = d.to || '';
    if (text) text.value = d.text || '';
    if (open) open.setAttribute('href', d.href || '#');
    var status = root.querySelector('[data-send-status]');
    if (status) {
      status.textContent = '링크를 만들었어요. 아래 문자를 휴대폰으로 보내 주세요(보냈는지는 기록되지 않아요).';
      status.classList.remove('d-none');
    }
    box.classList.remove('d-none');
  });

  function copied(btn, ok) {
    var original = btn.getAttribute('data-label') || btn.textContent;
    btn.setAttribute('data-label', original);
    btn.textContent = ok ? '복사했어요' : '복사하지 못했어요 — 글을 직접 골라 복사해 주세요';
    window.setTimeout(function () { btn.textContent = original; }, 2000);
  }

  document.addEventListener('click', function (e) {
    var btn = e.target && e.target.closest ? e.target.closest('[data-self-sms-copy]') : null;
    if (!btn) return;
    var text = document.getElementById('dw-self-sms-text');
    if (!text) return;
    var value = text.value;
    try {
      navigator.clipboard.writeText(value).then(function () { copied(btn, true); }, function () {
        text.select();
        copied(btn, false);
      });
    } catch (err) {
      text.select();
      copied(btn, false);
    }
  });

  // 창을 다시 열면 지난 문자 칸은 접는다.
  document.addEventListener('show.bs.modal', function (e) {
    if (!e.target || e.target.id !== MODAL_ID) return;
    var box = e.target.querySelector('[data-self-sms-box]');
    if (box) box.classList.add('d-none');
  });
})();
