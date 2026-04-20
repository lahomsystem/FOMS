# Wave 3 Batch W3-B5 — Aggregate-read canonicalization (`personal_board` only)

> **batch ID:** W3-B5  
> **risk axis:** code (`personal_board` context only)  
> **실행일:** 2026-04-13

## Scope lock

- **`personal_board`만** 변경. `events` 및 기타 API **금지** (W3-B4 loser).

## Inputs consumed

- `docs/plans/2026-04-13-wave3-batch4-aggregate-read-lock-run-record.md` (winner = `personal_board`)

## Wave 2 key normalization

| 항목 | 값 |
|------|-----|
| registry lane | `personal_board` / ERP aux API |
| spec domain | Wave 3 API canonicalization |
| FR20 context key | `personal_board` |

## Contract table

- W3-B4 winner 테이블과 동일 — **drift 없음**  
  - `GET /api/personal-board/summary`, `@login_required`, JSON 응답 형태 유지.

## Hidden side effect inventory

- W3-B4와 동일 (DB 읽기·session·lazy import in helpers). **새 쓰기 경로 없음.**

## FR19 decision

- **extend:** 단일 canonical 모듈 `foms/api/personal_board.py` 추가.  
- `apps/api/personal_board.py`는 **delete·내용 이전 후** thin wrapper (Blueprint + route + `login_required` + canonical 호출).

## Changes made

- `foms/api/personal_board.py` — canonical (헬퍼 + `personal_board_summary_response()`)
- `apps/api/personal_board.py` — thin adapter
- `tests/test_foms_namespace_imports.py` — canonical 경로 `foms.api.personal_board`로 contract 검증 정렬

## Spec §4 delta summary

| 항목 | 내용 |
|------|------|
| product file delta | `+foms/api/personal_board.py` |
| wrapper file delta | `apps/api/personal_board.py` → thin |
| test file delta | `tests/test_foms_namespace_imports.py` (import 소스만 `foms.api.personal_board`) |
| canonical target | `foms.api.personal_board` |
| removal/merge target | 장기: `apps.api.personal_board`를 re-export-only로 축소 (Wave 8) |
| new shim retirement wave | **Wave 8** (legacy bridge retirement) |
| local README update | **불필요** — 단일 런타임 모듈, FR20 게이트 통과 |

## Verification

| Command | Result |
|---------|--------|
| `python -c "import app; print('APP_OK')"` | PASS (`APP_OK`) |
| `python tools/harness/verify_result.py --json` | PASS (`success: true`) |
| `python -m pytest tests/test_foms_namespace_imports.py::test_personal_board_uses_canonical_erp_policy_imports tests/test_foms_namespace_imports.py::test_erp_display_lazy_callers_use_canonical_import_paths -q` | PASS (2 passed) |

## FR20 / README gate

- **단일 모듈** `foms/api/personal_board.py` — context당 3모듈 미만 → **local `README.md` 생략** (계획 FR20).

## Test footprint decision

- **기존** `test_foms_namespace_imports.py` **확장/정렬**만 (canonical import 경로). 신규 micro test 파일 **미추가**.

## Direction Lock answers

1. SSOT: `foms.api.personal_board` — **예**  
2. split-brain: wrapper는 명시적 retirement — **예**  
3. FR19: 단일 파일 extend — **예**  
4. 새 파일 1개 = 유지보수 chunk — **예**  
5–6. 증가 파일에 removal wave 기록 — **예**  
7. README 생략 조건 충족 — **예**  
8. 패턴 반복 시 정리 — **예**  
9. product vs bridge 구분 — **예**  
10. 구조만, 동작 변경 없음 — **예**

## Drift / stop decision

- contract drift **없음**. high-risk 쓰기 발견 **없음** → stop 조건 미해당.

## Shim / adapter record

| shim | canonical target | retirement wave | removal condition |
|------|------------------|-----------------|-------------------|
| `apps.api.personal_board` (thin) | `foms.api.personal_board` | Wave 8 | 테스트·소비자가 canonical import로 이전하고 wrapper가 re-export-only 가능할 때 |

## Next step or defer

- **W3-B6** — high-risk backlog freeze + closeout (`events` 등 defer register).

---

**touched files:** `foms/api/personal_board.py`, `apps/api/personal_board.py`, `tests/test_foms_namespace_imports.py`, 본 run record
