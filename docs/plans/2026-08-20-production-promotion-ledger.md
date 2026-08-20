# 운영 승격 준비 원장 (2026-08-20) — deploy → production

브랜치: `promote/2026-08-20-full` (base `origin/production` `67ecaff3`, merge `origin/deploy`)
worktree: `c:/tmp/foms-p0820` · **푸시·머지 안 함**(사용자 결정 대기)

## 왜 PR #113 을 그대로 쓰면 안 되는가

PR #113 head(`533265ec`, 08-18)는 현재 deploy 보다 **79커밋 낙후**이며 다음이 빠져 있다:

| 커밋 | 내용 |
|---|---|
| `ec6b22a9` | 폼 저장이 `parties` 하위 키를 지우던 회귀 수정 |
| `dd148b1f` | 유실 연락처 복구 스크립트 |
| `0687d222`·`872a670e` | ORDERER-AXIS-01 발주사/주문자 축 분리 |

그대로 머지하면 운영에서 ① 수집 연락처가 저장 때마다 사라지고 ② 발주사 칸의 개인 이름
때문에 알림톡이 하우드 프로필로 실발송된다. 두 문제 모두 이번 주에 스테이징에서 실측된
것이다.

## 운영 DB 실측 (2026-08-20, 읽기 전용 1회)

```
alembic_version        = assort_00
external_order_links   = 없음      (네이버 수집 미적용)
order_change_reasons   = 없음      (ORDER-REASON-00 미적용)
orders.as_axis_status  = 없음      (AS-AXIS-01 미적용)
order_attachments.sort_order / as_log_id = 있음
```

## 마이그레이션 체인 재배열 (이 승격의 핵심)

deploy 체인은 `asfresh_00 → naver_link_00 → orderreason_00 → naver_triage_00 →
navercollect_00 → naverdock_00 → asaxis_00 → assort_00 → naver_relation_00` 이다.
그런데 운영은 `asfresh_00` 다음에 **곧바로 `assort_00`**(PR #119 승격)을 실행했다.

alembic 은 현재 리비전보다 **아래를 검증하지 않는다**. 그래서 deploy 체인 그대로
`upgrade head` 를 돌리면 사이에 낀 6개는 조상으로 간주돼 **영구히 건너뛰고**,
`naver_relation_00` 이 없는 테이블을 ALTER 하다 **배포가 실패**한다.

승격 트리에서 실행 순서를 운영 실제 상태에 맞춰 다시 세웠다:

```
asfresh_00 → assort_00 → naver_link_00 → orderreason_00 → naver_triage_00
           → navercollect_00 → naverdock_00 → asaxis_00 → naver_relation_00(head)
```

바꾼 파일 3개:
- `assort_00_attachment_sort_order.py` — 운영이 실제로 실행한 부모(`asfresh_00`) 유지
- `naver_link_00_external_order_links.py` — 부모 `asfresh_00` → `assort_00`
- `naver_relation_00_link_relation_and_place_status.py` — 부모 `assort_00` → `asaxis_00`

**이 재배열은 승격 브랜치에만 있다**(deploy 체인은 그대로). 08-18 승격 트리도 같은 이유로
재배열했지만, 그 뒤 `assort_00` 이 먼저 운영에 올라가며 무효가 됐다 — 다음 승격에서도
운영 head 를 먼저 읽고 다시 판단해야 한다.

## 나머지 충돌 5건

| 파일 | 처리 |
|---|---|
| `erp_order_js.html` · `layout_scripts.html` | 양쪽 보존(deploy 의 `order-change-reason.js`·`order-delete-reason.js` 태그 추가) |
| `test_erp_mobile_order_display.py` | 양쪽 보존(오늘 추가한 buyer 테스트 2건 포함) |
| 인벤토리·매니페스트 4종 | deploy 판 채택 후 승격 트리에서 재생성(failopen·audit_coverage·mutation writer·state writer) |

## 검증 (승격 트리에서 실행)

- `alembic stamp assort_00` 로 **운영 상태를 로컬 PG(5440)에 재현** → `upgrade head` →
  7개 리비전이 순서대로 실행되고 `external_order_links`·`order_change_reasons`·
  `orders.as_axis_status`·`external_order_links.relation/place_order_status/triage_state`
  전부 생성 확인. 최종 head `naver_relation_00`.
- `tests/postgres/test_migration_chain.py` (MIGCHAIN-01 왕복) **1 passed**
- 게이트 6종(single head·write guard·rev_99·state guard·failopen·audit coverage) **68 passed**
- 축 분리·수집 통합 테스트 **319 passed**
- `pre_push_smoke.ps1` exit 0 (323) · `APP_OK`

## 남은 절차 (사용자 몫)

1. 이 브랜치 push → PR(base `production`) 생성 또는 PR #113 을 이 브랜치로 교체
2. CI 전 워크플로 green 확인(`gh run list` 전수 — `ci_watch` 는 1개만 본다)
3. 머지 = 운영 predeploy 에서 `alembic upgrade head` 실행
4. 승격 후 확인: 운영에서 `restore_naver_lost_contacts.py --dry-run` ·
   `split_orderer_buyer_axis.py --dry-run` 둘 다 **0건**이어야 정상(수집 이력이 없으므로)
