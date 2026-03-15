# ERP 대시보드 개선 Phase A/B/C/D 최종 GDM 감리 보고서

**작성일**: 2026-03-15  
**갱신일**: 2026-03-15 (현재 상황 반영)  
**감리자**: Grand Develop Master (GDM)  
**계획서**: docs/plans/2026-03-15-erp-dashboard-audit-performance-quality-plan.md  
**대상**: Phase A, B, C, D 실행 결과 및 Phase V 회귀 검증

---

## 1. 요약

| 구분 | 결과 |
|------|------|
| **계획서 vs 실행 1:1 대조** | Phase A/B/C/D 핵심 항목 대부분 완료, B-5/B-6/B-7·C-3·Phase V 미수행 |
| **GDM Findings 후속 반영** | Phase A 2건, Phase C 1건, Phase D 3건(print, D-1) 반영 완료. Phase D 5건 미반영 |
| **Phase 간 의존성·순서** | A→B→C→D 순서 준수 |
| **C 마이그레이션 Railway** | ✅ **완료** (Production DATABASE_URL로 alembic upgrade head 실행, phase_c_indexes 적용) |
| **Residual Risks** | 10건 통합 (C 마이그레이션·D-1·print 해소 반영) |
| **Phase V 회귀 검증** | V-1 자동만 수행, V-2/V-3/V-4 미수행 |
| **최종 판정** | **조건부 통과** — 운영 배포 전 Phase V 수동 검증 및 except: pass 2건 보완 권장 |

---

## 2. 계획서 vs 실행 보고서 1:1 대조

### 2.1 Phase A — 데이터 무결성/트랜잭션 버그

| 계획 항목 | 실행 상태 | 비고 |
|-----------|-----------|------|
| A-1 JSONB flag_modified + deepcopy | ✅ 완료 | erp_orders_drawing, erp_orders_revision 3곳 |
| A-2 workflow.get('stage') 수정 | ✅ 완료 | erp_policy.py |
| A-3 세션 롤백 (회귀 확인) | ✅ 확인 | 이미 올바른 패턴 |
| A-4 무음 실패 제거 | ✅ 완료 | erp_orders_structured, erp_orders_blueprint |

**누락/미완료**: 없음.

---

### 2.2 Phase B — 성능 저하 개선

| 계획 항목 | 실행 상태 | 비고 |
|-----------|-----------|------|
| B-1 실측 Summary API 과다 로드 | ⏭️ 생략 | mine 의미 확정 전제 필요 (계획서 착수 전 전제) |
| B-2 ERP 대시보드 User N+1 | ✅ 완료 | pre-pass + user_map |
| B-3 시공 첨부 삭제 순차 요청 | ✅ 완료 | Promise.all 병렬화 |
| B-4 출고 대시보드 정렬/색상 중복 | ✅ 완료 | fetch .then 1회, DOMContentLoaded/setTimeout 제거 |
| B-5 대형 인라인 스크립트 분리 | ❌ 미수행 | 계획서: common_utils.js 기준 import 정리 전제 |
| B-6 요청 경로 DDL + 별도 commit | ❌ 미수행 | erp_orders_structured _record_build_step |
| B-7 JSONB ilike 풀스캔 | ❌ 미수행 | 검색 필드 범위 확정 전제 |

**누락/미완료**: B-5, B-6, B-7 (계획서상 전제 조건 또는 별도 커밋 대상).

---

### 2.3 Phase C — 쿼리 기준/인덱스 정렬

| 계획 항목 | 실행 상태 | 비고 |
|-----------|-----------|------|
| C-0 soft-delete 기준 통일 | ✅ 완료 | Order.active_filter() 25+ 파일 적용 |
| C-1 active 주문 partial index | ✅ 마이그레이션 작성 | ix_orders_active_id (CONCURRENTLY) |
| C-2 JSONB GIN 인덱스 | ✅ 마이그레이션 작성 | ix_orders_structured_data_gin |
| C-3 substring 검색 인덱스 | ⏸️ 보류 | 검색 필드 범위 확정 후 진행 (계획서 443행) |

**누락/미완료**: C-3 보류(계획서 전제 미충족). **마이그레이션 실제 실행**: ✅ **Railway/Production에서 `alembic upgrade head` 실행 완료** (phase_c_indexes 적용, ix_orders_active_id, ix_orders_structured_data_gin).

---

### 2.4 Phase D — 코드 품질 및 리팩토링

| 계획 항목 | 실행 상태 | 비고 |
|-----------|-----------|------|
| D-1 query().get() 제거 | ✅ 완료 | 6개 파일 db.get(Order, order_id) 적용 |
| D-2 api_put_order_structured 책임 분리 | ✅ 완료 | 4개 helper 함수 |
| D-3 API 응답 형식 점진 통일 | ✅ 완료 | message 추가, error 호환 |
| D-4 중복 유틸 통합 | ✅ 완료 | erp_utils.ensure_path, common_utils.js |
| D-5 매직 문자열 상수화 | ✅ 완료 | constants.py |
| D-6 traceback 인라인 → logger | ✅ 완료 | erp_shipment_settings 등 |
| D-7 storage.get_file_type public | ✅ 완료 | 3개 파일 교체 |
| D-8 인라인 스타일 → CSS 클래스 | ✅ 완료 | erp-toast-container, erp-col-resizer |

**누락/미완료**: 계획서 Phase D 항목은 모두 완료. Phase D Code Review Findings 5건 미반영(§3.4 참조).

---

### 2.5 Phase V — 회귀 검증 게이트

| 계획 항목 | 실행 상태 | 비고 |
|-----------|-----------|------|
| V-1 자동 검증 (pytest -q) | ✅ 수행 | Phase A/B 보고서 기준 5 passed |
| V-2 쓰기 없는 스모크 (GET/렌더링) | ❌ 미수행 | /erp/dashboard, /erp/measurement 등 5경로 |
| V-3 수동 핵심 시나리오 (8항목) | ❌ 미수행 | 도면 전달/취소/수정요청 등 |
| V-4 tools/smoke 스크립트 | ❌ 미수행 | 공유 DB에서 실행 금지 주의 |

**누락/미완료**: V-2, V-3, V-4 전부 미수행.

---

## 3. 각 Phase GDM 감리 Findings → 후속 수정 반영 여부

### 3.1 Phase A GDM Findings

| Finding | 심각도 | 반영 여부 | 근거 |
|---------|--------|-----------|------|
| api_blueprint_complete 잘못된 세션 롤백 | high | ✅ 반영 | Phase A 실행 보고서 107행: db=None + if db is not None 패턴 |
| erp_orders_drawing rollback 실패 무음 처리 | low | ✅ 반영 | Phase A 실행 보고서 108행: logger.warning 추가 |

---

### 3.2 Phase B GDM Findings

| Finding | 심각도 | 반영 여부 | 근거 |
|---------|--------|-----------|------|
| B-4 fetch 실패 시 정렬/색상 미적용 | low | ⏸️ 유지 | 계획서 의도대로 현 상태 유지. 필요 시 검토 |

---

### 3.3 Phase C GDM/Code Review Findings

| Finding | 심각도 | 반영 여부 | 근거 |
|---------|--------|-----------|------|
| personal_board._recent_work active_filter 미적용 | low | ✅ 반영 | Phase C GDM 감리: Order.active_filter() 추가 |
| CONCURRENTLY 마이그레이션 env.py 트랜잭션 | medium | ✅ 완료 | Railway/Production에서 alembic upgrade head 실행 완료 |
| C-2 GIN 인덱스 partial 조건 부재 | low | ⏸️ 보류 | 쿼리 패턴 분석 후 필요 시 별도 마이그레이션 |

---

### 3.4 Phase D Code Review Findings

| Finding | 심각도 | 반영 여부 | 비고 |
|---------|--------|-----------|------|
| print 디버깅 (erp_orders_revision) | high | ✅ 반영 | 코드베이스 검증: print 없음, logger 사용 |
| D-1 erp_orders_revision query().first() 2곳 | medium | ✅ 반영 | db.get(Order, order_id) 4곳 적용 (57, 187, 270, 336행) |
| except Exception: pass (storage.py:246) | high | ❌ 미반영 | logger.warning/debug + fallback 권장 |
| except Exception: pass (chat/routes.py:105) | high | ❌ 미반영 | logger.warning/debug + fallback 권장 |
| safeJsonFetch HTTP 에러 미검증 | medium | ❌ 미반영 | res.ok 검증 또는 throw |
| ensure_path 중복 (orders.py vs erp_utils) | medium | ❌ 미반영 | erp_utils.ensure_path 통합 검토 |
| erp_orders_completion ensure_path 미사용 | low | ❌ 미반영 | ensure_path 패턴 통일 (선택) |
| API 응답 형식 일부 불일치 | low | ❌ 미반영 | error 키 추가 또는 클라이언트 규칙 명시 |

---

## 4. Phase 간 의존성·순서 준수 여부

| 순서 | Phase | 전제 | 준수 |
|------|-------|------|------|
| 1 | Phase A | — | ✅ |
| 2 | Phase B | A 완료 | ✅ Phase A 완료 후 B 착수 |
| 3 | Phase C | B 완료, Alembic CONCURRENTLY 전략 | ✅ B 완료 후 C 착수. CONCURRENTLY 전략 확정 후 진행 |
| 4 | Phase D | C 완료 | ✅ C 완료 후 D 착수 |
| 5 | Phase V | A/B/C/D 완료 | ❌ **미수행** |

**결론**: A→B→C→D 순서는 준수. Phase V는 계획서상 최종 게이트이나 실행되지 않음.

---

## 5. Residual Risks 통합 및 우선순위

### 5.1 🔴 High (운영 전 반드시 검토)

| # | 리스크 | 출처 | 권장 조치 |
|---|--------|------|-----------|
| 1 | Phase V 수동 검증 미수행 | Phase A/B GDM | 도면 전달/취소/수정요청, 완료처리 실패 rollback, structured save 등 8항목 수동 확인 |
| 2 | except Exception: pass (storage.py:246, chat/routes.py:105) | Phase D Code Review | logger.warning/debug + fallback 적용 |

### 5.2 🟡 Medium (배포 후 모니터링)

| # | 리스크 | 출처 | 권장 조치 |
|---|--------|------|-----------|
| 3 | safeJsonFetch HTTP 미검증 | Phase D Code Review | res.ok 검증 추가 |
| 4 | B-4 fetch 실패 시 정렬/색상 미적용 | Phase B GDM | 필요 시 .catch 내 applyShipmentWorkerSortAndColors 검토 |
| 5 | C-2 GIN 인덱스 partial 조건 | Phase C | active 전용 쿼리 비율 분석 후 partial index 검토 |
| 6 | ensure_path 중복 | Phase D Code Review | orders.py → erp_utils 통합 검토 |

### 5.3 🟢 Low (점진 개선)

| # | 리스크 | 출처 | 권장 조치 |
|---|--------|------|-----------|
| 7 | erp_orders_revision db=None 초기화 | Phase A GDM | NameError 가능성 낮음, 주석 또는 패턴 통일 |
| 8 | B-2 CONSTRUCTION assignee 수집 범위 | Phase B GDM | 런타임 검증 권장 |
| 9 | B-3 Promise.all vs Promise.allSettled | Phase B GDM | 부분 실패 사용자 알림 요구사항 확인 |
| 10 | erp_orders_completion ensure_path | Phase D Code Review | 선택적 통일 |

**해소된 리스크**: C 마이그레이션 Railway 실행 ✅, erp_orders_revision print ✅, D-1 revision db.get ✅

---

## 6. Phase V 미수행 항목 정리

### 6.1 V-2 쓰기 없는 스모크 검증 (미수행)

| 경로 | 상태 |
|------|------|
| GET /erp/dashboard | ❌ |
| GET /erp/measurement | ❌ |
| GET /erp/shipment | ❌ |
| GET /erp/as | ❌ |
| GET /erp/drawing-workbench | ❌ |

### 6.2 V-3 수동 핵심 시나리오 (미수행)

| # | 시나리오 | 상태 |
|---|----------|------|
| 1 | 도면 전달 | ❌ |
| 2 | 도면 전달 취소 | ❌ |
| 3 | 도면 수정 요청 | ❌ |
| 4 | 완료처리 실패 시 rollback | ❌ |
| 5 | structured save 후 이벤트/자동화 부가 로직 | ❌ |
| 6 | 시공 첨부 재업로드 | ❌ |
| 7 | 실측 mine=1 필터 결과 비교 | ❌ |
| 8 | ERP/실측/출고/AS 검색 결과 비교 | ❌ |

### 6.3 V-4 주의 사항

- `tools/smoke/tools_test_*.py` — 공유 DB에서 실행 금지. 로컬/스테이징에서만 실행.

---

## 7. 최종 판정

### 7.1 판정: **조건부 통과**

| 조건 | 상태 |
|------|------|
| Phase A/B/C/D 핵심 항목 실행 | ✅ 완료 |
| GDM 감리 Findings (Phase A/C) | ✅ 반영 |
| Phase D Code Review Findings | ⚠️ 5건 미반영 (except:pass 2건, safeJsonFetch, ensure_path, API 형식) |
| Phase V 회귀 검증 | ❌ 미수행 |
| C 마이그레이션 Railway 실행 | ✅ **완료** |

### 7.2 운영 배포 전 필수 권장 사항

1. **Phase V-2 스모크 검증**: 5개 ERP 경로 GET/렌더링 확인.
2. **Phase V-3 수동 시나리오**: 최소 1~6번 시나리오 수행 (도면·완료·structured·시공).
3. **Phase D 보완 (High)**: storage.py:246, chat/routes.py:105의 `except Exception: pass` → logger.warning/debug + fallback.

### 7.3 배포 후 점진 개선 권장

- Phase D Code Review medium/low Findings (safeJsonFetch, ensure_path, API 형식).
- B-5, B-6, B-7 (전제 확정 후 별도 커밋).
- C-3 substring 검색 인덱스 (검색 필드 범위 확정 후).

---

## 8. 보고 체계 (System 4)

| 항목 | 내용 |
|------|------|
| **무엇을 발견했는가** | 계획서 대비 Phase A/B/C/D 핵심 항목 대부분 완료. C 마이그레이션 Railway 실행 완료. erp_orders_revision print/D-1 반영 완료. B-5/B-6/B-7·C-3·Phase V 미수행. Phase D except:pass 2건·medium/low 3건 미반영. |
| **무엇을 작업했는가** | 코드베이스 검증(erp_orders_revision, storage, chat, common_utils), 계획서·실행 보고서 1:1 대조, Findings 반영 여부 재확인, Residual Risks 갱신, 최종 감리 보고서 갱신. |
| **왜 그런 결정을 내렸는가** | 조건부 통과 — C 마이그레이션·Phase D high 2건(print, D-1) 해소로 상태 개선. Phase V 미수행 및 except:pass 2건 잔존으로 운영 배포 전 보완 권장. |

---

*감리 완료: 2026-03-15 | 현재 상황 반영 갱신: 2026-03-15*
