/**
 * Global notification badge/panel (layout partial extract).
 */
(function () {
  'use strict';
  if (window.__FOMS_LAYOUT_SCRIPTS_CHAT_BOUND) return;
  window.__FOMS_LAYOUT_SCRIPTS_CHAT_BOUND = true;

// Global Notification System
        let globalNotificationOpen = false;
        function fomsLayoutHasCurrentUser() {
            var el = document.getElementById('foms-layout-bootstrap');
            return !!(el && el.getAttribute('data-has-current-user') === 'true');
        }
        var hasCurrentUser = fomsLayoutHasCurrentUser();

        function renderGlobalNotificationBadge(count) {
            const badge = document.getElementById('global-notification-badge');
            const icon = document.getElementById('global-notification-icon');
            if (!badge || !icon) return;

            if (count > 0) {
                badge.textContent = count > 99 ? '99+' : count;
                badge.style.display = 'block';
                icon.classList.add('bell-active');
            } else {
                badge.style.display = 'none';
                icon.classList.remove('bell-active');
                icon.style.color = '#6c757d';
            }
        }

        window.FOMSNotificationBadge = window.FOMSNotificationBadge || (function () {
            const subscribers = new Map();
            const POLL_INTERVAL_MS = 60000;
            const MIN_REFRESH_MS = 5000;
            let count = 0;
            let inFlight = null;
            let lastResolvedAt = 0;
            let pollTimer = null;
            let started = false;

            function emit() {
                subscribers.forEach(function (callback) {
                    try {
                        callback(count);
                    } catch (err) {
                        console.error('Notification badge subscriber error:', err);
                    }
                });
            }

            function normalizeCount(value) {
                const parsed = Number(value);
                return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
            }

            async function refresh(options) {
                options = options || {};
                const force = !!options.force;
                const now = Date.now();

                if (!hasCurrentUser) {
                    count = 0;
                    emit();
                    return count;
                }

                if (inFlight) {
                    return inFlight;
                }

                if (!force && lastResolvedAt && (now - lastResolvedAt) < MIN_REFRESH_MS) {
                    emit();
                    return count;
                }

                inFlight = fetch('/erp/api/notifications/badge', {
                    headers: { 'Accept': 'application/json' }
                })
                    .then(async function (res) {
                        if (!res.ok) {
                            return count;
                        }

                        const contentType = res.headers.get('content-type') || '';
                        if (!contentType.includes('application/json')) {
                            return count;
                        }

                        const data = await res.json();
                        count = normalizeCount(data.count);
                        lastResolvedAt = Date.now();
                        emit();
                        return count;
                    })
                    .catch(function (err) {
                        console.error('Notification badge error:', err);
                        return count;
                    })
                    .finally(function () {
                        inFlight = null;
                    });

                return inFlight;
            }

            function subscribe(key, callback) {
                if (!key || typeof callback !== 'function') return function () { };
                subscribers.set(key, callback);
                callback(count);
                return function () {
                    subscribers.delete(key);
                };
            }

            function startPolling() {
                if (started || !hasCurrentUser) return;
                started = true;
                refresh({ force: true, reason: 'init' });
                pollTimer = window.setInterval(function () {
                    refresh({ reason: 'poll' });
                }, POLL_INTERVAL_MS);
            }

            return {
                refresh: refresh,
                subscribe: subscribe,
                startPolling: startPolling,
                getCount: function () { return count; }
            };
        })();

        document.addEventListener('DOMContentLoaded', function () {
            if (hasCurrentUser) {
                window.FOMSNotificationBadge.subscribe('layout-global-badge', renderGlobalNotificationBadge);
                window.FOMSNotificationBadge.startPolling();

                // Close panel when clicking outside
                document.addEventListener('click', function (e) {
                    const panel = document.getElementById('global-notification-panel');
                    const btn = document.getElementById('global-notification-btn');
                    if (globalNotificationOpen && panel && !panel.contains(e.target) && !btn.contains(e.target)) {
                        panel.style.display = 'none';
                        globalNotificationOpen = false;
                        btn.setAttribute('aria-expanded', 'false');
                    }
                });
            }
        });

        async function loadGlobalNotificationBadge(force) {
            if (window.FOMSNotificationBadge && typeof window.FOMSNotificationBadge.refresh === 'function') {
                return window.FOMSNotificationBadge.refresh({ force: !!force, reason: 'global' });
            }
        }

        function getErpMineOnlyCookie() {
            return window.FOMS_ERP_MINE_ONLY ? window.FOMS_ERP_MINE_ONLY.getCookie() : '';
        }
        function setErpMineOnlyCookie(on) {
            if (window.FOMS_ERP_MINE_ONLY) {
                window.FOMS_ERP_MINE_ONLY.setCookie(on);
            }
        }
        function toggleGlobalMineOnly() {
            if (window.FOMS_ERP_MINE_ONLY) {
                window.FOMS_ERP_MINE_ONLY.toggle();
            }
        }
        function updateGlobalMineOnlyButton(on) {
            if (window.FOMS_ERP_MINE_ONLY) {
                window.FOMS_ERP_MINE_ONLY.syncChrome(!!on);
            }
        }
        (function initGlobalMineOnly() {
            if (window.FOMS_ERP_MINE_ONLY) {
                window.FOMS_ERP_MINE_ONLY.syncChrome(window.FOMS_ERP_MINE_ONLY.isActive());
            }
        })();

        async function toggleGlobalNotificationPanel() {
            const panel = document.getElementById('global-notification-panel');
            const btn = document.getElementById('global-notification-btn');
            if (!panel) return;

            globalNotificationOpen = !globalNotificationOpen;
            panel.style.display = globalNotificationOpen ? 'block' : 'none';
            if (btn) {
                btn.setAttribute('aria-expanded', globalNotificationOpen ? 'true' : 'false');
            }

            if (globalNotificationOpen) {
                await loadGlobalNotifications();
            }
        }

        async function loadGlobalNotifications() {
            const list = document.getElementById('global-notification-list');
            try {
                list.innerHTML = '<div class="text-center p-4 text-muted"><div class="spinner-border spinner-border-sm text-primary" role="status"></div> 로딩 중...</div>';

                const res = await fetch('/erp/api/notifications?limit=10'); // Get latest 10
                if (!res.ok) throw new Error('API Error');

                const data = await res.json();

                if (data.notifications && data.notifications.length > 0) {
                    let html = '';
                    data.notifications.forEach(noti => {
                        const isUnread = !noti.is_read;
                        // Format time (simple)
                        const time = noti.created_at.substring(5, 16).replace('T', ' '); // MM-DD HH:MM

                        const safeType = String(noti.notification_type || '').replace(/'/g, "\\'");
                        const safeTab = String(noti.deep_tab || '').replace(/'/g, "\\'");
                        const safeEventId = String(noti.deep_event_id || '').replace(/'/g, "\\'");
                        const safeTargetNo = String(noti.deep_target_no || '').replace(/'/g, "\\'");
                        html += `
                            <div class="list-group-item notification-item ${isUnread ? 'unread' : ''}" onclick="readGlobalNotification(${noti.id}, ${noti.order_id || 'null'}, '${safeType}', '${safeTab}', '${safeEventId}', '${safeTargetNo}')">
                                <div class="d-flex w-100 justify-content-between align-items-center mb-1">
                                    <strong class="mb-0 text-truncate" style="max-width: 300px;">${escapeHtml(noti.title)}</strong>
                                    <small class="notification-time flex-shrink-0 ms-1">${time}</small>
                                </div>
                                <p class="mb-1 text-secondary small" style="word-break: break-word; white-space: normal;">${escapeHtml(noti.message).replace(/\.\s+/g, '.<br>')}</p>
                            </div>
                        `;
                    });
                    list.innerHTML = html;
                } else {
                    list.innerHTML = '<div class="text-center p-4 text-muted"><i class="far fa-bell-slash fa-2x mb-2"></i><br>알림이 없습니다.</div>';
                }
            } catch (e) {
                console.error('List error:', e);
                list.innerHTML = '<div class="text-center p-3 text-danger"><i class="fas fa-exclamation-circle"></i> 로드 실패</div>';
            }
        }

        async function readGlobalNotification(id, orderId, notificationType, deepTab, deepEventId, deepTargetNo) {
            try {
                await window.FOMSNotificationWrite.fetch(`/erp/api/notifications/${id}/read`, { method: 'POST' });
                // Refresh badge
                loadGlobalNotificationBadge(true);

                // If orderId exists, navigate by notification type
                if (orderId) {
                    if (notificationType === 'DRAWING_TRANSFERRED' || notificationType === 'DRAWING_REVISION') {
                        const tab = deepTab || (notificationType === 'DRAWING_REVISION' ? 'requests' : 'timeline');
                        let url = `/erp/drawing-workbench/${orderId}?tab=${encodeURIComponent(tab)}`;
                        if (deepEventId) url += `&event_id=${encodeURIComponent(deepEventId)}`;
                        if (deepTargetNo) url += `&target_no=${encodeURIComponent(deepTargetNo)}`;
                        window.location.href = url;
                    } else {
                        // 기본: ERP Order 탭 오픈
                        window.location.href = `/edit/${orderId}?open=erp-order`;
                    }
                } else {
                    // Just refresh list to remove unread style
                    loadGlobalNotifications();
                }
            } catch (e) {
                console.error(e);
            }
        }

        async function markAllGlobalNotificationsRead() {
            if (!confirm('모든 알림을 읽음 처리하시겠습니까?')) return;
            try {
                await window.FOMSNotificationWrite.fetch('/erp/api/notifications/read-all', { method: 'POST' });
                loadGlobalNotificationBadge(true);
                loadGlobalNotifications();
            } catch (e) {
                console.error(e);
            }
        }

        async function deleteAllGlobalNotifications() {
            if (!confirm('알림을 모두 보관하시겠습니까? 보관하면 목록에서 사라집니다.')) return;
            try {
                const res = await window.FOMSNotificationWrite.fetch('/erp/api/notifications/archive-all', { method: 'POST' });
                const data = await res.json().catch(function () { return {}; });
                if (data.success) {
                    loadGlobalNotificationBadge(true);
                    loadGlobalNotifications();
                    if (data.count != null && data.count > 0) {
                        alert(data.message || data.count + '개 알림을 보관했습니다.');
                    }
                } else {
                    alert(data.message || '보관에 실패했습니다.');
                }
            } catch (e) {
                console.error(e);
                alert('알림 보관 중 오류가 발생했습니다.');
            }
        }

        function escapeHtml(text) {
            if (!text) return '';
            return text.replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }
  window.loadGlobalNotificationBadge = loadGlobalNotificationBadge;
  window.getErpMineOnlyCookie = getErpMineOnlyCookie;
  window.setErpMineOnlyCookie = setErpMineOnlyCookie;
  window.toggleGlobalMineOnly = toggleGlobalMineOnly;
  window.updateGlobalMineOnlyButton = updateGlobalMineOnlyButton;
  window.toggleGlobalNotificationPanel = toggleGlobalNotificationPanel;
  window.loadGlobalNotifications = loadGlobalNotifications;
  window.readGlobalNotification = readGlobalNotification;
  window.markAllGlobalNotificationsRead = markAllGlobalNotificationsRead;
  window.deleteAllGlobalNotifications = deleteAllGlobalNotifications;
  window.escapeHtml = escapeHtml;
})();

