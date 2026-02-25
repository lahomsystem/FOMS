# 코드 리뷰: ERP Beta 파일 업로드 속도 (시공/AS는 빠르고 일반 첨부는 느림)

**일자**: 2026-02-25  
**요청**: GDM 관점 업로드 프로세스 점검 — 시공·AS 업로드는 빠른데 ERP Beta 일반 첨부는 느린 원인 분석  
**참조**: `.cursor/agents/grand-develop-master.md`

---

## 1) 무엇을 발견했는가 (What was found)

### 업로드 경로 두 가지

| 구분 | 시공 완료 / AS 접수 (빠름) | ERP Beta 첨부·제품 이미지 (느릴 수 있음) |
|------|---------------------------|----------------------------------------|
| **진입점** | `erp_construction_scripts.html` | `erp_beta_js.html` (edit_order / add_order) |
| **플로우** | session → PUT(R2 직송) → complete | **USE_DIRECT_UPLOAD=true** 이면 동일; **false** 이면 FormData POST(서버 경유) |
| **동시성** | CONCURRENCY=3, `Promise.all(chunk.map(doUploadOne))` | true일 때 동일 3; **false일 때 순차** `for (i=0; i<files.length; i++) await fetch(POST)` |
| **파일 전달** | 브라우저 → R2 PUT (presigned) | true: 동일 / false: **브라우저 → Flask → R2** (이중 구간) |

### 느려질 수 있는 원인

1. **USE_DIRECT_UPLOAD=false 인 경우**
   - `services/context_processors.py`: `use_direct_upload = use_direct_upload_env and storage.storage_type in ('r2','s3')`  
   - R2/S3이면 기본 true. 로컬 스토리지·예외 시 false → **FormData 경로** 사용.
   - FormData 경로: **파일별 순차** 업로드 + **파일이 매번 Flask를 경유** (업로드 시간·메모리 2배 부담).
   - `api_order_attachments_upload`(POST `/api/orders/<id>/attachments`)에서 **ASYNC_ATTACHMENT_THUMBNAIL=false** 이면  
     `storage._generate_thumbnail(file, ...)` 를 **동기** 호출 → 요청이 썸네일 생성 끝날 때까지 대기.

2. **complete 단계의 R2 호출**
   - `api_order_attachments_complete`: `storage.object_exists(key)` → `head_object` 1회,  
     이어서 `storage.client.head_object` 로 `ContentLength` 조회 → **파일당 head_object 2회** (object_exists 내부 1회 + file_size 1회).
   - 시공/AS도 동일 complete API 사용하므로, **직접 업로드 경로를 쓰면** 이 부분은 동일 비용.

3. **동시성**
   - 시공/AS: 항상 CONCURRENCY=3.
   - ERP Beta: USE_DIRECT_UPLOAD=true일 때만 CONCURRENCY=3; false일 때는 1(순차).

### 구조적 요약 (GDM §4)

- **빠른 경로**: 브라우저 → session(JSON) → PUT(presigned) → complete(JSON). 파일 바이트는 서버를 거치지 않음. 3개씩 병렬.
- **느린 경로**: 브라우저 → FormData POST → Flask가 파일 수신 후 R2 업로드. 순차 처리 + 필요 시 동기 썸네일.

---

## 2) 무엇을 작업/수정했는가 (What was changed)

- **문서화**: 원인 분석 및 권장 사항을 이 코드 리뷰 문서에 기록.
- **적용 완료 (2026-02-25)**: 권장 2) complete 단계 R2 호출 줄이기
  - **서버** `apps/api/attachments.py` `api_order_attachments_complete`: 요청 body의 `size`를 수신해 유효하면(0 ≤ size ≤ max) 사용하고, **두 번째 head_object(ContentLength 조회) 생략**. `used_client_size`로 구분.
  - **클라이언트** complete 요청 body에 `size: file.size` 추가:
    - `templates/partials/erp_beta_js.html` (erpDoDirectUploadOne)
    - `templates/partials/erp_construction_scripts.html` (시공 완료, 시공 재업로드, AS 접수 3곳)
    - `templates/erp_drawing_workbench_detail.html` (attachments/complete 1곳)
  - 효과: 파일당 R2 head_object 2회 → 1회(object_exists만)로 감소, 502/지연 완화 기대.
- **추가 적용 (여전히 느림 대응)**:
  - **R2/S3 클라이언트 타임아웃** (`services/storage.py`): `botocore.config.Config(connect_timeout=10, read_timeout=15, retries=1)` 적용. 환경 변수 `R2_CONNECT_TIMEOUT`, `R2_READ_TIMEOUT`으로 조정 가능. 장시간 대기 시 502 대신 빠르게 실패.
  - **DELETE 첨부** (`apps/api/attachments.py`): 본문(storage_key) + 썸네일(thumbnail_key) R2 삭제를 `ThreadPoolExecutor`로 병렬 실행 → 대기 시간을 합이 아닌 max로 단축.

### 로그 해석 (complete 502 + badge/session 지연)
- **complete 502 (2분 2초)**: 게이트웨이 타임아웃. 서버가 2분 동안 응답하지 못함 → R2 `head_object` 등이 응답 지연.
- **complete 200 (2초)**: 클라이언트 `size` 적용 시 정상 응답은 2초대 가능.
- **badge 1분 29초 / 9초**: `/erp/api/notifications/badge`는 30초 캐시 있음. 캐시 미스 시에도 DB 1~2회 조회 수준이라 자체 지연은 짧음. **한 워커가 complete로 2분 잡고 있으면 다른 요청(badge, session)이 대기** → 1분대·9초대 지연 발생.
- **대응**: R2 클라이언트 `read_timeout=15` 적용 후에는 complete가 최대 ~15초 안에 성공/실패하고, 워커가 빨리 놓이므로 badge/session 대기 시간이 줄어듦. **타임아웃·병렬 삭제 변경이 deploy에 반영되어 있어야 함.**

---

## 3) 왜 그런 결정을 내렸는가 (Why)

- **단순화 우선**: “항상 직접 업로드 + 동시성” 한 가지 경로로 통일하면, FormData 경로·동기 썸네일 등 변수가 사라져 예측 가능하고 빠름.
- **시간 차원**: “지금 느리다”는 특정 화면(edit/add) 또는 환경(USE_DIRECT_UPLOAD false)에서의 현상일 수 있으므로, 환경·플로우 구분을 문서에 명시.
- **오컴의 면도날**: 해결책은 “직접 업로드 확실히 사용 + 완료 단계 R2 호출 최소화”로 압축 가능.

---

## 권장 사항 (우선순위)

### 🔴 1) 직접 업로드 사용 확실히 하기 (환경·템플릿)

- **운영/스테이징**: `USE_DIRECT_UPLOAD=1` 및 R2/S3 사용 시 `use_direct_upload`가 true로 노출되는지 확인.
- **edit_order / add_order**: 이미 context_processor의 `use_direct_upload`를 쓰므로, 스토리지 타입이 r2/s3이면 true.  
  로컬에서 “느리다”면 로컬 스토리지로 인해 false일 가능성 확인.
- **권장**: R2/S3 환경에서는 FormData 경로를 쓰지 않도록, 직접 업로드만 사용하거나(또는 direct 실패 시에만 FormData 폴백) 플래그를 명시적으로 true로 고정 검토.

### 🟡 2) complete 단계 R2 호출 줄이기

- `api_order_attachments_complete`에서 `file_size`를 위해 `head_object`를 한 번 더 부름.  
  클라이언트가 이미 `session` 요청 시 `size`를 보내므로, **complete 요청 body에 `size`를 넣어 전달**하고, 서버는 R2 `head_object` 없이 이 값을 쓰면 됨 (object_exists만 유지해도 됨).
- 효과: 완료 단계당 R2 호출 1회 감소, 지연·비용 소폭 절감.

### 🟡 3) 동시성 상향 (선택)

- 시공/AS와 동일하게 CONCURRENCY=3 유지해도 되고, 네트워크·R2 여유가 있으면 **5** 등으로 올려서 다수 파일 업로드 체감 속도 개선 가능.
- `erp_beta_js.html` 내 `erpUploadSelectedAttachments`, `erpUploadItemAttachments` 등에서 CONCURRENCY 상수만 조정하면 됨.

### 🟢 4) FormData 경로에서 동기 썸네일 제거

- `api_order_attachments_upload`에서 `ASYNC_ATTACHMENT_THUMBNAIL`이 False여도, **동기 `_generate_thumbnail` 호출을 제거**하고  
  direct 경로와 동일하게 `schedule_order_attachment_thumbnail_generation` 등 **비동기 큐**만 사용하도록 통일하면, FormData 경로를 쓰는 환경에서도 요청 지연이 줄어듦.

---

## 참조 코드 위치

| 항목 | 파일: 라인 |
|------|------------|
| 시공 업로드 (CONCURRENCY=3) | `templates/partials/erp_construction_scripts.html` (submitConstructionComplete, submitConstructionReupload, AS 접수) |
| ERP Beta 직접 업로드 1파일 | `templates/partials/erp_beta_js.html`: `erpDoDirectUploadOne` |
| ERP Beta 첨부 업로드 (CONCURRENCY vs 순차) | `templates/partials/erp_beta_js.html`: `erpUploadSelectedAttachments`, `erpUploadItemAttachments` |
| use_direct_upload 주입 | `services/context_processors.py` |
| session / complete / FormData upload | `apps/api/attachments.py`: `api_upload_session`, `api_order_attachments_complete`, `api_order_attachments_upload` |
| 썸네일 동기 생성 (FormData 경로) | `apps/api/attachments.py`: `api_order_attachments_upload` 내 `_generate_thumbnail` |
