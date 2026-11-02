/**
 * 회사 지식 '판' 탭(HAUD master brain 설계서 7.5 화면 6) — 판 목록 · 층별 동작 수 · 차이 요약. GET /api/brain/releases ·
 * /api/brain/releases/<번호>(수 · 차이는 내 보기 범위 안의 바뀜만). **되돌리기는 다음 단계(⑤-3)** — 단추는 꺼진 자리만 둔다.
 * 글은 textContent 만, 탭이 처음 보일 때 읽는다.
 */
(function () {
  'use strict';

  var ctx = window.FOMS_BRAIN_CTX;
  if (!ctx || window.__FOMS_BRAIN_RELEASES_BOUND) return;
  window.__FOMS_BRAIN_RELEASES_BOUND = true;

  var dom = window.FOMS_BRAIN_DOM;
  var view = window.FOMS_BRAIN_VIEW;
  var root = ctx.root;
  var list = root.querySelector('[data-brain-releases]');
  var status = root.querySelector('[data-brain-releases-status]');
  var prev = root.querySelector('[data-brain-releases-prev]');
  var next = root.querySelector('[data-brain-releases-next]');
  var pageText = root.querySelector('[data-brain-releases-text]');
  if (!list) return;

  var page = 1;
  var loaded = false;

  function layerLabel(layer) {
    return (ctx.display.layers || {})[layer] || layer || '층 없음';
  }

  function releaseTitle(item) {
    var title = '판 ' + item.number + (item.day ? ' · ' + item.day : '');
    return item.import ? title + ' · 지식 문서에서 옮겨 옴' : title;
  }

  /** 바뀜 한 줄 글 — '고침 · 이름(키)' 또는 '링크 더함 · 적용: 시작 → 끝'. */
  function changeText(change) {
    var op = (ctx.display.ops || {})[change.op] || change.op;
    if (change.link_kind) {
      var kind = view.linkInfo(ctx.display, change.link_kind).label;
      return op + ' · ' + kind + ': ' + (change.name || change.key) + ' → ' + (change.link_to_name || change.link_to);
    }
    return op + ' · ' + (change.name || change.key) + ' (' + change.key + ')';
  }

  function renderDiff(box, data) {
    dom.clear(box);
    data.layers.forEach(function (layer) {
      box.appendChild(dom.el('strong', { text: layerLabel(layer.layer) + ' — ' + layer.total + '건' }));
      var ul = dom.el('ul');
      layer.changes.forEach(function (change) { ul.appendChild(dom.el('li', { text: changeText(change) })); });
      if (layer.more) ul.appendChild(dom.el('li', { cls: 'brain-empty', text: '그 밖 ' + layer.more + '건' }));
      box.appendChild(ul);
    });
  }

  async function toggleDiff(button, box, number) {
    if (!box.hidden) {
      box.hidden = true;
      button.setAttribute('aria-expanded', 'false');
      return;
    }
    box.hidden = false;
    button.setAttribute('aria-expanded', 'true');
    if (box.getAttribute('data-loaded') === '1') return;
    box.textContent = '불러오는 중…';
    var res = await dom.getJson(ctx.urls.releases + '/' + encodeURIComponent(number));
    if (!res.ok) {
      box.textContent = res.error;
      return;
    }
    box.setAttribute('data-loaded', '1');
    renderDiff(box, res.data);
  }

  function renderRelease(item) {
    var li = dom.el('li', { cls: 'brain-release' });
    var head = dom.el('div', { cls: 'brain-release__head' });
    head.appendChild(dom.el('h3', { cls: 'brain-release__title', text: releaseTitle(item) }));
    var boxId = 'brain-release-diff-' + item.number;
    var diffButton = dom.el('button', { cls: 'brain-btn', text: '차이 보기',
                                        attrs: { type: 'button', 'aria-expanded': 'false', 'aria-controls': boxId } });
    head.appendChild(diffButton);
    li.appendChild(head);
    var layers = dom.el('ul', { cls: 'brain-release__layers' });
    item.layers.forEach(function (layer) {
      var row = dom.el('li', { cls: 'brain-release__layer' });
      row.appendChild(dom.el('span', { cls: 'brain-badge', text: layerLabel(layer.layer) }));
      row.appendChild(dom.el('span', { text: view.countsText(layer.counts, ctx.display) + ' (모두 ' + layer.total + '건)' }));
      row.appendChild(dom.el('button', { cls: 'brain-btn', text: '이 층 되돌리기 · 다음 단계',
                                         attrs: { type: 'button', disabled: 'disabled', 'aria-disabled': 'true',
                                                  title: '판 되돌리기는 다음 단계(⑤-3)에서 열립니다' } }));
      layers.appendChild(row);
    });
    li.appendChild(layers);
    var box = dom.el('div', { cls: 'brain-release__diff', attrs: { id: boxId } });
    box.hidden = true;
    li.appendChild(box);
    diffButton.addEventListener('click', function () { toggleDiff(diffButton, box, item.number); });
    return li;
  }

  async function load() {
    dom.setStatus(status, '불러오는 중…');
    var res = await dom.getJson(ctx.urls.releases + '?page=' + page);
    if (!res.ok) {
      dom.setStatus(status, res.error, 'error');
      return;
    }
    loaded = true;
    var data = res.data;
    page = data.page;
    dom.clear(list);
    data.items.forEach(function (item) { list.appendChild(renderRelease(item)); });
    dom.setStatus(status, data.total ? ('판 ' + data.total + '개(내 보기 범위 안의 바뀜이 있는 판)') : '아직 판이 없습니다.');
    var info = view.pager(data.page, data.pages, data.total, data.per_page);
    if (pageText) pageText.textContent = data.total ? (data.page + '/' + data.pages + '쪽') : '';
    if (prev) prev.disabled = !info.hasPrev;
    if (next) next.disabled = !info.hasNext;
  }

  if (prev) prev.addEventListener('click', function () { page = Math.max(1, page - 1); load(); });
  if (next) next.addEventListener('click', function () { page += 1; load(); });
  root.addEventListener('brain:tab', function (event) {
    if (event.detail.tab === 'releases' && !loaded) load();
  });
})();
