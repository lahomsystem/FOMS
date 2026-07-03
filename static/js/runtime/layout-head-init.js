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
                        // 클릭 시 한 번 더 물어보기 기능 ('닫기'는 ack 가 아님 — 창만 닫는다).
                        if (confirm('알림 내용을 충분히 확인하셨나요?\n\n[확인]을 누르시면 긴급 알람 창이 닫힙니다.')) {
                            overlay.remove();
                        }
                    });

                    // ack 버튼: notification id 가 payload 에 있을 때만 노출(P0 처리 인수).
                    const ackBtn = document.createElement('button');
                    ackBtn.id = 'urgent-overlay-ack-btn';
                    ackBtn.type = 'button';
                    ackBtn.innerHTML = '<i class="fas fa-check"></i> 확인(ack) 처리';
                    ackBtn.hidden = true;
                    ackBtn.style.cssText = 'margin-top: 16px; padding: 12px 32px; border: 2px solid rgba(255,255,255,0.85); border-radius: 50px; font-weight: bold; font-size: 1.1rem; background: rgba(255,255,255,0.18); color: #fff; cursor: pointer;';
                    ackBtn.addEventListener('click', function (e) {
                        e.preventDefault();
                        e.stopPropagation();
                        const nid = ackBtn.dataset.notificationId;
                        if (!nid || !window.FOMSNotificationWrite) return;
                        ackBtn.disabled = true;
                        window.FOMSNotificationWrite.fetch('/erp/api/notifications/' + encodeURIComponent(nid) + '/ack', {
                            method: 'POST', headers: { 'Accept': 'application/json' }
                        })
                            .then(function (r) { return r.json(); })
                            .then(function (d) {
                                if (d && d.success) {
                                    if (window.FOMSNotificationBadge && window.FOMSNotificationBadge.refresh) {
                                        window.FOMSNotificationBadge.refresh({ force: true });
                                    }
                                    overlay.remove();
                                } else {
                                    ackBtn.disabled = false;
                                    alert((d && d.message) || '확인 처리에 실패했습니다.');
                                }
                            })
                            .catch(function () { ackBtn.disabled = false; alert('확인 처리 중 오류가 발생했습니다.'); });
                    });
                    overlay.appendChild(ackBtn);

                    document.body.appendChild(overlay);
                }

                const safeTitle = data.title ? String(data.title).replace(/</g, "&lt;").replace(/>/g, "&gt;") : '🚨 긴급 알람 🚨';
                const safeMsg = data.message ? String(data.message).replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, '<br>') : '상세 내용은 알림 패널을 확인하세요.';

                overlay.querySelector('h1').innerHTML = safeTitle;
                overlay.querySelector('h3').innerHTML = safeMsg;

                // 매 이벤트마다 ack 버튼 상태 갱신: id 있으면 노출, 없으면 숨김.
                const ackBtnRef = overlay.querySelector('#urgent-overlay-ack-btn');
                if (ackBtnRef) {
                    const notifId = (data.notification_id != null) ? data.notification_id : data.id;
                    if (notifId != null && notifId !== '') {
                        ackBtnRef.dataset.notificationId = String(notifId);
                        ackBtnRef.disabled = false;
                        ackBtnRef.hidden = false;
                    } else {
                        ackBtnRef.hidden = true;
                        delete ackBtnRef.dataset.notificationId;
                    }
                }
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
