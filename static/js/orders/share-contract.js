/* 고객 공유 계약서 페이지 스크립트 (비로그인 독립 문서, 2026-08-31).

   담당 세 가지:
     1) 계좌번호 복사 — navigator.clipboard 우선, 막히면 textarea + execCommand 폴백.
        (카카오톡 인앱 브라우저는 보안 컨텍스트여도 clipboard 권한이 거절되는 사례가 있다.)
     2) 계약서 PNG 저장 — html2canvas 를 **쓸 때 1회만** 동적 로드한다(perf guard G2:
        외부 CDN 동기 script 금지). 로드 패턴은 static/js/drawing/wizard.js 정본 복제.
     3) 실패 표면화 — 조용히 죽지 않는다. 안내 문구를 화면에 띄운다
        (카톡 인앱에서 window.print() 가 무반응이던 것이 원래 신고 사유).

   ERP 셸이 없는 페이지다: jQuery 없음, Bootstrap 없음, querySelector/fetch 만 쓴다. */
(function () {
    'use strict';

    if (window.__FOMS_SHARE_CONTRACT_BOUND__) { return; }
    window.__FOMS_SHARE_CONTRACT_BOUND__ = true;

    var HTML2CANVAS_SRC = 'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js';
    var LOAD_TIMEOUT_MS = 15000;
    var RENDER_TIMEOUT_MS = 30000;
    var IMAGE_WAIT_MS = 4000;
    /* iOS 사파리 캔버스 상한(약 16.7M px) 아래로 유지 — 넘으면 toBlob 이 빈 이미지를 준다. */
    var MAX_CANVAS_PIXELS = 16000000;
    var COPY_LABEL_MS = 1500;
    /* 저장물 폭 — ERP 계약서 문서 폭과 같다(estimate-preview.js _EST_EXPORT_WIDTH). */
    var EXPORT_WIDTH = 700;
    /* clipboard API 가 매달릴 때 폴백으로 넘어가는 시한. */
    var CLIPBOARD_TIMEOUT_MS = 800;

    var _html2canvasPromise = null;

    /** @returns {HTMLElement|null} 계약서 문서 루트(캡처 대상 노드 하나). */
    function docRoot() {
        return document.querySelector('[data-share-contract-doc]');
    }

    function wrapEl() {
        return document.querySelector('[data-share-contract]');
    }

    /** 실패 안내를 화면에 띄운다(빈 문자열이면 감춘다). */
    function showError(message) {
        var el = document.querySelector('[data-share-contract-error]');
        if (!el) { return; }
        if (!message) {
            el.hidden = true;
            el.textContent = '';
            return;
        }
        el.textContent = message;
        el.hidden = false;
    }

    /* ── html2canvas lazy-load (wizard.js 패턴 복제, perf guard G2) ───────────── */
    function ensureHtml2canvas() {
        if (typeof window.html2canvas === 'function') { return Promise.resolve(); }
        if (_html2canvasPromise) { return _html2canvasPromise; }
        _html2canvasPromise = new Promise(function (resolve, reject) {
            var settled = false;
            var timer = window.setTimeout(function () {
                if (settled) { return; }
                settled = true;
                _html2canvasPromise = null;
                reject(new Error('html2canvas load timed out'));
            }, LOAD_TIMEOUT_MS);
            function finish(ok, err) {
                if (settled) { return; }
                settled = true;
                window.clearTimeout(timer);
                if (ok) { resolve(); return; }
                _html2canvasPromise = null;
                reject(err);
            }
            var s = document.createElement('script');
            s.src = HTML2CANVAS_SRC;
            s.async = true;
            s.onload = function () {
                if (typeof window.html2canvas === 'function') { finish(true); }
                else { finish(false, new Error('html2canvas loaded but global missing')); }
            };
            s.onerror = function () { finish(false, new Error('html2canvas load failed')); };
            document.head.appendChild(s);
        });
        return _html2canvasPromise;
    }

    function withTimeout(promise, ms, message) {
        return new Promise(function (resolve, reject) {
            var settled = false;
            var timer = window.setTimeout(function () {
                if (settled) { return; }
                settled = true;
                reject(new Error(message));
            }, ms);
            Promise.resolve(promise).then(function (value) {
                if (settled) { return; }
                settled = true;
                window.clearTimeout(timer);
                resolve(value);
            }, function (err) {
                if (settled) { return; }
                settled = true;
                window.clearTimeout(timer);
                reject(err);
            });
        });
    }

    /** 로고·인감이 아직 안 실렸으면 기다린다(빈 자리로 캡처되는 것 방지). */
    function waitForImages(node) {
        var images = Array.prototype.slice.call(node.querySelectorAll('img'));
        if (images.length === 0) { return Promise.resolve(); }
        return Promise.all(images.map(function (img) {
            if (img.complete) { return Promise.resolve(); }
            return new Promise(function (resolve) {
                var timer = window.setTimeout(resolve, IMAGE_WAIT_MS);
                function done() { window.clearTimeout(timer); resolve(); }
                img.addEventListener('load', done, { once: true });
                img.addEventListener('error', done, { once: true });
            });
        })).then(function () { });
    }

    /** 캔버스 픽셀 상한 안에서 최대 배율(기본 2). */
    function captureScale(w, h) {
        var limit = Math.sqrt(MAX_CANVAS_PIXELS / (Math.max(1, w) * Math.max(1, h)));
        var scale = Math.min(2, limit);
        if (!isFinite(scale) || scale <= 0) { return 1; }
        return Math.max(0.5, Math.floor(scale * 100) / 100);
    }

    /** PC 계약서(700px) 오프스크린 클론 — 저장물이 폰 레이아웃으로 찍히는 걸 막는다.

       화면의 노드를 그대로 캡처하면 좁은 화면 규칙이 걸린 1단 레이아웃이 그림이 된다.
       고객이 보관·전달하는 문서는 ERP 계약서와 같은 모양이어야 한다(ERP
       estimate-preview.js `_buildExportClone` 과 같은 수단). html2canvas 는 별도
       iframe 에 렌더하므로 `windowWidth` 를 700 으로 주면 클론 쪽 미디어쿼리도
       PC 분기로 평가된다. */
    function buildExportClone(sourceEl) {
        var clone = sourceEl.cloneNode(true);
        clone.removeAttribute('id');
        var ided = clone.querySelectorAll('[id]');
        for (var i = 0; i < ided.length; i += 1) { ided[i].removeAttribute('id'); }
        clone.classList.add('foms-share-contract__export-clone');
        document.body.appendChild(clone);
        return clone;
    }

    function removeExportClone(clone) {
        if (clone && clone.parentNode) { clone.parentNode.removeChild(clone); }
    }

    /** canvas → 다운로드 가능한 URL.

       **dataURL 이 1순위다.** WKWebView(iOS 사파리·카카오톡 인앱)는 `blob:` URL 을
       `<a download>` 의 href 로 지원하지 않아(WebKit 216918) 클릭해도 아무 일도 안 난다 —
       원래 신고된 "저장 버튼 무반응"과 똑같은 증상이 재발한다. 저장소 선례
       (static/js/measurement/image-export.js)도 toDataURL 을 쓴다.
       거대 캔버스에서 dataURL 이 비거나 던질 때만 toBlob + objectURL 로 내려간다. */
    function canvasToUrl(canvas) {
        var dataUrl = '';
        try {
            dataUrl = canvas.toDataURL('image/png');
        } catch (e) {
            dataUrl = '';
        }
        if (dataUrl && dataUrl !== 'data:,') {
            return Promise.resolve({ url: dataUrl, revoke: false });
        }
        if (typeof canvas.toBlob !== 'function') {
            return Promise.reject(new Error('canvas toDataURL returned empty image'));
        }
        return new Promise(function (resolve, reject) {
            canvas.toBlob(function (blob) {
                if (!blob) {
                    reject(new Error('canvas export returned empty image'));
                    return;
                }
                resolve({ url: URL.createObjectURL(blob), revoke: true });
            }, 'image/png');
        });
    }

    /** @returns {boolean} 앱 안에 박힌 브라우저(카카오톡 등)인가. */
    function isInAppBrowser() {
        var ua = String(navigator.userAgent || '').toUpperCase();
        return ua.indexOf('KAKAOTALK') !== -1 || ua.indexOf('NAVER(INAPP') !== -1 ||
            ua.indexOf('FB_IAV') !== -1 || ua.indexOf('INSTAGRAM') !== -1 ||
            ua.indexOf('DAUMAPPS') !== -1;
    }

    /** @returns {boolean} <a download> 로 저장이 실제로 되는 환경인가. */
    function downloadSupported() {
        return 'download' in document.createElement('a');
    }

    /** @returns {boolean} 손가락으로 쓰는 단말인가(폴백 이미지 노출 판정). */
    function isTouchDevice() {
        if (window.matchMedia && window.matchMedia('(pointer: coarse)').matches) { return true; }
        return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
    }

    /** 만든 이미지를 화면에 붙인다 — 길게 눌러 사진첩에 저장하는 폴백 경로. */
    function showFallbackImage(url) {
        var box = document.querySelector('[data-share-contract-fallback]');
        var img = document.querySelector('[data-share-contract-fallback-img]');
        if (!box || !img) { return; }
        img.src = url;
        box.hidden = false;
    }

    function downloadFileName(node) {
        var name = (node.getAttribute('data-share-customer-name') || '').trim();
        var date = (node.getAttribute('data-share-issued-date') || '').trim();
        var parts = ['계약서'];
        if (name) { parts.push(name.replace(/[\\/:*?"<>|]/g, '_')); }
        if (date) { parts.push(date); }
        return parts.join('_') + '.png';
    }

    function triggerDownload(url, filename) {
        var a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.rel = 'noopener';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }

    function savePng(btn) {
        var node = docRoot();
        var wrap = wrapEl();
        if (!node) {
            showError('계약서를 찾을 수 없습니다. 페이지를 새로고침해 주세요.');
            return;
        }
        var label = btn.querySelector('[data-share-btn-label]') || btn;
        var original = label.textContent;
        btn.disabled = true;
        label.textContent = '만드는 중…';
        showError('');
        if (wrap) { wrap.classList.add('foms-share-contract--exporting'); }

        var clone = null;
        ensureHtml2canvas()
            .then(function () {
                clone = buildExportClone(node);
                return waitForImages(clone);
            })
            .then(function () {
                var height = Math.max(1, Math.ceil(clone.scrollHeight || EXPORT_WIDTH));
                return withTimeout(window.html2canvas(clone, {
                    scale: captureScale(EXPORT_WIDTH, height),
                    backgroundColor: '#ffffff',
                    useCORS: true,
                    imageTimeout: 8000,
                    logging: false,
                    width: EXPORT_WIDTH,
                    height: height,
                    windowWidth: EXPORT_WIDTH,
                    windowHeight: height
                }), RENDER_TIMEOUT_MS, 'html2canvas render timed out');
            })
            .then(function (canvas) {
                removeExportClone(clone);
                clone = null;
                return canvasToUrl(canvas);
            })
            .then(function (result) {
                if (downloadSupported()) {
                    triggerDownload(result.url, downloadFileName(node));
                }
                // 인앱 브라우저는 download 속성을 무시하고, iOS 사파리는 비동기 클릭의
                // 다운로드를 막는 사례가 있다. 터치 단말에서는 성공 여부와 무관하게
                // 이미지를 화면에도 붙여 "길게 눌러 저장" 길을 남긴다(조용한 무반응 금지).
                if (!downloadSupported() || isInAppBrowser() || isTouchDevice()) {
                    showFallbackImage(result.url);
                }
                // 폴백 이미지를 붙였으면 revoke 하지 않는다 — 60초 뒤 그림이 깨진다.
                if (result.revoke && downloadSupported() && !isInAppBrowser() && !isTouchDevice()) {
                    window.setTimeout(function () { URL.revokeObjectURL(result.url); }, 60000);
                }
            })
            .catch(function (err) {
                console.error('[share-contract] PNG 저장 실패', err);
                showError('이미지를 만들지 못했습니다. 인터넷 연결을 확인하시거나, ' +
                    '화면을 길게 눌러 캡처하거나 담당자에게 문의해 주세요.');
            })
            .then(function () {
                removeExportClone(clone);
                clone = null;
                btn.disabled = false;
                label.textContent = original;
                if (wrap) { wrap.classList.remove('foms-share-contract--exporting'); }
            });
    }

    /* ── 계좌번호 복사 ───────────────────────────────────────────────────────── */
    function legacyCopy(text) {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', 'readonly');
        ta.setAttribute('aria-hidden', 'true');
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        ta.style.top = '0';
        document.body.appendChild(ta);
        var ok = false;
        try {
            ta.select();
            ta.setSelectionRange(0, ta.value.length);
            ok = document.execCommand('copy');
        } catch (e) {
            ok = false;
        }
        document.body.removeChild(ta);
        return ok;
    }

    function copyText(text) {
        // 인앱 브라우저는 보안 컨텍스트여도 clipboard 권한이 거절될 수 있다 → 폴백 필수.
        //
        // 거절보다 나쁜 경우에 대비한다: 문서에 포커스가 없는 웹뷰에서 writeText 프라미스가
        // resolve 도 reject 도 하지 않는 사례가 보고돼 있다. 그러면 버튼은 아무 반응이 없고
        // 실패 안내조차 안 뜬다 — 원래 신고된 "눌러도 무반응"과 같은 모양이다. 짧은
        // 타임아웃과 경주시켜, 시간을 넘기면 execCommand 폴백으로 내려간다.
        // (로컬 Chromium 실측에서는 정상 경로로 즉시 성공한다 — 이 갈래는 보험이다.)
        if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
            var settled = false;
            var native = navigator.clipboard.writeText(text).then(
                function () { settled = true; return true; },
                function () { settled = true; return legacyCopy(text); }
            );
            var timeout = new Promise(function (resolve) {
                window.setTimeout(function () {
                    resolve(settled ? null : legacyCopy(text));
                }, CLIPBOARD_TIMEOUT_MS);
            }).then(function (result) {
                // 그 사이 native 가 끝났으면 native 결과를 쓴다(null = 내가 아무것도 안 함).
                return result === null ? native : result;
            });
            return Promise.race([native, timeout]);
        }
        return Promise.resolve(legacyCopy(text));
    }

    function flashCopied(btn) {
        if (btn.dataset.shareCopyBusy === '1') { return; }
        var original = btn.textContent;
        btn.dataset.shareCopyBusy = '1';
        btn.textContent = '복사됨';
        btn.classList.add('is-copied');
        window.setTimeout(function () {
            btn.textContent = original;
            btn.classList.remove('is-copied');
            delete btn.dataset.shareCopyBusy;
        }, COPY_LABEL_MS);
    }

    function handleCopy(btn) {
        var text = btn.getAttribute('data-share-copy-value') || '';
        if (!text) { return; }
        showError('');
        copyText(text).then(function (ok) {
            if (ok) {
                flashCopied(btn);
                return;
            }
            showError('계좌번호를 자동으로 복사하지 못했습니다. 계좌번호를 길게 눌러 직접 복사해 주세요.');
        });
    }

    /* ── 품목표 가로 스크롤 신호 ─────────────────────────────────────────────── */
    function refreshScrollHints() {
        var wraps = document.querySelectorAll('[data-share-contract-scroll]');
        Array.prototype.forEach.call(wraps, function (el) {
            var scrollable = el.scrollWidth - el.clientWidth > 2;
            el.classList.toggle('is-scrollable', scrollable);
        });
    }

    /* 로고·인감 로드 실패 시 숨김. defer 스크립트라 error 이벤트를 놓칠 수 있으므로
       이미 실패한 것(complete && naturalWidth===0)도 함께 판정한다. */
    function bindImageFallbacks() {
        var imgs = document.querySelectorAll('[data-share-hide-on-error]');
        Array.prototype.forEach.call(imgs, function (img) {
            if (img.complete && img.naturalWidth === 0) {
                img.classList.add('erp-est-hidden');
                return;
            }
            img.addEventListener('error', function () {
                img.classList.add('erp-est-hidden');
            }, { once: true });
        });
    }

    /* ── 배선 ────────────────────────────────────────────────────────────────── */
    function init() {
        if (!docRoot()) { return; }

        document.addEventListener('click', function (e) {
            var copyBtn = e.target.closest ? e.target.closest('[data-share-copy]') : null;
            if (copyBtn) {
                e.preventDefault();
                handleCopy(copyBtn);
                return;
            }
            var saveBtn = e.target.closest ? e.target.closest('[data-share-contract-save]') : null;
            if (saveBtn) {
                e.preventDefault();
                savePng(saveBtn);
                return;
            }
            var printBtn = e.target.closest ? e.target.closest('[data-share-print]') : null;
            if (printBtn) {
                e.preventDefault();
                // PC 보조 수단. 인앱 브라우저에서 막히면 PNG 저장으로 안내한다.
                if (typeof window.print !== 'function') {
                    showError('이 브라우저에서는 인쇄를 열 수 없습니다. "이미지로 저장"을 이용해 주세요.');
                    return;
                }
                try {
                    window.print();
                } catch (err) {
                    console.error('[share-contract] print 실패', err);
                    showError('이 브라우저에서는 인쇄를 열 수 없습니다. "이미지로 저장"을 이용해 주세요.');
                }
            }
        });

        bindImageFallbacks();
        refreshScrollHints();
        window.addEventListener('resize', refreshScrollHints);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }
})();
