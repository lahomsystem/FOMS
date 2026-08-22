# 운영 승격 준비 원장 (2026-08-21) — deploy → production

브랜치: `promote/2026-08-21-full` (base `origin/production` `463cc472`, merge `origin/deploy`)
worktree: `c:/tmp/foms-p0821`
선행: PR #113(08-18) → PR #121(08-20) → 본 브랜치. **둘 다 같은 이유로 낡았다** — 아래 참조.

## 승격 PR 이 이틀 연속 무효가 된 이유

체인 재배열은 "운영이 실제로 어디까지 실행했는가"에 100% 의존한다. 그 값이 바뀌면 부모 지정을
다시 계산해야 한다.

| 시점 | 운영 alembic head | 무효가 된 계기 |
|---|---|---|
| 08-18 (PR #113) | `asfresh_00` | PR #119 로 `assort_00` 이 먼저 승격 |
| 08-20 (PR #121) | `assort_00` | 다른 세션이 `notifrole_00` 을 먼저 승격 |
| 08-21 (본 브랜치) | `notifrole_00` | — |

**교훈**: 승격 브랜치를 만들었으면 그날 안에 머지하거나, 머지 직전에 운영 head 를 다시 읽는다.

## 운영 DB 실측 (2026-08-21, 읽기 전용)

```
alembic_version              = notifrole_00
external_order_links         = NO
order_change_reasons         = NO
orders.as_axis_status        = NO
notifications.target_role    = YES
order_attachments.sort_order = YES
```

운영판 `notifrole_00` 부모 = `assort_00` (deploy 판은 `naver_relation_00`).

## 체인 재배열

미적용 리비전을 운영 head(`notifrole_00`) 위로 직렬화했다:

```
asfresh_00 → assort_00 → notifrole_00 → naver_link_00 → orderreason_00
           → naver_triage_00 → navercollect_00 → naverdock_00 → asaxis_00
           → naver_relation_00 → navergroup_00 → naverfail_00(head)
```

바꾼 파일:
- `assort_00`·`notifrole_00` — **운영 판 유지**(실제 실행 순서)
- `naver_link_00` — 부모 `asfresh_00` → `notifrole_00`
- `naver_relation_00` — 부모 `assort_00` → `asaxis_00`
- `navergroup_00` — 부모 `notifrole_00` → `naver_relation_00`

`navergroup_00`/`naverfail_00` 은 08-20 이후 deploy 에 새로 들어온 네이버 리비전이다. 처음에
빠뜨려 head 2개(분기)가 났고 `alembic heads` 로 잡았다 — **재배열 후 `alembic heads` 단일 확인은
생략 금지**.

## 충돌 22건 처리

| 분류 | 파일 | 처리 |
|---|---|---|
| 마이그레이션 | `assort_00`·`notifrole_00` | 운영 판 채택(실행 순서 정본) |
| 코드 | `foms/api/files/{common,direct_upload,order_routes}.py` | deploy 판(AS-BIND-01 `bind_as_log_id_for_upload` 가 운영판 `resolve_as_log_ref` 의 상위) |
| 화면 | `as_dashboard_body.html`·`as-dashboard.js`·`foms-as-attachment-order.css` | deploy 판 |
| 템플릿 | `erp_order_js.html`·`layout_scripts.html` | 양쪽 보존(script 태그 합집합) |
| 테스트 | `test_erp_mobile_order_display.py` | 양쪽 보존 / 나머지 2종 deploy 판 |
| 문서·인벤토리 | `AI_STATUS`·`AI_CHANGELOG`·원장 1·인벤토리 6종 | deploy 판 채택 후 승격 트리에서 재생성 |

## 검증

- **운영 상태 재현**(create_all → 수집·사유·as_axis 제거 → `stamp notifrole_00`) 후 `upgrade head`
  → 9개 리비전 순차 실행. 최종 head `naverfail_00`.
  생성 확인: `external_order_links`·`order_change_reasons` 테이블,
  `orders.as_axis_status`·`external_order_links.relation/group_key/triage_state` 컬럼.
- `alembic heads` **단일**(`naverfail_00`)
- MIGCHAIN-01 왕복 1 passed
- 게이트 6종 68 passed · `pre_push_smoke.ps1` exit 0(18 targets) · `APP_OK`
- 전체 스위트(`tests/domains`+`services`+`contracts`) — 실행 결과는 커밋 메시지 참조

## 머지 후 확인 (운영)

1. `/healthz` commit 이 승격 SHA 인지
2. `alembic_version = naverfail_00`
3. `restore_naver_lost_contacts.py --dry-run` · `split_orderer_buyer_axis.py --dry-run` 둘 다 0건
   (운영엔 수집 이력이 없다)
