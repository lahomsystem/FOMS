/**
 * 관리자 — 영업별 휴대폰 알림(Web Push) 구독 상태 표.
 *
 * templates/admin/notifications_send.html 의 [data-push-status-table] 영역에
 * GET /erp/api/notifications/push/subscriptions-status 결과를 표로 그린다.
 * 사용자 값(이름·아이디·플랫폼)은 textContent 로만 넣는다(innerHTML 금지).
 */
(function () {
  'use strict';
  if (window.__FOMS_PUSH_STATUS_TABLE_BOUND) return;
  window.__FOMS_PUSH_STATUS_TABLE_BOUND = true;

  var STATUS_URL = '/erp/api/notifications/push/subscriptions-status?team=SALES';
  var COLUMNS = [
    { key: 'name', label: '이름' },
    { key: 'username', label: '아이디' },
    { key: 'team', label: '팀' },
    { key: 'active_subscriptions', label: '구독 기기' },
    { key: 'platform', label: '기기' },
    { key: 'permission_state', label: '권한' },
    { key: 'last_seen_at', label: '마지막 접속' },
    { key: 'last_push_at', label: '마지막 발송' }
  ];

  function areaEl() {
    return document.querySelector('[data-push-status-table]');
  }

  function showMessage(text) {
    var area = areaEl();
    if (!area) return;
    area.replaceChildren();
    var p = document.createElement('p');
    p.className = 'text-muted small mb-0';
    p.setAttribute('data-push-status-message', '');
    p.textContent = text;
    area.appendChild(p);
  }

  function cellText(row, key) {
    var value = row[key];
    if (value === null || value === undefined || value === '') return '-';
    return String(value);
  }

  function buildTable(rows) {
    var table = document.createElement('table');
    table.className = 'table table-sm table-hover align-middle mb-0';
    var thead = document.createElement('thead');
    var headRow = document.createElement('tr');
    COLUMNS.forEach(function (col) {
      var th = document.createElement('th');
      th.scope = 'col';
      th.textContent = col.label;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    var tbody = document.createElement('tbody');
    rows.forEach(function (row) {
      var tr = document.createElement('tr');
      // 구독 기기 0 = 이 사람은 휴대폰 알림을 못 받는다 — 한눈에 보이게 흐린 경고색.
      if (!row.active_subscriptions) tr.className = 'table-warning';
      COLUMNS.forEach(function (col) {
        var td = document.createElement('td');
        td.textContent = cellText(row, col.key);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    return table;
  }

  async function load() {
    var area = areaEl();
    if (!area) return;
    showMessage('불러오는 중...');
    try {
      var res = await fetch(STATUS_URL, {
        headers: { 'Accept': 'application/json' },
        credentials: 'same-origin'
      });
      var data = await res.json();
      if (!res.ok || !data || !data.success) {
        throw new Error((data && data.error) || ('HTTP ' + res.status));
      }
      var rows = (data.data && data.data.rows) || [];
      if (!rows.length) {
        showMessage('영업팀 활성 사용자가 없습니다.');
        return;
      }
      area.replaceChildren(buildTable(rows));
    } catch (err) {
      console.error('[push-status] load failed', err);
      showMessage('구독 상태를 불러오지 못했습니다.');
    }
  }

  document.addEventListener('click', function (e) {
    if (!e.target || !e.target.closest) return;
    if (e.target.closest('[data-push-status-reload]')) {
      e.preventDefault();
      load();
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', load);
  } else {
    load();
  }
})();
