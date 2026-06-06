from __future__ import annotations

from typing import Any


# Source basis:
# - Jeonju official administrative district page, "전주시 행정동 및 법정동 관할구역 2025. 9. 30."
# - Local commercial-area aliases commonly used in restaurant searches.
# Coordinates are representative search centers for radius search, not legal-boundary centroids.
JEONJU_SEARCH_AREAS: dict[str, dict[str, Any]] = {
    "객사": {
        "aliases": ["객사", "객리단길", "객리단", "전주객사", "전주객사길", "객사길", "영화의거리"],
        "longitude": 127.1450,
        "latitude": 35.8191,
        "radius": 800,
    },
    "웨리단길": {
        "aliases": ["웨리단길", "전주웨리단길", "웨딩거리"],
        "longitude": 127.1442,
        "latitude": 35.8179,
        "radius": 700,
    },
    "한옥마을": {
        "aliases": ["한옥마을", "전주한옥마을", "경기전"],
        "longitude": 127.1530,
        "latitude": 35.8151,
        "radius": 900,
    },
    "중앙동": {
        "aliases": [
            "중앙동",
            "중앙동1가",
            "중앙동2가",
            "중앙동3가",
            "중앙동4가",
            "다가동",
            "다가동1가",
            "다가동2가",
            "다가동3가",
            "다가동4가",
            "고사동",
            "태평동",
            "중앙시장",
            "전주중앙시장",
            "신중앙시장",
            "전주중앙 버드나무시장",
        ],
        "longitude": 127.1442,
        "latitude": 35.8190,
        "radius": 1600,
    },
    "풍남동": {
        "aliases": [
            "풍남동",
            "풍남동1가",
            "풍남동2가",
            "풍남동3가",
            "경원동",
            "경원동1가",
            "경원동2가",
            "경원동3가",
            "전동",
            "전동1가",
            "전동3가",
            "교동",
            "남부시장",
            "풍남문",
        ],
        "longitude": 127.1484,
        "latitude": 35.8128,
        "radius": 1600,
    },
    "노송동": {
        "aliases": [
            "노송동",
            "중노송동",
            "남노송동",
            "서노송동",
            "전주시청",
            "시청",
            "시청앞",
            "시청 앞",
            "전주시청 앞",
            "병무청",
            "전북병무청",
            "전북지방병무청",
            "전주병무청",
        ],
        "longitude": 127.1510,
        "latitude": 35.8223,
        "radius": 1600,
    },
    "완산동": {
        "aliases": ["완산동", "동완산동", "서완산동", "서완산동1가", "서완산동2가"],
        "longitude": 127.1362,
        "latitude": 35.8110,
        "radius": 1600,
    },
    "동서학동": {
        "aliases": ["동서학동", "대성동", "색장동", "전주교대", "교대"],
        "longitude": 127.1559,
        "latitude": 35.8047,
        "radius": 2200,
    },
    "서서학동": {
        "aliases": ["서서학동"],
        "longitude": 127.1494,
        "latitude": 35.8042,
        "radius": 1500,
    },
    "중화산동": {
        "aliases": ["중화산동", "중화산", "중화산1동", "중화산2동", "중화산동1가", "중화산동2가"],
        "longitude": 127.1217,
        "latitude": 35.8137,
        "radius": 1800,
    },
    "평화동": {
        "aliases": ["평화동", "평화", "평화1동", "평화2동", "평화동1가", "평화동2가", "평화동3가", "석구동", "원당동"],
        "longitude": 127.1359,
        "latitude": 35.7947,
        "radius": 2200,
    },
    "서신동": {
        "aliases": ["서신동", "서신", "롯데백화점", "롯데백화점 전주점", "전주 롯데백화점", "이마트 전주점"],
        "longitude": 127.1218,
        "latitude": 35.8344,
        "radius": 1600,
    },
    "삼천동": {
        "aliases": [
            "삼천동",
            "삼천",
            "삼천1동",
            "삼천2동",
            "삼천3동",
            "삼천동1가",
            "삼천동2가",
            "삼천동3가",
            "중인동",
            "용복동",
        ],
        "longitude": 127.1212,
        "latitude": 35.7980,
        "radius": 2200,
    },
    "전북도청": {
        "aliases": [
            "전북도청",
            "도청",
            "전라북도청",
            "전북특별자치도청",
            "전북도청사",
            "도청사거리",
            "효자동 도청",
            "신시가지",
            "서부신시가지",
            "전주신시가지",
            "전주 신시가지",
            "홍산로",
            "홍산중앙로",
        ],
        "longitude": 127.1090,
        "latitude": 35.8202,
        "radius": 1600,
    },
    "전주대": {
        "aliases": [
            "전주대",
            "전주대학교",
            "전주대 정문",
            "전주대학교 정문",
            "전주대 구정문",
            "전주대학교 구정문",
            "전주대 근처",
            "천잠로 전주대",
            "전주대 스타센터",
        ],
        "longitude": 127.0899,
        "latitude": 35.8141,
        "radius": 1700,
    },
    "비전대": {
        "aliases": [
            "비전대",
            "전주비전대",
            "전주비전대학교",
            "비전대학교",
            "전주비전대학",
            "전주비전대 근처",
            "비전대 근처",
            "천잠로 비전대",
        ],
        "longitude": 127.0904,
        "latitude": 35.8091,
        "radius": 1500,
    },
    "효자동": {
        "aliases": [
            "효자동",
            "효자1동",
            "효자2동",
            "효자3동",
            "효자4동",
            "효자5동",
            "효자동1가",
            "효자동2가",
            "효자동3가",
            "상림동",
        ],
        "longitude": 127.1064,
        "latitude": 35.8195,
        "radius": 2600,
    },
    "완산구": {
        "aliases": ["완산구"],
        "longitude": 127.1397,
        "latitude": 35.8125,
        "radius": 4500,
    },
    "전북대 구정문": {
        "aliases": ["전북대 구정문", "전북대학교 구정문", "전대 구정문", "구정문", "북대 구정문"],
        "longitude": 127.1284,
        "latitude": 35.8452,
        "radius": 1200,
    },
    "전북대 신정문": {
        "aliases": [
            "전북대 신정문",
            "전북대학교 신정문",
            "전대 신정문",
            "북대 신정문",
            "신정문",
            "전북대 정문",
            "전북대학교 정문",
            "전북대 한옥정문",
            "전북대학교 한옥정문",
            "한옥정문",
            "전북대 한옥 정문",
            "전북대학교 한옥 정문",
            "전북대 신정문 오거리",
        ],
        "longitude": 127.1316,
        "latitude": 35.8414,
        "radius": 1200,
    },
    "전북대병원": {
        "aliases": ["전북대병원", "전북대학교병원", "전북대 병원", "전북대학교 병원"],
        "longitude": 127.1419,
        "latitude": 35.8473,
        "radius": 1300,
    },
    "사대부고사거리": {
        "aliases": ["사대부고사거리", "전주 사대부고사거리", "사대부고", "전북사대부고", "전북대 사대부고"],
        "longitude": 127.1400,
        "latitude": 35.8426,
        "radius": 1100,
    },
    "전북대": {
        "aliases": ["전북대", "전북대학교", "전대", "북대", "전북대 대학로", "전북대학교 대학로"],
        "longitude": 127.1297,
        "latitude": 35.8468,
        "radius": 1800,
    },
    "전주역": {
        "aliases": ["전주역", "역 앞", "역앞"],
        "longitude": 127.1616,
        "latitude": 35.8496,
        "radius": 1800,
    },
    "전주터미널": {
        "aliases": ["터미널", "고속버스터미널", "시외버스터미널", "전주터미널", "전주시외버스터미널", "전주고속버스터미널"],
        "longitude": 127.1248,
        "latitude": 35.8358,
        "radius": 1800,
    },
    "진북동": {
        "aliases": ["진북동"],
        "longitude": 127.1355,
        "latitude": 35.8296,
        "radius": 1500,
    },
    "인후동": {
        "aliases": [
            "인후동",
            "인후1동",
            "인후2동",
            "인후3동",
            "인후동1가",
            "인후동2가",
            "아중리",
            "아중",
            "모래내시장",
            "전주모래내시장",
        ],
        "longitude": 127.1623,
        "latitude": 35.8344,
        "radius": 2200,
    },
    "덕진동": {
        "aliases": [
            "덕진동",
            "덕진동1가",
            "덕진동2가",
            "덕진공원",
            "전주동물원",
            "종합경기장",
            "전주종합경기장",
            "전주 실내체육관",
            "전주실내체육관",
        ],
        "longitude": 127.1218,
        "latitude": 35.8465,
        "radius": 2000,
    },
    "금암동": {
        "aliases": ["금암동", "금암"],
        "longitude": 127.1330,
        "latitude": 35.8378,
        "radius": 1600,
    },
    "팔복동": {
        "aliases": ["팔복동", "팔복동1가", "팔복동2가", "팔복동3가", "팔복동4가"],
        "longitude": 127.1016,
        "latitude": 35.8495,
        "radius": 2200,
    },
    "우아동": {
        "aliases": ["우아동", "우아", "우아1동", "우아2동", "우아동1가", "우아동2가", "우아동3가", "산정동", "금상동"],
        "longitude": 127.1591,
        "latitude": 35.8336,
        "radius": 2200,
    },
    "호성동": {
        "aliases": ["호성동", "호성동1가", "호성동2가", "호성동3가"],
        "longitude": 127.1510,
        "latitude": 35.8585,
        "radius": 1800,
    },
    "송천동": {
        "aliases": ["송천동", "송천", "송천1동", "송천2동", "송천3동", "송천동1가", "송천동2가", "전미동", "전미동1가", "전미동2가", "에코시티", "전주에코시티"],
        "longitude": 127.1214,
        "latitude": 35.8694,
        "radius": 2400,
    },
    "조촌동": {
        "aliases": ["조촌동", "반월동", "화전동", "용정동", "성덕동", "원동", "도도동", "강흥동", "도덕동", "남정동"],
        "longitude": 127.0719,
        "latitude": 35.8693,
        "radius": 3200,
    },
    "여의동": {
        "aliases": ["여의동", "여의동2가", "고랑동", "동산동", "월드컵경기장", "전주월드컵경기장"],
        "longitude": 127.0757,
        "latitude": 35.8714,
        "radius": 2600,
    },
    "만성동": {
        "aliases": ["만성동", "만성", "법조타운", "전주법조타운"],
        "longitude": 127.0788,
        "latitude": 35.8402,
        "radius": 2000,
    },
    "혁신동": {
        "aliases": ["혁신동", "혁신도시", "전주혁신도시", "전북혁신도시", "중동", "장동"],
        "longitude": 127.0632,
        "latitude": 35.8381,
        "radius": 2600,
    },
    "덕진구": {
        "aliases": ["덕진구"],
        "longitude": 127.1340,
        "latitude": 35.8466,
        "radius": 5000,
    },
}


def jeonju_detail_area_aliases() -> dict[str, list[str]]:
    return {name: list(config["aliases"]) for name, config in JEONJU_SEARCH_AREAS.items()}


def jeonju_alias_terms() -> list[str]:
    terms: list[str] = []
    for config in JEONJU_SEARCH_AREAS.values():
        terms.extend(config["aliases"])
    return terms


def resolve_jeonju_search_area(text: str | None, *, near_gaeksa: bool = False) -> dict[str, Any] | None:
    if near_gaeksa:
        return {"name": "객사", "resolution_source": "local_jeonju_gazetteer", **JEONJU_SEARCH_AREAS["객사"]}

    query = text or ""
    matched: tuple[int, str, dict[str, Any]] | None = None
    for name, config in JEONJU_SEARCH_AREAS.items():
        for alias in config["aliases"]:
            if alias in query and (matched is None or len(alias) > matched[0]):
                matched = (len(alias), name, config)
    if matched is None:
        return None
    _, name, config = matched
    return {"name": name, "resolution_source": "local_jeonju_gazetteer", **config}
