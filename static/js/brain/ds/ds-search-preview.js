/**
 * 새 찾기 · 지식 표 오른쪽 미리 보기(판 ⑦) — templates/brain/ds/partials/search_aside.html 의 [data-ds-search-aside].
 *
 * - show(index): 지금 목록의 그 줄을 GET /api/brain/items/<키>(보기 범위 · 효력은 서버가 건다)로 읽어 요약(유형 · 쓰는 팀 · 이름 ·
 *   상태 · 승인을 기다리는 수정 · 낡음) · 글 · 값(눈에 띄는 칸 · 브랜드 · 확실한 정도 · 위험 등급 · 마지막 확인 · 다시 볼 날) ·
 *   연결된 지식 종류별 수 · [카드 열기] · [고칠 말 제안](카드의 #brain-card-propose)을 그린다.
 * - '쓰인 곳 · 지난 2주'(설계서 3.8): 화면에 data-usage 가 있을 때만(접목판 erp_read 스위치 — 서버가 정한다)
 *   GET /api/brain/items/<키>/usage 를 같이 읽어 읽은 쪽마다 수 · 이어진 ERP 물건을 그린다. 없으면 그 칸이 없다.
 * - 앞 · 다음 줄 단추로 목록 안에서 옮기고 onPick(index) 로 표에 알린다. 늦게 온 답은 버린다(차례 번호).
 * 요청은 brain-dom.js getJson 한 곳, 글은 textContent 만. window.FOMS_DS_SEARCH_PREVIEW 로 내놓는다.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var sv = window.FOMS_DS_SEARCH_VIEW;
  var rows = window.FOMS_DS_SEARCH_ROWS;
  var view = window.FOMS_BRAIN_VIEW;
  var aside = document.querySelector('[data-ds-search-aside]');
  if (!dom || !sv || !rows || !view || !aside || window.FOMS_DS_SEARCH_PREVIEW) return;

  var body = aside.querySelector('[data-ds-preview]');
  var pos = aside.querySelector('[data-ds-preview-pos]');
  var prev = aside.querySelector('[data-ds-preview-step="-1"]');
  var next = aside.querySelector('[data-ds-preview-step="1"]');
  var state = { ctx: null, keys: [], index: -1, seq: 0, onPick: null };

  function kv(list, term, value) {
    list.appendChild(dom.el('dt', { text: term }));
    var dd = dom.el('dd');
    if (typeof value === 'string') dd.textContent = value;
    else dd.appendChild(value);
    list.appendChild(dd);
  }

  function head(card) {
    var it = card.item;
    var ctx = state.ctx;
    var box = dom.el('div', { cls: 'f-col f-gap4' });
    var info = (ctx.display.types || {})[it.type];
    box.appendChild(rows.typeMark((ctx.icons || {})[it.type] || 'circle',
                                  (info ? info.label : it.type) + ' · ' + sv.label(ctx.display, 'layers', it.layer)));
    box.appendChild(dom.el('h2', { cls: 'f-h5', text: (card.labels && card.labels.pref) || it.name }));
    var tags = dom.el('div', { cls: 'f-row f-gap4' });
    tags.appendChild(rows.tag(sv.label(ctx.display, 'statuses', it.status), sv.STATUS_TONES[it.status] || ''));
    if (it.open_changes) tags.appendChild(rows.tag('승인을 기다리는 수정 ' + it.open_changes + '개', 'f-tag-minimal f-tag-warning'));
    if (it.stale) tags.appendChild(rows.tag('낡음', 'f-tag-minimal f-tag-warning'));
    box.appendChild(tags);
    return box;
  }

  function values(card) {
    var it = card.item;
    var d = state.ctx.display;
    var list = dom.el('dl', { cls: 'f-kv' });
    sv.keyFields(card.key_fields).forEach(function (f) { kv(list, f.label, f.shown || '—'); });
    kv(list, '브랜드', sv.label(d, 'brands', it.brand));
    var m = sv.rowModel(it, d, state.ctx.icons);
    var conf = dom.el('span', { cls: 'f-row-nw f-gap4' });
    conf.appendChild(rows.icon(m.confIcon, m.confCls));
    conf.appendChild(document.createTextNode(m.conf));
    kv(list, '확실한 정도', conf);
    kv(list, '위험 등급', it.risk_grade ? rows.tag(sv.label(d, 'grades', it.risk_grade), sv.GRADE_TONES[it.risk_grade] || '') : '—');
    kv(list, '마지막 확인', it.checked_at || '없음');
    kv(list, '다시 볼 날', it.stale_after || '—');
    return list;
  }

  function usageBox(usage) {
    var box = dom.el('div', { cls: 'f-card f-card-compact f-col', attrs: { 'data-ds-preview-usage': '' } });
    var top = dom.el('div', { cls: 'f-row' });
    top.appendChild(dom.el('span', { cls: 'f-h6', text: '쓰인 곳 · 지난 ' + (usage.days === 14 ? '2주' : usage.days + '일') }));
    top.appendChild(rows.tag('새로 붙음', 'f-tag-minimal f-tag-primary f-push'));
    box.appendChild(top);
    var nums = dom.el('div', { cls: 'fb-usage-nums' });
    sv.usageBars(usage.by_reader).forEach(function (bar) {
      var col = dom.el('div', { cls: 'f-col f-gap4' });
      col.appendChild(dom.el('span', { cls: 'f-small f-muted', text: bar.label }));
      col.appendChild(dom.el('span', { cls: 'f-h4 f-num', text: sv.num(bar.n) }));
      nums.appendChild(col);
    });
    box.appendChild(nums);
    if ((usage.erp_links || []).length) {
      box.appendChild(dom.el('span', { cls: 'f-small f-muted', text: '이어진 ERP 물건' }));
      var chips = dom.el('div', { cls: 'f-row f-gap4' });
      usage.erp_links.forEach(function (link) {
        var c = sv.erpChip(link);
        var chip = dom.el('span', { cls: 'f-chip', attrs: { title: c.note || null } });
        chip.appendChild(rows.icon(c.icon));
        chip.appendChild(document.createTextNode(c.text));
        chips.appendChild(chip);
      });
      box.appendChild(chips);
    }
    return box;
  }

  function links(card) {
    var sum = sv.linkSummary(card.links, state.ctx.display);
    var box = dom.el('div', { cls: 'f-col f-gap4' });
    box.appendChild(dom.el('span', { cls: 'f-h6', text: '연결된 지식 ' + sv.num(sum.total) }));
    var list = dom.el('ul', { cls: 'f-col f-gap4 f-small' });
    sum.rows.forEach(function (r) {
      var li = dom.el('li', { cls: 'f-row-nw f-between' });
      li.appendChild(dom.el('span', { text: r.label }));
      li.appendChild(dom.el('span', { cls: 'f-num f-muted', text: sv.num(r.n) }));
      list.appendChild(li);
    });
    if (!sum.rows.length) list.appendChild(dom.el('li', { cls: 'f-muted', text: '연결 없음' }));
    box.appendChild(list);
    return box;
  }

  function buttons(key) {
    var href = view.itemHref(state.ctx.itemBase, key);
    var row = dom.el('div', { cls: 'f-row' });
    var open = dom.el('a', { cls: 'f-btn f-btn-primary', attrs: { href: href } });
    open.appendChild(rows.icon('share'));
    open.appendChild(document.createTextNode('카드 열기'));
    var fix = dom.el('a', { cls: 'f-btn', attrs: { href: href + '#brain-card-propose' } });
    fix.appendChild(rows.icon('edit'));
    fix.appendChild(document.createTextNode('고칠 말 제안'));
    row.appendChild(open);
    row.appendChild(fix);
    return row;
  }

  function render(card, usage) {
    dom.clear(body);
    body.appendChild(head(card));
    if (card.item.text) body.appendChild(dom.el('div', { cls: 'f-quote fb-quote', text: card.item.text }));
    body.appendChild(values(card));
    if (usage) body.appendChild(usageBox(usage));
    body.appendChild(links(card));
    body.appendChild(buttons(card.item.key));
  }

  function paintPos() {
    pos.textContent = sv.previewPos(state.index, state.keys.length);
    prev.disabled = sv.stepIndex(state.index, -1, state.keys.length) < 0;
    next.disabled = sv.stepIndex(state.index, 1, state.keys.length) < 0;
  }

  async function show(index) {
    var key = state.keys[index];
    if (key === undefined) return;
    state.index = index;
    paintPos();
    var mine = ++state.seq;
    dom.clear(body);
    body.appendChild(dom.el('p', { cls: 'f-small f-muted', text: '불러오는 중…' }));
    var path = state.ctx.itemApi + view.itemHref('', key);
    var wants = [dom.getJson(path)];
    if (state.ctx.usage) wants.push(dom.getJson(path + '/usage'));
    var got = await Promise.all(wants);
    if (mine !== state.seq) return;  // 더 늦은 고름이 이미 나갔다
    if (!got[0].ok) {
      dom.clear(body);
      body.appendChild(dom.el('p', { cls: 'fb-status is-error', text: got[0].error }));
      return;
    }
    render(got[0].data, got[1] && got[1].ok && got[1].data && got[1].data.by_reader ? got[1].data : null);
  }

  /** 목록이 바뀌면 — 미리 보기를 비우고 자리 글을 새로. */
  function setRows(keys) {
    state.keys = (keys || []).slice();
    state.index = -1;
    state.seq += 1;
    dom.clear(body);
    body.appendChild(dom.el('div', { cls: 'f-empty', children: [rows.icon('eye-open', 'f-i-20'),
      dom.el('p', { text: state.keys.length ? '줄을 누르면 여기에 보여요.' : '보일 지식이 없어요.' })] }));
    paintPos();
  }

  aside.addEventListener('click', function (event) {
    var step = event.target.closest('[data-ds-preview-step]');
    if (!step || step.disabled) return;
    var to = sv.stepIndex(state.index, Number(step.getAttribute('data-ds-preview-step')), state.keys.length);
    if (to < 0) return;
    show(to);
    if (state.onPick) state.onPick(to);
  });

  window.FOMS_DS_SEARCH_PREVIEW = {
    init: function (ctx, onPick) { state.ctx = ctx; state.onPick = onPick; },
    setRows: setRows, show: show
  };
})();
