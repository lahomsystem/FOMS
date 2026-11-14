/**
 * 새 승인 대기 화면의 '다시 확인' 보기(?tab=recheck — 설계서 2026-11-14-foms-graft 5.4 · 옛 brain-recheck.js 와 같은 흐름 · D103).
 * GET /api/brain/recheck(확인 날이 지났거나 다가오는 지식 · 쓰인 횟수 순 · 내가 결정할 수 있고 볼 수 있는 것만),
 * '아직 맞음' 한 번 = POST /api/brain/recheck/confirm(서버가 확인 날만 바꾸는 제안을 만들어 반영 동작으로 넣는다).
 * 열린 제안이 있는 지식은 승인 대기로 보낸다. 값이 틀리면 지식 카드의 '고칠 말 제안'으로. 폰 폭에서 그대로 쓴다.
 * 글은 textContent 만 · 인라인 스타일 없음 · 전역 듣개는 한 번만(window.__FOMS_DS_RECHECK_BOUND).
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var view = window.FOMS_BRAIN_VIEW;
  var review = window.FOMS_BRAIN_REVIEW;
  var iv = window.FOMS_DS_INBOX_VIEW;
  var kit = window.FOMS_DS_INBOX_KIT;
  if (!dom || !view || !review || !iv || !kit || window.__FOMS_DS_RECHECK_BOUND) return;
  var c = kit.ctx();
  var list = c && c.root.querySelector('[data-ds-recheck]');
  if (!list || !c.urls.recheck) return;
  window.__FOMS_DS_RECHECK_BOUND = true;

  var line = c.root.querySelector('[data-ds-recheck-line]');
  var status = c.root.querySelector('[data-ds-recheck-status]');
  var items = {};

  function renderRow(item) {
    var li = dom.el('li', { cls: 'f-card f-card-compact f-col fb-recheck' + (item.overdue ? ' is-late' : ''),
                            attrs: { 'data-recheck-key': item.key, 'data-shown-at': Math.round(window.performance.now()) } });
    var href = view.itemHref(c.urls.itemBase, item.key);
    li.appendChild(dom.el('div', { cls: 'f-row f-gap4', children: [kit.typeTag(c, item, null),
      dom.el('a', { cls: 'f-strong', text: item.name, attrs: { href: href } })] }));
    var when = review.recheckWhen(item) + ' · 마지막 확인 ' + (item.checked_at || '없음') + ' · ' + item.usage_count + '번 쓰임';
    li.appendChild(dom.el('p', { cls: 'f-small' + (item.overdue ? ' fb-late' : ' f-muted'), text: when }));
    if (item.snippet) li.appendChild(dom.el('p', { cls: 'f-small', text: item.snippet }));
    var bar = dom.el('div', { cls: 'f-actions' });
    if (item.open) {
      bar.appendChild(dom.el('a', { cls: 'f-btn', text: '기다리는 수정 먼저 보기', attrs: { href: iv.addressFor(c.urls.page, '') } }));
    } else {
      var ok = kit.button(review.actionLabel(c.actions, 'recheck'), null, 'f-btn-primary', 'tick');
      ok.setAttribute('data-recheck-ok', '1');
      bar.appendChild(ok);
    }
    bar.appendChild(dom.el('a', { cls: 'f-btn f-btn-minimal', text: '틀림 — 고치기', attrs: { href: href + '#brain-card-propose' } }));
    li.appendChild(bar);
    li.appendChild(kit.statusLine('data-recheck-status'));
    return li;
  }

  function setCount(n) {
    Array.prototype.slice.call(document.querySelectorAll('[data-ds-count="recheck"]')).forEach(function (node) {
      node.textContent = String(n);
    });
  }

  async function load() {
    dom.setStatus(status, '불러오는 중…');
    var res = await dom.getJson(c.urls.recheck);
    if (!res.ok) {
      dom.setStatus(status, res.error, 'error');
      return;
    }
    items = {};
    dom.clear(list);
    res.data.items.forEach(function (item) {
      items[item.key] = item;
      list.appendChild(renderRow(item));
    });
    if (line) line.textContent = res.data.counts.line;
    dom.setStatus(status, '');  // 빈 목록 글은 위 묶음 줄(counts.line)이 이미 말한다
    setCount(res.data.counts.total);
  }

  async function confirmRow(row) {
    var item = items[row.getAttribute('data-recheck-key')];
    var button = row.querySelector('[data-recheck-ok]');
    var rowStatus = row.querySelector('[data-recheck-status]');
    if (!item || !button) return;
    button.disabled = true;
    dom.setStatus(rowStatus, '보내는 중…');
    var res = await dom.postJson(c.urls.recheckConfirm, { key: item.key, version: item.version,
      view_ms: review.elapsed(row.getAttribute('data-shown-at'), window.performance.now()) });
    if (!res.ok) {
      button.disabled = false;
      dom.setStatus(rowStatus, res.error, 'error');
      return;
    }
    dom.setStatus(rowStatus, res.data.message);
    row.classList.add('is-done');
    window.setTimeout(load, 600);
  }

  list.addEventListener('click', function (event) {
    var button = event.target.closest('[data-recheck-ok]');
    if (!button || !list.contains(button)) return;
    confirmRow(button.closest('[data-recheck-key]'));
  });
  load();
})();
