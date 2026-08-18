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
    var KIND_LABELS = { drawing: '도면', estimate: '견적서' };
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
        var revokeBtn = item.status === 'active'
            ? '<button type="button" class="btn btn-outline-danger btn-sm" data-share-revoke="'
              + item.share_id + '">회수</button>'
            : '';
        return '<li class="list-group-item d-flex justify-content-between align-items-center gap-2">'
            + '<span class="small">' + (KIND_LABELS[item.kind] || item.kind) + ' · ' + created
            + ' · ' + views + '</span>'
            + '<span class="d-flex align-items-center gap-2">'
            + '<span class="badge ' + badgeTone + '">' + status + '</span>' + revokeBtn
            + '</span></li>';
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

    /** POST create — 토큰 원문은 이 응답에서만 존재한다. */
    function _create() {
        if (_busy) return;
        var orderId = _orderId();
        if (!orderId) {
            _setNotice('저장 후 공유할 수 있습니다.');
            return;
        }
        var kindInput = document.querySelector('input[name="erp-share-kind"]:checked');
        var kind = kindInput ? kindInput.value : 'drawing';
        _busy = true;
        var btn = document.getElementById('erp-share-create-btn');
        if (btn) btn.disabled = true;

        fetch('/api/share/create/' + orderId, {
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
        var revokeBtn = target.closest('[data-share-revoke]');
        if (revokeBtn) {
            ev.preventDefault();
            _revoke(revokeBtn.getAttribute('data-share-revoke'));
        }
    });

    window.erpOpenShareModal = erpOpenShareModal;
})();
