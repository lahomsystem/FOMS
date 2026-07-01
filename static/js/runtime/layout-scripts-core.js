/**
 * Global immersive image viewer + mobile image gate (layout partial extract).
 */
(function () {
  'use strict';
  if (window.__FOMS_LAYOUT_SCRIPTS_CORE_BOUND) return;
  window.__FOMS_LAYOUT_SCRIPTS_CORE_BOUND = true;

// Global Immersive Image Viewer Logic
        window.GlobalImageViewer = (function () {
            const state = {
                files: [],
                index: 0,
                scale: 1,
                tx: 0, ty: 0,
                dragging: false,
                dragStartX: 0, dragStartY: 0,
                baseTx: 0, baseTy: 0,
                touchStartX: 0,
                touchStartY: 0,
                touchLastX: 0,
                touchLastY: 0,
                touching: false,
                pinching: false,
                pinchStartDist: 0,
                pinchStartScale: 1,
                panning: false,
                panStartX: 0,
                panStartY: 0,
                panBaseTx: 0,
                panBaseTy: 0,
                // Double-tap (tap-to-zoom) tracking
                touchStartTime: 0,
                lastTapTime: 0,
                lastTapX: 0,
                lastTapY: 0
            };

            let els = {};

            function init() {
                if (els.root) return; // Already init

                els = {
                    root: document.getElementById('global-image-viewer'),
                    backdrop: document.getElementById('global-viewer-backdrop'),
                    closeBtn: document.getElementById('global-viewer-close'),
                    downloadBtn: document.getElementById('global-viewer-download'),
                    prevBtn: document.getElementById('global-viewer-prev'),
                    nextBtn: document.getElementById('global-viewer-next'),
                    stage: document.getElementById('global-viewer-stage'),
                    image: document.getElementById('global-viewer-image'),
                    video: document.getElementById('global-viewer-video'),
                };

                if (!els.root) return;

                // Events
                els.closeBtn?.addEventListener('click', close);
                els.backdrop?.addEventListener('click', close);
                els.prevBtn?.addEventListener('click', prev);
                els.nextBtn?.addEventListener('click', next);

                // Show nav on mouse move
                els.root.addEventListener('mousemove', () => {
                    els.root.classList.add('nav-visible');
                });
                els.root.addEventListener('mouseleave', () => {
                    els.root.classList.remove('nav-visible');
                });

                // Zoom
                els.image?.addEventListener('wheel', handleWheel, { passive: false });

                // Drag
                els.image?.addEventListener('mousedown', startDrag);
                window.addEventListener('mousemove', doDrag);
                window.addEventListener('mouseup', endDrag);

                // Keys
                document.addEventListener('keydown', handleKey);

                // Keep desktop nav arrows pinned to screen edges
                els.image?.addEventListener('load', positionNavButtons);
                window.addEventListener('resize', () => {
                    if (els.root && els.root.style.display !== 'none') {
                        requestAnimationFrame(positionNavButtons);
                    }
                });

                // Close when clicking empty area (outside image)
                els.stage?.addEventListener('click', (e) => {
                    if (e.target === els.stage) close();
                });

                // Mobile gestures: 1-finger pan when zoomed, 2-finger pinch zoom, swipe nav when not zoomed.
                // touchmove must be non-passive so pan/pinch can preventDefault the browser's native zoom/scroll.
                els.stage?.addEventListener('touchstart', handleTouchStart, { passive: true });
                els.stage?.addEventListener('touchmove', handleTouchMove, { passive: false });
                els.stage?.addEventListener('touchend', handleTouchEnd, { passive: true });
                els.stage?.addEventListener('touchcancel', handleTouchEnd, { passive: true });
            }

            function open(files, startIndex = 0) {
                init(); // Ensure init
                if (!files || !files.length) return;

                // Normalize files structure while keeping durable src values on app file routes.
                state.files = files.map(f => {
                    function encodePath(k) { return String(k).split('/').map(function (s) { return encodeURIComponent(s); }).join('/'); }
                    function decodePath(k) { return String(k).split('/').map(function (s) { try { return decodeURIComponent(s); } catch (e) { return s; } }).join('/'); }
                    function appStorageKey(value, prefix) {
                        var text = String(value || '');
                        if (!text) return null;
                        try {
                            var parsed = new URL(text, window.location.origin);
                            if (parsed.pathname.indexOf(prefix) === 0) return decodePath(parsed.pathname.slice(prefix.length));
                        } catch (e) { }
                        if (text.indexOf(prefix) === 0) return decodePath(text.slice(prefix.length).split(/[?#]/, 1)[0]);
                        return null;
                    }
                    function isSignedStorageUrl(url) {
                        return /(?:^|\/\/|[.])r2\.cloudflarestorage\.com/i.test(url || '') ||
                            /(?:[?&](?:X-Amz-Signature|Signature)=)/i.test(url || '');
                    }
                    const key = f.key || f.storage_key || appStorageKey(f.download_url, '/api/files/download/') || appStorageKey(f.view_url || f.url, '/api/files/view/') || null;
                    const stableViewUrl = key ? `/api/files/view/${encodePath(key)}` : '';
                    const stableDownloadUrl = key ? `/api/files/download/${encodePath(key)}` : '';
                    const rawViewUrl = f.view_url || f.url || '';
                    const rawDownloadUrl = f.download_url || '';
                    return {
                        url: (key && isSignedStorageUrl(rawViewUrl)) ? stableViewUrl : (rawViewUrl || stableViewUrl),
                        filename: f.filename || f.name || '이미지',
                        download_url: (key && isSignedStorageUrl(rawDownloadUrl)) ? stableDownloadUrl : (rawDownloadUrl || stableDownloadUrl),
                        key: key || null
                    };
                }).filter(f => !!f.url);

                if (state.files.length === 0) {
                    alert('표시할 이미지가 없습니다.');
                    return;
                }

                state.index = Math.max(0, Math.min(state.files.length - 1, startIndex));

                els.root.style.display = 'flex';
                els.root.classList.add('d-flex');
                els.root.setAttribute('aria-hidden', 'false');
                document.body.style.overflow = 'hidden'; // Lock scroll

                render();
            }
            function close() {
                if (!els.root) return;
                els.root.style.display = 'none';
                els.root.classList.remove('d-flex');
                els.root.setAttribute('aria-hidden', 'true');
                document.body.style.overflow = '';
                state.files = [];
                // CS 완료 더블체크가 주입한 코멘트가 다음 이미지에 남지 않도록 정리.
                var completionExtra = document.getElementById('global-viewer-completion-extra');
                if (completionExtra) completionExtra.remove();
                if (els.video) {
                    els.video.pause();
                    els.video.src = '';
                }
            }

            function render() {
                const file = state.files[state.index];
                if (!file) return;

                // Reset transform + gesture state
                state.scale = 1;
                state.tx = 0;
                state.ty = 0;
                state.pinching = false;
                state.panning = false;
                state.touching = false;
                state.dragging = false;
                setGestureTransition(false);
                updateTransform();

                var isVideo = (file.url || '').match(/\.(mp4|webm|ogg)$/i) || (file.filename || '').match(/\.(mp4|webm|ogg)$/i);

                if (isVideo) {
                    els.image.style.display = 'none';
                    els.image.src = '';
                    els.video.style.display = 'block';
                    els.video.src = file.url;
                } else {
                    els.video.style.display = 'none';
                    els.video.pause();
                    els.video.src = '';
                    els.image.style.display = 'block';
                    els.image.src = file.url;
                    els.image.alt = file.filename;
                }

                if (els.downloadBtn) {
                    if (file.download_url) {
                        els.downloadBtn.href = file.download_url;
                        els.downloadBtn.style.display = 'flex';
                    } else {
                        els.downloadBtn.removeAttribute('href');
                        els.downloadBtn.style.display = 'none';
                    }
                }

                if (state.files.length > 1) {
                    els.root.classList.remove('single-file');
                } else {
                    els.root.classList.add('single-file');
                }
                requestAnimationFrame(positionNavButtons);

                // Direct R2 signed URLs expire; the app route issues a fresh redirect per load.
            }

            function updateTransform() {
                if (els.image) els.image.style.transform = `translate(${state.tx}px, ${state.ty}px) scale(${state.scale})`;
            }

            function stageCenter() {
                const r = (els.stage || els.root).getBoundingClientRect();
                return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
            }

            // Zoom toward a screen focal point (pinch midpoint / tap / cursor) so the
            // pixel under the fingers stays fixed — the "smooth" native-photos feel.
            // transform-origin is center center, so focal is measured from the stage center.
            function zoomToFocal(nextScale, focalClientX, focalClientY, animate) {
                nextScale = Math.max(1, Math.min(5, nextScale));
                const c = stageCenter();
                const fx = focalClientX - c.x;
                const fy = focalClientY - c.y;
                const ratio = state.scale > 0 ? nextScale / state.scale : 1;
                if (animate && els.image) els.image.style.transition = 'transform 0.22s ease';
                state.tx = fx - ratio * (fx - state.tx);
                state.ty = fy - ratio * (fy - state.ty);
                state.scale = nextScale;
                if (state.scale <= 1.01) {
                    state.scale = 1;
                    state.tx = 0;
                    state.ty = 0;
                } else {
                    clampPan();
                }
                updateTransform();
                if (animate && els.image) {
                    setTimeout(function () {
                        // Don't clobber the 'none' a live pinch/pan just set.
                        if (els.image && !state.pinching && !state.panning) els.image.style.transition = '';
                    }, 240);
                }
            }

            function prev() {
                if (state.index > 0) {
                    state.index--;
                    render();
                }
            }

            function next() {
                if (state.index < state.files.length - 1) {
                    state.index++;
                    render();
                }
            }

            function handleWheel(e) {
                e.preventDefault();
                // Multiplicative step + cursor focal point = smooth zoom toward the pointer.
                const factor = e.deltaY > 0 ? 0.9 : 1.1;
                zoomToFocal(state.scale * factor, e.clientX, e.clientY, false);
            }

            function startDrag(e) {
                e.preventDefault();
                state.dragging = true;
                state.dragStartX = e.clientX;
                state.dragStartY = e.clientY;
                state.baseTx = state.tx;
                state.baseTy = state.ty;
                els.image.style.cursor = 'grabbing';
            }

            function doDrag(e) {
                if (!state.dragging) return;
                e.preventDefault();
                state.tx = state.baseTx + (e.clientX - state.dragStartX);
                state.ty = state.baseTy + (e.clientY - state.dragStartY);
                clampPan();
                updateTransform();
            }

            function endDrag() {
                state.dragging = false;
                if (els.image) els.image.style.cursor = 'grab';
            }

            function handleKey(e) {
                if (!els.root || els.root.style.display === 'none') return;
                if (e.key === 'Escape') close();
                if (e.key === 'ArrowLeft') prev();
                if (e.key === 'ArrowRight') next();
            }

            function positionNavButtons() {
                if (!els.root || !els.image || !els.prevBtn || !els.nextBtn) return;
                if (els.root.classList.contains('single-file')) return;

                els.prevBtn.style.left = '24px';
                els.prevBtn.style.right = 'auto';
                els.prevBtn.style.top = '50%';

                els.nextBtn.style.left = 'auto';
                els.nextBtn.style.right = '24px';
                els.nextBtn.style.top = '50%';
            }

            function setGestureTransition(active) {
                // Disable the 0.1s transform transition during active gestures so pan/pinch tracks the finger.
                if (els.image) els.image.style.transition = active ? 'none' : '';
            }

            function touchDistance(a, b) {
                return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
            }

            function beginTouchPan(touch) {
                if (!touch) return;
                state.panning = true;
                state.touching = false;
                state.panStartX = touch.clientX;
                state.panStartY = touch.clientY;
                state.panBaseTx = state.tx;
                state.panBaseTy = state.ty;
                setGestureTransition(true);
            }

            function clampPan() {
                // Keep the (scaled) image from being dragged completely off the stage.
                if (!els.image) return;
                if (state.scale <= 1) { state.tx = 0; state.ty = 0; return; }
                const imgRect = els.image.getBoundingClientRect();
                const stageRect = els.stage
                    ? els.stage.getBoundingClientRect()
                    : { width: window.innerWidth, height: window.innerHeight };
                const maxX = Math.max(0, (imgRect.width - stageRect.width) / 2);
                const maxY = Math.max(0, (imgRect.height - stageRect.height) / 2);
                state.tx = Math.max(-maxX, Math.min(maxX, state.tx));
                state.ty = Math.max(-maxY, Math.min(maxY, state.ty));
            }

            function handleTouchStart(e) {
                if (!e.touches) return;

                if (e.touches.length === 2) {
                    // Begin pinch-zoom (viewer owns zoom; native page zoom is blocked via touch-action).
                    state.pinching = true;
                    state.panning = false;
                    state.touching = false;
                    state.pinchStartDist = touchDistance(e.touches[0], e.touches[1]);
                    state.pinchStartScale = state.scale;
                    setGestureTransition(true);
                    return;
                }

                if (e.touches.length === 1) {
                    const t = e.touches[0];
                    state.touchStartX = t.clientX;
                    state.touchStartY = t.clientY;
                    state.touchLastX = t.clientX;
                    state.touchLastY = t.clientY;
                    state.touchStartTime = Date.now();
                    if (state.scale > 1.05) {
                        // Zoomed in → one-finger drag pans the image.
                        beginTouchPan(t);
                    } else {
                        // Not zoomed → candidate for swipe navigation.
                        state.touching = true;
                    }
                }
            }

            function handleTouchMove(e) {
                if (state.pinching && e.touches && e.touches.length === 2) {
                    e.preventDefault();
                    const dist = touchDistance(e.touches[0], e.touches[1]);
                    if (state.pinchStartDist > 0) {
                        const next = state.pinchStartScale * (dist / state.pinchStartDist);
                        // Anchor zoom at the live pinch midpoint so the image tracks the fingers.
                        const midX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
                        const midY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
                        zoomToFocal(next, midX, midY, false);
                    }
                    return;
                }

                if (state.panning && e.touches && e.touches.length === 1) {
                    e.preventDefault();
                    const t = e.touches[0];
                    state.tx = state.panBaseTx + (t.clientX - state.panStartX);
                    state.ty = state.panBaseTy + (t.clientY - state.panStartY);
                    clampPan();
                    updateTransform();
                    return;
                }

                if (!state.pinching && !state.panning && state.scale > 1.05 && e.touches && e.touches.length === 1) {
                    e.preventDefault();
                    beginTouchPan(e.touches[0]);
                    return;
                }

                if (state.touching && e.touches && e.touches.length === 1) {
                    const t = e.touches[0];
                    state.touchLastX = t.clientX;
                    state.touchLastY = t.clientY;
                }
            }

            function handleTouchEnd(e) {
                const remaining = e && e.touches ? e.touches.length : 0;

                // Double-tap to zoom (toward the tap point) / reset — runs before pan/swipe
                // handling so a quick tap-tap is not mistaken for a pan or swipe.
                const ct = e && e.changedTouches && e.changedTouches[0];
                const wasTap = ct && remaining === 0 && !state.pinching &&
                    (Date.now() - state.touchStartTime) < 250 &&
                    Math.abs(ct.clientX - state.touchStartX) < 20 &&
                    Math.abs(ct.clientY - state.touchStartY) < 20;
                if (wasTap) {
                    const now = Date.now();
                    if (now - state.lastTapTime < 300 &&
                        Math.abs(ct.clientX - state.lastTapX) < 40 &&
                        Math.abs(ct.clientY - state.lastTapY) < 40) {
                        state.lastTapTime = 0;
                        state.panning = false;
                        state.touching = false;
                        if (state.scale > 1.05) zoomToFocal(1, ct.clientX, ct.clientY, true);
                        else zoomToFocal(2.5, ct.clientX, ct.clientY, true);
                        return;
                    }
                    state.lastTapTime = now;
                    state.lastTapX = ct.clientX;
                    state.lastTapY = ct.clientY;
                }

                if (state.pinching) {
                    if (remaining < 2) {
                        state.pinching = false;
                        if (state.scale <= 1.05) {
                            state.scale = 1;
                            state.tx = 0;
                            state.ty = 0;
                            setGestureTransition(false);
                            updateTransform();
                        } else if (remaining === 1 && e.touches && e.touches[0]) {
                            beginTouchPan(e.touches[0]);
                        } else {
                            setGestureTransition(false);
                        }
                    }
                    return;
                }

                if (state.panning) {
                    if (remaining === 0) {
                        state.panning = false;
                        setGestureTransition(false);
                    }
                    return;
                }

                if (!state.touching) return;
                state.touching = false;

                // While zoomed in, keep swipe navigation disabled.
                if (state.scale > 1.05) return;

                const dx = state.touchLastX - state.touchStartX;
                const dy = state.touchLastY - state.touchStartY;
                const horizontalSwipe = Math.abs(dx) > 56 && Math.abs(dx) > Math.abs(dy) * 1.2;
                if (!horizontalSwipe) return;

                if (dx < 0) next();
                else prev();
            }

            return {
                init,
                open,
                close
            };
        })();

        /**
         * Mobile image-viewing SSOT gate. On mobile (<=768px), all read-only image
         * viewing routes through GlobalImageViewer (blur backdrop + smooth focal zoom).
         * Desktop keeps its existing per-surface modals untouched.
         */
        window.fomsIsMobileImageViewer = function () {
            try {
                return !!(window.matchMedia && window.matchMedia('(max-width: 768px)').matches) &&
                    !!(window.GlobalImageViewer && window.GlobalImageViewer.open);
            } catch (e) {
                return false;
            }
        };

        /** Legacy hook: keep thumbnails on stable app file routes instead of expiring R2 signed URLs. */
        window.erpReplaceThumbnailsWithPresigned = function (container) {
            var root = container && container.nodeType === 1 ? container : document;
            var imgs = root.querySelectorAll ? root.querySelectorAll('img[data-storage-key]') : [];
            if (!imgs.length) return;
            function encodePath(k) { return String(k).split('/').map(function (s) { return encodeURIComponent(s); }).join('/'); }
            function isSignedStorageUrl(url) {
                return /(?:^|\/\/|[.])r2\.cloudflarestorage\.com/i.test(url || '') ||
                    /(?:[?&](?:X-Amz-Signature|Signature)=)/i.test(url || '');
            }
            Array.prototype.forEach.call(imgs, function (img) {
                var key = img.getAttribute('data-storage-key');
                if (!key) return;
                var stableUrl = img.getAttribute('data-foms-erp-attachment-view-url') || ('/api/files/view/' + encodePath(key));
                if (!img.getAttribute('src') || isSignedStorageUrl(img.getAttribute('src'))) {
                    img.src = stableUrl;
                }
            });
        };

        document.addEventListener('DOMContentLoaded', () => {
            window.GlobalImageViewer.init();
            if (window.erpReplaceThumbnailsWithPresigned) window.erpReplaceThumbnailsWithPresigned(document);
        });
})();

