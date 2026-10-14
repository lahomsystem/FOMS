"""모바일 홈 달력 머리띠 — 달마다 바뀌는 실제 사진 12장의 출처 (2026-10-14).

근거: docs/specs/2026-10-14-mobile-calendar-weather-band_SPEC.md §2.1

사진은 ``static/img/calendar/month-MM.webp`` (Wikimedia Commons, 780×420 이하로 줄임). CC BY-SA 사진은
출처 표시가 이용 조건이라 머리띠 오른쪽 아래에 :data:`MONTH_PHOTO_CREDITS` 의 한 줄을 늘 보여 준다.
사진을 바꾸면 이 표와 ``dashboard-tower-weather.css`` 의 ``.foms-cal-photo-N`` 을 함께 고친다.
"""

from __future__ import annotations

__all__ = ["MONTH_PHOTO_CREDITS", "month_photo"]

#: 월 → (화면에 보일 출처 한 줄, 원본 페이지).
MONTH_PHOTO_CREDITS: dict[int, tuple[str, str]] = {
    1: ('사진 Milan Bališin · CC BY-SA 4.0',
        'https://commons.wikimedia.org/wiki/File:Sninsk%C3%BD_kame%C5%88_(v_zime)_001.jpg'),
    2: ('사진 David Lally · CC BY-SA 2.0',
        'https://commons.wikimedia.org/wiki/File:Plum_blossom_-_geograph.org.uk_-_5331856.jpg'),
    3: ('사진 Wikimedia Commons · Public domain',
        'https://commons.wikimedia.org/wiki/File:Forsythia_turin.JPG'),
    4: ('사진 WANGYIFAN2024 · CC0',
        'https://commons.wikimedia.org/wiki/File:Cherry_blossoms_in_Seoul_Forest,_South_Korea2.jpg'),
    5: ('사진 Anonymous · CC BY-SA 3.0',
        'https://commons.wikimedia.org/wiki/File:Ukraine,_Sevastopol_-_Srping_Demir_Kapu_Chokrak_WMID3916642.jpg'),
    6: ('사진 Basile Morin · CC BY-SA 4.0',
        'https://commons.wikimedia.org/wiki/File:Hydrangea_macrophylla_in_front_of_Seongsan_Ilchulbong_volcano_at_blue_hour_in_Jeju_Island_South_Korea.jpg'),
    7: ('사진 Radomianin · CC BY-SA 4.0',
        'https://commons.wikimedia.org/wiki/File:Baltic_Sea_view_from_Schmiedeberg_hill_in_Rerik,_2025-06-23.jpg'),
    8: ('사진 Emilrex · CC BY-SA 4.0',
        'https://commons.wikimedia.org/wiki/File:Sunflower_field_Summer_2023_July.jpg'),
    9: ('사진 Undeka 11 · CC BY-SA 4.0',
        'https://commons.wikimedia.org/wiki/File:Ripening_rice_plants_in_paddy_field,_Indonesia.jpg'),
    10: ('사진 Aney · CC BY-SA 3.0',
        'https://commons.wikimedia.org/wiki/File:Red_Maple_Leaves_in_Yahiko.JPG'),
    11: ('사진 そらみみ · CC BY-SA 4.0',
        'https://commons.wikimedia.org/wiki/File:Ginkgo_biloba_trees_with_yellow_leaves_in_Fujita_Park_in_Hakata,_Fukuoka.JPG'),
    12: ('사진 LudwigSebastianMicheler · CC BY-SA 4.0',
        'https://commons.wikimedia.org/wiki/File:Fronhausen-Sichertshausen_(Germany),_first_snow_in_November_2015-11-22_(12).JPG'),
}


def month_photo(month: int) -> dict[str, object]:
    """달력 페이로드용 ``{"month": int, "credit": str}``."""
    credit, _page = MONTH_PHOTO_CREDITS.get(int(month), ("", ""))
    return {"month": int(month), "credit": credit}
