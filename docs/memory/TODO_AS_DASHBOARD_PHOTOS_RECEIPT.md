# AS 대시보드 사진·접수 TODO

## A. AS 대시보드 - 카테고리 사진 조회
- [x] erp_as_page: can_view_as_photos 전달
- [x] erp_as_dashboard.html PC: 주소·AS내용 사이 첨부 컬럼 + 파일 아이콘 (can_view_as_photos일 때만)
- [x] erp_as_dashboard.html 모바일: 주소·AS내용 사이 AS 사진 영역 + 아이콘
- [x] AS 사진 모달 + JS: GET attachments?category=as → 갤러리 표시

## B. AS 신규 접수 프로세스
- [x] DB: order_attachments.user_id 컬럼 + OrderAttachment.user_id
- [x] 업로드/complete 시 user_id 저장
- [x] 삭제 API: 타 사용자(user_id 불일치) 첨부 삭제 시 403
- [x] POST /api/orders/<id>/as/register (as_content, as_received_date=today, status=AS_RECEIVED)
- [x] AS 접수 모달: AS 내용 textarea + 등록 API 호출
- [x] AS 재업로드: 본인 AS 첨부만 삭제 후 업로드 (목록/삭제에 user_id 반영)
