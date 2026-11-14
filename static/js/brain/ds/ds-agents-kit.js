/**
 * AI 직원 화면 그리기 부품(판 ⑪ — 설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 3.10 · 9절) — ds-agents.js 가 쓴다.
 *
 * 왼쪽 직원 줄 · 머리 · 읽는 것 · 도구 · 할 일 표(수준 · 2주 승인율 막대 · 건수 · 메모) · 최근 실패 · 시간 · 비용 · 실행 기록을
 * 요소로 만든다. 글은 textContent 만(brain-dom.js 의 el) · 막대는 <progress>(인라인 스타일 없음) · 수준 고르기는 <select>.
 * window.FOMS_DS_AGENTS_KIT 로 내놓는다.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  if (!dom || window.FOMS_DS_AGENTS_KIT) return;
  var el = dom.el;

  /** 아이콘(장식) — cls 는 'i-chat' 처럼 'i-' 가 붙은 이름. */
  function icon(cls, extra) {
    return el('span', { cls: 'f-i ' + cls + (extra ? ' ' + extra : ''), attrs: { 'aria-hidden': 'true' } });
  }

  /** 꼬리표 — tone: primary · success · warning · danger(없으면 바탕만). */
  function tag(text, tone) {
    return el('span', { cls: 'f-tag f-tag-minimal' + (tone ? ' f-tag-' + tone : ''), text: text });
  }

  /** 밀리초 → '7.2초' · '12초'(없으면 빈 글). */
  function secs(ms) {
    if (ms === null || ms === undefined) return '';
    var s = Number(ms) / 1000;
    return (s < 10 ? s.toFixed(1) : String(Math.round(s))) + '초';
  }

  /** 왼쪽 직원 줄 하나 — 이름 · 상태 꼬리표 · 한 줄. */
  function navItem(agent, selected, href) {
    var link = el('a', { cls: 'f-nav-item fb-agents-item' + (selected ? ' is-selected' : ''),
                         attrs: { href: href, 'data-ds-agent': agent.key, 'aria-current': selected ? 'page' : null } });
    link.appendChild(icon(agent.icon, 'fb-agents-item__icon'));
    var col = el('span', { cls: 'f-col f-gap4 f-grow' });
    var row = el('span', { cls: 'f-row-nw' });
    row.appendChild(el('span', { cls: 'f-strong', text: agent.label }));
    var badge = tag(agent.tag.text, agent.tag.tone);
    badge.classList.add('f-push');
    row.appendChild(badge);
    col.appendChild(row);
    col.appendChild(el('span', { cls: 'f-small fb-agents-sub', text: agent.sub }));
    link.appendChild(col);
    return link;
  }

  /** 머리 — 이름 · 모델 이름(설정 값) · 상태 꼬리표 · 설명. */
  function head(refs, data) {
    refs.name.textContent = data.label;
    dom.clear(refs.tags);
    if (data.model) refs.tags.appendChild(tag(data.model, ''));
    refs.tags.appendChild(tag(data.status.text, data.status.tone));
    refs.about.textContent = data.about;
  }

  /** 읽는 것 줄 · 도구 표. */
  function reads(list, tbody, data) {
    dom.clear(list);
    data.reads.forEach(function (item) {
      var li = el('li', { cls: 'f-row-nw fb-agents-read' });
      li.appendChild(icon('i-' + item.icon, 'f-i-primary'));
      li.appendChild(el('span', { cls: 'f-col f-gap4', children: [
        el('span', { cls: 'f-strong', text: item.label }), el('span', { cls: 'f-small f-muted', text: item.help })] }));
      list.appendChild(li);
    });
    dom.clear(tbody);
    data.tools.forEach(function (tool) {
      var tr = el('tr');
      tr.appendChild(el('td', { cls: 'f-td-nw f-mono', text: tool.name }));
      tr.appendChild(el('td', { children: [el('span', { cls: 'f-small', text: tool.what })] }));
      tr.appendChild(el('td', { cls: 'f-td-nw', children: [tool.new ? tag('새로', 'primary') : null] }));
      tbody.appendChild(tr);
    });
  }

  /** 수준 칸 — ADMIN 이고 바꿀 수 있으면 고르기, 아니면 꼬리표. */
  function levelCell(row) {
    if (!row.editable || !row.choices.length) return tag(row.level_label, row.tone);
    var select = el('select', { cls: 'f-select fb-agents-level',
                                attrs: { 'aria-label': '수준 — ' + row.label, 'data-ds-agents-level': row.key } });
    row.choices.forEach(function (choice) {
      var option = el('option', { text: choice.label, attrs: { value: String(choice.value) } });
      option.selected = choice.value === row.level;
      select.appendChild(option);
    });
    return select;
  }

  /** 2주 승인율 칸 — 결정이 있으면 막대(<progress>) + 비율, 없으면 '—'. */
  function rateCell(rate) {
    var wrap = el('div', { cls: 'f-row-nw' });
    if (!rate || rate.pct === null || rate.pct === undefined) {
      wrap.appendChild(el('span', { cls: 'f-small f-muted', text: '—' }));
      return wrap;
    }
    var bar = el('progress', { cls: 'fb-agents-progress ' + (rate.pct >= 70 ? 'is-success' : 'is-warning'),
                               attrs: { max: '100', value: String(rate.pct), 'aria-label': '2주 승인율' } });
    wrap.appendChild(bar);
    wrap.appendChild(el('span', { cls: 'f-small f-num f-muted', text: rate.pct + '% (' + rate.approved + '/' + rate.decided + ')' }));
    return wrap;
  }

  /** 할 일 표 — 줄마다 이름 · 수준 · 2주 승인율 · 건수 · 메모. */
  function duties(tbody, rows) {
    dom.clear(tbody);
    rows.forEach(function (row) {
      var tr = el('tr', { attrs: { 'data-ds-agents-duty': row.key } });
      tr.appendChild(el('td', { cls: 'f-td-nw', children: [el('span', { cls: 'f-strong', text: row.label })] }));
      tr.appendChild(el('td', { cls: 'f-td-nw', children: [levelCell(row)] }));
      tr.appendChild(el('td', { cls: 'f-td-nw', children: [rateCell(row.rate)] }));
      tr.appendChild(el('td', { cls: 'f-td-num', text: row.count === null || row.count === undefined ? '—' : row.count }));
      tr.appendChild(el('td', { children: [el('span', { cls: 'f-small f-muted', text: row.note || '' })] }));
      tbody.appendChild(tr);
    });
  }

  /** 최근 실패 — 없으면 한 줄 안내. */
  function failures(list, items) {
    dom.clear(list);
    if (!items.length) {
      list.appendChild(el('li', { cls: 'f-small f-muted', text: '지난 2주 실패가 없어요.' }));
      return;
    }
    items.forEach(function (item) {
      var li = el('li', { cls: 'f-row-nw' });
      li.appendChild(icon('i-cross', 'f-i-danger'));
      li.appendChild(el(item.href ? 'a' : 'span', { text: item.label, attrs: { href: item.href || null } }));
      var tail = [item.code, item.at].filter(Boolean).join(' · ');
      if (tail) li.appendChild(el('span', { cls: 'f-small f-muted', text: tail }));
      list.appendChild(li);
    });
  }

  /** 시간 · 수 · (ADMIN 만) 비용 한 줄. */
  function usage(box, data) {
    dom.clear(box);
    var parts = [];
    if (Object.prototype.hasOwnProperty.call(data, 'cost')) {
      parts.push(['i-dollar', '지난 ' + data.cost_days + '일 비용 ' + (data.cost || '—')]);
    }
    if (data.avg_ms !== null && data.avg_ms !== undefined) parts.push(['i-time', '평균 ' + secs(data.avg_ms)]);
    if (data.count !== null && data.count !== undefined) {
      parts.push(['', '지난 ' + data.days + '일 ' + data.unit + ' ' + data.count + (data.unit === '실행' ? '번' : '개')]);
    }
    if (!parts.length) parts.push(['i-time', '아직 기록이 없어요.']);
    parts.forEach(function (part, index) {
      if (index) box.appendChild(el('span', { text: '·', attrs: { 'aria-hidden': 'true' } }));
      if (part[0]) box.appendChild(icon(part[0]));
      box.appendChild(el('span', { text: part[1] }));
    });
  }

  /** 실행 기록 하나 — 단계 · 모두 걸린 시간 · 만든 제안 수. 상담 AI 는 단계 시간이 없다(per_step 거짓). */
  function trace(refs, run, foot) {
    dom.clear(refs.list);
    refs.foot.textContent = foot || '';
    refs.title.textContent = run && run.at ? '실행 기록 · ' + run.at : '실행 기록';
    if (!run) {
      refs.list.appendChild(el('li', { cls: 'f-small f-muted', text: '아직 실행 기록이 없어요.' }));
      refs.sum.hidden = true;
      return;
    }
    run.steps.forEach(function (step) {
      var li = el('li', { cls: 'fb-agents-step' });
      li.appendChild(icon('i-small-tick', 'f-i-success'));
      li.appendChild(el('div', { cls: 'f-col f-gap4', children: [
        el('span', { cls: 'f-strong', text: step.what }), el('span', { cls: 'f-mono f-muted', text: step.tool }),
        step.detail ? el('span', { cls: 'f-small f-muted', text: step.detail }) : null] }));
      li.appendChild(el('span', { cls: 'f-small f-muted f-num', text: run.per_step ? secs(step.ms) : '' }));
      refs.list.appendChild(li);
    });
    var total = run.total_ms === null || run.total_ms === undefined ? '' : '모두 ' + secs(run.total_ms) + ' · ';
    refs.text.textContent = total + run.outcome + ' · 할 일 제안 ' + run.proposals + '개' +
      (run.per_step ? '' : ' · 단계마다 시간은 없어요(전체 시간만)');
    refs.sum.hidden = false;
  }

  window.FOMS_DS_AGENTS_KIT = { navItem: navItem, head: head, reads: reads, duties: duties, failures: failures,
                                usage: usage, trace: trace, secs: secs };
})();
