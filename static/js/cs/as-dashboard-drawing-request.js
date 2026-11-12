/**
 * AS 화면 'AS도면' 칸 [도면팀 부탁] — 설계서 docs/specs/2026-11-11-as-drawing-after-completion_SPEC.md §4.4(2판).
 * 작은 창: 여러 줄 글(Enter 줄바꿈 · Ctrl/⌘+Enter 보내기) + 사진 · 동영상(단추 · Ctrl+V · 끌어다 놓기).
 * POST .../drawing/as/request {memo} 가 차수와 AS 기록 한 줄을 저장하고 request_log_id 를 주면, 파일은 '기록 추가' 칸과
 * 같은 길(fomsUploadOrderAttachmentsBatch, category 'as' + asLogId)로 그 줄에 묶는다. 업로드만 실패해도 부탁은 그대로
 * (다시 올리기 = AS 기록의 클립 단추). 닫아도 글 · 파일은 주문마다 남는다(AS 접수 창 11-09 규칙). 미리보기는 as-attachment-order.js.
 */
(function () {
  'use strict';
  if (window.__fomsAsDrawingRequestWired) return; // fragment 재실행 가드
  window.__fomsAsDrawingRequestWired = true;

  const MEMO_ID = 'erp-as-drawing-req-memo';
  const drafts = new Map(); // 주문 id → { text, files }
  let pop = null;
  let ctl = null;
  let busy = false;

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text) node.textContent = text;
    return node;
  }

  function orderIdOf(btn) {
    const row = btn.closest('[data-order-id]');
    return row ? row.getAttribute('data-order-id') || '' : '';
  }

  /** 서버 state 로 칸 글자를 만든다 — 템플릿의 상태 링크(as_dashboard_body.html)와 같은 모양. */
  function stateLink(orderId, state) {
    const a = el('a', 'd-block small lh-sm');
    a.href = '/edit/' + encodeURIComponent(orderId);
    a.title = state.title || '';
    (state.words || []).forEach(function (w, i) {
      if (i) a.appendChild(document.createTextNode(' '));
      a.appendChild(el('span', 'text-nowrap', String(w)));
    });
    return a;
  }

  function settle(btn, orderId, state) {
    if (state && Array.isArray(state.words) && state.words.length) btn.replaceWith(stateLink(orderId, state));
    else btn.remove();
  }

  /** 같은 화면의 저장 알림(#saveToast, as-dashboard.js 와 같은 모양) — 칸이 54px 라 칸 안에 글을 두지 않는다. */
  function feedback(text, isError) {
    const toastEl = document.getElementById('saveToast');
    const msgEl = document.getElementById('toastMessage');
    if (toastEl && msgEl && window.bootstrap && window.bootstrap.Toast) {
      msgEl.textContent = text;
      toastEl.classList.remove('bg-success', 'bg-danger');
      toastEl.classList.add(isError ? 'bg-danger' : 'bg-success');
      window.bootstrap.Toast.getOrCreateInstance(toastEl).show();
      return;
    }
    window.alert(text);
  }

  function actButton(cls, text, act) {
    const b = el('button', cls, text);
    b.type = 'button';
    b.dataset.act = act;
    return b;
  }

  function files() { return ctl ? ctl.getFiles() : []; }

  function closePop(keepDraft) {
    if (!pop || busy) return;
    if (keepDraft !== false) {
      const memo = pop.querySelector('#' + MEMO_ID);
      drafts.set(pop.dataset.forOrder, { text: memo ? memo.value : '', files: files() });
    }
    pop.remove();
    pop = null;
    ctl = null;
  }

  /** 클립보드에서 사진만 골라 File[] 로 — 기록 추가 칸(dockClipboardImageFiles)과 같은 규칙. */
  function clipboardImages(e) {
    const items = e.clipboardData && e.clipboardData.items;
    const out = [];
    if (!items) return out;
    const stamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14);
    for (let i = 0; i < items.length; i += 1) {
      const it = items[i];
      if (!it || it.kind !== 'file' || String(it.type || '').indexOf('image/') !== 0) continue;
      const raw = it.getAsFile();
      if (!raw) continue;
      const type = raw.type || it.type || 'image/png';
      const ext = type === 'image/jpeg' ? 'jpg' : type === 'image/webp' ? 'webp' : type === 'image/gif' ? 'gif' : 'png';
      const name = 'capture-' + stamp + (out.length ? '-' + (out.length + 1) : '') + '.' + ext;
      try { out.push(new File([raw], name, { type: type, lastModified: Date.now() })); } catch (_) { out.push(raw); }
    }
    return out;
  }

  function addFiles(list) {
    const all = Array.prototype.slice.call(list || []);
    const media = all.filter(function (f) { return /^(image|video)\//.test(String(f.type || '')); });
    if (media.length < all.length) feedback('사진과 동영상만 담을 수 있어요.', true);
    if (ctl && media.length) ctl.addFiles(media);
  }

  function isFileDrag(e) {
    const types = e.dataTransfer && e.dataTransfer.types ? Array.prototype.slice.call(e.dataTransfer.types) : [];
    return types.indexOf('Files') >= 0;
  }

  async function post(orderId, memo) {
    try {
      const res = await fetch('/api/orders/' + encodeURIComponent(orderId) + '/drawing/as/request', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ memo: memo }),
      });
      let data = {};
      try { data = await res.json(); } catch (_) { data = {}; }
      return data || {};
    } catch (e) {
      return { success: false, error: '인터넷 연결을 확인해 주세요.' };
    }
  }

  async function upload(orderId, logId, list, statusEl) {
    if (!list.length) return 0;
    if (!logId || typeof window.fomsUploadOrderAttachmentsBatch !== 'function') return list.length;
    const label = '부탁은 저장했어요. 사진 · 동영상 올리는 중… ';
    statusEl.hidden = false;
    statusEl.textContent = label + '(0/' + list.length + ')';
    try {
      const result = await window.fomsUploadOrderAttachmentsBatch({
        orderId: orderId,
        files: list,
        folder: 'orders/' + orderId + '/attachments',
        category: 'as',
        asLogId: logId,
        sortOrders: list.map(function (_f, i) { return i; }),
        useDirectUpload: true,
        onUploadProgress: function (info) {
          statusEl.textContent = label + '(' + Math.round(info.done) + '/' + info.total + ')';
        },
      });
      return result && typeof result.ok === 'number' ? Math.max(0, result.total - result.ok) : list.length;
    } catch (e) {
      return list.length;
    }
  }

  async function send(btn, orderId, memoEl, sendBtn, statusEl) {
    const list = files();
    busy = true;
    sendBtn.disabled = true;
    const data = await post(orderId, memoEl.value.trim());
    if (!data.success) {
      busy = false;
      if (data.code === 'AS_DRAWING_OPEN') {
        // 다른 사람이 먼저 부탁했거나 도면팀이 시작했다 — 칸 글자를 지금 상태로 맞춘다.
        closePop();
        settle(btn, orderId, data.data && data.data.state);
      } else {
        sendBtn.disabled = false;
      }
      feedback(data.error || '부탁하지 못했어요. 잠시 뒤 다시 해 주세요.', true);
      return;
    }
    const failed = await upload(orderId, data.data && data.data.request_log_id, list, statusEl);
    busy = false;
    drafts.delete(orderId);
    closePop(false);
    settle(btn, orderId, data.data && data.data.state);
    if (failed) {
      feedback('부탁은 했어요. 사진 · 동영상 ' + failed + '개를 못 올렸어요. AS 기록의 클립 단추로 다시 올려 주세요.', true);
    } else {
      feedback(list.length ? '도면팀에 부탁했어요. 사진 · 동영상 ' + list.length + '개도 함께 보냈어요.'
        : '도면팀에 부탁했어요. 도면 담당 폰에 알림이 가요.', false);
    }
  }

  function position(btn) {
    if (!pop) return;
    const rect = btn.getBoundingClientRect();
    // 화면 크기(--foms-ui-zoom)가 붙으면 rect · scroll · innerWidth 는 보이는 px, style 은 배율 전 px 다.
    const uiZoom = window.fomsUiZoom ? window.fomsUiZoom() : 1;
    const popW = (pop.offsetWidth || 400) * uiZoom;
    const popH = (pop.offsetHeight || 320) * uiZoom;
    // 칸이 표 오른쪽에 있어 단추 오른쪽 끝에 맞춰 왼쪽으로 연다. 아래 자리가 모자라면 단추 위로 연다.
    const left = Math.max(8, Math.min(window.scrollX + rect.right - popW, window.scrollX + window.innerWidth - popW - 8));
    const below = rect.bottom + 4 + popH <= window.innerHeight || rect.top - 4 - popH < 0;
    const top = below ? window.scrollY + rect.bottom + 4 : window.scrollY + rect.top - 4 - popH;
    pop.style.top = (top / uiZoom) + 'px';
    pop.style.left = (left / uiZoom) + 'px';
  }

  function openPop(btn) {
    closePop();
    if (pop) return; // 올리는 중인 창은 닫지 않는다
    const orderId = orderIdOf(btn);
    const draft = drafts.get(orderId) || { text: '', files: [] };
    const received = btn.getAttribute('data-as-received') || '';
    pop = el('div', 'erp-as-avail-pop erp-as-drawing-req-pop');
    pop.dataset.forOrder = orderId;
    pop.setAttribute('role', 'dialog');
    pop.setAttribute('aria-label', '도면팀에 정확한 도면 부탁');
    pop.appendChild(el('div', 'erp-as-drawing-req-pop__title', '도면팀에 정확한 도면 부탁'));
    pop.appendChild(el('div', 'erp-as-drawing-req-pop__hint',
      received ? 'AS 접수 ' + received + '에 묶어요.' : '지금 열린 AS 접수에 묶어요.'));
    pop.appendChild(el('div', 'erp-as-drawing-req-pop__hint', '받는 사람: 도면 담당 (없으면 도면팀 전체)'));
    const label = el('label', 'erp-as-drawing-req-pop__label', '무엇을 그려야 하나요 (비우면 AS 내용)');
    label.htmlFor = MEMO_ID;
    const memo = el('textarea', 'erp-pro-input erp-as-drawing-req-pop__memo');
    memo.id = MEMO_ID;
    memo.rows = 5;
    memo.maxLength = 2000;
    memo.placeholder = '예: 오른쪽 문짝 1짝, 원래 크기 그대로\n줄을 바꿔 여러 줄로 써도 돼요';
    memo.value = draft.text;
    const bar = el('div', 'erp-as-drawing-req-pop__bar');
    const pick = actButton('btn btn-sm btn-outline-secondary', ' 사진 · 동영상', 'pick'); // 기록 추가 칸 [파일]과 같은 모양
    const clip = el('i', 'fas fa-paperclip');
    clip.setAttribute('aria-hidden', 'true');
    pick.prepend(clip);
    const input = el('input');
    input.type = 'file';
    input.accept = 'image/*,video/*';
    input.multiple = true;
    input.hidden = true;
    input.setAttribute('data-foms-no-capture', '');
    bar.append(pick, el('span', 'erp-as-drawing-req-pop__hint', '캡처는 Ctrl+V · 파일은 끌어다 놓기'), input);
    const preview = el('div', 'erp-as-drawing-req-pop__preview as-attach-order');
    preview.hidden = true;
    const status = el('div', 'erp-as-drawing-req-pop__status');
    status.hidden = true;
    status.setAttribute('role', 'status');
    const foot = el('div', 'erp-as-drawing-req-pop__foot');
    const actions = el('div', 'erp-as-avail-pop__actions');
    const sendBtn = actButton('erp-pro-btn erp-pro-btn--primary', '부탁하기', 'send');
    actions.append(actButton('erp-pro-btn erp-pro-btn--ghost', '닫기', 'close'), sendBtn);
    foot.append(el('span', 'erp-as-drawing-req-pop__hint', 'Ctrl+Enter 로도 보내요'), actions);
    pop.append(label, memo, bar, preview, status, foot);
    document.body.appendChild(pop);
    ctl = window.fomsAsAttachmentOrder
      ? window.fomsAsAttachmentOrder.mount(preview, { onChange: function () { position(btn); } }) : null;
    if (!ctl) bar.hidden = true; // 미리보기 부품이 없으면 글만 보낸다
    if (ctl && draft.files.length) ctl.addFiles(draft.files);
    position(btn);
    memo.focus();

    input.addEventListener('change', function () { addFiles(input.files); input.value = ''; });
    memo.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !e.isComposing) { e.preventDefault(); sendBtn.click(); }
    });
    pop.addEventListener('paste', function (e) {
      const shots = clipboardImages(e);
      if (!shots.length) return; // 글 붙여넣기는 그대로
      e.preventDefault();
      addFiles(shots);
    });
    pop.addEventListener('dragover', function (e) {
      if (!isFileDrag(e)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
      pop.classList.add('is-drop-over');
    });
    pop.addEventListener('dragleave', function () { if (pop) pop.classList.remove('is-drop-over'); });
    pop.addEventListener('drop', function (e) {
      if (!isFileDrag(e)) return;
      e.preventDefault();
      pop.classList.remove('is-drop-over');
      addFiles(e.dataTransfer.files);
    });
    pop.addEventListener('click', function (e) {
      const act = e.target.closest('[data-act]');
      if (!act || act.disabled || busy) return;
      if (act.dataset.act === 'pick') { input.click(); return; }
      if (act.dataset.act === 'close') { closePop(); btn.focus(); return; }
      send(btn, orderId, memo, sendBtn, status);
    });
  }

  document.addEventListener('click', function (e) {
    const btn = e.target.closest ? e.target.closest('[data-as-drawing-request]') : null;
    if (btn) {
      e.preventDefault();
      e.stopPropagation();
      if (pop && pop.dataset.forOrder === orderIdOf(btn)) { closePop(); return; }
      openPop(btn);
      return;
    }
    if (pop && !pop.contains(e.target)) closePop();
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closePop(); });
})();
