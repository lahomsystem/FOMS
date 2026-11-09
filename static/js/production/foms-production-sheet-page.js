/* 생산 작업 시트 공통 JS — 전체 화면 시트(/erp/production/sheet/<id>)와 칸반 옆 시트(fragment) 둘 다.
 * 루트 = [data-foms-prod-sheet-page] (주문 하나). 옆 시트는 fragment 로 갈아끼워지므로
 * foms:erp-shell-fragment-swapped 때 새 루트를 다시 묶는다(루트마다 1회, data-foms-sheet-init).
 * 도면 넘기기·전역 뷰어·공정 체크 POST·불량 알리기 POST. 설계서 §12.2·F2 ② (2026-11-09).
 * 제작 시작/완료/취소/보류/변경 확인 단추는 tablet-domain-sheets.js 몫(여기선 안 건드림).
 * 실패 글은 설계서 §8 한 가지: "연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요." */
(function () {
  'use strict';

  var OFFLINE_TEXT = '연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요.';

  function toArr(list) { return [].slice.call(list); }
  function pad(n) { return String(n).padStart(2, '0'); }
  function fmtAt(iso) {
    var d = new Date(iso || '');
    if (isNaN(d.getTime())) { return ''; }
    return (d.getMonth() + 1) + '/' + d.getDate() + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  // 공용 쓰기 래퍼가 있으면 그것(오프라인 큐·오류 분류), 없으면 fetch. 절대 reject 하지 않는다.
  function mutate(url, body) {
    var opts = {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    };
    if (window.fomsMutationFetch) { return window.fomsMutationFetch(url, opts); }
    return (window.fomsWriteFetch || fetch)(url, opts).then(function (res) {
      return res.json().catch(function () { return null; }).then(function (data) {
        if (data === null) {
          return { ok: false, kind: 'malformed', status: res.status, data: {}, message: '서버 응답을 읽지 못했어요.' };
        }
        var ok = res.ok && data.success !== false;
        return { ok: ok, kind: ok ? 'ok' : 'error', status: res.status, data: data,
          message: (data && (data.error || data.message)) || ('HTTP ' + res.status) };
      });
    }).catch(function () {
      return { ok: false, kind: 'network', status: 0, data: {}, message: OFFLINE_TEXT };
    });
  }
  function failText(result) {
    if (!result || result.kind === 'network' || result.status === 0) { return OFFLINE_TEXT; }
    return '오류: ' + (result.message || '처리하지 못했어요');
  }

  function initRoot(page) {
    if (!page || page.getAttribute('data-foms-sheet-init') === '1') { return; }
    page.setAttribute('data-foms-sheet-init', '1');

    var orderId = page.getAttribute('data-order-id');
    var inProduction = page.getAttribute('data-foms-prod-page-stage') === '제작중';
    var statusEl = page.querySelector('[data-foms-sheet-status]');
    function setStatus(text, kind) {
      if (!statusEl) { return; }
      statusEl.textContent = text || '';
      statusEl.classList.toggle('is-bad', kind === 'bad');
      statusEl.classList.toggle('is-ok', kind === 'ok');
    }

    // ── 도면 넘기기(전체 화면 시트만 main 이 있다) ──
    var mainImg = page.querySelector('[data-foms-sheet-dwg-main]');
    var cap = page.querySelector('[data-foms-sheet-dwg-cap]');
    var thumbs = toArr(page.querySelectorAll('[data-foms-sheet-dwg-th]'));
    var dwgIndex = 0;
    function viewerFiles() {
      return thumbs.map(function (t) {
        return {
          view_url: t.getAttribute('data-foms-erp-attachment-view-url') || '',
          download_url: t.getAttribute('data-foms-erp-attachment-download-url') || '',
          filename: t.getAttribute('data-foms-erp-attachment-label') || '도면'
        };
      });
    }
    function showDrawing(i) {
      if (!thumbs.length || !mainImg) { return; }
      dwgIndex = ((i % thumbs.length) + thumbs.length) % thumbs.length;
      var t = thumbs[dwgIndex];
      var label = t.getAttribute('data-foms-erp-attachment-label') || '';
      mainImg.src = t.getAttribute('data-foms-erp-attachment-view-url') || '';
      mainImg.alt = label;
      thumbs.forEach(function (x, k) { x.classList.toggle('is-on', k === dwgIndex); });
      if (cap) { cap.textContent = '도면 ' + (dwgIndex + 1) + ' / ' + thumbs.length + (label ? ' · ' + label : ''); }
    }
    function openViewer() {
      var viewer = window.GlobalImageViewer;
      if (!viewer || typeof viewer.open !== 'function' || !thumbs.length) { return; }
      viewer.open(viewerFiles(), dwgIndex);
    }

    // ── 공정 체크 ──
    var countEl = page.querySelector('[data-foms-sheet-steps-count]');
    function stepButtons() { return toArr(page.querySelectorAll('[data-foms-sheet-step]')); }
    function renderSteps(steps) {
      var buttons = stepButtons();
      var doneCount = 0;
      var nowTaken = false;
      steps.forEach(function (s) {
        var btn = buttons.filter(function (b) { return b.getAttribute('data-foms-sheet-step') === s.key; })[0];
        if (!btn) { return; }
        var done = !!s.done;
        if (done) { doneCount += 1; }
        var isNow = inProduction && !done && !nowTaken;
        if (isNow) { nowTaken = true; }
        btn.classList.toggle('is-done', done);
        btn.classList.toggle('is-now', isNow);
        btn.setAttribute('aria-pressed', done ? 'true' : 'false');
        var meta = btn.querySelector('[data-foms-sheet-step-meta]');
        if (meta) {
          meta.textContent = done ? [(s.by_name || '').trim(), fmtAt(s.at)].filter(Boolean).join(' · ') : '';
        }
      });
      if (countEl) { countEl.textContent = doneCount + '/' + steps.length; }
    }
    function toggleStep(btn) {
      if (btn.disabled) { return; }
      var key = btn.getAttribute('data-foms-sheet-step');
      var done = btn.getAttribute('aria-pressed') !== 'true';
      btn.disabled = true;
      setStatus('저장하는 중…');
      mutate('/api/orders/' + encodeURIComponent(orderId) + '/production/steps', { key: key, done: done })
        .then(function (result) {
          btn.disabled = false;
          if (!result.ok) { setStatus(failText(result), 'bad'); return; }
          var payload = (result.data && result.data.data) || {};
          if (payload.steps && payload.steps.length) {
            renderSteps(payload.steps);
          } else {
            btn.classList.toggle('is-done', done);
            btn.setAttribute('aria-pressed', done ? 'true' : 'false');
          }
          setStatus(done ? '체크했어요' : '체크를 풀었어요', 'ok');
        });
    }

    // ── 불량 알리기 ──
    var defectToggle = page.querySelector('[data-foms-sheet-defect-toggle]');
    var defectReasons = page.querySelector('[data-foms-sheet-defect-reasons]');
    var defectRecent = page.querySelector('[data-foms-sheet-defect-recent]');
    function setReasonsOpen(open) {
      if (!defectToggle || !defectReasons) { return; }
      defectReasons.hidden = !open;
      defectToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    }
    function reportDefect(chip) {
      var reason = chip.getAttribute('data-foms-sheet-defect-reason');
      if (!reason) { return; }
      var chips = toArr(page.querySelectorAll('[data-foms-sheet-defect-reason]'));
      chips.forEach(function (c) { c.disabled = true; });
      setStatus('알리는 중…');
      mutate('/api/orders/' + encodeURIComponent(orderId) + '/production/defect', { reason: reason })
        .then(function (result) {
          chips.forEach(function (c) { c.disabled = false; });
          if (!result.ok) { setStatus(failText(result), 'bad'); return; }
          var latest = (result.data && result.data.data && result.data.data.latest) || { reason: reason };
          if (defectRecent) {
            var parts = ['최근 불량 · ' + (latest.reason || reason)];
            var who = [(latest.by_name || '').trim(), fmtAt(latest.at)].filter(Boolean).join(' ');
            if (who) { parts.push(who); }
            defectRecent.textContent = parts.join(' · ');
            defectRecent.hidden = false;
          }
          setReasonsOpen(false);
          setStatus('불량을 알렸어요', 'ok');
        });
    }

    page.addEventListener('click', function (e) {
      var t = e.target;
      if (!t || typeof t.closest !== 'function') { return; }
      var th = t.closest('[data-foms-sheet-dwg-th]');
      if (th) { showDrawing(parseInt(th.getAttribute('data-foms-sheet-dwg-th'), 10) || 0); return; }
      if (t.closest('[data-foms-sheet-dwg-prev]')) { showDrawing(dwgIndex - 1); return; }
      if (t.closest('[data-foms-sheet-dwg-next]')) { showDrawing(dwgIndex + 1); return; }
      if (t.closest('[data-foms-sheet-dwg-open]')) { openViewer(); return; }
      var step = t.closest('[data-foms-sheet-step]');
      if (step) { toggleStep(step); return; }
      if (t.closest('[data-foms-sheet-defect-toggle]')) { setReasonsOpen(defectReasons && defectReasons.hidden); return; }
      var chip = t.closest('[data-foms-sheet-defect-reason]');
      if (chip) { reportDefect(chip); }
    });

    if (thumbs.length && mainImg) {
      // 좌우 화살표로도 넘긴다(키보드 붙인 태블릿·PC) — 전체 화면 시트만.
      document.addEventListener('keydown', function (e) {
        if (!document.body.contains(page)) { return; }
        if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) { return; }
        if (e.key === 'ArrowLeft') { showDrawing(dwgIndex - 1); }
        if (e.key === 'ArrowRight') { showDrawing(dwgIndex + 1); }
      });
    }
  }

  function initAll() {
    toArr(document.querySelectorAll('[data-foms-prod-sheet-page]')).forEach(initRoot);
  }
  initAll();
  document.addEventListener('foms:erp-shell-fragment-swapped', initAll);
  document.addEventListener('foms:main-content-swapped', initAll);
  window.FomsProductionSheetPage = { init: initAll };
})();
