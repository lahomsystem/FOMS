# 배포 노트 (쉬운 한글)

> deploy 브랜치에 올릴 때마다, **뭘 했는지 누구나 알 수 있게** 쉬운 말로 적어 둡니다.

---

## Railway production 브랜치 설정 (실 서비스)

**실제 서비스**는 `production` 브랜치에서 배포합니다.

1. [Railway 프로젝트](https://railway.com/project/cbe0af66-875b-460c-88f6-780dd705f45c) 접속
2. **FOMS 웹 서비스** 클릭 → **Settings**
3. **Source** 또는 **Repository** 섹션에서 **Branch**를 `production` 으로 변경
4. 저장 후 `production` 브랜치에 푸시할 때마다 자동 배포

참고: [Railway GitHub Autodeploys](https://docs.railway.app/guides/github-autodeploys)

---

## Staging → Production 설정 복제 (Worker/Replica 동일화)

**스테이징** [project/65ffbdc5-9bdf-4c17-a8d7-b1bc3615143a](https://railway.com/project/65ffbdc5-9bdf-4c17-a8d7-b1bc3615143a) 에 적용된 구성을 **프로덕션** [project/cbe0af66-875b-460c-88f6-780dd705f45c](https://railway.com/project/cbe0af66-875b-460c-88f6-780dd705f45c) 에 그대로 복제할 때:

### Web 서비스
| 항목 | 스테이징 값 | 프로덕션에 적용 |
|------|-------------|-----------------|
| Replica 수 | 2 | Settings → Replicas = 2 |
| Branch | deploy 또는 동일 | production |
| Start Command | `sh start.sh` (railway.toml) | 동일 |
| gunicorn workers | `-w 2` (start.sh) | 코드에 이미 반영 |
| gunicorn timeout | `--timeout 120` (초) | 요청이 120초 넘으면 워커 종료. 대용량 업로드는 Direct Upload(R2 presigned) 사용 권장. |

### Worker 서비스
| 항목 | 스테이징 값 | 프로덕션에 적용 |
|------|-------------|-----------------|
| 서비스 존재 | Worker 서비스 있음 | 없으면 생성 |
| Config Path | `railway-worker.toml` | Settings → Config Path = railway-worker.toml |
| Start Command | `rq worker default --url $REDIS_URL` | Procfile/railway-worker.toml |
| 환경변수 | `USE_RQ_WORKER=1`, `REDIS_URL` | 동일 설정 |
| GitHub 연결 | 같은 repo, branch | 같은 repo, branch = production |

### 절차
1. 프로덕션 프로젝트 열기
2. Web 서비스: Replicas 2로 설정 (Settings → Scale)
3. Worker 서비스: 스테이징과 동일하게 생성·설정 (Config Path, USE_RQ_WORKER=1, REDIS_URL)
4. 배포 후 로그에서 `rq worker default` 기동 확인

---

## 2026-02-19 (이번 배포)

### 뭘 했나요?
- **DB 관리 스크립트 비밀번호 환경변수화 (NEXT-004)**  
  `scripts/db_admin.py`에서 관리자(admin) 계정 기본 비밀번호를 **환경변수**로 바꿨습니다.
  - **환경변수**: `FOMS_ADMIN_DEFAULT_PASSWORD` (설정 안 하면 예전처럼 기본값 사용)
  - 프로덕션에서는 이 값을 꼭 설정해 두는 것을 권장합니다.

### 사용자 입장에서는?
- **바뀐 거 없음.** 로그인·관리자 기능은 그대로입니다.

---

## 2026-02-18 (이전 배포)

### 뭘 했나요?
- **ERP 화면 전부 역할별로 나눔 (erp.py 슬림)**  
  예전에 ERP 한 파일에 몰려 있던 **대시보드 화면 6개**를 각각 따로 파일로 빼 두었습니다.

  | 화면 | 새 파일 | 설명 |
  |------|---------|------|
  | 메인 대시보드 | erp_dashboard.py | ERP 프로세스 대기·진행 현황 |
  | 도면 작업실 | erp_drawing_workbench.py | 도면 목록·상세 |
  | 실측 대시보드 | erp_measurement_dashboard.py | 실측 일정·담당자 |
  | 출고 대시보드 | erp_shipment_page.py | 시공 일정·출고일지 |
  | AS 대시보드 | erp_as_page.py | AS 접수·완료 목록 |
  | 생산 대시보드 | erp_production_page.py | 제작대기·제작중 |
  | 시공 대시보드 | erp_construction_page.py | 시공대기·시공중·완료 |

  공통으로 쓰는 **필터·권한·표시 로직**도 `services/` 폴더로 빼 두었습니다.  
  → **화면·기능은 그대로**고, 코드만 나눠서 관리하기 쉬워졌습니다.

### 사용자 입장에서는?
- **바뀐 거 없음.**  
  ERP 메뉴에서 들어가는 모든 대시보드가 이전이랑 똑같이 동작합니다.

### 개발자 입장에서는?
- `apps/erp.py`가 **40줄**로 줄었습니다 (예전 2천 줄 넘던 것에서 분리 완료).
- 새 Blueprint: `erp_dashboard_bp`, `erp_drawing_workbench_bp`, `erp_measurement_dashboard_bp`, `erp_shipment_page_bp`, `erp_as_page_bp`, `erp_production_page_bp`, `erp_construction_page_bp`
- 공통: `services/erp_display.py`, `services/erp_permissions.py`, `services/erp_template_filters.py`

---

## 2026-02-17 (이전 배포)

### 뭘 했나요?
- **Phase 4 ERP 모듈 분리 (4-2 ~ 4-5c)**  
  ERP 한 덩어리 안에 있던 기능들을 **역할별로 나눠서** 별도 파일로 분리했습니다.

  | 구분 | 분리된 모듈 | 내용 |
  |------|-------------|------|
  | 4-2 | 출고 설정 | 시공 시간·도면 담당자·시공자·현장 주소 설정 |
  | 4-3 | 실측 | 실측 정보 업데이트, 실측 경로 조회 |
  | 4-4 | 지도·주소·유저 | 지도 데이터, 주소 업데이트, 유저 목록 |
  | 4-5a | 주문 Quick | 주문 빠른 검색, 요약 정보, 상태 조회 |
  | 4-5b | 도면 전달/취소 | 도면 전달 요청, 전달 취소 |
  | 4-5c | 도면 창구 업로드 | 도면 창구에서 파일 업로드 |

  → 화면·기능은 그대로고, 코드 관리만 더 쉬워졌습니다.

### 사용자 입장에서는?
- **바뀐 거 없음.**  
  ERP 대시보드, 실측, 출고, 도면 작업, 주문 검색 등 모두 이전이랑 똑같이 동작합니다.

### 개발자 입장에서는?
- 새 Blueprint: `erp_measurement_bp`, `erp_map_bp`, `erp_orders_quick_bp`, `erp_orders_drawing_bp`
- 파일: `apps/api/erp_measurement.py`, `erp_map.py`, `erp_orders_quick.py`, `erp_orders_drawing.py`
- `apps/erp.py`에서 해당 라우트 제거로 약 1,400줄 감소 (3,578줄 수준)

---

## 2026-02-16 (이전 배포)

### 뭘 했나요?
- **알림 기능 코드 정리 (Phase 4-1)**  
  예전에는 ERP 화면 쪽 코드 한 덩어리 안에 알림(목록 보기, 읽음 처리, 배지 숫자 등)이 같이 들어 있었습니다.  
  이번에 **알림만 따로 파일로 빼서** 두었습니다.  
  → 화면/기능은 그대로고, 나중에 수정·확장하기 쉬워졌습니다.

### 사용자 입장에서는?
- **바뀐 거 없음.**  
  알림 보기, 읽음 처리, 배지 숫자 모두 이전이랑 똑같이 동작합니다.

### 개발자 입장에서는?
- 알림 관련 API가 `apps/api/notifications.py` 한 파일로 모였습니다.
- ERP 메인 코드(`apps/erp.py`)가 그만큼 짧아져서 관리가 조금 수월해졌습니다.

---

## 2026-02-16 (ERP 이름 변경)

### 뭘 했나요?
- **이름 정리: "ERP Beta" → "ERP"**  
  메뉴/화면에서 쓰이던 "ERP Beta"라는 이름을 **"ERP"**로 통일했습니다.  
  (실제 기능은 그대로입니다.)

### 사용자 입장에서는?
- 메뉴나 화면에서 "ERP"라고만 보일 수 있습니다. 쓰는 방법은 같습니다.

---

*새로 배포할 때마다 위에 새 날짜로 "뭘 했나요 / 사용자 입장 / 개발자 입장"을 추가하면 됩니다.*

**커밋 메시지:** Windows에서 한글이 깨질 수 있으므로, 푸시용 커밋은 영문으로 적는 것을 권장합니다. 예: `deploy: ERP split and 2026-02-18 deploy notes`
