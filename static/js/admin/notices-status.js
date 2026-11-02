/**
 * FOMS 공지사항 확인 현황(설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §3 ack_status · §5).
 * GET /api/admin/notices/<id>/status → {total, acked, staff:{total,acked,people}, partner:{total,acked,people}}.
 * 진행 막대는 <progress> 값으로만 그린다(인라인 스타일 없음). 기본은 "안 한 사람만".
 * 글은 textContent 로만 넣는다(innerHTML 없음).
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-notice-status]');
  if (!root) return;
  var statusUrl = root.getAttribute('data-status-url');
  var peopleBox = root.querySelector('[data-status-people]');
  var onlyPending = root.querySelector('[data-status-only-pending]');
  var messageBox = root.querySelector('[data-notice-message]');
  var refreshBtn = root.querySelector('[data-status-refresh]');
  var activeTab = 'staff';
  var snapshot = null;

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

  function clearMessage() {
    if (messageBox) messageBox.className = 'alert d-none foms-notice-admin__message';
  }

  async function getJson(url) {
    var response;
    var data = null;
    try {
      response = await fetch(url, { credentials: 'same-origin', headers: { 'Accept': 'application/json' } });
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
      return { ok: false, data: null, error: data.error || '불러오지 못했습니다(' + response.status + ').' };
    }
    return { ok: true, data: data.data || {}, error: null };
  }

  /** '2026-11-02T09:30:12' · '2026-11-02 09:30' → '11-02 09:30'. 모르는 모양이면 그대로. */
  function shortTime(value) {
    var text = String(value || '').replace('T', ' ');
    var match = text.match(/^\d{4}-(\d{2}-\d{2}) (\d{2}:\d{2})/);
    return match ? match[1] + ' ' + match[2] : text;
  }

  function num(value) {
    var n = Number(value);
    return isFinite(n) ? n : 0;
  }

  function renderSummary(data) {
    var total = num(data.total);
    var acked = num(data.acked);
    var pct = total ? Math.round((acked / total) * 100) : 0;
    root.querySelector('[data-status-summary]').textContent =
      '받는 사람 ' + total + '명 중 ' + acked + '명 확인 · ' + (total - acked) + '명 아직';
    root.querySelector('[data-status-pct]').textContent = pct + '%';
    var bar = root.querySelector('[data-status-progress]');
    bar.max = total || 1;
    bar.value = acked;
    bar.textContent = pct + '%';
    ['staff', 'partner'].forEach(function (side) {
      var part = data[side] || {};
      root.querySelector('[data-status-tab-count="' + side + '"]').textContent =
        num(part.acked) + ' / ' + num(part.total);
    });
  }

  function personRow(person, side) {
    var row = el('li', 'foms-notice-person');
    var who = el('div', 'foms-notice-person__who');
    who.appendChild(el('span', 'foms-notice-person__name', person.name || ('사용자 ' + person.user_id)));
    var group = side === 'partner' ? person.org_name : person.team_label;
    if (group) who.appendChild(el('span', 'foms-notice-tag foms-notice-tag--' + side, group));
    row.appendChild(who);
    var stateText;
    var stateKey;
    if (person.acked_at) {
      stateKey = 'acked';
      stateText = '확인 ' + shortTime(person.acked_at);
    } else if (person.read_at) {
      stateKey = 'read';
      stateText = '읽기만 ' + shortTime(person.read_at);
    } else {
      stateKey = 'pending';
      stateText = '아직 안 봄';
    }
    row.appendChild(el('span', 'foms-notice-person__state foms-notice-person__state--' + stateKey, stateText));
    return row;
  }

  function renderPeople() {
    peopleBox.textContent = '';
    if (!snapshot) return;
    var part = snapshot[activeTab] || {};
    var people = Array.isArray(part.people) ? part.people : [];
    var pendingOnly = onlyPending && onlyPending.checked;
    var shown = people.filter(function (person) { return !pendingOnly || !person.acked_at; });
    if (!shown.length) {
      var empty = !people.length
        ? (activeTab === 'staff' ? '본사 받는 사람이 없어요.' : '협력사 받는 사람이 없어요.')
        : '모두 확인했어요.';
      peopleBox.appendChild(el('li', 'foms-notice-empty', empty));
      return;
    }
    shown.forEach(function (person) { peopleBox.appendChild(personRow(person, activeTab)); });
  }

  function selectTab(side) {
    activeTab = side;
    root.querySelectorAll('[data-status-tab]').forEach(function (tab) {
      tab.setAttribute('aria-selected', tab.getAttribute('data-status-tab') === side ? 'true' : 'false');
    });
    renderPeople();
  }

  async function load() {
    if (refreshBtn) refreshBtn.disabled = true;
    var result = await getJson(statusUrl);
    if (refreshBtn) refreshBtn.disabled = false;
    if (!result.ok) {
      root.querySelector('[data-status-summary]').textContent = '확인 현황을 불러오지 못했어요.';
      message('danger', result.error);
      return;
    }
    clearMessage();
    snapshot = result.data;
    renderSummary(snapshot);
    var staffTotal = num((snapshot.staff || {}).total);
    var partnerTotal = num((snapshot.partner || {}).total);
    if (activeTab === 'staff' && !staffTotal && partnerTotal) activeTab = 'partner';
    selectTab(activeTab);
  }

  root.addEventListener('click', function (event) {
    var tab = event.target.closest('[data-status-tab]');
    if (tab) selectTab(tab.getAttribute('data-status-tab'));
  });
  if (onlyPending) onlyPending.addEventListener('change', renderPeople);
  if (refreshBtn) refreshBtn.addEventListener('click', load);

  load();
})();
