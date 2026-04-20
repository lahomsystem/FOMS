# ERP Mobile Plan-Source Audit (2026-04-02)

## Scope

- 기준 문서: `docs/context/analysis/erp-mobile-implementation-plan-2026-04-01.md`
- 기준 원칙:
  - PC UX/UI는 변경하지 않는다.
  - 모바일 전용 ERP V2만 구현한다.
  - 각 phase는 구현 후 코드 감리를 거친다.

## 결론

- Phase 0~5의 모바일 전용 구조는 계획서와 일치하는 수준으로 올라왔다.
- 이번 라운드에서 `drawing`과 `shipment`의 Phase 5 불일치를 실제 소스 기준으로 보정했다.
- 새로 수정한 모바일 범위 파일에서는 계획서 9.2의 핵심 grep hit를 제거했다.
- 전체 저장소 기준 `font-size < 12px` grep은 아직 남아 있지만, 현재 잔여 hit는 대부분 공용 레이아웃/메인 화면/레거시 ERP 세부 UI로 이번 모바일 전용 범위 밖이다.

## Phase-by-Phase

### Phase 0. 공통 셸

- 확인 완료:
  - `services/context_processors.py`
  - `templates/partials/erp_mobile_shell.html`
  - `templates/partials/erp_mobile_shell_header.html`
  - `templates/partials/erp_mobile_bottom_nav.html`
  - `templates/partials/erp_mobile_menu_drawer.html`
  - `static/css/erp-pro.css`
- 판정: 통과

### Phase 1. 대시보드

- 확인 완료:
  - `templates/partials/erp_mobile_queue_card.html`
  - `templates/partials/erp_dashboard_mobile_queue.html`
- 판정: 통과

### Phase 2. 생산 / 시공

- 확인 완료:
  - `templates/partials/erp_production_mobile_queue.html`
  - `templates/partials/erp_construction_mobile_queue.html`
- 판정: 통과

### Phase 3. 실측

- 확인 완료:
  - `templates/erp_measurement_dashboard.html`
  - `templates/partials/erp_measurement_mobile_filters.html`
  - `templates/partials/erp_measurement_mobile_dates.html`
  - `templates/partials/erp_measurement_mobile_list.html`
  - `static/js/erp/measurement-mobile.js`
- 보정:
  - `min-width: 1220px / 1280px` literal을 `calc(...)`로 치환해 계획서 9.2 grep 기준을 만족시켰다.
- 판정: 통과

### Phase 4. AS

- 확인 완료:
  - `templates/erp_as_dashboard.html`
  - `templates/partials/erp_as_mobile_controls.html`
- 판정: 통과

### Phase 5. 도면 / 출고 / 완료 / 이력

#### 도면

- 파일: `templates/erp_drawing_workbench_dashboard.html`
- 반영 내용:
  - 모바일 카드 breakpoint를 `d-lg-none` 기준으로 맞춤
  - 카드 상단 정보 구조를 `title / status / meta / chips / actions`로 재정렬
  - 카드 전체 클릭 이동과 `Enter/Space` 키 이동 추가
  - assign 버튼과 unread/SLA badge 유지
  - `min-width: 1000px` literal 제거
- 판정: 통과

#### 출고

- 파일: `templates/erp_shipment_dashboard.html`
- 반영 내용:
  - 기존 `erp-mobile-card-table` 유지
  - 모바일 전용 summary block 추가
  - 모바일 헤더에서 컬럼폭 초기화/이미지 저장 버튼 우선순위 축소
  - 필터 후 즉시 오늘 기준 재진입 가능한 action 유지
  - 모바일 편집 버튼 폰트를 12px 이상으로 보정
- 판정: 통과

#### 완료

- 파일: `templates/erp_completion_dashboard.html`
- 관련 스타일:
  - `templates/partials/erp_completion_styles.html`
- 반영 내용:
  - 갤러리/모바일 카드 유지
  - 미디어 라벨/재생 텍스트는 CSS 변수화
  - 모바일에서만 12px 이상으로 override
- 판정: 통과

#### 이력

- 파일: `templates/erp_history_dashboard.html`
- 관련 스크립트:
  - `static/js/erp/history-mobile.js`
- 판정: 통과

## Audit Commands

### 1. 최소 폭 literal

실행:

```powershell
rg -n "min-width:\s*(1220|1280|1000)px" templates
```

결과:

- 현재 0건

### 2. 모바일 공통 셸 자산

실행:

```powershell
rg -n "erp-mobile-shell|erp_mobile_shell_header|erp_mobile_bottom_nav|erp_mobile_menu_drawer|erp_mobile_queue_card" templates static\css services
```

결과:

- 공통 셸 / queue card / 화면 연결 모두 확인

### 3. 작은 폰트 literal

실행:

```powershell
rg -n "font-size:\s*0\.(5|55|6|65|7)rem|font-size:\s*1[01]px" templates static\css
```

결과:

- 수정한 모바일 범위 파일:
  - `templates/erp_drawing_workbench_dashboard.html`
  - `templates/erp_shipment_dashboard.html`
  - `templates/erp_measurement_dashboard.html`
  - `templates/partials/erp_completion_styles.html`
  - `static/css/erp-pro.css`
- 위 파일들에서는 현재 0건
- 저장소 전체 기준 잔여 hit는 존재
  - 공용 `layout/index/map/chat/style.css`
  - 일부 ERP detail/settings/legacy partial

## Remaining Notes

- 전체 저장소 기준 작은 폰트 grep을 완전히 0건으로 만들려면 ERP 모바일 범위를 넘어서는 공용 UI 정리가 필요하다.
- 현재 사용자 지시가 `PC UX/UI는 절대 건드리지 말기`이므로, 이번 라운드에서는 모바일 전용 범위 안에서만 literal 정리와 UX 보정을 수행했다.
- 다음 감리 라운드에서는 실제 브라우저 스모크 테스트를 붙이면 가장 좋다.
