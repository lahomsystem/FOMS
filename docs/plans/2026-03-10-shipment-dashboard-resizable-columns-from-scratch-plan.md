# 출고 대시보드 컬럼 리사이즈 재작성 설계안

작성일: 2026-03-10
상태: 설계 초안
대상: `templates/erp_shipment_dashboard.html`

## 1. 목적

출고 대시보드의 컬럼 가로폭 제어를 기존 inline style, 셀별 CSS, 모바일 예외 규칙의 혼합 구조에서 분리한다.

목표는 아래 3가지다.

1. 사용자가 마우스로 컬럼 폭을 직접 조절할 수 있게 한다.
2. 폭 정의를 한 군데에서만 관리하게 만든다.
3. 기존 출고 대시보드의 편집 기능과 정렬/가독성을 유지하면서, 컬럼 폭 수정 작업을 반복하지 않게 만든다.

## 2. 현재 문제

현재 구조의 근본 문제는 컬럼 폭 정의가 여러 층으로 흩어져 있다는 점이다.

1. 헤더 `th`에 inline width/min-width가 있다.
2. 본문 셀에 별도 CSS width/min-width/max-width가 있다.
3. 모바일 미디어쿼리에서 일부 컬럼만 다시 덮어쓴다.
4. 편집 UI가 셀 내부에서 width를 다시 잡는다.
5. 컬럼 폭을 바꿀 때 헤더와 바디를 동시에 수정해야 한다.

이 구조에서는 한 컬럼 폭을 바꿀 때 아래 부작용이 반복된다.

1. 헤더/본문 얼라인먼트가 어긋남
2. 다른 컬럼 폭이 연쇄적으로 깨짐
3. 모바일 예외 규칙이 데스크톱 폭을 다시 덮음
4. 편집 input/button이 셀 폭보다 커져 레이아웃이 무너짐

즉, 지금 문제는 숫자 조정이 아니라 구조 문제다.

## 3. 재작성 원칙

이번 작업은 부분 수정이 아니라 재작성 기준으로 간다.

1. 컬럼 폭의 진실 원천은 `colgroup` 하나만 둔다.
2. 헤더와 바디는 같은 컬럼 모델을 공유한다.
3. 사용자 리사이즈는 JS가 `col` 요소 width만 변경한다.
4. 변경된 폭은 `localStorage`에 저장한다.
5. 새로고침 후 저장된 폭을 복원한다.
6. 최소 폭은 컬럼별로 강제한다.
7. 모바일에서는 드래그 리사이즈를 끄고 기본 프리셋 폭만 쓴다.

## 4. 범위

1차 적용 범위는 출고 대시보드 한 화면만이다.

대상 컬럼:

1. 상세
2. 고객
3. 대리점(발주사)
4. 제품
5. 규격(W/300)
6. 현장주소
7. 시공시간
8. 도면담당자
9. 시공자
10. 담당자

## 5. 최종 구조

### 5.1 템플릿 구조

현재 `table > thead > tbody` 구조는 유지한다.

추가/변경:

1. `table` 바로 아래에 `colgroup` 추가
2. 각 컬럼에 `col[data-col-key="..."]` 부여
3. 각 `th`에도 같은 `data-col-key` 부여
4. 각 리사이즈 가능한 `th` 안에 `resize handle` 요소 추가

예시 구조:

```html
<table class="table shipment-table" id="shipment-dashboard-table">
  <colgroup>
    <col data-col-key="detail">
    <col data-col-key="customer">
    <col data-col-key="orderer">
    <col data-col-key="product">
    <col data-col-key="spec">
    <col data-col-key="address">
    <col data-col-key="construction_time">
    <col data-col-key="drawing_managers">
    <col data-col-key="construction_workers">
    <col data-col-key="manager">
  </colgroup>
  <thead>
    <tr>
      <th data-col-key="detail"><span>상세</span><button class="col-resize-handle"></button></th>
      ...
    </tr>
  </thead>
  <tbody>...</tbody>
</table>
```

### 5.2 폭 정의

폭 정의는 JS 설정 객체 하나로만 관리한다.

예시:

```js
const SHIPMENT_COLUMN_SCHEMA = {
  detail: { defaultWidth: 60, minWidth: 48, resizable: true },
  customer: { defaultWidth: 90, minWidth: 80, resizable: true },
  orderer: { defaultWidth: 90, minWidth: 80, resizable: true },
  product: { defaultWidth: 100, minWidth: 60, resizable: true },
  spec: { defaultWidth: 84, minWidth: 70, resizable: true },
  address: { defaultWidth: 320, minWidth: 180, resizable: true, flexible: true },
  construction_time: { defaultWidth: 95, minWidth: 95, resizable: true },
  drawing_managers: { defaultWidth: 95, minWidth: 95, resizable: true },
  construction_workers: { defaultWidth: 95, minWidth: 95, resizable: true },
  manager: { defaultWidth: 95, minWidth: 95, resizable: true }
};
```

중요:

1. 헤더 inline width 제거
2. 본문 셀 width/min-width/max-width 제거
3. `colgroup`에만 width 반영

## 6. CSS 설계

새 CSS는 별도 블록 또는 별도 파일로 분리한다.

권장 파일:

1. `static/css/shipment-dashboard-columns.css`
2. `static/js/shipment-dashboard-columns.js`

핵심 CSS:

```css
.shipment-table {
  table-layout: fixed;
}

.shipment-table th,
.shipment-table td {
  position: relative;
}

.shipment-table .col-resize-handle {
  position: absolute;
  top: 0;
  right: -4px;
  width: 8px;
  height: 100%;
  border: 0;
  background: transparent;
  cursor: col-resize;
}

.shipment-table th:hover .col-resize-handle {
  background: rgba(13, 110, 253, 0.12);
}
```

텍스트 처리:

1. `제품`, `현장주소`는 `white-space: normal`
2. `overflow-wrap: anywhere`
3. 나머지는 기본 `nowrap` 유지 가능

## 7. JS 설계

### 7.1 저장 키

브라우저별 사용자 저장 키:

```js
const STORAGE_KEY = 'foms.shipmentDashboard.columnWidths.v1';
```

### 7.2 동작

초기화 시:

1. schema 로드
2. 저장된 사용자 폭 로드
3. `colgroup`에 width 적용
4. 리사이즈 핸들 이벤트 바인딩

드래그 시:

1. `mousedown`에서 시작 폭/마우스 X 저장
2. `mousemove`에서 새 폭 계산
3. `minWidth` 이하로 못 내려가게 clamp
4. 해당 `col` width 갱신
5. `mouseup`에서 저장

### 7.3 리셋

상단에 `컬럼 폭 초기화` 버튼 추가

동작:

1. 저장된 폭 삭제
2. schema 기본값 복원

## 8. 현장주소를 늘리는 방식

지금처럼 “제품 줄이면 주소 늘림”을 매번 하드코딩하지 않는다.

원칙:

1. 모든 컬럼은 기본 폭을 가진다.
2. `현장주소`만 `flexible` 컬럼으로 둔다.
3. 사용자가 다른 컬럼을 줄이면 전체 테이블 가용 폭에서 주소가 상대적으로 더 넓게 보인다.
4. 필요하면 리셋 시 주소 기본폭도 더 크게 둔다.

즉, `현장주소`는 수동 보정 대상이 아니라 기본적으로 가장 넓은 정보 컬럼으로 설계한다.

## 9. 편집 셀과의 호환성

중요한 제약:

1. `시공시간`
2. `도면담당자`
3. `시공자`

이 세 컬럼은 현재 row 기반 입력 시스템으로 정리된 상태다.

따라서 컬럼 리사이즈는 이 입력 시스템을 건드리면 안 된다.

호환성 원칙:

1. 입력 로직 JS와 컬럼 리사이즈 JS는 분리
2. 리사이즈는 `table/colgroup/th`만 제어
3. 입력 UI는 셀 내부 `width: 100%`만 유지
4. 편집 버튼/입력창 크기는 컬럼 최소 폭 안에 들어가게 제한

## 10. 모바일 정책

모바일에서는 리사이즈를 끈다.

이유:

1. 터치 드래그가 스크롤과 충돌함
2. 좁은 화면에서 컬럼 리사이즈보다 카드형/가로스크롤이 더 중요함

정책:

1. `max-width: 768px` 에서는 핸들 숨김
2. 저장된 폭 복원도 무시하거나 최소한만 적용
3. 모바일 프리셋 폭 별도 유지

## 11. 구현 단계

### Phase 1. 구조 정리

1. `th` inline width 제거
2. 본문 셀 width/min/max CSS 제거
3. `colgroup` 도입
4. 기본 schema 추가

### Phase 2. 리사이즈 기능

1. 핸들 렌더링
2. drag JS 구현
3. 최소 폭 적용
4. 저장/복원 적용

### Phase 3. UX 마무리

1. 초기화 버튼
2. 모바일 예외 처리
3. hover/focus 표시 정리
4. 가로 스크롤 상태 확인

### Phase 4. 코드 정리

1. 기존 폭 관련 dead CSS 제거
2. shipment 대시보드 테이블 전용 스타일을 별도 파일로 분리
3. 리사이즈 JS를 별도 파일로 분리

## 12. 삭제 대상

이번 재작성 때 아래는 제거 대상이다.

1. `th style="width: ..."` 중심 폭 제어
2. `.shipment-address-cell` 같은 개별 셀 width 하드코딩
3. 제품/주소/편집 칼럼별 산발적인 min/max-width 보정
4. 컬럼 폭 조절 때문에 계속 늘어난 임시 예외 규칙

## 13. 검증 기준

기능 검증:

1. 컬럼 드래그로 폭 변경 가능
2. 새로고침 후 폭 유지
3. 초기화 버튼으로 기본값 복원
4. `시공시간`, `도면담당자`, `시공자` 입력/삭제/불러오기 정상

레이아웃 검증:

1. 헤더/본문 세로선 정렬 유지
2. 제품 줄바꿈 정상
3. 현장주소 줄바꿈 정상
4. 가로 스크롤 시 레이아웃 깨짐 없음

회귀 검증:

1. 출고 대시보드 렌더 오류 없음
2. Jinja 파싱 정상
3. 모바일 카드형/가로스크롤 깨짐 없음

## 14. 최종 판단

이 작업은 “옵션 기능 추가”가 아니라, 현재 컬럼 폭 제어의 근본 구조를 정리하는 작업이다.

지금처럼 픽셀을 계속 수동 조절하는 방식은 유지보수 비용이 너무 높다.

따라서 다음 작업 방향은 명확하다.

1. 기존 컬럼 폭 제어 코드를 더 덧대지 않는다.
2. `colgroup + schema + resize handle + localStorage` 구조로 재작성한다.
3. 출고 대시보드 한 화면에서 먼저 완성한 뒤, 필요하면 다른 대시보드로 확장한다.
