/**
 * 변경 사유 집계 화면 (ORDER-REASON-00).
 *
 * 숫자는 전부 서버가 센다 — 화면은 그리기만 한다(집계 규칙이 두 벌이 되면 두 값이 갈린다).
 */
(function () {
  'use strict';

  var root = document.getElementById('change-reason-stats');
  if (!root) return;

  var rows = root.querySelector('[data-role="rows"]');
  var summary = root.querySelector('[data-role="summary"]');
  var daysSelect = root.querySelector('[data-role="days"]');

  /** 요약 타일 1개. */
  function tile(label, value, tone) {
    var col = document.createElement('div');
    col.className = 'col-6 col-md-3';
    var box = document.createElement('div');
    box.className = 'border rounded p-2 text-center' + (tone ? ' ' + tone : '');
    var num = document.createElement('div');
    num.className = 'fs-4 fw-bold';
    num.textContent = String(value);
    var cap = document.createElement('div');
    cap.className = 'small text-muted';
    cap.textContent = label;
    box.appendChild(num);
    box.appendChild(cap);
    col.appendChild(box);
    return col;
  }

  function render(data) {
    summary.textContent = '';
    summary.appendChild(tile('사유를 물은 저장', data.required));
    summary.appendChild(tile('사유가 붙은 저장', data.attached));
    summary.appendChild(tile('미입력', data.skipped, data.skipped ? 'border-warning' : ''));
    var rate = data.required ? Math.round((data.attached / data.required) * 100) : 0;
    summary.appendChild(tile('입력률(%)', rate));

    rows.textContent = '';
    data.by_code.forEach(function (entry) {
      var tr = document.createElement('tr');
      var label = document.createElement('td');
      label.textContent = entry.label;
      var count = document.createElement('td');
      count.className = 'text-end';
      count.textContent = String(entry.count);
      tr.appendChild(label);
      tr.appendChild(count);
      rows.appendChild(tr);
    });
  }

  function load() {
    var url = root.dataset.endpoint + '?days=' + encodeURIComponent(daysSelect.value);
    fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (res) { return res.json(); })
      .then(function (payload) {
        if (!payload || payload.success !== true) throw new Error(payload && payload.error);
        render(payload.data);
      })
      .catch(function (error) {
        rows.textContent = '';
        var tr = document.createElement('tr');
        var td = document.createElement('td');
        td.colSpan = 2;
        td.className = 'text-danger';
        td.textContent = '집계를 불러오지 못했습니다: ' + (error.message || '');
        tr.appendChild(td);
        rows.appendChild(tr);
      });
  }

  daysSelect.addEventListener('change', load);
  load();
})();
