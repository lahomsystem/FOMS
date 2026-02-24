# 파일 업/다운로드 코드 리뷰 (GDM 기준)

**검토일**: 2026-02-24  
**기준**: `.cursor/agents/grand-develop-master.md`  
**대상**: R2 direct 업/다운 적용 여부 및 전역 일관성

---

## 1) 무엇을 발견했는가 (What was found)

### 1.1 적용한 변경 사항
- **API**: `GET /api/files/presigned-urls/<path:storage_key>` 추가 (R2/S3 시 presigned URL 반환, 로컬 시 기존 view/download URL 반환).
- **ERP Beta 주문 입력**: 첨부 미리보기 모달에서 `storage_key`로 presigned URL 조회 후, 미리보기(img/video) 및 다운로드 링크를 R2 직접 링크로 교체.

### 1.2 코드 품질 (GDM 감사 항목)
| 항목 | 상태 | 비고 |
|------|------|------|
| 보안 | 양호 | `presigned_urls`: `..`, `/` prefix 검사, `@login_required` 적용 |
| 아키텍처 | 양호 | `files_bp` 일원화, `build_file_*_url` 재사용 |
| 단순화 | 양호 | 모달은 기존 URL로 즉시 표시 후 비동기로 presigned 교체(타이밍 이슈 회피) |
| 경로 처리 | 양호 | `storage_key` 세그먼트만 `encodeURIComponent`, 슬래시 유지 |

### 1.3 잠재 이슈 (경미)
- `erpOpenAttachmentPreview` 내 `body.querySelectorAll('a[href]')`로 **본문의 모든 링크**를 presigned `download_url`로 교체함.  
  현재 모달에는 "다운로드" 버튼 하나만 있어 문제 없으나, 추후 다른 링크가 들어가면 그 링크도 다운로드 URL로 바뀔 수 있음.  
  → 필요 시 셀렉터를 `body.querySelector('a.btn-primary')` 등으로 좁히는 것 권장.

---

## 2) FOMS 전체 API에서 업/다운이 원활한가?

### 결론: **아니요. 현재는 “ERP Beta 주문 입력 첨부”만 R2 최단 경로(다운/미리보기)가 적용됩니다.**

- **업로드**: 이미 여러 구간에서 R2 direct(session → presigned PUT) 사용 중 → **전역적으로 원활**.
- **다운로드/미리보기**: presigned 직접 링크를 **쓰는 곳은 ERP Beta 주문 입력 첨부 미리보기 모달뿐**이며, 나머지는 모두 `/api/files/view/...`, `/api/files/download/...`를 사용해 **요청마다 Flask 앱을 한 번 거칩니다** (리다이렉트로 R2는 되지만 최단 경로 아님).

### 업로드 사용처 (R2 direct 적용 여부)
| 구간 | 방식 | 병렬 업로드 | 비고 |
|------|------|-------------|------|
| ERP Beta 주문 첨부 (공통) | session → PUT | ✅ 3개씩 (2026-02-24) | R2 direct |
| ERP Beta 제품별 이미지 추가 | session → PUT | ✅ 3개씩 (2026-02-24) | R2 direct |
| 도면 워크벤치 | session → PUT | 별도 구현 | R2 direct |
| 채팅 | /api/chat/upload/session → PUT | — | R2 direct |
| edit_order 블루프린트 | /api/upload/session → PUT | — | R2 direct |
| 주문 첨부 Form fallback | POST multipart | — | 앱 경유 (R2/S3이면 storage.upload_file) |

### 다운로드/미리보기 사용처 (presigned 직접 vs 앱 경유) — 2026-02-24 갱신
| 구간 | view/download URL | presigned 직접 사용 |
|------|-------------------|----------------------|
| **ERP Beta 주문 입력 첨부 미리보기** | presigned 조회 후 교체 | 예 |
| **도면 워크벤치 상세** | GlobalImageViewer + data-key → presigned | 예 |
| **도면 워크벤치·대시보드 목록 썸네일** | img에 data-storage-key → erpReplaceThumbnailsWithPresigned | 예 (2026-02-24) |
| **대시보드 게이트웨이/첨부/생산/시공** | GlobalImageViewer.open 시 key 전달 → presigned | 예 |
| **채팅 이미지 라이트박스** | openImageLightbox(this) + data-key → presigned | 예 |
| edit_order 블루프린트 | /api/files/view, download | 아니오 (선택 미적용) |

---

## 3) 무엇을 권장하는가 (Why)

- **현재 변경만으로는** “FOMS의 모든 API에서 업/다운이 최단 경로로 원활하다”고 보기는 어렵습니다.  
  **업로드는 대부분 이미 R2 direct**이고, **다운/미리보기는 ERP Beta 첨부만 presigned 직접**입니다.
- **전역적으로 다운/미리보기도 최단 경로로 맞추려면**  
  - 도면 워크벤치, 대시보드 각 스크립트(도면/게이트웨이/첨부/상세/생산/시공), 채팅, edit_order 등에서  
  - 파일 표시/다운로드 시 `storage_key`(또는 key)로 `GET /api/files/presigned-urls/<key>` 호출 후  
  - 반환된 `view_url`/`download_url`을 사용하도록 단계적으로 적용하는 작업이 필요합니다.
- **우선순위 제안**:  
  1) 도면 워크벤치 상세 (이미지/다운로드 빈도 높음)  
  2) 대시보드 첨부/도면 관련 스크립트  
  3) 채팅·edit_order 블루프린트

---

## 4) 업로드 진행률 표시 (2026-02-23 적용)

**목표**: 모든 파일 업로드 구간에서 도면작업실처럼 **실제 업로드 %**를 막대 그래프로 표시.

### 적용 현황
| 구간 | 진행률 UI | 방식 | 비고 |
|------|-----------|------|------|
| **도면작업실 전달** | `#dw-transfer-progress` | XHR `upload.onprogress` | 기존 패턴 |
| **채팅 파일** | `#chat-upload-progress` | `uploadWithProgress()` (multipart) / 90→100% (direct) | 공통 유틸 |
| **ERP 대시보드 도면 전달** | `#erp-drawing-transfer-progress` | `uploadWithProgress()` 파일별 | 공통 유틸 |
| **주문 상세 도면(blueprint)** | `#blueprint-upload-progress` | `uploadWithProgress()` | 공통 유틸 |
| **ERP Beta 첨부 (공통·제품별)** | `#erp-attachments-progress` | direct 시 청크 완료 수/전체 %, multipart 시 `uploadWithProgress()` | 공통·제품별 모두 병렬(3개씩) 적용 |
| **도면작업실 수정요청 첨부** | `#dw-revision-progress` | 순차 업로드 + `uploadWithProgress()` fallback | 신규 적용 |

### 공통 유틸
- **`static/js/upload-progress.js`**: `window.uploadWithProgress(url, formData, { onProgress, timeout })` — XHR 기반, `xhr.upload.onprogress`로 0~100% 콜백. `layout.html`에서 전역 로드.

### GDM 리뷰 요약
- **일관성**: 도면작업실 전달 패턴을 참고해 multipart 업로드는 XHR 진행률, direct(PUT) 업로드는 퍼센트 이벤트 없어 단계(90→100%)만 표시.
- **품질**: progress bar는 `d-none`으로 초기 숨김, 완료/에러 시 0%로 초기화 후 숨김. `uploadWithProgress` 미정의 시 기존 `fetch` fallback 유지.
- **권장**: 신규 업로드 UI 추가 시 동일 패턴(progress wrap + bar + `uploadWithProgress` 또는 단계 표시) 적용.

---

## 참고 파일
- `apps/api/files.py`: view, download, presigned_urls
- `templates/partials/erp_beta_js.html`: erpOpenAttachmentPreview, erpDoDirectUploadOne
- `apps/api/attachments.py`: build_file_view_url, build_file_download_url 사용처
