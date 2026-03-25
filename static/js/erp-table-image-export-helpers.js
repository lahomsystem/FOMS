/**
 * 실측/출고 일정표 html2canvas PNG 저장 공통 헬퍼.
 * 고해상도 아이콘(예: 640px)이 CSS 40px로 축소된 뒤 캡처되면 이중 샘플링으로 흐려지므로,
 * scale 상향 + 클론 DOM에서 결제 아이콘만 일시 확대해 원본에 가깝게 래스터화한다.
 */
(function (global) {
    'use strict';

    /** 캡처 배율: Retina 대응, 상한으로 파일 크기 제한 */
    function erpTableExportCaptureScale() {
        return Math.min(4, Math.max(3, Math.ceil((window.devicePixelRatio || 1) * 1.5)));
    }

    /** html2canvas 전에 img 디코드 완료 대기 (미로드 시 저해상도/빈 그림 방지) */
    function erpTableExportWaitForImages(root) {
        var imgs = root.querySelectorAll('img');
        return Promise.all(
            Array.prototype.map.call(imgs, function (img) {
                if (img.complete && img.naturalWidth > 0) {
                    return img.decode ? img.decode().catch(function () {}) : Promise.resolve();
                }
                return new Promise(function (resolve) {
                    img.addEventListener('load', resolve, { once: true });
                    img.addEventListener('error', resolve, { once: true });
                }).then(function () {
                    return img.decode ? img.decode().catch(function () {}) : Promise.resolve();
                });
            })
        );
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
        });
        clonedDoc.querySelectorAll('img.erp-custom-payment-unconfirmed').forEach(function (img) {
            img.style.setProperty('filter', 'grayscale(1)');
            img.style.setProperty('-webkit-filter', 'grayscale(1)');
            img.style.setProperty('opacity', '0.5');
        });
        clonedDoc.querySelectorAll('img.erp-custom-payment-confirmed').forEach(function (img) {
            img.style.setProperty('filter', 'none');
            img.style.setProperty('opacity', '1');
        });
    }

    global.erpTableExportCaptureScale = erpTableExportCaptureScale;
    global.erpTableExportWaitForImages = erpTableExportWaitForImages;
    global.erpTableExportStylePaymentIconsInClone = erpTableExportStylePaymentIconsInClone;
})(typeof window !== 'undefined' ? window : globalThis);
