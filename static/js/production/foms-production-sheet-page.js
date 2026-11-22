/* 생산 작업 시트 공통 JS — 전체 화면 시트(/erp/production/sheet/<id>)와 칸반 옆 시트(fragment) 둘 다.
 * 루트 = [data-foms-prod-sheet-page] (주문 하나). 옆 시트는 fragment 로 갈아끼워지므로
 * foms:erp-shell-fragment-swapped 때 새 루트를 다시 묶는다(루트마다 1회, data-foms-sheet-init).
 * 도면 넘기기·전역 뷰어·공정 체크 POST·불량 알리기 POST. 설계서 §12.2·F2 ② (2026-11-09).
 * 제작 시작/완료/취소/보류/변경 확인 단추는 tablet-domain-sheets.js 몫(여기선 안 건드림).
 * 실패 글은 설계서 §8 한 가지: "연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요."
 * 전체 화면 시트만(11-21, 시안 안 2): 공정 '지금 여기' 글 · 저장 · 연결 한 줄.
 * 두 시트 모두(11-21): 검수까지 끝나야 파란 [제작 완료] — 서버 제작 완료 API 와 같은 규칙(공정 API 응답 complete_ready).
 * 2026-11-22: 회색 [제작 완료] · 잠긴 공정 칸(파트 계정)은 진짜 disabled 가 아니라 aria-disabled — 누르면 요청 없이 까닭을 상태 줄에
 * 알린다(남은 공정 이름 · 잠금 글). 예전에는 눌러도 아무 일이 없어 '단추가 안 먹는다'고 여러 번 눌렀다. */
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
    // 연결 한 줄(전체 화면 시트만) — 첫 화면 '연결 끊김' 줄과 같은 navigator.onLine + 이 화면 요청이 연결 실패로 끝났는지.
    var netEl = page.querySelector('[data-foms-sheet-net]');
    var netFailed = false;
    function renderNet() {
      if (!netEl) { return; }
      var ok = navigator.onLine !== false && !netFailed;
      netEl.textContent = ok ? '연결 좋음' : '연결 끊김';
      netEl.classList.toggle('is-ok', ok);
      netEl.classList.toggle('is-bad', !ok);
    }
    function noteResult(result) {
      netFailed = !!result && !result.ok && (result.kind === 'network' || result.status === 0);
      renderNet();
    }
    if (netEl) {
      window.addEventListener('online', function () { netFailed = false; renderNet(); });
      window.addEventListener('offline', renderNet);
      renderNet();
    }
    function savedText(fallback) {
      if (!netEl) { return fallback; }
      var d = new Date();
      return '저장됨 ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
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
    var nowText = netEl ? '지금 여기' : '';  // 전체 화면 시트만 지금 공정 옆에 글(옆 시트는 칸 테두리만)
    // [제작 완료] 단추 — 전체 화면 시트는 루트 안, 옆 시트는 공정 루트 밖 바닥 줄(.foms-prod-sheet 안)에 있다.
    var completeScope = (typeof page.closest === 'function' && page.closest('.foms-prod-sheet')) || page;
    var completeBtn = completeScope.querySelector('[data-foms-sheet-complete]');
    var completeHint = completeBtn ? completeBtn.querySelector('[data-foms-sheet-complete-hint]') : null;
    var completeBase = completeBtn && completeBtn.classList.contains('foms-prod-sheet__btn') ? 'foms-prod-sheet__btn' : 'foms-prod-page__btn';
    function stepButtons() { return toArr(page.querySelectorAll('[data-foms-sheet-step]')); }
    function stepLabel(b) { var n = b.querySelector('span'); return n ? String(n.textContent || '').trim() : ''; }
    // 회색 [제작 완료]를 누름 = 남은 공정을 글로(요청 없음). 공정 4칸 이름 · 남은 칸 이름은 화면의 칸 글 그대로.
    function completeBlockedText() {
      var buttons = stepButtons();
      var left = buttons.filter(function (b) { return b.getAttribute('aria-pressed') !== 'true'; }).map(stepLabel).filter(Boolean);
      var all = buttons.map(stepLabel).filter(Boolean);
      return '공정 ' + all.length + '칸(' + all.join(' · ') + ')을 모두 끝내야 제작 완료를 누를 수 있어요.' + (left.length ? ' 남은 공정: ' + left.join(' · ') : '');
    }
    // [제작 완료]: 검수까지(공정 4칸 모두) 끝났을 때만 파랗게 누를 수 있다 — 서버 제작 완료 API 도 같은 규칙으로 막는다(11-21).
    // serverReady = 공정 API 응답의 complete_ready(서버 한 함수 production_complete_ready). 응답이 없을 때만(오프라인 줄 세움)
    // 지금 칸 모양으로 미리 보인다 — 그래도 누르면 서버가 같은 판정으로 다시 본다.
    function syncComplete(serverReady) {
      if (!completeBtn) { return; }
      var buttons = stepButtons();
      var ready = typeof serverReady === 'boolean' ? serverReady
        : (buttons.length > 0 && (buttons.every(function (b) { return b.getAttribute('aria-pressed') === 'true'; })
          || buttons.every(function (b) { return b.getAttribute('aria-pressed') !== 'true'; })));  // 한 칸도 안 켰으면 규칙 밖(11-21)
      // 진짜 disabled 는 쓰지 않는다 — 회색에서 누르면 까닭을 알린다(아래 completeBtn 누름). 화면 읽기는 aria-disabled.
      if (ready) { completeBtn.disabled = false; completeBtn.removeAttribute('aria-disabled'); } else { completeBtn.setAttribute('aria-disabled', 'true'); }
      completeBtn.classList.toggle(completeBase + '--pri', ready);
      completeBtn.classList.toggle(completeBase + '--off', !ready);
      if (completeHint) { completeHint.hidden = ready; }
    }
    function renderSteps(steps, serverReady) {
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
          meta.textContent = done ? [(s.by_name || '').trim(), fmtAt(s.at)].filter(Boolean).join(' · ') : (isNow ? nowText : '');
        }
      });
      if (countEl) { countEl.textContent = doneCount + '/' + steps.length; }
      syncComplete(serverReady);
    }
    function toggleStep(btn) {
      if (btn.disabled) { return; }
      if (btn.getAttribute('aria-disabled') === 'true') { // 잠긴 칸(파트 계정) — 요청 없이 까닭만
        var note = page.querySelector('[data-foms-sheet-steps-locked]');
        setStatus((note && String(note.textContent || '').trim()) || '공정은 도면 카드에서 체크해요', 'bad');
        return;
      }
      var key = btn.getAttribute('data-foms-sheet-step');
      var done = btn.getAttribute('aria-pressed') !== 'true';
      btn.disabled = true;
      setStatus('저장하는 중…');
      mutate('/api/orders/' + encodeURIComponent(orderId) + '/production/steps', { key: key, done: done })
        .then(function (result) {
          btn.disabled = false;
          noteResult(result);
          if (!result.ok) { setStatus(failText(result), 'bad'); return; }
          var payload = (result.data && result.data.data) || {};
          if (payload.steps && payload.steps.length) {
            renderSteps(payload.steps, payload.complete_ready);
          } else {
            btn.classList.toggle('is-done', done);
            btn.setAttribute('aria-pressed', done ? 'true' : 'false');
            syncComplete();
          }
          setStatus(savedText(done ? '체크했어요' : '체크를 풀었어요'), 'ok');
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
          noteResult(result);
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
          setStatus(netEl ? savedText('') + ' · 불량을 알렸어요' : '불량을 알렸어요', 'ok');
        });
    }

    // 회색 [제작 완료] — 단추 자리에서 먼저 받아 막는다(옆 시트는 단추가 공정 루트 밖). 문서 위임(tablet-domain-sheets.js)까지 안 간다.
    if (completeBtn) {
      completeBtn.addEventListener('click', function (e) {
        if (completeBtn.getAttribute('aria-disabled') !== 'true') { return; }
        e.preventDefault();
        e.stopPropagation();
        setStatus(completeBlockedText(), 'bad');
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

  // 뒤로 단추(전체 화면 시트만): 생산 첫 화면에서 왔으면 그 주소(고른 날·탭)로 돌아간다.
  // 같은 출처 + 같은 경로일 때만 바꾼다(다른 곳 주소로는 절대 안 보냄). 옆 시트엔 단추가 없어 아무 일도 안 한다.
  function restoreBackLink() {
    var back = document.querySelector('[data-foms-prod-back]');
    if (!back || !document.referrer) { return; }
    try {
      var from = new URL(document.referrer);
      var home = new URL(back.getAttribute('href') || '', window.location.href);
      if (from.origin !== window.location.origin || from.pathname !== home.pathname) { return; }
      back.setAttribute('href', from.pathname + from.search);
    } catch (e) { /* 주소를 못 읽으면 기본 주소 그대로 */ }
  }
  restoreBackLink();
  initAll();
  document.addEventListener('foms:erp-shell-fragment-swapped', initAll);
  document.addEventListener('foms:main-content-swapped', initAll);
  window.FomsProductionSheetPage = { init: initAll };
})();
