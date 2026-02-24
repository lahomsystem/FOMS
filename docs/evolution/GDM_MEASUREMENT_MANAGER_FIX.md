# 실측 대시보드 담당자 입력 사라짐 현상 - 코드 리뷰 및 수정

**일자**: 2026-02-23  
**요청**: 담당자 입력 후 값이 저장되지 않고 사라짐 → GDM 코드 리뷰 후 수정

---

## 1. 발견한 원인 (코드 리뷰)

### 1.1 잘못된 API URL (근본 원인)

- **현상**: 담당자 입력 후 blur 시 "저장 중..." → 이전 값으로 되돌아감(입력 사라짐).
- **원인**: 비-ERP 주문 담당자 저장 시 `measurement.js`에서 **`/api/orders/update_order_field`** 를 호출하고 있었음.
- **사실**: `apps/api/orders.py`의 `orders_bp`는 `url_prefix='/api'` 이고 라우트는 `@orders_bp.route('/update_order_field')` 이므로 **실제 경로는 `/api/update_order_field`**.
- **결과**: `/api/orders/update_order_field` 호출 → **404 Not Found** → 응답이 HTML 에러 페이지 → `res.json()` 파싱 실패 또는 `data.success === false` → 기존 값으로 복원되어 "입력이 사라진 것처럼" 보임.

### 1.2 기타 보강 사항

- **비-JSON 응답**: 404 등으로 HTML이 오면 `response.json()`에서 예외가 나거나 잘못 파싱될 수 있음. Content-Type 확인 후 JSON만 파싱하도록 처리.
- **저장 실패 시 피드백**: 실패 시 콘솔에 메시지 출력해 디버깅 용이하게 함.
- **담당자 색상**: 저장 성공 후 셀 텍스트만 바꾸면 배경색이 이전 담당자 색으로 남을 수 있음. 새 값 기준으로 색 다시 적용.

---

## 2. 수정 내용

| 파일 | 변경 |
|------|------|
| `static/js/erp/measurement.js` | ① **URL 수정**: `/api/orders/update_order_field` → **`/api/update_order_field`** (비-ERP 담당자 저장). ② fetch에 `credentials: 'same-origin'` 명시. ③ 응답이 JSON인지 확인 후 파싱, 비-JSON이면 `{ success: false, error: '...' }` 로 처리. ④ 저장 성공 시 담당자 셀에 한해 `managerColorMap[newValue]` 또는 `#CCCCCC` 로 배경색 재적용. ⑤ 실패 시 `data.message`/`data.error`를 콘솔에 출력. |

---

## 3. 검증 방법

1. **실측 대시보드** (`/erp/measurement`) 접속.
2. **비-ERP Beta 주문**의 담당자 셀 클릭 → 이름 입력(또는 수정) → 셀 밖으로 포커스 이동.
3. "저장 중..." 후 **입력한 값이 그대로 유지**되는지 확인.
4. 해당 주문의 주문 상세/편집 페이지에서 **담당자 필드에 동일 값**이 보이는지 확인.
5. **ERP Beta 주문**으로도 동일하게 담당자 입력 → 유지·주문 상세 반영 확인.

---

## 4. 참조

- 실측 담당자 기능 계획: `docs/memory/PLAN_MEASUREMENT_MANAGER.md`
- API: `apps/api/orders.py` (`/api/update_order_field`), `apps/api/erp_measurement.py` (`/api/erp/measurement/update/<id>`)
- 다른 대시보드에서의 호출 예: `templates/regional_dashboard.html` 등은 **`/api/update_order_field`** 사용 (정상).
