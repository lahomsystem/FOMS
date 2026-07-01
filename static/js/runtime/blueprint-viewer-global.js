/**
 * Blueprint viewer modal + ERP order-list reload-after-save (layout partial extract).
 */
(function () {
  'use strict';
  if (window.__FOMS_BLUEPRINT_VIEWER_BOUND) return;
  window.__FOMS_BLUEPRINT_VIEWER_BOUND = true;

// 도면 뷰어 줌 관련 변수
        let blueprintZoom = {
            scale: 1,
            minScale: 0.5,
            maxScale: 5,
            translateX: 0,
            translateY: 0
        };

        function updateBlueprintTransform() {
            const img = document.getElementById('blueprint-viewer-img');
            if (img) {
                img.style.transform = `translate(${blueprintZoom.translateX}px, ${blueprintZoom.translateY}px) scale(${blueprintZoom.scale})`;
                img.style.transformOrigin = 'center center';
            }
        }

        function resetBlueprintZoom() {
            blueprintZoom.scale = 1;
            blueprintZoom.translateX = 0;
            blueprintZoom.translateY = 0;
            updateBlueprintTransform();
        }

        // 도면 다운로드 관련 변수
        let currentBlueprintUrl = null;
        let currentBlueprintOrderId = null;

        // =====================================================================
        // Global ERP Dashboard Reload Logic (for when returning from edit page)
        // =====================================================================
        (function () {
            var reloadKey = 'foms:reload-order-list-after-erp-save';
            var scrollKey = 'foms:restore-order-list-scroll';

            function sameOrderListUrl(expectedUrl) {
                if (!expectedUrl) return false;
                try {
                    var expected = new URL(expectedUrl, window.location.origin);
                    return expected.origin === window.location.origin
                        && expected.pathname === window.location.pathname
                        && expected.search === window.location.search;
                } catch (e) {
                    return false;
                }
            }

            window.addEventListener('pageshow', function (event) {
                var expectedUrl = '';
                try {
                    expectedUrl = sessionStorage.getItem(reloadKey) || '';
                } catch (e) {
                    expectedUrl = '';
                }
                
                // If the key is not for this page, do nothing.
                if (!sameOrderListUrl(expectedUrl)) return;

                // Check if this is a back/forward navigation (either bfcache or HTTP cache)
                var isBackForward = event.persisted;
                if (!isBackForward && window.performance) {
                    var navEntries = performance.getEntriesByType("navigation");
                    if (navEntries.length > 0 && navEntries[0].type === "back_forward") {
                        isBackForward = true;
                    }
                }

                if (!isBackForward) return;

                try {
                    sessionStorage.removeItem(reloadKey);
                    sessionStorage.setItem(scrollKey, String(window.scrollY || document.documentElement.scrollTop || 0));
                } catch (e) {
                    // Best-effort only; fresh data is more important than scroll restoration.
                }
                window.location.reload();
            });

            window.addEventListener('DOMContentLoaded', function () {
                try {
                    var expectedUrl = sessionStorage.getItem(reloadKey) || '';
                    if (sameOrderListUrl(expectedUrl)) {
                        // Check if this is a back/forward navigation
                        var isBackForward = false;
                        if (window.performance) {
                            var navEntries = performance.getEntriesByType("navigation");
                            if (navEntries.length > 0 && navEntries[0].type === "back_forward") {
                                isBackForward = true;
                            }
                        }
                        
                        // If it's a back navigation, DO NOT remove the key here, let pageshow handle it and reload.
                        // If it's a fresh load (e.g. they clicked a link to here), remove the key to prevent future reloads.
                        if (!isBackForward) {
                            sessionStorage.removeItem(reloadKey);
                        }
                    }
                } catch (e) {
                    // Ignore storage cleanup failures; the page itself is already fresh.
                }

                var y = '';
                try {
                    y = sessionStorage.getItem(scrollKey) || '';
                    sessionStorage.removeItem(scrollKey);
                } catch (e) {
                    y = '';
                }
                if (!y) return;
                var scrollY = parseInt(y, 10);
                if (!Number.isFinite(scrollY) || scrollY <= 0) return;
                requestAnimationFrame(function () {
                    window.scrollTo(0, scrollY);
                });
            });
        })();

        // 도면 다운로드 함수
        function downloadBlueprint() {
            if (!currentBlueprintUrl) {
                alert('다운로드할 도면이 없습니다.');
                return;
            }

            // 이미지 URL에서 파일명 추출 또는 orderId 기반 파일명 생성
            const filename = `blueprint_${currentBlueprintOrderId || 'image'}.jpg`;

            // 다운로드 링크 생성
            const link = document.createElement('a');
            link.href = currentBlueprintUrl;
            link.download = filename;
            link.target = '_blank';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }

        // 전역 함수로 노출
        window.openBlueprintViewer = function (orderId) {
            fetch(`/api/orders/${orderId}/blueprint`)
                .then(response => response.json())
                .then(data => {
                    if (data.success && data.url) {
                        const modal = new bootstrap.Modal(document.getElementById('blueprintViewerModal'));
                        const img = document.getElementById('blueprint-viewer-img');
                        const modalBody = document.getElementById('blueprint-viewer-body');
                        const downloadBtn = document.getElementById('blueprint-download-btn');

                        // 다운로드 버튼 표시 및 URL 저장
                        currentBlueprintUrl = data.url;
                        currentBlueprintOrderId = orderId;
                        if (downloadBtn) {
                            downloadBtn.style.display = 'inline-block';
                        }

                        // 줌 리셋
                        resetBlueprintZoom();

                        // 이미지 로드 후 transform 적용
                        img.onload = function () {
                            resetBlueprintZoom();
                        };

                        // 이미지 소스 설정
                        img.src = data.url;

                        // 모달 표시
                        modal.show();
                    } else {
                        alert('도면이 없습니다.');
                    }
                })
                .catch(error => {
                    console.error('도면 조회 오류:', error);
                    alert('도면을 불러올 수 없습니다.');
                });
        };

        // 마우스 휠로 줌 인/아웃
        document.addEventListener('DOMContentLoaded', function () {
            const modal = document.getElementById('blueprintViewerModal');
            const modalBody = document.getElementById('blueprint-viewer-body');
            const img = document.getElementById('blueprint-viewer-img');

            if (modal && modalBody && img) {
                // 마우스 휠 이벤트
                modalBody.addEventListener('wheel', function (e) {
                    // 모달이 활성화되어 있는지 확인
                    if (!modal.classList.contains('show')) {
                        return;
                    }

                    e.preventDefault();
                    e.stopPropagation();

                    const delta = e.deltaY > 0 ? -0.1 : 0.1;
                    const newScale = Math.max(blueprintZoom.minScale,
                        Math.min(blueprintZoom.maxScale, blueprintZoom.scale + delta));

                    // 마우스 위치를 중심으로 확대/축소
                    const rect = modalBody.getBoundingClientRect();
                    const mouseX = e.clientX - rect.left - rect.width / 2;
                    const mouseY = e.clientY - rect.top - rect.height / 2;

                    const scaleChange = newScale / blueprintZoom.scale;
                    blueprintZoom.translateX = blueprintZoom.translateX * scaleChange + mouseX * (1 - scaleChange);
                    blueprintZoom.translateY = blueprintZoom.translateY * scaleChange + mouseY * (1 - scaleChange);

                    blueprintZoom.scale = newScale;
                    updateBlueprintTransform();
                }, { passive: false });

                // 드래그로 이미지 이동
                let isDragging = false;
                let dragStartX = 0;
                let dragStartY = 0;
                let startTranslateX = 0;
                let startTranslateY = 0;

                img.addEventListener('mousedown', function (e) {
                    if (e.button === 0 && modal.classList.contains('show')) { // 왼쪽 마우스 버튼만
                        isDragging = true;
                        dragStartX = e.clientX;
                        dragStartY = e.clientY;
                        startTranslateX = blueprintZoom.translateX;
                        startTranslateY = blueprintZoom.translateY;
                        img.style.cursor = 'grabbing';
                        e.preventDefault();
                    }
                });

                document.addEventListener('mousemove', function (e) {
                    if (isDragging && modal.classList.contains('show')) {
                        const deltaX = e.clientX - dragStartX;
                        const deltaY = e.clientY - dragStartY;
                        blueprintZoom.translateX = startTranslateX + deltaX;
                        blueprintZoom.translateY = startTranslateY + deltaY;
                        updateBlueprintTransform();
                    }
                });

                document.addEventListener('mouseup', function (e) {
                    if (isDragging) {
                        isDragging = false;
                        img.style.cursor = 'grab';
                    }
                });

                // 모달이 닫힐 때 줌 리셋
                modal.addEventListener('hidden.bs.modal', function () {
                    resetBlueprintZoom();
                    // 다운로드 관련 변수 초기화
                    currentBlueprintUrl = null;
                    currentBlueprintOrderId = null;
                    const downloadBtn = document.getElementById('blueprint-download-btn');
                    if (downloadBtn) {
                        downloadBtn.style.display = 'none';
                    }
                });
            }
        });
  window.downloadBlueprint = downloadBlueprint;
})();

