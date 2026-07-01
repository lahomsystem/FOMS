/* FOMS layout-shared.bundle.js — generated; do not edit. */
/* Run: python tools/perf/build_layout_shared_bundle.py */

/* --- begin layout-head-init.js --- */
        // 전역 Socket.IO 초기화 (모든 페이지에서 알림 받을 수 있게)
        (function initGlobalSocketIO() {
            'use strict';

            if (typeof io === 'undefined') {
                const loader = document.getElementById('global-socketio-loader');
                if (loader && loader.dataset.fomsSocketLoadBound !== '1') {
                    loader.dataset.fomsSocketLoadBound = '1';
                    loader.addEventListener('load', initGlobalSocketIO, { once: true });
                    loader.addEventListener('error', function () {
                        console.error('[Global Socket.IO] ❌ Socket.IO 스크립트 로드 실패');
                    }, { once: true });
                    if (window.FOMS_DEBUG) console.log('[Global Socket.IO] defer 로드 대기 중');
                } else if (!loader) {
                    console.error('[Global Socket.IO] ❌ Socket.IO loader를 찾을 수 없습니다.');
                }
                return;
            }

            if (window.__globalSocketInitialized) return;

            if (window.FOMS_DEBUG) console.log('[Global Socket.IO] 초기화 시작');
            if (window.FOMS_DEBUG) console.log('[Global Socket.IO] current_user 존재:', true);
            if (window.FOMS_DEBUG) console.log('[Global Socket.IO] io 객체 존재:', typeof io !== 'undefined');

            // 전역 Socket.IO 싱글톤 생성/재사용 (설정은 JSON 블록에서 로드하여 JS 파서/Jinja 충돌 방지)
            var _socketConfigEl = document.getElementById('socket-config');
            var _socketConfig = _socketConfigEl ? (function () { try { return JSON.parse(_socketConfigEl.textContent); } catch (e) { return { forcePolling: false, allowPollingFallback: true }; } })() : { forcePolling: false, allowPollingFallback: true };
            const forcePollingInDebug = !!_socketConfig.forcePolling;
            const allowPollingFallback = !!_socketConfig.allowPollingFallback;
            window.getAppSocketOptions = window.getAppSocketOptions || function () {
                const options = {
                    transports: allowPollingFallback ? ['websocket', 'polling'] : ['websocket'],
                    upgrade: allowPollingFallback,
                    rememberUpgrade: true,
                    reconnection: true,
                    reconnectionAttempts: Infinity,
                    reconnectionDelay: 1000,
                    reconnectionDelayMax: 5000,
                    timeout: 30000
                };
                if (forcePollingInDebug) {
                    options.transports = ['polling'];
                    options.upgrade = false;
                }
                return options;
            };

            window.getAppSocket = window.getAppSocket || function () {
                if (window.__appSocket) return window.__appSocket;
                if (typeof io === 'undefined') return null;
                window.__appSocket = io(window.getAppSocketOptions());
                return window.__appSocket;
            };

            if (window.FOMS_DEBUG) console.log('[Global Socket.IO] Socket.IO 인스턴스 생성 중...');
            const globalSocket = window.getAppSocket();
            if (!globalSocket) {
                console.error('[Global Socket.IO] ❌ Socket.IO 인스턴스 생성 실패');
                return;
            }
            window.__globalSocketInitialized = true;

            // 연결 끊김/오류 시 stale sid 방지를 위해 싱글톤을 정리하고 새 핸드셰이크로 재연결 (RCA: ERR_CONNECTION_RESET / 400)
            function clearSocketAndScheduleReconnect(socketRef, delayMs) {
                if (window.__appSocketReconnectScheduled) return;
                delayMs = delayMs || 2000;
                if (window.FOMS_DEBUG) console.warn('[Global Socket.IO] 연결이 끊어졌습니다. ' + (delayMs / 1000) + '초 후 새 연결을 시도합니다.');
                window.__appSocketReconnectScheduled = true;
                setTimeout(function () {
                    window.__appSocketReconnectScheduled = false;
                    const s = window.__appSocket || socketRef;
                    if (s && !s.connected && typeof s.connect === 'function') {
                        try { s.connect(); } catch (e) { }
                    }
                }, delayMs);
            }

            // ERP 알림 수신 시 배지/목록을 즉시 동기화한다.
            function refreshErpNotificationUI(options) {
                options = options || {};
                const force = !!options.force;
                const reason = options.reason || 'realtime';
                if (window.FOMSNotificationBadge && typeof window.FOMSNotificationBadge.refresh === 'function') {
                    window.FOMSNotificationBadge.refresh({ force: force, reason: reason });
                } else {
                    if (typeof loadGlobalNotificationBadge === 'function') {
                        loadGlobalNotificationBadge(force);
                    }
                    if (typeof loadNotificationBadge === 'function') {
                        loadNotificationBadge(force);
                    }
                }
                const panel = document.getElementById('global-notification-panel');
                const isPanelVisible = panel && panel.style.display === 'block';
                if (isPanelVisible && typeof loadGlobalNotifications === 'function') {
                    loadGlobalNotifications();
                }
                if (isPanelVisible && typeof loadNotifications === 'function') {
                    loadNotifications();
                }
            }

            // 핸들러는 전역에 보관하여 중복 바인딩을 방지한다.
            const globalHandlers = window.__globalSocketHandlers || {
                onConnect: function () {
                    if (window.FOMS_DEBUG) console.log('[Global Socket.IO] ✅ 연결 성공');
                    if (window.FOMS_DEBUG) console.log('[Global Socket.IO] Socket ID:', globalSocket.id);
                    if (window.FOMS_DEBUG) console.log('[Global Socket.IO] 연결 상태:', globalSocket.connected);
                    refreshErpNotificationUI({ reason: 'socket-connect' });
                },
                onConnectError: function (error) {
                    console.error('[Global Socket.IO] ❌ 연결 오류:', error);
                    console.error('[Global Socket.IO] 오류 상세:', JSON.stringify(error, null, 2));
                    clearSocketAndScheduleReconnect(window.__appSocket, 2000);
                },
                onDisconnect: function (reason) {
                    if (window.FOMS_DEBUG) console.warn('[Global Socket.IO] ⚠️ 연결 해제:', reason);
                    if (reason === 'transport close' || reason === 'transport error' || reason === 'ping timeout') {
                        clearSocketAndScheduleReconnect(globalSocket, 2000);
                    }
                },
                onConnected: function (data) {
                    if (window.FOMS_DEBUG) console.log('[Global Socket.IO] 서버 연결 확인:', data);
                },
                onNewMessage: function (data) {
                    if (window.FOMS_DEBUG) console.log('[Global Socket.IO] 📨 새 메시지 수신:', data);
                    if (window.FOMS_DEBUG) console.log('[Global Socket.IO] 메시지 상세:', JSON.stringify(data, null, 2));

                    // 채팅 페이지에서는 chat.html의 핸들러가 처리한다.
                    const isChatPage = window.location.pathname === '/chat';
                    if (window.FOMS_DEBUG) console.log('[Global Socket.IO] 현재 페이지:', window.location.pathname);
                    if (window.FOMS_DEBUG) console.log('[Global Socket.IO] 채팅 페이지 여부:', isChatPage);
                    if (window.FOMS_DEBUG) console.log('[Global Socket.IO] window.currentRoomId:', window.currentRoomId);
                    if (window.FOMS_DEBUG) console.log('[Global Socket.IO] 메시지 room_id:', data.room_id);

                    if (isChatPage) {
                        if (window.FOMS_DEBUG) console.log('[Global Socket.IO] ⏭️ 채팅 페이지에서는 로컬 핸들러가 처리합니다. 전역 핸들러 무시');
                        return;
                    }

                    if (window.FOMS_DEBUG) console.log('[Global Socket.IO] ✅ 알림 표시 조건 만족 (다른 페이지)');
                    if (window.FOMS_DEBUG) console.log('[Global Socket.IO] showGlobalChatNotification 함수 존재:', typeof showGlobalChatNotification === 'function');
                    if (typeof showGlobalChatNotification === 'function') {
                        if (window.FOMS_DEBUG) console.log('[Global Socket.IO] showGlobalChatNotification 호출');
                        showGlobalChatNotification(data);
                    } else {
                        if (window.FOMS_DEBUG) console.log('[Global Socket.IO] showGlobalChatNotification 없음, 브라우저 알림 사용');
                        showBrowserNotification(data);
                    }
                },
                onErpNotification: function (data) {
                    if (window.FOMS_DEBUG) console.log('[Global Socket.IO] ERP 알림 수신:', data);
                    refreshErpNotificationUI({ force: true, reason: 'erp-notification' });
                    if (data && data.urgent) {
                        triggerUrgentBriefingAlert(data);
                    }
                }
            };
            window.__globalSocketHandlers = globalHandlers;

            // 긴급 알림 발생 시 시각적/청각적 강제 인지 함수
            window.triggerUrgentBriefingAlert = function (data) {
                console.warn('[URGENT] 긴급 이벤트 수신, 강제 인지 처리:', data);

                // 1. 청각 알림 (비프음)
                try {
                    const ctx = new (window.AudioContext || window.webkitAudioContext)();
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    osc.connect(gain);
                    gain.connect(ctx.destination);
                    osc.type = 'square';
                    osc.frequency.setValueAtTime(880, ctx.currentTime);
                    osc.frequency.exponentialRampToValueAtTime(440, ctx.currentTime + 0.1);
                    gain.gain.setValueAtTime(0.1, ctx.currentTime);
                    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
                    osc.start();
                    osc.stop(ctx.currentTime + 0.3);
                } catch (e) { console.error('Audio 처리 실패:', e); }

                // 2. 브리핑 보드 버튼 애니메이션 (붉은 점멸)
                const btn = document.getElementById('personal-briefing-toggle');
                if (btn) {
                    btn.classList.add('urgent-alert-active');
                    const icon = btn.querySelector('i');
                    if (icon) {
                        icon.setAttribute('data-orig-class', icon.className);
                        icon.className = 'fas fa-exclamation-triangle personal-briefing-chevron';
                    }
                    // 10초 후 자동 해제 (또는 열었을 때 해제되도록 함)
                    setTimeout(() => {
                        btn.classList.remove('urgent-alert-active');
                        if (icon && icon.getAttribute('data-orig-class')) {
                            icon.className = icon.getAttribute('data-orig-class');
                        }
                    }, 10000);
                }

                // 3. 거대한 긴급 알람 오버레이 (클릭 전까지 안 사라짐)
                let overlay = document.getElementById('urgent-fullscreen-overlay');
                if (!overlay) {
                    overlay = document.createElement('div');
                    overlay.id = 'urgent-fullscreen-overlay';
                    overlay.style.cssText = 'position: fixed; inset: 0; background-color: rgba(220, 53, 69, 0.95); z-index: 106000; display: flex; flex-direction: column; align-items: center; justify-content: center; backdrop-filter: blur(10px); text-align: center;';

                    const bellIcon = document.createElement('i');
                    bellIcon.className = 'fas fa-bell bell-active';
                    bellIcon.style.cssText = 'font-size: 50vh; color: #fff; text-shadow: 0 0 30px rgba(0,0,0,0.5); margin-bottom: 30px;';

                    const titleText = document.createElement('h1');
                    titleText.style.cssText = 'color: #fff; font-weight: 800; font-size: 3rem; text-shadow: 0 2px 10px rgba(0,0,0,0.3); margin-bottom: 10px; max-width: 90%; word-break: keep-all;';

                    const msgText = document.createElement('h3');
                    msgText.style.cssText = 'color: #fff; font-weight: 500; max-width: 80%; word-break: keep-all; line-height: 1.4;';

                    const clickBtn = document.createElement('button');
                    clickBtn.innerHTML = '알림 확인완료';
                    clickBtn.style.cssText = 'margin-top: 40px; padding: 15px 40px; border: 3px solid white; border-radius: 50px; font-weight: bold; font-size: 1.5rem; background: rgba(0,0,0,0.3); color: #fff; cursor: pointer; transition: all 0.2s;';
                    clickBtn.onmouseover = () => { clickBtn.style.background = 'rgba(0,0,0,0.5)'; clickBtn.style.transform = 'scale(1.05)'; };
                    clickBtn.onmouseleave = () => { clickBtn.style.background = 'rgba(0,0,0,0.3)'; clickBtn.style.transform = 'scale(1)'; };

                    overlay.appendChild(bellIcon);
                    overlay.appendChild(titleText);
                    overlay.appendChild(msgText);
                    overlay.appendChild(clickBtn);

                    clickBtn.addEventListener('click', function (e) {
                        e.preventDefault();
                        e.stopPropagation();
                        // 클릭 시 한 번 더 물어보기 기능
                        if (confirm('알림 내용을 충분히 확인하셨나요?\n\n[확인]을 누르시면 긴급 알람 창이 닫힙니다.')) {
                            overlay.remove();
                        }
                    });

                    document.body.appendChild(overlay);
                }

                const safeTitle = data.title ? String(data.title).replace(/</g, "&lt;").replace(/>/g, "&gt;") : '🚨 긴급 알람 🚨';
                const safeMsg = data.message ? String(data.message).replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, '<br>') : '상세 내용은 알림 패널을 확인하세요.';

                overlay.querySelector('h1').innerHTML = safeTitle;
                overlay.querySelector('h3').innerHTML = safeMsg;
            };

            globalSocket.off('connect', globalHandlers.onConnect);
            globalSocket.off('connect_error', globalHandlers.onConnectError);
            globalSocket.off('disconnect', globalHandlers.onDisconnect);
            globalSocket.off('connected', globalHandlers.onConnected);
            globalSocket.off('new_message', globalHandlers.onNewMessage);
            globalSocket.off('erp_notification', globalHandlers.onErpNotification);

            globalSocket.on('connect', globalHandlers.onConnect);
            globalSocket.on('connect_error', globalHandlers.onConnectError);
            globalSocket.on('disconnect', globalHandlers.onDisconnect);
            globalSocket.on('connected', globalHandlers.onConnected);
            globalSocket.on('new_message', globalHandlers.onNewMessage);
            globalSocket.on('erp_notification', globalHandlers.onErpNotification);

            // 전역 알림 표시 함수 (chat.html의 showChatNotification 로직 재사용)
            window.showGlobalChatNotification = function (messageData) {
                if (window.FOMS_DEBUG) console.log('[Global Socket.IO] 🔔 showGlobalChatNotification 호출됨:', messageData);

                // 채팅방 정보 조회
                if (window.FOMS_DEBUG) console.log('[Global Socket.IO] 채팅방 정보 조회 시작: room_id=', messageData.room_id);
                fetch(`/api/chat/rooms/${messageData.room_id}`)
                    .then(response => {
                        if (window.FOMS_DEBUG) console.log('[Global Socket.IO] 채팅방 정보 응답 상태:', response.status);
                        return response.json();
                    })
                    .then(result => {
                        if (window.FOMS_DEBUG) console.log('[Global Socket.IO] 채팅방 정보 조회 결과:', result);
                        if (result.success && result.room) {
                            if (window.FOMS_DEBUG) console.log('[Global Socket.IO] ✅ 채팅방 정보 조회 성공:', result.room);
                            // chat.html의 showChatNotification 함수가 있으면 사용
                            if (typeof showChatNotification === 'function') {
                                if (window.FOMS_DEBUG) console.log('[Global Socket.IO] showChatNotification 함수 사용');
                                showChatNotification(messageData, result.room);
                            } else {
                                if (window.FOMS_DEBUG) console.log('[Global Socket.IO] showChatNotification 없음, 간단한 알림 사용');
                                // 간단한 알림 표시
                                showSimpleNotification(messageData, result.room);
                            }
                        } else {
                            if (window.FOMS_DEBUG) console.warn('[Global Socket.IO] ⚠️ 채팅방 정보 조회 실패');
                            showSimpleNotification(messageData, { id: messageData.room_id, name: '알 수 없는 채팅방' });
                        }
                    })
                    .catch(err => {
                        console.error('[Global Socket.IO] ❌ 채팅방 정보 조회 오류:', err);
                        showSimpleNotification(messageData, { id: messageData.room_id, name: '알 수 없는 채팅방' });
                    });
            };

            // 간단한 알림 표시 (chat.html이 아닌 페이지용)
            function showSimpleNotification(messageData, roomData) {
                if (window.FOMS_DEBUG) console.log('[Global Socket.IO] showSimpleNotification 호출:', messageData, roomData);
                // 전역 알림 팝업 표시
                showGlobalNotificationPopup(messageData, roomData);
            }

            // 전역 알림 팝업 표시 함수 (모든 페이지에서 사용)
            function showGlobalNotificationPopup(messageData, roomData) {
                if (window.FOMS_DEBUG) console.log('[Global Socket.IO] showGlobalNotificationPopup 호출:', messageData, roomData);

                // 알림 컨테이너 확인
                let container = document.getElementById('chat-notification-container');
                if (!container) {
                    console.error('[Global Socket.IO] 알림 컨테이너를 찾을 수 없습니다.');
                    // 브라우저 알림으로 폴백
                    showBrowserNotification(messageData);
                    return;
                }

                // 중복 알림 방지
                const messageId = messageData.id || (messageData.room_id + '_' + (messageData.created_at || Date.now()));
                if (window.globalNotificationIds && window.globalNotificationIds.has(messageId)) {
                    if (window.FOMS_DEBUG) console.log('[Global Socket.IO] 중복 알림 스킵:', messageId);
                    return;
                }

                if (!window.globalNotificationIds) {
                    window.globalNotificationIds = new Set();
                }
                window.globalNotificationIds.add(messageId);

                // 알림 요소 생성
                const notificationId = 'global-notification-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
                const notificationEl = document.createElement('div');
                notificationEl.className = 'chat-notification';
                notificationEl.id = notificationId;

                // 메시지 내용 추출
                let messageContent = messageData.content || '(내용 없음)';
                const senderName = messageData.user_name || '알 수 없음';
                const roomName = roomData ? roomData.name : '알 수 없는 채팅방';
                const senderInitial = senderName.charAt(0).toUpperCase();

                // 시간 포맷
                let timeStr = '방금';
                if (messageData.created_at) {
                    const msgDate = new Date(messageData.created_at);
                    const now = new Date();
                    const diff = now - msgDate;
                    if (diff < 60000) {
                        timeStr = '방금';
                    } else if (diff < 3600000) {
                        timeStr = Math.floor(diff / 60000) + '분 전';
                    } else if (diff < 86400000) {
                        timeStr = Math.floor(diff / 3600000) + '시간 전';
                    } else {
                        timeStr = msgDate.toLocaleDateString('ko-KR');
                    }
                }

                // HTML 이스케이프 함수
                function escapeHtml(text) {
                    if (!text) return '';
                    const div = document.createElement('div');
                    div.textContent = text;
                    return div.innerHTML;
                }

                // 첨부파일 처리
                let attachmentHtml = '';
                if (messageData.attachments && messageData.attachments[0]) {
                    const attachment = messageData.attachments[0];
                    if (attachment.file_type === 'image' && attachment.thumbnail_url) {
                        attachmentHtml = `<img src="${attachment.thumbnail_url}" class="chat-notification-image" alt="이미지">`;
                    } else {
                        const fileIcon = attachment.file_type === 'video' ? 'fa-video' : 'fa-file';
                        attachmentHtml = `
                        <div class="chat-notification-file">
                            <i class="fas ${fileIcon} chat-notification-file-icon"></i>
                            <span class="chat-notification-file-name">${escapeHtml(attachment.filename || '파일')}</span>
                        </div>
                    `;
                    }
                }

                notificationEl.innerHTML = `
                <div class="chat-notification-header">
                    <h6 class="chat-notification-room-name">${escapeHtml(roomName)}</h6>
                    <button class="chat-notification-close" type="button" aria-label="닫기">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                <div class="chat-notification-content">
                    <div class="chat-notification-avatar">${senderInitial}</div>
                    <div class="chat-notification-body">
                        <div class="chat-notification-sender">${escapeHtml(senderName)}</div>
                        <div class="chat-notification-message">${escapeHtml(messageContent)}</div>
                        ${attachmentHtml}
                        <div class="chat-notification-time">${timeStr}</div>
                    </div>
                </div>
            `;

                // 닫기 버튼 이벤트
                const closeBtn = notificationEl.querySelector('.chat-notification-close');
                if (closeBtn) {
                    closeBtn.addEventListener('click', function (e) {
                        e.stopPropagation();
                        e.preventDefault();
                        closeGlobalNotification(notificationId, messageId);
                    });
                }

                // 클릭 이벤트: 채팅 페이지로 이동 (room_id 파라미터 포함)
                notificationEl.addEventListener('click', function (e) {
                    if (!e.target.classList.contains('chat-notification-close') &&
                        !e.target.closest('.chat-notification-close')) {
                        closeGlobalNotification(notificationId, messageId);
                        // 채팅 페이지로 이동 (room_id 파라미터 포함)
                        const roomId = roomData ? roomData.id : messageData.room_id;
                        if (roomId) {
                            window.location.href = `/chat?room_id=${roomId}`;
                        } else {
                            window.location.href = '/chat';
                        }
                    }
                });

                // 컨테이너에 추가
                container.appendChild(notificationEl);

                // 자동 닫기 (5초 후)
                setTimeout(() => {
                    closeGlobalNotification(notificationId, messageId);
                }, 5000);
            }

            // 전역 알림 닫기 함수
            function closeGlobalNotification(notificationId, messageId) {
                const notificationEl = document.getElementById(notificationId);
                if (notificationEl) {
                    notificationEl.style.animation = 'slideOutRight 0.3s ease-out';
                    setTimeout(() => {
                        notificationEl.remove();
                        if (messageId && window.globalNotificationIds) {
                            window.globalNotificationIds.delete(messageId);
                        }
                    }, 300);
                }
            }

            // 브라우저 알림
            function showBrowserNotification(messageData) {
                if (window.FOMS_DEBUG) console.log('[Global Socket.IO] showBrowserNotification 호출:', messageData);
                if (window.FOMS_DEBUG) console.log('[Global Socket.IO] Notification API 지원:', 'Notification' in window);
                if (window.FOMS_DEBUG) console.log('[Global Socket.IO] Notification 권한:', Notification.permission);

                if ('Notification' in window) {
                    if (Notification.permission === 'granted') {
                        if (window.FOMS_DEBUG) console.log('[Global Socket.IO] ✅ 브라우저 알림 표시');
                        const notification = new Notification(`${messageData.user_name || '알 수 없음'}님의 메시지`, {
                            body: messageData.content || '새 메시지가 도착했습니다.',
                            tag: `chat_${messageData.room_id}`,
                            requireInteraction: false
                        });
                        if (window.FOMS_DEBUG) console.log('[Global Socket.IO] 브라우저 알림 생성됨:', notification);
                    } else if (Notification.permission === 'default') {
                        if (window.FOMS_DEBUG) console.log('[Global Socket.IO] 알림 권한 요청');
                        Notification.requestPermission().then(permission => {
                            if (window.FOMS_DEBUG) console.log('[Global Socket.IO] 알림 권한 결과:', permission);
                            if (permission === 'granted') {
                                showBrowserNotification(messageData);
                            }
                        });
                    } else {
                        if (window.FOMS_DEBUG) console.warn('[Global Socket.IO] ⚠️ 알림 권한이 거부됨');
                    }
                } else {
                    if (window.FOMS_DEBUG) console.warn('[Global Socket.IO] ⚠️ 브라우저가 Notification API를 지원하지 않음');
                }
            }

            // 전역 변수로 노출 (하위 페이지에서 동일 인스턴스 재사용)
            window.globalSocket = globalSocket;
            window.__appSocket = globalSocket;
            if (window.FOMS_DEBUG) console.log('[Global Socket.IO] ✅ 전역 Socket.IO 초기화 완료');
        })();
/* --- end layout-head-init.js --- */

/* --- begin blueprint-viewer-global.js --- */
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
/* --- end blueprint-viewer-global.js --- */

/* --- begin layout-scripts-core.js --- */
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
/* --- end layout-scripts-core.js --- */

/* --- begin layout-scripts-chat.js --- */
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
/* --- end layout-scripts-chat.js --- */

