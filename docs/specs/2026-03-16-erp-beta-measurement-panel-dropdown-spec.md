# ERP Beta 실측 현황 패널 기능 개선 Spec
> 작성일: 2026-03-16 | 상태: 🟡 승인대기

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
ERP Beta 화면 내 **'실측 일정 현황'** 패널에서 각 날짜를 클릭했을 때, 
기존처럼 **'해당 날짜가 실측일 필드에 자동 입력'** 되는 기능은 그대로 유지하면서,
동시에 **'해당 날짜에 잡혀있는 실측건들의 상세 목록(고객명, 시간, 주소)'이 해당 날짜 항목 바로 아래에 드롭다운(아코디언 형태)으로 펼쳐지게** 개선합니다.

### 1.2 기능 요구사항
1. **백엔드 (API 개선)**: 
   - 기존 `/api/erp/measurement/summary` 엔드포인트는 단순히 각 날짜별 카운트만 반환합니다.
   - 이를 개선하여 각 날짜별 카운트뿐만 아니라 **상세 건수(cases) 목록(주문 ID, 고객명, 실측시간, ERP 주소 정보)** 도 함께 반환하도록 수정합니다.
2. **프론트엔드 (UI 렌더링)**:
   - 받은 `cases` 데이터를 바탕으로 뱃지(카운트) 등 기존 헤더 정보 아래에 `d-none` 처리된 상세 내역 영역을 추가 구성합니다.
   - 날짜 항목 클릭 이벤트 처리 리스너에서 기존의 "날짜 선택/입력" 로직은 유지하고, 클릭된 항목의 하위 상세 내역 영역의 표시 상태를 토글(`.classList.toggle('d-none')`)합니다.
3. **디자인/스타일**:
   - 상세 리스트 항목은 작고 깔끔하게(`small`, `text-muted`, 배경색 `bg-light` 등) 뷰를 구성하여 기존 UI와 어울리게 구성합니다.

### 1.3 예외/제약 조건
- ERP 실측 주소는 일반 주소가 비어있을 수 있으므로 기존 ERP Route 로직에서 사용된 "ERP Beta 주소 추출 폴백(Fallback)" 구조를 동일하게 사용합니다.
- 많은 날짜를 클릭해도 UI가 깨지지 않도록 DOM 구조를 깔끔하게 유지해야 합니다.
- (선택) 날짜 클릭 시 현재 열린 다른 날짜의 드롭다운을 접을지, 아니면 일일이 다 펼칠 수 있게 둘 지 결정해야 하며, 우선은 **개별 토글(독립적)** 로직으로 구성합니다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `apps/api/erp_measurement.py` | `api_erp_measurement_summary` 함수에서 `measurement_counts` 계산 시 각 주문의 상세 정보(시간, 고객명, 주소)를 수집하여 `panel_dates`의 각 항목에 `cases` 키로 반환. (ERP 주소 파싱 로직 포함) |
| `templates/partials/erp_beta_tab.html` | 필요 시 `<style>` 구역에 드롭다운 리스트용 스타일 클래스 `.measurement-cases-list`, `.measurement-cases-item` 등 추가 정의 |
| `templates/partials/erp_beta_js.html` | `loadMeasurementPanel` 내 렌더링 로직 수정 (숨김 처리된 상세 리스트 DOM 추가). 클릭 이벤트 시 `.measurement-cases-list` 찾아서 toggle(`d-none`). |

### 2.2 아키텍처 방향
- **GDM 원칙 - 단순화 우선(Occam's Razor)**:
  - 복잡한 jQuery 애니메이션이나 모달 추가 대신, Bootstrap 5 기반 `d-none` 클래스 토글링으로 최대한 로직을 단순하게 작성.
- 데이터를 백엔드 단일 API로 한번에 처리하여 불필요하게 날짜별로 다시 API를 호출하는 낭비(N+1 통신 등) 제거.
  
## 3. Steps — 실행 단계
- [ ] Step 1: `apps/api/erp_measurement.py`에서 ERP Beta 구조화 데이터(Site) 활용 주소 추출 함수 생성 후 Summary API 수정
- [ ] Step 2: `templates/partials/erp_beta_js.html` 수정, `html +=` 렌더링 부분에 `cases` 맵핑 추가 및 클릭 이벤트 내 토글 로직 구현
- [ ] Step 3: `templates/partials/erp_beta_tab.html`의 CSS Style 부분 조정하여 시인성 보강
- [ ] Step 4: 동작 테스트 수행

## 4. 검증 기준
- [ ] `python -c "import app"` 모듈 로드 정상 (문법 에러 없음)
- [ ] 브라우저 개발자 도구 (Network 탭)에서 `/api/erp/measurement/summary`가 cases 배열을 잘 포함하고 있는지 확인.
- [ ] 화면에서 날짜 클릭 시 실측일이 정상적으로 Input에 선택되며, 하단으로 주소 리스트가 토글되는지 확인.

---
🚨 **진행 전 GDM 사용자 승인 대기 단계입니다. 본 문서를 확인하시고 진행 여부를 지시해주세요.** 🚨
