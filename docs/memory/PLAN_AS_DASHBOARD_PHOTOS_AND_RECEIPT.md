# AS 대시보드 사진 조회 및 AS 신규 접수 프로세스 계획서

**작성일**: 2026-02-25  
**참조**: grand-develop-master, 기존 AS 대시보드·시공 AS 접수·첨부 API 코드 리뷰 반영

---

## A. AS 대시보드 - 카테고리 사진 조회

### 목표
AS 대시보드에서 해당 주문의 AS 카테고리 첨부 사진을 확인할 수 있도록 한다.

### 기존 코드 요약
- **AS 대시보드**: `apps/erp_as_page.py` → `templates/erp_as_dashboard.html`
- 테이블 컬럼: 주문, AS 접수일, AS 방문일, AS 완료일, 담당자, 고객, **주소**, **AS 내용**, 상태
- AS 내용: `structured_data.shipment.as_content`, 저장은 `/api/update_order_field` (field_name: `as_content`)
- 첨부 목록 API: `GET /api/orders/<id>/attachments?category=as` (이미 구현됨)
- 다른 대시보드에서 첨부 미리보기: `openAttachmentsPreview(orderId, initialCategory)` → 모달에 탭/갤러리

### 세부 요구사항 및 구현 방향

| 요구사항 | 구현 방향 |
|----------|-----------|
| 주소와 AS내용 컬럼 **사이**에 파일 아이콘 추가 | PC 테이블: 주소 다음에 `<th>첨부</th>` 추가, 각 행에 `<td>` + 파일 아이콘 버튼(해당 주문 AS 사진 개수 배지 가능). 모바일 카드: 주소/AS내용 사이에 첨부 영역 추가. |
| 아이콘 클릭 시 해당 AS 이미지 모달/갤러리 표시 | 기존 `openAttachmentsPreview(orderId, 'as')` 패턴 활용. AS 대시보드 전용 스크립트에서 `GET /api/orders/<id>/attachments?category=as` 호출 후 모달에 갤러리 렌더링(또는 기존 ERP 첨부 모달 재사용). |
| **권한: 시공자가 아닌 사용자만 조회** | 뷰에서 `current_user.team != 'CONSTRUCTION'`(또는 `can_view_as_photos`) 플래그 전달. 테이블/카드에서 해당 시 True일 때만 파일 아이콘 노출. |

### 작업 목록 (A)
1. **erp_as_page.py**: 템플릿에 `can_view_as_photos` 전달 (예: `not (current_user and getattr(current_user, 'team') == 'CONSTRUCTION')`).
2. **erp_as_dashboard.html (PC)**: `<th>주소</th>` 다음에 `<th>첨부</th>`, 각 행 주소 다음에 `<td>` 추가. 내부에 `can_view_as_photos`일 때만 파일 아이콘 버튼(또는 링크), `data-order-id`, 클릭 시 AS 사진 모달 오픈.
3. **erp_as_dashboard.html (모바일 카드)**: 주소 row와 AS 내용 row 사이에 “AS 사진” row 추가, `can_view_as_photos`일 때만 파일 아이콘 + 클릭 시 모달.
4. **AS 사진 전용 모달 + JS**: 모달 마크업 추가, 클릭 시 `GET /api/orders/<order_id>/attachments?category=as` 호출 후 갤러리 표시(이미지/동영상). 기존 `erpAttachmentsCategoryModal` 스타일 재사용 가능.

---

## B. AS 신규 접수 프로세스

### 목표
- 시공 대시보드에서 시공자가 “AS 접수” 시 **AS 내용 입력** + **접수일 자동 등록**까지 한 번에 처리.
- AS 이미지는 **재업로드 가능**하되, **다른 사용자가 올린 AS 이미지는 삭제하지 않음**.

### 기존 코드 요약
- **시공 AS 접수**: `openAsAcceptModal(orderId)` → `submitAsAccept()`: `category='as'`로 session → PUT → attachments/complete 만 호출. **AS 내용·접수일·상태 변경 없음.**
- **OrderAttachment**: `models.OrderAttachment`에 **user_id(업로더) 컬럼 없음.** → 재업로드 시 “본인만 삭제” 구현을 위해 **user_id 저장 필요.**
- **AS 내용 저장**: `/api/update_order_field` (order_id, field_name: `as_content`, new_value).
- **접수일/상태**: `Order.as_received_date`, `Order.status = 'AS_RECEIVED'`. 업데이트는 `update_order_field` 또는 전용 API로 가능.

### B.3 시공 대시보드 - AS 접수 입력 기능

| 요구사항 | 구현 방향 |
|----------|-----------|
| AS 이미지 업로드 시 **AS 내용** 입력란 추가 | AS 접수 모달(`erpConstructionAsAcceptModal`)에 텍스트 입력(textarea) 추가. placeholder 예: "AS 접수 내용을 입력하세요." |
| 입력된 AS 내용을 AS 대시보드의 as-content-input에 **자동 저장** | 업로드 성공 후 `POST /api/update_order_field`로 `field_name: 'as_content'`, `new_value: 모달 입력값` 전송. (이미 구현된 필드이므로 동일 API 사용.) |
| 접수일 **현재 날짜로 자동 등록** | 업로드(및 AS 내용 저장) 성공 후, `order.as_received_date = today`, `order.status = 'AS_RECEIVED'` 설정하는 API 호출. 신규 엔드포인트 예: `POST /api/orders/<id>/as/register` (as_content, as_received_date=today, status=AS_RECEIVED) 또는 기존 `update_order_field`에 as_received_date + status 연동. |

권장: **AS 접수 등록 API 1개**  
- `POST /api/orders/<order_id>/as/register`  
  - body: `{ "as_content": "..." }` (선택)  
  - 처리: `structured_data.shipment.as_content` 저장, `as_received_date = 오늘`, `status = 'AS_RECEIVED'`, 필요 시 workflow 기록.  
- 시공 대시보드: AS 이미지 업로드 완료 후 이 API 호출(모달 AS 내용 전달). 그 다음 페이지 새로고침 또는 성공 메시지.

### B.4 AS 이미지 재업로드 기능

| 요구사항 | 구현 방향 |
|----------|-----------|
| 시공자가 올린 AS 이미지는 **재업로드 가능** (기존 삭제 후 새 이미지) | 시공 완료 행 등에 “AS 재업로드” 버튼 추가. 클릭 시: **현재 로그인 사용자가 업로드한** AS 첨부만 삭제 후 새 파일 업로드. |
| **다른 사용자가 업로드한 AS 이미지는 절대 삭제 금지** | 삭제 시 조건: `category='as' AND user_id = current_user_id`. 따라서 **업로드 시 user_id 저장** 필요. |
| 업로드 사용자 ID 저장 | `order_attachments` 테이블에 `user_id`(nullable) 컬럼 추가. 업로드/complete 시 `session['user_id']` 저장. (기존 마이그레이션 `migrate_attachment_user.py` 등 참고.) |
| 재업로드 시 현재 사용자 == 업로드 사용자 확인 | 삭제 API 또는 재업로드 플로우: 목록 조회 시 `user_id` 포함, 삭제는 `attachment.user_id == current_user_id`인 것만 삭제. |

### 작업 목록 (B)

**DB·백엔드**
1. **order_attachments.user_id**: 컬럼 없으면 마이그레이션 추가. `OrderAttachment` 모델에 `user_id = Column(Integer, ForeignKey('users.id'), nullable=True)` 추가.
2. **업로드 시 user_id 저장**: `api_order_attachments_upload`, `api_order_attachments_complete` 등에서 생성/갱신 시 `user_id=session.get('user_id')` 설정.
3. **삭제 시 본인만**: `api_order_attachments_delete`에서 `att.user_id is not None and att.user_id != session.get('user_id')`이면 403 또는 400 반환(다른 사용자 첨부 삭제 금지).
4. **AS 접수 등록 API**: `POST /api/orders/<id>/as/register` (또는 기존 AS 라우트 확장). as_content 저장, as_received_date=today, status=AS_RECEIVED, 필요 시 workflow.

**시공 대시보드 UI**
5. **AS 접수 모달**: AS 내용 textarea 추가, submit 시 업로드 → as_content 저장 → as/register 호출(접수일·상태) → 새로고침.
6. **AS 재업로드 버튼**: 시공완료 행 퀘스트에 “AS 재업로드” 버튼 추가. 클릭 시 기존과 동일한 재업로드 모달이지만, **삭제 시 `GET /api/orders/<id>/attachments?category=as` 후 `user_id === current_user_id`인 것만 DELETE** 하도록 스크립트 수정.
7. **목록 API 응답에 user_id 포함**: `to_dict()` 또는 목록 응답에 `user_id` 포함해 프론트에서 “본인 업로드만 삭제” 판단 가능하게(이미 to_dict에 포함시키면 됨).

---

## 구현 순서 제안

1. **A**: AS 대시보드 파일 아이콘 + 조회 권한 + 모달/갤러리 (기존 API만 사용).
2. **B DB**: order_attachments.user_id 컬럼 및 모델, 업로드/complete 시 user_id 저장.
3. **B 삭제 보호**: 삭제 API에서 타 사용자 첨부 삭제 거부.
4. **B AS 접수 등록**: POST as/register 또는 update_order_field 연동으로 as_content + as_received_date + status.
5. **B 시공 UI**: AS 접수 모달에 AS 내용 입력 + 등록 API 호출, AS 재업로드 버튼 + “본인 것만 삭제 후 업로드” 로직.

---

## 참고 파일

- AS 대시보드: `apps/erp_as_page.py`, `templates/erp_as_dashboard.html`
- 시공 AS 접수: `templates/partials/erp_construction_modals.html`, `erp_construction_scripts.html` (openAsAcceptModal, submitAsAccept)
- 첨부 API: `apps/api/attachments.py`, `models.OrderAttachment`
- 주문 필드 업데이트: `apps/api/orders.py` (update_order_field, as_content, as_received_date 등)
- AS API: `apps/api/erp_orders_as.py`
