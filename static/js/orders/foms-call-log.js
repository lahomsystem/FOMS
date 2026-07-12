/**
 * B1 통화 결과 기록 바텀시트 컨트롤러.
 * - 히어로/큐 카드의 [data-foms-call-log-open] 진입 → 단일 시트를 열고 order-id 주입.
 * - 저장 시 POST /api/orders/<id>/call-log (try/catch + success 검증) → 성공 시 시트 닫고 reload.
 * - document 위임 + __FOMS_CALL_LOG_BOUND 싱글톤 → 셸 프래그먼트 재실행에도 중복 바인딩 없음(G4).
 */
(function () {
  'use strict';

  if (window.__FOMS_CALL_LOG_BOUND) {
    return;
  }
  window.__FOMS_CALL_LOG_BOUND = true;

  var SHEET_SEL = '[data-foms-call-log-sheet]';

  function getSheet() {
    return document.querySelector(SHEET_SEL);
  }

  function setError(sheet, msg) {
    var err = sheet && sheet.querySelector('[data-foms-call-log-error]');
    if (!err) {
      return;
    }
    if (msg) {
      err.textContent = msg;
      err.hidden = false;
    } else {
      err.textContent = '';
      err.hidden = true;
    }
  }

  function openSheet(orderId, customerName) {
    var sheet = getSheet();
    if (!sheet || !orderId) {
      return;
    }
    sheet.setAttribute('data-order-id', String(orderId));
    var cust = sheet.querySelector('[data-foms-call-log-customer]');
    if (cust) {
      cust.textContent = customerName || ('#' + orderId);
    }
    var form = sheet.querySelector('[data-foms-call-log-form]');
    if (form && typeof form.reset === 'function') {
      form.reset();
    }
    setError(sheet, '');
    var saveBtn = sheet.querySelector('[data-foms-call-log-save]');
    if (saveBtn) {
      saveBtn.disabled = false;
    }
    sheet.hidden = false;
    sheet.setAttribute('aria-hidden', 'false');
    document.body.classList.add('foms-call-log-open');
  }

  function closeSheet() {
    var sheet = getSheet();
    if (!sheet) {
      return;
    }
    sheet.hidden = true;
    sheet.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('foms-call-log-open');
  }

  function readValue(form, selector) {
    var el = form.querySelector(selector);
    return el ? (el.value || '') : '';
  }

  function submitSheet(sheet) {
    var orderId = sheet.getAttribute('data-order-id');
    var form = sheet.querySelector('[data-foms-call-log-form]');
    if (!orderId || !form) {
      return;
    }
    var checked = form.querySelector('input[name="call_result"]:checked');
    var result = checked ? checked.value : '';
    if (!result) {
      setError(sheet, '통화 결과를 선택하세요.');
      return;
    }

    var payload = { result: result, memo: readValue(form, '[name="call_memo"]') };
    var measDate = readValue(form, '[name="measurement_date"]');
    if (measDate) {
      payload.measurement_date = measDate;
    }

    var saveBtn = sheet.querySelector('[data-foms-call-log-save]');
    if (saveBtn) {
      saveBtn.disabled = true;
    }
    setError(sheet, '');

    fetch('/api/orders/' + encodeURIComponent(orderId) + '/call-log', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(function (resp) {
        return resp.json().catch(function () { return {}; }).then(function (data) {
          return { ok: resp.ok, data: data };
        });
      })
      .then(function (res) {
        if (!res.ok || !res.data || res.data.success !== true) {
          var msg = (res.data && (res.data.error || res.data.message)) || '저장에 실패했습니다.';
          setError(sheet, msg);
          if (saveBtn) {
            saveBtn.disabled = false;
          }
          return;
        }
        closeSheet();
        window.location.reload();
      })
      .catch(function () {
        setError(sheet, '네트워크 오류로 저장하지 못했습니다.');
        if (saveBtn) {
          saveBtn.disabled = false;
        }
      });
  }

  document.addEventListener('click', function (ev) {
    if (!ev.target || !ev.target.closest) {
      return;
    }
    var opener = ev.target.closest('[data-foms-call-log-open]');
    if (opener) {
      ev.preventDefault();
      openSheet(opener.getAttribute('data-order-id'), opener.getAttribute('data-customer-name'));
      return;
    }
    if (ev.target.closest('[data-foms-call-log-close]')) {
      ev.preventDefault();
      closeSheet();
    }
  });

  document.addEventListener('submit', function (ev) {
    var form = ev.target && ev.target.closest ? ev.target.closest('[data-foms-call-log-form]') : null;
    if (!form) {
      return;
    }
    ev.preventDefault();
    var sheet = form.closest(SHEET_SEL);
    if (sheet) {
      submitSheet(sheet);
    }
  });

  document.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Escape') {
      return;
    }
    var sheet = getSheet();
    if (sheet && !sheet.hidden) {
      closeSheet();
    }
  });
})();
