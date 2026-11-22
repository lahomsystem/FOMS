/* 생산 첫 화면 '내 공정' 판 하나 받기 — foms-production-home-steps.js 가 줄을 누를 때 쓴다(2026-11-22 터치 점검).
 * 서버는 공정 줄마다 고른 줄 판 하나만 그린다: 숨은 판을 줄마다 다 그리면(주문 150건 · 판 96개) 조각이 396KB · DOM 13,100 이라
 * 탭 바꾸기 · [다시 받기] · [끝] 뒤 화면이 1~2초 얼고 그동안 누름이 버려졌다. 다른 줄은 누를 때 그 판 하나를 받아 끼운다 —
 * 같은 주소 + view=panel&step=<공정>&order=<주문>, 응답 머리글 X-FOMS-HOME-PANEL = 받은 판의 주문 번호(날짜 탭 '날 고르기'와 같은 꼴).
 * - 받은 판은 화면에 남겨 다시 누르면 바로 보인다(조각을 다시 받으면 같이 사라진다).
 * - 받는 동안 옛 판은 숨기고 판 자리에 '받는 중'(다른 주문의 [끝]이 보이지 않게), 못 받으면 글 + [다시 해 보기].
 *   그 사이 다른 공정으로 옮겨 간 줄(404)은 '다시 받기' 글 — 누르면 부르는 쪽이 화면을 다시 받는다.
 * - 공정 줄마다 마지막 누름만 반영한다(AbortController + 차례 번호) — 늦게 온 앞 응답은 버린다.
 * - 끼운 판의 [불량] 칩은 작업 시트 JS(FomsProductionSheetPage.init)가 묶고, [보류] · 그림 · [끝]은 화면 위임이라 묶을 것이 없다.
 * 셸 조각 교체로 다시 실행돼도 window.FomsProdStepPanes 를 한 번만 만든다. 리스너는 달지 않는다. */
(function () {
  'use strict';

  if (window.FomsProdStepPanes) { return; }
  var OFFLINE_TEXT = '연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요.';
  var GONE_TEXT = '이 주문은 그 사이 다른 공정으로 옮겨졌어요. [다시 받기]를 눌러 주세요.';
  var LOAD_TEXT = '판을 받는 중…';
  var PANEL_VIEW = 'panel';
  var PANEL_HEADER = 'X-FOMS-HOME-PANEL';
  function toArr(list) { return [].slice.call(list || []); }
  function attr(node, name) { return (node && node.getAttribute(name)) || ''; }
  function keyOf(queue) { return attr(queue, 'data-foms-home-stepq'); }
  function idOf(row) { return attr(row, 'data-foms-home-qrow'); }

  function paneIn(queue, id) {
    return toArr(queue.querySelectorAll('[data-foms-step-pane]')).filter(function (p) { return attr(p, 'data-foms-step-pane') === id; })[0] || null;
  }
  function showPane(queue, id) {
    toArr(queue.querySelectorAll('[data-foms-step-pane]')).forEach(function (p) { p.hidden = attr(p, 'data-foms-step-pane') !== id; });
  }
  // 판 자리 한 칸: state '' (숨김) · 'load' · 'bad'(연결) · 'gone'(줄이 옮겨 감)
  function setWait(queue, state) {
    var box = queue.querySelector('[data-foms-step-wait]');
    if (!box) { return; }
    var bad = state === 'bad' || state === 'gone';
    box.hidden = !state;
    box.classList.toggle('is-bad', bad);
    box.setAttribute('data-state', state);
    var msg = box.querySelector('[data-foms-step-wait-text]');
    if (msg) { msg.textContent = state === 'gone' ? GONE_TEXT : (bad ? OFFLINE_TEXT : LOAD_TEXT); }
    var retry = box.querySelector('[data-foms-step-retry]');
    if (retry) {
      retry.hidden = !bad;
      retry.textContent = state === 'gone' ? '다시 받기' : '다시 해 보기';
    }
  }

  /** hrefOf(row) = 그 줄 링크 주소(?tab=steps&order=<id>). 돌려주는 것: select(row) · ensure(queue) · isGone(queue). */
  function create(hrefOf) {
    var reqs = {}; // 공정 열쇠 → {seq, ctl, id}

    function drop(key) {
      var r = reqs[key] || (reqs[key] = { seq: 0, ctl: null, id: '' });
      r.seq += 1;
      r.id = '';
      if (r.ctl) {
        try { r.ctl.abort(); } catch (e) { /* 이미 끝난 요청 */ }
      }
      r.ctl = null;
      return r;
    }
    function insert(queue, id, html) {
      var tpl = document.createElement('template');
      tpl.innerHTML = html;
      var pane = tpl.content.querySelector('[data-foms-step-pane]');
      if (!pane || attr(pane, 'data-foms-step-pane') !== id) { throw new Error('panel body'); }
      var box = queue.querySelector('[data-foms-step-panes]');
      if (box && !paneIn(queue, id)) { box.insertBefore(pane, queue.querySelector('[data-foms-step-wait]')); }
      var sheet = window.FomsProductionSheetPage; // [불량] 칩 · 최근 불량 = 작업 시트 JS 가 새 판 루트를 묶는다
      if (sheet && typeof sheet.init === 'function') { sheet.init(); }
    }
    function load(queue, row) {
      var key = keyOf(queue);
      var id = idOf(row);
      var r = drop(key);
      var seq = r.seq;
      r.id = id;
      r.ctl = typeof AbortController !== 'undefined' ? new AbortController() : null;
      var url = new URL(hrefOf(row) || window.location.href, window.location.href);
      url.searchParams.set('view', PANEL_VIEW);
      url.searchParams.set('step', key);
      url.searchParams.set('order', id);
      setWait(queue, 'load');
      var req;
      try {
        req = fetch(url.toString(), { credentials: 'same-origin', cache: 'no-store', signal: r.ctl ? r.ctl.signal : undefined,
          headers: { Accept: 'text/html', 'X-Requested-With': 'XMLHttpRequest' } });
      } catch (e) {
        req = Promise.reject(e);
      }
      req.then(function (res) {
        if (res.status === 404) { throw Object.assign(new Error('gone'), { gone: true }); }
        if (!res.ok || res.headers.get(PANEL_HEADER) !== id) { throw new Error('panel ' + res.status); }
        return res.text();
      }).then(function (html) {
        if (seq !== r.seq) { return; }
        insert(queue, id, html);
        r.ctl = null;
        r.id = '';
        setWait(queue, '');
        showPane(queue, id);
      }).catch(function (err) {
        if (seq !== r.seq || (err && err.name === 'AbortError')) { return; }
        r.ctl = null;
        r.id = '';
        setWait(queue, err && err.gone ? 'gone' : 'bad');
      });
    }
    // 줄을 골랐다(고른 표시는 부르는 쪽이 이미 바꿈): 받은 판이면 바로, 받는 중인 같은 줄이면 그대로, 아니면 받는다
    function select(row) {
      var queue = row.closest('[data-foms-home-stepq]');
      if (!queue) { return; }
      var id = idOf(row);
      var key = keyOf(queue);
      showPane(queue, id); // 옛 판은 바로 숨긴다
      if (paneIn(queue, id)) {
        drop(key);
        setWait(queue, '');
        return;
      }
      if (reqs[key] && reqs[key].id === id) { return; }
      load(queue, row);
    }
    // 공정 탭을 바꿈 · [다시 해 보기]: 그 줄의 고른 줄 판이 아직 없고 받는 중도 아니면 받는다
    function ensure(queue) {
      if (!queue || !queue.querySelector('[data-foms-step-panes]')) { return; }
      var on = queue.querySelector('[data-foms-home-qrow].is-on');
      var key = keyOf(queue);
      if (on && !paneIn(queue, idOf(on)) && !(reqs[key] && reqs[key].id)) { load(queue, on); }
    }
    function isGone(queue) {
      var box = queue && queue.querySelector('[data-foms-step-wait]');
      return attr(box, 'data-state') === 'gone';
    }
    return { select: select, ensure: ensure, isGone: isGone };
  }

  window.FomsProdStepPanes = { create: create };
})();
