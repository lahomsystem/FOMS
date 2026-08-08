# Progress Ledger — 시스템 전체 감사 로깅 (2026-08-05, `**D`)

스펙: `docs/specs/2026-08-05-system-audit-logging-design.md` (2차 개정판)
플랜: `docs/plans/2026-08-05-system-audit-logging-plan.md`
브랜치: `deploy` (푸시는 세션 커밋만, production 승격 금지 — 사용자 지시 대기)

| Task | 상태 | 검증 결과 |
|---|---|---|
| T1 프로덕션 로깅 부트스트랩 (+request_id, 구 T7 흡수) — 파일럿 | DONE | 커밋 `a37a5445`. 위임→검증→커밋 흐름 정상. 계약 12건 신설 포함 31 passed + APP_OK(메인 세션 직접 재실행). 타 세션 소유 파일(order_date_sync·push_sender) 무접촉·미스테이징 확인 |
| T2 PAYMENT_CHANGED before_flush SSOT | DONE | 커밋 `16088409`. domains 23·PG 5·회귀 692·반증 2회. 빠른수정·레거시 폼·인라인 PATCH는 payment 미접촉 구조(전제 고정 테스트) — 상세 `docs/harness/runtime/OVERNIGHT_REPORT.md` |
| T3 ERP 생성 ORDER_CREATED 배선 | DONE | 커밋 `48e38dda`. 신규 10·domains 전수 3915 passed. as_orders 승격 경로 동시 커버 |
| T-CP1 Phase 1 검증·커밋·푸시 | DONE | smoke exit 0 + hygiene 15 passed. [08-06] 자기 몫 7커밋 cherry-pick push → origin/deploy `d7f0d9ea`, **CI 4/4 green**(FOMS·PG Lane·perf-gate·Harness). 스테이징 302/200·x-request-id 정상. 충돌은 state_writer 인벤토리 라인시프트만(원격 트리 재생성 40/24로 해소, 코드 의존 아님). Railway 로그 INFO 육안 1분만 잔여 |
| T4 첨부 soft delete + 이벤트 | DONE | 커밋 `3ec9bfd2`. 신규 35+PG 6+첨부 856+PG 전수 652. tombstone 404·outbox 2행·전역 필터·raw SQL 사각 2곳·복구 API. ⚠ 마이그레이션 `attach_life_00`은 타 세션 `account_self_00` 위 체이닝 |
| T5 관리자 행위 구조화 + 접근거부 기록 | DONE | 커밋 `9d02f0f5`. 신규 15+PG 7(독립 커밋 인과 증명)+연관 599. from→to·비번 값 부재·403/CSRF 독립 기록·dedupe |
| T6 access_logs 부활 (파일 접근 3곳) | DONE | 커밋 `ea8a1abc`. 신규 32+PG 8. FILE_VIEW 10분 dedupe·PRESIGNED·DOWNLOAD, 인덱스 `access_log_00` |
| T7 — **T1에 흡수(결번)** | — | 단순화 심판 판정 |
| T-CP2 Phase 2 검증·커밋·푸시 | DONE | smoke exit 0 + hygiene 15. [08-06 아침] push 완료 — 원격 최종 `156cb70c`, **CI 4/4 green**. CI red 2건 근본수정: ① PG DSN `str(URL)` 비번 마스킹(`***`) → render 원문 ② AccessLog 인덱스 모델↔마이그레이션 드리프트 → `__table_args__` 정합. `attach_life_00`은 origin `merge_acct_typedrift` 뒤 재부모화. **스테이징 E2E 13/13 PASS**(draft 생성→업로드→열람 302→삭제→목록 제외→404→복구→302, 주문 4399 CLAUDE-TEST) — 마이그레이션 2개 실적용 실증 |
| T8 security_logs 구조화 | DONE | 커밋 `7a8bf528`. 신규 26+PG 8, action/target/detail JSONB·log_access 확장·감사 화면 필터 |
| T9 감사 원장 수명주기 (retention + FK 분리) | DONE | 커밋 `bac253cc`. PG 18+체인 왕복, order_events FK 분리 3중 정합·purge_audit_logs·cron 체이닝 |
| T10 Sentry + gunicorn access log | DONE(사용자 액션 잔여) | 커밋 `7519a416`. no-op 실증(sentry_sdk 0 로드)·재귀 마스킹 워커·access-logfile. 잔여=DSN 발급·Railway env |
| T11 잔여 구멍 (user_deletion·FAILOPEN·EXTERNAL) | DONE(EXTERNAL 제외) | 커밋 `a9b8ecb7`. 사용자 비활성화 전환·FAILOPEN disposition 180 무성장. EXTERNAL 감축은 인벤토리 타 세션 점유로 별건 |
| T-CP3 최종 검증·AI_STATUS 갱신 | DONE(push 제외) | smoke exit 0 + hygiene 15 + verify_result success:true + AI_STATUS 갱신. push는 아침(마이그레이션 3종 체인 — origin head 재확인) |
| T11 병합 (타 세션 가입거절 가드와 충돌 해결) | DONE | 원격 `e4aea16b`. 차단 검사·notification 상태 정리는 hard delete 전용 유지, 비활성화는 미적용. delete 라우트 거부 계약은 reject_user 테스트로 이전. domains 4179 passed |
| T12 파일 열람 기록 화면 (access_logs 조회) | DONE | `GET /admin/file-access-logs` ADMIN 전용. KST 기간 경계·주문 접두 오탐 가드 계약 13건. domains 4193·PG 712 passed |

## 사용자 결정 (2026-08-05)

- 범위: **P0(3)·P1(4)·P2(4) 전 항목** 선택.
- 방식: **설계서 먼저, 승인 후 구현** — 승인 전 T1 착수 금지.
- 승인 시 확정할 결정 5건(스펙 §8): ① 금액 이벤트 단일 타입(권장) ② draft 별도 타입(권장)
  ③ 파일 view 기록 dedupe 창 10분(권장) ④ order_events FK drop+models 동기 수정(권장)
  ⑤ 사용자 삭제 → 비활성화+감사 actor 보존(권장).

## 설계 리뷰 (2026-08-05, 승인 전 완료)

- 사실 대조 18건: 17 정확, 1 수정 — **T2 금액 캡처 목록 교정**(출고가는
  `totals.shipping_price` 파생값이라 diff 금지, 배송비 전용 키 없음 —
  `payment.free_input` 텍스트, `Order.shipping_fee`는 flat 컬럼 별도 감지).
- 적대 리뷰 CRITICAL 2·MAJOR 6·MINOR 7 → 스펙·플랜 전부 반영:
  감사 쓰기 2모드(GET/abort 경로는 무커밋이라 전용 단명 세션), 마스킹 필터
  핸들러 부착(root 로거 부착은 전파 레코드에 무효), T2 before 출처=get_history+
  재할당 계약+부정 테스트, T4 전역 필터(`with_loader_criteria`), T6 chokepoint
  이동(presigned 라우트는 사문·실경로는 /view/ 302), T9 models 동기 수정+
  downgrade 고아 차단, T10 재귀 마스킹 워커, T2 draft 억제.
- 리뷰어 핵심 주장 4건(무커밋 teardown·totals 파생·shipping_fee flat·root 로거
  필터)은 코드 직독 재확인함(`db.py:99`·`structured_form_projection.py:160`·
  `models.py:69`·`error_logging.py:96`).

## `**D` 최종 점검 (2026-08-05, CEO 리뷰 + 3-agent 교차검수)

- CEO 리뷰(HOLD SCOPE — 범위는 사용자 기결정이라 재협상 없이 엄격 검증):
  파일럿 T1은 two-way door(되돌리기 쉬움)로 적격, one-way door는 T9 FK drop·
  T11 삭제 의미 변경뿐(결정 ④⑤로 기승인, Phase 3 스테이징 선행). 승인.
- 3-agent 교차검수(반증·단순화·사실검증) 주요 반영 — 상세 스펙 §9:
  - **[실증] flag_modified가 history old 파괴**(SQLAlchemy 2.0.23 로컬 재현:
    재할당만=old 잔존, flag 후=deleted=()) → T2 before = DB 배치 SELECT로 전면 교체.
  - **[확정] 풀 5+5·timeout 10s**(db.py:52-55) → 독립 모드는 전용 소형 감사 engine.
  - shipping_fee는 이미 SHIPPING_FEE_CHANGED 이벤트 있음(storage.py:292-296) → 캡처 제외.
  - Alembic 체인은 빈 DB 실행 불가(tests/postgres/conftest.py:9-13) → T9 편입 삭제.
  - 첨부 raw SQL 2곳·canonical 분기 tombstone 사각 → T4 편입.
  - 동시 세션(출고 알림 잔여 T6)이 order_date_sync.py 수정 예정 → T2 무접촉 복제,
    금지 파일 목록 플랜 명시.
  - 구 T7은 T1에 흡수(결번).
- 본진 진입 방식: 파일럿 T1 통과 후 `/overnight` 명령 제시(자동 진입 금지).

## 조사 확정 사실 (2026-08-05 deep research — 재조사 금지)

- 프로덕션 gunicorn 경로에 로깅 설정 0건 — root=WARNING, INFO 전량 드롭.
  `dashboard_cache.py:24` 국소 우회가 문제를 문서화.
- payment 블록 diff 코드 부재(`_record_structured_events`는 3종만). 실사고: 주문 4414
  할인 11,060원 소실(`2026-07-31-full-promotion-prep-ledger.md:385`).
- ERP draft 생성·승격은 `create_order()` 미경유 — 생성 이력 0. add_order.html이 고정.
- 첨부 삭제는 hard delete + R2 즉시삭제, `ATTACHMENT_*` 라벨은 emit 0.
  정답 패턴 = `blueprint_projection.py`(이벤트+outbox).
- `access_logs` writer 0건 사문. `log_access()`는 SecurityLog에 쓰고 additional_data 버림.
- `order_events`: FK CASCADE로 purge 시 동반 소멸, Alembic 미편입, 단독 인덱스 3개.
- retention 없는 테이블: security_logs·order_events·notification_events·channel_delivery_logs.
- `user_deletion.py:29-40`이 감사 actor 일괄 NULL.
- FAILOPEN `LOG_AND_CONTINUE`+`has_logging=False` 179건 게이트 green 통과 중.
- mutation writer EXTERNAL 22곳 baseline 핀.
- 복제 패턴: `order_date_sync.py` before_flush SSOT(origin 기억·복귀 취소·재진입 가드).

## 미해결 / 대기 (2026-08-07 갱신)

- **T1~T11 전 task DONE.** 스펙 §8 결정 5건 전부 권장안으로 확정·구현 완료.
- **push 대기**: P3 커밋 4개(`7a8bf528`·`bac253cc`·`7519a416`·`a9b8ecb7`) + 문서.
  마이그레이션 3종 체인(`seclog_struct_00`→`auditlife_00`) — push 전 origin head 재확인.
- **사용자 액션 잔여**: Sentry 프로젝트·DSN 발급·Railway `SENTRY_DSN` env 등록·실수신 확인.
- **운영 주의**: purge cron은 `--apply` 체이닝(dry-run 아님). 첫 실행 전 보존기간
  730/365일 확정 여부 확인.
- **별건 이월**: EXTERNAL mutation writer 22곳 감축(인벤토리 타 세션 점유로 이번 런 생략).
