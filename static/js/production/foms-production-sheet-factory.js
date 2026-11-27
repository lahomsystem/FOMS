/* 생산 작업 시트 — 공장마다 제작 완료(설계서 docs/specs/2026-11-23-production-self-claim-and-factory2_SPEC.md §4-14 '작업 시트', 3단계 ⑥).
 * 섞인 주문(2공장 장이 있는 주문) · 쓰기 단추가 있을 때만 실린다(sheet.html). 한 공장 주문은 이 파일이 없다(지금 시트 그대로).
 *  · [2공장 제작 완료] · [2공장 완료 취소](data-foms-sheet-factory = 공장, data-done = 1 · 0)
 *      → POST /api/orders/<id>/production/factory-done {factory, done}. 회색(aria-disabled)이면 요청 없이 까닭(서버 글)을 상태 줄에.
 *  · 관리자 제작완료 단계 [1공장 완료 취소] · [2공장 완료 취소](data-foms-sheet-reopen = 공장) → POST …/production/uncomplete {factories:[공장]}
 *      (지금 [완료 취소]는 그대로 = 둘 다).
 * 묻기는 [제작 완료] · [완료 취소]처럼 앱 확인 창 한 번(2026-11-27, 창 조각이 없으면 브라우저 확인 창). 성공하면 다시 받기(단계 · 공장 줄 · 단추가 서버 값으로).
 * 거절 · 연결 끊김은 상태 줄에 서버 글 그대로. 시트 루트마다 한 번 묶는다(data-foms-sheet-factory-bound).
 * 공정 칸 손 체크 · 해제 뒤: 공정 API 응답의 factories({"2": {ready, why}})로 [N공장 제작 완료] 색 · 회색 까닭을 다시 그린다
 * (sheet-parts.js 가 응답마다 'foms:sheet-steps' 를 시트 루트에 쏜다 — 작업 시트 본체 JS 는 손대지 않는다). */
(function () {
  'use strict';

  var OFFLINE = '연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요.';

  function post(url, body) {
    var opts = { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
    try {
      return fetch(url, opts).then(function (res) {
        return res.json().catch(function () { return null; }).then(function (data) {
          var ok = res.ok && !!data && data.success === true;
          return { ok: ok, text: (data && (data.error || data.message)) || '' };
        });
      }).catch(function () { return { ok: false, text: OFFLINE }; });
    } catch (e) {
      return Promise.resolve({ ok: false, text: OFFLINE });
    }
  }

  function bind(page) {
    if (!page || page.getAttribute('data-foms-sheet-factory-bound') === '1') { return; }
    page.setAttribute('data-foms-sheet-factory-bound', '1');
    var status = page.querySelector('[data-foms-sheet-status]');
    function say(text, bad) {
      if (!status) { if (bad && text) { window.alert(text); } return; }
      status.textContent = text || '';
      status.classList.toggle('is-bad', !!bad);
    }
    // 묻기 = 작업 시트 공정 칸과 같은 앱 창(sheet-parts.js confirm, 사장님 2026-11-27 "앱 창으로 바꾸기") — 제목 "<단추 글>할까요?",
    // [닫기] [<단추 글>]. 창 조각 · sheet-parts.js 가 없으면 지금 기본 창. 떠 있는 창 위 누름은 버린다.
    function run(btn, url, body, label) {
      if (btn.disabled) { return; }
      var question = label + '할까요?';
      function save() {
        btn.disabled = true;
        say('저장하는 중…');
        post(url, body).then(function (r) {
          if (r.ok) { window.location.reload(); return; }
          btn.disabled = false;
          say(r.text || OFFLINE, true);
        });
      }
      var sp = window.FomsSheetParts;
      var box = document.querySelector('[data-foms-sheet-confirm]');
      if (box && sp && typeof sp.confirm === 'function') {
        if (box.hidden) { sp.confirm({ title: question, yes: label, no: '닫기', opener: btn, go: save }); }
        return;
      }
      if (window.confirm(question)) { save(); }
    }
    page.addEventListener('foms:sheet-steps', function (e) {
      var facs = (e.detail || {}).factories || {};
      [].slice.call(page.querySelectorAll('[data-foms-sheet-factory][data-done="1"]')).forEach(function (btn) {
        var info = facs[btn.getAttribute('data-foms-sheet-factory')];
        if (!info) { return; }
        btn.classList.toggle('foms-prod-page__btn--pri', !!info.ready);
        btn.classList.toggle('foms-prod-page__btn--off', !info.ready);
        if (info.ready) { btn.removeAttribute('aria-disabled'); btn.removeAttribute('data-foms-sheet-factory-why'); return; }
        btn.setAttribute('aria-disabled', 'true');
        btn.setAttribute('data-foms-sheet-factory-why', info.why || '');
      });
    });
    page.addEventListener('click', function (e) {
      var t = e.target;
      if (!t || typeof t.closest !== 'function') { return; }
      var id = encodeURIComponent(page.getAttribute('data-order-id') || '');
      var btn = t.closest('[data-foms-sheet-factory]');
      if (btn) {
        e.preventDefault();
        if (btn.getAttribute('aria-disabled') === 'true') { say(btn.getAttribute('data-foms-sheet-factory-why') || '', true); return; }
        var label = (btn.textContent || '').trim();
        var done = btn.getAttribute('data-done') === '1';
        run(btn, '/api/orders/' + id + '/production/factory-done',
          { factory: Number(btn.getAttribute('data-foms-sheet-factory')), done: done }, label);
        return;
      }
      var reopen = t.closest('[data-foms-sheet-reopen]');
      if (reopen) {
        e.preventDefault();
        run(reopen, '/api/orders/' + id + '/production/uncomplete',
          { factories: [Number(reopen.getAttribute('data-foms-sheet-reopen'))] }, (reopen.textContent || '').trim());
      }
    });
  }

  function init() {
    [].slice.call(document.querySelectorAll('[data-foms-prod-sheet-page]')).forEach(bind);
  }
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', init); } else { init(); }
})();
