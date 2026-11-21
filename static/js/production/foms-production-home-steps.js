/* 생산 첫 화면 '내 공정' 탭 오른쪽 판(태블릿 가로) — 설계서 docs/specs/2026-11-21-production-my-steps-panel_SPEC.md §3-4 ~ §3-6
 * · 사용자 결정 2026-11-21 "추천안(반반)대로 만들기".
 * 줄을 누르면 판을 바꾼다 — 서버가 공정 줄 전부의 판을 그려 두었고 여기서는 보이기/숨기기만 한다(새 요청 없음, 공장 와이파이 D5).
 * 주소 · [다시 받기]는 고른 줄 링크의 href(?tab=steps&order=<id>, 서버 home_href 가 지은 것)로 맞춘다(replaceState). 공정 탭을 바꾸면
 * 그 탭의 고른 줄로, [보류]를 누르면 그 판의 줄로 맞춘다(보류 뒤 새로고침이 같은 줄로 돌아온다).
 * 큰 [<공정> 끝] = 확인 창(#foms-step-confirm-modal, 파트 도면 카드 창 꼴) — 창의 [<공정> 끝]을 눌러야 POST /api/orders/<id>/production/steps
 * {key, done:true} 한 번. 성공하면 '끝내면 다음은' 줄 주소로 다시 받는다(셸이 있으면 셸 조각 교체). [취소] · 바깥 · Esc 는 아무것도 안 바꾼다.
 * 그림을 누르면 전역 원본 뷰어(GlobalImageViewer)에 그림 원본 전부(작업 시트와 같은 목록). [불량] = foms-production-sheet-page.js,
 * [보류] = tablet-domain-sheets.js 몫(지금 작업 시트와 같은 길). 판이 안 보이면(태블릿을 세로로 돌림) 줄 이름은 지금처럼 작업 시트로 간다.
 * 폰 · PC 줄 [끝](확인 창 없이 바로 저장)은 foms-production-home.js 몫 — 이 파일은 판이 있는 화면에만 실린다.
 * 첫 탭: 주소 order= 가 선 공정 탭(서버 data-foms-home-step-pin)을 마지막 탭 기억보다 앞에 — foms-production-home.js 가 읽기 전에 기억을 맞춘다.
 * 셸 조각 교체로 다시 실행된다 — 화면에는 한 번(data-foms-home-steps-bound), 문서 리스너(Esc)는 window.__FOMS_PROD_STEPS_BOUND 로 한 번. */
(function () {
  'use strict';

  var root = document.querySelector('[data-foms-prod-home]');
  var modal = root && root.querySelector('[data-foms-step-modal]');
  if (!root || !modal || root.getAttribute('data-foms-home-steps-bound') === '1') { return; }
  root.setAttribute('data-foms-home-steps-bound', '1');
  var G = window.__FOMS_PROD_STEPS_BOUND = window.__FOMS_PROD_STEPS_BOUND || {};

  var OFFLINE_TEXT = '연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요.';
  var STEP_TAB_KEY = 'foms-prod-step-tab'; // foms-production-home.js 와 같은 열쇠
  var ME = modal.getAttribute('data-foms-step-me') || '';
  var pending = null;
  function toArr(list) { return [].slice.call(list || []); }
  function attr(node, name) { return (node && node.getAttribute(name)) || ''; }
  function q(sel) { return modal.querySelector(sel); }
  function textOf(scope, sel) { var n = scope && scope.querySelector(sel); return n ? String(n.textContent || '').trim() : ''; }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text) { node.textContent = text; }
    return node;
  }
  function parseList(text) {
    var utils = window.ERPUtils;
    if (utils && typeof utils.safeJsonParse === 'function') { return utils.safeJsonParse(text, []) || []; }
    try { return JSON.parse(text || '[]') || []; } catch (e) { return []; }
  }
  function setStatus(text, bad) {
    var box = root.querySelector('[data-foms-home-status]');
    if (box) { box.textContent = text || ''; box.classList.toggle('is-bad', !!bad); }
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

  // ── 줄 고르기 = 판 보이기/숨기기 ──
  function selectRow(row) {
    var queue = row.closest('[data-foms-home-stepq]');
    if (!queue) { return; }
    var id = attr(row, 'data-foms-home-qrow');
    toArr(queue.querySelectorAll('[data-foms-home-qrow]')).forEach(function (r) {
      var on = r === row;
      r.classList.toggle('is-on', on);
      if (on) { r.setAttribute('aria-current', 'true'); } else { r.removeAttribute('aria-current'); }
    });
    toArr(queue.querySelectorAll('[data-foms-step-pane]')).forEach(function (p) { p.hidden = attr(p, 'data-foms-step-pane') !== id; });
    keepUrl(rowHref(row));
  }
  function panelShown(queue) {
    var panes = queue && queue.querySelector('[data-foms-step-panes]');
    return !!panes && panes.getClientRects().length > 0;
  }

  // ── 그림 = 전역 원본 뷰어(그림 원본 전부) ──
  function openViewer(pic) {
    var viewer = window.GlobalImageViewer;
    var files = parseList(attr(pic, 'data-foms-step-view'));
    if (viewer && typeof viewer.open === 'function' && files.length) { viewer.open(files, 0); }
  }

  // ── 확인 창(파트 도면 카드 창 꼴) ──
  function listItem(pane, label) {
    var li = el('li', 'foms-prod-change-modal__item pp-mitem');
    var pic = el('div', 'pp-mimg');
    var img = pane.querySelector('[data-foms-step-img]');
    if (img) {
      var copy = img.cloneNode(false); // 판에 이미 받은 그림 — 창이 뜨는 순간 비지 않는다
      copy.removeAttribute('data-foms-step-img');
      copy.setAttribute('loading', 'eager');
      pic.appendChild(copy);
    } else {
      pic.appendChild(el('b', '', textOf(pane, '[data-foms-step-piclabel]') || '도면 없음'));
    }
    var body = el('div', 'foms-prod-change-modal__item-body');
    var head = el('div', 'foms-prod-change-modal__item-head');
    var who = el('span', 'foms-prod-change-modal__item-customer', textOf(pane, '[data-foms-step-name]') + ' ');
    who.appendChild(el('small', '', '#' + attr(pane, 'data-foms-step-pane')));
    head.appendChild(who);
    head.appendChild(el('span', 'foms-prod-change-modal__item-id', textOf(pane, '[data-foms-step-piclabel]')));
    body.appendChild(head);
    body.appendChild(el('span', 'foms-prod-change-modal__alert-detail', textOf(pane, '[data-foms-step-sub]')));
    var line = el('div', 'foms-prod-change-modal__alert pp-al--done');
    line.appendChild(el('span', 'foms-prod-change-modal__alert-label', label + ' 중 → ' + label + ' 끝' + (ME ? ' · ' + ME : '')));
    body.appendChild(line);
    li.appendChild(pic);
    li.appendChild(body);
    return li;
  }
  function openModal(btn) {
    var pane = btn.closest('[data-foms-step-pane]');
    if (!pane) { return; }
    var label = attr(btn, 'data-step-label');
    pending = { opener: btn, id: attr(btn, 'data-order-id'), key: attr(btn, 'data-step-key'), next: attr(btn, 'data-next-order'),
      run: label + ' 끝', busy: false };
    q('[data-foms-step-modal-title]').textContent = label + ' 끝으로 바꿀까요?';
    var list = q('[data-foms-step-modal-list]');
    list.textContent = '';
    list.appendChild(listItem(pane, label));
    showError('');
    setBusy(false);
    modal.hidden = false;
    modal.classList.add('is-open');
    q('[data-foms-step-modal-close]').focus();
  }
  function closeModal() {
    if (!pending || pending.busy) { return; }
    var opener = pending.opener;
    pending = null;
    modal.classList.remove('is-open');
    modal.hidden = true;
    if (opener && typeof opener.focus === 'function' && document.contains(opener)) { opener.focus(); }
  }
  function setBusy(busy) {
    if (pending) { pending.busy = busy; }
    var run = q('[data-foms-step-modal-run]');
    run.disabled = busy;
    q('[data-foms-step-modal-close]').disabled = busy;
    run.textContent = busy ? '저장하는 중…' : (pending ? pending.run : '확인');
  }
  function showError(text) {
    var err = q('[data-foms-step-modal-err]');
    err.textContent = text || '';
    err.hidden = !text;
  }

  // ── 쓰기 — 지금 줄 [끝]과 같은 공정 API(새 쓰기 경로 0) ──
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
  function go(href) {
    var url = new URL(href, window.location.href).href;
    var shell = window.FOMS_ERP_SHELL;
    if (shell && typeof shell.navigateByShell === 'function' && typeof shell.isShellFragmentSwapUrl === 'function' && shell.isShellFragmentSwapUrl(url)) {
      shell.navigateByShell(url, { bypassCache: true, replaceHistory: true });
      return;
    }
    window.location.replace(url);
  }
  function send() {
    if (!pending || pending.busy) { return; }
    var job = pending;
    setBusy(true);
    mutate('/api/orders/' + encodeURIComponent(job.id) + '/production/steps', { key: job.key, done: true }).then(function (result) {
      if (pending !== job) { return; }
      if (!result || !result.ok) {
        setBusy(false);
        showError(!result || result.kind === 'network' || result.status === 0 ? OFFLINE_TEXT : ('오류: ' + (result.message || '처리하지 못했어요')));
        return;
      }
      setStatus('끝냈어요. 다음 공정으로 옮겨요');
      // 끝낸 주문은 다음 공정 줄로 간다 — '끝내면 다음은' 손님이 고른 줄이 된다(없으면 이 탭 첫 줄, 탭은 기억됨)
      go(rowHref(rowOf(job.next)) || attr(modal, 'data-foms-step-base') || window.location.href);
    });
  }

  // ── 누름(이 화면 안 위임) ──
  root.addEventListener('click', function (e) {
    var t = e.target;
    if (!t || typeof t.closest !== 'function') { return; }
    if (t.closest('[data-foms-step-modal]')) {
      if (t === modal || t.closest('[data-foms-step-modal-close]')) { closeModal(); return; }
      if (t.closest('[data-foms-step-modal-run]')) { send(); }
      return;
    }
    var finish = t.closest('[data-foms-step-finish]');
    if (finish) { openModal(finish); return; }
    var pic = t.closest('[data-foms-step-view]');
    if (pic) { openViewer(pic); return; }
    var tab = t.closest('[data-foms-home-steptab]');
    if (tab) {
      var on = selectedRow(queueOf(attr(tab, 'data-foms-home-steptab')));
      keepUrl(on ? rowHref(on) : attr(modal, 'data-foms-step-base'));
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
    if (link) { e.preventDefault(); }
    selectRow(row);
  });

  // ── Esc = 창 닫기. 문서 리스너는 한 번(셸 교체로 다시 실행돼도 쌓이지 않게) — 지금 화면 함수를 부른다 ──
  G.api = { escape: function () { if (pending && !modal.hidden) { closeModal(); } } };
  if (!G.once) {
    G.once = true;
    document.addEventListener('keydown', function (e) {
      if ((e.key === 'Escape' || e.key === 'Esc') && G.api) { G.api.escape(); }
    });
  }
})();
