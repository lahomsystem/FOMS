/**
 * 제안함 · 다시 확인 · 판 되돌리기 순수 함수(HAUD master brain 설계서 7.5 화면 4 · 5 · 6 — DOM 을 만지지 않는다).
 *
 * 받은 카드(GET /api/brain/inbox) → 한 줄 요약 · 칸별 전 → 후 줄 · 관문 줄 · 사례 · 이웃 글 · 화면별(휴대폰 · PC) 결정 단추 ·
 * 넣기 본문(기준 판 · 결정 시간 · 등급 B 확인 · 고친 값). 휴대폰은 칸 하나 고침의 넣기만(사장님 D103). 등급 B 확인 글은 서버가
 * 준 글을 그대로 돌려보내고, 고쳐 넣은 칸이면 고친 글을 보낸다(서버가 다시 만든 글과 같아야 넣는다).
 * window.FOMS_BRAIN_REVIEW 로 내놓고 node 에서는 module.exports — tests/domains/test_brain_review_js.py.
 */
(function (root) {
  'use strict';

  var EDITABLE = ['name', 'text', 'valid_from', 'valid_to'];
  var DATE_FIELDS = ['valid_from', 'valid_to', 'checked_at'];

  function labels(display, group) {
    return (display && display[group]) || {};
  }

  /** 칸 값 → 보이는 글(없음 · 목록 · 실음 칸 · 값 목록 이름 · 수에 단위). */
  function valueText(field, value, display, unit) {
    if (value === null || value === undefined || value === '') return '(없음)';
    if (Array.isArray(value)) return value.length ? value.map(String).join(' · ') : '(빈 목록)';
    if (typeof value === 'object') return '실음 칸 ' + Object.keys(value).length + '개 칸';
    if (typeof value === 'number' && unit) return String(value) + unit;
    var group = { status: 'statuses', confidence: 'confidences', risk_grade: 'grades', visibility: 'visibilities' }[field];
    return group ? (labels(display, group)[value] || String(value)) : String(value);
  }

  /** 칸별 전 → 후 줄 — [{field, label, before, after, proposed}](이름 · 단위는 서버 속성 틀이 준 것 먼저 ·
   *  proposed 는 고쳐 넣기 전 처음 제안 값 · 없으면 null). */
  function diffRows(fields, display) {
    return (fields || []).map(function (row) {
      var unit = row.unit || null;
      return { field: row.field, label: row.label || labels(display, 'fields')[row.field] || row.field,
               before: valueText(row.field, row.before, display, unit), after: valueText(row.field, row.after, display, unit),
               proposed: Object.prototype.hasOwnProperty.call(row, 'proposed')
                 ? valueText(row.field, row.proposed, display, unit) : null };
    });
  }

  /** 카드 한 줄 요약 — '고침 · 유형 · 이름 — 칸들' / '링크 더함 · 적용: 시작 → 끝'. */
  function summary(card, display) {
    var view = card.main;
    var op = labels(display, 'ops')[view.op] || view.op;
    if (view.link) {
      var kind = (labels(display, 'links')[view.link.kind] || {}).label || view.link.kind;
      return op + ' · ' + kind + ': ' + view.link.from + ' → ' + view.link.to;
    }
    var type = (labels(display, 'types')[card.type] || {}).label || card.type;
    var names = diffRows(view.fields, display).map(function (r) { return r.label; });
    var tail = view.op === 'update' && names.length ? ' — ' + names.join(' · ') : '';
    return op + ' · ' + type + ' · ' + (card.title || card.name) + tail;
  }

  /** 관문 줄 — [{label, text, cls}](통과 · 안 됨 · 아직). */
  function gateRows(gates, display) {
    return (gates || []).map(function (gate) {
      var cls = gate.value === 'pass' ? 'is-pass' : (gate.value === 'fail' ? 'is-fail' : 'is-wait');
      return { label: labels(display, 'gates')[gate.name] || gate.name,
               text: labels(display, 'gate_values')[gate.value] || gate.value, cls: cls };
    });
  }

  /** 화면별 결정 단추 — 휴대폰은 칸 하나 고침의 넣기와 'PC 에서 볼게요'만, 기준 판이 바뀌었으면 넣기 없음. */
  function actionsFor(view, phone) {
    var stale = !!(view.base && view.base.changed);
    if (phone) {
      return { apply: !!view.phone_ok && !stale, edit: false, reject: false, later: true, hint: !view.phone_ok };
    }
    var editable = (view.op === 'create' || view.op === 'update') && editableFields(view).length > 0;
    return { apply: !stale, edit: editable && !stale, reject: true, later: true, hint: false };
  }

  function isEditable(row) {
    return row.editable === undefined ? EDITABLE.indexOf(row.field) >= 0 : !!row.editable;
  }

  /** 고쳐 넣기로 고칠 수 있는 칸(서버가 속성 틀로 표시 — 이름 · 글 · 유효 기간 · 실음 칸 틀 칸). */
  function editableFields(view) {
    return (view.fields || []).filter(isEditable).map(function (row) { return row.field; });
  }

  /** 고친 칸 글 모음 → 자료형 값으로 바꿔 처음 '후' 값과 다른 칸만(빈 칸은 null). */
  function editsFrom(view, values) {
    var out = {};
    var count = 0;
    (view.fields || []).forEach(function (row) {
      if (!isEditable(row) || !Object.prototype.hasOwnProperty.call(values || {}, row.field)) return;
      var datatype = row.datatype || (DATE_FIELDS.indexOf(row.field) >= 0 ? 'date' : 'text');
      var value = row.field === 'text' || row.field === 'name' ? values[row.field] : fieldValue(datatype, values[row.field]);
      if (JSON.stringify(value === undefined ? null : value) !== JSON.stringify(row.after === undefined ? null : row.after)) {
        out[row.field] = value;
        count += 1;
      }
    });
    return count ? out : null;
  }

  /** 넣기 본문 — 기준 판 · 결정 시간 · (고친 값) · (등급 B 확인). */
  function applyBody(view, opts) {
    var o = opts || {};
    var body = { base_version: view.base_version === undefined ? null : view.base_version,
                 view_ms: Math.max(0, Math.round(Number(o.viewMs) || 0)) };
    if (o.edits) body.edits = o.edits;
    if (view.confirm && o.confirmed) {
      var field = view.confirm.field;
      var edited = o.edits && Object.prototype.hasOwnProperty.call(o.edits, field);
      body.confirm = { field: field, value: edited ? String(o.edits[field] === null ? '' : o.edits[field]) : view.confirm.value };
    }
    return body;
  }

  /** 등급 A 한꺼번에 넣기 대상 — 카드의 첫 제안이 등급 A 이고 기준 판이 그대로인 것. */
  function bulkIds(cards) {
    return (cards || []).filter(function (card) {
      return card.main.bulk_ok && !(card.main.base && card.main.base.changed);
    }).map(function (card) { return card.main.id; });
  }

  /** 기준 판 바뀜 경고 글(바뀌지 않았으면 빈 글). */
  function conflictText(view) {
    if (!view.base || !view.base.changed) return '';
    var was = view.base_version === null || view.base_version === undefined ? '없음' : '판 ' + view.base_version;
    var now = view.base.current === null || view.base.current === undefined ? '없음' : '판 ' + view.base.current;
    return '제안을 만든 뒤 이 지식이 바뀌었어요(기준 ' + was + ' → 지금 ' + now + '). 승인할 수 없어요 — 거절하거나 지식 화면에서 새로 제안해 주세요.';
  }

  /** 근거 사진 주소 — 'photo:<상담 차례>/<번호>' 만(그 밖 근거 id 는 글로만 — 가린 글 자리). */
  function evidenceHref(ref) {
    var match = /^photo:(\d+)\/(\d+)$/.exec(String(ref || ''));
    return match ? '/cs-agent/turns/' + match[1] + '/photos/' + match[2] : null;
  }

  /** 비슷한 사례 글. */
  function similarText(similar) {
    if (!similar || !similar.count) return '비슷한 사례 없음(이 항목을 받치는 관찰이 아직 없어요)';
    var span = similar.first === similar.last ? similar.first : similar.first + ' ~ ' + similar.last;
    return '비슷한 사례 ' + similar.count + '건 (' + span + ')';
  }

  /** 함께 닿는 항목 글 — '적용 대상: 이름, 이름 … 그 밖 n개'. */
  function touchText(touches, copies, display) {
    var parts = [];
    var items = (touches && touches.items) || [];
    if (items.length) {
      var names = items.map(function (t) { return t.name; }).join(', ');
      var more = touches.total > items.length ? ' 그 밖 ' + (touches.total - items.length) + '개' : '';
      parts.push('이어진 항목 ' + touches.total + '개: ' + names + more);
    }
    if (copies) parts.push('사본 ' + copies + '곳(매크로 · 스토어 상세 같은 곳 — 함께 고칠 일)');
    return parts.length ? parts.join(' · ') : '함께 닿는 항목 없음';
  }

  /** 제안함 맨 위 줄 · AI 자리 줄. */
  function inboxStatus(data) {
    var cards = (data && data.cards) || [];
    return cards.length ? '' : '승인 대기가 없어요.';  // 수는 탭 · 묶음 줄에 이미 있다
  }

  function aiLine(data) {
    var ai = (data && data.ai) || { cap: 20, left: 0 };
    var waiting = (data && data.counts && data.counts.ai_waiting) || 0;
    return 'AI 제안 이번 주 자리 ' + ai.left + '/' + ai.cap + ' 남음' + (waiting ? ' · 자리를 기다리는 AI 제안 ' + waiting + '건' : '') +
      ' · AI 제안은 4주가 지나면 저절로 닫혀요';
  }

  /** 다시 확인 줄 글 — '확인 날 3일 지남' · '오늘이 확인 날' · '5일 뒤 확인'. */
  function recheckWhen(item) {
    var days = Number(item.days) || 0;
    if (days < 0) return '확인 날 ' + (-days) + '일 지남';
    if (days === 0) return '오늘이 확인 날';
    return days + '일 뒤 확인';
  }

  /** 판 층 되돌림 표시 글. */
  function rollbackText(mark) {
    return mark ? '되돌림 — 판 ' + mark.into + '에서(' + mark.at + ')' : '';
  }

  /** 입력 칸 글 → 속성 틀 자료형 값(수 · 정수 · 목록 · 글 — 빈 칸은 null). */
  function fieldValue(datatype, raw) {
    var text = String(raw === null || raw === undefined ? '' : raw).trim();
    if (!text) return null;
    if (datatype === 'int' || datatype === 'number') {
      var number = Number(text);
      return Number.isFinite(number) ? number : text;
    }
    if (datatype === 'list') {
      return text.split(',').map(function (x) { return x.trim(); }).filter(function (x) { return x; });
    }
    return text;
  }

  /** 지금 값과 다른 칸만 고칠 칸으로(같으면 null) — 견주기는 JSON 글로(목록 · 수 같이). */
  function changedAfter(current, values) {
    var out = {};
    var count = 0;
    Object.keys(values || {}).forEach(function (name) {
      var was = current && Object.prototype.hasOwnProperty.call(current, name) ? current[name] : null;
      if (JSON.stringify(was === undefined ? null : was) === JSON.stringify(values[name])) return;
      out[name] = values[name];
      count += 1;
    });
    return count ? out : null;
  }

  /** 액션 이름 → 화면 이름(이름 있는 액션 목록 — 없으면 이름 그대로). */
  function actionLabel(actions, name) {
    var found = (actions || []).filter(function (a) { return a.name === name; })[0];
    return found ? found.label : name;
  }

  /** 액션 매개변수의 고른 값 [{value, label}](거절 까닭 칩 · 층). */
  function actionChoices(actions, name, param) {
    var found = (actions || []).filter(function (a) { return a.name === name; })[0];
    var spec = found && found.params.filter(function (p) { return p.name === param; })[0];
    return (spec && spec.choices) || [];
  }

  /** 카드를 보인 뒤 누를 때까지(밀리초). */
  function elapsed(start, now) {
    return Math.max(0, Math.round(Number(now) - Number(start)));
  }

  var api = { valueText: valueText, diffRows: diffRows, summary: summary, gateRows: gateRows, actionsFor: actionsFor,
              editableFields: editableFields, editsFrom: editsFrom, applyBody: applyBody, bulkIds: bulkIds,
              conflictText: conflictText, evidenceHref: evidenceHref, similarText: similarText, touchText: touchText,
              inboxStatus: inboxStatus, aiLine: aiLine, recheckWhen: recheckWhen, rollbackText: rollbackText,
              elapsed: elapsed, fieldValue: fieldValue, changedAfter: changedAfter, actionLabel: actionLabel,
              actionChoices: actionChoices, EDITABLE: EDITABLE };
  root.FOMS_BRAIN_REVIEW = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
