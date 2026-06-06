from __future__ import annotations

import hashlib
import html
import json
import logging
import math
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from jeonju_gazetteer import JEONJU_SEARCH_AREAS, resolve_jeonju_search_area


mcp = FastMCP("공공데이터 맛집 서버")
logging.getLogger("httpx").setLevel(logging.WARNING)

GAEKSA_COORDINATES = {
    "longitude": JEONJU_SEARCH_AREAS["객사"]["longitude"],
    "latitude": JEONJU_SEARCH_AREAS["객사"]["latitude"],
}
CACHE_ROOT = Path("data/cache/tourapi")
DEFAULT_CACHE_TTL = timedelta(hours=24)
CONTENT_TYPE_RESTAURANT = "39"
KAKAO_LOCAL_BASE_URL = "https://dapi.kakao.com/v2/local"

CATEGORY_CUISINES = {
    "A05020100": "한식",
    "A05020200": "양식",
    "A05020300": "일식",
    "A05020400": "중식",
    "A05020500": "아시아식",
    "A05020600": "이색음식점",
    "A05020700": "카페",
    "A05020900": "카페",
}

CUISINE_KEYWORDS = {
    "한식": ["한식", "비빔", "국밥", "백반", "갈비", "전주", "콩나물", "한정식", "찌개", "칼국수"],
    "일식": ["일식", "초밥", "스시", "돈까스", "돈카츠", "우동", "라멘", "나베", "소바", "이자카야", "오마카세"],
    "중식": ["중식", "반점", "짜장", "자장", "짬뽕", "탕수육", "마라", "마라탕", "훠궈"],
    "분식": ["분식", "떡볶이", "김밥", "튀김", "라볶이", "순대"],
    "베이커리": ["빵집", "베이커리", "제과", "제빵", "빵", "바게트", "크루아상", "소금빵", "케이크"],
    "디저트 카페": ["디저트카페", "디저트 카페", "디저트", "빙수", "아이스크림", "케이크"],
    "카페": ["카페", "커피", "라떼", "디저트", "차", "찻집"],
    "고기": ["고기", "갈비", "삼겹", "구이", "장어", "불고기", "곱창", "막창", "족발", "보쌈", "치킨"],
    "이탈리안": ["이탈리안", "이탈리아", "파스타", "피자", "리조또"],
    "프렌치": ["프렌치", "프랑스"],
    "멕시칸": ["멕시칸", "멕시코", "타코", "부리또"],
    "양식": ["파스타", "피자", "스테이크", "브런치", "리조또", "양식", "버거", "햄버거", "샐러드"],
    "베트남": ["쌀국수", "베트남", "분짜", "반미"],
    "태국": ["태국", "타이", "팟타이", "똠얌"],
    "인도": ["인도", "커리", "카레", "난", "탄두리"],
    "아시아식": ["쌀국수", "베트남", "태국", "타이", "인도", "커리", "카레", "아시아"],
    "해산물": ["회", "횟집", "해산물", "생선", "조개", "초밥"],
    "술집": ["술집", "혼술", "한잔", "막걸리", "전집", "파전", "해물파전", "포차", "호프", "펍", "이자카야", "맥주", "소주", "와인", "와인바", "칵테일", "바"],
}
KAKAO_CATEGORY_CUISINE_RULES = [
    ("디저트 카페", ["디저트카페", "디저트 카페", "빙수", "아이스크림"]),
    ("베이커리", ["제과,베이커리", "제과", "제빵", "베이커리", "빵집"]),
    ("바", ["와인바", "칵테일바", "Bar", "BAR", " 바"]),
    ("술집", ["술집", "포장마차", "포차", "호프", "맥주", "이자카야", "주점"]),
    ("베트남", ["베트남", "쌀국수", "분짜", "반미"]),
    ("태국", ["태국", "타이", "팟타이"]),
    ("인도", ["인도", "커리", "카레"]),
    ("멕시칸", ["멕시칸", "멕시코", "타코"]),
    ("이탈리안", ["이탈리안", "이탈리아", "파스타", "피자", "리조또"]),
    ("프렌치", ["프렌치", "프랑스"]),
    ("일식", ["일식", "초밥", "스시", "라멘", "우동", "돈까스", "돈카츠", "소바"]),
    ("중식", ["중식", "중국", "반점", "짜장", "짬뽕", "마라", "훠궈"]),
    ("분식", ["분식", "떡볶이", "김밥", "순대"]),
    ("고기", ["육류", "고기", "삼겹", "갈비", "곱창", "막창", "족발", "보쌈", "치킨"]),
    ("해산물", ["해산물", "횟집", "생선회", "조개"]),
    ("카페", ["카페", "커피전문점", "커피"]),
    ("한식", ["한식", "국밥", "백반", "찌개", "전골", "칼국수", "비빔밥"]),
]
DRINKING_PLACE_TERMS = ["술집", "혼술", "한잔", "술자리", "포차", "호프", "펍", "이자카야", "맥주", "소주", "와인바", "칵테일바", "칵테일", "비어", "beer"]
TRADITIONAL_DRINKING_TERMS = ["막걸리", "전집", "파전", "해물파전"]
BAR_ONLY_TERMS = ["와인바", "칵테일바", "바", "bar", "BAR", "펍"]
BAKERY_TERMS = ["빵집", "베이커리", "제과", "제빵", "빵", "바게트", "크루아상", "소금빵", "케이크", "bakery", "BAKERY"]
BAKERY_EXCLUDE_TERMS = ["설빙", "더리터", "메가커피", "컴포즈", "빽다방", "스타벅스", "투썸", "이디야", "공차", "요거프레소", "쥬씨"]
STRICT_FOOD_QUERIES = {"술집", "바", "혼술", "한잔", "술자리", "막걸리", "전집", "파전", "해물파전", "포차", "호프", "펍", "이자카야", "맥주", "소주", "와인바", "칵테일", "칵테일바", "빵집", "베이커리", "빵", "디저트카페", "디저트 카페"}
KAKAO_BAR_KEYWORDS = ["술집", "포차", "호프", "펍", "이자카야", "맥주", "소주", "와인바", "칵테일바"]
KAKAO_BAR_ONLY_KEYWORDS = ["와인바", "칵테일바", "바", "펍"]
KAKAO_BAKERY_KEYWORDS = ["빵집", "베이커리", "제과점", "제빵소"]
KAKAO_DESSERT_CAFE_KEYWORDS = ["디저트카페", "디저트 카페", "빙수", "케이크"]
WEATHER_EXPECTATION_MATCH_TERMS = {
    "비": ["파전", "해물파전", "막걸리", "전집", "술집", "국밥", "찌개", "전골", "칼국수", "실내"],
    "눈": ["국밥", "탕", "찌개", "전골", "칼국수", "라멘", "우동", "실내"],
    "추움": ["국밥", "탕", "찌개", "전골", "칼국수", "라멘", "우동", "온면"],
    "더움": ["냉면", "콩국수", "막국수", "초계국수", "물회", "빙수", "샐러드", "카페"],
    "맑음": ["카페", "브런치", "테라스", "한옥", "공원", "도보"],
}

FOOD_QUERY_STOPWORDS = {
    "맛집",
    "음식점",
    "식당",
    "추천",
    "근처",
    "주변",
    "에서",
    "으로",
    "좋은",
    "괜찮은",
}


def _load_settings() -> dict[str, str]:
    load_dotenv()
    return {
        "service_key": os.getenv("TOUR_API_SERVICE_KEY", "").strip(),
        "base_url": os.getenv("TOUR_API_BASE_URL", "https://apis.data.go.kr/B551011/KorService2").rstrip("/"),
        "mobile_os": os.getenv("TOUR_API_MOBILE_OS", "ETC").strip() or "ETC",
        "mobile_app": os.getenv("TOUR_API_MOBILE_APP", "ReAct-aurant").strip() or "ReAct-aurant",
        "area_code": os.getenv("TOUR_API_DEFAULT_AREA_CODE", "37").strip() or "37",
        "sigungu_code": os.getenv("TOUR_API_DEFAULT_SIGUNGU_CODE", "12").strip() or "12",
    }


def _safe_params(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if key.lower() != "servicekey"}


def _mask_secret(text: str, secret: str) -> str:
    if not secret:
        return text
    return text.replace(secret, "***")


def _cache_key(path: str, params: dict[str, Any]) -> str:
    raw = json.dumps({"path": path, "params": _safe_params(params)}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_path(cache_key: str) -> Path:
    return CACHE_ROOT / f"{cache_key}.json"


def _read_cache(cache_key: str) -> dict[str, Any] | None:
    path = _cache_path(cache_key)
    if not path.exists():
        return None
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
        cached_at = datetime.fromisoformat(entry["cached_at"])
    except Exception:
        return None
    if datetime.now() - cached_at > DEFAULT_CACHE_TTL:
        return None
    return entry.get("payload")


def _write_cache(cache_key: str, path: str, params: dict[str, Any], payload: dict[str, Any]) -> None:
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    entry = {
        "cached_at": datetime.now().isoformat(timespec="seconds"),
        "path": path,
        "params": _safe_params(params),
        "payload": payload,
    }
    _cache_path(cache_key).write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")


def _tourapi_request(path: str, params: dict[str, Any], use_cache: bool = True) -> dict[str, Any]:
    settings = _load_settings()
    request_params = {
        "serviceKey": settings["service_key"],
        "MobileOS": settings["mobile_os"],
        "MobileApp": settings["mobile_app"],
        "_type": "json",
        **params,
    }
    cache_key = _cache_key(path, request_params)

    if use_cache:
        cached_payload = _read_cache(cache_key)
        if cached_payload is not None:
            return {
                "status": "ok",
                "source": "cache",
                "cache_key": cache_key,
                "payload": cached_payload,
            }

    if not settings["service_key"]:
        return {
            "status": "error",
            "source": "missing_api_key",
            "cache_key": cache_key,
            "message": "TOUR_API_SERVICE_KEY가 없어 TourAPI를 호출할 수 없습니다.",
        }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{settings['base_url']}/{path}", params=request_params)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        message = _mask_secret(str(exc), settings["service_key"])
        return {
            "status": "error",
            "source": "TourAPI",
            "cache_key": cache_key,
            "message": f"TourAPI 호출 실패: {message}",
        }

    result = _tourapi_result(payload)
    if result["result_code"] != "0000":
        return {
            "status": "error",
            "source": "TourAPI",
            "cache_key": cache_key,
            "result_code": result["result_code"],
            "message": result["result_msg"],
            "payload": payload,
        }

    _write_cache(cache_key, path, request_params, payload)
    return {
        "status": "ok",
        "source": "TourAPI",
        "cache_key": cache_key,
        "payload": payload,
    }


def _kakao_request(path: str, params: dict[str, Any]) -> dict[str, Any]:
    api_key = os.getenv("KAKAO_REST_API_KEY", "").strip()
    if not api_key:
        return {
            "status": "error",
            "source": "Kakao Local API",
            "message": "KAKAO_REST_API_KEY가 없어 Kakao Local API 장소 검색을 건너뜁니다.",
        }

    try:
        with httpx.Client(timeout=8.0) as client:
            response = client.get(
                f"{KAKAO_LOCAL_BASE_URL}/{path.lstrip('/')}",
                params={key: value for key, value in params.items() if value is not None},
                headers={"Authorization": f"KakaoAK {api_key}"},
            )
        response.raise_for_status()
        return {
            "status": "ok",
            "source": "Kakao Local API",
            "payload": response.json(),
        }
    except httpx.HTTPStatusError as exc:
        safe_text = _mask_secret(exc.response.text, api_key)
        if exc.response.status_code == 403 and "OPEN_MAP_AND_LOCAL" in safe_text:
            message = (
                "Kakao Local API 권한 오류 403: Kakao Developers 내 애플리케이션에서 "
                "카카오맵/로컬 API 서비스가 활성화되어 있지 않습니다. "
                "내 애플리케이션 > 제품 설정 또는 사용 설정에서 카카오맵/로컬 API 사용을 활성화해야 합니다."
            )
        else:
            message = f"Kakao Local API HTTP 오류 {exc.response.status_code}: {safe_text[:300]}"
        return {
            "status": "error",
            "source": "Kakao Local API",
            "message": message,
        }
    except Exception as exc:
        return {
            "status": "error",
            "source": "Kakao Local API",
            "message": f"Kakao Local API 호출 실패: {exc}",
        }


def _tourapi_result(payload: dict[str, Any]) -> dict[str, str]:
    if "response" in payload:
        header = payload.get("response", {}).get("header", {})
        return {
            "result_code": str(header.get("resultCode", "")),
            "result_msg": str(header.get("resultMsg", "")),
        }
    return {
        "result_code": str(payload.get("resultCode", "")),
        "result_msg": str(payload.get("resultMsg", "")),
    }


def _items_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    body = payload.get("response", {}).get("body", {})
    items = body.get("items") or {}
    item = items.get("item") if isinstance(items, dict) else None
    if item is None:
        return []
    if isinstance(item, list):
        return item
    if isinstance(item, dict):
        return [item]
    return []


def _body_total_count(payload: dict[str, Any]) -> int:
    body = payload.get("response", {}).get("body", {})
    try:
        return int(body.get("totalCount", 0))
    except (TypeError, ValueError):
        return 0


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            return text
    return None


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_search_area(area: str | None, near_gaeksa: bool = False) -> dict[str, Any] | None:
    return resolve_jeonju_search_area(area, near_gaeksa=near_gaeksa)


def _clean_jeonju_location_keyword(area: str | None) -> str | None:
    text = re.sub(r"\s+", " ", area or "").strip()
    if not text or "전주" not in text:
        return None
    text = re.sub(r"^전주시?\s*", "", text)
    text = re.sub(r"(맛집|음식점|식당|추천|근처|주변|에서|으로|가까운|찾아줘|알려줘)", " ", text)
    for terms in CUISINE_KEYWORDS.values():
        for term in terms:
            text = re.sub(re.escape(term), " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _resolve_search_area_from_tourapi(area: str | None, use_cache: bool = True) -> dict[str, Any] | None:
    keyword = _clean_jeonju_location_keyword(area)
    if not keyword:
        return None

    settings = _load_settings()
    keyword_candidates = [keyword]
    if not keyword.startswith("전주"):
        keyword_candidates.append(f"전주 {keyword}")

    for candidate in keyword_candidates:
        result = _tourapi_request(
            "searchKeyword2",
            {
                "numOfRows": 10,
                "pageNo": 1,
                "arrange": "A",
                "areaCode": settings["area_code"],
                "sigunguCode": settings["sigungu_code"],
                "keyword": candidate,
            },
            use_cache=use_cache,
        )
        if result["status"] != "ok":
            continue
        for item in _items_from_payload(result["payload"]):
            longitude = _float_or_none(_first_text(item.get("mapx")))
            latitude = _float_or_none(_first_text(item.get("mapy")))
            address = _first_text(item.get("addr1")) or ""
            if longitude is None or latitude is None or "전주" not in address:
                continue
            title = _first_text(item.get("title")) or keyword
            return {
                "name": keyword,
                "aliases": [keyword],
                "longitude": longitude,
                "latitude": latitude,
                "radius": 1800,
                "resolution_source": "TourAPI searchKeyword2",
                "resolved_from": {
                    "title": title,
                    "address": address,
                    "content_id": _first_text(item.get("contentid")),
                    "cache_key": result.get("cache_key"),
                },
            }
    return None


def _resolve_search_area_from_kakao(area: str | None) -> dict[str, Any] | None:
    keyword = _clean_jeonju_location_keyword(area)
    if not keyword:
        return None

    keyword_candidates = [keyword]
    if not keyword.startswith("전주"):
        keyword_candidates.append(f"전주 {keyword}")

    for candidate in keyword_candidates:
        result = _kakao_request(
            "search/keyword.json",
            {
                "query": candidate,
                "size": 10,
            },
        )
        if result["status"] != "ok":
            continue
        for item in result.get("payload", {}).get("documents", []):
            longitude = _float_or_none(item.get("x"))
            latitude = _float_or_none(item.get("y"))
            address = item.get("road_address_name") or item.get("address_name") or ""
            place_name = item.get("place_name") or keyword
            if longitude is None or latitude is None or "전주" not in address:
                continue
            return {
                "name": keyword,
                "aliases": [keyword],
                "longitude": longitude,
                "latitude": latitude,
                "radius": 1800,
                "resolution_source": "Kakao Local API keyword search",
                "resolved_from": {
                    "title": place_name,
                    "address": address,
                    "place_url": item.get("place_url"),
                    "kakao_id": item.get("id"),
                },
            }
    return None


def _resolve_search_area_for_query(
    area: str | None,
    near_gaeksa: bool = False,
    use_cache: bool = True,
) -> dict[str, Any] | None:
    fixed_area = _resolve_search_area(area, near_gaeksa=near_gaeksa)
    if fixed_area is not None:
        return fixed_area
    return _resolve_search_area_from_tourapi(area, use_cache=use_cache)


def _resolve_search_area_for_kakao_query(area: str | None, near_gaeksa: bool = False) -> dict[str, Any] | None:
    fixed_area = _resolve_search_area(area, near_gaeksa=near_gaeksa)
    if fixed_area is not None:
        return {**fixed_area, "resolution_source": fixed_area.get("resolution_source", "Jeonju gazetteer")}
    return _resolve_search_area_from_kakao(area)


def _distance_m(
    longitude: float | None,
    latitude: float | None,
    reference_coordinates: dict[str, float] | None = None,
) -> int | None:
    if longitude is None or latitude is None:
        return None

    reference = reference_coordinates or GAEKSA_COORDINATES
    lon1 = math.radians(reference["longitude"])
    lat1 = math.radians(reference["latitude"])
    lon2 = math.radians(longitude)
    lat2 = math.radians(latitude)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return int(round(6371000 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))))


def _split_menu(value: str | None) -> list[str]:
    if not value:
        return []
    cleaned = re.sub(r"<[^>]+>", " ", value)
    parts = re.split(r"[,/|·\n\r]+", cleaned)
    return [part.strip() for part in parts if part.strip()][:6]


def _infer_cuisine(raw: dict[str, Any], menus: list[str]) -> str | None:
    cat3 = _first_text(raw.get("cat3"))
    if cat3 in CATEGORY_CUISINES:
        return CATEGORY_CUISINES[cat3]

    haystack = " ".join(
        str(value)
        for value in [
            raw.get("title"),
            raw.get("addr1"),
            raw.get("overview"),
            raw.get("firstmenu"),
            raw.get("treatmenu"),
            " ".join(menus),
        ]
        if value
    )
    for cuisine, keywords in CUISINE_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return cuisine
    return None


def _standardize_restaurant(
    item: dict[str, Any],
    detail_common: dict[str, Any] | None = None,
    detail_intro: dict[str, Any] | None = None,
    reference_coordinates: dict[str, float] | None = None,
    reference_name: str | None = None,
) -> dict[str, Any]:
    common = detail_common or {}
    intro = detail_intro or {}
    raw = {**item, **common, **intro}

    content_id = _first_text(raw.get("contentid"), raw.get("contentId")) or ""
    longitude = _float_or_none(_first_text(raw.get("mapx")))
    latitude = _float_or_none(_first_text(raw.get("mapy")))
    distance = _float_or_none(raw.get("dist"))
    if distance is None and reference_coordinates is not None:
        distance = _distance_m(longitude, latitude, reference_coordinates)

    menus = _split_menu(_first_text(raw.get("firstmenu"), raw.get("treatmenu")))
    cuisine = _infer_cuisine(raw, menus)
    address = " ".join(
        part for part in [_first_text(raw.get("addr1")), _first_text(raw.get("addr2"))] if part
    ).strip()
    name = _first_text(raw.get("title")) or "이름 없는 음식점"
    overview = _first_text(raw.get("overview"))

    restaurant = {
        "restaurant_id": f"tourapi:{content_id}",
        "content_id": content_id,
        "name": name,
        "location": "전주",
        "address": address or None,
        "cuisine": cuisine,
        "category_codes": {
            "cat1": _first_text(raw.get("cat1")),
            "cat2": _first_text(raw.get("cat2")),
            "cat3": _first_text(raw.get("cat3")),
        },
        "phone": _first_text(raw.get("tel"), raw.get("infocenterfood")),
        "image_url": _first_text(raw.get("firstimage")),
        "thumbnail_url": _first_text(raw.get("firstimage2")),
        "longitude": longitude,
        "latitude": latitude,
        "distance_m": int(distance) if distance is not None else None,
        "distance_reference": reference_name,
        "rating": None,
        "review_count": None,
        "average_price": None,
        "signature_menu": menus,
        "overview": overview,
        "operation": {
            "open_time": _first_text(raw.get("opentimefood")),
            "rest_date": _first_text(raw.get("restdatefood")),
            "parking": _first_text(raw.get("parkingfood")),
            "reservation": _first_text(raw.get("reservationfood")),
        },
        "source": "TourAPI KorService2",
        "source_confidence": 0.9,
        "modified_time": _first_text(raw.get("modifiedtime")),
        "recommendation_reason": "한국관광공사 TourAPI에 등록된 전주시 음식점입니다.",
        "source_note": "TourAPI는 평점, 리뷰 수, 가격대를 제공하지 않아 해당 항목은 추천 기준에 포함하지 않습니다.",
    }
    return restaurant


def _infer_kakao_cuisine(document: dict[str, Any], requested_keyword: str | None = None) -> str:
    category_name = str(document.get("category_name") or "")
    blob = " ".join(
        str(value)
        for value in [
            document.get("place_name"),
            category_name,
            document.get("category_group_name"),
        ]
        if value
    )
    if _has_bakery_signal(blob):
        return "베이커리"
    if _has_strict_bar_signal(blob):
        return "바"
    if _has_bar_place_signal(blob):
        return "술집"
    category_leaf = _kakao_food_category_leaf(category_name)
    if category_leaf:
        return category_leaf
    for cuisine, keywords in KAKAO_CATEGORY_CUISINE_RULES:
        if any(keyword in blob for keyword in keywords):
            return cuisine
    for cuisine, keywords in CUISINE_KEYWORDS.items():
        if any(keyword in blob for keyword in keywords):
            return cuisine
    return document.get("category_group_name") or "음식점"


def _kakao_food_category_leaf(category_name: str | None) -> str | None:
    if not category_name or "음식점" not in category_name:
        return None
    parts = [part.strip() for part in str(category_name).split(">") if part.strip()]
    if not parts:
        return None
    leaf = parts[-1].strip()
    if not leaf or leaf == "음식점":
        return None
    return re.sub(r"\s+", " ", leaf)


def _standardize_kakao_place(
    document: dict[str, Any],
    reference_coordinates: dict[str, float] | None,
    reference_name: str | None,
    requested_keyword: str | None = None,
) -> dict[str, Any]:
    longitude = _float_or_none(document.get("x"))
    latitude = _float_or_none(document.get("y"))
    distance = _float_or_none(document.get("distance"))
    if distance is None and reference_coordinates is not None:
        distance = _distance_m(longitude, latitude, reference_coordinates)

    address = document.get("road_address_name") or document.get("address_name") or None
    category_name = document.get("category_name") or ""
    place_url = document.get("place_url") or None
    place_id = str(document.get("id") or document.get("place_name") or "")

    return {
        "restaurant_id": f"kakao:{place_id}",
        "content_id": place_id,
        "name": document.get("place_name") or "이름 없는 장소",
        "location": "전주",
        "address": address,
        "cuisine": _infer_kakao_cuisine(document, requested_keyword),
        "category_codes": {
            "cat1": "KAKAO_LOCAL",
            "cat2": document.get("category_group_code"),
            "cat3": category_name,
        },
        "phone": document.get("phone") or None,
        "image_url": None,
        "thumbnail_url": None,
        "longitude": longitude,
        "latitude": latitude,
        "distance_m": int(distance) if distance is not None else None,
        "distance_reference": reference_name,
        "rating": None,
        "review_count": None,
        "average_price": None,
        "signature_menu": [],
        "search_keyword": requested_keyword,
        "overview": f"Kakao Local category: {category_name}".strip(),
        "operation": {
            "open_time": None,
            "rest_date": None,
            "parking": None,
            "reservation": None,
        },
        "source": "Kakao Local API",
        "source_confidence": 0.86,
        "modified_time": None,
        "place_url": place_url,
        "recommendation_reason": "Kakao Local API 장소 검색 결과의 위치, 카테고리, 거리 정보를 반영했습니다.",
        "source_note": "Kakao Local API 공식 응답은 장소명, 주소, 카테고리, 전화번호, 거리, 장소 URL을 제공하며 평점/리뷰/가격대는 제공하지 않습니다. 장소 URL에서 사용자가 직접 추가 후기를 확인할 수 있습니다.",
    }


def _kakao_metadata_quality(restaurant: dict[str, Any], cuisine: str | None = None) -> tuple[int, list[str]]:
    checks: list[str] = []
    if restaurant.get("place_url"):
        checks.append("카카오 장소 링크 제공")
    if restaurant.get("category_codes", {}).get("cat3"):
        checks.append("카카오 세부 카테고리 제공")
    if restaurant.get("address"):
        checks.append("전주 주소 확인")
    if restaurant.get("distance_m") is not None:
        checks.append("기준 위치와 거리 확인")
    if restaurant.get("phone"):
        checks.append("전화번호 제공")
    if cuisine and _matches_food_query(restaurant, cuisine):
        checks.append("요청 업종 직접 일치")
    return len(checks), checks


def _text_blob(restaurant: dict[str, Any]) -> str:
    return " ".join(
        str(value)
        for value in [
            restaurant.get("name"),
            restaurant.get("address"),
            restaurant.get("cuisine"),
            restaurant.get("overview"),
            " ".join(restaurant.get("signature_menu", [])),
            restaurant.get("operation", {}).get("open_time"),
        ]
        if value
    )


def _food_query_terms(food_query: str | None) -> list[str]:
    if not food_query:
        return []
    query = food_query.strip()
    if not query:
        return []

    terms = [query]
    for cuisine, keywords in CUISINE_KEYWORDS.items():
        if query == cuisine or query in keywords or any(keyword in query for keyword in keywords):
            terms.extend([cuisine, *keywords])
    cleaned_terms: list[str] = []
    for term in terms:
        term = term.strip()
        if term and term not in FOOD_QUERY_STOPWORDS and term not in cleaned_terms:
            cleaned_terms.append(term)
    if any(term in STRICT_FOOD_QUERIES for term in cleaned_terms):
        priority_terms = ["술집", "바", "와인바", "칵테일바", "막걸리", "전집", "파전", "해물파전", "이자카야", "포차", "호프", "펍", "맥주", "빵집", "베이커리", "빵", "디저트카페", "디저트 카페"]
        return [term for term in priority_terms if term in cleaned_terms] + [
            term for term in cleaned_terms if term not in priority_terms
        ]
    return cleaned_terms


def _has_strict_bar_signal(blob: str) -> bool:
    if any(term in blob for term in BAR_ONLY_TERMS if term != "바"):
        return True
    return bool(re.search(r"(^|[^가-힣A-Za-z])바($|[^가-힣A-Za-z])", blob))


def _has_bar_place_signal(blob: str) -> bool:
    if any(term in blob for term in [*DRINKING_PLACE_TERMS, *TRADITIONAL_DRINKING_TERMS]):
        return True
    # "주점" is a valid category term, but it appears inside "전주점" in branch names.
    return bool(re.search(r"(?<!전)주점", blob))


def _has_traditional_drinking_signal(blob: str) -> bool:
    return any(term in blob for term in TRADITIONAL_DRINKING_TERMS)


def _has_bakery_signal(blob: str) -> bool:
    if any(term in blob for term in BAKERY_EXCLUDE_TERMS):
        return False
    return any(term in blob for term in BAKERY_TERMS)


def _matches_food_query(restaurant: dict[str, Any], food_query: str | None) -> bool:
    terms = _food_query_terms(food_query)
    if not terms:
        return True
    cuisine = str(restaurant.get("cuisine") or "")
    blob = _text_blob(restaurant)
    requested = str(food_query or "").strip()
    if requested == "바":
        return _has_strict_bar_signal(blob)
    if requested in {"빵집", "베이커리", "빵"}:
        return _has_bakery_signal(blob)
    if requested in {"디저트카페", "디저트 카페"}:
        return any(term in blob for term in ["디저트카페", "디저트 카페", "빙수", "아이스크림", "케이크"])
    if requested in {"막걸리", "전집", "파전", "해물파전"}:
        return _has_traditional_drinking_signal(blob)
    if requested == "술집":
        return _has_bar_place_signal(blob)
    return any(term == cuisine or term in blob for term in terms)


def _is_jeonju_restaurant(restaurant: dict[str, Any]) -> bool:
    return "전주" in (restaurant.get("address") or "")


def _merge_restaurants(restaurants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for restaurant in restaurants:
        key = restaurant.get("content_id") or restaurant.get("restaurant_id") or restaurant.get("name")
        if key is None:
            continue
        existing = merged.get(str(key))
        if existing is None:
            merged[str(key)] = restaurant
            continue
        existing_completeness = sum(1 for value in existing.values() if value)
        new_completeness = sum(1 for value in restaurant.values() if value)
        if new_completeness > existing_completeness:
            merged[str(key)] = restaurant
    return list(merged.values())


def _score_public_restaurant(
    restaurant: dict[str, Any],
    ranking_policy: dict[str, Any],
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    address = restaurant.get("address") or ""
    if "전주" in address:
        score += 18
        reasons.append("전주 주소 일치")

    distance_reference = restaurant.get("distance_reference") or "검색 기준"
    distance_m = restaurant.get("distance_m")
    if isinstance(distance_m, int):
        if distance_m <= 500:
            score += 14
            reasons.append(f"{distance_reference} 기준 500m 이내")
        elif distance_m <= 1000:
            score += 10
            reasons.append(f"{distance_reference} 기준 1km 이내")
        elif distance_m <= 1500:
            score += 7
            reasons.append(f"{distance_reference} 기준 1.5km 이내")
        else:
            score += 3
            reasons.append("전주 권역 좌표 보유")

    if restaurant.get("category_codes", {}).get("cat1") == "A05":
        score += 10
        reasons.append("음식점 분류")

    completeness = 0
    for field in ["address", "phone", "image_url", "longitude", "latitude"]:
        if restaurant.get(field):
            completeness += 1
    if restaurant.get("signature_menu"):
        completeness += 1
    if restaurant.get("operation", {}).get("open_time"):
        completeness += 1
    score += completeness * 2
    reasons.append(f"상세정보 {completeness}개 확보")

    if restaurant.get("source") == "Kakao Local API":
        metadata_score = int(restaurant.get("metadata_quality_score") or 0)
        metadata_checks = restaurant.get("metadata_quality_checks") or []
        if metadata_score:
            score += min(10, metadata_score * 2)
            reasons.append(f"공식 메타데이터 검증 {metadata_score}점: {', '.join(metadata_checks[:4])}")

    desired_cuisine = ranking_policy.get("cuisine")
    strict_food_requested = bool(desired_cuisine and str(desired_cuisine) in STRICT_FOOD_QUERIES)
    if desired_cuisine and _matches_food_query(restaurant, str(desired_cuisine)):
        score += 20 if strict_food_requested else 10
        reasons.append(f"{desired_cuisine} 조건 일치")
    elif desired_cuisine:
        score -= 18 if strict_food_requested else 6
        reasons.append(f"{desired_cuisine} 조건 직접 매칭 없음")

    preferred_cuisines = ranking_policy.get("preferred_cuisines", []) or []
    if restaurant.get("cuisine") in preferred_cuisines:
        score += 4
        reasons.append("사용자 선호 음식 분류")

    blob = _text_blob(restaurant)
    purpose = str(ranking_policy.get("purpose", ""))
    if "친구" in purpose and any(keyword in blob for keyword in ["객사", "길", "회관", "관", "식당"]):
        score += 4
        reasons.append("친구 방문 목적에 활용 가능한 음식점 정보")
    if "저녁" in purpose and restaurant.get("cuisine") != "카페":
        score += 5
        reasons.append("카페보다 식사 후보에 가까움")
    if any(term in purpose for term in ["혼술", "술자리"]) and (_has_bar_place_signal(blob) or _has_traditional_drinking_signal(blob)):
        score += 12
        reasons.append("술자리 목적과 직접 관련된 메뉴/업종 단서")

    weather_hints = ranking_policy.get("weather_hints", []) or []
    matched_hints = [hint for hint in weather_hints if hint and len(str(hint)) > 1 and hint in blob]
    if matched_hints:
        score += min(14, 4 + len(matched_hints) * 3)
        reasons.append(f"날씨 힌트 매칭: {', '.join(matched_hints[:3])}")

    requested_weather = ranking_policy.get("requested_weather")
    expectation_terms = WEATHER_EXPECTATION_MATCH_TERMS.get(str(requested_weather), [])
    matched_expectations = [term for term in expectation_terms if term in blob]
    if matched_expectations:
        score += 10
        reasons.append(f"{requested_weather} 날씨 보편 기대 매칭: {', '.join(matched_expectations[:3])}")
    if requested_weather == "비" and isinstance(distance_m, int):
        if distance_m <= 500:
            score += 6
            reasons.append("비 오는 날 이동 부담이 낮은 가까운 거리")
        elif distance_m <= 1000:
            score += 3
            reasons.append("비 오는 날 이동 가능한 거리")

    max_distance_m = ranking_policy.get("max_distance_m")
    if isinstance(distance_m, int) and max_distance_m:
        if distance_m <= int(max_distance_m):
            score += 4
            reasons.append(f"요청 거리 {int(max_distance_m)}m 이내")
            if distance_m <= int(max_distance_m) * 0.6:
                score += 3
                reasons.append("요청 위치 중심에 가까운 후보")
        else:
            score -= 100
            reasons.append(f"요청 거리 {int(max_distance_m)}m 초과")

    source_label = "Kakao Local" if restaurant.get("source") == "Kakao Local API" else "TourAPI"
    if ranking_policy.get("min_rating") is not None and restaurant.get("rating") is None:
        reasons.append(f"{source_label} 평점 미제공")
    if ranking_policy.get("min_review_count") is not None and restaurant.get("review_count") is None:
        reasons.append(f"{source_label} 리뷰 수 미제공")
    if ranking_policy.get("max_price_level") is not None and restaurant.get("average_price") is None:
        reasons.append(f"{source_label} 가격대 미제공")

    if not restaurant.get("address"):
        score -= 5
        reasons.append("주소 누락")
    if restaurant.get("distance_m") is None:
        score -= 4
        reasons.append("좌표/거리 정보 누락")

    return round(score, 2), reasons


def _keyword_restaurants(
    food_query: str | None,
    reference_coordinates: dict[str, float] | None,
    reference_name: str | None,
    use_cache: bool,
    rows: int,
) -> list[dict[str, Any]]:
    terms = _food_query_terms(food_query)
    if not terms:
        return []

    settings = _load_settings()
    restaurants: list[dict[str, Any]] = []
    for term in terms[:8]:
        result = _tourapi_request(
            "searchKeyword2",
            {
                "numOfRows": rows,
                "pageNo": 1,
                "arrange": "A",
                "contentTypeId": CONTENT_TYPE_RESTAURANT,
                "areaCode": settings["area_code"],
                "sigunguCode": settings["sigungu_code"],
                "keyword": term,
            },
            use_cache=use_cache,
        )
        if result["status"] != "ok":
            continue
        for item in _items_from_payload(result["payload"]):
            restaurants.append(
                _standardize_restaurant(
                    item,
                    reference_coordinates=reference_coordinates,
                    reference_name=reference_name,
                )
            )
    return _merge_restaurants(restaurants)


@mcp.tool()
def search_tourapi_restaurants(
    area: str = "전주",
    keyword: str | None = None,
    cuisine: str | None = None,
    max_price_level: int | None = None,
    min_rating: float | None = None,
    min_review_count: int | None = None,
    max_distance_m: int | None = None,
    near_gaeksa: bool = False,
    limit: int = 20,
    use_cache: bool = True,
) -> dict[str, Any]:
    """한국관광공사 TourAPI에서 전주 음식점 후보를 검색합니다."""
    if "전주" not in (area or ""):
        return {
            "status": "error",
            "source": "TourAPI KorService2",
            "message": "현재 공공데이터 검색 범위는 전주로 한정되어 있습니다.",
            "candidates": [],
        }

    rows = min(max(int(limit) * 3, 20), 100)
    settings = _load_settings()
    search_area = _resolve_search_area_for_query(area, near_gaeksa=near_gaeksa, use_cache=use_cache)
    if search_area is not None:
        path = "locationBasedList2"
        effective_radius = int(max_distance_m or search_area["radius"])
        params = {
            "numOfRows": rows,
            "pageNo": 1,
            "arrange": "A",
            "contentTypeId": CONTENT_TYPE_RESTAURANT,
            "mapX": search_area["longitude"],
            "mapY": search_area["latitude"],
            "radius": min(max(effective_radius, 300), 20000),
        }
    else:
        path = "areaBasedList2"
        params = {
            "numOfRows": rows,
            "pageNo": 1,
            "arrange": "A",
            "contentTypeId": CONTENT_TYPE_RESTAURANT,
            "areaCode": settings["area_code"],
            "sigunguCode": settings["sigungu_code"],
        }

    result = _tourapi_request(path, params, use_cache=use_cache)
    if result["status"] != "ok":
        return {
            **result,
            "query": {"area": area, "keyword": keyword, "near_gaeksa": near_gaeksa, "limit": limit},
            "candidates": [],
        }

    payload = result["payload"]
    reference_coordinates = (
        {"longitude": search_area["longitude"], "latitude": search_area["latitude"]} if search_area is not None else None
    )
    reference_name = search_area["name"] if search_area is not None else None
    restaurants = [
        _standardize_restaurant(
            item,
            reference_coordinates=reference_coordinates,
            reference_name=reference_name,
        )
        for item in _items_from_payload(payload)
    ]

    food_query = cuisine or keyword
    restaurants = _merge_restaurants(
        restaurants
        + _keyword_restaurants(
            food_query=food_query,
            reference_coordinates=reference_coordinates,
            reference_name=reference_name,
            use_cache=use_cache,
            rows=rows,
        )
    )
    restaurants = [restaurant for restaurant in restaurants if _is_jeonju_restaurant(restaurant)]

    if max_distance_m and reference_coordinates is not None:
        restaurants = [
            restaurant
            for restaurant in restaurants
            if restaurant.get("distance_m") is None or int(restaurant["distance_m"]) <= int(max_distance_m)
        ]

    matched_food = [restaurant for restaurant in restaurants if _matches_food_query(restaurant, food_query)]
    food_filter_relaxed = False
    if food_query:
        if matched_food:
            restaurants = matched_food
        else:
            food_filter_relaxed = True

    restaurants.sort(
        key=lambda restaurant: (
            restaurant.get("distance_m") is None,
            restaurant.get("distance_m") if restaurant.get("distance_m") is not None else 999999,
            restaurant.get("name") or "",
        )
    )

    unavailable_filters = []
    if min_rating is not None:
        unavailable_filters.append("rating")
    if min_review_count is not None:
        unavailable_filters.append("review_count")
    if max_price_level is not None:
        unavailable_filters.append("price_level")

    return {
        "status": "ok",
        "source": result["source"],
        "cache_key": result["cache_key"],
        "query": {
            "area": area,
            "keyword": keyword,
            "cuisine": cuisine,
            "max_price_level": max_price_level,
            "min_rating": min_rating,
            "min_review_count": min_review_count,
            "max_distance_m": max_distance_m,
            "near_gaeksa": near_gaeksa,
            "target_area": search_area["name"] if search_area is not None else None,
            "location_resolution": (
                {
                    "status": "resolved",
                    "source": search_area.get("resolution_source"),
                    "longitude": search_area["longitude"],
                    "latitude": search_area["latitude"],
                    "resolved_from": search_area.get("resolved_from"),
                }
                if search_area is not None
                else {"status": "unresolved_fallback_to_jeonju_area_list", "source": None}
            ),
            "limit": limit,
            "contentTypeId": CONTENT_TYPE_RESTAURANT,
            "search_method": path,
            "radius": params.get("radius"),
            "food_filter_relaxed": food_filter_relaxed,
        },
        "unavailable_filters": unavailable_filters,
        "data_limitations": (
            "TourAPI KorService2는 평점, 리뷰 수, 가격대를 제공하지 않아 해당 조건은 거리/상세정보/음식종류 점수와 한계 고지로 처리합니다."
            if unavailable_filters
            else None
        ),
        "total_count": _body_total_count(payload),
        "count": len(restaurants[: max(1, limit)]),
        "candidates": restaurants[: max(1, limit)],
        "message": (
            f"전주 {search_area['name']} 주변 음식점 공공데이터 후보를 조회했습니다."
            if search_area is not None
            else "전주 전체 음식점 공공데이터 후보를 조회했습니다."
        ),
    }


@mcp.tool()
def search_kakao_local_places(
    area: str = "전주",
    keyword: str | None = None,
    cuisine: str | None = None,
    max_price_level: int | None = None,
    min_rating: float | None = None,
    min_review_count: int | None = None,
    max_distance_m: int | None = None,
    near_gaeksa: bool = False,
    limit: int = 10,
) -> dict[str, Any]:
    """Kakao Local API에서 전주 장소 후보를 검색합니다. 키가 없으면 error Observation을 반환합니다."""
    if "전주" not in (area or ""):
        return {
            "status": "error",
            "source": "Kakao Local API",
            "message": "현재 Kakao Local 보강 검색 범위는 전주로 한정되어 있습니다.",
            "candidates": [],
        }

    search_area = _resolve_search_area_for_kakao_query(area, near_gaeksa=near_gaeksa)
    if search_area is None:
        return {
            "status": "error",
            "source": "Kakao Local API",
            "message": "전주 세부 위치 좌표를 해석하지 못해 Kakao Local 반경 검색을 수행하지 않았습니다.",
            "candidates": [],
        }

    radius = min(max(int(max_distance_m or search_area["radius"]), 300), 20000)
    reference_coordinates = {"longitude": search_area["longitude"], "latitude": search_area["latitude"]}
    requested = (cuisine or keyword or "맛집").strip()
    if requested == "술집":
        queries = KAKAO_BAR_KEYWORDS
    elif requested == "바":
        queries = KAKAO_BAR_ONLY_KEYWORDS
    elif requested in {"빵집", "베이커리", "빵"}:
        queries = KAKAO_BAKERY_KEYWORDS
    elif requested in {"디저트카페", "디저트 카페"}:
        queries = KAKAO_DESSERT_CAFE_KEYWORDS
    elif requested in {"막걸리", "전집", "파전", "해물파전"}:
        queries = [requested]
    else:
        queries = [requested]

    places: list[dict[str, Any]] = []
    last_error: dict[str, Any] | None = None
    for query in queries:
        result = _kakao_request(
            "search/keyword.json",
            {
                "query": query,
                "x": search_area["longitude"],
                "y": search_area["latitude"],
                "radius": radius,
                "sort": "distance",
                "size": min(max(limit, 1), 15),
            },
        )
        if result["status"] != "ok":
            last_error = result
            continue
        for document in result.get("payload", {}).get("documents", []):
            places.append(
                _standardize_kakao_place(
                    document,
                    reference_coordinates=reference_coordinates,
                    reference_name=search_area["name"],
                    requested_keyword=query,
                )
            )

    places = _merge_restaurants(places)
    places = [place for place in places if _is_jeonju_restaurant(place)]
    if max_distance_m:
        places = [
            place
            for place in places
            if place.get("distance_m") is None or int(place["distance_m"]) <= int(max_distance_m)
        ]
    if cuisine in {"술집", "바", "빵집", "베이커리", "빵", "디저트카페", "디저트 카페", "막걸리", "전집", "파전", "해물파전"}:
        places = [place for place in places if _matches_food_query(place, cuisine)]

    metric_conditions_requested = any(value is not None for value in [max_price_level, min_rating, min_review_count])
    for place in places:
        quality_score, quality_checks = _kakao_metadata_quality(place, cuisine)
        place["metadata_quality_score"] = quality_score
        place["metadata_quality_checks"] = quality_checks
    if metric_conditions_requested:
        places = [place for place in places if int(place.get("metadata_quality_score") or 0) >= 4]

    places.sort(
        key=lambda place: (
            -int(place.get("metadata_quality_score") or 0),
            place.get("distance_m") is None,
            int(place.get("distance_m") if place.get("distance_m") is not None else 999999),
            place.get("name") or "",
        )
    )

    if not places and last_error is not None:
        return {
            **last_error,
            "query": {
                "area": area,
                "keyword": keyword,
                "cuisine": cuisine,
                "max_price_level": max_price_level,
                "min_rating": min_rating,
                "min_review_count": min_review_count,
                "max_distance_m": max_distance_m,
                "target_area": search_area["name"],
                "radius": radius,
                "queries": queries,
                "location_resolution": search_area.get("resolution_source"),
            },
            "candidates": [],
        }

    return {
        "status": "ok" if places else "error",
        "source": "Kakao Local API",
        "query": {
            "area": area,
            "keyword": keyword,
            "cuisine": cuisine,
            "max_price_level": max_price_level,
            "min_rating": min_rating,
            "min_review_count": min_review_count,
            "max_distance_m": max_distance_m,
            "target_area": search_area["name"],
            "radius": radius,
            "queries": queries,
            "location_resolution": search_area.get("resolution_source"),
        },
        "unavailable_filters": ["rating", "review_count", "price_level"],
        "metric_proxy_policy": (
            "평점/리뷰 수/가격대는 Kakao Local API 공식 응답에 없어 직접 필터링하지 않고, 장소 링크·세부 카테고리·주소·거리·전화번호·업종 일치 기반 공식 메타데이터 검증 점수를 최소 4점 이상으로 적용했습니다."
            if metric_conditions_requested
            else None
        ),
        "data_limitations": "Kakao Local API 공식 응답은 평점, 리뷰 수, 가격대를 제공하지 않습니다. 해당 수치는 생성하지 않고 장소명, 세부 카테고리, 주소, 거리, 전화번호, 장소 URL의 공식 메타데이터 검증으로 보완합니다.",
        "count": len(places[: max(1, limit)]),
        "candidates": places[: max(1, limit)],
        "message": (
            f"Kakao Local API로 전주 {search_area['name']} 주변 장소 후보를 조회했습니다."
            if places
            else "Kakao Local API에서 조건에 맞는 장소 후보를 확보하지 못했습니다."
        ),
    }


@mcp.tool()
def get_tourapi_restaurant_detail(content_id: str, use_cache: bool = True) -> dict[str, Any]:
    """TourAPI content_id에 해당하는 음식점 상세 정보를 조회합니다."""
    safe_content_id = (content_id or "").replace("tourapi:", "").strip()
    if not safe_content_id:
        return {
            "status": "error",
            "source": "TourAPI KorService2",
            "message": "content_id가 비어 있습니다.",
            "restaurant": None,
        }

    common_result = _tourapi_request(
        "detailCommon2",
        {
            "contentId": safe_content_id,
        },
        use_cache=use_cache,
    )
    intro_result = _tourapi_request(
        "detailIntro2",
        {
            "contentId": safe_content_id,
            "contentTypeId": CONTENT_TYPE_RESTAURANT,
        },
        use_cache=use_cache,
    )

    if common_result["status"] != "ok":
        return {
            **common_result,
            "restaurant": None,
        }

    common_items = _items_from_payload(common_result["payload"])
    intro_items = _items_from_payload(intro_result["payload"]) if intro_result["status"] == "ok" else []
    common = common_items[0] if common_items else {"contentid": safe_content_id}
    intro = intro_items[0] if intro_items else {}
    restaurant = _standardize_restaurant(common, detail_common=common, detail_intro=intro)

    return {
        "status": "ok",
        "source": common_result["source"],
        "content_id": safe_content_id,
        "common_cache_key": common_result["cache_key"],
        "intro_cache_key": intro_result.get("cache_key"),
        "restaurant": restaurant,
        "message": "TourAPI 음식점 상세 정보를 조회했습니다.",
    }


@mcp.tool()
def rank_tourapi_restaurants(
    candidates: list[dict[str, Any]],
    ranking_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """TourAPI 후보를 공공데이터에 맞는 기준으로 점수화하고 정렬합니다."""
    policy = ranking_policy or {}
    ranked_candidates: list[dict[str, Any]] = []
    source_names = {candidate.get("source") for candidate in candidates if candidate.get("source")}
    source_name = "Kakao Local API" if "Kakao Local API" in source_names else "TourAPI KorService2"

    for candidate in candidates:
        score, reasons = _score_public_restaurant(candidate, policy)
        ranked = candidate.copy()
        ranked["score"] = score
        ranked["score_reasons"] = reasons
        ranked["recommendation_reason"] = (
            "Kakao Local API 장소 검색 결과 기준으로 주소, 거리, 카테고리, 요청 조건 일치도를 반영했습니다."
            if ranked.get("source") == "Kakao Local API"
            else "한국관광공사 TourAPI 등록 정보 기준으로 주소, 거리, 상세정보 충실도, 요청 조건 일치도를 반영했습니다."
        )
        ranked_candidates.append(ranked)

    ranked_candidates.sort(
        key=lambda item: (
            -float(item["score"]),
            item.get("distance_m") is None,
            int(item.get("distance_m") if item.get("distance_m") is not None else 999999),
            item.get("name") or "",
        )
    )

    return {
        "status": "ok" if ranked_candidates else "error",
        "source": source_name,
        "ranking_policy": policy,
        "ranked_candidates": ranked_candidates,
        "message": "장소 후보 정렬을 완료했습니다." if ranked_candidates else "정렬할 장소 후보가 없습니다.",
    }


@mcp.tool()
def cache_tourapi_response(cache_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    """제출 검증용으로 공개 TourAPI 응답 payload를 캐시에 저장합니다."""
    safe_key = re.sub(r"[^a-zA-Z0-9_-]", "_", cache_key or "").strip("_")
    if not safe_key:
        return {"status": "error", "message": "cache_key가 비어 있습니다."}
    _write_cache(safe_key, "manual", {}, payload)
    return {
        "status": "ok",
        "cache_key": safe_key,
        "message": "TourAPI 캐시를 저장했습니다.",
    }


if __name__ == "__main__":
    mcp.run("stdio")
