# 실행 프롬프트 — WDCalculator 저장 상태 리셋 + 단가 표기 배치

이 문서는 **다른 LLM이 새 세션에서 바로 이어받아 실행**할 수 있도록 만든 자립형 handoff 프롬프트다.  
이전 대화 맥락이 없어도 아래만 읽고 작업할 수 있어야 한다.

계획서 보강일: 2026-04-20 — 실행 계획본과 동기화됨.

---

## 0. 역할

너는 FOMS 저장소에서 WDCalculator 기능 배치를 **근본 원인 기반으로 구현하고, 마지막에 GDM 정밀 감리까지 수행하는 시니어 코딩 에이전트**다.

금지:

- 저장 overwrite 증상을 버튼 disable 같은 미봉책으로 덮기
- `try/catch`로 조용히 삼키기
- 단가 표기를 **실제 금액**을 화면별로 하드코딩해 박기(형식 예시 문구는 계획서 §4-2 참고 — 예시 숫자는 포맷용)
- 무관한 dirty worktree 정리
- 사용자가 명시하기 전 커밋/푸시

이번 턴의 목표:

1. 견적 저장/수정 후 WDCalculator가 **완전한 신규 입력 상태**로 돌아가게 만든다.
2. `기본 견적:` 우측에 적용 단가를 표기한다.
3. 이미 저장된 견적과 진행 중 견적에도 단가를 표기한다.
4. `진행 중인 견적` 헤더 우측에 단가 표시 on/off 버튼을 추가한다.
5. 구현 후 **GDM 총괄 감리**까지 완료한다.

---

## 1. 저장소 / 규칙

### 저장소

- 경로: `C:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS`
- 셸: PowerShell

### 반드시 지킬 규칙

- 루트 `AGENTS.md`
- Root Cause Fix Only
- `python -c "import app; print('APP_OK')"` 가 표준 import 검증
- `git add .`, `git add -A` 금지
- 파일 지정 staging만 허용
- 사용자가 명시하기 전 커밋/푸시 금지

---

## 2. 사전 조사 결과 (이미 확인됨)

### 2-1. 저장 overwrite의 실제 근본 원인

아래 흐름이 이미 확인됐다.

- [estimate-lifecycle.js](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/wdcalculator/estimate-lifecycle.js)
  - `WdCalculatorLoadSavedEstimateToForm.loadEstimateToForm()`
    - `setCurrentDatabaseEstimateId(estimate.id)` 호출
    - 헤더를 `견적 수정` 모드로 전환
  - `WdCalculatorSaveEstimate.handleSaveEstimate()`
    - POST body에 `estimate_id: getCurrentDatabaseEstimateId()` 사용
  - `WdCalculatorRefreshAfterSave.refreshAfterSave()`
    - `resetInputFormKeepCustomerName()` 호출
  - `WdCalculatorResetInputFormKeepCustomer.resetInputFormKeepCustomerName()`
    - `setEditingEstimateId(null)`만 수행
    - `currentDatabaseEstimateId`는 해제하지 않음
    - 수정모드 헤더/배지/reset 버튼도 완전 복구하지 않음

즉, 저장 후에도 DB 대상 견적 ID가 남아 다음 저장이 overwrite로 이어질 수 있다.

### 2-2. 단가는 이미 파생 가능

단가 표시용 원천 데이터는 이미 있다.

- [primary-form.js](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/wdcalculator/primary-form.js)
  - `baseComponents`
  - `manualPricing`
- [pricing-core.js](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/wdcalculator/pricing-core.js)
  - `pricing_type`
  - `price_30cm`
  - `price_1cm`
  - `price_1m`
- [estimate-lifecycle.js](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/wdcalculator/estimate-lifecycle.js)
  - 현재 견적/진행 중 견적/저장된 견적 렌더링

즉, 저장 스키마 추가보다 **공통 단가 요약 헬퍼 + UI 슬롯 추가**가 먼저다.

### 2-3. 서버/API 계약 (착수 시 확인)

저장 엔드포인트에서 `estimate_id` 유무가 **insert vs update**를 어떻게 가르는지 코드로 확인하고 한 줄로 메모한다. 클라이언트에서 ID를 null로 만드는 수정과 **모순 없어야** 한다. 스키마 대수술은 이번 배치 범위 밖.

### 2-4. 저장 실패 시

저장 실패 시에는 `currentDatabaseEstimateId` / 수정모드를 **유지**하고, full reset은 **성공 콜백**에서만 호출한다.

---

## 3. 이번 턴에서 읽어야 할 파일

반드시 읽기:

- [templates/wdcalculator/partials/wdcalculator_body.html](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/templates/wdcalculator/partials/wdcalculator_body.html)
- [static/js/wdcalculator/estimate-lifecycle.js](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/wdcalculator/estimate-lifecycle.js)
- [static/js/wdcalculator/primary-form.js](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/wdcalculator/primary-form.js)
- [static/js/wdcalculator/pricing-core.js](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/wdcalculator/pricing-core.js)
- [templates/wdcalculator/partials/wdcalculator_styles.html](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/templates/wdcalculator/partials/wdcalculator_styles.html)
- [templates/wdcalculator/partials/wdcalculator_scripts.html](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/templates/wdcalculator/partials/wdcalculator_scripts.html)

참고:

- [docs/harness/policy/DECISIONS.md](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/docs/harness/policy/DECISIONS.md)
- [docs/ARCHIVE_INDEX.md](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/docs/ARCHIVE_INDEX.md)
- [2026-04-20-wdcalculator-save-reset-unit-price-execution-plan.md](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/docs/plans/2026-04-20-wdcalculator-save-reset-unit-price-execution-plan.md)

---

## 4. 구현 요구사항

### A. 저장/수정 후 완전한 신규 입력 상태

#### 반드시 만족할 것

1. 저장 성공 후:
   - `editingEstimateId = null`
   - `currentDatabaseEstimateId = null`
   - 수정모드 헤더/배지 제거
   - reset 버튼 제거/숨김
   - 로컬 진행 중 견적 목록 비움
   - 고객명/기본구성/옵션/비고/가격표시 초기화
   - 쿠폰/배송 기본값 복원
2. 진행 중 견적 `견적 수정 적용` 후에도 같은 상태로 복귀
3. 다음 저장은 기존 row update가 아니라 신규 저장 경로를 타야 함

#### 구현 힌트

- 먼저 `resetInputFormKeepCustomerName`(및 유사 부분 리셋) **호출부를 전부 검색**하고, 저장 성공/수정 적용 외 경로(취소·새 견적 등)는 **고객명 유지가 필요하면 부분 리셋 유지**할지 결정한다.
- `resetInputFormKeepCustomerName()`를 그대로 쓰지 말고,
  - 새 full reset helper를 만들거나
  - 역할을 분리해라
- `refreshAfterSave()`는 그 full reset helper를 사용하도록 바꿔라
- `loadEstimateToForm()`이 만든 수정모드 UI를 full reset이 되돌리게 해야 한다

### B. 단가 표기

#### 현재 견적

- [wdcalculator_body.html](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/templates/wdcalculator/partials/wdcalculator_body.html)
  - `기본 견적:` 우측에 적용 단가 표시

#### 진행 중 견적

- [estimate-lifecycle.js](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/wdcalculator/estimate-lifecycle.js)
  - `renderEstimatesList()` 카드에 단가 표시

#### 저장된 견적

- [estimate-lifecycle.js](C:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/static/js/wdcalculator/estimate-lifecycle.js)
  - `buildSidebarEstimateItem()`에 단가 표시

#### 단가 요약 규칙

1. 제품 선택 모드
   - `1m` 제품이면 `1m 330,000원`
   - `30cm` 제품이면 `30cm 187,000원 / 1cm 623원`
2. 직접입력 모드
   - `manualPricing` 기준으로 같은 규칙
3. 기본 구성 여러 개면
   - 단일 값 강제 금지
   - component별 chip/list 요약 사용
4. 레거시 저장 견적처럼 원천이 부족하면
   - `단가 정보 없음` muted fallback 허용
   - silent failure 금지
5. 실행 계획 §4-2의 **330,000원 등은 형식 예시**이며, 실제 금액은 항상 파생 데이터에서만 취한다.

#### DOM/XSS

단가 요약을 넣을 때 `innerHTML`에 검증되지 않은 문자열을 붙이지 마라. 숫자·라벨만 조합하거나 `textContent`·이스케이프를 사용한다.

### C. 단가 표시 토글

- `진행 중인 견적` 헤더 우측에 버튼 추가
- 기본값 `ON`
- 토글 대상:
  - 진행 중 견적 카드 단가 메타
  - 저장된 견적 사이드바 단가 메타
- 현재 “견적 결과” 박스의 `기본 견적:` 우측 단가 표시는 항상 유지
- `localStorage` 권장, 키 고정: `foms.wdcalculator.unitPriceMetaVisible`

### D. 저장된 견적 검색 결과 목록

사이드바 `buildSidebarEstimateItem`과 **동일 렌더**면 토글·단가가 자동 정렬된다. 별도 경로면 동일 `deriveEstimateUnitPriceSummary`를 호출한다. 사용자 대면 완료 기준의 1순위는 **기본 견적 + 진행 중 카드 + 저장 사이드바**다.

---

## 5. 추천 구현 순서

### Step 1. 상태 리셋 경로 분리

아래를 먼저 끝내라.

- full reset helper 추가
- save success 후 full reset 호출
- local edit apply 후 full reset 호출
- DB estimate id / edit id / header/reset button까지 완전 복귀

### Step 2. 단가 요약 헬퍼 추가

권장 helper 예시:

- `deriveEstimateUnitPriceSummary(estimate, products)`
- `renderEstimateUnitPriceHtml(summary, options)`

주의:

- current estimate / in-progress estimate / saved estimate가 같은 규칙을 쓰게 해라
- 렌더마다 로직을 복붙하지 마라

### Step 3. UI 삽입

- 현재 결과 영역
- 진행 중 견적 카드
- 저장된 견적 사이드바
- 토글 버튼

### Step 4. GDM 감리

감리 포인트:

1. overwrite 버그가 진짜 root cause 기준으로 제거됐는지
2. 단가 표기가 하드코딩이 아닌 파생 로직인지
3. 복합 기본 구성에서 UI가 깨지지 않는지
4. 저장된 견적과 진행 중 견적이 같은 단가 규칙을 쓰는지
5. 회귀 가능성이 남는 상태 전이가 없는지
6. 저장 실패 시 ID/수정모드가 유지되는지(§2-4)
7. 단가 삽입 경로에 XSS 여지가 없는지
8. `setCurrentDatabaseEstimateId` / `getCurrentDatabaseEstimateId` 읽기·쓰기 전반이 성공 경로에서 null로 정리되는지
9. 토글 OFF 시 레이아웃이 과도하게 흔들리지 않는지

---

## 6. 테스트 / 검증

최소:

```powershell
python -c "import app; print('APP_OK')"
python tools/harness/verify_result.py --json
pytest tests/contracts/wdcalculator/test_composition_contracts.py tests/domains/test_wdcalculator_product_settings.py -q
```

권장:

- 새 focused 테스트 추가
  - 예: `tests/domains/test_wdcalculator_estimate_reset_contract.py`
  - 최소 1개 이상 의미 있는 assertion(API 필드·템플릿 마커 등 검증 가능한 경계). 실행 계획 §5 테스트 후보 설명 참고.

수동 스모크:

1. 저장된 견적 불러오기
2. 수정 후 저장
3. 저장 직후 수정모드가 완전히 해제됐는지 확인
4. 새 견적 저장 시 overwrite가 아니라 신규 저장인지 확인
5. 현재 결과 `기본 견적:` 우측 단가 확인
6. 저장된 견적 사이드바 단가 확인
7. 진행 중 견적 토글 ON/OFF 확인
8. 저장 의도적으로 실패시켜(또는 네트워크 끊김 시뮬레이션) 수정모드·estimate id가 유지되는지 확인

---

## 7. 절대 하면 안 되는 것

1. `estimate_id`를 **클라이언트에서만** 억지로 안 보내는 식의 증상 우회(서버 계약과 불일치 시 §2-3으로 해결)
2. 저장 후 스피너/토스트만 바꾸고 상태는 그대로 두는 것
3. 단가 문자열을 화면별로 각각 하드코딩하는 것
4. 이미 완료된 WD performance 배치를 불필요하게 건드리는 것
5. 무관한 dirty worktree 정리
6. 사용자가 요청하지 않은 커밋/푸시

---

## 8. 완료 기준

- 저장 후 완전한 신규 입력 상태가 된다
- 수정 적용 후도 완전한 신규 입력 상태가 된다
- `기본 견적:` 우측 단가 표시가 나온다
- 저장된 견적 / 진행 중 견적에도 단가 표시가 나온다
- 토글 ON/OFF가 동작한다
- `APP_OK` 및 관련 검증 통과
- 최종 GDM 감리에서 blocker 없음

---

## 9. 최종 보고 형식

최종 응답은 아래 형식으로 정리하라.

1. **이번에 실제로 수정한 WDCalculator 근본 문제**
2. **왜 그게 overwrite와 단가 미표기의 근본 원인이었는지**
3. **검증 결과**
4. **남은 리스크 또는 후속 과제**
5. **GDM 감리 결과**
6. **커밋 여부**
   - 커밋/푸시는 사용자가 명시적으로 요청했을 때만

