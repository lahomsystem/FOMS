/* 생산팀 첫 화면 — 탭(날짜·내 공정·바뀐 것·찾기) 공통 JS. 설계서 §12 (2026-11-09 · D18 11-10).
 * 날짜: 왼쪽 띠에서 날을 고르면 오른쪽 한 장만 바뀐다(보이기/숨기기, 새 요청 없음) — 주소와 [다시 받기]도 그날로.
 * 전체 주문: 날짜 묶음 접기/펴기·보기 칸·찾기(보이기/숨기기만, 새 요청 없음). 접기/펴기는 모바일 실측 탭
 * (measurement/mobile-glance-tabs.js)과 같은 말: is-closed · aria-expanded · 모두 펼치기/접기.
 * 내 공정: 공정 탭(마지막 탭은 이 브라우저에 기억) · [<공정> 끝] = POST /api/orders/<id>/production/steps {key, done:true}.
 * 바뀐 것의 [확인했어요] 는 tablet-domain-sheets.js(change-ack) 몫. 실패 글은 설계서 §8 한 가지. */
(function () {
  'use strict';

  var root = document.querySelector('[data-foms-prod-home]');
  if (!root) { return; }

  var OFFLINE_TEXT = '연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요.';
  var STEP_TAB_KEY = 'foms-prod-step-tab';
  function toArr(list) { return [].slice.call(list); }

  var statusEl = root.querySelector('[data-foms-home-status]');
  function setStatus(text, bad) {
    if (!statusEl) { return; }
    statusEl.textContent = text || '';
    statusEl.classList.toggle('is-bad', !!bad);
  }

  // ── 전체 주문: 날짜 묶음 접기/펴기 + 보기 칸 + 찾기 ──
  var tabs = toArr(root.querySelectorAll('[data-foms-home-view]'));
  var jobs = toArr(root.querySelectorAll('[data-foms-home-job]'));
  var groups = toArr(root.querySelectorAll('[data-foms-home-grp]'));
  var search = root.querySelector('[data-foms-home-q]');
  var none = root.querySelector('[data-foms-home-none]');
  var view = 'all';
  var term = '';

  function setOpen(grp, open) {
    grp.classList.toggle('is-closed', !open);
    var tog = grp.querySelector('[data-foms-home-tog]');
    if (tog) { tog.setAttribute('aria-expanded', open ? 'true' : 'false'); }
  }
  function syncCtl() {
    var visible = groups.filter(function (g) { return !g.hidden; });
    var openCount = root.querySelector('[data-foms-home-open-count]');
    if (openCount) {
      openCount.textContent = String(visible.filter(function (g) { return !g.classList.contains('is-closed'); }).length);
    }
    var anyClosed = visible.some(function (g) { return g.classList.contains('is-closed'); });
    var all = root.querySelector('[data-foms-home-all]');
    if (all) { all.setAttribute('data-foms-home-all', anyClosed ? 'open' : 'close'); }
    var label = root.querySelector('[data-foms-home-all-label]');
    if (label) { label.textContent = anyClosed ? '모두 펼치기' : '모두 접기'; }
  }
  function matches(job) {
    if (view === 'prod' && job.getAttribute('data-view') !== 'prod') { return false; }
    if (view === 'changed' && job.getAttribute('data-changed') !== '1') { return false; }
    if (term && (job.getAttribute('data-q') || '').indexOf(term) < 0) { return false; }
    return true;
  }
  function apply() {
    var shown = 0;
    jobs.forEach(function (job) {
      var ok = matches(job);
      job.hidden = !ok;
      if (ok) { shown += 1; }
    });
    var filtering = view !== 'all' || !!term;
    groups.forEach(function (grp) {
      var hit = toArr(grp.querySelectorAll('[data-foms-home-job]')).filter(function (j) { return !j.hidden; }).length;
      grp.hidden = hit === 0;
      var count = grp.querySelector('[data-foms-home-grp-count]');
      if (count) { count.textContent = hit + '건'; }
      if (filtering && hit > 0) { setOpen(grp, true); } // 거르는 중엔 맞는 묶음을 펼쳐 둔다
    });
    if (none) { none.hidden = shown > 0 || jobs.length === 0; }
    syncCtl();
  }
  if (search) {
    search.addEventListener('input', function () {
      term = (search.value || '').trim().toLowerCase();
      apply();
    });
  }

  // ── 날짜(안 3): 띠는 제목 줄 바로 아래에 붙는다 — 제목 줄 높이를 재서 CSS 변수로(줄이 접혀도 안 겹치게) ──
  var bar = root.querySelector('.foms-prod-home__bar');
  function syncBarHeight() { if (bar) { root.style.setProperty('--fph-bar-h', bar.offsetHeight + 'px'); } }
  syncBarHeight();
  window.addEventListener('resize', syncBarHeight);
  if (window.ResizeObserver && bar) { new ResizeObserver(syncBarHeight).observe(bar); }

  // ── 날짜(안 3): 날 고르기 ──
  var dayBtns = toArr(root.querySelectorAll('[data-foms-home-daybtn]'));
  function selectDay(key) {
    dayBtns.forEach(function (b) {
      var on = b.getAttribute('data-foms-home-daybtn') === key;
      b.classList.toggle('is-on', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    toArr(root.querySelectorAll('[data-foms-home-daypane]')).forEach(function (p) {
      p.hidden = p.getAttribute('data-foms-home-daypane') !== key;
    });
    var url = window.location.pathname + '?day=' + encodeURIComponent(key);
    try { window.history.replaceState(null, '', url); } catch (e) { /* 주소를 못 바꿔도 화면은 그대로 */ }
    var reload = root.querySelector('[data-foms-home-reload]');
    if (reload) { reload.setAttribute('href', url); }
    window.scrollTo(0, 0);
  }

  // ── 내 공정: 탭 기억 + [끝] ──
  var stepTabs = toArr(root.querySelectorAll('[data-foms-home-steptab]'));
  function selectStepTab(key) {
    if (!stepTabs.length) { return; }
    var known = stepTabs.some(function (t) { return t.getAttribute('data-foms-home-steptab') === key; });
    if (!known) { key = stepTabs[0].getAttribute('data-foms-home-steptab'); }
    stepTabs.forEach(function (t) {
      var on = t.getAttribute('data-foms-home-steptab') === key;
      t.classList.toggle('is-on', on);
      t.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    toArr(root.querySelectorAll('[data-foms-home-stepq]')).forEach(function (q) {
      q.hidden = q.getAttribute('data-foms-home-stepq') !== key;
    });
    try { window.localStorage.setItem(STEP_TAB_KEY, key); } catch (e) { /* 저장 못 해도 화면은 그대로 */ }
  }
  if (stepTabs.length) {
    var saved = null;
    try { saved = window.localStorage.getItem(STEP_TAB_KEY); } catch (e) { saved = null; }
    selectStepTab(saved || stepTabs[0].getAttribute('data-foms-home-steptab'));
  }
  function mutate(url, body) {
    var opts = { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) };
    if (window.fomsMutationFetch) { return window.fomsMutationFetch(url, opts); }
    return (window.fomsWriteFetch || fetch)(url, opts).then(function (res) {
      return res.json().catch(function () { return null; }).then(function (data) {
        var ok = !!data && res.ok && data.success !== false;
        return { ok: ok, kind: ok ? 'ok' : 'error', status: res.status, data: data || {},
          message: (data && (data.error || data.message)) || ('HTTP ' + res.status) };
      });
    }).catch(function () { return { ok: false, kind: 'network', status: 0, data: {}, message: OFFLINE_TEXT }; });
  }
  function finishStep(btn) {
    if (btn.disabled) { return; }
    var orderId = btn.getAttribute('data-order-id');
    var key = btn.getAttribute('data-step-key');
    btn.disabled = true;
    setStatus('저장하는 중…');
    mutate('/api/orders/' + encodeURIComponent(orderId) + '/production/steps', { key: key, done: true })
      .then(function (result) {
        if (!result.ok) {
          btn.disabled = false;
          setStatus(result.kind === 'network' || result.status === 0 ? OFFLINE_TEXT : ('오류: ' + (result.message || '처리하지 못했어요')), true);
          return;
        }
        setStatus('끝냈어요. 다음 공정으로 옮겨요');
        window.location.reload(); // 줄·숫자는 서버가 다시 그린다(탭은 기억됨)
      });
  }

  // ── 클릭 위임(이 화면 안) ──
  root.addEventListener('click', function (e) {
    var t = e.target;
    if (!t || typeof t.closest !== 'function') { return; }
    var tog = t.closest('[data-foms-home-tog]');
    if (tog) {
      var grp = tog.closest('[data-foms-home-grp]');
      if (grp) { setOpen(grp, grp.classList.contains('is-closed')); syncCtl(); }
      return;
    }
    var all = t.closest('[data-foms-home-all]');
    if (all) {
      var open = all.getAttribute('data-foms-home-all') === 'open';
      groups.forEach(function (g) { if (!g.hidden) { setOpen(g, open); } });
      syncCtl();
      return;
    }
    var tab = t.closest('[data-foms-home-view]');
    if (tab) {
      view = tab.getAttribute('data-foms-home-view') || 'all';
      tabs.forEach(function (other) {
        var on = other === tab;
        other.classList.toggle('is-on', on);
        other.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
      apply();
      return;
    }
    var dayBtn = t.closest('[data-foms-home-daybtn]');
    if (dayBtn) { selectDay(dayBtn.getAttribute('data-foms-home-daybtn')); return; }
    var stepTab = t.closest('[data-foms-home-steptab]');
    if (stepTab) { selectStepTab(stepTab.getAttribute('data-foms-home-steptab')); return; }
    var done = t.closest('[data-foms-home-step-done]');
    if (done) { finishStep(done); }
  });

  // ── 받은 시각 — 1분마다 "N분 전에 받음". 10분 넘으면 점이 노랗게. ──
  var sync = root.querySelector('[data-foms-home-sync]');
  var loadedAt = Date.parse(root.getAttribute('data-loaded-at') || '');
  function tick() {
    if (!sync || isNaN(loadedAt)) { return; }
    var minutes = Math.floor((Date.now() - loadedAt) / 60000);
    sync.textContent = minutes < 1 ? '방금 받음' : (minutes + '분 전에 받음');
    sync.classList.toggle('is-stale', minutes >= 10);
  }
  tick();
  window.setInterval(tick, 60000);

  // ── 연결 끊김(D5) — 표시만. ──
  function onlineState() { root.classList.toggle('is-offline', !navigator.onLine); }
  window.addEventListener('online', onlineState);
  window.addEventListener('offline', onlineState);
  onlineState();
})();
