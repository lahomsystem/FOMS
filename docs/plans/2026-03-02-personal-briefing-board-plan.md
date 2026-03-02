---
description: 개인 맞춤형 브리핑 보드(상단 슬라이드 패널) 구축 계획서 (GDM 지휘 - 검증 및 완료본)
date: 2026-03-02
status: IMPLEMENTED
agent: grand-develop-master
---

# 🧑‍💼 FOMS 개인 맞춤형 브리핑 보드 (Personal Briefing Board) 구축 계획서

> **작성자**: Grand Develop Master (개발 총괄 감독관)
> **1:1 소스코드 검증 결과**: **적합(PASS)**. 기존 코드 및 모델(`Order`, `Notification`, `Chat`, `Quest`, `Task`, `Calendar`, `Settlement`)과의 호환성 확인 완료. 
> **추가 분석 반영**: FOMS 내 가용 데이터(`OrderEvent`, `Hold` 상태)를 토대로 브리핑 보드를 더욱 "나의 대시보드"답게 활용할 수 있는 추천 기능을 최종 추가함.

---

## 🔬 1. 현황 분석 및 아키텍처 진단 (1:1 소스코드 리뷰)

### 1.1. 기존 시스템 데이터 소스 매칭 완료
- **주문/업무 흐름**: `Order.status` & `structured_data` (팀별 필터링 기능 확인)
- **알림/채팅**: `Notification` 모델 구조, `ChatRoomMember.last_read_at` 로직 확인
- **결재/작업**: `Order.structured_data.quest` (Quest 로직 확인), `OrderTask` 매칭 확인
- **일정/정산**: `structured_data.schedule` & `settlement.deductions` 구조 검증 완료

### 1.2. UI 진입점 검증
- **`layout.html`**: Bootstrap 5가 이미 반영되어 있으므로, 상단에서 내려오는 `offcanvas-top` 컴포넌트가 최적의 선택임을 재차 확인.
- **방향성 적용**: 사용자의 지시에 맞춰 헤더의 중앙 또는 우측 상단버튼을 누르면 화면 최상단에서 아래로 넓게 패널이 슬라이드 다운되는 구조로 확정.

---

## 🎯 2. 핵심 기능 요구사항 (기존 요구 + 신규 추천)

### 2.1. 기본 요구 기능 (사용자 필수)
1. **📊 [내 업무 스트림] My Work Stream**
   - 현재 단계 기준, 내 팀의 할 일 건수 (예: 영업팀=발주 전 / 도면팀=도면 작업 중 등 단계 노출).
2. **📢 [공지사항] Announcements**
   - 전사 공지 기능. (추천: 기존 `Notification` 모델에 `notification_type='ANNOUNCEMENT'` 데이터를 저장하여 시스템 내 별도 테이블 추가를 방지하는 가벼운 접근 권장).
3. **🚨 [긴급 알림함] Urgent Inbox**
   - 읽지 않은 'ERP 알림(N건)' 및 '미읽음 채팅방(N건)' 합산.
   - **⚠️ (신규) 시각적·청각적 강조 효과**: 사용자 멘션(1:1 호출) 또는 긴급 공지(긴급도 상)가 도착할 경우, 시스템에서 짧고 세련된 **알림음(청각)**을 발생시키고, 헤더의 알림 아이콘/팝업이 **붉은색 펄스(Pulse) 애니메이션(시각)**으로 점멸하여 작업자가 절대 놓치지 않도록 강하게 인지시킵니다.

### 2.2. GDM 분석에 따른 "추가 제안 기능" (FOMS 코드베이스 기반 신규)
4. **🛑 [지연/정체 주의] Stalled & Delayed Orders**
   - **코드베이스 근거**: `Order.status`에 `HOLD` 값이 존재하지 않으므로, 대신 **`OrderEvent` 테이블의 `created_at` 기준으로 일정 기간(예: 3일) 이상 이벤트 변경이 없는 주문**을 정체(Stalled) 건으로 감지. 
   - **동작**: 담당/팀이 '나/내부서'인데 현재 3일 이상 상태 변화가 없는 주문 건을 빨간색으로 표기해, 빠른 병목 해결을 유도합니다.
5. **🕒 [내 최근 작업] My Recent Work (이어하기)**
   - **코드베이스 근거**: `OrderEvent` 테이블 확인 완료 (`models.py` L124-136). `created_by_user_id` 필드로 필터링하여 내가 직접 상태 변경을 발생시킨 가장 최근 주문 3~5건 노출.
   - **효과**: 아침에 출근해서 보드를 열면 어제 작업하던 상세페이지(`erp_drawing_workbench_detail` 등)로 1초 만에 바로 진입(점프) 가능합니다.
6. **📅 [오늘/내일 일정] Schedule**
   - 실측일 및 시공일(`structured_data.schedule`) 중 나와 내 부서 대상 일정.
7. **💸 [비용 청구(AS)] Settlement Alerts**
   - 귀속 대상에 지목된 정산/AS 차감 이슈. (시공 대시보드 연동)
8. **✅ [내 퀘스트/Task] Pending Actions**
   - 미결 퀘스트 승인 대상 건 및 미해결된 'OPEN Task' 관리.
9. **🔗 [빠른 바로가기] Quick Links**
   - 흩어져 있는 대시보드들에 대한 원클릭 서브 아이콘 (시공팀 필터 로직 그대로 적용).

---

## 📐 3. 아키텍처 설계 방향

### 3.1. Frontend (`offcanvas-top` 및 시청각 효과)
- 화면 상단에서 높이 50%~60% 정도를 채우고 열리는 거대한 퀵 뷰포트 사용.
- 내부 구성은 대시보드(Grid/Card) 형식으로, 각 항목의 "건수(숫자 표기)" 중심의 마이크로 위젯 형태로 세팅.
- **시청각 알림 구현**:
  - `layout.html`에 HTML5 `<audio>` 태그를 숨겨서(display:none) 처리해두고, Socket.IO로 '긴급/멘션' 신호 수신 시 `play()` 실행. 기존 `onErpNotification` 핸들러(`layout.html` L388)가 이미 구현되어 있으므로 해당 위치에 삽입 가능 (코드 확인 완료).
  - CSS `@keyframes pulse-danger`를 추가하여 중요 알림 카운트 뱃지에 쿵쾅거리는 시각적 강조 효과 매핑.

### 3.2. Backend (`/api/personal-board/summary`)
- 하나의 단일 API 주소로 위 9가지 항목의 데이터를 모두 연산하여 JSON으로 리턴.
- DB 과부하를 막기 위해 **배치/선택 쿼리**로 효율적으로 집계(`COUNT()`, `GROUP BY`)하고 N+1 쿼리 발생을 원천 차단.

### 3.3. Database
- 추가 테이블 생성 없이 **`Notification` 모델의 `notification_type='ANNOUNCEMENT'`**로 공지사항 처리 로직 구축 확정(가장 경제적).

---

## 📝 4. Phase별 실행 계획 (Execution Roadmap)

### Phase 1: 기반 UI 마련 및 백엔드 단일 API 연결 (시작점)
- `layout.html` 상단에 토글 버튼(가운데 위쪽)과 브리핑 보드용 `<div class="offcanvas offcanvas-top">` 추가.
- `apps/api/personal_board.py` 를 신설하여 `/api/personal-board/summary` 기본 뼈대 API 작성 및 Flask 앱 등록.

### Phase 2: 데이터 쿼리 구축 (내 업무/알림 중심으로)
- 1) 업무 스트림(status), 2) 공지사항(`ANNOUNCEMENT`), 3) 알림/채팅방 카운트용 서버 연산 추가.
- 4) 최근 작업 활동(`OrderEvent`) 불러오기 API 구현.
- 브라우저 로딩 완료 직후 API fetch 후 숫자를 카드형 위젯에 바인딩.

### Phase 3: 고도화된 스케줄 및 퀘스트 데이터 추가
- 실측/시공 스케줄, 퀘스트/Task/정산알림 및 보류(`HOLD`) 건에 대한 카운트 추가 로직 구현.
- 각 위젯 터치 시 즉시 해당 대시보드의 상세 내역 페이지로 하이퍼링크 라우팅 딥링크 제공.

---

## ✅ 5. 1:1 진단 및 향후 방향
기존 문서에 2가지(보류 건 파악, 내 최근작업 이력) 기능이 덧붙어 개인업무 관리가 매우 강력해지는 완전체 기획으로 진화했습니다. 

다음 단계 지시로 **"Phase 1부터 구현 시작"** 명령을 주시면, 즉각 HTML 마크업과 신규 라우터 개발을 진행하겠습니다.

---

## ✅ 6. 구현 완료 (GDM 지휘)

- **Phase 1**: `layout.html` 헤더에 브리핑 보드 토글 버튼(아이콘) 및 `offcanvas-top` 패널 추가. `apps/api/personal_board.py` 신설, `GET /api/personal-board/summary` 뼈대 API 및 Flask 등록. 오프캔버스 열릴 때 API fetch 후 카드 위젯 렌더링.
- **Phase 2**: 내 팀 업무 스트림(단계별 건수), 공지(ANNOUNCEMENT) 건수, 미읽음 알림/채팅 수, 정체(3일 이상 이벤트 없음) 건수, 내 최근 작업(OrderEvent 기반 order_id 목록), OPEN Task 건수 연동. 위젯에 숫자 및 "내 최근 작업" 바로가기 링크 표시.
- **Phase 3**: 오늘/내일 일정(schedule.measurement.date, schedule.construction.date), 비용 청구 알림(settlement.deductions 중 charge_to_user_id 귀속 건수), 위젯별 딥링크(내 업무→/erp/dashboard, 공지/알림→알림 패널, 비용 청구→/erp/completion 등) 적용.
