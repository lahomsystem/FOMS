# 원격 업로드 속도 개선 계획서

**작성일**: 2026-02-23  
**작성자**: Grand Develop Master  
**목표**: 원격(production)에서 파일 업로드가 느리다는 문제를 체감·실제 속도 측면에서 개선.

---

## 1. 요구사항 분석

- **현상**: 원격(lahom-production.up.railway.app)에서 첨부/도면 등 업로드가 너무 느림.
- **현재 구조**: Phase D Direct Upload 사용 중 — 브라우저가 `/api/upload/session`으로 presigned PUT URL을 받은 뒤, **브라우저 → R2**로 직접 PUT. (Railway 경유 없음, 이미 최단 경로.)
- **제약**: CORS는 이미 PUT 허용. 느린 구간은 **사용자 네트워크 ↔ R2**이므로, 서버 변경만으로 대역폭을 늘릴 수 없음.

---

## 2. 아키텍처·영향도

- **영향 파일**: `templates/partials/erp_beta_js.html` (ERP 첨부 업로드), 동일 패턴 사용처(`erp_drawing_workbench_detail.html`, `edit_order.html` blueprint, `chat_scripts_file.html` 등)는 필요 시 동일 방식 적용.
- **변경 범위**: 프론트엔드 전용. 백엔드 API(`/api/upload/session`, `/complete`) 변경 없음.
- **위험도**: 낮음. 기존 순차 업로드 로직을 “동시에 N개까지”로만 바꾸고, 실패 시 기존과 동일하게 폴백.

---

## 3. 구현 방안 (GDM: 단순화 우선)

### Phase 1 (즉시 적용 권장): 병렬 업로드

- **내용**: 여러 파일을 **한 번에 2~3개씩** 동시에 올리기. (현재는 1개씩 순차.)
- **근거**: 같은 회선에서도 대기 시간이 줄어 총 체감 시간 단축. API는 그대로 사용.
- **구현**: `erpUploadSelectedAttachments`에서 `for` + `await` 대신, `Promise.all` + 청크(예: 2~3개씩 묶어서) 또는 `Promise.allSettled`로 동시 실행. 진행률은 “완료된 개수 / 전체”로 표시.
- **담당**: frontend-ui (또는 GDM 직접).

### Phase 2 (목록/썸네일 presigned) — 2026-02-24 적용

- **내용**: 목록·갤러리 썸네일 `img`의 src를 `/api/files/view` 경유 대신 **presigned URL(R2 직행)**로 로드.
- **구현**: (1) `layout.html`에 `erpReplaceThumbnailsWithPresigned(container)` 공통 후크 — `img[data-storage-key]`에 대해 `GET /api/files/presigned-urls/<key>` 호출 후 src 교체(5개씩 병렬). (2) 대시보드 첨부 `buildDrawingTargetCards` 썸네일에 `data-storage-key` 추가, 카드 삽입 후 후크 호출. (3) 도면 워크벤치 상세(Jinja) 썸네일 3곳에 `data-storage-key` 추가 → DOMContentLoaded 시 후크가 document 전체에 적용.
- **효과**: 썸네일 로딩 시 Railway 경유 없이 R2 직행으로 체감 속도 개선.

### Phase 2a (선택): Direct PUT 진행률 표시

- **내용**: `fetch(sess.upload_url, { method: 'PUT', body: file })`는 업로드 진행 이벤트 미지원 → **XMLHttpRequest**로 PUT하여 `upload.onprogress`로 진행률 표시.
- **효과**: 실제 전송 속도는 동일하나, “몇 % 올라가는지” 보여주어 체감 개선.
- **비고**: 구현량 대비 효과를 보고 Phase 1 이후 필요 시 적용.

### Phase 3 (미적용·참고만): Multipart / 이미지 압축

- **Multipart**: 대용량 파일을 파트 나누어 병렬 PUT. 백엔드에 multipart initiate/complete API 추가 필요 → 비용 대비 이번 스코프에서는 제외.
- **이미지 압축**: 클라이언트에서 리사이즈·압축 후 업로드 → 별도 요구 시 검토.

---

## 4. 추천안 및 진행 단계

- **추천**: **Phase 1(병렬 업로드)만 우선 적용.**  
  - 이유: 코드 변경 최소, API 변경 없음, 기존 폴백 유지. 원격에서 여러 파일 올릴 때 체감 속도 개선 기대.
- **진행 단계**:
  1. ✅ `erp_beta_js.html`의 `erpUploadSelectedAttachments`에서 direct-upload 분기만 병렬화 (동시 3개, 진행률 = 완료 수/전체). **적용 완료.**
  2. ✅ `erp_beta_js.html`의 `erpUploadItemAttachments`(제품별 이미지 추가)에서 동일하게 CONCURRENCY=3, `Promise.all(chunk.map(...))` 적용. **2026-02-24 적용 완료.**
  3. (선택) 도면 워크벤치·블루프린트 등 다른 진입점에서도 동일 방식 적용.
  4. 검증: 원격에서 공통 첨부·제품별 이미지 각각 다수 파일 업로드 후 시간·진행 표시 확인.

---

## 5. R2 CORS 정책 권장 (Cloudflare 대시보드)

- **현재**: Allowed Origins에 `http://localhost:5000`, `https://lahom-production.up.railway.app` / Allowed Methods에 `GET`, `PUT`, `HEAD` 설정된 상태면 업로드는 가능.
- **권장 업데이트**: **Allowed Headers**가 비어 있거나 `--`로 두면, 일부 브라우저/환경에서 PUT 요청 시 `Content-Type` 헤더가 preflight에서 막힐 수 있음. R2 CORS 편집에서 **Allowed Headers**에 `Content-Type`을 추가해 두면 더 안정적.
- **적용 방법**: R2 버킷 → CORS Policy → Edit → Allowed Headers에 `Content-Type` 입력(또는 필요한 경우 `*`). 저장.

---

## 6. 검증 체크리스트 (GDM §5)

- [ ] `python -c "import app"` 성공
- [ ] 로컬에서 ERP Beta 탭 → 첨부 여러 개 선택 → 업로드 성공
- [ ] 원격(Railway)에서 동일 시나리오 1회 이상 확인
- [ ] 기존 순차 폴백(USE_DIRECT_UPLOAD 비활성 또는 session 실패 시) 동작 유지
