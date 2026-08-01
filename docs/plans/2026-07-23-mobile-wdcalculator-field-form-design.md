# 모바일 계산기 Field Form (세그먼트 + 세로 전폭 가격) Spec
> 작성일: 2026-07-23 | 상태: 🟢 승인됨 · 구현 완료 (계획: `2026-07-23-mobile-wdcalculator-field-form-plan.md`)  
> 접근법: ① 수술(HOLD SCOPE) — 사용자 승인  
> 선행 철회(모바일만): `2026-07-16-wdcalculator-input-ux-3surface_SPEC.md`의 “모드=네이티브 select만”

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
모바일(<992px) WD 계산기 **기본 구성** 행에서:
1. 모드(제품선택 / 커스텀 / 직접)를 **3칸 세그먼트 버튼**으로 선택
2. 커스텀·직접 입력을 **위→아래 전폭**으로 쌓고, **가격 칸을 크게** 보이게
3. PC·계산 엔진·제품 바텀시트·빌더 IA는 그대로

### 1.2 기능 요구사항
1. **모드 세그먼트**: 툴바 한 줄 `[제품선택][커스텀][직접]` + 오른쪽 끝 `✕삭제`(간격 확보)
2. **SSOT**: 숨김 `.base-mode-select`가 엔진 정본. 세그먼트 탭 → select.value 동기 → 기존 `applyBaseMode` 경로
3. **커스텀 세로 스택**: 제품명 → 단가방식(기존 `.base-manual-pricing-type` select, 전폭) → 30cm(원) 전폭·큰 글자 → 1cm(자동) → 가로(mm) → 추가 항목
4. **직접 세로 스택**: 항목 이름 → 금액 전폭·큰 글자 → `+ 직접입력`
5. **가격 가독**: 가격/금액 input 높이 ≥48px, `font-variant-numeric: tabular-nums`, 잘림 0
6. **데스크톱(≥992)**: 기존 네이티브 select·레이아웃 유지

### 1.3 예외/제약
- `pricing-core` 수식·제품 카탈로그 시트·할인/옵션/비고 IA 변경 금지
- 태블릿은 이번 라운드 비범위(후속)
- 인라인 스타일·동기 CDN script·N+1 등 perf 가드 위반 금지
- ERP shell fragment idempotent 유지(`window.__*_BOUND` 패턴 해당 시)

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 |
|------|------|
| `static/js/wdcalculator/mobile-enhance.js` | `buildBaseToolbar`: 세그먼트 UI 생성, `.base-mode-select` 숨김+동기, 삭제 버튼 배치 |
| `static/css/wdcalculator/mobile.css` | 세그먼트 스타일; 커스텀/직접 `display:contents` 한줄 압착 폐기 → 세로 전폭; 가격 크기 |
| `static/css/wdcalculator/builder.css` | builder 셸 내 manual/direct 그리드를 모바일 세로 스택에 맞춤 |
| `templates/wdcalculator/calculator.html` (+ scripts_config) | `?v=` 캐시 범프 |
| 관련 계약 테스트 | 리터럴/셀렉터 갱신(필요 시) |

### 2.2 아키텍처 방향
- 기존 패턴: `mobile-enhance.js`가 host DOM을 **재배치·위임**만 하고 계산은 host SSOT
- 모드 UI만 세그먼트로 교체; select는 DOM에 남기되 화면에서 숨김
- 커스텀/직접은 CSS로 Bootstrap col을 전폭 블록으로 덮음 (마크업 재작성 없음 = 접근법 ①)

### 2.3 의존성·영향
- 영향: 모바일 계산기 UI만
- DB/API/마이그레이션: 없음
- `2026-07-16` 3surface 스펙: 모바일 모드 UI 조항만 부분 철회(문서에 명시)

## 3. Steps — 실행 단계
- [x] Step 1: `buildBaseToolbar`에 3칸 세그먼트 + select 동기 + 삭제 격리
- [x] Step 2: 모바일 CSS — 모드 select 숨김, 세그먼트 터치 타깃
- [x] Step 3: 커스텀 세로 전폭 + 가격 ≥48px tabular-nums
- [x] Step 4: 직접 fee 이름/금액 세로 전폭
- [x] Step 5: `?v=` 범프 + 계약 테스트 갱신
- [x] Step 6: `APP_OK` + wdcalculator pytest + (가능 시) 390px 스모크

## 4. 검증 기준
- [ ] 390px: 모드=세그먼트 3칸, 네이티브 모드 드롭다운 비가시 (수동 스모크)
- [ ] 커스텀: `187,000` 가격 잘림 없음 (수동 스모크)
- [ ] 직접: 금액 전폭·가독 (수동 스모크)
- [ ] 삭제 ✕가 모드 버튼과 붙지 않음 (수동 스모크)
- [ ] ≥992px 데스크톱 회귀 없음 (수동 스모크)
- [x] `python -c "import app; print('APP_OK')"`
- [x] `pytest` wdcalculator 관련 계약 통과

## 5. 비범위 (명시)
- 빌더 IA 재작성, 태블릿 스킨, 제품 피커 시트 변경, 새 견적 기능

## 6. 승인 기록
- 모드: 3칸 세그먼트 (사용자)
- 가격 배치: 전부 세로 전폭 (사용자)
- 접근법: ① 수술 (사용자)
- §1~§3 설계: OK (사용자)
