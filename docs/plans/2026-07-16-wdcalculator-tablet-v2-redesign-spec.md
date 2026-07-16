# WD 계산기 태블릿 가로 v2 — PC 기능 전량 이식 재설계 Spec

- 날짜: 2026-07-16
- 목업: https://claude.ai/code/artifact/e2cf7805-04e5-4acb-aa58-ac7c169afcaa (3프레임)
- 상태: **사용자 승인 대기** (승인 후 writing-plans → SDD 구현)

## 1. 배경 / 문제

현행 태블릿 계산기(e1bf823c, 표형 UI)는 모바일 목업 frame11 혈통이다. 사용자 지시:
모바일 목업 방식을 버리고 **PC 버전 기능 전체를 태블릿에 맞게 그라운드업 재설계**한다.

현행 판의 결함:
- D/H 열이 존재하나 가격은 W 기준 → 무의미한 입력 부담 + 센티널 직렬화 복잡도.
- 추가 옵션/쿠폰·배송·비고 카드가 공간만 차지하고 정보 밀도 낮음.
- PC 기능 누락: 행별 선택/직접 모드, 직접입력 30cm/1m 단가 방식, 행별 추가금,
  비고 선택/직접 토글, 단가 표시 토글 등이 태블릿 표면에 없거나 불완전.
- 중요/비중요 입력의 폭 위계 부재.

## 2. 목표 (사용자 지시 매핑)

| # | 지시 | 반영 |
|---|------|------|
| 1 | 디자인 스킬로 UX/UI 신규 | minimalist(웜 모노크롬+그린 액센트) 어휘로 그라운드업 |
| 2 | 실사용자 persona | 상담팀: 통화/대면 중 제품+W 입력 90%, 시선 분산 상태에서 총액 상시 가시 |
| 3 | 한 화면 완결 | 좌 워크시트(입력 전부) + 우 라이브 패널(계산 전부) + 하단 액션바, 무스크롤 목표 |
| 4 | 입력 폭 위계 | W 128px·18px 볼드 / 제품 1fr / 할인·배송 104px / 비고 칩 |
| 5 | D/H 제거 | 열 삭제. 구견적 센티널은 행별 추가금 서브행으로 자연 노출·보존(§6) |
| 6 | 직접입력 넓게 | 직접 행은 상세 셀이 [30cm/1m 세그 + 단가 입력 + 1cm 자동] 3필드로 확장 |
| 7 | PC 기능 100% | §5 커버리지 표 25항목 — 구현 완료 기준(체크표) |
| 8 | 디자인 자유 | erp-pro 문법 비의존. 단 신규 CSS는 토큰 변수로 정의(인라인 스타일 금지 준수) |
| 9 | HTML/CSS/JS 재구현 | tablet-skin.js/css 전면 재작성(v2). 엔진은 READ-ONLY |

## 3. 접근 대안

- **A안(채택): tablet-skin v2 그라운드업** — 신규 DOM + 은닉 엔진 위젯 양방향 미러
  (T16/T18 검증 패턴 승계). 디자인 자유도 최대, 엔진 무접촉.
- B안: 현행 표형 CSS 개보수(D/H 제거+스트립화) — 빠르나 "재설계" 지시 미충족,
  레이아웃 위계 재편 불가.
- C안: 태블릿 전용 독립 페이지 + 엔진 포크 — 계산/저장 로직 이중화, SSOT 위반. 기각.

## 4. 레이아웃 (목업 Frame 1–3)

게이트: `(min-width:992px) and (orientation:landscape) and (pointer:coarse)` 且 비임베디드
(현행 유지). 세로 coarse = 모바일 셸(SSOT 3-조건) 불변. embedded(frame13 iframe)는 PC
레이아웃 유지. 좌측 72px 전역 레일 존치.

```
[72 레일][ 워크시트 (flex) ][ 진행 견적 패널 312px ]
          탑바: WD계산기 · 고객명(밑줄 대형) · 견적검색 · 제품설정
          기본 구성 섹션: [모드칩 64|제품/직접 1fr|W 128|단가 156|✕ 40]
          추가 옵션 섹션: [배지 64|옵션 1fr|금액 156|✕ 40]
          조정 스트립: 할인(−) · 배송(＋,포함☑) · 비고 칩
          액션바: 총견적(대형) · [견적 계산] · [진행 견적에 추가→]
패널:     현재 견적 브레이크다운(라이브) → 진행 견적 스택(단가 토글) → 전체합계+새견적/전체저장
```

시각 언어: **입력칸 = 흰 배경+실선 테두리 / 계산값 = 그린 틴트**(#EFF7F2, 잉크 #0B5C3E).
웜 본 캔버스(#EDEBE4), 행 높이 56px, 입력 48px, 숫자 tabular-nums. 직접 모드 칩은
앰버 틴트로 구분. 저장 견적은 우측 오버레이(392px) — 기존 48px 접힘 레일 폐지,
진입점은 탑바 [견적 검색] 단일화.

## 5. PC 기능 커버리지 표 (구현 완료 기준 — 전 항목 ✓ 전 "완료" 금지)

| # | PC 기능 (엔진 위젯) | 태블릿 v2 표현 |
|---|---------------------|----------------|
| 1 | 고객명 `#customerName` | 탑바 밑줄형 대형 입력 (미러) |
| 2 | 저장 견적 사이드바(검색·목록·새로고침·불러오기) | [견적 검색] → 우측 오버레이 (노드 도킹) |
| 3 | 제품 설정 링크 | 탑바 버튼 |
| 4 | 구성 행 추가 `#addBaseComponentBtn` | [＋ 구성 행 추가] / [✎ 직접 입력 행 추가](추가 후 모드 전환) |
| 5 | 행별 선택/직접 토글 `.base-mode-btn` | 행 모드칩 탭 전환 |
| 6 | 제품 선택 `.base-product-select` | 제품 시트(3열 그리드, 30cm 단가 병기) |
| 7 | W 입력 `.base-width-input` | W 셀 (numeric inputmode) |
| 8 | 직접: 방식 `.base-manual-pricing-type` + `.base-manual-price30/-price1/-price1m` | 세그(30cm/1m) + 단가 입력 + 1cm 자동(readonly) 인라인 |
| 9 | 행별 추가금 `.base-add-fee-btn/-fee-name/-fee-amount` | 들여쓴 서브행 + [＋ 추가금] |
| 10 | 행 삭제 `.base-remove-btn` | ✕ (클릭 위임) |
| 11 | 행 단가 표시 | 그린 틴트 셀 = `wdcComputeCurrentEstimateMath` 관찰 + ×N구간 메타 |
| 12 | 옵션 행 추가 `#addOptionBtn` | [＋ 옵션 추가] |
| 13 | 옵션 선택 `[data-category-option-select]` + 직접명 `.option-name-input` + 금액 `[data-option-price]` | 옵션 시트(카테고리›옵션) + 직접 입력 + 금액 셀 |
| 14 | 옵션 행 삭제 | ✕ |
| 15 | 비고 `#btnAddNote` + select/직접 textarea 토글 | 비고 칩 + 시트(저장 문구 그리드 + 직접 입력) |
| 16 | 쿠폰 할인 `#globalCouponValue` | 스트립 할인 필 (104px) |
| 17 | 배송비 `#shippingCost` + 포함 `#shippingIncluded` | 스트립 배송 필 + 체크 |
| 18 | 견적 계산 `#calculateBtn` | 액션바 [견적 계산] |
| 19 | 견적 추가 `#addEstimateBtn` | 액션바 [진행 견적에 추가→] |
| 20 | 견적 저장 `#saveEstimateBtn` | 패널 [전체 저장] (※cloneNode 교체 위젯 → 미러, 이동 금지) |
| 21 | 새 견적 `#resetEstimateBtn` | 패널 [새 견적] (※동적 생성 → 미러) |
| 22 | 진행 견적 리스트 `#estimatesListContainer`(수정/삭제) | 패널 도킹 + 카드 재스타일 (엔진 렌더 소유 유지) |
| 23 | 단가 표시 토글 `#wdUnitPriceMetaToggle` | 패널 헤더 스위치 (미러) |
| 24 | 견적 결과(`#totalBasePrice/#totalAdditionalPrice/#totalPrice/#finalPrice/#couponInfo/#notesDisplay`) | 패널 브레이크다운 + 액션바 총견적 (노드 미러) |
| 25 | embedded 모드 | v2 스킨 미적용 (기존 동작 유지) |

## 6. D/H 센티널 하위 호환

- D/H 입력 열 삭제. `encodeDH/parseDH/writeRowDH` 계열 제거.
- 구견적의 `[규격] D.. H..` 센티널 = 이름 있는 0원 행별 추가금 → **§5-9 서브행으로
  자연 노출**(파싱 특별처리 불필요). 사용자가 지우면 소멸, 두면 재직렬화 보존.
- 0원 추가금은 pricing-core가 가격/표시 skip — 총액 무영향(기존 확인 사항).

## 7. 라이브 총액 (표시 전용)

- 1차: 기존 검증 패턴 = 엔진 노드(`#finalPrice` 등) MutationObserver 미러.
- 보강: `wdcComputeAggregateTotals`(순수 함수) 관찰로 입력 즉시 브레이크다운 갱신.
  **표시 전용** — 엔진 상태·저장 데이터에 무개입, [견적 계산] 버튼 계약 불변.
  구현 시 엔진 갱신 타이밍 실사 후 보강 범위 확정.

## 8. 파일 계획

- `static/js/wdcalculator/tablet-skin.js` — 전면 재작성 (미러 계약 승계 + v2 DOM)
- `static/css/wdcalculator/tablet-skin.css` — 전면 재작성 (토큰 변수 정의)
- `templates/wdcalculator/calculator.html` — ?v 범프 (자체 link — 번들 아님)
- 계약 테스트: 기존 표형(P11) 구조 테스트 → v2 구조 테스트로 대체
- 손대지 않는 것: primary-form.js · pricing-core.js · estimate-lifecycle.js ·
  composition.js · mobile-enhance.js · wdcalculator_body.html 마크업 · blueprint.py

## 9. 검증 계획

- APP_OK + 계약 테스트(v2 구조·미러 계약·게이트 3열거) + pre_push_smoke exit 0
- coarse landscape 에뮬(CSSOM strip + matchMedia 패치)로 실렌더 확인, PC/폰/embedded 무회귀
- 라운드트립: 견적 추가→전체 저장→검색→불러오기, D/H 센티널 구견적 로드(서브행 노출)
- 커버리지 표 25항목 체크표(✓/✗+사유) — 전 항목 ✓ 전 "완료" 보고 금지

## 10. 비범위

- 세로(portrait) 태블릿 계산기 — 모바일 빌더 유지
- 엔진 리팩터/추가금 편집기 0원 행 노출 개선(기존 FLAG) — 별도 건
- 제품 설정 페이지 태블릿화 — 별도 건
