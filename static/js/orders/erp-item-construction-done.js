/**
 * 주문 화면 제품 줄 "11/05 시공 끝" · [되돌리기] (제품마다 시공 끝 2단계, 설계서
 * docs/specs/2026-11-21-item-construction-done_SPEC.md 6절 · 결정 N9).
 *
 * 자료 = #erp-items[data-item-construction-done] (서버 판정 item_construction_done_view — 스위치가 켜져 있고
 * 나눠 시공하는 주문이며 '시공 끝' 기록이 있을 때만 실린다. 없으면 이 파일은 아무것도 하지 않는다).
 *   {order_id, records: [{uid, name, label}], can_undo}
 * 제품 줄(.erp-item-row[data-item-uid])은 erp-order-shared.js 가 그린 뒤에도 다시 그려질 수 있어
 * #erp-items 의 자식 변화를 지켜보다 줄마다 한 번씩 글을 단다.
 * [되돌리기]는 관리자 · 매니저 · CS 에게만(can_undo) — 사유를 받아
 * POST /api/orders/<id>/items/<uid>/construction-done/undo {reason} → 성공하면 화면을 다시 읽는다.
 * 사유 창은 그 화면의 공용 사유 시트(window.FomsReasonSheet), 없으면 window.prompt.
 * 셸 조각 로더(fragment-loader.js)는 src 스크립트를 한 번만 실행한다 — 태블릿 나눠 보기에서 주문 A → B 를 열면
 * #erp-items 가 새로 생기므로 foms:main-content-swapped 때 start() 를 다시 돌려 옛 지켜보기를 끊고 새 칸을 찾는다.
 * 싱글턴 가드는 문서 클릭 위임 · 이벤트 연결에만 둔다.
 */
(function () {
  'use strict';

  var HOST_SEL = '#erp-items[data-item-construction-done]';
  var LINE_CLASS = 'erp-item-done-line';
  var UNDO_SEL = '[data-erp-item-done-undo]';
  var REASON_MAX = 200;

  function safeJsonParse(val, fb) {
    try {
      var s = String(val || '').trim();
      if (!s) return fb;
      var o = JSON.parse(s);
      return (o && typeof o === 'object') ? o : fb;
    } catch (_) {
      return fb;
    }
  }

  function readConfig(host) {
    var cfg = safeJsonParse(host.getAttribute('data-item-construction-done'), null);
    if (!cfg || !Array.isArray(cfg.records) || !cfg.records.length) return null;
    return cfg;
  }

  function lineFor(record, canUndo) {
    var line = document.createElement('div');
    line.className = LINE_CLASS;
    var text = document.createElement('span');
    text.textContent = String(record.label || '시공 끝');
    line.appendChild(text);
    if (canUndo) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'erp-item-done-line__undo';
      btn.setAttribute('data-erp-item-done-undo', '');
      btn.setAttribute('data-uid', String(record.uid || ''));
      btn.setAttribute('data-name', String(record.name || ''));
      btn.textContent = '되돌리기';
      line.appendChild(btn);
    }
    return line;
  }

  function decorate(host) {
    var cfg = readConfig(host);
    if (!cfg) return;
    cfg.records.forEach(function (record) {
      if (!record || !record.uid) return;
      var row = host.querySelector('.erp-item-row[data-item-uid="' + String(record.uid) + '"]');
      if (!row || row.querySelector('.' + LINE_CLASS)) return;
      var head = row.firstElementChild;
      var line = lineFor(record, !!cfg.can_undo);
      if (head && head.nextSibling) {
        row.insertBefore(line, head.nextSibling);
      } else {
        row.appendChild(line);
      }
    });
  }

  function askReason(name, onReason) {
    var sheet = window.FomsReasonSheet;
    if (sheet && typeof sheet.open === 'function' && document.querySelector('[data-foms-reason-sheet]')) {
      sheet.open({
        title: '시공 끝 되돌리기',
        actionLabel: '되돌리기',
        reasons: null,
        detailLabel: (name ? name + ' — ' : '') + '되돌리는 사유',
        requireDetail: true,
        onSubmit: function (_code, detail) {
          onReason(String(detail || '').trim());
        }
      });
      return;
    }
    var typed = window.prompt((name ? name + ' ' : '') + '시공 끝 표시를 지웁니다. 사유를 적어 주세요.', '');
    if (typed === null) return;
    var reason = String(typed).trim();
    if (!reason) {
      window.alert('사유를 적어 주세요.');
      return;
    }
    onReason(reason);
  }

  async function sendUndo(btn, orderId, uid, reason) {
    if (btn.getAttribute('data-busy') === '1') return;
    if (reason.length > REASON_MAX) {
      window.alert('사유는 ' + REASON_MAX + '자까지 적을 수 있어요.');
      return;
    }
    btn.setAttribute('data-busy', '1');
    btn.disabled = true;
    try {
      var res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/items/' + encodeURIComponent(uid)
        + '/construction-done/undo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
        body: JSON.stringify({ reason: reason })
      });
      var data = null;
      try {
        data = await res.json();
      } catch (_) {
        data = null;
      }
      if (!data || !data.success) {
        throw new Error((data && (data.error || data.message)) || '시공 끝 표시를 되돌리지 못했습니다.');
      }
      window.location.reload();
    } catch (err) {
      window.alert(String((err && err.message) || err || '시공 끝 표시를 되돌리지 못했습니다.'));
      btn.removeAttribute('data-busy');
      btn.disabled = false;
    }
  }

  function onClick(event) {
    var target = event.target;
    var btn = target && target.closest ? target.closest(UNDO_SEL) : null;
    if (!btn) return;
    event.preventDefault();
    var host = btn.closest(HOST_SEL);
    var cfg = host ? readConfig(host) : null;
    var uid = btn.getAttribute('data-uid') || '';
    if (!cfg || !cfg.can_undo || !cfg.order_id || !uid) return;
    askReason(btn.getAttribute('data-name') || '', function (reason) {
      sendUndo(btn, cfg.order_id, uid, reason);
    });
  }

  /**
   * 지금 문서의 #erp-items 를 찾아 글을 달고 지켜본다. 옛 지켜보기는 끊는다(조각 교체마다 다시 부른다).
   * 지켜보기는 window 에 하나만 둔다 — 파일이 두 번 실려도 앞 실행의 지켜보기까지 끊긴다.
   */
  function start() {
    if (window.__fomsItemDoneObserver) {
      window.__fomsItemDoneObserver.disconnect();
      window.__fomsItemDoneObserver = null;
    }
    var host = document.querySelector(HOST_SEL);
    if (!host) return;
    decorate(host);
    if (typeof MutationObserver === 'function') {
      var observer = new MutationObserver(function () { decorate(host); });
      observer.observe(host, { childList: true, subtree: true });
      window.__fomsItemDoneObserver = observer;
    }
  }

  window.FomsItemConstructionDone = { start: start };

  if (!window.__FOMS_ITEM_DONE_BOUND) {
    window.__FOMS_ITEM_DONE_BOUND = true;
    document.addEventListener('click', onClick);
    document.addEventListener('foms:main-content-swapped', function () { window.FomsItemConstructionDone.start(); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
