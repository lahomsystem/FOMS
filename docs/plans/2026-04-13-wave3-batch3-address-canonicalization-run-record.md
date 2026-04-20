# Wave 3 Batch W3-B3 — Second low-risk canonicalization (`address`)

> **batch ID:** W3-B3  
> **risk axis:** code (`address` context only)  
> **실행일:** 2026-04-13

## Scope lock

- **`foms/api/address.py` + `apps/api/address.py`만** 변경.

## Inputs consumed

- `W3-B2` 완료
- 기존 `apps/api/address.py` 동작 (Kakao 프록시)

## Wave 2 key normalization

| 항목 | 값 |
|------|-----|
| registry lane | `address` |
| spec domain | Wave 3 API canonicalization |
| FR20 context key | `address` |

## Contract table

| route path | methods | decorator stack | auth | response shape | behavior-sensitive |
|------------|---------|-----------------|------|------------------|---------------------|
| `/api/address/search` | GET | `@route` → `@login_required` | required | `jsonify({success, results})` 또는 오류 | 쿼리 variant 순서: `_query_variants`; 주소 API는 **variant == 원본 q일 때만** 호출; 키워드 API는 variant마다; `requests` **timeout=10**; 헤더 `KakaoAK` |

## Hidden side effect inventory

| 항목 | 내용 |
|------|------|
| 외부 HTTP | Kakao `dapi.kakao.com` address + keyword 엔드포인트 |
| 중복 제거 | `(x, y, road|address name)` 키 |
| size clamp | 1–15 |

## FR19 decision

- 단일 모듈 `foms/api/address.py`로 **extend**; apps는 re-export만.

## Changes made

- `foms/api/address.py` (canonical, 신규)
- `apps/api/address.py` (thin)

## Spec §4 delta summary

- product: `+foms/api/address.py`
- wrapper: `apps/api/address.py` thin
- canonical: `foms.api.address`
- shim retirement: Wave 8 (동일 패턴)
- README: 단일 모듈 — **생략**

## Verification

| Command | Result |
|---------|--------|
| `python -c "import app; print('APP_OK')"` | PASS |
| `python tools/harness/verify_result.py --json` | PASS |

## FR20 / README gate

- 단일 파일 canonical — **README 불필요**.

## Test footprint decision

- 기존 테스트 확장 우선; 신규 micro pair 없음.

## Direction Lock answers

- 기능/쿼리 정책 변경 없이 이동 — **예 (구조만)**

## Drift / stop decision

- 없음.

## Query/response contract inventory (요약)

- **Preprocessor:** `_strip_detail`, `_query_variants` (순서 고정)
- **Normalize:** `_doc_to_result`, `_keyword_doc_to_result`
- **Kakao:** address URL 먼저(원본 q일 때만), 이후 keyword per variant

## Shim record

| shim | canonical | retirement | removal |
|------|-------------|------------|---------|
| `apps.api.address` | `foms.api.address` | Wave 8 | 직접 import 전환 후 |

## Next step or defer

- **W3-B4** docs: `personal_board` vs `events` winner lock.

---

**touched files:** `foms/api/address.py`, `apps/api/address.py`, 본 run record
