# Wave 3 Batch W3-B1 — Pilot contract freeze (`files`)

> **batch ID:** W3-B1  
> **risk axis:** docs / contract freeze (`apps.api.files` only)  
> **선행:** W3-B0  
> **실행일:** 2026-04-13

## Scope lock

- **`apps/api/files.py`만** 분석 대상으로 한다 (읽기 전용).
- 런타임 코드·`foms/api/*`·`blueprints.py` **변경 없음**.

## Inputs consumed

- `docs/plans/2026-04-13-wave3-batch0-readiness-gate-run-record.md` (pilot = `files` lock)
- `apps/api/files.py` (현재 99줄, L1–L99)

## Wave 2 key normalization

| 항목 | 값 |
|------|-----|
| registry lane | `files` (`blueprints.py`: `from apps.api.files import files_bp`) |
| spec domain | Modular monolith rebaseline — **Wave 3 API canonicalization** |
| FR20 context key | `files` (단일 canonical 모듈 가정 시 README는 **선택**; 다층 패키지 시 필수) |

## Contract table (route별)

| route path | methods | decorator stack | auth | response shape | external dependency |
|------------|---------|-------------------|------|----------------|------------------------|
| `/api/files/view/<path:storage_key>` | GET | `@files_bp.route` → `@login_required` | login_required | R2/S3: **302 redirect** to presigned URL; local: `send_file` inline; 오류 시 `jsonify({success, message})` 400/404/500 | `get_storage()`, `storage.get_download_url`, `send_file`, `redirect` |
| `/api/files/presigned-urls/<path:storage_key>` | GET | 동일 | login_required | R2/S3: `jsonify({success, view_url, download_url})` 동일 URL; local: `view_url`/`download_url`이 **앱 경로** 문자열 (`build_file_*`) | 동일 + `build_file_view_url` / `build_file_download_url` |
| `/api/files/download/<path:storage_key>` | GET | 동일 | login_required | R2/S3: redirect with `response_content_disposition=attachment`; local: `send_file(..., as_attachment=True)` | `get_download_url(..., response_content_disposition=...)` |

### Module-level public helpers (import contract)

| 심볼 | 계약 |
|------|------|
| `build_file_view_url(storage_key)` | 문자열 `"/api/files/view/" + storage_key` (leading slash 고정) |
| `build_file_download_url(storage_key)` | 문자열 `"/api/files/download/" + storage_key` |
| `files_bp` | `Blueprint('files', __name__, url_prefix='/api/files')` |

**다른 모듈에서의 import:** `build_file_view_url`, `build_file_download_url` — `erp_orders_*`, `attachments`, `chat` 등에서 사용. **Thin wrapper 이후에도 `apps.api.files`에서 re-export 유지 필수.**

## Hidden side effect inventory

| 항목 | 내용 |
|------|------|
| presigned URL 발급 | R2/S3에서 `get_download_url(..., expires_in=3600)` — **객체 스토어 읽기 전용 URL** (앱 DB 쓰기 없음) |
| storage provider 분기 | `storage.storage_type in ['r2','s3']` vs 로컬 `upload_folder` |
| redirect vs send_file | 클라우드는 redirect; 로컬은 파일 시스템 읽기 |
| path validation | `'..' in storage_key` 또는 `storage_key.startswith('/')` → 400 |
| 예외 로깅 | `print` + `traceback.format_exc()` (요청당 부작용: 로그만) |

## FR19 decision

- **extend:** 기존 단일 모듈을 유지하고 `foms/api/files.py` **단일 canonical 모듈**로 **확장(이동)** — package 분할 **불필요** (route·helper 밀도가 단일 파일 수용 범위).

## Changes made

- 본 run record 파일만.

## Spec §4 delta summary

- product/canonical: (W3-B2에서 `foms/api/files.py` 추가 예정)  
- wrapper: (W3-B2에서 `apps/api/files.py` thin화 예정)  
- test: 기존 contract test 확장 우선  
- canonical target: `foms/api/files` (단일 `.py` 모듈)  
- shim: `apps.api.files` — **Wave 8** legacy bridge retirement 검토; removal 조건: `foms.api.files` 직접 import로 소비자 전환 완료 시.

## Verification

| 검사 | 결과 |
|------|------|
| docs-only | ✅ |
| presigned/redirect 누락 없음 | ✅ |

## FR20 / README gate

- canonical이 **단일 런타임 모듈**로 예상 → **`foms/api/files/README.md` 의무 없음** (FR20: 3+ 모듈/패키지 다층 시). W3-B2에서 재확인.

## Test footprint decision

- 신규 micro test pair **불필요**; 기존 import/contract 테스트가 있으면 **확장**.

## Direction Lock answers

1. SSOT: canonical 경로를 `foms/api/files`로 고정 예정 — **예**  
2. split-brain: `apps` shim 유지로 일시 이중 — Wave 8 removal 조건 문서화 — **예**  
3. FR19: 단일 모듈 우선 — **예**  
4. chunk: 단일 파일 — **예**  
5. 파일 수: +1 canonical, apps 얇아짐 — 순증가 아님(책임 이동)  
6. 제거: Wave 8 shim 제거 조건 기록 — **예 (W3-B2 run record)**  
7. README: 단일 모듈 — 생략 가능  
8. 반복: 패턴 일관 — **예**  
9. API-only 경계 유지 — **예**  
10. 기능 변경 없음 — **예**

## Drift / stop decision

- stop 없음.

## Canonical target shape decision

- **`foms/api/files.py` 단일 모듈** (package 불필요: 3 route + 2 URL builder + 동일 예외 패턴).

## Next step or defer

- **`W3-B2`:** `foms/api/files.py` 구현 + `apps/api/files.py` thin re-export.

---

**touched files:** `docs/plans/2026-04-13-wave3-batch1-files-contract-freeze-run-record.md`  
**verification result:** PASS (docs-only)
