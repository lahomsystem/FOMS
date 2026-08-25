# 네이버 운영 승격 — alembic 계보 재설계 SPEC (2026-08-24)

- **상태**: 설계 확정 대기(사용자 승인 필요 — §9)
- **작성 시각**: 2026-08-24 19:34 KST (`2026-08-24T10:34Z`)
- **작성 워크트리**: `c:/tmp/foms-s-naver-ingest` · 브랜치 `session/naver-ingest`
- **선행 문서**: `docs/plans/2026-08-24-naver-production-promotion-blockers.md`(차단 사유 실측)
- **이 문서의 범위**: **설계뿐이다.** 마이그레이션 파일을 만들거나 고치지 않았고,
  어떤 브랜치에도 push·merge·cherry-pick 하지 않았다. 운영 DB 에 쓰지 않았다.
  이 세션의 파일 변경은 **이 문서 1개**다.

---

## 1. 재확인 실측 (2026-08-24 19:34 KST, git 전용)

선행 문서의 값을 **그대로 믿지 않고** `git ls-remote`·`git log`·리비전 파일 파싱으로
다시 쟀다. 결과: **6개 항목 중 3개가 이미 낡았고, 1개는 사실과 다르다.**

| 항목 | blockers 문서(08-24 오전) | 지금 재확인 | 판정 |
|---|---|---|---|
| `origin/production` | `d5b44d87` | **`e849927e`** | ⚠️ **이동**(PR #140·#141·#142 추가 머지) |
| `origin/deploy` | `b085569d` | **`a8ded306`** | ⚠️ **이동** |
| 미승격 커밋 | 440 | **463** | ⚠️ **+23** |
| production 그래프 head | `merge_prod_drawq` | `merge_prod_drawq` | ✅ 유지 |
| deploy 그래프 head | `merge_drawq_naverfail` | `merge_drawq_naverfail` | ✅ 유지 |
| `merge_prod_drawqueue_notifrole.py` | production 에만 존재 | production 에만 존재 | ✅ 유지 |
| `assort_00` 부모 | 운영 `asfresh_00` / deploy `asaxis_00` | 동일 | ✅ 유지 |
| `notifrole_00` 부모 | 운영 `assort_00` / deploy `naver_relation_00` | 동일 | ✅ 유지 |
| 부팅 시 자동 마이그레이션 | **"없다 (Procfile 은 gunicorn 만)"** | **있다** — §1.2 | ❌ **정정** |

반나절 만에 tip 두 개가 모두 움직이고 미승격 커밋이 23개 늘었다. §7 의 "당일 머지"
제약은 수사가 아니라 **오늘 안에서도 관측된 사실**이다.

### 1.1 재확인에 쓴 명령 (복붙 가능)

```bash
cd /c/tmp/foms-s-naver-ingest
git fetch origin --quiet
git ls-remote origin refs/heads/production refs/heads/deploy
git rev-list --count origin/production..origin/deploy
git diff --name-only origin/production origin/deploy -- migrations/versions/
```

리비전 그래프 head 는 DB 없이 파일만으로 계산한다(`tests/domains/test_alembic_single_head.py`
와 같은 방식). 임시 파싱 스크립트는 스크래치패드에만 두었고 저장소에 커밋하지 않았다.
저장소 내장 게이트로도 같은 값을 얻는다:

```bash
python -m pytest tests/domains/test_alembic_single_head.py -q     # 현재 브랜치 파일 기준
python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; \
c=Config('alembic.ini'); print(ScriptDirectory.from_config(c).get_heads())"
```

### 1.2 정정 — 자동 마이그레이션은 **있다** (fail-closed)

`Procfile` 만 보면 `gunicorn` 뿐이라 "자동 마이그레이션 없음"으로 보인다. 그러나 Railway 는
`railway.toml` 을 config-as-code 로 읽고, 거기에 **`preDeployCommand`** 가 있다.

`railway.toml`(운영 브랜치 `origin/production` 에도 **동일하게 존재**):

```toml
[deploy]
startCommand      = "sh start.sh"
preDeployCommand  = "sh predeploy.sh"
```

`predeploy.sh`:

```sh
set -e
if [ "$USE_RQ_WORKER" = "1" ]; then exit 0; fi   # 워커는 스키마 미소유 → 스킵
alembic upgrade head
python tools/ops/ensure_schema.py
```

이 사실이 설계를 크게 바꾼다:

1. **스키마가 코드보다 먼저다.** `preDeployCommand` 는 새 배포가 라이브되기 전 **1회**
   도는 one-off 컨테이너다. 마이그레이션이 끝난 뒤에야 replica 가 뜬다.
   → §5 의 "스키마 우선" 순서는 **이미 인프라가 강제**하고 있고, 우리는 그것을 깨지
   않기만 하면 된다.
2. **실패하면 배포가 라이브되지 않는다**(`set -e` → Railway fail-closed).
   → blockers 문서가 걱정한 *"코드만 살아 있고 스키마는 옛것"* 조합은 **일어나지 않는다.**
   대신 **배포가 통째로 막힌다**(운영은 옛 코드로 계속 정상 서비스).
3. 그래서 지금 승격을 강행했을 때의 실제 결말은 "전 시스템 500"이 아니라
   **"운영 배포 영구 실패 + 옛 버전 유지"** 다. 덜 나쁘지만 여전히 승격 불가다.

> **단, 이 안전망은 검증 대상이다.** `railway.toml` 은 서비스 설정에서 덮어쓸 수 있다.
> 운영 web 서비스의 Config Source 가 실제로 `railway.toml` 인지, `preDeployCommand` 가
> 대시보드에서 비워져 있지 않은지 **§5 S0 에서 사람이 눈으로 확인**해야 한다.
> 만약 덮어써져 있다면 위 1~3 이 전부 뒤집히고 blockers 문서의 최악 시나리오가 되살아난다.

### 1.3 이 워크트리는 deploy tip 이 아니다

```
session/naver-ingest 그래프 head = naverfail_00              (82 리비전)
origin/deploy        그래프 head = merge_drawq_naverfail     (84 리비전)
```

이 브랜치에는 `drawqueue_00`·`merge_drawq_naverfail` 이 없다(딴 세션이 deploy 에 올린 뒤
이 브랜치가 안 따라잡았다). **실제 재직렬화 작업은 이 워크트리에서 하면 안 된다** —
§5 S1 이 지시하는 대로 `origin/deploy` tip 에서 딴 깨끗한 워크트리에서 해야 한다.

---

## 2. 문제의 정확한 형태

### 2.1 정합 판정 기준 (한 문장)

> **파일 그래프에서 "그 DB 가 stamp 한 리비전의 조상집합"이, "그 DB 가 실제로 적용한
> 리비전 집합"과 정확히 같아야 한다. 운영 DB 와 스테이징 DB 둘 다 동시에.**

alembic 은 `alembic_version` 에 **현재 head 하나만** 저장한다. 지나온 경로는 저장하지
않는다. 그래서 **리비전들 사이 순서를 다시 엮는 것(re-serialization) 자체는 죄가 아니다.**
죄가 되는 것은 위 등식이 깨질 때뿐이다. 깨지면 두 가지로 나타난다:

- **조상집합 > 적용집합** → alembic 이 "이미 했다"고 착각 → 그 DDL 이 **영영 안 돈다**
  (조용한 스키마 구멍, 혹은 뒤따르는 ALTER 가 없는 테이블을 건드려 폭사).
- **조상집합 < 적용집합** → alembic 이 이미 만든 것을 **다시 만들려 든다**
  (`DuplicateColumn`/`DuplicateTable`).

### 2.2 지금 deploy 파일을 그대로 얹으면 왜 죽는가

운영 DB 는 `merge_prod_drawq` 에 stamp 돼 있다. deploy 파일 집합에는 그 리비전 **파일이
없다** → `alembic upgrade head` 가 `Can't locate revision identified by 'merge_prod_drawq'`
로 즉사 → `set -e` → 배포 라이브 안 됨.

**그렇다면 파일만 되살리면 되는가? 안 된다.** deploy 파일 그대로에
`merge_prod_drawqueue_notifrole.py` 만 복원하면 그래프는 이렇게 된다:

```
merge_prod_drawq ← (drawqueue_00, notifrole_00)
                        └ notifrole_00 ← naver_relation_00 ← assort_00 ← asaxis_00
                          ← naverdock_00 ← navercollect_00 ← naver_triage_00
                          ← orderreason_00 ← naver_link_00 ← asfresh_00
```

즉 **`merge_prod_drawq` 의 조상집합에 네이버 체인 전부와 `asaxis_00` 이 들어간다.**
운영은 그것들을 한 번도 실행한 적이 없는데 alembic 은 "이미 적용됨"으로 본다
(§2.1 의 *조상집합 > 적용집합*). `upgrade head` 가 실행할 것은 `navergroup_00`,
`naverfail_00`, `merge_drawq_naverfail` 셋뿐이다. 그런데—

```python
# navergroup_00_external_order_link_group_key.py
TABLE = 'external_order_links'
op.add_column(TABLE, sa.Column('group_key', sa.String(length=200), nullable=True))
```

`external_order_links` 는 `naver_link_00` 이 만드는데 그건 "이미 했다"고 건너뛴 리비전이다
→ `UndefinedTable` → 배포 실패. 운 나쁘게 통과했다면 `orders.as_axis_status` 가 없는 채로
코드가 올라가 **전 시스템 500** 이 된다.

**결론: 파일 복원만으로는 안 된다. `assort_00`·`notifrole_00` 의 부모를 운영이 실제로
지나온 값으로 되돌려야 한다.**

### 2.3 누가 부모를 바꿨는가 (책임 소재 — 재발 방지용)

```bash
git log --oneline origin/deploy     -- migrations/versions/assort_00_attachment_sort_order.py
#  0f1a516e  ← 최초 생성 1회뿐, 부모 asaxis_00 로 태어나 한 번도 안 바뀜
git log --oneline origin/production -- migrations/versions/assort_00_attachment_sort_order.py
#  a5758256  ← 승격 cherry-pick 커밋. 여기서 부모가 asfresh_00 로 바뀌었다
```

**바꿔치기는 deploy 가 아니라 "승격하는 쪽"에서 일어났다.** 승격자가 cherry-pick 하면서
`down_revision` 을 손으로 고쳐 운영 계보에 끼워 넣었다(`notifrole_00` 도 동일 — `0fe42d24`).
그 순간 같은 revision id 가 두 부모를 갖게 됐고, 오늘의 교착이 시작됐다.

**다만 지금 시점에서 "누가 옳았나"는 무의미하다.** 운영 DB 는 이미 `asfresh_00 → assort_00`
순서로 **실행을 끝냈다.** 그 사실은 되돌릴 수 없다. 따라서 **운영의 부모가 정본**이고,
deploy 파일이 그쪽에 맞춰야 한다.

> 재발 방지: 승격 시 `down_revision` 을 손으로 고치는 것은 **금지**다.
> 계보가 갈리면 이 문서처럼 **병합 리비전(no-op merge)** 으로 잇는다.
> 실제로 `merge_prod_drawqueue_notifrole.py` 의 docstring 이 이미 그 규칙("부모
> 바꿔치기 금지")을 적어 놓았는데, 그 파일을 만든 세션조차 그 앞의 두 건
> (`assort_00`·`notifrole_00`)은 이미 바꿔치기한 뒤였다.

---

## 3. 리비전 그래프 3장

노드 표기: `revision_id  ←  부모`. 세로선은 부모→자식.

### 3.1 지금 (운영) — `origin/production` `e849927e`, 75 리비전

```
  … senderphone_00
        │
     asfresh_00                   ← senderphone_00
        │
     assort_00                    ← asfresh_00                    ★운영이 실제로 지나온 부모
        ├───────────────┐
        │               │
  drawqueue_00      notifrole_00  ← assort_00                     ★운영이 실제로 지나온 부모
   ← assort_00          │
        │               │
        └───────┬───────┘
                │
        merge_prod_drawq          ← (drawqueue_00, notifrole_00)
                                     ▲ head = 1개
                                     ▲ 운영 DB alembic_version 이 여기에 stamp 돼 있다
```

운영에 없는 것: `naver_link_00` `orderreason_00` `naver_triage_00` `navercollect_00`
`naverdock_00` `asaxis_00` `naver_relation_00` `navergroup_00` `naverfail_00`
`merge_drawq_naverfail` (**10개**).

### 3.2 지금 (deploy) — `origin/deploy` `a8ded306`, 84 리비전

```
  … senderphone_00
        │
     asfresh_00
        │
   naver_link_00                   ← asfresh_00                    ☆운영과 다른 자리
        │
   orderreason_00                  ← naver_link_00
        │
   naver_triage_00                 ← orderreason_00
        │
   navercollect_00                 ← naver_triage_00
        │
   naverdock_00                    ← navercollect_00
        │
   asaxis_00                       ← naverdock_00
        │
   assort_00                       ← asaxis_00                     ☆☆ 운영은 asfresh_00
        ├────────────────┐
        │                │
  drawqueue_00   naver_relation_00 ← assort_00
   ← assort_00          │
        │        notifrole_00      ← naver_relation_00             ☆☆ 운영은 assort_00
        │                │
        │        navergroup_00     ← notifrole_00
        │                │
        │        naverfail_00      ← navergroup_00
        │                │
        └───────┬────────┘
                │
   merge_drawq_naverfail           ← (drawqueue_00, naverfail_00)
                                     ▲ head = 1개
                                     ▲ 스테이징 DB 가 여기에 stamp 돼 있다(가정 — S0 에서 확인)

   merge_prod_drawq : 파일 자체가 없다  ← 운영이 서 있는 자리를 deploy 는 모른다
```

### 3.3 설계 후 — 양 브랜치 **공통 파일 집합**, 85 리비전, **head 1개**

```
  … senderphone_00
        │
     asfresh_00                       [무변경]
        │
     assort_00        ← 'asfresh_00'                        ★복원 (운영값)
        ├───────────────────────┐
        │                       │
  drawqueue_00              notifrole_00  ← 'assort_00'     ★복원 (운영값)
   ← 'assort_00' [무변경]        │
        │                       │
        ├───────────┬───────────┘
        │           │
        │   merge_prod_drawq  ← ('drawqueue_00','notifrole_00')   ★파일 부활 (내용 무변경)
        │           │
        │           │  ◀── 운영 DB 는 지금 정확히 여기에 서 있다.
        │           │       승격 후 여기서부터 아래 9개가 순서대로 돈다.
        │           │
        │    naver_link_00      ← 'merge_prod_drawq'       ☆재배치 (was asfresh_00)
        │           │
        │    orderreason_00     ← 'naver_link_00'          [무변경]
        │           │
        │    naver_triage_00    ← 'orderreason_00'         [무변경]
        │           │
        │    navercollect_00    ← 'naver_triage_00'        [무변경]
        │           │
        │    naverdock_00       ← 'navercollect_00'        [무변경]
        │           │
        │    asaxis_00          ← 'naverdock_00'           [무변경]
        │           │
        │    naver_relation_00  ← 'asaxis_00'              ☆재배치 (was assort_00)
        │           │
        │    navergroup_00      ← 'naver_relation_00'      ☆재배치 (was notifrole_00)
        │           │
        │    naverfail_00       ← 'navergroup_00'          [무변경]
        │           │
        └─────┬─────┘
              │
  merge_drawq_naverfail  ← ('drawqueue_00','naverfail_00')  [무변경]
              ▲
              ▲ head = **정확히 1개**
              ▲ 스테이징 DB 는 이미 여기에 stamp 돼 있다(= upgrade 무동작)
```

**head 가 1개임의 확인** — 자식이 없는 노드를 전부 세면:

| 노드 | 설계 후 자식 | head? |
|---|---|---|
| `asfresh_00` | `assort_00` | 아니오 |
| `assort_00` | `drawqueue_00`, `notifrole_00` | 아니오 |
| `drawqueue_00` | `merge_prod_drawq`, `merge_drawq_naverfail` | 아니오 |
| `notifrole_00` | `merge_prod_drawq` | 아니오 |
| `merge_prod_drawq` | `naver_link_00` | 아니오 |
| `naver_link_00` … `naverdock_00` | 각각 다음 노드 | 아니오 |
| `asaxis_00` | `naver_relation_00` | 아니오 |
| `naver_relation_00` | `navergroup_00` | 아니오 |
| `navergroup_00` | `naverfail_00` | 아니오 |
| `naverfail_00` | `merge_drawq_naverfail` | 아니오 |
| `merge_drawq_naverfail` | **없음** | ✅ **유일 head** |

사이클 없음: `drawqueue_00` → `merge_prod_drawq` → … → `naverfail_00` → `merge_drawq_naverfail`
와 `drawqueue_00` → `merge_drawq_naverfail` 는 같은 방향이라 DAG 다.

### 3.4 그래프 시뮬레이션 결과 (파일을 고치기 전에 미리 계산했다)

E1~E6(§4)을 **메모리 위에서만** 적용해 설계 후 그래프를 계산했다. 저장소 파일은 건드리지
않았다. 재현 스크립트는 부록 B.

```
리비전 수 : 85
head      : ['merge_drawq_naverfail']          ← 정확히 1개
dangling  : []                                 ← 부모가 없는 리비전 참조 0건
운영 조상집합 크기 : 75                         ← origin/production 리비전 수와 정확히 일치
운영에 없는 리비전 : ['asaxis_00', 'merge_drawq_naverfail', 'naver_link_00',
                     'naver_relation_00', 'naver_triage_00', 'navercollect_00',
                     'naverdock_00', 'naverfail_00', 'navergroup_00', 'orderreason_00']
운영 조상에 네이버/asaxis 가 섞였나 : 없음 (OK)  ← §2.2 의 조용한 건너뜀이 없다는 증명
스테이징 stamp 조상집합 == 전체 : True

운영이 실행할 리비전 순서 (위상정렬):
   1. naver_link_00     2. orderreason_00   3. naver_triage_00  4. navercollect_00
   5. naverdock_00      6. asaxis_00        7. naver_relation_00 8. navergroup_00
   9. naverfail_00     10. merge_drawq_naverfail
```

**"운영 조상집합 크기 = 75 = `origin/production` 의 리비전 수"** 가 §4.2 등식의 기계적
확인이다. 운영이 실제로 가진 75개와 alembic 이 "적용됐다"고 볼 75개가 정확히 같다.
그리고 위 10개 순서가 §4.2 에 적은 순서·§5 S4 의 기대 로그와 글자 단위로 같다.

> 단, 이것은 **그래프 계산**이지 **DDL 실행**이 아니다. 실제 SQL 이 도는지는 §6 R2 가
> 증명한다. 둘 다 green 이어야 승격한다.

---

## 4. 편집 목록 — 정확히 6곳

| # | 파일 | 지금 deploy 값 | 설계 후 값 | 종류 |
|---|---|---|---|---|
| E1 | `migrations/versions/merge_prod_drawqueue_notifrole.py` | **파일 없음** | `origin/production` 사본 그대로 부활 | 파일 복원 |
| E2 | `migrations/versions/assort_00_attachment_sort_order.py` | `down_revision = "asaxis_00"` | `down_revision = "asfresh_00"` | **운영값 복원** |
| E3 | `migrations/versions/notifrole_00_notification_target_role.py` | `down_revision = "naver_relation_00"` | `down_revision = "assort_00"` | **운영값 복원** |
| E4 | `migrations/versions/naver_link_00_external_order_links.py` | `down_revision = 'asfresh_00'` | `down_revision = 'merge_prod_drawq'` | 재배치 |
| E5 | `migrations/versions/naver_relation_00_link_relation_and_place_status.py` | `down_revision = 'assort_00'` | `down_revision = 'asaxis_00'` | 재배치 |
| E6 | `migrations/versions/navergroup_00_external_order_link_group_key.py` | `down_revision = 'notifrole_00'` | `down_revision = 'naver_relation_00'` | 재배치 |

**바뀌지 않는 것**: `upgrade()`/`downgrade()` 본문을 **한 줄도** 건드리지 않는다.
`revision` id 도 그대로다. `merge_drawqueue_naverfail_heads.py` 도 그대로 둔다.
`asaxis_00`·`orderreason_00`·`naver_triage_00`·`navercollect_00`·`naverdock_00`·
`naverfail_00`·`drawqueue_00` 은 무변경이다.

E1 복원 명령(실행은 §5 S1 에서):

```bash
git show origin/production:migrations/versions/merge_prod_drawqueue_notifrole.py \
  > migrations/versions/merge_prod_drawqueue_notifrole.py
```

E2~E6 은 각 파일에서 `down_revision` 한 줄만 고친다. docstring 의 `Revises:` 줄도
같은 값으로 맞추고, 왜 바꿨는지 한 줄(“운영 실제 계보 정합 — 2026-08-24 SPEC §4”)을
덧붙인다.

### 4.1 "부모 바꿔치기 금지" 를 어긴 곳이 없다는 증명

금지 규칙의 정확한 뜻은 §2.1 이다: **어떤 DB 가 이미 지나온 부모 관계를 파일에서 지우면
안 된다.** 6개 편집을 그 기준으로 하나씩 판정한다.

| # | 어떤 DB 가 이 관계를 실제로 지나갔나 | 판정 |
|---|---|---|
| E1 | 운영이 `merge_prod_drawq` 를 실행하고 stamp 했다 | **복원 = 사실 보존** ✅ |
| E2 | 운영은 `asfresh_00 → assort_00` 을, 스테이징은 `asaxis_00 → assort_00` 을 실행했다 | 파일은 하나뿐 → **운영값 채택**. 스테이징 무해성은 §4.2·§4.3 ✅ |
| E3 | 운영은 `assort_00 → notifrole_00`, 스테이징은 `naver_relation_00 → notifrole_00` | E2 와 동일 ✅ |
| E4 | `naver_link_00` — **운영은 한 번도 실행한 적 없다** | 미적용 리비전의 재배치 ✅ |
| E5 | `naver_relation_00` — **운영 미적용** | ✅ |
| E6 | `navergroup_00` — **운영 미적용** | ✅ |

E4~E6 은 운영이 지나간 적 없는 리비전을 운영이 지나간 노드(`merge_prod_drawq`) 뒤로
옮기는 것이다. **운영의 과거를 고치는 게 아니라 운영의 미래를 정하는 것**이므로
바꿔치기가 아니다. E2·E3 은 운영의 과거를 **복원**하는 것이므로 역시 아니다.

### 4.2 두 DB 동시 정합 증명 (§2.1 등식)

| DB | `alembic_version` | 설계 후 파일 그래프의 **조상집합** | 그 DB 가 **실제 적용**한 집합 | 등식 |
|---|---|---|---|---|
| **운영** | `merge_prod_drawq` | `{…옛것…, asfresh_00, assort_00, drawqueue_00, notifrole_00, merge_prod_drawq}` | 정확히 동일 | ✅ |
| **스테이징** | `merge_drawq_naverfail` | 전 85 리비전 | 84 리비전(= 85 − `merge_prod_drawq`) | ⚠️ §4.3 |

따라서 **운영에서 `alembic upgrade head` 는 정확히 다음 순서로 9개 DDL + 1개 no-op 을 돈다**:

```
merge_prod_drawq
 → naver_link_00        CREATE TABLE external_order_links
 → orderreason_00       CREATE TABLE order_change_reasons (+ 인덱스 3)
 → naver_triage_00      ALTER external_order_links
 → navercollect_00      ALTER external_order_links
 → naverdock_00         ALTER external_order_links
 → asaxis_00            ALTER orders ADD as_axis_status (+ 부분 인덱스)   ← 치명 1 해소
 → naver_relation_00    ALTER external_order_links (+ CHECK, 백필)
 → navergroup_00        ALTER external_order_links
 → naverfail_00         CREATE INDEX on external_order_links
 → merge_drawq_naverfail  (no-op)
```

의존 순서 확인: `external_order_links` 를 `ALTER` 하는 5개(`naver_triage_00`
`navercollect_00` `naverdock_00` `naver_relation_00` `navergroup_00`)와 인덱스를 다는
`naverfail_00` 이 **전부 `naver_link_00`(CREATE TABLE) 뒤**에 온다. ✅
`asaxis_00`(orders 컬럼)·`orderreason_00`(새 테이블)은 다른 것과 객체가 겹치지 않아
순서에 자유롭다. ✅

**스테이징에서 `alembic upgrade head` 는 무동작이다** — 이미 head 에 stamp 돼 있다.
재실행되는 DDL 이 0 이므로 스테이징이 다칠 경로가 없다.

### 4.3 유일한 의도적 허구와 그것이 무해한 이유

스테이징은 `merge_prod_drawq` 를 **실행한 적이 없다.** 그런데 설계 후 그래프에서는
그것이 스테이징 stamp(`merge_drawq_naverfail`)의 조상이 되므로, alembic 은
"스테이징도 적용했다"고 간주한다. §2.1 의 *조상집합 > 적용집합* 이다.

**무해한 이유**: `merge_prod_drawq` 는 **DDL 이 한 줄도 없는 병합 노드**다.

```python
def upgrade() -> None:
    """병합 노드 — 스키마 변경 없음."""
    pass
def downgrade() -> None:
    """병합 노드 — 스키마 변경 없음."""
    pass
```

"적용했다고 간주"와 "실제로 적용"의 스키마 차이가 **0** 이다. 조상집합 > 적용집합이
위험한 이유는 오직 *건너뛴 DDL* 때문인데, 여기엔 건너뛸 DDL 이 없다.
이것이 이 설계 전체에서 유일하게 등식을 벗어나는 지점이며, 의도된 것이다.

### 4.4 (선택) 정리안 — 채택하지 않음

`merge_drawq_naverfail` 의 부모에서 `drawqueue_00` 을 빼면(`('naverfail_00',)` 로) 중복
부모가 사라져 그래프가 더 깔끔해진다. 설계 후 `drawqueue_00` 은 `naverfail_00` 의
조상이므로 조상집합은 그대로다.

**채택하지 않는 이유**: 그건 **스테이징이 이미 stamp 한 노드의 부모를 고치는 것**이다.
지금 얻는 이득(가독성)이 규칙을 흐리는 비용보다 작다. 중복 부모는 alembic 이 허용하며,
§6 R0 이 이를 실증한다. **그대로 둔다.**

---

## 5. 단계별 승격 순서와 롤백

원칙 두 개를 못박는다.

> **P1. 스키마가 코드보다 먼저다.** 운영에서 이 순서는 `preDeployCommand`(§1.2)가
> 인프라 수준에서 강제한다. **사람이 순서를 지키는 게 아니라, 순서를 깨지 않는 것이 일이다.**
> 유일한 위험은 `preDeployCommand` 가 대시보드에서 꺼져 있는 경우다 → **S0 에서 확인**.
>
> **P2. 재직렬화는 deploy 에 먼저 랜딩한다.** 운영에만 넣으면 계보가 또 갈린다(그게
> 오늘의 사고 원인이다). deploy → 스테이징 검증 → 그 다음 승격.

### S0 — 사전 게이트 (승격 착수 전, 30분)

| 항목 | 방법 | 통과 조건 |
|---|---|---|
| S0-1 | Railway 운영 web 서비스 Settings → Config-as-code 소스 확인 | `railway.toml` 사용 중 **and** `preDeployCommand` 미덮어씀 |
| S0-2 | 운영 `alembic_version` 재조회(**읽기 전용**) | `merge_prod_drawq` 1행 |
| S0-3 | 스테이징 `alembic_version` 조회 | `merge_drawq_naverfail` 1행 (§4.2 의 가정 확인) |
| S0-4 | `git ls-remote` 로 두 tip 재기록 | §7.3 체크리스트에 값 기재 |
| S0-5 | 운영 백업 시점 확인(Railway 백업 보존 6일) | 직전 24h 내 스냅샷 존재 |

S0-2 / S0-3 조회 (쓰기 절대 금지):

```bash
psql "$PRODUCTION_DATABASE_PUBLIC_URL" -c "SET default_transaction_read_only = on; \
  SELECT version_num FROM alembic_version;"
psql "$STAGING_DATABASE_PUBLIC_URL"    -c "SET default_transaction_read_only = on; \
  SELECT version_num FROM alembic_version;"
```

**S0-2 가 `merge_prod_drawq` 가 아니면 이 문서는 그 자리에서 무효다.** §3.1 부터 다시 그린다.

### S1 — 재직렬화 커밋을 `deploy` 에 랜딩

깨끗한 워크트리에서(§1.3 — 이 세션 워크트리 아님):

```bash
# ※ 주 세션이 실행. 공유 트리(C:\DEV\FOMS)에서 worktree 만 딴다.
git -C /c/DEV/FOMS worktree add /c/tmp/foms-chain origin/deploy -b chore/alembic-prod-lineage
cd /c/tmp/foms-chain
git log -1 --format=%H            # origin/deploy tip 이 S0-4 값과 같은지 확인
```

E1~E6(§4) 적용 → 검증(§6 R0·R1·R2·R3 전부 green) → 커밋 1개.
커밋 메시지(한글, UTF-8 파일 저장 후 `git commit -F`):

```
chore(migrations): 운영 실제 head(merge_prod_drawq)를 출발점으로 alembic 계보 재직렬화

운영이 이미 지나온 assort_00·notifrole_00 의 부모를 운영값으로 복원하고,
운영 미적용인 네이버·asaxis·orderreason 체인을 merge_prod_drawq 뒤로 옮긴다.
upgrade()/downgrade() 본문과 revision id 는 무변경. head 1개 유지.
근거: docs/specs/2026-08-24-naver-production-promotion-chain_SPEC.md
```

**롤백 S1**: push 전이면 `git reset --hard origin/deploy`. push 후면 `git revert` 1커밋.
스테이징 DB 는 이 시점까지 아무 DDL 도 실행하지 않으므로 **DB 롤백 불필요**.

### S2 — 스테이징 실증

deploy push → Railway 자동 배포 → `predeploy` 로그에서 확인:

```
[predeploy] Running DB migrations...
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
(Running upgrade 라인이 0개여야 한다 — 이미 head)
[predeploy] Migrations complete.
```

**`Running upgrade` 가 한 줄이라도 찍히면 §4.2 의 스테이징 stamp 가정이 틀린 것이다
→ 즉시 중단.**

이어서 스테이징 스모크: 주문 목록·상세·대시보드·네이버 워크벤치 각 1회 200 확인.

**롤백 S2**: `git revert` 후 재배포. DDL 이 안 돌았으므로 DB 되돌릴 것 없음.

### S3 — 운영 승격 PR 작성 (아직 배포 아님)

범위는 §8 에서 사용자가 고른 안. 어느 안이든 **S1 커밋이 반드시 포함**돼야 한다.

```bash
python tools/harness/promote_completeness.py --shas <S1_SHA>,<...> --json
python tools/harness/promote_own_to_production.py --shas <S1_SHA>,<...>
```

PR 생성 후 **머지 전에** 승격 워크트리에서 그래프를 다시 잰다(승격 트리에서만 보이는
충돌이 이 프로젝트의 반복 사고다):

```bash
cd <promote_worktree>
python -m pytest tests/domains/test_alembic_single_head.py -q     # head 1개
git diff --stat origin/production...HEAD -- migrations/versions/  # 13개 파일만
```

**롤백 S3**: PR close. 운영에 아무 영향 없음.

### S4 — 운영 배포 (되돌리기 어려운 유일한 단계)

PR 머지 → Railway 운영 배포 → `preDeployCommand` 가 **replica 가 뜨기 전에**
`alembic upgrade head` 실행.

기대 로그 — **§4.2 의 9개가 정확히 이 순서로**:

```
Running upgrade merge_prod_drawq -> naver_link_00
Running upgrade naver_link_00 -> orderreason_00
Running upgrade orderreason_00 -> naver_triage_00
Running upgrade naver_triage_00 -> navercollect_00
Running upgrade navercollect_00 -> naverdock_00
Running upgrade naverdock_00 -> asaxis_00
Running upgrade asaxis_00 -> naver_relation_00
Running upgrade naver_relation_00 -> navergroup_00
Running upgrade navergroup_00 -> naverfail_00
Running upgrade drawqueue_00, naverfail_00 -> merge_drawq_naverfail
[predeploy] Migrations complete.
```

**롤백 S4** (4층, 위에서부터):

1. **predeploy 실패 시** — 원칙적으로 아무것도 안 해도 된다. `set -e` 로 배포가
   라이브되지 않고 운영은 옛 코드+옛 스키마로 계속 돈다. 로그의 실패 리비전을 근본
   수정하고 재시도.
   *단 부분 적용 여부 확인 필수*: `SELECT version_num FROM alembic_version` 이 중간
   리비전이면 그만큼 DDL 이 남아 있다 → 아래 2번.
2. **스키마만 되돌리기** — `alembic downgrade merge_prod_drawq`
   (§6 R2 가 이 경로를 사전에 실증한다). 그다음 3번.
   ⚠️ `naver_link_00` 의 downgrade 는 `external_order_links` 를 **DROP** 한다 —
   수집 멱등 근거가 사라져 재수집 시 과거 주문이 되살아날 수 있다. 운영 downgrade 는
   **수집 게이트 off 상태에서만**(운영엔 `FOMS_NAVER_SYNC_ENABLED` 가 없으므로 현재 off ✅).
3. **코드 되돌리기** — 운영 PR revert 후 재배포. 반드시 2번(스키마) **다음**에 한다.
   (코드를 먼저 되돌리면 옛 코드 + 새 스키마 조합이 되는데, 그 자체는 무해하지만
   `ensure_schema.py` 와 섞이면 상태 판단이 어려워진다.)
4. **최후** — Railway 백업 복원(보존 6일, PITR 은 fork 로만). 데이터 손실을 동반하므로
   사용자 승인 필수.

### S5 — 배포 후 (30분 내)

| 확인 | 방법 |
|---|---|
| 스키마 | `SELECT version_num FROM alembic_version` = `merge_drawq_naverfail` |
| 치명 1 해소 | 운영 주문 목록·상세·대시보드·검색 각 1회 200 |
| 네이버 비활성 유지 | `NAVER_COMMERCE_CLIENT_ID` / `FOMS_NAVER_SYNC_ENABLED` / `FOMS_NAVER_WORKBENCH_ENABLED` 셋 다 **없음** |
| CI | `gh run list --commit <머지 SHA>` 로 **전 워크플로 나열** (1개만 보면 안 된다) |

**운영에서 네이버 기능을 켜는 것은 이 승격의 범위가 아니다** — 스키마와 코드만 올리고
게이트는 닫아 둔다. 켜는 것은 별도 승인 건이다(§9 D6).

---

## 6. 왕복 실증 계획 (복붙 가능)

로컬에 Docker·WSL 이 없다. PostgreSQL 은 네이티브로 15/16/17 이 설치돼 있다
(`/c/Program Files/PostgreSQL/{15,16,17}/bin` — 실측 확인).

> **레인 현황(실측)**: 관행상의 5440 클러스터는 **깨져 있다**
> (`could not open file "base/1/4171"`, 2026-08-20 원장). 현재 살아 있는 레인은
> **`/c/tmp/pglane5441` (포트 5441, PG17, trust)** 이고 지금도 LISTENING 이다.
> 아래는 5441 을 쓴다. 5440 을 되살릴 필요 없다.

### R0 — 그래프·문법 (DB 불필요, 10초)

```bash
cd /c/tmp/foms-chain
python -m pytest tests/domains/test_alembic_single_head.py -q
python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; \
c=Config('alembic.ini'); s=ScriptDirectory.from_config(c); \
print('heads =', s.get_heads()); \
print('count =', len(list(s.walk_revisions())))"
alembic history --verbose | head -60
```

**통과 조건**: `heads = ('merge_drawq_naverfail',)` (**정확히 1개**), `count = 85`,
`alembic history` 가 예외 없이 출력(= §4.4 의 중복 부모를 alembic 이 받아들인다는 실증).

### R1 — 로컬 PG 레인 준비

```bash
export PATH="/c/Program Files/PostgreSQL/17/bin:$PATH"
CLUSTER=/c/tmp/pglane5441

# 이미 떠 있으면 start 는 건너뛴다
pg_ctl -D "$CLUSTER" status \
  || pg_ctl -D "$CLUSTER" -o "-p 5441" -l "$CLUSTER/pg.log" start

psql -h 127.0.0.1 -p 5441 -U postgres -d postgres -c "SELECT version();"
```

클러스터가 없을 때만(신규 생성):

```bash
initdb -D /c/tmp/pglane5441 -U postgres --encoding=UTF8 --locale=C --auth=trust
pg_ctl -D /c/tmp/pglane5441 -o "-p 5441" -l /c/tmp/pglane5441/pg.log start
```

### R2 — **운영 출발점 리허설** (이 설계의 핵심 실증)

운영 상태를 로컬에서 재현하는 방법: `create_all` 로 최신 스키마를 만들고 head 로 stamp 한
뒤 **`merge_prod_drawq` 까지 downgrade** 한다. 그러면 남는 스키마는 정의상
"네이버 체인·asaxis·orderreason 이 없는 상태" = **운영 스키마 모양**이고,
`alembic_version` 도 **운영과 같은 `merge_prod_drawq`** 가 된다.
거기서 `upgrade head` 를 돌리는 것이 곧 **운영 승격의 예행연습**이다.

> 왜 빈 DB 에서 `upgrade head` 를 못 하나: base 리비전 `aef164da4c43` 이 create-table
> 없이 `add_column('orders')` 로 시작한다(과거 `create_all`+`stamp` 부트스트랩 이력).
> `tests/postgres/conftest.py` 와 `tests/postgres/test_migration_chain.py` 의 docstring 이
> 같은 사실을 적어 놓았다. 그래서 baseline 은 반드시 `create_all` 이다.

```bash
cd /c/tmp/foms-chain
export PATH="/c/Program Files/PostgreSQL/17/bin:$PATH"

DB=foms_test_promo_rehearsal_$(date +%H%M%S)
psql -h 127.0.0.1 -p 5441 -U postgres -d postgres -c "CREATE DATABASE \"$DB\";"
export DATABASE_URL="postgresql+psycopg2://postgres@127.0.0.1:5441/$DB"

python - <<'PY'
"""운영 출발점 리허설: create_all -> stamp head -> downgrade merge_prod_drawq
-> (운영 모양 확인) -> upgrade head -> (복원 확인) -> 2회차 왕복."""
import os
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

import app  # noqa: F401  전 모델을 Base.metadata 에 등록
from db import Base

URL = os.environ["DATABASE_URL"]
engine = create_engine(URL, connect_args={"client_encoding": "utf8"})

# alembic.ini 를 안 주는 이유: env.py 의 fileConfig 가 전역 logging 을 갈아엎는다.
cfg = Config()
cfg.set_main_option("script_location", "migrations")


def fingerprint() -> tuple:
    """(컬럼 지문 집합, 인덱스 이름 집합) — alembic_version 제외."""
    with engine.connect() as c:
        cols = {tuple(r) for r in c.execute(text(
            "SELECT table_name, column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name<>'alembic_version'"))}
        idx = {r[0] for r in c.execute(text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname='public' AND tablename<>'alembic_version'"))}
    return cols, idx


def scalar(sql: str):
    """단일 스칼라 조회."""
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()


Base.metadata.create_all(bind=engine)

# create_all(ORM) 이 자동 명명한 FK 를 마이그레이션이 소유한 이름으로 정렬한다.
# (tests/postgres/test_migration_chain.py 의 _FK_NAME_ALIGNMENT 와 같은 이유)
with engine.begin() as c:
    for col, owned in (("wizard_pending_id_fkey", "wizard_pending"),
                       ("order_import_artifact_id_fkey", "order_import_artifact"),
                       ("upload_draft_id_fkey", "upload_draft"),
                       ("upload_ticket_id_fkey", "upload_ticket")):
        c.execute(text("ALTER TABLE domain_side_effect_outbox "
                       f"RENAME CONSTRAINT domain_side_effect_outbox_{col} "
                       f"TO fk_dseo_{owned}"))

command.stamp(cfg, "head")
before = fingerprint()

# --- 운영 모양으로 내려간다 -------------------------------------------------
command.downgrade(cfg, "merge_prod_drawq")
stamp = scalar("SELECT version_num FROM alembic_version")
assert stamp == "merge_prod_drawq", f"stamp={stamp} (운영과 다르다)"
assert scalar("SELECT to_regclass('public.external_order_links')") is None
assert scalar("SELECT to_regclass('public.order_change_reasons')") is None
assert scalar("SELECT count(*) FROM information_schema.columns "
              "WHERE table_name='orders' AND column_name='as_axis_status'") == 0
print("[OK] 운영 출발점 재현 — stamp=merge_prod_drawq, 신규 객체 3종 부재")

# --- 승격 예행: 여기서부터가 운영 predeploy 와 같은 경로 ---------------------
command.upgrade(cfg, "head")
stamp = scalar("SELECT version_num FROM alembic_version")
assert stamp == "merge_drawq_naverfail", f"stamp={stamp}"
assert scalar("SELECT to_regclass('public.external_order_links')") is not None
assert scalar("SELECT to_regclass('public.order_change_reasons')") is not None
assert scalar("SELECT count(*) FROM information_schema.columns "
              "WHERE table_name='orders' AND column_name='as_axis_status'") == 1
after = fingerprint()
assert after == before, (
    "왕복 후 스키마가 달라졌다:\n"
    f"  컬럼 유실 {sorted(before[0] - after[0])[:5]}\n"
    f"  컬럼 잉여 {sorted(after[0] - before[0])[:5]}\n"
    f"  인덱스 유실 {sorted(before[1] - after[1])[:5]}\n"
    f"  인덱스 잉여 {sorted(after[1] - before[1])[:5]}")
print("[OK] 승격 예행 성공 — 9개 DDL 적용 후 스키마 지문 동일")

# --- 2회차 왕복(멱등 확인) --------------------------------------------------
command.downgrade(cfg, "merge_prod_drawq")
command.upgrade(cfg, "head")
assert fingerprint() == before
print("ROUNDTRIP_OK")
PY

psql -h 127.0.0.1 -p 5441 -U postgres -d postgres -c "DROP DATABASE \"$DB\";"
```

**통과 조건**: 마지막 줄에 `ROUNDTRIP_OK`. 어느 assert 라도 터지면 **승격 중단**.

### R3 — 기존 계약 테스트 전수 (같은 레인)

```bash
cd /c/tmp/foms-chain
export FOMS_TEST_DATABASE_URL="postgresql://postgres@127.0.0.1:5441/postgres"
python -m pytest tests/postgres/ -q            # 마이그레이션 배치 후 전수는 이 프로젝트 규약
python -m pytest tests/domains/test_alembic_single_head.py tests/domains/test_startup_pure.py -q
python -c "import app; print('APP_OK')"
bash -c 'pwsh -File scripts/ops/pre_push_smoke.ps1' ; echo "exit=$?"   # push 직전 exit 0 필수
```

`tests/postgres/test_migration_chain.py` 는 `_ROUNDTRIP_FLOOR = "index_ops_00"` 까지
내려갔다 올라온다. `index_ops_00` 은 `merge_prod_drawq` 보다 **한참 아래**라 이번 체인
전체가 그 창 안에 들어 있다 — 즉 R2 와 별개로 **CI 가 자동으로 이 체인을 왕복**한다.

### R4 — (선택·고정밀) 운영 스키마 덤프 리허설

R2 는 "현재 `models.py` 로 만든 스키마"를 baseline 으로 쓴다. 운영 실물과 미세하게 다를 수
있다(과거 수동 DDL·`ensure_schema.py` 흔적). 최고 정밀도가 필요하면 운영 스키마를
**읽기 전용으로** 떠서 쓴다.

```bash
export PATH="/c/Program Files/PostgreSQL/17/bin:$PATH"     # 운영 PG 17.10 → 클라이언트도 17
SNAP=/c/tmp/prod_schema_$(date +%Y%m%d).sql
pg_dump --schema-only --no-owner --no-privileges "$PRODUCTION_DATABASE_PUBLIC_URL" > "$SNAP"

DB=foms_test_promo_prodshape
psql -h 127.0.0.1 -p 5441 -U postgres -d postgres -c "CREATE DATABASE \"$DB\";"
psql -h 127.0.0.1 -p 5441 -U postgres -d "$DB" -f "$SNAP"

export DATABASE_URL="postgresql+psycopg2://postgres@127.0.0.1:5441/$DB"
psql -h 127.0.0.1 -p 5441 -U postgres -d "$DB" -c "SELECT version_num FROM alembic_version;"
#   → merge_prod_drawq 여야 한다(덤프에 포함된다)
alembic upgrade head
psql -h 127.0.0.1 -p 5441 -U postgres -d "$DB" -c "SELECT version_num FROM alembic_version;"
#   → merge_drawq_naverfail
alembic downgrade merge_prod_drawq        # S4 롤백 2번 경로 실증
alembic upgrade head
psql -h 127.0.0.1 -p 5441 -U postgres -d postgres -c "DROP DATABASE \"$DB\";"
```

- `pg_dump --schema-only` 는 **읽기만** 한다. 운영 데이터 행은 나오지 않는다.
- 그래도 운영 DSN 을 로컬에서 쓰는 것이므로 **사용자 승인 항목**이다(§9 D4).
- `naver_relation_00` 은 백필 UPDATE 를 포함하지만 대상이 `external_order_links` 이고
  운영엔 그 테이블 행이 0이라 무동작이다.

---

## 7. 당일 머지 제약 — 왜 하루면 무효인가

### 7.1 원인

이 설계의 **모든 전제가 "그때의 tip"에 매달려 있다**:

| 전제 | 깨뜨리는 사건 |
|---|---|
| 운영 stamp = `merge_prod_drawq` | 타 세션이 운영에 **마이그레이션을 동반한 승격**을 하면 stamp 가 앞으로 간다 → §3.1·§3.3·§4 전부 다시 |
| deploy head = `merge_drawq_naverfail` | 타 세션이 deploy 에 **새 마이그레이션**을 올리면 head 가 바뀌고, 잘못하면 이중 head |
| 미승격 = 463 커밋 | 매 시간 늘어난다. §8 의 위험 계산이 낡는다 |
| `assort_00`·`notifrole_00` 부모 | 타 세션이 또 cherry-pick 하며 `down_revision` 을 고치면 제3의 계보 |

**오늘 반나절의 실측이 그 증거다**: blockers 문서가 쓰인 시점(08-24 오전)과 이 문서를
쓰는 시점(19:34 KST) 사이에 운영 tip 이 `d5b44d87` → `e849927e` 로, deploy tip 이
`b085569d` → `a8ded306` 으로 움직였고 미승격 커밋이 440 → 463 으로 늘었다.
원장의 `#113`·`#121` 연속 무효, PR `#133` 무효도 전부 같은 패턴이다.

### 7.2 시간 예산 (S0 착수 → S4 완료 **4시간 이내**)

| 단계 | 예산 | 누적 |
|---|---|---|
| S0 사전 게이트 | 30분 | 0:30 |
| E1~E6 편집 | 20분 | 0:50 |
| R0+R1+R2 실증 | 40분 | 1:30 |
| R3 PG 전수 + smoke | 40분 | 2:10 |
| S1 커밋 + deploy push + CI | 30분 | 2:40 |
| S2 스테이징 확인 | 20분 | 3:00 |
| S3 승격 PR + 승격 트리 재검증 | 30분 | 3:30 |
| S4 운영 배포 + S5 확인 | 30분 | 4:00 |

**4시간을 넘기면 S0 부터 다시 한다.** 걸치기(오늘 설계 → 내일 실행)는 금지다.

### 7.3 중간에 타 세션이 승격했을 때 재확인 체크리스트

각 단계 진입 시 `git ls-remote` 로 tip 이동을 감지했다면:

- [ ] **C1** 운영 `alembic_version` 재조회. `merge_prod_drawq` 가 아니면 → **이 문서 무효.**
      §3.1 을 새 stamp 로 다시 그리고 §4 의 E4(체인 진입점)를 새 stamp 로 바꾼다.
- [ ] **C2** `git diff --name-only origin/production origin/deploy -- migrations/versions/`
      → 13개보다 늘었으면 새 마이그레이션이 끼어든 것. 어느 계보에 붙었는지 확인하고
      §3.3 그래프에 편입한다(head 1개 유지).
- [ ] **C3** `assort_00`·`notifrole_00` 의 양쪽 `down_revision` 재확인
      (`git show origin/production:<파일> | grep down_revision` vs `origin/deploy`).
      값이 §4 표와 다르면 제3의 계보가 생긴 것 → 착수 중단, 사용자 확인.
- [ ] **C4** 미승격 커밋 수 재계수 → §8 의 판단이 유효한지 재확인.
- [ ] **C5** 승격 **워크트리 안에서** `test_alembic_single_head` 재실행.
      브랜치에서는 단일 head 인데 승격 트리에서만 이중 head 가 되는 사고가 실제로 있었다.
- [ ] **C6** 인벤토리 3종(`foms_failopen_inventory.json` 등)이 승격 트리에서 덮어써졌는지
      확인 — 얽혔으면 **함께 승격하지 말고 승격 트리에서 재생성**한다.
- [ ] **C7** 운영 `requirements.txt` 와 deploy 의 diff 재확인(현재 차이 없음. 있으면
      승격 후 운영만 import 실패하는 드리프트 사고 계열).

> **무출력을 곧바로 '부재'로 읽지 마라.** 이 체크리스트의 여러 확인은 "매치가 **없어야**
> 정상"인 검사다(운영 `models.py` 에 신규 3객체가 없다 등). 그런 검사는 명령이 잘못
> 적혀도 똑같이 무출력이라 **절대 red 가 되지 않는다** — 실제로 이 문서 초안의 부록 A
> 3줄이 `grep -n "A|B|C"`(`-E` 누락)라서, 3객체가 **전부 들어 있는** `origin/deploy` 에
> 대해서도 무출력이었다. 판정 전에 반드시 **대조군**(매치가 나와야 하는 쪽, 보통
> `origin/deploy`)에서 같은 명령이 매치를 내는지 확인하고 나서 '부재'라고 적어라.

---

## 8. 승격 범위 — 463 커밋 전량 vs 네이버 체인만

프로젝트 규칙: **"세션 자기 커밋 cherry-pick 이 기본, 전체 머지는 사용자 명시 시에만."**
따라서 기본값은 B 이고, A 는 사용자가 "전체 푸쉬"라고 명시해야 열린다.

### 실측 규모

```
미승격 커밋         463
건드린 파일         330
미승격 마이그레이션  13개 파일 (§4 표의 6개 + 무변경 7개)
네이버 관련 커밋      99  (foms/services/integrations/, foms/web/admin/naver_ingest.py,
                          templates/admin/, migrations/versions/naver*|asaxis|orderreason)
```

### 선택지 비교

| | **A. 전량 승격** (463) | **B. 네이버 체인만 cherry-pick** (~99) | **C. 마이그레이션만 먼저** (S1 커밋 1개) |
|---|---|---|---|
| 스키마 결과 | 동일(9 DDL) | 동일(9 DDL) | 동일(9 DDL) |
| cherry-pick 충돌 | **틀린 칸이었다 — 2026-08-24 실측 25개 파일 충돌.** 승격이 cherry-pick 이라 같은 수정이 deploy·production 에 다른 SHA 로 있고 git 이 전부 충돌로 낸다(deploy 에 없는 운영 커밋 74개). 그중 14개가 타 세션 파일이다 | **높음** — 99커밋이 330파일 중 일부만 건드리고 나머지는 운영 기준과 어긋난다 | 없음(13파일 중 6개, 독립) |
| 미검증 코드 유입 | **463커밋 전부** — 타 세션 미검증분 포함 | 99커밋 | **0** (DDL 만) |
| 코드↔스키마 정합 | ✅ 완전 | ⚠️ **깨진다** — `models.py` 는 코드 커밋에 딸려 오는데, 네이버 외 커밋이 만든 모델 변경이 빠지면 ORM↔스키마 불일치 | ⚠️ **의도적으로 깨진다** — 스키마엔 컬럼이 있고 `models.py` 엔 없다(무해: 여분 컬럼은 SELECT 절에 안 들어간다) |
| 롤백 난이도 | 높음(463커밋 revert) | 중간 | **낮음**(1커밋 revert + downgrade) |
| 이번 목표 달성 | ✅ 네이버 운영 가동 | ✅ | ❌ 코드는 안 간다 |
| 프로젝트 규칙 | **사용자 명시 필요** | 기본 | 기본 |

### 각 안의 실제 위험

**A(전량)** — 위험의 본체는 alembic 이 아니라 **463커밋의 코드**다. 그중 상당수가 타
세션이 스테이징에서만 검증한 것이다. 승격 후 460+ 커밋을 개별 revert 하는 것은 현실적으로
불가능하므로, 롤백은 **머지 커밋 1개의 revert**로 처리한다
(`git push --force` 는 훅이 차단한다 — 되감기 시도 금지).

**B(네이버만 99)** — 겉보기엔 안전해 보이지만 **가장 위험하다.** 이유:
`models.py`·`app.py`·공용 서비스·템플릿은 네이버 외 커밋도 함께 고친 **핫파일**이다.
99커밋만 골라 cherry-pick 하면 그 파일들에서 충돌이 나고, 충돌을 "임의로 해결"하는
순간 운영에만 존재하는 제4의 코드 상태가 생긴다. 프로젝트 규칙이 정확히 이것을 금지한다 —
**cherry-pick 충돌 = 타 세션 의존 신호 → 임의 해결 금지, 사용자 확인.**
99커밋 × 330파일 규모에서 충돌 0 을 기대할 근거가 없다.

**C(마이그레이션만)** — 이번 목표(네이버 운영 가동)를 달성하지 못한다. 그러나
**A 의 전처리로서 가치가 크다**: 스키마를 먼저 안전하게 올려 두면 치명 1(`as_axis_status`)이
사라지고, 뒤이은 코드 승격은 순수한 코드 리스크만 남는다. 스키마 여분 컬럼은 무해하다 —
운영 `models.py` 에 `as_axis_status`·`ExternalOrderLink`·`OrderChangeReason` 이 **없음을**
`git show origin/production:models.py` 로 확인했으므로 ORM 이 그 컬럼을 SELECT 하지 않는다.

### 권고

> **C → A 2단 승격.** 먼저 S1 커밋(마이그레이션 재직렬화)만 운영에 올려 스키마를 앞세우고
> (롤백 쉬움·코드 위험 0), 그것이 green 인 것을 확인한 뒤 **같은 날 안에** A(전량)를
> 올린다. B(부분 cherry-pick)는 **권하지 않는다** — 이 규모에서는 충돌 해결이 새 사고의
> 원천이다.
>
> 다만 **A 는 프로젝트 규칙상 사용자 명시 승인 없이는 열 수 없다**(§9 D5).
> 사용자가 A 를 거부하면 남는 실질 선택지는 **"이번엔 승격하지 않는다"** 이다 —
> B 를 차선책으로 삼지 마라.

---

## 9. 사용자 승인이 필요한 지점

실행 전에 사람이 반드시 결정해야 하는 항목. **하나라도 미결이면 S1 에 들어가지 않는다.**

| # | 결정 항목 | 선택지 | 기본값(권고) | 왜 사람이 정해야 하나 |
|---|---|---|---|---|
| **D1** | 승격을 **오늘** 착수하는가 | 오늘 4시간 완주 / 다음 기회 | — | §7.2 시간 예산을 감당할 시간대인지는 사용자만 안다. 걸치기 금지 |
| **D2** | 재직렬화 커밋(S1)을 **deploy 에 먼저** 랜딩하는 것에 동의 | 예 / 아니오 | 예 | 스테이징 계보를 건드린다 = 타 세션 작업에 영향 |
| **D3** | 스테이징·운영 `alembic_version` 조회용 DSN 제공 | 제공 / 생략 | 제공 | §4.2 의 두 stamp 가정을 실증하는 유일한 방법 |
| **D4** | R4(운영 스키마 `pg_dump`) 실행 여부 | 실행 / R2 만 | R2 만 | 운영 DSN 을 로컬에서 사용. 읽기 전용이나 승인 대상 |
| **D5** | **승격 범위** | A 전량 463 / B 네이버 99 / C 마이그레이션만 / 안 함 | **C → A** | 프로젝트 규칙상 A 는 **사용자 명시 필수**. B 는 충돌 위험으로 비권고 |
| **D6** | 승격 후 운영에서 네이버 기능을 **켤지** | 지금 켠다 / 닫아 둔다 | **닫아 둔다** | 켜려면 `NAVER_COMMERCE_CLIENT_ID`/`SECRET`·`FOMS_NAVER_SYNC_ENABLED`·`FOMS_NAVER_WORKBENCH_ENABLED` 를 운영에 넣어야 한다 = 실주문 자동 생성 시작 |
| **D7** | S4 실패 시 **downgrade 권한** 사전 위임 | 위임 / 매번 확인 | 매번 확인 | `naver_link_00` downgrade 는 `external_order_links` 를 DROP 한다(§S4 롤백 2번 경고) |
| **D8** | 운영 배포 시간대 | 업무 시간 / 야간 | 야간 권고 | predeploy 가 fail-closed 라 최악도 "배포 안 됨"이지만, S4 롤백은 서비스 영향이 있다 |

---

## 10. 미확인 항목·잔여 위험 (정직한 목록)

이 문서가 **git 만으로** 확인한 것과, **확인하지 못한 것**을 구분해 둔다.

| # | 항목 | 상태 | 해소 방법 |
|---|---|---|---|
| U1 | 운영 `alembic_version` 이 **지금도** `merge_prod_drawq` 인가 | ✅ **해소 (2026-08-24 20:54 KST 실조회)** — 운영 DB 읽기 전용 1회 조회: `alembic_version = ['merge_prod_drawq']` **단일 행**, `orders.as_axis_status` 컬럼 **0개**, `external_order_links`·`order_change_reasons` 둘 다 `None`. 설계 전제와 정확히 일치 | 완료 |
| U2 | 스테이징 `alembic_version` = `merge_drawq_naverfail` 인가 | ✅ **해소 (실조회)** — `['merge_drawq_naverfail']` = 설계 head. 재직렬화 후 스테이징 `upgrade head` 는 **무동작**이다(§4.3 의 '의도적 허구'가 무해한 이유가 실측으로 확인됨) | 완료 |
| U3 | 운영 web 서비스가 실제로 `railway.toml` 의 `preDeployCommand` 를 쓰는가 | **미확인**(대시보드 덮어쓰기 가능) | S0-1. **아니면 §1.2 의 안전망이 전부 무효** |
| U4 | `tools/ops/ensure_schema.py` 가 `upgrade head` 이후 무엇을 손보는가 | ✅ **해소** — `designer_drawing_extractions`·`designer_extraction_candidates`·`designer_design_cases` 에 `ADD COLUMN IF NOT EXISTS` 5개 + 레거시 stamp 보정(`designer_eval_snapshots` → `designer_wdplanner_v2_fix`). **이번 체인 객체(네이버·asaxis·orderreason)와 겹치는 것이 0개**이고, 운영 stamp 가 `merge_prod_drawq` 라 stamp 보정 UPDATE 는 no-op | 완료 |
| U5 | `merge_drawq_naverfail` 의 중복 부모(`drawqueue_00` 이 `naverfail_00` 의 조상이면서 동시에 직접 부모)를 alembic 이 문제없이 처리하는가 | ✅ **해소** — R0 실행: `heads = ['merge_drawq_naverfail']`(1개) · `count = 85` · dangling 0 · `test_alembic_single_head` 1 passed. R2 에서 실제 `downgrade`/`upgrade` 도 이 노드를 정상 통과했다 | 완료 |
| U6 | R2 의 `downgrade merge_prod_drawq` 가 `create_all` DB 에서 완주하는가 | ✅ **해소 (2026-08-24 실행, PG17.9 로컬 레인 5441)** — `ROUNDTRIP_OK`. 컬럼 778 → 754 로 실제로 걷혔고(무의미한 no-op 왕복이 아님), `upgrade head` 후 **컬럼 유실 0 · 타입/nullable/default 드리프트 0 · 인덱스 유실 0**. 2회차 왕복도 통과. R3(`tests/postgres` 전수) **747 passed** | 완료 |
| U7 | nav 뱃지 fail-open 이 실패 쿼리로 요청 트랜잭션을 오염시켜 후속 쿼리를 연쇄로 죽이는가 | **미확인**(blockers 문서에서도 미확인) | C/A 안에서는 스키마가 먼저 올라가므로 이 경로 자체가 사라진다 |
| U8 | 463커밋 안에 **다른 세션의 미완결 작업**이 있는가 | **미조사** | D5 에서 A 를 고를 때 사용자가 감수하는 위험 |

---

## 부록 A — 이 문서가 실행한 명령 전량 (재현용)

```bash
pwd
git fetch origin --quiet
git ls-remote origin refs/heads/production refs/heads/deploy
git rev-parse origin/deploy origin/production
git rev-list --count origin/production..origin/deploy
git diff --name-only origin/production origin/deploy -- migrations/versions/
git diff --name-only origin/production...origin/deploy | wc -l
git log --oneline origin/production -10
git log --oneline origin/deploy     -- migrations/versions/assort_00_attachment_sort_order.py
git log --oneline origin/production -- migrations/versions/assort_00_attachment_sort_order.py
git log --oneline origin/deploy     -- migrations/versions/notifrole_00_notification_target_role.py
git log --oneline origin/production -- migrations/versions/notifrole_00_notification_target_role.py
git show origin/production:migrations/versions/merge_prod_drawqueue_notifrole.py
git show origin/production:models.py    | grep -nE "as_axis_status|ExternalOrderLink|OrderChangeReason"
git show origin/production:railway.toml | grep -nE "preDeployCommand|startCommand"
git show origin/production:predeploy.sh | grep -nE "alembic upgrade|ensure_schema"
# 대조군 — 위 셋은 "무출력이 정상"인 검사다. 대조군에서 매치가 나오는지 반드시 함께 본다.
git show origin/deploy:models.py        | grep -cE "as_axis_status|ExternalOrderLink|OrderChangeReason"   # 9 (2026-08-24 실측)
git show origin/production:Procfile
cat Procfile railway.toml predeploy.sh
tail -20 Dockerfile
grep -rn "5441" docs/plans/*.md
```

리비전 그래프 파싱 스크립트는 스크래치패드에만 두었고 저장소에 커밋하지 않았다.

## 부록 B — §3.4 시뮬레이션 재현 스크립트

파일을 고치지 않고 설계 후 그래프를 계산한다. **읽기 전용**(`git ls-tree`/`git show` 만
쓴다). 실행 전 `git fetch origin` 으로 두 ref 를 최신화하고, §7.3 C1~C3 이 통과했는지
먼저 확인해라 — tip 이 움직였으면 이 결과도 낡는다.

```bash
cd /c/tmp/foms-s-naver-ingest   # 또는 승격 워크트리
python - <<'PY'
"""설계 후 alembic 그래프를 시뮬레이션한다(파일 무수정, 읽기 전용).

검증 항목: head 1개 · dangling 0 · 운영 조상집합이 origin/production 과 일치 ·
운영 조상에 네이버/asaxis/orderreason 부재 · 운영 upgrade 위상순서.
"""
import collections
import re
import subprocess


def sh(args: list[str]) -> str:
    """git 출력을 UTF-8 로 디코딩해 돌려준다(cp949 환경 회피)."""
    return subprocess.run(args, capture_output=True, check=True).stdout.decode("utf-8", "replace")


def parse(ref: str) -> dict[str, tuple[str, ...]]:
    """ref 의 migrations/versions 를 읽어 {revision: (부모...)} 를 만든다."""
    graph: dict[str, tuple[str, ...]] = {}
    for path in sh(["git", "ls-tree", "-r", "--name-only", ref, "migrations/versions/"]).splitlines():
        if not path.endswith(".py"):
            continue
        src = sh(["git", "show", f"{ref}:{path}"])
        rev = re.search(r"^revision(?::[^=\n]+)?\s*=\s*(.+)$", src, re.M)
        if not rev:
            continue
        name = rev.group(1).split("#")[0].strip().strip("'\"")
        down = re.search(r"^down_revision(?::[^=\n]+)?\s*=\s*", src, re.M)
        parents: tuple[str, ...] = ()
        if down:
            rest = src[down.end():]
            first = rest.split("\n", 1)[0].strip()
            if first.startswith("("):
                body = re.search(r"\((.*?)\)", rest, re.S).group(1)
                parents = tuple(x.split("#")[0].strip().strip("'\"")
                                for x in body.split(",") if x.split("#")[0].strip())
            elif not first.startswith("None"):
                parents = (first.split("#")[0].strip().strip("'\""),)
        graph[name] = parents
    return graph


def ancestors(graph: dict[str, tuple[str, ...]], node: str) -> set[str]:
    """node 자신을 포함한 조상집합."""
    seen: set[str] = set()
    stack = [node]
    while stack:
        cur = stack.pop()
        if cur in seen or cur not in graph:
            continue
        seen.add(cur)
        stack.extend(graph[cur])
    return seen


deploy = parse("origin/deploy")
prod_graph = parse("origin/production")

graph = dict(deploy)
graph["merge_prod_drawq"] = prod_graph["merge_prod_drawq"]   # E1 파일 복원
graph["assort_00"] = ("asfresh_00",)                         # E2 운영값 복원
graph["notifrole_00"] = ("assort_00",)                       # E3 운영값 복원
graph["naver_link_00"] = ("merge_prod_drawq",)               # E4 재배치
graph["naver_relation_00"] = ("asaxis_00",)                  # E5 재배치
graph["navergroup_00"] = ("naver_relation_00",)              # E6 재배치

children_of = {p for parents in graph.values() for p in parents}
heads = sorted(r for r in graph if r not in children_of)
assert heads == ["merge_drawq_naverfail"], f"head 가 1개가 아니다: {heads}"
assert not (children_of - set(graph)), "부모가 없는 리비전 참조가 있다"

prod_anc = ancestors(graph, "merge_prod_drawq")
assert prod_anc == set(prod_graph), "운영 조상집합이 origin/production 과 다르다"
leaked = sorted(x for x in prod_anc if x.startswith(("naver", "asaxis", "orderreason")))
assert not leaked, f"운영 조상에 미적용 리비전이 샜다: {leaked}"
assert ancestors(graph, heads[0]) == set(graph), "스테이징 조상집합이 전체가 아니다"

todo = set(graph) - prod_anc
indeg = {n: len([p for p in graph[n] if p in todo]) for n in todo}
child_map = collections.defaultdict(list)
for n in todo:
    for p in graph[n]:
        if p in todo:
            child_map[p].append(n)
queue = collections.deque(sorted(n for n, d in indeg.items() if d == 0))
order = []
while queue:
    cur = queue.popleft()
    order.append(cur)
    for nxt in child_map[cur]:
        indeg[nxt] -= 1
        if indeg[nxt] == 0:
            queue.append(nxt)

print(f"리비전 수 {len(graph)} · head {heads} · 운영 조상 {len(prod_anc)}")
print("운영 upgrade 순서:")
for i, name in enumerate(order, 1):
    print(f"  {i:2d}. {name}")
print("GRAPH_OK")
PY
```

**통과 조건**: 마지막 줄 `GRAPH_OK`, 그리고 출력된 10개 순서가 §4.2·§5 S4 와 같을 것.

## 부록 C — 참고 문서

- `docs/plans/2026-08-24-naver-production-promotion-blockers.md` — 차단 사유 실측
  (§1 이 3건 갱신·1건 정정)
- `AGENTS.md` §브랜치·푸시 — 승격 절차 SSOT
- `tests/postgres/test_migration_chain.py` — 왕복 창의 기존 계약(`_ROUNDTRIP_FLOOR = index_ops_00`)
- `tests/domains/test_alembic_single_head.py` — 단일 head 게이트(ALEMBIC-HEADS-01)
- `tests/postgres/conftest.py` — PG 레인 안전장치(로컬 호스트 강제·`foms_test_` 접두어 강제)
- `predeploy.sh` / `railway.toml` — 운영 마이그레이션 실행 지점(fail-closed)
