from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("맛집 데이터 서버")


RESTAURANTS: list[dict[str, Any]] = [
    {
        "restaurant_id": "jj_gaeksa_001",
        "name": "객사온반",
        "location": "전주 객사",
        "cuisine": "한식",
        "price_level": 2,
        "average_price": "1인 12,000~16,000원",
        "rating": 4.7,
        "review_count": 486,
        "distance_m": 280,
        "purpose_tags": ["친구", "저녁", "대화", "실내"],
        "weather_tags": ["비", "흐림", "추움"],
        "preference_tags": ["가성비", "리뷰좋음", "따뜻한메뉴"],
        "signature_menu": ["전주식 온반", "들깨 수제비", "불고기 정식"],
        "recommendation_reason": "가격대가 부담스럽지 않고 따뜻한 한식 메뉴가 많아 친구와 저녁 식사에 적합합니다.",
    },
    {
        "restaurant_id": "jj_gaeksa_002",
        "name": "객리단길 소반집",
        "location": "전주 객사",
        "cuisine": "한식",
        "price_level": 2,
        "average_price": "1인 13,000~18,000원",
        "rating": 4.6,
        "review_count": 352,
        "distance_m": 430,
        "purpose_tags": ["친구", "저녁", "모임", "대화"],
        "weather_tags": ["맑음", "흐림", "비"],
        "preference_tags": ["리뷰좋음", "깔끔함", "가성비"],
        "signature_menu": ["비빔 정식", "제육 반상", "버섯 전골"],
        "recommendation_reason": "리뷰 수와 평점이 안정적이고 객사에서 걸어가기 좋은 거리의 한식 반상집입니다.",
    },
    {
        "restaurant_id": "jj_gaeksa_003",
        "name": "노을돈카츠 객사점",
        "location": "전주 객사",
        "cuisine": "일식",
        "price_level": 2,
        "average_price": "1인 11,000~15,000원",
        "rating": 4.5,
        "review_count": 298,
        "distance_m": 360,
        "purpose_tags": ["친구", "저녁", "캐주얼"],
        "weather_tags": ["맑음", "흐림"],
        "preference_tags": ["가성비", "리뷰좋음", "든든함"],
        "signature_menu": ["등심 돈카츠", "치즈 돈카츠", "우동 세트"],
        "recommendation_reason": "가격이 비교적 낮고 캐주얼하게 먹기 좋아 친구와 부담 없는 저녁에 어울립니다.",
    },
    {
        "restaurant_id": "jj_gaeksa_004",
        "name": "한옥파스타 객사",
        "location": "전주 객사",
        "cuisine": "양식",
        "price_level": 3,
        "average_price": "1인 18,000~25,000원",
        "rating": 4.8,
        "review_count": 221,
        "distance_m": 520,
        "purpose_tags": ["친구", "저녁", "분위기"],
        "weather_tags": ["맑음", "흐림"],
        "preference_tags": ["리뷰좋음", "분위기", "사진"],
        "signature_menu": ["크림 파스타", "라구 파스타", "버섯 리조또"],
        "recommendation_reason": "평점은 높지만 가격대가 다소 있어 조건이 완화될 때 추천하기 좋은 후보입니다.",
    },
    {
        "restaurant_id": "jj_gaeksa_005",
        "name": "객사분식 연구소",
        "location": "전주 객사",
        "cuisine": "분식",
        "price_level": 1,
        "average_price": "1인 7,000~11,000원",
        "rating": 4.3,
        "review_count": 512,
        "distance_m": 240,
        "purpose_tags": ["친구", "저녁", "간단식", "캐주얼"],
        "weather_tags": ["맑음", "흐림", "비"],
        "preference_tags": ["가성비", "리뷰많음", "빠른식사"],
        "signature_menu": ["즉석 떡볶이", "튀김 세트", "김밥"],
        "recommendation_reason": "리뷰 수가 많고 가격이 낮아 가성비 조건에는 강하지만 조용한 저녁 목적에는 약간 가볍습니다.",
    },
    {
        "restaurant_id": "jj_gaeksa_006",
        "name": "전주나베 골목",
        "location": "전주 객사",
        "cuisine": "일식",
        "price_level": 2,
        "average_price": "1인 14,000~19,000원",
        "rating": 4.6,
        "review_count": 264,
        "distance_m": 610,
        "purpose_tags": ["친구", "저녁", "실내", "대화"],
        "weather_tags": ["비", "추움", "흐림"],
        "preference_tags": ["따뜻한메뉴", "리뷰좋음", "든든함"],
        "signature_menu": ["밀푀유나베", "돈코츠 나베", "우동 사리"],
        "recommendation_reason": "날씨가 흐리거나 비가 올 때 따뜻한 메뉴를 먹기 좋고 가격대도 중간 수준입니다.",
    },
    {
        "restaurant_id": "jj_gaeksa_007",
        "name": "객사구이마당",
        "location": "전주 객사",
        "cuisine": "고기",
        "price_level": 3,
        "average_price": "1인 22,000~32,000원",
        "rating": 4.4,
        "review_count": 188,
        "distance_m": 700,
        "purpose_tags": ["친구", "저녁", "모임"],
        "weather_tags": ["맑음", "흐림"],
        "preference_tags": ["든든함", "모임"],
        "signature_menu": ["양념 갈비", "목살 구이", "된장찌개"],
        "recommendation_reason": "친구 모임에는 좋지만 가격대가 높아 '너무 비싸지 않음' 조건에서는 후순위입니다.",
    },
    {
        "restaurant_id": "jj_gaeksa_008",
        "name": "청년국밥 객사",
        "location": "전주 객사",
        "cuisine": "한식",
        "price_level": 1,
        "average_price": "1인 8,000~10,000원",
        "rating": 4.2,
        "review_count": 642,
        "distance_m": 390,
        "purpose_tags": ["친구", "저녁", "혼밥", "든든함"],
        "weather_tags": ["비", "추움", "흐림"],
        "preference_tags": ["가성비", "리뷰많음", "따뜻한메뉴"],
        "signature_menu": ["순대국밥", "돼지국밥", "수육백반"],
        "recommendation_reason": "가격이 낮고 리뷰가 많아 가성비와 따뜻한 식사 조건에 잘 맞습니다.",
    },
    {
        "restaurant_id": "jj_gaeksa_009",
        "name": "전주샐러드바",
        "location": "전주 객사",
        "cuisine": "양식",
        "price_level": 2,
        "average_price": "1인 12,000~17,000원",
        "rating": 4.1,
        "review_count": 96,
        "distance_m": 330,
        "purpose_tags": ["친구", "점심", "가벼운식사"],
        "weather_tags": ["더움", "맑음"],
        "preference_tags": ["가벼움", "건강식"],
        "signature_menu": ["닭가슴살 샐러드", "연어 포케", "수프 세트"],
        "recommendation_reason": "가볍게 먹기 좋지만 리뷰 수가 조건보다 적어 저녁 추천에서는 후순위입니다.",
    },
    {
        "restaurant_id": "jj_gaeksa_010",
        "name": "객사디저트카페",
        "location": "전주 객사",
        "cuisine": "카페",
        "price_level": 2,
        "average_price": "1인 8,000~14,000원",
        "rating": 4.5,
        "review_count": 402,
        "distance_m": 260,
        "purpose_tags": ["친구", "대화", "후식"],
        "weather_tags": ["맑음", "흐림", "비"],
        "preference_tags": ["리뷰좋음", "분위기"],
        "signature_menu": ["수제 케이크", "아인슈페너", "크림 라떼"],
        "recommendation_reason": "저녁 식사 후 대화하기 좋은 후식 후보이며, 식사 장소로는 보조 추천에 가깝습니다.",
    },
]


def _matches_text(value: str | None, target: str | None) -> bool:
    if not target:
        return True
    if not value:
        return False
    normalized_value = value.strip().lower()
    normalized_target = target.strip().lower()
    return normalized_target in normalized_value or normalized_value in normalized_target


def _restaurant_by_id(restaurant_id: str) -> dict[str, Any] | None:
    for restaurant in RESTAURANTS:
        if restaurant["restaurant_id"] == restaurant_id:
            return restaurant
    return None


def _score_restaurant(restaurant: dict[str, Any], ranking_policy: dict[str, Any]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0

    rating = float(restaurant["rating"])
    review_count = int(restaurant["review_count"])
    distance_m = int(restaurant["distance_m"])
    price_level = int(restaurant["price_level"])

    score += rating * 18
    reasons.append(f"평점 {rating:.1f}")

    review_score = min(review_count / 80, 8)
    score += review_score
    reasons.append(f"리뷰 {review_count}개")

    if distance_m <= 300:
        score += 8
        reasons.append("매우 가까움")
    elif distance_m <= 600:
        score += 5
        reasons.append("도보 이동 가능")
    else:
        score += 2
        reasons.append("조금 걸어야 함")

    max_price_level = int(ranking_policy.get("max_price_level", 2) or 2)
    if price_level <= max_price_level:
        score += 10
        reasons.append("가격 조건 적합")
    else:
        score -= 8 * (price_level - max_price_level)
        reasons.append("가격 조건보다 높음")

    purpose = str(ranking_policy.get("purpose", ""))
    if any(tag in purpose for tag in restaurant["purpose_tags"]):
        score += 8
        reasons.append("방문 목적 적합")
    elif "친구" in restaurant["purpose_tags"] and "저녁" in restaurant["purpose_tags"]:
        score += 6
        reasons.append("친구와 저녁에 적합")

    weather_hints = ranking_policy.get("weather_hints", []) or []
    if set(weather_hints) & set(restaurant["weather_tags"] + restaurant["preference_tags"]):
        score += 4
        reasons.append("날씨/선호 힌트 적합")

    preferred_cuisines = ranking_policy.get("preferred_cuisines", []) or []
    if restaurant["cuisine"] in preferred_cuisines:
        score += 3
        reasons.append("사용자 선호 음식")

    return round(score, 2), reasons


@mcp.tool()
def search_restaurants(
    location: str,
    cuisine: str | None = None,
    max_price_level: int = 4,
    min_rating: float = 0.0,
    min_review_count: int = 0,
    max_distance_m: int = 2000,
    purpose: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """조건에 맞는 맛집 후보를 검색합니다."""
    if not location or not location.strip():
        return {"status": "error", "message": "지역 조건이 비어 있습니다.", "candidates": []}

    normalized_location = location.strip()
    location_candidates = [
        restaurant
        for restaurant in RESTAURANTS
        if _matches_text(restaurant["location"], normalized_location)
    ]

    if not location_candidates:
        return {
            "status": "error",
            "message": f"지원하지 않는 지역입니다: {location}",
            "supported_locations": sorted({restaurant["location"] for restaurant in RESTAURANTS}),
            "candidates": [],
        }

    candidates: list[dict[str, Any]] = []
    for restaurant in location_candidates:
        if cuisine and not _matches_text(restaurant["cuisine"], cuisine):
            continue
        if int(restaurant["price_level"]) > max_price_level:
            continue
        if float(restaurant["rating"]) < min_rating:
            continue
        if int(restaurant["review_count"]) < min_review_count:
            continue
        if int(restaurant["distance_m"]) > max_distance_m:
            continue
        if purpose and "친구" in purpose and "친구" not in restaurant["purpose_tags"]:
            continue
        candidates.append(restaurant)

    return {
        "status": "ok",
        "query": {
            "location": location,
            "cuisine": cuisine,
            "max_price_level": max_price_level,
            "min_rating": min_rating,
            "min_review_count": min_review_count,
            "max_distance_m": max_distance_m,
            "purpose": purpose,
            "limit": limit,
        },
        "count": len(candidates),
        "candidates": candidates[: max(1, limit)],
    }


@mcp.tool()
def get_restaurant_detail(restaurant_id: str) -> dict[str, Any]:
    """restaurant_id에 해당하는 맛집 상세 정보를 반환합니다."""
    restaurant = _restaurant_by_id(restaurant_id)
    if restaurant is None:
        return {
            "status": "error",
            "message": f"존재하지 않는 restaurant_id입니다: {restaurant_id}",
            "restaurant": None,
        }
    return {"status": "ok", "restaurant": restaurant}


@mcp.tool()
def rank_restaurants(candidate_ids: list[str], ranking_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """후보 맛집을 과제 조건에 맞게 점수화하고 정렬합니다."""
    policy = ranking_policy or {}
    candidates: list[dict[str, Any]] = []
    missing_ids: list[str] = []

    for restaurant_id in candidate_ids:
        restaurant = _restaurant_by_id(restaurant_id)
        if restaurant is None:
            missing_ids.append(restaurant_id)
            continue
        score, score_reasons = _score_restaurant(restaurant, policy)
        ranked = restaurant.copy()
        ranked["score"] = score
        ranked["score_reasons"] = score_reasons
        candidates.append(ranked)

    candidates.sort(key=lambda item: item["score"], reverse=True)

    return {
        "status": "ok" if candidates else "error",
        "ranking_policy": policy,
        "missing_ids": missing_ids,
        "ranked_candidates": candidates,
        "message": "후보 정렬을 완료했습니다." if candidates else "정렬할 후보가 없습니다.",
    }


if __name__ == "__main__":
    mcp.run("stdio")
