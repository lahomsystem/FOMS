/* 생산팀 첫 화면(전체 주문 한 줄) — 탭·찾기·받은 시각·연결 표시. 설계서 §12 (2026-11-09).
 * 서버가 전부 그려 두고, 여기서는 보이기/숨기기만 한다(새 요청 없음). "다시 받기"는 링크(새로고침). */
(function () {
  'use strict';

  var root = document.querySelector('[data-foms-prod-home]');
  if (!root) { return; }

  var tabs = [].slice.call(root.querySelectorAll('[data-foms-home-view]'));
  var jobs = [].slice.call(root.querySelectorAll('[data-foms-home-job]'));
  var days = [].slice.call(root.querySelectorAll('[data-foms-home-day]'));
  var search = root.querySelector('[data-foms-home-q]');
  var none = root.querySelector('[data-foms-home-none]');
  var sync = root.querySelector('[data-foms-home-sync]');
  var view = 'all';
  var term = '';

  function matches(job) {
    if (view === 'prod' && job.getAttribute('data-view') !== 'prod') { return false; }
    if (view === 'changed' && job.getAttribute('data-changed') !== '1') { return false; }
    if (term && (job.getAttribute('data-q') || '').indexOf(term) < 0) { return false; }
    return true;
  }

  function apply() {
    var shown = 0;
    var dayHasJob = {};
    jobs.forEach(function (job) {
      var ok = matches(job);
      job.hidden = !ok;
      if (ok) {
        shown += 1;
        dayHasJob[job.getAttribute('data-day')] = true;
      }
    });
    days.forEach(function (day) {
      day.hidden = !dayHasJob[day.getAttribute('data-foms-home-day')];
    });
    if (none) { none.hidden = shown > 0 || jobs.length === 0; }
  }

  tabs.forEach(function (tab) {
    tab.addEventListener('click', function () {
      view = tab.getAttribute('data-foms-home-view') || 'all';
      tabs.forEach(function (other) {
        var on = other === tab;
        other.classList.toggle('is-on', on);
        other.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
      apply();
    });
  });

  if (search) {
    search.addEventListener('input', function () {
      term = (search.value || '').trim().toLowerCase();
      apply();
    });
  }

  // 받은 시각 — 1분마다 "N분 전에 받음". 10분 넘으면 점이 노랗게.
  var loadedAt = Date.parse(root.getAttribute('data-loaded-at') || '');
  function tick() {
    if (!sync || isNaN(loadedAt)) { return; }
    var minutes = Math.floor((Date.now() - loadedAt) / 60000);
    sync.textContent = minutes < 1 ? '방금 받음' : (minutes + '분 전에 받음');
    sync.classList.toggle('is-stale', minutes >= 10);
  }
  tick();
  window.setInterval(tick, 60000);

  // 연결 끊김(D5) — 표시만. 보이는 목록은 받은 시각 것이라고 적어 둔다.
  function onlineState() {
    root.classList.toggle('is-offline', !navigator.onLine);
  }
  window.addEventListener('online', onlineState);
  window.addEventListener('offline', onlineState);
  onlineState();
})();
