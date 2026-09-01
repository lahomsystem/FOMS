/**
 * ERP 고객 공유 링크 — 발급/복사/카톡 공유/이력·회수 모달 (PC·모바일 표면, Phase A T4).
 *
 * 목록·발급은 버튼 클릭 시점에만 fetch 한다(전역 프리페치 없음, perf G1).
 * document 위임 + window.__FOMS_SHARE_BOUND 싱글톤으로 fragment 재실행에도
 * 리스너가 중복 등록되지 않는다(perf G4, erp-alimtalk-send.js 선례).
 *
 * 토큰은 해시-온리 저장 — URL 은 발급 응답에서만 존재하며 메모리에만 둔다.
 * 카카오 SDK 는 카톡 버튼이 활성일 때 lazy 로드하고, 키 부재·로드 실패는
 * 버튼 비활성 + 안내로 표면화한다(조용한 무반응 금지).
 */
(function () {
    'use strict';

    if (window.__FOMS_SHARE_BOUND) return;
    window.__FOMS_SHARE_BOUND = true;

    var KAKAO_SDK_URL = 'https://t1.kakaocdn.net/kakao_js_sdk/2.7.4/kakao.min.js';

    var STATUS_LABELS = {
        active: '활성',
        expired: '만료',
        revoked: '회수됨',
    };
    var KIND_LABELS = { drawing: '도면', estimate: '견적서', bundle: '도면·계약서' };
    var ERROR_LABELS = {
        order_not_found: '주문을 찾을 수 없습니다',
        unknown_kind: '알 수 없는 공유 종류입니다',
        share_not_found: '공유 링크를 찾을 수 없습니다',
        token_mismatch: '링크 정보가 맞지 않습니다 — 회수 후 다시 발급해 주세요',
        share_expired: '만료된 링크입니다 — 다시 발급해 주세요',
        share_revoked: '회수된 링크입니다 — 다시 발급해 주세요',
        no_valid_phone: '고객 휴대폰 번호가 올바르지 않습니다',
        not_configured: '문자 발신 설정이 없습니다 — 관리자에게 문의하세요',
        duplicate_send: '방금 발송을 시도했습니다 — 잠시 후 다시 시도해 주세요',
        invalid_phone: '수신 번호가 올바르지 않습니다',
        auth: '문자 인증 정보가 올바르지 않습니다',
        balance: '문자 잔액이 부족합니다',
        network: '네트워크 오류가 발생했습니다',
    };

    var _busy = false;
    var _issued = null; // {shareId, url} — 발급 직후에만 존재(메모리 한정)

    /** @returns {string} 사용자 문구 */
    function _label(code) {
        return ERROR_LABELS[code] || String(code || '알 수 없는 오류');
    }

    /** @returns {HTMLElement|null} */
    function _modalEl() {
        return document.getElementById('erpShareModal');
    }

    /** @returns {Object|null} bootstrap Modal 인스턴스 */
    function _modal() {
        var el = _modalEl();
        if (!el || !window.bootstrap || !window.bootstrap.Modal) return null;
        return window.bootstrap.Modal.getOrCreateInstance(el);
    }

    /** 모달 상단 경고/안내 줄 토글. */
    function _setNotice(text) {
        var el = document.getElementById('erp-share-notice');
        if (!el) return;
        el.textContent = text || '';
        el.classList.toggle('d-none', !text);
    }

    /** @returns {number} 현재 주문 id */
    function _orderId() {
        return parseInt(String(window.ORDER_ID || '0'), 10) || 0;
    }

    /** 발급 패널 표시/초기화. */
    function _showIssued(url) {
        var panel = document.getElementById('erp-share-issued');
        var input = document.getElementById('erp-share-url');
        if (input) input.value = url || '';
        if (panel) panel.classList.toggle('d-none', !url);
        _syncKakaoButton();
    }

    /** 카톡 버튼 활성 조건(키 존재 + 발급 URL 존재) 동기화. */
    function _syncKakaoButton() {
        var btn = document.getElementById('erp-share-kakao-btn');
        if (!btn) return;
        var el = _modalEl();
        var key = el ? (el.getAttribute('data-kakao-js-key') || '') : '';
        if (!key) {
            btn.disabled = true;
            btn.title = '카카오 공유 미설정 — 관리자에게 문의하세요';
            return;
        }
        btn.disabled = !(_issued && _issued.url);
        btn.title = btn.disabled ? '먼저 링크를 발급하세요' : '';
    }

    /** 이력 한 건을 li 로 렌더. @returns {string} */
    function _itemHtml(item) {
        var status = STATUS_LABELS[item.status] || item.status;
        var badgeTone = item.status === 'active' ? 'text-bg-success' : 'text-bg-secondary';
        var created = String(item.created_at || '').replace('T', ' ').slice(0, 16);
        var views = '열람 ' + (item.view_count || 0) + '회';
        // 좁은 모달에서 버튼 라벨이 세로로 접히지 않게 nowrap 고정.
        var revokeBtn = item.status === 'active'
            ? '<button type="button" class="btn btn-outline-danger btn-sm text-nowrap" data-share-revoke="'
              + item.share_id + '">회수</button>'
            : '';
        // 계약 내용이 있는 종류만 열람 기록이 쌓인다(도면 링크는 대상 아님 — SHARE-HIST-00).
        var histBtn = (item.kind === 'estimate' || item.kind === 'bundle')
            ? '<button type="button" class="btn btn-outline-secondary btn-sm text-nowrap" data-share-history="'
              + item.share_id + '">고객이 본 내용</button>'
            : '';
        // 버튼이 셋(기록·회수·상태뱃지)까지 늘어 좁은 모달에서 한 줄에 안 들어간다 —
        // 라벨을 자르는 대신 오른쪽 묶음이 아래로 접히게 한다(flex-wrap).
        return '<li class="list-group-item d-flex justify-content-between align-items-center gap-2 flex-wrap">'
            + '<span class="small">' + (KIND_LABELS[item.kind] || item.kind) + ' · ' + created
            + ' · ' + views + '</span>'
            + '<span class="d-flex align-items-center gap-2 flex-shrink-0">'
            + '<span class="badge text-nowrap ' + badgeTone + '">' + status + '</span>'
            + histBtn + revokeBtn
            + '</span></li>';
    }

    /** 금액을 천단위 구분 문자열로. @returns {string} */
    function _won(value) {
        return (Number(value) || 0).toLocaleString('ko-KR') + '원';
    }

    /** 열람 기록 한 건을 li 로 렌더. @returns {string} */
    function _historyItemHtml(row) {
        var seen = String(row.first_viewed_at || '').replace('T', ' ').slice(0, 16);
        var sum = row.summary || {};
        var repeat = (row.view_count || 0) > 1 ? ' · ' + row.view_count + '회' : '';
        var stored = row.source === 'stored' ? ' · 발급 저장본' : '';
        return '<li class="list-group-item d-flex justify-content-between align-items-center gap-2">'
            + '<span class="small">' + seen + repeat + stored
            + '<br><span class="text-muted">잔금 ' + _won(sum.balance_amount)
            + ' · 예약금 ' + _won(sum.deposit_amount)
            + ' · 품목 ' + (sum.items_count || 0) + '개</span></span>'
            + '<button type="button" class="btn btn-outline-primary btn-sm text-nowrap flex-shrink-0"'
            + ' data-share-history-open="' + row.snapshot_id + '">그때 화면 보기</button>'
            + '</li>';
    }

    /**
     * 그 링크로 고객이 본 계약서 이력을 불러와 목록 아래에 편다.
     *
     * 계약서는 라이브 반영이라 같은 링크가 시점마다 다른 금액을 보여준다 — 이 목록이
     * "고객이 언제 얼마짜리를 봤나"를 답한다. 내용이 바뀐 순간에만 한 줄이다.
     *
     * @param {string} shareId 공유 토큰 id.
     */
    function _openHistory(shareId) {
        var box = document.getElementById('erp-share-history');
        if (!box) return;
        box.innerHTML = '<div class="small text-muted">불러오는 중…</div>';
        fetch('/api/share/history/' + shareId, { credentials: 'same-origin' })
            .then(function (res) { return res.json(); })
            .then(function (body) {
                if (!body || !body.success || !body.data) {
                    box.innerHTML = '<div class="small text-danger">기록을 불러오지 못했습니다.</div>';
                    return;
                }
                var items = body.data.items || [];
                if (!items.length) {
                    box.innerHTML = '<div class="small text-muted">아직 고객이 열람한 기록이 없습니다.</div>';
                    return;
                }
                box.innerHTML = '<div class="small fw-semibold mb-1">고객이 본 계약서 기록 ('
                    + items.length + '건)</div>'
                    + '<ul class="list-group list-group-flush">'
                    + items.map(_historyItemHtml).join('') + '</ul>';
            })
            .catch(function () {
                box.innerHTML = '<div class="small text-danger">기록을 불러오지 못했습니다 — '
                    + _label('network') + '</div>';
            });
    }

    /** 발급 이력 목록을 다시 그린다. */
    function _renderList(items) {
        var box = document.getElementById('erp-share-list');
        if (!box) return;
        if (!items || !items.length) {
            box.innerHTML = '<div class="small text-muted">발급된 링크가 없습니다.</div>';
            return;
        }
        box.innerHTML = '<ul class="list-group list-group-flush">'
            + items.map(_itemHtml).join('') + '</ul>';
        // 목록이 새로 그려지면 열려 있던 이력 패널은 어떤 링크의 것인지 알 수 없다 — 비운다.
        var hist = document.getElementById('erp-share-history');
        if (hist) hist.innerHTML = '';
    }

    /** GET list — 메타만 온다(URL·토큰 없음). */
    function _refreshList() {
        var orderId = _orderId();
        if (!orderId) return Promise.resolve();
        return fetch('/api/share/list/' + orderId, { credentials: 'same-origin' })
            .then(function (res) { return res.json(); })
            .then(function (body) {
                if (body && body.success && body.data) _renderList(body.data.items);
            })
            .catch(function () {
                _setNotice('이력을 불러오지 못했습니다 — ' + _label('network'));
            });
    }

    /**
     * 미저장 편집이 있으면 기존 통합 저장을 먼저 돌린다(T13, erp-alimtalk-send.js 공용 헬퍼).
     *
     * 공유 링크는 열람 시점의 저장본을 보여주므로, 저장 없이 발급하면 고객이 화면과
     * 다른 내용을 본다. 헬퍼가 없으면(로드 실패) 기존 동작대로 그대로 진행한다.
     *
     * @param {function(string):void} say 상태/오류 문구 표시.
     * @returns {Promise<boolean>} 계속 진행해도 되는지.
     */
    function _ensureSaved(say) {
        var ensure = window.fomsErpEnsureSavedForSend;
        if (typeof ensure !== 'function') return Promise.resolve(true);
        return ensure(say).catch(function () { return false; });
    }

    /** POST create — 토큰 원문은 이 응답에서만 존재한다. */
    async function _create() {
        if (_busy) return;
        var kindInput = document.querySelector('input[name="erp-share-kind"]:checked');
        var kind = kindInput ? kindInput.value : 'drawing';
        _busy = true;
        // 저장이 먼저다 — 신규·draft 주문도 여기서 저장(승격)된 뒤 id 를 읽는다.
        // 앞에서 id 를 보고 되돌려보내면 입력해 둔 내용이 그대로 남은 채 막힌다.
        if (!(await _ensureSaved(_setNotice))) {
            _busy = false;
            return;
        }
        var orderId = _orderId();
        if (!orderId) {
            _setNotice('저장 후 공유할 수 있습니다.');
            _busy = false;
            return;
        }
        var btn = document.getElementById('erp-share-create-btn');
        if (btn) btn.disabled = true;

        return fetch('/api/share/create/' + orderId, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ kind: kind }),
        })
            .then(function (res) { return res.json(); })
            .then(function (body) {
                if (!body || !body.success || !body.data) {
                    _setNotice('발급 실패 — ' + _label(body && body.error));
                    return;
                }
                _issued = { shareId: body.data.share_id, url: body.data.url,
                    kind: body.data.kind, token: body.data.token };
                _setNotice('');
                _showIssued(body.data.url);
                return _refreshList();
            })
            .catch(function () { _setNotice('발급 실패 — ' + _label('network')); })
            .finally(function () {
                _busy = false;
                if (btn) btn.disabled = false;
            });
    }

    /** 클립보드 복사(secure context 불가 시 execCommand 폴백). */
    function _copy() {
        var input = document.getElementById('erp-share-url');
        if (!input || !input.value) return;
        var done = function () { _setNotice(''); _flashCopied(); };
        var fail = function () { _setNotice('복사에 실패했습니다 — 주소를 길게 눌러 복사하세요.'); };
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(input.value).then(done, function () {
                _copyFallback(input, done, fail);
            });
            return;
        }
        _copyFallback(input, done, fail);
    }

    /** execCommand 폴백 경로. */
    function _copyFallback(input, done, fail) {
        try {
            input.focus();
            input.select();
            var ok = document.execCommand('copy');
            (ok ? done : fail)();
        } catch (e) {
            fail();
        }
    }

    /** 복사 버튼 라벨 1.5초 피드백. */
    function _flashCopied() {
        var btn = document.getElementById('erp-share-copy-btn');
        if (!btn) return;
        var original = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-check"></i> 복사됨';
        window.setTimeout(function () { btn.innerHTML = original; }, 1500);
    }

    /** Kakao SDK lazy 로드(1회). @returns {Promise<Object>} window.Kakao */
    function _ensureKakao(key) {
        if (window.Kakao && window.Kakao.isInitialized && window.Kakao.isInitialized()) {
            return Promise.resolve(window.Kakao);
        }
        return new Promise(function (resolve, reject) {
            var finish = function () {
                try {
                    if (window.Kakao && !window.Kakao.isInitialized()) window.Kakao.init(key);
                    resolve(window.Kakao);
                } catch (e) {
                    reject(e);
                }
            };
            if (window.Kakao) { finish(); return; }
            var script = document.createElement('script');
            script.src = KAKAO_SDK_URL;
            script.onload = finish;
            script.onerror = function () { reject(new Error('kakao sdk load failed')); };
            document.head.appendChild(script);
        });
    }

    /** 카톡 공유(sendDefault feed, 버튼 1개 — 스펙 D8 버튼≤2). */
    function _shareKakao() {
        if (!_issued || !_issued.url) return;
        var el = _modalEl();
        var key = el ? (el.getAttribute('data-kakao-js-key') || '') : '';
        var logo = el ? (el.getAttribute('data-share-logo-url') || '') : '';
        var url = _issued.url;
        var isEstimate = _issued.kind === 'estimate';
        var title = isEstimate ? '견적서 확인' : '도면 확인';
        var description = isEstimate ? '견적서를 확인해 주세요.' : '도면을 확인해 주세요.';
        _ensureKakao(key)
            .then(function (Kakao) {
                Kakao.Share.sendDefault({
                    objectType: 'feed',
                    content: {
                        title: title,
                        description: description,
                        imageUrl: logo,
                        link: { mobileWebUrl: url, webUrl: url },
                    },
                    buttons: [
                        { title: isEstimate ? '견적서 보기' : '도면 보기',
                          link: { mobileWebUrl: url, webUrl: url } },
                    ],
                });
            })
            .catch(function () {
                var btn = document.getElementById('erp-share-kakao-btn');
                if (btn) {
                    btn.disabled = true;
                    btn.title = '카카오 공유를 사용할 수 없습니다';
                }
                _setNotice('카카오 공유를 사용할 수 없습니다 — 링크 복사로 전달해 주세요.');
            });
    }

    /** POST send-sms — 발급 직후에만 가능(토큰 원문은 메모리에만 존재, §1 재해시 검증). */
    function _sendSms() {
        if (!_issued || !_issued.token) {
            _setNotice('먼저 링크를 발급하세요 — 문자는 발급 직후에만 보낼 수 있습니다.');
            return;
        }
        var btn = document.getElementById('erp-share-sms-btn');
        if (btn && btn.disabled) return;
        if (btn) btn.disabled = true; // §1 클라 버튼 잠금(발송 중)
        fetch('/api/share/send-sms/' + _issued.shareId, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: _issued.token }),
        })
            .then(function (res) { return res.json(); })
            .then(function (body) {
                var sent = !!(body && body.success && body.data && body.data.sent);
                if (body && body.data) _publishShareTrace(body.data.last_share);
                if (sent) {
                    _setNotice('');
                    _flashSmsSent();
                    return;
                }
                var code = (body && (body.error || (body.data && body.data.error))) || 'network';
                _setNotice('문자 발송 실패 — ' + _label(code));
            })
            .catch(function () { _setNotice('문자 발송 실패 — ' + _label('network')); })
            .finally(function () { if (btn) btn.disabled = false; });
    }

    /** 문자 버튼 라벨 1.5초 피드백. */
    function _flashSmsSent() {
        _flashSent('erp-share-sms-btn');
    }

    /** 발송 버튼 라벨 1.5초 피드백 (문자·알림톡 공용). */
    function _flashSent(btnId) {
        var btn = document.getElementById(btnId);
        if (!btn) return;
        var original = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-check"></i> 발송됨';
        window.setTimeout(function () { btn.innerHTML = original; }, 1500);
    }

    /**
     * 내 휴대폰 문자앱으로 보내기(모바일 전용) — 링크 발급 후 sms: 딥링크로 넘긴다.
     *
     * 회사 발송(알림톡/LMS)과 달리 실제 전송은 사용자의 기기에서 일어난다. 서버에는
     * 발급·열람·회수 기록만 남고 "보냈는지"는 남지 않는다(영업 개인번호 발신 요구).
     * 본문·수신번호는 서버가 준 값을 그대로 쓴다 — 화면값 조립 금지(알림톡 문구와 동일).
     *
     * @param {string} kind 공유 종류(drawing/estimate).
     */
    async function _selfSms(kind) {
        if (_busy) return;
        _busy = true;
        // 저장이 먼저 — 신규·draft 주문도 저장(승격)된 뒤 id 를 읽는다(_create 와 같은 규칙).
        if (!(await _ensureSaved(function (msg) { window.alert(msg); }))) {
            _busy = false;
            return;
        }
        var orderId = _orderId();
        if (!orderId) {
            window.alert('저장 후 공유할 수 있습니다.');
            _busy = false;
            return;
        }
        try {
            var res = await fetch('/api/share/create/' + orderId, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ kind: kind }),
            });
            var body = await res.json();
            if (!body || !body.success || !body.data) {
                window.alert('발급 실패 — ' + _label(body && body.error));
                return;
            }
            if (!body.data.to_phone) {
                window.alert(_label('no_valid_phone'));
                return;
            }
            window.location.href = _smsHref(body.data.to_phone, body.data.sms_text || body.data.url);
        } catch (e) {
            window.alert('발급 실패 — ' + _label('network'));
        } finally {
            _busy = false;
        }
    }

    /**
     * sms: 딥링크 조립 — 본문 구분자가 iOS 는 ``&``, 그 외는 ``?`` 다.
     *
     * @param {string} phone 수신번호(서버가 정규화한 숫자).
     * @param {string} text 본문.
     * @returns {string} sms 스킴 URL.
     */
    function _smsHref(phone, text) {
        var sep = /iPad|iPhone|iPod|Macintosh/.test(navigator.userAgent) ? '&' : '?';
        return 'sms:' + phone + sep + 'body=' + encodeURIComponent(text);
    }

    /**
     * 방금 남은 공유 발송 흔적을 화면 칩에 흘려보낸다(추가 조회 없음).
     *
     * 서버가 ``data.last_share`` 로 돌려준 레코드를 그대로 싣는다. 추적 대상이 아닌
     * 종류(도면 단독 등)는 서버가 ``null`` 을 주므로 칩이 생기지 않는다.
     *
     * @param {Object|null} record 서버가 돌려준 발송 이력.
     */
    function _publishShareTrace(record) {
        if (!record) return;
        document.dispatchEvent(new CustomEvent('foms:share-trace-update', {
            detail: { record: record },
        }));
    }

    /** 원클릭 알림톡 — 모달 없이 링크 자동 발급 후 즉시 알림톡 발송(도면/견적서). */
    async function _quickAlimtalk(btn) {
        if (_busy || (btn && btn.disabled)) return;
        var kind = (btn && btn.getAttribute('data-share-kind')) || 'drawing';
        var kindLabel = KIND_LABELS[kind] || '문서';
        if (!window.confirm('고객에게 ' + kindLabel + ' 열람 링크를 알림톡으로 보낼까요?')) return;
        _busy = true;
        if (btn) btn.disabled = true;
        if (!(await _ensureSaved(function (msg) { window.alert(msg); }))) {
            _busy = false;
            if (btn) btn.disabled = false;
            return;
        }
        return fetch('/api/share/create/' + _orderId(), {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ kind: kind }),
        })
            .then(function (res) { return res.json(); })
            .then(function (body) {
                if (!body || !body.success || !body.data) {
                    throw new Error((body && body.error) || 'network');
                }
                return fetch('/api/share/send-alimtalk/' + body.data.share_id, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ token: body.data.token }),
                }).then(function (res) { return res.json(); });
            })
            .then(function (body) {
                var sent = !!(body && body.success && body.data && body.data.sent);
                if (body && body.data) _publishShareTrace(body.data.last_share);
                if (sent) {
                    if (btn) {
                        var original = btn.innerHTML;
                        btn.innerHTML = '<i class="fas fa-check"></i> 발송됨';
                        window.setTimeout(function () { btn.innerHTML = original; }, 1500);
                    }
                    return;
                }
                var code = (body && (body.error || (body.data && body.data.error))) || 'network';
                window.alert('알림톡 발송 실패 — ' + _label(code));
            })
            .catch(function (err) {
                window.alert('알림톡 발송 실패 — ' + _label((err && err.message) || 'network'));
            })
            .finally(function () { _busy = false; if (btn) btn.disabled = false; });
    }

    /** POST send-alimtalk — 문자와 대칭, 실패 시 Solapi 가 문자로 자동 대체발송. */
    function _sendAlimtalk() {
        if (!_issued || !_issued.token) {
            _setNotice('먼저 링크를 발급하세요 — 알림톡은 발급 직후에만 보낼 수 있습니다.');
            return;
        }
        var btn = document.getElementById('erp-share-alimtalk-btn');
        if (btn && btn.disabled) return;
        if (btn) btn.disabled = true;
        fetch('/api/share/send-alimtalk/' + _issued.shareId, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: _issued.token }),
        })
            .then(function (res) { return res.json(); })
            .then(function (body) {
                var sent = !!(body && body.success && body.data && body.data.sent);
                if (body && body.data) _publishShareTrace(body.data.last_share);
                if (sent) {
                    _setNotice('');
                    _flashSent('erp-share-alimtalk-btn');
                    return;
                }
                var code = (body && (body.error || (body.data && body.data.error))) || 'network';
                _setNotice('알림톡 발송 실패 — ' + _label(code));
            })
            .catch(function () { _setNotice('알림톡 발송 실패 — ' + _label('network')); })
            .finally(function () { if (btn) btn.disabled = false; });
    }

    /** POST revoke — 목록의 활성 링크를 즉시 죽인다. */
    function _revoke(shareId) {
        if (!window.confirm('이 공유 링크를 회수할까요? 고객은 즉시 열람할 수 없게 됩니다.')) return;
        fetch('/api/share/revoke/' + shareId, { method: 'POST', credentials: 'same-origin' })
            .then(function (res) { return res.json(); })
            .then(function (body) {
                if (!body || !body.success) {
                    _setNotice('회수 실패 — ' + _label(body && body.error));
                    return;
                }
                if (_issued && String(_issued.shareId) === String(shareId)) {
                    _issued = null;
                    _showIssued('');
                }
                return _refreshList();
            })
            .catch(function () { _setNotice('회수 실패 — ' + _label('network')); });
    }

    /** 버튼 클릭 진입점: 이력 조회 → 모달 표시. */
    function erpOpenShareModal() {
        var orderId = _orderId();
        if (!orderId) return;
        _issued = null;
        _showIssued('');
        _setNotice('');
        _refreshList().then(function () {
            var modal = _modal();
            if (modal) modal.show();
        });
        _syncKakaoButton();
    }

    // 위임 바인딩 — 클릭 시점 조회라 fragment swap 후에도 유효(G4).
    // 태블릿 버튼([data-tmf-share-open])은 자체 핸들러 소유(T9) — 이중 처리 방지.
    document.addEventListener('click', function (ev) {
        var target = ev.target;
        if (!target || typeof target.closest !== 'function') return;
        if (target.closest('.erp-share-open-btn:not([data-tmf-share-open])')) {
            ev.preventDefault();
            erpOpenShareModal();
            return;
        }
        var selfSmsBtn = target.closest('.erp-share-sms-self-btn');
        if (selfSmsBtn) {
            ev.preventDefault();
            void _selfSms(selfSmsBtn.getAttribute('data-share-kind') || 'drawing');
            return;
        }
        if (target.closest('#erp-share-create-btn')) {
            ev.preventDefault();
            _create();
            return;
        }
        if (target.closest('#erp-share-copy-btn')) {
            ev.preventDefault();
            _copy();
            return;
        }
        if (target.closest('#erp-share-kakao-btn')) {
            ev.preventDefault();
            _shareKakao();
            return;
        }
        if (target.closest('#erp-share-sms-btn')) {
            ev.preventDefault();
            _sendSms();
            return;
        }
        if (target.closest('#erp-share-alimtalk-btn')) {
            ev.preventDefault();
            _sendAlimtalk();
            return;
        }
        var quickBtn = target.closest('.erp-share-alimtalk-quick-btn');
        if (quickBtn) {
            ev.preventDefault();
            _quickAlimtalk(quickBtn);
            return;
        }
        var histBtn = target.closest('[data-share-history]');
        if (histBtn) {
            ev.preventDefault();
            _openHistory(histBtn.getAttribute('data-share-history'));
            return;
        }
        var histOpen = target.closest('[data-share-history-open]');
        if (histOpen) {
            ev.preventDefault();
            // 새 탭 — ERP 셸에 공유 전용 CSS 를 끌어들이지 않는다(스타일 오염 0).
            window.open('/api/share/history/'
                + histOpen.getAttribute('data-share-history-open') + '/page', '_blank');
            return;
        }
        var revokeBtn = target.closest('[data-share-revoke]');
        if (revokeBtn) {
            ev.preventDefault();
            _revoke(revokeBtn.getAttribute('data-share-revoke'));
        }
    });

    window.erpOpenShareModal = erpOpenShareModal;
})();
