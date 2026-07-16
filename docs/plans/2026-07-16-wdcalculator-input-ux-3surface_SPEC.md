# WD 계산기 3표면 입력 UX (드롭다운 + 정렬) Spec
> 작성일: 2026-07-16 | 상태: 🟢 승인됨 (implement 지시)

## 1. What

### 1.1 최종 결과물
PC·모바일·태블릿 WD 계산기 **기본구성** 행에서:
1. 모드(제품선택/커스텀/직접)는 **네이티브 `<select>`** 로만 선택 (모달·바텀시트 금지)
2. 라벨·입력·삭제 버튼이 한 기준선으로 정렬
3. fee는 `＋ 직접입력`으로만 추가 (자동 시드 없음)

### 1.2 기능 요구사항
1. 엔진 SSOT: `.base-mode-select` + 숨김 `.base-mode-btn` 위임 유지
2. 태블릿: `openBaseModeSheet` 제거 → 모드 칸 네이티브 select
3. 모바일: btn-group 툴바 이동 대신 select 노출; describeBaseRow 라벨 정리
4. 태블릿 5열 그리드 자식 수·direct span(`grid-column:2/4`) 유지; 모드 열 폭만 select용으로 소폭 확대 허용

### 1.3 비범위
- pricing-core 수식, 제품 카탈로그 시트, ERP 타탭, 제품설정

## 2. How

| 파일 | 변경 |
|------|------|
| `static/js/wdcalculator/primary-form.js` | select SSOT + applyBaseMode |
| `templates/wdcalculator/partials/wdcalculator_styles.html` | PC 모드 열·행 정렬 |
| `static/js/wdcalculator/tablet-skin.js` | 시트→select, 정렬 |
| `static/css/wdcalculator/tablet-skin.css` | modesel + colhead nowrap + 겹침 방지 |
| `static/js/wdcalculator/mobile-enhance.js` | select 툴바·라벨 |
| `static/css/wdcalculator/mobile.css` | 모드 select |
| `templates/wdcalculator/calculator.html` + scripts_config | `?v=20260716g` |
| 계약 테스트 | 리터럴 갱신 |

## 3. 검증
- [ ] 모드 변경 시 시트/모달 0
- [ ] CUSTOM 제품명·W·서브행 겹침 0
- [ ] 헤더 「제품 구성」세로쓰기 0
- [ ] pytest 관련 계약 + APP_OK + pre_push_smoke → deploy → CI green
