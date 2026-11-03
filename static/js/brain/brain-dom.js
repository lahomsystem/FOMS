/**
 * 회사 지식 화면 DOM 도움(HAUD master brain 설계서 7.5) — 요소 만들기(글은 textContent 만 · innerHTML 없음) · 유형 칩 ·
 * 항목 줄 · JSON 읽기 · 쓰기(fetch 는 requestJson 한 곳 — try/catch + data.success 확인) · 알림 줄.
 * 쓰기(POST)의 CSRF 머리는 공용 partials/shared/csrf_bootstrap.html 이 같은 출처 fetch 에 자동으로 싣는다(WRITE-GUARD-01).
 * window.FOMS_BRAIN_DOM 으로 내놓고 회사 지식 화면 스크립트들이 같이 쓴다.
 */
(function () {
  'use strict';

  var view = window.FOMS_BRAIN_VIEW;

  /** 요소 하나 — opts: {cls, text, attrs, children}. 글은 textContent 로만. */
  function el(tag, opts) {
    var node = document.createElement(tag);
    var o = opts || {};
    if (o.cls) node.className = o.cls;
    if (o.text !== undefined && o.text !== null) node.textContent = String(o.text);
    Object.keys(o.attrs || {}).forEach(function (name) {
      var value = o.attrs[name];
      if (value !== undefined && value !== null && value !== false) node.setAttribute(name, String(value));
    });
    (o.children || []).forEach(function (child) { if (child) node.appendChild(child); });
    return node;
  }

  /** 아이콘(장식 — 화면 읽기에서 숨김). */
  function icon(name) {
    return el('i', { cls: 'fas ' + name + ' brain-chip__icon', attrs: { 'aria-hidden': 'true' } });
  }

  /** 유형 칩 — 색은 .brain-type--<유형> 클래스(인라인 스타일 없음). href 가 있으면 링크. */
  function typeChip(display, type, href) {
    var info = view.typeInfo(display, type);
    var chip = el(href ? 'a' : 'span', { cls: 'brain-chip brain-type--' + type, attrs: { href: href || null } });
    chip.appendChild(icon(info.icon));
    chip.appendChild(document.createTextNode(info.label));
    return chip;
  }

  /** 작은 표들(상태 · 확신 · 낡음 · 확인 필요). */
  function badgeNodes(item, display) {
    return view.badges(item, display).map(function (b) { return el('span', { cls: 'brain-badge ' + b.cls, text: b.text }); });
  }

  /** 항목 줄(찾기 결과 · 링크 끝) — 유형 색 왼쪽 띠 · 상태 모양 · 이름 링크 · 표 · 글 앞부분. */
  function itemRow(ctx, item, opts) {
    var classes = ['brain-item', 'brain-type--' + item.type].concat(view.stateClasses(item));
    var row = el((opts && opts.tag) || 'li', { cls: classes.join(' ') });
    if (opts && opts.chip) row.appendChild(typeChip(ctx.display, item.type));
    row.appendChild(el('a', { cls: 'brain-item__name', text: item.name, attrs: { href: view.itemHref(ctx.itemBase, item.key) } }));
    badgeNodes(item, ctx.display).forEach(function (b) { row.appendChild(b); });
    if (item.snippet) row.appendChild(el('p', { cls: 'brain-item__snippet', text: item.snippet }));
    return row;
  }

  /** 알림 줄 글 — kind 'error' 면 빨강. */
  function setStatus(node, text, kind) {
    if (!node) return;
    node.textContent = text || '';
    node.classList.toggle('is-error', kind === 'error');
  }

  /** 자식 모두 지우기. */
  function clear(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  /** JSON 요청 — {ok, status, data, error}. 실패 답의 data(오류 코드 · 지금 판 같은 것)도 돌려준다.
   *  네트워크 · 꼴 오류는 정한 글로(서버 글은 정한 글만 온다). */
  async function requestJson(url, init) {
    try {
      var response = await fetch(url, Object.assign({ credentials: 'same-origin' }, init || {}));
      var payload = null;
      try {
        payload = await response.json();
      } catch (parseError) {
        return { ok: false, status: response.status, data: null, error: '답을 읽지 못했어요(' + response.status + ').' };
      }
      if (!payload || payload.success !== true) {
        return { ok: false, status: response.status, data: (payload && payload.data) || null,
                 error: (payload && payload.error) || '처리하지 못했어요.' };
      }
      return { ok: true, status: response.status, data: payload.data, error: null };
    } catch (networkError) {
      return { ok: false, status: 0, data: null, error: '연결이 끊겼어요. 잠시 뒤 다시 해 주세요.' };
    }
  }

  /** GET JSON. */
  function getJson(url) {
    return requestJson(url, { headers: { Accept: 'application/json' } });
  }

  /** POST JSON(본문 객체). */
  function postJson(url, body) {
    return requestJson(url, { method: 'POST', body: JSON.stringify(body || {}),
                              headers: { Accept: 'application/json', 'Content-Type': 'application/json' } });
  }

  /** data-* JSON 읽기(틀리면 fallback). */
  function safeJsonParse(value, fallback) {
    try {
      var text = String(value || '').trim();
      return text ? JSON.parse(text) : fallback;
    } catch (error) {
      return fallback;
    }
  }

  window.FOMS_BRAIN_DOM = { el: el, icon: icon, typeChip: typeChip, badgeNodes: badgeNodes, itemRow: itemRow,
                            setStatus: setStatus, clear: clear, getJson: getJson, postJson: postJson,
                            safeJsonParse: safeJsonParse };
})();
