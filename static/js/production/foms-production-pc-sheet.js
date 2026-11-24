/* 생산 PC 첫 화면 — 공정 칸을 누르면 그 주문 · 그 파트의 도면 목록 창(사장님 2026-11-24 "PC 에서도 도면별로 체크, PC 는 감독 성격이
 * 강해 세세한 정보를 볼 수 있어야 돼"). 설계서 docs/specs/2026-11-23-production-self-claim-and-factory2_SPEC.md §4-2 · §4-5 · §4-7 ·
 * §4-11 · §5 · §8-4 에 PC 창을 더한 것.
 *  · 칸 = home_pc_macros.pc_steps 의 [data-foms-pc-sheet="<파트>"](확정 도면 1장 이상인 줄만). 누름 · Enter · Space 로 연다.
 *  · 열 때 GET 두 번(같이): /api/production/part-sheet(도면마다 상태 · 담당 · 완료 · 바뀜 · 막힘 — 글은 서버 글 그대로) ·
 *    /api/production/part-history(바뀐 기록 — 작업 시트와 같은 글, foms-production-sheet-parts.js renderLog). 페이지 · 날짜 탭 요청은 그대로.
 *  · [고치기] 켬(data-edit="1") + 서버 can_write(관리자 · 반장) + 쓰기 파일(foms-production-pc-sheet-write.js)이 있을 때만 줄마다
 *    [체크] · [체크 해제], 창 머리 [모두 체크](아무도 안 맡은 파트) · [체크 해제](손으로 통째 체크한 파트). 누르면 그 파트를 다시 받아
 *    바뀐 줄만 다시 그리고, 뒤의 PC 줄 공정 칸 · 상태 칸을 서버가 그린 HTML(같은 매크로)로 바꿔 끼운다. 막히면 서버 글을 그 줄에.
 *  · 창 = 공용 사유 시트 겉틀(home_pc_sheet.html). Esc 닫기 · 초점 가둠 · 닫으면 누른 칸으로. 반장 손 체크 확인 창(sheet-parts)이 위에
 *    열려 있으면 키는 그 창 몫. 셸 조각 교체로 다시 실행돼도 화면마다 한 번(data-foms-pc-sheet-bound), 문서 키 리스너는 한 번. */
(function () {
  'use strict';

  var root = document.querySelector('[data-foms-prod-home]');
  var box = root && root.querySelector('[data-foms-pc-sheet-box]');
  if (!root || !box || root.getAttribute('data-foms-pc-sheet-bound') === '1') { return; }
  root.setAttribute('data-foms-pc-sheet-bound', '1');
  var G = window.__FOMS_PC_SHEET = window.__FOMS_PC_SHEET || {};

  var OFFLINE = '연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요.';
  var WAIT = '불러오는 중…';
  var SAVING = '저장하는 중…';
  var LABELS = { cut: '재단', edge: '엣지', assemble: '조립', inspect: '검수' };
  var S = { id: '', part: '', opener: null, data: null, seq: 0, busy: false, sig: {} };
  function toArr(list) { return [].slice.call(list || []); }
  function q(sel) { return box.querySelector(sel); }
  function el(tag, cls, text) { var n = document.createElement(tag); n.className = cls || ''; if (text != null) { n.textContent = text; } return n; }

  // ── 읽기(GET) — 늘 {status, body} 로 끝난다(try/catch · 받은 몸은 부르는 쪽이 success 를 본다) ──
  function getJson(url) {
    try {
      return fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
        .then(function (res) { return res.json().catch(function () { return null; }).then(function (body) { return { status: res.status, body: body }; }); })
        .catch(function () { return { status: 0, body: null }; });
    } catch (e) { return Promise.resolve({ status: 0, body: null }); }
  }
  function failText(r) { return !r || r.status === 0 ? OFFLINE : ((r.body && r.body.error) || '불러오지 못했어요. 다시 눌러 주세요.'); }
  function ok(r) { return !!(r && r.body && r.body.success === true && r.body.data); }

  function writer() { return box.getAttribute('data-edit') === '1' && !!(S.data && S.data.can_write) && !!window.FomsPcSheetWrite; }
  function actButton(text, kind, key, pri) {
    var b = el('button', 'foms-prod-home__btn fpc-sheet__btn' + (pri ? ' foms-prod-home__btn--pri' : ''), text);
    b.type = 'button';
    b.setAttribute('data-foms-pc-sheet-act', kind);
    b.setAttribute('data-label', text);
    if (key) { b.setAttribute('data-key', key); }
    return b;
  }

  // ── 그리기 — 서버 글을 textContent 로만(HTML 은 서버 매크로가 그린 줄 칸뿐) ──
  function picNode(r) {
    var pic = Object.assign(el('a', 'fpc-sheet__pic' + (r.thumb ? '' : ' is-file')), { href: r.view_url || '#', target: '_blank', rel: 'noopener' });
    pic.setAttribute('aria-label', r.label + ' 크게 보기');
    if (!r.thumb) {
      pic.appendChild(el('b', '', String(r.filename || r.key).split('.').pop().toUpperCase()));
      return pic;
    }
    var img = Object.assign(el('img'), { alt: '', loading: 'lazy', decoding: 'async' });
    img.addEventListener('error', function () { img.replaceWith(el('span', 'fpc-sheet__broken', '그림을 못 불러왔어요')); });
    img.src = r.thumb;
    pic.appendChild(img);
    return pic;
  }
  function rowNode(r) {
    var li = el('li', 'fpc-sheet__row is-' + r.state);
    li.setAttribute('data-key', r.key);
    li.appendChild(picNode(r));
    var main = el('div', 'fpc-sheet__main');
    var nm = el('p', 'fpc-sheet__nm');
    nm.appendChild(el('b', '', r.label));
    nm.appendChild(el('span', '', r.item));
    main.appendChild(nm);
    var meta = [r.holder, r.done].filter(Boolean);
    if (meta.length) {
      var m = el('p', 'fpc-sheet__meta');
      meta.forEach(function (t) { m.appendChild(el('span', '', t)); });
      main.appendChild(m);
    }
    if (r.handed) { main.appendChild(el('p', 'fpc-sheet__chg', r.handed)); }
    if (r.block) { main.appendChild(el('p', 'fpc-sheet__blk is-' + r.block.kind, r.block.text)); }
    var err = el('p', 'fpc-sheet__err');
    err.setAttribute('role', 'alert');
    err.hidden = true;
    main.appendChild(err);
    li.appendChild(main);
    var st = el('span', 'fpc-sheet__st is-' + r.state, r.word);
    if (r.note) { st.appendChild(el('small', '', r.note)); }
    li.appendChild(st);
    if (writer() && r.act) { li.appendChild(actButton(r.act === 'check' ? '체크' : '체크 해제', r.act, r.key, r.act === 'check')); }
    return li;
  }
  function renderHead(d) {
    var w = writer();
    q('[data-foms-pc-sheet-title]').textContent = d.label + ' · 도면 ' + d.total + '장';
    q('[data-foms-pc-sheet-sub]').textContent = d.customer_name + ' #' + d.order_id;
    var note = q('[data-foms-pc-sheet-note]');
    note.textContent = w && d.notice ? d.notice : '';
    note.hidden = !(w && d.notice);
    var tools = q('[data-foms-pc-sheet-tools]');
    tools.textContent = '';
    if (w && d.all) {
      var all = actButton('모두 체크', 'all', '', true);
      all.setAttribute('data-foms-sheet-step', d.part); // 반장 손 체크 확인 창(sheet-parts beforeToggle)이 파트를 읽는다
      tools.appendChild(all);
    }
    if (w && d.hand_off) { tools.appendChild(actButton('체크 해제', 'hand-off', '', false)); }
    box.setAttribute('data-order-id', String(d.order_id));
    q('[data-foms-sheet-parts]').setAttribute('data-foms-sheet-parts', JSON.stringify({ sheets: d.sheets, parts: d.parts, keys: d.keys }));
  }
  function renderRows(d) { // 바뀐 줄만 새로 그린다(안 바뀐 줄 · 그림은 그대로 둔다)
    var list = q('[data-foms-pc-sheet-rows]');
    var old = {};
    var sigs = {};
    var w = writer() ? '1' : '0';
    toArr(list.children).forEach(function (n) { old[n.getAttribute('data-key')] = n; });
    var nodes = d.rows.map(function (r) {
      sigs[r.key] = JSON.stringify(r) + w;
      return old[r.key] && S.sig[r.key] === sigs[r.key] ? old[r.key] : rowNode(r);
    });
    nodes.forEach(function (n, i) { if (list.children[i] !== n) { list.insertBefore(n, list.children[i] || null); } });
    while (list.children.length > nodes.length) { list.removeChild(list.lastChild); }
    S.sig = sigs;
  }
  function msg(text) { q('[data-foms-pc-sheet-msg]').textContent = text || ''; }
  function renderLog(r) {
    var list = q('[data-foms-pc-sheet-log]');
    var sp = window.FomsSheetParts;
    var show = !!(sp && sp.renderLog);
    list.hidden = !show;
    q('[data-foms-pc-sheet-loghead]').hidden = !show;
    if (!show) { return; }
    if (!ok(r)) {
      list.textContent = '';
      list.appendChild(el('li', '', r && r.status === 0 ? OFFLINE : '기록을 못 불러왔어요. 다시 눌러 주세요.'));
      return;
    }
    sp.renderLog(list, r.body.data.items || [], (S.data && S.data.keys) || []);
  }

  // 뒤의 PC 줄 — 서버가 첫 화면과 같은 매크로로 그린 공정 칸 · 상태 칸을 바꿔 끼운다(늦음 · 빠듯 테두리도)
  function applyRow(d) {
    if (!d.cells_html) { return; }
    toArr(root.querySelectorAll('[data-foms-home-dayrow="' + d.order_id + '"]')).forEach(function (row) {
      var steps = row.querySelector('.fpc-steps');
      var st = row.querySelector('.fpc-st');
      if (!steps) { return; }
      steps.outerHTML = d.cells_html;
      if (st && d.status_html) { st.outerHTML = d.status_html; }
      row.classList.toggle('is-late', d.late === 'late');
      row.classList.toggle('is-tight', d.late === 'tight');
    });
  }

  // ── 받기 — 열 때 · 쓰기 뒤. 창이 닫혔거나 다른 칸을 열었으면 버린다(seq) ──
  function load(after) {
    var seq = S.seq;
    var base = 'order_id=' + encodeURIComponent(S.id) + '&part=' + encodeURIComponent(S.part);
    return Promise.all([getJson('/api/production/part-sheet?' + base), getJson('/api/production/part-history?' + base)]).then(function (got) {
      if (seq !== S.seq || box.hidden) { return; }
      if (!ok(got[0])) { msg(failText(got[0])); return; }
      S.data = got[0].body.data;
      msg('');
      renderHead(S.data);
      renderRows(S.data);
      renderLog(got[1]);
      if (after) { applyRow(S.data); }
    });
  }
  function open(cell) {
    var row = cell.closest('[data-foms-home-dayrow]');
    if (!row) { return; }
    S.seq += 1;
    S.id = row.getAttribute('data-foms-home-dayrow');
    S.part = cell.getAttribute('data-foms-pc-sheet');
    S.opener = cell;
    S.data = null;
    S.sig = {};
    S.busy = false;
    var name = row.querySelector('.fpc-nm b');
    q('[data-foms-pc-sheet-title]').textContent = LABELS[S.part] || S.part;
    q('[data-foms-pc-sheet-sub]').textContent = (name ? name.textContent : '') + ' #' + S.id;
    q('[data-foms-pc-sheet-note]').hidden = true;
    q('[data-foms-pc-sheet-tools]').textContent = '';
    q('[data-foms-pc-sheet-rows]').textContent = '';
    q('[data-foms-pc-sheet-log]').hidden = true;
    q('[data-foms-pc-sheet-loghead]').hidden = true;
    msg(WAIT);
    box.hidden = false;
    box.setAttribute('aria-hidden', 'false');
    q('[data-foms-pc-sheet-body]').scrollTop = 0;
    q('.fpc-sheet__x').focus();
    load(false);
  }
  function cellOf(id, part) { return root.querySelector('[data-foms-home-dayrow="' + id + '"] [data-foms-pc-sheet="' + part + '"]'); }
  function close() {
    if (box.hidden) { return; }
    S.seq += 1;
    box.hidden = true;
    box.setAttribute('aria-hidden', 'true');
    var back = S.opener && document.contains(S.opener) ? S.opener : cellOf(S.id, S.part); // 칸을 바꿔 끼웠으면 새 칸으로
    if (back) { back.focus(); }
  }

  // ── 쓰기 단추 — 쓰기는 foms-production-pc-sheet-write.js(있는 쓰기 길). 두 번 누름은 버리고, 끝나면 다시 받아 서버 모습으로 ──
  function setBusy(on, btn) {
    S.busy = on;
    toArr(box.querySelectorAll('[data-foms-pc-sheet-act]')).forEach(function (b) {
      b.classList.toggle('is-wait', on);
      if (on) { b.setAttribute('aria-disabled', 'true'); } else { b.removeAttribute('aria-disabled'); b.textContent = b.getAttribute('data-label'); }
    });
    if (on && btn) { btn.textContent = SAVING; }
  }
  function rowOf(key) { return key ? toArr(q('[data-foms-pc-sheet-rows]').children).filter(function (n) { return n.getAttribute('data-key') === key; })[0] : null; }
  function showError(key, text) {
    var li = rowOf(key);
    var err = li && li.querySelector('.fpc-sheet__err');
    if (err) { err.textContent = text; err.hidden = false; } else { msg(text); }
  }
  function focusAfter(key) {
    var li = rowOf(key);
    var target = (li && li.querySelector('[data-foms-pc-sheet-act]')) || q('[data-foms-pc-sheet-act]') || q('.fpc-sheet__x');
    if (target) { target.focus(); }
  }
  function track(btn, key, promise) {
    toArr(box.querySelectorAll('.fpc-sheet__err')).forEach(function (n) { n.hidden = true; });
    msg('');
    setBusy(true, btn);
    var seq = S.seq;
    return promise.then(function (res) {
      return load(true).then(function () {
        if (seq !== S.seq) { return; }
        setBusy(false);
        if (!res || !res.ok) { showError(key, (res && res.message) || OFFLINE); }
        focusAfter(key);
      });
    });
  }
  function act(btn) {
    var W = window.FomsPcSheetWrite;
    if (!W || !S.data || S.busy || btn.getAttribute('aria-disabled') === 'true') { return; }
    var kind = btn.getAttribute('data-foms-pc-sheet-act');
    var key = btn.getAttribute('data-key') || '';
    var r = S.data.rows.filter(function (x) { return x.key === key; })[0];
    if (kind === 'all') { W.askAll(box, btn, function () { track(btn, '', W.stepSet(S.data, true)); }); return; }
    if (kind === 'hand-off') { track(btn, '', W.stepSet(S.data, false)); return; }
    if (r) { track(btn, key, kind === 'check' ? W.check(S.data, r) : W.uncheck(S.data, r)); }
  }

  // ── 누름 · 키(이 화면 안 위임) ──
  root.addEventListener('click', function (e) {
    var t = e.target;
    if (!t || typeof t.closest !== 'function') { return; }
    var cell = t.closest('[data-foms-pc-sheet]');
    if (cell && !box.contains(cell)) { e.preventDefault(); open(cell); return; }
    var b = t.closest('[data-foms-pc-sheet-act]');
    if (b && box.contains(b)) { act(b); return; }
    if (t.closest('[data-foms-pc-sheet-close]')) { close(); }
  });
  root.addEventListener('keydown', function (e) {
    var cell = e.target && typeof e.target.closest === 'function' ? e.target.closest('[data-foms-pc-sheet]') : null;
    if (cell && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); open(cell); }
  });
  function confirmOpen() {
    var c = document.querySelector('[data-foms-sheet-confirm]');
    return !!c && !c.hidden;
  }
  function onKey(e) {
    if (box.hidden || !document.contains(box) || confirmOpen()) { return; } // 확인 창이 위면 그 창 몫(sheet-parts)
    if (e.key === 'Escape') { e.preventDefault(); close(); return; }
    if (e.key !== 'Tab') { return; }
    var list = toArr(box.querySelectorAll('a[href], button')).filter(function (n) { return n.offsetParent !== null && !n.disabled; });
    if (!list.length) { return; }
    var i = list.indexOf(document.activeElement);
    e.preventDefault();
    list[e.shiftKey ? (i <= 0 ? list.length - 1 : i - 1) : (i < 0 || i === list.length - 1 ? 0 : i + 1)].focus();
  }
  G.api = { key: onKey };
  if (!G.once) {
    G.once = true;
    document.addEventListener('keydown', function (e) { if (G.api) { G.api.key(e); } }, true); // 확인 창 Esc 보다 먼저 보고 비켜 준다
  }
  window.FomsPcSheet = { open: open, close: close };
})();
