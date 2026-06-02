from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("환경 컨텍스트 서버")


LOCATION_COORDINATES: dict[str, dict[str, float | str]] = {
    "전주 객사": {"latitude": 35.8187, "longitude": 127.1467, "label": "전주 객사"},
    "전주": {"latitude": 35.8242, "longitude": 127.1480, "label": "전주"},
    "서울 홍대": {"latitude": 37.5563, "longitude": 126.9236, "label": "서울 홍대"},
}


USER_PROFILES: dict[str, dict[str, Any]] = {
    "default": {
        "user_id": "default",
        "preferred_cuisines": ["한식", "일식", "양식"],
        "avoid_cuisines": [],
        "preferred_price_level": 2,
        "visit_purposes": ["친구와 저녁", "대화하기 좋은 곳"],
        "notes": ["너무 비싸지 않은 곳", "리뷰가 좋은 곳", "걷기 부담 없는 거리"],
    }
}


PROFILE_MEMORY: dict[str, list[str]] = {
    "default": ["친구와 저녁 식사에는 가격대가 중간 이하이고 리뷰가 많은 곳을 선호합니다."]
}


def _resolve_location(location: str) -> dict[str, float | str]:
    normalized = (location or "").strip()
    for key, value in LOCATION_COORDINATES.items():
        if key in normalized or normalized in key:
            return value
    raise ValueError(f"지원하지 않는 지역입니다: {location}")


def _weather_food_hints(temperature: float, precipitation: float) -> list[str]:
    hints: list[str] = []
    if temperature <= 5:
        hints.extend(["국물", "전골", "따뜻한 한식"])
    elif temperature >= 28:
        hints.extend(["냉면", "샐러드", "가벼운 식사"])
    else:
        hints.extend(["한식", "일식", "양식"])

    if precipitation > 0:
        hints.extend(["실내 좌석", "따뜻한 메뉴", "이동 거리 짧은 곳"])

    return list(dict.fromkeys(hints))


def _mock_weather(location: str, reason: str) -> dict[str, Any]:
    return {
        "source": "mock",
        "location": location,
        "weather": "흐림",
        "temperature_c": 18.0,
        "precipitation_mm": 0.0,
        "food_hints": ["한식", "일식", "대화하기 좋은 실내 좌석"],
        "confidence": 0.55,
        "observed_at": datetime.now().isoformat(timespec="seconds"),
        "fallback_reason": reason,
    }


@mcp.tool()
def get_weather_context(location: str) -> dict[str, Any]:
    """지역 날씨와 음식 추천 힌트를 반환합니다."""
    try:
        coordinates = _resolve_location(location)
    except ValueError as exc:
        return {
            "source": "error",
            "location": location,
            "error": str(exc),
            "confidence": 0.0,
            "food_hints": [],
        }

    params = {
        "latitude": coordinates["latitude"],
        "longitude": coordinates["longitude"],
        "current": "temperature_2m,precipitation,weather_code",
        "timezone": "Asia/Seoul",
    }

    try:
        with httpx.Client(timeout=4.0) as client:
            response = client.get("https://api.open-meteo.com/v1/forecast", params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        return _mock_weather(str(coordinates["label"]), f"Open-Meteo 호출 실패: {exc}")

    current = payload.get("current", {})
    temperature = float(current.get("temperature_2m", 18.0))
    precipitation = float(current.get("precipitation", 0.0))
    weather_code = int(current.get("weather_code", 3))

    if precipitation > 0:
        weather = "비"
    elif weather_code in {0, 1}:
        weather = "맑음"
    elif weather_code in {2, 3}:
        weather = "흐림"
    else:
        weather = "변동성 있음"

    return {
        "source": "Open-Meteo",
        "location": coordinates["label"],
        "weather": weather,
        "temperature_c": temperature,
        "precipitation_mm": precipitation,
        "food_hints": _weather_food_hints(temperature, precipitation),
        "confidence": 0.86,
        "observed_at": current.get("time", datetime.now().isoformat(timespec="seconds")),
    }


@mcp.tool()
def get_user_profile(user_id: str = "default") -> dict[str, Any]:
    """사용자의 과제용 선호 프로필을 반환합니다."""
    profile = USER_PROFILES.get(user_id, USER_PROFILES["default"]).copy()
    profile["memory"] = PROFILE_MEMORY.get(user_id, PROFILE_MEMORY["default"])
    profile["source"] = "local_profile_memory"
    profile["confidence"] = 0.8
    return profile


@mcp.tool()
def remember_preference(user_id: str, preference_note: str) -> dict[str, Any]:
    """사용자 선호 문장을 단기 메모리에 저장합니다."""
    safe_user_id = (user_id or "default").strip() or "default"
    safe_note = (preference_note or "").strip()
    if not safe_note:
        return {
            "user_id": safe_user_id,
            "stored": False,
            "memory": PROFILE_MEMORY.get(safe_user_id, []),
            "message": "저장할 선호 정보가 비어 있습니다.",
        }

    PROFILE_MEMORY.setdefault(safe_user_id, []).append(safe_note)
    return {
        "user_id": safe_user_id,
        "stored": True,
        "memory": PROFILE_MEMORY[safe_user_id],
        "message": "사용자 선호 정보를 단기 메모리에 저장했습니다.",
    }


if __name__ == "__main__":
    mcp.run("stdio")
