/**
 * "오늘 끝낸 제품" 체크 목록 — 제품마다 시공 끝(한 주문 여러 시공일 2단계, 설계서
 * docs/specs/2026-11-21-item-construction-done_SPEC.md 6절 · 결정 N2 · N3).
 *
 * 태블릿 · 폰 완료 준비 창(foms-complete-gate.js)과 PC 시공 대시보드 완료 창(dashboard.js)이 함께 쓴다.
 * - GET /api/orders/<id>/construction/visit-items?date=<그 줄의 날 또는 오늘> 로 남은 제품을 받는다.
 * - 나눠 시공하는 주문이 아니면(split=false · 제품 없음) 아무것도 그리지 않는다 — 창이 지금과 같다.
 * - 그날이 마지막 시공일인 제품은 미리 체크(precheck), 뒤 날짜가 남은 제품은 "11/17 시공 남음" 과 함께 빈 칸.
 * - 남은 제품을 다 고르면 단추 글은 원래 글([시공 완료]), 아니면 "오늘 시공 끝 — 남은 제품 N개".
 *   하나도 안 고르면 단추를 끈다(blocked).
 * - 나눠 시공 줄(data-visit-date 가 있는 줄)인데 목록을 못 읽으면 "다시 읽기" 글 단추를 그리고 단추를 끈다.
 *   나눠 시공인지 모르는 줄은 못 읽어도 아무것도 그리지 않는다(지금과 같다).
 * - 보낼 때 done_item_uids = 고른 제품의 ref, visit_date = 그날.
 * 그날은 줄 · 카드 뿌리의 data-visit-date(서버가 나눠 시공 줄에만 싣는다)를 먼저 읽고, 없으면 오늘이다.
 */
(function () {
  'use strict';

  if (window.FomsVisitItems) {
    return;
  }

  var SECTION_SEL = '[data-foms-visit-items]';
  var CHECK_SEL = 'input[data-foms-visit-item]';
  var FAILED = { failed: true };

  function pad(n) {
    return (n < 10 ? '0' : '') + n;
  }

  function todayIso() {
    var d = new Date();
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  }

  function splitRow(orderId) {
    return document.querySelector('[data-visit-date][data-order-id="' + String(orderId) + '"]');
  }

  /** 완료 창이 고를 날 — 나눠 시공 줄의 data-visit-date, 없으면 오늘. */
  function visitDate(orderId) {
    var src = splitRow(orderId);
    var v = src ? String(src.getAttribute('data-visit-date') || '') : '';
    return /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : todayIso();
  }

  /**
   * 남은 제품 목록을 받는다.
   * @param {string|number} orderId
   * @returns {Promise<Object|null>} 목록 자료(data.data), 나눠 시공 아님 = null, 못 읽음 = {failed: true}
   */
  async function load(orderId) {
    var url = '/api/orders/' + encodeURIComponent(String(orderId)) + '/construction/visit-items?date='
      + encodeURIComponent(visitDate(orderId));
    try {
      var res = await fetch(url, { credentials: 'same-origin' });
      var body = await res.json();
      if (!body || !body.success || !body.data) {
        return FAILED;
      }
      var d = body.data;
      if (!d.split || !Array.isArray(d.items) || !d.items.length) {
        return null;
      }
      return d;
    } catch (_) {
      return FAILED;
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

  function place(host, anchor, section) {
    if (anchor && anchor.parentNode) {
      anchor.parentNode.insertBefore(section, anchor.nextSibling);
    } else if (host) {
      host.appendChild(section);
    }
  }

  function shell() {
    var section = el('section', 'foms-visit-items');
    section.setAttribute('data-foms-visit-items', '');
    section.setAttribute('aria-label', '오늘 끝낸 제품');
    section.appendChild(el('div', 'foms-visit-items__title', '오늘 끝낸 제품'));
    return section;
  }

  /** 체크 목록을 anchor 바로 뒤에 그린다(이미 있으면 바꾼다). */
  function render(host, anchor, data, onChange) {
    remove(host);
    var section = shell();
    data.items.forEach(function (item) {
      section.appendChild(itemRow(item));
    });
    section.addEventListener('change', function (ev) {
      if (ev.target && ev.target.matches && ev.target.matches(CHECK_SEL) && typeof onChange === 'function') {
        onChange();
      }
    });
    place(host, anchor, section);
    return section;
  }

  /** 못 읽은 자리 — "제품 목록을 못 읽었어요" + [다시 읽기]. 이 자리가 있으면 완료 단추를 끈다. */
  function renderRetry(host, anchor, onRetry) {
    remove(host);
    var section = shell();
    section.setAttribute('data-foms-visit-items-failed', '');
    var line = el('div', 'foms-visit-items__failed', '제품 목록을 못 읽었어요 ');
    var btn = el('button', 'foms-visit-items__retry', '다시 읽기');
    btn.type = 'button';
    btn.addEventListener('click', function (ev) {
      ev.preventDefault();
      onRetry();
    });
    line.appendChild(btn);
    section.appendChild(line);
    place(host, anchor, section);
    return section;
  }

  /**
   * 목록을 읽어 그린다. 그린 뒤(또는 못 읽은 자리를 그린 뒤) onChange 를 부른다.
   * @param {Element} host 창 뿌리(한 창에 목록 하나)
   * @param {function(): Element} anchorOf 넣을 자리(이 요소 뒤)
   * @param {string|number} orderId
   * @param {function(): boolean} stillOpen 그 창이 아직 이 주문으로 열려 있나(늦은 응답 버림)
   * @param {function(): void} onChange 체크 · 상태가 바뀔 때
   */
  function mount(host, anchorOf, orderId, stillOpen, onChange) {
    remove(host);
    return load(orderId).then(function (d) {
      if (!stillOpen()) return;
      if (d && d.failed) {
        if (splitRow(orderId)) {
          renderRetry(host, anchorOf(), function () { mount(host, anchorOf, orderId, stillOpen, onChange); });
        }
      } else if (d) {
        render(host, anchorOf(), d, onChange);
      }
      if (typeof onChange === 'function') onChange();
    });
  }

  function boxes(host) {
    var section = host ? host.querySelector(SECTION_SEL) : null;
    if (!section || section.hasAttribute('data-foms-visit-items-failed')) return null;
    return Array.prototype.slice.call(section.querySelectorAll(CHECK_SEL));
  }

  /** 목록이 있으면 고른 ref 배열, 목록이 없으면 null(나눠 시공 아님 — 몸에 넣지 않는다). */
  function selected(host) {
    var list = boxes(host);
    if (!list) return null;
    return list.filter(function (b) { return b.checked; }).map(function (b) { return b.value; });
  }

  /** 완료 단추를 꺼야 하나 — 못 읽은 자리가 있거나, 목록이 있는데 하나도 안 골랐다. */
  function blocked(host) {
    var section = host ? host.querySelector(SECTION_SEL) : null;
    if (!section) return false;
    if (section.hasAttribute('data-foms-visit-items-failed')) return true;
    var picked = selected(host);
    return !!picked && picked.length === 0;
  }

  /** 남은 제품이 남는 선택인가(목록이 있고 안 고른 제품이 있다). */
  function leavesRemaining(host) {
    var list = boxes(host);
    return !!list && list.some(function (b) { return !b.checked; });
  }

  /** 단추 글 — 목록이 없거나 남은 제품을 다 골랐으면 fallback, 아니면 "오늘 시공 끝 — 남은 제품 N개". */
  function buttonLabel(host, fallback) {
    var list = boxes(host);
    if (!list) return fallback;
    var left = list.filter(function (b) { return !b.checked; }).length;
    return left ? ('오늘 시공 끝 — 남은 제품 ' + left + '개') : fallback;
  }

  /** 완료 요청 몸에 고른 제품 · 그날을 더한다(목록이 없으면 몸 그대로 — 지금과 같다). */
  function extendBody(host, orderId, body) {
    var refs = selected(host);
    if (refs) {
      body.done_item_uids = refs;
      body.visit_date = visitDate(orderId);
    }
    return body;
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
    mount: mount,
    render: render,
    remove: remove,
    selected: selected,
    blocked: blocked,
    leavesRemaining: leavesRemaining,
    buttonLabel: buttonLabel,
    extendBody: extendBody,
    visitDate: visitDate,
    notifyVisit: notifyVisit,
    TOAST_WAIT_MS: 1200
  };
})();
