/* 생산 작업 시트 — 파트 카드 3판 칸(설계서 2026-11-23 §4-2 · §8-3, 승인 때 고친 것 2 · 3). 루트 = [data-foms-prod-sheet-page].
 * foms-production-sheet-page.js 가 이 파일(window.FomsSheetParts)이 있을 때만 부른다 — 없으면 시트는 지금 그대로다.
 *  · beforeToggle: 반장 · 관리자가 카드를 안 쓴 파트의 공정 칸을 **켤 때**(끌 때는 아님), 확정 도면이 1장 이상이면 먼저 묻는다
 *    "재단 완료할까요?" · "이 주문의 도면 5장이 모두 재단 완료로 처리돼요." [취소] [재단 완료]. 카드를 쓴 파트는 묻지 않고 보낸다
 *    (서버가 남은 장을 세어 막는다 — 409 PART_USES_CARDS). 확정 도면 0장이면 지금처럼 바로.
 *    '내 공정' [<공정> 완료](옛 [<공정> 끝] · foms-production-home-steps.js 판 · foms-production-home.js 줄, 사장님 2026-11-25 "도면이 있는 주문만 한 번
 *    묻기")도 이 함수 하나 — 단추에 서버가 실은 자료(data-foms-sheet-parts, 열쇠 = data-step-key), [취소] · Esc · 바깥이면 no().
 *    창을 연 뒤 OPEN_GUARD_MS 안의 누름은 버린다(두 번 누름의 둘째가 [작업 완료] · 바깥에 떨어지지 않게).
 *    막힌 도면이 있는 주문(서버 자료 fix — 2026-11-25 설계서 §2-4)은 본문만 "이 주문의 도면 5장 중 4장이 재단 완료로 처리돼요. 도면 2는
 *    고치는 중이라 빼요."(뒤 문장 = 서버 글 fix.tail). 응답 expanded(막힌 장을 빼고 처리됨)는 그 칸 옆 글을 서버 글(expanded.note)로,
 *    '내 공정' [<공정> 완료] 뒤 알림은 doneText(expanded) — "도면 3장 중 2장을 재단 완료로 처리했어요. 도면 2는 고치는 중이라 뺐어요."
 *  · refused: 서버 거절 글(PART_USES_CARDS · STEP_SET_BY_CARDS)을 공정 칸 아래 .fpp-stepmsg 에(글 = 서버 글 그대로).
 *  · why: 회색 [제작 완료] 누름 — 카드를 쓴 주문은 서버의 남은 장 수(parts.left_n)로 "미완료가 있어요 — 재단 1장 · 검수 3장".
 *    카드를 안 쓴 주문은 null(시트 JS 가 지금 글을 그대로 쓴다).
 *  · [바뀐 기록 보기]: 처음 누를 때 GET /api/production/part-history 한 번, 공정 · 장마다 한 줄. 쓰기 요청은 POST 0(공정 POST 는 시트 JS).
 * 창 겉모양은 공용 사유 시트(foms-reason-sheet.css) — 초점 가두기 · Esc · 닫으면 누른 칸으로 초점. */
(function () {
  'use strict';

  var LABELS = { cut: '재단', edge: '엣지', assemble: '조립', inspect: '검수' };
  var ORDER = ['cut', 'edge', 'assemble', 'inspect'];
  // 바뀐 기록 낱말(2026-11-25 multi-holder §8-1 · §8-2 24) — check = PC [완료 처리](시작 + 완료 한 요청), remove = 반장의 남의 시작 취소
  var KIND = { take: '작업 시작', join: '같이 작업', basic: '기본', done: '완료', check: '완료', undo: '완료 취소', release: '시작 취소',
    remove: '시작 취소', step_on: '작업 완료', step_off: '작업 취소' };
  function toArr(list) { return [].slice.call(list || []); }
  function safeJsonParse(value, fallback) {
    try { var text = String(value || '').trim(); return text ? JSON.parse(text) : fallback; } catch (e) { return fallback; }
  }
  function toward(name) { var c = name.charCodeAt(name.length - 1) - 0xAC00; var f = c >= 0 && c < 11172 ? c % 28 : -1; return name + (f === 0 || f === 8 ? '로' : '으로'); }
  function kst(iso) { var t = Date.parse(iso || ''); return isNaN(t) ? null : new Date(t + 9 * 36e5); }
  function stamp(d, prev) {
    var hm = ('0' + d.getUTCHours()).slice(-2) + ':' + ('0' + d.getUTCMinutes()).slice(-2);
    var day = (d.getUTCMonth() + 1) + '/' + d.getUTCDate();
    return prev && prev.getUTCDate() === d.getUTCDate() && prev.getUTCMonth() === d.getUTCMonth() ? hm : day + ' ' + hm;
  }
  function holder(page) { return page.hasAttribute('data-foms-sheet-parts') ? page : page.querySelector('[data-foms-sheet-parts]'); }
  function data(page) { var h = holder(page); return h ? safeJsonParse(h.getAttribute('data-foms-sheet-parts'), null) : null; }
  // 옆 시트는 자료가 안 실려 있다 — 칸을 켤 때만 공정 API GET 한 번(읽기)
  function load(page) {
    var have = data(page);
    if (have) { return Promise.resolve(have); }
    var url = '/api/orders/' + encodeURIComponent(page.getAttribute('data-order-id') || '') + '/production/steps';
    try {
      return fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
        .then(function (res) { return res.ok ? res.json() : null; })
        .then(function (body) { return body && body.success === true ? body.data : null; })
        .catch(function () { return null; });
    } catch (e) { return Promise.resolve(null); }
  }

  // ── 반장 손 체크 확인 창 ──
  // 창 상태 · 문서 리스너는 문서에 하나 — 셸 조각 교체로 이 파일이 다시 돌아도 리스너(한 번)는 마지막으로 돈 함수(S.api)와 같은 창 상태를
  // 본다(예전엔 리스너가 첫 실행의 창 상태만 봐서, 조각 교체 뒤 연 창의 [작업 완료] · [취소]가 먹지 않았다 — 2026-11-25 찾음).
  var S = window.__FOMS_SHEET_PARTS = window.__FOMS_SHEET_PARTS || { dlg: { box: null, yes: null, no: null, opener: null, at: 0 } };
  var dlg = S.dlg;
  var OPEN_GUARD_MS = 400;
  function closeDialog(run) {
    var box = dlg.box;
    if (!box || box.hidden) { return; }
    box.hidden = true;
    box.setAttribute('aria-hidden', 'true');
    var yes = dlg.yes;
    var no = dlg.no;
    var opener = dlg.opener;
    dlg.yes = null;
    dlg.no = null;
    if (opener && document.contains(opener)) { opener.focus(); }
    if (run && yes) { yes(); } else if (!run && no) { no(); }
  }
  function body(label, sheets, fix) {
    if (fix && fix.tail) { return '이 주문의 도면 ' + sheets + '장 중 ' + fix.done + '장이 ' + label + ' 완료로 처리돼요. ' + fix.tail; }
    return '이 주문의 도면 ' + sheets + '장이 모두 ' + label + ' 완료로 처리돼요.';
  }
  function doneText(ex) { // 풀어 쓴 [<공정> 완료] 뒤 알림(판결 B) — 뒤 문장(조사 포함)은 서버 글 ex.tail, 화면은 잇기만
    return '도면 ' + ex.total_n + '장 중 ' + ex.done_n + '장을 ' + ex.part_label + ' 완료로 처리했어요. ' + ex.tail;
  }
  // 글 + 단추 둘 창 하나 — 공정 칸 손 체크(ask)와 작업 시트 생산 단추(tablet-domain-sheets.js · sheet-factory.js, 사장님 2026-11-27
  // "앱 창으로 바꾸기")가 같이 쓴다. o = {title, body, yes, no, opener, go, cancel}. 창 조각이 없으면 false(부른 쪽이 지금 길로). 본문이 없으면 숨김
  function open(o) {
    var box = document.querySelector('[data-foms-sheet-confirm]');
    if (!box) { return false; }
    dlg.box = box;
    dlg.yes = o.go;
    dlg.no = o.cancel || null;
    dlg.opener = o.opener || null;
    dlg.at = Date.now();
    box.querySelector('[data-foms-sheet-confirm-title]').textContent = o.title;
    box.querySelector('[data-foms-sheet-confirm-yes]').textContent = o.yes;
    var text = box.querySelector('[data-foms-sheet-confirm-body]');
    text.textContent = o.body || '';
    text.hidden = !o.body;
    var no = box.querySelector('[data-foms-sheet-confirm-no].foms-btn');
    if (no) { no.textContent = o.no || '취소'; }
    box.hidden = false;
    box.setAttribute('aria-hidden', 'false');
    if (no) { no.focus(); }
    return true;
  }
  function ask(label, sheets, opener, go, no, fix) { // 제목 = 누른 단추와 같은 말(사장님 2026-11-26)
    if (!open({ title: label + ' 완료할까요?', yes: label + ' 완료', body: body(label, sheets, fix), opener: opener, go: go, cancel: no })) { go(); }
  }
  function beforeToggle(page, btn, done, go, no) {
    if (!done) { go(); return; }
    var key = btn.getAttribute('data-foms-sheet-step') || btn.getAttribute('data-step-key'); // 공정 칸 · '내 공정' [<공정> 완료]
    btn.disabled = true;
    load(page).then(function (info) {
      btn.disabled = false;
      var part = info && info.parts ? info.parts[key] : null;
      if (!info || !info.sheets || !part || part.uses_cards) { go(); return; } // 카드 쓴 파트 · 도면 0장 · 자료 없음 = 서버가 판정
      ask(LABELS[key] || key, info.sheets, btn, go, no, info.fix);
    });
  }

  // ── 서버 거절 글 · 응답 뒤 자료 ──
  function stepMsg(page, text) {
    var box = page.querySelector('[data-foms-sheet-stepmsg]');
    if (!box) { return false; }
    box.textContent = text || '';
    box.hidden = !text;
    return true;
  }
  function refused(page, result) {
    var body = (result && result.data) || {};
    var code = (body.data && body.data.code) || body.code;
    if (code !== 'PART_USES_CARDS' && code !== 'STEP_SET_BY_CARDS') { return false; }
    return stepMsg(page, body.error || body.message || result.message);
  }
  function render(page, payload) {
    page.dispatchEvent(new CustomEvent('foms:sheet-steps', { detail: payload || {} })); // 공정 응답 — 공장 단추(sheet-factory)가 다시 그린다
    stepMsg(page, '');
    var h = holder(page);
    var info = data(page);
    expandedNote(page, payload && payload.expanded);
    if (!h || !info || !payload || !payload.parts) { return; }
    info.parts = payload.parts;
    if (payload.sheets != null) { info.sheets = payload.sheets; }
    if (payload.fix) { info.fix = payload.fix; } else { delete info.fix; }
    h.setAttribute('data-foms-sheet-parts', JSON.stringify(info));
  }
  function expandedNote(page, ex) { // 막힌 장을 빼고 처리된 파트 — 칸 옆 글 = 서버 글("도면 4/5 · 1장 미완료"), 카드 쓴 파트 글처럼 고정
    if (!ex || !ex.note) { return; }
    var cell = page.querySelector('[data-foms-sheet-step="' + ex.part + '"] [data-foms-sheet-step-meta]');
    if (!cell) { return; }
    cell.textContent = ex.note;
    cell.setAttribute('data-foms-sheet-cardnote', '');
    cell.classList.add('fpp-note', 'is-miss');
  }
  function why(page) {
    var info = data(page);
    if (!info || !info.parts || !ORDER.some(function (k) { return info.parts[k] && info.parts[k].uses_cards; })) { return null; }
    if (!info.sheets) { return '도면이 없어요 — 공정 칸을 작업 완료로 처리하거나 관리자에게 말해 주세요.'; }
    var left = ORDER.filter(function (k) { return info.parts[k] && !info.parts[k].done; })
      .map(function (k) { return LABELS[k] + ' ' + info.parts[k].left_n + '장'; });
    return left.length ? '미완료가 있어요 — ' + left.join(' · ') : null;
  }
  function showWhy(statusEl, text) {
    if (!statusEl) { return; }
    statusEl.textContent = '';
    statusEl.classList.remove('is-ok');
    statusEl.classList.add('is-bad');
    var span = document.createElement('span');
    span.className = 'fpp-why';
    span.textContent = text;
    statusEl.appendChild(span);
  }

  // ── 바뀐 기록 ──
  function line(item, prev) {
    var d = kst(item.at);
    var who = item.by_name || '';
    var t = d ? ' ' + stamp(d, prev) : '';
    if (item.kind === 'takeover') { return (who ? toward(who) + ' ' : '') + '바뀜' + t; }
    if (item.kind === 'step_on' && item.via === 'part_marks') { return '도면 모두 완료 — 작업 완료 처리' + t; } // 카드 동기화(사람 이름 없음)
    if (item.kind === 'step_off' && item.via === 'part_marks') { return '도면 미완료 — 작업 취소 처리' + t; }
    if ((item.kind === 'remove' || item.kind === 'release') && item.target_name && item.target_name !== who) { // "김재단 시작 취소 (박반장)"
      return item.target_name + ' ' + KIND[item.kind] + (who ? ' (' + who + ')' : '') + t;
    }
    var holderName = item.holder_name && item.holder_name !== who ? '(' + item.holder_name + ' 대신)' : '';
    return [who, holderName, KIND[item.kind] || item.kind].filter(Boolean).join(' ') + t;
  }
  function renderLog(list, items, keys) {
    var groups = {};
    var order = [];
    items.forEach(function (it) {
      var g = (it.part || '') + '|' + (it.drawing_key || '');
      if (!groups[g]) { groups[g] = []; order.push(g); }
      groups[g].push(it);
    });
    order.sort(function (a, b) {
      var pa = a.split('|');
      var pb = b.split('|');
      return (ORDER.indexOf(pa[0]) - ORDER.indexOf(pb[0])) || (keys.indexOf(pa[1]) - keys.indexOf(pb[1]));
    });
    list.textContent = '';
    order.forEach(function (g) {
      var parts = g.split('|');
      var no = keys.indexOf(parts[1]);
      var head = (LABELS[parts[0]] || parts[0]) + (parts[1] ? (no >= 0 ? ' 도면 ' + (no + 1) + '/' + keys.length : ' 옛 도면') : ' 칸');
      var prev = null;
      var text = groups[g].map(function (it) { var s = line(it, prev); prev = kst(it.at) || prev; return s; }).join(' → ');
      var li = document.createElement('li');
      var b = document.createElement('b');
      b.textContent = head;
      li.appendChild(b);
      li.appendChild(document.createTextNode(': ' + text));
      list.appendChild(li);
    });
    if (!order.length) { var none = document.createElement('li'); none.textContent = '아직 기록이 없어요.'; list.appendChild(none); }
  }
  function toggleLog(page, btn) {
    var list = page.querySelector('[data-foms-sheet-log]');
    if (!list) { return; }
    var open = list.hidden;
    list.hidden = !open;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (!open || list.getAttribute('data-loaded') === '1') { return; }
    list.textContent = '';
    var wait = document.createElement('li');
    wait.textContent = '불러오는 중…';
    list.appendChild(wait);
    var url = '/api/production/part-history?order_id=' + encodeURIComponent(page.getAttribute('data-order-id') || '');
    var keys = ((data(page) || {}).keys) || [];
    try {
      fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
        .then(function (res) { return res.json().catch(function () { return null; }); })
        .then(function (body) {
          if (!body || body.success !== true) { wait.textContent = (body && body.error) || '기록을 못 불러왔어요. 다시 눌러 주세요.'; return; }
          list.setAttribute('data-loaded', '1');
          renderLog(list, (body.data && body.data.items) || [], keys);
        })
        .catch(function () { wait.textContent = '연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요.'; });
    } catch (e) { wait.textContent = '기록을 못 불러왔어요. 다시 눌러 주세요.'; }
  }

  S.api = { close: closeDialog, toggleLog: toggleLog };
  if (!S.bound) {
    S.bound = true;
    document.addEventListener('click', function (e) {
      var t = e.target;
      if (!t || typeof t.closest !== 'function') { return; }
      var hit = t.closest('[data-foms-sheet-confirm-yes], [data-foms-sheet-confirm-no]');
      if (hit) { // 지금 연 창의 단추만 · 연 뒤 OPEN_GUARD_MS 안 누름은 버린다(두 번 누름)
        if (dlg.box && dlg.box.contains(hit) && Date.now() - dlg.at >= OPEN_GUARD_MS) { S.api.close(hit.hasAttribute('data-foms-sheet-confirm-yes')); }
        return;
      }
      var log = t.closest('[data-foms-sheet-loglink]');
      var page = log && log.closest('[data-foms-prod-sheet-page]');
      if (page) { S.api.toggleLog(page, log); }
    });
    document.addEventListener('keydown', function (e) {
      var box = dlg.box;
      if (!box || box.hidden || !document.contains(box)) { return; } // 조각 교체로 떠난 창은 키를 가두지 않는다
      if (e.key === 'Escape') { S.api.close(false); return; }
      if (e.key !== 'Tab') { return; }
      var btns = toArr(box.querySelectorAll('button.foms-btn'));
      if (!btns.length) { return; }
      var i = btns.indexOf(document.activeElement);
      e.preventDefault();
      btns[(i + (e.shiftKey ? -1 : 1) + btns.length) % btns.length].focus();
    });
  }
  // renderLog: PC 도면 목록 창(foms-production-pc-sheet.js, 2026-11-24)이 바뀐 기록을 작업 시트와 같은 글로 그린다
  // confirm: 작업 시트 · 생산 첫 화면의 [제작 시작] · [제작 완료] · [완료 취소] · [보류 해제] · 공장 단추 확인(위 open)
  window.FomsSheetParts = { beforeToggle: beforeToggle, refused: refused, render: render, why: why, showWhy: showWhy, renderLog: renderLog,
    doneText: doneText, confirm: open };
})();
