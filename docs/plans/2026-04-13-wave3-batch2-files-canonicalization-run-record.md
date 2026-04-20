# Wave 3 Batch W3-B2 — Pilot canonicalization (`files`)

> **batch ID:** W3-B2  
> **risk axis:** code (`files` context only)  
> **실행일:** 2026-04-13

## Scope lock

- **`foms/api/files.py` + `apps/api/files.py`만** 변경. 다른 context/API **금지**.

## Inputs consumed

- `docs/plans/2026-04-13-wave3-batch1-files-contract-freeze-run-record.md`
- `W3-B1` contract table (drift 없음)

## Wave 2 key normalization

| 항목 | 값 |
|------|-----|
| registry lane | `files` |
| spec domain | Wave 3 API canonicalization |
| FR20 context key | `files` |

## Contract table

- `W3-B1`과 동일 (route path / methods / decorator / response shape **변경 없음**).

## Hidden side effect inventory

- `W3-B1`과 동일 (presigned/redirect/storage 분기).

## FR19 decision

- **extend:** 단일 canonical 모듈 `foms/api/files.py` 추가.  
- `apps/api/files.py`는 **delete 내용 후 merge-style**으로 canonical에서 re-export (기호 동일).

## Changes made

- `foms/api/files.py` (신규 — canonical)
- `apps/api/files.py` (thin re-export shim)

## Spec §4 delta summary

- product file delta: `+foms/api/files.py`
- wrapper file delta: `apps/api/files.py` → re-export만
- test file delta: 없음 (기존 contract 유지)
- canonical target: `foms.api.files`
- removal target: 장기적으로 `apps.api.files` shim (`Wave 8`)
- new shim retirement wave: **Wave 8** (spec Wave 8 legacy bridge)
- local README: **불필요** (단일 모듈)

## Verification

| Command | Result |
|---------|--------|
| `python -c "import app; print('APP_OK')"` | PASS (`APP_OK`) |
| `python tools/harness/verify_result.py --json` | PASS (`success: true`) |

## FR20 / README gate

- 단일 런타임 모듈 — **`foms/api/files/README.md` 생략** (계획 FR20 조건 충족).

## Test footprint decision

- 신규 micro test **미추가**; 회귀는 harness + import smoke.

## Direction Lock answers

1–10: 단일 SSOT(`foms.api.files`), shim은 명시적 retirement, 기능 변경 없음 — **전부 예/해당**

## Drift / stop decision

- contract drift **없음**.

## Shim / adapter record

| shim | canonical target | retirement wave | removal condition |
|------|------------------|-----------------|-------------------|
| `apps.api.files` re-export | `foms.api.files` | Wave 8 | 소비자가 전부 `foms.api.files` 직접 import로 이전 |

## Next step or defer

- **W3-B3** (`address` only).

---

**touched files:** `foms/api/files.py`, `apps/api/files.py`, 본 run record
