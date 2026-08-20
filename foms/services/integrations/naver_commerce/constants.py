"""네이버 수집 공용 상수 (NAVER-INGEST-01).

**의존성 없는 모듈**이다. 채널 코드·시스템 계정 username 은 web 화면도 알아야 하는데,
그걸 ``ingest`` 에서 당겨오면 web 이 수집 파이프라인(HTTP 를 내는 코드)을 import 하게 된다.
그러면 "네이버 HTTP 는 WORKER 단일 출구"(§3.1) 계약이 흐려지고, 실제로 계약 테스트가 red 로
잡는다. 상수는 여기에 두고 양쪽이 각자 가져간다.
"""

from __future__ import annotations

#: 판매채널 코드. v1 은 네이버 하나뿐이지만 링크 테이블은 채널 확장을 막지 않는다.
CHANNEL = "NAVER"

#: 수집 주문임을 표시하는 ``structured_data['source']`` 마커.
#: 대시보드(‘담당 미지정’ 뱃지)도 이 값을 읽으므로 매핑 모듈이 아니라 여기에 둔다.
SOURCE_MARKER = "NAVER_SMARTSTORE"

#: 수집 주문의 이벤트 author·``assigned_by`` 로 쓰는 봇 계정(role=MANAGER).
ACTOR_USERNAME = "naver_ingest_bot"

#: 미배정 보류함 owner(활성 SALES). 실존 영업사원이 아니라 "아직 주인 없음"을 표현하는 자리다.
#: ``create_order`` 가 owner 없는 주문을 허용하지 않기 때문에 필요하다(ASSIGNMENT-00).
OWNER_USERNAME = "naver_unassigned"

#: 네이버 ``productClass`` 값 — 추가옵션(부모 링크 없는 독립 productOrder).
#: 본품은 ``조합형옵션상품`` 으로 온다(2026-08-14 실측). 매핑과 도크가 같은 값을 봐야 해서
#: 여기에 둔다 — 한쪽만 바뀌면 품목 생성과 화면 표시가 어긋난다.
ADDON_PRODUCT_CLASS = "추가구성상품"

#: 수집 주문의 **발주사**(``parties.orderer.name``). 네이버 스마트스토어가 라홈 스토어라
#: 발주사는 항상 라홈이다. ERP 에서 이 자리는 발주사 전용이고 주문한 사람은
#: ``parties.buyer`` 로 간다 — 두 뜻이 겹쳐 있던 것을 가른 것이 ORDERER-AXIS-01 이다.
#: 이 값으로 알림톡 브랜드 프로필·도면 로고·퀘스트 CS 팀·견적서 양식이 갈린다.
DEFAULT_ORDERER_NAME = "라홈"

__all__ = ["ACTOR_USERNAME", "ADDON_PRODUCT_CLASS", "CHANNEL", "DEFAULT_ORDERER_NAME",
           "OWNER_USERNAME", "SOURCE_MARKER"]
