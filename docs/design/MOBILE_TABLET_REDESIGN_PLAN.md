# FOMS 모바일·태블릿 UI/UX 리디자인 마스터 계획서

> 작성: 2026-05-28 | 버전: 1.0 | 작성자: Claude Opus 4.7 (FOMS Master Architect 모드)
> 후속 문서: `MOBILE_TABLET_DESIGN_SYSTEM.md`, `COMPONENT_LIBRARY_MOBILE.md`, `MIGRATION_ROADMAP.md`
> 목업: `docs/design/mockups/*.html`

---

## Executive Summary

FOMS는 현재 데스크톱 ERP UI를 모바일·태블릿에 그대로 축소해서 보여주는 상태다. 그러나 **인프라의 70%는 이미 만들어져 있다** — `ERP_MOBILE_V2_ENABLED` 환경변수가 기본 `false`로 잠겨 있고, ChannelTalk 풍 뷰어(`channel/wam/**`)와 ERP 모바일 셸이 서로 통합되지 않은 채 병존하기 때문이다. 본 계획은 이 두 패러다임을 통합하고, 비효율 결함 2건과 기존 모바일 카드 gap 3건을 P0에서 제거하며, 태블릿 가로 1024px+에서 master-detail split-view를 신설한다.

핵심 발견 3가지:

1. **ERP 모바일 V2 인프라는 이미 존재하지만 기본값은 false로 유지한다.** cohort flag로 Day 1→3→7 점진 활성화하며, 도면·AS·시공 페이지의 모바일 카드도 **이미 존재**한다(도면 `workbench_dashboard_body.html:314`, AS `as_dashboard_body.html:364`, 시공 `dashboard_body.html:121`). P0 작업은 신규 구현이 아니라 **audit + gap patch**(단계 색 배지 표준화, thumbnail 추가, 필터 통합). [v1.0 audit 오류 정정 — v1.1]
2. **모바일·태블릿은 별도 패러다임이 아니다.** 모바일=세로 단일 컬럼, 태블릿 가로=360px 마스터 + fluid 상세. 동일 컴포넌트가 컨테이너 쿼리로 자동 적응한다.
3. **erporder 폼은 39~44개 필드를 단일 스크롤로 노출한다.** Sticky bottom CTA·multi-step accordion·자동저장·카메라 직접 캡처가 모두 부재. 폼 입력 효율이 가장 큰 손실 지점이다.

본 계획의 산출물은 다음과 같다:

- **DESIGN.md** — 통합 디자인 시스템(토큰, 타이포, 간격, 컴포넌트 사양)
- **HTML 목업** — 모바일·태블릿 대표 화면 8장 (인터랙티브)
- **컴포넌트 라이브러리 초안** — Bootstrap 5 + 커스텀 14개 컴포넌트 (C14 product item accordion 포함)
- **마이그레이션 로드맵** — P0(즉시)·P1(1~2주)·P2(분기)

---

## 1. 사용자 페르소나 & 시나리오 (FOMS 특화)

채널톡 스크린샷과 실 데이터를 통해 도출한 3개 페르소나:

### P1. 안중훈 — 현장 영업·시공 담당 (Primary, 60%)
- 디바이스: 갤럭시 S 시리즈 (안드로이드, 6.1~6.7인치)
- 사용 환경: 현장 (조명·소음·장갑·먼지), 차량 내 (운전 직후), 사무실 (잠깐)
- 핵심 행동:
  - 채널톡 방을 ERP처럼 사용 — 방=워크플로우 단계, 메시지=주문 정보 카드
  - "발주방"·"도면방"·"시공현황_재판부"에 새 주문 정보 + 도면 사진 + 현장 사진 게시
  - 검색으로 "고객명/연락처/주소"로 과거 주문 찾기
  - 외근 중 빠른 상태 확인 (실측일·시공일·잔금 여부)
- 가장 큰 통증:
  - 사진 첨부 — Ctrl+V로 클립보드 paste 시도하나 모바일은 불가능
  - 주소·연락처 입력 시 자동완성 부재
  - 폼 길어서 한 화면에 다 안 보임

### P2. 사무실 보조 — 발주·일정 관리 (Secondary, 30%)
- 디바이스: 아이패드 또는 갤럭시 탭 (10~12인치, 가로 모드 우선)
- 사용 환경: 사무실 책상
- 핵심 행동:
  - 일일 발주 목록 확인 + 입력
  - 도면 검토 + 승인
  - 일정 조율 (실측·시공·상차)
- 가장 큰 통증:
  - 태블릿 전용 레이아웃 부재 — 모바일 뷰가 그대로 늘어남
  - 가로 모드에서 좌측 리스트와 우측 상세를 동시에 못 봄

### P3. 관리자 — 대시보드·이력 검색 (Tertiary, 10%)
- 디바이스: PC + 모바일 혼용
- 핵심 행동: 전체 큐 모니터링, KPI 확인, 이력 검색
- 가장 큰 통증: 모바일에서 13컬럼 테이블 가로 스크롤만 가능

### 핵심 사용 시나리오 5가지

| # | 시나리오 | 디바이스 | 빈도 | 현재 상태 | 목표 |
|---|---|---|---|---|---|
| S1 | 현장에서 새 AS 접수 + 도면 사진 첨부 | 모바일 | 매일 5~10건 | Ctrl+V 안 됨, 폼 길어서 키보드 가림 | 카메라 직접 캡처, 마법사 4-step, sticky CTA |
| S2 | 출고 임박 주문 확인 | 모바일·태블릿 | 매일 | 13컬럼 가로 스크롤만 가능 | 카드 리스트 + 색상 배지 + sticky 필터 |
| S3 | 도면 검토 + 승인 | 태블릿 가로 | 매일 | 도면 페이지가 lg<992px에서 표시 안 됨 | split-view (좌 리스트 + 우 도면 zoom) |
| S4 | 고객 전화 받고 과거 이력 검색 | 모바일 | 주 10건 | 13컬럼 테이블, 모바일 카드 부분만 표시 | 검색 우선 화면, KV 카드, tel: 딥링크 |
| S5 | 일정 변경 (실측일·시공일) | 모바일·태블릿 | 매일 | text input + placeholder "여러 날짜 가능" | native date picker + 빠른 수정 |

---

## 2. 디자인 원칙

이 프로젝트의 모든 결정은 다음 5가지 원칙에 따른다. 충돌 시 위 원칙이 우선한다.

### 원칙 1. **현장 제일 (Field-First)**
> 모든 화면은 한 손·장갑·햇빛 아래에서도 동작해야 한다.

- 터치 타깃 최소 48×48px (M3 기준, HIG 44pt 초과). 아이콘 버튼은 최소 44px.
- 글자 최소 16px (iOS 줌 방지 + 햇빛 가독). 보조 텍스트도 14px 미만 금지.
- 색 대비 WCAG AA (4.5:1) 보장. 옥외 환경 고려 AAA(7:1) 우선.
- 햅틱 피드백: 액션 성공·경고에서 vibrate 짧게 (Web Vibration API).

### 원칙 2. **데이터 우선 (Data-First, Chrome-Light)**
> 화면의 70% 이상은 사용자 데이터여야 한다. 크롬(헤더·푸터·여백)은 30% 이하.

- 헤더 높이 48~52px (현재 56px+ → 축소).
- 카드 패딩 12px (Bootstrap 기본 16px 대비 축소).
- 색상은 데이터 강조(상태·뱃지)에만 사용. 크롬은 무채색.
- 정보 밀도: 모바일 한 화면 4~5건 카드 / 태블릿 가로 6~8건.

### 원칙 3. **단일 진실 (Single Source of UI)**
> ERP 셸과 WAM 뷰어를 분리하지 않는다. 한 컴포넌트가 모든 컨텍스트에서 동작한다.

- 토큰 단일화: `--foms-*` 네임스페이스 하나로 erp-pro·mobile·channel 흡수.
- 매크로 단일화: `_kv_list.html`, `_attachment_grid.html`, `_sticky_action_bar.html`을 공용 partial로 승격.
- 다크모드는 토큰 레벨에서 자동 해결 (별도 CSS 파일 금지).

### 원칙 4. **사진 = 1급 데이터 (Photo as First-class)**
> 가구 시공·도면 ERP에서 사진은 텍스트보다 중요하다. 사진은 항상 thumbnail·lightbox·copy URL 제공.

- 모든 file input에 `capture="environment"` 자동 부착.
- 사진 그리드는 carousel·zoom·메타 (촬영일·위치)와 짝.
- AS 접수 paste 모달은 **카메라 우선 + paste 보조** 구조로 역전.

### 원칙 5. **점진 (Progressive Enhancement)**
> SPA 풀-리라이트 금지. 기존 Flask + Jinja2 위에 HTMX 2.0 + Alpine.js를 점진 도입.

- Phase 1: 환경변수 ON + 누락 카드 페이지 3종 추가
- Phase 2: HTMX hx-boost로 nav 탭 전환 fragment swap
- Phase 3: Alpine.js로 폼 상태 관리, Service Worker로 캐시
- 어떤 phase든 JS 비활성 환경에서 폼 제출은 작동해야 함 (서버 렌더 fallback)

---

## 3. 정보 구조 (IA)

### 3.1 모바일 (≤767px, 세로 단일 컬럼)

```
┌─────────────────────────┐
│  Sticky Header (48px)   │  ← 페이지명·검색·메뉴
│  ─────────────────────  │
│  Filter Chips (sticky)  │  ← 단계·기간·담당
│  ─────────────────────  │
│                         │
│   Queue Card #1         │  ← 큐 카드 (120~140px)
│                         │     - 단계 배지
│   Queue Card #2         │     - 고객명 / 연락처
│                         │     - 핵심 일정
│   Queue Card #3         │     - 다음 액션 CTA
│                         │     - 첨부 카운트
│   ...                   │
│                         │
│  ─────────────────────  │
│  FAB (+) 신규 주문      │  ← 우하단, 56×56px
│  ─────────────────────  │
│  Bottom Nav (60+SA px)  │  ← 5탭 + 배지 카운트
└─────────────────────────┘
```

**Bottom Nav 5탭 (모바일·태블릿 세로 공용)**:
1. **홈** — 전체 큐 (단계 미지정 또는 RECEIVED) - 미처리 배지
2. **실측** — 측정·도면 작업 - 오늘 일정 배지
3. **생산·출고** — 생산·출고·상차 - 출고 임박 배지
4. **시공·AS** — 시공·완료·AS - 오늘 시공 배지
5. **더보기** — 이력 검색·설정·로그아웃·드로어 메뉴

### 3.2 태블릿 가로 (≥1024px, master-detail split-view)

```
┌────────────────────────────────────────────────────────────┐
│  Sticky Header (56px)  [브랜드] [검색...] [알림] [프로필]   │
├──────────────┬─────────────────────────────────────────────┤
│              │                                             │
│  Master List │  Detail Panel                               │
│  (360px)     │  (fluid, min 600px)                         │
│              │                                             │
│  Filter Chip │  ┌─────────────────────────────────────┐    │
│  ──────────  │  │ 주문 헤더 (배지·CTA)              │    │
│  Queue Card  │  ├─────────────────────────────────────┤    │
│  Queue Card  │  │ KV 리스트 (고객·주소·전화·일정)    │    │
│  Queue Card  │  ├─────────────────────────────────────┤    │
│  Queue Card  │  │ 첨부 그리드 (도면·사진)             │    │
│  ...         │  ├─────────────────────────────────────┤    │
│              │  │ 타임라인                            │    │
│  ──────────  │  └─────────────────────────────────────┘    │
│  FAB (+)     │                                             │
├──────────────┴─────────────────────────────────────────────┤
│  Side Tab Strip (40px)  [홈][실측][생산·출고][시공·AS][더보기]│
└────────────────────────────────────────────────────────────┘
```

- 가로 모드: split-view 활성, 하단 탭이 측면 탭으로 회전
- 세로 모드: 단일 컬럼 (모바일과 동일), 하단 탭 유지
- 회전 감지: `matchMedia('(orientation: landscape)')` + container query

### 3.3 태블릿 세로 (768~1023px)

모바일과 동일한 단일 컬럼. 단:
- 큐 카드 너비 600px max, 중앙 정렬
- 폰트·간격 1.05~1.1배 확대
- 한 화면 카드 6~8건 노출

### 3.4 ERP 대시보드 메뉴 (사용자 sub order #6 반영)

모바일·태블릿에서는 **ERP 대시보드 메뉴만 노출**. 다른 전역 nav(설정·관리·통계)는 "더보기" 탭 내부로 이관.

```
[Bottom Nav 5탭 = ERP 워크플로우 단계 그룹]
홈 → RECEIVED·HAPPYCALL (접수·해피콜)
실측 → MEASURE·DRAWING (실측·도면)
생산·출고 → CONFIRM·PRODUCTION·shipment (확정·생산·출고)
시공·AS → CONSTRUCTION·CS·COMPLETED (시공·AS·완료)
더보기 → 이력 검색·관리자 메뉴·로그아웃
```

---

## 4. 디자인 시스템 핵심

상세는 `MOBILE_TABLET_DESIGN_SYSTEM.md` 참조. 여기서는 결정만 요약.

### 4.1 색상 토큰 통합

- 단일 네임스페이스 `--foms-*`로 흡수.
- 다크모드는 `[data-theme="dark"]` 속성으로 토큰 값만 swap.
- Primary: 기존 erp-pro `#5a67d8` (FOMS 퍼플) 유지.
- Semantic: success(#38a169), warning(#d69e2e), danger(#e53e3e), info(#3182ce).
- Surface: 라이트 #ffffff/#f7f8fa/#eef0f3 3단계, 다크 #0f1115/#16191f/#1d2128 3단계.

### 4.2 타이포

- 한글: Pretendard (이미 시스템 폰트 fallback에 포함 검토). 영문: Inter.
- 크기: 12 / 14 / 16 (base) / 18 / 20 / 24 / 28 / 32.
- 줄간격: 본문 1.55, 헤더 1.25.
- font-size: 모바일 base 16px 고정 (iOS 자동 줌 방지).

### 4.3 간격 (4pt grid)

- 4 / 8 / 12 / 16 / 20 / 24 / 32 / 48.
- 카드 패딩 12 (모바일) / 16 (태블릿).
- 섹션 간격 16 (모바일) / 24 (태블릿).

### 4.4 라운드·그림자

- 라운드: 6 (input·badge) / 10 (card·modal) / 16 (FAB).
- 그림자: sm (`0 1px 2px rgba(0,0,0,.04)`), md (`0 4px 12px rgba(0,0,0,.08)`), lg (`0 8px 24px rgba(0,0,0,.12)`).

### 4.5 모션

- duration: 120ms (instant) / 200ms (default) / 320ms (emphasized).
- easing: `cubic-bezier(.2,.8,.2,1)` (M3 emphasized).
- `prefers-reduced-motion` 존중.

### 4.6 Breakpoint 단일화

기존 8종 → 4종으로 압축:
- `--bp-sm: 576px` (스마트폰 가로)
- `--bp-md: 768px` (태블릿 세로 시작)
- `--bp-lg: 1024px` (태블릿 가로 / split-view 시작)
- `--bp-xl: 1280px` (작은 데스크톱)

기존 991.98 / 992 / 993 1px 오프바이원 정리.

---

## 5. 컴포넌트 핵심 14종

| # | 컴포넌트 | 용도 | 신규/기존 |
|---|---|---|---|
| C01 | `<foms-app-shell>` | 헤더·바디·바텀탭 통합 셸 | 통합 (기존 erp_mobile_shell + WAM 통합) |
| C02 | `<foms-bottom-nav>` | 5탭 + 미처리 배지 | 확장 (배지 추가) |
| C03 | `<foms-side-tab>` | 태블릿 가로 측면 탭 | 신규 |
| C04 | `<foms-master-list>` | 가로 split-view 좌측 360px | 신규 |
| C05 | `<foms-queue-card>` | 주문 카드 (다목적) | 확장 |
| C06 | `<foms-kv-row>` | Key-Value 행 (딥링크 통합) | 통합 (WAM macro 승격) |
| C07 | `<foms-attachment-grid>` | 첨부 썸네일 + 라이트박스 | 통합 (WAM 승격) |
| C08 | `<foms-sticky-action-bar>` | 하단 sticky CTA | 통합 (WAM 승격) |
| C09 | `<foms-wizard-stepper>` | 신규 주문 4-step | 신규 |
| C10 | `<foms-filter-drawer>` | offcanvas 필터 | 기존 |
| C11 | `<foms-search-overlay>` | 풀스크린 검색 | 신규 |
| C12 | `<foms-photo-capture>` | 카메라 직접 캡처 + paste | 신규 (AS 모달 대체) |
| C13 | `<foms-status-badge>` | 단계·경보 배지 | 기존 표준화 |
| C14 | `<foms-product-item-accordion>` | 제품 항목 인라인 편집 + W·D·H/spec_rows | 신규 (v1.1) |

상세 props·slot·이벤트는 `COMPONENT_LIBRARY_MOBILE.md` 참조.

---

## 6. 화면별 리디자인 명세

각 화면의 변경점만 요약. 상세 와이어프레임은 `mockups/*.html` 참조.

### 6.1 NAV (전 화면 공통)

| 항목 | 현재 | 신규 |
|---|---|---|
| 글로벌 nav | 768px 이하 햄버거 | 모바일·태블릿에서 **숨김** (사용자 sub order #6) |
| ERP sub nav | 992px 이하 햄버거 | **bottom nav 5탭**으로 대체 |
| 햄버거 → 드로어 | offcanvas-bottom | **유지** (더보기 탭 내부) |
| 배지 카운트 | 없음 | **신규** — context_processor에서 stage별 미처리 건수 주입 |
| 태블릿 가로 | 부재 | **신규** — 측면 측면 측면 탭 strip (40px) |
| 충돌 영역 768~992 | 글로벌 nav + ERP shell 동시 표시 | 단일 컴포넌트로 해소 |

**구현**:
- `templates/partials/shared/foms_app_shell.html` 신규 (단일 진입점)
- `static/css/foundation/foms-shell.css` 신규
- `ERP_MOBILE_V2_ENABLED` 기본값은 `false` 유지. `FOMS_V3_SHELL_COHORT` user id 목록으로 Day 1→3→7 cohort 점진 출시.

### 6.2 ERP 대시보드 (홈)

| 항목 | 현재 | 신규 |
|---|---|---|
| 정보 표시 | 13컬럼 테이블 + 부분 카드 | 카드 리스트 단일 |
| 카드 내 표시 | 단계·고객·일정·주소 | **단계 배지 + 고객(굵게) + 일정 + 다음 액션 CTA + 첨부 카운트 + 경보** |
| 검색 | 텍스트 입력 | **검색 오버레이** (full-screen) — 고객명·전화·주소·주문번호 통합 |
| 필터 | offcanvas 작동 | **유지 + 칩 sticky** (적용된 필터 visible) |
| 정렬 | 컬럼 클릭 | **드롭다운 칩** (최신순·일정순·금액순) |
| 무한스크롤 | 페이지네이션 | **IntersectionObserver 무한스크롤** + sticky 페이지 인디케이터 |
| 빈 상태 | 빈 테이블 | **일러스트 + CTA** (필터 초기화·신규 주문) |

### 6.3 도면 작업실 (P0 — 현재 모바일 사용 불가)

| 항목 | 현재 | 신규 |
|---|---|---|
| 모바일 표시 | lg<992 테이블 숨김 + 대체 없음 | **카드 리스트 신설** |
| 도면 미리보기 | 카드 내 미표시 | **카드 상단 16:9 첨부 영역** (큰 도면 1장 + n개) |
| 도면 zoom | 모바일 미지원 | **pinch-zoom 라이트박스** + 회전 + 다운로드 |
| 승인 액션 | 데스크톱만 | **카드 swipe-action** (왼쪽 swipe → 승인, 오른쪽 → 반려) |
| 태블릿 가로 | 없음 | **split-view** (좌 리스트 360, 우 도면 zoom + 메타) |

### 6.4 erporder 입력·수정 (P0 — 가장 큰 통증)

**전면 재설계**. 단일 스크롤 폼 → **4-step Wizard + 인라인 편집 hybrid**.

신규 주문 작성 흐름:
```
Step 1. 기본 정보 (5필드)
  - 고객명 / 연락처 / 발주사 / 주소 / 접수일
  - "전화부에서 가져오기" 버튼 (Contact API)
  - Sticky bottom: [취소] [다음 →]

Step 2. 제품 항목 (반복 가능)
  - 제품명 / 규격 / 색상 / 옵션 / 손잡이 / 금액
  - 사진·도면 첨부 (카메라 직접)
  - "+ 항목 추가" 풀-너비 버튼
  - Sticky bottom: [← 이전] [다음 →]

Step 3. 일정·담당
  - 실측일·실측시간 / 시공일·시공시간 / 담당자
  - native date·time picker
  - Sticky bottom: [← 이전] [다음 →]

Step 4. 확인·저장
  - 전체 요약 (수정 가능 인라인)
  - 금액 합계·예약금·잔금
  - Sticky bottom: [← 이전] [저장]
```

기존 주문 수정 흐름:
- **인라인 편집** (필드 탭 → 즉시 편집 → blur 시 자동저장)
- 마법사 없음. 모든 필드 동시 visible.
- 저장 버튼 없음 (자동저장 + 토스트 "저장됨")

**자동저장**:
- `localStorage` 키 `foms.draft.{order_id|new}`로 매 5초 또는 blur 시 백업
- 페이지 이탈 시 `navigator.sendBeacon` 으로 서버 draft 저장
- 복귀 시 토스트 "이전에 작성하던 내용이 있습니다. 복구할까요?"

**카메라 직접 캡처**:
- 모든 file input에 `accept="image/*" capture="environment"` 부착
- "사진 촬영" 버튼 = file input 위의 label
- "파일에서 선택" 보조 버튼
- "복사된 이미지 붙여넣기" 보조 버튼 (PC에서만 visible)

### 6.5 AS 접수 모달 (P0 — 모바일 작동 불가)

현재 Ctrl+V paste 기반 → **카메라 우선 + paste 보조 역전**.

```
┌─────────────────────────────────┐
│  AS 접수                  ✕     │
├─────────────────────────────────┤
│                                 │
│  📷  [사진 촬영]                │  ← 풀-너비 primary
│  🖼  [갤러리에서 선택]          │
│  📋  [복사한 이미지 붙여넣기]   │  ← PC에서만 visible
│                                 │
│  ─── 첨부됨 ───────────────────  │
│  [thumbnail] [thumbnail] [+]    │
│                                 │
│  ─── 내용 ──────────────────── │
│  [고객 요청 내용 textarea]      │
│                                 │
├─────────────────────────────────┤
│  [취소]              [접수]     │  ← sticky bottom
└─────────────────────────────────┘
```

### 6.6 검색

전역 검색 = **풀스크린 오버레이**.

```
┌─────────────────────────────────┐
│  ← [검색어 입력]              ✕ │
├─────────────────────────────────┤
│  최근 검색                       │
│  • 고명옥                        │
│  • 010-2690-2242                 │
│  • 안양시 충훈로                 │
│  ─────────────────────────────  │
│  자동완성 결과                   │
│  [고객 카드]                     │
│  [주문 카드]                     │
│  [주소 카드]                     │
└─────────────────────────────────┘
```

- debounce 200ms
- 결과 그룹: 고객 / 주문 / 도면 (탭)
- 키보드 첫 단어 입력 시 가장 빈도 높은 결과 prefetch

---

## 7. 접근성·성능·국제화

### 7.1 접근성 (WCAG 2.2 AA)

- 색 대비 4.5:1 이상. AAA(7:1)는 핵심 데이터.
- 터치 타깃 44pt+ (HIG) / 48dp+ (M3).
- 모든 인터랙티브 요소에 `aria-label`.
- 키보드만으로 모든 흐름 가능 (focus visible).
- 스크린리더 친화 — `aria-live` 자동저장 알림.
- `prefers-reduced-motion` 존중.

### 7.2 성능 목표

| 지표 | 현재 추정 | 목표 |
|---|---|---|
| FCP (모바일) | ~2.0s | ≤1.2s |
| LCP | ~3.5s | ≤2.5s |
| CLS | unknown | ≤0.05 |
| INP | ~250ms | ≤200ms |
| TBT | ~400ms | ≤200ms |

전략:
- 이미지 lazy + `decoding="async"` + AVIF/WebP
- 첨부 썸네일 R2 Image Resizing (모바일 320w / 태블릿 640w)
- HTMX `hx-boost` + fragment swap = SPA 체감 (full reload 없음)
- Service Worker (Workbox) — 큐 카드 최근 20건 캐시
- CSS 모듈화 — 라우트별 critical CSS 인라인

### 7.3 국제화·로케일

- 한국어 우선. 모든 라벨·CTA 한글.
- 숫자: `Intl.NumberFormat('ko-KR')` (1,510,000원).
- 날짜: `2026-05-22` 표준 + 보조 "5월 22일 (목)" 한글.
- 전화: `010-2690-2242` 자동 포매팅.

---

## 8. 마이그레이션 로드맵 (P0/P1/P2)

상세는 `MIGRATION_ROADMAP.md` 참조.

### P0 — 즉시 (약 7 작업일, **58h**) — v1.1
> 비효율 결함 2건 제거 + 기존 모바일 카드 gap patch. cohort Day 1~7 점진 출시.

0. **P0-00 Foundation PR** — `feature_flags.py` 계약, OrderDraft 모델·마이그레이션, cleanup worker, Playwright baseline을 선행 확정.
1. **cohort 점진 출시** — `ERP_MOBILE_V2_ENABLED` 기본값 `false` 유지. `FOMS_V3_SHELL_COHORT` user id 목록으로 Day 1 안중훈씨 → Day 3 사무실 보조 5명 → Day 7 전체. `foms/services/feature_flags.py`의 `is_enabled_for_user()`로 제어.
2. **도면 카드 audit + gap patch** — `templates/drawing/partials/workbench_dashboard_body.html:314` 이미 존재. 갭만 보완 (thumbnail 16:9 + 필터 offcanvas).
3. **AS 카드 audit + gap patch** — `templates/cs/partials/as_dashboard_body.html:364` 이미 존재. 갭만 보완 (단계 색 배지 표준화 + 검색·필터 통합).
4. **시공 카드 audit + gap patch** — `templates/construction/partials/dashboard_body.html:121` 이미 존재. 갭만 보완 (권한 분리 검증 + 도면 첨부).
5. 모든 `<input type="file" accept="image/*">`에 `capture="environment"` 부착.
6. **AS 접수 모달** 카메라 우선 + paste 보조 역전 (PC에서만 paste 버튼 visible).
7. **768~991px 충돌 해소** — 모바일·태블릿에서 글로벌 nav 강제 숨김 (사용 불가 결함).
8. **add_order/edit_order 폼** sticky bottom CTA + `.foms-page-form` 클래스 부여 (44px 터치 타깃 룰 적용).

**산출물**: P0-00 포함 8개 PR, 총 58h ≈ 7 작업일. 각 PR `python -c "import app; print('APP_OK')"` 통과 + `pytest -x` 통과 + Playwright snapshot diff < 0.1%.

### P1 — 1~2주차
> 핵심 UX 확장. 사용자 6개 sub order 직접 대응.

1. Bottom nav 미처리 배지 (`context_processor`에서 stage별 카운트 주입)
2. 검색 풀스크린 오버레이 신설
3. erporder 마법사 4-step + 자동저장 + draft 복구
4. 인라인 편집 (기존 주문 수정)
5. 태블릿 가로 split-view (1024px+)
6. 통합 디자인 시스템 토큰 도입 (`foms-tokens.css`)
7. KV 행 macro 통합 + 딥링크 (`tel:`, `maps:`, `copy`)

**산출물**: 7개 PR + 디자인 토큰 마이그레이션 가이드.

### P2 — 분기 (3개월)
> 진화·실험.

1. HTMX 2.0 도입 + fragment swap
2. Alpine.js 폼 상태 관리
3. Service Worker 오프라인 캐시
4. 다크모드 (토큰 swap만)
5. 사진 lightbox + pinch-zoom + 회전
6. 음성 입력 (Web Speech API) — 메모·검색
7. PWA 매니페스트 + 앱 설치 프롬프트
8. 햅틱 피드백 + swipe action

---

## 9. 리스크·완화

| 리스크 | 영향 | 확률 | 완화책 |
|---|---|---|---|
| 환경변수 ON 시 v2 카드의 미발견 버그 노출 | 사용자 불만 | 中 | feature flag로 사용자별 점진 출시. 7일 베타. |
| Bootstrap 5 + HTMX + Alpine 충돌 | 인터랙션 깨짐 | 低 | E2E 테스트 셋 우선 작성 (Playwright). |
| 디자인 토큰 마이그레이션 중 색상 불일치 | 부분 화면 깨짐 | 中 | 토큰 매핑 표 + 자동 변환 스크립트 + 시각 회귀 테스트. |
| 자동저장 데이터 충돌 (PC + 모바일 동시 편집) | 데이터 소실 | 中 | 서버 측 `updated_at` 비교 + 충돌 시 사용자 선택 다이얼로그. |
| Service Worker 캐시 stale | 잘못된 데이터 노출 | 中 | stale-while-revalidate + 명시적 sync 버튼. |
| 한 손 사용 시 thumb-zone 도달 어려움 (큰 폰) | 사용성 저하 | 中 | Bottom nav 56pt+ 확보. FAB는 thumb zone. |

---

## 10. 측정·검증

### 10.1 정량 KPI

- 신규 주문 입력 평균 시간: 현재 ~5분 → 목표 ≤2분
- AS 접수 모달 첨부 성공률: 현재 PC 100%·모바일 ~10% → 목표 모바일 95%+
- 모바일 일일 활성 사용자 비율: 측정 시작
- 모바일 페이지 평균 체류 시간 / bounce rate
- LCP·INP·CLS (RUM)

### 10.2 정성 검증

- 안중훈씨 1주일 사용 일지 (videocall 인터뷰)
- 사무실 보조 5명 task completion 테스트
- 디자인 토큰 변경 전후 시각 회귀 (Percy 또는 Playwright snapshot)

### 10.3 회귀 방지

- `tools/harness/verify_result.py` 통과
- `pytest tests/` 통과
- Playwright E2E (홈·도면·AS·신규·수정) 최종 통과. P0-00D는 주문 목록 route `/` 6장 visual baseline만 선행하고, 도면·AS·신규·수정 시나리오는 각 후속 PR에서 확장.
- Lighthouse mobile 점수 ≥ 90

---

## 11. 의사결정 기록 (Decision Log)

| ID | 결정 | 대안 | 선택 이유 |
|---|---|---|---|
| D01 | 채널톡 차용 ❌, FOMS 자체 패턴 확립 | 채널톡 메타포 유지 | 사용자 직접 지시 (2026-05-28) |
| D02 | 모바일·태블릿 동등 1급 | 모바일 우선 | 사용자 직접 지시 |
| D03 | 태블릿 가로 split 360+fluid | 단일 컬럼 + 회전 | 사용자 직접 지시 |
| D04 | Full 패키지 산출 | 계획서만 | 사용자 직접 지시 |
| D05 | 인프라 재사용 (`ERP_MOBILE_V2_*`) | 그린필드 | 70% 이미 구축됨 |
| D06 | HTMX 2.0 + Alpine.js — **new surface only** (v1.1 재고) | 기존 fragment swap 일부 대체 | erp-shell.js 회귀 회피, 신규 페이지만 도입 |
| D07 | 자동저장 (수정) + 마법사 (신규) — **critical field 명시 저장** (v1.1 재고) | 모든 필드 자동저장 | 금액·시공일·실측일·연락처는 명시 저장 + undo 5초 |
| D08 | Bottom nav 5탭 = ERP 워크플로우 그룹화 | 단계별 9탭 | sub order #6 (ERP 메뉴만 노출) + 5탭이 thumb-zone 적합 |
| D09 | 디자인 토큰 — **alias bridge 3 phase** (v1.1 재고) | P1-06 일괄 치환 | 회귀 0 + 1년 점진 마이그레이션 (Phase 1 P0-07, Phase 2 P1-06, Phase 3 P2) |
| D10 | 카메라 직접 캡처 우선 + paste 보조 | paste 유지 | 모바일 paste 불가능, 현장 시나리오 사진이 1급 |

---

## 12. 다음 단계

1. **본 문서 사용자 승인** → `MOBILE_TABLET_DESIGN_SYSTEM.md` 작성 진행
2. HTML 목업 8장 생성 (`docs/design/mockups/`)
3. `COMPONENT_LIBRARY_MOBILE.md` 작성
4. `MIGRATION_ROADMAP.md` 상세 작성 (PR 단위 + 시간 추정)
5. P0-00 Foundation PR 시작 — feature flag 계약, OrderDraft 기반, cleanup worker, Playwright baseline 확정

본 계획서는 사용자 승인 후 `docs/AI_STATUS.md` 및 `docs/harness/policy/DECISIONS.md`에 등록한다.

---

> 본 문서는 Claude Opus 4.7 단독 작성이 아닌, 5개 병렬 agent의 코드베이스 audit + 5건의 외부 웹 리서치를 기반으로 한다. 출처:
> - `agentId: afcffd864443b836a` (NAV/모바일 셸 audit)
> - `agentId: a609f22f9c2c67c9d` (ERP 대시보드 audit)
> - `agentId: a0b13875cd1fcf40b` (erporder audit)
> - `agentId: a007a35c3c6ab5597` (반응형 CSS audit)
> - `agentId: a1bc23ba8426b5219` (외부 UX 리서치, `docs/research/MOBILE_TABLET_UX_RESEARCH.md`)
> - WebSearch 결과: Apple HIG, Material 3, iPad split-view, BuilderTrend/Procore 모바일, 이카운트/더존, 모바일 폼 best practices 2026
