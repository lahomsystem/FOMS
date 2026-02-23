# 전역 파일 업/다운로드 R2 최단 경로 적용 계획서

**작성일**: 2026-02-23  
**기준**: `.cursor/agents/grand-develop-master.md`, `docs/memory/FILE_UPLOAD_DOWNLOAD_REVIEW.md`  
**목표**: FOMS 전역에서 파일 미리보기/다운로드 시 R2 presigned 직접 링크 사용으로 앱 서버 경유 최소화

---

## 1. 현황 요약

| 구분 | 업로드 | 다운로드/미리보기 |
|------|--------|-------------------|
| **이미 R2 직접** | ERP Beta 첨부, 도면 워크벤치, 채팅, edit_order 블루프린트 (session → PUT) | **ERP Beta 주문 입력 첨부 미리보기 모달만** (presigned 조회 후 교체) |
| **앱 경유** | Form fallback (POST multipart) | 도면 워크벤치, 대시보드 전 구간, 채팅 뷰어, edit_order 블루프린트 보기 등 |

**기존 API**: `GET /api/files/presigned-urls/<path:storage_key>` 이미 존재. R2/S3 시 presigned URL 반환, 로컬 시 기존 view/download URL 반환.

---

## 2. 설계 원칙

1. **단일 API 사용**: 모든 프론트에서 `GET /api/files/presigned-urls/<storage_key>`만 사용. 채팅 파일도 동일 스토리지 키 체계면 동일 API 사용.
2. **점진 적용**: 뷰어/모달을 **열 때** 기존 URL로 즉시 표시한 뒤, 비동기로 presigned 조회 후 `img.src`/다운로드 링크만 교체 (ERP Beta와 동일 패턴). 타이밍 이슈·깜빡임 최소화.
3. **중앙화**: `GlobalImageViewer`(layout.html)를 사용하는 모든 구간은 **뷰어 한 곳**에서만 presigned 로직 수행. 호출 측은 `key`(storage_key)만 넘기면 됨.
4. **하위 호환**: `key`가 없으면 기존처럼 앱 URL만 사용 (리다이렉트로 동작 유지).

---

## 3. 적용 구간 및 데이터 흐름

### 3.1 GlobalImageViewer 사용처 (layout.html)

- **역할**: 전역 이미지 뷰어. `GlobalImageViewer.open(files, startIndex)` 호출 시 `files[]`에 `url`, `download_url`, `filename`, **(추가) key** 포함.
- **수정**:
  - `open()`에서 `state.files`에 `key: f.key || parseKeyFromUrl(f.url) || parseKeyFromUrl(f.download_url) || null` 보존.
  - `render()`에서 `els.image.src = file.url` 설정 후, `file.key`가 있으면 `fetch('/api/files/presigned-urls/' + encodePath(file.key))` → 성공 시 `els.image.src = data.view_url`로 교체.
  - 공통 유틸: `function encodePath(key) { return key.split('/').map(s => encodeURIComponent(s)).join('/'); }`
- **호출 측 의무**: `open(files, index)` 시 각 `f`에 `key`(storage_key) 포함. 없으면 기존 URL만 사용.

### 3.2 도면 워크벤치 상세 (`erp_drawing_workbench_detail.html`)

- **현재**: `render_gateway_file_gallery` 등에서 `data-view-url`, `data-download-url`, `data-filename` 있음. `data-key` 없음.
- **수정**:
  - 매크로/섹션에서 `data-key` 또는 `data-storage-key="{{ fkey }}"` 추가 (fkey = `f.get('key')` 또는 동일 값).
  - `openDrawingGatewayImageViewer`에서 `files` 구성 시 `key: el.dataset.key || el.dataset.storageKey || ''` 추가.
  - `GlobalImageViewer.open(files, index)`에 그대로 전달 → layout 쪽에서 presigned 처리.

### 3.3 대시보드 partials (GlobalImageViewer 호출부)

- **erp_dashboard_scripts_gateway.html**: `viewerFiles`에 `view_url`, `download_url`, `filename` 있음. `f.key` 있으면 `key: f.key` 추가.
- **erp_production_scripts.html**: `imageFiles`/`__currentAttachmentList`에 `storage_key` 있으면 `key: a.storage_key` 추가.
- **erp_construction_scripts.html**: 동일. 첨부 목록에 `storage_key` 포함해 `key` 전달.
- **erp_dashboard_scripts_attachments.html**: 동일. `key` 전달.
- **erp_dashboard_scripts_detail.html**: `viewUrl`, `downloadUrl` 구성 시 `key: a.storage_key` 추가.
- **erp_dashboard_scripts_core.html**: 동일. API에서 오는 첨부에 `storage_key` 있으면 `key`로 전달.

(위 구간은 모두 이미 `view_url`/`download_url`을 API·서버에서 받고 있으므로, 같은 객체에 `storage_key` 또는 `key`가 있으면 open 시 포함만 하면 됨.)

### 3.4 채팅 (layout + chat partials)

- **layout.html**: 채팅에서 뷰어를 열 때 이미 `f.key` 등으로 파일 목록을 넘길 수 있으면, `state.files`에 `key` 포함되도록 정규화만 하면 됨.
- **openImageLightbox** (chat_scripts_lightbox.html): 단일 URL만 받음.  
  - **선택 A**: `openImageLightbox(url, key)`로 확장. `key` 있으면 presigned 조회 후 `img.src` 교체.  
  - **선택 B**: 채팅 메시지에서 이미지 클릭 시 `GlobalImageViewer.open([{ url, download_url, filename, key }], 0)` 호출로 통일.  
  - **권장**: 선택 A (최소 변경). 호출부에서 `key` 전달 가능하면 전달 (예: `/api/files/view/chat/xxx` → key `chat/xxx` 파싱해 전달).

### 3.5 edit_order 블루프린트

- **현재**: `blueprint_image_url`로 이미지 표시, 다운로드 버튼이 별도 존재.
- **선택 사항**: 블루프린트 보기/다운로드도 presigned 적용 시, `blueprint_image_url`에서 key 추출 (또는 서버에서 `blueprint_storage_key` 전달) 후 페이지 로드 또는 버튼 클릭 시 presigned 조회해 `img.src`/다운로드 링크 교체. 우선순위 낮음.

---

## 4. 단계별 실행 순서 (착수 계획)

| 단계 | 작업 | 파일 | 검증 |
|------|------|------|------|
| 1 | GlobalImageViewer에 `key` 보존 + render()에서 presigned 조회·교체 | layout.html | 뷰어 열었을 때 R2 직접 로드 확인 |
| 2 | 도면 워크벤치 상세에 `data-key` 추가, open 시 `key` 전달 | erp_drawing_workbench_detail.html | 도면 갤러리 클릭 시 presigned 적용 |
| 3 | 대시보드 gateway에서 viewerFiles에 `key` 포함 | erp_dashboard_scripts_gateway.html | 게이트웨이 이미지 클릭 시 presigned |
| 4 | 대시보드 attachments/production/construction/detail/core에서 open 시 `key` 포함 | 해당 partials 5개 | 각 구간 이미지 미리보기 presigned |
| 5 | 채팅 openImageLightbox에 key 인자·presigned 처리 또는 채팅→GlobalImageViewer 통일 | chat_scripts_lightbox.html, 채팅 메시지 렌더링부 | 채팅 이미지 클릭 시 presigned |
| 6 | (선택) edit_order 블루프린트 보기/다운 presigned | edit_order.html | 블루프린트 presigned |

---

## 5. 위험·롤백

- **위험**: presigned API 실패 시 기존 앱 URL이 이미 적용되어 있으므로 동작은 유지됨.
- **롤백**: 각 단계는 독립적. layout의 presigned 로직 제거 또는 `key` 미전달로 즉시 앱 경유로 복귀 가능.

---

## 6. 참조

- `apps/api/files.py`: `presigned_urls(storage_key)`
- `templates/partials/erp_beta_js.html`: `erpOpenAttachmentPreview` (presigned 적용 참고)
- `docs/memory/FILE_UPLOAD_DOWNLOAD_REVIEW.md`: 사용처 정리
