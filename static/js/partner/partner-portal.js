/**
 * PARTNER-02: 협력사 화면 — 새 주문 등록(품목 줄 · 보내기 · 파일 올리기)과 상세의 파일 더 보내기.
 *
 * 서버 계약: POST /api/partner/orders (JSON) → {success, data:{order_id, item_count}, error}
 *            POST /api/partner/orders/<id>/files (multipart file + kind=photo|draft [+ item_index: 제품 실측 사진])
 * 제품 항목 입력은 partner-items.js(window.PartnerItems)가 맡는다.
 *            POST /api/partner/orders/<id>/manager · /api/partner/me/phone (JSON 한 칸 — form[data-pp-json-url])
 * CSRF 헤더는 partials/shared/csrf_bootstrap.html 이 fetch 에 자동으로 싣는다.
 */
(function () {
  'use strict';

  function setStatus(text, isError) {
    var el = document.getElementById('ppStatus');
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('pp-status--error', !!isError);
  }

  function withOrderId(templateUrl, orderId) {
    // url_for(..., order_id=0) 로 만든 주소의 0 자리를 실제 번호로 바꾼다.
    return String(templateUrl || '').replace(/\/0(\/files)?$/, '/' + orderId + '$1');
  }

  async function postJson(url, body) {
    var resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      credentials: 'same-origin',
    });
    var data = null;
    try { data = await resp.json(); } catch (e) { data = null; }
    if (!data || !data.success) {
      throw new Error((data && data.error) || '보내지 못했습니다. 잠시 뒤 다시 시도해 주세요.');
    }
    return data.data;
  }

  async function uploadOne(url, file, kind, itemIndex) {
    var form = new FormData();
    form.append('file', file);
    form.append('kind', kind);
    if (itemIndex != null) form.append('item_index', String(itemIndex));
    var resp = await fetch(url, { method: 'POST', body: form, credentials: 'same-origin' });
    var data = null;
    try { data = await resp.json(); } catch (e) { data = null; }
    if (!data || !data.success) {
      throw new Error(file.name + ': ' + ((data && data.error) || '올리지 못했습니다.'));
    }
  }

  /**
   * 공통 사진 · 초안과 제품별 실측 사진(itemJobs: [{index, files}])을 하나씩 올린다.
   * commonJobs: 사진 칸의 공통 사진 · 초안([[파일, 'photo'|'draft'], …], PartnerPhotos.commonJobs).
   * 실패한 파일 이름 목록을 돌려준다.
   */
  async function uploadFiles(form, url, itemJobs, commonJobs) {
    var jobs = [];
    var photos = form.querySelector('input[name="photos"]');
    var drafts = form.querySelector('input[name="drafts"]');
    Array.prototype.forEach.call((photos && photos.files) || [], function (f) { jobs.push([f, 'photo', null]); });
    Array.prototype.forEach.call((drafts && drafts.files) || [], function (f) { jobs.push([f, 'draft', null]); });
    (commonJobs || []).forEach(function (job) { jobs.push([job[0], job[1], null]); });
    (itemJobs || []).forEach(function (job) {
      job.files.forEach(function (f) { jobs.push([f, 'photo', job.index]); });
    });
    var failed = [];
    for (var i = 0; i < jobs.length; i += 1) {
      setStatus('파일 올리는 중 ' + (i + 1) + ' / ' + jobs.length);
      try {
        await uploadOne(url, jobs[i][0], jobs[i][1], jobs[i][2]);
      } catch (err) {
        failed.push(err.message);
      }
    }
    return failed;
  }

  function bindNewOrder(form) {
    var items = form.querySelector('[data-pp-items]');
    if (!window.PartnerItems) return;
    window.PartnerItems.init(items, form.querySelectorAll('[data-pp-add-item]'));
    var busy = false;
    form.addEventListener('submit', async function (ev) {
      ev.preventDefault();
      if (busy) return;
      var collected = window.PartnerItems.collect(items);
      var payload = {
        customer_name: form.elements.customer_name.value.trim(),
        customer_phone: form.elements.customer_phone.value.trim(),
        address: form.elements.address.value.trim(),
        measured_on: form.elements.measured_on.value.trim(),
        measured_time: form.elements.measured_time.value.trim(),
        requested_construction_date: form.elements.requested_construction_date.value.trim(),
        requested_construction_time: form.elements.requested_construction_time.value.trim(),
        memo: form.elements.memo.value.trim(),
        items: collected.items,
      };
      if (!payload.customer_name || !payload.customer_phone || !payload.address) {
        setStatus('고객 이름 · 연락처 · 현장 주소를 넣어 주세요.', true);
        return;
      }
      if (!payload.items.length) {
        setStatus('제품명을 넣은 제품 항목이 하나 이상 있어야 합니다.', true);
        return;
      }
      if (collected.orphanPhotos) {
        setStatus('제품명이 없는 항목에 사진이 ' + collected.orphanPhotos + '개 있습니다. 제품명을 넣거나 사진을 공통으로 옮겨 주세요.', true);
        return;
      }
      busy = true;
      form.querySelector('button[type="submit"]').disabled = true;
      setStatus('저장하는 중…');
      try {
        var created = await postJson(form.getAttribute('data-create-url'), payload);
        var orderId = created.order_id;
        var uploadUrl = withOrderId(form.getAttribute('data-upload-url'), orderId);
        var common = window.PartnerPhotos ? window.PartnerPhotos.commonJobs() : [];
        var failed = await uploadFiles(form, uploadUrl, collected.photoJobs, common);
        if (failed.length) {
          // 주문은 이미 저장됐다 — 다시 저장하면 중복 주문이 생기니, 목록에서 그 주문을 열어 파일만 더 올리게 한다.
          window.alert('주문은 저장됐지만 일부 파일을 올리지 못했습니다. 목록에서 주문 #' + orderId + ' 을 열어 "실측 사진 더 보내기"로 다시 보내 주세요.\n\n' + failed.join('\n'));
        }
        // 우리 FOMS 처럼 저장하면 바로 목록으로(사용자 2026-10-21).
        window.location.href = form.getAttribute('data-list-url');
      } catch (err) {
        setStatus(err.message, true);
        busy = false;
        form.querySelector('button[type="submit"]').disabled = false;
      }
    });
  }

  function bindMoreFiles(form) {
    var busy = false;
    form.addEventListener('submit', async function (ev) {
      ev.preventDefault();
      if (busy) return;
      busy = true;
      form.querySelector('button[type="submit"]').disabled = true;
      var common = window.PartnerPhotos ? window.PartnerPhotos.commonJobs() : [];
      var failed = await uploadFiles(form, form.getAttribute('data-upload-url'), [], common);
      if (failed.length) {
        setStatus(failed.join(' / '), true);
        busy = false;
        form.querySelector('button[type="submit"]').disabled = false;
        return;
      }
      window.location.reload();
    });
  }

  function bindApprove(button) {
    var busy = false;
    button.addEventListener('click', async function () {
      if (busy) return;
      if (!window.confirm('이 도면대로 제작을 시작할까요? 누르면 되돌릴 수 없습니다.')) return;
      busy = true;
      button.disabled = true;
      setStatus('보내는 중…');
      try {
        var key = 'pp-approve-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
        await postJson(button.getAttribute('data-pp-approve-url'), { idempotency_key: key });
        window.location.reload();
      } catch (err) {
        setStatus(err.message, true);
        busy = false;
        button.disabled = false;
      }
    });
  }

  /** 메모 + 사진 폼(수정 요청 · AS 접수) — multipart 로 한 번에 보낸다. */
  function bindPostForm(form) {
    var busy = false;
    var status = form.querySelector('[data-pp-status]');
    function show(text, isError) {
      if (!status) return;
      status.textContent = text || '';
      status.classList.toggle('pp-status--error', !!isError);
    }
    form.addEventListener('submit', async function (ev) {
      ev.preventDefault();
      if (busy) return;
      var text = form.querySelector('textarea');
      if (text && !text.value.trim()) { show('내용을 적어 주세요.', true); return; }
      if (!window.confirm(form.getAttribute('data-pp-confirm') || '보낼까요?')) return;
      busy = true;
      form.querySelector('button[type="submit"]').disabled = true;
      show('보내는 중…');
      try {
        var body = new FormData(form);
        body.append('idempotency_key', 'pp-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8));
        var resp = await fetch(form.getAttribute('data-pp-post-url'), { method: 'POST', body: body, credentials: 'same-origin' });
        var data = null;
        try { data = await resp.json(); } catch (e) { data = null; }
        if (!data || !data.success) throw new Error((data && data.error) || '보내지 못했습니다. 잠시 뒤 다시 시도해 주세요.');
        if (data.data && data.data.photo_error) window.alert('접수는 됐지만 사진을 올리지 못했습니다: ' + data.data.photo_error);
        window.location.reload();
      } catch (err) {
        show(err.message, true);
        busy = false;
        form.querySelector('button[type="submit"]').disabled = false;
      }
    });
  }

  /** 한 칸짜리 JSON 폼(담당 바꾸기 · 내 연락처) — 성공하면 새로고침. */
  function bindJsonForm(form) {
    var busy = false;
    var status = form.querySelector('[data-pp-status]');
    function show(text, isError) {
      if (!status) return;
      status.textContent = text || '';
      status.classList.toggle('pp-status--error', !!isError);
    }
    form.addEventListener('submit', async function (ev) {
      ev.preventDefault();
      if (busy) return;
      var key = form.getAttribute('data-pp-json-key');
      var field = form.elements[key];
      var value = field ? String(field.value || '').trim() : '';
      if (!value) { show('값을 넣어 주세요.', true); return; }
      busy = true;
      form.querySelector('button[type="submit"]').disabled = true;
      show('저장하는 중…');
      try {
        var body = {};
        body[key] = value;
        await postJson(form.getAttribute('data-pp-json-url'), body);
        window.location.reload();
      } catch (err) {
        show(err.message, true);
        busy = false;
        form.querySelector('button[type="submit"]').disabled = false;
      }
    });
  }

  /** 주문 목록: 필터 줄은 고르면 바로 거르고, 작업 큐 줄은 눌러 주문 화면으로 간다(안의 링크는 그대로). */
  function bindBoard() {
    Array.prototype.forEach.call(document.querySelectorAll('form[data-pp-autosubmit]'), function (form) {
      form.addEventListener('change', function (ev) {
        if (ev.target.matches('select, input[type="checkbox"]')) form.submit();
      });
    });
    document.addEventListener('click', function (ev) {
      var row = ev.target.closest('[data-pp-row-href]');
      if (row && !ev.target.closest('a, button')) window.location.href = row.getAttribute('data-pp-row-href');
    });
  }

  /** 칩 줄: 고른 칩이 오른쪽 화면 밖이면 보이게 가로로만 민다(완료 · AS 칩이 안 보여 무엇을 골랐는지 몰랐다). */
  function revealActiveChip() {
    Array.prototype.forEach.call(document.querySelectorAll('.foms-chip-strip'), function (strip) {
      var chip = strip.querySelector('.foms-chip.is-active');
      if (!chip) return;
      var left = chip.getBoundingClientRect().left - strip.getBoundingClientRect().left + strip.scrollLeft;
      if (left + chip.offsetWidth > strip.scrollLeft + strip.clientWidth || left < strip.scrollLeft) {
        strip.scrollLeft = Math.max(0, left - (strip.clientWidth - chip.offsetWidth) / 2);
      }
    });
  }

  // 주문 화면 품목 저장(partner-order.js)이 같은 상태 줄 · 파일 올리기를 쓴다.
  window.PartnerPortal = { setStatus: setStatus, uploadFiles: uploadFiles };

  document.addEventListener('DOMContentLoaded', function () {
    bindBoard();
    revealActiveChip();
    Array.prototype.forEach.call(document.querySelectorAll('form[data-pp-json-url]'), bindJsonForm);
    Array.prototype.forEach.call(document.querySelectorAll('form[data-pp-post-url]'), bindPostForm);
    var approve = document.querySelector('[data-pp-approve-url]');
    if (approve) bindApprove(approve);
    var newOrder = document.getElementById('ppNewOrder');
    if (newOrder) bindNewOrder(newOrder);
    var more = document.getElementById('ppMoreFiles');
    if (more) bindMoreFiles(more);
  });
})();
