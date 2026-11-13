# 협력사 AS 접수 · 수정 · 채널톡 AS방 PUSH (PARTNER-AS-02)

- 작성: 2026-11-13
- 상태: ✅ 운영 반영 — deploy `584e0a963` · 운영 PR #837 (`df20c387`, 2026-11-13). 잔여: 첫 실사용 확인 · §7
- 목업: https://claude.ai/artifact/1tVmxSWYS1yLysE83GAqrY (8장 — 흐름 · PC 목록 · 접수 창 3가지 · 접수 뒤 주문 화면 · 휴대폰 · AS방 글)
- 선행: `2026-10-08-partner-portal_SPEC.md` §14(협력사 AS 접수 1판), `2026-10-19-partner-foms-mode_SPEC.md` §3.6,
  `2026-08-20-as-erp-gallery-bind-and-push-confirm_SPEC.md`(AS PUSH 첨부 고르기)

## 1. 왜

협력사 고객의 AS 는 협력사를 통해서만 받는다(2026-10-08 결정). 1판은 접수만 됐다.

- 접수 뒤 고칠 수 없었다(열린 건이 있으면 409 "저희 담당자에게 알려 주세요").
- 채널톡 AS방으로 가지 않았다. 우리 AS 팀은 AS방을 보고 일한다.
- 본사 접수 정본(`register_as_from_payload`)을 타지 않아 부수 기록이 달랐다 — 변경 원장 ·
  `_audit_as` · 앞 접수 사진 옮기기 · 미결합 AS 사진 결합이 없었다.
- 사진만 됐다(동영상 안 됨).

## 2. 결정

| # | 결정 | 누가 |
|---|------|------|
| D1 | 협력사 접수 · 수정은 본사 접수 정본 `register_as_from_payload` 를 그대로 탄다(새 건 = `register_as_cycle`, 열린 건 = 같은 건 갱신 `_apply_reregistration`). 협력사 몫은 권한 · 단계 문 · 이름 꼬리 "(협력사)" 뿐 | 사용자(“본사 erp 프로세스와 완벽히 호환”) |
| D2 | 접수(처음 · 재접수) 때 AS방 자동 PUSH, 수정 때 `[수정]` 머리말로 자동 재 PUSH. 글 · 방 · 이력 칸은 본사 AS PUSH 와 같다(`run_manual_push(push_kind='as')`) | 사용자 |
| D3 | 수정은 AS 가 끝나기 전까지(현재 건 RECEIVED · IN_PROGRESS) | 사용자 11-13 |
| D4 | 메뉴 "완공 사진 · AS" = 완료 + AS 진행 중 한 목록. PC 목록 줄의 "현재 작업" 칸에 [AS 접수] · [AS 재접수] · [AS 접수 수정] | 사용자 11-13 |
| D5 | 동영상도 받는다. 갤러리 열기는 본사 주문 상세 AS 접수 창 그대로(`photo-capture.js` 갤러리 입력 `multiple accept="image/*,video/*,.gif"`, 카메라 입력은 `accept="image/*" capture`) | 사용자 11-13 |
| D6 | 협력사 창에서 뺀 칸: 비용 구분(협력사 접수는 늘 '미정' — 판정은 우리 AS 팀), 상차일(지방), 도면팀 부탁, 끝난 건 다시 열기(같은 건 재접수) | 목업 승인 |
| D7 | 2번째 AS 의 첫 PUSH: AS PUSH 이력 칸이 주문마다 하나라 본사와 똑같이 "다시 보내기"로 나간다. 머리말 `[수정]` 아래 줄 "새 AS 접수 (N번째 AS)" | Claude(본사 동작을 바꾸지 않으려고) |
| D8 | 파일은 협력사 길(`/api/partner/orders/<id>/as/files`)로 한 개씩 올린다. 본사 R2 직접 올리기 길은 협력사 계정에 열려 있지 않다 → 파일 한 개 50MB 까지(요청 본문 상한) | Claude |

## 3. 길 (주소)

모두 `partner_required` + `partner_can_read_order`(자기 회사 주문만, 아니면 404). 새 Blueprint `partner_as`
(`foms/api/partner/as_intake.py`, url_prefix `/api/partner`) — `foms/api/partner/__init__.py` 500줄 래칫 때문에 옮김.

| 주소 | 하는 일 |
|------|---------|
| `GET  /orders/<id>/as` | 접수 창 값: `mode`(new · reintake · edit), 지금 접수 글, 지난 AS 요약, 완공 사진, AS방 상태 |
| `POST /orders/<id>/as` | 처음 · 재접수. multipart `content` · `construction_photo_ids` · `recurrence` · `photos`(1판 그대로) · `defer_push` · `idempotency_key` |
| `POST /orders/<id>/as/edit` | 같은 건 고치기. `content` · `change_note`(필수) · `defer_push` |
| `POST /orders/<id>/as/files` | 파일 1개(`file` · `as_log_id` · `sort_order`). `as_log_id` 는 **현재 건의 지금 접수 줄**만 |
| `POST /orders/<id>/as/push` | AS방 보내기(창이 파일을 다 올린 뒤, 또는 실패 뒤 [다시 보내기]). `attachment_ids` · `change_note` |

창 흐름: 파일이 없으면 접수 한 번에 끝(서버가 바로 PUSH). 파일이 있으면 `defer_push=1` 로 접수 → 파일 한 개씩 →
`/as/push`(올린 파일 id 만). 수정 PUSH 는 새로 올린 파일만 싣는다(보낸 사진을 또 보내지 않는다).

PUSH 가 실패해도 접수 · 수정은 그대로 남는다. 화면은 "AS방 전송 실패 · [다시 보내기]"를 보인다. "보낼 게 남았다"
판정 = 지금 접수 줄 시각 > AS PUSH 마지막 보낸 시각.

## 4. 본사와 같은 것 · 다른 것

같음: AS 건(`as_lifecycle`) · 접수 기록(`as_log` reception) · "AS 접수됨" 시스템 줄 · 변경 원장 · `_audit_as` ·
앞 접수 사진 옮기기(`carry_over_reception_attachments`) · AS 사진 칸(`category='as'` + `as_log_id`) · AS방
(`CHANNEL_GROUP_AS`) · AS방 글(`build_as_push_text`) · 이력 칸(`channeltalk_push_as`). 그래서 우리 직원이
나중에 AS 대시보드에서 AS PUSH 를 누르면 재전송으로 이어진다.

다름(협력사 꼬리): 접수 줄 `by` = "이름 (협력사)", 시스템 줄 "AS 접수됨 (협력사)", 완공 사진 고르기 →
접수 줄 `ref_attachment_ids` + 글 끝 "[완공 사진 참고] …", 감사 `PARTNER_AS_REGISTERED` · `PARTNER_AS_UPDATED`,
처음 · 재접수 때 CS 벨 1건(1판 그대로). 본사 함수에는 키워드 3개만 더한다(`actor_label` · `system_text` ·
`reception_extra`, 기본값이면 본사 동작 그대로).

## 5. 화면

- 창은 본사 `#asReceiveModal` 과 같은 칸 · 같은 글(제목 · AS 내용 예시 · 같은 건 안내 · 지난 AS 요약 · 지난 증상
  불러오기 · 재발 체크 · 사진/동영상 첨부 · 순서 정하기 `as-attachment-order.js` · Ctrl+V). 협력사 화면엔 부트스트랩
  JS 가 없어 여닫기만 협력사 방식(휴대폰은 아래에서 올라오는 칸).
- 주문 화면 완공 사진 탭: 1판의 접수 칸 대신 [AS 접수] · [AS 재접수] 단추, 진행 중이면 AS 내용 · AS방 줄 · [AS 접수 수정].
- 목록(PC): D4. 휴대폰 목록 줄은 그대로(주문 화면에서 접수).

## 6. 시험

`tests/security/test_partner_as_intake_v2.py` — 본사 정본 부수 기록(원장 · 시스템 줄 · 꼬리 · 비용 미정), 같은 건
고치기(건 수 그대로 · 접수 줄 하나 더 · 앞 사진 옮김), 열린 건 없을 때 고치기 409, 파일은 지금 접수 줄에만, PUSH
글 종류 · 머리말(D7) · 새 파일만, 남의 회사 404, 허용 목록 · 매니페스트.

## 7. 남은 것

- 50MB 넘는 동영상: 협력사용 R2 직접 올리기 길(별도 보안 검토).
- 실화면: 스테이징 AS방은 실제 방일 수 있다 — 전송은 로컬 준비물 서버에서 막고 확인한다.

## 8. AS 내역 — 접수 내역 · 완료 내역 (사용자 2026-11-13 추가)

"AS 완료 시 완료 내역 > 접수 시 접수 내역도 볼 수 있게". 주문 화면 완공 사진 탭에 건마다(최근 건 먼저,
`foms/services/partners/as_history.py`):

- 접수 내역: 접수일 · 접수 내용(지금 글) · 고친 기록(같은 건 재접수로 쌓인 앞 글, 시각 · 쓴 사람) · 접수 사진
- 완료 내역: 방문일 · 완료일 · 처리(몇 차 미결 → 몇 차 완결) · 처리 사진(판정 · 방안 · 조치 · 메모 줄에 붙은 사진)
- 숨김(우리 몫): 판정 사유 · 완료 메모 글(2026-10-19 이력 탭 결정 — "부품비 우리 부담" 같은 글), 통화 · 자재 ·
  메모 · 방안 글, 비용, 자재 · 통화 줄 사진(견적 · 영수증일 수 있다)

진행 중인 건은 위 진행 칸에서 같은 접수 내역 · 처리 · 사진을 보이고, 끝난 건은 접기 칸(가장 최근 건이 펼쳐짐).
시험: `test_completed_as_shows_reception_and_completion_history`.
