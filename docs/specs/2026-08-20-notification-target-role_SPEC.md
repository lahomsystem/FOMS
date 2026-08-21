# NOTIF-ROLE-01: 역할 대상 알림(`target_role`) — 관리자 팬아웃 SSOT 복원

> 2026-08-20 작성. 상태: **구현 완료 · deploy 반영** (사용자 승인 후 멀티에이전트 실행, 총감독 재검증)
> 실측: ROLE 원본 1건 → 관리자 1인당 에스컬레이션 1건(3). 전환 전 형태(관리자마다 원본)는 같은 조건에서 9건 — N² → N 확인.
> 선행: `docs/plans/2026-07-16-notification-escalation-push-realtime_SPEC.md`(Phase 3C 에스컬레이션)

## 1. 문제

관리자 전원에게 같은 내용을 보내야 하는 알림이 **수신자 수만큼 별개 `Notification` row** 로 만들어진다.
알림 SSOT 는 "공유 `Notification` 1건 + 수신자별 `notification_user_states`" 인데, 이 두 곳이 규약을 벗어난다.

| 위치 | 현재 | 배포 상태 |
|---|---|---|
| `foms/services/integrations/naver_commerce/claim_watch.py:128-140` | 클레임 1건마다 `for user_id in targets:` → 관리자 수만큼 `Notification` 생성 | deploy 전용 |
| `foms/services/security/account_requests.py:59-69` | 가입/재설정 요청 1건마다 `for admin in admins:` → 관리자 수만큼 `Notification` 생성 | **운영 반영됨** |

### 실측 피해 (스테이징, 2026-08-20)

- `NAVER_ORDER_CLAIMED` 148건 → `URGENT_ESCALATION` **1073건**.
- 증식 경로: 원본이 관리자 수(N)만큼 쪼개짐 × 에스컬레이션이 state 마다 상급자 N명에게 발송 = **N²**.
- 1차 완화(배포 완료): 에스컬레이션 원본당 1건 중복 억제(`67ecaff3`) + 브로드캐스트 유형 제외(`240c25ae`).
  → 증식은 멈췄지만 **원본이 쪼개지는 구조 자체는 그대로**다. 이 스펙이 그 뿌리를 없앤다.

### 쪼개짐이 남기는 실제 비용

1. 같은 사건의 읽음/보관/확인이 row 별로 흩어져 "이 사건을 누가 확인했나"를 한 번에 못 본다.
2. 감사 이벤트(`notification_events`)가 사건 단위가 아니라 사본 단위로 흩어진다.
3. 관리자 1명 늘 때마다 알림 row 가 사건 수만큼 늘어난다(선형이 아니라 곱).
4. 에스컬레이션·집계·배지 등 후속 기능이 전부 이 곱셈을 물려받는다.

## 2. 목표 / 비목표

**목표**
- `Notification` 1건이 "역할(role) 전체"에 도달하는 정식 경로를 만든다.
- 위 두 호출부를 그 경로로 전환한다. 사건 1건 = row 1건.
- 읽기 경로(목록·배지·상세)는 **무변경**으로 유지한다.

**비목표**
- 기존 데이터 마이그레이션(과거에 쪼개져 만들어진 row 병합) — 하지 않는다. 신규만 새 경로.
- 알림 UI 변경, 긴급/푸시 정책 변경.
- 에스컬레이션 제외 목록 재조정(별건).

## 3. 설계

### 3.1 스키마 (1 컬럼 추가)

```
notifications.target_role  VARCHAR(20) NULL, index
```

- `target_type = 'ROLE'`, `target_role = 'ADMIN'` 형태로 사용.
- 기존 4경로(`USER`/`ALL`/`TEAM`/`MANAGER_NAME`)와 동급의 5번째 수신 경로.
- NULL = 레거시·비역할 알림(기존 동작 그대로).

마이그레이션: `notifrole_00_notification_target_role.py`, `down_revision = "assort_00"`(현재 단일 head).
`downgrade()` 는 index → column 순 drop. **마이그레이션 상수 동결 원칙**대로 `models` 를 import 하지 않고 리터럴 고정.

### 3.2 수신자 해석 (`foms/services/notifications/recipients.py`)

`resolve_recipients_for_notification` 에 경로 1개 추가:

```python
role = (notification.target_role or '').strip().upper()
if role:
    rows = db.query(User.id).filter(
        func.upper(User.role) == role, User.is_active == True
    ).yield_per(500)
    for (uid,) in rows:
        source_by_user[int(uid)] = NotificationRecipientSource.TARGET_ROLE
```

`models.NotificationRecipientSource` 에 `TARGET_ROLE = 'target_role'` 상수 추가.
우선순위(`_SOURCE_ORDER`)는 넓은 것 → 좁은 것 순으로 `TARGET_ALL < TARGET_ROLE < TARGET_TEAM < TARGET_MANAGER_NAME < TARGET_USER`.
(역할은 팀보다 넓다. 같은 사용자가 두 경로에 걸리면 더 좁은 쪽을 기록.)

### 3.3 읽기 경로 무변경 근거

- 목록: `api_notifications_list` 는 `notification_user_states` 조인만 본다(`foms/api/notifications/__init__.py:294-308`).
- 배지: 같은 states 기준 카운트.
- 즉 **state 가 생기면 그걸로 끝**이다. 새 target 종류를 읽기 쿼리가 알 필요가 없다.

### 3.4 호출부 전환

**claim_watch.`_notify`**
- 담당자가 있으면: 지금처럼 `target_type='USER'` 1건.
- 담당자가 없어 ADMIN 폴백이면: `target_type='ROLE'`, `target_role='ADMIN'` **1건** + `fan_out_new_notification`.
- 반환값(만든 알림 건수)의 의미가 "알림 row 수"에서 달라지므로, 호출부 로그·카운터는 **state 수**를 쓰도록 맞춘다.

**account_requests.`_notify_admins`**
- 루프 제거, `target_type='ROLE'`, `target_role='ADMIN'` 1건 + fan_out. 반환값은 생성된 state 수.

### 3.5 에스컬레이션과의 관계

- 원본이 1건이 되면 이미 배포된 원본당 1건 억제(`_fresh_targets`)와 맞물려 **사건 1건 → 관리자 1인당 최대 1건**이 된다.
- `NAVER_ORDER_CLAIMED` 는 여전히 제외 목록에 있으므로 에스컬레이션 자체가 안 걸린다. 제외를 나중에 풀어도 폭주하지 않는 상태가 이 스펙의 결과다.

## 4. 테스트 계약 (완료 기준)

| # | 대상 | 검증 |
|---|---|---|
| T1 | `resolve_recipients_for_notification` | `target_type='ROLE', target_role='ADMIN'` → 활성 ADMIN 전원, source=`target_role`, 비활성 제외 |
| T2 | 우선순위 | ADMIN이면서 `target_user_id` 지정 → source 는 `target_user` |
| T3 | `fan_out_new_notification` | ROLE 알림 1건 → state N개 + `created` 이벤트 N건, 재호출 idempotent |
| T4 | `claim_watch._notify` | 담당자 없음 → `Notification` **1건**·state N개 (현재는 N건) |
| T5 | `account_requests._notify_admins` | 가입 요청 1건 → `Notification` 1건·state N개 |
| T6 | 읽기 경로 | ROLE 알림이 각 관리자 목록/배지에 1건씩 보인다(API 응답 기준) |
| T7 | 에스컬레이션 | 제외 해제(env) 상태에서 ROLE 원본 1건 → 관리자 1인당 에스컬레이션 1건 |
| T8 | 마이그레이션 | baseline `create_all` + `stamp` + `upgrade head` + `downgrade` 왕복(PG 레인) |
| T9 | 모델/마이그레이션 정합 | `models.py` 와 스키마 일치(pg-lane `test_startup_schema`) |

추가 게이트: `pre_push_smoke` exit 0, `APP_OK`, FOMS CI·PG Lane·Harness·perf-gate green.

## 5. 작업 순서 (task 단위 · 각 단계 검증 후 다음)

1. **T-A** 모델 상수 + 컬럼 정의(`models.py`) — `APP_OK`
2. **T-B** 마이그레이션 리비전 + 왕복 검증(로컬 PG 5440 레인) — T8
3. **T-C** `recipients.py` ROLE 경로 + 단위 테스트 — T1·T2·T3
4. **T-D** `account_requests` 전환(운영 반영 코드라 먼저) — T5·T6
5. **T-E** `claim_watch` 전환(deploy 전용) — T4
6. **T-F** 에스컬레이션 상호작용 테스트 + 문서 갱신 — T7, AI_CHANGELOG/AI_STATUS
7. **T-G** deploy push → CI 전 워크플로 green → 운영 승격 PR(마이그레이션 동반)

## 6. 롤아웃·롤백

- 마이그레이션은 `predeploy.sh` 의 `alembic upgrade head` 로 배포 전에 1회 실행된다(다중 replica 는 advisory lock 직렬화).
- 승격 시 **마이그레이션 파일과 모델 정의를 같이** 옮긴다(둘 중 하나만 가면 pg-lane 왕복 red).
- 롤백: 컬럼은 nullable·index 뿐이라 코드만 되돌려도 무해(NULL 이면 기존 4경로로만 동작). 스키마 되돌림이 필요하면 `downgrade` 1스텝.

## 7. 리스크

| 리스크 | 대응 |
|---|---|
| `claim_watch` 는 타 세션(네이버 수집)이 활발히 편집 중 | T-E 는 마지막 task, 착수 직전 `origin/deploy` 재확인 후 최소 diff. 충돌 시 사용자 확인 |
| 반환값 의미 변경(알림 수 → state 수)이 호출부 로그/테스트 파손 | T4·T5 에서 호출부 계약 테스트로 고정 |
| ROLE 팬아웃이 의도보다 넓게 퍼짐(예: 향후 VIEWER 역할에 사용) | 이번 범위는 `ADMIN` 만. 다른 역할 사용은 별도 승인 |
| 과거에 쪼개진 row 는 그대로 남음 | 의도된 비목표. 신규만 정상화, 과거분은 보관 처리로 정리(2026-08-20 완료) |

## 8. 승인 필요 항목

1. `notifications.target_role` 컬럼 신설(스키마 변경) 승인
2. 운영 반영 코드(`account_requests`) 동작 변경 승인 — 관리자 알림이 사건당 1건으로 바뀐다(각자 받는 건수는 동일)
3. 작업 순서 T-A~T-G 로 이 세션에서 완주할지, 별도 세션(`**B`/`**C`)으로 돌릴지
