/**
 * AS 접수 창 초안 보관 — 접수 전이면 새로고침·창 닫기에도 쓰던 내용이 남는다(사용자 11-09).
 *
 * 보관하는 것: AS 내용 글, 비용 구분(무상·유상·미정)과 금액, 재발 표시, 사진·동영상 파일.
 * 파일(Blob)은 localStorage 에 못 넣으므로 IndexedDB 에 통째로 둔다(브라우저가 File 을 그대로 복제 저장).
 * 열쇠 = 주문 번호 + 창 모드(new·edit·reintake). 접수에 성공하면 그 주문의 초안을 지운다.
 * 7일 지난 초안은 꺼낼 때 버린다.
 *
 * 저장소를 못 쓰는 브라우저(사생활 보호 창 등)에서는 조용히 아무것도 안 한다 —
 * 그래도 같은 화면 안에서는 erp-order-shared.js 의 창 초안 유지가 그대로 동작한다.
 */
(function () {
    'use strict';

    const DB_NAME = 'foms-as-receive-draft';
    const STORE = 'drafts';
    const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
    const SAVE_DELAY_MS = 400;

    let dbPromise = null;
    let saveTimer = null;
    let restoring = false;

    function openDb() {
        if (dbPromise) return dbPromise;
        dbPromise = new Promise(function (resolve) {
            try {
                if (!window.indexedDB) { resolve(null); return; }
                const req = window.indexedDB.open(DB_NAME, 1);
                req.onupgradeneeded = function () {
                    if (!req.result.objectStoreNames.contains(STORE)) {
                        req.result.createObjectStore(STORE, { keyPath: 'key' });
                    }
                };
                req.onsuccess = function () { resolve(req.result); };
                req.onerror = function () { resolve(null); };
                req.onblocked = function () { resolve(null); };
            } catch (_e) {
                resolve(null);
            }
        });
        return dbPromise;
    }

    function run(mode, fn) {
        return openDb().then(function (db) {
            if (!db) return null;
            return new Promise(function (resolve) {
                try {
                    const tx = db.transaction(STORE, mode);
                    const result = fn(tx.objectStore(STORE));
                    tx.oncomplete = function () { resolve(result && 'result' in result ? result.result : null); };
                    tx.onerror = function () { resolve(null); };
                    tx.onabort = function () { resolve(null); };
                } catch (_e) {
                    resolve(null);
                }
            });
        });
    }

    function keyOf(orderId, mode) {
        return `${orderId}:${mode}`;
    }

    function currentKey() {
        const orderId = window.__erpAsReceiveTargetId;
        const mode = window.__erpAsReceiveMode;
        if (!orderId || orderId <= 0 || !mode) return '';
        return keyOf(orderId, mode);
    }

    function byId(id) {
        return document.getElementById(id);
    }

    function currentFiles() {
        const previewEl = byId('as-receive-preview');
        if (previewEl && previewEl._asOrder) return previewEl._asOrder.getFiles();
        const clip = window.__erpAsReceiveClipboardFiles;
        if (Array.isArray(clip) && clip.length) return clip.slice();
        const filesEl = byId('as-receive-files');
        return filesEl && filesEl.files ? Array.from(filesEl.files) : [];
    }

    function collect() {
        const billing = document.querySelector('input[name="as-receive-billing"]:checked');
        return {
            content: (byId('as-receive-content') || {}).value || '',
            billing: billing ? billing.value : '',
            amount: (byId('as-receive-amount') || {}).value || '',
            recurrence: !!(byId('as-receive-recurrence') || {}).checked,
            files: currentFiles(),
        };
    }

    function isEmpty(state) {
        return !state.content.trim() && !state.files.length && !state.amount && !state.recurrence;
    }

    function saveNow() {
        if (restoring) return Promise.resolve(null);
        // 접수 성공 때 erp-order-shared.js 가 초안 표식을 비운다 — 그 뒤 닫힘 이벤트가 옛 글을 다시 넣지 않게.
        if (window.__erpAsReceiveSubmitted === true || !window.__erpAsReceiveDraftKey) {
            return Promise.resolve(null);
        }
        const key = currentKey();
        if (!key) return Promise.resolve(null);
        const state = collect();
        if (isEmpty(state)) return run('readwrite', function (store) { return store.delete(key); });
        state.key = key;
        state.savedAt = Date.now();
        return run('readwrite', function (store) { return store.put(state); });
    }

    function scheduleSave() {
        if (saveTimer) clearTimeout(saveTimer);
        saveTimer = setTimeout(function () { saveTimer = null; saveNow(); }, SAVE_DELAY_MS);
    }

    function apply(draft) {
        const contentEl = byId('as-receive-content');
        if (contentEl && typeof draft.content === 'string') contentEl.value = draft.content;
        const radios = Array.from(document.querySelectorAll('input[name="as-receive-billing"]'));
        const target = radios.find(function (r) { return r.value === draft.billing && !r.disabled; });
        if (target) {
            target.checked = true;
            target.dispatchEvent(new Event('change', { bubbles: true }));
        }
        const amountEl = byId('as-receive-amount');
        if (amountEl && !amountEl.disabled && draft.amount) amountEl.value = draft.amount;
        const recurEl = byId('as-receive-recurrence');
        const recurWrap = byId('as-receive-recurrence-wrap');
        if (recurEl && recurWrap && !recurWrap.classList.contains('d-none')) {
            recurEl.checked = !!draft.recurrence;
        }
        const files = Array.isArray(draft.files) ? draft.files : [];
        if (files.length && typeof window.erpAppendAsReceiveFiles === 'function') {
            window.erpAppendAsReceiveFiles(files);
        }
    }

    /**
     * 그 주문·모드의 초안이 있으면 창 칸에 되살린다. 창을 연 직후(초기화 뒤)에 부른다.
     * @returns {Promise<boolean>} 되살렸으면 true.
     */
    function restore(orderId, mode) {
        const key = keyOf(orderId, mode);
        return run('readonly', function (store) { return store.get(key); }).then(function (draft) {
            if (!draft) return false;
            if (!draft.savedAt || Date.now() - draft.savedAt > MAX_AGE_MS) {
                run('readwrite', function (store) { return store.delete(key); });
                return false;
            }
            if (currentKey() !== key || window.__erpAsReceiveSubmitted === true) return false;
            restoring = true;
            try { apply(draft); } finally { restoring = false; }
            return true;
        });
    }

    /** 접수 성공 뒤 그 주문의 초안(모든 모드)을 지운다. */
    function clear(orderId) {
        if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
        const prefix = `${orderId}:`;
        return run('readwrite', function (store) {
            ['new', 'edit', 'reintake'].forEach(function (mode) { store.delete(prefix + mode); });
            return null;
        });
    }

    function bind() {
        const modalEl = byId('asReceiveModal');
        if (!modalEl || modalEl.dataset.asDraftBound === '1') return;
        modalEl.dataset.asDraftBound = '1';
        modalEl.addEventListener('input', scheduleSave);
        modalEl.addEventListener('change', scheduleSave);
        modalEl.addEventListener('hidden.bs.modal', function () {
            if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
            saveNow();
        });
        window.addEventListener('pagehide', function () {
            if (modalEl.classList.contains('show')) saveNow();
        });
    }

    window.fomsAsReceiveDraft = {
        restore: restore,
        clear: clear,
        scheduleSave: scheduleSave,
    };

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind);
    else bind();
})();
