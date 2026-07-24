/**
 * B3 생산 공정 스텝 바텀시트 (모바일 v2 생산 큐).
 *
 * 카드의 [data-foms-prod-steps-open] 탭 → 공용 바텀시트 오픈 →
 * GET /api/orders/<id>/production/steps lazy 로드 → 체크 5행 렌더.
 * 행 탭 → POST {key, done} → 행/헤더/카드 배지 갱신.
 * 카드당 인라인 마크업 반복 금지(fragment 전송 바이트 예산) — 렌더는 전부 시트에서.
 *
 * ERP shell fragment 재실행 대비 window.__FOMS_PROD_STEPS_BOUND 싱글톤 가드(G4).
 * DOM 조립은 createElement/textContent 만 사용(사용자 유래 by_name XSS 차단).
 */
(function () {
  'use strict';
  if (window.__FOMS_PROD_STEPS_BOUND) return;
  window.__FOMS_PROD_STEPS_BOUND = true;

  var SHEET_ID = 'foms-production-steps-sheet';
  var currentOrderId = null;
  var loading = false;

  // B7: 쓰기(POST)만 공용 래퍼 경유 → 오프라인 시 큐 적재 + sync 배지 갱신. GET은 기존 fetch.
  function writeFetch(url, opts) {
    return (window.fomsWriteFetch || fetch)(url, opts);
  }

  // ERR-UX-01: 공용 mutation 에러 parser 경유(timeout/malformed JSON/403/409/428 을
  // 한 곳에서 분류 → { ok, kind, status, data, message }). 절대 reject 하지 않는다.
  // 폴백은 공용 parser 미로드 시에만(로드 순서 방어, foms-write.js 는 defer 순서상 항상 먼저).
  function mutationFetch(url, opts) {
    if (window.fomsMutationFetch) return window.fomsMutationFetch(url, opts);
    return writeFetch(url, opts).then(function (res) {
      return res.json().catch(function () { return null; }).then(function (data) {
        if (data === null) {
          return { ok: false, kind: 'malformed', status: res.status, data: {}, message: '서버 응답을 해석하지 못했습니다.' };
        }
        var ok = res.ok && data.success !== false;
        return {
          ok: ok, kind: ok ? 'ok' : 'error', status: res.status, data: data,
          message: (data && (data.error || data.message)) || ('HTTP ' + res.status)
        };
      });
    }).catch(function () {
      return { ok: false, kind: 'network', status: 0, data: {}, message: '네트워크 오류가 발생했습니다.' };
    });
  }

  function hasOffcanvas() {
    return !!(window.bootstrap && window.bootstrap.Offcanvas);
  }

  function sheetEl() {
    return document.getElementById(SHEET_ID);
  }

  function listEl() {
    return document.querySelector('[data-foms-prod-steps-sheet-list]');
  }

  function formatAt(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso).slice(0, 16).replace('T', ' ');
    var pad = function (n) { return String(n).padStart(2, '0'); };
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
      ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  function setLoading() {
    var list = listEl();
    if (!list) return;
    list.textContent = '';
    // 스켈레톤 3행(createElement) + 텍스트 폴백(.foms-prod-steps__loading 유지).
    for (var i = 0; i < 3; i++) {
      var row = document.createElement('li');
      row.className = 'foms-prod-steps__skeleton';
      row.setAttribute('aria-hidden', 'true');
      var dot = document.createElement('span');
      dot.className = 'foms-prod-steps__skeleton-dot';
      var lines = document.createElement('span');
      lines.className = 'foms-prod-steps__skeleton-lines';
      var a = document.createElement('span');
      a.className = 'foms-prod-steps__sk foms-prod-steps__sk--a';
      var b = document.createElement('span');
      b.className = 'foms-prod-steps__sk foms-prod-steps__sk--b';
      lines.appendChild(a);
      lines.appendChild(b);
      row.appendChild(dot);
      row.appendChild(lines);
      list.appendChild(row);
    }
    var li = document.createElement('li');
    li.className = 'foms-prod-steps__loading';
    li.setAttribute('role', 'status');
    li.textContent = '불러오는 중...';
    list.appendChild(li);
  }

  function setError(message) {
    var list = listEl();
    if (!list) return;
    list.textContent = '';
    var li = document.createElement('li');
    li.className = 'foms-prod-steps__error';
    li.textContent = message || '공정 정보를 불러오지 못했습니다.';
    list.appendChild(li);
  }

  function buildRow(step) {
    var li = document.createElement('li');
    li.className = 'foms-prod-steps__row' + (step.done ? ' is-done' : '');
    li.setAttribute('data-foms-prod-step-row', '');
    li.setAttribute('data-step-key', step.key);

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'foms-prod-steps__toggle';
    btn.setAttribute('data-foms-prod-step-toggle', '');
    btn.setAttribute('data-step-key', step.key);
    btn.setAttribute('aria-pressed', step.done ? 'true' : 'false');

    var check = document.createElement('span');
    check.className = 'foms-prod-steps__check';
    check.setAttribute('aria-hidden', 'true');
    var icon = document.createElement('i');
    icon.className = 'fas fa-check';
    check.appendChild(icon);

    var label = document.createElement('span');
    label.className = 'foms-prod-steps__label';
    label.textContent = step.label || step.key;

    var meta = document.createElement('span');
    meta.className = 'foms-prod-steps__meta';
    meta.setAttribute('data-foms-prod-step-meta', '');
    if (step.done) {
      var at = formatAt(step.at);
      meta.textContent = step.by_name ? (at + ' · ' + step.by_name) : at;
    }

    btn.appendChild(check);
    btn.appendChild(label);
    btn.appendChild(meta);
    li.appendChild(btn);
    return li;
  }

  function renderSteps(payload) {
    var list = listEl();
    if (!list) return;
    var steps = (payload && payload.steps) || [];
    list.textContent = '';
    steps.forEach(function (s) { list.appendChild(buildRow(s)); });
    updateCounts(payload);
  }

  function updateCounts(payload) {
    var done = (payload && payload.done_count) || 0;
    var total = (payload && payload.total) || 5;
    var head = document.querySelector('[data-foms-prod-steps-sheet-count]');
    if (head) head.textContent = done + '/' + total;
    if (currentOrderId != null) {
      var badge = document.querySelector('[data-foms-prod-steps-badge="' + currentOrderId + '"]');
      if (badge) badge.textContent = '공정 ' + done + '/' + total;
    }
  }

  async function loadSteps(orderId) {
    if (loading) return;
    loading = true;
    setLoading();
    try {
      var res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/production/steps', {
        credentials: 'same-origin'
      });
      var data = await res.json();
      if (!res.ok || !data.success) {
        setError((data && (data.error || data.message)) || ('HTTP ' + res.status));
        return;
      }
      renderSteps(data.data || {});
      renderDefectRecent((data.data || {}).latest_defect);
    } catch (err) {
      console.error('production steps load error:', err);
      setError('공정 정보를 불러오지 못했습니다.');
    } finally {
      loading = false;
    }
  }

  // --- G3 불량 보고 (ghost 버튼 → 사유 칩 → POST, 최근 이력 1줄) ------------------
  function defectRecentEl() { return document.querySelector('[data-foms-prod-defect-recent]'); }
  function defectReasonsEl() { return document.querySelector('[data-foms-prod-defect-reasons]'); }
  function defectToggleEl() { return document.querySelector('[data-foms-prod-defect-toggle]'); }
  function defectStatusEl() { return document.querySelector('[data-foms-prod-defect-status]'); }

  function renderDefectRecent(latest) {
    var el = defectRecentEl();
    if (!el) return;
    el.textContent = '';
    if (!latest || !latest.reason) {
      el.hidden = true;
      return;
    }
    // createElement/textContent 만 사용(사용자 유래 reason/by_name XSS 차단).
    var head = document.createElement('strong');
    head.textContent = '최근 불량: ';
    el.appendChild(head);
    var body = document.createElement('span');
    var parts = [latest.reason];
    var when = latest.at ? formatAt(latest.at) : '';
    if (when) parts.push(when);
    if (latest.by_name) parts.push(latest.by_name);
    body.textContent = parts.join(' · ');
    el.appendChild(body);
    el.hidden = false;
  }

  function collapseDefectReasons() {
    var reasons = defectReasonsEl();
    if (reasons) reasons.hidden = true;
    var toggle = defectToggleEl();
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
  }

  function setDefectStatus(msg) {
    var el = defectStatusEl();
    if (!el) return;
    if (msg) {
      el.textContent = msg;
      el.hidden = false;
    } else {
      el.textContent = '';
      el.hidden = true;
    }
  }

  function resetDefectUi() {
    collapseDefectReasons();
    setDefectStatus('');
    renderDefectRecent(null);
  }

  function setDefectChipsDisabled(disabled) {
    var reasons = defectReasonsEl();
    if (!reasons) return;
    reasons.querySelectorAll('[data-foms-prod-defect-reason]').forEach(function (b) {
      b.disabled = disabled;
    });
  }

  async function reportDefect(reason) {
    if (currentOrderId == null || !reason) return;
    setDefectChipsDisabled(true);
    setDefectStatus('보고 중...');
    var result = await mutationFetch('/api/orders/' + encodeURIComponent(currentOrderId) + '/production/defect', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: reason })
    });
    setDefectChipsDisabled(false);
    if (!result.ok) {
      setDefectStatus('보고 실패: ' + result.message);
      return;
    }
    renderDefectRecent((result.data.data && result.data.data.latest) || null);
    collapseDefectReasons();
    setDefectStatus('불량이 보고되었습니다.');
  }

  function openSheet(orderId) {
    if (!hasOffcanvas()) return;
    var sheet = sheetEl();
    if (!sheet) return;
    currentOrderId = orderId;
    resetDefectUi();
    window.bootstrap.Offcanvas.getOrCreateInstance(sheet).show();
    loadSteps(orderId);
  }

  async function toggleStep(btn) {
    var key = btn.getAttribute('data-step-key');
    if (!key || currentOrderId == null || btn.disabled) return;
    var nextDone = btn.getAttribute('aria-pressed') !== 'true';
    btn.disabled = true;
    var result = await mutationFetch('/api/orders/' + encodeURIComponent(currentOrderId) + '/production/steps', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: key, done: nextDone })
    });
    // 낙관 업데이트를 하지 않는 흐름이라(체크 상태는 renderSteps 성공 응답에서만 반영)
    // rollback 대상 DOM 변경이 없다 — 버튼 re-enable만으로 원상태 보존.
    btn.disabled = false;
    if (!result.ok) {
      alert('공정 저장 실패: ' + result.message);
      return;
    }
    renderSteps(result.data.data || {});
  }

  // 카드 배지 버튼 — capture 위임(카드 nav listener 보다 먼저 가로채 시트만 연다;
  // foms-order-timeline-sheet.js 와 동일 패턴).
  document.addEventListener('click', function (e) {
    if (!e.target || !e.target.closest) return;
    var trigger = e.target.closest('[data-foms-prod-steps-open]');
    if (!trigger) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    var id = trigger.getAttribute('data-foms-prod-steps-open');
    if (id == null || id === '') return;
    openSheet(id);
  }, true);

  // 시트 내부 체크 토글 — 일반 bubble 위임.
  document.addEventListener('click', function (e) {
    if (!e.target || !e.target.closest) return;
    var btn = e.target.closest('[data-foms-prod-step-toggle]');
    if (!btn) return;
    e.preventDefault();
    toggleStep(btn);
  });

  // G3 불량 보고 — ghost 토글(사유 칩 펼치기/접기)과 칩 선택(POST) bubble 위임.
  document.addEventListener('click', function (e) {
    if (!e.target || !e.target.closest) return;
    var toggle = e.target.closest('[data-foms-prod-defect-toggle]');
    if (toggle) {
      e.preventDefault();
      var reasons = defectReasonsEl();
      if (reasons) {
        var willShow = reasons.hidden;
        reasons.hidden = !willShow;
        toggle.setAttribute('aria-expanded', willShow ? 'true' : 'false');
        if (willShow) setDefectStatus('');
      }
      return;
    }
    var chip = e.target.closest('[data-foms-prod-defect-reason]');
    if (chip) {
      e.preventDefault();
      reportDefect(chip.getAttribute('data-foms-prod-defect-reason'));
    }
  });
})();
