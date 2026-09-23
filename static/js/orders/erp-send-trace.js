/**
 * ERP 주문 화면 발송 기록 칩 (2026-09-23 목업 제안 A). 알림톡(예약 안내·공유 링크)과 PUSH 를
 * 한 가지 칩 문법 "[보낸 길 아이콘] 무엇 · 언제" 로 한 자리에 그린다 — 예전엔 두 모듈이 따로 그려
 * 이름("보냄" vs "실측 PUSH 보냄")·정렬이 제각각이었다. 시각은 짧게(오늘 14:05 · 어제 18:30 ·
 * 그 전 9/21), 다시 보냄은 ↻, 못 보낸 것 먼저 그다음 최근 순, 왼쪽부터.
 * 표면: `wide`(PC) 전부 나열 + 예약 안내 미발송 점선 칩(T15) / `fold`(모바일) 요약 한 줄 → 누르면
 * 두 칸 격자, 기록이 없으면 비운다. 화면 사본(`__erpLastStructuredData`)만 읽는다(서버 왕복 0).
 * 칩을 누르면 기존 발송 이력 창(erp-alimtalk-trace.js)이 열린다.
 */
(function () {
    'use strict';

    if (window.__FOMS_SEND_TRACE_BOUND) return;
    window.__FOMS_SEND_TRACE_BOUND = true;

    //: 벤더가 '문자로 대체발송했다'고 답하는 type 들(erp-alimtalk-trace.js 와 같은 값).
    const TEXT_CHANNELS = ['SMS', 'LMS', 'MMS'];

    //: push 종류 → structured_data 이력 키·칩 이름. 서버 _PUSH_KIND_CONFIG / _ESTIMATE_PUSH_HISTORY_KEY 와 같은 키.
    const PUSH_KINDS = [
        { key: 'channeltalk_push_drawing', label: '발주 PUSH' },
        { key: 'channeltalk_push', label: '영발 PUSH' },
        { key: 'channeltalk_push_measure_room', label: '실측 PUSH' },
        { key: 'channeltalk_push_as', label: 'AS PUSH' },
        { key: 'channeltalk_push_estimate', label: '견적서 PUSH' },
        { key: 'channeltalk_push_drawing_room', label: '도면방 PUSH' },
    ];

    //: 공유 링크 종류 — 칩 폭(모바일 두 칸 격자 약 176px)에 들어가도록 짧은 이름을 쓴다.
    //  원래 이름(도면·계약서 링크)은 이력 창에 그대로 나온다.
    const SHARE_LABELS = { drawing: '도면 링크', estimate: '계약서 링크', bundle: '도면+계약 링크' };

    const SVG_OPEN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        + 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">';
    const ICONS = {
        alim: SVG_OPEN + '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9.6 9.6 0 0 1-3.6-.7L3 21l1.6-4.4A8 8 0 0 1 3 11.5 8.6 8.6 0 0 1 12 3a8.6 8.6 0 0 1 9 8.5z"></path></svg>',
        push: SVG_OPEN + '<path d="M22 2 11 13"></path><path d="M22 2 15 22l-4-9-9-4 20-7z"></path></svg>',
        sms: SVG_OPEN + '<rect x="6" y="2" width="12" height="20" rx="2"></rect><path d="M11 18h2"></path></svg>',
        fail: SVG_OPEN + '<circle cx="12" cy="12" r="10"></circle><path d="M12 7v6"></path><path d="M12 17h.01"></path></svg>',
        resend: SVG_OPEN + '<path d="M21 12a9 9 0 1 1-3-6.7"></path><path d="M21 3v6h-6"></path></svg>',
        up: SVG_OPEN + '<path d="m6 15 6-6 6 6"></path></svg>',
        down: SVG_OPEN + '<path d="m6 9 6 6 6-6"></path></svg>',
    };

    //: 모바일 펼침 상태 — 다시 그려도(발송 직후 등) 펼친 채 유지한다.
    let _foldOpen = false;

    /** @returns {number} ISO 문자열 → ms(타임존 표기가 없으면 UTC — 프로젝트 timestamp 규약). 모르면 0. */
    function _ms(value) {
        if (!value) return 0;
        const raw = String(value);
        const zoned = /(Z|[+-]\d{2}:?\d{2})$/.test(raw) ? raw : raw + 'Z';
        const ms = new Date(zoned).getTime();
        return isNaN(ms) ? 0 : ms;
    }

    /** @returns {{day: string, month: number, date: number, clock: string}} KST 날짜 조각. */
    function _kstParts(ms) {
        const parts = new Intl.DateTimeFormat('ko-KR', {
            timeZone: 'Asia/Seoul',
            year: 'numeric',
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
        const hour = pick('hour') === '24' ? '00' : pick('hour');
        return {
            day: pick('year') + '-' + pick('month') + '-' + pick('day'),
            month: parseInt(pick('month'), 10),
            date: parseInt(pick('day'), 10),
            clock: hour + ':' + pick('minute'),
        };
    }

    /** 칩 시각: 오늘 `14:05`, 어제 `어제 18:30`, 그 전 `9/21`. nowMs 는 기준 시각(테스트가 고정). */
    function shortWhen(ms, nowMs) {
        if (!ms) return '';
        const sent = _kstParts(ms);
        if (sent.day === _kstParts(nowMs).day) return sent.clock;
        if (sent.day === _kstParts(nowMs - 24 * 60 * 60 * 1000).day) return '어제 ' + sent.clock;
        return sent.month + '/' + sent.date;
    }

    function _reasonLabel(code) {
        if (typeof window.erpAlimtalkReasonLabel === 'function') {
            return window.erpAlimtalkReasonLabel(code);
        }
        return String(code || '알 수 없는 오류');
    }

    function _isText(channel) {
        return TEXT_CHANNELS.indexOf(String(channel || '').toUpperCase()) !== -1;
    }

    /** 구조화 데이터 → {chips(정렬 끝남), measurementSent(예약 안내 기록이 있는지)}. */
    function buildModel(sd, nowMs) {
        const chips = [];
        const data = sd && typeof sd === 'object' ? sd : {};

        const measure = data.alimtalk_measurement;
        const measurementSent = !!(measure && typeof measure === 'object' && (measure.sent_at || measure.error));
        if (measurementSent) {
            const failed = !!measure.error;
            chips.push({
                kind: failed ? 'fail' : (_isText(measure.channel) ? 'sms' : 'alim'),
                label: failed ? '예약 안내 실패' : '예약 안내',
                meta: failed ? _reasonLabel(measure.error) : '',
                ms: _ms(measure.sent_at),
                resent: false,
            });
        }

        const share = data.alimtalk_share;
        if (share && typeof share === 'object' && (share.sent_at || share.error)) {
            const failed = !!share.error;
            const name = SHARE_LABELS[share.kind] || '링크';
            chips.push({
                kind: failed ? 'fail' : (String(share.channel || '') === 'sms' ? 'sms' : 'alim'),
                label: failed ? name + ' 실패' : name,
                meta: failed ? _reasonLabel(share.error) : '',
                ms: _ms(share.sent_at),
                resent: false,
            });
        }

        for (let i = 0; i < PUSH_KINDS.length; i += 1) {
            const spec = PUSH_KINDS[i];
            const record = data[spec.key];
            if (!record || typeof record !== 'object' || (!record.pushed && !record.sent_at)) continue;
            chips.push({
                kind: 'push',
                label: spec.label,
                meta: '',
                ms: _ms(record.sent_at),
                resent: !!record.is_modified,
            });
        }

        for (let i = 0; i < chips.length; i += 1) {
            if (!chips[i].meta) chips[i].meta = shortWhen(chips[i].ms, nowMs);
        }
        chips.sort(function (a, b) {
            const af = a.kind === 'fail' ? 0 : 1;
            const bf = b.kind === 'fail' ? 0 : 1;
            if (af !== bf) return af - bf;
            return b.ms - a.ms;
        });
        return { chips: chips, measurementSent: measurementSent };
    }

    /** @returns {HTMLElement} 칩 하나. 이력 창이 있으면 누르면 열리는 버튼. */
    function _chip(chip, clickable) {
        const node = document.createElement(clickable ? 'button' : 'span');
        if (clickable) {
            node.type = 'button';
            node.setAttribute('data-erp-alimtalk-trace-open', '1');
            node.title = '눌러서 발송 이력을 봅니다.';
        }
        node.className = 'erp-send-chip erp-send-chip--' + chip.kind;
        node.setAttribute('data-foms-no-autodismiss', '1');
        if (ICONS[chip.kind]) node.insertAdjacentHTML('beforeend', ICONS[chip.kind]);
        const label = document.createElement('span');
        label.className = 'erp-send-chip__label';
        label.textContent = chip.label;
        node.appendChild(label);
        if (chip.resent) {
            node.insertAdjacentHTML('beforeend', ICONS.resend.replace('<svg ', '<svg class="erp-send-chip__re" '));
            node.setAttribute('aria-label', chip.label + ' 다시 보냄 ' + chip.meta);
        }
        if (chip.meta) {
            const meta = document.createElement('span');
            meta.className = 'erp-send-chip__meta';
            meta.textContent = chip.meta;
            node.appendChild(meta);
        }
        return node;
    }

    /** @returns {HTMLElement} 예약 안내 미발송 점선 칩(PC 전용). */
    function _noneChip(clickable) {
        const node = _chip({ kind: 'none', label: '예약 안내', meta: '아직 안 보냄', resent: false }, clickable);
        if (clickable) node.title = '아직 실측 예약 안내를 보내지 않았습니다. 눌러서 발송 이력을 봅니다.';
        return node;
    }

    function _renderWide(slot, model, clickable) {
        slot.textContent = '';
        for (let i = 0; i < model.chips.length; i += 1) {
            slot.appendChild(_chip(model.chips[i], clickable));
        }
        if (!model.measurementSent) slot.appendChild(_noneChip(clickable));
    }

    function _renderFold(slot, model, clickable) {
        slot.textContent = '';
        const chips = model.chips;
        if (!chips.length) return;
        const fails = chips.filter(function (c) { return c.kind === 'fail'; });
        const latest = chips.find(function (c) { return c.kind !== 'fail'; }) || null;

        if (_foldOpen) {
            const grid = document.createElement('div');
            grid.className = 'erp-send-trace__grid';
            grid.id = 'erp-send-trace-grid';
            for (let i = 0; i < chips.length; i += 1) grid.appendChild(_chip(chips[i], clickable));
            slot.appendChild(grid);
        }

        const summary = document.createElement('button');
        summary.type = 'button';
        summary.className = 'erp-send-trace__summary';
        summary.setAttribute('data-erp-send-trace-toggle', '1');
        summary.setAttribute('data-foms-no-autodismiss', '1');
        summary.setAttribute('aria-expanded', _foldOpen ? 'true' : 'false');
        summary.setAttribute('aria-controls', 'erp-send-trace-grid');
        if (fails.length) {
            const bad = document.createElement('span');
            bad.className = 'erp-send-chip erp-send-chip--fail erp-send-trace__fail';
            bad.insertAdjacentHTML('beforeend', ICONS.fail);
            const text = document.createElement('span');
            text.className = 'erp-send-chip__label';
            text.textContent = '실패 ' + fails.length;
            bad.appendChild(text);
            summary.appendChild(bad);
        }
        const title = document.createElement('span');
        title.className = 'erp-send-trace__title';
        title.textContent = '발송 기록 ' + chips.length;
        summary.appendChild(title);
        const recent = document.createElement('span');
        recent.className = 'erp-send-trace__recent';
        recent.textContent = latest ? '최근 ' + latest.label + ' · ' + latest.meta : '';
        summary.appendChild(recent);
        summary.insertAdjacentHTML('beforeend', (_foldOpen ? ICONS.down : ICONS.up)
            .replace('<svg ', '<svg class="erp-send-trace__chev" '));
        slot.appendChild(summary);
    }

    /** 모든 발송 기록 자리를 현재 구조화 데이터로 다시 그린다. */
    function erpSendTraceRender() {
        const slots = document.querySelectorAll('[data-erp-send-trace]');
        if (!slots.length) return;
        const model = buildModel(window.__erpLastStructuredData, Date.now());
        const clickable = !!document.getElementById('erpAlimtalkTraceModal');
        for (let i = 0; i < slots.length; i += 1) {
            const slot = slots[i];
            if (slot.getAttribute('data-erp-send-trace') === 'fold') {
                _renderFold(slot, model, clickable);
            } else {
                _renderWide(slot, model, clickable);
            }
        }
    }

    document.addEventListener('click', function (ev) {
        const target = ev.target;
        if (!target || typeof target.closest !== 'function') return;
        if (!target.closest('[data-erp-send-trace-toggle]')) return;
        ev.preventDefault();
        _foldOpen = !_foldOpen;
        erpSendTraceRender();
    });

    // 다른 모듈이 이력 사본을 고친 뒤(발송 직후·채널 확정·구조화 데이터 도착) 다시 그린다.
    // 사본을 고치는 쪽 리스너가 먼저 돌도록 한 틱 미룬다.
    function _later() { setTimeout(erpSendTraceRender, 0); }
    ['foms:erp-structured-loaded', 'foms:alimtalk-trace-update', 'foms:share-trace-update',
        'foms:channel-push-trace-update', 'foms:send-trace-refresh'].forEach(function (name) {
        document.addEventListener(name, _later);
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', erpSendTraceRender);
    } else {
        erpSendTraceRender();
    }

    window.erpSendTraceRender = erpSendTraceRender;
    // 테스트·다른 화면이 같은 규칙을 쓰도록 순수 함수만 내보낸다.
    window.erpSendTraceModel = buildModel;
    window.erpSendTraceShortWhen = shortWhen;
})();
