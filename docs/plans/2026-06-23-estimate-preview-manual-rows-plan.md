# 계약서 프리뷰 수동 행 추가 설계

작성일: 2026-06-23

## 목표

계약서 탭의 `#est-items-tbody` 제품 행 사이마다 `+` 버튼을 노출하고, 사용자가 버튼을 눌러 직접 입력 가능한 수동 행을 끼워 넣을 수 있게 한다.

## 현상 리뷰

- 렌더 표면은 `templates/orders/partials/estimate_pane.html`의 `#erp-estimate-items-table` / `#est-items-tbody`다.
- 실제 행은 `static/js/orders/estimate-preview.js`의 `_renderItems(items)`가 `/api/orders/<order_id>/estimate-preview` 응답을 받아 매번 `tr:not(#est-items-empty)`를 제거한 뒤 새로 만든다.
- 데이터 원천은 `foms/api/erp_estimates.py:get_estimate_preview()` -> `foms/services/estimate_service.py:extract_estimate_data_from_order()`이며, 현재는 `structured_data.items`만 계약서 항목으로 변환한다.
- 같은 DOM을 PNG 저장과 모바일 미리보기 캡처가 사용한다. 따라서 `+` 버튼/입력 컨트롤은 화면 편집 시에는 보이고, 캡처/export 시에는 숨겨져야 한다.
- 컬럼 리사이저는 `static/js/orders/estimate-table-columns.js`가 테이블 DOM 기준으로 grip을 재계산한다. 수동 행 추가/삭제 후 `scheduleEstimateColumnRefresh()` 호출이 필요하다.
- 저장 경로는 이미 `erpSaveStructured()` -> `PUT /api/orders/<id>/structured`가 있다. 하지만 `erpCollectStructured()`의 보존 키 목록에 없는 새 최상위 키는 full save 때 유실될 수 있다.

## 근본 원인

현재 계약서 프리뷰는 "서버 산출 읽기 전용 결과"다. 프리뷰 DOM에만 행을 넣으면 다음 탭 진입, 자동 저장 후 재조회, 새로고침, 모바일 캡처 재생성 시 행이 사라진다.

근본 수정은 수동 행을 별도 데이터 계약으로 저장하고, 서버의 견적 프리뷰 추출 단계에서 기존 제품 행과 병합하는 것이다.

## 데이터 계약

`structured_data.estimate_preview.manual_rows`를 추가한다.

```json
{
  "estimate_preview": {
    "manual_rows": [
      {
        "id": "mr_20260623_001",
        "after_index": 0,
        "product_name": "",
        "spec": "",
        "color": "",
        "quantity": "",
        "amount": "",
        "affects_total": false
      }
    ]
  }
}
```

- `after_index`: 원본 `structured_data.items` 기준 삽입 위치. `-1`은 첫 행 앞, `0`은 첫 행 뒤, 마지막 index는 마지막 행 뒤.
- `amount`: 사람이 입력한 표시값을 허용하되 서버 계산에는 `_parse_money_amount()`로 정규화한다.
- `affects_total`: 기본 `false`. 사용자가 메모/주석성 행으로 쓰는 경우 합계 오염 방지. 금액 합계 반영 요구가 확인되면 UI 체크 또는 기본 `true`로 바꾼다.

## 렌더 설계

1. `_renderItems(items, manualRows)`로 확장한다.
2. 원본 행마다 다음 순서로 렌더한다.
   - 원본 제품 행
   - 해당 위치의 수동 행들
   - `+` 삽입 컨트롤 행
3. 제품이 0개여도 empty row 아래에 `+` 컨트롤을 표시해 첫 수동 행을 만들 수 있게 한다.
4. 수동 행은 5개 컬럼과 1:1 매칭한다.
   - 품명: input
   - 규격: textarea 또는 input, `erp-est-td-spec` 유지
   - 색상: input
   - 수량: input
   - 금액: input, 우측 정렬
5. 삭제 버튼은 수동 행 내부에 작은 icon button으로 제공한다.
6. `+` 행과 삭제 버튼은 `.erp-est-edit-control` 계열 클래스로 묶고 export/capture 시 숨긴다.

## 저장 설계

1. 프리뷰 JS에서 `manualRows` 상태를 `window.__erpLastStructuredData.estimate_preview.manual_rows`와 동기화한다.
2. 수동 행 input 변경 시:
   - 로컬 상태 갱신
   - `_mobilePreviewDataUrl = ''`
   - debounce 후 `erpSaveStructured({ redirect: false, _skipValidation: true })`
3. `erpCollectStructured()`의 `preservedTopLevelKeys`에 `estimate_preview`를 추가한다. 그렇지 않으면 다른 폼 저장 때 수동 행이 유실된다.
4. 저장 성공 후 `erpInvalidateEstimateCache()`가 호출되므로, 다음 프리뷰 로드는 서버 병합 결과를 다시 그린다.

## 서버 병합 설계

`extract_estimate_data_from_order()`에서:

1. 기존 `structured_data.items`를 현행대로 `estimate_items`로 변환한다.
2. `structured_data.estimate_preview.manual_rows`를 검증/정규화한다.
3. `after_index` 기준으로 원본 행 사이에 수동 행을 끼워 넣는다.
4. 각 수동 행에는 `source: "manual"`과 `manual_row_id`를 포함한다.
5. `affects_total === true`인 수동 행만 `total_amount`에 더한다. 기본은 합계 미반영.

## CSS/export 설계

- `.erp-est-manual-row input`, `.erp-est-manual-row textarea`는 계약서 인쇄 표 안에서 텍스트처럼 보이게 border/background를 최소화한다.
- `.erp-est-exporting .erp-est-edit-control` 및 export clone 내 control row를 숨긴다.
- 입력값 자체는 export에 남아야 하므로 input/textarea를 숨기지 않는다. 캡처 전 input value가 보이도록 스타일만 정리한다.

## 테스트 계획

- `tests/domains/test_estimate_service.py`
  - manual row가 원본 행 사이에 병합된다.
  - `affects_total=false`면 합계가 변하지 않는다.
  - `affects_total=true`면 합계/잔금이 반영된다.
- `tests/domains/test_erp_order_shared_form_scripts.py`
  - `estimate_preview` 보존 키가 `erpCollectStructured()`에 포함된다.
  - `estimate-preview.js`에 수동 행 렌더/저장 훅/컨트롤 export hide 계약이 있다.
  - `estimate_pane.html`에 수동 행 CSS와 export hide CSS가 있다.
- 검증 명령
  - `python -c "import app; print('APP_OK')"`
  - `python -m pytest tests/domains/test_estimate_service.py tests/domains/test_erp_order_shared_form_scripts.py -q`
  - `python tools/perf/perf_scan.py --guard`

## 구현 순서

1. 서비스 계층: 수동 행 정규화/병합 helper 추가 및 단위 테스트 작성.
2. 프리뷰 JS: `manualRows` 상태, `+` 컨트롤 행, 수동 행 input 렌더, 삭제, debounce 저장 추가.
3. 공유 저장 JS: `estimate_preview` 보존 키 추가.
4. 템플릿 CSS: 수동 행/컨트롤/export hide 스타일 추가.
5. JS cache bust 버전 갱신.
6. focused test + APP_OK + perf guard.
7. 구현 후 1:1 소스 리뷰 및 full inspection.

## 구현 상태

사용자 승인 후 순차 구현 완료.

- 수동 행 저장 위치: `structured_data.estimate_preview.manual_rows`
- 서버 병합: `extract_estimate_data_from_order()`에서 원본 제품 행 사이에 수동 행 병합
- UI: 계약서 프리뷰 표 행 사이 `+` 버튼, 수동 행 입력, 삭제 버튼
- 저장: 프리뷰 JS 상태 -> `window.__erpLastStructuredData.estimate_preview.manual_rows` -> 기존 `erpSaveStructured()` 경로
- 검증: focused pytest, APP_OK, perf guard, browser-engine smoke
