# 시공 대시보드 UX 수정 계획 (리뷰 반영)

## 코드 리뷰 요약

### 현재 구현 상태
- **프로세스 맵 타일**: `erp_construction_page.py`에서 `display_stage`(시공대기/시공중/시공완료)로 집계·필터링. 타일 클릭 시 `applyFilter('stage', value)`로 폼의 `stage` 값을 설정 후 `form.submit()` 호출.
- **필터 폼**: `erp_construction_filters_grid.html`의 select `name="stage"` 옵션에 **시공대기/시공중/시공완료가 없음**(주문접수, 해피콜, 실측, 도면, 고객컨펌, 생산, 시공만 존재). 따라서 타일 클릭으로 설정한 값이 제출 시 유지되지 않을 수 있음.
- **시공 시작 API**: `api_construction_start`는 `workflow.history`에 '시공 시작'만 추가하고 `workflow.stage`는 변경하지 않음. 페이지에서는 `is_started = any(note == '시공 시작')`로 **시공중** 표시 → 시공 시작 클릭 시 시공중으로 이동하는 로직은 이미 정상.
- **상세 버튼**: `loadOrderDetail`에서 `stage = sd.workflow.stage`(예: CONSTRUCTION)만 사용. **display_stage**(시공대기 vs 시공중)를 계산하지 않아, 시공중인 주문에도 항상 '시공 시작'만 노출되는 문제 있음.
- **시공 완료 API**: `api_construction_complete`는 `stage = 'CS'`, `order.status = 'CS'`로 설정. `erp_construction_page.py`는 `stage in ('COMPLETED','완료','AS_WAIT')`만 시공완료로 매핑하므로 **CS인 주문은 시공완료 타일에 포함되지 않음**(목록에서 빠짐).
- **시공 완료 모달**: 시공 사진 업로드 후 `category: 'construction'`으로 finalize 호출 → 공통 첨부 시공 카테고리와 동일하게 저장됨. 요구사항 4·5는 이미 구현됨.

---

## 수정 요청 정리

| # | 요청 | 비고 |
|---|------|------|
| 1 | 프로세스맵 타일(시공대기/시공중/시공완료) 클릭 시 **해당 단계 주문만** 필터되어 표시 | 백엔드 필터는 구현됨. 폼에서 stage 값 전달만 보완 필요 |
| 2 | 시공대기에서 **시공 시작** 버튼 클릭 → 프로세스맵 **시공중** 단계로 이동 | 현재 구현대로 동작(추가 수정 없음) |
| 3 | 시공중 단계에서 **시공 완료** 버튼 노출(현재 잘못 '시공 시작'으로 표시됨) | 상세에서 display_stage 계산 후 시공중일 때만 '시공 완료' 버튼 표시 |
| 4 | 시공 완료 버튼 클릭 시 시공자가 **시공 사진** 업로드 가능 | 모달 + 업로드 플로우 이미 구현됨 |
| 5 | 올린 시공 사진은 **공통 첨부의 '시공' 카테고리**에 저장 | finalize 시 category='construction' 사용 중 → 유지 |

---

## 수정 계획 (실행 순서)

### 1. 타일 필터가 올바르게 동작하도록 폼 수정
- **파일**: `templates/partials/erp_construction_filters_grid.html`
- **내용**: 시공 대시보드 전용이므로 단계 select 옵션에 **시공대기**, **시공중**, **시공완료** 추가. 기존 '시공' 등과 중복되지 않도록 시공 관련 옵션을 이 세 가지로 정리하거나, 기존 옵션 뒤에 추가.
- **결과**: 타일 클릭 시 `applyFilter('stage', '시공대기'|'시공중'|'시공완료')`가 select에 반영되고, submit 시 `stage` 쿼리 파라미터로 전달됨.

### 2. 시공 완료(CS) 주문이 시공완료 타일에 보이도록 백엔드 매핑 추가
- **파일**: `apps/erp_construction_page.py`
- **내용**: `display_stage` 결정 분기에서 `stage == 'CS'`인 경우 `display_stage = '시공완료'`로 설정.
- **결과**: 시공 완료 처리된 주문이 프로세스맵 '시공완료' 타일 개수에 포함되고, 해당 타일 클릭 시 목록에 표시됨.

### 3. 상세 영역에서 display_stage 계산 후 버튼 분기
- **파일**: `templates/partials/erp_construction_scripts.html`
- **내용**: `loadOrderDetail` 내에서 `sd.workflow.stage`와 `sd.workflow.history`를 사용해 백엔드와 동일한 규칙으로 **displayStage** 계산.
  - `stage in ('CONSTRUCTION','시공')` 이면: `history`에 note '시공 시작' 있으면 displayStage = '시공중', 없으면 '시공대기'.
  - `stage in ('CS','COMPLETED','완료','AS_WAIT')` 이면: displayStage = '시공완료'.
  - 시공대기일 때만 **시공 시작** 버튼, 시공중일 때만 **시공 완료** 버튼 노출.
- **결과**: 시공중 주문을 열면 '시공 완료' 버튼만 보이고, 시공대기 주문은 '시공 시작'만 보임.

### 4. (선택) 시공 완료 후 이동 처리
- 현재: 완료 성공 시 `window.location.href = '/erp/dashboard?stage=완료'`로 메인 ERP 완료 탭 이동.
- 요구사항에 “시공완료 단계로 이동”만 명시되어 있으므로, 필요 시 시공 대시보드 새로고침으로 타일 숫자 갱신만 할지, 기존처럼 메인 대시보드로 이동할지는 사용자 확인 후 유지/변경.

---

## 검증 체크리스트
- [ ] 시공대기 타일 클릭 → 시공대기 주문만 표시
- [ ] 시공중 타일 클릭 → 시공중 주문만 표시
- [ ] 시공완료 타일 클릭 → 시공완료(CS 포함) 주문만 표시
- [ ] 시공대기 주문 상세 → '시공 시작' 버튼만 노출
- [ ] 시공 시작 클릭 후 해당 주문이 시공중 타일로 이동(숫자 증가)
- [ ] 시공중 주문 상세 → '시공 완료' 버튼만 노출
- [ ] 시공 완료 클릭 → 모달에서 사진 업로드 가능, 완료 처리 후 시공완료 타일에 반영
