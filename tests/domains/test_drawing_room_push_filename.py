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
