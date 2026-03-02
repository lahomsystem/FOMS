---
title: "긴급 알림(공지/멘션) 강제 인지 및 브리핑 보드 연동 계획"
date: 2026-03-02
status: PLAN_REVIEWED
reviewed_by: AI Double-Check
---

# 긴급 알림 및 브리핑 보드 연동 시스템 구축 계획

## 1. 개요 및 목적
현재 FOMS의 알림 시스템은 종 모양 아이콘의 단순 숫자 증가와 리스트 추가에 머물러 있어, **긴급한 공지나 1:1 멘션** 발생 시 즉각적인 업무 인지가 어렵습니다.
이를 해결하기 위해, 새로 구축된 **개인 브리핑 보드 열기 버튼(Chevron)**과 **보드 내 위젯**에 **시각·청각적 이펙트**를 추가하여 사용자가 즉각적으로 반응할 수 있는 '강제 인지 UX'를 도입합니다.

### 1-1. 현황 분석 (더블체크 결과)

**이미 구현된 부분:**
- `layout.html` > `triggerUrgentBriefingAlert(data)` 함수: 오디오 경고음, 버튼 빨간 펄스, 아이콘 `fa-exclamation-triangle` 스와핑, 10초 자동 해제 **구현 완료**
- `services/realtime_notifications.py` > `emit_erp_notification_to_users(user_ids, payload)`: Socket.IO `user_{id}` room 전송 파이프라인 **동작 중**
- 클라이언트 Socket.IO 리스너: `data.urgent === true` 분기 처리 **동작 중**
- 알림 API: `/erp/api/notifications` (목록), `/badge` (카운트), `/<id>/read`, `/read-all` **기존 운영 중**

**미구현 (이번 계획 범위):**
- 백엔드에서 `is_urgent` 플래그를 포함한 알림 생성/발송 기능 없음
- 관리자 공지 발송 UI 없음
- `Notification` 모델에 `is_urgent` 컬럼 없음
- `order_id`가 NOT NULL → 주문 무관 전체 공지 불가
- `target_user_id` 컬럼 없음 → 특정 사용자 직접 지정 불가

---

## 2. DB 모델 변경 (Notification 테이블)

### 현재 컬럼
| 컬럼 | 타입 | 비고 |
|------|------|------|
| id | Integer PK | |
| order_id | Integer FK (NOT NULL) | **nullable로 변경 필요** |
| notification_type | String(50) | DRAWING_TRANSFERRED, STAGE_CHANGED, QUEST_ASSIGNED, AS_REQUIRED |
| target_team | String(50) | CS, HAUDD, SALES 등 |
| target_manager_name | String(100) | 특정 영업사원명 |
| title | String(200) | |
| message | Text | |
| created_by_user_id | Integer FK | |
| created_by_name | String(100) | |
| is_read | Boolean | |
| read_at | DateTime | |
| read_by_user_id | Integer FK | |
| created_at | DateTime | |

### 추가/변경할 컬럼
| 변경 | 컬럼 | 타입 | 설명 |
|------|------|------|------|
| **ALTER** | order_id | Integer FK **nullable=True** | 전체 공지는 주문 무관 |
| **ADD** | is_urgent | Boolean default=False | 긴급 여부 |
| **ADD** | target_user_id | Integer FK (nullable) | 특정 사용자 직접 지정 |
| **ADD** | target_type | String(20) default='ORDER' | 'ALL'(전체), 'TEAM'(팀 지정), 'USER'(특정인 지정), 'ORDER'(주문 관련) 기능 명확화 |

### notification_type 확장
| 기존 값 | 용도 |
|---------|------|
| DRAWING_TRANSFERRED | 도면 전달됨 |
| DRAWING_REVISION | 도면 수정 요청 |
| STAGE_CHANGED | 단계 변경됨 |
| QUEST_ASSIGNED | 퀘스트 할당됨 |
| AS_REQUIRED | AS 필요 |

| **신규 값** | 용도 |
|------------|------|
| URGENT_ANNOUNCEMENT | 관리자 긴급 공지 |
| URGENT_MENTION | 긴급 멘션(호출) |
| ANNOUNCEMENT | 일반 공지 |

---

## 3. 백엔드 API 구축

### A. 관리자 전용 '공지/알림 발송' API
- **경로**: `POST /erp/api/notifications/send`
- **권한**: ADMIN, MANAGER 전용
- **파라미터**:
  ```json
  {
    "title": "공지 제목",
    "message": "공지 내용",
    "is_urgent": true,
    "target_type": "ALL" | "TEAM" | "USER",
    "target_team": "SALES",
    "target_user_ids": [1, 2, 3],
    "order_id": null
  }
  ```
- **처리 로직**:
  1. `target_type`에 따라 대상 사용자 ID 목록 산출
  2. `Notification` 레코드 생성 (order_id=null 허용)
  3. `emit_erp_notification_to_users(user_ids, {'urgent': is_urgent, ...})` 호출
  4. 이미 구현된 클라이언트 `triggerUrgentBriefingAlert()`가 자동 반응

### B. 주문 상세 '긴급 멘션(호출)' API
- **경로**: `POST /erp/api/orders/<order_id>/urgent-mention`
- **파라미터**:
  ```json
  {
    "target_user_id": 5,
    "message": "도면 확인 부탁드립니다"
  }
  ```
- **처리 로직**:
  1. `Notification` 생성 (notification_type=URGENT_MENTION, is_urgent=True, order_id 연결)
  2. Socket.IO 긴급 이벤트 전파 (payload에 order_id 포함 → 클릭 시 딥링크)

> **NOTE**: `@사용자이름` 텍스트 파싱 + 자동완성 UI는 복잡도가 높아 2차 계획으로 분리. 1차에서는 전용 '동료 호출' 버튼 방식으로 구현.

### C. 기존 알림 조회 로직(쿼리) 업데이트 필수
- **대상 파일**: `apps/api/notifications.py` 및 `apps/api/personal_board.py`, `models.py`
- **수정 내용**: 
  1. `Notification` 조회 쿼리의 `or_()` 조건절에 `target_user_id == user.id` 조건 추가 (특정인 대상 멘션/수신 확인)
  2. 전체 공지를 누구나 볼 수 있도록 `target_type == 'ALL'` 조건 추가 (현재 코드는 team이나 manager_name이 일치하지 않으면 아예 필터링됨)
  3. `models.py`의 `Notification.to_dict()` 에 `is_urgent`, `target_user_id`, `target_type` 등의 신규 필드 반환 추가
  4. 딥링크 로직(`_resolve_notification_deep_link` 등)에서 `order_id`가 `None`인 경우 오류가 나지 않도록 안전(None-safe) 처리 보강.

---

## 4. 프론트엔드 보강 (layout.html)

### A. 기존 구현 유지 (변경 불필요)
- `triggerUrgentBriefingAlert(data)` - 오디오, 버튼 펄스, 아이콘 스와핑 **그대로 활용**
- Socket.IO `erp_notification` 리스너의 `data.urgent` 분기 **그대로 활용**

### B. 추가 구현 필요
1. **브리핑 보드 내 긴급 배너**: 오프캔버스 최상단에 붉은 배너 영역 추가
   - 긴급 알림 존재 시 `[긴급] 관리자 공지: ...` 또는 `[긴급 멘션] OOO님이 #1245 주문에서 호출했습니다` 표시
   - 클릭 시 해당 주문으로 딥링크 (order_id가 있는 경우)
2. **딥링크 지원**: 알림 클릭 시 `window.location = '/erp/dashboard/' + order_id` 이동
3. **개인 보드 API 확장**: `GET /api/personal-board/summary` 응답에 `urgent_notifications` 리스트 추가 (제목, 메시지, order_id, 생성시각)

---

## 5. 관리자 UI (발송 화면)

### 위치
- 기존 관리자 메뉴 (`/admin`) 하위에 '공지/알림 발송' 탭 추가
- 또는 독립 페이지 `/admin/notifications`

### 화면 구성
| 요소 | 설명 |
|------|------|
| 제목 입력 | 알림 제목 (200자) |
| 내용 입력 | textarea, 선택 사항 |
| 대상 선택 | 라디오: 전체 / 특정 팀 / 특정 사용자 |
| 팀 선택 | 드롭다운 (대상=팀일 때) |
| 사용자 선택 | 멀티 셀렉트 (대상=사용자일 때) |
| 긴급 여부 | 체크박스 |
| 발송 버튼 | POST → `/erp/api/notifications/send` |

---

## 6. 실행 순서 (수정됨)

> 기존 계획의 "Step 1: 프론트엔드 선행"은 이미 구현 완료. 백엔드부터 시작.

| 단계 | 내용 | 비고 |
|------|------|------|
| **Phase 1** | DB 마이그레이션 | `order_id` nullable, `is_urgent`, `target_user_id`, `target_type` 추가 및 `models.py` 업데이트 |
| **Phase 2** | 조회 API 쿼리 보강 | 기존 알림/브리핑보드 API에서 `target_user_id`, `target_type='ALL'`, `order_id IS NULL`을 커버하도록 쿼리 업데이트 |
| **Phase 3** | 발송 API 구축 | `POST /erp/api/notifications/send` + Socket.IO 연동 |
| **Phase 4** | 관리자 발송 UI | `/admin/notifications` 화면 |
| **Phase 5** | 브리핑 보드 긴급 배너 | 오프캔버스 상단 긴급 알림 리스트 + 딥링크 |
| **Phase 6** | 주문 상세 긴급 멘션 | '동료 호출' 버튼 + `POST /erp/api/orders/<id>/urgent-mention` |
| *(2차)* | @멘션 텍스트 파싱 | 자동완성 UI, 텍스트 내 @태그 인식 |

---

## 7. 더블체크 변경 이력

| 항목 | 원본 | 수정 | 사유 |
|------|------|------|------|
| 현황 분석 | 없음 | 1-1절 추가 | 이미 구현된 부분 명시 (중복 작업 방지) |
| DB 모델 | `is_urgent` 언급만 | 상세 테이블 작성 | `order_id` nullable, `target_user_id` 추가 필요 발견 |
| notification_type | 세분화 언급 | 기존+신규 값 목록 명시 | 기존 값 누락 방지 |
| @멘션 | 1차 범위 | 2차로 분리 | 텍스트 파싱+자동완성 복잡도 높음 |
| 실행 순서 | FE 선행 | BE 선행으로 변경 | 프론트엔드 긴급 UX 이미 구현됨 |
| 프론트엔드 | 전체 구현 계획 | 기존 유지 + 추가분만 명시 | 중복 개발 제거 |
| 발송 API | 가칭만 | 경로·파라미터·로직 구체화 | 구현 가능한 수준으로 상세화 |
