/**
 * 생산 현장 알람 화면 — 설계서 docs/specs/2026-11-28-production-floor-alarm_SPEC.md §2-2 · §2-4 · §3-3 · §4-7 · §6-4.
 * 띠(머리 줄 아래 한 줄 · "1/3") · 소리 단추 글 · 화면 안 꺼지게 · 멈춤을 새 일보다 먼저 · 합친 알람 글 갈아 끼우기 ·
 * 서버가 닫은 알람 치우기 · [확인] 뒤 그 주문 생산 화면으로 · 다시 받기(GET /api/production/alarms/pending — 없거나
 * 실패면 조용히). 전체 화면 창 · 색 · 소리는 공용(foms-urgent-alert.js · .css · urgent-sound.js)이 맡는다.
 * 실시간 값(약속 6)은 urgent · floor_notice · floor_closed 만 본다(kind · notice · interrupt 칸은 안 읽는다).
 * flag_floor_alarm 이 참일 때만 실린다(templates/production/partials/floor_alarm.html — 문서당 한 번).
 */
(function () {
  'use strict';
  if (window.FOMSFloorAlarm) return;

  var PENDING = '/api/production/alarms/pending', HOME = '/erp/production/home';
  var FLOOR = 'PRODUCTION_FLOOR_', STOP = 'PRODUCTION_FLOOR_STOP'; // 화면은 알림 종류 앞머리만 본다(약속 5)
  var MIN_GAP_MS = 30000; // 다시 받기 최소 간격(긴급 창 다시 띄우기와 같은 값) — 소켓 붙음 · 줄 빔은 바로 묻는다
  var LABEL = { on: '소리 켬', locked: '소리 켜기', off: '소리 꺼짐' };

  var bands = [];   // 띠 줄 — 한 번에 한 건
  var seen = {};    // 알림 번호 → 긴급 창에 넘긴 값(합친 알람 글 갈아 끼우기)
  var gone = {};    // 확인했거나 서버가 닫은 번호
  var shown = null; // 지금 전체 화면 창에 뜬 건(foms:urgent-shown)
  var goTo = '';    // [확인]으로 줄이 비면 갈 주소
  var band = null, lock = null, locking = false, bound = null, channel = null;
  var lastAsk = 0, asking = false, bandBusy = false;

  function idOf(x) { return x && x.notification_id != null && x.notification_id !== '' ? String(x.notification_id) : ''; }
  function typeOf(x) { return String((x && x.notification_type) || ''); }
  function isFloor(x) { return typeOf(x).indexOf(FLOOR) === 0; }
  function isStop(x) { return typeOf(x).indexOf(STOP) === 0; }
  function home() { return document.querySelector('[data-foms-floor-sound]'); } // 생산 화면 = 소리 단추가 있는 문서
  function orderHref(x) { var n = parseInt(x && x.order_id, 10); return n > 0 ? HOME + '?order=' + n : ''; }

  // 이미 그 주문 화면이면(첫 화면 ?order= 또는 그 주문 작업 시트) 창만 닫힌다(§2-2).
  function here(n) {
    var loc = window.location || {};
    if (loc.pathname === HOME && new URLSearchParams(loc.search || '').get('order') === String(n)) return true;
    var sheet = document.querySelector('[data-foms-prod-sheet-page]');
    return !!sheet && sheet.getAttribute('data-order-id') === String(n);
  }
  function go(href) { // 갔으면 참
    if (!href || here(parseInt(String(href).split('order=')[1], 10))) return false;
    window.location.href = href;
    return true;
  }

  function post(id, verb) { // 지금 있는 알림 쓰기 길(같은 출처 머리글)
    var url = '/erp/api/notifications/' + encodeURIComponent(id) + '/' + verb, h = { 'Accept': 'application/json' };
    var W = window.FOMSNotificationWrite;
    if (W && typeof W.fetch === 'function') return W.fetch(url, { method: 'POST', headers: h });
    h['X-FOMS-Notification-Write'] = '1';
    if (typeof window.fomsCsrfToken === 'function') h['X-CSRF-Token'] = window.fomsCsrfToken();
    return window.fetch(url, { method: 'POST', headers: h, credentials: 'same-origin' });
  }

  // ── 전체 화면(긴급) ─────────────────────────────────────────
  function retext(old, x) { // 60초 합치기 — 같은 번호로 고친 글이 다시 온다
    [old, shown].forEach(function (o) { if (o && idOf(o) === idOf(x)) { o.title = x.title; o.message = x.message; } });
    if (idOf(shown) !== idOf(x)) return; // 줄에서 기다리는 건은 값만 바뀌고, 뜰 때 새 글로 그려진다
    var t = document.getElementById('foms-urgent-alert-title'), m = document.getElementById('foms-urgent-alert-message');
    if (t && x.title) t.textContent = String(x.title);
    if (m && x.message) m.textContent = String(x.message);
  }
  function urgent(list) {
    var A = window.FOMSUrgentAlert, first = '';
    if (!A) return;
    list.filter(isStop).concat(list.filter(function (x) { return !isStop(x); })).forEach(function (x) {
      var id = idOf(x);
      if (!id || gone[id] || !isFloor(x)) return;
      if (seen[id] && seen[id] !== x) { retext(seen[id], x); return; }
      var item = x.urgent === true ? x : Object.assign({ urgent: true }, x);
      seen[id] = item;
      A.show(item);
      if (!first && isStop(item)) first = id;
    });
    // 멈춤이 새 일보다 먼저(§2-2): 새 일 창이 떠 있으면 멈춤을 맨 앞으로.
    if (first && shown && isFloor(shown) && !isStop(shown)) A.openFromPush(first);
  }

  // ── 띠(보통) ───────────────────────────────────────────────
  function el(tag, cls, parent, text) {
    var node = document.createElement(tag);
    node.className = cls;
    if (tag === 'button') node.type = 'button';
    if (text) node.textContent = text;
    parent.appendChild(node);
    return node;
  }
  function bandEl() { // 머리 줄(header) 안 맨 끝 — 머리 줄과 같이 위에 붙어 있고, 넘치면 다음 줄 전체를 쓴다(CSS)
    var host = home();
    if (!host) return null;
    if (band && band.isConnected !== false) return band;
    var bar = (host.closest && host.closest('header')) || host.parentNode;
    if (!bar) return null;
    band = el('div', 'foms-floor-band', bar);
    band.setAttribute('data-foms-floor-band', '');
    band.setAttribute('role', 'status');
    band.goBtn = el('button', 'foms-floor-band__go', band);
    band.count = el('span', 'foms-floor-band__count', band);
    band.okBtn = el('button', 'foms-floor-band__ok', band, '확인');
    band.goBtn.addEventListener('click', function () { ackBand(true); });
    band.okBtn.addEventListener('click', function () { ackBand(false); });
    return band;
  }
  function renderBand() {
    var item = bands[0], b = item || band ? bandEl() : null; // 띠가 없으면 그리지도 않는다
    if (!b) return;
    b.hidden = !item;
    if (!item) return;
    b.goBtn.textContent = [item.title, item.message].filter(Boolean).join(' · ').replace(/\s*\n+\s*/g, ' · ');
    b.count.textContent = bands.length > 1 ? '1/' + bands.length : '';
    b.count.hidden = bands.length <= 1;
  }
  function addBands(list, live) {
    var before = bands.length;
    list.forEach(function (x) {
      var id = idOf(x);
      if (id && !gone[id] && !bands.some(function (b) { return idOf(b) === id; })) bands.push(x);
    });
    if (bands.length === before) return;
    renderBand();
    if (live && window.FOMSUrgentSound && window.FOMSUrgentSound.play) window.FOMSUrgentSound.play('band');
  }
  function dropBand(id) {
    bands = bands.filter(function (b) { return idOf(b) !== id; });
    renderBand();
  }
  // [확인] = 확인 기록 + 읽음 기록(지금 있는 두 API — 종 숫자가 같이 준다) 뒤 다음 줄, 마지막 줄이면 그 주문으로.
  // 띠를 누르면 같은 기록 뒤 그 주문으로 바로 간다.
  function ackBand(goNow) {
    var item = bands[0];
    if (!item || bandBusy) return;
    var id = idOf(item), href = orderHref(item);
    bandBusy = true;
    Promise.resolve()
      .then(function () { return post(id, 'ack'); })
      .then(function (res) { return res.status === 404 ? { success: true } : res.json(); })
      .then(function (data) {
        if (!data || !data.success) return;
        gone[id] = true;
        dropBand(id);
        return Promise.resolve().then(function () { return post(id, 'read'); })
          .catch(function () { /* 읽음은 덤 — 확인은 남았다 */ })
          .then(function () {
            var badge = window.FOMSNotificationBadge;
            if (badge && typeof badge.refresh === 'function') badge.refresh({ force: true });
            if (goNow || !bands.length) go(href);
          });
      })
      .catch(function (e) { console.warn('[floor-alarm] 띠 확인 실패:', e); })
      .then(function () { bandBusy = false; });
  }

  // ── 서버가 닫은 알람 치우기(약속 6 floor_closed) ──────────────────
  function close(ids) {
    (Array.isArray(ids) ? ids : []).forEach(function (n) {
      var id = String(n);
      gone[id] = true;
      dropBand(id);
      try { // 긴급 창은 탭 사이 통로의 ack 로 그 건을 뺀다(같은 창 안의 다른 통로 객체에도 간다)
        if (!channel && typeof window.BroadcastChannel === 'function') channel = new window.BroadcastChannel('foms-urgent');
        if (channel) channel.postMessage({ type: 'ack', notification_id: id });
      } catch (e) { console.warn('[floor-alarm] 닫기 전달 실패:', e); }
    });
  }
  function onNote(data) {
    if (!data || typeof data !== 'object') return;
    if (data.floor_closed === true) close(data.notification_ids);
    else if (data.urgent === true) { if (isFloor(data)) urgent([data]); }
    else if (data.floor_notice === true) addBands([data], true);
  }

  // ── 다시 받기(약속 7) — 생산 화면을 열 때 · 다시 보일 때 · 소켓이 붙을 때 · [확인]으로 줄이 비었을 때 ──
  function ask(reason, force) {
    var now = Date.now();
    if (asking || !home() || (!force && now - lastAsk < MIN_GAP_MS)) return;
    lastAsk = now; asking = true;
    Promise.resolve()
      .then(function () { return window.fetch(PENDING, { credentials: 'same-origin', headers: { 'Accept': 'application/json' } }); })
      .then(function (res) { return res && res.ok ? res.json() : null; }) // 404(아직 없는 주소) · 500 = 조용히
      .then(function (data) {
        var d = data && data.success ? data.data : null;
        if (d && Array.isArray(d.urgent)) urgent(d.urgent);
        if (d && Array.isArray(d.notices)) addBands(d.notices, false);
      })
      .catch(function (e) { if (window.FOMS_DEBUG) console.warn('[floor-alarm] 다시 받기 실패(' + reason + '):', e); })
      .then(function () { asking = false; });
  }

  // ── 소리 단추 · 화면 안 꺼지게 ─────────────────────────────────
  function syncSound() {
    var S = window.FOMSUrgentSound, st = S && S.state ? S.state() : 'locked';
    document.querySelectorAll('[data-foms-floor-sound]').forEach(function (b) {
      ['on', 'locked', 'off'].forEach(function (k) { b.classList.toggle('is-' + k, k === st); });
      b.setAttribute('aria-pressed', st === 'on' ? 'true' : 'false');
      var label = b.querySelector('[data-foms-floor-sound-label]'), icon = b.querySelector('i');
      if (label) label.textContent = LABEL[st];
      if (icon) icon.className = st === 'off' ? 'fas fa-volume-mute' : 'fas fa-volume-up';
    });
  }
  function wake() { // 생산 화면이 보이는 동안만(터치 기기) — 숨으면 브라우저가 풀고 다시 보이면 다시 건다. 실패는 조용히.
    var wl = window.navigator && window.navigator.wakeLock;
    var touch = typeof window.matchMedia === 'function' && window.matchMedia('(pointer: coarse)').matches;
    if (!home()) { if (lock) { lock.release().catch(function () {}); lock = null; } return; }
    if (lock || locking || !wl || !touch || document.visibilityState !== 'visible') return;
    locking = true;
    Promise.resolve().then(function () { return wl.request('screen'); })
      .then(function (l) {
        lock = l;
        if (l && l.addEventListener) l.addEventListener('release', function () { if (lock === l) lock = null; });
      })
      .catch(function () { /* 절전 · 배터리 부족 · 지원 안 함 */ })
      .then(function () { locking = false; });
  }

  function bind() { // 공용 머리가 만든 소켓(window.__appSocket)에 하나 더 듣는다 — 다시 만들어지면 새 것에 다시
    var s = window.__appSocket;
    if (!s || s === bound || typeof s.on !== 'function') return;
    bound = s;
    if (s.__fomsFloorBound) return;
    s.__fomsFloorBound = true;
    s.on('erp_notification', onNote);
    s.on('connect', function () { ask('socket-connect', true); });
  }
  function refresh(reason) { bind(); syncSound(); renderBand(); wake(); ask(reason, false); }

  document.addEventListener('foms:urgent-shown', function (e) { shown = (e && e.detail) || null; });
  document.addEventListener('foms:urgent-acked', function (e) {
    var item = e && e.detail;
    if (!isFloor(item)) return;
    gone[idOf(item)] = true;
    goTo = orderHref(item) || goTo;
    setTimeout(function () { // 다음 건이 떠 있으면 다 누른 뒤 마지막 것의 주문으로 간다
      if (document.getElementById('foms-urgent-alert')) return;
      var href = goTo;
      shown = null;
      goTo = '';
      if (!go(href)) ask('emptied', true); // 여섯째부터 이어 띄우기(다른 주문으로 가면 새 화면이 다시 묻는다)
    }, 0);
  });
  document.addEventListener('foms:urgent-sound-state', syncSound);
  document.addEventListener('foms:erp-shell-fragment-swapped', function () { refresh('swap'); });
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'visible') refresh('visible'); });
  setInterval(bind, 5000);

  window.FOMSFloorAlarm = { handle: onNote, resync: ask };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { refresh('load'); }, { once: true });
  } else refresh('load');
})();
