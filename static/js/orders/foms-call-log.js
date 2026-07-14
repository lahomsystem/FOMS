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
  var recognition = null;

  // B7: 공용 쓰기 래퍼(있으면) 경유 → 오프라인 시 큐 적재 + sync 배지 갱신. 없으면 기존 fetch.
  function writeFetch(url, opts) {
    return (window.fomsWriteFetch || fetch)(url, opts);
  }

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

  function setMicStatus(sheet, msg) {
    var el = sheet && sheet.querySelector('[data-foms-call-log-mic-status]');
    if (el) {
      el.textContent = msg || '';
    }
  }

  function pad2(n) {
    return (n < 10 ? '0' : '') + n;
  }

  function toIsoDate(d) {
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
  }

  // 실측일 제안 칩(내일/모레/3일 후) 라벨을 서버 렌더가 아닌 열람 시점 로컬 날짜로 채운다.
  function populateDateChips(sheet) {
    var chips = sheet.querySelectorAll('[data-foms-call-log-date-chip]');
    var base = new Date();
    base.setHours(0, 0, 0, 0);
    Array.prototype.forEach.call(chips, function (chip) {
      var offset = parseInt(chip.getAttribute('data-offset'), 10) || 0;
      var d = new Date(base.getTime());
      d.setDate(d.getDate() + offset);
      chip.setAttribute('data-value', toIsoDate(d));
      chip.classList.remove('foms-call-log-date-chip--active');
      chip.setAttribute('aria-pressed', 'false');
      var lbl = chip.querySelector('[data-foms-call-log-date-label]');
      if (lbl) {
        lbl.textContent = (d.getMonth() + 1) + '/' + d.getDate();
      }
    });
  }

  function applyDateChip(sheet, chip) {
    var input = sheet.querySelector('[name="measurement_date"]');
    if (input) {
      input.value = chip.getAttribute('data-value') || '';
    }
    var chips = sheet.querySelectorAll('[data-foms-call-log-date-chip]');
    Array.prototype.forEach.call(chips, function (c) {
      var active = c === chip;
      c.classList.toggle('foms-call-log-date-chip--active', active);
      c.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  function stopRecognition() {
    if (recognition) {
      try {
        recognition.stop();
      } catch (_err) {
        /* stop 중복 호출은 무해 */
      }
      recognition = null;
    }
  }

  // 메모 음성 받아쓰기(Web Speech API ko-KR).
  function toggleMic(sheet, mic) {
    var Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Rec) {
      return;
    }
    if (recognition) {
      stopRecognition();
      mic.setAttribute('aria-pressed', 'false');
      setMicStatus(sheet, '');
      return;
    }
    var memo = sheet.querySelector('[name="call_memo"]');
    recognition = new Rec();
    recognition.lang = 'ko-KR';
    recognition.interimResults = false;
    recognition.continuous = false;
    mic.setAttribute('aria-pressed', 'true');
    setMicStatus(sheet, '듣는 중...');
    recognition.onresult = function (ev) {
      var transcript = '';
      for (var i = ev.resultIndex; i < ev.results.length; i += 1) {
        transcript += ev.results[i][0].transcript;
      }
      transcript = transcript.trim();
      if (memo && transcript) {
        memo.value = memo.value ? (memo.value + ' ' + transcript) : transcript;
      }
    };
    recognition.onerror = function (ev) {
      // 에러를 삼키지 않고 상태 라벨로 노출.
      setMicStatus(sheet, '음성 인식 오류: ' + (ev && ev.error ? ev.error : '알 수 없음'));
      recognition = null;
      mic.setAttribute('aria-pressed', 'false');
    };
    recognition.onend = function () {
      recognition = null;
      mic.setAttribute('aria-pressed', 'false');
      setMicStatus(sheet, '');
    };
    try {
      recognition.start();
    } catch (err) {
      setMicStatus(sheet, '음성 인식을 시작할 수 없습니다.');
      recognition = null;
      mic.setAttribute('aria-pressed', 'false');
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
    var mic = sheet.querySelector('[data-foms-call-log-mic]');
    if (mic) {
      mic.hidden = !(window.SpeechRecognition || window.webkitSpeechRecognition);
      mic.setAttribute('aria-pressed', 'false');
    }
    setMicStatus(sheet, '');
    populateDateChips(sheet);
    sheet.hidden = false;
    sheet.setAttribute('aria-hidden', 'false');
    document.body.classList.add('foms-call-log-open');
  }

  function closeSheet() {
    var sheet = getSheet();
    if (!sheet) {
      return;
    }
    stopRecognition();
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

    writeFetch('/api/orders/' + encodeURIComponent(orderId) + '/call-log', {
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
    var dateChip = ev.target.closest('[data-foms-call-log-date-chip]');
    if (dateChip) {
      ev.preventDefault();
      var dcSheet = dateChip.closest(SHEET_SEL);
      if (dcSheet) {
        applyDateChip(dcSheet, dateChip);
      }
      return;
    }
    var mic = ev.target.closest('[data-foms-call-log-mic]');
    if (mic) {
      ev.preventDefault();
      var micSheet = mic.closest(SHEET_SEL);
      if (micSheet) {
        toggleMic(micSheet, mic);
      }
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

  // 사용자가 날짜 입력을 직접 바꾸면 제안 칩 하이라이트를 해제(프로그램 setvalue 는 change 미발생).
  document.addEventListener('change', function (ev) {
    var input = ev.target && ev.target.closest ? ev.target.closest('[name="measurement_date"]') : null;
    if (!input) {
      return;
    }
    var sheet = input.closest(SHEET_SEL);
    if (!sheet) {
      return;
    }
    var chips = sheet.querySelectorAll('[data-foms-call-log-date-chip]');
    Array.prototype.forEach.call(chips, function (c) {
      c.classList.remove('foms-call-log-date-chip--active');
      c.setAttribute('aria-pressed', 'false');
    });
  });
})();
