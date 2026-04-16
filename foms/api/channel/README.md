# Channel (API-first context — FR20)

## 목적

채널·채팅·Socket.IO·WAM 등 **API·실시간** surface의 canonical owner를 둔다. human-facing 페이지가 분리되어 있으면 `foms/web/channel/` 과 짝을 이룬다.

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

- `chat` blueprint 이름으로의 page `url_for` (PAC: `channel_chat_pages.*` 사용).
- quarantine 트리 import 금지.
