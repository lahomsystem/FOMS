# 고객 공유 채널 Phase A — Progress Ledger

> 플랜: `docs/plans/2026-08-11-customer-share-phase-a-plan.md` / 스펙: `docs/specs/2026-08-11-customer-share-phase-a-design.md` (v3)
> 상태값: PENDING / IN_PROGRESS / DONE / BLOCKED(사유 원문 필수)
> 갱신 규칙: task 완료 = 검증 명령 exit 0 + 커밋 SHA 기록 후 DONE. compaction 후 재개 시 이 파일이 정본.
> 작업 트리: `c:/tmp/foms-alimtalk-reapply` (브랜치 `alimtalk-reapply`)

## Stage-1 — 도면 공유

| Task | 내용 | 완료 기준 | 상태 | 커밋 SHA | 비고 |
|---|---|---|---|---|---|
| T1 | 토큰 모델·마이그레이션·서비스 코어 (파일럿) | `pytest tests/domains/test_order_share_service.py tests/domains/test_alembic_single_head.py -q` PASS + APP_OK | DONE | 073b89b3 | 14 passed. head=seclog_time_00 뒤 단일 연결. 지문 정합 위해 양쪽 server_default 無, snapshot=JSON+JSONB variant |
| T2 | 비로그인 열람 `GET /s/<token>` (drawing) | `pytest tests/domains/test_order_share_view.py -q` PASS(격리·410·fail-closed 503 표면·헤더·FILE_VIEW 1행) + APP_OK | DONE | 84319e30 | 12 passed + namespace 게이트 358 passed. presign 전멸=503, onerror 새로고침 안내 |
| T3 | 직원 API create/revoke + manifest·감사 | `pytest tests/domains/test_order_share_api.py tests/domains/test_write_guard.py tests/domains/test_auth_enforcement.py -q` PASS + audit 인벤토리 재생성 + APP_OK | DONE | 93b0e142 | 49 passed + audit 게이트 11 passed(coverage 100%). 감사에 토큰·URL 미격납 assert |
| T4 | 공유 UI 모달 (PC·모바일) + list API | 계약 테스트 PASS + browse 2뷰포트 스모크(모달·복사·목록) + APP_OK | DONE | bef517a5 | 110 passed(계약+게이트). browse 스모크는 T5 통합 실행(알림톡 T5 선례). 카톡 키=지도 앱 키 fallback+env 오버라이드 |
| T5 | Stage-1 통합 검증·스테이징 배포 | pre_push_smoke exit 0 + `gh run list` 전 워크플로 green + E2E 기록 | DONE | 1f7999e4 | smoke 0·CI 4/4 green(Harness/PG Lane/perf-gate/FOMS). E2E 13항목 PASS: 로그인→발급→시크릿 열람 200+헤더 2종→열람수 반영→revoke 410→불량토큰 404→estimate 400. 주문 4287 카드·presigned·lightbox 렌더 확인. **주의**: 스테이징 이미지 실바이트는 전 키 NoSuchKey — 스테이징 DB(운영 복제)↔R2 버킷 드리프트(환경 이슈, presign 서명·경로 정상, onerror 안내 표면화). 실객체 검증=T10 업로드 흐름 동반. 카톡 실공유=**BLOCKED**(카카오 도메인 등록 사용자 액션 대기) |

## Stage-2 — 견적서·문자·태블릿

| Task | 내용 | 완료 기준 | 상태 | 커밋 SHA | 비고 |
|---|---|---|---|---|---|
| T6 | 견적 스냅샷 빌더 (화이트리스트+동결+64KB 캡) | `pytest tests/domains/test_order_share_estimate.py -q` PASS(타 브랜드 계좌 부재·불변·400) + APP_OK | DONE | c871807e | 8+14 passed. 브랜드 교차 계좌 유출 0·내부 키 차단·grand total 공식·동결·캡 400 전부 assert |
| T7 | 견적 열람 렌더 + kind UI 해금 | view 테스트 PASS + browse 모바일 렌더(옵션 해금·64KB 400 표시) + APP_OK | DONE | db6f23af | 27 passed. 스냅샷-온리 렌더(수정 미반영 assert)·스냅샷 부재 503·카톡 문구 kind 분기·?v 20260812a 범프+핀 전수. browse는 T10 통합 |
| T8 | 문자 발송 (sender_phone·_solapi_send_text·멱등·버튼 배선) | `pytest tests/domains/test_order_share_sms.py tests/domains/test_write_guard.py tests/domains/test_auth_enforcement.py -q` PASS + audit 인벤토리 재생성 + APP_OK | DONE | 6fd32f3c | 64 passed(게이트 포함)·coverage 100%. 선점 insert 멱등=벤더 호출 1회 assert, 감사=수신번호 마스킹·토큰 미격납, 발신 폴백 2분기, senderphone_00 마이그레이션 |
| T9 | 태블릿 공유 버튼 (tablet-measure-form.js) | 태블릿 계약 테스트 PASS + browse coarse 스모크 + APP_OK | DONE | cb9feef1 | 117 passed. 발급→URL 복사→(선택) 문자 confirm 흐름, ?v 20260812a 범프. browse coarse는 T10 통합 |
| T8.1 | 발신번호 3단 우선순위(담당자→브랜드 대표→구 폴백)+②실패 시 브랜드 백업 1회 재시도 | `pytest tests/domains/test_order_share_sms.py tests/domains/test_write_guard.py tests/domains/test_auth_enforcement.py tests/domains/test_audit_action_coverage.py tests/domains/test_audit_coverage_inventory.py -q` PASS + APP_OK + CI 전 워크플로 green | DONE | ad6dd47e | 17+63 passed. 구 규칙(버튼 누른 직원) 폐기, resolve_brand SSOT 재사용, 멱등 앵커 1개 유지·payload attempts 2회 기록(마스킹), 감사 sender_source 기록 |
| T10 | Stage-2 통합 검증·스테이징 E2E | pre_push_smoke exit 0 + CI green + E2E(스냅샷 불변·문자 3사·카톡 실기기) | DONE | 59e12874 | smoke 0·CI 4/4 green. E2E 12항목 PASS(주문 4389): 견적 발급→비로그인 열람(계좌·출고가·잔금 렌더·헤더 2종·내부 키 부재)→revoke 410, send-sms 503 not_configured 표면(스테이징 Solapi env 無 — 정상 fail-visible)·토큰 불일치 400. 스냅샷 동결은 pytest 5건이 정본 검증. **BLOCKED 3건**: 문자 3사 실수신(발신번호+Solapi env)·카톡 실기기(도메인 등록)·도면 이미지 실객체(스테이징 R2 드리프트, T5 참조) |

## 외부 준비 (사용자 액션)

### 문자 발신번호 확정 (사용자 결정 2026-08-12 — T8.1 발신 규칙의 정본)
- 발신 우선순위: ① 주문 담당자의 등록 개인번호(`users.sender_phone`, 담당자 기준 — 발송 버튼 누른 사람 아님) ② 브랜드 대표번호 ③ ② 벤더 실패 시 브랜드별 백업번호로 같은 요청 내 1회 재시도
- 하우드: 대표 `15660703` / 백업 `01044644260` → env `SOLAPI_SENDER_PHONE_HAUD` / `SOLAPI_SENDER_FALLBACK_HAUD`
- 라홈: 대표 `15660792` / 백업 `01083277282` → env `SOLAPI_SENDER_PHONE_LAHOM` / `SOLAPI_SENDER_FALLBACK_LAHOM`
- 영업 개인번호는 각자 Solapi 등록 후 /admin/users "문자 발신번호"에 입력. 위 4개 번호도 전부 Solapi 발신번호 등록 필요(법인 서류). 구 `SOLAPI_SENDER_PHONE`은 최후 폴백으로 유지.
- [x] Railway env 등록 완료 (2026-08-12, `--skip-deploys` — 다음 배포 때 적용): 스테이징=FOMS-DEV/서비스 `FOMS`, 운영=FOMS-PRODUCTION/서비스 `web`, 각 6종(발신 4 + 회전된 `SOLAPI_API_KEY`/`SECRET`). 로컬 .env도 새 키로 갱신됨. env 잔여 없음 — 실발송 검증 잔여는 Solapi 발신번호 등록(대표2·백업2·개인)과 카카오 도메인 등록뿐.
- [x] 카카오 개발자 앱 도메인 등록 완료 (2026-08-12 사용자) — 카톡 공유 검증 가능
- [~] Solapi 발신번호 등록 진행 중 (2026-08-12 — 대표2·백업2·영업 개인, 완료 시 문자 실수신 검증 가능)

## 결정 기록
- 플랜 확정 3건(CEO 2-agent 리뷰 반영): 스냅샷 64KB 캡=초과 시 400(절단 금지) / send-sms 멱등=**발송 전 앵커 선점 insert**+시간버킷 dedupe_key(`share_sms:{share_id}:{floor(epoch/5)}`) — DB UNIQUE로 동시 중복 차단, 감사 조회식 check-then-act 폐기 / send-sms URL=body 토큰 원문 재해시 검증 후 서버 조립(해시-온리 저장과 충돌 해소, 문자 발송은 발급 직후만)
- CEO 2-agent 리뷰(2026-08-11): HIGH 3건(T1 가짜 테스트 경로·URL 재구성 충돌·멱등 레이스)+MED 6건 플랜 반영 완료, 수용 리스크는 플랜 §4 기록
- 스펙 v3 사용자 결정 D1~D8 준수(풀스코프 v1, 도면 먼저 단계 배포)
