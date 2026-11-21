/**
 * "오늘 끝낸 제품" 체크 목록 — 제품마다 시공 끝(한 주문 여러 시공일 2단계, 설계서
 * docs/specs/2026-11-21-item-construction-done_SPEC.md 6절 · 결정 N2 · N3).
 *
 * 태블릿 · 폰 완료 준비 창(foms-complete-gate.js)과 PC 시공 대시보드 완료 창(dashboard.js)이 함께 쓴다.
 * - GET /api/orders/<id>/construction/visit-items?date=<그 줄의 날 또는 오늘> 로 남은 제품을 받는다.
 * - 나눠 시공하는 주문이 아니면(split=false · 제품 없음) 아무것도 그리지 않는다 — 창이 지금과 같다.
 * - 그날이 마지막 시공일인 제품은 미리 체크(precheck), 뒤 날짜가 남은 제품은 "11/17 시공 남음" 과 함께 빈 칸.
 * - 남은 제품을 다 고르면 단추 글은 원래 글([시공 완료]), 아니면 "오늘 시공 끝 — 남은 제품 N개".
 * - 보낼 때 done_item_uids = 고른 제품의 ref.
 * 그날은 줄 · 카드 뿌리의 data-visit-date(서버가 나눠 시공 줄에만 싣는다)를 먼저 읽고, 없으면 오늘이다.
 */
(function () {
  'use strict';

  if (window.FomsVisitItems) {
    return;
  }

  var SECTION_SEL = '[data-foms-visit-items]';
  var CHECK_SEL = 'input[data-foms-visit-item]';

  function pad(n) {
    return (n < 10 ? '0' : '') + n;
  }

  function todayIso() {
    var d = new Date();
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  }

  function visitDate(orderId) {
    var src = document.querySelector('[data-visit-date][data-order-id="' + String(orderId) + '"]');
    var v = src ? String(src.getAttribute('data-visit-date') || '') : '';
    return /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : todayIso();
  }

  /**
   * 남은 제품 목록을 받는다. 나눠 시공이 아니거나 실패하면 null(창은 지금과 같다).
   * @param {string|number} orderId
   * @returns {Promise<Object|null>} data.data ({split, items, done, remaining_summary})
   */
  async function load(orderId) {
    var url = '/api/orders/' + encodeURIComponent(String(orderId)) + '/construction/visit-items?date='
      + encodeURIComponent(visitDate(orderId));
    try {
      var res = await fetch(url, { credentials: 'same-origin' });
      var body = await res.json();
      if (!body || !body.success || !body.data) {
        return null;
      }
      var d = body.data;
      if (!d.split || !Array.isArray(d.items) || !d.items.length) {
        return null;
      }
      return d;
    } catch (_) {
      return null;
    }
  }

  function remove(host) {
    var old = host ? host.querySelector(SECTION_SEL) : null;
    if (old && old.parentNode) {
      old.parentNode.removeChild(old);
    }
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
  }

  function itemRow(item) {
    var label = el('label', 'foms-visit-items__row');
    var box = document.createElement('input');
    box.type = 'checkbox';
    box.className = 'foms-visit-items__box';
    box.setAttribute('data-foms-visit-item', '');
    box.value = String(item.ref || '');
    box.checked = !!item.precheck;
    label.appendChild(box);
    label.appendChild(el('span', 'foms-visit-items__name', String(item.name || '')));
    if (!item.precheck && item.last_label) {
      label.appendChild(el('span', 'foms-visit-items__later', item.last_label + ' 시공 남음'));
    }
    return label;
  }

  /**
   * 체크 목록을 anchor 바로 뒤에 그린다(이미 있으면 바꾼다).
   * @param {Element} host 창 뿌리(한 창에 목록 하나)
   * @param {Element} anchor 이 요소 뒤에 넣는다
   * @param {Object} data load() 결과
   * @param {function(): void} onChange 체크가 바뀔 때
   * @returns {Element} 목록 section
   */
  function render(host, anchor, data, onChange) {
    remove(host);
    var section = el('section', 'foms-visit-items');
    section.setAttribute('data-foms-visit-items', '');
    section.setAttribute('aria-label', '오늘 끝낸 제품');
    section.appendChild(el('div', 'foms-visit-items__title', '오늘 끝낸 제품'));
    data.items.forEach(function (item) {
      section.appendChild(itemRow(item));
    });
    section.addEventListener('change', function (ev) {
      if (ev.target && ev.target.matches && ev.target.matches(CHECK_SEL) && typeof onChange === 'function') {
        onChange();
      }
    });
    if (anchor && anchor.parentNode) {
      anchor.parentNode.insertBefore(section, anchor.nextSibling);
    } else if (host) {
      host.appendChild(section);
    }
    return section;
  }

  function boxes(host) {
    var section = host ? host.querySelector(SECTION_SEL) : null;
    return section ? Array.prototype.slice.call(section.querySelectorAll(CHECK_SEL)) : null;
  }

  /** 목록이 있으면 고른 ref 배열, 목록이 없으면 null(나눠 시공 아님 — 몸에 넣지 않는다). */
  function selected(host) {
    var list = boxes(host);
    if (!list) return null;
    return list.filter(function (b) { return b.checked; }).map(function (b) { return b.value; });
  }

  /** 단추 글 — 목록이 없거나 남은 제품을 다 골랐으면 fallback, 아니면 "오늘 시공 끝 — 남은 제품 N개". */
  function buttonLabel(host, fallback) {
    var list = boxes(host);
    if (!list) return fallback;
    var left = list.filter(function (b) { return !b.checked; }).length;
    return left ? ('오늘 시공 끝 — 남은 제품 ' + left + '개') : fallback;
  }

  /**
   * 완료 응답이 부분 방문(mode=visit)이면 짧은 알림을 띄우고 true. 아니면 false.
   * @param {Object} payload 응답의 data 칸
   */
  function notifyVisit(payload) {
    if (!payload || payload.mode !== 'visit') return false;
    var text = '오늘 시공 끝' + (payload.remaining_summary ? ' — 남은 시공 ' + payload.remaining_summary : '');
    if (typeof window.fomsShowToast === 'function') {
      window.fomsShowToast(text);
    } else {
      window.alert(text);
    }
    return true;
  }

  window.FomsVisitItems = {
    load: load,
    render: render,
    remove: remove,
    selected: selected,
    buttonLabel: buttonLabel,
    notifyVisit: notifyVisit,
    TOAST_WAIT_MS: 1200
  };
})();
