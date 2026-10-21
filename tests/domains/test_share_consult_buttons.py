"""알림톡 '상담 먼저' — 링크를 카톡 버튼으로 보내기(Open API).

2026-10-21 하우드 실폰에서 채널톡 Open API 버튼이 카카오 상담톡에 버튼으로 뜨는 것을 확인했다.
키가 없거나 버튼 쓰기가 실패하면 글 속 링크로 다시 보낸다. 네트워크는 쓰지 않는다.
"""

from __future__ import annotations

from db import db_session
from foms.services import channel_client
from foms.services import share_consult as sc
from tests.domains.test_share_consult_first import (  # noqa: F401 — chat_stub 는 fixture
    _message,
    _mk_order,
    _request_event,
    chat_stub,
)


def test_delivers_buttons_when_open_api_configured(app, chat_stub):
    """키가 있으면 링크는 글이 아니라 버튼으로 간다 — 한 통에 [도면 보기][계약서 보기]."""
    chat_stub['buttons'] = []
    order = _mk_order()
    _request_event(order.id)

    assert sc.handle_user_chat_message(db_session, _message(order.id)) == 'delivered'
    assert [m for m in chat_stub['sent'] if not m['private']] == []
    (sent,) = chat_stub['buttons']
    assert sent['chat'] == 'uc-1' and sent['brand'] == 'HAUD'
    assert [title for title, _url in sent['buttons']] == ['도면 보기', '계약서 보기']
    assert all('/s/' in url for _title, url in sent['buttons'])
    assert '/s/' not in sent['text'] and '이 대화방에' in sent['text']


def test_split_buttons_one_per_message(app, chat_stub):
    chat_stub['buttons'] = []
    order = _mk_order()
    _request_event(order.id, split=True)

    assert sc.handle_user_chat_message(db_session, _message(order.id)) == 'delivered'
    assert [[t for t, _u in m['buttons']] for m in chat_stub['buttons']] == [['도면 보기'], ['계약서 보기']]
    assert '이 대화방에' not in chat_stub['buttons'][0]['text']
    assert '이 대화방에' in chat_stub['buttons'][1]['text']


def test_button_failure_falls_back_to_link_text(app, chat_stub):
    """버튼 쓰기가 실패하면 같은 링크를 글 속 링크로 다시 보낸다(고객이 빈손이 되지 않게)."""
    chat_stub['buttons'] = []
    chat_stub['buttons_fail'] = True
    order = _mk_order()
    _request_event(order.id)

    assert sc.handle_user_chat_message(db_session, _message(order.id)) == 'delivered'
    public = [m for m in chat_stub['sent'] if not m['private']]
    assert len(public) == 1 and public[0]['text'].count('/s/') == 2
    assert public[0]['channel'] == 'ch-lahom'


def test_send_user_chat_buttons_payload(monkeypatch):
    monkeypatch.delenv('CHANNEL_OPENAPI_KEY_HAUD', raising=False)
    monkeypatch.delenv('CHANNEL_OPENAPI_SECRET_HAUD', raising=False)
    assert channel_client.send_user_chat_buttons('HAUD', 'c', '글', [('도면 보기', 'https://x/s/1')]) \
        == {'success': False, 'message_id': None, 'error': 'not_configured'}

    monkeypatch.setenv('CHANNEL_OPENAPI_KEY_HAUD', 'k')
    monkeypatch.setenv('CHANNEL_OPENAPI_SECRET_HAUD', 's')
    calls = []

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {'message': {'id': 'msg-9'}}

    def _post(url, *, params, json, headers, timeout):
        calls.append({'url': url, 'params': params, 'json': json, 'headers': headers})
        return _Resp()

    monkeypatch.setattr(channel_client.requests, 'post', _post)
    result = channel_client.send_user_chat_buttons(
        'HAUD', 'uc-7', '고객님 문서입니다', [('도면 보기', 'https://x/s/1'), ('계약서 보기', 'https://x/s/2'),
                                         ('넘침', 'https://x/s/3')], bot_name='FOMS')

    assert result == {'success': True, 'message_id': 'msg-9', 'error': None}
    (call,) = calls
    assert call['url'] == 'https://api.channel.io/open/user-chats/uc-7/messages'
    assert call['params'] == {'botName': 'FOMS'}
    assert call['headers']['x-access-key'] == 'k'
    assert call['json']['plainText'] == '고객님 문서입니다'
    assert call['json']['buttons'] == [
        {'title': '도면 보기', 'colorVariant': 'cobalt',
         'action': {'type': 'web', 'attributes': {'url': 'https://x/s/1'}}},
        {'title': '계약서 보기', 'colorVariant': 'cobalt',
         'action': {'type': 'web', 'attributes': {'url': 'https://x/s/2'}}},
    ]

    class _Bad:
        status_code = 422

    monkeypatch.setattr(channel_client.requests, 'post', lambda *a, **k: _Bad())
    assert channel_client.send_user_chat_buttons('HAUD', 'uc-7', '글', [('a', 'b')])['error'] == 'http_422'
