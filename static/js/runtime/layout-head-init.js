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
                    if (window.FOMSAlertSync && typeof window.FOMSAlertSync.resync === 'function') { window.FOMSAlertSync.resync('socket-connect'); }
                    if (window.FOMSUrgentAlert) { window.FOMSUrgentAlert.resync('socket-connect'); }
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
                onErpNotification: function (data) {
                    if (window.FOMS_DEBUG) console.log('[Global Socket.IO] ERP 알림 수신:', data);
                    refreshErpNotificationUI({ force: true, reason: 'erp-notification' });
                    if (data && data.urgent && window.FOMSUrgentAlert) {
                        // 긴급(P0) 전체화면 빨간 창 — 공용 모듈 SSOT(static/js/foms/foms-urgent-alert.js).
                        window.FOMSUrgentAlert.handle(data);
                    } else if (data && window.FOMSDrawingAlert) {
                        // 등급별 표시: interrupt=중앙 확인창(도면 수정 요청),
                        // notice=오른쪽 아래 쪽지(수정 요청 취소). 판정은 서버 payload 가 한다.
                        window.FOMSDrawingAlert.handle(data);
                    }
                }
            };
            window.__globalSocketHandlers = globalHandlers;

            globalSocket.off('connect', globalHandlers.onConnect);
            globalSocket.off('connect_error', globalHandlers.onConnectError);
            globalSocket.off('disconnect', globalHandlers.onDisconnect);
            globalSocket.off('connected', globalHandlers.onConnected);
            globalSocket.off('erp_notification', globalHandlers.onErpNotification);

            globalSocket.on('connect', globalHandlers.onConnect);
            globalSocket.on('connect_error', globalHandlers.onConnectError);
            globalSocket.on('disconnect', globalHandlers.onDisconnect);
            globalSocket.on('connected', globalHandlers.onConnected);
            globalSocket.on('erp_notification', globalHandlers.onErpNotification);

            // 전역 변수로 노출 (하위 페이지에서 동일 인스턴스 재사용)
            window.globalSocket = globalSocket;
            window.__appSocket = globalSocket;
            if (window.FOMS_DEBUG) console.log('[Global Socket.IO] ✅ 전역 Socket.IO 초기화 완료');
        })();
