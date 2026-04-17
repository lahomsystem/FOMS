// 알림 시스템 JavaScript
        let notificationPanelOpen = false;

        function renderNotificationBadge(count) {
          const badge = document.getElementById('notification-badge');
          if (!badge) return;
          if (count > 0) {
            badge.textContent = count > 99 ? '99+' : count;
            badge.style.display = 'block';
          } else {
            badge.style.display = 'none';
          }
        }

        async function loadNotificationBadge(force) {
          if (window.FOMSNotificationBadge && typeof window.FOMSNotificationBadge.refresh === 'function') {
            return window.FOMSNotificationBadge.refresh({ force: !!force, reason: 'erp-dashboard' });
          }
        }

        async function loadNotifications() {
          const list = document.getElementById('notification-list');
          try {
            const res = await fetch('/erp/api/notifications?limit=20');
            if (!res.ok) {
              if (res.status === 429 && list) {
                list.innerHTML = '<div class="notification-empty">요청이 많아 잠시 후 다시 시도해 주세요.</div>';
              }
              return;
            }
            const contentType = res.headers.get('content-type') || '';
            if (!contentType.includes('application/json')) {
              if (list) list.innerHTML = '<div class="notification-empty">알림을 불러올 수 없습니다.</div>';
              return;
            }
            const data = await res.json();

            if (!data.success || !data.notifications || data.notifications.length === 0) {
              list.innerHTML = '<div class="notification-empty">알림이 없습니다.</div>';
              return;
            }

            const safeAttr = (v) => String(v == null ? '' : v).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            list.innerHTML = data.notifications.map(n => {
              return '<div class="notification-item ' + (n.is_read ? '' : 'notification-item--unread') + '" data-notification-id="' + n.id + '" data-order-id="' + (n.order_id || '') + '" data-notification-type="' + safeAttr(n.notification_type) + '" data-deep-tab="' + safeAttr(n.deep_tab) + '" data-deep-event-id="' + safeAttr(n.deep_event_id) + '" data-deep-target-no="' + safeAttr(n.deep_target_no) + '" role="button" tabindex="0">' +
                '<div class="notification-item__header"><span class="notification-item__title">' + escapeHtml(n.title) + '</span><span class="notification-item__time">' + formatNotificationTime(n.created_at) + '</span></div>' +
                '<div class="notification-item__message">' + escapeHtml(n.message) + '</div>' +
                '<div class="notification-item__target">' + (n.target_manager_name ? '담당: ' + escapeHtml(n.target_manager_name) : (n.target_team ? '팀: ' + escapeHtml(n.target_team) : '')) + '</div></div>';
            }).join('');
          } catch (e) {
            console.error('Load notifications error:', e);
          }
        }

        document.body.addEventListener('click', function (ev) {
          const item = ev.target.closest('#notification-list .notification-item[data-notification-id]');
          if (!item) return;
          ev.preventDefault();
          const id = parseInt(item.getAttribute('data-notification-id'), 10);
          const orderId = parseInt(item.getAttribute('data-order-id'), 10) || null;
          handleNotificationClick(id, orderId, item.getAttribute('data-notification-type') || '', item.getAttribute('data-deep-tab') || '', item.getAttribute('data-deep-event-id') || '', item.getAttribute('data-deep-target-no') || '');
        });

        function toggleNotificationPanel() {
          const panel = document.getElementById('notification-panel');
          notificationPanelOpen = !notificationPanelOpen;
          panel.style.display = notificationPanelOpen ? 'block' : 'none';

          if (notificationPanelOpen) {
            loadNotifications();
          }
        }

        async function handleNotificationClick(notificationId, orderId, notificationType, deepTab, deepEventId, deepTargetNo) {
          // 읽음 처리
          try {
            await fetch(`/erp/api/notifications/${notificationId}/read`, { method: 'POST' });
            loadNotificationBadge(true);

            // 해당 주문 상세로 이동
            if (orderId) {
              if (notificationType === 'DRAWING_TRANSFERRED' || notificationType === 'DRAWING_REVISION') {
                const tab = deepTab || (notificationType === 'DRAWING_REVISION' ? 'requests' : 'timeline');
                let url = `/erp/drawing-workbench/${orderId}?tab=${encodeURIComponent(tab)}`;
                if (deepEventId) url += `&event_id=${encodeURIComponent(deepEventId)}`;
                if (deepTargetNo) url += `&target_no=${encodeURIComponent(deepTargetNo)}`;
                window.location.href = url;
              } else {
                window.location.href = `/edit/${orderId}`;
              }
            }
          } catch (e) {
            console.error('Notification click error:', e);
          }
        }

        async function markAllNotificationsRead() {
          try {
            const res = await fetch('/erp/api/notifications/read-all', { method: 'POST' });
            const data = await res.json();
            if (data.success) {
              loadNotificationBadge(true);
              loadNotifications();
            }
          } catch (e) {
            console.error('Mark all read error:', e);
          }
        }

        function formatNotificationTime(dateStr) {
          if (!dateStr) return '';
          const date = new Date(dateStr.replace(' ', 'T'));
          const now = new Date();
          const diff = (now - date) / 1000;

          if (diff < 60) return '방금';
          if (diff < 3600) return Math.floor(diff / 60) + '분 전';
          if (diff < 86400) return Math.floor(diff / 3600) + '시간 전';
          if (diff < 604800) return Math.floor(diff / 86400) + '일 전';

          return dateStr.split(' ')[0];
        }

        function escapeHtml(text) {
          if (!text) return '';
          const div = document.createElement('div');
          div.textContent = String(text);
          return div.innerHTML;
        }

        // 페이지 로드 시 배지 업데이트
        document.addEventListener('DOMContentLoaded', function () {
          if (window.FOMSNotificationBadge && typeof window.FOMSNotificationBadge.subscribe === 'function') {
            window.FOMSNotificationBadge.subscribe('erp-dashboard-page-badge', renderNotificationBadge);
            window.FOMSNotificationBadge.startPolling();
          }
        });

        // 패널 외부 클릭 시 닫기 (ERP 레이아웃은 `notification-btn` 없이 `global-notification-*`만 있을 수 있음)
        document.addEventListener('click', function (e) {
          const panel = document.getElementById('notification-panel');
          const btn = document.getElementById('notification-btn');
          if (!notificationPanelOpen || !panel) return;
          if (panel.contains(e.target)) return;
          if (btn && btn.contains(e.target)) return;
          toggleNotificationPanel();
        });
