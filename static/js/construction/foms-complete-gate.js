/**
 * B5 시공 완료 게이트 바텀시트 컨트롤러.
 * - 카드 "완료 준비"([data-action="openCompleteGate"], .erp-construction-action 위임) → 시트를 열고
 *   order-id 주입 + 현재 증빙 상태(structured) 시딩.
 * - before/after: input[file] → 멀티파트 업로드(category=construction) → evidence 등록(kind).
 * - 서명: canvas 드로잉 → toBlob(PNG) 업로드 → evidence 등록(kind=signature).
 * - 게이트(after >= 2 AND 서명) 충족 시 [시공 완료] 활성 → 기존 complete API 호출.
 * - document 위임 + __FOMS_CGATE_BOUND 싱글톤 → 셸 프래그먼트 재실행에도 중복 바인딩 없음(G4).
 */
(function () {
  'use strict';

  if (window.__FOMS_CGATE_BOUND) {
    return;
  }
  window.__FOMS_CGATE_BOUND = true;

  var SHEET_SEL = '[data-foms-cgate-sheet]';

  function getSheet() {
    return document.querySelector(SHEET_SEL);
  }

  function setError(sheet, msg) {
    var err = sheet && sheet.querySelector('[data-foms-cgate-error]');
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

  function setCount(sheet, kind, n) {
    var el = sheet.querySelector('[data-foms-cgate-count="' + kind + '"]');
    if (el) {
      el.textContent = n + '장';
    }
  }

  function setSignState(sheet, signed) {
    var el = sheet.querySelector('[data-foms-cgate-sign-state]');
    if (el) {
      el.textContent = signed ? '서명 완료' : '미서명';
      el.classList.toggle('is-signed', !!signed);
    }
  }

  function updateGate(sheet, after, signed) {
    var status = sheet.querySelector('[data-foms-cgate-status]');
    if (status) {
      status.textContent = '완료까지: 시공 후 ' + after + '/2 · 서명 ' + (signed ? 'O' : 'X');
    }
    var btn = sheet.querySelector('[data-foms-cgate-complete]');
    if (btn) {
      btn.disabled = !(after >= 2 && signed);
    }
  }

  function applyEvidence(sheet, ev) {
    ev = ev || {};
    var after = (ev.after || []).length;
    setCount(sheet, 'before', (ev.before || []).length);
    setCount(sheet, 'after', after);
    var signed = !!ev.signature_att_id;
    setSignState(sheet, signed);
    updateGate(sheet, after, signed);
  }

  function clearCanvas(sheet) {
    var canvas = sheet.querySelector('[data-foms-cgate-canvas]');
    if (canvas) {
      var ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      canvas.__cgateDirty = false;
    }
  }

  function resetSheet(sheet) {
    ['before', 'after'].forEach(function (kind) {
      var thumbs = sheet.querySelector('[data-foms-cgate-thumbs="' + kind + '"]');
      if (thumbs) {
        thumbs.innerHTML = '';
      }
      setCount(sheet, kind, 0);
    });
    var note = sheet.querySelector('[data-foms-cgate-note]');
    if (note) {
      note.value = '';
    }
    setSignState(sheet, false);
    updateGate(sheet, 0, false);
    setError(sheet, '');
    clearCanvas(sheet);
  }

  function openSheet(orderId) {
    var sheet = getSheet();
    if (!sheet || !orderId) {
      return;
    }
    sheet.setAttribute('data-order-id', String(orderId));
    resetSheet(sheet);
    var cust = sheet.querySelector('[data-foms-cgate-customer]');
    if (cust) {
      var titleEl = document.querySelector('.foms-queue-card-v2[data-order-id="' + orderId + '"] .foms-queue-card-v2__title');
      cust.textContent = (titleEl ? titleEl.textContent.trim() : '') || ('#' + orderId);
    }
    sheet.hidden = false;
    sheet.setAttribute('aria-hidden', 'false');
    document.body.classList.add('foms-cgate-open');

    fetch('/api/orders/' + encodeURIComponent(orderId) + '/structured', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (d && d.success && d.structured_data) {
          var ev = ((d.structured_data.construction || {}).evidence) || {};
          applyEvidence(sheet, ev);
        }
      })
      .catch(function () { /* 시딩 실패는 무시: 0부터 시작 */ });
  }
  // 기존 .erp-construction-action 위임(construction/partials/scripts.html)이 호출한다.
  window.openCompleteGate = openSheet;

  function closeSheet() {
    var sheet = getSheet();
    if (!sheet) {
      return;
    }
    sheet.hidden = true;
    sheet.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('foms-cgate-open');
  }

  // ERR-UX-01: 공용 mutation 에러 parser 경유(timeout/malformed JSON/403/409/428 분류,
  // 절대 reject 하지 않음). 폴백은 공용 parser 미로드 시에만(로드 순서 방어).
  function mutationFetch(url, opts) {
    if (window.fomsMutationFetch) return window.fomsMutationFetch(url, opts);
    return fetch(url, opts)
      .then(function (r) {
        return r.json().catch(function () { return null; }).then(function (data) {
          if (data === null) {
            return { ok: false, kind: 'malformed', status: r.status, data: {}, message: '서버 응답을 해석하지 못했습니다.' };
          }
          var ok = r.ok && data.success !== false;
          return {
            ok: ok, kind: ok ? 'ok' : 'error', status: r.status, data: data,
            message: (data && (data.error || data.message)) || ('HTTP ' + r.status)
          };
        });
      })
      .catch(function () {
        return { ok: false, kind: 'network', status: 0, data: {}, message: '네트워크 오류가 발생했습니다.' };
      });
  }

  function uploadAttachment(orderId, file, filename) {
    var fd = new FormData();
    fd.append('file', file, filename);
    fd.append('category', 'construction');
    return mutationFetch('/api/orders/' + encodeURIComponent(orderId) + '/attachments', {
      method: 'POST',
      credentials: 'same-origin',
      body: fd
    }).then(function (result) {
      if (!result.ok || !result.data.attachment) {
        var err = new Error('upload failed');
        err.fomsMessage = result.message;
        throw err;
      }
      return result.data.attachment;
    });
  }

  function registerEvidence(orderId, kind, attachmentId) {
    return mutationFetch('/api/orders/' + encodeURIComponent(orderId) + '/construction/evidence', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind: kind, attachment_id: attachmentId })
    }).then(function (result) {
      if (!result.ok) {
        var err = new Error('register failed');
        err.fomsMessage = result.message;
        throw err;
      }
      return result.data.data || {};
    });
  }

  function handlePhotoUpload(sheet, kind, file) {
    var orderId = sheet.getAttribute('data-order-id');
    if (!orderId || !file) {
      return;
    }
    setError(sheet, '');
    var thumbs = sheet.querySelector('[data-foms-cgate-thumbs="' + kind + '"]');
    var img = null;
    if (thumbs) {
      img = document.createElement('img');
      img.className = 'foms-cgate-thumb';
      img.alt = kind + ' 사진';
      try {
        img.src = URL.createObjectURL(file);
      } catch (_) { /* preview 실패는 무시 */ }
      thumbs.appendChild(img);
    }
    uploadAttachment(orderId, file, file.name)
      .then(function (att) { return registerEvidence(orderId, kind, att.id); })
      .then(function (ev) { applyEvidence(sheet, ev); })
      .catch(function (err) {
        // DOM rollback: 실패 시 낙관적으로 붙였던 미리보기 썸네일을 되돌린다.
        if (img && img.parentNode) {
          img.parentNode.removeChild(img);
        }
        setError(sheet, (err && err.fomsMessage) || '사진 업로드에 실패했습니다. 다시 시도하세요.');
      });
  }

  function saveSignature(sheet) {
    var orderId = sheet.getAttribute('data-order-id');
    var canvas = sheet.querySelector('[data-foms-cgate-canvas]');
    if (!orderId || !canvas) {
      return;
    }
    if (!canvas.__cgateDirty) {
      setError(sheet, '서명을 먼저 입력하세요.');
      return;
    }
    setError(sheet, '');
    var saveBtn = sheet.querySelector('[data-foms-cgate-sign-save]');
    if (saveBtn) {
      saveBtn.disabled = true;
    }
    canvas.toBlob(function (blob) {
      if (!blob) {
        if (saveBtn) { saveBtn.disabled = false; }
        setError(sheet, '서명 이미지를 생성하지 못했습니다.');
        return;
      }
      var filename = 'signature_' + orderId + '_' + Date.now() + '.png';
      uploadAttachment(orderId, blob, filename)
        .then(function (att) { return registerEvidence(orderId, 'signature', att.id); })
        .then(function (ev) { applyEvidence(sheet, ev); })
        .catch(function (err) {
          setError(sheet, (err && err.fomsMessage) || '서명 저장에 실패했습니다. 다시 시도하세요.');
        })
        .then(function () { if (saveBtn) { saveBtn.disabled = false; } });
    }, 'image/png');
  }

  function submitComplete(sheet) {
    var orderId = sheet.getAttribute('data-order-id');
    if (!orderId) {
      return;
    }
    var noteEl = sheet.querySelector('[data-foms-cgate-note]');
    var note = noteEl ? (noteEl.value || '').trim() : '';
    var btn = sheet.querySelector('[data-foms-cgate-complete]');
    if (btn) {
      btn.disabled = true;
    }
    setError(sheet, '');
    mutationFetch('/api/orders/' + encodeURIComponent(orderId) + '/construction/complete', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ completion_note: note })
    }).then(function (result) {
      if (!result.ok) {
        setError(sheet, result.message || '완료 처리에 실패했습니다.');
        if (btn) { btn.disabled = false; }
        return;
      }
      closeSheet();
      window.location.reload();
    });
  }

  // --- 서명 패드 드로잉(pointer 위임) ---------------------------------------
  var activeCanvas = null;
  var activeCtx = null;

  function canvasPoint(canvas, ev) {
    var rect = canvas.getBoundingClientRect();
    var sx = rect.width ? (canvas.width / rect.width) : 1;
    var sy = rect.height ? (canvas.height / rect.height) : 1;
    return { x: (ev.clientX - rect.left) * sx, y: (ev.clientY - rect.top) * sy };
  }

  document.addEventListener('pointerdown', function (ev) {
    var canvas = ev.target && ev.target.closest ? ev.target.closest('[data-foms-cgate-canvas]') : null;
    if (!canvas) {
      return;
    }
    ev.preventDefault();
    activeCanvas = canvas;
    activeCtx = canvas.getContext('2d');
    activeCtx.lineWidth = 2.5;
    activeCtx.lineCap = 'round';
    activeCtx.strokeStyle = '#111827';
    var pt = canvasPoint(canvas, ev);
    activeCtx.beginPath();
    activeCtx.moveTo(pt.x, pt.y);
    canvas.__cgateDirty = true;
    if (canvas.setPointerCapture) {
      try { canvas.setPointerCapture(ev.pointerId); } catch (_) { /* noop */ }
    }
  });

  document.addEventListener('pointermove', function (ev) {
    if (!activeCanvas || !activeCtx) {
      return;
    }
    var pt = canvasPoint(activeCanvas, ev);
    activeCtx.lineTo(pt.x, pt.y);
    activeCtx.stroke();
  });

  function endStroke() {
    activeCanvas = null;
    activeCtx = null;
  }
  document.addEventListener('pointerup', endStroke);
  document.addEventListener('pointercancel', endStroke);

  // --- 위임: 클릭 / 변경 / 키다운 --------------------------------------------
  document.addEventListener('click', function (ev) {
    if (!ev.target || !ev.target.closest) {
      return;
    }
    if (ev.target.closest('[data-foms-cgate-close]')) {
      ev.preventDefault();
      closeSheet();
      return;
    }
    var sheet = ev.target.closest(SHEET_SEL);
    if (!sheet) {
      return;
    }
    if (ev.target.closest('[data-foms-cgate-sign-clear]')) {
      ev.preventDefault();
      clearCanvas(sheet);
      return;
    }
    if (ev.target.closest('[data-foms-cgate-sign-save]')) {
      ev.preventDefault();
      saveSignature(sheet);
      return;
    }
    if (ev.target.closest('[data-foms-cgate-complete]')) {
      ev.preventDefault();
      submitComplete(sheet);
    }
  });

  document.addEventListener('change', function (ev) {
    var input = ev.target && ev.target.closest ? ev.target.closest('[data-foms-cgate-input]') : null;
    if (!input) {
      return;
    }
    var sheet = input.closest(SHEET_SEL);
    if (!sheet) {
      return;
    }
    var kind = input.getAttribute('data-foms-cgate-input');
    var files = input.files ? Array.prototype.slice.call(input.files) : [];
    files.forEach(function (f) { handlePhotoUpload(sheet, kind, f); });
    input.value = '';
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
