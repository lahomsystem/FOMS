/**
 * Global notification badge/panel + personal briefing board (layout partial extract).
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
                await fetch(`/erp/api/notifications/${id}/read`, { method: 'POST' });
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
                await fetch('/erp/api/notifications/read-all', { method: 'POST' });
                loadGlobalNotificationBadge(true);
                loadGlobalNotifications();
            } catch (e) {
                console.error(e);
            }
        }

        async function deleteAllGlobalNotifications() {
            if (!confirm('알림을 모두 삭제하시겠습니까? 삭제된 알림은 복구할 수 없습니다.')) return;
            try {
                const res = await fetch('/erp/api/notifications/delete-all', { method: 'POST' });
                const data = await res.json().catch(function () { return {}; });
                if (data.success) {
                    loadGlobalNotificationBadge(true);
                    loadGlobalNotifications();
                    if (data.count != null && data.count > 0) {
                        alert(data.message || data.count + '개 알림을 삭제했습니다.');
                    }
                } else {
                    alert(data.message || '삭제에 실패했습니다.');
                }
            } catch (e) {
                console.error(e);
                alert('알림 삭제 중 오류가 발생했습니다.');
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

        (function personalBriefingBoard() {
            const offcanvasEl = document.getElementById('personal-briefing-offcanvas');
            const placeholderEl = document.getElementById('personal-briefing-placeholder');
            const widgetsEl = document.getElementById('personal-briefing-widgets');
            if (!offcanvasEl || !placeholderEl || !widgetsEl) return;

            function _esc(s) {
                return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
            }
            function stagePill(label) {
                return label ? '<span class="badge rounded-pill text-bg-light border" style="font-size:0.65rem">' + _esc(label) + '</span>' : '';
            }
            function orderCard(item) {
                var borderCls = item.is_urgent ? 'border-danger border-2' : 'border';
                var bg = item.is_urgent ? 'background:#fff5f5;' : '';
                var icon = item.is_urgent ? '🚨 ' : '';
                var url = item.deep_url || '/erp/dashboard';
                return '<a href="' + url + '" class="text-decoration-none d-block mb-1">' +
                    '<div class="d-flex align-items-center justify-content-between px-2 py-1 rounded ' + borderCls + '" style="background:#fff;min-height:36px;' + bg + '">' +
                    '<span class="fw-semibold text-dark" style="font-size:0.85rem">' + icon + _esc(item.customer_name) + '</span>' +
                    '<span>' + stagePill(item.stage_label || item.type_label) +
                    (item.is_urgent ? '<span class="badge bg-danger ms-1" style="font-size:0.65rem">긴급</span>' : '') +
                    '</span></div></a>';
            }
            function schedCard(item) {
                var borderCls = item.is_urgent ? 'border-danger border-2' : 'border';
                var bg = item.is_urgent ? 'background:#fff5f5;' : '';
                var typeColor = item.type === 'measurement' ? '#198754' : '#0d6efd';
                var url = item.deep_url || '/erp/dashboard';
                return '<a href="' + url + '" class="text-decoration-none d-block mb-1">' +
                    '<div class="d-flex align-items-center justify-content-between px-2 py-1 rounded ' + borderCls + '" style="background:#fff;min-height:36px;' + bg + '">' +
                    '<span class="fw-semibold text-dark" style="font-size:0.85rem">' + (item.is_urgent ? '🚨 ' : '') + _esc(item.customer_name) + '</span>' +
                    '<span>' +
                    '<span class="badge me-1" style="background:' + typeColor + ';font-size:0.65rem">' + _esc(item.type_label || '') + '</span>' +
                    (item.time ? '<span class="text-muted" style="font-size:0.72rem">' + _esc(item.time) + '</span>' : '') +
                    (item.is_urgent ? '<span class="badge bg-danger ms-1" style="font-size:0.65rem">긴급</span>' : '') +
                    '</span></div></a>';
            }
            function numWidget(icon, title, value, href, colorCls) {
                return '<div class="col-4 col-md-2"><a href="' + href + '" class="text-decoration-none">' +
                    '<div class="card h-100 text-center border shadow-sm py-1 px-0">' +
                    '<div class="fw-bold ' + colorCls + '" style="font-size:1.25rem;line-height:1.1">' + value + '</div>' +
                    '<div class="text-muted" style="font-size:0.6rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + title + '">' + icon + ' ' + title + '</div>' +
                    '</div></a></div>';
            }

            offcanvasEl.addEventListener('show.bs.offcanvas', function () {
                const btn = document.getElementById('personal-briefing-toggle');
                if (btn && btn.classList.contains('urgent-alert-active')) {
                    btn.classList.remove('urgent-alert-active');
                    const icon = btn.querySelector('i');
                    if (icon && icon.getAttribute('data-orig-class')) {
                        icon.className = icon.getAttribute('data-orig-class');
                    }
                }
            });

            offcanvasEl.addEventListener('shown.bs.offcanvas', function () {
                placeholderEl.classList.remove('d-none');
                widgetsEl.classList.add('d-none');
                widgetsEl.innerHTML = '';
                fetch('/api/personal-board/summary', { credentials: 'same-origin' })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (!data.success) {
                            placeholderEl.innerHTML = '<p class="text-danger mb-0 text-center">요약을 불러올 수 없습니다.</p>';
                            return;
                        }
                        placeholderEl.classList.add('d-none');
                        widgetsEl.classList.remove('d-none');

                        // ── 긴급 알림 배너 (최상단) ──
                        var urgentBanner = document.getElementById('urgent-banner-area');
                        var urgentList = data.urgent_notifications || [];
                        if (urgentList.length && urgentBanner) {
                            var bHtml = '';
                            urgentList.forEach(function (un) {
                                var deepHref = un.order_id ? '/erp/dashboard?focus_order=' + un.order_id : '#';
                                var typeLabel = un.notification_type === 'URGENT_MENTION' ? '긴급 멘션' : '긴급 공지';
                                bHtml += '<a href="' + deepHref + '" class="alert alert-danger d-flex align-items-center gap-2 py-2 px-3 mb-1 text-decoration-none" role="alert" style="font-size:0.85rem">' +
                                    '<i class="fas fa-exclamation-triangle"></i>' +
                                    '<span class="fw-semibold">[' + _esc(typeLabel) + ']</span> ' +
                                    '<span class="flex-grow-1 text-truncate">' + _esc(un.title) + '</span>' +
                                    (un.created_by_name ? '<small class="text-muted ms-1">by ' + _esc(un.created_by_name) + '</small>' : '') +
                                    '</a>';
                            });
                            urgentBanner.innerHTML = bHtml;
                            urgentBanner.classList.remove('d-none');
                        } else if (urgentBanner) {
                            urgentBanner.classList.add('d-none');
                            urgentBanner.innerHTML = '';
                        }

                        var u = data.urgent_inbox || {};
                        var noti = u.notifications || 0;
                        var chats = u.unread_chats || 0;
                        var ws = data.work_stream || {};
                        var workTotal = Object.values(ws).reduce(function (s, v) { return s + (v || 0); }, 0);

                        // ── 요약 숫자 위젯 클릭시 해당 대시보드 이동 ──
                        var row1 = '<div class="col-12"><div class="row g-1 mb-2">';
                        row1 += numWidget('📋', '내 업무', workTotal, '/erp/dashboard', workTotal > 0 ? 'text-primary' : 'text-muted');
                        row1 += numWidget('🔔', 'ERP알림', noti, '#', noti > 0 ? 'text-danger' : 'text-muted');
                        row1 += numWidget('💬', '채팅', chats, '/chat', chats > 0 ? 'text-warning' : 'text-muted');
                        row1 += numWidget('⚠️', '정체', data.stalled_count || 0, '/erp/dashboard', (data.stalled_count || 0) > 0 ? 'text-danger' : 'text-muted');
                        row1 += numWidget('💸', '첩구', data.settlement_alerts || 0, '/erp/completion', (data.settlement_alerts || 0) > 0 ? 'text-danger' : 'text-muted');
                        row1 += numWidget('✅', 'Task', data.pending_task_count || 0, '/erp/dashboard', (data.pending_task_count || 0) > 0 ? 'text-warning' : 'text-muted');
                        row1 += '</div></div>';
                        widgetsEl.insertAdjacentHTML('beforeend', row1);

                        // ── 단계별 업무 현황 넷지 ──
                        var wsKeys = Object.keys(ws);
                        if (wsKeys.length) {
                            var wsHtml = '<div class="col-12"><div class="border rounded p-2 mb-2" style="background:#f8f9fa">' +
                                '<div class="text-muted mb-1" style="font-size:0.7rem;font-weight:600">📊 내 팀 업무 현황</div><div class="d-flex flex-wrap gap-1">';
                            wsKeys.forEach(function (label) {
                                var cnt = ws[label];
                                var cls = cnt > 5 ? 'bg-danger' : cnt > 2 ? 'bg-warning text-dark' : 'bg-secondary';
                                wsHtml += '<span class="badge ' + cls + '">' + _esc(label) + ' <strong>' + cnt + '건</strong></span>';
                            });
                            wsHtml += '</div></div></div>';
                            widgetsEl.insertAdjacentHTML('beforeend', wsHtml);
                        }

                        // ── 최근 작업 + 일정 나란히 2콼 ──
                        var row2 = '<div class="col-12"><div class="row g-2">';

                        var recent = data.recent_work || [];
                        row2 += '<div class="col-12 col-md-6"><div class="border rounded p-2" style="min-height:80px">' +
                            '<div class="text-muted mb-1" style="font-size:0.7rem;font-weight:600">🕒 내 최근 작업 (이어하기)</div>';
                        if (recent.length) {
                            recent.forEach(function (item) { row2 += orderCard(item); });
                        } else {
                            row2 += '<p class="text-muted small mb-0">최근 작업 내역이 없습니다.</p>';
                        }
                        row2 += '</div></div>';

                        var st = data.schedule_today || [];
                        var stm = data.schedule_tomorrow || [];
                        row2 += '<div class="col-12 col-md-6"><div class="border rounded p-2" style="min-height:80px">' +
                            '<div class="text-muted mb-1" style="font-size:0.7rem;font-weight:600">📅 오늘/내일 일정</div>';
                        if (st.length || stm.length) {
                            if (st.length) {
                                row2 += '<div class="text-muted" style="font-size:0.65rem;font-weight:600">▶ 오늘</div>';
                                st.forEach(function (item) { row2 += schedCard(item); });
                            }
                            if (stm.length) {
                                row2 += '<div class="text-muted mt-1" style="font-size:0.65rem;font-weight:600">▶ 내일</div>';
                                stm.forEach(function (item) { row2 += schedCard(item); });
                            }
                        } else {
                            row2 += '<p class="text-muted small mb-0">예정된 일정이 없습니다.</p>';
                        }
                        row2 += '</div></div>';

                        row2 += '</div></div>';
                        widgetsEl.insertAdjacentHTML('beforeend', row2);
                    })
                    .catch(function () {
                        placeholderEl.innerHTML = '<p class="text-danger mb-0 text-center">요약 로드 실패.</p>';
                    });
            });
        })();
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

