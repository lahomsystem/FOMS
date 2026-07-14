/**
 * 출고 패킹 체크리스트 (B6).
 * 카드의 [data-foms-packing-trigger] 클릭 → 바텀시트 열고 GET 로드 →
 * 체크/항목 추가는 POST → 카운터·배지 갱신.
 * fragment 재실행 시 리스너 중복 바인딩 방지: window.__FOMS_PACKING_BOUND 싱글톤.
 */
(function () {
  'use strict';

  if (window.__FOMS_PACKING_BOUND) return;
  window.__FOMS_PACKING_BOUND = true;

  var state = { orderId: null, trigger: null, items: [] };
  var ISSUE_LABELS = { missing: '미입고', damaged: '파손', short: '수량 부족' };
  // P6: 상차 완료 → 출발 보고 2단 확인. 1탭 arm → DEPART_ARM_MS 내 재탭 확정(미확정 시 자동 해제).
  var DEPART_ARM_MS = 3200;
  var DEPART_LABEL = '상차 완료 → 출발 보고';
  var departTimer = null;

  function sheetEl() {
    return document.querySelector('[data-foms-packing-sheet]');
  }

  function q(root, sel) {
    return root ? root.querySelector(sel) : null;
  }

  function getSheetInstance(el) {
    if (!el || typeof bootstrap === 'undefined' || !bootstrap.Offcanvas) return null;
    return bootstrap.Offcanvas.getOrCreateInstance(el);
  }

  function setError(el, message) {
    var box = q(el, '[data-foms-packing-error]');
    if (!box) return;
    box.textContent = message || '';
    box.classList.toggle('d-none', !message);
  }

  // 로딩 스켈레톤(3행 + 텍스트 폴백) — createElement 조립. loader 표시 시 스켈레톤을
  // 채우고, 숨길 때 비운다(정적 템플릿 텍스트는 JS 실행 전 폴백).
  function renderPackingSkeleton(loader) {
    loader.textContent = '';
    loader.setAttribute('role', 'status');
    loader.setAttribute('aria-label', '불러오는 중');
    for (var i = 0; i < 3; i++) {
      var row = document.createElement('div');
      row.className = 'foms-packing-skeleton';
      row.setAttribute('aria-hidden', 'true');
      var box = document.createElement('span');
      box.className = 'foms-packing-skeleton__box';
      var lines = document.createElement('span');
      lines.className = 'foms-packing-skeleton__lines';
      var a = document.createElement('span');
      a.className = 'foms-packing-skeleton__sk foms-packing-skeleton__sk--a';
      var b = document.createElement('span');
      b.className = 'foms-packing-skeleton__sk foms-packing-skeleton__sk--b';
      lines.appendChild(a);
      lines.appendChild(b);
      row.appendChild(box);
      row.appendChild(lines);
      loader.appendChild(row);
    }
    var text = document.createElement('span');
    text.className = 'foms-packing-loading__text';
    text.textContent = '불러오는 중...';
    loader.appendChild(text);
  }

  function setLoading(el, isLoading) {
    var loader = q(el, '[data-foms-packing-loading]');
    if (!loader) return;
    loader.hidden = !isLoading;
    if (isLoading) renderPackingSkeleton(loader);
    else loader.textContent = '';
  }

  function apiUrl(orderId) {
    return '/api/erp/shipment/packing/' + encodeURIComponent(orderId);
  }

  function updateBadge(trigger, checked, total) {
    if (!trigger) return;
    var badge = trigger.querySelector('[data-foms-packing-badge]');
    if (!badge) return;
    badge.textContent = checked + '/' + total;
    badge.hidden = total === 0;
    badge.classList.toggle('foms-packing-badge--done', total > 0 && checked === total);
  }

  function renderSummary(el, checked, total) {
    var count = q(el, '[data-foms-packing-count]');
    if (count) count.textContent = checked + ' / ' + total;
    var done = q(el, '[data-foms-packing-done]');
    if (done) done.hidden = !(total > 0 && checked === total);
  }

  // P6: departed_at ISO → "YYYY. M. D. HH:MM" (ko-KR). 무효 시 빈 문자열.
  function fmtDepartWhen(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleDateString('ko-KR') + ' ' +
      d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
  }

  function setDepartLabel(btn, text) {
    var label = btn && btn.querySelector('[data-foms-packing-depart-label]');
    if (label) label.textContent = text;
  }

  // arm 해제(타이머 clear + armed 표식 제거). 라벨은 renderDepart/호출부가 세팅.
  function resetDepartArm(btn) {
    if (departTimer) { clearTimeout(departTimer); departTimer = null; }
    if (!btn) return;
    btn.setAttribute('data-armed', 'false');
    btn.classList.remove('foms-packing-depart--armed');
  }

  // 헤더 출발 보고 상태 + sticky 버튼 상태를 데이터로 렌더(전 항목 체크 시에만 활성).
  function renderDepart(el, checked, total, departedAt, departedByName) {
    var status = q(el, '[data-foms-packing-departed]');
    if (status) {
      if (departedAt) {
        var when = fmtDepartWhen(departedAt);
        status.textContent = '출발 보고됨' + (when ? ' · ' + when : '') +
          (departedByName ? ' · ' + departedByName : '');
        status.hidden = false;
      } else {
        status.textContent = '';
        status.hidden = true;
      }
    }
    var btn = q(el, '[data-foms-packing-depart]');
    if (!btn) return;
    resetDepartArm(btn);
    if (departedAt) {
      btn.disabled = true;
      btn.classList.add('foms-packing-depart--done');
      setDepartLabel(btn, '출발 보고 완료');
    } else {
      btn.disabled = !(total > 0 && checked === total);
      btn.classList.remove('foms-packing-depart--done');
      setDepartLabel(btn, DEPART_LABEL);
    }
  }

  function armDepart(btn) {
    if (btn.disabled) return;
    if (btn.getAttribute('data-armed') === 'true') {
      submitDepart(btn);
      return;
    }
    btn.setAttribute('data-armed', 'true');
    btn.classList.add('foms-packing-depart--armed');
    setDepartLabel(btn, '한 번 더 탭해 확정');
    if (departTimer) clearTimeout(departTimer);
    departTimer = setTimeout(function () {
      resetDepartArm(btn);
      setDepartLabel(btn, DEPART_LABEL);
    }, DEPART_ARM_MS);
  }

  async function submitDepart(btn) {
    resetDepartArm(btn);
    btn.disabled = true;
    setDepartLabel(btn, '보고 중...');
    var ok = await postPacking({ departed: true });
    // 성공 시 applyData→renderDepart 가 완료 상태로 전환. 실패 시 재시도 가능하게 복구.
    if (!ok) {
      btn.disabled = false;
      setDepartLabel(btn, DEPART_LABEL);
    }
  }

  function rowMeta(item) {
    if (!item.checked || !item.by_name) return '';
    var when = '';
    if (item.at) {
      var d = new Date(item.at);
      if (!isNaN(d.getTime())) {
        when = ' · ' + d.toLocaleDateString('ko-KR') + ' ' +
          d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
      }
    }
    return item.by_name + when;
  }

  function issueTemplateContent(el) {
    var tpl = q(el, '[data-foms-packing-issue-template]');
    return tpl && tpl.content ? tpl.content : null;
  }

  function renderRows(el, items) {
    var list = q(el, '[data-foms-packing-list]');
    if (!list) return;
    var tplContent = issueTemplateContent(el);
    list.textContent = '';
    items.forEach(function (item) {
      var li = document.createElement('li');
      li.className = 'foms-packing-row'
        + (item.checked ? ' foms-packing-row--checked' : '')
        + (item.issue ? ' foms-packing-row--issue' : '');
      li.dataset.key = item.key;

      var main = document.createElement('div');
      main.className = 'foms-packing-row__main';

      var input = document.createElement('input');
      input.type = 'checkbox';
      input.className = 'foms-packing-row__check';
      input.checked = !!item.checked;
      input.setAttribute('data-foms-packing-check', '');
      input.setAttribute('aria-label', item.label);

      var body = document.createElement('div');
      body.className = 'foms-packing-row__body';
      var label = document.createElement('span');
      label.className = 'foms-packing-row__label';
      label.textContent = item.label;
      body.appendChild(label);
      if (item.issue && ISSUE_LABELS[item.issue]) {
        var issueLabel = document.createElement('span');
        issueLabel.className = 'foms-packing-row__issue-label';
        issueLabel.textContent = '누락 · ' + ISSUE_LABELS[item.issue];
        body.appendChild(issueLabel);
      }
      var metaText = rowMeta(item);
      if (metaText) {
        var meta = document.createElement('span');
        meta.className = 'foms-packing-row__meta';
        meta.textContent = metaText;
        body.appendChild(meta);
      }

      var qty = document.createElement('span');
      qty.className = 'foms-packing-row__qty';
      qty.textContent = '×' + (item.qty || 1);

      main.appendChild(input);
      main.appendChild(body);
      main.appendChild(qty);
      li.appendChild(main);

      if (tplContent) {
        var frag = tplContent.cloneNode(true);
        if (item.issue) {
          var activeChip = frag.querySelector('[data-foms-packing-issue-chip="' + item.issue + '"]');
          if (activeChip) activeChip.classList.add('foms-packing-issue-chip--active');
        }
        li.appendChild(frag);
      }

      list.appendChild(li);
    });
  }

  function applyData(el, data) {
    state.items = Array.isArray(data.items) ? data.items : [];
    var total = typeof data.total === 'number' ? data.total : state.items.length;
    var checked = typeof data.checked_count === 'number'
      ? data.checked_count
      : state.items.filter(function (it) { return it.checked; }).length;
    renderRows(el, state.items);
    renderSummary(el, checked, total);
    updateBadge(state.trigger, checked, total);
    renderDepart(el, checked, total, data.departed_at, data.departed_by_name);
  }

  async function request(orderId, options) {
    options = options || {};
    // B7: 쓰기(POST 등)만 공용 래퍼 경유 → 오프라인 시 큐 적재 + sync 배지 갱신. GET은 기존 fetch.
    var isWrite = (options.method || 'GET').toUpperCase() !== 'GET';
    var doFetch = (isWrite && window.fomsWriteFetch) ? window.fomsWriteFetch : fetch;
    var res = await doFetch(apiUrl(orderId), Object.assign({
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    }, options));
    var data = await res.json().catch(function () { return {}; });
    if (!res.ok || !data.success) {
      throw new Error(data.error || data.message || '요청에 실패했습니다.');
    }
    return data.data || {};
  }

  async function loadPacking(orderId) {
    var el = sheetEl();
    if (!el) return;
    setError(el, '');
    setLoading(el, true);
    try {
      var data = await request(orderId, { method: 'GET' });
      applyData(el, data);
    } catch (error) {
      setError(el, String((error && error.message) || error));
    } finally {
      setLoading(el, false);
    }
  }

  async function postPacking(payload) {
    var el = sheetEl();
    if (!el || !state.orderId) return;
    setError(el, '');
    try {
      var data = await request(state.orderId, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
        body: JSON.stringify(payload)
      });
      applyData(el, data);
      return true;
    } catch (error) {
      setError(el, String((error && error.message) || error));
      return false;
    }
  }

  function openSheet(trigger) {
    var orderId = trigger.dataset.orderId;
    if (!orderId) return;
    state.orderId = orderId;
    state.trigger = trigger;
    var el = sheetEl();
    if (el) {
      var sub = q(el, '[data-foms-packing-subtitle]');
      if (sub) sub.textContent = '주문 #' + orderId + ' · 제품별 패킹 항목을 체크하세요.';
      var list = q(el, '[data-foms-packing-list]');
      if (list) list.textContent = '';
      // 이전 주문의 출발 보고 상태가 로드 전까지 잔상으로 남지 않게 초기화.
      renderDepart(el, 0, 0, null, null);
      var instance = getSheetInstance(el);
      if (instance) instance.show();
    }
    loadPacking(orderId);
  }

  document.addEventListener('click', function (event) {
    var trigger = event.target.closest('[data-foms-packing-trigger]');
    if (trigger) {
      event.preventDefault();
      openSheet(trigger);
      return;
    }
    var departBtn = event.target.closest('[data-foms-packing-depart]');
    if (departBtn) {
      event.preventDefault();
      armDepart(departBtn);
      return;
    }
    var issueToggle = event.target.closest('[data-foms-packing-issue-toggle]');
    if (issueToggle) {
      event.preventDefault();
      var toggleRow = issueToggle.closest('.foms-packing-row');
      var chips = toggleRow ? toggleRow.querySelector('[data-foms-packing-issue-chips]') : null;
      if (chips) {
        var show = chips.hidden;
        chips.hidden = !show;
        issueToggle.setAttribute('aria-expanded', show ? 'true' : 'false');
      }
      return;
    }
    var issueChip = event.target.closest('[data-foms-packing-issue-chip]');
    if (issueChip) {
      event.preventDefault();
      var chipRow = issueChip.closest('.foms-packing-row');
      if (!chipRow) return;
      // 활성 칩 재클릭 → 해제(null), 그 외 → 해당 사유로 표기.
      var isActive = issueChip.classList.contains('foms-packing-issue-chip--active');
      var value = isActive ? null : issueChip.getAttribute('data-foms-packing-issue-chip');
      postPacking({ updates: [{ key: chipRow.dataset.key, issue: value }] });
      return;
    }
  });

  document.addEventListener('change', function (event) {
    var check = event.target.closest('[data-foms-packing-check]');
    if (!check) return;
    var row = check.closest('.foms-packing-row');
    if (!row) return;
    var key = row.dataset.key;
    var checked = check.checked;
    row.classList.toggle('foms-packing-row--checked', checked);
    postPacking({ updates: [{ key: key, checked: checked }] }).then(function (ok) {
      if (!ok) check.checked = !checked;
    });
  });

  document.addEventListener('submit', function (event) {
    var form = event.target.closest('[data-foms-packing-add]');
    if (!form) return;
    event.preventDefault();
    var labelInput = form.querySelector('[name="label"]');
    var qtyInput = form.querySelector('[name="qty"]');
    var label = labelInput ? labelInput.value.trim() : '';
    if (!label) {
      if (labelInput) labelInput.focus();
      return;
    }
    var qty = qtyInput ? parseInt(qtyInput.value, 10) : 1;
    if (!qty || qty < 1) qty = 1;
    postPacking({ add: { label: label, qty: qty } }).then(function (ok) {
      if (ok && labelInput) {
        labelInput.value = '';
        if (qtyInput) qtyInput.value = '1';
        labelInput.focus();
      }
    });
  });
})();
