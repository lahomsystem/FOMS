# Mobile-safe Upload Compression Spec
> 작성일: 2026-06-30 | 상태: ✅ 완료

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
FOMS의 사진 업로드 압축은 유지하되, 모바일 기기에서 여러 장 업로드 시 발생할 수 있는 UI 멈춤·메모리 폭증·탭 종료 위험을 줄인다.

최종 사용자는 다음 상태를 보게 된다.

- 현장 모바일에서 10장 이상 사진 업로드 시에도 화면이 멈춘 것처럼 보이지 않는다.
- 압축 중에는 `이미지 최적화 중 x/y` 상태가 보인다.
- 업로드는 R2 direct upload 흐름을 유지한다.
- 압축 실패, 브라우저 미지원, timeout 발생 시 원본 업로드로 자동 fallback 한다.
- 같은 이름의 파일 여러 개를 선택해도 서로 다른 presigned session/key가 올바르게 매칭된다.

### 1.2 기능 요구사항
1. 클라이언트 이미지 압축은 계속 사용한다.
2. 서버-side 이미지 압축은 도입하지 않는다.
3. Phase 1에서는 Web Worker/OffscreenCanvas 신규 파일을 만들지 않는다.
4. `compressImageFile()`은 모바일 안전형으로 교체한다.
   - non-image, GIF, SVG, video, PDF는 압축하지 않는다.
   - 압축 시도 MIME은 `image/jpeg`, `image/png`, `image/webp`로 제한한다. HEIC/AVIF 등 기타 `image/*`는 원본 fallback 한다.
   - 800KB 미만 이미지는 압축하지 않는다.
   - 압축 대상 이미지는 긴 변 기준 `1920px`, 품질 `0.82` 기본값을 사용한다.
   - MIME과 filename은 Phase 1에서 변경하지 않는다.
   - `toBlob` 결과의 `blob.type`이 원본 `file.type`과 다르면 원본을 반환한다.
   - compressed file이 원본보다 크거나, blob이 없거나, 오류/timeout이면 원본을 반환한다.
   - `readAsDataURL()` 대신 `createImageBitmap()` 우선, object URL 기반 fallback을 사용한다.
5. batch upload는 압축 단계와 업로드 단계를 분리한다.
   - 모바일/coarse pointer: 압축 동시성 `1`, PUT 업로드 동시성 `3`
   - 데스크톱: 압축 동시성 `2`, PUT 업로드 동시성 `5`
6. presigned session은 압축 후 파일의 `size`로 요청한다.
7. batch session은 optional `client_id`를 받고 response에 그대로 반환한다.
8. frontend는 `client_id`로 session을 매칭한다. `sessionMap[file.name]` 의존을 제거한다.
9. 기존 `/api/upload/session/batch` caller와 API는 backward compatible이어야 한다.
10. migrated path에는 `CONCURRENCY = 10`과 unbounded `Promise.all(fileList.map(...))`를 남기지 않는다.

### 1.3 예외/제약 조건
- 하자 증빙 품질 때문에 원본 삭제/원본 별도 압축 손실 정책은 이 작업 범위가 아니다.
- PNG → JPEG/WebP 변환은 Phase 1에서 하지 않는다. Content-Type signed URL mismatch 방지 목적이다.
- 영상 압축/transcoding은 하지 않는다.
- R2 storage lifecycle/retention policy는 별도 Spec 대상이다.
- 채팅 업로드는 Phase 1B 범위에 포함한다. 단, batch crash 핵심 경로가 아니므로 ERP/AS/시공/도면 batch 경로 안정화 뒤 single-file 정렬로 처리한다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `static/js/runtime/upload-progress.js` | mobile-safe `compressImageFile()` v2, queue policy/helper, batch prepare/session/upload helper 추가 |
| `foms/api/files/direct_upload.py` | `/api/upload/session/batch`에서 optional `client_id` echo 지원 |
| `static/js/orders/erp-order-shared.js` | ERP 첨부/품목 첨부/AS 수령 업로드를 shared helper로 이전, `CONCURRENCY=10` 제거 |
| `templates/construction/partials/scripts.html` | 시공/AS 현장 사진 batch upload를 shared helper로 이전 |
| `static/js/cs/as-dashboard.js` | AS modal batch upload를 shared helper로 이전 |
| `templates/drawing/partials/workbench_detail_body.html` | 도면 전달/수정요청 batch upload 동시성 제한 및 session 매칭 정렬 |
| `static/js/orders/dashboard/erp-dashboard-drawing.js` | 도면 대시보드 upload 동시성 제한 및 helper 정렬 |
| `templates/orders/partials/dashboard_scripts_drawing.html` | 포함되는 legacy duplicate 경로도 동일 계약 유지 |
| `templates/orders/edit_order.html` | blueprint single upload가 v2 `compressImageFile()` fallback 정책을 사용하도록 유지/정렬 |
| `templates/partials/chat_scripts_file.html` | Phase 1B: image single upload 압축 여부를 명시적으로 정렬 |
| `tests/support/upload_progress_contract_node_checks.js` | `upload-progress.js` Node contract 추가 |
| `tests/contracts/runtime/test_upload_progress_contracts.py` | Node contract pytest runner 추가 |
| `tests/domains/test_upload_compression_surface_contracts.py` | cross-surface source contract 추가 |
| `tests/domains/test_direct_upload_api.py` 또는 `tests/domains/test_erp_orders_structured_put.py` | batch `client_id`, duplicate filename, complete size contract 추가 |

### 2.2 아키텍처 방향
기존 Phase D 원칙은 유지한다.

```text
Client -> session API -> R2 PUT -> complete API
```

변경되는 것은 frontend 준비 단계다.

```text
files selected
-> optimistic UI
-> prepare/compress queue
-> batch session with client_id + compressed size
-> R2 PUT queue
-> complete
-> refresh
```

`upload-progress.js`를 runtime upload SSOT로 둔다. 각 화면은 UI 상태 업데이트와 도메인별 complete endpoint만 가진다.

### 2.3 Shared helper contract
`upload-progress.js`에 다음 전역 helper를 둔다.

- `window.fomsGetUploadQueuePolicy(options)`
  - coarse pointer/mobile 감지
  - `{ compressConcurrency, uploadConcurrency }` 반환
- `window.fomsShouldCompressImage(file, options)`
  - 압축 대상 판단
- `window.compressImageFile(file, options)`
  - 기존 public API 유지
  - 실패 시 reject하지 않고 원본 반환
- `window.fomsPrepareUploadFiles(files, options)`
  - 각 파일에 stable `clientId`, `originalFile`, `file`, `compressed`, `skipped`, `error` 메타 부여
  - compression progress callback 호출
- `window.fomsRunLimitedQueue(items, concurrency, worker)`
  - unbounded Promise.all 제거용 queue runner

Direct upload 화면별 helper는 두 선택지 중 더 작은 변경을 선택한다.

1. 공통 helper가 session/PUT/complete까지 처리
2. 공통 helper는 prepare/queue만 맡고 각 화면의 기존 uploadOne을 보존

Phase 1 구현은 risk가 낮은 2번부터 시작한다. 이후 중복 제거는 작은 단위로 진행한다.

### 2.4 Backend API compatibility
`/api/upload/session/batch`는 기존 request를 계속 받는다.

기존:
```json
{"files":[{"filename":"a.jpg","size":123}],"folder":"orders/1/attachments"}
```

추가:
```json
{"files":[{"client_id":"foms-upload-1","filename":"a.jpg","size":123}],"folder":"orders/1/attachments"}
```

response는 기존 envelope을 유지하고, 각 session 안에 `client_id`가 있으면 echo 한다.

```json
{"success":true,"sessions":[{"filename":"a.jpg","client_id":"foms-upload-1","upload_url":"...","key":"...","expires_at":"..."}]}
```

`client_id`는 신뢰 보안값이 아니다. frontend 매칭용 opaque token이다. 서버는 문자열 타입만 echo 하며, 길이는 최대 128자로 제한한다. 문자열이 아니거나 너무 길면 해당 entry에서는 `client_id`를 생략하고 기존 동작으로 처리한다.

### 2.5 관련 결정 갱신
기존 결정: `docs/harness/policy/DECISIONS.md` 2026-02-26 업로드 로직 표준화 — 최대 10개 동시.

이번 변경의 의미:
- 10개 병렬은 R2 direct PUT 도입 당시 네트워크/서버 부하 개선용이었다.
- 이미지 압축이 들어간 현재 모바일에서는 CPU/RAM이 새 병목이다.
- 새 표준은 "압축 동시성"과 "업로드 동시성"을 분리한다.

구현 완료 시 `DECISIONS.md`에 2026-06-30 결정을 추가한다.

### 2.6 의존성 및 영향 범위
- DB migration 없음.
- Python dependency 없음.
- 신규 frontend dependency 없음.
- R2/S3 API shape는 backward compatible.
- 서비스워커 변경 없음.
- `upload-progress.js`는 shared layout에서 `defer` 유지해야 한다.

## 3. Steps — 실행 단계

### Step 0 — 테스트 먼저
- [ ] Node contract runner 추가 또는 기존 WDCalculator runner 패턴 재사용
- [ ] `upload-progress.js` contract 작성
- [ ] source surface contract 작성
- [ ] backend direct upload API contract 작성

### Step 1 — Backend batch session `client_id`
- [ ] `api_upload_session_batch()`에서 `client_id = file_data.get("client_id")`
- [ ] session payload에 `client_id` 조건부 포함
- [ ] duplicate filename 2개가 서로 다른 key와 client_id로 응답되는지 테스트

### Step 2 — `upload-progress.js` mobile-safe compression
- [ ] `readAsDataURL()` 제거
- [ ] `createImageBitmap(file, { imageOrientation: "from-image" })` 우선 사용
- [ ] `ImageBitmap`은 성공/실패와 관계없이 `finally`에서 `bitmap.close()`로 정리
- [ ] object URL fallback 구현 및 `URL.revokeObjectURL()` 보장
- [ ] 긴 변 기준 resize
- [ ] decode/draw/toBlob 전체 compression task timeout 구현
- [ ] timeout 시 `settled` guard를 세우고 canvas dimension reset, object URL revoke, bitmap close cleanup을 즉시 실행
- [ ] timeout 이후 늦게 도착한 decode/load/toBlob callback은 결과를 무시하고 cleanup만 재실행
- [ ] 각 heavy compression item 시작 전 `requestAnimationFrame` yield로 progress text paint 기회 보장
- [ ] canvas width/height 0으로 정리
- [ ] 작은 파일 skip
- [ ] 실패 시 원본 반환

### Step 3 — Queue policy/helper
- [ ] coarse pointer 감지
- [ ] mobile `compress=1`, `upload=3`
- [ ] desktop `compress=2`, `upload=5`
- [ ] `fomsRunLimitedQueue()` 추가
- [ ] `fomsPrepareUploadFiles()` 추가
- [ ] progress callback: `이미지 최적화 중 x/y`

### Step 4 — ERP shared upload migration
- [ ] `erpUploadCommonAttachmentFiles()` direct path에서 prepare 후 batch session 요청
- [ ] `erpDoDirectUploadOne()`는 prepared file/session을 받을 수 있게 정렬
- [ ] `sessionMap[file.name]` 제거
- [ ] non-direct fallback도 압축된 file 사용
- [ ] `CONCURRENCY=10` 제거

### Step 5 — construction / AS / drawing migration
- [ ] `templates/construction/partials/scripts.html` queue 적용
- [ ] `static/js/cs/as-dashboard.js` queue 적용
- [ ] `templates/drawing/partials/workbench_detail_body.html` unbounded Promise.all 제거
- [ ] `static/js/orders/dashboard/erp-dashboard-drawing.js` queue 적용
- [ ] `templates/orders/partials/dashboard_scripts_drawing.html` 동일 계약 확인

### Step 6 — single upload 정렬
- [ ] `templates/orders/edit_order.html` blueprint path 확인
- [ ] `templates/partials/chat_scripts_file.html` image single upload compress 적용

### Step 7 — 문서/결정 갱신
- [ ] `DECISIONS.md`에 mobile-safe upload concurrency 결정 추가
- [ ] 필요 시 `docs/AI_STATUS.md`는 session_stop hook 또는 수동 워크플로로 갱신

## 4. 검증 기준

### 4.1 필수 자동 검증
- [ ] `python -c "import app; print('APP_OK')"`
- [ ] `python -m pytest tests/contracts/runtime/test_upload_progress_contracts.py -q`
- [ ] `python -m pytest tests/domains/test_upload_compression_surface_contracts.py -q`
- [ ] `python -m pytest tests/domains/test_direct_upload_api.py -q` 또는 확장된 focused direct upload 테스트
- [ ] 기존 영향권 focused tests:
  - `python -m pytest tests/domains/test_erp_order_shared_form_scripts.py -q`
  - `python -m pytest tests/domains/test_as_dashboard_attachment_modal.py -q`
  - `python -m pytest tests/domains/test_construction_dashboard_mobile.py -q`
  - `python -m pytest tests/domains/test_drawing_workbench_mobile.py -q`
- [ ] `python tools/perf/perf_scan.py --guard`

### 4.2 수동/브라우저 검증
- [ ] 모바일 viewport에서 ERP 주문 첨부 10장 업로드
- [ ] coarse-pointer stub 또는 실제 모바일에서 queue policy가 `compress=1`, `upload=3`으로 동작함을 확인
- [ ] 중복 파일명 2개 업로드
- [ ] 압축 실패 stub 또는 작은 파일 skip 경로 확인
- [ ] R2 direct upload 성공 후 attachment 목록 refresh
- [ ] progress text가 `이미지 최적화 중 x/y`와 업로드 진행 상태를 보여줌

### 4.3 Acceptance criteria
- [ ] migrated frontend path에 `CONCURRENCY = 10` 없음
- [ ] migrated frontend path에 `sessionMap[file.name]` 없음
- [ ] migrated batch direct path는 압축 후 `size`로 session 요청
- [ ] source contract는 `Promise.all(fileList.map(...))`, `const uploadPromises = fileList.map(...); await Promise.all(uploadPromises)`, chunked `Promise.all(chunk.map(...))` 중 업로드 파일 처리 패턴을 모두 차단하거나 limited queue 사용을 증명
- [ ] backend batch session response가 `client_id`를 echo
- [ ] duplicate filename이 wrong key/session으로 complete 되지 않음
- [ ] 실패 시 기능 중단 없이 원본 fallback 또는 multipart fallback

## 5. 위험 및 대응

| 위험 | 대응 |
|------|------|
| 모바일 브라우저 `createImageBitmap` 미지원 | object URL + `Image` fallback |
| HEIC/AVIF 등 unsupported `image/*` | `image/jpeg`, `image/png`, `image/webp`만 압축 시도; 나머지는 원본 fallback |
| canvas encoder가 다른 MIME 반환 | `blob.type === file.type`이 아니면 원본 fallback |
| `ImageBitmap` 메모리 누수 | `finally`에서 `bitmap.close()` 호출 |
| decode/draw/`toBlob` hang | compression task 전체 timeout 후 원본 fallback |
| timeout 후 late callback 메모리 점유 | `settled` guard + cleanup 재실행으로 late result 무시 |
| progress text 미표시 | heavy item 전 `requestAnimationFrame` yield |
| 압축 후 MIME mismatch | Phase 1에서 MIME/filename 보존, PNG→JPEG 금지 |
| duplicate filename session collision | `client_id` 매칭 |
| upload progress가 0%에 오래 머묾 | compression progress text 추가 |
| helper 대형 리팩터로 회귀 | 화면별 기존 uploadOne 보존, prepare/queue부터 점진 적용 |
| unconverted path 잔류 | source contract로 `CONCURRENCY=10`, `sessionMap[file.name]`, unbounded Promise.all 차단 |

## 6. 구현 금지선

다음은 사용자 승인 전 금지한다.

- 제품 코드 수정
- 테스트 파일 추가
- API shape 변경
- `DECISIONS.md` 갱신

현재 상태는 구현 및 검증 완료다.

## 7. 참고 자료

- `docs/harness/policy/DECISIONS.md` — 2026-02-26 업로드 로직 표준화, 2026-02-27 도면 파일 생명주기
- `docs/plans/2026-02-22-phase-d-direct-upload-design.md` — Direct R2 Upload 설계
- `static/js/runtime/upload-progress.js`
- `foms/api/files/direct_upload.py`
- `static/js/orders/erp-order-shared.js`
- `templates/construction/partials/scripts.html`
- `static/js/cs/as-dashboard.js`
- `templates/drawing/partials/workbench_detail_body.html`

## 8. Plan Status

`완료`
