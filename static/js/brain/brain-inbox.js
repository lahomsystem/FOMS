/**
 * 회사 지식 '제안함' 탭(HAUD master brain 설계서 7.5 화면 4 · 승인 흐름 · 사장님 D101 · D103) — 읽기 GET /api/brain/inbox,
 * 결정 POST /api/brain/proposals/<id>/apply · reject · bulk-apply. fetch 는 brain-dom.js 한 곳(try/catch + data.success).
 *
 * - 첫 화면은 네 묶음 한 줄씩(brain-inbox-bins.js · 설계서 7.9), '열기'를 누르면 그 묶음 카드만 · '← 승인 대기'로 돌아간다.
 * - ① 이름 · ④ 표시 묶음은 관리자 PC 에서 표 한 장(brain-inbox-table.js · D151) — 안 고친 줄은 한꺼번에, 고친 줄은 하나씩.
 * - 승인: 기준 판 · 화면이 잰 결정 시간(카드를 보인 뒤 누를 때까지) · 등급 B 확인 글을 같이 보낸다(서버가 다시 본다).
 * - 고쳐 넣기: 한 번 누르면 고칠 칸이 열리고, '고친 값으로 넣기' 한 번이면 넣는다(넣기만큼 쉽게).
 * - 거절: 까닭 칩 하나를 누르면 끝(남겨서 같은 제안이 다시 오지 않게). 'PC 에서 볼게요'는 이 화면에서만 접는다(서버 쓰기 없음).
 * - 휴대폰 폭(640px 이하)이면 칸 하나 고침의 넣기와 'PC 에서 볼게요'만 그리고, 폭이 바뀌면 다시 그린다.
 */
(function () {
  'use strict';

  var ctx = window.FOMS_BRAIN_CTX;
  if (!ctx || window.__FOMS_BRAIN_INBOX_BOUND) return;
  window.__FOMS_BRAIN_INBOX_BOUND = true;

  var dom = window.FOMS_BRAIN_DOM;
  var review = window.FOMS_BRAIN_REVIEW;
  var cardKit = window.FOMS_BRAIN_INBOX_CARD;
  var bins = window.FOMS_BRAIN_INBOX_BINS;
  var tableKit = window.FOMS_BRAIN_INBOX_TABLE;
  var questionKit = window.FOMS_BRAIN_INBOX_QUESTION;
  var root = ctx.root;
  // 등급과 상관없이 한꺼번에 승인하는 묶음(서버 판정 — 관리자 ① · ④, 상담팀장 ①: 설계서 7.9 · D151 · D167)
  var tableBins = (root.getAttribute('data-wide-bins') || '').split(' ');
  var list = root.querySelector('[data-brain-inbox]');
  var laterList = root.querySelector('[data-brain-later]');
  var laterBox = root.querySelector('[data-brain-later-box]');
  var laterTitle = root.querySelector('[data-brain-later-title]');
  var status = root.querySelector('[data-brain-inbox-status]');
  var aiLine = root.querySelector('[data-brain-inbox-ai]');
  var bulk = root.querySelector('[data-brain-bulk]');
  var binList = root.querySelector('[data-brain-bins]');
  var binIntro = root.querySelector('[data-brain-bins-intro]');
  var binBar = root.querySelector('[data-brain-binbar]');
  var binTitle = root.querySelector('[data-brain-bin-title]');
  if (!list || !cardKit || !review || !bins || !binList) return;

  var urls = { inbox: root.getAttribute('data-inbox-url'), proposals: root.getAttribute('data-proposals-url'),
               bulk: root.getAttribute('data-bulk-url') };
  var phoneQuery = window.matchMedia('(max-width: 640px)');
  var data = null;
  var loaded = false;
  var deferred = {};
  var openBin = '';

  function isPhone() {
    return phoneQuery.matches;
  }

  function setCount(n) {
    var badge = root.querySelector('[data-brain-count="inbox"]');
    if (!badge) return;
    badge.textContent = String(n);
    badge.classList.toggle('is-zero', !n);
  }

  function findView(changeId) {
    var id = Number(changeId);
    var cards = (data && data.cards) || [];
    for (var i = 0; i < cards.length; i += 1) {
      var all = [cards[i].main].concat(cards[i].attached);
      for (var j = 0; j < all.length; j += 1) if (all[j].id === id) return all[j];
    }
    return null;
  }

  /** 첫 화면(묶음 목록)과 묶음 안(카드)을 갈라 보인다 — 연 묶음이 비면 첫 화면으로. */
  function showBins(all) {
    if (openBin && !bins.inBin(all, openBin).length) openBin = '';
    binList.hidden = !!openBin;
    if (binIntro) binIntro.hidden = !all.length;  // 카드마다 되풀이하던 '승인의 뜻'을 여기 한 번만(사장님 11-04)
    if (binBar) binBar.hidden = !openBin;
    if (binTitle) binTitle.textContent = openBin ? bins.title(openBin, bins.inBin(all, openBin).length) : '';
    if (!openBin) bins.renderOverview(binList, all);
    return openBin ? bins.inBin(all, openBin) : [];
  }

  function render() {
    var phone = isPhone();
    root.classList.toggle('is-phone', phone);
    dom.clear(list);
    dom.clear(laterList);
    var all = (data && data.cards) || [];
    var cards = showBins(all);
    var later = 0;
    var asTable = !!tableKit && !phone && tableBins.indexOf(openBin) >= 0;
    if (asTable) tableKit.render(list, cards, openBin);
    var asQuestion = !!questionKit && openBin === 'decide';  // 질문 카드는 휴대폰에서도(사장님이 폰으로 정한다)
    cards.forEach(function (card) {
      if (asTable) return;
      var node = asQuestion ? questionKit.build(card) : cardKit.build(card, ctx, phone);
      if (deferred[card.id]) { laterList.appendChild(node); later += 1; } else { list.appendChild(node); }
    });
    if (laterBox) laterBox.hidden = !later;
    if (laterTitle) laterTitle.textContent = (phone ? 'PC 에서 볼 것 ' : '나중에 볼 것 ') + later + '장';
    dom.setStatus(status, review.inboxStatus(data));
    if (aiLine) aiLine.textContent = '';  // AI 제안 자리 수는 기계 정보라 '승인 대기'에서 안 보인다(설계서 7.9)
    var ids = review.bulkIds(cards.filter(function (card) { return !deferred[card.id]; }));
    if (bulk) {
      bulk.hidden = phone || asTable || asQuestion || ids.length < 2;  // ③ 질문은 답으로만 닫는다
      bulk.textContent = '등급 A 모두 승인 (' + ids.length + '건)';
    }
    setCount(all.length);
  }

  async function load() {
    dom.setStatus(status, '불러오는 중…');
    var res = await dom.getJson(urls.inbox);
    if (!res.ok) {
      dom.setStatus(status, res.error, 'error');
      return;
    }
    loaded = true;
    data = res.data;
    render();
  }

  function propStatus(box, text, kind) {
    dom.setStatus(box.querySelector('[data-brain-prop-status]'), text, kind);
  }

  function busy(box, on) {
    box.querySelectorAll('[data-brain-act]').forEach(function (b) { b.disabled = on; });
  }

  /** 결정 하나를 보내고 결과를 그 제안 줄에 적는다. 성공이면 목록을 다시 읽는다. */
  async function send(box, url, body) {
    busy(box, true);
    propStatus(box, '보내는 중…');
    var res = await dom.postJson(url, body);
    if (!res.ok) {
      busy(box, false);
      propStatus(box, res.error, 'error');
      return;
    }
    propStatus(box, (res.data && res.data.message) || '했어요.');
    await load();
  }

  /** 표의 체크한 줄 승인 — 안 고친 줄은 한꺼번에(50개씩), 이름을 고친 줄은 하나씩 '고쳐서 승인'. */
  async function applyTable(button) {
    var tableStatus = list.querySelector('[data-brain-table-status]');
    var pick = tableKit.collect(list);
    if (!pick.ids.length && !pick.edits.length) { dom.setStatus(tableStatus, '체크한 줄이 없어요.', 'error'); return; }
    button.disabled = true;
    dom.setStatus(tableStatus, '승인하는 중…');
    var done = 0;
    var failed = 0;
    for (var i = 0; i < pick.ids.length; i += 50) {
      var part = pick.ids.slice(i, i + 50);
      var res = await dom.postJson(urls.bulk, { ids: part });
      if (!res.ok) { failed += part.length; continue; }
      done += res.data.applied.length;
      failed += (res.data.failed || []).length;
    }
    for (var j = 0; j < pick.edits.length; j += 1) {
      var view = findView(pick.edits[j].id);
      var edits = {};
      edits[tableKit.prefField] = pick.edits[j].name;
      var one = view && await dom.postJson(urls.proposals + '/' + view.id + '/apply',
                                           review.applyBody(view, { viewMs: 0, confirmed: true, edits: edits }));
      if (one && one.ok) done += 1; else failed += 1;
    }
    await load();
    dom.setStatus(status, '승인 ' + done + '건' + (failed ? ' · 못 함 ' + failed + '건(카드로 하나씩 봐 주세요)' : ''),
                  failed ? 'error' : undefined);
  }

  function viewMs(box) {
    return review.elapsed(box.getAttribute('data-shown-at'), window.performance.now());
  }

  function confirmed(box) {
    var input = box.querySelector('[data-brain-confirm]');
    return !!(input && input.checked);
  }

  function readEdits(box, prop) {
    var values = {};
    box.querySelectorAll('[data-brain-edit]').forEach(function (input) {
      values[input.getAttribute('data-brain-edit')] = input.value;
    });
    return review.editsFrom(prop, values);
  }

  function apply(box, prop, edits) {
    if (prop.confirm && !confirmed(box)) {
      propStatus(box, '등급 B 제안이에요 — 핵심 값을 보고 확인 칸을 눌러 주세요.', 'error');
      return;
    }
    var body = review.applyBody(prop, { viewMs: viewMs(box), confirmed: confirmed(box), edits: edits });
    send(box, urls.proposals + '/' + prop.id + '/apply', body);
  }

  function toggleEdit(box, open) {
    var editor = box.querySelector('[data-brain-edit-box]');
    var save = box.querySelector('[data-brain-act="edit-apply"]');
    var start = box.querySelector('[data-brain-act="edit"]');
    if (editor) editor.hidden = !open;
    if (save) save.hidden = !open;
    if (start) start.hidden = open;
    if (open && editor) {
      var first = editor.querySelector('[data-brain-edit]');
      if (first) first.focus();
    }
  }

  function onAct(button) {
    var box = button.closest('[data-change-id]');
    var prop = box && findView(box.getAttribute('data-change-id'));
    if (!prop) return;
    var act = button.getAttribute('data-brain-act');
    if (act === 'apply') apply(box, prop, null);
    else if (act === 'edit') toggleEdit(box, true);
    else if (act === 'edit-apply') {
      var edits = readEdits(box, prop);
      if (!edits) { propStatus(box, '고친 값이 처음 제안과 같아요 — 그대로면 승인을 눌러 주세요.', 'error'); return; }
      apply(box, prop, edits);
    } else if (act === 'reject') {
      var chips = box.querySelector('[data-brain-reject-box]');
      if (chips) chips.hidden = !chips.hidden;
    } else if (act === 'reject-code') {
      send(box, urls.proposals + '/' + prop.id + '/reject',
           { code: button.getAttribute('data-reject-code'), view_ms: viewMs(box) });
    } else if (act === 'later') {
      var card = button.closest('[data-card-id]');
      if (card) deferred[card.getAttribute('data-card-id')] = true;
      render();
    }
  }

  root.addEventListener('click', function (event) {
    var answer = event.target.closest('[data-brain-answer]');
    if (answer && root.contains(answer) && questionKit) {
      questionKit.answer(answer, { urls: urls, findView: findView, reload: load,
                                   done: function (text) { dom.setStatus(status, text); } });
      return;
    }
    var tableApply = event.target.closest('[data-brain-table-apply]');
    if (tableApply && root.contains(tableApply)) {
      applyTable(tableApply);
      return;
    }
    var binButton = event.target.closest('[data-brain-bin-open], [data-brain-bin-back]');
    if (binButton && root.contains(binButton)) {
      openBin = binButton.getAttribute('data-brain-bin-open') || '';
      render();
      return;
    }
    var button = event.target.closest('[data-brain-act]');
    if (!button || !root.contains(button) || !button.closest('#brain-tab-inbox')) return;
    onAct(button);
  });

  if (bulk) {
    bulk.addEventListener('click', async function () {
      var shown = openBin ? bins.inBin((data && data.cards) || [], openBin) : [];
      var ids = review.bulkIds(shown.filter(function (card) { return !deferred[card.id]; }));
      if (!ids.length || !window.confirm('등급 A 제안 ' + ids.length + '건을 한꺼번에 승인할까요?')) return;
      bulk.disabled = true;
      var res = await dom.postJson(urls.bulk, { ids: ids });
      bulk.disabled = false;
      if (!res.ok) {
        dom.setStatus(status, res.error, 'error');
        return;
      }
      await load();
      var failed = (res.data.failed || []).length;
      dom.setStatus(status, '승인 ' + res.data.applied.length + '건' + (failed ? ' · 못 함 ' + failed + '건(새로 보고 하나씩)' : ''));
    });
  }

  phoneQuery.addEventListener('change', function () { if (loaded) render(); });
  root.addEventListener('brain:tab', function (event) {
    if (event.detail.tab === 'inbox' && !loaded) load();
  });
})();
