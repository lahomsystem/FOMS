# Task Registry

> AI 세션 간 작업 추적. 세션이 바뀌어도 진행 상황을 유지합니다.

## 활성 작업

| ID | 상태 | 설명 | 시작일 | 최종 업데이트 |
|----|------|------|--------|-------------|
| SLIM-002 | 대기 | feature/erp-beta-rename-to-erp → deploy 머지·푸시 | 2026-02-16 | 2026-02-16 |
| SLIM-003 | 대기 | Phase 4 준비: apps/erp.py 구조 파악 및 1차 분리 후보 선정 | 2026-02-16 | 2026-02-16 |
| SLIM-001 | 완료 | app 슬림다운 Phase 1: services/ 도입 (1-1~1-4 완료) | 2026-02-16 | 2026-02-16 |

## 완료된 작업

| ID | 설명 | 완료일 |
|----|------|--------|
| CTX-001 | Cursor Rules 8개 생성 | 2026-02-15 |
| CTX-002 | MCP 6개 최적화 | 2026-02-15 |
| CTX-003 | Skills 4개 설치 | 2026-02-16 |
| CTX-004 | Subagents 6개 생성 | 2026-02-16 |
| CTX-005 | Context Engineering 시스템 구축 | 2026-02-16 |
| SLIM-001a | services/ 폴더 생성 + business_calendar 이동 | 2026-02-16 |
| SLIM-001b | erp_policy → services/erp_policy.py | 2026-02-16 |
| SLIM-001c | storage → services/storage.py | 2026-02-16 |

## 작업 등록 규칙
- 새 작업 시작 시 여기에 등록
- 상태: `진행중`, `대기`, `완료`, `취소`
- 세션 종료 시 자동 업데이트 (Hook)
