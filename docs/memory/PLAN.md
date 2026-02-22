# GDM 실행 계획: Phase C·D·Railway 잔여 작업

> **기준일**: 2026-02-22  
> **근거**: `2026-02-22-phase-c-map-design.md`, `2026-02-22-phase-d-direct-upload-design.md`, `2026-02-22-railway-multi-user-scalability-plan.md` 검증 결과

## 1. 개요

계획서 3종 대조 결과, 핵심 코드는 구현 완료. 남은 것은 **Railway 인프라 설정**, **검증·부하 테스트**, **채팅 direct 업로드**이다.

## 2. 실행 순서 (승인 후 차례대로 수행)

| 순서 | 작업 | 계획서 | 담당 | 비고 |
|------|------|--------|------|------|
| 1 | Railway Worker 서비스 추가 + USE_RQ_WORKER=1 | railway §B | 인프라 | 대시보드 수동 |
| 2 | Railway Web Replica 2개 설정 | railway §A | 인프라 | 대시보드 수동 |
| 3 | Phase C 7.3: 지도 동시 40명 부하 테스트 | phase-c §7.3 | 검증 | k6/locust 등 |
| 4 | 채팅 direct upload (백엔드 + UI) | phase-d §3.4, §4.4 | 개발 | **완료** (session/complete·use_direct_upload 전달·Content-Type 허용 목록) |
| 5 | Phase D 6.1~6.3 검증 | phase-d §4.6 | 검증 | 대용량/동시/로컬 (선택) |

## 3. 각 작업 상세

### 3.1 Railway Worker + USE_RQ_WORKER=1 (Railway 대시보드)
- Worker 서비스 추가, Start Command: `rq worker default`
- 환경변수: `USE_RQ_WORKER=1`, `REDIS_URL` 공유

### 3.2 Railway Web Replica 2개
- Web 서비스에서 Replica 2개 설정 (railway.toml/gunicorn -w 2와 별개로 인스턴스 스케일)

### 3.3 Phase C 7.3 부하 테스트
- 지도 API(`/api/erp/map/data` 등) 동시 40명 접속 시나리오
- 응답 시간/오류율 목표: 2초 이내, 오류 0%

### 3.4 채팅 direct upload
- `apps/api/chat/routes.py`: session → complete API 추가
- 채팅 업로드 UI: multipart 대신 direct 플로우 적용

### 3.5 Phase D 검증
- 6.1 대용량 업로드
- 6.2 동시 업로드
- 6.3 로컬 multipart fallback

## 4. 영향 범위

| 작업 | 영향 파일/영역 |
|------|----------------|
| 3.1~3.2 | Railway 대시보드 (코드 변경 없음) |
| 3.3 | 테스트 스크립트 (신규) |
| 3.4 | `apps/api/chat/routes.py`, 채팅 UI 템플릿 |
| 3.5 | 테스트/검증 스크립트 |

## 5. 지도 주소변환 UX 개선 (2026-02-22)

**증상**: 처음 열면 주소변환이 안 되다가, 시간이 지나 웹 새로고침을 해야 정상 표시됨 (Worker가 geocode를 순차 처리해 건당 ~4.5초).

**조치 1 (완료)**: 지도 화면에서 `conversion_status='pending'`인 주문이 있으면 6초 간격으로 자동 폴링(최대 10회).

**조치 2 (신규) - 지도 버튼 누르면 바로 빠르게 변환**:
- **현재**: `api_generate_map`에서 lat/lng 없는 주문은 enqueue만 하고 즉시 반환 → 마커 없음, 폴링 대기.
- **개선**: 지도 API 응답 전에, lat/lng 없는 주문을 **동기 병렬 geocode** (ThreadPoolExecutor, 최대 5건 동시) 처리.
- **제한**: 한 번에 최대 10건까지 동기 처리 (나머지는 기존처럼 enqueue).
- **예상 체감**: 8건 × 2초/5병렬 ≈ 3~4초 후 지도 로드 (기존 36초+ 대비 대폭 단축).
- **영향 파일**: `apps/api/erp_map.py` (api_generate_map)

## 6. 롤백

- 3.1~3.2: Railway에서 Worker/Replica 제거·환경변수 원복
- 3.4: 채팅 multipart 경로 유지, direct는 feature flag
- 3.3·3.5: 검증만 수행, 코드 변경 없음

---

# 계획: 로그인 담당자 필터 + 시공팀 전용 접근 (2026-02-22)

> **요청**: (1) 알림 버튼 왼쪽에 "로그인 담당자만 표시" 토글 버튼 추가, (2) "내 할 일" 기능 적용해 본인 관련 주문/이벤트만 필터, (3) 시공팀은 출고·시공 대시보드만 접근, 두 대시보드에서도 본인 배정 주문만 표시.

## 6.1 관련 코드 리뷰 요약

| 영역 | 파일 | 현황 |
|------|------|------|
| 전역 알림 버튼 | `templates/layout.html` | `global-notification-btn`, `toggleGlobalNotificationPanel()` — 동일 스타일로 "내 할 일" 버튼 추가 |
| 내 할 일 필터 | `apps/erp_drawing_workbench.py` | `mine_only = request.args.get('mine') == '1'`, `my_todo`(도면 담당자/영업 담당) 기준 필터 적용됨 |
| 출고 배정 | `apps/erp_shipment_page.py` | `structured_data.shipment.construction_workers`(시공자 이름 목록)로 배정 관리. `User.name`과 매칭 가능 |
| 시공 대시보드 | `apps/erp_construction_page.py` | 현재 mine/배정 필터 없음. 동일하게 `shipment.construction_workers` + `current_user.name` 매칭 필요 |
| ERP 서브 내비 | `templates/partials/erp_sub_nav.html` | 대시보드/실측/도면작업실/생산/출고/AS/시공 전부 노출. 시공팀은 출고·시공만 노출하도록 조건 분기 필요 |
| 권한 | `services/erp_permissions.py` | `can_edit_erp`: ADMIN 또는 CS/SALES만. 시공팀은 수정 권한 없음(조회만). 접근 경로 제한은 별도 필요 |
| 사용자 팀 | `models.User.team`, `apps/auth.TEAMS` | `CONSTRUCTION` = 시공팀 |

## 6.2 구현 순서

| 순서 | 작업 | 산출물 |
|------|------|--------|
| 1 | **전역 "내 할 일" 버튼** | layout.html: 알림 버튼 왼쪽에 버튼 추가. cookie `erp_mine_only=1` 토글. ERP 페이지 로드 시 cookie 있으면 `mine=1` 기본 적용(또는 리다이렉트) |
| 2 | **출고 대시보드 mine 필터** | erp_shipment_page: `mine=1` 또는 cookie 시 `structured_data.shipment.construction_workers`에 `current_user.name` 포함된 주문만 표시 (이름 정규화: strip, lower 비교) |
| 3 | **시공 대시보드 mine 필터** | erp_construction_page: 동일. `mine=1` 또는 cookie 시 `construction_workers`에 본인 포함된 주문만 표시 |
| 4 | **시공팀 접근 제한** | (a) ERP 진입 시: `user.team == 'CONSTRUCTION'`이면 `/erp/dashboard` → `/erp/construction/dashboard`(또는 출고)로 리다이렉트. (b) 실측/도면/생산/AS/대시보드 라우트에서 CONSTRUCTION 팀이면 403 또는 출고/시공으로 리다이렉트. (c) `erp_sub_nav.html`: 시공팀일 때 출고·시공 링크만 렌더 |
| 5 | **시공팀 데이터 강제** | 출고·시공 대시보드에서 `user.team == 'CONSTRUCTION'`이면 **항상** 본인 배정 주문만 표시(mine 강제, cookie 무관) |
| 6 | **도면작업실 연동** | 도면작업실은 기존 `mine` 쿼리 유지. 전역 cookie 있으면 기본 체크된 상태로 표시 또는 리다이렉트 시 `mine=1` 추가 |

## 6.3 영향 파일

| 파일 | 변경 내용 |
|------|-----------|
| `templates/layout.html` | 전역 "내 할 일" 버튼 + JS(cookie 토글, ERP 페이지 이동 시 mine=1 반영) |
| `apps/erp_shipment_page.py` | mine/cookie 판단, CONSTRUCTION 팀이면 mine 강제, construction_workers 필터 |
| `apps/erp_construction_page.py` | mine/cookie 판단, CONSTRUCTION 팀이면 mine 강제, construction_workers 필터 |
| `templates/partials/erp_sub_nav.html` | `current_user.team == 'CONSTRUCTION'`일 때 출고·시공만 노출 |
| `apps/erp_dashboard.py` | CONSTRUCTION 팀 접근 시 출고 또는 시공 대시보드로 리다이렉트 |
| `apps/erp_measurement_dashboard.py` 등 | CONSTRUCTION 팀 접근 시 403 또는 리다이렉트 (공통 before_request 또는 데코레이터 검토) |

## 6.4 시공 배정 매칭 규칙

- **출고/시공 "본인 배정"**: `order.structured_data.shipment.construction_workers`(문자열 목록)에 `current_user.name`이 포함된 경우. 비교 시 `strip()` 및 소문자 통일(`lower()`) 권장하여 "홍길동" vs " 홍길동 " 등 허용.

## 6.5 롤백

- cookie 제거 시 전체 표시로 복귀. 시공팀 제한 제거 시 기존처럼 모든 ERP 메뉴 접근 가능.

---

## 7. 출고 대시보드 시공자 다건 배정 (2026-02-22)

**요청**: 시공자는 여러 건 배정 가능. 작업자 목록에서 배정된 시공자 제외하지 않음. 여러 건 배정 시 이름 옆에 배정 건수 표시 (예: "고동일 3").

**완료**:
- `getAssignedWorkerNameSet` → `getAssignedWorkerCountMap` (시공자별 배정 건수 맵)
- `fillDatalist`: 제외 로직 제거, 2건 이상일 때 "고동일 3" 형식 표시
- `showSavedDropdown`: construction_workers 필터 제거, 건수 표시 추가
- `isDuplicateWorkerName` 제거, blur/callback에서 중복 차단·알림 제거
