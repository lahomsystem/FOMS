/**
 * ERP 채널톡 재전송 확인 — 변경 내용 입력 modal/sheet.
 * Idempotent: fomsMountErpOrderSurface에서 erpMountChannelPushResendModal() 1회 호출.
 */
(function () {
    'use strict';

    const MIN_NOTE_LEN = 5;
    const HISTORY_KEYS = {
        measurement: 'channeltalk_push',
        drawing: 'channeltalk_push_drawing',
    };
    const PUSH_LABELS = {
        measurement: '영발 PUSH',
        drawing: '발주 PUSH',
    };

    /** @returns {string} structured_data 이력 키 */
    function erpChannelPushHistoryKey(pushKind) {
        return HISTORY_KEYS[pushKind] || HISTORY_KEYS.measurement;
    }

    /** @returns {boolean} 해당 push_kind로 이전 전송 이력이 있는지 */
    function erpHasPriorChannelPush(pushKind) {
        const sd = window.__erpLastStructuredData;
        if (!sd || typeof sd !== 'object') return false;
        const rec = sd[erpChannelPushHistoryKey(pushKind)];
        return !!(rec && rec.pushed);
    }

    /**
     * 전송 성공 후 클라이언트 structured_data 푸시 플래그 갱신.
     * @param {string} pushKind
     */
    function erpMarkChannelPushSent(pushKind) {
        const key = erpChannelPushHistoryKey(pushKind);
        if (!window.__erpLastStructuredData || typeof window.__erpLastStructuredData !== 'object') {
            window.__erpLastStructuredData = {};
        }
        const prev = window.__erpLastStructuredData[key] || {};
        window.__erpLastStructuredData[key] = Object.assign({}, prev, { pushed: true });
    }

    let _pendingResolve = null;

    function _finishPending(value) {
        if (typeof _pendingResolve !== 'function') return;
        const resolve = _pendingResolve;
        _pendingResolve = null;
        resolve(value);
    }

    /** Modal send/cancel/hidden — singleton bind (G4). */
    function erpMountChannelPushResendModal() {
        if (window.__ERP_CHANNEL_PUSH_RESEND_BOUND) return;
        window.__ERP_CHANNEL_PUSH_RESEND_BOUND = true;

        const modalEl = document.getElementById('erpChannelPushResendModal');
        const textarea = document.getElementById('erp-channel-push-resend-note');
        const sendBtn = document.getElementById('erp-channel-push-resend-send-btn');
        if (!modalEl || !textarea || !sendBtn) return;

        sendBtn.addEventListener('click', function () {
            const trimmed = (textarea.value || '').trim();
            if (trimmed.length < MIN_NOTE_LEN) {
                alert('변경 내용을 5자 이상 입력해주세요.');
                textarea.focus();
                return;
            }
            const bsModal = window.bootstrap && window.bootstrap.Modal
                ? window.bootstrap.Modal.getInstance(modalEl)
                : null;
            _finishPending(trimmed);
            if (bsModal) bsModal.hide();
        });

        modalEl.addEventListener('hidden.bs.modal', function () {
            if (typeof _pendingResolve === 'function') {
                _finishPending(null);
            }
        });
    }

    /**
     * 재전송 변경 내용 입력 modal/sheet.
     * @param {string} pushKind 'measurement' | 'drawing'
     * @returns {Promise<string|null>} 확인 시 note, 취소 시 null
     */
    function erpPromptChannelPushResendNote(pushKind) {
        erpMountChannelPushResendModal();

        const modalEl = document.getElementById('erpChannelPushResendModal');
        const textarea = document.getElementById('erp-channel-push-resend-note');
        const titleEl = document.getElementById('erp-channel-push-resend-title');
        if (!modalEl || !textarea) {
            return Promise.resolve(null);
        }

        const label = PUSH_LABELS[pushKind] || 'PUSH';
        if (titleEl) titleEl.textContent = '재전송 확인 · ' + label;
        textarea.value = '';

        const bsModal = window.bootstrap && window.bootstrap.Modal
            ? window.bootstrap.Modal.getOrCreateInstance(modalEl)
            : null;
        if (!bsModal) {
            const fallback = window.prompt('변경 내용을 입력해주세요 (5자 이상)');
            const trimmed = (fallback || '').trim();
            return Promise.resolve(trimmed.length >= MIN_NOTE_LEN ? trimmed : null);
        }

        return new Promise(function (resolve) {
            _pendingResolve = resolve;
            bsModal.show();
            window.setTimeout(function () {
                textarea.focus();
            }, 280);
        });
    }

    window.erpChannelPushHistoryKey = erpChannelPushHistoryKey;
    window.erpHasPriorChannelPush = erpHasPriorChannelPush;
    window.erpMarkChannelPushSent = erpMarkChannelPushSent;
    window.erpMountChannelPushResendModal = erpMountChannelPushResendModal;
    window.erpPromptChannelPushResendNote = erpPromptChannelPushResendNote;
})();
