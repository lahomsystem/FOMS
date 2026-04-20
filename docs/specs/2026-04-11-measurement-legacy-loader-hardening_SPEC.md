# measurement Legacy Loader Hardening Spec
> 작성일: 2026-04-11 | 상태: 🟢 승인됨

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
legacy measurement shim 경로에서 `document.write` 기반 loader를 제거하고, 기존 legacy static URL을 계속 유지하면서도 strict CSP에 더 안전한 방식으로 canonical measurement JS를 제공한다. 이번 배치에서는 전역 CSP 헤더나 템플릿 구조를 바꾸지 않고, legacy shim 파일 자체만 hardening한다.

### 1.2 기능 요구사항
1. `static/js/erp/measurement*.js` 및 `static/js/measurement-image-export.js`는 더 이상 `document.write`를 사용하지 않는다.
2. legacy shim URL은 계속 유효해야 하며, 기존 canonical measurement JS와 동일한 동작을 제공해야 한다.
3. canonical measurement JS의 동작 순서와 `DOMContentLoaded` 계약을 깨지 않도록, legacy shim은 runtime injection 대신 정적 mirror 방식으로 제공한다.
4. future drift를 막기 위해 legacy shim과 canonical file sync를 확인하는 focused regression test를 추가한다.
5. `templates/measurement/dashboard.html`, app-wide CSP header, bundler 도입은 이번 배치에 포함하지 않는다.

### 1.3 예외/제약 조건
- 이번 배치는 legacy shim 5개와 해당 sync regression test만 다룬다.
- canonical source는 계속 `static/js/measurement/*.js`가 단일 기준선이다.
- manual/automated sync contract 없이 수동 복붙만 남기지 않는다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `static/js/erp/measurement.js` | canonical `static/js/measurement/dashboard.js`의 legacy mirror로 교체 |
| `static/js/erp/measurement-mobile.js` | canonical `static/js/measurement/mobile.js`의 legacy mirror로 교체 |
| `static/js/erp/measurement-dashboard-columns.js` | canonical `static/js/measurement/dashboard-columns.js`의 legacy mirror로 교체 |
| `static/js/erp/measurement-manual-rows.js` | canonical `static/js/measurement/manual-rows.js`의 legacy mirror로 교체 |
| `static/js/measurement-image-export.js` | canonical `static/js/measurement/image-export.js`의 legacy mirror로 교체 |
| `tests/test_measurement_legacy_shims.py` | legacy shim과 canonical file sync/no-document.write regression test 추가 |
| `docs/specs/2026-04-11-measurement-legacy-loader-hardening_SPEC.md` | 이번 배치 범위를 기록 |
| `docs/ARCHIVE_INDEX.md` | 신규 spec 문서 인덱스 추가 |

### 2.2 아키텍처 방향
- canonical source는 계속 `static/js/measurement/*.js`다.
- legacy path는 runtime loader가 아니라 “compatibility mirror”로 유지한다.
- test에서 mirror body와 canonical body의 일치를 강제해 split-brain을 막는다.

### 2.3 의존성 및 영향 범위
- 영향 범위:
  - legacy measurement static URL consumers
  - measurement image export path
- 비영향 범위:
  - `templates/measurement/dashboard.html` canonical script order
  - app-wide CSP header/config
  - measurement map/API/backend 로직
- DB 마이그레이션: 없음

## 3. Steps — 실행 단계
- [ ] Step 1: legacy shim 5개를 `document.write` 없는 compatibility mirror로 교체한다.
- [ ] Step 2: legacy shim/canonical sync를 강제하는 focused regression test를 추가한다.
- [ ] Step 3: measurement focused pytest와 `APP_OK` smoke를 재검증한다.
- [ ] Step 4: 후감리 후 다음 운영/수동 QA 체크로 넘긴다.

## 4. 검증 기준
- [ ] `python -c "import app; print('APP_OK')"` 통과
- [ ] `python -m pytest tests/test_measurement_legacy_shims.py tests/test_erp_measurement_mobile_render.py -q` 통과
- [ ] legacy shim 파일에 `document.write`가 남아 있지 않음
- [ ] legacy shim body와 canonical source body sync regression test 통과

## 5. 참고 자료
- 관련 상태: `docs/AI_STATUS.md`의 measurement legacy loader known issue
- 관련 계획: `docs/plans/2026-04-11-quality-ops-separation-plan.md` Track C
- 관련 구현 기준:
  - `templates/measurement/dashboard.html`
  - `static/js/measurement/*.js`
