/**
 * 승인 대기의 '문장으로 고친 것' 보기(?tab=requests — 설계서 docs/specs/2026-11-18-brain-sentence-change_SPEC.md 4절 '목록').
 * '판 · 기록' 보기(ds-inbox-releases.js)와 같은 꼴: GET /api/brain/change-requests?page= → 줄마다 날짜 · 한 줄 요약 · 상태 ·
 * 고친 수(승인 대기 수), 줄을 누르면 묶음 화면(/brain/requests/<번호>). 상태 꼬리표 색은 서버 표(data-tones — 무채색 없음).
 * fetch 는 brain-dom.js 한 곳 · 글은 textContent 만 · 전역 듣개는 한 번만.
 */
(function (root) {
  'use strict';

  /** 날짜 글 — '2026-11-18T01:00:00'(UTC) → 한국 날짜 · 시각 '11월 18일 10:00'. 못 읽으면 빈 글. */
  function whenText(iso) {
    var at = iso ? new Date(String(iso) + (/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? '' : 'Z')) : null;
    if (!at || isNaN(at.getTime())) return '';
    var kst = new Date(at.getTime() + 9 * 3600 * 1000);
    var pad = function (n) { return (n < 10 ? '0' : '') + n; };
    return (kst.getUTCMonth() + 1) + '월 ' + kst.getUTCDate() + '일 ' + pad(kst.getUTCHours()) + ':' + pad(kst.getUTCMinutes());
  }

  /** 고친 수 글 — '3곳 고침 · 승인 대기 1' · 아무것도 안 고쳤으면 '줄 4개'. */
  function countText(item) {
    var parts = [];
    if (item.applied) parts.push(item.applied + '곳 고침');
    if (item.pending) parts.push('승인 대기 ' + item.pending);
    if (!parts.length) parts.push('줄 ' + (item.lines || 0) + '개');
    return parts.join(' · ');
  }

  /** 꼬리표 class — tones[status] = [tone, 옅은 바탕]. 모르는 상태는 옅은 파랑(무채색 없음). */
  function tagClass(tones, status) {
    var tone = (tones || {})[status] || ['primary', true];
    return 'f-tag' + (tone[1] ? ' f-tag-minimal' : '') + ' f-tag-' + tone[0];
  }

  var api = { whenText: whenText, countText: countText, tagClass: tagClass };
  root.FOMS_DS_REQUEST_LIST = api;
  if (typeof module === 'object' && module.exports) module.exports = api;

  var dom = root.FOMS_BRAIN_DOM;
  var doc = root.document;
  var list = doc && doc.querySelector('[data-ds-reqs]');
  if (!dom || !list || root.__FOMS_DS_REQS_BOUND) return;
  root.__FOMS_DS_REQS_BOUND = true;

  var box = list.closest('[data-ds-inbox]') || doc;
  var status = box.querySelector('[data-ds-reqs-status]');
  var prev = box.querySelector('[data-ds-reqs-prev]');
  var next = box.querySelector('[data-ds-reqs-next]');
  var pageText = box.querySelector('[data-ds-reqs-text]');
  var url = list.getAttribute('data-list-url');
  var base = list.getAttribute('data-request-base');
  var tones = dom.safeJsonParse(list.getAttribute('data-tones'), {});
  var page = 1;

  function row(item) {
    var link = dom.el('a', { cls: 'f-card f-card-compact f-card-interactive f-col fb-req-row',
                             attrs: { href: base + encodeURIComponent(item.id), 'data-ds-req-id': item.id } });
    link.appendChild(dom.el('span', { cls: 'f-strong fb-req-row__title', text: item.summary || item.text }));
    link.appendChild(dom.el('span', { cls: 'f-row f-gap4 f-small', children: [
      dom.el('span', { cls: tagClass(tones, item.status), text: item.status_label }),
      dom.el('span', { cls: 'f-muted f-num', text: whenText(item.created_at) }),
      dom.el('span', { cls: 'f-muted', text: countText(item) })] }));
    return dom.el('li', { children: [link] });
  }

  async function load() {
    dom.setStatus(status, '불러오는 중…');
    var res = await dom.getJson(url + '?page=' + page);
    if (!res.ok) {
      dom.setStatus(status, res.error, 'error');
      return;
    }
    var data = res.data;
    page = data.page;
    dom.clear(list);
    data.items.forEach(function (item) { list.appendChild(row(item)); });
    dom.setStatus(status, data.total ? ('묶음 ' + data.total + '개') : '아직 문장으로 고친 것이 없어요. 위 칸에 바뀐 내용을 적어 보세요.');
    if (pageText) pageText.textContent = data.total ? (data.page + '/' + data.pages + '쪽') : '';
    if (prev) prev.disabled = data.page <= 1;
    if (next) next.disabled = data.page >= data.pages;
  }

  if (prev) prev.addEventListener('click', function () { page = Math.max(1, page - 1); load(); });
  if (next) next.addEventListener('click', function () { page += 1; load(); });
  load();
})(typeof window !== 'undefined' ? window : globalThis);
