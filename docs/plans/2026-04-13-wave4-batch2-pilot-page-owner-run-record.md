# Wave 4 Batch W4-B2 — Pilot page owner canonicalization (`cs`)

> **batch ID:** W4-B2  
> **risk axis:** code / page owner  
> **pilot_context:** `cs`  
> **실행일:** 2026-04-14

## Scope lock

- **허용:** `foms/web/cs/*`, legacy `apps/erp_completion_page.py` thin shim, 본 run record.  
- **금지:** `foms/platform/blueprints.py`, template path 변경, API 본편, DB.

## Inputs consumed

| # | 소스 |
|---|------|
| 1 | `docs/plans/2026-04-13-wave4-batch1-pilot-contract-freeze-run-record.md` |
| 2 | Measurement precedent `foms/web/measurement/dashboard.py` + `apps/erp_measurement_dashboard.py` shim |

## Wave key normalization

| 키 | 값 |
|----|-----|
| registry lane | ERP HTML — completion / CS |
| spec domain | CS / completion (§2.3, §2.9) |
| FR20 context key | `completion` |

## Public contract table (unchanged — owner만 이동)

| route path | methods | auth | blueprint | endpoint | `render_template` (post W4-B3) |
|------------|---------|------|-----------|----------|--------------------------------|
| `/erp/completion` | GET | `@login_required` | `erp_completion_page_bp` | `erp_completion_dashboard` | `cs/completion_dashboard.html` |

## Hidden coupling / side effect

| 유형 | 내용 |
|------|------|
| shared shell | `layout.html`, `erp_sub_nav`, 조건부 `erp_mobile_shell` — **이동 안 함** |
| API | 기존 `partials/erp_completion_scripts.html` — Wave 4에서 API 변경 없음 |

## FR19 decision

- **merge:** legacy `apps/erp_completion_page.py` → `importlib` module alias → `foms.web.cs.completion_dashboard`
- **extend:** canonical `foms/web/cs/completion_dashboard.py`에 Blueprint + 뷰 SoT
- **delete:** 동일 본문 이중 유지 없음

## Spec §4 delta summary

| 항목 | 값 |
|------|-----|
| product file delta | +`foms/web/cs/__init__.py`, +`foms/web/cs/completion_dashboard.py` |
| wrapper delta | `apps/erp_completion_page.py` → 6-line shim |
| test delta | W4-B3 직후 `tests/test_foms_namespace_imports.py`에 cs shim·template 계약 확장 |
| canonical target | `foms/web/cs/completion_dashboard.py` |
| removal/merge target | 장기: `apps/erp_completion_page` import 경로는 레거시 소비자 소멸 시 제거 검토 |
| new shim retirement wave | apps thin layer 유지 중 — Wave 1~4 공통 bridge 정책 |
| local README | **없음** (FR20 미충족: 단일 module) |

## Verification

| 검사 | 결과 |
|------|------|
| `python -c "import app; print('APP_OK')"` | ✅ |
| `python tools/harness/verify_result.py --json` | ✅ `success: true` |
| `tests/test_foms_namespace_imports.py` (cs 관련) | ✅ |
| `tests/test_menu_config.py` | ✅ (5 passed) |
| web+worker parity | **N/A** — `app`/worker import contract 파일 미변경 (blueprints·Procfile 동결) |

## FR20 / README gate

- 단일 module → README 생성 안 함.

## Test footprint decision

- 기존 네임스페이스 테스트에 **shim identity + template 존재** assertion 확장.

## Direction Lock (10문항)

| # | 답 | 한 줄 근거 |
|---|-----|------------|
| 1 | yes | 페이지 SoT는 `foms/web/cs` 한 곳 |
| 2 | yes | 레거시 모듈명은 shim으로만 유지; 제거 시점 run record에 기록 |
| 3 | yes | delete→merge→extend 순서 준수 |
| 4 | yes | 단일 `completion_dashboard.py` chunk |
| 5 | yes | product+shim 최소 증가 |
| 6 | N/A | 순증가는 bridge 정책상 명시적 retirement와 함께 |
| 7 | N/A | README 불필요 |
| 8 | yes | 동일 패턴 반복 시에도 owner 선명 |
| 9 | yes | `apps`는 bridge, `foms/web`은 product |
| 10 | yes | 라우트/권한/비즈니스 규칙 변경 없음 |

## Next batch

- **W4-B3** — `templates/cs/completion_dashboard.html` canonical + legacy thin wrapper.
