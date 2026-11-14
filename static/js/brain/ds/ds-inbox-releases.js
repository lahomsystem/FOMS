/**
 * 새 승인 대기 화면의 '판 · 기록' 보기(?tab=releases — 설계서 2026-11-14-foms-graft 5.4 · 옛 brain-releases.js 와 같은 흐름).
 * 판 목록 · 층별 동작 수 · 차이 요약: GET /api/brain/releases · /api/brain/releases/<번호>(내 보기 범위 안의 바뀜만).
 * 층 되돌리기는 ADMIN 만(data-is-admin) — 한 번 누르면 확인 줄(무엇이 되돌아가는지 한 줄)이 열리고 '판 N 층 되돌리기'를 한 번
 * 더 눌러야 POST /api/brain/releases/<번호>/rollback {layer, confirm_number} 를 보낸다(같은 판 번호를 다시 보내 확인 — 서버가
 * 다시 본다). 되돌린 층은 '되돌림 — 판 N 에서' 로 남는다. 글은 textContent 만 · 전역 듣개는 한 번만.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var view = window.FOMS_BRAIN_VIEW;
  var review = window.FOMS_BRAIN_REVIEW;
  var kit = window.FOMS_DS_INBOX_KIT;
  if (!dom || !view || !review || !kit || window.__FOMS_DS_RELEASES_BOUND) return;
  var c = kit.ctx();
  var list = c && c.root.querySelector('[data-ds-releases]');
  if (!list || !c.urls.releases) return;
  window.__FOMS_DS_RELEASES_BOUND = true;

  var status = c.root.querySelector('[data-ds-releases-status]');
  var prev = c.root.querySelector('[data-ds-releases-prev]');
  var next = c.root.querySelector('[data-ds-releases-next]');
  var pageText = c.root.querySelector('[data-ds-releases-text]');
  var page = 1;
  var ROLLBACK_NOTE = '이 판에서 새로 만든 지식은 지워지고, 고친 · 은퇴한 · 지운 지식과 연결은 이 판 전으로 돌아가요. 기록은 남아요.';

  function layerLabel(layer) {
    return (c.display.layers || {})[layer] || layer || '층 없음';
  }

  function releaseTitle(item) {
    var title = '판 ' + item.number + (item.day ? ' · ' + item.day : '');
    return item.import ? title + ' · 문서에서 옮겨 옴' : title;
  }

  /** 바뀜 한 줄 — '고침 · 이름' 또는 '링크 더함 · 적용: 시작 → 끝'(이름은 한글 이름 먼저). */
  function changeText(change) {
    var op = (c.display.ops || {})[change.op] || change.op;
    var name = change.title || change.name || change.key;
    if (change.link_kind) {
      return op + ' · ' + view.linkInfo(c.display, change.link_kind).label + ': ' + name + ' → ' +
        (change.link_to_title || change.link_to_name || change.link_to);
    }
    return op + ' · ' + name;
  }

  function renderDiff(box, data) {
    dom.clear(box);
    data.layers.forEach(function (layer) {
      box.appendChild(dom.el('span', { cls: 'f-h6', text: layerLabel(layer.layer) + ' — ' + layer.total + '건' }));
      var ul = dom.el('ul', { cls: 'f-col f-gap4 f-small' });
      layer.changes.forEach(function (change) { ul.appendChild(dom.el('li', { text: changeText(change) })); });
      if (layer.more) ul.appendChild(dom.el('li', { cls: 'f-muted', text: '그 밖 ' + layer.more + '건' }));
      box.appendChild(ul);
    });
  }

  async function toggleDiff(button, box, number) {
    box.hidden = !box.hidden;
    button.setAttribute('aria-expanded', box.hidden ? 'false' : 'true');
    if (box.hidden || box.getAttribute('data-loaded') === '1') return;
    box.textContent = '불러오는 중…';
    var res = await dom.getJson(c.urls.releases + '/' + encodeURIComponent(number));
    if (!res.ok) {
      box.textContent = res.error;
      return;
    }
    box.setAttribute('data-loaded', '1');
    renderDiff(box, res.data);
  }

  /** 층 되돌리기 — 첫 누름은 확인 줄만 연다. */
  function rollbackControl(number, layer) {
    var box = dom.el('span', { cls: 'f-row f-gap4' });
    var start = kit.button('이 층 ' + review.actionLabel(c.actions, 'release_rollback'), null, 'f-btn-small', 'undo');
    var ask = dom.el('span', { cls: 'f-row f-gap4' });
    ask.hidden = true;
    var noteId = 'ds-release-undo-' + number + '-' + layer;
    var what = dom.el('span', { cls: 'f-help', text: ROLLBACK_NOTE, attrs: { id: noteId, 'data-ds-rollback-note': '1' } });
    var yes = kit.button('판 ' + number + ' ' + layerLabel(layer) + ' 되돌리기', null, 'f-btn-small f-btn-danger');
    yes.setAttribute('aria-describedby', noteId);
    var no = kit.button('취소', null, 'f-btn-small f-btn-minimal');
    var note = kit.statusLine('data-ds-rollback-status');
    [what, yes, no].forEach(function (n) { ask.appendChild(n); });
    [start, ask, note].forEach(function (n) { box.appendChild(n); });
    start.addEventListener('click', function () { start.hidden = true; ask.hidden = false; yes.focus(); });
    no.addEventListener('click', function () { ask.hidden = true; start.hidden = false; });
    yes.addEventListener('click', async function () {
      yes.disabled = true;
      dom.setStatus(note, '되돌리는 중…');
      var res = await dom.postJson(c.urls.releases + '/' + encodeURIComponent(number) + '/rollback',
                                   { layer: layer, confirm_number: number });
      if (!res.ok) {
        yes.disabled = false;
        dom.setStatus(note, res.error, 'error');
        return;
      }
      dom.setStatus(note, res.data.message);
      load();
    });
    return box;
  }

  function layerRow(item, layer) {
    var row = dom.el('li', { cls: 'f-row f-gap4' });
    row.appendChild(dom.el('span', { cls: 'f-tag f-tag-minimal', text: layerLabel(layer.layer) }));
    row.appendChild(dom.el('span', { cls: 'f-small', text: view.countsText(layer.counts, c.display) }));
    if (layer.rollback) {
      row.appendChild(dom.el('span', { cls: 'f-tag f-tag-minimal f-tag-warning', text: review.rollbackText(layer.rollback) }));
    } else if (c.isAdmin && !item.import) {
      row.appendChild(rollbackControl(item.number, layer.layer));
    }
    return row;
  }

  function renderRelease(item) {
    var li = dom.el('li', { cls: 'f-card f-card-compact f-col fb-release' });
    var boxId = 'ds-release-diff-' + item.number;
    var diffButton = kit.button('바뀐 것 보기', null, 'f-btn-small f-push');
    diffButton.setAttribute('aria-expanded', 'false');
    diffButton.setAttribute('aria-controls', boxId);
    li.appendChild(dom.el('div', { cls: 'f-row', children: [dom.el('h2', { cls: 'f-h5', text: releaseTitle(item) }), diffButton] }));
    var layers = dom.el('ul', { cls: 'f-col f-gap4' });
    item.layers.forEach(function (layer) { layers.appendChild(layerRow(item, layer)); });
    li.appendChild(layers);
    var box = dom.el('div', { cls: 'f-col f-gap4 fb-release__diff', attrs: { id: boxId } });
    box.hidden = true;
    li.appendChild(box);
    diffButton.addEventListener('click', function () { toggleDiff(diffButton, box, item.number); });
    return li;
  }

  async function load() {
    dom.setStatus(status, '불러오는 중…');
    var res = await dom.getJson(c.urls.releases + '?page=' + page);
    if (!res.ok) {
      dom.setStatus(status, res.error, 'error');
      return;
    }
    var data = res.data;
    page = data.page;
    dom.clear(list);
    data.items.forEach(function (item) { list.appendChild(renderRelease(item)); });
    dom.setStatus(status, data.total ? ('판 ' + data.total + '개') : '아직 판이 없어요.');
    var info = view.pager(data.page, data.pages, data.total, data.per_page);
    if (pageText) pageText.textContent = data.total ? (data.page + '/' + data.pages + '쪽') : '';
    if (prev) prev.disabled = !info.hasPrev;
    if (next) next.disabled = !info.hasNext;
  }

  if (prev) prev.addEventListener('click', function () { page = Math.max(1, page - 1); load(); });
  if (next) next.addEventListener('click', function () { page += 1; load(); });
  load();
})();
