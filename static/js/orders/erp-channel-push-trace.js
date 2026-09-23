/**
 * ERP 채널톡 PUSH 발송 흔적 칩 — PUSH 를 '보냈는지'를 0클릭으로 남긴다 (2026-09-23).
 *
 * 지금까지는 PUSH 를 눌러도 버튼 글자가 3초 '전송완료'로 바뀌었다 돌아올 뿐이라, 화면을
 * 다시 열면 보냈는지 알 길이 없었다. 서버는 이미 종류별 이력을 남긴다
 * (`sd['channeltalk_push*']` = { pushed, sent_at, is_modified, ... }).
 *
 * 알림톡 흔적 칩(erp-alimtalk-trace.js)과 같은 원리다 — 주문 화면이 열릴 때 들어와 있는
 * `window.__erpLastStructuredData` 만 읽으므로 **칩을 그리는 데 서버 왕복이 없다**.
 * 발송 직후에는 `erpMarkChannelPushSent(kind, sentAt)` 가 사본의 `sent_at` 을 고치고
 * `foms:channel-push-trace-update` 를 쏜다 → 즉시 다시 그린다(추가 조회 없음).
 *
 * 모바일(축약형)은 **보낸 적이 있을 때만** 칩을 그린다 — 2026-09-21 사용자 제보(좁은
 * 액션바가 '아직 안 보냄' 칩 때문에 답답하다)와 같은 정책이다. PC 는 폭이 넉넉하므로
 * 미발송도 점선 칩으로 그린다(빈 자리는 '확인 못 함'으로 읽힌다).
 *
 * document 위임 + `window.__FOMS_CHANNEL_PUSH_TRACE_BOUND` 싱글톤이라 fragment 재실행에도
 * 리스너가 중복 등록되지 않는다(perf G4).
 */
(function () {
    'use strict';

    if (window.__FOMS_CHANNEL_PUSH_TRACE_BOUND) return;
    window.__FOMS_CHANNEL_PUSH_TRACE_BOUND = true;

    //: push 종류 → structured_data 이력 키·버튼과 같은 이름. 순서 = PC 칩 순서.
    //  서버 _PUSH_KIND_CONFIG / _ESTIMATE_PUSH_HISTORY_KEY 와 같은 키다.
    const PUSH_KINDS = [
        { kind: 'drawing', key: 'channeltalk_push_drawing', label: '발주 PUSH' },
        { kind: 'measurement', key: 'channeltalk_push', label: '영발 PUSH' },
        { kind: 'measure_room', key: 'channeltalk_push_measure_room', label: '실측 PUSH' },
        { kind: 'as', key: 'channeltalk_push_as', label: 'AS PUSH' },
        { kind: 'estimate', key: 'channeltalk_push_estimate', label: '견적서 PUSH' },
        { kind: 'drawing_room', key: 'channeltalk_push_drawing_room', label: '도면방 PUSH' },
    ];

    /** @returns {Array<{kind: string, label: string, record: Object}>} 보낸 적 있는 종류들. */
    function _sentRecords() {
        const sd = window.__erpLastStructuredData;
        if (!sd || typeof sd !== 'object') return [];
        const out = [];
        for (let i = 0; i < PUSH_KINDS.length; i += 1) {
            const spec = PUSH_KINDS[i];
            const record = sd[spec.key];
            if (!record || typeof record !== 'object') continue;
            if (!record.pushed && !record.sent_at) continue;
            out.push({ kind: spec.kind, label: spec.label, record: record });
        }
        return out;
    }

    /** @returns {number} 정렬용 발송 시각(ms). 모르면 0. */
    function _sentMs(record) {
        if (!record || !record.sent_at) return 0;
        const raw = String(record.sent_at);
        const zoned = /(Z|[+-]\d{2}:?\d{2})$/.test(raw) ? raw : raw + 'Z';
        const ms = new Date(zoned).getTime();
        return isNaN(ms) ? 0 : ms;
    }

    /**
     * ISO 문자열을 KST `MM-DD HH:MM` 으로 만든다(알림톡 칩과 같은 표기).
     * 타임존 표기가 없으면 UTC 로 읽는다(프로젝트 timestamp 규약).
     *
     * @param {string} value ISO 문자열.
     * @returns {string} 표시 문자열(파싱 불가면 빈 문자열).
     */
    function _formatWhen(value) {
        const ms = _sentMs({ sent_at: value });
        if (!ms) return '';
        const parts = new Intl.DateTimeFormat('ko-KR', {
            timeZone: 'Asia/Seoul',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
        }).formatToParts(new Date(ms));
        const pick = function (type) {
            const found = parts.find(function (p) { return p.type === type; });
            return found ? found.value : '';
        };
        return pick('month') + '-' + pick('day') + ' ' + pick('hour') + ':' + pick('minute');
    }

    /** 칩 조각 하나(구분점 포함)를 붙인다. */
    function _appendPart(chip, text, className) {
        if (!text) return;
        if (chip.childElementCount > 1) {
            const sep = document.createElement('span');
            sep.className = 'erp-channel-push-trace__sep';
            sep.textContent = '·';
            chip.appendChild(sep);
        }
        const node = document.createElement('span');
        node.className = className;
        node.textContent = text;
        chip.appendChild(node);
    }

    /** @returns {HTMLElement} 점(✓ 또는 빈 점선) 하나를 단 칩 뼈대. */
    function _chipShell(state) {
        const chip = document.createElement('span');
        chip.className = 'erp-channel-push-trace erp-channel-push-trace--' + state;
        chip.setAttribute('data-foms-no-autodismiss', '1');
        const dot = document.createElement('span');
        dot.className = 'erp-channel-push-trace__dot';
        dot.setAttribute('aria-hidden', 'true');
        dot.textContent = state === 'none' ? '' : '✓';
        chip.appendChild(dot);
        return chip;
    }

    /**
     * 보낸 종류 1개의 칩.
     *
     * @param {{label: string, record: Object}} entry 종류 이름 + 이력.
     * @returns {HTMLElement} 칩.
     */
    function _buildSentChip(entry) {
        const chip = _chipShell('sent');
        chip.setAttribute('data-erp-channel-push-kind', entry.kind);
        const resent = !!entry.record.is_modified;
        _appendPart(chip, entry.label + (resent ? ' 다시 보냄' : ' 보냄'),
                    'erp-channel-push-trace__label');
        _appendPart(chip, _formatWhen(entry.record.sent_at), 'erp-channel-push-trace__when');
        chip.title = entry.label + (resent ? '를 다시 보낸 기록입니다.' : '를 보낸 기록입니다.');
        return chip;
    }

    /** @returns {HTMLElement} PC 전용 미발송 칩. */
    function _buildNoneChip() {
        const chip = _chipShell('none');
        _appendPart(chip, 'PUSH 아직 안 보냄', 'erp-channel-push-trace__label');
        chip.title = '아직 이 주문으로 채널톡 PUSH 를 보내지 않았습니다.';
        return chip;
    }

    /**
     * 모바일 축약형: 가장 최근 1종만 칩으로, 나머지는 '+N' 으로 접는다(좁은 액션바).
     *
     * @param {Array} entries 보낸 종류들(최근 순).
     * @returns {HTMLElement} 칩.
     */
    function _buildCompactChip(entries) {
        const chip = _buildSentChip(entries[0]);
        if (entries.length > 1) {
            _appendPart(chip, '+' + (entries.length - 1), 'erp-channel-push-trace__more');
            chip.title = entries.map(function (e) {
                return e.label + ' ' + (_formatWhen(e.record.sent_at) || '보냄');
            }).join('\n');
        }
        return chip;
    }

    /** 모든 칩 자리를 현재 이력으로 다시 그린다. */
    function erpChannelPushTraceRender() {
        const slots = document.querySelectorAll('[data-erp-channel-push-trace]');
        if (!slots.length) return;
        const entries = _sentRecords().sort(function (a, b) {
            return _sentMs(b.record) - _sentMs(a.record);
        });
        for (let i = 0; i < slots.length; i += 1) {
            const slot = slots[i];
            const compact = slot.getAttribute('data-erp-channel-push-trace') === 'compact';
            slot.textContent = '';
            if (!entries.length) {
                // 모바일은 미발송 칩을 그리지 않는다 — 빈 자리는 CSS(:empty)가 접는다.
                if (!compact) slot.appendChild(_buildNoneChip());
                continue;
            }
            if (compact) {
                slot.appendChild(_buildCompactChip(entries));
                continue;
            }
            for (let j = 0; j < entries.length; j += 1) {
                slot.appendChild(_buildSentChip(entries[j]));
            }
        }
    }

    // --- 배선 -----------------------------------------------------------------

    // 발송 성공 직후 erpMarkChannelPushSent 가 사본을 고치고 알린다(추가 조회 없음).
    document.addEventListener('foms:channel-push-trace-update', erpChannelPushTraceRender);

    // 구조화 데이터가 늦게 도착하는 화면은 로드 완료 신호를 받아 다시 그린다.
    document.addEventListener('foms:erp-structured-loaded', erpChannelPushTraceRender);

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', erpChannelPushTraceRender);
    } else {
        erpChannelPushTraceRender();
    }

    window.erpChannelPushTraceRender = erpChannelPushTraceRender;
})();
