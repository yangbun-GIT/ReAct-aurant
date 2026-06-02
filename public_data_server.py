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


mcp = FastMCP("공공데이터 맛집 서버")
logging.getLogger("httpx").setLevel(logging.WARNING)

GAEKSA_COORDINATES = {"longitude": 127.1467, "latitude": 35.8187}
CACHE_ROOT = Path("data/cache/tourapi")
DEFAULT_CACHE_TTL = timedelta(hours=24)
CONTENT_TYPE_RESTAURANT = "39"

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
    "일식": ["일식", "초밥", "스시", "돈까스", "돈카츠", "우동", "라멘", "나베"],
    "중식": ["중식", "반점", "짜장", "짬뽕", "탕수육", "마라"],
    "분식": ["분식", "떡볶이", "김밥", "튀김", "라볶이"],
    "카페": ["카페", "커피", "라떼", "디저트", "차", "찻집"],
    "고기": ["고기", "갈비", "삼겹", "구이", "장어", "불고기"],
    "양식": ["파스타", "피자", "스테이크", "브런치", "리조또", "양식"],
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


def _distance_m(longitude: float | None, latitude: float | None) -> int | None:
    if longitude is None or latitude is None:
        return None

    lon1 = math.radians(GAEKSA_COORDINATES["longitude"])
    lat1 = math.radians(GAEKSA_COORDINATES["latitude"])
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
) -> dict[str, Any]:
    common = detail_common or {}
    intro = detail_intro or {}
    raw = {**item, **common, **intro}

    content_id = _first_text(raw.get("contentid"), raw.get("contentId")) or ""
    longitude = _float_or_none(_first_text(raw.get("mapx")))
    latitude = _float_or_none(_first_text(raw.get("mapy")))
    distance = _float_or_none(raw.get("dist"))
    if distance is None:
        distance = _distance_m(longitude, latitude)

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
        "source_note": "TourAPI는 리뷰 수와 평점을 제공하지 않아 해당 항목은 추천 기준에 포함하지 않습니다.",
    }
    return restaurant


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

    distance_m = restaurant.get("distance_m")
    if isinstance(distance_m, int):
        if distance_m <= 500:
            score += 14
            reasons.append("객사 기준 500m 이내")
        elif distance_m <= 1000:
            score += 10
            reasons.append("객사 기준 1km 이내")
        elif distance_m <= 1500:
            score += 7
            reasons.append("객사 기준 1.5km 이내")
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

    desired_cuisine = ranking_policy.get("cuisine")
    if desired_cuisine and restaurant.get("cuisine") == desired_cuisine:
        score += 10
        reasons.append(f"{desired_cuisine} 조건 일치")

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

    weather_hints = ranking_policy.get("weather_hints", []) or []
    matched_hints = [hint for hint in weather_hints if hint and hint in blob]
    if matched_hints:
        score += 5
        reasons.append(f"날씨 힌트 매칭: {', '.join(matched_hints[:3])}")

    if not restaurant.get("address"):
        score -= 5
        reasons.append("주소 누락")
    if restaurant.get("distance_m") is None:
        score -= 4
        reasons.append("좌표/거리 정보 누락")

    return round(score, 2), reasons


@mcp.tool()
def search_tourapi_restaurants(
    area: str = "전주",
    keyword: str | None = None,
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

    settings = _load_settings()
    rows = min(max(int(limit) * 3, 20), 100)
    if near_gaeksa:
        path = "locationBasedList2"
        params = {
            "numOfRows": rows,
            "pageNo": 1,
            "arrange": "A",
            "contentTypeId": CONTENT_TYPE_RESTAURANT,
            "mapX": GAEKSA_COORDINATES["longitude"],
            "mapY": GAEKSA_COORDINATES["latitude"],
            "radius": 1500,
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
    restaurants = [_standardize_restaurant(item) for item in _items_from_payload(payload)]
    if keyword:
        restaurants = [restaurant for restaurant in restaurants if keyword in _text_blob(restaurant)]
    restaurants.sort(
        key=lambda restaurant: (
            restaurant.get("distance_m") is None,
            restaurant.get("distance_m") if restaurant.get("distance_m") is not None else 999999,
            restaurant.get("name") or "",
        )
    )

    return {
        "status": "ok",
        "source": result["source"],
        "cache_key": result["cache_key"],
        "query": {
            "area": area,
            "keyword": keyword,
            "near_gaeksa": near_gaeksa,
            "limit": limit,
            "contentTypeId": CONTENT_TYPE_RESTAURANT,
        },
        "total_count": _body_total_count(payload),
        "count": len(restaurants[: max(1, limit)]),
        "candidates": restaurants[: max(1, limit)],
        "message": "전주 음식점 공공데이터 후보를 조회했습니다.",
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

    for candidate in candidates:
        score, reasons = _score_public_restaurant(candidate, policy)
        ranked = candidate.copy()
        ranked["score"] = score
        ranked["score_reasons"] = reasons
        ranked["recommendation_reason"] = (
            "한국관광공사 TourAPI 등록 정보 기준으로 주소, 거리, 상세정보 충실도, 요청 조건 일치도를 반영했습니다."
        )
        ranked_candidates.append(ranked)

    ranked_candidates.sort(key=lambda item: item["score"], reverse=True)

    return {
        "status": "ok" if ranked_candidates else "error",
        "source": "TourAPI KorService2",
        "ranking_policy": policy,
        "ranked_candidates": ranked_candidates,
        "message": "공공데이터 후보 정렬을 완료했습니다." if ranked_candidates else "정렬할 공공데이터 후보가 없습니다.",
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
