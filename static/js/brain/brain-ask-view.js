/**
 * 회사 지식 물어보기 순수 함수(HAUD master brain 설계서 10절 · D88 · ⑤-5 — DOM 을 만지지 않는다).
 *
 * 받은 답(POST /api/brain/chat/ask) → 화면 값: 모름 표시 · 답 글 · 근거 칩(이름 · 유형 · 마지막 확인 — 카드를 열 수 있는 사람만
 * 링크) · 확인 중 항목 · 확신 줄(근거 확신 + 답 확신). 피드백 본문 · 남은 질문 글 · 설정 칸(ADMIN) · 빈 지식 줄.
 * 표시 표(display)는 서버 display.py 가 data-display 로 싣는다. window.FOMS_BRAIN_ASK_VIEW · node 에서는 module.exports
 * — tests/domains/test_brain_chat_js.py.
 */
(function (root) {
  'use strict';

  var CERTAINTY = { high: '높음', medium: '보통', low: '낮음' };
  var FEEDBACKS = ['helpful', 'not_helpful', 'wrong'];
  var FEEDBACK_LABELS = { helpful: '도움 됨', not_helpful: '안 됨', wrong: '틀림' };

  function labels(display, group) {
    return (display && display[group]) || {};
  }

  /** 근거 칩 하나 — {key, name, type, href|null, meta}. 카드를 열 수 없으면 링크 없음. */
  function chip(item, display, base, links) {
    var conf = labels(display, 'confidences')[item.confidence] || item.confidence || '';
    var meta = [conf, item.checked_at ? '마지막 확인 ' + item.checked_at : ''].filter(Boolean).join(' · ');
    return { key: item.key, name: item.name, type: item.type,
             href: links ? String(base || '/brain/items/') + String(item.key).split('/').map(encodeURIComponent).join('/') : null,
             meta: meta };
  }

  /** 확신 줄 — '근거 확신: 확정 · 답 확신: 높음'(모름이면 빈 글). */
  function confidenceLine(data, display) {
    if (!data || data.unknown) return '';
    var parts = [];
    if (data.confidence) parts.push('근거 확신: ' + (labels(display, 'confidences')[data.confidence] || data.confidence));
    if (data.certainty) parts.push('답 확신: ' + (CERTAINTY[data.certainty] || data.certainty));
    return parts.join(' · ');
  }

  /** 답 → 화면 값 {cls, badge, text, confidence, chips, checks, feedback, fixLink}. */
  function answerView(data, display, base) {
    var d = data || {};
    var links = !!d.card_links;
    var chips = (d.evidence || []).map(function (item) { return chip(item, display, base, links); });
    var checks = (d.checks || []).map(function (item) {
      return { key: item.key, name: item.name, why: item.why || '확인 필요' };
    });
    return {
      cls: d.unknown ? 'is-unknown' : 'is-answer',
      badge: d.unknown ? '모름' : '',
      text: String(d.answer || ''),
      confidence: confidenceLine(d, display),
      chips: chips,
      checks: checks.length ? '지금 확인 중인 항목(값을 쓰지 않았어요): ' + checks.map(function (c) {
        return c.name + '(' + c.why + ')';
      }).join(', ') : '',
      feedback: FEEDBACKS.map(function (f) { return { value: f, label: FEEDBACK_LABELS[f] }; }),
      fixLink: links && chips.length ? chips[0].href + '#brain-card-propose' : null
    };
  }

  /** 피드백 본문 — 틀림만 고칠 말을 싣는다(빈 글이면 싣지 않는다). 모르는 값은 null. */
  function feedbackBody(choice, note) {
    if (FEEDBACKS.indexOf(choice) < 0) return null;
    var body = { feedback: choice };
    var text = String(note || '').trim();
    if (choice === 'wrong' && text) body.note = text.slice(0, 500);
    return body;
  }

  /** 피드백 주소 — '/…/questions/0/feedback' 의 0 을 질문 번호로. */
  function feedbackUrl(template, id) {
    return String(template || '').replace(/\/0\/feedback$/, '/' + encodeURIComponent(String(id)) + '/feedback');
  }

  /** 오늘 남은 질문 글. */
  function leftText(n) {
    var left = Number(n);
    return isFinite(left) ? '오늘 남은 질문 ' + Math.max(0, left) + '번' : '';
  }

  /** 상태 줄 — 꺼짐 · 단계 · 돈 상한 준비. */
  function stateText(state) {
    var s = state || {};
    if (!s.enabled) return s.is_admin ? '물어보기가 꺼져 있어요 — 아래 설정에서 켤 수 있어요.' : '물어보기가 꺼져 있어요.';
    if (s.is_admin && s.cap_ready === false) return '하루 돈 상한이 비어 있어 답을 부르지 않아요 — 아래 설정에서 정해 주세요.';
    return s.can_ask ? '' : '지금 단계에서는 물을 수 없어요.';
  }

  /** 설정 칸 값 꼴 맞추기 — 칸 종류(bool · int · money · choice)대로. 틀리면 undefined. */
  function coerce(field, raw) {
    if (field.kind === 'bool') return !!raw;
    if (field.kind === 'int') {
      var n = Number(raw);
      return String(raw).trim() !== '' && Math.floor(n) === n ? n : undefined;
    }
    if (field.kind === 'money') return String(raw || '').trim() === '' ? null : String(raw).trim();
    var hit = (field.choices || []).filter(function (c) { return String(c.value) === String(raw); })[0];
    return hit ? hit.value : undefined;
  }

  /** 설정 바뀐 칸만 {이름: 값}(틀린 칸은 bad 목록). */
  function settingsChanges(fields, raw) {
    var changes = {};
    var bad = [];
    (fields || []).forEach(function (field) {
      if (!Object.prototype.hasOwnProperty.call(raw || {}, field.name)) return;
      var value = coerce(field, raw[field.name]);
      if (value === undefined) { bad.push(field.name); return; }
      var before = field.kind === 'money' && field.value !== null ? String(field.value) : field.value;
      if (value !== before) changes[field.name] = value;
    });
    return { changes: changes, bad: bad };
  }

  /** 빈 지식 줄 — [{layer, text}](층 이름 · 묶음 이름 · 수 · 틀림 수 · 마지막 날). */
  function gapRows(gaps, display) {
    var out = [];
    var layers = (gaps && gaps.layers) || {};
    Object.keys(layers).forEach(function (layer) {
      (layers[layer] || []).forEach(function (g) {
        out.push({ layer: layer, text: (labels(display, 'layers')[layer] || layer) + ' · ' + g.label + ' — ' + g.count + '건' +
                   (g.wrong ? '(틀림 ' + g.wrong + ')' : '') + ' · 마지막 ' + g.last });
      });
    });
    return out;
  }

  var api = { answerView: answerView, confidenceLine: confidenceLine, feedbackBody: feedbackBody, feedbackUrl: feedbackUrl,
              leftText: leftText, stateText: stateText, coerce: coerce, settingsChanges: settingsChanges, gapRows: gapRows };
  root.FOMS_BRAIN_ASK_VIEW = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
