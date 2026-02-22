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

(3.1~3.5 기존 내용 유지)

## 4. 영향 범위

(기존 유지)

## 5. 지도 주소변환 UX 개선 (2026-02-22)

(기존 유지)

## 6. 롤백

(기존 유지)

## 7. 출고 대시보드 시공자 다건 배정 (2026-02-22)

**완료** (기존 유지)

---

## 8. 출고 대시보드 시공자 그룹·파스텔 색상 (2026-02-22)

**요청**: 실측 대시보드(담당자 그룹·색상)와 동일하게, 출고 대시보드에서 (1) 시공자가 같은 주문끼리 묶어 정렬, (2) 같은 시공자끼리 파스텔톤 배경색으로 표시, (3) **새로고침 없이** 시공자 입력/추가/삭제 시 자동 정렬·색상 적용, (4) 시공자 삭제 시 해당 행은 정렬 반영·색상 해제(기본 배경).

### 8.1 참고: 실측 대시보드

- **백엔드**: `erp_measurement_dashboard.py` — `rows.sort(key=lambda o: (get_manager_name_for_sort(o) or 'ZZZ', o.id))`
- **템플릿**: `erp_measurement_dashboard.html` — 첫 루프로 `manager_list` 수집, `color_list`(원색), 행별 `manager_key` → `manager_index` → `manager_bg_color`, `<td class="manager-cell">`에 배경·글자색, hover 시 `var(--manager-bg-color)` 유지

### 8.2 출고 측 구현 순서

| 순서 | 작업 | 산출물 |
|------|------|--------|
| 1 | **백엔드 정렬** | `erp_shipment_page.py`: `get_construction_worker_key_for_sort(order)` 추가(첫 번째 시공자 문자열), `is_as_order(order)`. `rows.sort(key=(AS 0/1, worker_key, manager, id))` — AS는 하단, 같은 시공자끼리 묶음 |
| 2 | **템플릿: 서버 렌더** | `erp_shipment_dashboard.html`: 첫 루프로 `worker_list`(첫 시공자 등장순), `pastel_colors` 10종. 행별 `worker_key`, `namespace(worker_index)`, `worker_bg_color`/`worker_text_color`. `<tr>`에 `data-as`, `data-manager`. 시공자 `<td>`에 `shipment-worker-cell`, `--worker-bg-color`, `background-color`, `data-worker-bg-color` |
| 3 | **CSS** | `.shipment-worker-cell` 스타일 및 tbody tr:hover 시 배경 유지(`var(--worker-bg-color)`) |
| 4 | **JS: 클라이언트 정렬·색** | `getFirstWorkerFromRow(tr)`, `workerKeyForSort(tr)`(소문자 통일), `applyShipmentWorkerSortAndColors()`(행 정렬 → re-append → worker_list 구축 → 셀 배경/색 적용), `scheduleApplyShipmentWorkerSortAndColors()`(setTimeout 0). 파스텔 색상·기본 배경 상수 |
| 5 | **JS: 호출 시점** | 페이지 로드: fetch then/catch 후 1회 + DOMContentLoaded 또는 즉시 setTimeout 50ms. 이벤트: 시공자 input blur(기존 + 위임), 시공자 추가 후 blur, 시공자 삭제(×) 클릭, 저장된 시공자 불러오기 선택 시 `scheduleApplyShipmentWorkerSortAndColors()` 호출 |
| 6 | **시공자 삭제 시** | 해당 행 첫 시공자 없음 → `getFirstWorkerFromRow` 빈 문자열 → 정렬 시 'ZZZ'로 하단 근처, 색상은 `WORKER_DEFAULT_BG`(회색) 적용 → “색상 적용 해제” 충족 |

### 8.3 영향 파일

| 파일 | 변경 내용 |
|------|-----------|
| `apps/erp_shipment_page.py` | 시공자 키 함수, AS/시공자/담당자/id 정렬 |
| `templates/erp_shipment_dashboard.html` | worker_list·pastel_colors, 행별 색·tr data-*, 시공자 td 클래스·스타일, CSS, JS 정렬·색 함수 및 호출 |

### 8.4 롤백

- 백엔드: `get_construction_worker_key_for_sort`·`is_as_order` 제거, `rows.sort`를 담당자+id만 사용하도록 복원
- 템플릿: worker_list/색/JS 정렬·색 로직 전부 제거, 시공자 td를 기존 `shipment-field-cell`만 유지
