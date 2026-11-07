# Channel (API-first context — FR20)

## 목적

채널톡 연동(PUSH·웹훅·함수·WAM) **API** surface의 canonical owner를 둔다. 사내 채팅(`chat` blueprint · `/chat` · Socket.IO 채팅 이벤트)은 CHAT-DEL-01(2026-11-07)로 지웠다 — 실시간 알림 연결은 `foms/services/notifications/realtime_notifications.py`.

## 주요 모듈

| 모듈 | 역할 |
|------|------|
| `__init__.py` | Blueprint·라우트 등록 |
| 기타 | 채널 메시지·첨부·정책·보안 관련 API |

서비스 구현은 `foms/services/channel_*`, `foms/services/notifications/` 등과 연결된다.

## 읽기 순서

1. `foms/platform/blueprints.py`
2. 본 디렉터리 패키지
3. `foms/services/channel_*` — 정책·전달

## 금지 의존성

- 사내 채팅 되살리기(`chat` blueprint · `/chat`) — 삭제 결정 `docs/specs/2026-11-07-internal-chat-removal_SPEC.md`.
- quarantine 트리 import 금지.
