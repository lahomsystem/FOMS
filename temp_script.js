// 설정 정보를 DOM에서 가져오기
const chatContainer = document.querySelector('.chat-sidebar-card');
const socketioAvailable = chatContainer ? chatContainer.getAttribute('data-socketio-available') === 'true' : false;
const userIdFromData = chatContainer ? parseInt(chatContainer.getAttribute('data-user-id') || '0', 10) : 0;

let socket = null;
let currentRoomId = null;
let currentUserId = userIdFromData;
window.SOCKETIO_AVAILABLE = window.SOCKETIO_AVAILABLE || socketioAvailable;


// 새 메시지 처리 함수 (통합)
function handleNewMessage(data) {
    console.log('새 메시지 수신:', data);
    
    if (data.room_id == currentRoomId) {
        // 중복 방지: 이미 존재하는 메시지 ID인지 확인 (이중 방어)
        if (data.id) {
            const container = document.getElementById('messages-container');
            const existingMessage = container.querySelector(`[data-message-id="${data.id}"]`);
            if (existingMessage) {
                console.log('[handleNewMessage] 중복 메시지 스킵:', data.id);
                return; // 이미 존재하는 메시지는 추가하지 않음
            }
        }
        
        // 현재 채팅방이면 메시지 추가
        appendMessage(data);
        scrollToBottom();
        
        // 새 메시지 수신 시 읽음 상태 업데이트
        if (socket && socket.connected) {
            socket.emit('mark_read', { room_id: currentRoomId });
        } else {
            fetch(`/api/chat/rooms/${currentRoomId}/mark-read`, {
                method: 'POST'
            }).catch(err => console.error('읽음 상태 업데이트 오류:', err));
        }
    } else {
        // 다른 채팅방이면 알림 표시
        if (data.user_id != currentUserId) {
            fetch(`/api/chat/rooms/${data.room_id}`)
                .then(response => response.json())
                .then(result => {
                    if (result.success && result.room) {
                        showChatNotification(data, result.room);
                    } else {
                        showChatNotification(data, { id: data.room_id, name: '알 수 없는 채팅방' });
                    }
                })
                .catch(err => {
                    console.error('채팅방 정보 조회 오류:', err);
                    showChatNotification(data, { id: data.room_id, name: '알 수 없는 채팅방' });
                });
        }
    }
}

// Socket.IO 초기화 함수
function initializeSocketIO() {
    try {
        if (typeof io === 'undefined') {
            console.error('Socket.IO가 로드되지 않았습니다.');
            return;
        }

        // layout의 싱글톤 소켓을 재사용 (페이지당 소켓 1개 보장)
        if (typeof window.getAppSocket === 'function') {
            socket = window.getAppSocket();
        } else if (window.globalSocket) {
            socket = window.globalSocket;
        } else {
            // fallback: layout 스크립트가 없는 예외 상황에서만 직접 생성
            const fallbackOptions = (typeof window.getAppSocketOptions === 'function')
                ? window.getAppSocketOptions()
                : {
                    transports: ['websocket', 'polling'],
                    upgrade: true,
                    reconnection: true,
                    reconnectionAttempts: Infinity,
                    reconnectionDelay: 1000,
                    reconnectionDelayMax: 5000,
                    timeout: 20000
                };
            socket = io(fallbackOptions);
            window.globalSocket = socket;
            window.__appSocket = socket;
        }

        if (!socket) {
            console.error('Socket.IO 인스턴스를 가져오지 못했습니다.');
            return;
        }

        // 핸들러는 idempotent하게 바인딩해서 중복 등록을 방지
        const handlers = window.__chatSocketHandlers || {
            onConnect: function() {
                console.log('Socket.IO 연결 성공');
                loadRooms();
            },
            onConnectError: function(error) {
                console.error('Socket.IO 연결 오류:', error);
            },
            onDisconnect: function(reason) {
                console.log('Socket.IO 연결 해제:', reason);
                if (reason === 'io server disconnect' && socket) {
                    socket.connect();
                }
            },
            onReconnect: function(attemptNumber) {
                console.log('Socket.IO 재연결 성공:', attemptNumber);
            },
            onNewMessage: function(data) {
                handleNewMessage(data);
            },
            onMessageRead: function(data) {
                if (data.room_id == currentRoomId) {
                    console.log('읽음 상태 업데이트:', data);
                }
            },
            onUserTyping: function(data) {
                if (data.room_id == currentRoomId && data.user_id != currentUserId) {
                    showTypingIndicator(data.user_id, data.is_typing);
                }
            }
        };
        window.__chatSocketHandlers = handlers;

        socket.off('connect', handlers.onConnect);
        socket.off('connect_error', handlers.onConnectError);
        socket.off('disconnect', handlers.onDisconnect);
        socket.off('reconnect', handlers.onReconnect);
        socket.off('new_message', handlers.onNewMessage);
        socket.off('message_read', handlers.onMessageRead);
        socket.off('user_typing', handlers.onUserTyping);

        socket.on('connect', handlers.onConnect);
        socket.on('connect_error', handlers.onConnectError);
        socket.on('disconnect', handlers.onDisconnect);
        socket.on('reconnect', handlers.onReconnect);
        socket.on('new_message', handlers.onNewMessage);
        socket.on('message_read', handlers.onMessageRead);
        socket.on('user_typing', handlers.onUserTyping);

        // 이미 연결된 상태에서 진입하면 즉시 초기 데이터 로드
        if (socket.connected) {
            loadRooms();
        }

    } catch (error) {
        console.error('Socket.IO 초기화 오류:', error);
    }
}
// ============================================
// 이미지 확대/축소 기능 (Lightbox) - 전역 스코프
// ============================================
let imageZoom = {
    scale: 1,
    minScale: 0.5,
    maxScale: 5,
    translateX: 0,
    translateY: 0,
    lastTranslateX: 0,
    lastTranslateY: 0
};

function openImageLightbox(imageUrl, optionalKey) {
    const lightbox = document.getElementById('image-lightbox');
    const img = document.getElementById('image-lightbox-img');
    
    if (!lightbox || !img) {
        console.error('라이트박스 요소를 찾을 수 없습니다.');
        return;
    }
    
    var url = (typeof imageUrl === 'string') ? imageUrl : (imageUrl && (imageUrl.dataset && imageUrl.dataset.url) || imageUrl.src);
    var key = optionalKey || (imageUrl && imageUrl.dataset && imageUrl.dataset.key) || null;
    if (!url) return;
    
    // 이미지 로드 후 transform 적용
    img.onload = function() {
        imageZoom.scale = 1;
        imageZoom.translateX = 0;
        imageZoom.translateY = 0;
        imageZoom.lastTranslateX = 0;
        imageZoom.lastTranslateY = 0;
        updateImageTransform();
    };
    
    if (img.complete) {
        img.onload();
    }
    
    img.src = url;
    lightbox.classList.add('active');
    
    if (key) {
        var path = String(key).split('/').map(function(s) { return encodeURIComponent(s); }).join('/');
        fetch('/api/files/presigned-urls/' + path).then(function(r) { return r.json(); }).then(function(data) {
            if (data.success && data.view_url) img.src = data.view_url;
        }).catch(function() {});
    }
    
    document.addEventListener('keydown', handleLightboxKeydown);
}

function closeImageLightbox(event) {
    // 이벤트가 없거나 배경/닫기 버튼을 클릭한 경우
    if (!event || 
        event.target.id === 'image-lightbox' || 
        event.target.id === 'image-lightbox-close' || 
        event.target.closest('.image-lightbox-controls')) {
        
        const lightbox = document.getElementById('image-lightbox');
        if (lightbox) {
            lightbox.classList.remove('active');
        }
        document.removeEventListener('keydown', handleLightboxKeydown);
    }
}

function handleLightboxKeydown(e) {
    if (e.key === 'Escape') {
        closeImageLightbox(e);
    }
}

function resetImageZoom() {
    imageZoom.scale = 1;
    imageZoom.translateX = 0;
    imageZoom.translateY = 0;
    imageZoom.lastTranslateX = 0;
    imageZoom.lastTranslateY = 0;
    updateImageTransform();
}

function updateImageTransform() {
    const content = document.getElementById('image-lightbox-content');
    if (content) {
        content.style.transform = `translate(${imageZoom.translateX}px, ${imageZoom.translateY}px) scale(${imageZoom.scale})`;
    }
}
// 유틸리티 함수 (다른 partial에서 공통 사용)
// 백틱도 &#96;로 이스케이프하여 템플릿 리터럴 안에서 삽입 시 구문 오류 방지
function escapeHtml(text) {
    if (text == null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML.replace(/`/g, '&#96;');
}
/** onclick 등 단일 따옴표 JS 문자열·템플릿 리터럴 안에 넣을 때 사용 (작은따옴표·백슬래시·백틱 이스케이프) */
function escapeJsString(s) {
    if (s == null || s === undefined) return '';
    return String(s)
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'")
        .replace(/`/g, '\\`');
}

/** HTML 속성(쌍따옴표 기반) 안에 동적 문자열을 안전하게 삽입하기 위한 이스케이프 함수 */
function safeAttr(str) {
    if (str == null || str === undefined) return '';
    const d = document.createElement('div');
    d.textContent = String(str);
    return d.innerHTML.replace(/"/g, '&quot;');
}

function formatDate(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);
    
    if (minutes < 1) return '방금';
    if (minutes < 60) return `${minutes}분 전`;
    if (hours < 24) return `${hours}시간 전`;
    if (days < 7) return `${days}일 전`;
    
    return date.toLocaleDateString('ko-KR');
}

function formatDateTime(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
}

function scrollToBottom() {
    const container = document.getElementById('messages-container');
    if (container) container.scrollTop = container.scrollHeight;
}

/** 메시지 영역(#messages-container) 안에서만 스크롤하여 요소가 보이게 함. 페이지 스크롤 방지 */
function scrollMessageIntoView(element) {
    const container = document.getElementById('messages-container');
    if (!container || !element) return;
    const elTop = element.offsetTop;
    const elH = element.offsetHeight;
    const cH = container.clientHeight;
    container.scrollTop = Math.max(0, elTop - Math.floor(cH / 2) + Math.floor(elH / 2));
}
// ============================================
// 채팅 알림 팝업 관리 (채널톡 스타일)
// ============================================
let notificationStack = [];
const MAX_NOTIFICATIONS = 5;
const NOTIFICATION_DURATION = 5000; // 5초
let notificationIds = new Set(); // 중복 방지용

function showChatNotification(messageData, roomData) {
    // 현재 채팅방이면 알림 표시 안 함
    if (messageData.room_id == currentRoomId) {
        return;
    }
    
    // 자신이 보낸 메시지는 알림 표시 안 함
    if (messageData.user_id == currentUserId) {
        return;
    }
    
    // 중복 알림 방지: 같은 메시지 ID는 한 번만 표시
    const messageId = messageData.id || (messageData.room_id + '_' + messageData.created_at);
    if (notificationIds.has(messageId)) {
        return;
    }
    notificationIds.add(messageId);
    
    // 알림 스택에 추가
    const notificationId = 'notification-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
    const notification = {
        id: notificationId,
        message: messageData,
        room: roomData,
        timestamp: new Date(),
        messageId: messageId
    };
    
    notificationStack.push(notification);
    
    // 최대 개수 초과 시 오래된 알림 제거
    if (notificationStack.length > MAX_NOTIFICATIONS) {
        const oldest = notificationStack.shift();
        closeNotification(oldest.id);
        if (oldest.messageId) {
            notificationIds.delete(oldest.messageId);
        }
    }
    
    // 알림 DOM 생성
    const container = document.getElementById('chat-notification-container');
    if (!container) {
        console.error('알림 컨테이너를 찾을 수 없습니다.');
        return;
    }
    
    const notificationEl = createNotificationElement(notification);
    container.appendChild(notificationEl);
    
    // 자동 닫기 타이머
    const autoCloseTimer = setTimeout(() => {
        closeNotification(notificationId);
        if (messageId) {
            notificationIds.delete(messageId);
        }
    }, NOTIFICATION_DURATION);
    
    // 알림 요소에 타이머 ID 저장
    notificationEl.dataset.timerId = autoCloseTimer;
    
    // 클릭 이벤트: 해당 채팅방으로 이동
    notificationEl.addEventListener('click', function(e) {
        if (!e.target.classList.contains('chat-notification-close') && 
            !e.target.closest('.chat-notification-close')) {
            closeNotification(notificationId);
            if (messageId) {
                notificationIds.delete(messageId);
            }
            if (roomData && roomData.id) {
                selectRoom(roomData.id);
                window.focus();
            }
        }
    });
}

// showChatNotification 함수를 전역으로 노출 (layout.html에서 사용 가능)
window.showChatNotification = showChatNotification;

function createNotificationElement(notification) {
    const { message, room } = notification;
    const senderName = message.user_name || '알 수 없음';
    const roomName = room ? room.name : '알 수 없는 채팅방';
    const senderInitial = senderName.charAt(0).toUpperCase();
    
    // 메시지 내용 추출
    let messageContent = '';
    let hasAttachment = false;
    
    if (message.message_type === 'text') {
        messageContent = escapeHtml(message.content || '(메시지 없음)');
    } else if (message.attachments && message.attachments.length > 0) {
        const attachment = message.attachments[0];
        hasAttachment = true;
        if (attachment.file_type === 'image') {
            messageContent = '📷 이미지';
        } else if (attachment.file_type === 'video') {
            messageContent = '📥 동영상';
        } else {
            messageContent = '📎 ' + escapeHtml(attachment.filename || '파일');
        }
    } else {
        messageContent = '(내용 없음)';
    }
    
    // 시간 포맷
    const timeStr = formatNotificationTime(message.created_at);
    
    const notificationEl = document.createElement('div');
    notificationEl.className = 'chat-notification';
    notificationEl.id = notification.id;
    notificationEl.dataset.roomId = message.room_id;
    
    let attachmentHtml = '';
    if (hasAttachment && message.attachments && message.attachments[0]) {
        const attachment = message.attachments[0];
        if (attachment.file_type === 'image' && attachment.thumbnail_url) {
            attachmentHtml = `<img src="${escapeHtml(attachment.thumbnail_url || '')}" class="chat-notification-image" alt="이미지">`;
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
                <div class="chat-notification-message">${messageContent}</div>
                ${attachmentHtml}
                <div class="chat-notification-time">${timeStr}</div>
            </div>
        </div>
    `;
    
    // 닫기 버튼 이벤트 핸들러 추가 (인라인 onclick 대신)
    const closeBtn = notificationEl.querySelector('.chat-notification-close');
    if (closeBtn) {
        closeBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            e.preventDefault();
            closeNotification(notification.id);
            if (notification.messageId) {
                notificationIds.delete(notification.messageId);
            }
        });
    }
    
    return notificationEl;
}

function closeNotification(notificationId) {
    const notificationEl = document.getElementById(notificationId);
    if (!notificationEl) {
        return;
    }
    
    // 타이머 취소
    const timerId = notificationEl.dataset.timerId;
    if (timerId) {
        clearTimeout(parseInt(timerId));
    }
    
    // messageId 제거
    const notification = notificationStack.find(n => n.id === notificationId);
    if (notification && notification.messageId) {
        notificationIds.delete(notification.messageId);
    }
    
    // 닫기 애니메이션
    notificationEl.classList.add('closing');
    
    setTimeout(() => {
        notificationEl.remove();
        // 스택에서도 제거
        notificationStack = notificationStack.filter(n => n.id !== notificationId);
    }, 300);
}

function formatNotificationTime(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    
    if (minutes < 1) return '방금 전';
    if (minutes < 60) return `${minutes}분 전`;
    if (hours < 24) return `${hours}시간 전`;
    
    return date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
}
// textarea 자동 높이 조절 함수 (채널톡 스타일)
function autoResizeTextarea(textarea) {
    if (!textarea) return;
    // 높이 초기화
    textarea.style.height = 'auto';
    // scrollHeight로 내용 높이 계산
    const scrollHeight = textarea.scrollHeight;
    // 최소 38px, 최대 120px로 제한
    const newHeight = Math.max(38, Math.min(scrollHeight, 120));
    textarea.style.height = newHeight + 'px';
}

// 채팅 페이지 높이 동적 계산 (반응형)
function adjustChatPageHeight() {
    const header = document.querySelector('header');
    const nav = document.querySelector('nav.navbar');
    
    if (header && nav) {
        const headerHeight = header.offsetHeight || 0;
        const navHeight = nav.offsetHeight || 0;
        const totalHeight = headerHeight + navHeight;
        
        // 바깥 container-fluid(header 포함)만 높이 제한 — 채팅 입력창 하단 고정을 위한 루트
        const outerContainer = document.querySelector('body .container-fluid:has(header)');
        if (outerContainer && document.querySelector('.chat-page-wrapper')) {
            outerContainer.style.height = `calc(100vh - ${totalHeight}px)`;
            outerContainer.style.maxHeight = `calc(100vh - ${totalHeight}px)`;
            outerContainer.style.overflow = 'hidden';
            outerContainer.style.display = 'flex';
            outerContainer.style.flexDirection = 'column';
        }
    }
}
// Socket.IO 연결 (외부 scripts.js 지연 로드 시 이미 loaded일 수 있음)
(function runWhenReady() {
    function init() {
    // 채팅 페이지 높이 조절
    adjustChatPageHeight();
    
    // 리사이즈 이벤트 리스너
    let resizeTimer;
    window.addEventListener('resize', function() {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function() {
            adjustChatPageHeight();
        }, 100);
    });
    
    // textarea 자동 높이 조절
    const messageInput = document.getElementById('message-input');
    if (messageInput) {
        // 입력 시 자동 높이 조절
        messageInput.addEventListener('input', function() {
            autoResizeTextarea(this);
        });
        
        // 포커스 시 초기 높이 설정
        messageInput.addEventListener('focus', function() {
            autoResizeTextarea(this);
        });
        
        // 초기 높이 설정
        autoResizeTextarea(messageInput);
    }
    
    // 네비게이션 바 높이 계산 및 sticky-top 요소 위치 조정
    function adjustStickyPositions() {
        // 채팅 페이지에서는 sticky positioning을 사용하지 않으므로 이 함수 비활성화
        // 채팅 페이지인지 확인
        const isChatPage = document.querySelector('.chat-page-wrapper') !== null;
        if (isChatPage) {
            // 채팅 페이지에서는 이 함수를 실행하지 않음
            return;
        }
        
        const header = document.querySelector('header');
        const nav = document.querySelector('nav.navbar');
        
        if (header && nav) {
            const headerHeight = header.offsetHeight;
            const navHeight = nav.offsetHeight;
            const totalHeight = headerHeight + navHeight + 20; // 여유 공간 20px
            
            // sticky-top 요소들 위치 조정
            const stickyCards = document.querySelectorAll('[data-sticky-top="true"]');
            stickyCards.forEach(card => {
                card.style.top = totalHeight + 'px';
                card.style.maxHeight = `calc(100vh - ${totalHeight + 40}px)`;
            });
            
            // min-height가 필요한 요소들 조정
            const minHeightCards = document.querySelectorAll('[data-min-height="true"]');
            minHeightCards.forEach(card => {
                card.style.minHeight = `calc(100vh - ${totalHeight + 40}px)`;
            });
        } else {
            // 네비게이션 바가 없는 경우 기본값 사용
            const stickyCards = document.querySelectorAll('[data-sticky-top="true"]');
            stickyCards.forEach(card => {
                card.style.top = '20px';
                card.style.maxHeight = 'calc(100vh - 40px)';
            });
            
            const minHeightCards = document.querySelectorAll('[data-min-height="true"]');
            minHeightCards.forEach(card => {
                card.style.minHeight = 'calc(100vh - 40px)';
            });
        }
    }
    
    // 초기 위치 조정
    adjustStickyPositions();
    
    // 윈도우 리사이즈 시 다시 조정
    window.addEventListener('resize', adjustStickyPositions);
    
    // Socket.IO 초기화
    if (socketioAvailable) {
        // Socket.IO 스크립트가 로드될 때까지 대기
        if (typeof io !== 'undefined') {
            initializeSocketIO();
        } else {
            // 스크립트 로드를 기다림
            let attempts = 0;
            const checkIO = setInterval(function() {
                attempts++;
                if (typeof io !== 'undefined') {
                    clearInterval(checkIO);
                    initializeSocketIO();
                } else if (attempts >= 50) {
                    clearInterval(checkIO);
                    console.error('Socket.IO 스크립트를 로드할 수 없습니다.');
                    loadRooms();
                }
            }, 100);
        }
    } else {
        loadRooms();
    }
    
    
    // Enter 키로 메시지 전송
    const msgInput = document.getElementById('message-input');
    if (msgInput) {
        msgInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    }
    
    // 파일 선택 이벤트
    const fileInput = document.getElementById('file-input');
    if (fileInput) {
        fileInput.addEventListener('change', function(e) {
            handleFileSelect(e.target.files);
        });
    }
    
    // 채팅방 목록 클릭 위임 (Phase 2.1: 인라인 onclick 제거)
    const roomsListEl = document.getElementById('rooms-list');
    if (roomsListEl) {
        roomsListEl.addEventListener('click', function(e) {
            const item = e.target.closest('.chat-room-item[data-room-id]');
            if (item) {
                const id = parseInt(item.getAttribute('data-room-id'), 10);
                if (!isNaN(id) && typeof selectRoom === 'function') selectRoom(id);
            }
        });
        roomsListEl.addEventListener('keydown', function(e) {
            if (e.key !== 'Enter' && e.key !== ' ') return;
            const item = e.target.closest('.chat-room-item[data-room-id]');
            if (item) {
                e.preventDefault();
                const id = parseInt(item.getAttribute('data-room-id'), 10);
                if (!isNaN(id) && typeof selectRoom === 'function') selectRoom(id);
            }
        });
    }
    
    // 주문 위젯 위임 (Phase 2.2.1: change, focusout, click)
    const orderWidgetEl = document.getElementById('chat-order-widget-container');
    if (orderWidgetEl) {
        orderWidgetEl.addEventListener('change', function(e) {
            const el = e.target;
            const orderId = parseInt(el.getAttribute('data-order-id'), 10);
            if (isNaN(orderId)) return;
            if (el.classList.contains('status-dropdown') && el.getAttribute('data-field') === 'status') {
                if (typeof updateOrderStatus === 'function') updateOrderStatus(orderId, el.value);
                if (typeof applyStatusColor === 'function') applyStatusColor(el);
            } else if (el.getAttribute('data-field') === 'scheduled_date') {
                if (typeof updateOrderField === 'function') updateOrderField(orderId, 'scheduled_date', el.value);
            }
        });
        orderWidgetEl.addEventListener('focusout', function(e) {
            const el = e.target;
            if (el.getAttribute('data-field') !== 'manager_name') return;
            const orderId = parseInt(el.getAttribute('data-order-id'), 10);
            if (!isNaN(orderId) && typeof updateOrderField === 'function') updateOrderField(orderId, 'manager_name', el.value);
        });
        orderWidgetEl.addEventListener('click', function(e) {
            const btn = e.target.closest('[data-action="open-blueprint"]');
            if (!btn) return;
            const orderId = parseInt(btn.getAttribute('data-order-id'), 10);
            if (!isNaN(orderId) && typeof openBlueprintViewer === 'function') openBlueprintViewer(orderId);
        });
    }
    
    // 메시지 다운로드 버튼 위임 (Phase 2.4)
    const messagesContainer = document.getElementById('messages-container');
    if (messagesContainer) {
        messagesContainer.addEventListener('click', function(e) {
            const btn = e.target.closest('[data-action="download-chat-image"]');
            if (btn) {
                e.preventDefault();
                var key = btn.getAttribute('data-storage-key') || '';
                var filename = btn.getAttribute('data-filename') || '';
                if (typeof downloadChatImage === 'function') downloadChatImage(key, filename, e);
                return;
            }
            const allBtn = e.target.closest('[data-action="download-all-images"]');
            if (allBtn) {
                e.preventDefault();
                var mid = parseInt(allBtn.getAttribute('data-message-id'), 10);
                if (!isNaN(mid) && typeof downloadAllChatImages === 'function') downloadAllChatImages(mid, e);
            }
        });
    }
    
    // 전역 검색 결과 클릭 위임 (Phase 2.5)
    const globalSearchResults = document.getElementById('global-search-results');
    if (globalSearchResults) {
        globalSearchResults.addEventListener('click', function(e) {
            const row = e.target.closest('.global-search-row[data-action]');
            if (!row) return;
            const action = row.getAttribute('data-action');
            const roomId = parseInt(row.getAttribute('data-room-id'), 10);
            if (isNaN(roomId)) return;
            if (action === 'search-result-message' && typeof selectRoomAndHighlight === 'function') {
                var mid = parseInt(row.getAttribute('data-message-id'), 10);
                selectRoomAndHighlight(roomId, isNaN(mid) ? 0 : mid);
            } else if (action === 'search-result-room' && typeof selectRoom === 'function') {
                selectRoom(roomId);
            }
        });
    }
    
    // 주문 검색/연결 모달 행 클릭 위임 (Phase 2.3)
    document.addEventListener('click', function(e) {
        const row = e.target.closest('.order-search-row[data-action]');
        if (row) {
            const action = row.getAttribute('data-action');
            const orderId = parseInt(row.getAttribute('data-order-id'), 10);
            if (isNaN(orderId)) return;
            if (action === 'select-order' && typeof selectOrderForRoom === 'function') {
                const customerName = row.getAttribute('data-customer-name') || '';
                const product = row.getAttribute('data-product') || '';
                selectOrderForRoom(orderId, customerName, product);
            } else if (action === 'connect-order' && typeof connectOrderToRoom === 'function') {
                connectOrderToRoom(orderId, '');
            }
            return;
        }
        const btn = e.target.closest('#chat-header [data-action]');
        if (!btn) return;
        const action = btn.getAttribute('data-action');
        const roomId = parseInt(btn.getAttribute('data-room-id'), 10);
        if (action === 'toggle-search' && typeof toggleSearch === 'function') { toggleSearch(); return; }
        if (action === 'back-to-list' && typeof goBackToChatList === 'function') { goBackToChatList(); return; }
        if (isNaN(roomId)) return;
        if (action === 'edit-room-name' && typeof showEditRoomNameModal === 'function') {
            const name = btn.getAttribute('data-room-name') || '';
            showEditRoomNameModal(roomId, name);
        } else if (action === 'connect-order' && typeof showConnectOrderModal === 'function') { showConnectOrderModal(roomId);
        } else if (action === 'disconnect-order' && typeof disconnectOrder === 'function') { disconnectOrder(roomId);
        } else if (action === 'invite-member' && typeof showInviteMemberModal === 'function') { showInviteMemberModal(roomId);
        } else if (action === 'delete-room' && typeof deleteRoom === 'function') { deleteRoom(roomId);
        }
    });
    
    // 마우스 휠로 확대/축소 (라이트박스가 활성화된 경우에만)
    const lightbox = document.getElementById('image-lightbox');
    if (lightbox) {
        lightbox.addEventListener('wheel', function(e) {
            // 라이트박스가 활성화되어 있는지 확인
            if (!lightbox.classList.contains('active')) {
                return;
            }
            
            e.preventDefault();
            e.stopPropagation();
            
            const delta = e.deltaY > 0 ? -0.1 : 0.1;
            const newScale = Math.max(imageZoom.minScale, 
                                     Math.min(imageZoom.maxScale, imageZoom.scale + delta));
            
            // 마우스 위치를 중심으로 확대/축소
            const rect = lightbox.getBoundingClientRect();
            const mouseX = e.clientX - rect.left - rect.width / 2;
            const mouseY = e.clientY - rect.top - rect.height / 2;
            
            const scaleChange = newScale / imageZoom.scale;
            imageZoom.translateX = imageZoom.translateX * scaleChange + mouseX * (1 - scaleChange);
            imageZoom.translateY = imageZoom.translateY * scaleChange + mouseY * (1 - scaleChange);
            
            imageZoom.scale = newScale;
            updateImageTransform();
        }, { passive: false });
    }
    
    // 이미지 드래그로 이동
    const lightboxContent = document.getElementById('image-lightbox-content');
    if (lightboxContent && lightbox) {
        let isDragging = false;
        let dragStartX = 0;
        let dragStartY = 0;
        let startTranslateX = 0;
        let startTranslateY = 0;
        
        lightboxContent.addEventListener('mousedown', function(e) {
            if (e.button === 0 && lightbox.classList.contains('active')) { // 왼쪽 마우스 버튼만
                isDragging = true;
                dragStartX = e.clientX;
                dragStartY = e.clientY;
                startTranslateX = imageZoom.translateX;
                startTranslateY = imageZoom.translateY;
                lightboxContent.style.cursor = 'grabbing';
                e.preventDefault();
            }
        });
        
        document.addEventListener('mousemove', function(e) {
            if (isDragging && lightbox.classList.contains('active')) {
                const deltaX = e.clientX - dragStartX;
                const deltaY = e.clientY - dragStartY;
                imageZoom.translateX = startTranslateX + deltaX;
                imageZoom.translateY = startTranslateY + deltaY;
                updateImageTransform();
            }
        });
        
        document.addEventListener('mouseup', function(e) {
            if (isDragging) {
                isDragging = false;
                lightboxContent.style.cursor = 'grab';
            }
        });
        
        // 터치 제스처 지원 (모바일)
        let touchStartDistance = 0;
        let touchStartScale = 1;
        let touchStartX = 0;
        let touchStartY = 0;
        
        lightboxContent.addEventListener('touchstart', function(e) {
            if (!lightbox.classList.contains('active')) return;
            
            if (e.touches.length === 1) {
                // 단일 터치: 이동
                touchStartX = e.touches[0].clientX;
                touchStartY = e.touches[0].clientY;
                startTranslateX = imageZoom.translateX;
                startTranslateY = imageZoom.translateY;
            } else if (e.touches.length === 2) {
                // 핀치 줌
                const touch1 = e.touches[0];
                const touch2 = e.touches[1];
                touchStartDistance = Math.hypot(
                    touch2.clientX - touch1.clientX,
                    touch2.clientY - touch1.clientY
                );
                touchStartScale = imageZoom.scale;
            }
        });
        
        lightboxContent.addEventListener('touchmove', function(e) {
            if (!lightbox.classList.contains('active')) return;
            
            e.preventDefault();
            
            if (e.touches.length === 1) {
                // 단일 터치: 이동
                const deltaX = e.touches[0].clientX - touchStartX;
                const deltaY = e.touches[0].clientY - touchStartY;
                imageZoom.translateX = startTranslateX + deltaX;
                imageZoom.translateY = startTranslateY + deltaY;
                updateImageTransform();
            } else if (e.touches.length === 2) {
                // 핀치 줌
                const touch1 = e.touches[0];
                const touch2 = e.touches[1];
                const currentDistance = Math.hypot(
                    touch2.clientX - touch1.clientX,
                    touch2.clientY - touch1.clientY
                );
                const scaleChange = currentDistance / touchStartDistance;
                imageZoom.scale = Math.max(imageZoom.minScale, 
                                         Math.min(imageZoom.maxScale, touchStartScale * scaleChange));
                updateImageTransform();
            }
        });
    }
    
    // ============================================
    // 드래그 앤 드롭 기능
    // ============================================
    const chatInputArea = document.getElementById('chat-input-area');
    const dragOverlay = document.getElementById('drag-overlay');
    
    // 요소 존재 확인
    if (!chatInputArea) {
        console.error('chat-input-area 요소를 찾을 수 없습니다.');
    } else if (!dragOverlay) {
        console.error('drag-overlay 요소를 찾을 수 없습니다.');
    } else {
        // 드래그 오버 이벤트
        chatInputArea.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.stopPropagation();
            chatInputArea.classList.add('drag-over');
            dragOverlay.classList.add('active');
        });
        
        chatInputArea.addEventListener('dragleave', function(e) {
            e.preventDefault();
            e.stopPropagation();
            // 드래그가 자식 요소로 이동한 경우는 제외
            if (!chatInputArea.contains(e.relatedTarget)) {
                chatInputArea.classList.remove('drag-over');
                dragOverlay.classList.remove('active');
            }
        });
        
        // 드롭 이벤트
        chatInputArea.addEventListener('drop', function(e) {
            e.preventDefault();
            e.stopPropagation();
            chatInputArea.classList.remove('drag-over');
            dragOverlay.classList.remove('active');
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                handleFileSelect(files);
            }
        });
    }
    
    // 전체 화면 드래그 오버 (채팅 영역 밖에서도)
    // chatInputArea와 dragOverlay가 존재할 때만 처리
    if (chatInputArea && dragOverlay) {
        document.addEventListener('dragover', function(e) {
            e.preventDefault();
            // 채팅 입력 영역이 보이는 경우에만 오버레이 표시
            if (chatInputArea.style.display !== 'none') {
                dragOverlay.classList.add('active');
            }
        });
        
        document.addEventListener('dragleave', function(e) {
            e.preventDefault();
            // 드래그가 완전히 벗어난 경우
            if (!e.relatedTarget || e.relatedTarget === document.body) {
                dragOverlay.classList.remove('active');
            }
        });
        
        document.addEventListener('drop', function(e) {
            e.preventDefault();
            dragOverlay.classList.remove('active');
            
            // 채팅 입력 영역이 보이는 경우에만 파일 처리
            if (chatInputArea.style.display !== 'none' && e.dataTransfer.files.length > 0) {
                const files = e.dataTransfer.files;
                handleFileSelect(files);
            }
        });
    }
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
// 채팅방 목록 로드
function loadRooms() {
    fetch('/api/chat/rooms')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                renderRooms(data.rooms);
                
                // URL 파라미터에서 room_id 확인 및 자동 선택
                const urlParams = new URLSearchParams(window.location.search);
                const roomIdFromUrl = urlParams.get('room_id');
                
                if (roomIdFromUrl) {
                    const roomId = parseInt(roomIdFromUrl, 10);
                    if (roomId && !isNaN(roomId)) {
                        // 채팅방이 목록에 있는지 확인
                        const roomExists = data.rooms.some(room => room.id === roomId);
                        if (roomExists) {
                            // 약간의 지연 후 선택 (DOM 렌더링 완료 대기)
                            setTimeout(() => {
                                selectRoom(roomId);
                            }, 100);
                        } else {
                            console.warn(`채팅방 ID ${roomId}를 찾을 수 없습니다.`);
                        }
                    }
                }
            }
        })
        .catch(error => {
            console.error('채팅방 목록 로드 오류:', error);
        });
}

// 채팅방 목록 렌더링
function renderRooms(rooms) {
    const container = document.getElementById('rooms-list');
    
    if (rooms.length === 0) {
        container.innerHTML = '<div class="text-center text-muted py-4">채팅방이 없습니다</div>';
        return;
    }
    
    container.innerHTML = rooms.map(room => {
        const lastMessage = room.last_message ? 
            (room.last_message.content || '파일') : '메시지가 없습니다';
        const unreadBadge = room.unread_count > 0 ? 
            '<span class="unread-badge">' + room.unread_count + '</span>' : '';
        const rid = Number(room.id) || 0;
        return '<div class="chat-room-item" data-room-id="' + rid + '" role="button" tabindex="0">' +
            '<div class="room-name">' + escapeHtml(room.name) + '</div>' +
            '<div class="room-last-message">' + escapeHtml(lastMessage) + '</div>' +
            '<div class="room-meta"><span>' + formatDate(room.updated_at || room.created_at) + '</span>' + unreadBadge + '</div></div>';
    }).join('');
}

// 모바일: 목록 ↔ 메시지 전환 (WhatsApp 패턴)
function goBackToChatList() {
    document.querySelector('.chat-page-content')?.classList.remove('chat-mobile-show-messages');
}

// 채팅방 선택
function selectRoom(roomId) {
    currentRoomId = roomId;
    if (window.matchMedia('(max-width: 992px)').matches) {
        document.querySelector('.chat-page-content')?.classList.add('chat-mobile-show-messages');
    }
    
    // URL 업데이트 (브라우저 히스토리 관리)
    const url = new URL(window.location);
    url.searchParams.set('room_id', roomId);
    window.history.pushState({ room_id: roomId }, '', url);
    
    // UI 업데이트
    document.querySelectorAll('.chat-room-item').forEach(item => {
        item.classList.remove('active');
    });
    
    // null 체크 추가
    const roomElement = document.querySelector(`[data-room-id="${roomId}"]`);
    if (roomElement) {
        roomElement.classList.add('active');
    }
    
    // Socket.IO 방 입장 (socket이 존재할 때만)
    if (socket && socket.connected) {
        socket.emit('join_room', { room_id: roomId });
    }
    
    // 채팅방 상세 정보 로드
    loadRoomDetail(roomId);
}

// 채팅방 상세 정보 로드
function loadRoomDetail(roomId) {
    fetch(`/api/chat/rooms/${roomId}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                renderRoomHeader(data.room);
                renderMessages(data.room.messages);
                document.getElementById('chat-input-area').style.display = 'block';
                updateChatHeader();  // 검색 버튼 표시
                scrollToBottom();
                
                // 채팅방 입장 시 읽음 상태 업데이트
                if (socket && socket.connected) {
                    socket.emit('mark_read', { room_id: roomId });
                } else {
                    // REST API로 읽음 상태 업데이트
                    fetch(`/api/chat/rooms/${roomId}/mark-read`, {
                        method: 'POST'
                    }).catch(err => console.error('읽음 상태 업데이트 오류:', err));
                }
            }
        })
        .catch(error => {
            console.error('채팅방 상세 로드 오류:', error);
        });
}

// 채팅방 헤더 렌더링
function renderRoomHeader(room) {
    const header = document.getElementById('chat-header');
    const orderWidgetContainer = document.getElementById('chat-order-widget-container');
    let orderWidget = '';
    const safeRoomId = Number(room.id) || 0;
    
    // 주문 정보 위젯 (Quest 12) - 테이블 형식으로 표시
    if (room.order) {
        const order = room.order;
        
        // 미처리 항목 확인
        let unprocessedBadges = '';
        const unprocessedItems = [];
        if (!order.manager_name) {
            unprocessedItems.push('<span class="badge bg-danger">담당자 미지정</span>');
        }
        if (!order.scheduled_date) {
            unprocessedItems.push('<span class="badge bg-danger">설치일 미지정</span>');
        }
        unprocessedBadges = unprocessedItems.length > 0 
            ? `<div class="unprocessed-badges">${unprocessedItems.join('')}</div>` 
            : '-';
        
        // 상태 옵션 생성
        const statusList = {
            'RECEIVED': '접수',
            'MEASURED': '실측',
            'REGIONAL_MEASURED': '지방실측',
            'SCHEDULED': '설치 예정',
            'SHIPPED_PENDING': '상차 예정',
            'COMPLETED': '완료',
            'AS_RECEIVED': 'AS 접수',
            'AS_COMPLETED': 'AS 완료',
            'ON_HOLD': '보류'
        };
        
        // order.status 값 정규화 및 디버깅
        const currentStatus = (order.status || 'RECEIVED').toString().trim().toUpperCase();
        console.log('Order ID:', order.id, 'Current Status:', currentStatus, 'Raw Status:', order.status);
        
        let statusOptions = '';
        for (const [code, name] of Object.entries(statusList)) {
            const codeUpper = code.toUpperCase();
            const selected = (currentStatus === codeUpper) ? 'selected' : '';
            statusOptions += `<option value="${escapeHtml(code)}" ${selected}>${escapeHtml(name)}</option>`;
        }
        const defaultStatusOption = '<option value="RECEIVED" selected>접수</option>';
        if (!statusOptions) {
            console.warn('Status options is empty, using default');
            statusOptions = defaultStatusOption;
        }
        const safeOrderId = Number(order.id) || 0;
        const statusClass = (currentStatus || 'RECEIVED').toLowerCase().replace(/_/g, '_');
        const selectCellHtml = '<select class="form-select form-select-sm status-dropdown status-' + statusClass + '" data-order-id="' + safeOrderId + '" data-field="status" data-current-status="' + (currentStatus || 'RECEIVED') + '">' + statusOptions + '</select>';
        const managerInputHtml = '<input type="text" class="form-control form-control-sm" value="' + escapeHtml(order.manager_name || '') + '" placeholder="담당자 입력" data-order-id="' + safeOrderId + '" data-field="manager_name">';
        const scheduledInputHtml = '<input type="date" class="form-control form-control-sm" value="' + (order.scheduled_date || '') + '" data-order-id="' + safeOrderId + '" data-field="scheduled_date">';
        
        console.log('Generated status options:', statusOptions.substring(0, 200));
        
        orderWidget = `
            <div class="chat-order-widget-table">
                <div class="table-responsive">
                    <table class="table table-bordered table-sm mb-0" style="table-layout: auto; width: 100%;">
                        <thead>
                            <tr>
                                <th style="width: 60px;">번호</th>
                                <th>고객명</th>
                                <th>주소</th>
                                <th>제품</th>
                                <th style="width: 100px;">상태</th>
                                <th style="width: 100px;">실측일</th>
                                <th style="width: 150px;">미처리 항목</th>
                                <th style="width: 120px;">담당자</th>
                                <th style="width: 140px;">설치 예정일</th>
                                <th style="width: 80px;">작업</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td>#${safeOrderId}</td>
                                <td>
                                    <div class="d-flex align-items-center gap-2">
                                        <div>
                                            <div>${escapeHtml(order.customer_name || '-')}</div>
                                            <small class="text-muted">${escapeHtml(order.phone || '-')}</small>
                                        </div>
                                        ${order.blueprint_image_url ? '<button type="button" class="btn btn-sm btn-outline-info" data-action="open-blueprint" data-order-id="' + safeOrderId + '" title="도면 보기"><i class="fas fa-drafting-compass"></i> 도면</button>' : ''}
                                    </div>
                                </td>
                                <td title="${escapeHtml(order.address || '-')}">
                                    ${escapeHtml(order.address || '-')}
                                </td>
                                <td title="${escapeHtml(order.product || '-')}">
                                    ${escapeHtml(order.product || '-')}
                                </td>
                                <td>
                                    ${selectCellHtml}
                                </td>
                                <td>${order.measurement_date || '-'}</td>
                                <td>${unprocessedBadges}</td>
                                <td>
                                    ${managerInputHtml}
                                </td>
                                <td>
                                    ${scheduledInputHtml}
                                </td>
                                <td>
                                    <a href="/edit/${safeOrderId}" 
                                       class="btn btn-sm btn-outline-secondary" 
                                       title="수정"
                                       target="_blank">
                                        <i class="fas fa-edit"></i>
                                    </a>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        `;
        orderWidgetContainer.innerHTML = orderWidget;
        orderWidgetContainer.style.display = 'block';
        // order-widget-container의 top을 chat-header 높이로 설정
        const headerHeight = header.offsetHeight;
        orderWidgetContainer.style.top = headerHeight + 'px';
    } else {
        orderWidgetContainer.innerHTML = '';
        orderWidgetContainer.style.display = 'none';
    }
    
    // 멤버 목록 표시 - 뱃지 대신 심플한 텍스트로
    const membersText = room.members ? room.members.map(m => m.user_name || (m.user ? m.user.name : '알 수 없음')).join(', ') : '';
    
    const roomNameAttr = safeAttr(room.name);
    
    // 모바일/PC 통합 드롭다운 메뉴 아이템
    const editRoomItem = room.created_by == currentUserId
        ? '<li><button class="dropdown-item py-2" type="button" data-action="edit-room-name" data-room-id="' + safeRoomId + '" data-room-name="' + roomNameAttr + '"><i class="fas fa-edit fa-fw text-secondary me-2"></i>이름 수정</button></li>'
        : '';
    const connectItem = !room.order
        ? '<li><button class="dropdown-item py-2" type="button" data-action="connect-order" data-room-id="' + safeRoomId + '"><i class="fas fa-link fa-fw text-info me-2"></i>주문 연결</button></li>'
        : '<li><button class="dropdown-item py-2" type="button" data-action="disconnect-order" data-room-id="' + safeRoomId + '"><i class="fas fa-unlink fa-fw text-warning me-2"></i>연결 해제</button></li>';
    const inviteItem = '<li><button class="dropdown-item py-2" type="button" data-action="invite-member" data-room-id="' + safeRoomId + '"><i class="fas fa-user-plus fa-fw text-primary me-2"></i>멤버 초대</button></li>';
    const deleteItem = '<li><hr class="dropdown-divider my-1"></li><li><button class="dropdown-item py-2 text-danger" type="button" data-action="delete-room" data-room-id="' + safeRoomId + '"><i class="fas fa-trash fa-fw me-2"></i>채팅방 삭제</button></li>';

    const menuHtml = '<div class="dropdown d-inline-block">' +
        '<button class="btn btn-link text-dark p-2 text-decoration-none" type="button" data-bs-toggle="dropdown" aria-expanded="false"><i class="fas fa-ellipsis-v fa-lg"></i></button>' +
        '<ul class="dropdown-menu dropdown-menu-end shadow-sm" style="font-size: 0.95rem; min-width: 150px;">' +
        editRoomItem + connectItem + inviteItem + deleteItem +
        '</ul></div>';
    
    header.innerHTML = '<div class="d-flex align-items-center justify-content-between w-100" style="min-width: 0;">' +
        '<div class="d-flex align-items-center pe-2" style="min-width: 0; flex: 1;">' +
            '<button type="button" class="btn btn-link text-dark chat-mobile-back-btn p-0 me-2 d-none flex-shrink-0 text-decoration-none" data-action="back-to-list" title="목록으로"><i class="fas fa-arrow-left fa-lg"></i></button>' +
            '<div class="d-flex flex-column" style="min-width: 0; flex: 1;">' +
                '<h5 class="mb-0 text-truncate fw-bold" style="font-size:1.15rem; line-height: 1.2;">' + escapeHtml(room.name) + '</h5>' +
                (membersText ? '<span class="text-muted text-truncate" style="font-size:0.8rem; line-height: 1.2; margin-top: 2px;">' + escapeHtml(membersText) + '</span>' : '') +
            '</div>' +
        '</div>' +
        '<div class="d-flex align-items-center flex-shrink-0">' +
            '<button type="button" class="btn btn-link text-dark p-2 text-decoration-none" data-action="toggle-search" title="메시지 검색"><i class="fas fa-search fa-lg"></i></button>' +
            menuHtml +
        '</div>' +
    '</div>';
}

// 메시지 목록 렌더링
function renderMessages(messages) {
    const container = document.getElementById('messages-container');
    container.innerHTML = messages.map(msg => renderMessage(msg)).join('');
}

// 메시지 렌더링
function renderMessage(msg) {
    const isOwn = msg.user_id == currentUserId;
    const className = isOwn ? 'own' : 'other';
    const userName = msg.user_name || '알 수 없음';
    
    let content = '';
    if (msg.message_type === 'text') {
        content = escapeHtml(msg.content || '');
    } else if (msg.attachments && msg.attachments.length > 0) {
        // 이미지 첨부파일 필터링
        const imageAttachments = msg.attachments.filter(a => a.file_type === 'image');
        const hasMultipleImages = imageAttachments.length > 1;
        
        if (imageAttachments.length > 0) {
            // 이미지들 렌더링 (다운로드 아이콘 포함)
            const imageHtml = imageAttachments.map((attachment, index) => {
                const imageUrl = attachment.url || attachment.storage_url;
                const storageKey = attachment.storage_key || '';
                const filename = attachment.filename || `image_${index + 1}.jpg`;
                
                return '<div class="message-file-image-wrapper">' +
                    '<img src="' + escapeHtml(attachment.thumbnail_url || imageUrl || '') + '" ' +
                    'data-url="' + safeAttr(imageUrl) + '" data-key="' + safeAttr(storageKey) + '" ' +
                    'onclick="openImageLightbox(this)" style="cursor: zoom-in; max-width: 300px; border-radius: 8px; background-color: white; padding: 4px; display: block;">' +
                    '<button type="button" class="chat-image-download-btn" data-action="download-chat-image" data-storage-key="' + safeAttr(storageKey) + '" data-filename="' + safeAttr(filename) + '" title="다운로드">' +
                    '<i class="fas fa-download"></i></button></div>';
            }).join('');
            
            const msgIdNum = Number(msg.id) || 0;
            const downloadAllBtn = hasMultipleImages
                ? '<div class="mt-2"><button type="button" class="btn btn-sm btn-outline-primary" data-action="download-all-images" data-message-id="' + msgIdNum + '" title="모든 이미지 다운로드"><i class="fas fa-download"></i> 전체 다운로드 (' + imageAttachments.length + '개)</button></div>'
                : '';
            
            content = `<div class="message-file">${imageHtml}${downloadAllBtn}</div>`;
        } else {
            // 이미지가 아닌 첨부파일 처리
            const attachment = msg.attachments[0];
            if (attachment.file_type === 'video') {
                const videoUrl = attachment.url || attachment.storage_url;
                const storageKey = attachment.storage_key || '';
                const filename = attachment.filename || 'video.mp4';
                const safeJsStr = (s) => String(s || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                
                content = '<div class="message-file" style="position: relative; display: inline-block;">' +
                    '<video controls style="max-width: 300px;"><source src="' + escapeHtml(videoUrl || '') + '"></video>' +
                    '<button type="button" class="chat-image-download-btn" data-action="download-chat-image" data-storage-key="' + (function(){ var s = String(storageKey || ''); return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;'); })() + '" data-filename="' + (function(){ var s = String(filename || ''); return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;'); })() + '" title="다운로드"><i class="fas fa-download"></i></button></div>';
            } else {
                const fileUrl = attachment.url || attachment.storage_url;
                content = `<a href="${escapeHtml(fileUrl || '')}" target="_blank" class="btn btn-sm btn-outline-primary">
                              <i class="fas fa-download"></i> ${escapeHtml(attachment.filename)}
                           </a>`;
            }
        }
    }
    
    // 읽음 표시 (채널톡 스타일 - 실제 읽음 상태 확인)
    let readReceipt = '';
    if (isOwn && msg.read_status) {
        if (msg.read_status === 'no_other_members') {
            // 다른 멤버가 없으면 표시하지 않음
            readReceipt = '';
        } else if (msg.read_status === 'unread') {
            // 아직 아무도 읽지 않음
            readReceipt = '<div class="read-receipt" style="color: #999;"><i class="fas fa-check"></i> 전송됨</div>';
        } else if (msg.read_status === 'all_read') {
            // 모두 읽음
            readReceipt = '<div class="read-receipt"><i class="fas fa-check read-icon"></i> 읽음</div>';
        } else if (msg.read_status === 'some_read') {
            // 일부 읽음
            readReceipt = `<div class="read-receipt"><i class="fas fa-check read-icon"></i> ${msg.read_count}/${msg.total_other_members}명 읽음</div>`;
        }
    }
    
    return `
        <div class="message-item ${className}" data-message-id="${msg.id}">
            <div class="message-bubble">
                ${content}
            </div>
            <div class="message-meta">
                ${!isOwn ? escapeHtml(userName) + ' · ' : ''}${formatDateTime(msg.created_at)}
            </div>
            ${readReceipt}
        </div>
    `;
}

// 메시지 추가 (실시간)
function appendMessage(msg) {
    const container = document.getElementById('messages-container');
    
    // 중복 방지: 메시지 ID로 이미 존재하는지 확인
    if (msg.id) {
        const existingMessage = container.querySelector(`[data-message-id="${msg.id}"]`);
        if (existingMessage) {
            console.log('[appendMessage] 중복 메시지 스킵:', msg.id);
            return; // 이미 존재하는 메시지는 추가하지 않음
        }
    }
    
    // 메시지 추가
    container.innerHTML += renderMessage(msg);
}

// 메시지 전송
function sendMessage() {
    const input = document.getElementById('message-input');
    const message = input.value.trim();
    
    if (!currentRoomId) {
        alert('채팅방을 선택하세요');
        return;
    }
    
    if (!message && !previewFile) {
        return;
    }
    
    const messageData = {
        room_id: currentRoomId,
        message_type: previewFile ? previewFile.type : 'text',
        content: message,
        file_info: previewFile ? previewFile.info : null
    };
    
    // Socket.IO가 연결되어 있으면 사용, 아니면 REST API로 전송
    if (socket && socket.connected) {
        socket.emit('send_message', messageData);
    } else {
        // REST API로 메시지 전송 (폴백)
        fetch('/api/chat/messages', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(messageData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 메시지 목록 새로고침
                loadRoomDetail(currentRoomId);
            } else {
                alert('메시지 전송 실패: ' + data.message);
            }
        })
        .catch(error => {
            console.error('메시지 전송 오류:', error);
            alert('메시지 전송 중 오류가 발생했습니다.');
        });
    }
    
    // 입력 필드 초기화
    input.value = '';
    removePreview();
}

// 파일 미리보기
// 파일 미리보기 (Phase D: Direct upload 지원)
var USE_DIRECT_UPLOAD_CHAT = true;
let previewFile = null;

function handleFileSelect(files) {
    if (files.length === 0) return;
    
    // 채팅방이 선택되지 않았으면 경고
    if (!currentRoomId) {
        alert('채팅방을 먼저 선택해주세요.');
        return;
    }
    
    const file = files[0];
    
    // 요소 가져오기 및 null 체크
    const preview = document.getElementById('file-preview');
    let content = document.getElementById('preview-content');
    const chatInputArea = document.getElementById('chat-input-area');
    
    if (!preview) {
        console.error('file-preview 요소를 찾을 수 없습니다.');
        alert('파일 미리보기 영역을 찾을 수 없습니다.');
        return;
    }
    
    if (!content && preview) {
        content = document.createElement('div');
        content.id = 'preview-content';
        preview.appendChild(content);
    }
    
    if (chatInputArea && chatInputArea.style.display === 'none') {
        chatInputArea.style.display = 'block';
    }
    
    const finalContent = content || preview;
    finalContent.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 업로드 중...';
    preview.classList.add('active');
    
    var progressWrap = document.getElementById('chat-upload-progress');
    var progressBar = document.getElementById('chat-upload-progress-bar');
    function showProgress(percent) {
      if (progressWrap) progressWrap.classList.remove('d-none');
      if (progressBar) { progressBar.style.width = percent + '%'; progressBar.textContent = percent + '%'; }
    }
    function hideProgress() {
      if (progressWrap) progressWrap.classList.add('d-none');
      if (progressBar) { progressBar.style.width = '0%'; progressBar.textContent = '0%'; }
    }
    
    if (USE_DIRECT_UPLOAD_CHAT) {
        // Phase D: session -> PUT -> complete
        fetch('/api/chat/upload/session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filename: file.name,
                size: file.size,
                room_id: String(currentRoomId || '')
            })
        })
        .then(r => r.json())
        .then(sessionData => {
            if (!sessionData.success || !sessionData.upload_url) {
                throw new Error(sessionData.message || '세션 발급 실패');
            }
            return fetch(sessionData.upload_url, {
                method: 'PUT',
                body: file,
                headers: { 'Content-Type': file.type || 'application/octet-stream' }
            }).then(() => sessionData.key);
        })
        .then(key => {
            showProgress(90);
            return fetch('/api/chat/upload/complete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: key, filename: file.name })
            });
        })
        .then(r => r.json())
        .then(data => {
            showProgress(100);
            hideProgress();
            if (data.success) {
                previewFile = { type: data.file_info.file_type, info: data.file_info };
                showPreview(data.file_info);
            } else {
                preview.classList.remove('active');
                if (finalContent) finalContent.innerHTML = '';
                alert('파일 업로드 실패: ' + (data.message || '알 수 없는 오류'));
            }
        })
        .catch(err => {
            console.warn('Direct 업로드 실패, multipart로 재시도:', err);
            const formData = new FormData();
            formData.append('file', file);
            formData.append('room_id', currentRoomId);
            if (typeof uploadWithProgress !== 'undefined') {
                uploadWithProgress('/api/chat/upload', formData, { onProgress: showProgress })
                .then(data => {
                    showProgress(100);
                    hideProgress();
                    if (data.success) {
                        previewFile = { type: data.file_info.file_type, info: data.file_info };
                        showPreview(data.file_info);
                    } else {
                        preview.classList.remove('active');
                        if (finalContent) finalContent.innerHTML = '';
                        alert('파일 업로드 실패: ' + (data.message || '알 수 없는 오류'));
                    }
                })
                .catch(err2 => {
                    hideProgress();
                    console.error('파일 업로드 오류:', err2);
                    preview.classList.remove('active');
                    if (finalContent) finalContent.innerHTML = '';
                    alert('파일 업로드 중 오류가 발생했습니다.');
                });
            } else {
                fetch('/api/chat/upload', { method: 'POST', body: formData })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        previewFile = { type: data.file_info.file_type, info: data.file_info };
                        showPreview(data.file_info);
                    } else {
                        preview.classList.remove('active');
                        if (finalContent) finalContent.innerHTML = '';
                        alert('파일 업로드 실패: ' + (data.message || '알 수 없는 오류'));
                    }
                })
                .catch(err2 => {
                    console.error('파일 업로드 오류:', err2);
                    preview.classList.remove('active');
                    if (finalContent) finalContent.innerHTML = '';
                    alert('파일 업로드 중 오류가 발생했습니다.');
                });
            }
        });
    } else {
        // 기존 multipart (진행률 표시)
        const formData = new FormData();
        formData.append('file', file);
        formData.append('room_id', currentRoomId);
        if (typeof uploadWithProgress !== 'undefined') {
            uploadWithProgress('/api/chat/upload', formData, { onProgress: showProgress })
            .then(data => {
                showProgress(100);
                hideProgress();
                if (data.success) {
                    previewFile = { type: data.file_info.file_type, info: data.file_info };
                    showPreview(data.file_info);
                } else {
                    preview.classList.remove('active');
                    if (finalContent) finalContent.innerHTML = '';
                    alert('파일 업로드 실패: ' + data.message);
                }
            })
            .catch(err => {
                hideProgress();
                console.error('파일 업로드 오류:', err);
                preview.classList.remove('active');
                if (finalContent) finalContent.innerHTML = '';
                alert('파일 업로드 중 오류가 발생했습니다.');
            });
        } else {
        fetch('/api/chat/upload', { method: 'POST', body: formData })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                previewFile = { type: data.file_info.file_type, info: data.file_info };
                showPreview(data.file_info);
            } else {
                preview.classList.remove('active');
                if (finalContent) finalContent.innerHTML = '';
                alert('파일 업로드 실패: ' + data.message);
            }
        })
        .catch(err => {
            console.error('파일 업로드 오류:', err);
            preview.classList.remove('active');
            if (finalContent) finalContent.innerHTML = '';
            alert('파일 업로드 중 오류가 발생했습니다.');
        });
        }
    }
}

function showPreview(fileInfo) {
    const preview = document.getElementById('file-preview');
    let content = document.getElementById('preview-content');
    const chatInputArea = document.getElementById('chat-input-area');
    
    // 요소가 없으면 에러 처리
    if (!preview) {
        console.error('file-preview 요소를 찾을 수 없습니다.');
        return;
    }
    
    // preview-content가 없으면 생성
    if (!content && preview) {
        content = document.createElement('div');
        content.id = 'preview-content';
        preview.appendChild(content);
    }
    
    // chat-input-area가 숨겨져 있으면 표시
    if (chatInputArea && chatInputArea.style.display === 'none') {
        chatInputArea.style.display = 'block';
    }
    
    // content가 여전히 null이면 preview를 직접 사용
    const finalContent = content || preview;
    
    // X 버튼 HTML
    const removeBtn = '<button type="button" class="file-remove-btn" onclick="removePreview()" title="파일 삭제">×</button>';
    
    if (fileInfo.file_type === 'image') {
        const imageUrl = fileInfo.thumbnail_url || fileInfo.url || fileInfo.storage_url;
        finalContent.innerHTML = `<div style="position: relative; display: inline-block;">${removeBtn}<img src="${imageUrl}" style="max-width: 200px; background-color: white; padding: 4px; border-radius: 8px; display: block;"></div>`;
    } else if (fileInfo.file_type === 'video') {
        const videoUrl = fileInfo.url || fileInfo.storage_url;
        finalContent.innerHTML = `<div style="position: relative; display: inline-block;">${removeBtn}<video controls style="max-width: 200px; border-radius: 8px; display: block;"><source src="${videoUrl}"></video></div>`;
    } else {
        finalContent.innerHTML = `<div style="position: relative; display: inline-block; padding: 8px 12px; background-color: white; border-radius: 8px; border: 1px solid #ddd;">${removeBtn}<i class="fas fa-file"></i> ${escapeHtml(fileInfo.filename)}</div>`;
    }
    
    preview.classList.add('active');
}

function removePreview() {
    previewFile = null;
    const preview = document.getElementById('file-preview');
    const content = document.getElementById('preview-content');
    
    if (preview) {
        preview.classList.remove('active');
    }
    
    if (content) {
        content.innerHTML = '';
    }
    
    const fileInput = document.getElementById('file-input');
    if (fileInput) {
        fileInput.value = '';
    }
}

// 채팅 이미지 다운로드 함수
function downloadChatImage(storageKey, filename, event) {
    if (event) {
        event.stopPropagation();
        event.preventDefault();
    }
    
    if (!storageKey) {
        alert('다운로드할 수 없습니다. 파일 정보가 없습니다.');
        return;
    }
    
    // 다운로드 API 호출
    const downloadUrl = `/api/chat/download/${encodeURIComponent(storageKey)}`;
    const link = document.createElement('a');
    link.href = downloadUrl;
    link.download = filename;
    link.target = '_blank';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// 전체 이미지 다운로드 함수
function downloadAllChatImages(messageId, event) {
    if (event) {
        event.stopPropagation();
        event.preventDefault();
    }
    
    // 현재 채팅방의 메시지 데이터에서 attachments 찾기
    fetch(`/api/chat/messages/${messageId}`)
        .then(response => response.json())
        .then(data => {
            if (data.success && data.message && data.message.attachments) {
                const imageAttachments = data.message.attachments.filter(a => a.file_type === 'image');
                
                if (imageAttachments.length === 0) {
                    alert('다운로드할 이미지가 없습니다.');
                    return;
                }
                
                // 각 이미지를 순차적으로 다운로드
                imageAttachments.forEach((attachment, index) => {
                    setTimeout(() => {
                        const storageKey = attachment.storage_key || '';
                        const filename = attachment.filename || `image_${index + 1}.jpg`;
                        if (storageKey) {
                            downloadChatImage(storageKey, filename, null);
                        }
                    }, index * 300); // 300ms 간격으로 다운로드
                });
            } else {
                alert('메시지 정보를 가져올 수 없습니다.');
            }
        })
        .catch(error => {
            console.error('메시지 조회 오류:', error);
            alert('메시지 정보를 가져오는 중 오류가 발생했습니다.');
        });
}
// 사용자 목록 로드 함수
function loadUsers() {
    fetch('/api/chat/users')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                renderUserList(data.users);
            } else {
                document.getElementById('user-select-container').innerHTML = 
                    '<div class="text-center text-muted py-2">사용자 목록을 불러올 수 없습니다.</div>';
            }
        })
        .catch(error => {
            console.error('사용자 목록 로드 오류:', error);
            document.getElementById('user-select-container').innerHTML = 
                '<div class="text-center text-danger py-2">사용자 목록 로드 중 오류가 발생했습니다.</div>';
        });
}

function renderUserList(users) {
    const container = document.getElementById('user-select-container');
    if (users.length === 0) {
        container.innerHTML = '<div class="text-center text-muted py-2">초대할 사용자가 없습니다.</div>';
        return;
    }
    container.innerHTML = users.map(user => `
        <div class="form-check">
            <input class="form-check-input" type="checkbox" value="${user.id}" id="user-${user.id}">
            <label class="form-check-label" for="user-${user.id}">
                ${escapeHtml(user.name)} (${escapeHtml(user.username)})
            </label>
        </div>
    `).join('');
}

// 새 채팅방 생성
function showCreateRoomModal() {
    loadUsers();  // 사용자 목록 로드
    clearOrderSelection();  // 주문 선택 초기화
    const modal = new bootstrap.Modal(document.getElementById('createRoomModal'));
    modal.show();
}

function createRoom() {
    const name = document.getElementById('room-name').value.trim();
    const description = document.getElementById('room-description').value.trim();
    
    if (!name) {
        alert('채팅방 이름을 입력하세요');
        return;
    }
    
    // 선택된 멤버 ID 수집
    const selectedUsers = Array.from(document.querySelectorAll('#user-select-container input[type="checkbox"]:checked'))
        .map(checkbox => parseInt(checkbox.value));
    
    fetch('/api/chat/rooms', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            name: name,
            description: description,
            member_ids: selectedUsers,  // 멤버 ID 배열 추가
            order_id: selectedOrderId || null  // 주문 ID 추가
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            bootstrap.Modal.getInstance(document.getElementById('createRoomModal')).hide();
            document.getElementById('room-name').value = '';
            document.getElementById('room-description').value = '';
            // 체크박스 초기화
            document.querySelectorAll('#user-select-container input[type="checkbox"]').forEach(cb => cb.checked = false);
            clearOrderSelection();  // 주문 선택 초기화
            loadRooms();
            selectRoom(data.room.id);
        } else {
            alert('채팅방 생성 실패: ' + data.message);
        }
    })
    .catch(error => {
        console.error('채팅방 생성 오류:', error);
        alert('채팅방 생성 중 오류가 발생했습니다.');
    });
}

// 주문 상세 보기 (Quest 12)
function viewOrderDetail(orderId) {
    window.open(`/edit/${orderId}`, '_blank');
}

// 주문 상태 업데이트
function updateOrderStatus(orderId, newStatus) {
    fetch('/api/update_order_status', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            order_id: orderId,
            status: newStatus
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log('주문 상태가 업데이트되었습니다.');
            // 상태 드롭다운 색상 업데이트
            const selectElement = document.querySelector(`select[data-order-id="${orderId}"]`);
            if (selectElement) {
                // 기존 상태 클래스 제거
                selectElement.classList.remove('status-received', 'status-measured', 'status-regional_measured', 
                                              'status-scheduled', 'status-shipped_pending', 'status-completed', 
                                              'status-as_received', 'status-as_completed', 'status-on_hold');
                // 새로운 상태 클래스 추가
                if (newStatus) {
                    selectElement.classList.add('status-' + newStatus.toLowerCase());
                }
                // applyStatusColor 함수가 있으면 호출
                if (typeof applyStatusColor === 'function') {
                    applyStatusColor(selectElement);
                }
            }
            // 주문이 연결된 경우 헤더를 다시 렌더링
            if (currentRoomId) {
                loadRoomDetail(currentRoomId);
            }
        } else {
            alert('주문 상태 업데이트 실패: ' + data.message);
        }
    })
    .catch(error => {
        console.error('주문 상태 업데이트 오류:', error);
        alert('주문 상태 업데이트 중 오류가 발생했습니다.');
    });
}

// 주문 필드 업데이트 (담당자, 설치 예정일 등)
function updateOrderField(orderId, field, value) {
    fetch('/api/update_order_field', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            order_id: orderId,
            field: field,
            value: value || null
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log(`주문 ${field}가 업데이트되었습니다.`);
            // 주문이 연결된 경우 헤더를 다시 렌더링
            if (currentRoomId) {
                loadRoomDetail(currentRoomId);
            }
        } else {
            alert(`주문 ${field} 업데이트 실패: ` + data.message);
        }
    })
    .catch(error => {
        console.error(`주문 ${field} 업데이트 오류:`, error);
        alert(`주문 ${field} 업데이트 중 오류가 발생했습니다.`);
    });
}

// 주문 연결 관련 함수들
let selectedOrderId = null;
let connectRoomId = null;

function searchOrdersForRoom(query) {
    if (!query || query.length < 2) {
        document.getElementById('order-search-results').style.display = 'none';
        return;
    }
    
    fetch(`/api/chat/search-orders?q=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(data => {
            const resultsDiv = document.getElementById('order-search-results');
            if (data.success && data.orders.length > 0) {
                resultsDiv.innerHTML = data.orders.map(order => {
                    const oid = Number(order.id) || 0;
                    const custAttr = safeAttr(order.customer_name);
                    const prodAttr = safeAttr(order.product || '-');
                    return '<div class="p-2 border-bottom order-search-row" role="button" tabindex="0" style="cursor: pointer; background-color: white;" data-action="select-order" data-order-id="' + oid + '" data-customer-name="' + custAttr + '" data-product="' + prodAttr + '">' +
                        '<strong>주문 #' + oid + '</strong> - ' + escapeHtml(order.customer_name) + '<br>' +
                        '<small class="text-muted">' + escapeHtml(order.product || '-') + ' | ' + escapeHtml(order.status || '-') + '</small></div>';
                }).join('');
                resultsDiv.style.display = 'block';
            } else {
                resultsDiv.innerHTML = '<div class="text-center text-muted py-2">검색 결과가 없습니다</div>';
                resultsDiv.style.display = 'block';
            }
        })
        .catch(error => {
            console.error('주문 검색 오류:', error);
        });
}

function selectOrderForRoom(orderId, customerName, product) {
    selectedOrderId = orderId;
    document.getElementById('selected-order').style.display = 'block';
    document.getElementById('selected-order-name').textContent = '주문 #' + orderId + ' - ' + customerName + ' (' + product + ')';
    document.getElementById('order-search-results').style.display = 'none';
    document.getElementById('order-search').value = '';
}

function clearOrderSelection() {
    selectedOrderId = null;
    document.getElementById('selected-order').style.display = 'none';
    document.getElementById('order-search').value = '';
    document.getElementById('order-search-results').style.display = 'none';
}

function showConnectOrderModal(roomId) {
    connectRoomId = roomId;
    selectedOrderId = null;
    document.getElementById('connect-order-search').value = '';
    document.getElementById('connect-order-results').innerHTML = '<div class="text-center text-muted py-2">검색어를 입력하세요</div>';
    const modal = new bootstrap.Modal(document.getElementById('connectOrderModal'));
    modal.show();
}

function searchOrdersForConnect(query) {
    if (!query || query.length < 2) {
        document.getElementById('connect-order-results').innerHTML = '<div class="text-center text-muted py-2">검색어를 입력하세요</div>';
        return;
    }
    
    fetch(`/api/chat/search-orders?q=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(data => {
            const resultsDiv = document.getElementById('connect-order-results');
            if (data.success && data.orders.length > 0) {
                resultsDiv.innerHTML = data.orders.map(order => {
                    const oid = Number(order.id) || 0;
                    return '<div class="p-2 border-bottom order-search-row" role="button" tabindex="0" style="cursor: pointer; background-color: white;" data-action="connect-order" data-order-id="' + oid + '">' +
                        '<strong>주문 #' + oid + '</strong> - ' + escapeHtml(order.customer_name) + '<br>' +
                        '<small class="text-muted">' + escapeHtml(order.product || '-') + ' | ' + escapeHtml(order.status || '-') + '</small></div>';
                }).join('');
            } else {
                resultsDiv.innerHTML = '<div class="text-center text-muted py-2">검색 결과가 없습니다</div>';
            }
        })
        .catch(error => {
            console.error('주문 검색 오류:', error);
        });
}

function connectOrderToRoom(orderId, customerName) {
    if (!connectRoomId) return;
    
    fetch(`/api/chat/rooms/${connectRoomId}`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            order_id: orderId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            bootstrap.Modal.getInstance(document.getElementById('connectOrderModal')).hide();
            loadRoomDetail(connectRoomId);
        } else {
            alert('주문 연결 실패: ' + data.message);
        }
    })
    .catch(error => {
        console.error('주문 연결 오류:', error);
        alert('주문 연결 중 오류가 발생했습니다.');
    });
}

function disconnectOrder(roomId) {
    if (!confirm('주문 연결을 해제하시겠습니까?')) {
        return;
    }
    
    fetch(`/api/chat/rooms/${roomId}`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            order_id: null
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            loadRoomDetail(roomId);
        } else {
            alert('주문 연결 해제 실패: ' + data.message);
        }
    })
    .catch(error => {
        console.error('주문 연결 해제 오류:', error);
        alert('주문 연결 해제 중 오류가 발생했습니다.');
    });
}

// 채팅방 이름 수정
function showEditRoomNameModal(roomId, currentName) {
    const newName = prompt('채팅방 이름을 입력하세요:', currentName);
    if (!newName || newName.trim() === '' || newName.trim() === currentName) {
        return;
    }
    
    fetch(`/api/chat/rooms/${roomId}`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            name: newName.trim()
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            loadRoomDetail(roomId);
            loadRooms(); // 채팅방 목록도 업데이트
        } else {
            alert('이름 수정 실패: ' + data.message);
        }
    })
    .catch(error => {
        console.error('이름 수정 오류:', error);
        alert('이름 수정 중 오류가 발생했습니다.');
    });
}

// 멤버 초대 관련 함수들
let inviteRoomId = null;

function showInviteMemberModal(roomId) {
    inviteRoomId = roomId;
    loadUsersForInvite(roomId);
    const modal = new bootstrap.Modal(document.getElementById('inviteMemberModal'));
    modal.show();
}

function loadUsersForInvite(roomId) {
    // 현재 멤버 목록 가져오기
    fetch(`/api/chat/rooms/${roomId}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const currentMemberIds = data.room.members.map(m => m.user_id);
                loadUsersForInviteList(currentMemberIds);
            } else {
                document.getElementById('invite-user-select-container').innerHTML = 
                    '<div class="text-center text-danger py-2">채팅방 정보를 불러올 수 없습니다.</div>';
            }
        })
        .catch(error => {
            console.error('채팅방 정보 로드 오류:', error);
            document.getElementById('invite-user-select-container').innerHTML = 
                '<div class="text-center text-danger py-2">채팅방 정보 로드 중 오류가 발생했습니다.</div>';
        });
}

function loadUsersForInviteList(excludeIds) {
    fetch('/api/chat/users')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 이미 멤버인 사용자 제외
                const availableUsers = data.users.filter(u => !excludeIds.includes(u.id));
                renderInviteUserList(availableUsers);
            } else {
                document.getElementById('invite-user-select-container').innerHTML = 
                    '<div class="text-center text-danger py-2">사용자 목록을 불러올 수 없습니다.</div>';
            }
        })
        .catch(error => {
            console.error('사용자 목록 로드 오류:', error);
            document.getElementById('invite-user-select-container').innerHTML = 
                '<div class="text-center text-danger py-2">사용자 목록 로드 중 오류가 발생했습니다.</div>';
        });
}

function renderInviteUserList(users) {
    const container = document.getElementById('invite-user-select-container');
    if (users.length === 0) {
        container.innerHTML = '<div class="text-center text-muted py-2">초대할 사용자가 없습니다.</div>';
        return;
    }
    container.innerHTML = users.map(user => `
        <div class="form-check">
            <input class="form-check-input" type="checkbox" value="${user.id}" id="invite-user-${user.id}">
            <label class="form-check-label" for="invite-user-${user.id}">
                ${escapeHtml(user.name)} (${escapeHtml(user.username)})
            </label>
        </div>
    `).join('');
}

function inviteMembers() {
    if (!inviteRoomId) {
        alert('채팅방 정보가 없습니다.');
        return;
    }
    
    const selectedUsers = Array.from(document.querySelectorAll('#invite-user-select-container input[type="checkbox"]:checked'))
        .map(checkbox => parseInt(checkbox.value));
    
    if (selectedUsers.length === 0) {
        alert('초대할 사용자를 선택하세요');
        return;
    }
    
    // 여러 사용자를 한 번에 초대
    Promise.all(selectedUsers.map(userId => 
        fetch(`/api/chat/rooms/${inviteRoomId}/members`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ user_id: userId })
        })
    ))
    .then(responses => Promise.all(responses.map(r => r.json())))
    .then(results => {
        const failed = results.filter(r => !r.success);
        const successCount = results.length - failed.length;
        
        if (failed.length > 0) {
            alert(`${successCount}명 초대 완료. ${failed.length}명 실패: ${failed.map(f => f.message).join(', ')}`);
        } else {
            alert(`${successCount}명이 초대되었습니다.`);
        }
        
        bootstrap.Modal.getInstance(document.getElementById('inviteMemberModal')).hide();
        // 체크박스 초기화
        document.querySelectorAll('#invite-user-select-container input[type="checkbox"]').forEach(cb => cb.checked = false);
        
        // 채팅방 정보 새로고침
        if (currentRoomId === inviteRoomId) {
            loadRoomDetail(inviteRoomId);
        }
        loadRooms();
    })
    .catch(error => {
        console.error('멤버 초대 오류:', error);
        alert('멤버 초대 중 오류가 발생했습니다.');
    });
}

// 채팅방 삭제 함수
function deleteRoom(roomId) {
    if (!confirm('정말 이 채팅방을 삭제하시겠습니까?\n모든 메시지와 파일이 삭제되며 복구할 수 없습니다.')) {
        return;
    }
    
    fetch(`/api/chat/rooms/${roomId}`, {
        method: 'DELETE'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('채팅방이 삭제되었습니다.');
            currentRoomId = null;
            document.getElementById('chat-header').innerHTML = '<div class="text-center text-muted py-4" style="flex: 1;">채팅방을 선택하세요</div><button type="button" class="btn btn-sm btn-outline-secondary" data-action="toggle-search" title="메시지 검색" style="display: none;" id="search-btn"><i class="fas fa-search"></i></button>';
            document.getElementById('chat-order-widget-container').innerHTML = '';
            document.getElementById('chat-order-widget-container').style.display = 'none';
            document.getElementById('messages-container').innerHTML = '';
            document.getElementById('chat-input-area').style.display = 'none';
            loadRooms();
        } else {
            alert('채팅방 삭제 실패: ' + data.message);
        }
    })
    .catch(error => {
        console.error('채팅방 삭제 오류:', error);
        alert('채팅방 삭제 중 오류가 발생했습니다.');
    });
}

// 채널톡 스타일 추가 기능

// 타이핑 인디케이터
let typingTimeout = null;
let typingUsers = {};

function handleTyping() {
    if (!currentRoomId || !socket || !socket.connected) return;
    
    // 타이핑 중 이벤트 전송
    socket.emit('typing', {
        room_id: currentRoomId,
        is_typing: true
    });
    
    // 3초 후 타이핑 중지
    clearTimeout(typingTimeout);
    typingTimeout = setTimeout(() => {
        if (socket && socket.connected) {
            socket.emit('typing', {
                room_id: currentRoomId,
                is_typing: false
            });
        }
    }, 3000);
}

function showTypingIndicator(userId, isTyping) {
    const container = document.getElementById('messages-container');
    let indicator = document.getElementById('typing-indicator');
    
    if (isTyping) {
        typingUsers[userId] = true;
        if (!indicator) {
            indicator = document.createElement('div');
            indicator.id = 'typing-indicator';
            indicator.className = 'typing-indicator';
            container.appendChild(indicator);
        }
        // 사용자 이름 가져오기 (간단히 처리)
        indicator.textContent = '입력 중...';
    } else {
        delete typingUsers[userId];
        if (Object.keys(typingUsers).length === 0 && indicator) {
            indicator.remove();
        }
    }
}

// 메시지 검색 기능
function toggleSearch() {
    const searchDiv = document.getElementById('message-search');
    if (searchDiv.style.display === 'none') {
        searchDiv.style.display = 'block';
        document.getElementById('search-input').focus();
    } else {
        closeSearch();
    }
}

function closeSearch() {
    document.getElementById('message-search').style.display = 'none';
    document.getElementById('search-input').value = '';
    // 검색 결과 초기화
    if (currentRoomId) {
        loadRoomDetail(currentRoomId);
    }
}

function searchMessages(query) {
    if (!currentRoomId || !query.trim()) {
        return;
    }
    
    // 간단한 클라이언트 사이드 검색
    const messages = document.querySelectorAll('.message-item');
    messages.forEach(msg => {
        const text = msg.textContent.toLowerCase();
        if (text.includes(query.toLowerCase())) {
            msg.style.backgroundColor = '#fff3cd';
            scrollMessageIntoView(msg);
        } else {
            msg.style.backgroundColor = '';
        }
    });
}

// 전역 검색 기능
function performGlobalSearch(query) {
    const resultsDiv = document.getElementById('global-search-results');
    const roomsList = document.getElementById('rooms-list');
    
    if (!query || query.length < 2) {
        resultsDiv.style.display = 'none';
        roomsList.style.display = 'block';
        return;
    }
    
    fetch(`/api/chat/search?q=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(data => {
            if (data.success && data.results.length > 0) {
                resultsDiv.innerHTML = data.results.map(result => {
                    const rid = Number(result.room_id) || 0;
                    const mid = Number(result.message_id) || 0;
                    if (result.type === 'message') {
                        const contentPreview = result.content ? escapeHtml(result.content.substring(0, 50)) + (result.content.length > 50 ? '...' : '') : '메시지';
                        return '<div class="p-2 border-bottom global-search-row" role="button" tabindex="0" style="cursor: pointer; background-color: white;" data-action="search-result-message" data-room-id="' + rid + '" data-message-id="' + mid + '">' +
                            '<strong>' + escapeHtml(result.room_name || '알 수 없음') + '</strong><br>' +
                            '<small>메시지: ' + contentPreview + '</small><br>' +
                            '<small class="text-muted">' + escapeHtml(result.user_name || '알 수 없음') + ' | ' + (result.created_at || '') + '</small></div>';
                    } else if (result.type === 'room') {
                        const desc = result.description ? '<br><small class="text-muted">' + escapeHtml(result.description) + '</small>' : '';
                        return '<div class="p-2 border-bottom global-search-row" role="button" tabindex="0" style="cursor: pointer; background-color: white;" data-action="search-result-room" data-room-id="' + rid + '">' +
                            '<strong>채팅방: ' + escapeHtml(result.room_name || '') + '</strong>' + desc + '</div>';
                    } else if (result.type === 'order') {
                        return '<div class="p-2 border-bottom global-search-row" role="button" tabindex="0" style="cursor: pointer; background-color: white;" data-action="search-result-room" data-room-id="' + rid + '">' +
                            '<strong>' + escapeHtml(result.room_name || '알 수 없음') + '</strong><br>' +
                            '<small>주문 #' + (result.order_id || '') + ': ' + escapeHtml(result.customer_name || '-') + ' | ' + escapeHtml(result.phone || '-') + ' | ' + escapeHtml(result.address || '-') + '</small></div>';
                    }
                    return '';
                }).join('');
                resultsDiv.style.display = 'block';
                roomsList.style.display = 'none';
            } else {
                resultsDiv.innerHTML = '<div class="text-center text-muted py-2">검색 결과가 없습니다</div>';
                resultsDiv.style.display = 'block';
                roomsList.style.display = 'none';
            }
        })
        .catch(error => {
            console.error('전체 검색 오류:', error);
            resultsDiv.innerHTML = '<div class="text-center text-danger py-2">검색 중 오류가 발생했습니다</div>';
            resultsDiv.style.display = 'block';
        });
}

function selectRoomAndHighlight(roomId, messageId) {
    selectRoom(roomId);
    setTimeout(() => {
        const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
        if (messageElement) {
            scrollMessageIntoView(messageElement);
            messageElement.style.backgroundColor = '#fff3cd';
            setTimeout(() => {
                messageElement.style.backgroundColor = '';
            }, 3000);
        }
    }, 500);
}

// 채팅방 헤더에 검색 버튼 표시
function updateChatHeader() {
    const searchBtn = document.getElementById('search-btn');
    if (currentRoomId && searchBtn) {
        searchBtn.style.display = 'block';
    } else if (searchBtn) {
        searchBtn.style.display = 'none';
    }
}