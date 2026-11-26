/* 생산 도면 판 [도면 수정 요청] 창 — 설계서 2026-11-25 §2-4 · §10 · N3(D4), 시안 04 ① ②.
 * 카드의 [도면 수정 요청](data-pp-req)을 누르면 창(#foms-part-request-modal, home_parts_overlays.html): "어느 도면인가요?"(그 사람이 요청할 수
 * 있는 그 주문 장 — 카드의 data-pp-req-opts, 누른 장이 미리 골라짐, 여러 장) · "사유"(꼭 적기) · "사진 (있으면 올려 주세요 · 3장까지)".
 * 사진은 고르는 즉시 한 장씩 POST …/production/drawing-request/photo(다시 고르면 바꿔 넣음 — 빼기 단추 없음). [요청 보내기] = POST
 * …/production/drawing-request {targets, note, photos} + 머리글 Idempotency-Key(같은 몸으로 다시 누르면 같은 열쇠 — 두 번 눌러도 한 건).
 * 되면 창을 닫고 "도면팀에 수정 요청을 보냈어요." · 보낸 도면 카드는 바로 '도면 고치는 중'(서버가 준 막힌 칸 — 도면 판과 같은 함수) ·
 * 그 카드의 [도면 수정 요청]은 숨긴다. 안 되면 서버 글을 창 안에(창은 그대로). fetch 는 try/catch + data.success 로 판정.
 * 셸 조각 교체로 다시 실행된다: 화면(root)마다 한 번(window.__FOMS_PROD_PARTS_BOUND.request). */
(function () {
  'use strict';

  var root = document.querySelector('[data-foms-prod-home]');
  var modal = root && root.querySelector('[data-pp-rq]');
  if (!root || !modal) { return; }
  var bound = window.__FOMS_PROD_PARTS_BOUND = window.__FOMS_PROD_PARTS_BOUND || {};
  if (bound.request === root) { return; }
  bound.request = root;

  var MAX_PHOTOS = 3;
  var TEXT = {
    sent: '도면팀에 수정 요청을 보냈어요.',
    note: '사유를 적어 주세요.',
    pick: '수정할 도면을 골라 주세요.',
    tooMany: '사진은 3장까지 올릴 수 있어요.',
    photoBad: '사진을 다시 올려 주세요.',
    tooBig: '사진이 너무 커요. 크기를 줄여 올려 주세요.', // 서버 글(heic_convert ERR_PIXELS 는 다른 화면도 써서 그대로) — 413 받으면
    offline: '연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요.'
  };
  var state = null;

  function q(sel) { return modal.querySelector(sel); }
  function toArr(list) { return [].slice.call(list || []); }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text) { node.textContent = text; }
    return node;
  }
  function safeJsonParse(value, fallback) {
    try { var text = String(value || '').trim(); return text ? JSON.parse(text) : fallback; } catch (e) { return fallback; }
  }
  function newKey() {
    var c = window.crypto;
    if (c && typeof c.randomUUID === 'function') { return c.randomUUID(); }
    return 'rq-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 12);
  }
  function showError(text) {
    var box = q('[data-pp-rq-err]');
    box.textContent = text || '';
    box.hidden = !text;
  }
  function setStatus(text) {
    var box = root.querySelector('[data-foms-home-status]');
    if (box) { box.textContent = text || ''; box.classList.remove('is-bad'); }
  }

  // ── 고르기 · 사진 칸 그리기 ──
  function renderPicks() {
    var box = q('[data-pp-rq-picks]');
    box.textContent = '';
    state.opts.forEach(function (opt) {
      var on = !!state.picked[opt.no];
      var btn = el('button', 'pp-rq__pick' + (on ? ' is-on' : ''), '도면 ' + opt.no);
      btn.type = 'button';
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
      btn.setAttribute('data-pp-rq-no', String(opt.no));
      box.appendChild(btn);
    });
  }
  function renderThumbs() {
    var box = q('[data-pp-rq-thumbs]');
    box.textContent = '';
    state.photos.forEach(function (p) {
      var cell = el('span', 'pp-rq__thumb' + (p.key ? '' : ' is-wait'));
      if (p.url) { var img = el('img'); img.src = p.url; img.alt = p.filename || ''; cell.appendChild(img); }
      cell.appendChild(el('small', '', p.filename || ''));
      box.appendChild(cell);
    });
  }
  function setBusy(busy) {
    state.busy = busy;
    q('[data-pp-rq-send]').disabled = busy || state.uploading > 0;
  }

  // ── 열기 · 닫기(확인 창과 같은 꼴 — 열린 동안 판은 inert) ──
  function setInert(on) {
    if (on) {
      state.inert = toArr(modal.parentNode.children).filter(function (n) { return n !== modal && !n.inert; });
      state.inert.forEach(function (n) { n.inert = true; });
    } else if (state && state.inert) {
      state.inert.forEach(function (n) { n.inert = false; });
    }
  }
  function open(btn) {
    var card = btn.closest('[data-pp-card]');
    if (!card) { return; }
    var opts = safeJsonParse(btn.getAttribute('data-pp-req-opts'), []) || [];
    var no = Number(card.getAttribute('data-no'));
    state = { orderId: card.getAttribute('data-order-id'), opts: opts, picked: {}, photos: [], uploading: 0, busy: false,
      key: '', sentBody: '', opener: btn };
    if (opts.some(function (o) { return o.no === no; })) { state.picked[no] = true; }
    var who = card.querySelector('.fph-dr__nm b');
    q('[data-pp-rq-who]').textContent = (who ? who.textContent + ' ' : '') + '#' + state.orderId;
    q('[data-pp-rq-note]').value = '';
    showError('');
    renderPicks();
    renderThumbs();
    setBusy(false);
    setInert(true);
    modal.hidden = false;
    modal.classList.add('is-open');
    var first = q('[data-pp-rq-picks] button');
    if (first) { first.focus(); }
  }
  function close() {
    if (!state || state.busy) { return; }
    var opener = state.opener;
    setInert(false);
    state = null;
    modal.classList.remove('is-open');
    modal.hidden = true;
    if (opener && document.contains(opener) && !opener.hidden) { opener.focus(); }
  }

  // ── 사진(고르는 즉시 올림, 다시 고르면 바꿔 넣음) ──
  function upload(file) {
    var form = new FormData();
    form.append('file', file, file.name);
    var url = '/api/orders/' + encodeURIComponent(state.orderId) + '/production/drawing-request/photo';
    return fetch(url, { method: 'POST', credentials: 'same-origin', body: form }).then(function (res) {
      if (res.status === 413) { return { big: true }; } // 몸 상한(success 칸 없는 답일 수 있다)
      return res.json().catch(function () { return null; }).then(function (data) {
        return data && data.success === true && data.data && data.data.file ? { file: data.data.file } : {};
      });
    }).catch(function (e) {
      console.warn('[drawing-request] photo', e);
      return {};
    });
  }
  function onFiles(list) {
    var files = toArr(list);
    if (!files.length || !state) { return; }
    if (files.length > MAX_PHOTOS) { showError(TEXT.tooMany); return; }
    showError('');
    var mine = state;
    mine.photos = files.map(function (f) {
      var preview = window.URL && typeof window.URL.createObjectURL === 'function' ? window.URL.createObjectURL(f) : '';
      return { key: '', filename: f.name, url: preview };
    });
    mine.uploading = files.length;
    renderThumbs();
    setBusy(false);
    files.forEach(function (file, i) {
      upload(file).then(function (saved) {
        if (state !== mine) { return; }
        mine.uploading -= 1;
        if (saved.file) { mine.photos[i].key = saved.file.key; mine.photos[i].filename = saved.file.filename; } else { mine.photos[i].bad = saved.big ? 'big' : 'bad'; }
        if (!mine.uploading && mine.photos.some(function (p) { return p.bad; })) {
          var big = mine.photos.some(function (p) { return p.bad === 'big'; });
          mine.photos = mine.photos.filter(function (p) { return !p.bad; });
          showError(big ? TEXT.tooBig : TEXT.photoBad);
        }
        renderThumbs();
        setBusy(false);
      });
    });
  }

  // ── 보내기 ──
  function body() {
    var targets = state.opts.filter(function (o) { return state.picked[o.no]; }).map(function (o) {
      return o.sheet_id ? { sheet_id: o.sheet_id } : { key: o.key };
    });
    var photos = state.photos.filter(function (p) { return p.key; }).map(function (p) { return { key: p.key, filename: p.filename }; });
    return { targets: targets, note: String(q('[data-pp-rq-note]').value || '').trim(), photos: photos };
  }
  function blockCards(orderId, keys, block) {
    var cards = window.FomsPartsCards || {};
    toArr(root.querySelectorAll('[data-pp-card]')).forEach(function (card) {
      if (card.getAttribute('data-order-id') !== String(orderId) || (keys || []).indexOf(card.getAttribute('data-key')) < 0) { return; }
      var bulk = card.getAttribute('data-state') === 'none' && !card.getAttribute('data-pp-block');
      if (block) {
        card.setAttribute('data-pp-block', block.kind);
        card.setAttribute('data-pp-block-text', block.text);
        card.setAttribute('data-pp-block-why', block.why);
        if (typeof cards.render === 'function') { cards.render(card); }
      }
      var pane = card.closest('[data-pp-pane]');
      if (!bulk || !block || !pane) { return; }
      // [남은 N장 모두 기본] 숫자 — 막힌 안 본 장은 빼고 센다(parts.js bulkable 과 같은 기준)
      toArr(pane.querySelectorAll('[data-pp-act="bulk"] [data-pp-count="unseen"]')).forEach(function (n) {
        var left = Math.max(0, Number(n.textContent || 0) - 1);
        n.textContent = String(left);
        var btn = n.closest('[data-pp-act="bulk"]');
        if (btn && !left) { btn.hidden = true; }
      });
      var text = pane.querySelector('[data-pp-unseen-text]'); // '안 본 도면 N장'도 같은 기준(사장님 2026-11-26)
      if (text) {
        var look = Math.max(0, Number(text.getAttribute('data-pp-unseen-text') || 0) - 1);
        text.setAttribute('data-pp-unseen-text', String(look));
        text.textContent = look ? '안 본 도면 ' : '안 본 도면 없어요';
        if (look) { text.appendChild(document.createElement('b')).textContent = String(look); text.appendChild(document.createTextNode('장')); }
      }
    });
  }
  // 보낸 도면은 이제 막혔다 — 같은 주문 다른 카드 창 고르기에서도 빼고(서버 409 REQUEST_BLOCKED 와 같은 판정), 제 장이 빠진 카드 단추는 숨긴다
  function pruneOpts(orderId, numbers) {
    toArr(root.querySelectorAll('[data-pp-card]')).forEach(function (card) {
      var req = card.getAttribute('data-order-id') === String(orderId) && card.querySelector('[data-pp-req]');
      if (!req) { return; }
      var left = (safeJsonParse(req.getAttribute('data-pp-req-opts'), []) || []).filter(function (o) { return (numbers || []).indexOf(o.no) < 0; });
      req.setAttribute('data-pp-req-opts', JSON.stringify(left));
      if (!left.some(function (o) { return String(o.no) === card.getAttribute('data-no'); })) { req.hidden = true; }
    });
  }
  function send() {
    if (!state || state.busy || state.uploading > 0) { return Promise.resolve(); }
    var data = body();
    if (!data.targets.length) { showError(TEXT.pick); return Promise.resolve(); }
    if (!data.note) { showError(TEXT.note); q('[data-pp-rq-note]').focus(); return Promise.resolve(); }
    var text = JSON.stringify(data);
    if (text !== state.sentBody) { state.key = newKey(); state.sentBody = text; } // 같은 몸으로 다시 누르면 같은 열쇠(한 건)
    var mine = state;
    showError('');
    setBusy(true);
    var url = '/api/orders/' + encodeURIComponent(mine.orderId) + '/production/drawing-request';
    var opts = { method: 'POST', credentials: 'same-origin', body: text,
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'Idempotency-Key': mine.key } };
    var call;
    try { call = fetch(url, opts); } catch (e) { call = Promise.reject(e); }
    return call.then(function (res) {
      return res.json().catch(function () { return null; });
    }).then(function (res) {
      if (state !== mine) { return; }
      setBusy(false);
      if (res && res.success === true) {
        var got = res.data || {};
        close();
        blockCards(mine.orderId, got.keys, got.block);
        pruneOpts(mine.orderId, (got.request && got.request.numbers) || []);
        setStatus(TEXT.sent);
        return;
      }
      showError((res && (res.error || res.message)) || TEXT.offline);
    }).catch(function (e) {
      console.warn('[drawing-request] send', e);
      if (state !== mine) { return; }
      setBusy(false);
      showError(TEXT.offline);
    });
  }

  root.addEventListener('click', function (e) {
    var t = e.target;
    if (!t || typeof t.closest !== 'function') { return; }
    var opener = t.closest('[data-pp-req]');
    if (opener && !modal.contains(opener)) { open(opener); return; }
    if (!state) { return; }
    if (t === modal || t.closest('[data-pp-rq-close]')) { close(); return; }
    var pick = t.closest('[data-pp-rq-no]');
    if (pick) {
      var no = Number(pick.getAttribute('data-pp-rq-no'));
      state.picked[no] = !state.picked[no];
      renderPicks();
      showError('');
      return;
    }
    if (t.closest('[data-pp-rq-add]')) { q('[data-pp-rq-file]').click(); return; }
    if (t.closest('[data-pp-rq-send]')) { send(); }
  });
  q('[data-pp-rq-file]').addEventListener('change', function (e) {
    onFiles(e.target.files);
    e.target.value = '';
  });
  modal.addEventListener('keydown', function (e) { if (e.key === 'Escape') { close(); } });

  window.FomsPartRequest = { open: open, close: close, send: send, onFiles: onFiles, state: function () { return state; } };
})();
