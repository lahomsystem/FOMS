# WD 계산기 행 프리미티브 (Container Query) Spec
> 작성일: 2026-07-16 | 상태: 🟢 승인됨 (순차 진행 지시)

## 1. What

### 1.1 최종 결과물
해상도마다 `@media`를 늘리지 않고, **행(카드) 자기 폭**에 반응하는 공유 레이아웃 토큰·규칙을 둔다.
- PC·모바일 엔진 마크업(`.base-component-row`)이 좁으면 세로 스택, 넓으면 기존 다열.
- 태블릿 미러(`.wdc2-brow` 5열 계약)는 **건드리지 않음** (엔진은 은닉).
- 입력 높이·갭은 `--wd-line-*` 토큰 단일 출처.

### 1.2 기능 요구사항
1. `static/css/wdcalculator/wd-line.css` 신설 — tokens + `container-type` + `@container wd-line`
2. `calculator.html`에 defer-safe `<link>` (캐시버스트)
3. 좁은 컨테이너(≤520px): mode / details / width / delete 가 전폭 스택
4. 모바일 기존 전폭 가드(제품명·단가방식)가 토큰(`--wd-line-touch-h`)을 참조
5. 계약 테스트: 파일 존재, `container-name: wd-line`, `@container`, link `?v=`

### 1.3 비범위 / 금지
- tablet-skin.js/css 5열 그리드·span 변경
- pricing-core / React 폼 라이브러리 도입
- Bootstrap 전면 폐기, 뷰포트별 HTML 복제
- `display:contents` 전면 제거(2B에서 점진 이전)

## 2. How

| 파일 | 변경 |
|------|------|
| `static/css/wdcalculator/wd-line.css` | 신설 |
| `templates/wdcalculator/calculator.html` | link |
| `static/css/wdcalculator/mobile.css` | touch 높이 토큰 참조 |
| `tests/domains/test_wdcalculator_engine_v2_contract.py` | CQ 계약 |
| Spec 본 문서 | SSOT |

### 2.2 아키텍처
```
엔진 SSOT (.base-component-row)
  └─ wd-line.css  (@container)     ← 공유
모바일 스킨 (mobile.css / enhance)  ← IA·터치만
태블릿 스킨 (wdc2-*)               ← 미러 그리드 유지
```
Media query = 셸(헤더/레일). Container query = 행 내부.

## 3. Steps
- [x] Step A: Spec + `wd-line.css` + link + 토큰 연결 + 계약 + deploy (`67a04b10`)
- [ ] Step B: mobile `contents` 해체를 CQ/그리드 zone으로 이전 (후속)
- [ ] Step C: PC dense row를 Bootstrap col 대신 zone grid로 이전 (후속)

## 4. 검증
- [ ] APP_OK
- [ ] pytest engine contract (CQ pins)
- [ ] pre_push_smoke → deploy → CI green
- [ ] 스테이징: 좁은 PC 창·모바일 커스텀에서 입력 전폭

## 5. 참고
- CEO 리서치: CQ + stack-first + 3스킨 유지
- 선행 핫픽스: `362bcfd7` (PC select / 직접 즉시입력 / 모바일 전폭)
