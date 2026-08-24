/**
 * ERP 알림톡 수동 발송 — 미리보기 확인 modal/sheet (PC·모바일 표면).
 *
 * 버튼 클릭 시점에만 GET preview 를 호출한다(전역 프리페치 없음, perf G1).
 * 본문은 저장본 SSOT 라 미저장 입력이 있으면 preview 전에 기존 통합 저장을 먼저 돌린다
 * (T13 — 화면값 직접 조립은 저장본 불일치 발송 사고 위험이라 하지 않는다).
 * document 위임 + window.__FOMS_ALIMTALK_BOUND 싱글톤으로 fragment 재실행에도
 * 리스너가 중복 등록되지 않는다(perf G4).
 *
 * 태블릿 표면(tablet-measure-form.js)은 이 파일이 로드되지 않는 대시보드에서 동작하므로
 * 같은 흐름을 window.confirm 기반으로 자체 구현한다(채널톡 pushManual 선례와 동일).
 */
(function () {
    'use strict';

    if (window.__FOMS_ALIMTALK_BOUND) return;
    window.__FOMS_ALIMTALK_BOUND = true;

    // 서버 자격/오류 코드 → 사용자 문구. tablet-measure-form.js 의 동일 맵과 미러 관계다.
    const REASON_LABELS = {
        order_not_found: '주문을 찾을 수 없습니다',
        not_configured: '알림톡 서버 설정이 없습니다',
        not_eligible: '실측 일정이 확정되지 않았습니다',
        no_valid_phone: '고객 휴대폰 번호가 올바르지 않습니다',
        brand_profile_missing: '이 발주사의 알림톡 발신프로필이 아직 등록되지 않았습니다',
        auth: '알림톡 인증 정보가 올바르지 않습니다',
        balance: '알림톡 잔액이 부족합니다',
        template_mismatch: '승인된 템플릿과 본문이 일치하지 않습니다',
        invalid_phone: '수신 번호가 올바르지 않습니다',
        length_exceeded: '본문이 1,000자를 넘었습니다',
        network: '전송 중 네트워크 오류가 발생했습니다',
    };

    let _busy = false;

    /** @returns {string} 사용자에게 보여줄 사유 문구 */
    function erpAlimtalkReasonLabel(code) {
        return REASON_LABELS[code] || String(code || '알 수 없는 오류');
    }

    /** @returns {number} 현재 주문 id(아직 저장 전이면 0). */
    function erpAlimtalkOrderId() {
        return parseInt(String(window.ORDER_ID || '0'), 10) || 0;
    }

    /** @returns {boolean} 저장되지 않은 편집이 남아 있는지 */
    function erpAlimtalkIsDirty() {
        const autosave = window.fomsErpAutosave;
        return !!(autosave && typeof autosave.isDirty === 'function' && autosave.isDirty());
    }

    /**
     * 미저장 편집이 있으면 기존 ERP 통합 저장(erpSaveStructured)을 먼저 실행한다(T13).
     *
     * 알림톡 본문은 서버가 저장된 structured_data 로 조립하므로, 저장 없이 발송하면
     * 화면에 보이는 값과 다른 본문이 고객에게 나간다. 저장 실패 시 발송을 중단한다.
     *
     * @param {function(string):void} [setStatus] 상태 문구 표시(기본: 알림톡 상태 줄).
     * @returns {Promise<boolean>} 발송 흐름을 계속해도 되는지(저장 실패면 false).
     */
    async function erpAlimtalkEnsureSaved(setStatus) {
        const say = typeof setStatus === 'function' ? setStatus : erpAlimtalkSetStatus;
        const dirty = erpAlimtalkIsDirty();
        // 아직 저장된 주문이 없거나(신규) draft 백업이면 **저장본이 없어서** 서버 자격 판정이
        // 통과할 수 없다. 예전에는 여기서 저장을 건너뛰고 not_eligible 을 그대로 보여줬는데,
        // 사용자에겐 "입력해 놨는데 발송이 안 된다"로만 읽힌다(2026-08-24 사용자 보고).
        // 채널 PUSH(erpRunChannelPush)와 **같은 규칙**으로 여기서 먼저 저장(draft면 승격)한다.
        const needsPersist = !erpAlimtalkOrderId()
            || (typeof window.erpIsDraftBackedOrder === 'function'
                && window.erpIsDraftBackedOrder());
        if (!dirty && !needsPersist) return true;
        if (typeof window.erpSaveStructured !== 'function') {
            say('저장되지 않은 변경이 있습니다. 저장 후 발송해주세요.');
            return false;
        }
        // 필수값 검증(고객명·전화·주소·제품)은 저장 함수가 그대로 한다 — 누락이면 저장이
        // 실패하고 아래에서 발송이 멈춘다(조용히 옛 저장본으로 나가지 않는다).
        say(dirty ? '저장 중…' : '발송 전 주문을 저장합니다…');
        let result = null;
        try {
            result = await window.erpSaveStructured({ redirect: false });
        } catch (e) {
            result = null;
        }
        if (!result || result.success !== true) {
            say('저장 실패 — 저장 후 다시 시도해주세요.');
            return false;
        }
        return true;
    }

    /** 버튼 옆 상태 한 줄(있는 표면에서만) 갱신. */
    function erpAlimtalkSetStatus(text) {
        const nodes = document.querySelectorAll('.erp-alimtalk-status');
        for (let i = 0; i < nodes.length; i += 1) {
            nodes[i].textContent = text || '';
        }
    }

    /** 모달 상단 경고/안내 줄 토글. */
    function _setNotice(text) {
        const el = document.getElementById('erp-alimtalk-notice');
        if (!el) return;
        el.textContent = text || '';
        el.classList.toggle('d-none', !text);
    }

    /** 마지막 발송 이력 줄 렌더(없으면 숨김). */
    function _setLast(last) {
        const el = document.getElementById('erp-alimtalk-last');
        if (!el) return;
        let text = '';
        if (last && last.error) {
            text = '마지막 시도 실패 · ' + erpAlimtalkReasonLabel(last.error);
        } else if (last && last.sent_at) {
            text = '최근 발송 · ' + String(last.sent_at).replace('T', ' ').slice(0, 16);
        }
        el.textContent = text;
        el.classList.toggle('d-none', !text);
    }

    /** @returns {Object|null} bootstrap Modal 인스턴스 */
    function _modal() {
        const el = document.getElementById('erpAlimtalkModal');
        if (!el || !window.bootstrap || !window.bootstrap.Modal) return null;
        return window.bootstrap.Modal.getOrCreateInstance(el);
    }

    /** 모달 본문/버튼을 preview 응답으로 채운다. @returns {boolean} 발송 가능 여부 */
    function _fillModal(data) {
        const pre = document.getElementById('erp-alimtalk-preview');
        const confirmBtn = document.getElementById('erp-alimtalk-confirm-btn');
        if (pre) pre.textContent = data.text || '';
        _setLast(data.last);

        let blocked = '';
        if (!data.configured) {
            blocked = '서버 미설정 — 관리자에게 알림톡 발신 설정을 요청해주세요.';
        } else if (!data.eligible) {
            blocked = '발송 불가 — ' + erpAlimtalkReasonLabel(data.ineligible_reason);
        } else if (erpAlimtalkIsDirty()) {
            blocked = '저장되지 않은 변경이 있습니다. 저장 후 발송해주세요.';
        }
        const sendable = !blocked;
        if (!blocked && data.last && (data.last.sent_at || data.last.error)) {
            _setNotice('이미 발송 이력이 있습니다. 확인 시 고객에게 다시 발송됩니다.');
        } else {
            _setNotice(blocked);
        }
        if (confirmBtn) {
            confirmBtn.disabled = !sendable;
            confirmBtn.title = sendable ? '' : blocked;
        }
        return sendable;
    }

    /**
     * 방금 기록된 발송 이력을 발송 흔적 칩(erp-alimtalk-trace.js)에 전달한다.
     *
     * 칩은 sd 만 읽어 그리므로 발송 직후에는 화면의 사본이 낡아 있다. 서버 응답에 실려 온
     * 이력을 그대로 넘겨 추가 조회 없이 갱신한다. 칩 모듈이 없는 표면에서는 무해하다.
     *
     * @param {Object|null} record send-manual 응답의 ``last``.
     */
    function _publishTrace(record) {
        document.dispatchEvent(new CustomEvent('foms:alimtalk-trace-update', {
            detail: { record: record || null },
        }));
    }

    /** POST send-manual — CSRF 헤더는 layout_head 전역 fetch 래퍼가 붙인다. */
    function _send(orderId) {
        const confirmBtn = document.getElementById('erp-alimtalk-confirm-btn');
        if (confirmBtn) confirmBtn.disabled = true;
        erpAlimtalkSetStatus('알림톡 발송 중…');

        return fetch('/api/kakao/alimtalk/send-manual/' + orderId, {
            method: 'POST',
            credentials: 'same-origin',
        })
            .then(function (res) {
                return res.json().then(function (body) { return body; });
            })
            .then(function (body) {
                const sent = !!(body && body.success && body.data && body.data.sent);
                // 성공·실패 모두 방금 기록된 이력을 칩에 흘려보낸다(추가 조회 없음, T15).
                _publishTrace(body && body.data ? body.data.last : null);
                if (sent) {
                    erpAlimtalkSetStatus('알림톡 발송 완료');
                    const modal = _modal();
                    if (modal) modal.hide();
                    return;
                }
                const code = (body && (body.error || (body.data && body.data.error))) || 'network';
                erpAlimtalkSetStatus('알림톡 발송 실패 · ' + erpAlimtalkReasonLabel(code));
                _setNotice('발송 실패 — ' + erpAlimtalkReasonLabel(code));
                if (confirmBtn) confirmBtn.disabled = false;
            })
            .catch(function () {
                erpAlimtalkSetStatus('알림톡 발송 실패 · ' + erpAlimtalkReasonLabel('network'));
                _setNotice('발송 실패 — ' + erpAlimtalkReasonLabel('network'));
                if (confirmBtn) confirmBtn.disabled = false;
            });
    }

    /** 버튼 클릭 진입점: (미저장이면) 자동 저장 → preview 조회 → 모달 표시. */
    async function erpOpenAlimtalkModal() {
        if (_busy) return;
        _busy = true;
        try {
            // 저장이 **먼저**다. 아직 저장 전인 주문에서 여기서 되돌려보내면 사용자는
            // 입력해 둔 내용을 두고 "발송이 안 된다"만 본다(채널 PUSH 와 같은 동선).
            if (!(await erpAlimtalkEnsureSaved())) return;
            // 저장이 주문을 만들거나 승격했으면 ORDER_ID 가 갱신된다 — 저장 뒤에 읽는다.
            const orderId = erpAlimtalkOrderId();
            if (!orderId) {
                erpAlimtalkSetStatus('저장 후 발송할 수 있습니다.');
                return;
            }
            erpAlimtalkSetStatus('미리보기 불러오는 중…');

            const res = await fetch('/api/kakao/alimtalk/preview/' + orderId, {
                credentials: 'same-origin',
            });
            const body = await res.json();
            if (!body || !body.success || !body.data) {
                const code = (body && body.error) || 'network';
                erpAlimtalkSetStatus('미리보기 실패 · ' + erpAlimtalkReasonLabel(code));
                return;
            }
            erpAlimtalkSetStatus('');
            _fillModal(body.data);
            const modal = _modal();
            if (modal) {
                modal.show();
                return;
            }
            // bootstrap 미로드 폴백 — 본문 확인 후 즉시 발송 여부만 묻는다.
            if (window.confirm(body.data.text || '')) void _send(orderId);
        } catch (e) {
            erpAlimtalkSetStatus('미리보기 실패 · ' + erpAlimtalkReasonLabel('network'));
        } finally {
            _busy = false;
        }
    }

    // 위임 바인딩 — 클릭 시점에 요소를 조회하므로 fragment swap 후에도 유효하다.
    // 태블릿 버튼([data-tmf-alimtalk-send])은 자체 핸들러가 처리하므로 제외한다.
    document.addEventListener('click', function (ev) {
        const target = ev.target;
        if (!target || typeof target.closest !== 'function') return;
        const btn = target.closest('.erp-alimtalk-send-btn:not([data-tmf-alimtalk-send])');
        if (!btn) return;
        ev.preventDefault();
        erpOpenAlimtalkModal();
    });

    document.addEventListener('click', function (ev) {
        const target = ev.target;
        if (!target || typeof target.closest !== 'function') return;
        if (!target.closest('#erp-alimtalk-confirm-btn')) return;
        ev.preventDefault();
        const orderId = parseInt(String(window.ORDER_ID || '0'), 10) || 0;
        if (orderId) void _send(orderId);
    });

    // --- 알림톡 종류 선택 시트 (모바일 하단 액션바 전용) ----------------------------
    // dropdown 은 좁은 폭에서 메뉴가 액션바 위로 겹쳐 터치 대상이 무너진다.
    // PUSH 와 같은 선택 시트(erp-channel-push.css)로 통일한다.
    // 시트 안의 선택지는 PC 드롭다운과 같은 클래스를 그대로 달고 있으므로,
    // 시트가 완전히 닫힌 뒤 같은 버튼을 replay 클릭해 기존 위임 핸들러가 처리하게 한다
    // (모달 2개가 겹쳐 열려 backdrop 이 남는 것을 막는다).
    let _pendingPickBtn = null;

    /** 선택 시트 버튼/닫힘 이벤트 singleton bind. */
    function erpMountAlimtalkPickerModal() {
        if (window.__ERP_ALIMTALK_PICKER_BOUND) return;
        const modalEl = document.getElementById('erpAlimtalkPickerModal');
        if (!modalEl) return;
        window.__ERP_ALIMTALK_PICKER_BOUND = true;

        modalEl.querySelectorAll('.erp-channel-push-picker-options .foms-btn').forEach(function (btn) {
            btn.addEventListener('click', function (ev) {
                if (btn.dataset.erpAlimtalkReplay === '1') {
                    delete btn.dataset.erpAlimtalkReplay;
                    return;
                }
                ev.preventDefault();
                ev.stopPropagation();
                const bsModal = window.bootstrap && window.bootstrap.Modal
                    ? window.bootstrap.Modal.getInstance(modalEl)
                    : null;
                if (!bsModal) {
                    _replayPick(btn);
                    return;
                }
                _pendingPickBtn = btn;
                bsModal.hide();
            });
        });

        modalEl.addEventListener('hidden.bs.modal', function () {
            const btn = _pendingPickBtn;
            _pendingPickBtn = null;
            if (btn) _replayPick(btn);
        });
    }

    /** 선택지 버튼을 다시 클릭해 기존 위임 핸들러로 흘려보낸다. */
    function _replayPick(btn) {
        btn.dataset.erpAlimtalkReplay = '1';
        btn.click();
    }

    /** 알림톡 종류 선택 시트 열기. */
    function erpOpenAlimtalkPicker() {
        erpMountAlimtalkPickerModal();
        const modalEl = document.getElementById('erpAlimtalkPickerModal');
        if (!modalEl) {
            erpOpenAlimtalkModal();
            return;
        }
        const bsModal = window.bootstrap && window.bootstrap.Modal
            ? window.bootstrap.Modal.getOrCreateInstance(modalEl)
            : null;
        if (!bsModal) {
            erpOpenAlimtalkModal();
            return;
        }
        bsModal.show();
    }

    document.addEventListener('click', function (ev) {
        const target = ev.target;
        if (!target || typeof target.closest !== 'function') return;
        if (!target.closest('#erp-alimtalk-picker-btn')) return;
        ev.preventDefault();
        erpOpenAlimtalkPicker();
    });

    window.erpOpenAlimtalkModal = erpOpenAlimtalkModal;
    window.erpOpenAlimtalkPicker = erpOpenAlimtalkPicker;
    window.erpMountAlimtalkPickerModal = erpMountAlimtalkPickerModal;
    // 공유 링크(erp-share.js)도 같은 dirty 가드를 쓴다 — 로드 순서상 이 파일이 먼저다.
    window.fomsErpEnsureSavedForSend = erpAlimtalkEnsureSaved;
    window.erpAlimtalkReasonLabel = erpAlimtalkReasonLabel;
})();
