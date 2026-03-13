# 🚀 FOMS × 채널톡 연동 프로젝트 계획도

## 1. 프로젝트 개요
* **목표**: 현재 ERP로 사용 중인 채널톡에서 FOMS로 전환하는 과정의 마찰을 줄이고, 채널톡을 '정보 아카이브' 및 '퀵 액션 도구'로 활용.
* **핵심 전략**: 
  1. FOMS 데이터 → 채널톡 채팅방 푸시 (아카이브)
  2. 채널톡 내 FOMS 데이터 조회/조작 (Command + WAM)
  3. 채널톡 메시지 → FOMS 주문 연동 (Webhook)

---

## 2. 단계별 구축 계획 (Phases)

### 🟢 Phase 1: 아카이브 푸시 구축 (단방향: FOMS → 채널톡)
**목표**: FOMS에서 주문이 접수/수정되거나 단계가 변경될 때, 기존 채널톡 그룹 채팅방으로 텍스트 요약과 현장/도면 사진을 자동 전송.
* **Task 1-1. 채널톡 App 초기 설정**
  * 채널톡 Developer Portal에서 Custom App 생성 및 `App ID`, `App Secret` 발급
  * 필요한 권한(Permission) 설정: `writeGroupMessage` 등
* **Task 1-2. 채널톡 API 통신 모듈 개발 (`services/channel_client.py`)**
  * `issueToken` Native Function을 통한 Channel Token 발급 및 캐싱 (만료 30분 전 갱신 로직)
  * `writeGroupMessage` Native Function 호출 래퍼 작성
* **Task 1-3. 데이터 포맷터 및 URL 퍼블리싱**
  * FOMS `structured_data`를 채널톡 블록 포맷(텍스트)으로 예쁘게 변환하는 Formatter 구현
  * `OrderAttachment`의 R2 객체를 채널톡 렌더링을 위해 Public URL 또는 Presigned URL로 변환
* **Task 1-4. FOMS 이벤트 훅 연동**
  * `erp_orders_structured.py` 등 저장/상태변경 트랜잭션 성공 직후 비동기 큐(또는 백그라운드 스레드)로 채널톡 푸시 트리거
  * 팀별(실측/도면/시공) 채널톡 Group ID를 매핑하여 타겟 라우팅

### 🟡 Phase 2: 채널톡 내 FOMS 퀵 액션 (양방향: Command & WAM)
**목표**: 채널톡 대화창에서 `/foms` 명령어를 통해 FOMS 주문 상세를 확인하고, 간단한 상태 변경을 수행.
* **Task 2-1. Command 등록 및 라우터 구축**
  * 서버 기동 시 `registerCommands`를 호출하여 `/foms 주문번호`, `/foms 실측일정` 등 등록
  * 채널톡에서 오는 `PUT /api/channel/functions` 요청을 받는 Endpoint 구현 (`X-Signature` 서명 검증 필수)
* **Task 2-2. WAM(Web Application Module) 미니 앱 개발**
  * 채널톡 iframe 안에서 열릴 경량화된 React/Vue(또는 순수 JS) UI 구현 (`templates/channel_wam.html` 등)
  * WAM에서 주문 요약 확인, 첨부파일 보기, 상태 변경(드롭다운) 기능 제공
* **Task 2-3. 인증 및 권한 매핑**
  * 채널톡 Manager 정보와 FOMS `User` 정보를 매핑하여, WAM 내 액션 권한(Role) 통제

### 🔴 Phase 3: 수신 및 주문 자동화 (단방향: 채널톡 → FOMS)
**목표**: 채널톡에 올라온 특정 메시지나 양식을 분석해 FOMS의 신규 주문(Draft)으로 자동 접수.
* **Task 3-1. Webhook Endpoint 구축**
  * 채널톡에서 전송하는 메시지 작성 이벤트(UserChat/Group Message) 수신 API 구현
* **Task 3-2. 데이터 파싱 및 자동 접수**
  * 기존 `parse_order_text()` 엔진을 활용하여 채널톡 텍스트에서 정보(고객명, 주소, 제품 등) 추출
  * 추출된 데이터를 바탕으로 FOMS 임시 주문(Draft) 생성 후, 채널톡에 접수 완료 알림 회신

---

## 3. 시스템 아키텍처 (예상)

* **백엔드 (Flask)**: 
  * `apps/api/channel_integration.py` (새 Blueprint 생성)
  * 채널톡 Token 캐싱을 위한 기존 In-memory 또는 캐시 시스템 활용
* **네트워크 보안**: 
  * 외부(채널톡) → 내부(FOMS) 요청 시 `X-Signature` HMAC 검증 방어벽 구축
* **파일 스토리지**:
  * 채널톡은 내부망 이미지를 읽을 수 없으므로, 푸시 시점의 R2 이미지는 일시적으로 접근 가능한 방식(Presigned URL)으로 전달

---

## 4. 필요 환경 변수 (Config)

```env
# 채널톡 연동
CHANNEL_APP_ID=your_app_id
CHANNEL_APP_SECRET=your_app_secret
CHANNEL_SIGNING_KEY=your_signing_key

# 아카이브용 타겟 채팅방(Group) ID
CHANNEL_GROUP_MEASUREMENT=12345
CHANNEL_GROUP_CONSTRUCTION=12346
CHANNEL_GROUP_GENERAL=12347
```