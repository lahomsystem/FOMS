"""보내기 전 검사의 '금지 꼴' 규칙 — 다른 브랜드 · 할인 · 환불 · 날짜 확답 · 연락 시각 약속 · 내부 말 · 가림 표시 · 톡톡.

판정 묶음은 :mod:`.checks`, 글 맞추기 · 숫자 · 링크 읽기는 :mod:`.checks_read`. 순수 함수이고 글은 ``normalize`` 뒤에 본다.

- 할인 · 환불 약속은 '낱말 + 사이 말(조사 · 꾸밈말 · 처리 · 진행 같은 일 이름) 6개까지 + 우리 행동 말(해 드리 · 하겠 · 됩니다 ·
  완료 · 가능 …)'로 본다(R6-1). 날짜 · 연락은 '날 · 때 말 + 같은 문장 20자 안 확답 · 연락 말'(R6-2 · R6-4).
- 부정은 그 말 바로 뒤에 붙을 때만 약속을 지운다('할인은 어렵습니다' · '드릴 수 없습니다' · '가능 여부' · '가능하신지').
  문장 안 다른 말의 부정('할인해 드리고 추가금 없어요')이나 묻는 끝('드릴까요?')은 약속을 지우지 않는다 — AI 가 먼저 묻는
  것도 제안이다(R6-3).
"""

from __future__ import annotations

import re
from typing import Optional

from foms.services.cs_agent.checks_read import NOT_FRACTION, host_allowed, sentence_after

__all__ = [
    "MEDIUM_NAVER_TALK", "NAVER_HOSTS", "check_brand", "is_naver_talk", "mask_marker_count", "other_brand_count",
    "pattern_codes", "talktalk_codes",
]

#: 확정된 날(해 또는 None, 달, 날) 모음.
Confirmed = frozenset[tuple[Optional[int], int, int]]

#: 시범 매체 값. 이 상담이 네이버 톡톡이면(또는 매체를 모르면) 톡톡 규칙을 더한다(D30).
MEDIUM_NAVER_TALK = "appNaverTalk"
#: 톡톡 상담에서 남는 링크 집 — 네이버 안쪽만. 호출 쪽이 더 넣은 집도 이 안쪽만 남는다.
NAVER_HOSTS = ("naver.com", "naver.me")
#: 날 말 뒤 이만큼(자) 안에 확답 말이 오면 날짜 확답(시범 20자).
_DATE_REACH = 20
#: 때 말 뒤 이만큼(자) 안의 연락 약속만 본다(시범 15자).
_CONTACT_REACH = 20

# ── 브랜드 ───────────────────────────────────────────────────────────────
#: 다른 브랜드 이름(시범 '하우드(?!시스템)'). 라홈 초안의 '주식회사 하우드시스템'(기본 안내 계좌 예금주)은 허용(10-28 사장님).
_OTHER_BRAND: dict[str, re.Pattern[str]] = {
    "LAHOM": re.compile(r"하우드(?!\s?시스템)|(?<![a-z])haud(?![a-z])", re.I),
    "HAUD": re.compile(r"라홈|(?<![a-z])lahom(?![a-z])", re.I),
}

# ── 할인 · 환불 약속 ─────────────────────────────────────────────────────
#: 약속 말 사이에 끼는 꾸밈말('바로 해 드릴게요' · '조금 빼 드릴게요').
_ADV = r"(?:(?:바로|즉시|특별히|전액|조금|좀|더|다시)\s?)*"
#: '… 해 드리' 꼴 — 우리가 주겠다는 말.
_GIVE = r"(?:해\s?드|드리|드릴|드려|도와\s?드|넣어\s?드|챙겨\s?드)"
#: 우리 행동 말(약속 말) — '해 드리 · 하겠 · 할게 · 합니다 · 됩니다 · 되었 · 완료 · 예정 · 가능 · 입니다'(R6-1).
_PROMISE_VERB = (
    r"(?:(?:해|하여|해서)\s?)?(?:드리|드릴|드려|드립)|도와\s?드|하겠|할게|할께|해\s?놓|해요|합니다"
    r"|됩|되었|됐|될|되십|되세|완료|예정|가능(?!성)|입니|이에|이고|들어가|들어갑|받으실|받으시"
)
#: 낱말과 약속 말 사이에 끼는 말 — 조사 · 꾸밈말 · '진행 · 처리 · 적용 · 쿠폰 · 혜택' 같은 일 이름(6개까지 본다).
_FILL = (
    r"\s|을|를|은|는|이|가|도|만|까지|으로|로|에|된|받은|해서|하여|해|금액|가격|혜택|쿠폰|진행|처리|적용|접수|요청|신청|발급"
    r"|보내|넣어|챙겨|안내|돌려|지급|적립|빼|바로|즉시|특별히|추가로|추가|모두|전부|전액|다시|조금|좀|더|꼭|빠르게|정상적으로"
)
#: 할인 낱말('네고 · 디씨')이 낱말로 쓰였을 때만 — 붙여 쓴 인사 '네고객님' · '네네고객님' · '네고민' 은 아니다.
_SLANG_ALONE = r"(?<![가-힣])(?:네고|디씨)(?=[^가-힣]|$|를|가|는|도|해|가능|드|진행)"
#: 할인 낱말 — 할인 · 낱말로 쓴 네고 · 디씨 · DC · 에누리 · 특가 · 반값 · 반 가격 · 원가 · 싸게 · 저렴하게 · 쿠폰 · 서비스로.
_DISCOUNT_WORD = (
    rf"할\s?인|{_SLANG_ALONE}|(?<![a-z])d\.?c(?![a-z])|에누리|특가|반\s?값|반\s?가격|반액|원가|싸게|저렴하게|쿠폰|서비스로"
)
#: 할인 약속(시범: 할인해 드리 · 할인 가능 · 할인 적용해 드리) — 낱말 + 사이 말 + 우리 행동 말('할인 진행해 드리 · 쿠폰 보내 드리').
_DISCOUNT = re.compile(rf"(?:{_DISCOUNT_WORD})(?:{_FILL}){{0,6}}(?:{_PROMISE_VERB})", re.I)
#: 돈 항목 — 무료 · 무상 · 안 받 · 저희가 부담이 붙으면 할인 약속이다(R6-1, 끝이 '원' 인 금액 말 포함 — '만 원 덜 받').
_MONEY_ITEM = r"(?:배송비|운임|운송비|택배비|설치비|시공비|철거비|출장비|추가금|추가\s?비용|수수료|차액|비용|금액|만\s?원|천\s?원|원)"
#: 돈 항목에 붙은 할인 · 돌려 말한 할인(무료 · 안 받 · 저희가 부담 · 없이 해 드리 · 예산에 맞춰 · 무상 교체해 드리 · N% 할인 ·
#: 적립금). '실측 · 상담 · 견적' 의 무료는 늘 그런 안내라 뺀다('무료로 실측 가능하십니다').
_DISCOUNT_MONEY = re.compile(
    rf"(?<!실측)(?<!실측\s)(?<!상담)(?<!상담\s)(?<!견적)(?<!견적\s){_MONEY_ITEM}\s?(?:은|는|이|가|도|까지|만)?\s?(?:무료|무상|공짜|면제|0\s?원)"
    rf"|{_MONEY_ITEM}\s?(?:은|는|을|를|도|만)?\s?(?:(?:안|덜)\s?(?:받|청구)|(?:받지|청구하지)\s?(?:않|안))"
    rf"|{_MONEY_ITEM}\s?(?:은|는|을|를)?\s?(?:저희가|저희\s?쪽에서|당사가|회사에서|제가)\s?(?:부담|내\s?드|(?:처리)?해\s?드)"
    rf"|{_MONEY_ITEM}\s?(?:은|는)?\s?(?:없이|빼고)\s?(?:진행|처리)?\s?(?:해\s?)?(?:드리|드릴|드려|드립)"
    rf"|(?:가격|금액|비용|견적|단가|예산|원)\s?(?:을|를|은|는|도|에서|에)?\s?{_ADV}(?:조정|맞춰|낮춰|내려|빼)\s?"
    rf"(?:(?:견적|가격|금액|제작|진행|구성)\s?)?(?:해\s?)?(?:드|줄|주)"
    rf"|(?:무료|무상|공짜)(?:로|으로)?\s?(?!실측|상담|견적)(?:[가-힣]{{1,4}}\s?)?(?:해\s?)?(?:드리|드릴|드려|드립)"
    rf"|\d\s?%\s?(?:할인|off|오프|디씨|dc)|원\s?할\s?인|할\s?인\s?(?:된|받은)\s?(?:금액|가격)|깎(?:아\s?(?:드|줄|주)|을게|겠)"
    rf"|(?:끝자리|차액)\s?(?:은|는|을|를|도|에서)?\s?{_ADV}빼\s?(?:드|줄|주)|(?:적립금|포인트)\s?(?:으로|로)?\s?(?:돌려|지급|{_GIVE})",
    re.I,
)
#: 환불 낱말 — 환불 · 반품 · (결제 · 카드 · 주문 · 예약) 취소.
_REFUND_WORD = r"환\s?불|반품|(?:(?:결제|카드|주문|예약)\s?)?취소"
#: 환불 약속(시범: 환불해 드리 · 환불 가능합니다 · 환불 처리해 드리) — 낱말 + 사이 말 + 우리 행동 말('처리하겠 · 완료되었').
_REFUND = re.compile(rf"(?:{_REFUND_WORD})(?:{_FILL}){{0,6}}(?:{_PROMISE_VERB})")
#: 돈 돌려 드리기 — '전액 돌려 드리 · 차액은 다시 입금해 드리'.
_REFUND_MONEY = re.compile(
    rf"(?:금액|돈|비용|차액|전액|대금)\s?(?:은|는|을|를)?\s?{_ADV}(?:돌려|반환해|입금해|송금해|환급해)\s?(?:드|줄|주)"
)
#: 약속 말 바로 뒤에 붙으면 약속이 아니다 — '할인은 어렵 · 드릴 수 없 · 드리기 어렵 · 드리지 않 · 가능 여부 · 가능하신지 ·
#: 무료가 아닙'. 묻는 끝('드릴까요?')은 넣지 않는다(R6-3).
_NEGATED_AFTER = re.compile(
    r"\s?(?:은|는|이|가|도)?\s?(?:어렵|불가|힘들|곤란|안\s?되|안\s?돼|안\s?됩|않|못|없|아니|아닙|아닌)"
    r"|\s?(?:ㄹ|을|할|릴|드릴)?\s?수\s?(?:가|는|도)?\s?없|\s?수\s?(?:가\s?)?있(?:는|을)지"
    r"|기\s?(?:는|가)?\s?(?:어렵|힘들|곤란)|지\s?(?:는|도)?\s?(?:않|못|마)"
    r"|\s?여부|(?:하신|한|할|하실|될|되는|되실|되신|드릴|인|일|신|실|는)?지(?![가-힣])"
)

# ── 날짜 확답 ────────────────────────────────────────────────────────────
#: 날 말(시범: N월 N일 · N/N · 내일 · 모레 · 이번 주 · 다음 주) + 2026-11-03 · 오늘 · 'N일에 · N일 뒤' · 다음 날 · 이달 · 월말 ·
#: 연내 · 'N월 중' · '주말에' · 요일(R6-2). 늘 그런 말('토요일도 · 월요일부터 · 평일 · 토요일 · 월~토요일 · 매주 토요일 ·
#: 주말에도 · 토요일 오전에도')은 날짜 확답이 아니다(D19 '토 가능' · R6-20). '1/2 가격' 은 분수다.
_DAY_WORD = re.compile(
    r"(?<![\d.])\d{4}\s?[-./]\s?(?P<m4>\d{1,2})\s?[-./]\s?(?P<d4>\d{1,2})(?!\d)"
    r"|(?<!\d)(?:\d{4}\s?년\s?)?(?P<m>\d{1,2})\s?월\s?(?P<d>\d{1,2})\s?일"
    rf"|(?<![\d/])(?P<m2>\d{{1,2}})/(?P<d2>\d{{1,2}})(?![\d/]){NOT_FRACTION}"
    r"|(?<![\d~\-])(?P<d3>\d{1,2})\s?일\s?(?:에|날|자로)|(?<![\d~\-])\d{1,2}\s?일\s?(?:뒤|후)"
    r"|(?:이틀|사흘|나흘|일주일|한\s?주|보름)\s?(?:뒤|후|안|내)|(?<!\d)\d{1,2}\s?월\s?(?:초|초순|중순|하순|말)?\s?(?:에|중|쯤|경)"
    r"|오늘|금일|당일|내일|명일|모레|글피|다음\s?날|익일|이번\s?주|금주|다음\s?주|차주|이번\s?달|이달|금월|다음\s?달|월말|월초|연내"
    r"|올해\s?안|(?:주말|주중)\s?에(?!는|도)"
    r"|(?<![^\w\s])(?<![^\w\s]\s)(?<!매주)(?<!매주\s)[월화수목금토일]요일"
    r"(?!\s?(?:도|은|는|엔|이나|나|만|및|과|와|부터|까지|마다|에도|에는|[^\w\s]|(?:오전|오후|아침|점심|저녁)\s?(?:에도|에는|도|은|는)))"
)
#: 날짜 확답 말(시범: 확정 · 가능합니다 · 가능해요 · 방문드리 · 시공해 드리 · 설치해 드리) + 가능하십니다 · 예정 · 잡아 드리 · 뵙겠 ·
#: '설치하겠 · 출고합니다 · 방문합니다 · 들어갑니다 · 받아 보실 · 보내겠'(R6-2).
_DATE_VERB = re.compile(
    r"확정|가능합니다|가능해요|가능하십니다|가능하세요|가능할\s?것|됩니다|되십니다|잡아\s?드|보내\s?드|보내겠|찾아\s?뵙|뵙겠|뵐게"
    r"|받아\s?보실|받아\s?보시|받으실|받으시|방문하겠|가겠|갑니다|오겠|오십니다"
    r"|(?:방문|시공|설치|배송|배달|출고|발송|도착|진행|예약|교체|수리|철거|입고|작업|납품)\s?(?:을|이|가|은|는|도)?\s?"
    r"(?:해\s?드|드리|드릴|드려|도와|예정|가능(?!성)|완료|됩|되|될|하겠|할게|할\s?예정|합니다|해요|해\s?놓|들어가|들어갑|나가|나갑|잡혀|잡아)"
)

# ── 연락 시각 약속 ───────────────────────────────────────────────────────
#: 때 말(시범: 오늘 · 내일 · 모레 · 오전 중 · 오후 중 · N시) + 요일 · 아침 · 저녁 · 퇴근 전 · 'N분 · N시간 안' · 한글 숫자
#: ('한 시간 안 · 삼십 분 뒤 · 이틀 안', R6-4). '시공 당일' 처럼 일에 매인 날은 때 약속이 아니다.
_TIME_WORD = re.compile(
    r"오늘|금일|내일|명일|모레|글피|이번\s?주|금주|다음\s?주|차주|[월화수목금토일]요일|오전|오후|아침|점심|저녁"
    r"|퇴근\s?전|(?:업무|영업)\s?시간\s?(?:안|내)|(?:하루|이틀|사흘|나흘|닷새|열흘|보름|일주일)\s?(?:안|이내|내|뒤|후|까지)"
    r"|(?<!\d)\d{1,2}\s?시(?!간)|(?<!\d)\d+\s?(?:분|시간|일)\s?(?:안|내(?!외)|이내|뒤|후|까지|정도|쯤)"
    r"|(?<![가-힣])(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|스무|[일이삼사오육칠팔구십]{1,3})\s?(?:분|시간|일)"
    r"\s?(?:안|내(?!외)|이내|뒤|후|까지|정도|쯤)"
)
#: 연락 약속 말(시범: 연락 · 안내 · 전화 드리) + 회신 · 답변 · 답 · 문자 · 메시지 드리 · 알려 드리 · 확인해 보겠 · 연락하겠 ·
#: '연락이 갈 · 회신 예정'(R6-4). 때 말 없는 '확인해 보겠습니다'는 된다.
_CONTACT_VERB = re.compile(
    r"(?:연락|안내|전화|통화|회신|답변|답장|말씀|해피\s?콜|답|문자|메시지|메세지|톡)\s?(?:을|를|은|도)?\s?(?:꼭\s?|바로\s?|다시\s?)?"
    r"(?:도와\s?|해\s?|하여\s?)?(?:드리|드릴|드려|드립)|알려\s?(?:드리|드릴|드려)|확인\s?(?:해|하여|후|하고|해서)?\s?(?:보겠|드리|드릴|드려|해\s?드)"
    r"|(?:연락|전화|회신|답변|답장|문자|메시지)\s?(?:을|를)?\s?(?:하겠|할게|할\s?예정|합니다|해요)"
    r"|(?:연락|전화|안내|회신|답변|문자)\s?(?:이|가|은|는)?\s?(?:갈|가실|갑니|가겠|나갈|나갑)|(?:연락|안내|전화|회신|답변|답장)\s?예정"
)
#: 손님이 할 일 · 이미 한 일이 붙은 말 — 우리 약속이 아니다("내일 전화 주시면 안내 …" · "오늘 문의 주신 내용 확인해 보겠습니다" ·
#: "오후 5시 이후 문의는 …").
_CUSTOMER_FIRST = re.compile(r"(?:시|으시)면|실\s?때|주세요|(?:주|하|보내|남기|올리)신|문의(?:는|하신)")

# ── 내부 말 · 가림 표시 ──────────────────────────────────────────────────
#: 직원 · 에이전트끼리 쓰는 말(시범: [사람] · [정본 · Jev · 총괄 에이전트 · ABOVE) + 메모 칸 이름 · 내부 메모 · FOMS · 프롬프트.
_INTERNAL = re.compile(
    r"\[사람\]|\[정본|(?<![a-z])jev(?![a-z])|총괄\s?에이전트|(?-i:ABOVE)|손님께\s?보낼\s?답|직원\s?(?:참고|용|메모|전용)"
    r"|(?:내부|상담원|담당자)\s?(?:메모|참고)|내부용|\(초안\)|초안\s?:|(?<![a-z])ai\s?(?:초안|메모)"
    r"|(?:손님|고객)님?(?:에게|께)는?\s?(?:보내지|보이지|말하지|알리지|전하지|말씀하지)\s?(?:마|않)"
    r"|\[FOMS|(?<![a-z])foms(?![a-z])|프롬프트|(?<![a-z])prompt(?![a-z])|근거\s?id|넘김\s?(?:여부|:)|의도\s?:",
    re.I,
)
#: AI 표시 · 자기소개('AI 상담사입니다' · 챗봇 · 자동 응답) — 직원이 자기 이름으로 보내는 글이다(사장님 D15, 10-29 다시 지시).
#: 'AI' 는 대문자 낱말만(AIR 같은 영어 낱말 속은 아니다).
_AI_SELF = re.compile(r"(?<![A-Za-z])AI(?![A-Za-z])|인공\s?지능|챗봇|상담\s?봇|자동\s?(?:응답|답변)")
#: 괄호 안 짧은 말 — 안에 가림 · 빈칸 낱말이 있으면 가림 표시다(띄어 써도 — '[ 이 름 ]', R6-8).
_BRACKETED = re.compile(r"[\[{<【〔]([^\[\]{}<>【】〔〕\n]{1,24})[\]}>】〕]")
#: 가림 · 빈칸 낱말(시범: 이름 · 전화 · 주소 · 예금주 · 직원이름) + 단지 · 동호 · 링크 · 금액 · '고객명' 같은 'OO명' · 영문 name 등.
_FIELD_WORD = re.compile(
    r"이름|성함|성명|전화|번호|연락처|주소|예금주|단지|동호|계좌|메일|링크|아이디|생년|주민|카드|차량|금액|가격|날짜|시간|상호"
    r"|[가-힣]{0,4}명(?![가-힣])"
    r"|(?<![a-z])(?:name|phone|tel|mobile|address|addr|e-?mail|account|number|date|price|amount|customer|link|url)(?![a-z])",
    re.I,
)
#: 따로 보는 빈칸 꼴 — 가림(C2-3)의 '[링크:도메인]'(도메인이 길어 위 꼴에 안 든다) · '{{…}}' · '(이름)' · '○○ 고객님' · 'OO님'(R6-8).
_PLACEHOLDER = re.compile(
    r"\[링크:[^\]\n]{0,100}\]|\{\{[^{}\n]{1,40}\}\}"
    r"|\((?:이름|성함|성명|고객명|전화번호|연락처|주소|번호|금액|날짜|name|phone)\)"
    r"|(?:(?<![○◯●□△◇☆★*])[○◯●□△◇☆★*]{2,}+|(?<![a-z])(?:oo|xx)(?![a-z]))\s?(?:고객님|고객|님|씨|아파트|단지|동|호|원)",
    re.I,
)

# ── 톡톡(D30) ────────────────────────────────────────────────────────────
#: 네이버 톡톡 매체 이름 — 시범 값 'appNaverTalk' 말고 'naverTalk' · 'talktalk' 꼴도 톡톡이다.
_NAVER_TALK_MEDIUM = re.compile(r"naver\s?_?talk|talk\s?_?talk|톡톡", re.I)
#: 톡톡 상담을 바깥으로 옮기자는 말(시범 NAVER_BANS + 다른 메신저 · '문자 · 메일 주세요' · '라인으로 연락' · '카 카 오' — R6-6).
#: '고객센터로 전화 주시면'은 된다. 상품 줄('화이트 라인으로 제작')은 '라인' 뒤가 연락 말일 때만 본다.
_TALKTALK_OUTSIDE = re.compile(
    r"카\s?톡|카\s?카\s?오|(?<![a-z])kakao|오픈\s?채팅|오픈\s?톡|단톡|플러스\s?친구|인스타|instagram|(?<![a-z])dm(?![a-z])"
    r"|텔레그램|telegram|위챗|wechat|왓츠앱|whatsapp|페이스북|facebook|(?<![가-힣])라인\s?(?:아이디|메신저|id|친구)"
    r"|라인\s?(?:으로|로)\s?(?:연락|문의|메시지|메세지|톡|채팅|친구|추가|대화)|메신저\s?(?:로|아이디)|(?<![a-z])sns(?![a-z])"
    r"|문자\s?(?:로|메시지|메세지|보내|주|남겨|드리|드릴)|메일\s?(?:로|주소|주|보내|드리|드릴)|(?<![a-z])e-?mail|홈페이지|채널\s?톡"
    r"|(?<!스토어)(?<!스토어\s)(?:웹\s?)?사이트|자사몰",
    re.I,
)
#: 번호를 달라는 말.
_ASK = r"(?:남겨|알려|보내|적어|기재|입력|공유|말씀해|부탁|주시|주세요|주실|필요)"
#: 손님 번호 이름(연락처 · 휴대폰 · 전화 번호) — 앞말과 상관없이 따로 찾는다('주문 번호와 연락처 남겨 주세요' — R6-6).
_PHONE_ASK_STRONG = re.compile(
    rf"(?:연락처|(?:핸드폰|휴대폰|휴대\s?전화|전화|연락)\s?번호)(?!\s?로)\s?(?:를|을|가|도|와|랑|하고|만)?[^.!?\n]{{0,10}}?{_ASK}"
)
#: 그냥 '번호'(시범: 번호 뒤 10자 안 남겨 · 알려 · 보내) — '고객센터 번호 · 주문 번호' 처럼 손님 번호가 아니면 뺀다.
_PHONE_ASK_BARE = re.compile(
    rf"(?<!전화)(?<!전화\s)(?<!핸드폰)(?<!휴대폰)(?<!연락)번호(?!\s?로)\s?(?:를|을|가|도|와|랑|하고|만)?[^.!?\n]{{0,10}}?{_ASK}"
)
#: 손님 번호가 아닌 번호(고객센터 번호 · 주문 번호 …)의 앞말.
_NOT_CUSTOMER_NUMBER = re.compile(r"(?:고객센터|대표|저희|매장|본사|주문|송장|운송장|상품|모델|계좌|사업자|아래|위)\s?$")


def check_brand(brand: str) -> str:
    """브랜드 키 확인(state.BRAND_HOURS 와 같은 키) — 모르는 브랜드면 ValueError(조용히 틀리지 않게)."""
    if brand not in _OTHER_BRAND:
        raise ValueError(f"모르는 브랜드: {brand!r}")
    return brand


def other_brand_count(body: str, brand: str) -> int:
    """다른 브랜드 이름 수(사람 답 사후 점검도 쓴다)."""
    return len(_OTHER_BRAND[check_brand(brand)].findall(body))


def is_naver_talk(medium: Optional[str]) -> bool:
    """네이버 톡톡 상담인가 — 'appNaverTalk'(시범 값) · 'naverTalk' · 'talktalk' 꼴."""
    return bool(_NAVER_TALK_MEDIUM.search(medium or ""))


def _promise_count(patterns: tuple[re.Pattern[str], ...], body: str) -> int:
    """약속 꼴 수 — 그 말 바로 뒤에 부정이 붙으면('어렵 · 수 없 · 여부 · 하신지') 세지 않는다(R6-3)."""
    return sum(1 for p in patterns for m in p.finditer(body) if not _NEGATED_AFTER.match(body, m.end()))


def _confirmed_day(m: re.Match[str], confirmed: Confirmed) -> bool:
    """날 말이 확정 값과 같은 날인가 — 달이 없는 'N일에' 는 날만 견준다. '내일 · 요일' 은 확정 값과 못 맞춘다."""
    day = m.group("d") or m.group("d2") or m.group("d3") or m.group("d4")
    if day is None:
        return False
    month = m.group("m") or m.group("m2") or m.group("m4")
    return any(int(day) == d and (month is None or int(month) == mo) for _, mo, d in confirmed)


def _date_promise_count(body: str, confirmed: Confirmed) -> int:
    """날짜 확답 수 — 날 말 뒤 20자 안의 확답 말(그 말 바로 뒤에 부정이 붙으면 아님). 확정 값과 같은 날이면 된다."""
    verbs: set[int] = set()
    for m in _DAY_WORD.finditer(body):
        verb = _DATE_VERB.search(sentence_after(body, m.end(), _DATE_REACH))
        if verb is None or _NEGATED_AFTER.match(body, m.end() + verb.end()) or _confirmed_day(m, confirmed):
            continue
        verbs.add(m.end() + verb.start())
    return len(verbs)


def _contact_promise_count(body: str) -> int:
    """연락 시각 약속 수 — 때 말 뒤 20자 안의 연락 약속 말(그 사이에 손님이 먼저 할 일이 있으면 아님)."""
    verbs: set[int] = set()
    for m in _TIME_WORD.finditer(body):
        window = sentence_after(body, m.end(), _CONTACT_REACH)
        verb = _CONTACT_VERB.search(window)
        if verb and not _CUSTOMER_FIRST.search(window[: verb.start()]):
            verbs.add(m.end() + verb.start())
    return len(verbs)


def mask_marker_count(body: str) -> int:
    """가림 표시 · 빈칸 꼴 수(R6-8) — 괄호 안 말은 띄어쓰기를 지우고 본다. 같은 자리는 한 번만 센다."""
    spans = {m.span() for m in _PLACEHOLDER.finditer(body)}
    spans |= {m.span() for m in _BRACKETED.finditer(body) if _FIELD_WORD.search(m.group(1).replace(" ", ""))}
    return len(spans)


def pattern_codes(body: str, brand: str, confirmed: Confirmed) -> list[str]:
    """금지 꼴 — 다른 브랜드 · 할인 · 환불 · 날짜 확답 · 연락 시각 약속 · 내부 말 · AI 표시 · 가림 표시."""
    codes = ["other_brand"] * other_brand_count(body, brand)
    codes += ["discount_promise"] * _promise_count((_DISCOUNT, _DISCOUNT_MONEY), body)
    codes += ["refund_promise"] * _promise_count((_REFUND, _REFUND_MONEY), body)
    codes += ["date_promise"] * _date_promise_count(body, confirmed)
    codes += ["contact_time_promise"] * _contact_promise_count(body)
    codes += ["internal_words"] * len(_INTERNAL.findall(body))
    codes += ["ai_mention"] * len(_AI_SELF.findall(body))
    return codes + ["mask_marker"] * mask_marker_count(body)


def talktalk_codes(body: str, links: list[str], hosts: tuple[str, ...]) -> list[str]:
    """톡톡 매체 규칙(D30) — 바깥 메신저 · 네이버 밖 링크 · 채팅으로 번호 받기('고객센터 번호 · 주문 번호' 는 아님)."""
    naver = tuple(h for h in hosts if host_allowed(h, NAVER_HOSTS))
    codes = ["talktalk_outside"] * len(_TALKTALK_OUTSIDE.findall(body))
    codes += ["talktalk_link" for host in links if not host_allowed(host, naver)]
    asks = len(_PHONE_ASK_STRONG.findall(body))
    asks += sum(
        1 for m in _PHONE_ASK_BARE.finditer(body) if not _NOT_CUSTOMER_NUMBER.search(body[max(0, m.start() - 8):m.start()])
    )
    return codes + ["talktalk_phone_ask"] * asks
