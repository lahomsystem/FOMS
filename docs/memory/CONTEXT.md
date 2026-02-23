# 전역 업/다운로드 R2 적용 맥락 (CONTEXT)

**작성일**: 2026-02-23

---

## 1. 결정 배경

- **요구**: FOMS 전역에서 파일 업/다운이 “원활”하게 동작 (R2 direct 최단 경로).
- **현황**: 업로드는 대부분 이미 R2 direct(session → PUT). 다운/미리보기는 ERP Beta 첨부만 presigned 직접 적용, 나머지는 `/api/files/view|download` 경유(리다이렉트).
- **선택**: 기존 `GET /api/files/presigned-urls/<path:storage_key>` API를 그대로 사용하고, **프론트만** “뷰어/모달을 열 때 presigned 조회 후 src/href 교체”하도록 확장.

## 2. 기술 선택

- **Presigned API 유지**: 이미 구현·보안 검사(`..`, `/` 제거, `@login_required`) 완료. 채팅·주문·도면 모두 동일 스토리지 키 체계면 동일 API 사용.
- **중앙 처리**: `GlobalImageViewer`(layout.html)에서만 presigned fetch 수행. 호출부는 `key`만 넘기면 되어, 중복 로직·실수 가능성 감소.
- **점진 적용**: 뷰어 열 때 기존 URL로 먼저 표시 후 비동기 presigned로 교체. 실패 시 기존 URL 유지로 하위 호환.

## 3. 데이터 소스

- **OrderAttachment**: `to_dict()`에 `storage_key` 포함. API 응답에 그대로 노출.
- **도면 파일**: `drawing_files` 등에 `key` 또는 `storage_key` 형태로 존재. Jinja에서 `fkey`로 전달.
- **채팅**: `f.key` 또는 `storage_key` 형태. layout 쪽 파일 목록에 `key` 포함 가능.
- **블루프린트**: `order.blueprint_image_url`가 `/api/files/view/...` 형식이면 key 추출 가능. 필요 시 서버에서 `blueprint_storage_key` 추가.

## 4. 제약

- **파일 크기**: GDM 목표(HTML 800줄, JS 300줄) 초과 템플릿은 기존대로. 이번 작업은 기존 스크립트 내 소량 추가 위주.
- **인증**: presigned-urls는 `@login_required`. 비로그인 시 기존 앱 URL만 사용.
- **로컬 스토리지**: presigned API가 로컬일 때 기존 view/download URL을 반환하므로, 로컬 환경에서도 동작 유지.

## 5. 미적용 범위

- **업로드**: 변경 없음 (이미 R2 direct 적용 구간 다수).
- **Form fallback 업로드**: 계속 앱 경유. 필요 시 추후 session 방식으로 통일 검토.
- **edit_order 블루프린트**: 우선순위 낮음, 선택 단계에서 적용.
