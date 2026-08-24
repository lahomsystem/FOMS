# 네이버 기능 운영 승격 — 차단 사유 실측 (2026-08-24)

deploy `b085569d` 기준. 운영 DB·Railway env·alembic 그래프를 **실측**했다(운영 DB 는
`set_session(readonly=True)` 읽기 전용). 결론: **지금 승격하면 전 시스템이 죽는다.**

승격은 커밋 cherry-pick 문제가 아니라 **alembic 계보 재설계 문제**다.

## 실측값

| 항목 | 값 |
|---|---|
| `origin/production` | `d5b44d87` |
| `origin/deploy` | `b085569d` |
| 미승격 커밋 | **440** |
| 운영 `alembic_version` | **`merge_prod_drawq`** |
| 운영에 없는 테이블 | `external_order_links` · `order_change_reasons` |
| 운영에 없는 컬럼 | **`orders.as_axis_status`** |
| `requirements.txt` 차이 | **없음**(solapi 류 의존 드리프트 아님) |

## 치명 1 — `orders.as_axis_status` 없음 = 전 시스템 500

`as_axis_status` 는 `orders` 테이블 컬럼이다. SQLAlchemy 는 `Order` 를 조회할 때마다 이
컬럼을 `SELECT` 절에 넣는다. 없으면 `UndefinedColumn: column orders.as_axis_status does not
exist` — **주문을 읽는 모든 화면이 500**(대시보드·목록·상세·검색).

나머지 둘은 자기 기능만 죽인다(네이버 화면 / 저장 사유). **이것 하나만 전 시스템이다.**

→ 마이그레이션이 코드보다 **먼저, 반드시 성공해야 한다.** 그런데 —

## 치명 2 — 마이그레이션이 실행 자체가 안 된다

운영 DB 는 `merge_prod_drawq` 에 stamp 돼 있는데, 그 리비전 파일
(`migrations/versions/merge_prod_drawqueue_notifrole.py`)은 **deploy 에서 삭제됐다**.

```
alembic upgrade head
→ Can't locate revision identified by 'merge_prod_drawq'
```

시작점을 못 찾으니 한 줄도 안 돈다. 치명 1이 그대로 현실이 된다.

부팅 시 자동 마이그레이션은 **없다**(`Procfile` 은 gunicorn 만) — 그래서 "부팅 파산"은
아니지만, 코드만 살아 있고 스키마는 옛것인 **최악의 조합**이 된다.

## 치명 3 — 같은 revision id 가 두 계보를 갖는다

deploy 가 **이미 적용된 리비전의 부모를 바꿔치기** 했다:

| revision | 운영이 실제 적용한 부모 | deploy 파일의 부모 |
|---|---|---|
| `assort_00` | `asfresh_00` | **`asaxis_00`** |
| `notifrole_00` | `assort_00` | **`naver_relation_00`** |

운영은 옛 부모로 이미 실행을 끝냈다. deploy 파일을 얹으면 alembic 이 보는 조상과 DB 가
실제로 지나온 길이 갈리고, `downgrade` 도 신뢰할 수 없어진다.

deploy 그래프 head 는 `merge_drawq_naverfail`(부모 `drawqueue_00`+`naverfail_00`) 하나다.

## PR #133 은 쓸 수 없다 (또 낡았다)

`promote/2026-08-21-full` (OPEN, MERGEABLE) 은 체인을 `notifrole_00` 위로 재직렬화했다.

1. 운영 head 는 이제 `notifrole_00` 이 아니라 **`merge_prod_drawq`** 다. 머지하면
   `notifrole_00` 에 자식이 둘(`merge_prod_drawq`, `naver_link_00`) 생겨 **head 2개** —
   `upgrade head` 가 "Multiple head revisions" 로 거절한다.
2. #133 의 `naver_link_00.down_revision = notifrole_00` 인데 **deploy 는 `asfresh_00`** 이다.
   #133 을 먼저 머지하면 운영이 deploy 와도 다른 **제3의 계보**가 된다.
3. 3일 낡았다 — v3 워크벤치·관계 축·직접취소·폴링이 전부 빠져 있다.

원장에 기록된 `#113`·`#121` 연속 무효와 **같은 패턴**이다(승격 체인 전제는 하루면 낡는다).

## 위험하지 않은 것 (실측 확인)

- **네이버 열쇠가 운영에 없다** — `NAVER_COMMERCE_CLIENT_ID`/`SECRET` 이 web·WORKER·
  FOMS-cron 어디에도 없다. 승격해도 네이버로 나가는 호출 0.
- **자동 수집이 안 켜진다** — `start.sh` 가 `FOMS_NAVER_SYNC_ENABLED=1` 일 때만 수집 루프를
  띄우는데 운영에 그 변수가 없다. 실주문 자동 생성 없음.
- **워크벤치 게이트 기본 off** — `FOMS_NAVER_WORKBENCH_ENABLED` 없음.
- **nav 뱃지는 fail-open** — `compute_triage_pending_count` 가 `SQLAlchemyError` + 광의
  `except` 두 겹으로 잡아 0 을 돌려준다(테이블이 없어도 전 페이지 500 은 안 난다).
  ※ 미확인: 실패한 쿼리가 요청 트랜잭션을 오염시켜 이후 쿼리가 연쇄로 죽는지.
- **egress IP** — dev·운영이 같은 region 풀이라 네이버 화이트리스트 교체 불필요.

## 승격에 필요한 것

1. 운영 실제 head(`merge_prod_drawq`)를 **출발점으로 인정**하는 체인 설계.
   이미 적용된 `assort_00`·`notifrole_00` 의 부모는 **운영 값 그대로 두고**,
   네이버·`asaxis_00`·`orderreason_00` 체인을 `merge_prod_drawq` 뒤에 단다.
   (부모 바꿔치기 금지 — 같은 revision 두 갈래를 만들지 않는다.)
2. 운영 스냅샷 복제본에 걸어 왕복 실증: baseline `create_all` + stamp + 전체 `upgrade` +
   `downgrade`. 단일 head 확인.
3. **당일 머지** — 하루 지나면 타 세션 승격으로 head 전제가 또 깨진다.
4. 440 커밋 승격이라 별도 스펙·원장 + 사용자 명시 승인이 필요하다.

## 사용자 결정 (2026-08-24)

**지금은 멈추고 설계부터.** 승격은 착수하지 않는다. 대신 전 직원 개방 전 승격 게이트
3건 + 벌크 폴링을 먼저 처리한다.
