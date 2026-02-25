# AS 대시보드 사진 조회·AS 접수 완성 코드 검수 리뷰

**검수일**: 2026-02-25  
**검수 기준**: Grand Develop Master, 계획서 PLAN_AS_DASHBOARD_PHOTOS_AND_RECEIPT.md

---

## 구현 요약

| 구분 | 항목 | 상태 | 비고 |
|------|------|------|------|
| A | can_view_as_photos 전달 | ✅ | erp_as_page.py, 시공 팀이 아닐 때만 True |
| A | PC 테이블 주소·AS내용 사이 첨부 컬럼 | ✅ | th 첨부, td 파일 아이콘(권한 시만) |
| A | 모바일 카드 AS 사진 row | ✅ | can_view_as_photos일 때만 |
| A | AS 사진 모달 + GET ?category=as 갤러리 | ✅ | asPhotosModal, 이미지/파일 링크 표시 |
| B | order_attachments.user_id 컬럼·모델 | ✅ | 모델 추가, ensure_order_attachments_user_id_column() |
| B | 업로드/complete 시 user_id 저장 | ✅ | session.get('user_id') |
| B | 삭제 API 타 사용자 403 | ✅ | att.user_id != current_user_id 시 403 |
| B | POST /api/orders/<id>/as/register | ✅ | as_content, as_received_date=today, status=AS_RECEIVED |
| B | AS 접수 모달 textarea + 등록 API | ✅ | 업로드 성공 후 as/register 호출 |
| B | AS 재업로드(본인 것만 삭제) | ✅ | openAsReuploadModal, submit 시 user_id 일치만 DELETE |

---

## 보안·권한

- **AS 사진 조회**: 시공 팀(CONSTRUCTION)이 아니면 파일 아이콘 노출·모달 조회 가능. API는 기존 `GET /api/orders/<id>/attachments?category=as` (login_required) 그대로 사용.
- **AS 접수 등록**: `erp_construction_edit_required`로 시공팀·관리자만 `POST as/register` 호출 가능.
- **첨부 삭제**: `user_id`가 있는 레코드는 업로더만 삭제 가능(403). `user_id` NULL(레거시)은 기존처럼 삭제 허용(마이그레이션 기간).

---

## 엣지 케이스

- **AS 접수 시 사진 0개**: 현재는 "AS 사진을 선택해주세요"로 업로드 필수. 내용만 등록하려면 별도 플로우 필요 시 확장 가능.
- **AS 재업로드 시 CURRENT_USER_ID 없음**: `data-current-user-id`가 비면 프론트에서 본인 삭제 단계를 건너뜀(삭제 0건 후 업로드만 수행). 서버 삭제 API는 여전히 본인만 403으로 보호.
- **PostgreSQL user_id 컬럼**: `ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL` 사용. 기존 `migrate_attachment_user.py`로 이미 컬럼이 있으면 ensure 시 스킵.

---

## 파일 변경 목록

- `apps/erp_as_page.py`: can_view_as_photos 계산·전달
- `templates/erp_as_dashboard.html`: 첨부 컬럼, 모달, AS 사진 버튼·JS
- `models.py`: OrderAttachment.user_id, to_dict에 user_id
- `apps/api/attachments.py`: ensure_order_attachments_user_id_column, complete/upload 시 user_id, delete 시 403
- `apps/api/erp_orders_as.py`: POST as/register, _ensure_path
- `templates/partials/erp_construction_modals.html`: AS 내용 textarea, reupload hidden, data-current-user-id
- `templates/partials/erp_construction_scripts.html`: openAsReuploadModal, submitAsAccept 재업로드·등록 로직, CURRENT_USER_ID
- `templates/partials/erp_construction_filters_grid.html`: AS 재업로드 버튼

---

## 권장 사항

1. **DB**: 최초 배포 시 `user_id` 컬럼 없으면 ensure 호출로 자동 추가됨. 이미 `migrate_attachment_user.py` 실행한 환경은 동일 스키마.
2. **테스트**: 시공 팀 계정으로 AS 접수·재업로드, 비시공 팀 계정으로 AS 대시보드에서 사진 조회·비조회 확인 권장.
3. **AS 접수일 타임존**: `datetime.datetime.now()`는 서버 로컬 시간. KST 고정이 필요하면 `get_today_kst()` 등 기존 정책에 맞춰 통일.

---

**검수 결과**: 계획서 반영 완료, 권한·삭제 보호·API 일관성 유지. 위 권장 사항만 확인 후 배포 가능.
