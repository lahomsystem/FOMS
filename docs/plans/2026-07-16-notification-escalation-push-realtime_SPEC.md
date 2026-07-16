# Escalation → Push/Realtime 설계 갭 Spec
> 작성일: 2026-07-16 | 상태: 🟢 승인됨 · 구현 완료 (D1=α, D2=urgent payload true, D3=수신자별 enqueue)
> 근거: 알림 프로세스 분석(세션) §8.1 — `URGENT_ESCALATION` 생성 후 push/socket 미연결

## 0. 갭 요약 (현재)

| 단계 | DB fanout | badge invalidate | Socket.IO emit | Web Push enqueue |
|------|-----------|------------------|----------------|------------------|
| `URGENT_MENTION` 등 P0 생성 | ✅ | ✅ | ✅ | ✅ |
| Stage1/2 `escalate_overdue_urgent` | ✅ (`fan_out`만) | ❌ | ❌ | ❌ |

결과: 상급자(MANAGER/ADMIN) inbox에 row는 생기지만, **앱이 열려 있어도 실시간 toast/배지 즉시 갱신 없음**, **앱이 닫혀 있으면 OS banner 없음**. 배지 폴(클라 60s)·수동 새로고침에만 의존. P0 에스컬레이션 목적과 불일치.

관련 인시던트 패턴: `docs/context/INCIDENT_URGENT_NOTIFICATION_NOT_DELIVERED_2026-03-04.md` (realtime 미도달 = DB만 남는 동일 실패모드).

---

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물

`escalate_overdue_urgent`가 Stage1/Stage2에서 생성한 **각** `URGENT_ESCALATION` 알림에 대해, 기존 멘션/공지와 동일한 커밋-후 배달 계약이 성립한다:

1. 수신자 배지 캐시 invalidate
2. Socket.IO `erp_notification` → room `user_{id}`
3. Web Push enqueue (severity 게이트 통과) → RQ → pywebpush → SW banner

상급자 기기/탭이 열려 있으면 **즉시** 인지, 닫혀 있고 구독이 있으면 **OS 배너**.

### 1.2 기능 요구사항

1. **Commit 경계**: escalation CLI/worker가 `db.commit()` 한 **뒤**에만 push enqueue + emit 실행 (기존 send/mention과 동일 — worker가 커밋된 row 재조회).
2. **수신자 집합**: Stage1/2에서 `_create_escalation_notification`으로 만든 알림들의 `target_user_id`(또는 fanout으로 생긴 state의 user_id)만 대상. 원본 긴급 수신자에게 재발송 금지.
3. **Realtime payload**: generic 가능. 최소 `{ kind, title, urgent:false|true, notification_type:'URGENT_ESCALATION', order_id, notification_id }`. 고객명·사유 민감정보 금지(push와 동일 정책).
4. **Push 게이트**: 현재 `_should_push`는 `is_urgent` 또는 P1 타입만. Escalation row는 **의도적으로 `is_urgent=False`**(재에스컬레이션 루프 방지). 따라서 다음 중 **하나**를 선택해 Spec에 고정:
   - **Option α (권장)**: `URGENT_ESCALATION`을 P1 기본 집합(`_DEFAULT_P1_TYPES`)에 추가. `is_urgent`는 False 유지.
   - **Option β**: escalation 전용 `enqueue` 경로에서 severity 우회 플래그. (특수 경로 → 비권장)
5. **Badge**: `invalidate_badge_cache_for_user_ids(escalation_recipient_ids)` 호출.
6. **Audit**: 기존 `PUSH_*` / `REALTIME_ATTEMPTED` 이벤트 패턴을 escalation 생성 알림에도 적용(emit 직후 기록은 mention과 동일 수준이면 충분).
7. **Idempotent**: 스윕 재실행이 새 escalation 알림을 안 만들면 push도 안 나감(이미 `escalated_at` / `operator_escalated` 가드로 보장). 같은 notif_id 재enqueue는 push_sender 기존 동작에 위임.
8. **Flag off**: `FOMS_WEB_PUSH_ENABLED` off면 push skip(기존). realtime/badge는 flag와 무관하게 동작.

### 1.3 예외/제약

- Escalation 알림 자체에 `is_urgent=True` 부여 **금지** (Stage 루프 재진입).
- deep_link: `order_id` 있으면 `/erp/orders/{id}` 또는 기존 `_deep_link` 규칙. 없으면 `/erp`.
- Queue unavailable 시 기존처럼 `queue_unavailable` 이벤트 + state 표시. 스윕 실패로 전체 롤백하지 않음(commit 이후 best-effort).
- 마이그레이션 불필요.
- production 직접 push 금지 — deploy 스테이징 검증 후 사용자 승인 시에만 승격.

---

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일

| 파일 | 변경 |
|------|------|
| `foms/services/notifications/escalation.py` | `_create_escalation_notification`이 생성 notif id(+ recipient uid)를 반환·수집. `escalate_overdue_urgent` 반환값에 `created_notification_ids` / `recipient_user_ids` 추가 **또는** finalize 헬퍼 분리 |
| `foms/services/notifications/escalation.py` (또는 신규 `escalation_delivery.py`) | `finalize_escalation_delivery(db, created_ids)` — badge invalidate + emit + enqueue. **commit 호출은 하지 않음** |
| `scripts/maintenance/run_notification_escalation.py` | 스윕 → commit → `finalize_escalation_delivery` 순서 고정 |
| `foms/services/jobs/tasks.py` | `run_notification_escalation_task`도 동일 commit→finalize |
| `foms/services/notifications/push_sender.py` | Option α: `_DEFAULT_P1_TYPES`에 `URGENT_ESCALATION` 추가. `_generic_title`에 "에스컬레이션" 문구 |
| `tests/domains/test_push_sender.py` | P1에 escalation 포함 시 push 시도 검증 |
| `tests/domains/test_push_sender.py` / escalation 테스트 | finalize 호출·emit mock·enqueue mock |

### 2.2 아키텍처 방향

기존 패턴 준수 — `finalize_drawing_order_change_alert` / `api_order_urgent_mention`의 **commit 후 배달**과 동일:

```
escalate_overdue_urgent(db)  # flush only, collect ids
db.commit()                  # CLI/RQ wrapper
finalize_escalation_delivery(created_ids, recipient_ids)
  → invalidate_badge
  → emit_erp_notification_to_users
  → enqueue_push_for_notification(each id)
```

참고: `foms/services/notifications/drawing_order_change.py` `finalize_drawing_order_change_alert`.

### 2.3 의존성 및 영향 범위

- RQ worker + escalation loop 이미 운영 배선(AI_STATUS 2026-07-04). finalize만 추가.
- Socket.IO / REDIS_URL 다중 워커 전제(인시던트 2026-03-04).
- DB 마이그레이션 없음.
- 알림 볼륨: 미ack P0 × (매니저 수 + admin 수). 기존 스윕 주기(예: 60s)와 동일.

### 2.4 결정 포인트 (승인 시 확정)

| ID | 질문 | 권장 |
|----|------|------|
| D1 | Push 게이트 Option α vs β | **α** (`URGENT_ESCALATION` ∈ P1) |
| D2 | realtime `urgent` 필드 | `true` 권장(클라 강조음/오버레이) — DB `is_urgent`와 분리 가능 |
| D3 | Stage2 ADMIN 다수일 때 N회 push | 수신자별 1알림 1enqueue 유지(현재 모델) |

---

## 3. Steps — 실행 단계

- [x] Step 1: D1–D3 사용자 승인 (순차 진행 선택 + 권장값)
- [x] Step 2: `escalate_overdue_urgent`가 생성 notif id·recipient 수집
- [x] Step 3: `finalize_escalation_delivery` 구현 + CLI/RQ commit 후 호출
- [x] Step 4: `_DEFAULT_P1_TYPES` + generic title (Option α)
- [x] Step 5: 단위 테스트(mock emit/enqueue) + 기존 escalation idempotent 회귀
- [ ] Step 6: 스테이징 — 미ack 긴급 멘션 시드 → N분 대기(또는 분 단위 env) → 매니저 기기 push/realtime 확인
- [ ] Step 7: `pre_push_smoke` → deploy push → CI green

---

## 4. 검증 기준

- [ ] `python -c "import app; print('APP_OK')"`
- [ ] pytest: escalation + push_sender 관련 도메인 테스트 green
- [ ] 스테이징: Stage1 후 매니저 (a) 열린 탭 badge/toast (b) 구독 기기 OS banner
- [ ] Stage1 알림 `is_urgent=False` 유지 → 재스윕이 그 알림을 다시 escalate 대상으로 삼지 않음
- [ ] `FOMS_WEB_PUSH_ENABLED=0` 시 realtime/badge만 동작, push skip
- [ ] perf guard / pre_push_smoke exit 0

---

## 5. 참고 자료

- 코드: `foms/services/notifications/escalation.py`
- 배달 참고: `drawing_order_change.finalize_drawing_order_change_alert`, `api_order_urgent_mention`
- 인시던트: `docs/context/INCIDENT_URGENT_NOTIFICATION_NOT_DELIVERED_2026-03-04.md`
- 운영: `docs/AI_STATUS.md` Phase 0A–3C / escalation worker
- 형제: `docs/plans/2026-07-16-notification-center-unify-refactor-scope.md`, `docs/plans/2026-07-16-notification-e2e-sequences.md`
