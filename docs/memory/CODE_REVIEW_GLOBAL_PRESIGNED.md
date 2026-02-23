# 전역 Presigned 업/다운 적용 코드 리뷰 (GDM 기준)

**리뷰일**: 2026-02-23  
**기준**: `.cursor/agents/grand-develop-master.md` (개발 품질 감사·보안·아키텍처)  
**대상**: 전역 파일 미리보기/다운로드 R2 presigned 적용 변경분

---

## 1) 무엇을 발견했는가 (What was found)

### 1.1 변경 범위
- **layout.html**: GlobalImageViewer — `state.files`에 `key` 보존, `render()`에서 presigned fetch 후 `els.image.src` 교체.
- **erp_drawing_workbench_detail.html**: `data-key` 추가, `openDrawingGatewayImageViewer`에서 `files[].key` 전달.
- **erp_dashboard_scripts_gateway.html**: `viewerFiles`에 `key` 포함.
- **erp_production_scripts / erp_dashboard_scripts_attachments / erp_construction_scripts**: `imageFiles` 맵에 `key: a.storage_key` 추가.
- **chat_scripts_lightbox.html**: `openImageLightbox(imageUrl, optionalKey)` 확장, element 시 `data-url`/`data-key` 사용 후 presigned 조회.
- **chat_scripts_messages.html**: 이미지에 `data-url`/`data-key` 추가, `safeAttr()`로 속성 이스케이프, `onclick="openImageLightbox(this)"`.

### 1.2 백엔드 (기존)
- **apps/api/files.py** `presigned_urls(storage_key)`: `..` 및 `startswith('/')` 검사, `@login_required` 적용. R2/S3 시 `get_download_url(3600)` 반환. **보안·역할 적절.**

---

## 2) GDM 감사 결과

### 긴급 (🔴) — 0건
- 없음.

### 개선 권장 (🟡) — 2건 반영함

1. **채팅: onclick 내 storageKey 이스케이프** — ✅ 반영  
   `safeJsStr(s)` 도입(`\` → `\\`, `'` → `\'`), `downloadChatImage('${safeJsStr(storageKey)}', ...)` 적용(이미지·영상 다운로드 버튼).

2. **ERP Beta 미리보기: 다운로드 링크 셀렉터 범위** — ✅ 반영  
   `body.querySelector('a.btn-primary') || body.querySelector('a[href*="download"]')` 로 presigned 적용 대상 링크만 교체.

3. **에러·로딩 피드백**  
   presigned fetch 실패 시 사용자에게 토스트/메시지 없이 기존 앱 URL만 유지. 동작은 유지되나, 네트워크 오류 시 “이미지가 안 바뀌었다”는 인지가 어려울 수 있음.  
   **권장**: (선택) 실패 시 로그만 남기거나, 디버그용 플래그가 있을 때만 토스트 노출.

### 양호 (🟢)

1. **보안**  
   - 서버: `presigned_urls`에서 path traversal 방지(`..`, `/`), 인증(`@login_required`).  
   - 클라이언트: presigned 요청 경로는 세그먼트만 `encodeURIComponent`로 인코딩.  
   - 채팅: `data-url`/`data-key`에 `safeAttr()` 적용(`&`, `"`, `<` 이스케이프).

2. **레이스 컨디션 방지**  
   layout `render()`에서 `state.files[state.index] === file` 확인 후에만 `els.image.src` 갱신. 이미지 전환 후 늦게 도착한 응답이 덮어쓰지 않음.

3. **하위 호환**  
   `key`가 없거나 presigned 실패 시 기존 앱 URL 유지. 로컬 스토리지 시에도 API가 기존 view/download URL을 반환해 동작 유지.

4. **아키텍처**  
   단일 API(`/api/files/presigned-urls/<path:storage_key>`) 사용, GlobalImageViewer 한 곳에서 presigned 처리로 중복 최소화.

5. **파일 크기**  
   변경은 소량 추가 위주. GDM 권장(HTML 800줄, JS 300줄)을 위반하는 대규모 증설 없음.

---

## 3) 결론

- **전반**: 전역 presigned 적용 방향과 구현은 GDM 관점에서 **적절**하며, **긴급 이슈 없음**.
- **권장**: 채팅 `storageKey` JS 이스케이프, ERP Beta 다운로드 링크 셀렉터 축소 적용 시 유지보수·안정성 향상.

---

## 4) 참조

- `docs/memory/PLAN.md`, `CONTEXT.md`, `TODO.md`
- `docs/memory/FILE_UPLOAD_DOWNLOAD_REVIEW.md`
