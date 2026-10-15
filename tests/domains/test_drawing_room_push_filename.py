"""도면방 PUSH 파일 이름 = 고객명(여러 장이면 고객명+번호)."""

import app  # noqa: F401  - 순환 import 회피용 선적재

from foms.api.channel.channel_integration import _rename_drawing_room_files


def test_single_file_uses_customer_name():
    out = _rename_drawing_room_files([{'fileName': 'draw_v3.pdf', 'url': 'u'}], '홍길동')
    assert out == [{'fileName': '홍길동.pdf', 'url': 'u'}]


def test_multiple_files_append_number_and_keep_ext():
    out = _rename_drawing_room_files(
        [{'fileName': 'a.pdf'}, {'fileName': 'b.PNG'}], ' 홍/길동 '
    )
    assert [f['fileName'] for f in out] == ['홍길동1.pdf', '홍길동2.PNG']


def test_blank_customer_name_keeps_original():
    files = [{'fileName': 'a.pdf'}]
    assert _rename_drawing_room_files(files, None) == files
    assert _rename_drawing_room_files(files, '  ') == files


def test_disposition_carries_korean_name():
    from foms.api.channel.channel_integration import _attachment_disposition

    value = _attachment_disposition('홍길동1.pdf')
    assert value.startswith('attachment; filename="')
    assert "filename*=UTF-8''%ED%99%8D%EA%B8%B8%EB%8F%991.pdf" in value


def test_drawing_room_url_signed_with_customer_disposition():
    import inspect

    from foms.api.channel import channel_integration as ci

    src = inspect.getsource(ci)
    assert 'response_content_disposition=_attachment_disposition(' in src
