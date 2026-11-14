/**
 * 새 찾기 · 지식 표 · 지식 카드(설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 5.3 · 5.4 · 판 ⑦ · ⑧) 순수 계산 — DOM 을 만지지 않는다.
 *
 * 표 줄 모양(상태 · 등급 꼬리표 색 갈래 — 무채색 없음, 확실한 정도 아이콘, 다시 볼 날 지남 표시, 확인 필요 표시) · 처음 고를 유형 ·
 * 수 글(1,204) · 미리 보기 자리 글('10개 중 4') · 앞뒤 줄 옮기기 · 쓰인 곳 막대(읽은 쪽 셋) · 이어진 ERP 물건 칩 · 연결된 지식
 * 종류별 수 · 카드 속성 칸 고르기 · 주소 물음 글. 이름표는 서버 표시 표(display — foms/services/brain/display.py)에서 읽는다.
 * window.FOMS_DS_SEARCH_VIEW 로 내놓고 node 에서는 module.exports — tests/domains/test_brain_ds_search.py.
 */
(function (root) {
  'use strict';

  /** 상태 꼬리표 — 사용 중 초록(꽉 찬), 초안 파랑 · 은퇴 빨강(옅은 바탕). 회색(무채색)은 쓰지 않는다. */
  var STATUS_TONES = { active: 'f-tag-success', draft: 'f-tag-minimal f-tag-primary', retired: 'f-tag-minimal f-tag-danger' };
  /** 위험 등급 꼬리표 — A 초록 · B(가벼움) 주황(옅은 바탕) · B 빨강(꽉 찬 — 판 ⑦ 은 옅은 바탕이지만 옅은 초록 · 주황과 색 차가
   *  10 아래 · 색약 흉내 뒤 1 이라 무거운 B 만 꽉 채운다. 잰 값은 T4 보고서). */
  var GRADE_TONES = { A: 'f-tag-minimal f-tag-success', B_LIGHT: 'f-tag-minimal f-tag-warning', B: 'f-tag-danger' };
  /** 확실한 정도 → [아이콘, 색]. */
  var CONF_ICONS = { confirmed: ['endorsed', 'f-i-primary'], evidenced: ['small-tick', 'f-i-success'],
                     observed: ['eye-open', 'f-i-warning'] };
  /** 쓰인 곳 읽은 쪽 차례 · 이름(판 ⑧ — 상담 초안 · 할 일 제안 · 물어보기 답). */
  var READERS = [['cs_draft', '상담 초안'], ['erp_action', '할 일 제안'], ['chatbot', '물어보기 답']];
  var TONES = ['primary', 'success', 'warning', 'danger'];
  /** 카드 속성 표에서 빼는 칸 — 제목 · 비슷한 말 · 유효 기간 · 마지막 확인 · 근거 줄에 이미 있다(옛 카드와 같은 규칙). */
  var SHOWN_ELSEWHERE = ['payload.pref_label', 'payload.aliases', 'valid_from', 'valid_to', 'checked_at', 'evidence_ref'];

  function own(map, key) {
    return map && Object.prototype.hasOwnProperty.call(map, key) ? map[key] : null;
  }

  /** 수 글 — 세 자리마다 쉼표(1204 → '1,204'). 수가 아니면 '0'. */
  function num(value) {
    var n = Math.round(Number(value) || 0);
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  /** 표시 표의 이름(없으면 값 그대로, 빈 값은 '—'). */
  function label(display, table, value) {
    if (value === null || value === undefined || value === '') return '—';
    return own((display || {})[table], value) || String(value);
  }

  /** 'YYYY-MM-DD' → 'MM-DD'(꼴이 아니면 그대로). */
  function shortDay(day) {
    var s = String(day || '');
    return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s.slice(5) : s;
  }

  /** 다시 볼 날 칸 — {text, warn}. 지났으면 'MM-DD 지남'(주황), 없으면 '—'. */
  function dueText(item) {
    var day = item && item.stale_after;
    if (!day) return { text: '—', warn: false };
    return item.stale ? { text: shortDay(day) + ' 지남', warn: true } : { text: String(day), warn: false };
  }

  /** 표 줄 하나의 모양 — 글은 이름표로, 색은 class 로(인라인 스타일 없음). */
  function rowModel(item, display, icons) {
    var it = item || {};
    var info = own((display || {}).types, it.type);
    var conf = own(CONF_ICONS, it.confidence) || ['circle', 'f-i-muted'];
    var flags = [];
    if (it.needs_check) flags.push({ text: '확인 필요', cls: 'f-tag-minimal f-tag-warning' });
    return {
      key: String(it.key || ''), name: String(it.name || it.key || ''), type: String(it.type || ''),
      typeLabel: info ? info.label : String(it.type || ''), icon: own(icons, it.type) || 'circle',
      team: label(display, 'layers', it.layer), brand: label(display, 'brands', it.brand),
      status: label(display, 'statuses', it.status), statusCls: own(STATUS_TONES, it.status) || 'f-tag-minimal f-tag-primary',
      conf: label(display, 'confidences', it.confidence), confIcon: conf[0], confCls: conf[1],
      grade: it.grade ? label(display, 'grades', it.grade) : '—', gradeCls: it.grade ? own(GRADE_TONES, it.grade) || '' : '',
      used: num(it.usage_count), checked: it.checked_at || '—', due: dueText(it), flags: flags
    };
  }

  /** 처음 고를 유형 — 주소의 유형, 없으면 차례(type_order)에서 지식이 있는 첫 유형, 그것도 없으면 첫 유형. */
  function pickStartType(start, counts, order) {
    var list = order || [];
    if (start && list.indexOf(start) >= 0) return start;
    for (var i = 0; i < list.length; i += 1) if (Number((counts || {})[list[i]]) > 0) return list[i];
    return list[0] || '';
  }

  /** 미리 보기 자리 글 — '10개 중 4'(줄이 없으면 빈 글). */
  function previewPos(index, total) {
    var n = Number(total) || 0;
    return n && index >= 0 ? num(n) + '개 중 ' + (index + 1) : '';
  }

  /** 앞 · 다음 줄 — 범위를 넘으면 -1. */
  function stepIndex(index, step, total) {
    var next = Number(index) + Number(step);
    return next >= 0 && next < Number(total) ? next : -1;
  }

  /** 쓰인 곳 막대 셋 — [{key, label, n, pct}] (pct = 가장 큰 쪽을 100 으로, 정수). */
  function usageBars(byReader) {
    var counts = READERS.map(function (r) { return Math.max(0, Number((byReader || {})[r[0]]) || 0); });
    var top = Math.max.apply(null, counts);
    return READERS.map(function (r, i) {
      return { key: r[0], label: r[1], n: counts[i], pct: top ? Math.round(counts[i] * 100 / top) : 0 };
    });
  }

  /** 쓰인 곳 최근 줄 상태 꼬리표 class(서버 색 갈래 — 모르는 갈래는 파랑). */
  function toneCls(tone) {
    return 'f-tag-minimal f-tag-' + (TONES.indexOf(tone) >= 0 ? tone : 'primary');
  }

  /** 이어진 ERP 물건 한 줄 → {icon, text, note}. 걸린 공정 단계는 단계 아이콘, 그 밖은 물건(주문 품목) 아이콘. */
  function erpChip(link) {
    var l = link || {};
    return { icon: l.rel === 'at_step' ? 'timeline-bar-chart' : 'cube',
             text: (l.type_label ? l.type_label + ' · ' : '') + String(l.label || ''), note: String(l.note || '') };
  }

  /** 카드 연결 묶음 → [{kind, label, n}] (방향에 맞는 이름 — 나가는 쪽 out · 들어오는 쪽 in) + 합. */
  function linkSummary(groups, display) {
    var rows = (groups || []).map(function (g) {
      var info = own((display || {}).links, g.kind);
      var name = info ? (g.direction === 'in' ? info['in'] : info.out) : String(g.kind || '');
      return { kind: g.kind, label: name, n: Number(g.count) || 0 };
    });
    return { rows: rows, total: rows.reduce(function (sum, r) { return sum + r.n; }, 0) };
  }

  /** 카드의 눈에 띄는 칸 가운데 미리 보기에 보일 것(다른 줄에 있는 칸은 뺀다) — 앞 limit 개. */
  function keyFields(fields, limit) {
    return (fields || []).filter(function (f) { return SHOWN_ELSEWHERE.indexOf(f.path) < 0; })
      .slice(0, limit === undefined ? 3 : limit);
  }

  /** 지식 표 아래 쪽 글 — '1,204개 중 1–10 · 쓰인 횟수 많은 순'(판 ⑦). 0 개면 '0개'. */
  function pagerText(page, perPage, total, sortLabel) {
    var count = Math.max(0, Number(total) || 0);
    if (!count) return '0개';
    var size = Math.max(1, Number(perPage) || 1);
    var from = (Math.max(1, Number(page) || 1) - 1) * size + 1;
    var to = Math.min(count, from + size - 1);
    return num(count) + '개 중 ' + from + '–' + to + (sortLabel ? ' · ' + sortLabel : '');
  }

  /** 주소 물음 글 — 찾기면 ?tab=search(&q=), 지식 표면 ?tab=table&type=. */
  function pageQuery(mode, value) {
    if (mode === 'table') return '?tab=table' + (value ? '&type=' + encodeURIComponent(value) : '');
    var q = String(value || '').trim();
    return '?tab=search' + (q ? '&q=' + encodeURIComponent(q) : '');
  }

  var api = { STATUS_TONES: STATUS_TONES, GRADE_TONES: GRADE_TONES, num: num, label: label, shortDay: shortDay,
              dueText: dueText, rowModel: rowModel, pickStartType: pickStartType, previewPos: previewPos,
              stepIndex: stepIndex, usageBars: usageBars, toneCls: toneCls, erpChip: erpChip, linkSummary: linkSummary,
              keyFields: keyFields, pagerText: pagerText, pageQuery: pageQuery };
  root.FOMS_DS_SEARCH_VIEW = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
