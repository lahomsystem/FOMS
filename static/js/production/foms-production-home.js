/* 생산팀 첫 화면(전체 주문 한 줄) — 날짜 묶음 접기/펴기·탭·찾기·받은 시각·연결 표시. 설계서 §12 (2026-11-09).
 * 서버가 전부 그려 두고, 여기서는 보이기/숨기기만 한다(새 요청 없음). "다시 받기"는 링크(새로고침).
 * 접기/펴기는 모바일 실측 탭(measurement/mobile-glance-tabs.js)과 같은 말: is-closed · aria-expanded · 모두 펼치기/접기. */
(function () {
  'use strict';

  var root = document.querySelector('[data-foms-prod-home]');
  if (!root) { return; }

  function toArr(list) { return [].slice.call(list); }

  var tabs = toArr(root.querySelectorAll('[data-foms-home-view]'));
  var jobs = toArr(root.querySelectorAll('[data-foms-home-job]'));
  var groups = toArr(root.querySelectorAll('[data-foms-home-grp]'));
  var search = root.querySelector('[data-foms-home-q]');
  var none = root.querySelector('[data-foms-home-none]');
  var sync = root.querySelector('[data-foms-home-sync]');
  var view = 'all';
  var term = '';

  // ── 날짜 묶음 접기/펴기 ──
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

  // ── 탭·찾기 필터 ──
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
      var rows = toArr(grp.querySelectorAll('[data-foms-home-job]'));
      var hit = rows.filter(function (job) { return !job.hidden; }).length;
      grp.hidden = hit === 0;
      var count = grp.querySelector('[data-foms-home-grp-count]');
      if (count) { count.textContent = hit + '건'; }
      // 거르는 중엔 맞는 묶음을 펼쳐 둔다 — 접힌 채로는 찾은 줄이 안 보인다.
      if (filtering && hit > 0) { setOpen(grp, true); }
    });
    if (none) { none.hidden = shown > 0 || jobs.length === 0; }
    syncCtl();
  }

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
    }
  });

  if (search) {
    search.addEventListener('input', function () {
      term = (search.value || '').trim().toLowerCase();
      apply();
    });
  }

  // ── 받은 시각 — 1분마다 "N분 전에 받음". 10분 넘으면 점이 노랗게. ──
  var loadedAt = Date.parse(root.getAttribute('data-loaded-at') || '');
  function tick() {
    if (!sync || isNaN(loadedAt)) { return; }
    var minutes = Math.floor((Date.now() - loadedAt) / 60000);
    sync.textContent = minutes < 1 ? '방금 받음' : (minutes + '분 전에 받음');
    sync.classList.toggle('is-stale', minutes >= 10);
  }
  tick();
  window.setInterval(tick, 60000);

  // ── 연결 끊김(D5) — 표시만. 보이는 목록은 받은 시각 것이라고 적어 둔다. ──
  function onlineState() {
    root.classList.toggle('is-offline', !navigator.onLine);
  }
  window.addEventListener('online', onlineState);
  window.addEventListener('offline', onlineState);
  onlineState();
})();
