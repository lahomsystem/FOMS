/**
 * 새 온톨로지 화면(판 ⑩ — 설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 3.8 · 5.4 · 9절) 순수 계산 — DOM 을 만지지 않는다.
 *
 * - 주소의 고른 것(?kind=&id=) 읽기 · 쓰기 · 처음 고를 것(ERP 칸이 있으면 주문, 없으면 제품 라인 — 옛 화면과 같다).
 * - 왼쪽 목록 값(지식 유형 묶음 · ERP 물건 종류 · 정의 수) · 찾기 칸 거르기.
 * - 지식 종류 상세 글(수 · 표준 · 층 · 필요한 능력 질문 · 단위 · 범위 · 개수 규칙 · 상대 종류) — 옛 brain-onto-view.js 와 같은 글.
 * - ERP 물건 상세 글(정본 자리 한 줄 · 가림 칸 수) · 읽기 · 쓰기 갈래 색 · 할 일 수준 색 · 승인 자리 아이콘. '지금 칸'은 API 값 그대로.
 * - 능력 질문 점수 · 켜기 전 → 지금 · 아직 못 푸는 질문(모자란 재료 · ERP 재료인가).
 * window.FOMS_DS_ONTO_VIEW · node 에서는 module.exports — tests/domains/test_brain_ds_onto.py.
 */
(function (root) {
  'use strict';

  var KINDS = ['type', 'erp', 'links', 'actions', 'erp_actions', 'cq'];
  var DATATYPES = { text: '글', int: '정수', number: '수', date: '날짜', datetime: '때', enum: '하나 고름', list: '목록' };
  var BASIS = { rule: '규칙', calculator: '계산기', order_data: '주문 자료', photo: '사진', human_judgment: '사람 판단' };
  var STAGES = { propose: '제안', decide: '결정' };
  /** 읽기 · 쓰기 갈래 → 꼬리표 색(읽기만은 옅은 회색 — 상태 배지가 아니라 갈래 표). */
  var ACCESS_TONES = { read: '', action: 'primary', link: 'primary', person: 'warning', masked: 'warning', money: 'danger' };
  var WHERE_ICONS = { '폰 승인': 'mobile-phone', 'PC 승인': 'panel-stats', 'PC · 사장님': 'shield', '주문 화면에서': 'link' };

  function text(value) {
    return value === null || value === undefined ? '' : String(value);
  }

  /** 주소 글(?kind=&id=) → {kind, id} — 모르는 갈래 · 빈 값이면 null. */
  function pickFromQuery(search) {
    var params = new URLSearchParams(text(search).replace(/^\?/, ''));
    var kind = params.get('kind') || '';
    var id = (params.get('id') || '').slice(0, 60);
    if (KINDS.indexOf(kind) < 0) return null;
    if ((kind === 'type' || kind === 'erp') && !id) return null;
    return { kind: kind, id: kind === 'type' || kind === 'erp' ? id : 'all' };
  }

  /** {kind, id} → 주소 글('tab=onto&kind=…&id=…'). */
  function pickQuery(pick) {
    var params = new URLSearchParams();
    params.set('tab', 'onto');
    params.set('kind', pick.kind);
    if (pick.kind === 'type' || pick.kind === 'erp') params.set('id', pick.id);
    return params.toString();
  }

  /** 처음 고를 것 — ERP 칸이 있으면 주문, 없으면 제품 라인(옛 화면 첫 상세). */
  function defaultPick(summary) {
    return summary && summary.erp ? { kind: 'erp', id: 'erp:order' } : { kind: 'type', id: 'product_line' };
  }

  /** 왼쪽 목록 값 — {total, groups: [{key, label, count, types: [{type, label, count}]}], erp: [..] | null, defs: [..]}. */
  function navModel(summary) {
    var s = summary || {};
    var groups = (s.groups || []).map(function (g) {
      return { key: g.key, label: text(g.label), count: (g.types || []).length,
               types: (g.types || []).map(function (t) { return { type: t.type, label: text(t.label), count: t.count }; }) };
    });
    var kinds = groups.reduce(function (n, g) { return n + g.count; }, 0);
    var erp = s.erp ? (s.erp.types || []).map(function (t) {
      return { type: t.type, label: text(t.label), sub: text(t.sub), icon: text(t.icon).replace(/^i-/, '') || 'cube' };
    }) : null;
    var cq = s.cq || { covered: 0, total: 0 };
    var defs = [{ kind: 'links', label: '연결 종류', icon: 'link', count: String((s.links || []).length) }];
    if (s.erp) defs.push({ kind: 'erp_actions', label: '할 일 종류', icon: 'flash', count: String((s.erp.actions || []).length) });
    defs.push({ kind: 'actions', label: '동작 종류', icon: 'properties', count: String((s.actions || []).length) });
    defs.push({ kind: 'cq', label: '능력 질문', icon: 'lab-test', count: cq.covered + ' / ' + cq.total });
    return { kinds: kinds, groups: groups, erp: erp, defs: defs };
  }

  /** 찾기 칸 — 줄 글에 찾을 말이 있나(빈 말이면 늘 참). */
  function matches(label, query) {
    var q = text(query).trim().toLowerCase();
    return !q || text(label).toLowerCase().indexOf(q) >= 0;
  }

  /** 지식 종류 상세 머리 아래 줄 — '3개 · 표준 schema:Product · 층 공통 · 능력 질문 4개가 필요'. */
  function typeSub(data) {
    var d = data || {};
    var parts = [(d.count || 0) + '개', '표준 ' + text(d.standard)];
    if ((d.layers || []).length) parts.push('층 ' + d.layers.join(' · '));
    parts.push('능력 질문 ' + (d.cq || []).length + '개가 필요');
    return parts.join(' · ');
  }

  function rangeText(prop) {
    var parts = [];
    if (prop.low !== null && prop.low !== undefined) parts.push(prop.low + ' 이상');
    if (prop.high !== null && prop.high !== undefined) parts.push(prop.high + ' 이하');
    return [text(prop.unit), parts.join(' · ')].filter(Boolean).join(' · ');
  }

  function requiredText(prop) {
    return prop.required === 'always' ? '꼭' : prop.required === 'active' ? '반영 때 꼭' : '';
  }

  function cardinalityText(link) {
    if (link.direction === 'in') return '';
    var max = link.max === null || link.max === undefined ? '여럿' : link.max;
    return link.min + ' ~ ' + max;
  }

  /** 연결 끝 이름들 — {type} 은 표시 표의 이름, {group} 은 '<묶음> 전체'. */
  function endsText(display, groupLabels, ends) {
    var types = (display && display.types) || {};
    return (ends || []).map(function (end) {
      if (end.group) return text((groupLabels || {})[end.group] || end.group) + ' 전체';
      return text((types[end.type] || {}).label || end.type);
    }).join(' · ') || '없음';
  }

  /** ERP 물건 상세 머리 아래 줄 — ['표 orders + JSONB 칸 structured_data', '새 표 없음', '가림 4칸', '능력 질문 9개가 씀']. */
  function erpMeta(detail) {
    var d = detail || {};
    var src = d.source || {};
    var parts = ['표 ' + text(src.table) + (src.json ? ' + JSONB 칸 ' + src.json : ''), '새 표 없음'];
    if (d.masked) parts.push('가림 ' + d.masked + '칸');
    parts.push('능력 질문 ' + (d.cq || []).length + '개가 씀');
    return parts;
  }

  function accessTone(access) {
    return Object.prototype.hasOwnProperty.call(ACCESS_TONES, access) ? ACCESS_TONES[access] : 'primary';
  }

  /** 할 일 수준 꼬리표 색 — 사람만 빨강 · 0 읽기만 옅은 회색 · 그 밖 파랑. */
  function levelTone(action) {
    if (!action || action.mode === 'human') return 'danger';
    return /^0\b/.test(text(action.level_label)) ? '' : 'primary';
  }

  function whereIcon(where) {
    return WHERE_ICONS[where] || 'info-sign';
  }

  /** 점수 — {text, covered, total, before, change}. before 는 ERP 재료를 세기 전 수(erp 칸이 있을 때만). */
  function score(cq) {
    var c = cq || { covered: 0, total: 0 };
    var before = c.covered_before === undefined || c.covered_before === null ? null : Number(c.covered_before);
    return { text: c.covered + ' / ' + c.total, covered: Number(c.covered) || 0, total: Number(c.total) || 0, before: before,
             change: before === null ? '' : 'ERP 재료를 세기 전 ' + before + ' → 지금 ' + c.covered };
  }

  /** 아직 못 푸는 질문 — 앞 n 개 {id, question, missing: [{label, erp}], erpFix} + 모두 수. */
  function fails(cq, n) {
    var rows = ((cq && cq.rows) || []).filter(function (row) { return !row.covered; });
    return { total: rows.length, rows: rows.slice(0, n).map(function (row) {
      var missing = (row.needs || []).concat(row.links || []).filter(function (x) { return !x.have; })
        .map(function (x) { return { label: text(x.label), erp: !!x.erp }; });
      return { id: text(row.id), question: text(row.question), missing: missing,
               erpFix: missing.length > 0 && missing.every(function (x) { return x.erp; }) };
    }) };
  }

  var api = { pickFromQuery: pickFromQuery, pickQuery: pickQuery, defaultPick: defaultPick, navModel: navModel,
              matches: matches, typeSub: typeSub, rangeText: rangeText, requiredText: requiredText,
              cardinalityText: cardinalityText, endsText: endsText, erpMeta: erpMeta, accessTone: accessTone,
              levelTone: levelTone, whereIcon: whereIcon, score: score, fails: fails,
              DATATYPES: DATATYPES, BASIS: BASIS, STAGES: STAGES };
  root.FOMS_DS_ONTO_VIEW = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
