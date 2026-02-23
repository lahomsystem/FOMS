# GDM 코드 리뷰: ERP 제품 이미지 업로드 진행률 및 CORS

**일자:** 2026-02-23  
**대상:** 제품별 "이미지 추가" 업로드 UI, 업로드 상태 표시 바 미노출 및 CORS 오류  
**기준:** `.cursor/agents/grand-develop-master.md` (개발 품질 감사·보고서 형식)

---

## 요약

- **업로드 상태 표시 바가 안 뜨던 이유:** "공통 첨부" 업로드는 `erp-attachments-progress` 진행률 바를 쓰고 `uploadWithProgress`로 %를 갱신하지만, **제품별 "이미지 추가"**는 `erpUploadItemAttachments`에서 진행률 UI를 표시하지 않고, 비직접 업로드 시에도 `fetch`만 사용하고 있었음.
- **콘솔 CORS 오류:** `USE_DIRECT_UPLOAD` 사용 시 브라우저가 R2 presigned URL로 직접 PUT 요청을 보내는데, R2 버킷에 `Access-Control-Allow-Origin`이 설정되어 있지 않아 `lahom-production.up.railway.app` 오리진이 차단됨.

---

## 🏥 FOMS 개발 건강 진단 (해당 영역)

- **해당 영역 점수:** 72/100 (업로드 UX·CORS 반영)
- **긴급 조치:** 1건 (CORS로 인한 직접 업로드 실패)
- **개선 완료:** 1건 (제품 이미지 업로드 진행률 표시)
- **양호:** 1건 (공통 첨부 업로드는 이미 진행률·fallback 구조 양호)

### 긴급 (🔴)

1. **R2 직접 업로드 CORS 차단**  
   - 브라우저가 Railway 도메인에서 R2 presigned URL로 PUT 시 preflight 실패 → "No 'Access-Control-Allow-Origin' header"  
   - **영향:** 직접 업로드(Phase D) 사용 시 업로드 실패. 현재는 `erpDoDirectUploadOne` 내에서 실패 시 서버 경유 fallback으로 넘어가므로 동작은 하되, 직접 업로드 이점을 못 받음.  
   - **조치 (택일):**  
     - **(권장)** Cloudflare R2 버킷에 CORS 설정 추가: `AllowedOrigins`에 `https://lahom-production.up.railway.app`(및 필요 시 dev 도메인) 포함.  
     - 또는 운영에서 **`USE_DIRECT_UPLOAD=0`** 로 두어 모든 업로드를 서버 경유로 통일 → CORS 없음, 진행률 표시 일관되게 동작.

### 개선 완료 (🟡 → 적용함)

1. **제품별 "이미지 추가" 업로드 진행률 표시**  
   - `erpUploadItemAttachments`에서 `erp-attachments-progress` / `erp-attachments-progress-bar`를 사용해 공통 첨부와 동일한 진행률 바 표시.  
   - 비직접 업로드 경로에서 `uploadWithProgress` 사용해 파일별 % 반영. 직접 업로드 경로에서는 파일 인덱스 기준으로 진행률 표시.  
   - 완료 후 progress 영역 `d-none` 및 0%로 초기화.

### 양호 (🟢)

1. **공통 첨부 업로드 (`erpUploadSelectedAttachments`)**  
   - 진행률 바 표시, `uploadWithProgress` 사용, direct 실패 시 서버 POST fallback 구조가 이미 잘 갖춰져 있음.  
   - 제품 이미지 업로드도 동일한 progress 영역을 재사용하도록 맞춰 일관성 확보.

---

## 수정 파일

| 파일 | 변경 내용 |
|------|------------|
| `templates/partials/erp_beta_js.html` | `erpUploadItemAttachments` 내 progress 영역 표시/숨김, 비직접 시 `uploadWithProgress` 사용, 직접 시 파일 인덱스 기준 % 표시 |

---

## 참고

- 진행률 바 HTML: `templates/partials/erp_beta_tab.html`의 `#erp-attachments-progress`, `#erp-attachments-progress-bar`.  
- Direct upload 설계: `docs/plans/2026-02-22-phase-d-direct-upload-design.md`, `USE_DIRECT_UPLOAD` 환경 변수.
