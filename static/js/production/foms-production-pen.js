/* 생산 도면 펜 기록 — 쓰는 상태(설계서 docs/specs/2026-11-28-production-pen-record_SPEC.md §6-3 · §6-5 · §8, 사장님 9 · 12 · 14 · 15번 답).
 * 보기 JS(foms-production-parts-viewer.js)가 [기록 쓰기]를 처음 누를 때 foms-production-pen-ink.js 다음에 받는다(첫 화면 값 0) — start(ctx) 로 연다.
 * 머리 줄 한 줄이 쓰는 줄로 바뀌고 아래 줄(.pp-vbot)은 숨는다(도면이 화면에서 가장 크다): [취소] · "도면 2/3 · 생산 기록" · 도구 다섯 · 되돌리기 ·
 * 다시 하기 · 색 셋 · 굵기 셋 · 배율(누르면 화면에 맞춤) · [저장]. [저장]은 바뀐 것이 있을 때만 켜지고, 쓴 것이 있는데 [취소]면 머리 줄이 묻는 줄로 바뀐다.
 * 길: 열 때 GET(기록 원본 · 버전) → [저장] = PUT multipart(payload JSON + ink 투명 PNG), 다 지우고 [저장] = DELETE(seen_version — 새 기록은 0).
 * 쓰기 = 공용 window.fomsMutationFetch — part-marks 를 부르는 foms-production-parts.js post() 와 같은 길(CSRF 는 csrf_bootstrap 의 fetch 가
 * X-CSRF-Token 을 붙이고, 같은 토큰 window.fomsCsrfToken() 을 X-CSRFToken 으로도 싣는다). 거절 글 읽기는 parts.js handle() 꼴({success:false,
 * data:{code}, error:글}) — 앞 층 거절(권한 문 data:null · 큰 몸 error 가 객체 · 꺼짐 404 HTML)에도 죽지 않는다: 글(문자열 error · message) 먼저,
 * 없으면 코드의 §6-5 글, 코드도 없으면 SAVE_FAILED 글. 저장이 안 되면 쓴 것은 화면에 그대로 둔다. 쓰는 동안(editing)은 보기 JS 가 다시 그리지
 * 않는다(30초 받아 오기에도 쓰기 화면 그대로).
 * 이 파일은 문서에 한 번만 돈다 — 셸 조각 교체로 보기 창이 바뀌어도 start(ctx) 가 받은 창에 그때 묶는다(창마다 한 번). */
(function () {
  'use strict';
  if (window.FomsPen) { return; }

  var NOTES = '/api/production/drawing-notes';
  var MAX_BYTES = 400000; // 기록 원본 전체(서버 한도 400KB)
  var TEXT = { saved: "저장했어요. 주문 첨부 '생산'에도 들어갔어요.", cleared: '생산 기록을 지웠어요. 원본 도면만 남아요.', saving: '저장 중…', save: '저장',
    erase: '선이나 글에 대면 그 하나가 통째로 지워져요', offline: '연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요.', tag: '생산 기록' };
  var REFUSE = {
    PEN_FORBIDDEN: '펜 기록은 정해진 사람만 쓸 수 있어요.',
    NOTE_CHANGED: '그사이 다른 사람이 기록을 고쳤어요. 닫고 다시 열어 주세요.', // 서버 글(쓴 사람 이름)이 먼저 — 이것은 글이 없을 때만
    DRAWING_NOT_CURRENT: '도면이 바뀌었어요. [다시 받기]를 눌러 주세요.',
    NOT_AN_IMAGE: '그림 도면에만 적을 수 있어요.',
    NOTE_TOO_LARGE: '기록이 너무 많아요. 조금 지우고 다시 저장해 주세요.',
    BAD_REQUEST: '보낸 값이 올바르지 않아요.',
    SAVE_FAILED: '저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.'
  };
  var cur = null;
  var toastTimer = 0;

  function toArr(list) { return [].slice.call(list || []); }
  function attr(el, name) { return (el && el.getAttribute(name)) || ''; }
  function q(v, sel) { return v.querySelector(sel); }
  function zoom() { return window.FomsPartsZoom || null; }
  function say(v, text, stay) { // 머리 줄 아래 알림 한 줄 — 알림은 3초 뒤 사라지고, 거절 글은 다음 누름까지 남는다
    var box = q(v, '[data-pp-ptoast]');
    if (!box) { return; }
    box.textContent = text || '';
    box.hidden = !text;
    window.clearTimeout(toastTimer);
    if (text && !stay) { toastTimer = window.setTimeout(function () { box.hidden = true; }, 3200); }
  }
  function bars(v, mode) { // 'view' | 'edit' | 'ask' — 머리 줄 한 자리를 바꿔 쓴다, 아래 줄은 보는 상태에서만
    q(v, '[data-pp-pview]').hidden = mode !== 'view';
    q(v, '[data-pp-pedit]').hidden = mode !== 'edit';
    q(v, '[data-pp-pask]').hidden = mode !== 'ask';
    var bottom = q(v, '.pp-vbot');
    if (bottom) { bottom.hidden = mode !== 'view'; }
    v.classList.toggle('is-pen-edit', mode !== 'view');
  }
  function press(box, name, value) {
    toArr(box.querySelectorAll('[' + name + ']')).forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute(name) === String(value))); });
  }
  function sync() { // 단추 상태 = 기록 상태(되돌리기 · 다시 하기 · [저장] 잠김 · 고른 도구 · 색 · 굵기 · 배율)
    if (!cur) { return; }
    var v = cur.viewer;
    var ink = cur.ink;
    var idle = cur.ready && !cur.busy;
    var tool = ink.get('tool');
    q(v, '[data-pp-pen="undo"]').disabled = !idle || !ink.canUndo();
    q(v, '[data-pp-pen="redo"]').disabled = !idle || !ink.canRedo();
    var save = q(v, '[data-pp-pen="save"]');
    save.disabled = !idle || !ink.dirty();
    save.textContent = cur.busy ? TEXT.saving : TEXT.save;
    q(v, '[data-pp-pen="cancel"]').disabled = cur.busy;
    press(v, 'data-pp-tool', tool);
    press(v, 'data-pp-color', ink.get('color'));
    press(v, 'data-pp-width', ink.get('width'));
    q(v, '[data-pp-colors]').classList.toggle('is-off', tool === 'erase' || tool === 'marker'); // 형광펜은 색 · 굵기가 고정
    q(v, '[data-pp-widths]').classList.toggle('is-off', tool === 'erase' || tool === 'marker');
    var z = zoom();
    q(v, '[data-pp-pen="fit"]').textContent = Math.round(((z && z.state ? z.state().scale : 1) || 1) * 100) + '%';
  }

  function load(card) { // 열 때 한 번 — {note} 또는 못 받으면 null
    var url = NOTES + '?order_id=' + encodeURIComponent(attr(card, 'data-order-id')) + '&drawing_key=' + encodeURIComponent(attr(card, 'data-key'));
    try {
      return fetch(url, { method: 'GET', credentials: 'same-origin', cache: 'no-store', headers: { Accept: 'application/json' } })
        .then(function (res) { return res.ok ? res.json() : null; })
        .then(function (body) { return body && body.success === true && body.data ? { note: body.data.note || null } : null; })
        .catch(function () { return null; });
    } catch (e) {
      return Promise.resolve(null);
    }
  }
  function send(opts) { // foms-production-parts.js post() 와 같은 길 — 끊기면 network 꼴, JSON 이 아닌 몸(꺼짐 404 HTML)은 빈 몸
    var offline = { ok: false, kind: 'network', status: 0, data: {}, message: TEXT.offline };
    var call = window.fomsMutationFetch || function (u, o) {
      return fetch(u, o).then(function (res) {
        return res.json().catch(function () { return null; }).then(function (d) { return { ok: res.ok, status: res.status, data: d || {}, message: '' }; });
      });
    };
    opts.headers = opts.headers || {};
    if (typeof window.fomsCsrfToken === 'function') { opts.headers['X-CSRFToken'] = window.fomsCsrfToken(); }
    try { return call(NOTES, opts).catch(function () { return offline; }); } catch (e) { return Promise.resolve(offline); }
  }

  // 저장 뒤 카드(같은 장이 여러 판에 있으면 모두) — data-note-* · 딱지 · 읽는 이름. 보기 JS 가 이 속성으로 장 묶음 점 · [생산 기록 | 원본]을 그린다
  function setNote(card, note) {
    var cards = window.FomsPartsCards && window.FomsPartsCards.find ? window.FomsPartsCards.find(attr(card, 'data-order-id'), attr(card, 'data-key')) : [];
    if (cards.indexOf(card) < 0) { cards.push(card); }
    var vals = note ? { 'data-note-v': note.version, 'data-note-by': note.by, 'data-note-at': note.at, 'data-note-url': note.view_url } : {};
    cards.forEach(function (c) {
      ['data-note-v', 'data-note-by', 'data-note-at', 'data-note-url'].forEach(function (k) {
        if (note) { c.setAttribute(k, vals[k] == null ? '' : String(vals[k])); } else { c.removeAttribute(k); }
      });
      var box = c.querySelector('[data-pp-open]');
      var tag = box && box.querySelector('[data-pp-ptag]');
      if (!box) { return; }
      var label = attr(box, 'aria-label').replace(' · ' + TEXT.tag, '');
      box.setAttribute('aria-label', note ? label + ' · ' + TEXT.tag : label);
      if (note && !tag) {
        tag = document.createElement('span');
        tag.className = 'pp-ptag';
        tag.setAttribute('data-pp-ptag', '');
        tag.textContent = TEXT.tag;
        box.appendChild(tag);
      }
      if (!note && tag) { box.removeChild(tag); }
    });
  }

  function leave(show) {
    if (!cur) { return; }
    var c = cur;
    cur = null;
    c.ink.destroy();
    bars(c.viewer, 'view');
    if (zoom()) { zoom().reset(); }
    if (c.done) { c.done(show); } // 보기 JS 가 다시 그린다(장 묶음 · 점 · [생산 기록 | 원본] · 그림 주소)
    var back = q(c.viewer, '[data-pp-pen-open]');
    if (back && !back.hidden) { back.focus(); } // 초점은 숨은 쓰는 줄에 남지 않게
  }
  function cancel() {
    if (!cur || cur.busy) { return; }
    cur.ink.commitText();
    if (!cur.ink.dirty()) { leave(null); return; }
    bars(cur.viewer, 'ask'); // 창을 띄우지 않고 머리 줄이 묻는 줄로(§6-3)
    var keep = q(cur.viewer, '[data-pp-pen="keep"]');
    if (keep) { keep.focus(); }
  }
  function done(mine, cleared, result) {
    if (cur !== mine) { return; }
    var body = result.data || {};
    var data = body.data || {}; // 앞 층 거절은 data: null
    mine.busy = false;
    if (result.ok && body.success === true && (cleared || data.note)) {
      setNote(mine.card, cleared ? null : data.note);
      leave(cleared ? 'orig' : 'note');
      say(mine.viewer, cleared ? TEXT.cleared : TEXT.saved);
      return;
    }
    mine.ink.enable(true); // 쓴 것은 그대로 — 다시 [저장]을 누를 수 있다
    sync();
    if (result.status === 0 || result.kind === 'network' || result.kind === 'timeout') { say(mine.viewer, TEXT.offline, true); return; }
    var text = [body.error, body.message].filter(function (t) { return typeof t === 'string' && t; })[0]; // error 가 객체면 건너뛴다
    say(mine.viewer, text || REFUSE[data.code || body.code] || REFUSE.SAVE_FAILED, true);
  }
  function save() {
    if (!cur || cur.busy || !cur.ready) { return; }
    cur.ink.commitText();
    if (!cur.ink.dirty()) { sync(); return; }
    var mine = cur;
    var objs = mine.ink.objects();
    var base = mine.ink.base();
    var ids = { order_id: Number(attr(mine.card, 'data-order-id')), drawing_key: attr(mine.card, 'data-key'), seen_version: mine.version };
    if (JSON.stringify(objs).length > MAX_BYTES) { say(mine.viewer, REFUSE.NOTE_TOO_LARGE, true); return; }
    mine.busy = true;
    mine.ink.enable(false);
    say(mine.viewer, '');
    sync();
    var go = !objs.length
      ? send({ method: 'DELETE', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(ids) }) // 다 지우고 [저장]
      : mine.ink.toPng().then(function (blob) {
        if (!blob) { return { ok: false, kind: 'error', status: 500, data: {}, message: '' }; }
        var form = new FormData();
        form.append('payload', JSON.stringify({ order_id: ids.order_id, drawing_key: ids.drawing_key, objects: objs, base_w: base.w, base_h: base.h,
          seen_version: ids.seen_version }));
        form.append('ink', blob, 'ink.png');
        return send({ method: 'PUT', credentials: 'same-origin', body: form, timeoutMs: 30000 }); // 합치기는 서버 몫이라 넉넉히
      });
    go.then(function (result) { done(mine, !objs.length, result || {}); }, function () { done(mine, !objs.length, { status: 500, data: {} }); });
  }

  // 보기 창마다 한 번 — 쓰는 줄 · 묻는 줄 누름, 글 칸 Enter · Esc, 배율 글(손가락 · 휠 확대 뒤)
  function bind(v) {
    if (v.__ppPenBound) { return; }
    v.__ppPenBound = true;
    v.addEventListener('click', function (e) {
      var t = e.target;
      if (!cur || cur.viewer !== v || !t || typeof t.closest !== 'function') { return; }
      var btn = t.closest('[data-pp-pen]');
      var act = btn ? btn.getAttribute('data-pp-pen') : '';
      var pick = t.closest('[data-pp-tool], [data-pp-color], [data-pp-width]');
      if (pick && !cur.busy) {
        if (pick.hasAttribute('data-pp-tool')) { cur.ink.set('tool', pick.getAttribute('data-pp-tool')); }
        if (pick.hasAttribute('data-pp-color')) { cur.ink.set('color', pick.getAttribute('data-pp-color')); }
        if (pick.hasAttribute('data-pp-width')) { cur.ink.set('width', Number(pick.getAttribute('data-pp-width'))); }
        if (pick.getAttribute('data-pp-tool') === 'erase') { say(v, TEXT.erase); }
        sync();
        return;
      }
      if (!btn || btn.disabled) { return; }
      if (act === 'undo') { cur.ink.undo(); } else if (act === 'redo') { cur.ink.redo(); } else if (act === 'save') { save(); } else if (act === 'cancel') { cancel(); }
      if (act === 'keep') { bars(v, 'edit'); }
      if (act === 'drop') { leave(null); return; }
      if (act === 'fit' && zoom()) { zoom().reset(); }
      sync();
    });
    var box = q(v, '[data-pp-ptext]');
    if (box) {
      box.addEventListener('keydown', function (e) {
        if (!cur) { return; }
        if (e.key === 'Enter') { e.preventDefault(); cur.ink.commitText(); }
        if (e.key === 'Escape') { e.preventDefault(); if (e.stopPropagation) { e.stopPropagation(); } cur.ink.dropText(); }
      });
      box.addEventListener('blur', function () { if (cur) { cur.ink.commitText(); } });
    }
    var stage = q(v, '[data-pp-v-zoom]');
    ['wheel', 'touchend'].forEach(function (name) { stage.addEventListener(name, function () { if (cur) { sync(); } }); });
  }

  // 쓰는 상태 열기 — ctx = {viewer, img, card, done(show)}. 원본 위에 쓴다(합친 그림이 아니라). 기록을 받기 전에는 쓰지 못한다
  function start(ctx) {
    if (cur || !window.FomsPenInk || !ctx || !ctx.card || !ctx.viewer || !q(ctx.viewer, '[data-pp-pedit]')) { return false; }
    var v = ctx.viewer;
    var card = ctx.card;
    var stage = q(v, '[data-pp-v-zoom]');
    bind(v);
    say(v, '');
    bars(v, 'edit');
    q(v, '[data-pp-pen-title]').textContent = '도면 ' + attr(card, 'data-no') + '/' + attr(card, 'data-of') + ' · 생산 기록';
    if (ctx.img.getAttribute('src') !== attr(card, 'data-view-url')) { ctx.img.src = attr(card, 'data-view-url'); }
    if (zoom()) { zoom().reset(); }
    var mine = { viewer: v, card: card, done: ctx.done, busy: false, ready: false, version: 0 };
    mine.ink = window.FomsPenInk.create({ stage: stage, img: ctx.img, text: q(v, '[data-pp-ptext]'), onChange: sync,
      onLimit: function () { say(v, REFUSE.NOTE_TOO_LARGE, true); } });
    cur = mine;
    sync();
    q(v, '[data-pp-pen="cancel"]').focus();
    load(card).then(function (got) {
      if (cur !== mine) { return null; }
      if (!got) { leave(null); say(v, TEXT.offline, true); return null; }
      mine.version = got.note ? Number(got.note.version) || 0 : 0;
      return mine.ink.mount(got.note ? got.note.objects : [], got.note).then(function (ok) {
        if (cur !== mine || !ok) { return; }
        mine.ready = true;
        mine.ink.enable(true);
        sync();
      });
    });
    return true;
  }

  if (typeof window.addEventListener === 'function') { // 창 크기 · 돌림 — 쓰는 층을 그림 자리에 다시(확대 파일의 resize 뒤)
    window.addEventListener('resize', function () { if (cur) { cur.ink.fit(); } });
  }
  window.FomsPen = {
    start: start,
    cancel: cancel,
    editing: function (v) { return !!cur && (!v || cur.viewer === v); },
    inking: function () { return !!cur && cur.ink.inking(); }
  };
})();
