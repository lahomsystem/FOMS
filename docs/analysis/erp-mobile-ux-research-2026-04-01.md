# ERP 모바일 UX/UI 리서치 및 FOMS 진단 보고서

- 작성일: 2026-04-01
- 범위: `https://lahom-production.up.railway.app/erp` 하위 ERP 메뉴 전반
- 목적: 최신 ERP 모바일 UX 패턴을 실제로 조사하고, 현재 FOMS ERP의 모바일 UX 문제를 메뉴 단위로 진단해 개선 우선순위를 제안한다.

## 1. 조사 방법

이번 보고서는 아래 3가지를 병행했다.

1. 공식 자료 리서치
   - SAP Fiori Design
   - Oracle Redwood / Fusion 관련 공식 문서
   - Microsoft Dynamics 365 / Power Apps 공식 문서
2. 배포 환경 확인
   - 2026-04-01 기준 HTTP 응답 확인
3. 로컬 코드베이스 분석
   - `/erp` 하위 템플릿, 공통 CSS, 부분 템플릿, 모바일 브레이크포인트, 테이블/필터/메뉴 구조 확인

## 2. 먼저 결론

현재 FOMS ERP의 가장 큰 모바일 UX 문제는 "반응형 CSS 부족" 자체가 아니다. 더 근본 원인은 아래 3가지다.

1. 정보 구조가 데스크톱 테이블 중심으로 설계돼 있다.
   - 모바일에서는 화면만 줄어들 뿐, 업무 구조는 그대로 유지된다.
2. 공통 메뉴와 필터가 모바일 우선이 아니라 데스크톱 구성의 축소판이다.
   - 메뉴는 가로 스크롤 탭, 필터는 최소폭이 고정된 다중 컨트롤 묶음이다.
3. 화면별 구현 철학이 통일돼 있지 않다.
   - 어떤 화면은 모바일 카드 뷰가 있고, 어떤 화면은 1000px 이상 테이블을 그대로 유지한다.

즉, 지금 FOMS ERP는 "모바일 최적화가 덜 된 시스템"이라기보다 "데스크톱 ERP를 화면별로 부분 대응한 상태"에 가깝다.

## 3. 배포 환경 확인 결과

2026-04-01에 배포 URL을 직접 확인한 결과:

- `https://lahom-production.up.railway.app/erp` 는 `404` 응답이었다.
- `https://lahom-production.up.railway.app/erp/dashboard` 는 `302`로 `/login?next=/erp/dashboard` 로 이동한 뒤 로그인 페이지를 반환했다.

의미:

- 인증 전 상태에서는 실제 ERP 내부 화면의 라이브 DOM 전체를 직접 검증할 수 없었다.
- 따라서 "실제 운영 화면" 평가는 로그인 뒤 화면 캡처가 아니라, 로컬 템플릿/CSS/JS 구조 분석을 근거로 작성했다.
- 다만 진단 신뢰도는 충분하다. 이유는 ERP 핵심 화면이 서버 렌더링 템플릿과 공통 CSS에 강하게 묶여 있기 때문이다.

## 4. 최신 ERP 모바일 UX 리서치 요약

### 4.1 SAP Fiori에서 읽히는 패턴

SAP Fiori 공식 가이드에서 반복적으로 보이는 모바일 UX 방향은 아래와 같다.

- 역할 기반 진입
  - Launchpad, shell bar 기반으로 "메뉴를 길게 나열"하기보다 역할과 최근 작업 중심으로 진입한다.
- 단일 컬럼 우선
  - Object Page, Dynamic Page, Flexible Column Layout 계열은 작은 화면에서 1컬럼 중심으로 시작하고 화면이 넓어질수록 확장된다.
- 카드/섹션/점진적 공개
  - 모바일에서 모든 필드와 액션을 한 화면에 밀어 넣기보다, 카드와 섹션 단위로 나누고 필요한 곳만 펼친다.
- 필터는 항상 노출된 다중 드롭다운보다 다이얼로그/점진 노출이 자연스럽다.
- 테이블은 "가로 스크롤을 감수하는 기본형"이 아니라, responsive table이 우선이다.
  - SAP는 responsive table을 우선 선택지로 안내하고, 가로 스크롤 없이 항목을 파악하도록 설계한다.

FOMS에 주는 시사점:

- 현재의 "상단 가로 탭 + 복잡한 필터 바 + 넓은 업무 테이블"은 SAP 최신 모바일 패턴과 거리가 있다.
- FOMS는 모바일에서 "업무 목록 카드 -> 상세 드로어/상세 페이지 -> 빠른 액션" 흐름으로 재설계하는 편이 맞다.

### 4.2 Oracle Redwood에서 읽히는 패턴

Oracle 공식 문서 기준 Redwood 계열 모바일 UX는 다음 성격이 강하다.

- 터치 중심 PWA
- 바코드/카메라/현장 작업 등 모바일 컨텍스트 반영
- 입력을 한 화면에 모두 두지 않고 drawer 등 보조 패널로 분리
- 리스트와 액션을 분리해서 오조작을 줄임

FOMS에 주는 시사점:

- 실측, 출고, 시공, AS 같이 현장성이 강한 화면은 데스크톱 테이블보다 "모바일 작업 큐" 관점이 더 적합하다.
- 주소, 일정, 담당자, 사진, 상태 변경은 카드 내부 빠른 액션 또는 하단 액션시트 구조가 유리하다.

### 4.3 Microsoft Dynamics 365에서 읽히는 패턴

Microsoft 공식 자료에서 보이는 방향은 아래와 같다.

- 모바일 앱도 모델 기반 구조를 유지하되, 모바일용 대시보드/폼/빠른 입력을 별도로 고려한다.
- 최근 앱, 즐겨찾기, 검색, 역할 기반 접근이 중요하다.
- 새 작업 경험은 리스트에서 빠른 업데이트를 하고, 자세한 편집은 사이드 패널/상세 폼으로 넘긴다.

FOMS에 주는 시사점:

- 현재 FOMS는 목록 안에 너무 많은 정보를 동시에 넣는다.
- 모바일은 "목록에서 핵심 4~6개만 보고 빠른 액션 -> 세부정보는 상세" 패턴으로 분리해야 한다.

## 5. FOMS ERP 메뉴별 진단

아래 평가는 모바일 기준이다.

| 메뉴 | 현재 상태 | 핵심 문제 | 심각도 |
|---|---|---|---|
| 공통 메뉴 | 가로 스크롤 탭 | 메뉴 수가 많고, 모바일에서 정보 구조가 드러나지 않음 | 높음 |
| 메인 대시보드 | 대형 작업 큐 테이블 중심 | 다수 컬럼, sticky, min-width, 복잡 필터 | 매우 높음 |
| 실측 | 1220px 이상 테이블 유지 | 모바일 전용 카드 전환이 없음 | 매우 높음 |
| 도면 작업대시 | PC 테이블 + 모바일 카드 병행 | 혼합형이라 그나마 나으나 구조가 이원화됨 | 중간 |
| 생산 | 메인 대시보드와 유사 | 넓은 테이블 + 필터 최소폭 + 데스크톱 정보량 | 매우 높음 |
| 출고 | 일부 모바일 대응 존재 | 여전히 테이블/컬럼 리사이즈 전제가 강함 | 높음 |
| AS | 모바일 카드 뷰 존재 | 화면별 구현 방식이 따로 놀고 편집 UI가 촘촘함 | 중간 |
| 시공 | 생산/대시보드와 유사 | 넓은 테이블 + 필터 최소폭 + 데스크톱 정보량 | 매우 높음 |
| 시공 완료 | 상대적으로 양호 | 갤러리 중심이라 낫지만 공통 메뉴 구조 영향 받음 | 낮음~중간 |
| 이력 | 비교적 양호 | 일부 모바일 대응 있으나 공통 ERP 내비 구조 영향 받음 | 낮음~중간 |

## 6. 코드 근거

### 6.1 공통 ERP 메뉴는 모바일에서 여전히 "가로 스크롤 탭"

- `templates/partials/erp_sub_nav.html:5-54`
  - ERP 메뉴가 대시보드, 실측, 도면작업, 생산, 출고, AS, 시공, 시공완료, 이력 순으로 길게 나열된다.
- `static/css/erp-pro.css:139-147`
  - `.erp-pro-nav` 가 `display: flex` + `overflow-x: auto` 로 구성된다.
- `static/css/erp-pro.css:2454-2481`
  - 모바일에서도 구조를 바꾸지 않고 가로 스크롤 탭을 유지한 채 active 표시만 강화한다.

진단:

- 모바일 사용자는 현재 위치와 가능한 다음 행동을 한눈에 이해하기 어렵다.
- 최신 ERP 모바일 UX처럼 역할 기반 홈, 우선순위별 섹션, 최근 작업 진입 구조가 없다.

### 6.2 메인 대시보드/생산/시공은 공통적으로 "넓은 작업 큐 테이블"

- `templates/partials/erp_dashboard_grid.html:37-40`
  - 메인 그리드가 `table-responsive` 기반의 대형 테이블이다.
- `templates/partials/erp_dashboard_styles.html:54-61`
  - 별도 스크롤 래퍼와 sticky 동작 보정을 가진다.
- `templates/partials/erp_dashboard_styles.html:585-605`
  - 주소 280px, 제품 200px 등 컬럼 폭 전제가 강하다.
- `templates/partials/erp_dashboard_styles.html:837-866`
  - 모바일 대응도 구조 변경보다 간격/폰트/컴포넌트 축소가 중심이다.
- `templates/partials/erp_production_styles.html:425-454`
  - 생산 화면도 동일 패턴으로 큰 컬럼 최소폭을 유지한다.

진단:

- 이 구조는 "모바일에서 한 손 조작"이 아니라 "가로 스크롤 + 세부정보 과밀"을 유발한다.
- 반응형 문제가 아니라 업무 리스트를 테이블로 모델링한 정보 구조가 근본 원인이다.

### 6.3 메인 필터는 모바일 우선이 아니라 데스크톱 필터 축소판

- `templates/partials/erp_dashboard_filters.html:15`
  - 검색 영역이 `min-width: 200px`
- `templates/partials/erp_dashboard_filters.html:23`
  - 단계 선택이 `min-width: 110px`
- `templates/partials/erp_dashboard_filters.html:34`
  - 팀 선택도 `min-width: 110px`
- 같은 패턴이 `templates/partials/erp_production_filters.html`, `templates/partials/erp_construction_filters.html` 에 반복된다.

진단:

- 모바일에서는 필터가 "빠른 좁히기"가 아니라 "밀집한 컨트롤 집합"처럼 보인다.
- SAP Fiori Filter Bar처럼 기본 검색 + 추가 필터 진입 구조로 나누는 편이 낫다.

### 6.4 실측 화면은 현재 가장 대표적인 비모바일 구조

- `templates/erp_measurement_dashboard.html:99-128`
  - `.measurement-table` 에 `min-width: 1220px`
- `templates/erp_measurement_dashboard.html:541-542`
  - 모바일 영역에서도 동일 최소폭을 유지한다.
- `templates/erp_measurement_dashboard.html:125`, `templates/erp_measurement_dashboard.html:195`
  - 1220px, 1280px 기준이 반복된다.

진단:

- 실측은 현장 사용 가능성이 높은데도 모바일 카드/작업 큐 구조가 없다.
- 실측일, 주소, 담당자, 제품, 지도/동선은 모바일에 매우 중요한데, 현재는 넓은 테이블 읽기를 전제로 한다.

### 6.5 도면/AS/출고는 오히려 재사용 가능한 좋은 힌트가 있다

- `templates/erp_drawing_workbench_dashboard.html:257`, `templates/erp_drawing_workbench_dashboard.html:423`
  - 도면 작업대시는 PC 테이블과 모바일 카드 리스트를 분리한다.
- `templates/erp_as_dashboard.html:208-318`, `templates/erp_as_dashboard.html:321-405`
  - AS 화면은 PC 테이블과 모바일 카드 뷰를 분리했다.
- `templates/erp_shipment_dashboard.html:44`
  - 출고는 공통 필터 폼을 사용하고,
- `static/css/erp-pro.css:2344-2426`
  - 모바일 카드형 출고 레이아웃을 별도로 가진다.
- `templates/partials/erp_completion_styles.html:2-17`
  - 시공 완료는 갤러리 기반이라 상대적으로 모바일 친화적이다.

진단:

- FOMS 안에도 이미 "모바일 카드형 화면"의 재료가 있다.
- 문제는 좋은 패턴이 일부 화면에만 있고, ERP 전체 설계 원칙으로 승격되지 않았다는 점이다.

## 7. 근본 원인 분석

### 원인 1. ERP 핵심 리스트를 "테이블"로 정의한 설계

현재 메인 대시보드, 생산, 시공, 실측은 업무 단위를 카드/작업 큐가 아니라 테이블 행으로 정의한다.

결과:

- 모바일에서 정보 우선순위가 흐려진다.
- 주소, 일정, 담당자, 상태, 알림, 액션이 한 줄 안에 몰린다.
- 작은 화면에서 가독성과 터치 정확도가 급격히 떨어진다.

### 원인 2. 모바일 대응이 "구조 재설계"가 아니라 "예외 CSS 추가"

코드에는 모바일 관련 CSS가 많다. 하지만 대부분은:

- 간격 축소
- 버튼 크기 조정
- 일부 overflow 조정
- 특정 버튼/배지 크기 보정

즉, 근본 문제인 정보 구조를 바꾸기보다 증상을 눌러온 흔적이 많다.

### 원인 3. 공통 UX 시스템이 없다

현재 ERP 각 화면은 다음이 섞여 있다.

- 공통 ERP Pro 스타일
- 화면별 인라인 스타일
- 부분 템플릿별 별도 보정 CSS
- 어떤 화면은 카드 뷰, 어떤 화면은 테이블 유지

결과:

- 화면별 완성도 편차가 크다.
- 유지보수 비용이 높다.
- 새로운 메뉴를 추가할수록 모바일 품질이 다시 흔들린다.

## 8. FOMS에 맞는 개선 방향

### 8.1 공통 구조부터 바꿔야 한다

우선순위 1:

- ERP 모바일 홈을 새로 정의
  - "전체 메뉴 탭"보다
  - 오늘 일정
  - 내 업무
  - 긴급 건
  - 최근 작업
  - 팀별 큐
  - 빠른 진입
  구조로 재편

우선순위 2:

- 메뉴를 가로 스크롤 탭에서 "모바일 전용 섹션 메뉴"로 전환
  - 예: 하단 탭 4개 + 더보기, 또는 역할별 그룹화된 drawer

우선순위 3:

- 공통 필터를 "기본 검색 + 필터 열기" 방식으로 전환
  - 기본 노출: 검색, 날짜, 내 업무 토글
  - 숨김/드로어: 단계, 팀, 경보, 세부 조건

### 8.2 리스트 화면은 카드형 작업 큐로 통일

모바일에서 1차 리스트에 남겨야 할 정보는 최대 4~6개 수준이 적절하다.

권장 카드 구조:

- 1행: 고객명 + 상태 배지 + 긴급 배지
- 2행: 일정(실측/시공/AS) + 담당자
- 3행: 주소 요약 + 지도 버튼
- 4행: 핵심 액션 2~3개
  - 상세
  - 완료/시작
  - 사진
  - 전화

세부 정보는:

- 상세 페이지
- 하단 sheet
- side drawer 대체 구조
로 분리하는 편이 맞다.

### 8.3 FOMS 내부에서 재사용할 패턴

재사용 가치가 높은 현재 패턴:

- AS 모바일 카드 뷰
- 도면 작업대시 모바일 카드 뷰
- 출고 모바일 카드형 레이아웃
- 시공 완료 갤러리형 리스트

즉, 새로 처음부터 만드는 것보다:

- AS/도면/출고의 모바일 카드 패턴을 공통 ERP 리스트 컴포넌트로 추출
- 메인 대시보드/생산/시공/실측에 공통 적용

이 경로가 가장 현실적이다.

## 9. 실행 우선순위 제안

### 1차

- 공통 ERP 모바일 IA 재설계
- 공통 메뉴 구조 교체
- 공통 필터 구조 교체

### 2차

- 메인 대시보드 모바일 카드형 작업 큐
- 생산/시공 대시보드 공통 카드형 리스트 전환

### 3차

- 실측 화면 모바일 전용 작업 큐 설계
  - 일정
  - 주소
  - 지도
  - 담당자
  - 동선
  - 완료/수정 액션 중심

### 4차

- 화면별 스타일 중복 제거
- 인라인 스타일 제거
- 공통 ERP mobile component system 정리

## 10. 최종 판단

현재 가장 큰 문제 2가지는 아래처럼 정리된다.

1. 모바일 최적화 부족
   - 맞다. 하지만 원인은 단순 CSS 부족이 아니라, ERP의 핵심 업무 흐름이 데스크톱 테이블 중심으로 설계돼 있기 때문이다.
2. SAP 등 최신 ERP 모바일 UX를 참고해야 하는가
   - 반드시 그렇다.
   - 특히 SAP Fiori, Oracle Redwood, Microsoft Dynamics 365가 공통적으로 보여주는 방향은:
     - 역할 기반 진입
     - 단일 컬럼 우선
     - 카드/드로어/점진적 공개
     - 모바일용 빠른 액션
     - 상세 정보의 분리
     이다.

FOMS가 바로 적용해야 할 핵심 한 줄은 이것이다.

> 모바일 ERP를 "작은 데스크톱"으로 만들지 말고, "작업 큐 중심의 현장용 앱"으로 다시 정의해야 한다.

## 11. 참고 자료

### SAP

- SAP Fiori Design System, Floorplan Overview  
  https://www.sap.com/design-system/fiori-design-web/page-types/floorplan-overview
- SAP Fiori, Responsive Table  
  https://www.sap.com/design-system/fiori-design-web/v1-142/ui-elements/responsive-table/usage
- SAP Fiori, Object Page  
  https://experience.sap.com/fiori-design-web/v1-58/object-page/
- SAP Fiori, Filter Bar  
  https://experience.sap.com/fiori-design-web/v1-48/filter-bar/
- SAP Fiori, Work List  
  https://experience.sap.com/fiori-design-web/v1-52/work-list/

### Oracle

- Oracle Redwood Mobile WMS  
  https://docs.oracle.com/en/cloud/saas/warehouse-management/25b/owmma/redwood-mobile-wms.html
- Oracle Redwood Responsive Self-Service Receiving  
  https://docs.oracle.com/en/cloud/saas/readiness/scm/25b/inv25b/25B-inventory-wn-f36676.htm
- Oracle Redwood UX Drawer Guidance  
  https://docs.oracle.com/en/cloud/saas/sales/fasqa/how-do-i-increase-the-width-of-a-drawer-to-accomodate-more-fields-in-sales-in-the-redwood-ux.html

### Microsoft

- Dynamics 365 Field Service Mobile Overview  
  https://learn.microsoft.com/en-us/dynamics365/field-service/mobile/overview
- Dynamics 365 Mobile Setup  
  https://learn.microsoft.com/en-us/dynamics365/mobile-app/set-up-dynamics-365-for-phones-and-dynamics-365-for-tablets
- Power Apps Mobile Home / Recent / Favorites  
  https://learn.microsoft.com/en-us/power-apps/mobile/run-powerapps-on-mobile
- Dynamics 365 New Work Order Experience  
  https://learn.microsoft.com/en-us/dynamics365/field-service/work-order-experience
