/**
 * 새 물어보기 화면(판 ⑨ — 설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 3.7 · 5.3 · 9절) 순수 계산 — DOM 을 만지지 않는다.
 *
 * - 내 질문 목록 줄(GET /api/brain/chat/history 의 한 줄 → 글 · 아래 줄 · 아이콘 · 때).
 * - 답 머리 꼬리표(모름 · ERP 읽기) · 확신 색 · 주문 근거 칩 · 물은 줄(이름 · 때 · 가린 곳 수).
 * - '이 답이 읽은 것' 옆 창 값(답의 erp 칸 → 주문 요약 · 방문 · 쓴 도구) — 서버가 준 값만 쓴다(손님 이름 · 전화 · 주소 · 금액은
 *   서버가 주지 않고, 여기서도 만들지 않는다). 주문 번호는 '#<번호>', 방문 줄에 팀 · 인원 · 사진 수는 없다(설계서 9절 · D211).
 * - 도구 시간은 서버가 ms(정수)로 준다 → '0.5초'.
 * 답 판정(근거 칩 · 확신 줄 · 피드백 본문)은 옛 화면과 한 벌인 brain-ask-view.js 가 맡는다.
 * window.FOMS_DS_ASK_VIEW · node 에서는 module.exports — tests/domains/test_brain_ds_ask.py.
 */
(function (root) {
  'use strict';

  var WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];
  /** 방문 갈래 → 상태 꼬리표 색(디자인 시스템 주문 상태 여덟 갈래 — 무채색 없음). */
  var VISIT_ST = { measurement: 'contract', construction: 'site', as_visit: 'hold', shipping: 'make' };
  var CERTAINTY = { high: { text: '높음', tone: 'success' }, medium: { text: '보통', tone: 'warning' },
                    low: { text: '낮음', tone: 'danger' } };
  var TONES = ['primary', 'success', 'warning', 'danger'];

  function text(value) {
    return value === null || value === undefined ? '' : String(value);
  }

  function pad(n) {
    return (n < 10 ? '0' : '') + n;
  }

  /** 'YYYY-MM-DD' → '11-20 (금)'(요일은 그 날 그대로 — 시간대 없이 센다). 꼴이 틀리면 받은 글 그대로. */
  function dayLabel(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(text(iso));
    if (!m) return text(iso);
    var day = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
    return m[2] + '-' + m[3] + ' (' + WEEKDAYS[day.getUTCDay()] + ')';
  }

  /** ms(정수) → '0.5초'. 0.1초가 안 되면 '0.1초 아래'. 수가 아니면 빈 글. */
  function secsLabel(ms) {
    var n = Number(ms);
    if (ms === null || ms === undefined || ms === '' || !isFinite(n) || n < 0) return '';
    if (n < 100) return '0.1초 아래';
    return (Math.round(n / 100) / 10).toFixed(1) + '초';
  }

  /** 물은 때(ISO 'YYYY-MM-DDTHH:MM' — 한국 시각) → 오늘이면 '10:42', 아니면 '11-12'. */
  function whenLabel(iso, isToday) {
    var m = /^\d{4}-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(text(iso));
    if (!m) return '';
    return isToday ? m[3] + ':' + m[4] : m[1] + '-' + m[2];
  }

  /** 내 질문 한 줄 → {id, text, sub, icon, when}. 모름 · ERP 읽음 · 회사 지식 갈래(확신 · 물을 곳은 서버 글 그대로). */
  function historyItem(row, isToday) {
    var r = row || {};
    var sub;
    var icon;
    if (r.unknown) {
      sub = ['모름', text(r.ask_label)];
      icon = 'help';
    } else if (r.erp) {
      sub = ['ERP 읽음', text(r.certainty_label)];
      icon = 'data-lineage';
    } else {
      sub = ['회사 지식', text(r.certainty_label)];
      icon = 'properties';
    }
    return { id: r.id, text: text(r.text), sub: sub.filter(Boolean).join(' · '), icon: icon,
             when: whenLabel(r.asked_at, !!isToday) };
  }

  /** 목록 전체 → {today: [줄], week: [줄], count, empty}. */
  function historyLists(data) {
    var d = data || {};
    var today = (d.today || []).map(function (row) { return historyItem(row, true); });
    var week = (d.week || []).map(function (row) { return historyItem(row, false); });
    return { today: today, week: week, count: today.length, empty: !today.length && !week.length };
  }

  /** 답 머리 꼬리표 — 모름(주황 · 꽉 참) · ERP 읽기(파랑 · 옅음) · 그 밖 null. */
  function kindTag(data) {
    var d = data || {};
    if (d.unknown) return { text: '모름', tone: 'warning', minimal: false, icon: 'help' };
    if (d.kind === 'erp') return { text: 'ERP 읽기', tone: 'primary', minimal: true, icon: 'data-lineage' };
    return null;
  }

  /** 답이 맞을 가능성 → 꼬리표 {text, tone}(모름이거나 값이 없으면 null — 높음 초록 · 보통 주황 · 낮음 빨강). */
  function certaintyTag(data) {
    var d = data || {};
    if (d.unknown || !d.certainty) return null;
    return CERTAINTY[d.certainty] || { text: text(d.certainty), tone: 'primary' };
  }

  /** 주문 · 방문 근거 칩(ERP 답만) — [{text, icon}]. */
  function erpChips(data) {
    var d = data || {};
    var erp = d.erp;
    if (d.unknown || d.kind !== 'erp' || !erp || !erp.order) return [];
    var chips = [{ text: '주문 #' + text(erp.order.id) + (erp.order.stage_label ? ' · ' + erp.order.stage_label : ''),
                   icon: 'cube' }];
    (erp.visits || []).forEach(function (v) {
      chips.push({ text: '방문 · ' + text(v.label) + ' ' + dayLabel(v.day) + (v.time_label ? ' ' + v.time_label : ''),
                   icon: 'calendar' });
    });
    return chips;
  }

  /** 물은 줄 — '김영업 · 10:42' + 가린 곳이 있으면 ' · 1곳을 가려서 보냄'(가림 도구가 센 수 — 글은 싣지 않는다). */
  function askedLine(me, clock, erp) {
    var parts = [text(me), text(clock)].filter(Boolean);
    var mask = ((erp && erp.tools) || []).filter(function (t) { return t && t.name === 'mask.apply'; })[0];
    var n = mask ? Number((/(\d+)/.exec(text(mask.what)) || [])[1]) : 0;
    if (n > 0) parts.push(n + '곳을 가려서 보냄');
    return parts.join(' · ');
  }

  /** '이 답이 읽은 것' 값 — erp 칸이 없거나 주문이 없으면 null(옆 창을 그리지 않는다). */
  function readView(erp) {
    if (!erp || !erp.order) return null;
    var order = erp.order;
    var tone = TONES.indexOf(order.stage_tone) >= 0 ? order.stage_tone : 'primary';
    return {
      title: '#' + text(order.id),
      stage: { text: text(order.stage_label || order.stage), tone: tone },
      products: (order.products || []).map(text).filter(Boolean).join(' · '),
      manager: text(order.manager_label),
      masked: (order.masked || []).map(text).filter(Boolean).join(' · '),
      visits: (erp.visits || []).map(function (v) {
        return { label: text(v.label), st: VISIT_ST[v.kind] || 'talk', day: dayLabel(v.day), time: text(v.time_label),
                 state: text(v.state_label || v.state) };
      }),
      tools: (erp.tools || []).map(function (t) {
        return { name: text(t.name), label: text(t.label), what: text(t.what), secs: secsLabel(t.ms) };
      }),
      change: !!erp.change_asked
    };
  }

  /** 빈 지식 수 · 틀림 신고 수(관리 길잡이) — 빈 지식 목록(gaps.layers)에서 센다. */
  function gapCounts(gaps) {
    var out = { gaps: 0, wrong: 0 };
    var layers = (gaps && gaps.layers) || {};
    Object.keys(layers).forEach(function (layer) {
      (layers[layer] || []).forEach(function (g) {
        out.gaps += 1;
        out.wrong += Number(g.wrong) || 0;
      });
    });
    return out;
  }

  /** 지금 시각 → 'HH:MM'. */
  function clockOf(date) {
    var d = date || new Date();
    return pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  var api = { dayLabel: dayLabel, secsLabel: secsLabel, whenLabel: whenLabel, historyItem: historyItem,
              historyLists: historyLists, kindTag: kindTag, certaintyTag: certaintyTag, erpChips: erpChips,
              askedLine: askedLine, readView: readView, gapCounts: gapCounts, clockOf: clockOf };
  root.FOMS_DS_ASK_VIEW = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
