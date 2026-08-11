# 고객 공유 채널 Phase A — Progress Ledger

> 플랜: `docs/plans/2026-08-11-customer-share-phase-a-plan.md` / 스펙: `docs/specs/2026-08-11-customer-share-phase-a-design.md` (v3)
> 상태값: PENDING / IN_PROGRESS / DONE / BLOCKED(사유 원문 필수)
> 갱신 규칙: task 완료 = 검증 명령 exit 0 + 커밋 SHA 기록 후 DONE. compaction 후 재개 시 이 파일이 정본.
> 작업 트리: `c:/tmp/foms-alimtalk-reapply` (브랜치 `alimtalk-reapply`)

## Stage-1 — 도면 공유

| Task | 내용 | 완료 기준 | 상태 | 커밋 SHA | 비고 |
|---|---|---|---|---|---|
| T1 | 토큰 모델·마이그레이션·서비스 코어 (파일럿) | `pytest tests/domains/test_order_share_service.py tests/domains/test_alembic_single_head.py -q` PASS + APP_OK | DONE | 073b89b3 | 14 passed. head=seclog_time_00 뒤 단일 연결. 지문 정합 위해 양쪽 server_default 無, snapshot=JSON+JSONB variant |
| T2 | 비로그인 열람 `GET /s/<token>` (drawing) | `pytest tests/domains/test_order_share_view.py -q` PASS(격리·410·fail-closed 503 표면·헤더·FILE_VIEW 1행) + APP_OK | PENDING | | estimate kind는 404 |
| T3 | 직원 API create/revoke + manifest·감사 | `pytest tests/domains/test_order_share_api.py tests/domains/test_write_guard.py tests/domains/test_auth_enforcement.py -q` PASS + audit 인벤토리 재생성 + APP_OK | PENDING | | cb58edb6 등재 패턴 미러 |
| T4 | 공유 UI 모달 (PC·모바일) + list API | 계약 테스트 PASS + browse 2뷰포트 스모크(모달·복사·목록) + APP_OK | PENDING | | baa0fee8 패턴 미러, 견적서 옵션 비활성, URL은 발급 직후 1회만 |
| T5 | Stage-1 통합 검증·스테이징 배포 | pre_push_smoke exit 0 + `gh run list` 전 워크플로 green + E2E 기록 | PENDING | | 카톡 실공유는 도메인 등록 후(미완=BLOCKED 기록 후 전진) |

## Stage-2 — 견적서·문자·태블릿

| Task | 내용 | 완료 기준 | 상태 | 커밋 SHA | 비고 |
|---|---|---|---|---|---|
| T6 | 견적 스냅샷 빌더 (화이트리스트+동결+64KB 캡) | `pytest tests/domains/test_order_share_estimate.py -q` PASS(타 브랜드 계좌 부재·불변·400) + APP_OK | PENDING | | |
| T7 | 견적 열람 렌더 + kind UI 해금 | view 테스트 PASS + browse 모바일 렌더(옵션 해금·64KB 400 표시) + APP_OK | PENDING | | erp-share.js ?v 범프 |
| T8 | 문자 발송 (sender_phone·_solapi_send_text·멱등·버튼 배선) | `pytest tests/domains/test_order_share_sms.py tests/domains/test_write_guard.py tests/domains/test_auth_enforcement.py -q` PASS + audit 인벤토리 재생성 + APP_OK | PENDING | | 실발신은 T10, §1 선점 insert+토큰 원문 검증 |
| T9 | 태블릿 공유 버튼 (tablet-measure-form.js) | 태블릿 계약 테스트 PASS + browse coarse 스모크 + APP_OK | PENDING | | 핫파일 규칙 확인 |
| T10 | Stage-2 통합 검증·스테이징 E2E | pre_push_smoke exit 0 + CI green + E2E(스냅샷 불변·문자 3사·카톡 실기기) | PENDING | | 발신번호 미등록=문자만 BLOCKED |

## 외부 준비 (사용자 액션)
- [ ] 카카오 개발자 앱 도메인 2종 등록 + 지도 앱과 동일 앱 여부 회신 (T5 카톡 E2E 전제)
- [ ] 영업 인원 Solapi 발신번호 등록 → 번호 목록 전달 (T10 실수신 전제)

## 결정 기록
- 플랜 확정 3건(CEO 2-agent 리뷰 반영): 스냅샷 64KB 캡=초과 시 400(절단 금지) / send-sms 멱등=**발송 전 앵커 선점 insert**+시간버킷 dedupe_key(`share_sms:{share_id}:{floor(epoch/5)}`) — DB UNIQUE로 동시 중복 차단, 감사 조회식 check-then-act 폐기 / send-sms URL=body 토큰 원문 재해시 검증 후 서버 조립(해시-온리 저장과 충돌 해소, 문자 발송은 발급 직후만)
- CEO 2-agent 리뷰(2026-08-11): HIGH 3건(T1 가짜 테스트 경로·URL 재구성 충돌·멱등 레이스)+MED 6건 플랜 반영 완료, 수용 리스크는 플랜 §4 기록
- 스펙 v3 사용자 결정 D1~D8 준수(풀스코프 v1, 도면 먼저 단계 배포)
