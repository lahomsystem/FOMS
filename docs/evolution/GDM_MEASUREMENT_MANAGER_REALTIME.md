# 실측 대시보드 담당자 실시간 정렬·색상 (출고 시공자 패턴 적용)

**일자**: 2026-02-23  
**요청**: 담당자 입력 후 새로고침 없이 같은 담당자끼리 묶이고 색이 붙도록, 출고 대시보드 시공자 입력 처리처럼 실시간 반영

---

## 1. 코드 리뷰 (참조: 출고 대시보드)

### 1.1 출고 대시보드 시공자 패턴 (erp_shipment_dashboard.html)

- **workerKeyForSort(tr)**: 행에서 시공자 셀 내용으로 정렬 키 추출.
- **applyShipmentWorkerSortAndColors()**:
  1. tbody에서 `tr.shipment-row` 수집.
  2. AS 여부 → 시공자 키 → 담당자 → orderId 순으로 정렬.
  3. 정렬된 순서로 DOM에 다시 append (재배치).
  4. 등장 순서대로 시공자 목록(managerList) 구성 후, 행별로 색 부여.
- **scheduleApplyShipmentWorkerSortAndColors()**: `setTimeout(..., 0)` 로 한 틱 뒤 실행 (blur 직후 DOM 안정화).
- **트리거**: 시공자 입력 셀 blur 시 `scheduleApplyShipmentWorkerSortAndColors()` 호출.

### 1.2 실측 대시보드 기존 동작

- 초기 로드 시 서버에서 정렬·색상 적용 (Jinja2).
- 담당자 인라인 편집 후 저장만 반영되고, **정렬·색상은 새로고침 전까지 갱신되지 않음**.

---

## 2. 적용 계획

| 단계 | 내용 |
|------|------|
| 1 | 출고와 동일하게 **getManagerFromRow**, **managerKeyForSort**, **applyMeasurementManagerSortAndColors**, **scheduleApplyMeasurementManagerSortAndColors** 도입. |
| 2 | 정렬 기준: 담당자명(소문자) → orderId. 빈 값·'-'는 'ZZZ'로 정렬해 맨 뒤로. |
| 3 | 색상: 현재 셀 내용 기준으로 등장 순서대로 managerList 구성 후, MEASUREMENT_MANAGER_COLORS[index] 적용. 새로 입력한 담당자도 자동으로 색 부여. |
| 4 | 초기 로드 시 기존 2단계(수동 색 맵) 제거하고 **applyMeasurementManagerSortAndColors()** 한 번 호출로 통일. |
| 5 | 담당자 blur 저장 **성공 시** `tr.dataset.manager` 갱신 후 **scheduleApplyMeasurementManagerSortAndColors()** 호출. |

---

## 3. 구현 내용 (static/js/erp/measurement.js)

- **MEASUREMENT_MANAGER_COLORS**: 기존 10색 배열 상수로 고정.
- **getManagerFromRow(tr)**: `tr.querySelector('td.manager-cell')` 의 textContent trim.
- **managerKeyForSort(tr)**: 담당자 없음('', '-') → 'ZZZ', 있으면 소문자.
- **applyMeasurementManagerSortAndColors()**:
  - `.measurement-table tbody` 내 `tr.measurement-row` 수집.
  - managerKeyForSort → orderId 순 정렬 후 appendChild로 재배치.
  - 등장 순서로 managerList 구성 (빈/'-' 제외).
  - 각 행의 manager 셀에 색 적용, `tr.dataset.manager` 동기화.
- **scheduleApplyMeasurementManagerSortAndColors()**: `setTimeout(applyMeasurementManagerSortAndColors, 0)`.
- **초기**: 2번 블록을 `applyMeasurementManagerSortAndColors()` 한 번 호출로 대체.
- **인라인 편집 blur 성공 시**: `this.textContent = newValue || '-'`, `tr.dataset.manager = newValue || ''`, `scheduleApplyMeasurementManagerSortAndColors()` 호출.

---

## 4. 코드 리뷰 체크리스트

| 항목 | 상태 |
|------|------|
| 출고 시공자 패턴(정렬 → DOM 재배치 → 색 재적용)과 동일 구조 | ✅ |
| 빈/'-' 담당자 정렬·색상(맨 뒤, 회색) 일관 처리 | ✅ |
| 새로 입력한 담당자명도 등장 순서로 색 부여 | ✅ |
| blur 저장 성공 시에만 재정렬·재색상 (불필요한 호출 최소화) | ✅ |
| 초기 로드와 편집 후 동일 함수로 동작 (중복 제거) | ✅ |

---

## 5. 검증 방법

1. 실측 대시보드 접속 → 담당자별로 묶여 있고 색이 붙어 있는지 확인.
2. 한 건의 담당자를 다른 담당자명으로 수정 후 blur → 저장 성공 시 **즉시** 해당 행이 해당 담당자 구간으로 이동하고 색이 바뀌는지 확인.
3. 새 담당자명(기존 목록에 없던 이름) 입력 후 blur → 새 색이 부여되고 같은 이름끼리 묶이는지 확인.
4. 담당자를 비우거나 '-'로 두면 맨 뒤로 가고 회색(#CCCCCC)인지 확인.
