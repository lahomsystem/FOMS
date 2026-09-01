/**
 * ERP 알림톡 발송 흔적 칩 — 주문 화면에 '보냈는지'를 0클릭으로 남긴다 (T15).
 *
 * 지금까지는 드롭다운 → 항목 → 모달을 거쳐야 마지막 발송이 보였다. 확인 비용이 커서 아무도
 * 확인하지 않고 눌렀고, 같은 고객에게 예약 안내가 두 번 나가는 걸 막을 방법이 화면에 없었다.
 *
 * 데이터는 `sd['alimtalk_measurement']` 다. 주문 화면이 열릴 때 이미
 * `window.__erpLastStructuredData` 로 들어와 있으므로 **칩을 그리는 데 서버 왕복이 없다**.
 * 발송 직후 갱신도 send-manual 응답의 `last` 를 그대로 쓴다(추가 조회 없음).
 *
 * 채널(카톡 / 문자 대체발송)만은 발송 직후에 알 수 없다 — 접수 시점 type 은 항상 ATA 이고
 * 카톡이 실패해야 벤더가 문자로 바꾼다. 그래서 발송 1분 뒤에 confirm-channel 을 한 번 부른다.
 * 타이머 도중 화면을 떠났으면 다음에 주문을 열 때 같은 조건으로 한 번 더 시도한다(멱등).
 *
 * document 위임 + `window.__FOMS_ALIMTALK_TRACE_BOUND` 싱글톤이라 fragment 재실행에도
 * 리스너가 중복 등록되지 않는다(perf G4).
 */
(function () {
    'use strict';

    if (window.__FOMS_ALIMTALK_TRACE_BOUND) return;
    window.__FOMS_ALIMTALK_TRACE_BOUND = true;

    //: 벤더가 '문자로 대체발송했다'고 답하는 type 들.
    const TEXT_CHANNELS = ['SMS', 'LMS', 'MMS'];

    //: 발송 직후엔 벤더가 아직 채널을 바꾸지 않았다(서버 상수와 같은 값 — 둘이 갈리면
    //  서버가 too_early 로 되돌려 보내므로 조용히 틀리지는 않는다).
    const PROBE_DELAY_MS = 60 * 1000;

    const HISTORY_EVENT_TYPES = 'ALIMTALK_SENT,ALIMTALK_FAILED';

    let _probeTimer = null;
    let _probing = false;

    /**
     * 현재 주문 id.
     *
     * ERP 주문 화면은 전역 `ORDER_ID` 를 갖지만 태블릿 실측 폼은 갖지 않는다 — 그쪽은 칩
     * 자리에 주문 id 를 실어 준다.
     *
     * @returns {number} 주문 id(아직 저장 전이면 0).
     */
    function _orderId() {
        const global = parseInt(String(window.ORDER_ID || '0'), 10) || 0;
        if (global) return global;
        const slot = document.querySelector('[data-erp-alimtalk-trace-order]');
        const owned = slot ? slot.getAttribute('data-erp-alimtalk-trace-order') : '';
        return parseInt(String(owned || '0'), 10) || 0;
    }

    /** @returns {boolean} 이 표면에 이력 패널 마크업이 있는지(태블릿엔 없다). */
    function _hasPanel() {
        return !!document.getElementById('erpAlimtalkTraceModal');
    }

    /** @returns {Object|null} 화면이 이미 들고 있는 마지막 발송 이력. */
    function _record() {
        const sd = window.__erpLastStructuredData;
        if (!sd || typeof sd !== 'object') return null;
        const record = sd.alimtalk_measurement;
        return record && typeof record === 'object' ? record : null;
    }

    /** @returns {Object|null} 화면이 이미 들고 있는 마지막 공유 링크 발송 이력. */
    function _shareRecord() {
        const sd = window.__erpLastStructuredData;
        if (!sd || typeof sd !== 'object') return null;
        const record = sd.alimtalk_share;
        return record && typeof record === 'object' ? record : null;
    }

    /**
     * 공유 링크 이력 사본을 전역 구조화 데이터에 되꽂는다.
     *
     * @param {Object|null} record 발송 이력(없으면 null → 지운다).
     */
    function _storeShareRecord(record) {
        if (!window.__erpLastStructuredData || typeof window.__erpLastStructuredData !== 'object') {
            window.__erpLastStructuredData = {};
        }
        if (record && typeof record === 'object') {
            window.__erpLastStructuredData.alimtalk_share = record;
        } else {
            delete window.__erpLastStructuredData.alimtalk_share;
        }
    }

    /**
     * 이력 사본을 화면 전역 구조화 데이터에 되꽂는다(다음 렌더의 입력).
     *
     * ``null`` 은 '이 주문엔 이력이 없다'를 뜻하며 남아 있던 값을 **지운다** — 태블릿은 한
     * 화면에서 주문을 갈아끼우므로, 지우지 않으면 이전 주문의 발송이 새 주문 칩에 남는다.
     *
     * @param {Object|null} record 발송 이력(없으면 null).
     */
    function _storeRecord(record) {
        if (!window.__erpLastStructuredData || typeof window.__erpLastStructuredData !== 'object') {
            window.__erpLastStructuredData = {};
        }
        if (record && typeof record === 'object') {
            window.__erpLastStructuredData.alimtalk_measurement = record;
        } else {
            delete window.__erpLastStructuredData.alimtalk_measurement;
        }
    }

    /** @returns {boolean} 이 이력이 '문자로 나갔다'인지 */
    function _isTextChannel(channel) {
        return TEXT_CHANNELS.indexOf(String(channel || '').toUpperCase()) !== -1;
    }

    /** @returns {string} 사유 코드 → 사람 문구(발송 모듈의 맵 재사용 — 사본 금지). */
    function _reasonLabel(code) {
        if (typeof window.erpAlimtalkReasonLabel === 'function') {
            return window.erpAlimtalkReasonLabel(code);
        }
        return String(code || '알 수 없는 오류');
    }

    /**
     * 서버가 남긴 naive UTC ISO 문자열을 KST `MM-DD HH:MM` 으로 만든다.
     *
     * 초·연도는 아무 결정도 바꾸지 않으면서 긴 고객명을 밀어내므로 쓰지 않는다.
     * 타임존 표기가 없으면 UTC 로 읽는다(프로젝트 timestamp 규약).
     *
     * @param {string} value ISO 문자열.
     * @returns {string} 표시 문자열(파싱 불가면 빈 문자열).
     */
    function _formatWhen(value) {
        if (!value) return '';
        const raw = String(value);
        const zoned = /(Z|[+-]\d{2}:?\d{2})$/.test(raw) ? raw : raw + 'Z';
        const date = new Date(zoned);
        if (isNaN(date.getTime())) return '';
        const parts = new Intl.DateTimeFormat('ko-KR', {
            timeZone: 'Asia/Seoul',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
        }).formatToParts(date);
        const pick = function (type) {
            const found = parts.find(function (p) { return p.type === type; });
            return found ? found.value : '';
        };
        const day = pick('month') + '-' + pick('day');
        const clock = pick('hour') + ':' + pick('minute');
        return day + ' ' + clock;
    }

    /** @returns {number|null} 발송 후 지난 밀리초(모르면 null). */
    function _elapsedMs(record) {
        if (!record || !record.sent_at) return null;
        const raw = String(record.sent_at);
        const zoned = /(Z|[+-]\d{2}:?\d{2})$/.test(raw) ? raw : raw + 'Z';
        const sent = new Date(zoned).getTime();
        if (isNaN(sent)) return null;
        return Date.now() - sent;
    }

    /** @returns {string} 칩 상태 — none / sent / text / failed */
    function _state(record) {
        if (!record || (!record.sent_at && !record.error)) return 'none';
        if (record.error) return 'failed';
        return _isTextChannel(record.channel) ? 'text' : 'sent';
    }

    /** 칩 조각 하나(구분점 포함)를 붙인다. */
    function _appendPart(chip, text, className) {
        if (!text) return;
        if (chip.childElementCount > 1) {
            const sep = document.createElement('span');
            sep.className = 'erp-alimtalk-trace__sep';
            sep.textContent = '·';
            chip.appendChild(sep);
        }
        const node = document.createElement('span');
        node.className = className;
        node.textContent = text;
        chip.appendChild(node);
    }

    /**
     * 칩 1개를 만든다.
     *
     * @param {Object|null} record 발송 이력.
     * @param {boolean} compact 좁은 폭(모바일·태블릿) — 보낸 사람을 떨어뜨린다.
     * @returns {HTMLElement} 클릭하면 이력이 열리는 버튼.
     */
    function _buildChip(record, compact) {
        const state = _state(record);
        // 이력 패널이 없는 표면(태블릿)에서는 눌러도 아무 일이 없는 버튼을 만들지 않는다.
        const clickable = _hasPanel();
        const chip = document.createElement(clickable ? 'button' : 'span');
        if (clickable) {
            chip.type = 'button';
            chip.setAttribute('data-erp-alimtalk-trace-open', '1');
        }
        chip.className = 'erp-alimtalk-trace erp-alimtalk-trace--' + state;
        chip.setAttribute('data-foms-no-autodismiss', '1');

        const dot = document.createElement('span');
        dot.className = 'erp-alimtalk-trace__dot';
        dot.setAttribute('aria-hidden', 'true');
        dot.textContent = state === 'failed' ? '!' : (state === 'none' ? '' : '✓');
        chip.appendChild(dot);

        let label = '아직 안 보냄';
        if (state === 'failed') label = '발송 실패';
        else if (state === 'text') label = '문자로 보냄';
        else if (state === 'sent') label = compact ? '보냄' : '예약 안내 보냄';
        _appendPart(chip, label, 'erp-alimtalk-trace__label');

        if (state === 'failed') {
            // 사유를 접지 않는다 — 접으면 아무도 펴지 않고, 고객이 안내를 못 받은 상태다.
            _appendPart(chip, _reasonLabel(record.error), 'erp-alimtalk-trace__reason');
        } else if (state !== 'none') {
            _appendPart(chip, _formatWhen(record.sent_at), 'erp-alimtalk-trace__when');
            if (!compact) {
                const who = record.sent_by_name || (record.sent_by ? '' : '자동 발송');
                _appendPart(chip, who, 'erp-alimtalk-trace__who');
            }
        }

        if (clickable) {
            chip.title = state === 'none'
                ? '아직 실측 예약 안내를 보내지 않았습니다. 눌러서 발송 이력을 봅니다.'
                : '눌러서 알림톡 발송 이력을 봅니다.';
        } else if (state === 'none') {
            chip.title = '아직 실측 예약 안내를 보내지 않았습니다.';
        }
        return chip;
    }

    //: 공유 종류 표기 — 서버 record.kind 와 같은 값.
    const SHARE_KIND_LABELS = { drawing: '도면', estimate: '계약서', bundle: '도면·계약서' };

    /**
     * 공유 링크 발송 칩. **보낸 적이 없으면 아무것도 만들지 않는다** — 공유 링크는 모든
     * 주문에 보내는 게 아니라서, 미발송 점선 칩을 늘 띄우면 정상 상태가 경고처럼 보인다.
     *
     * @param {Object|null} record 공유 발송 이력.
     * @param {boolean} compact 좁은 폭 — 보낸 사람을 떨어뜨린다.
     * @returns {HTMLElement|null} 칩(이력이 없으면 null).
     */
    function _buildShareChip(record, compact) {
        if (!record || (!record.sent_at && !record.error)) return null;
        const failed = !!record.error;
        const chip = document.createElement('span');
        chip.className = 'erp-alimtalk-trace erp-alimtalk-trace--'
            + (failed ? 'failed' : 'share');
        chip.setAttribute('data-foms-no-autodismiss', '1');
        chip.setAttribute('data-erp-share-trace', '1');

        const dot = document.createElement('span');
        dot.className = 'erp-alimtalk-trace__dot';
        dot.setAttribute('aria-hidden', 'true');
        dot.textContent = failed ? '!' : '✓';
        chip.appendChild(dot);

        const kindLabel = SHARE_KIND_LABELS[record.kind] || '링크';
        const via = record.channel === 'sms' ? '문자' : '알림톡';
        _appendPart(chip, failed ? kindLabel + ' 발송 실패' : kindLabel + ' ' + via + ' 보냄',
                    'erp-alimtalk-trace__label');

        if (failed) {
            _appendPart(chip, _reasonLabel(record.error), 'erp-alimtalk-trace__reason');
        } else {
            _appendPart(chip, _formatWhen(record.sent_at), 'erp-alimtalk-trace__when');
            if (!compact) {
                _appendPart(chip, record.sent_by_name || '', 'erp-alimtalk-trace__who');
            }
        }
        chip.title = failed
            ? '고객에게 공유 링크를 보내지 못했습니다.'
            : '고객에게 공유 링크를 보낸 기록입니다.';
        return chip;
    }

    /** 모든 칩 자리를 현재 이력으로 다시 그린다. */
    function erpAlimtalkTraceRender() {
        const slots = document.querySelectorAll('[data-erp-alimtalk-trace]');
        if (!slots.length) return;
        const record = _record();
        for (let i = 0; i < slots.length; i += 1) {
            const slot = slots[i];
            const compact = slot.getAttribute('data-erp-alimtalk-trace') === 'compact';
            slot.textContent = '';
            slot.appendChild(_buildChip(record, compact));
            const shareChip = _buildShareChip(_shareRecord(), compact);
            if (shareChip) slot.appendChild(shareChip);
        }
    }

    // --- 채널 확정 -------------------------------------------------------------

    /** @returns {boolean} 아직 채널을 물어보지 않은 성공 발송인지 */
    function _needsProbe(record) {
        if (!record || record.error || !record.message_id) return false;
        return !record.channel_checked_at;
    }

    /** confirm-channel 1회 호출 — CSRF 헤더는 layout_head 전역 fetch 래퍼가 붙인다. */
    function _probe() {
        const orderId = _orderId();
        const record = _record();
        if (!orderId || _probing || !_needsProbe(record)) return;
        _probing = true;
        fetch('/api/kakao/alimtalk/confirm-channel/' + orderId, {
            method: 'POST',
            credentials: 'same-origin',
        })
            .then(function (res) { return res.json(); })
            .then(function (body) {
                if (!body || !body.success || !body.data || !body.data.checked) return;
                const current = _record();
                if (!current) return;
                current.channel = body.data.channel || null;
                current.channel_checked_at = current.channel_checked_at || new Date().toISOString();
                _storeRecord(current);
                erpAlimtalkTraceRender();
            })
            .catch(function () { /* 확정 실패는 화면을 바꾸지 않는다 — 다음 열람에 다시 묻는다 */ })
            .finally(function () { _probing = false; });
    }

    /** 발송 후 경과 시간에 맞춰 채널 확정을 1회 예약한다(이미 예약돼 있으면 교체). */
    function erpAlimtalkTraceScheduleProbe() {
        const record = _record();
        if (_probeTimer) {
            clearTimeout(_probeTimer);
            _probeTimer = null;
        }
        if (!_needsProbe(record)) return;
        const elapsed = _elapsedMs(record);
        const wait = elapsed === null ? PROBE_DELAY_MS : Math.max(0, PROBE_DELAY_MS - elapsed);
        _probeTimer = setTimeout(function () {
            _probeTimer = null;
            _probe();
        }, wait);
    }

    // --- 이력 패널 -------------------------------------------------------------

    /** 이력 한 줄을 만든다. */
    function _buildLogItem(event) {
        const failed = event.event_type === 'ALIMTALK_FAILED';
        const item = document.createElement('li');
        item.className = 'erp-alimtalk-trace-log__item';

        const mark = document.createElement('span');
        mark.className = 'erp-alimtalk-trace-log__mark erp-alimtalk-trace-log__mark--'
            + (failed ? 'bad' : 'ok');
        mark.setAttribute('aria-hidden', 'true');
        mark.textContent = failed ? '!' : '✓';
        item.appendChild(mark);

        const body = document.createElement('div');
        body.className = 'erp-alimtalk-trace-log__body';

        const head = document.createElement('div');
        head.className = 'erp-alimtalk-trace-log__head';
        const when = document.createElement('span');
        when.className = 'erp-alimtalk-trace-log__when';
        when.textContent = _formatWhen(event.created_at) || String(event.created_at || '');
        head.appendChild(when);
        const kind = document.createElement('span');
        kind.className = 'erp-alimtalk-trace-log__kind';
        kind.textContent = '실측 예약 안내';
        head.appendChild(kind);
        const who = document.createElement('span');
        who.className = 'erp-alimtalk-trace-log__who';
        who.textContent = event.created_by_name || '자동 발송';
        head.appendChild(who);
        body.appendChild(head);

        const payload = event.payload && typeof event.payload === 'object' ? event.payload : {};
        if (failed && payload.error) {
            const sub = document.createElement('div');
            sub.className = 'erp-alimtalk-trace-log__reason';
            sub.textContent = payload.error === 'in_flight'
                ? '발송 진행 중 기록'
                : _reasonLabel(payload.error);
            body.appendChild(sub);
        }
        item.appendChild(body);
        return item;
    }

    /** 이력 목록을 서버에서 받아 패널에 채운다. */
    function _loadHistory() {
        const list = document.getElementById('erp-alimtalk-trace-log');
        const count = document.getElementById('erp-alimtalk-trace-count');
        const orderId = _orderId();
        if (!list) return;
        list.textContent = '';
        if (count) count.textContent = '';
        if (!orderId) {
            const empty = document.createElement('li');
            empty.className = 'erp-alimtalk-trace-log__empty';
            empty.textContent = '아직 저장되지 않은 주문입니다.';
            list.appendChild(empty);
            return;
        }
        fetch('/api/orders/' + orderId + '/events?limit=50&event_type=' + HISTORY_EVENT_TYPES, {
            credentials: 'same-origin',
        })
            .then(function (res) { return res.json(); })
            .then(function (body) {
                if (!body || body.success !== true) throw new Error('load failed');
                const events = Array.isArray(body.events) ? body.events : [];
                if (!events.length) {
                    const empty = document.createElement('li');
                    empty.className = 'erp-alimtalk-trace-log__empty';
                    empty.textContent = '아직 보낸 알림톡이 없습니다.';
                    list.appendChild(empty);
                    return;
                }
                for (let i = 0; i < events.length; i += 1) {
                    list.appendChild(_buildLogItem(events[i]));
                }
                if (count) count.textContent = events.length + '건';
            })
            .catch(function () {
                const failed = document.createElement('li');
                failed.className = 'erp-alimtalk-trace-log__empty';
                failed.textContent = '이력을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.';
                list.appendChild(failed);
            });
    }

    /** 이력 패널을 연다(부트스트랩 없으면 조용히 무시 — 칩 표시는 그대로 유효). */
    function erpOpenAlimtalkTracePanel() {
        const modalEl = document.getElementById('erpAlimtalkTraceModal');
        if (!modalEl || !window.bootstrap || !window.bootstrap.Modal) return;
        _loadHistory();
        window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }

    // --- 배선 -----------------------------------------------------------------

    document.addEventListener('click', function (ev) {
        const target = ev.target;
        if (!target || typeof target.closest !== 'function') return;
        if (!target.closest('[data-erp-alimtalk-trace-open]')) return;
        ev.preventDefault();
        erpOpenAlimtalkTracePanel();
    });

    // 발송 모듈이 방금 기록된 이력을 실어 보낸다 — 칩은 추가 조회 없이 즉시 갱신된다.
    document.addEventListener('foms:alimtalk-trace-update', function (ev) {
        _storeRecord(ev && ev.detail ? ev.detail.record : null);
        erpAlimtalkTraceRender();
        erpAlimtalkTraceScheduleProbe();
    });

    // 공유 발송 모듈이 방금 기록된 이력을 실어 보낸다(추가 조회 없음). 빈 값 게시는
    // 예약 안내 칩과 같은 규칙으로 공유 칩을 지운다.
    document.addEventListener('foms:share-trace-update', function (ev) {
        _storeShareRecord(ev && ev.detail ? ev.detail.record : null);
        erpAlimtalkTraceRender();
    });

    // 구조화 데이터가 늦게 도착하는 화면(주문 상세)은 로드 완료 신호를 받아 다시 그린다.
    document.addEventListener('foms:erp-structured-loaded', function () {
        erpAlimtalkTraceRender();
        erpAlimtalkTraceScheduleProbe();
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            erpAlimtalkTraceRender();
            erpAlimtalkTraceScheduleProbe();
        });
    } else {
        erpAlimtalkTraceRender();
        erpAlimtalkTraceScheduleProbe();
    }

    window.erpAlimtalkTraceRender = erpAlimtalkTraceRender;
    window.erpOpenAlimtalkTracePanel = erpOpenAlimtalkTracePanel;
})();
