/**
 * FOMS 공지사항 관리자 목록(설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §5).
 * GET /api/admin/notices 로 읽어 줄을 그리고, 지우기는 DELETE /api/admin/notices/<id>(soft) 로 보낸다.
 * CSRF 토큰은 공용 csrf_bootstrap 의 fetch 래퍼가 붙인다. 글은 textContent 로만 넣는다(innerHTML 없음).
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-notice-list]');
  if (!root) return;
  var listBody = root.querySelector('[data-notice-list-body]');
  var messageBox = root.querySelector('[data-notice-message]');
  var apiUrl = root.getAttribute('data-api-url') || '/api/admin/notices';
  var pageBase = root.getAttribute('data-page-base') || '/admin/notices';
  var MODE_LABELS = { POPUP: '확인 창', LIST: '목록에만' };

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function message(kind, text) {
    if (!messageBox) return;
    messageBox.className = 'alert foms-notice-admin__message alert-' + kind;
    messageBox.textContent = text;
  }

  async function requestJson(url, method) {
    var response;
    var data = null;
    try {
      response = await fetch(url, {
        method: method || 'GET',
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' }
      });
    } catch (err) {
      return { ok: false, data: null, error: '서버에 닿지 못했습니다. 인터넷 연결을 확인해 주세요.' };
    }
    try {
      data = await response.json();
    } catch (err) {
      data = null;
    }
    if (!data || typeof data !== 'object') {
      return { ok: false, data: null, error: '응답을 읽지 못했습니다(' + response.status + ').' };
    }
    if (!response.ok || !data.success) {
      return { ok: false, data: null, error: data.error || '처리하지 못했습니다(' + response.status + ').' };
    }
    return { ok: true, data: data.data, error: null };
  }

  /** '2026-11-02T09:30' · '2026-11-02 09:30:00' → '11-02 09:30'. 모르는 모양이면 그대로. */
  function shortTime(value) {
    var text = String(value || '').replace('T', ' ');
    var match = text.match(/^\d{4}-(\d{2}-\d{2}) (\d{2}:\d{2})/);
    return match ? match[1] + ' ' + match[2] : text;
  }

  function toDate(value) {
    if (!value) return null;
    var parsed = new Date(String(value).replace(' ', 'T'));
    return isNaN(parsed.getTime()) ? null : parsed;
  }

  function stateOf(item) {
    var now = new Date();
    var starts = toDate(item.starts_at);
    var ends = toDate(item.ends_at);
    if (starts && starts > now) return { key: 'scheduled', label: '예정' };
    if (ends && ends <= now) return { key: 'ended', label: '끝남' };
    return { key: 'live', label: '게시 중' };
  }

  /** "본사 전체 + 협력사: 라운즈" → 칩 두 개(본사 = 보라, 협력사 = 하늘). */
  function audienceChips(label) {
    var wrap = el('span', 'foms-notice-row__chips');
    String(label || '').split(' + ').forEach(function (part) {
      var text = part.trim();
      if (!text) return;
      var side = text.indexOf('협력사') === 0 ? 'partner' : 'staff';
      wrap.appendChild(el('span', 'foms-notice-tag foms-notice-tag--' + side, text));
    });
    return wrap;
  }

  function periodText(item) {
    if (!item.starts_at && !item.ends_at) return '기간 없음(계속)';
    var from = item.starts_at ? shortTime(item.starts_at) : '바로';
    var to = item.ends_at ? shortTime(item.ends_at) : '계속';
    return from + ' ~ ' + to;
  }

  function link(href, text, className) {
    var anchor = el('a', className, text);
    anchor.href = href;
    return anchor;
  }

  function renderRow(item) {
    var row = el('article', 'foms-notice-row');
    row.setAttribute('data-notice-id', String(item.id));
    var main = el('div', 'foms-notice-row__main');
    var badges = el('div', 'foms-notice-row__badges');
    if (item.pinned) badges.appendChild(el('span', 'foms-notice-badge foms-notice-badge--pin', '맨 위 고정'));
    var state = stateOf(item);
    badges.appendChild(el('span', 'foms-notice-badge foms-notice-badge--' + state.key, state.label));
    badges.appendChild(el('span', 'foms-notice-badge', MODE_LABELS[item.display_mode] || item.display_mode || ''));
    main.appendChild(badges);
    main.appendChild(link(pageBase + '/' + item.id + '/status', item.title || '(제목 없음)', 'foms-notice-row__title'));
    var meta = el('div', 'foms-notice-row__meta');
    meta.appendChild(audienceChips(item.audience_label));
    meta.appendChild(el('span', null, (item.created_by_name || '') + ' · ' + shortTime(item.created_at)));
    meta.appendChild(el('span', null, '게시 ' + periodText(item)));
    main.appendChild(meta);
    row.appendChild(main);

    var side = el('div', 'foms-notice-row__side');
    var ack = item.ack || {};
    var total = Number(ack.total) || 0;
    var acked = Number(ack.acked) || 0;
    side.appendChild(el('span', 'foms-notice-row__ack', '확인 ' + acked + ' / ' + total + '명'));
    var bar = el('progress', 'foms-notice-progress foms-notice-progress--small');
    bar.max = total || 1;
    bar.value = acked;
    side.appendChild(bar);
    var actions = el('div', 'foms-notice-row__actions');
    actions.appendChild(link(pageBase + '/' + item.id + '/status', '확인 현황', 'foms-notice-btn foms-notice-btn--ghost'));
    actions.appendChild(link(pageBase + '/' + item.id + '/edit', '고치기', 'foms-notice-btn foms-notice-btn--ghost'));
    var del = el('button', 'foms-notice-btn foms-notice-btn--danger', '지우기');
    del.type = 'button';
    del.setAttribute('data-notice-delete', String(item.id));
    del.setAttribute('data-notice-title', item.title || '');
    actions.appendChild(del);
    side.appendChild(actions);
    row.appendChild(side);
    return row;
  }

  function render(items) {
    listBody.textContent = '';
    if (!items.length) {
      listBody.appendChild(el('p', 'foms-notice-empty', '아직 쓴 공지가 없어요. [공지 쓰기]를 눌러 첫 공지를 올려 보세요.'));
      return;
    }
    items.forEach(function (item) { listBody.appendChild(renderRow(item)); });
  }

  async function load() {
    var result = await requestJson(apiUrl, 'GET');
    if (!result.ok) {
      listBody.textContent = '';
      listBody.appendChild(el('p', 'foms-notice-empty', '공지를 불러오지 못했어요.'));
      message('danger', result.error);
      return;
    }
    var data = result.data;
    var items = Array.isArray(data) ? data : (data && Array.isArray(data.items) ? data.items : []);
    render(items);
  }

  async function onDelete(button) {
    var title = button.getAttribute('data-notice-title') || '이 공지';
    if (!window.confirm('"' + title + '" 공지를 지울까요? 받는 사람 화면에서도 사라져요.')) return;
    button.disabled = true;
    var result = await requestJson(apiUrl + '/' + button.getAttribute('data-notice-delete'), 'DELETE');
    if (!result.ok) {
      button.disabled = false;
      message('danger', result.error);
      return;
    }
    message('success', '공지를 지웠어요.');
    load();
  }

  listBody.addEventListener('click', function (event) {
    var button = event.target.closest('[data-notice-delete]');
    if (button) onDelete(button);
  });

  try {
    var flashText = window.sessionStorage.getItem('foms-notice-flash');
    if (flashText) {
      window.sessionStorage.removeItem('foms-notice-flash');
      message('success', flashText);
    }
  } catch (err) { /* sessionStorage 막힘 — 글만 안 보인다 */ }

  load();
})();
