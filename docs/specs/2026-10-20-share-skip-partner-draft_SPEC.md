# 고객 공유 링크 도면 목록에서 협력사 초안 빼기 — SPEC (2026-10-20)

## 목적
협력사가 주문 화면에서 올린 "초안 도면"은 도면팀이 고쳐 넘기기 전의 참고 자료다. 협력사 화면의 "최종 도면"은 이미 초안을 뺀다(`resolve_final_drawing_files`, 스펙 `docs/specs/2026-10-08-partner-portal_SPEC.md` 3-1). 그런데 직원이 그 주문으로 공유 링크를 만들면 링크의 도면 목록에 초안이 "도면"으로 들어간다. 링크 주소를 복사해 전하면 도면팀 작업 전 초안이 도면처럼 보인다.

## 확인한 현재 동작(2026-10-20, 테스트 DB 재현)
- 협력사 "초안" 업로드: 첨부 분류 `drawing`, 폴더 `orders/<id>/partner_draft/`(`foms/api/partner/__init__.py` `_KINDS`).
- 고객 알림톡·문자 보내기: 협력사 주문이면 409 `partner_order` — 막혀 있다.
- 공유 링크 만들기 `POST /api/share/create/<id>`: 협력사 주문도 200(수신번호·문자 본문만 비움).
- 공유 링크 도면 목록 `_collect_drawing_files`(`foms/api/share.py`): 분류 `drawing` 첨부를 전부 모아 초안 키가 들어간다.

## 변경
- `_collect_drawing_files` 가 협력사 원본 폴더 키(`is_partner_original_key`, `foms/services/order_attachment_permissions.py`)를 건너뛴다. 이 함수를 쓰는 세 곳(공유 화면 도면 탭·도면 묶음 내려받기·도면 이미지 목록)이 함께 바뀐다.
- 첨부 행·파일은 그대로 둔다(직원 첨부 탭·협력사 화면 표시는 지금처럼).

## 건드리지 않는 것
- 협력사 주문 공유 링크 만들기 자체를 막는 일(협력사에게 직원이 링크를 전하는 쓰임이 있을 수 있다 — 막을지는 별도 결정).
- 첨부 분류 바꾸기(SEC-04 업로드 분류 신뢰 축, 사용자 결정으로 수정 안 함).

## 테스트
`tests/security/test_partner_share_draft.py`: 협력사 초안·실측 사진을 올린 주문에서 공유 도면 목록에 초안이 없고, 직원이 올린 도면은 있다(음성 대조군).
