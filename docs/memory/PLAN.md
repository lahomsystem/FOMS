# AS대시보드 Staging -> Production 데이터 이관 계획서

**작성일**: 2026-02-23
**작성자**: Grand Develop Master (Virtual CTO)
**목표**: Staging 환경의 AS대시보드 전용 주문 건 중 Production에 없는 데이터를 추출해 완벽하게(상태 포함) 이관.

---

## 1. 요구사항 분석
- **Staging DB**: `postgresql://postgres:jDkSuQDkQZkGZCFmPMOnFoDaXNJebidd@maglev.proxy.rlwy.net:24958/railway`
- **Production DB**: `postgresql://postgres:XMuhzNDZDeBlQStbmUQymJTGQvgIKAVq@yamanote.proxy.rlwy.net:34306/railway`
- **조건 1**: AS대시보드 노출 대상 데이터만 한정 (status in ('AS', 'AS_RECEIVED', 'AS_COMPLETED') 또는 workflow.stage == 'AS')
- **조건 2**: Staging과 Production에 공통으로 존재하는 주문은 이관에서 제외.
- **조건 3**: Production에 없는 Staging 주문을 추출해 상태(status, structured_data, 날짜 등) 보존 하에 Production에 삽입.

---

## 2. 아키텍처 및 데이터 영향도 평가
- **식별자(PK) 충돌 문제**: Staging에서 생성된 주문의 `id`가 이미 Production에 존재할 수 있습니다. 따라서 `id`를 그대로 덮어쓰는 것은 기존 Production 데이터(비-AS 주문 포함)를 손상시킬 수 있어 매우 위험합니다. 
- **공통 주문 판별 기준**: `id`가 다를 수 있으므로 `(customer_name, phone, product)` 또는 `(customer_name, phone, address)`를 복합 키로 사용하여 동일 주문을 판별해야 합니다.
- **관계형 데이터 (연관 테이블)**: 주문(`orders`) 테이블뿐만 아니라 `order_attachments`(첨부파일), `system_build_steps`(시스템 로그), `erp_logs` 등 연관 데이터까지 이관할지 결정해야 "완벽한 상태 보존"이 됩니다.

---

## 3. 구현 방법 (3가지 대안)

### 방법 A: 일회성 Python 마이그레이션 스크립트 작성 (권장)
- **개요**: psycopg2 또는 SQLAlchemy를 사용해 양쪽 DB에 동시 접속하는 Python 스크립트를 작성합니다.
- **장점**: 논리적 비교(고객명+전화번호)가 쉽고, 관계형 데이터(첨부파일 등)의 외래키(`order_id`)를 새 Production `id`에 맞춰 매핑/변경하기 용이합니다.
- **단점**: 스크립트 개발 시간이 약간 소요됩니다.

### 방법 B: SQL 덤프 및 조건부 INSERT (pg_dump + DBeaver/DataGrip)
- **개요**: Staging에서 AS 주문만 `pg_dump`로 SQL화 한 후, Production에서 `INSERT INTO ... ON CONFLICT DO NOTHING` 실행.
- **장점**: 별도 코딩 없이 SQL만으로 빠르게 처리 가능합니다.
- **단점**: `id` 충돌 발생 시 처리가 까다롭고, 공통 데이터 제외 기준을 SQL 조인으로 작성해야 하므로 실수 시 Production 데이터 오염 위험이 높습니다.

### 방법 C: CSV/Excel 추출 후 FOMS 업로드 기능 활용
- **개요**: Staging에서 AS 데이터를 엑셀로 다운로드 후 Production의 "주문 추가" 기능으로 업로드.
- **장점**: 가장 안전하며 Production DB를 직접 건드리지 않습니다.
- **단점**: `structured_data` 등 ERP Beta의 복잡한 JSON 상태나 첨부파일이 완벽하게 이관되지 않습니다. (요구사항 3 충족 실패 가능성)

---

## 4. 추천안 및 이유 (The GDM Way)
**추천안: 방법 A (일회성 Python 마이그레이션 스크립트 작성)**
- **이유**: "주문 건 상태까지 완벽하게 넣으려고 해"라는 요구사항을 충족하려면 `structured_data`, `status`, 날짜 필드들을 그대로 복제해야 합니다. Staging과 Production 간 `order_id` 충돌을 피하기 위해 새 `id`를 발급받되, 기존 데이터 구조를 그대로 복사하는 것은 Python 스크립트(Pandas/SQLAlchemy)가 가장 안전하고 확실합니다.

---

## 5. 진행 단계 (실행 계획)
1. **분석**: Staging DB에서 AS 주문 총 건수 및 식별 기준 확립 (고객명+연락처 기준).
2. **스크립트 작성**: `scripts/migrate_as_orders.py` 작성.
   - Staging DB 연결 -> AS 주문 조회.
   - Production DB 연결 -> 기존 AS 주문 조회.
   - 교집합 제외(고객명+전화번호 기준).
   - 남은 Staging 주문을 Production DB에 `INSERT` (단, `id`는 자동 증가 적용).
   - 연관된 `order_attachments`가 있다면 새 `order_id`로 변경하여 `INSERT`.
3. **Dry-Run (모의 실행)**: 실제 삽입 없이 로그로 몇 건이 이관되는지 출력.
4. **실제 반영**: 사용자 승인 후 스크립트 실행.

---

사용자님, 위 **방법 A(Python 스크립트 기반 이관)** 로 진행하는 것에 동의하시는지요? 
승인해주시면 `migrate_as_orders.py` 스크립트를 작성하고 모의 실행(Dry-Run) 결과를 보여드리겠습니다.