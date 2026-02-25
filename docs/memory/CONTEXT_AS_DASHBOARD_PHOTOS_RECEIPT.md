# AS 대시보드 사진 조회·AS 접수 맥락 노트

**목적**: A(AS 사진 조회)·B(AS 접수 프로세스) 결정 사항과 배경 기록.

- **권한**: “시공자가 아닌 사용자만 AS 사진 조회” → `current_user.team != 'CONSTRUCTION'`(또는 동등한 팀/역할 체크)로 판단. 팀 코드는 기존 `User.team`/역할 규칙에 맞춤.
- **AS 내용·접수일**: AS 내용은 `structured_data.shipment.as_content`, 접수일은 `Order.as_received_date`. 기존 `update_order_field`로 as_content 저장 가능. 접수일+상태(AS_RECEIVED)는 전용 `POST as/register`로 한 번에 처리하는 것을 권장.
- **재업로드 보호**: `OrderAttachment`에 `user_id` 추가해 “본인이 올린 AS 첨부만 삭제/재업로드” 가능하도록 함. 다른 사용자 첨부는 DELETE API에서 403 처리.
- **갤러리/모달**: 기존 ERP 첨부 미리보기(`openAttachmentsPreview`, category=as) 패턴 재사용. AS 대시보드만 별도 모달로 둘 경우 동일 API `GET /api/orders/<id>/attachments?category=as` 사용.
