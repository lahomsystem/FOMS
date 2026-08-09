/**
 * ERP 채널톡 재전송 확인 — 변경 내용 입력 modal/sheet.
 * Idempotent: fomsMountErpOrderSurface에서 erpMountChannelPushResendModal() 1회 호출.
 */
(function () {
    'use strict';

    const MIN_NOTE_LEN = 1;
    const HISTORY_KEYS = {
        measurement: 'channeltalk_push',
        drawing: 'channeltalk_push_drawing',
        estimate: 'channeltalk_push_estimate',
        as: 'channeltalk_push_as',
    };
    const PUSH_LABELS = {
        measurement: '영발 PUSH',
        drawing: '발주 PUSH',
        estimate: '견적서 PUSH',
        as: 'AS PUSH',
    };
    const PUSH_BUTTON_IDS = [
        'erp-channeltalk-push-btn',
        'erp-channeltalk-push-drawing-btn',
        'erp-channeltalk-push-as-btn',
        'erp-channeltalk-push-picker-btn',
    ];

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
     * 서버 400: 재전송 change_note 필수 응답인지 판별.
     * @param {string} message
     * @returns {boolean}
     */
    function erpIsChannelPushResendNoteRequired(message) {
        return String(message || '').indexOf('재전송 시 변경 내용') >= 0;
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
    let _resolvedBySend = false;

    function _finishPending(value) {
        if (typeof _pendingResolve !== 'function') return;
        const resolve = _pendingResolve;
        _pendingResolve = null;
        resolve(value);
    }

    /** Modal 열림 동안 영발/발주 PUSH 버튼 중복 클릭 차단 (M2). */
    function _setChannelPushButtonsLocked(locked) {
        PUSH_BUTTON_IDS.forEach(function (id) {
            const el = document.getElementById(id);
            if (el) el.disabled = !!locked;
        });
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
                alert('변경 내용을 입력해주세요.');
                textarea.focus();
                return;
            }
            const bsModal = window.bootstrap && window.bootstrap.Modal
                ? window.bootstrap.Modal.getInstance(modalEl)
                : null;
            _resolvedBySend = true;
            _finishPending(trimmed);
            if (bsModal) bsModal.hide();
        });

        modalEl.addEventListener('hidden.bs.modal', function () {
            _setChannelPushButtonsLocked(false);
            if (!_resolvedBySend && typeof _pendingResolve === 'function') {
                _finishPending(null);
            }
            _resolvedBySend = false;
        });
    }

    /**
     * 재전송 변경 내용 입력 modal/sheet.
     * @param {string} pushKind 'measurement' | 'drawing'
     * @returns {Promise<string|null>} 확인 시 note, 취소 시 null
     */
    function erpPromptChannelPushResendNote(pushKind) {
        erpMountChannelPushResendModal();

        if (typeof _pendingResolve === 'function') {
            return Promise.resolve(null);
        }

        const modalEl = document.getElementById('erpChannelPushResendModal');
        const textarea = document.getElementById('erp-channel-push-resend-note');
        const titleEl = document.getElementById('erp-channel-push-resend-title');
        if (!modalEl || !textarea) {
            return Promise.resolve(null);
        }

        const label = PUSH_LABELS[pushKind] || 'PUSH';
        if (titleEl) titleEl.textContent = '재전송 확인 · ' + label;
        textarea.value = '';
        _resolvedBySend = false;

        const bsModal = window.bootstrap && window.bootstrap.Modal
            ? window.bootstrap.Modal.getOrCreateInstance(modalEl)
            : null;
        if (!bsModal) {
            const fallback = window.prompt('변경 내용을 입력해주세요');
            const trimmed = (fallback || '').trim();
            return Promise.resolve(trimmed.length >= MIN_NOTE_LEN ? trimmed : null);
        }

        return new Promise(function (resolve) {
            _pendingResolve = resolve;
            _setChannelPushButtonsLocked(true);
            bsModal.show();
            window.setTimeout(function () {
                textarea.focus();
            }, 280);
        });
    }

    // --- PUSH 종류 선택 시트 (모바일 하단 액션바 전용) ---------------------------------
    // 모바일 액션바에 PUSH 버튼 3개를 나란히 두면 좁은 폭에서 라벨이 깨지므로,
    // 버튼 1개 → 시트에서 영발/발주/AS 중 선택으로 바꾼다. 재전송 note modal 과
    // 겹치지 않도록 선택 결과는 시트가 완전히 닫힌 뒤(hidden.bs.modal) 반환한다.
    let _pendingKindResolve = null;
    let _pickedKind = null;

    function _finishPendingKind(value) {
        if (typeof _pendingKindResolve !== 'function') return;
        const resolve = _pendingKindResolve;
        _pendingKindResolve = null;
        resolve(value);
    }

    /** 선택 시트 버튼/닫힘 이벤트 singleton bind. */
    function erpMountChannelPushPickerModal() {
        if (window.__ERP_CHANNEL_PUSH_PICKER_BOUND) return;
        const modalEl = document.getElementById('erpChannelPushPickerModal');
        if (!modalEl) return;
        window.__ERP_CHANNEL_PUSH_PICKER_BOUND = true;

        modalEl.querySelectorAll('[data-erp-push-kind]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                _pickedKind = btn.getAttribute('data-erp-push-kind') || null;
                const bsModal = window.bootstrap && window.bootstrap.Modal
                    ? window.bootstrap.Modal.getInstance(modalEl)
                    : null;
                if (bsModal) {
                    bsModal.hide();
                    return;
                }
                _finishPendingKind(_pickedKind);
                _pickedKind = null;
            });
        });

        modalEl.addEventListener('hidden.bs.modal', function () {
            const picked = _pickedKind;
            _pickedKind = null;
            _finishPendingKind(picked);
        });
    }

    /**
     * PUSH 종류 선택 시트.
     * @returns {Promise<string|null>} 선택 시 push_kind, 취소/닫힘 시 null
     */
    function erpPromptChannelPushKind() {
        erpMountChannelPushPickerModal();

        const modalEl = document.getElementById('erpChannelPushPickerModal');
        if (!modalEl || typeof _pendingKindResolve === 'function') {
            return Promise.resolve(null);
        }

        const bsModal = window.bootstrap && window.bootstrap.Modal
            ? window.bootstrap.Modal.getOrCreateInstance(modalEl)
            : null;
        if (!bsModal) {
            return Promise.resolve(null);
        }

        _pickedKind = null;
        return new Promise(function (resolve) {
            _pendingKindResolve = resolve;
            bsModal.show();
        });
    }

    window.erpChannelPushHistoryKey = erpChannelPushHistoryKey;
    window.erpHasPriorChannelPush = erpHasPriorChannelPush;
    window.erpIsChannelPushResendNoteRequired = erpIsChannelPushResendNoteRequired;
    window.erpMarkChannelPushSent = erpMarkChannelPushSent;
    window.erpMountChannelPushResendModal = erpMountChannelPushResendModal;
    window.erpMountChannelPushPickerModal = erpMountChannelPushPickerModal;
    window.erpPromptChannelPushResendNote = erpPromptChannelPushResendNote;
    window.erpPromptChannelPushKind = erpPromptChannelPushKind;
})();
