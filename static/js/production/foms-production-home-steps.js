/* 생산 첫 화면 '내 공정' 탭 오른쪽 판(태블릿 가로) — 설계서 docs/specs/2026-11-21-production-my-steps-panel_SPEC.md §3-4 ~ §3-6
 * · 사용자 결정 2026-11-21 "추천안(반반)대로 만들기" · 2026-11-22 "확인 창 빼기"(두 번 누름 + 되돌리기).
 * 줄을 누르면 고른 표시를 바로 바꾸고 판을 바꾼다 — 서버는 공정 줄마다 고른 줄 판 하나만 그리고, 다른 줄 판은 받아 끼운다
 * (foms-production-home-steppane.js, 2026-11-22). 그 파일이 아직 없으면 줄 링크(?tab=steps&order=)가 그대로 그 줄 페이지를 연다.
 * 주소 · [다시 받기]는 고른 줄 링크의 href(?tab=steps&order=<id>, 서버 home_href 가 지은 것)로 맞춘다(replaceState). 공정 탭을 바꾸면
 * 그 탭의 고른 줄로, [보류]를 누르면 그 판의 줄로 맞춘다(보류 뒤 새로고침이 같은 줄로 돌아온다).
 * 큰 [<공정> 끝] = 누르면 바로 POST /api/orders/<id>/production/steps {key, done:true} 한 번(확인 창 없음). 첫 누름부터 답이 올 때까지
 * 판 [끝]은 모두 잠그고, 저장되면 '끝내면 다음은' 줄 주소로 다시 받는다(셸이 있으면 셸 조각 교체). 새 화면이 뜬 뒤 GUARD_MS 동안은
 * 새 판 [끝]도 잠그고 그동안 또 누르면 다시 센다 — 두 번 누름 · 연타가 바뀐 화면의 다음 주문 [끝]에 떨어지지 않게(잠금은
 * aria-disabled + 흐림 — 진짜 disabled 는 누름을 삼켜 연장을 못 한다). 저장 뒤 UNDO_MS 동안 화면 상태 줄에
 * '<손님> <공정> 끝 — [되돌리기]'(48px 이상). [되돌리기] = 같은 공정 API {key, done:false}(공정 칸 끄기와 같은 길) → 그 주문 줄로 다시 받기.
 * 저장 · 되돌리기 실패는 판 · 상태 줄에 글(화면은 그대로). 되돌리기 상태는 셸 교체를 건너 window.__FOMS_PROD_STEPS_BOUND 에 둔다.
 * 그림을 누르면 전역 원본 뷰어(GlobalImageViewer)에 그림 원본 전부(작업 시트와 같은 목록). [불량] = foms-production-sheet-page.js,
 * [보류] = tablet-domain-sheets.js 몫(지금 작업 시트와 같은 길). 판이 안 보이면(태블릿을 세로로 돌림) 줄 이름은 지금처럼 작업 시트로 간다.
 * 폰 · PC 줄 [끝](바로 저장)은 foms-production-home.js 몫 — 이 파일은 판이 있는 화면에만 실린다.
 * 첫 탭: 주소 order= 가 선 공정 탭(서버 data-foms-home-step-pin)을 마지막 탭 기억보다 앞에 — foms-production-home.js 가 읽기 전에 기억을 맞춘다.
 * 셸 조각 교체로 다시 실행된다 — 화면에는 한 번(data-foms-home-steps-bound). 창 · 문서 리스너는 없다. */
(function () {
  'use strict';

  var root = document.querySelector('[data-foms-prod-home]');
  var base = root && root.querySelector('[data-foms-step-base]');
  if (!root || !base || root.getAttribute('data-foms-home-steps-bound') === '1') { return; }
  root.setAttribute('data-foms-home-steps-bound', '1');
  var G = window.__FOMS_PROD_STEPS_BOUND = window.__FOMS_PROD_STEPS_BOUND || {};

  var OFFLINE_TEXT = '연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요.';
  var STEP_TAB_KEY = 'foms-prod-step-tab'; // foms-production-home.js 와 같은 열쇠
  var UNDO_MS = 8000;  // 되돌리기가 보이는 시간
  var GUARD_MS = 600;  // 저장 뒤 새 화면의 [끝]을 잠그는 시간(두 번 누름이 다음 주문에 떨어지지 않게)
  function toArr(list) { return [].slice.call(list || []); }
  function attr(node, name) { return (node && node.getAttribute(name)) || ''; }
  function textOf(scope, sel) { var n = scope && scope.querySelector(sel); return n ? String(n.textContent || '').trim() : ''; }
  function parseList(text) {
    var utils = window.ERPUtils;
    if (utils && typeof utils.safeJsonParse === 'function') { return utils.safeJsonParse(text, []) || []; }
    try { return JSON.parse(text || '[]') || []; } catch (e) { return []; }
  }
  // 카드를 쓴 파트의 [끝]은 서버가 남은 장을 세어 막는다(409 PART_USES_CARDS, 설계서 2026-11-23 §4-2) — 그 글은 서버 글 그대로
  function failText(result) {
    return !result || result.kind === 'network' || result.kind === 'timeout' || result.status === 0 ? OFFLINE_TEXT
      : result.status === 409 && result.message ? result.message : ('오류: ' + (result.message || '처리하지 못했어요'));
  }
  var statusBox = root.querySelector('[data-foms-home-status]');
  function setStatus(text, bad) {
    if (!statusBox) { return; }
    statusBox.classList.remove('is-undo', 'is-err');
    statusBox.textContent = text || '';
    statusBox.classList.toggle('is-bad', !!bad);
  }

  // ── 첫 탭: order= 가 선 탭이 마지막 탭 기억보다 앞(설계서 §3-6) ──
  var pinBox = root.querySelector('[data-foms-home-step-pin]');
  if (pinBox) {
    try { window.localStorage.setItem(STEP_TAB_KEY, attr(pinBox, 'data-foms-home-step-pin')); } catch (e) { /* 기억 못 해도 서버가 그 탭을 그렸다 */ }
  }

  // ── 주소 · [다시 받기] ──
  function rowOf(id) { return id ? root.querySelector('[data-foms-home-qrow="' + id + '"]') : null; }
  function rowHref(row) {
    var link = row && row.querySelector('[data-foms-step-sheet]');
    return link ? attr(link, 'href') : '';
  }
  function keepUrl(href) {
    if (!href) { return; }
    try { window.history.replaceState(window.history.state, '', href); } catch (e) { /* 주소를 못 바꿔도 화면은 그대로 */ }
    var shell = window.FOMS_ERP_SHELL;
    if (shell && typeof shell.syncRenderedUrl === 'function') { shell.syncRenderedUrl(); }
    var reload = root.querySelector('[data-foms-home-reload]');
    if (reload) { reload.setAttribute('href', href); }
  }
  function queueOf(key) { return root.querySelector('[data-foms-home-stepq="' + key + '"]'); }
  function selectedRow(queue) {
    return toArr(queue ? queue.querySelectorAll('[data-foms-home-qrow]') : []).filter(function (r) { return r.classList.contains('is-on'); })[0] || null;
  }
  function orderHref(id) { // 그 주문을 고른 '내 공정' 주소(되돌리기 뒤 · 다음 줄이 없을 때)
    var url = new URL(attr(base, 'data-foms-step-base') || window.location.href, window.location.href);
    if (id) { url.searchParams.set('order', id); }
    return url.pathname + url.search;
  }

  // ── 줄 고르기 = 누르는 즉시 고른 표시, 판은 steppane.js(받은 판이면 바로 · 아니면 받는다) ──
  function selectRow(row) {
    var queue = row.closest('[data-foms-home-stepq]');
    if (!queue) { return; }
    toArr(queue.querySelectorAll('[data-foms-home-qrow]')).forEach(function (r) {
      var on = r === row;
      r.classList.toggle('is-on', on);
      if (on) { r.setAttribute('aria-current', 'true'); } else { r.removeAttribute('aria-current'); }
    });
    keepUrl(rowHref(row));
    panes().select(row); // 받은 판이면 바로 · 아니면 받는다(받는 동안 옛 판은 숨김)
  }
  var paneApi = null;
  function panes() {
    if (!paneApi && window.FomsProdStepPanes) { paneApi = window.FomsProdStepPanes.create(rowHref); }
    return paneApi;
  }
  function panelShown(queue) {
    var box = queue && queue.querySelector('[data-foms-step-panes]');
    return !!box && box.getClientRects().length > 0;
  }

  // ── 그림 = 전역 원본 뷰어(그림 원본 전부) ──
  function openViewer(pic) {
    var viewer = window.GlobalImageViewer;
    var files = parseList(attr(pic, 'data-foms-step-view'));
    if (viewer && typeof viewer.open === 'function' && files.length) { viewer.open(files, 0); }
  }

  // ── 쓰기 — 지금 줄 [끝] · 공정 칸과 같은 공정 API(새 쓰기 경로 0) ──
  function mutate(id, key, done) {
    var url = '/api/orders/' + encodeURIComponent(id) + '/production/steps';
    var opts = { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key: key, done: done }) };
    if (window.fomsMutationFetch) { return window.fomsMutationFetch(url, opts); }
    return (window.fomsWriteFetch || fetch)(url, opts).then(function (res) {
      return res.json().catch(function () { return null; }).then(function (data) {
        var ok = !!data && res.ok && data.success !== false;
        return { ok: ok, kind: ok ? 'ok' : 'error', status: res.status, data: data || {},
          message: (data && (data.error || data.message)) || ('HTTP ' + res.status) };
      });
    }).catch(function () { return { ok: false, kind: 'network', status: 0, data: {}, message: OFFLINE_TEXT }; });
  }
  function go(href) {
    var url = new URL(href, window.location.href).href;
    var shell = window.FOMS_ERP_SHELL;
    if (shell && typeof shell.navigateByShell === 'function' && typeof shell.isShellFragmentSwapUrl === 'function' && shell.isShellFragmentSwapUrl(url)) {
      shell.navigateByShell(url, { bypassCache: true, replaceHistory: true });
      return;
    }
    window.location.replace(url);
  }
  // [끝] 잠금 = aria-disabled + 흐림(진짜 disabled 는 누름을 삼켜 잠금 연장을 못 한다)
  function lockFinish(on) {
    toArr(root.querySelectorAll('[data-foms-step-finish]')).forEach(function (b) {
      b.classList.toggle('is-wait', on);
      if (on) { b.setAttribute('aria-disabled', 'true'); } else { b.removeAttribute('aria-disabled'); }
    });
  }
  // 새 화면 직후 잠금 — 그동안 또 누르면 GUARD_MS 를 다시 센다(연타가 다음 · 그다음 주문에 떨어지지 않게)
  function holdGuard() {
    lockFinish(true);
    window.clearTimeout(G.guardTimer);
    G.guardTimer = window.setTimeout(function () { if (G.api) { G.api.releaseGuard(); } }, Math.max(0, (G.guardUntil || 0) - Date.now()));
  }
  function releaseGuard() {
    if (Date.now() < (G.guardUntil || 0)) { holdGuard(); return; }
    if (!G.saving && !G.guardNext) { lockFinish(false); }
  }
  function finish(btn) {
    if (G.saving || G.guardNext) { return; } // 저장 중 · 저장 뒤 새 화면을 받는 중 누름은 버린다
    if (Date.now() < (G.guardUntil || 0)) { G.guardUntil = Date.now() + GUARD_MS; holdGuard(); return; }
    var pane = btn.closest('[data-foms-step-pane]');
    var job = { id: attr(btn, 'data-order-id'), key: attr(btn, 'data-step-key'), next: attr(btn, 'data-next-order'),
      name: textOf(pane, '[data-foms-step-name]'), label: attr(btn, 'data-step-label') };
    var line = pane && pane.querySelector('[data-foms-sheet-status]');
    G.saving = true;
    lockFinish(true);
    if (line) { line.textContent = '저장하는 중…'; line.classList.remove('is-bad'); }
    mutate(job.id, job.key, true).then(function (result) {
      G.saving = false;
      if (!result || !result.ok) {
        lockFinish(false);
        if (line) { line.textContent = failText(result); line.classList.add('is-bad'); }
        return;
      }
      if (line) { line.textContent = ''; }
      G.undo = { id: job.id, key: job.key, name: job.name, label: job.label, until: Date.now() + UNDO_MS, busy: false, error: '' };
      G.guardNext = true; // 새 화면이 뜨면 GUARD_MS 동안 [끝] 잠금
      showUndo();
      // 끝낸 주문은 다음 공정 줄로 간다 — '끝내면 다음은' 손님이 고른 줄이 된다(없으면 이 탭 첫 줄, 탭은 기억됨)
      go(rowHref(rowOf(job.next)) || orderHref(''));
      window.setTimeout(function () { // 화면이 끝내 안 바뀌면(받기 실패) 이 화면 [끝]을 다시 푼다
        if (document.contains(root)) { G.guardNext = false; lockFinish(false); }
      }, 10000);
    });
  }

  // ── 되돌리기(상태 줄) — 저장 뒤 UNDO_MS 동안. 셸 교체로 온 새 화면도 G.undo 로 다시 그린다 ──
  function showUndo() {
    var u = G.undo;
    if (!statusBox || !u || Date.now() >= u.until) { return; }
    statusBox.textContent = '';
    statusBox.classList.remove('is-bad');
    statusBox.classList.add('is-undo');
    statusBox.classList.toggle('is-err', !!u.error);
    var msg = document.createElement('span');
    msg.textContent = u.error || (u.name + ' ' + u.label + ' 끝');
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'foms-prod-home__undo';
    btn.setAttribute('data-foms-step-undo', '');
    btn.textContent = u.busy ? '되돌리는 중…' : '되돌리기';
    btn.disabled = !!u.busy;
    statusBox.appendChild(msg);
    statusBox.appendChild(btn);
    window.clearTimeout(G.undoTimer);
    G.undoTimer = window.setTimeout(function () {
      if (G.undo === u && !u.busy) { G.undo = null; }
      if (G.api) { G.api.clearUndo(u); }
    }, u.until - Date.now());
  }
  function clearUndo(u) {
    if (statusBox && statusBox.classList.contains('is-undo') && (!G.undo || G.undo !== u)) { setStatus(''); }
  }
  function undo() {
    var u = G.undo;
    if (!u || u.busy) { return; }
    u.busy = true;
    u.error = '';
    showUndo();
    mutate(u.id, u.key, false).then(function (result) {
      u.busy = false;
      if (!result || !result.ok) { // 화면은 그대로(끝낸 채) — 글을 보이고 조금 더 기다린다
        u.error = '되돌리지 못했어요. ' + failText(result);
        u.until = Date.now() + UNDO_MS;
        if (G.api) { G.api.showUndo(); }
        return;
      }
      G.undo = null;
      if (G.api) { G.api.setStatus('되돌렸어요. ' + u.name + ' — 다시 ' + u.label + ' 줄로 가요'); }
      go(orderHref(u.id)); // 그 주문이 다시 그 공정 줄에 선다(서버가 고른 줄 · 첫 탭)
    });
  }

  // ── 누름(이 화면 안 위임) ──
  root.addEventListener('click', function (e) {
    var t = e.target;
    if (!t || typeof t.closest !== 'function') { return; }
    if (t.closest('[data-foms-step-undo]')) { undo(); return; }
    var fin = t.closest('[data-foms-step-finish]');
    if (fin) { finish(fin); return; }
    var pic = t.closest('[data-foms-step-view]');
    if (pic) { openViewer(pic); return; }
    var retry = t.closest('[data-foms-step-retry]');
    if (retry && panes()) {
      var rq = retry.closest('[data-foms-home-stepq]');
      if (panes().isGone(rq)) { go(attr(root.querySelector('[data-foms-home-reload]'), 'href') || window.location.href); } else { panes().ensure(rq); }
      return;
    }
    var tab = t.closest('[data-foms-home-steptab]');
    if (tab) {
      var tq = queueOf(attr(tab, 'data-foms-home-steptab'));
      var on = selectedRow(tq);
      keepUrl(on ? rowHref(on) : orderHref(''));
      if (panes()) { panes().ensure(tq); }
      return;
    }
    var pane = t.closest('[data-foms-step-pane]');
    if (pane) {
      if (t.closest('[data-tablet-sheet-action]')) { keepUrl(rowHref(rowOf(attr(pane, 'data-foms-step-pane')))); }
      return; // [불량] · [보류] 는 작업 시트 JS · 도메인 시트 JS 몫
    }
    var row = t.closest('[data-foms-home-qrow]');
    if (!row || t.closest('[data-foms-home-step-done]') || e.metaKey || e.ctrlKey || e.shiftKey || e.button > 0) { return; }
    var link = t.closest('[data-foms-step-sheet]');
    if (!panelShown(row.closest('[data-foms-home-stepq]'))) {
      // 판이 안 보이는 화면(세로로 돌림): 줄 이름은 지금처럼 작업 시트로
      if (link) { e.preventDefault(); window.location.assign(attr(link, 'data-foms-step-sheet')); }
      return;
    }
    if (!panes()) { return; } // 판 받기 파일이 아직 없으면 줄 링크가 그 줄 페이지를 연다
    if (link) { e.preventDefault(); }
    selectRow(row);
  });

  // ── 저장 뒤 새 화면: [끝] 잠깐 잠금 · 되돌리기 다시 그리기(타이머는 지금 화면 함수를 부른다) ──
  G.api = { showUndo: showUndo, clearUndo: clearUndo, setStatus: setStatus, releaseGuard: releaseGuard };
  if (G.guardNext) {
    G.guardNext = false;
    G.guardUntil = Date.now() + GUARD_MS;
    holdGuard();
  }
  showUndo();
})();
