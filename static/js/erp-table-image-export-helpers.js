/**
 * 실측/출고 일정표 html2canvas PNG 저장 공통 헬퍼.
 * 고해상도 아이콘(예: 640px)이 CSS 40px로 축소된 뒤 캡처되면 이중 샘플링으로 흐려지므로,
 * scale 상향 + 클론 DOM에서 결제 아이콘만 일시 확대해 원본에 가깝게 래스터화한다.
 * 미확인 상태는 pay-*-gray.png 비트맵을 쓰므로 clone에서 filter를 적용하지 않는다.
 */
(function (global) {
    'use strict';

    /** 캡처 배율: Retina 대응, 상한으로 파일 크기 제한 */
    function erpTableExportCaptureScale() {
        return Math.min(4, Math.max(3, Math.ceil((window.devicePixelRatio || 1) * 1.5)));
    }

    /** 단일 이미지가 load/error 없이 멈추는 경우(프로덕션 CDN 지연 등) 무한 대기 방지 */
    var ERP_TABLE_EXPORT_IMAGE_MS = 12000;

    /** html2canvas 전에 img 디코드 완료 대기 (미로드 시 저해상도/빈 그림 방지) */
    function erpTableExportWaitForImages(root) {
        var imgs = root.querySelectorAll('img');
        return Promise.all(
            Array.prototype.map.call(imgs, function (img) {
                return new Promise(function (resolve) {
                    var settled = false;
                    function finish() {
                        if (settled) return;
                        settled = true;
                        if (img.decode) {
                            img.decode().catch(function () {}).then(function () {
                                resolve();
                            });
                        } else {
                            resolve();
                        }
                    }
                    if (img.complete && img.naturalWidth > 0) {
                        finish();
                        return;
                    }
                    var t = setTimeout(finish, ERP_TABLE_EXPORT_IMAGE_MS);
                    img.addEventListener(
                        'load',
                        function () {
                            clearTimeout(t);
                            finish();
                        },
                        { once: true }
                    );
                    img.addEventListener(
                        'error',
                        function () {
                            clearTimeout(t);
                            finish();
                        },
                        { once: true }
                    );
                });
            })
        );
    }

    /**
     * Promise가 일정 시간 안에 끝나지 않으면 거부 (html2canvas 무한 대기 방지).
     * @param {Promise} promise
     * @param {number} ms
     * @param {string} [label]
     */
    function erpTableExportPromiseWithTimeout(promise, ms, label) {
        var msNum = typeof ms === 'number' && ms > 0 ? ms : 180000;
        var tag = label || '작업';
        return Promise.race([
            promise,
            new Promise(function (_, reject) {
                setTimeout(function () {
                    reject(new Error(tag + ' 시간 초과(' + Math.round(msNum / 1000) + '초). 네트워크 또는 표 크기를 확인해 주세요.'));
                }, msNum);
            })
        ]);
    }

    /**
     * onclone 문서에서 결제 아이콘 스타일.
     * @param {Document} clonedDoc
     * @param {number} [iconCssPx=80] 화면 40px 대비 클론에서만 확대할 크기
     */
    function erpTableExportStylePaymentIconsInClone(clonedDoc, iconCssPx) {
        var px = iconCssPx != null ? iconCssPx : 80;
        clonedDoc.querySelectorAll('img.erp-custom-payment-icon').forEach(function (img) {
            img.style.setProperty('width', px + 'px');
            img.style.setProperty('height', px + 'px');
            img.style.setProperty('transition', 'none');
            img.style.setProperty('object-fit', 'contain');
            img.style.setProperty('filter', 'none');
            img.style.setProperty('opacity', '1');
        });
    }

    global.erpTableExportCaptureScale = erpTableExportCaptureScale;
    global.erpTableExportWaitForImages = erpTableExportWaitForImages;
    global.erpTableExportPromiseWithTimeout = erpTableExportPromiseWithTimeout;
    global.erpTableExportStylePaymentIconsInClone = erpTableExportStylePaymentIconsInClone;
})(typeof window !== 'undefined' ? window : globalThis);
