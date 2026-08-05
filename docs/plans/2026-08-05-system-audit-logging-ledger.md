# Progress Ledger — 시스템 전체 감사 로깅 (2026-08-05, `**D`)

스펙: `docs/specs/2026-08-05-system-audit-logging-design.md` (2차 개정판)
플랜: `docs/plans/2026-08-05-system-audit-logging-plan.md`
브랜치: `deploy` (푸시는 세션 커밋만, production 승격 금지 — 사용자 지시 대기)

| Task | 상태 | 검증 결과 |
|---|---|---|
| T1 프로덕션 로깅 부트스트랩 (+request_id, 구 T7 흡수) — 파일럿 | DONE | 커밋 `a37a5445`. 위임→검증→커밋 흐름 정상. 계약 12건 신설 포함 31 passed + APP_OK(메인 세션 직접 재실행). 타 세션 소유 파일(order_date_sync·push_sender) 무접촉·미스테이징 확인 |
| T2 PAYMENT_CHANGED before_flush SSOT | PENDING | |
| T3 ERP 생성 ORDER_CREATED 배선 | PENDING | |
| T-CP1 Phase 1 검증·커밋·푸시 | PENDING | |
| T4 첨부 soft delete + 이벤트 | PENDING | |
| T5 관리자 행위 구조화 + 접근거부 기록 | PENDING | |
| T6 access_logs 부활 (파일 접근 3곳) | PENDING | |
| T7 — **T1에 흡수(결번)** | — | 단순화 심판 판정 |
| T-CP2 Phase 2 검증·커밋·푸시 | PENDING | |
| T8 security_logs 구조화 | PENDING | |
| T9 감사 원장 수명주기 (retention + FK 분리) | PENDING | |
| T10 Sentry + gunicorn access log | PENDING | |
| T11 잔여 구멍 (user_deletion·FAILOPEN·EXTERNAL) | PENDING | |
| T-CP3 최종 검증·AI_STATUS 갱신 | PENDING | |

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

## 미해결 / 대기

- **스펙 승인 대기** — 승인 전 전 task 착수 금지.
- 승인 시 §8 결정 4건 확정 필요(전부 권장안 있음 — "권장대로" 한마디면 충분).
- T9 보존기간(security_logs 2년·나머지 1년 제안)은 T9 착수 전 사용자 확인.
