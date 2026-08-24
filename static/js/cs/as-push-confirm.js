/**
 * AS PUSH 전송 확인창 (AS-FRESH-01 T7 / AS-BIND-01).
 * 대시보드·ERP 주문이 같은 모달·같은 전송 계약을 쓴다.
 * 문서 위임(G4)이라 ERP shell fragment 스왑 뒤에도 산 모달을 찾는다.
 */
(function () {
  'use strict';

  if (window.__AS_PUSH_CONFIRM_BOUND) return;
  window.__AS_PUSH_CONFIRM_BOUND = true;

  var dragFrom = -1;
  var pendingResolve = null;
  var resolvedBySend = false;
  var activeOrderId = null;
  var presetChangeNote = null;

  function escapeText(value) {
    if (typeof window.escapeHtml === 'function') {
      return window.escapeHtml(value || '');
    }
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function selectedEl() {
    return document.getElementById('as-push-confirm-selected');
  }

  function filesEl() {
    return document.getElementById('as-push-confirm-files');
  }

  function selectedPushIds() {
    var pushSelectedEl = selectedEl();
    if (!pushSelectedEl) return [];
    return Array.from(pushSelectedEl.querySelectorAll('.as-push-confirm__file'))
      .map(function (el) { return Number(el.dataset.fileId); })
      .filter(function (n) { return Number.isFinite(n); });
  }

  function pushFileCard(file, selected) {
    var name = escapeText(file.filename || '');
    var source = escapeText(file.source || '');
    var media = file.is_image
      ? '<img class="as-push-confirm__thumb" src="' + file.url + '" alt="' + name + '" loading="lazy">'
      : '<div class="as-push-confirm__doc"><i class="fas fa-file"></i></div>';
    return '<label class="as-push-confirm__file' + (selected ? ' is-on' : '') + '" draggable="' + (selected ? 'true' : 'false') + '" data-file-id="' + file.id + '">'
      + '<span class="as-push-confirm__ord">' + (selected ? '1' : '') + '</span>'
      + '<input type="checkbox" value="' + file.id + '"' + (file.selected ? ' checked' : '') + '>'
      + media
      + '<span class="as-push-confirm__name" title="' + name + '">' + name + '</span>'
      + '<span class="as-push-confirm__source">' + source + '</span>'
      + '<span class="as-push-confirm__nudge-row">'
      + '<button type="button" class="as-push-confirm__nudge" data-dir="-1" aria-label="앞으로">▲</button>'
      + '<button type="button" class="as-push-confirm__nudge" data-dir="1" aria-label="뒤로">▼</button>'
      + '</span>'
      + '</label>';
  }

  function finishPending(value) {
    if (typeof pendingResolve !== 'function') return;
    var resolve = pendingResolve;
    pendingResolve = null;
    resolve(value);
  }

  function syncPushCount() {
    var pushCountEl = document.getElementById('as-push-confirm-count');
    var pushCapHint = document.getElementById('as-push-confirm-cap-hint');
    var pushSelectedEl = selectedEl();
    var pushFilesEl = filesEl();
    if (!pushCountEl) return;
    var selected = selectedPushIds().length;
    var pool = pushFilesEl ? pushFilesEl.querySelectorAll('.as-push-confirm__file').length : 0;
    pushCountEl.textContent = (selected || pool) ? selected + '건 전송' : '';
    if (pushCapHint) pushCapHint.hidden = selected <= 20;
    if (pushSelectedEl) {
      Array.from(pushSelectedEl.querySelectorAll('.as-push-confirm__file')).forEach(function (el, idx) {
        el.classList.toggle('is-over-cap', idx >= 20);
        var ord = el.querySelector('.as-push-confirm__ord');
        if (ord) ord.textContent = String(idx + 1);
      });
    }
  }

  function renderPushFiles(files) {
    var pushFilesEl = filesEl();
    var pushSelectedEl = selectedEl();
    if (!pushFilesEl) return;
    if (!files.length) {
      if (pushSelectedEl) pushSelectedEl.innerHTML = '';
      pushFilesEl.innerHTML = '<div class="as-push-confirm__empty">보낼 AS 첨부가 없습니다. 본문만 전송됩니다.</div>';
      syncPushCount();
      return;
    }
    var selected = files.filter(function (f) { return f.selected; });
    var rest = files.filter(function (f) { return !f.selected; });
    if (pushSelectedEl) {
      pushSelectedEl.innerHTML = selected.map(function (f) { return pushFileCard(f, true); }).join('');
    }
    pushFilesEl.innerHTML = rest.length
      ? rest.map(function (f) { return pushFileCard(f, false); }).join('')
      : '<div class="as-push-confirm__empty">후보 없음</div>';
    syncPushCount();
  }

  function movePushSelected(from, to) {
    var pushSelectedEl = selectedEl();
    if (!pushSelectedEl) return;
    var nodes = Array.from(pushSelectedEl.querySelectorAll('.as-push-confirm__file'));
    if (from < 0 || to < 0 || from >= nodes.length || to >= nodes.length || from === to) return;
    var taken = nodes[from];
    var target = nodes[to];
    if (from < to) pushSelectedEl.insertBefore(taken, target.nextSibling);
    else pushSelectedEl.insertBefore(taken, target);
    syncPushCount();
  }

  async function postPush(orderId, attachmentIds, changeNote) {
    var payload = {
      order_id: Number(orderId),
      push_kind: 'as',
      attachment_ids: attachmentIds,
    };
    if (changeNote) payload.change_note = changeNote;
    var resp = await fetch('/api/channel/push-manual', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(payload),
    });
    return resp.json();
  }

  document.addEventListener('change', function (e) {
    var box = e.target.closest && e.target.closest('#as-push-confirm-selected input[type="checkbox"]');
    if (box) {
      if (box.checked) return;
      var label = box.closest('.as-push-confirm__file');
      var pushFilesEl = filesEl();
      if (!label || !pushFilesEl) return;
      box.checked = false;
      label.classList.remove('is-on');
      label.setAttribute('draggable', 'false');
      pushFilesEl.appendChild(label);
      syncPushCount();
      return;
    }
    box = e.target.closest && e.target.closest('#as-push-confirm-files input[type="checkbox"]');
    if (!box || !box.checked) return;
    var selected = selectedEl();
    var onLabel = box.closest('.as-push-confirm__file');
    if (!onLabel || !selected) return;
    onLabel.classList.add('is-on');
    onLabel.setAttribute('draggable', 'true');
    selected.appendChild(onLabel);
    syncPushCount();
  });

  document.addEventListener('dragstart', function (e) {
    var label = e.target.closest && e.target.closest('#as-push-confirm-selected .as-push-confirm__file');
    var pushSelectedEl = selectedEl();
    if (!label || !pushSelectedEl) return;
    dragFrom = Array.from(pushSelectedEl.querySelectorAll('.as-push-confirm__file')).indexOf(label);
  });
  document.addEventListener('dragover', function (e) {
    if (e.target.closest && e.target.closest('#as-push-confirm-selected')) e.preventDefault();
  });
  document.addEventListener('drop', function (e) {
    var label = e.target.closest && e.target.closest('#as-push-confirm-selected .as-push-confirm__file');
    var pushSelectedEl = selectedEl();
    if (!label || !pushSelectedEl) return;
    e.preventDefault();
    var to = Array.from(pushSelectedEl.querySelectorAll('.as-push-confirm__file')).indexOf(label);
    movePushSelected(dragFrom, to);
    dragFrom = -1;
  });
  document.addEventListener('click', function (e) {
    var nudge = e.target.closest && e.target.closest('.as-push-confirm__nudge');
    if (!nudge) return;
    e.preventDefault();
    e.stopPropagation();
    var label = nudge.closest('.as-push-confirm__file');
    var pushSelectedEl = selectedEl();
    if (!label || !pushSelectedEl) return;
    var nodes = Array.from(pushSelectedEl.querySelectorAll('.as-push-confirm__file'));
    var from = nodes.indexOf(label);
    movePushSelected(from, from + Number(nudge.getAttribute('data-dir')));
  });

  document.addEventListener('click', async function (e) {
    var sendBtn = e.target.closest && e.target.closest('#as-push-confirm-send');
    if (!sendBtn || !activeOrderId) return;
    var attachmentIds = selectedPushIds();
    sendBtn.disabled = true;
    var originalHtml = sendBtn.innerHTML;
    sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 전송중...';
    try {
      var data = await postPush(activeOrderId, attachmentIds, presetChangeNote);
      if (!data.success) {
        var msg = data.error || data.message || '알 수 없는 오류';
        if (msg.indexOf('재전송 시 변경 내용') >= 0 && !presetChangeNote) {
          var note = (window.prompt(
            '이미 전송한 AS PUSH입니다. 변경 내용을 입력하면 채널톡 메시지 상단에 [수정]으로 표시됩니다.'
          ) || '').trim();
          if (!note) return;
          data = await postPush(activeOrderId, attachmentIds, note);
        }
      }
      if (data.success) {
        resolvedBySend = true;
        var modalEl = document.getElementById('asPushConfirmModal');
        var bsModal = window.bootstrap && window.bootstrap.Modal && modalEl
          ? window.bootstrap.Modal.getInstance(modalEl)
          : null;
        if (bsModal) bsModal.hide();
        finishPending(data);
      } else {
        finishPending(data);
      }
    } catch (err) {
      finishPending({
        success: false,
        message: String((err && err.message) || err || '네트워크 오류'),
      });
    } finally {
      sendBtn.disabled = false;
      sendBtn.innerHTML = originalHtml;
    }
  });

  document.addEventListener('hidden.bs.modal', function (e) {
    if (!e.target || e.target.id !== 'asPushConfirmModal') return;
    if (!resolvedBySend) finishPending({ cancelled: true });
    resolvedBySend = false;
    activeOrderId = null;
    presetChangeNote = null;
  });

  window.fomsConfirmAndSendAsPush = async function (options) {
    options = options || {};
    var orderId = options.orderId;
    if (!orderId) {
      return { success: false, message: '주문 ID가 없습니다.' };
    }
    if (typeof pendingResolve === 'function') {
      return { cancelled: true };
    }
    var res = await fetch(
      '/api/channel/push-preview?order_id=' + encodeURIComponent(orderId) + '&push_kind=as',
      { credentials: 'same-origin' }
    );
    var preview = await res.json();
    if (!preview.success) {
      return { success: false, message: preview.message || '미리보기 실패' };
    }
    var modalEl = document.getElementById('asPushConfirmModal');
    var pushTextEl = document.getElementById('as-push-confirm-text');
    if (!modalEl) {
      return { success: false, message: '확인창을 열 수 없습니다.' };
    }
    activeOrderId = orderId;
    presetChangeNote = options.changeNote || null;
    if (pushTextEl) pushTextEl.textContent = preview.text || '';
    renderPushFiles(preview.files || []);
    var bsModal = window.bootstrap && window.bootstrap.Modal
      ? window.bootstrap.Modal.getOrCreateInstance(modalEl)
      : null;
    if (!bsModal) {
      return { success: false, message: '확인창을 열 수 없습니다.' };
    }
    resolvedBySend = false;
    return new Promise(function (resolve) {
      pendingResolve = resolve;
      bsModal.show();
    });
  };
})();
