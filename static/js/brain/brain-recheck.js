/**
 * 회사 지식 '다시 확인' 탭(HAUD master brain 설계서 7.5 화면 5 · 사장님 D103) — GET /api/brain/recheck(낡음 날이 지났거나
 * 다가오는 항목 · 쓰인 횟수 순 · 내가 결정할 수 있고 볼 수 있는 것만), '아직 맞음' 한 번 = POST /api/brain/recheck/confirm.
 * 서버가 확인 날만 바꾸는 제안을 만들어 반영 동작으로 넣는다. 열린 제안이 있는 항목은 제안함으로 보낸다. 예외(값이 틀림)는
 * 항목 카드의 '고칠 말 제안'으로. 휴대폰 폭에서 그대로 쓰도록 줄마다 큰 단추 하나. 글은 textContent 만.
 */
(function () {
  'use strict';

  var ctx = window.FOMS_BRAIN_CTX;
  if (!ctx || window.__FOMS_BRAIN_RECHECK_BOUND) return;
  window.__FOMS_BRAIN_RECHECK_BOUND = true;

  var dom = window.FOMS_BRAIN_DOM;
  var view = window.FOMS_BRAIN_VIEW;
  var review = window.FOMS_BRAIN_REVIEW;
  var root = ctx.root;
  var list = root.querySelector('[data-brain-recheck]');
  var line = root.querySelector('[data-brain-recheck-line]');
  var status = root.querySelector('[data-brain-recheck-status]');
  if (!list || !review) return;

  var urls = { list: root.getAttribute('data-recheck-url'), confirm: root.getAttribute('data-recheck-confirm-url') };
  var loaded = false;
  var items = {};

  function setCount(n) {
    var badge = root.querySelector('[data-brain-count="recheck"]');
    if (!badge) return;
    badge.textContent = String(n);
    badge.classList.toggle('is-zero', !n);
  }

  function renderRow(item) {
    var li = dom.el('li', { cls: 'brain-recheck__row brain-type--' + item.type + (item.overdue ? ' brain-state--stale' : ''),
                            attrs: { 'data-recheck-key': item.key, 'data-shown-at': Math.round(window.performance.now()) } });
    var head = dom.el('div', { cls: 'brain-recheck__head' });
    head.appendChild(dom.typeChip(ctx.display, item.type));
    head.appendChild(dom.el('a', { cls: 'brain-item__name', text: item.name, attrs: { href: view.itemHref(ctx.itemBase, item.key) } }));
    li.appendChild(head);
    li.appendChild(dom.el('p', { cls: 'brain-recheck__when' + (item.overdue ? ' is-late' : ''),
                                 text: review.recheckWhen(item) + ' · 마지막 확인 ' + (item.checked_at || '없음') +
                                       ' · ' + item.usage_count + '번 쓰임' }));
    if (item.snippet) li.appendChild(dom.el('p', { cls: 'brain-item__snippet', text: item.snippet }));
    var bar = dom.el('div', { cls: 'brain-recheck__actions' });
    if (item.open) {
      bar.appendChild(dom.el('a', { cls: 'brain-btn', text: '기다리는 수정 먼저 보기',
                                    attrs: { href: ctx.urls.page + '?tab=inbox' } }));
    } else {
      bar.appendChild(dom.el('button', { cls: 'brain-btn brain-btn--primary brain-recheck__ok',
                                         text: review.actionLabel(ctx.actions, 'recheck'),
                                         attrs: { type: 'button', 'data-recheck-ok': '1' } }));
    }
    bar.appendChild(dom.el('a', { cls: 'brain-btn', text: '틀림 — 고치기',
                                  attrs: { href: view.itemHref(ctx.itemBase, item.key) + '#brain-card-propose' } }));
    li.appendChild(bar);
    li.appendChild(dom.el('p', { cls: 'brain-status-line', attrs: { 'data-recheck-status': '1', role: 'status', 'aria-live': 'polite' } }));
    return li;
  }

  async function load() {
    dom.setStatus(status, '불러오는 중…');
    var res = await dom.getJson(urls.list);
    if (!res.ok) {
      dom.setStatus(status, res.error, 'error');
      return;
    }
    loaded = true;
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
    var res = await dom.postJson(urls.confirm, { key: item.key, version: item.version,
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
  root.addEventListener('brain:tab', function (event) {
    if (event.detail.tab === 'recheck' && !loaded) load();
  });
})();
