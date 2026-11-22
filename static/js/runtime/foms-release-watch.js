/* 열어 둔 탭도 새 화면으로 — 새 배포가 나가면 한가할 때 문서를 한 번 새로 읽는다(STALE-TAB-01, 2026-11-22).

   2026-11-21 운영: 공장 태블릿이 03:39 UTC 에 연 생산 첫 화면이 뒤에서 멈췄다가 10:47 에 깨어났는데, 그 사이 나간 배포를
   못 받고 옛 HTML · 옛 핀 CSS/JS 를 그대로 보였다(셸은 깨어날 때 미리 받아 둔 조각만 다시 받는다). 자산 핀이 릴리스마다
   바뀌므로 조각 갈아 끼우기로는 모자라고 문서를 통째로 새로 읽어야 한다.

   견주는 값: 이 문서를 그린 릴리스(이 <script> 의 data-foms-release, layout_scripts.html) ↔ 서버의 지금 릴리스
   (foms/services/common/release_watch.py — HTML · 셸 조각 응답 머리글 X-Foms-Release, GET /api/foms/release).
   묻는 때: 다시 보일 때 · bfcache 복귀 · 망 복귀 · 캐시에서 꺼낸 문서 · 보이는 동안 5분마다(셸 하트비트 · 이동 응답 머리글로
   이미 들었으면 건너뛴다 — erp-shell.js 가 FOMS_RELEASE_WATCH.observe 를 부른다).
   새로 읽는 때: 다를 때, 안전할 때만 — 보임 · 온라인 · 인쇄 아님 · 30초 손대지 않음 · 쓰기 요청 없음 · 글 칸 커서 없음 · 고친 칸
   (찾을 말을 쳐 둔 검색 칸 포함) 없음 · 바쁨 표시 없음 · 열린 창(모달 · 시트 · 사진 보기 — 뒤를 막지 않는 붙박이 패널은 빼고) 없음 · 1분 안에 서버가 새 릴리스로 답함(배포 중 502 에 읽지 않게).
   안전하지 않으면 15초 뒤 다시 본다. 숨으면 멈추고 다시 보일 때 처음부터.
   되풀이 방지: sessionStorage `바라던|시각|횟수|떠난`. 같은 릴리스로 2번까지, 두 번째는 5분 뒤(롤링 배포 중 옛 컨테이너가
   받았거나 페이지의 나가기 확인 창에서 머문 경우). 떠난 릴리스는 10분 동안 다시 좇지 않는다(배포 중 옛 · 새 컨테이너가 번갈아
   답해도 오가며 읽지 않게 — 그 뒤의 되돌리기 배포는 따른다). 저장소를 못 쓰면 새로 읽지 않는다
   (foms-wide-surface-recover.js 와 같은 꼴). 한 번만 묶는다(퍼포먼스 가드 G4). */
(function () {
  'use strict';
  if (window.__FOMS_RELEASE_WATCH_BOUND) return;
  window.__FOMS_RELEASE_WATCH_BOUND = true;

  var tag = document.currentScript || document.querySelector('script[data-foms-release]');
  var PAGE_RELEASE = (tag && tag.getAttribute('data-foms-release')) || '';
  if (!PAGE_RELEASE) return; // 서버가 알릴 값이 없다(워커마다 다른 식별자 등) — 아무것도 하지 않는다.

  var ENDPOINT = '/api/foms/release';
  var GUARD_KEY = 'foms_release_reload';
  var MIN = 60 * 1000;
  var CHECK_EVERY_MS = 5 * MIN;
  var QUIET_MS = 30 * 1000;
  var RETRY_MS = 15 * 1000;
  var HEARD_FRESH_MS = MIN;
  var SECOND_TRY_AFTER_MS = 5 * MIN;
  var LEFT_MEMORY_MS = 10 * MIN;
  var MAX_TRIES = 2;
  /** 열린 창. aria-modal="false" 인 창은 뒤를 막지 않는 붙박이 패널(대시보드 태블릿 오른쪽 도킹 시트, tablet-side-sheet.js)이라
      빼고, 같은 시트가 도킹 없이 밀려 나와 주문을 보이는 동안(is-open)만 따로 센다(2026-11-22 터치 감사 — 도킹 시트 때문에 늘 '열린 창'). */
  var OVERLAY_SELECTOR = 'dialog[open], .modal.show, .offcanvas.show, [aria-modal="true"], [role="dialog"]:not([aria-modal="false"]), ' +
    '[role="alertdialog"]:not([aria-modal="false"]), .foms-tablet-sheet.is-open:not(.foms-tablet-sheet--docked)';
  /** html · body 에 다는 열림 표시(modal-open · foms-lightbox-open · foms-tower-sheet-open · foms-mdel-lock …). */
  var OPEN_CLASS_RE = /(^|\s)(modal-open|[\w-]+-open|[\w-]+-lock)(?=\s|$)/;
  var NOT_TEXT_TYPES = /^(checkbox|radio|range|color|file|button|submit|reset|image|hidden)$/;
  var CHOICE_TYPES = /^(checkbox|radio|range|color|file)$/;

  var nativeFetch = window.fetch;
  var pending = '';
  var lastHeardTs = Date.now();
  var lastActivityTs = 0;
  var checking = false;
  var timer = 0;
  var writes = 0;
  var printing = false;
  var edited = [];
  var storageWarned = false;

  /** @param {'get'|'set'} op  실패하면 undefined(1회 경고) — 그러면 새로 읽지 않는다. */
  function guard(op, value) {
    try {
      if (op === 'get') return window.sessionStorage.getItem(GUARD_KEY);
      window.sessionStorage.setItem(GUARD_KEY, value);
      return value;
    } catch (e) {
      if (!storageWarned) console.warn('[foms-release-watch] sessionStorage 사용 불가 — 새 배포 새로고침을 하지 않는다:', e);
      storageWarned = true;
      return undefined;
    }
  }

  /** 표식 `바라던|시각|횟수|떠난` → 기록(없거나 모양이 다르면 null). 저장소 실패면 undefined. 릴리스 값에 | 는 없다(서버가 거른다). */
  function readGuard() {
    var raw = guard('get');
    if (raw === undefined) return undefined;
    var p = String(raw || '').split('|');
    return p.length === 4 ? { to: p[0], at: Number(p[1]) || 0, n: Number(p[2]) || 0, from: p[3] } : null;
  }

  function inputType(el) { return String(el.type || 'text').toLowerCase(); }

  function isTextEntry(el) {
    if (!el || el.nodeType !== 1) return false;
    if (el.isContentEditable || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') return true;
    return el.tagName === 'INPUT' && !NOT_TEXT_TYPES.test(inputType(el));
  }

  /** 고친 칸으로 칠 것 — 글 칸(검색 칸 포함) · 폼 안의 고르기 칸. 폼 밖 체크는 누르는 즉시 저장하는 단추다. */
  function countsAsEdit(el) {
    if (!el || el.nodeType !== 1 || el.tagName !== 'INPUT') return isTextEntry(el);
    if (CHOICE_TYPES.test(inputType(el))) return !!el.form;
    return isTextEntry(el);
  }

  function selectChanged(el) {
    var def = -1;
    for (var i = 0; i < el.options.length; i += 1) {
      if (el.multiple && el.options[i].selected !== el.options[i].defaultSelected) return true;
      if (el.options[i].defaultSelected && def < 0) def = i;
    }
    return !el.multiple && el.selectedIndex !== (def < 0 ? 0 : def);
  }

  /** 아직 문서에 있고 서버가 그린 값과 다른가(되돌렸거나 화면이 바뀌어 칸이 사라졌으면 고친 칸이 아니다). */
  function stillChanged(el) {
    if (el.isContentEditable) return true;
    if (el.tagName === 'SELECT') return selectChanged(el);
    var type = inputType(el);
    if (type === 'checkbox' || type === 'radio') return el.checked !== el.defaultChecked;
    if (type === 'file') return !!(el.files && el.files.length);
    // 검색 칸: 쳐 둔 찾을 말이 새로 읽으면 사라진다(실측 · AS · 완료, 11-22). 비웠거나 닫힌 창 속(그려지지 않음)이면 아니다.
    if (type === 'search') return el.value !== el.defaultValue && el.getClientRects().length > 0;
    return el.value !== el.defaultValue;
  }

  function hasUnsavedEdits() {
    edited = edited.filter(function (el) { return el.isConnected; });
    return edited.some(stillChanged);
  }

  function shown(el) {
    if (el.closest('[hidden], [aria-hidden="true"], [inert]')) return false;
    var r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1 || r.right <= 0 || r.bottom <= 0 || r.left >= window.innerWidth || r.top >= window.innerHeight) {
      return false; // 화면 밖으로 밀어 둔 닫힌 시트
    }
    var cs = window.getComputedStyle(el);
    return cs.display !== 'none' && cs.visibility !== 'hidden' && Number(cs.opacity) !== 0;
  }

  function overlayOpen() {
    var classes = String(document.documentElement.className || '') + ' ' + String((document.body && document.body.className) || '');
    if (OPEN_CLASS_RE.test(classes)) return true;
    var nodes = document.querySelectorAll(OVERLAY_SELECTOR);
    for (var i = 0; i < nodes.length; i += 1) {
      if (shown(nodes[i])) return true;
    }
    return false;
  }

  /** 지금 새로 읽으면 안 되는 이유(없으면 빈 문자열). */
  function unsafeReason() {
    if (document.visibilityState !== 'visible') return 'hidden';
    if (navigator.onLine === false) return 'offline';
    if (printing) return 'printing';
    if (Date.now() - lastActivityTs < QUIET_MS) return 'active';
    if (writes > 0) return 'saving';
    if (isTextEntry(document.activeElement)) return 'typing';
    if (hasUnsavedEdits()) return 'unsaved';
    if (document.querySelector('[aria-busy="true"]') || (document.body && document.body.classList.contains('is-nav-loading'))) {
      return 'busy';
    }
    return overlayOpen() ? 'overlay' : '';
  }

  function schedule(ms) {
    window.clearTimeout(timer);
    timer = pending ? window.setTimeout(step, ms) : 0;
  }

  function step() {
    timer = 0;
    if (!pending || document.visibilityState !== 'visible') return; // 다시 보일 때 처음부터(visibilitychange)
    var g = readGuard();
    var tries = g && g.to === pending ? g.n : 0;
    if (g === undefined || tries >= MAX_TRIES) return; // 저장소 없음 · 이 릴리스로 이미 2번 — 멈춘다
    if ((tries > 0 && Date.now() - g.at < SECOND_TRY_AFTER_MS) || unsafeReason()) return schedule(RETRY_MS);
    // 오래전에 들은 값 — 서버가 지금도 새 릴리스로 답하는지 한 번 더(답하면 observe → 다시 여기).
    if (Date.now() - lastHeardTs > HEARD_FRESH_MS) return check();
    if (guard('set', [pending, Date.now(), tries + 1, PAGE_RELEASE].join('|')) === undefined) return;
    console.info('[foms-release-watch] 새 배포 ' + pending + ' — 지금 화면(' + PAGE_RELEASE + ')을 새로 읽는다');
    window.location.reload();
  }

  /** 서버가 알린 지금 릴리스(머리글 · API 값). 셸(erp-shell.js)도 조각 응답마다 부른다. */
  function observe(release) {
    var value = String(release || '').trim();
    if (!value) return;
    lastHeardTs = Date.now();
    var g = readGuard();
    var justLeft = !!g && g.from === value && Date.now() - g.at < LEFT_MEMORY_MS; // 방금 떠나온 옛 릴리스(배포 중 옛 컨테이너)
    pending = value === PAGE_RELEASE || justLeft ? '' : value; // 같으면 기다리던 것도 거둔다
    schedule(0);
  }

  function check() {
    if (checking || navigator.onLine === false || typeof nativeFetch !== 'function') return;
    checking = true;
    nativeFetch.call(window, ENDPOINT, { credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        if (!data || !data.success || !data.data) throw new Error('응답 모양이 다르다');
        checking = false;
        observe(data.data.release);
      })
      .catch(function (e) {
        checking = false;
        console.info('[foms-release-watch] 릴리스 확인 실패 — 지금 화면을 그대로 둔다:', e && e.message ? e.message : e);
        if (pending) schedule(MIN);
      });
  }

  function isWrite(method) {
    var m = String(method || 'GET').toUpperCase();
    return m !== 'GET' && m !== 'HEAD' && m !== 'OPTIONS';
  }

  /** 쓰기(fetch · XHR — R2 직접 올리기 포함) 비행 수. 새로 읽으면 끊기므로 0 일 때만 새로 읽는다. */
  function trackWrites() {
    if (typeof nativeFetch === 'function') {
      window.fetch = function (input, init) {
        var method = (init && init.method) || (input && typeof input === 'object' && input.method) || 'GET';
        var p = nativeFetch.apply(this || window, arguments);
        if (isWrite(method) && p && typeof p.then === 'function') {
          writes += 1;
          var done = function () { writes -= 1; };
          p.then(done, done);
        }
        return p;
      };
    }
    var proto = window.XMLHttpRequest && window.XMLHttpRequest.prototype;
    if (!proto) return;
    var open = proto.open;
    var send = proto.send;
    proto.open = function (method) {
      this.__fomsReleaseWatchWrite = isWrite(method);
      return open.apply(this, arguments);
    };
    proto.send = function () {
      if (!this.__fomsReleaseWatchWrite) return send.apply(this, arguments);
      var xhr = this;
      var done = function () { xhr.removeEventListener('loadend', done); writes -= 1; };
      writes += 1;
      xhr.addEventListener('loadend', done);
      try {
        return send.apply(this, arguments);
      } catch (e) {
        done();
        throw e;
      }
    };
  }

  function onEdit(e) {
    var el = e && e.target;
    if (countsAsEdit(el) && edited.indexOf(el) === -1 && edited.length < 50) edited.push(el);
  }

  /** 탭 되살리기 · 뒤로 가기는 디스크 캐시의 옛 문서를 꺼낼 수 있다. */
  function servedFromCache() {
    var perf = window.performance;
    var nav = perf && typeof perf.getEntriesByType === 'function' ? perf.getEntriesByType('navigation')[0] : null;
    return !!nav && (nav.type === 'back_forward' || (nav.transferSize === 0 && nav.decodedBodySize > 0));
  }

  trackWrites();
  ['pointerdown', 'pointermove', 'keydown', 'wheel', 'touchstart', 'scroll'].forEach(function (evt) {
    document.addEventListener(evt, function () { lastActivityTs = Date.now(); }, { passive: true, capture: true });
  });
  document.addEventListener('input', onEdit, true);
  document.addEventListener('change', onEdit, true);
  window.addEventListener('beforeprint', function () { printing = true; });
  window.addEventListener('afterprint', function () { printing = false; });
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') check();
  });
  window.addEventListener('pageshow', function (e) {
    if (e && e.persisted) check();
  });
  window.addEventListener('online', check);
  window.setInterval(function () {
    if (document.visibilityState === 'visible' && Date.now() - lastHeardTs >= CHECK_EVERY_MS) check();
  }, MIN);

  window.FOMS_RELEASE_WATCH = { page: PAGE_RELEASE, observe: observe, check: check, why: unsafeReason };
  if (servedFromCache()) {
    lastHeardTs = 0;
    check();
  }
})();
