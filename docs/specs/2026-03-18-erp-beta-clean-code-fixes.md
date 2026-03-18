# ERP Beta 클린코드 수정 Spec

> 작성일: 2026-03-18 | 상태: 🟡 승인대기

## 1. What — 무엇을 수정하는가

### 1.1 최종 결과물
- `erp_beta_js.html` 내 빈 catch 8곳을 구체적 예외 처리로 교체
- (Phase 2) targetId 확보 로직 공통 함수 추출
- (Phase 3) 인라인 스크립트 300줄 초과 대응 — 별도 .js 분리 (선택)

### 1.2 수정 요구사항
1. **에러 숨기기 제거**: `catch (e) { }` → 최소 `console.warn(context, e)` 추가
2. **AGENTS.md 준수**: "에러 숨기기 금지: try/except: pass, 빈 catch"
3. **기능 유지**: 기존 동작(graceful degradation)은 그대로 유지

### 1.3 예외/제약 조건
- `URL.createObjectURL` 실패 시 previewUrl은 '' 유지 (이미지 미표시만 발생)
- batch session fetch 실패 시 sessionMap은 {} 유지 (개별 session 요청으로 fallback)
- `erpSetOrderId`의 parseInt 실패 시 ORDER_ID 갱신만 실패, data-attr 동기화는 수행

---

## 2. How — 어떻게 수정하는가

### 2.1 수정 대상 파일

| 파일 | 변경 내용 |
|------|-----------|
| `templates/partials/erp_beta_js.html` | 빈 catch 8곳 → console.warn 추가 |

### 2.2 수정 상세 (Phase 1)

| 라인 | 함수/컨텍스트 | 현재 | 수정 후 |
|------|---------------|------|---------|
| 149 | `erpSetOrderId` | `catch (e) { }` | `catch (e) { console.warn('[erpSetOrderId]', e); }` |
| 533 | `erpApplyStructured` (전화번호 포맷) | `catch (e) { }` | `catch (e) { console.warn('[erpApplyStructured] formatPhone', e); }` |
| 1188 | AS 접수 batch session fetch | `catch (e) { }` | `catch (e) { console.warn('[AS receive] batch session', e); }` |
| 1394 | 첨부 업로드 `URL.createObjectURL` | `try { ... } catch (e) { }` | `try { ... } catch (e) { console.warn('[upload] createObjectURL', e); }` |
| 1433 | 측정 이미지 batch session fetch | `catch (e) { }` | `catch (e) { console.warn('[measurement] batch session', e); }` |
| 1725 | 첨부 다운로드 URL fetch | `.catch(function () { });` | `.catch(function (e) { console.warn('[attachment] download URL', e); });` |
| 1813 | 첨부 업로드 `URL.createObjectURL` | `try { ... } catch (e) { }` | `try { ... } catch (e) { console.warn('[upload] createObjectURL', e); }` |
| 1858 | 공통 첨부 batch session fetch | `catch (e) { }` | `catch (e) { console.warn('[attachments] batch session', e); }` |

### 2.3 Phase 2 (선택) — targetId 공통 함수

| 파일 | 변경 내용 |
|------|-----------|
| `templates/partials/erp_beta_js.html` | `erpResolveOrderId()` 함수 추가, erpTogglePayment·erpSaveStructured에서 호출 |

```javascript
/** ORDER_ID 또는 card data-attr에서 order id 확보. draft 모드에서 0이면 null 반환. */
async function erpResolveOrderId(ensureDraftIfZero = false) {
    let id = parseInt(String(typeof ORDER_ID !== 'undefined' ? ORDER_ID : 0), 10) || 0;
    if (!id) {
        const card = document.querySelector('.card[data-erp-order-id]') || document.querySelector('.card[data-order-id]');
        if (card) id = parseInt(String(card.dataset.erpOrderId || card.dataset.orderId || '0'), 10) || 0;
    }
    if (id <= 0 && ensureDraftIfZero && window.__ERP_BETA_DRAFT_MODE) {
        id = await erpRequireOrderIdOrWarn('ID:') || 0;
    }
    return id > 0 ? id : 0;
}
```

### 2.4 Phase 3 (선택) — erp_beta_js 분리

- **규칙**: CLAUDE.md "인라인 script 300줄 초과 시 별도 .js 파일로 분리"
- **현황**: erp_beta_js.html 2,348줄
- **작업**: `static/js/erp_beta.js` 생성, `templates/partials/erp_beta_js.html`을 `<script src="{{ url_for('static', filename='js/erp_beta.js') }}"></script>` + 글로벌 변수 주입용 최소 인라인으로 변경
- **주의**: add_order/edit_order에서 `ORDER_ID`, `ERP_BETA_ENABLED`, `__ERP_BETA_DRAFT_MODE` 등 주입 방식 유지 필요

---

## 3. Steps — 실행 단계

### Phase 1 (필수)
- [ ] Step 1: L149 `erpSetOrderId` catch 수정
- [ ] Step 2: L533 `erpApplyStructured` catch 수정
- [ ] Step 3: L1188 AS 접수 catch 수정
- [ ] Step 4: L1394, L1813 `URL.createObjectURL` catch 수정
- [ ] Step 5: L1433, L1858 batch session catch 수정
- [ ] Step 6: L1725 `.catch` 수정

### Phase 2 (선택)
- [ ] Step 7: `erpResolveOrderId()` 함수 추가
- [ ] Step 8: `erpTogglePayment`에서 `erpResolveOrderId(true)` 호출로 교체
- [ ] Step 9: `erpSaveStructured`에서 `erpResolveOrderId(true)` 호출로 교체

### Phase 3 (선택, 별도 Spec 권장)
- [ ] erp_beta.js 분리 및 include 구조 변경

---

## 4. 검증 기준

- [ ] `python -c "import app; print('APP_OK')"` 통과
- [ ] add_order ERP Beta 탭: 저장 없이 결제 아이콘 클릭 → draft 생성 후 결제 확인 토글
- [ ] edit_order ERP Beta 탭: 결제 아이콘 클릭 → 기존대로 동작
- [ ] 첨부 업로드, AS 접수 등 기존 플로우 정상 동작
- [ ] 브라우저 콘솔에 불필요한 에러 없음 (의도적 console.warn만 발생)

---

## 5. 참고 자료

- `docs/evolution/2026-03-18-PAYMENT-ICON-SAVE-FREE-CLICK.md`
- `AGENTS.md` — 문제 수정 정책 (에러 숨기기 금지)
- `CLAUDE.md` — 코딩 규칙 (인라인 script 300줄)
