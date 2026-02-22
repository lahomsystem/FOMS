# Phase D: Direct R2 Presigned URL 업로드 상세 설계

작성일: 2026-02-22  
근거: `2026-02-22-railway-multi-user-scalability-plan.md` 단계 D

## 1. 목표

- 업로드 시 **파일이 앱 서버를 경유하지 않고** 클라이언트 → R2 직접 전송
- 앱 서버는 업로드 세션 발급(presigned PUT URL)과 완료 검증만 수행
- 대용량 동시 업로드 시 웹 앱 리소스 사용량 급감

## 2. 현재 업로드 구조 요약

### 2.1 업로드 엔드포인트

| 파일 | 라우트 | 용도 |
|------|--------|------|
| `apps/api/attachments.py` | POST `/api/orders/<id>/attachments` | 주문 첨부(사진/동영상) |
| `apps/api/erp_orders_blueprint.py` | POST `/api/orders/<id>/blueprint` | 도면 이미지 |
| `apps/api/erp_orders_drawing.py` | POST `/<id>/drawing-gateway-upload` | 도면 수정요청 파일 |
| `apps/api/chat/routes.py` | POST `/api/chat/upload` | 채팅 파일 |

### 2.2 현재 흐름

```
Client --(multipart/form-data, file)--> App Server --(upload_file/upload_chat_file)--> R2/로컬
```

- `services/storage.py`: `StorageAdapter.upload_file()`, `upload_chat_file()`
- 파일 바이너리가 Flask 요청 본문으로 들어와 메모리/디스크 경유 후 스토리지로 전송

### 2.3 StorageAdapter 구조

- `_upload_to_cloud()`: boto3 `client.upload_fileobj()` 사용 (파일 객체 → R2)
- `get_download_url()`: `generate_presigned_url('get_object', ...)` (다운로드용, 이미 사용 중)
- R2/S3: `generate_presigned_url('put_object', ...)` 는 현재 미사용

## 3. Direct Upload 목표 흐름

```
1. Client → POST /api/.../upload/session { filename, size, folder }
   ← { upload_url (presigned PUT), key, expires_at }

2. Client → PUT upload_url (body = file binary)  [R2 직접]

3. Client → POST /api/.../upload/complete { key }
   App: head_object 확인 후 DB 등록
```

- 앱 서버는 1, 3만 처리. 2는 클라이언트가 R2로 직접 PUT.

## 4. 구현 순서 (실행 체크리스트)

### 4.1 StorageAdapter 확장

- [x] 1.1 `generate_presigned_put_url(key, content_type, expires_in=900)` 메서드 추가 (2026-02-22)
- [x] 1.2 `object_exists(key)` 메서드 추가
- [x] 1.3 `generate_direct_upload_key(filename, folder)` 메서드 추가
- [x] 로컬 스토리지 모드: presigned PUT URL은 None 반환, 기존 multipart 유지

### 4.2 업로드 세션 API (공통)

- [x] 2.1 `POST /api/upload/session` (2026-02-22)
  - 입력: `filename`, `size`, `folder`
  - 출력: `upload_url`, `key`, `expires_at`
- [x] 2.2 `POST /api/orders/<id>/attachments/complete`
  - 입력: `key`, `filename`, `category`, `item_index`
  - object_exists 검증 후 DB 등록

### 4.3 도메인별 전환

- [x] 3.1 **주문 첨부** (`attachments.py`) - session, complete API 추가 완료
  - 새 플로우: session → PUT → complete
  - 기존 multipart 경로: deprecated 또는 feature flag로 유지
- [x] 3.2 **도면** (`erp_orders_blueprint.py`) — 2026-02-22
  - `POST /api/orders/<id>/blueprint/complete` 추가. session → PUT → complete 플로우 지원.
- [x] 3.3 **도면 수정요청** (`erp_orders_drawing.py`) — 2026-02-22
  - `POST /api/orders/<id>/drawing-gateway/complete` 추가. 동일 플로우.
- [x] 3.4 **채팅** (`chat/routes.py`) — 2026-02-22
  - session/complete API 구현됨. key 경로 `chat/` 검증, room_id 반영 폴더.

### 4.4 프론트엔드

- [x] 4.1 첨부 업로드 UI: session 요청 → fetch(PUT, upload_url, body=file) → complete 요청 (2026-02-22)
  - erpUploadSelectedAttachments, erpUploadItemAttachments에서 USE_DIRECT_UPLOAD 시 direct 플로우 적용
- [x] 4.2 도면(blueprint) 업로드 UI: edit_order.html uploadBlueprint에서 USE_DIRECT_UPLOAD 시 session→PUT→blueprint/complete (2026-02-22)
- [x] 4.3 도면 수정요청(drawing-gateway) 업로드 UI: erp_dashboard_scripts_drawing, erp_drawing_workbench_detail의 uploadRevisionGatewayFiles에서 direct 플로우 (2026-02-22)
- [x] 4.4 채팅 업로드 UI: chat_scripts_file.html USE_DIRECT_UPLOAD_CHAT 시 session→PUT→complete. 채팅 라우트에서 use_direct_upload 전달 (2026-02-22)
- [x] 4.5 파일 크기/타입 사전 검증 (세션 요청 시) — 각 세션 API에서 size·허용 확장자 검증 적용됨

### 4.5 보안·제한

- [x] 5.1 presigned URL 만료 시간: 15분 (expires_in=900)
- [x] 5.2 Content-Type 제한 (세션 발급 시 DIRECT_UPLOAD_ALLOWED_CONTENT_TYPES 허용 목록, constants.py)
- [x] 5.3 파일 크기 상한 (세션 요청 시 get_erp_media_max_size / get_chat_file_max_size 검증)
- [x] 5.4 key 경로 검증: complete 시 `orders/<id>/` 또는 `chat/` prefix 검증

### 4.6 검증

- [ ] 6.1 대용량(100MB+) 파일 direct upload 테스트
- [ ] 6.2 동시 20건 업로드 시 웹 프로세스 CPU/메모리 비교 (기존 vs direct)
- [ ] 6.3 로컬 스토리지 모드에서 기존 multipart 경로 정상 동작 확인

## 5. API 스펙 초안

### POST /api/upload/session (공통)

**Request:**
```json
{
  "filename": "photo.jpg",
  "size": 1048576,
  "folder": "orders/123/attachments",
  "content_type": "image/jpeg"
}
```

**Response:**
```json
{
  "success": true,
  "upload_url": "https://...r2.dev/...?X-Amz-...",
  "key": "orders/123/attachments/20260222_120000_photo.jpg",
  "expires_at": "2026-02-22T12:15:00Z"
}
```

### POST /api/orders/<id>/attachments/complete

**Request:**
```json
{
  "key": "orders/123/attachments/20260222_120000_photo.jpg",
  "filename": "photo.jpg",
  "category": "measurement",
  "item_index": null
}
```

**Response:** 기존 attachment 응답과 동일.

## 6. StorageAdapter 메서드 시그니처 (추가)

```python
def generate_presigned_put_url(self, key: str, content_type: str, expires_in: int = 900) -> str | None
def object_exists(self, key: str) -> bool
```

## 7. 롤백

- 기존 multipart 업로드 경로 유지 (direct 사용 여부를 feature flag로 제어)
- `USE_DIRECT_UPLOAD=0`이면 기존 경로 사용

## 8. 의존 관계

- Phase D는 R2/S3 스토리지 사용 시에만 의미 있음. 로컬 스토리지는 기존 흐름 유지.
- 썸네일 생성은 Phase B처럼 worker job으로 이미 분리됨 → complete 시점에 enqueue만 하면 됨.
