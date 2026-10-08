/**
 * PARTNER-02: 협력사 화면 — 새 주문 등록(품목 줄 · 보내기 · 파일 올리기)과 상세의 파일 더 보내기.
 *
 * 서버 계약: POST /api/partner/orders (JSON) → {success, data:{order_id}, error}
 *            POST /api/partner/orders/<id>/files (multipart file + kind=photo|draft)
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

  async function uploadOne(url, file, kind) {
    var form = new FormData();
    form.append('file', file);
    form.append('kind', kind);
    var resp = await fetch(url, { method: 'POST', body: form, credentials: 'same-origin' });
    var data = null;
    try { data = await resp.json(); } catch (e) { data = null; }
    if (!data || !data.success) {
      throw new Error(file.name + ': ' + ((data && data.error) || '올리지 못했습니다.'));
    }
  }

  /** 폼의 사진·초안 파일을 하나씩 올린다. 실패한 파일 이름 목록을 돌려준다. */
  async function uploadFiles(form, url) {
    var jobs = [];
    var photos = form.querySelector('input[name="photos"]');
    var drafts = form.querySelector('input[name="drafts"]');
    Array.prototype.forEach.call((photos && photos.files) || [], function (f) { jobs.push([f, 'photo']); });
    Array.prototype.forEach.call((drafts && drafts.files) || [], function (f) { jobs.push([f, 'draft']); });
    var failed = [];
    for (var i = 0; i < jobs.length; i += 1) {
      setStatus('파일 올리는 중 ' + (i + 1) + ' / ' + jobs.length);
      try {
        await uploadOne(url, jobs[i][0], jobs[i][1]);
      } catch (err) {
        failed.push(err.message);
      }
    }
    return failed;
  }

  function addItemRow(container) {
    var tpl = document.getElementById('ppItemRow');
    if (!tpl || !container) return;
    container.appendChild(tpl.content.cloneNode(true));
  }

  function collectItems(container) {
    var rows = container ? container.querySelectorAll('.pp-item') : [];
    var items = [];
    Array.prototype.forEach.call(rows, function (row) {
      var item = {};
      Array.prototype.forEach.call(row.querySelectorAll('[data-k]'), function (input) {
        item[input.getAttribute('data-k')] = input.value.trim();
      });
      if (item.product_name) items.push(item);
    });
    return items;
  }

  function bindNewOrder(form) {
    var items = document.getElementById('ppItems');
    addItemRow(items);
    form.addEventListener('click', function (ev) {
      if (ev.target.closest('[data-pp-add-item]')) addItemRow(items);
      var remove = ev.target.closest('[data-pp-remove-item]');
      if (remove && items.querySelectorAll('.pp-item').length > 1) remove.closest('.pp-item').remove();
    });
    var busy = false;
    form.addEventListener('submit', async function (ev) {
      ev.preventDefault();
      if (busy) return;
      var payload = {
        customer_name: form.elements.customer_name.value.trim(),
        customer_phone: form.elements.customer_phone.value.trim(),
        address: form.elements.address.value.trim(),
        measured_on: form.elements.measured_on.value,
        memo: form.elements.memo.value.trim(),
        items: collectItems(items),
      };
      if (!payload.customer_name || !payload.customer_phone || !payload.address) {
        setStatus('고객 이름 · 연락처 · 현장 주소를 넣어 주세요.', true);
        return;
      }
      if (!payload.items.length) {
        setStatus('품목을 하나 이상 넣어 주세요.', true);
        return;
      }
      busy = true;
      form.querySelector('button[type="submit"]').disabled = true;
      setStatus('보내는 중…');
      try {
        var created = await postJson(form.getAttribute('data-create-url'), payload);
        var orderId = created.order_id;
        var failed = await uploadFiles(form, withOrderId(form.getAttribute('data-upload-url'), orderId));
        var detail = withOrderId(form.getAttribute('data-detail-url'), orderId);
        if (failed.length) {
          // 주문은 이미 등록됐다 — 다시 보내면 중복 주문이 생기니 상세로 보내 거기서 파일만 더 올리게 한다.
          window.alert('주문은 등록됐지만 일부 파일을 올리지 못했습니다. 상세 화면에서 다시 보내 주세요.\n\n' + failed.join('\n'));
        }
        window.location.href = detail;
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
      var failed = await uploadFiles(form, form.getAttribute('data-upload-url'));
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

  document.addEventListener('DOMContentLoaded', function () {
    Array.prototype.forEach.call(document.querySelectorAll('form[data-pp-post-url]'), bindPostForm);
    var approve = document.querySelector('[data-pp-approve-url]');
    if (approve) bindApprove(approve);
    var newOrder = document.getElementById('ppNewOrder');
    if (newOrder) bindNewOrder(newOrder);
    var more = document.getElementById('ppMoreFiles');
    if (more) bindMoreFiles(more);
  });
})();
