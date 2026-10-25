/**
 * 도면 마법사 — 자재표 계산 칸의 '결과 · 맞춰 보기'(칸 맨 위에 고정)와 '줄마다 계산 근거'.
 *
 * 보고서 2026-10-25 큼-3·보통-7(계산 칸 배치 안 A):
 * - 결과와 맞춰 보기를 합쳐 줄마다 계산 값 + 맞춰 보기 칩을 한 줄에 둔다(같은 숫자를 두 번 보이지 않는다).
 * - 칸 맨 위에 두어 모듈을 치는 동안에도 늘 보인다. 6줄이 넘으면 '더 보기'로 접는다(접으면 칸 스크롤을 맨 위로,
 *   펼치면 제자리). 제목·요약 칩은 칸 위에 붙어 있어 펼친 칸을 내려도 보인다(wizard.css .dws-calc-top-head sticky).
 *   이 칸은 아래 스크롤 구역이 길어져도 줄지 않는다(wizard.css .dws-calc-body flex-basis 0 — 실화면 QA 2026-10-25).
 * - 요약 칩: 'N줄 중 M줄 같음 · 다름 K'. 빨강은 진짜 다름·짧음에만, 아직 안 친 칸은 회색.
 * 계산·맞춰 보기 자체는 bom-calc.js(calc · parseBom · compare)가 하고 여기는 그리기만 한다.
 *
 * window.FomsBomResults = { summary(res, hasRows), renderTop(host, lines, rows, C), renderWhy(host, lines) }
 */
(function () {
  'use strict';
  if (window.FomsBomResults) { return; }

  var FOLD_AT = 6;
  var KIND_NAMES = { ok: '같음', warn: '여유', bad: '다름', todo: '시트에 아직 안 친 칸', extra: '시트에만 있는 줄' };
  var showAll = false;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (text != null) { e.textContent = text; }
    return e;
  }

  /** 맞춰 본 결과 → 요약 { text, tone: ok|warn|bad|todo, counts }. hasRows=false 면 시트에 친 자재표가 없다. */
  function summary(res, hasRows) {
    var c = { ok: 0, warn: 0, bad: 0, todo: 0, extra: 0 };
    (res || []).forEach(function (r) { c[r.kind] = (c[r.kind] || 0) + 1; });
    var n = (res || []).length - c.extra;
    if (!hasRows) { return { text: '계산 ' + n + '줄 · 시트에 아직 안 침', tone: 'todo', counts: c }; }
    var parts = [n + '줄 중 ' + c.ok + '줄 같음'];
    if (c.warn) { parts.push('여유 ' + c.warn); }
    if (c.bad) { parts.push('다름 ' + c.bad); }
    if (c.todo) { parts.push('아직 안 침 ' + c.todo); }
    if (c.extra) { parts.push('시트에만 ' + c.extra); }
    var tone = c.bad ? 'bad' : (c.warn ? 'warn' : ((c.todo || c.extra) ? 'todo' : 'ok'));
    return { text: parts.join(' · '), tone: tone, counts: c };
  }

  function resRow(list, r, label) {
    var sub = r.sec === '손잡이';   // 'ㄴ피닉스바 2EA' 는 바로 위 문 줄에 딸린 줄
    var row = list.appendChild(el('div', 'dws-calc-res' + (sub ? ' dws-calc-res-sub' : '') + (r.kind === 'extra' ? ' dws-calc-res-extra' : '')));
    row.appendChild(el('span', 'dws-calc-sec-name', label));
    row.appendChild(el('span', 'dws-calc-val', r.text));
    var chip = row.appendChild(el('span', 'dws-calc-chip dws-calc-chip-' + r.kind, r.note));
    chip.title = KIND_NAMES[r.kind] || '';
  }

  /** 칸 맨 위 '결과 · 맞춰 보기'. rows = C.parseBom(시트 글자). refocus 는 '더 보기'·'접기'를 눌러 다시 그릴 때만. */
  function renderTop(host, lines, rows, C, refocus) {
    var keep = host.scrollTop || 0;
    host.textContent = '';
    var head = host.appendChild(el('div', 'dws-calc-top-head'));
    head.appendChild(el('strong', 'dws-calc-top-title', '결과 · 맞춰 보기'));
    if (!(lines || []).some(function (l) { return !l.head; })) {
      host.appendChild(el('p', 'dws-calc-empty', '전체 폭·천장 높이와 모듈을 넣으면 계산이 나옵니다.'));
      return;
    }
    var res = C.compare(lines, rows);
    var sum = summary(res, rows.length > 0);
    head.appendChild(el('span', 'dws-calc-score dws-calc-chip dws-calc-chip-' + sum.tone, sum.text));
    if (rows.orphans) {
      host.appendChild(el('p', 'dws-calc-hint', '머리글 없이 친 줄 ' + rows.orphans + '개는 맞춰 보지 못했습니다. [DOOR] 같은 머리글과 한 글자 상자에 써 주세요.'));
    }
    var list = host.appendChild(el('div', 'dws-calc-res-list'));
    var hidden = 0, hiddenBad = 0, prev = null;
    res.forEach(function (r, i) {
      if (!showAll && i >= FOLD_AT) {
        hidden += 1;
        if (r.kind === 'bad' || r.kind === 'warn') { hiddenBad += 1; }
        return;
      }
      var sub = r.sec === '손잡이';
      resRow(list, r, (sub || r.sec === prev) ? '' : r.sec);
      if (!sub) { prev = r.sec; }
    });
    if (res.length > FOLD_AT) {
      var more = host.appendChild(el('button', 'dws-calc-more',
        showAll ? '접기' : '더 보기(' + hidden + '줄' + (hiddenBad ? ' · 다름 ' + hiddenBad : '') + ')'));
      more.type = 'button';
      more.setAttribute('aria-expanded', String(showAll));
      more.addEventListener('click', function () {
        showAll = !showAll;
        renderTop(host, lines, rows, C, true);
      });
      if (refocus) {
        // 다시 그린 단추로 포커스를 옮기되 칸은 내리지 않는다 — 1366×657 에서 '더 보기' 뒤 '접기' 단추를 보이려고 칸이
        // 86px 내려가 제목·요약 칩·첫 줄(SR)이 머리 줄 밑에 숨었다(실화면 QA 2026-10-25 V2).
        try { more.focus({ preventScroll: true }); } catch (_) { more.focus(); }
      }
    }
    if (!rows.length) {
      host.appendChild(el('p', 'dws-calc-hint', '시트의 [SR]·[DOOR] 같은 머리글 아래에 줄을 치면 줄마다 맞춰 봅니다.'));
    }
    // 다시 그려도 보던 자리 그대로(펼침·입력마다 칸이 튀지 않게). 접을 때만 맨 위로 — 펼친 채 내려간 자리에 남으면
    // 제목·요약 칩이 가려진다(실화면 QA 2026-10-25).
    host.scrollTop = (refocus && !showAll) ? 0 : keep;
  }

  function whyRow(host, text, why) {
    var row = host.appendChild(el('div', 'dws-calc-line'));
    row.appendChild(el('span', 'dws-calc-val', text));
    row.appendChild(el('span', 'dws-calc-why', why));
  }

  /** 접힌 묶음 '줄마다 계산 근거' — 줄마다 어떻게 셈했는지(규칙 이름이 붙은 숫자). */
  function renderWhy(host, lines) {
    host.textContent = '';
    if (!lines.length) { host.appendChild(el('p', 'dws-calc-empty', '계산이 나오면 줄마다 어떻게 셈했는지 보여 줍니다.')); return; }
    lines.forEach(function (l) {
      if (l.head) { host.appendChild(el('div', 'dws-calc-head-line', '[' + l.head + ']')); return; }
      whyRow(host, l.text, l.why);
      if (l.ea) { whyRow(host, 'ㄴ피닉스바 ' + l.ea + 'EA', '문 ' + l.q + '짝 ÷ 2 올림'); }
    });
  }

  window.FomsBomResults = { summary: summary, renderTop: renderTop, renderWhy: renderWhy };
})();
