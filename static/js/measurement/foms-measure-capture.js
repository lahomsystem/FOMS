/**
 * B2 실측 캡처 바텀시트 컨트롤러.
 * - 히어로/큐 카드의 [data-foms-measure-capture-open] 진입 → 단일 시트를 열고 order-id·
 *   현재 dims/note 를 주입.
 * - 사진: [data-foms-measure-capture-photo] input change → 기존 멀티파트
 *   POST /api/orders/<id>/attachments (file + category=measurement) 업로드 → 상태 표시.
 * - 치수: W/D/H 스테퍼(±100/±10) + W 프리셋 칩.
 * - 특이사항: textarea + 🎤(Web Speech API ko-KR, 미지원 시 버튼 숨김, 에러는 상태 라벨로 노출).
 * - 저장: POST /api/erp/measurement/capture/<id> {dims?, note?} (try/catch + success 검증).
 * - document 위임 + __FOMS_MEAS_CAPTURE_BOUND 싱글톤 → 셸 프래그먼트 재실행에도 중복 바인딩 없음(G4).
 */
(function () {
  'use strict';

  if (window.__FOMS_MEAS_CAPTURE_BOUND) {
    return;
  }
  window.__FOMS_MEAS_CAPTURE_BOUND = true;

  var SHEET_SEL = '[data-foms-measure-capture-sheet]';
  var DIM_MIN = 0;
  var DIM_MAX = 9999;
  var recognition = null;

  function getSheet() {
    return document.querySelector(SHEET_SEL);
  }

  function setError(sheet, msg) {
    var err = sheet && sheet.querySelector('[data-foms-measure-capture-error]');
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

  function setPhotoStatus(sheet, msg) {
    var el = sheet && sheet.querySelector('[data-foms-measure-capture-photo-status]');
    if (el) {
      el.textContent = msg || '';
    }
  }

  function setMicStatus(sheet, msg) {
    var el = sheet && sheet.querySelector('[data-foms-measure-capture-mic-status]');
    if (el) {
      el.textContent = msg || '';
    }
  }

  function clampDim(value) {
    if (!isFinite(value)) {
      return 0;
    }
    return Math.max(DIM_MIN, Math.min(DIM_MAX, Math.round(value)));
  }

  function readStepperValue(stepper) {
    var out = stepper.querySelector('[data-foms-measure-value]');
    return out ? (parseInt(out.textContent, 10) || 0) : 0;
  }

  function writeStepperValue(stepper, value) {
    var out = stepper.querySelector('[data-foms-measure-value]');
    if (out) {
      out.textContent = String(clampDim(value));
    }
  }

  function setDim(sheet, key, value) {
    var stepper = sheet.querySelector('[data-foms-measure-stepper="' + key + '"]');
    if (stepper) {
      writeStepperValue(stepper, value);
    }
  }

  function openSheet(opener) {
    var sheet = getSheet();
    var orderId = opener.getAttribute('data-order-id');
    if (!sheet || !orderId) {
      return;
    }
    sheet.setAttribute('data-order-id', String(orderId));
    var cust = sheet.querySelector('[data-foms-measure-capture-customer]');
    if (cust) {
      cust.textContent = opener.getAttribute('data-customer-name') || ('#' + orderId);
    }
    setDim(sheet, 'w', parseInt(opener.getAttribute('data-dim-w'), 10) || 0);
    setDim(sheet, 'd', parseInt(opener.getAttribute('data-dim-d'), 10) || 0);
    setDim(sheet, 'h', parseInt(opener.getAttribute('data-dim-h'), 10) || 0);
    var note = sheet.querySelector('[data-foms-measure-capture-note]');
    if (note) {
      note.value = opener.getAttribute('data-note') || '';
    }
    setError(sheet, '');
    setPhotoStatus(sheet, '');
    setMicStatus(sheet, '');
    var saveBtn = sheet.querySelector('[data-foms-measure-capture-save]');
    if (saveBtn) {
      saveBtn.disabled = false;
    }
    var mic = sheet.querySelector('[data-foms-measure-capture-mic]');
    if (mic) {
      mic.hidden = !(window.SpeechRecognition || window.webkitSpeechRecognition);
      mic.setAttribute('aria-pressed', 'false');
    }
    sheet.hidden = false;
    sheet.setAttribute('aria-hidden', 'false');
    document.body.classList.add('foms-measure-capture-open');
  }

  function closeSheet() {
    var sheet = getSheet();
    if (!sheet) {
      return;
    }
    stopRecognition();
    sheet.hidden = true;
    sheet.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('foms-measure-capture-open');
  }

  function uploadPhotos(sheet, files) {
    var orderId = sheet.getAttribute('data-order-id');
    if (!orderId || !files || !files.length) {
      return;
    }
    var total = files.length;
    var done = 0;
    var failed = 0;
    setPhotoStatus(sheet, total + '장 업로드 중...');
    var uploads = Array.prototype.map.call(files, function (file) {
      var fd = new FormData();
      fd.append('file', file);
      fd.append('category', 'measurement');
      return fetch('/api/orders/' + encodeURIComponent(orderId) + '/attachments', {
        method: 'POST',
        credentials: 'same-origin',
        body: fd
      })
        .then(function (resp) {
          return resp.json().catch(function () { return {}; }).then(function (data) {
            return resp.ok && data && data.success === true;
          });
        })
        .then(function (ok) { if (ok) { done += 1; } else { failed += 1; } })
        .catch(function () { failed += 1; });
    });
    Promise.all(uploads).then(function () {
      if (failed) {
        setPhotoStatus(sheet, done + '장 업로드 완료 · ' + failed + '장 실패');
      } else {
        setPhotoStatus(sheet, done + '장 업로드 완료');
      }
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
    var note = sheet.querySelector('[data-foms-measure-capture-note]');
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
      if (note && transcript) {
        note.value = note.value ? (note.value + ' ' + transcript) : transcript;
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

  function collectPayload(sheet) {
    var payload = {};
    var w = 0;
    var d = 0;
    var h = 0;
    var steppers = sheet.querySelectorAll('[data-foms-measure-stepper]');
    Array.prototype.forEach.call(steppers, function (stepper) {
      var key = stepper.getAttribute('data-foms-measure-stepper');
      var val = readStepperValue(stepper);
      if (key === 'w') { w = val; } else if (key === 'd') { d = val; } else if (key === 'h') { h = val; }
    });
    if (w > 0 && d > 0 && h > 0) {
      payload.dims = { w: w, d: d, h: h };
    }
    var note = sheet.querySelector('[data-foms-measure-capture-note]');
    var noteVal = note ? note.value.trim() : '';
    if (noteVal) {
      payload.note = noteVal;
    }
    return payload;
  }

  function submitSheet(sheet) {
    var orderId = sheet.getAttribute('data-order-id');
    if (!orderId) {
      return;
    }
    var payload = collectPayload(sheet);
    if (!payload.dims && typeof payload.note !== 'string') {
      setError(sheet, '치수(W·D·H 모두) 또는 특이사항을 입력하세요.');
      return;
    }
    var saveBtn = sheet.querySelector('[data-foms-measure-capture-save]');
    if (saveBtn) {
      saveBtn.disabled = true;
    }
    setError(sheet, '');
    stopRecognition();

    fetch('/api/erp/measurement/capture/' + encodeURIComponent(orderId), {
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
    var opener = ev.target.closest('[data-foms-measure-capture-open]');
    if (opener) {
      ev.preventDefault();
      openSheet(opener);
      return;
    }
    if (ev.target.closest('[data-foms-measure-capture-close]')) {
      ev.preventDefault();
      closeSheet();
      return;
    }
    var stepBtn = ev.target.closest('[data-foms-measure-step]');
    if (stepBtn) {
      ev.preventDefault();
      var stepper = stepBtn.closest('[data-foms-measure-stepper]');
      if (stepper) {
        var delta = parseInt(stepBtn.getAttribute('data-foms-measure-step'), 10) || 0;
        writeStepperValue(stepper, readStepperValue(stepper) + delta);
      }
      return;
    }
    var preset = ev.target.closest('[data-foms-measure-preset]');
    if (preset) {
      ev.preventDefault();
      var presetStepper = preset.closest('[data-foms-measure-stepper]');
      if (presetStepper) {
        writeStepperValue(presetStepper, parseInt(preset.getAttribute('data-foms-measure-preset'), 10) || 0);
      }
      return;
    }
    var mic = ev.target.closest('[data-foms-measure-capture-mic]');
    if (mic) {
      ev.preventDefault();
      var micSheet = mic.closest(SHEET_SEL);
      if (micSheet) {
        toggleMic(micSheet, mic);
      }
      return;
    }
    var saveBtn = ev.target.closest('[data-foms-measure-capture-save]');
    if (saveBtn) {
      ev.preventDefault();
      var saveSheet = saveBtn.closest(SHEET_SEL);
      if (saveSheet) {
        submitSheet(saveSheet);
      }
    }
  });

  document.addEventListener('change', function (ev) {
    var input = ev.target && ev.target.closest ? ev.target.closest('[data-foms-measure-capture-photo]') : null;
    if (!input) {
      return;
    }
    var sheet = input.closest(SHEET_SEL);
    if (sheet && input.files && input.files.length) {
      uploadPhotos(sheet, input.files);
      input.value = '';
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
