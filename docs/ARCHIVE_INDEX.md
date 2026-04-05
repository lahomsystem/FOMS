# 프로젝트 아카이브 인덱스
> AI가 Research 단계에서 관련 과거 기록을 빠르게 찾기 위한 목차.
> 새 파일 추가 시 반드시 이 인덱스도 갱신할 것.

## 장애 기록 (docs/incidents/)
| 파일 | 날짜 | 키워드 | 요약 |
|------|------|--------|------|
| 2026-02-22-map-geocode-not-running.md | 02-22 | 지도, geocode, RQ | geocode 미실행 원인: RQ Worker 미연결, Fallback 동기 처리 추가 |
| 2026-02-22-railway-worker-map-utils.md | 02-22 | Railway, Worker, 지도 | Railway Worker 서비스 지도 유틸 경로 문제 |
| 2026-02-22-remote-geocode-diagnosis.md | 02-22 | geocode, 원격, 진단 | 원격 환경 geocode 실패 진단 (카카오 API, 환경변수) |
| 2026-02-23-503-ssl-unexpected-eof-cloudflare.md | 02-23 | SSL, 503, Cloudflare | Cloudflare SSL EOF 에러, R2 업로드 간헐적 실패 |

## 장애 기록 (docs/context/)
| 파일 | 날짜 | 키워드 | 요약 |
|------|------|--------|------|
| INCIDENT_RAILWAY_GEVENT_SOCKET_2026-02-20.md | 02-20 | Railway, gevent, socket | gevent monkey-patch socket 충돌 |
| INCIDENT_SOCKETIO_CONNECTION_2026-02-20.md | 02-20 | Socket.IO, 연결, 400 | Socket.IO 연결 실패 (400 에러) 분석 |

## 기술 분석 (docs/evolution/)
| 파일 | 키워드 | 요약 |
|------|--------|------|
| GDM_AUDIT_REPORT_2026-02-22.md | 감사, 품질 | 전체 코드 품질 감사 62/100, 긴급 3건 |
| GDM_AUDIT_2026-02-19.md | 감사, 품질 | ERP 분리 후 감사 |
| GDM_AUDIT_2026-02-18.md | 감사, 품질 | ERP 분리 감사 72/100 |
| GDM_BACKUP_ISSUE_ANALYSIS_2026-02-17.md | 백업, Socket.IO | 백업 시 Socket.IO 콘솔 에러 분석 |
| GDM_MEASUREMENT_MANAGER_FIX.md | 실측, 담당자 | 실측 담당자 지정 버그 수정 |
| GDM_MEASUREMENT_MANAGER_REALTIME.md | 실측, 실시간 | 실측 실시간 업데이트 분석 |
| FOMS_PRODUCTION_SCALABILITY_ANALYSIS.md | 확장성, 성능 | Production 확장성 분석 |
| BACKUP_RESTORE_VERIFICATION.md | 백업, 복원 | 백업/복원 검증 절차 |
| EVOLUTION_DECISIONS.md | 진화, 결정 | 시스템 진화 결정 기록 |
| EVOLUTION_EXECUTION_REPORT_2026-02-17.md | 진화, 실행 | 2/17 진화 실행 보고 |
| EXPERIMENT_LOG.md | 실험, 로그 | 기술 실험 로그 |
| HYPOTHESIS_BACKLOG.md | 가설, 백로그 | 기술 가설 백로그 |
| RADAR.md | 기술, 레이더 | 기술 트렌드 레이더 |

## 기술 분석 — 리서치 (docs/evolution/research/)
| 파일 | 키워드 | 요약 |
|------|--------|------|
| CENTER_OPERATING_MODEL.md | 운영, 모델 | 센터 운영 모델 분석 |
| LATEST.md | 최신, 리서치 | 최신 기술 리서치 종합 (11KB) |
| reports/ | 보고서 | 리서치 보고서 하위 폴더 (1파일) |

## 설계 계획 (docs/plans/)
| 파일 | 키워드 | 요약 |
|------|--------|------|
| 2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md | harness, gstack, Cursor, Claude, Codex | Cursor/Claude/Codex 통합 하네스 엔지니어링 설계 및 단계별 도입 플랜 |
| 2026-02-22-phase-c-map-design.md | 지도, geocode | Phase C 지도 geocode 설계 |
| 2026-02-22-phase-d-direct-upload-design.md | R2, 업로드 | Phase D Direct R2 Upload 설계 |
| 2026-02-22-railway-multi-user-scalability-plan.md | Railway, 확장 | 다중 사용자 확장 계획 |
| SDD.md | SDD, 방법론 | Spec Driven Development 요약 |
| Alignment.md | RPI, Dumb Zone | AI 생산성/Alignment 방법론 |
