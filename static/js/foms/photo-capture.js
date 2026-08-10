/**
 * P0-05: Mobile photo capture helpers (C12 draft).
 * - Applies capture="environment" to image-capable file inputs.
 * - Binds [data-foms-photo-capture] widgets (camera / gallery actions).
 */
(function (global) {
    'use strict';

    function acceptsImages(input) {
        const accept = String(input.getAttribute('accept') || '').toLowerCase();
        return accept.includes('image');
    }

    function shouldUseEnvironmentCapture(input) {
        if (!input || input.type !== 'file') return false;
        if (!acceptsImages(input)) return false;
        if (input.hasAttribute('capture')) return false;
        // 명시적 opt-out: iOS에서 카메라 강제 대신 갤러리/카메라 선택을 허용해야 하는 input.
        if (input.hasAttribute('data-foms-no-capture')) return false;
        if (input.classList.contains('foms-photo-capture__gallery-input')) return false;
        const accept = String(input.getAttribute('accept') || '').toLowerCase();
        const nonCameraExtensions = ['.pdf', '.zip', '.dwg', '.doc', '.docx', '.xlsx'];
        if (nonCameraExtensions.some(function (ext) { return accept.includes(ext); })) {
            return false;
        }
        return true;
    }

    function applyEnvironmentCapture(root) {
        const scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll('input[type="file"]').forEach(function (input) {
            if (shouldUseEnvironmentCapture(input)) {
                input.setAttribute('capture', 'environment');
            }
        });
    }

    function isCoarsePointer() {
        try {
            return !!(global.matchMedia && global.matchMedia('(pointer: coarse)').matches);
        } catch (_) {
            return false;
        }
    }

    function showDesktopPasteControls(widget) {
        const showOnDesktop = widget.querySelectorAll('[data-show-on="desktop"]');
        const coarse = isCoarsePointer();
        showOnDesktop.forEach(function (el) {
            if (coarse) {
                el.classList.add('d-none');
            } else {
                el.classList.remove('d-none');
            }
        });
        const pasteZone = widget.querySelector('[data-erp-attachment-paste-zone]');
        if (pasteZone) {
            pasteZone.classList.toggle('d-none', coarse);
        }
    }

    function bindPhotoCaptureWidget(widget) {
        if (!widget || widget._fomsPhotoCaptureBound) return;
        widget._fomsPhotoCaptureBound = true;

        const targetId = widget.getAttribute('data-target-input');
        const targetInput = targetId
            ? document.getElementById(targetId)
            : widget.querySelector('input[type="file"]:not(.foms-photo-capture__gallery-input)');

        const cameraBtn = widget.querySelector('[data-action="camera"]');
        if (cameraBtn && targetInput) {
            cameraBtn.addEventListener('click', function () {
                targetInput.click();
            });
        }

        const galleryInput = widget.querySelector('input.foms-photo-capture__gallery-input');
        const galleryBtn = widget.querySelector('[data-action="gallery"]');
        if (galleryBtn && galleryInput) {
            galleryBtn.addEventListener('click', function () {
                galleryInput.click();
            });
            galleryInput.addEventListener('change', function () {
                if (!galleryInput.files || !galleryInput.files.length) return;
                const selectedFiles = Array.from(galleryInput.files);
                if (typeof global.erpAppendAsReceiveFiles === 'function') {
                    global.erpAppendAsReceiveFiles(selectedFiles);
                } else if (targetInput) {
                    targetInput.files = galleryInput.files;
                    targetInput.dispatchEvent(new Event('change', { bubbles: true }));
                }
                galleryInput.value = '';
            });
        }

        showDesktopPasteControls(widget);
    }

    function bindPhotoCaptureWidgets(root) {
        const scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll('[data-foms-photo-capture]').forEach(bindPhotoCaptureWidget);
    }

    function initAsReceiveModalFocus() {
        const modal = document.getElementById('asReceiveModal');
        if (!modal || modal._fomsPhotoCaptureFocusBound) return;
        modal._fomsPhotoCaptureFocusBound = true;
        modal.addEventListener('shown.bs.modal', function () {
            if (!isCoarsePointer()) return;
            const cameraBtn = modal.querySelector('[data-action="camera"]');
            if (cameraBtn && typeof cameraBtn.focus === 'function') {
                cameraBtn.focus();
            }
        });
    }

    function initPhotoCapture(root) {
        const scope = root && root.nodeType === 1 ? root : document;
        applyEnvironmentCapture(scope);
        bindPhotoCaptureWidgets(scope);
        initAsReceiveModalFocus();

        if (scope._fomsPhotoCaptureObserver) return;
        const observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                mutation.addedNodes.forEach(function (node) {
                    if (!node || node.nodeType !== 1) return;
                    applyEnvironmentCapture(node);
                    bindPhotoCaptureWidgets(node);
                });
            });
        });
        observer.observe(scope, { childList: true, subtree: true });
        scope._fomsPhotoCaptureObserver = observer;
    }

    global.FOMSPhotoCapture = {
        applyEnvironmentCapture: applyEnvironmentCapture,
        initPhotoCapture: initPhotoCapture,
        isCoarsePointer: isCoarsePointer,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            initPhotoCapture(document);
        });
    } else {
        initPhotoCapture(document);
    }
})(typeof window !== 'undefined' ? window : globalThis);
