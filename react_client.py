from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from contextlib import AsyncExitStack
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, Field

from jeonju_gazetteer import jeonju_alias_terms, jeonju_detail_area_aliases


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


DEFAULT_QUERY = "전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집을 찾아줘. 너무 비싸지 않고, 리뷰가 좋은 곳 위주로 3곳 추천해줘."
DEFAULT_LOCATION = "전주 객사"
JEONJU_DETAIL_AREA_ALIASES: dict[str, list[str]] = jeonju_detail_area_aliases()

FOOD_QUERY_TERMS = [
    "한정식",
    "콩나물국밥",
    "비빔밥",
    "국밥",
    "백반",
    "찌개",
    "칼국수",
    "한식",
    "초밥",
    "스시",
    "돈카츠",
    "돈까스",
    "라멘",
    "우동",
    "소바",
    "이자카야",
    "일식",
    "마라탕",
    "훠궈",
    "짬뽕",
    "짜장",
    "중식",
    "파스타",
    "피자",
    "스테이크",
    "브런치",
    "리조또",
    "양식",
    "쌀국수",
    "베트남",
    "태국",
    "커리",
    "카레",
    "아시아",
    "떡볶이",
    "김밥",
    "분식",
    "카페",
    "디저트",
    "베이커리",
    "빵",
    "케이크",
    "고기",
    "삼겹살",
    "갈비",
    "곱창",
    "막창",
    "족발",
    "보쌈",
    "치킨",
    "회",
    "해산물",
    "술집",
    "막걸리",
    "전집",
    "파전",
    "포차",
    "호프",
    "펍",
    "맥주",
    "소주",
    "와인",
    "와인바",
    "칵테일",
]

RESTAURANT_CONTEXT_TERMS = [
    "맛집",
    "음식점",
    "식당",
    "먹",
    "밥",
    "메뉴",
    "카페",
    "디저트",
    "전주",
    "객사",
    "한옥마을",
    "웨리단길",
    "전북대",
    "신시가지",
]
AMBIGUOUS_FOOD_TERMS = ["아무거나", "뭐 먹지", "뭐먹지", "맛있는 거", "맛있는거", "음식", "밥", "메뉴"]
NON_CUISINE_TERMS = {
    "점심",
    "저녁",
    "아침",
    "브런치",
    "혼밥",
    "회식",
    "데이트",
    "가족",
    "친구",
    "식사",
    "야식",
    "간식",
}
UNSUPPORTED_REGION_TERMS = [
    "홍대",
    "서울",
    "부산",
    "대구",
    "광주",
    "대전",
    "인천",
    "제주",
    "강릉",
    "수원",
    "성남",
    "청주",
    "천안",
]
UNRELATED_HINT_TERMS = ["파이썬", "코드", "주식", "번역", "수학", "게임", "과제", "보고서", "날씨만", "정치"]
BLOCKED_SAFETY_TERMS = ["성적인", "음란", "성매매", "19금", "자해", "마약", "불법", "해킹", "칼부림"]
CONTEXTUAL_SAFETY_TERMS = ["폭력", "폭행", "살인"]
SAFETY_TERMS = BLOCKED_SAFETY_TERMS + CONTEXTUAL_SAFETY_TERMS
WEATHER_CONDITION_KEYWORDS = {
    "비": ["비오는", "비오는날", "비오는날씨", "비올때", "비올 때", "비가오는", "비가 오는", "비 오는", "우천", "장마", "빗날"],
    "눈": ["눈오는", "눈오는날", "눈올때", "눈 올 때", "눈 오는", "폭설"],
    "추움": ["추운", "춥", "한파", "쌀쌀", "추울", "찬바람"],
    "더움": ["더운", "덥", "폭염", "무더운", "더울", "여름"],
    "맑음": ["맑은", "화창", "날씨 좋은"],
}
REQUESTED_WEATHER_HINTS = {
    "비": ["파전", "해물파전", "막걸리", "전집", "술집", "실내 좌석", "따뜻한 메뉴", "따뜻한메뉴", "국물", "찌개", "전골", "칼국수", "한식", "이동 거리 짧은 곳"],
    "눈": ["국밥", "탕", "찌개", "전골", "칼국수", "라멘", "우동", "실내 좌석", "따뜻한 메뉴", "따뜻한메뉴", "이동 거리 짧은 곳"],
    "추움": ["국밥", "탕", "찌개", "전골", "칼국수", "라멘", "우동", "따뜻한 메뉴", "따뜻한메뉴", "국물", "한식", "실내 좌석"],
    "더움": ["냉면", "콩국수", "막국수", "초계국수", "물회", "빙수", "샐러드", "가벼운 식사", "카페", "실내 좌석"],
    "맑음": ["도보 이동", "분위기", "일식", "양식", "카페"],
}
WEATHER_EXPECTATION_NOTES = {
    "비": "보편적인 기대: 비 오는 날은 파전, 막걸리, 따뜻한 국물, 이동 부담이 낮은 실내 좌석 선호를 추천 힌트로 적용했습니다.",
    "눈": "보편적인 기대: 눈 오는 날은 따뜻한 국물, 전골, 국밥, 가까운 실내 좌석 선호를 추천 힌트로 적용했습니다.",
    "추움": "보편적인 기대: 추운 날은 국밥, 탕, 찌개, 전골, 라멘처럼 따뜻한 메뉴 선호를 추천 힌트로 적용했습니다.",
    "더움": "보편적인 기대: 더운 날은 냉면, 콩국수, 물회, 빙수처럼 시원하거나 가벼운 메뉴 선호를 추천 힌트로 적용했습니다.",
    "맑음": "보편적인 기대: 날씨가 좋은 날은 도보 이동, 분위기, 카페나 브런치 선호를 추천 힌트로 적용했습니다.",
}
BAR_INTENT_TERMS = ["술집", "주점", "혼술", "한잔", "술자리", "포차", "호프", "펍", "맥주", "소주", "와인바", "칵테일", "이자카야"]
BAR_CANDIDATE_MATCH_TERMS = ["술집", "혼술", "한잔", "술자리", "포차", "호프", "펍", "맥주", "소주", "와인바", "칵테일", "이자카야", "막걸리", "전집", "파전", "해물파전"]
ALCOHOL_INTENT_TERMS = [*BAR_INTENT_TERMS, "막걸리", "전집", "파전"]
STRICT_PUBLIC_CUISINE_TERMS = set(ALCOHOL_INTENT_TERMS)


class ParsedRequest(BaseModel):
    location: str = DEFAULT_LOCATION
    cuisine: str | None = None
    requested_weather: str | None = None
    purpose: str = "일반 식사"
    max_price_level: int = 2
    min_rating: float = 4.2
    min_review_count: int = 100
    max_distance_m: int = 1000
    limit: int = 3
    extracted_conditions: list[str] = Field(default_factory=list)
    fallback_location: str | None = None
    fallback_reason: str | None = None
    fallback_applied: bool = False
    missing_conditions: list[str] = Field(default_factory=list)
    input_warnings: list[str] = Field(default_factory=list)
    handled_exceptions: list[dict[str, Any]] = Field(default_factory=list)
    routing_decision: str = "continue"


class ToolAction(BaseModel):
    agent_name: str
    pattern: str
    tool_name: str
    tool_input: dict[str, Any]
    mcp_server: str
    thought_summary: str


class Observation(BaseModel):
    status: str
    source: str
    data: dict[str, Any]
    summary: str


class TraceEvent(BaseModel):
    timestamp: str
    step: int
    agent_name: str
    pattern: str
    thought_summary: str | None = None
    action_name: str | None = None
    action_input: dict[str, Any] | None = None
    mcp_server: str | None = None
    jsonrpc_method: str | None = None
    observation: dict[str, Any] | str | None = None
    reflection: str | None = None
    messages_count: int | None = None
    final_answer: str | None = None


class TraceLogger:
    def __init__(self, trace_path: Path | None) -> None:
        self.trace_path = trace_path
        self.step = 0
        if self.trace_path is not None:
            self.trace_path.parent.mkdir(parents=True, exist_ok=True)
            self.trace_path.write_text("", encoding="utf-8")

    def write(
        self,
        *,
        agent_name: str,
        pattern: str,
        thought_summary: str | None = None,
        action_name: str | None = None,
        action_input: dict[str, Any] | None = None,
        mcp_server: str | None = None,
        jsonrpc_method: str | None = None,
        observation: dict[str, Any] | str | None = None,
        reflection: str | None = None,
        messages_count: int | None = None,
        final_answer: str | None = None,
    ) -> None:
        self.step += 1
        event = TraceEvent(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            step=self.step,
            agent_name=agent_name,
            pattern=pattern,
            thought_summary=thought_summary,
            action_name=action_name,
            action_input=action_input,
            mcp_server=mcp_server,
            jsonrpc_method=jsonrpc_method,
            observation=observation,
            reflection=reflection,
            messages_count=messages_count,
            final_answer=final_answer,
        )
        line = event.model_dump_json(exclude_none=True)
        if self.trace_path is not None:
            with self.trace_path.open("a", encoding="utf-8") as file:
                file.write(line + "\n")


class MCPToolClient:
    def __init__(self, session: ClientSession, server_name: str, trace: TraceLogger) -> None:
        self.session = session
        self.server_name = server_name
        self.trace = trace

    async def list_tools(self) -> list[str]:
        result = await self.session.list_tools()
        names = [tool.name for tool in result.tools]
        self.trace.write(
            agent_name="Coordinator Agent",
            pattern="Tool Use Pattern",
            thought_summary=f"{self.server_name}에서 사용 가능한 도구 목록을 확인합니다.",
            action_name="tools/list",
            action_input={},
            mcp_server=self.server_name,
            jsonrpc_method="tools/list",
            observation={"tools": names},
        )
        return names

    async def call_tool(self, action: ToolAction) -> Observation:
        self.trace.write(
            agent_name=action.agent_name,
            pattern=action.pattern,
            thought_summary=action.thought_summary,
            action_name=action.tool_name,
            action_input=action.tool_input,
            mcp_server=action.mcp_server,
            jsonrpc_method="tools/call",
        )
        try:
            result = await self.session.call_tool(action.tool_name, action.tool_input)
            payload = _parse_tool_payload(result)
            summary = _summarize_payload(action.tool_name, payload)
            observation = Observation(
                status=str(payload.get("status", "ok")),
                source=action.tool_name,
                data=payload,
                summary=summary,
            )
        except Exception as exc:
            observation = Observation(
                status="error",
                source=action.tool_name,
                data={"error": str(exc), "tool_input": action.tool_input},
                summary=f"도구 호출 실패: {exc}",
            )

        self.trace.write(
            agent_name=action.agent_name,
            pattern=action.pattern,
            thought_summary="도구 실행 결과를 Observation으로 기록합니다.",
            action_name=f"Observation:{action.tool_name}",
            mcp_server=action.mcp_server,
            jsonrpc_method="tools/call/result",
            observation=observation.model_dump(),
        )
        return observation


def _parse_tool_payload(result: Any) -> dict[str, Any]:
    if getattr(result, "structured_content", None):
        return dict(result.structured_content)
    if not result.content:
        return {"status": "error", "message": "도구 결과가 비어 있습니다."}
    first_content = result.content[0]
    text = getattr(first_content, "text", "")
    if not text:
        return {"status": "error", "message": "도구 결과 텍스트가 비어 있습니다."}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"status": "ok", "text": text}


def _summarize_payload(tool_name: str, payload: dict[str, Any]) -> str:
    if tool_name == "search_restaurants":
        return f"검색 후보 {payload.get('count', 0)}개를 수신했습니다."
    if tool_name == "rank_restaurants":
        return f"정렬 후보 {len(payload.get('ranked_candidates', []))}개를 수신했습니다."
    if tool_name == "get_weather_context":
        return f"{payload.get('location', '지역')} 날씨는 {payload.get('weather', '알 수 없음')}입니다."
    if tool_name == "get_user_profile":
        return "사용자 선호 프로필을 수신했습니다."
    if tool_name == "get_restaurant_detail":
        restaurant = payload.get("restaurant") or {}
        return f"{restaurant.get('name', '맛집')} 상세 정보를 수신했습니다."
    if tool_name == "search_tourapi_restaurants":
        return f"TourAPI 공공데이터 후보 {payload.get('count', 0)}개를 수신했습니다."
    if tool_name == "rank_tourapi_restaurants":
        return f"TourAPI 공공데이터 정렬 후보 {len(payload.get('ranked_candidates', []))}개를 수신했습니다."
    if tool_name == "get_tourapi_restaurant_detail":
        restaurant = payload.get("restaurant") or {}
        return f"{restaurant.get('name', '공공데이터 음식점')} TourAPI 상세 정보를 수신했습니다."
    return f"{tool_name} 결과를 수신했습니다."


def _is_error_payload(payload: dict[str, Any]) -> bool:
    return str(payload.get("status", "")).lower() == "error" or payload.get("source") == "error"


def should_use_llm(requested: bool) -> bool:
    return requested and bool(os.getenv("OPENAI_API_KEY"))


def llm_model_name() -> str:
    return os.getenv("OPENAI_MODEL") or "gpt-4o-mini"


def parse_llm_json(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"raw_plan": content}


def _contains_any(query: str, terms: list[str]) -> bool:
    return any(term in query for term in terms)


def _contains_bar_intent(query: str) -> bool:
    for term in BAR_INTENT_TERMS:
        if term == "주점":
            if re.search(r"(?<!전)주점", query):
                return True
            continue
        if term in query:
            return True
    return False


def _all_jeonju_alias_terms() -> list[str]:
    return jeonju_alias_terms()


def _non_cuisine_terms() -> set[str]:
    return {
        "전주",
        "근처",
        "주변",
        "좋은",
        "괜찮은",
        "맛집",
        "음식점",
        "식당",
        "날씨",
    } | NON_CUISINE_TERMS | set(_all_jeonju_alias_terms())


def detect_cuisine(query: str) -> str | None:
    if _contains_bar_intent(query):
        return "술집"
    for term in FOOD_QUERY_TERMS:
        if term in query:
            return term
    match = re.search(r"([가-힣A-Za-z]+)\s*(?:맛집|음식점|식당|전문점)", query)
    if match:
        candidate = match.group(1).strip()
        if candidate and candidate not in _non_cuisine_terms():
            return candidate
    return None


def detect_requested_weather(query: str) -> str | None:
    compact = re.sub(r"\s+", "", query)
    for weather, keywords in WEATHER_CONDITION_KEYWORDS.items():
        if any(keyword in query or keyword.replace(" ", "") in compact for keyword in keywords):
            return weather
    return None


def infer_max_distance_m(query: str, location: str, requested_weather: str | None) -> int:
    explicit = re.search(r"(\d{2,4})\s*m", query.lower())
    if explicit:
        return max(300, min(int(explicit.group(1)), 3000))

    compact_location_terms = [
        "객사",
        "객리단길",
        "웨리단길",
        "한옥마을",
        "전북대 구정문",
        "구정문",
        "전북대",
        "신시가지",
        "에코시티",
    ]
    wants_nearby = _contains_any(query, ["근처", "주변", "가까운", "인근", "도보", "걸어서", "걷기"])
    compact_area = _contains_any(location, compact_location_terms) or _contains_any(query, compact_location_terms)
    bad_weather = requested_weather in {"비", "눈"}

    if bad_weather and (wants_nearby or compact_area):
        return 700
    if wants_nearby and compact_area:
        return 800
    if compact_area:
        return 900
    if wants_nearby:
        return 1000
    return 1200


def detect_unsupported_location(query: str) -> str | None:
    if "전주" in query:
        return None
    for region in sorted(UNSUPPORTED_REGION_TERMS, key=len, reverse=True):
        if region in query:
            return "서울 홍대" if region == "홍대" else region
    return None


def _has_restaurant_context(query: str, cuisine: str | None) -> bool:
    if cuisine:
        return True
    if _contains_any(query, RESTAURANT_CONTEXT_TERMS + FOOD_QUERY_TERMS + _all_jeonju_alias_terms()):
        return True
    if _contains_any(query, UNRELATED_HINT_TERMS):
        return False
    stripped = query.strip()
    return len(stripped) <= 12 and _contains_any(stripped, ["추천", "알려줘", "찾아줘"])


def evaluate_input_guard(query: str, parsed: ParsedRequest) -> dict[str, Any]:
    restaurant_related = _has_restaurant_context(query, parsed.cuisine)
    issues: list[dict[str, Any]] = []
    alternatives = [
        "전주 객사 한식 맛집 추천",
        "전주 송천동에서 저렴한 점심 맛집 추천",
        "전주 전북대 구정문 근처 소바 맛집 3곳 추천",
    ]

    matched_blocked_terms = [term for term in BLOCKED_SAFETY_TERMS if term in query]
    matched_contextual_terms = [term for term in CONTEXTUAL_SAFETY_TERMS if term in query]
    matched_safety_terms = matched_blocked_terms + matched_contextual_terms
    strict_harmful_action = _contains_any(query, ["방법", "하는 법", "구매", "판매", "공격", "제조", "죽이는", "때리는"])
    harmful_intent = bool(matched_blocked_terms) or (
        bool(matched_contextual_terms) and (strict_harmful_action or not restaurant_related)
    )
    if harmful_intent:
        issues.append(
            {
                "type": "safety_blocked",
                "severity": "error",
                "message": "선정적이거나 폭력적이거나 불법적인 요청은 맛집 추천 Agent가 처리하지 않습니다.",
                "matched_terms": matched_safety_terms,
                "recovery": "전주 지역, 음식 종류, 가격대, 방문 목적을 포함한 맛집 추천 요청으로 다시 입력하세요.",
            }
        )
        return {
            "status": "blocked",
            "routing_decision": "refuse_and_redirect",
            "restaurant_related": restaurant_related,
            "issues": issues,
            "alternatives": alternatives,
        }

    if matched_safety_terms:
        issues.append(
            {
                "type": "unsafe_expression_sanitized",
                "severity": "warning",
                "message": "부적절하거나 폭력적으로 읽힐 수 있는 표현은 추천 조건에서 제외하고 맛집 맥락만 사용합니다.",
                "matched_terms": matched_safety_terms,
                "recovery": "지역, 음식 종류, 가격대, 거리 같은 안전한 맛집 조건만 반영합니다.",
            }
        )

    unrelated = not restaurant_related and _contains_any(query, UNRELATED_HINT_TERMS)
    if not restaurant_related or unrelated:
        issues.append(
            {
                "type": "unrelated_request",
                "severity": "error",
                "message": "입력 내용이 맛집 찾기 목적과 직접 관련되지 않습니다.",
                "recovery": "전주 지역의 세부 위치, 음식 종류, 가격대, 방문 목적 중 하나 이상을 포함해 다시 요청하세요.",
            }
        )
        return {
            "status": "blocked",
            "routing_decision": "refuse_and_redirect",
            "restaurant_related": restaurant_related,
            "issues": issues,
            "alternatives": alternatives,
        }

    if parsed.missing_conditions:
        issues.append(
            {
                "type": "insufficient_conditions",
                "severity": "warning",
                "message": f"사용자 조건이 부족합니다: {', '.join(parsed.missing_conditions)}.",
                "recovery": "누락 조건은 과제 기본값으로 보완하고, 최종 답변에 어떤 기본값을 사용했는지 표시합니다.",
                "assumptions": {
                    "location": parsed.location,
                    "purpose": parsed.purpose,
                    "max_price_level": parsed.max_price_level,
                    "min_rating": parsed.min_rating,
                    "min_review_count": parsed.min_review_count,
                },
            }
        )

    if parsed.cuisine is None and _contains_any(query, AMBIGUOUS_FOOD_TERMS):
        issues.append(
            {
                "type": "ambiguous_food_type",
                "severity": "warning",
                "message": "음식 종류가 모호해 특정 메뉴로 제한하지 않습니다.",
                "recovery": "전체 음식점 후보를 먼저 검색하고, 결과가 부족하면 사용자 선호와 거리 기준으로 정렬합니다.",
            }
        )

    if parsed.fallback_reason and parsed.fallback_location:
        issues.append(
            {
                "type": "unsupported_or_unresolved_location",
                "severity": "warning",
                "message": parsed.fallback_reason,
                "recovery": f"도구가 error Observation을 반환하면 {parsed.fallback_location} 기준으로 재검색합니다.",
            }
        )

    status = "warning" if issues else "ok"
    return {
        "status": status,
        "routing_decision": "continue_with_assumptions" if issues else "continue",
        "restaurant_related": restaurant_related,
        "issues": issues,
        "alternatives": alternatives if issues else [],
    }


def build_guardrail_answer(query: str, guard: dict[str, Any]) -> str:
    issue_lines = []
    for issue in guard.get("issues", []):
        issue_lines.append(f"- {issue.get('message')} 대안: {issue.get('recovery')}")
    alternatives = "\n".join(f"- {item}" for item in guard.get("alternatives", []))
    return (
        "요청을 맛집 추천 작업으로 처리하기 어렵습니다.\n\n"
        f"요청: {query}\n"
        "Observation: 입력 검증 단계에서 error가 감지되었습니다.\n"
        + "\n".join(issue_lines)
        + "\n\n다시 입력할 수 있는 예시:\n"
        + alternatives
        + "\n\nReflection: Agent는 무관하거나 안전하지 않은 요청에는 도구를 호출하지 않고, 과제 범위인 전주 맛집 추천 요청으로 다시 작성할 수 있는 대안을 제시했습니다."
    )


def _clean_detected_location_suffix(text: str, cuisine: str | None) -> str:
    cleaned = text
    if cuisine:
        cleaned = cleaned.replace(cuisine, " ")
    for term in FOOD_QUERY_TERMS:
        cleaned = cleaned.replace(term, " ")
    cleaned = re.sub(
        r"(맛집|음식점|식당|추천|근처|주변|가까운|에서|으로|쪽|부근|찾아줘|알려줘|좋은|괜찮은|친구|저녁|점심|아침|혼밥|회식|데이트)",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,./")
    if cleaned in {"점", "본점", "분점", "지점"} or len(cleaned) <= 1:
        return ""
    return cleaned


def detect_jeonju_location(query: str, cuisine: str | None = None) -> str | None:
    matched: tuple[int, str] | None = None
    for area_name, aliases in JEONJU_DETAIL_AREA_ALIASES.items():
        for alias in aliases:
            if alias in query and (matched is None or len(alias) > matched[0]):
                matched = (len(alias), area_name)
    if matched is not None:
        return f"전주 {matched[1]}"

    if "전주" in query:
        after_jeonju = re.split(r"전주시?|전주", query, maxsplit=1)[-1]
        suffix = _clean_detected_location_suffix(after_jeonju, cuisine)
        if suffix:
            return f"전주 {suffix}"
        return "전주"
    return None


def parse_user_request(query: str) -> ParsedRequest:
    conditions: list[str] = []
    missing_conditions: list[str] = []
    input_warnings: list[str] = []
    fallback_location: str | None = None
    fallback_reason: str | None = None
    cuisine = detect_cuisine(query)
    requested_weather = detect_requested_weather(query)
    detected_location = detect_jeonju_location(query, cuisine)
    unsupported_location = detect_unsupported_location(query)

    if unsupported_location:
        location = unsupported_location
        fallback_location = DEFAULT_LOCATION
        fallback_reason = "현재 과제 검색 범위는 전주로 한정되어 있어, 도구 검색 실패 시 전주 객사로 대체합니다."
    elif "존재하지 않는" in query or "없는 지역" in query or "미지원" in query:
        location = "존재하지 않는 지역"
        fallback_location = DEFAULT_LOCATION
        fallback_reason = "요청 지역을 지원하지 않아 과제 기본 지역인 전주 객사로 대체합니다."
    elif detected_location:
        location = detected_location
        if location != DEFAULT_LOCATION:
            fallback_location = DEFAULT_LOCATION
            fallback_reason = None
    else:
        location = DEFAULT_LOCATION
        fallback_reason = "요청에 명확한 지원 지역이 없어 과제 기본 지역인 전주 객사를 사용합니다."
        missing_conditions.append("지역")
    conditions.append(f"지역={location}")
    if fallback_reason and not (location.startswith("전주") and fallback_location == DEFAULT_LOCATION):
        conditions.append(f"지역보정={fallback_reason}")

    if cuisine:
        conditions.append(f"음식종류={cuisine}")
    elif _contains_any(query, AMBIGUOUS_FOOD_TERMS):
        input_warnings.append("음식 종류가 모호해 전체 음식점 후보로 검색합니다.")
    elif not _contains_any(query, FOOD_QUERY_TERMS):
        missing_conditions.append("음식 종류")

    if requested_weather:
        conditions.append(f"날씨조건={requested_weather}")

    purpose_parts: list[str] = []
    if "친구" in query:
        purpose_parts.append("친구")
    if "저녁" in query:
        purpose_parts.append("저녁")
    if "점심" in query:
        purpose_parts.append("점심")
    if "가족" in query:
        purpose_parts.append("가족")
    if "데이트" in query:
        purpose_parts.append("데이트")
    if "혼밥" in query:
        purpose_parts.append("혼밥")
    if "혼술" in query:
        purpose_parts.append("혼술")
    elif _contains_any(query, ["술자리", "한잔"]):
        purpose_parts.append("술자리")
    purpose = "와 ".join(purpose_parts) if purpose_parts else "일반 식사"
    if not purpose_parts:
        missing_conditions.append("방문 목적")
    conditions.append(f"목적={purpose}")

    max_price_level = 2
    explicit_price = _contains_any(query, ["아주 저렴", "저렴", "비싸", "가성비", "부담", "가격", "비싼"])
    if "아주 저렴" in query or "저렴" in query:
        max_price_level = 1
    elif "비싸" in query or "가성비" in query or "부담" in query:
        max_price_level = 2
    if not explicit_price:
        missing_conditions.append("가격대")
    conditions.append(f"최대가격대={max_price_level}")

    min_rating = 4.2 if "리뷰" in query or "평점" in query or "좋은" in query else 4.0
    min_review_count = 100 if "리뷰" in query else 50
    if "10000" in query:
        min_review_count = 10000
    conditions.append(f"최소평점={min_rating}")
    conditions.append(f"최소리뷰수={min_review_count}")
    max_distance_m = infer_max_distance_m(query, location, requested_weather)
    conditions.append(f"최대거리={max_distance_m}m")

    return ParsedRequest(
        location=location,
        cuisine=cuisine,
        requested_weather=requested_weather,
        purpose=purpose,
        max_price_level=max_price_level,
        min_rating=min_rating,
        min_review_count=min_review_count,
        max_distance_m=max_distance_m,
        limit=3,
        extracted_conditions=conditions,
        fallback_location=fallback_location,
        fallback_reason=fallback_reason,
        missing_conditions=missing_conditions,
        input_warnings=input_warnings,
    )


def build_search_input(parsed: ParsedRequest) -> dict[str, Any]:
    return {
        "location": parsed.location,
        "cuisine": parsed.cuisine,
        "max_price_level": parsed.max_price_level,
        "min_rating": parsed.min_rating,
        "min_review_count": parsed.min_review_count,
        "max_distance_m": parsed.max_distance_m,
        "purpose": parsed.purpose,
        "limit": 10,
    }


def build_ranking_policy(
    parsed: ParsedRequest,
    weather: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    weather_hints = list(weather.get("food_hints", []) or [])
    if parsed.requested_weather:
        requested_hints = REQUESTED_WEATHER_HINTS.get(parsed.requested_weather, [])
        weather_hints = list(dict.fromkeys([*requested_hints, *weather_hints]))

    return {
        "purpose": parsed.purpose,
        "cuisine": parsed.cuisine,
        "max_price_level": parsed.max_price_level,
        "min_rating": parsed.min_rating,
        "min_review_count": parsed.min_review_count,
        "max_distance_m": parsed.max_distance_m,
        "weather": parsed.requested_weather or weather.get("weather"),
        "actual_weather": weather.get("weather"),
        "requested_weather": parsed.requested_weather,
        "weather_hints": weather_hints,
        "weather_expectation_note": WEATHER_EXPECTATION_NOTES.get(parsed.requested_weather or ""),
        "preferred_cuisines": profile.get("preferred_cuisines", []),
        "preferred_price_level": profile.get("preferred_price_level", parsed.max_price_level),
        "target_location": parsed.location,
        "location_strictness": "strict",
    }


def reflect_recommendations(
    ranked_candidates: list[dict[str, Any]],
    parsed: ParsedRequest,
) -> tuple[list[dict[str, Any]], str]:
    accepted: list[dict[str, Any]] = []
    warnings: list[str] = []

    for candidate in ranked_candidates:
        if int(candidate["price_level"]) > parsed.max_price_level:
            warnings.append(f"{candidate['name']}: 가격대가 높아 제외했습니다.")
            continue
        if int(candidate["review_count"]) < parsed.min_review_count:
            warnings.append(f"{candidate['name']}: 리뷰 수가 부족해 제외했습니다.")
            continue
        if float(candidate["rating"]) < parsed.min_rating:
            warnings.append(f"{candidate['name']}: 평점 조건이 부족해 제외했습니다.")
            continue
        accepted.append(candidate)
        if len(accepted) >= parsed.limit:
            break

    if len(accepted) < parsed.limit:
        for candidate in ranked_candidates:
            if candidate not in accepted:
                accepted.append(candidate)
            if len(accepted) >= parsed.limit:
                break
        if accepted:
            warnings.append("엄격한 조건만으로 3곳이 부족할 경우를 대비해 점수 순 대체 후보를 보완했습니다.")
        else:
            warnings.append("조건을 완화해도 추천 가능한 후보가 없습니다.")

    reflection = f"조건 검토 완료: 가격, 리뷰 수, 평점, 거리, {parsed.purpose} 목적을 확인했습니다."
    if warnings:
        reflection += " " + " ".join(warnings)
    return accepted[: parsed.limit], reflection


def _exception_feedback_lines(parsed: ParsedRequest) -> list[str]:
    lines: list[str] = []
    for issue in parsed.handled_exceptions:
        severity = issue.get("severity", "info")
        if severity == "error":
            continue
        message = issue.get("message")
        recovery = issue.get("recovery")
        if not message:
            continue
        line = f"- {message}"
        if recovery:
            line += f" 처리: {recovery}"
        lines.append(line)
    return lines


def _weather_line(parsed: ParsedRequest, weather: dict[str, Any]) -> str:
    actual = (
        f"{weather.get('location', parsed.location)} 기준 "
        f"{weather.get('weather', '알 수 없음')}, {weather.get('temperature_c', '알 수 없음')}도"
    )
    if parsed.requested_weather:
        note = WEATHER_EXPECTATION_NOTES.get(parsed.requested_weather)
        feedback = "원하지 않으면 음식 종류나 제외 조건을 직접 입력하면 그 조건을 우선합니다."
        if note:
            return f"날씨 반영: 사용자 요청 날씨 조건={parsed.requested_weather}를 우선 반영했습니다. {note} {feedback} 실제 날씨 조회: {actual}"
        return f"날씨 반영: 사용자 요청 날씨 조건={parsed.requested_weather}를 우선 반영했습니다. {feedback} 실제 날씨 조회: {actual}"
    return f"날씨 반영: {actual}"


def build_final_answer(
    query: str,
    parsed: ParsedRequest,
    weather: dict[str, Any],
    profile: dict[str, Any],
    recommendations: list[dict[str, Any]],
    reflection: str,
    data_source_note: str | None = None,
) -> str:
    lines = [
        "최종 추천 결과",
        "",
        f"요청: {query}",
        f"분석 조건: {', '.join(parsed.extracted_conditions)}",
        _weather_line(parsed, weather),
        f"사용자 선호 반영: {', '.join(profile.get('notes', []))}",
    ]
    if data_source_note:
        lines.append(f"데이터 처리: {data_source_note}")
    if parsed.fallback_applied and parsed.fallback_reason:
        lines.append(f"대체 처리: {parsed.fallback_reason} 현재 추천 기준 지역은 {parsed.location}입니다.")
    elif parsed.fallback_reason:
        lines.append(f"요청 보정: {parsed.fallback_reason}")
    feedback_lines = _exception_feedback_lines(parsed)
    if feedback_lines:
        lines.append("예외 처리 피드백:")
        lines.extend(feedback_lines)
    lines.append("")

    if not recommendations:
        lines.append("조건 완화 후에도 추천 가능한 후보가 없습니다.")
        lines.append("")
    elif len(recommendations) < parsed.limit:
        lines.append(f"조건 완화 후에도 추천 가능한 후보는 {len(recommendations)}곳입니다.")
        lines.append("")

    for index, restaurant in enumerate(recommendations, start=1):
        score_reasons = ", ".join(restaurant.get("score_reasons", []))
        lines.extend(
            [
                f"{index}. {restaurant['name']} ({restaurant['cuisine']})",
                f"- 추천 이유: {restaurant['recommendation_reason']}",
                f"- 근거: 평점 {restaurant['rating']}, 리뷰 {restaurant['review_count']}개, 거리 {restaurant['distance_m']}m, 가격대 {restaurant['average_price']}",
                f"- 점수 근거: {score_reasons}",
                f"- 대표 메뉴: {', '.join(restaurant.get('signature_menu', []))}",
                "",
            ]
        )

    lines.append(f"Reflection: {reflection}")
    return "\n".join(lines).strip()


def reflect_public_recommendations(
    ranked_candidates: list[dict[str, Any]],
    parsed: ParsedRequest,
) -> tuple[list[dict[str, Any]], str]:
    accepted: list[dict[str, Any]] = []
    warnings: list[str] = []
    strict_food = bool(parsed.cuisine and parsed.cuisine in STRICT_PUBLIC_CUISINE_TERMS)

    for candidate in ranked_candidates:
        if parsed.cuisine and not _public_candidate_matches_cuisine(candidate, parsed.cuisine):
            warnings.append(f"{candidate.get('name', '후보')}: 요청 음식 종류와 달라 후순위로 두었습니다.")
            continue
        accepted.append(candidate)
        if len(accepted) >= parsed.limit:
            break

    if len(accepted) < parsed.limit and not strict_food:
        for candidate in ranked_candidates:
            if candidate not in accepted:
                accepted.append(candidate)
            if len(accepted) >= parsed.limit:
                break
        if len(accepted) < parsed.limit:
            warnings.append(f"공공데이터 후보가 {len(accepted)}곳만 확보되었습니다.")
        elif warnings:
            warnings.append("음식 종류 조건을 엄격히 적용하면 후보가 부족해 점수 순 대체 후보를 보완했습니다.")
    elif len(accepted) < parsed.limit and strict_food:
        if accepted:
            warnings.append(
                f"{parsed.cuisine} 의도는 엄격히 유지했습니다. TourAPI에서 직접 매칭되는 후보가 {len(accepted)}곳뿐이라 일반 식당으로 채우지 않았습니다."
            )
        else:
            warnings.append(
                f"TourAPI에서 {parsed.cuisine} 의도와 직접 맞는 후보를 찾지 못했습니다. 일반 음식점으로 임의 대체하지 않고 데이터 한계를 표시합니다."
            )

    reflection = (
        "공공데이터 검토 완료: 한국관광공사 TourAPI의 주소, 좌표, 상세정보 충실도, 요청 조건 일치도를 확인했습니다. "
        "TourAPI는 평점, 리뷰 수, 가격대를 제공하지 않아 해당 항목은 추천 기준에서 제외했습니다."
    )
    if warnings:
        reflection += " " + " ".join(warnings)
    return accepted[: parsed.limit], reflection


def _public_candidate_matches_cuisine(candidate: dict[str, Any], cuisine: str) -> bool:
    terms = [cuisine]
    if cuisine == "술집":
        terms.extend(BAR_CANDIDATE_MATCH_TERMS)
    elif cuisine in {"막걸리", "전집", "파전"}:
        terms.extend(["막걸리", "전집", "파전", "해물파전"])
    for term in FOOD_QUERY_TERMS:
        if cuisine in term or term in cuisine:
            terms.append(term)
    blob = " ".join(
        str(value)
        for value in [
            candidate.get("name"),
            candidate.get("cuisine"),
            candidate.get("address"),
            candidate.get("overview"),
            " ".join(candidate.get("signature_menu") or []),
        ]
        if value
    )
    if cuisine == "술집" and re.search(r"(?<!전)주점", blob):
        return True
    return any(term and term in blob for term in terms)


def _public_value(value: Any, fallback: str = "정보 없음") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def build_public_final_answer(
    query: str,
    parsed: ParsedRequest,
    weather: dict[str, Any],
    profile: dict[str, Any],
    recommendations: list[dict[str, Any]],
    reflection: str,
    data_source_label: str | None = None,
) -> str:
    source_names = {str(item.get("source")) for item in recommendations if item.get("source")}
    if data_source_label == "Kakao Local API" or "Kakao Local API" in source_names:
        source_label = "Kakao Local API"
        limitation = "Kakao Local API는 평점, 리뷰 수, 가격대를 제공하지 않아 장소명, 카테고리, 주소, 거리 중심으로 보강 검색했습니다."
        missing_metric_label = "Kakao Local 미제공"
    else:
        source_label = "한국관광공사 TourAPI KorService2"
        limitation = "TourAPI는 평점, 리뷰 수, 가격대를 제공하지 않아 임의 수치를 생성하지 않았습니다."
        missing_metric_label = "TourAPI 미제공"

    lines = [
        "최종 추천 결과",
        "",
        f"요청: {query}",
        f"분석 조건: {', '.join(parsed.extracted_conditions)}",
        f"데이터 출처: {source_label}",
        f"데이터 한계: {limitation}",
        _weather_line(parsed, weather),
        f"사용자 선호 반영: {', '.join(profile.get('notes', []))}",
        "",
    ]

    feedback_lines = _exception_feedback_lines(parsed)
    if feedback_lines:
        lines.insert(-1, "예외 처리 피드백:")
        for feedback in feedback_lines:
            lines.insert(-1, feedback)

    if not recommendations:
        lines.append("공공데이터 후보를 확보하지 못했습니다.")
        lines.append("")

    for index, restaurant in enumerate(recommendations, start=1):
        score_reasons = ", ".join(restaurant.get("score_reasons", [])) or "공공데이터 필드 기준 정렬"
        menus = restaurant.get("signature_menu") or []
        operation = restaurant.get("operation") or {}
        distance = restaurant.get("distance_m")
        distance_reference = restaurant.get("distance_reference") or parsed.location
        distance_text = f"{distance}m" if isinstance(distance, int) else "정보 없음"
        rating_text = _public_value(restaurant.get("rating"), missing_metric_label)
        review_text = _public_value(restaurant.get("review_count"), missing_metric_label)
        price_text = _public_value(restaurant.get("average_price"), missing_metric_label)
        menu_fallback = "Kakao 장소 검색 키워드 정보" if restaurant.get("source") == "Kakao Local API" else "TourAPI 상세 메뉴 정보 없음"
        lines.extend(
            [
                f"{index}. {restaurant['name']} ({restaurant.get('cuisine') or '음식점'})",
                f"- 추천 이유: {restaurant.get('recommendation_reason', 'TourAPI 등록 음식점 정보 기준으로 추천했습니다.')}",
                f"- 주소: {_public_value(restaurant.get('address'))}",
                f"- 거리: {distance_reference} 기준 {distance_text}",
                f"- 평점/리뷰/가격대: 평점 {rating_text}, 리뷰 {review_text}, 가격대 {price_text}",
                f"- 전화: {_public_value(restaurant.get('phone'))}",
                f"- 대표 메뉴: {', '.join(menus) if menus else menu_fallback}",
                f"- 영업 정보: {_public_value(operation.get('open_time'))}, 휴무 {_public_value(operation.get('rest_date'))}",
                f"- 점수 근거: {score_reasons}",
            ]
        )
        if restaurant.get("place_url"):
            lines.append(f"- 장소 링크: {restaurant.get('place_url')}")
        lines.append("")

    lines.append(f"Reflection: {reflection}")
    return "\n".join(lines).strip()


async def call_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 900,
    temperature: float = 0.2,
) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 없어 LLM을 호출할 수 없습니다.")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    response = await client.chat.completions.create(
        model=llm_model_name(),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""


async def run_llm_planner(
    query: str,
    parsed: ParsedRequest,
    trace: TraceLogger,
    messages_count: int,
    use_llm: bool,
) -> dict[str, Any] | None:
    if not should_use_llm(use_llm):
        trace.write(
            agent_name="LLM Planner",
            pattern="Plan-and-Solve Pattern",
            thought_summary="OPENAI_API_KEY가 없거나 LLM이 비활성화되어 규칙 기반 계획을 사용합니다.",
            observation={"llm_enabled": False, "model": None},
            messages_count=messages_count,
        )
        return None

    system_prompt = (
        "너는 맛집 추천 ReAct Agent의 Planner다. 사용자의 요청과 1차 파싱 결과를 보고 "
        "도구 호출 계획과 검토 기준을 한국어 JSON으로 작성한다. 실제 맛집 정보, 평점, 리뷰 수를 만들어내지 않는다."
    )
    user_prompt = json.dumps(
        {
            "user_query": query,
            "parsed_request": parsed.model_dump(),
            "available_mcp_servers": {
                "env_context_server.py": ["get_weather_context", "get_user_profile", "remember_preference"],
                "public_data_server.py": [
                    "search_tourapi_restaurants",
                    "get_tourapi_restaurant_detail",
                    "rank_tourapi_restaurants",
                ],
                "gourmet_db_server.py": ["search_restaurants", "rank_restaurants", "get_restaurant_detail"],
            },
            "instruction": {
                "format": "JSON only",
                "keys": ["interpreted_conditions", "tool_plan", "reflection_checklist", "final_answer_policy"],
                "policy": "TourAPI에는 평점/리뷰 수가 없으므로 해당 수치를 생성하지 말 것",
            },
        },
        ensure_ascii=False,
    )

    try:
        content = await call_llm(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=700, temperature=0.1)
        plan = parse_llm_json(content)
        trace.write(
            agent_name="LLM Planner",
            pattern="Plan-and-Solve Pattern",
            thought_summary="GPT가 사용자 요청을 분석하고 MCP 도구 호출 계획을 작성했습니다.",
            action_name="openai.chat.completions.create",
            action_input={"model": llm_model_name(), "stage": "planner"},
            observation=plan,
            messages_count=messages_count,
        )
        return plan
    except Exception as exc:
        trace.write(
            agent_name="LLM Planner",
            pattern="Plan-and-Solve Pattern",
            thought_summary="LLM 계획 생성이 실패해 규칙 기반 계획으로 대체합니다.",
            action_name="openai.chat.completions.create",
            action_input={"model": llm_model_name(), "stage": "planner"},
            observation={"status": "error", "message": str(exc)},
            messages_count=messages_count,
        )
        return None


async def run_llm_reflection(
    *,
    query: str,
    parsed: ParsedRequest,
    recommendations: list[dict[str, Any]],
    deterministic_reflection: str,
    trace: TraceLogger,
    messages_count: int,
    use_llm: bool,
    data_source: str,
) -> str:
    if not should_use_llm(use_llm):
        return deterministic_reflection

    compact_recommendations = [
        {
            "name": item.get("name"),
            "cuisine": item.get("cuisine"),
            "address": item.get("address"),
            "distance_m": item.get("distance_m"),
            "distance_reference": item.get("distance_reference"),
            "score_reasons": item.get("score_reasons", []),
            "rating": item.get("rating"),
            "review_count": item.get("review_count"),
        }
        for item in recommendations
    ]
    system_prompt = (
        "너는 ReAct Agent의 Reflection Reviewer다. 추천 후보가 사용자 조건에 맞는지 검토하고 "
        "부족한 점과 데이터 한계를 짧은 한국어 문장으로 작성한다. 없는 평점/리뷰 수는 절대 만들지 않는다. "
        "부정적으로 단정하지 말고 '데이터 한계가 있다' 수준으로 표현한다."
    )
    user_prompt = json.dumps(
        {
            "user_query": query,
            "parsed_request": parsed.model_dump(),
            "data_source": data_source,
            "recommendations": compact_recommendations,
            "deterministic_reflection": deterministic_reflection,
            "instruction": "최종 답변에 붙일 Reflection 문장만 작성",
        },
        ensure_ascii=False,
    )

    try:
        reflection = await call_llm(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=300, temperature=0.2)
        reflection = reflection.strip() or deterministic_reflection
        trace.write(
            agent_name="LLM Reflection Reviewer",
            pattern="Reflection Pattern",
            thought_summary="GPT가 Observation과 추천 후보를 검토해 Reflection을 생성했습니다.",
            action_name="openai.chat.completions.create",
            action_input={"model": llm_model_name(), "stage": "reflection", "data_source": data_source},
            reflection=reflection,
            observation={"recommendation_ids": [item.get("restaurant_id") for item in recommendations]},
            messages_count=messages_count,
        )
        return reflection
    except Exception as exc:
        trace.write(
            agent_name="LLM Reflection Reviewer",
            pattern="Reflection Pattern",
            thought_summary="LLM Reflection 생성이 실패해 규칙 기반 Reflection을 사용합니다.",
            action_name="openai.chat.completions.create",
            action_input={"model": llm_model_name(), "stage": "reflection", "data_source": data_source},
            observation={"status": "error", "message": str(exc)},
            reflection=deterministic_reflection,
            messages_count=messages_count,
        )
        return deterministic_reflection


async def run_llm_final_answer(
    *,
    draft_answer: str,
    trace: TraceLogger,
    messages_count: int,
    use_llm: bool,
    data_source: str,
) -> str:
    if not should_use_llm(use_llm):
        return draft_answer

    system_prompt = (
        "너는 맛집 추천 ReAct Agent의 최종 답변 생성기다. 제공된 초안의 식당명, 주소, 거리, 전화번호, "
        "평점/리뷰/가격대, 메뉴, 영업정보, 추천 이유, 점수 근거, Reflection, 데이터 한계를 변경하거나 삭제하지 말고 "
        "한국어로 자연스럽게 정리한다. 각 식당에는 반드시 추천 이유와 점수 근거를 포함한다. "
        "초안에 '평점/리뷰/가격대' 줄이 있으면 각 식당별로 반드시 그대로 보존한다. "
        "초안에 '예외 처리 피드백' 섹션이 있으면 삭제하지 말고 그대로 보존한다. "
        "답변 마지막에는 반드시 'Reflection:'으로 시작하는 검토 문장을 포함한다. "
        "초안에 없는 '유명', '인기', '맛있다', '평이 좋다' 같은 평가 표현을 새로 추가하지 않는다. "
        "추천 이유와 점수 근거는 초안의 의미와 항목을 그대로 유지한다. "
        "TourAPI가 제공하지 않는 평점/리뷰 수/가격대는 절대 만들지 않는다."
    )
    user_prompt = json.dumps(
        {
            "data_source": data_source,
            "draft_answer": draft_answer,
            "instruction": "과제 제출용 최종 답변만 작성",
        },
        ensure_ascii=False,
    )

    try:
        final_answer = await call_llm(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=1500, temperature=0.2)
        final_answer = final_answer.strip() or draft_answer
        draft_required_count = draft_answer.count("- 평점/리뷰/가격대")
        if draft_required_count and final_answer.count("- 평점/리뷰/가격대") < draft_required_count:
            final_answer = draft_answer
        trace.write(
            agent_name="LLM Final Answer Agent",
            pattern="Final Answer",
            thought_summary="GPT가 MCP Observation과 Reflection 기반 초안을 최종 답변으로 구성했습니다.",
            action_name="openai.chat.completions.create",
            action_input={"model": llm_model_name(), "stage": "final_answer", "data_source": data_source},
            final_answer=final_answer,
            messages_count=messages_count,
        )
        return final_answer
    except Exception as exc:
        trace.write(
            agent_name="LLM Final Answer Agent",
            pattern="Final Answer",
            thought_summary="LLM 최종 답변 생성이 실패해 규칙 기반 답변을 사용합니다.",
            action_name="openai.chat.completions.create",
            action_input={"model": llm_model_name(), "stage": "final_answer", "data_source": data_source},
            observation={"status": "error", "message": str(exc)},
            final_answer=draft_answer,
            messages_count=messages_count,
        )
        return draft_answer


async def run_agent(
    query: str,
    trace_path: Path | None,
    use_llm: bool,
    data_source: Literal["local", "public", "auto", "kakao"] = "auto",
) -> str:
    load_dotenv()
    trace = TraceLogger(trace_path)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": "ReAct-aurant 맛집 추천 Agent 실행을 시작합니다."},
        {"role": "user", "content": query},
    ]

    trace.write(
        agent_name="Coordinator Agent",
        pattern="Plan-and-Solve Pattern",
        thought_summary="요구사항을 단계로 분해하고 MCP 서버 연결을 준비합니다.",
        messages_count=len(messages),
    )

    parsed = parse_user_request(query)
    input_guard = evaluate_input_guard(query, parsed)
    if input_guard["issues"]:
        parsed.handled_exceptions = input_guard["issues"]
        parsed.routing_decision = input_guard["routing_decision"]
        trace.write(
            agent_name="Input Guard Agent",
            pattern="Exception Handling Pattern",
            thought_summary="사용자 입력이 맛집 추천 과제 범위와 안전 기준에 맞는지 검증합니다.",
            action_name="validate_user_request",
            action_input={"query": query},
            observation=input_guard,
            messages_count=len(messages),
        )
        if input_guard["status"] == "blocked":
            reflection = "입력이 맛집 추천 범위를 벗어나거나 안전하지 않아 MCP 도구 호출을 중단하고 대체 입력 예시를 제공합니다."
            trace.write(
                agent_name="Input Guard Agent",
                pattern="Reflection Pattern",
                thought_summary="error Observation을 검토해 도구 호출 대신 안전한 대안을 제시하기로 결정합니다.",
                reflection=reflection,
                observation=input_guard,
                messages_count=len(messages),
            )
            answer = build_guardrail_answer(query, input_guard)
            trace.write(
                agent_name="Coordinator Agent",
                pattern="Final Answer",
                thought_summary="입력 검증 Observation과 Reflection을 바탕으로 대안 중심 답변을 생성합니다.",
                messages_count=len(messages),
                final_answer=answer,
            )
            return answer

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"

    async with AsyncExitStack() as stack:
        server_errlog = stack.enter_context(open(os.devnull, "w", encoding="utf-8"))
        env_read, env_write = await stack.enter_async_context(
            stdio_client(
                StdioServerParameters(command=sys.executable, args=["env_context_server.py"], env=env),
                errlog=server_errlog,
            )
        )
        gourmet_read, gourmet_write = await stack.enter_async_context(
            stdio_client(
                StdioServerParameters(command=sys.executable, args=["gourmet_db_server.py"], env=env),
                errlog=server_errlog,
            )
        )
        public_read = public_write = None
        if data_source in {"public", "auto", "kakao"}:
            public_read, public_write = await stack.enter_async_context(
                stdio_client(
                    StdioServerParameters(command=sys.executable, args=["public_data_server.py"], env=env),
                    errlog=server_errlog,
                )
            )

        env_session = await stack.enter_async_context(ClientSession(env_read, env_write))
        gourmet_session = await stack.enter_async_context(ClientSession(gourmet_read, gourmet_write))
        await env_session.initialize()
        await gourmet_session.initialize()
        public_session: ClientSession | None = None
        if public_read is not None and public_write is not None:
            public_session = await stack.enter_async_context(ClientSession(public_read, public_write))
            await public_session.initialize()

        env_client = MCPToolClient(env_session, "env_context_server.py", trace)
        gourmet_client = MCPToolClient(gourmet_session, "gourmet_db_server.py", trace)
        public_client = MCPToolClient(public_session, "public_data_server.py", trace) if public_session else None
        env_tools = await env_client.list_tools()
        gourmet_tools = await gourmet_client.list_tools()
        public_tools: list[str] = []
        if public_client is not None:
            public_tools = await public_client.list_tools()

        trace.write(
            agent_name="Context Specialist Agent",
            pattern="Plan-and-Solve Pattern",
            thought_summary="사용자 요청에서 지역, 목적, 가격, 리뷰 조건을 구조화했습니다.",
            observation=parsed.model_dump(),
            messages_count=len(messages),
        )
        messages.append({"role": "assistant", "content": f"Thought: {parsed.extracted_conditions}"})
        llm_plan = await run_llm_planner(
            query=query,
            parsed=parsed,
            trace=trace,
            messages_count=len(messages),
            use_llm=use_llm,
        )
        if llm_plan is not None:
            messages.append({"role": "assistant", "content": f"LLM Plan: {json.dumps(llm_plan, ensure_ascii=False)}"})

        selected_tools = [
            {
                "server": "env_context_server.py",
                "tools": [tool for tool in ["get_weather_context", "get_user_profile", "remember_preference"] if tool in env_tools],
                "reason": "날씨, 사용자 선호, 단기 메모리를 추천 기준에 반영합니다.",
            }
        ]
        if public_client is not None:
            selected_tools.append(
                {
                    "server": "public_data_server.py",
                    "tools": [
                        tool
                        for tool in [
                            "search_kakao_local_places",
                            "search_tourapi_restaurants",
                            "get_tourapi_restaurant_detail",
                            "rank_tourapi_restaurants",
                        ]
                        if tool in public_tools
                    ],
                    "reason": (
                        "Kakao Local API를 1차 장소 검색 도구로 사용하고 랭킹을 수행합니다."
                        if data_source == "kakao"
                        else "TourAPI 공공데이터 후보를 기본 검색하고, 필요한 경우 Kakao Local API로 보강합니다."
                    ),
                }
            )
        if data_source in {"local", "auto"}:
            selected_tools.append(
                {
                    "server": "gourmet_db_server.py",
                    "tools": [
                        tool
                        for tool in ["search_restaurants", "get_restaurant_detail", "rank_restaurants"]
                        if tool in gourmet_tools
                    ],
                    "reason": "공공데이터 후보가 부족하거나 실패할 때 로컬 샘플 데이터셋 fallback을 수행합니다.",
                }
            )
        trace.write(
            agent_name="Coordinator Agent",
            pattern="Tool Use Pattern",
            thought_summary="사용자 조건, 데이터 소스, MCP 도구 목록을 바탕으로 이번 실행에 필요한 도구를 선택합니다.",
            action_name="select_tools",
            action_input={"data_source": data_source, "location": parsed.location, "cuisine": parsed.cuisine},
            observation={"selected_tools": selected_tools},
            messages_count=len(messages),
        )

        weather_observation = await env_client.call_tool(
            ToolAction(
                agent_name="Context Specialist Agent",
                pattern="Tool Use Pattern",
                tool_name="get_weather_context",
                tool_input={"location": parsed.location},
                mcp_server="env_context_server.py",
                thought_summary="날씨 조건을 추천 기준에 반영하기 위해 환경 도구를 호출합니다.",
            )
        )
        if _is_error_payload(weather_observation.data) and parsed.fallback_location:
            trace.write(
                agent_name="Context Specialist Agent",
                pattern="Reflection Pattern",
                thought_summary="날씨 도구가 지원하지 않는 지역 error를 반환해 기본 과제 지역으로 대체합니다.",
                reflection=parsed.fallback_reason,
                observation=weather_observation.data,
                messages_count=len(messages),
            )
            weather_observation = await env_client.call_tool(
                ToolAction(
                    agent_name="Context Specialist Agent",
                    pattern="Reflection Pattern",
                    tool_name="get_weather_context",
                    tool_input={"location": parsed.fallback_location},
                    mcp_server="env_context_server.py",
                    thought_summary="Fallback Action: 지원 가능한 기본 지역의 날씨를 다시 조회합니다.",
                )
            )
        profile_observation = await env_client.call_tool(
            ToolAction(
                agent_name="Context Specialist Agent",
                pattern="Memory Pattern",
                tool_name="get_user_profile",
                tool_input={"user_id": "default"},
                mcp_server="env_context_server.py",
                thought_summary="사용자 선호도와 가격 민감도를 반영하기 위해 프로필을 조회합니다.",
            )
        )
        await env_client.call_tool(
            ToolAction(
                agent_name="Context Specialist Agent",
                pattern="Memory Pattern",
                tool_name="remember_preference",
                tool_input={"user_id": "default", "preference_note": f"최근 요청: {query}"},
                mcp_server="env_context_server.py",
                thought_summary="이번 요청을 단기 메모리에 저장합니다.",
            )
        )

        public_fallback_reason: str | None = None
        if public_client is not None:
            public_area = parsed.location
            near_gaeksa = "객사" in parsed.location or "객사" in query
            if data_source == "kakao":
                kakao_search_observation = await public_client.call_tool(
                    ToolAction(
                        agent_name="Public Data Agent",
                        pattern="ReAct Pattern",
                        tool_name="search_kakao_local_places",
                        tool_input={
                            "area": public_area,
                            "cuisine": parsed.cuisine,
                            "max_distance_m": parsed.max_distance_m,
                            "near_gaeksa": near_gaeksa,
                            "limit": 8,
                        },
                        mcp_server="public_data_server.py",
                        thought_summary="Thought: 사용자가 Kakao Local API 우선 사용을 활성화했으므로 장소 후보와 위치 기준을 Kakao Local API로 먼저 조회합니다.",
                    )
                )
                messages.append({"role": "tool", "content": f"Observation: {kakao_search_observation.summary}"})
                kakao_payload = kakao_search_observation.data
                recommendations: list[dict[str, Any]] = []
                deterministic_reflection = (
                    "Kakao Local API를 1차 장소 검색 도구로 사용했습니다. "
                    "TourAPI는 평점/리뷰/가격 보강에 한계가 있어 이번 실행에서는 Kakao의 장소명, 카테고리, 주소, 거리 정보를 우선했습니다."
                )
                source_for_answer = "Kakao Local API"

                if kakao_payload.get("status") == "ok" and kakao_payload.get("count", 0) > 0:
                    kakao_rank_observation = await public_client.call_tool(
                        ToolAction(
                            agent_name="Public Data Agent",
                            pattern="ReAct Pattern",
                            tool_name="rank_tourapi_restaurants",
                            tool_input={
                                "candidates": kakao_payload.get("candidates", []),
                                "ranking_policy": build_ranking_policy(parsed, weather_observation.data, profile_observation.data),
                            },
                            mcp_server="public_data_server.py",
                            thought_summary="Thought: Kakao Local 후보를 거리, 카테고리, 요청 조건 일치도로 정렬합니다.",
                        )
                    )
                    messages.append({"role": "tool", "content": f"Observation: {kakao_rank_observation.summary}"})
                    kakao_rank_payload = kakao_rank_observation.data
                    kakao_ranked = kakao_rank_payload.get("ranked_candidates", [])
                    if kakao_ranked:
                        recommendations, deterministic_reflection = reflect_public_recommendations(kakao_ranked, parsed)
                        deterministic_reflection = "Kakao Local API 우선 모드로 장소 후보를 조회했습니다. " + deterministic_reflection
                else:
                    kakao_issue = {
                        "type": "kakao_local_unavailable",
                        "severity": "warning",
                        "message": "Kakao Local API 우선 모드에서 조건에 맞는 장소 후보를 확보하지 못했습니다.",
                        "recovery": kakao_payload.get("message", "KAKAO_REST_API_KEY 또는 Kakao Local API 검색 조건을 확인해야 합니다."),
                    }
                    parsed.handled_exceptions.append(kakao_issue)
                    deterministic_reflection += " " + kakao_issue["recovery"]
                    trace.write(
                        agent_name="Public Data Agent",
                        pattern="Reflection Pattern",
                        thought_summary="Kakao Local API Observation을 검토해 후보 부족 또는 API 설정 문제를 최종 답변에 표시합니다.",
                        reflection=kakao_issue["recovery"],
                        observation=kakao_payload,
                        messages_count=len(messages),
                    )

                reflection = await run_llm_reflection(
                    query=query,
                    parsed=parsed,
                    recommendations=recommendations,
                    deterministic_reflection=deterministic_reflection,
                    trace=trace,
                    messages_count=len(messages),
                    use_llm=use_llm,
                    data_source=source_for_answer,
                )
                trace.write(
                    agent_name="Reflection Reviewer",
                    pattern="Reflection Pattern",
                    thought_summary="Kakao Local API 후보가 사용자 조건에 맞는지 점검합니다.",
                    reflection=reflection,
                    observation={"recommendation_ids": [item["restaurant_id"] for item in recommendations]},
                    messages_count=len(messages),
                )
                answer = build_public_final_answer(
                    query=query,
                    parsed=parsed,
                    weather=weather_observation.data,
                    profile=profile_observation.data,
                    recommendations=recommendations,
                    reflection=reflection,
                    data_source_label=source_for_answer,
                )
                answer = await run_llm_final_answer(
                    draft_answer=answer,
                    trace=trace,
                    messages_count=len(messages),
                    use_llm=use_llm,
                    data_source=source_for_answer,
                )
                messages.append({"role": "assistant", "content": f"Final Answer: {answer}"})
                trace.write(
                    agent_name="Coordinator Agent",
                    pattern="Final Answer",
                    thought_summary="Kakao Local API Observation과 Reflection 결과를 종합해 최종 답변을 생성합니다.",
                    messages_count=len(messages),
                    final_answer=answer,
                )
                return answer

            public_search_observation = await public_client.call_tool(
                ToolAction(
                    agent_name="Public Data Agent",
                    pattern="ReAct Pattern",
                    tool_name="search_tourapi_restaurants",
                    tool_input={
                        "area": public_area,
                        "cuisine": parsed.cuisine,
                        "max_price_level": parsed.max_price_level,
                        "min_rating": parsed.min_rating,
                        "min_review_count": parsed.min_review_count,
                        "max_distance_m": parsed.max_distance_m,
                        "near_gaeksa": near_gaeksa,
                        "limit": 8,
                        "use_cache": True,
                    },
                    mcp_server="public_data_server.py",
                    thought_summary="Thought: 실제 공공데이터 기반 후보를 먼저 확보해 샘플 데이터 의존도를 낮춥니다.",
                )
            )
            messages.append({"role": "tool", "content": f"Observation: {public_search_observation.summary}"})
            public_search_payload = public_search_observation.data
            if public_search_payload.get("query", {}).get("food_filter_relaxed"):
                strict_food_requested = parsed.cuisine in STRICT_PUBLIC_CUISINE_TERMS
                relaxed_issue = {
                    "type": "food_filter_relaxed",
                    "severity": "warning",
                    "message": "요청한 음식 종류와 정확히 일치하는 공공데이터 후보가 부족합니다.",
                    "recovery": (
                        "TourAPI 후보는 넓게 수집하되 최종 추천에서는 술집 의도를 엄격히 유지하고, 가능하면 Kakao Local API 보강 검색을 시도합니다."
                        if strict_food_requested
                        else "음식 종류 필터를 완화하고 전주 음식점 후보 전체를 거리와 상세정보 기준으로 다시 비교합니다."
                    ),
                }
                parsed.handled_exceptions.append(relaxed_issue)
                trace.write(
                    agent_name="Public Data Agent",
                    pattern="Reflection Pattern",
                    thought_summary="공공데이터 Observation에서 음식 종류 필터 완화가 필요하다고 판단했습니다.",
                    reflection=relaxed_issue["recovery"],
                    observation=public_search_payload,
                    messages_count=len(messages),
                )

            if public_search_payload.get("status") == "ok" and public_search_payload.get("count", 0) > 0:
                public_candidates = public_search_payload.get("candidates", [])
                detailed_candidates: list[dict[str, Any]] = []
                for candidate in public_candidates[:5]:
                    detail_observation = await public_client.call_tool(
                        ToolAction(
                            agent_name="Public Data Agent",
                            pattern="Tool Use Pattern",
                            tool_name="get_tourapi_restaurant_detail",
                            tool_input={"content_id": candidate["content_id"], "use_cache": True},
                            mcp_server="public_data_server.py",
                            thought_summary=f"Final Answer 전 공공데이터 상세 근거 보강을 위해 {candidate['name']} 정보를 조회합니다.",
                        )
                    )
                    detail_payload = detail_observation.data
                    detailed = detail_payload.get("restaurant") if detail_payload.get("status") == "ok" else None
                    if detailed is not None:
                        for field in ["distance_m", "distance_reference"]:
                            if candidate.get(field) is not None:
                                detailed[field] = candidate[field]
                    detailed_candidates.append(detailed or candidate)
                    messages.append({"role": "tool", "content": f"Observation: {detail_observation.summary}"})

                ranking_policy = build_ranking_policy(parsed, weather_observation.data, profile_observation.data)
                public_rank_observation = await public_client.call_tool(
                    ToolAction(
                        agent_name="Public Data Agent",
                        pattern="ReAct Pattern",
                        tool_name="rank_tourapi_restaurants",
                        tool_input={"candidates": detailed_candidates, "ranking_policy": ranking_policy},
                        mcp_server="public_data_server.py",
                        thought_summary="Thought: 공공데이터 후보를 거리, 상세정보 충실도, 요청 조건 일치도로 정렬합니다.",
                    )
                )
                messages.append({"role": "tool", "content": f"Observation: {public_rank_observation.summary}"})
                public_rank_payload = public_rank_observation.data
                public_ranked_candidates = public_rank_payload.get("ranked_candidates", [])

                if public_ranked_candidates:
                    recommendations, deterministic_reflection = reflect_public_recommendations(public_ranked_candidates, parsed)
                    source_for_answer = str(public_rank_payload.get("source") or "TourAPI KorService2")
                    if (
                        not recommendations
                        and parsed.cuisine in STRICT_PUBLIC_CUISINE_TERMS
                        and "search_kakao_local_places" in public_tools
                    ):
                        kakao_observation = await public_client.call_tool(
                            ToolAction(
                                agent_name="Public Data Agent",
                                pattern="Tool Use Pattern",
                                tool_name="search_kakao_local_places",
                                tool_input={
                                    "area": public_area,
                                    "cuisine": parsed.cuisine,
                                    "max_distance_m": parsed.max_distance_m,
                                    "near_gaeksa": near_gaeksa,
                                    "limit": 8,
                                },
                                mcp_server="public_data_server.py",
                                thought_summary="Thought: TourAPI가 요청 음식 종류를 직접 충족하지 못해 Kakao Local API로 장소 후보를 보강 검색합니다.",
                            )
                        )
                        messages.append({"role": "tool", "content": f"Observation: {kakao_observation.summary}"})
                        kakao_payload = kakao_observation.data
                        if kakao_payload.get("status") == "ok" and kakao_payload.get("count", 0) > 0:
                            kakao_rank_observation = await public_client.call_tool(
                                ToolAction(
                                    agent_name="Public Data Agent",
                                    pattern="ReAct Pattern",
                                    tool_name="rank_tourapi_restaurants",
                                    tool_input={
                                        "candidates": kakao_payload.get("candidates", []),
                                        "ranking_policy": build_ranking_policy(parsed, weather_observation.data, profile_observation.data),
                                    },
                                    mcp_server="public_data_server.py",
                                    thought_summary="Thought: Kakao Local 후보를 거리, 카테고리, 요청 조건 일치도로 정렬합니다.",
                                )
                            )
                            messages.append({"role": "tool", "content": f"Observation: {kakao_rank_observation.summary}"})
                            kakao_rank_payload = kakao_rank_observation.data
                            kakao_ranked = kakao_rank_payload.get("ranked_candidates", [])
                            if kakao_ranked:
                                recommendations, deterministic_reflection = reflect_public_recommendations(kakao_ranked, parsed)
                                source_for_answer = str(kakao_rank_payload.get("source") or "Kakao Local API")
                                deterministic_reflection = (
                                    "TourAPI에서 요청 음식 종류를 직접 충족하는 후보가 부족해 Kakao Local API 보강 검색을 수행했습니다. "
                                    + deterministic_reflection
                                )
                        else:
                            kakao_issue = {
                                "type": "kakao_local_unavailable",
                                "severity": "warning",
                                "message": "TourAPI 후보가 부족해 Kakao Local API 보강 검색을 시도했지만 사용할 수 없었습니다.",
                                "recovery": kakao_payload.get("message", "KAKAO_REST_API_KEY가 있으면 Kakao Local API로 장소 후보를 보강할 수 있습니다."),
                            }
                            parsed.handled_exceptions.append(kakao_issue)
                            trace.write(
                                agent_name="Public Data Agent",
                                pattern="Reflection Pattern",
                                thought_summary="Kakao Local API 보강 검색이 실패해 기존 데이터 한계를 최종 답변에 표시합니다.",
                                reflection=kakao_issue["recovery"],
                                observation=kakao_payload,
                                messages_count=len(messages),
                            )
                    reflection = await run_llm_reflection(
                        query=query,
                        parsed=parsed,
                        recommendations=recommendations,
                        deterministic_reflection=deterministic_reflection,
                        trace=trace,
                        messages_count=len(messages),
                        use_llm=use_llm,
                        data_source=source_for_answer,
                    )
                    trace.write(
                        agent_name="Reflection Reviewer",
                        pattern="Reflection Pattern",
                        thought_summary="공공데이터 후보가 사용자 조건에 맞는지 점검합니다.",
                        reflection=reflection,
                        observation={"recommendation_ids": [item["restaurant_id"] for item in recommendations]},
                        messages_count=len(messages),
                    )
                    answer = build_public_final_answer(
                        query=query,
                        parsed=parsed,
                        weather=weather_observation.data,
                        profile=profile_observation.data,
                        recommendations=recommendations,
                        reflection=reflection,
                    )
                    answer = await run_llm_final_answer(
                        draft_answer=answer,
                        trace=trace,
                        messages_count=len(messages),
                        use_llm=use_llm,
                        data_source=source_for_answer,
                    )
                    messages.append({"role": "assistant", "content": f"Final Answer: {answer}"})
                    trace.write(
                        agent_name="Coordinator Agent",
                        pattern="Final Answer",
                        thought_summary="공공데이터 Observation과 Reflection 결과를 종합해 최종 답변을 생성합니다.",
                        messages_count=len(messages),
                        final_answer=answer,
                    )
                    return answer

                public_fallback_reason = "공공데이터 후보 정렬 결과가 비어 있어 로컬 샘플 데이터셋으로 대체합니다."
            else:
                public_fallback_reason = public_search_payload.get("message") or "공공데이터 후보를 확보하지 못했습니다."

            trace.write(
                agent_name="Public Data Agent",
                pattern="Reflection Pattern",
                thought_summary="공공데이터 경로를 사용할 수 없어 로컬 샘플 데이터셋 fallback을 수행합니다.",
                reflection=public_fallback_reason,
                observation=public_search_payload,
                messages_count=len(messages),
            )

        max_steps = 5
        search_payload: dict[str, Any] | None = None
        ranking_payload: dict[str, Any] | None = None

        for step in range(1, max_steps + 1):
            if step == 1:
                search_input = build_search_input(parsed)
                observation = await gourmet_client.call_tool(
                    ToolAction(
                        agent_name="Culinary Finder Agent",
                        pattern="ReAct Pattern",
                        tool_name="search_restaurants",
                        tool_input=search_input,
                        mcp_server="gourmet_db_server.py",
                        thought_summary="Thought: 사용자의 지역, 가격, 리뷰 조건에 맞는 후보를 먼저 검색합니다.",
                    )
                )
                search_payload = observation.data
                messages.append({"role": "tool", "content": f"Observation: {observation.summary}"})

                if _is_error_payload(search_payload) and parsed.fallback_location:
                    local_fallback_reason = (
                        parsed.fallback_reason
                        or "로컬 샘플 데이터셋은 전주 객사 후보만 포함해, 실제 전주 세부 지역 검색이 필요할 때는 TourAPI 공공데이터 경로를 사용합니다. 현재 로컬 실행에서는 전주 객사 샘플로 대체합니다."
                    )
                    trace.write(
                        agent_name="Culinary Finder Agent",
                        pattern="Reflection Pattern",
                        thought_summary="맛집 검색 도구가 지원하지 않는 지역 error를 반환해 기본 과제 지역으로 대체합니다.",
                        reflection=local_fallback_reason,
                        observation=search_payload,
                        messages_count=len(messages),
                    )
                    parsed.location = parsed.fallback_location
                    parsed.fallback_reason = local_fallback_reason
                    parsed.fallback_applied = True
                    parsed.extracted_conditions.append(f"대체검색지역={parsed.location}")
                    search_input = build_search_input(parsed)
                    observation = await gourmet_client.call_tool(
                        ToolAction(
                            agent_name="Culinary Finder Agent",
                            pattern="Reflection Pattern",
                            tool_name="search_restaurants",
                            tool_input=search_input,
                            mcp_server="gourmet_db_server.py",
                            thought_summary="Fallback Action: 지원 가능한 과제 기본 지역으로 후보를 재검색합니다.",
                        )
                    )
                    search_payload = observation.data
                    messages.append({"role": "tool", "content": f"Observation: {observation.summary}"})

                if search_payload.get("count", 0) > 0:
                    continue

                relaxed_input = search_input.copy()
                relaxed_input["min_review_count"] = 0
                relaxed_input["min_rating"] = 4.0
                observation = await gourmet_client.call_tool(
                    ToolAction(
                        agent_name="Culinary Finder Agent",
                        pattern="Reflection Pattern",
                        tool_name="search_restaurants",
                        tool_input=relaxed_input,
                        mcp_server="gourmet_db_server.py",
                        thought_summary="Observation 결과 후보가 부족해 리뷰/평점 조건을 완화해 재검색합니다.",
                    )
                )
                search_payload = observation.data
                messages.append({"role": "tool", "content": f"Observation: {observation.summary}"})
                if search_payload.get("count", 0) == 0 and parsed.cuisine:
                    relaxed_issue = {
                        "type": "no_results_for_food_type",
                        "severity": "warning",
                        "message": f"{parsed.cuisine} 조건으로는 추천 후보를 찾지 못했습니다.",
                        "recovery": "음식 종류 조건을 해제하고 같은 지역의 전체 맛집 후보를 재검색합니다.",
                    }
                    parsed.handled_exceptions.append(relaxed_issue)
                    trace.write(
                        agent_name="Culinary Finder Agent",
                        pattern="Reflection Pattern",
                        thought_summary="검색 결과가 없어 음식 종류 조건을 완화하는 대안을 선택합니다.",
                        reflection=relaxed_issue["recovery"],
                        observation=search_payload,
                        messages_count=len(messages),
                    )
                    parsed.extracted_conditions.append("음식종류조건완화=전체")
                    parsed.cuisine = None
                    relaxed_input = build_search_input(parsed)
                    relaxed_input["min_review_count"] = 0
                    relaxed_input["min_rating"] = 4.0
                    observation = await gourmet_client.call_tool(
                        ToolAction(
                            agent_name="Culinary Finder Agent",
                            pattern="Reflection Pattern",
                            tool_name="search_restaurants",
                            tool_input=relaxed_input,
                            mcp_server="gourmet_db_server.py",
                            thought_summary="Fallback Action: 음식 종류를 전체로 넓혀 후보를 다시 검색합니다.",
                        )
                    )
                    search_payload = observation.data
                    messages.append({"role": "tool", "content": f"Observation: {observation.summary}"})
                continue

            if step == 2 and search_payload is not None:
                candidate_ids = [item["restaurant_id"] for item in search_payload.get("candidates", [])]
                ranking_policy = build_ranking_policy(parsed, weather_observation.data, profile_observation.data)
                observation = await gourmet_client.call_tool(
                    ToolAction(
                        agent_name="Culinary Finder Agent",
                        pattern="ReAct Pattern",
                        tool_name="rank_restaurants",
                        tool_input={"candidate_ids": candidate_ids, "ranking_policy": ranking_policy},
                        mcp_server="gourmet_db_server.py",
                        thought_summary="Thought: 검색 후보를 평점, 리뷰 수, 가격, 거리, 목적 적합성으로 정렬합니다.",
                    )
                )
                ranking_payload = observation.data
                messages.append({"role": "tool", "content": f"Observation: {observation.summary}"})
                continue

            if step == 3 and ranking_payload is not None:
                top_candidates = ranking_payload.get("ranked_candidates", [])[: parsed.limit]
                for candidate in top_candidates:
                    observation = await gourmet_client.call_tool(
                        ToolAction(
                            agent_name="Culinary Finder Agent",
                            pattern="Tool Use Pattern",
                            tool_name="get_restaurant_detail",
                            tool_input={"restaurant_id": candidate["restaurant_id"]},
                            mcp_server="gourmet_db_server.py",
                            thought_summary=f"Final Answer 전 추천 근거 보강을 위해 {candidate['name']} 상세 정보를 조회합니다.",
                        )
                    )
                    messages.append({"role": "tool", "content": f"Observation: {observation.summary}"})
                break

        ranked_candidates = (ranking_payload or {}).get("ranked_candidates", [])
        recommendations, deterministic_reflection = reflect_recommendations(ranked_candidates, parsed)
        reflection = await run_llm_reflection(
            query=query,
            parsed=parsed,
            recommendations=recommendations,
            deterministic_reflection=deterministic_reflection,
            trace=trace,
            messages_count=len(messages),
            use_llm=use_llm,
            data_source="local_sample_dataset",
        )
        trace.write(
            agent_name="Reflection Reviewer",
            pattern="Reflection Pattern",
            thought_summary="최종 후보 3곳이 사용자 조건에 맞는지 점검합니다.",
            reflection=reflection,
            observation={"recommendation_ids": [item["restaurant_id"] for item in recommendations]},
            messages_count=len(messages),
        )

        answer = build_final_answer(
            query=query,
            parsed=parsed,
            weather=weather_observation.data,
            profile=profile_observation.data,
            recommendations=recommendations,
            reflection=reflection,
            data_source_note=(
                f"공공데이터 경로를 사용할 수 없어 로컬 샘플 데이터셋으로 대체했습니다. 사유: {public_fallback_reason}"
                if public_fallback_reason
                else None
            ),
        )
        answer = await run_llm_final_answer(
            draft_answer=answer,
            trace=trace,
            messages_count=len(messages),
            use_llm=use_llm,
            data_source="local_sample_dataset",
        )
        messages.append({"role": "assistant", "content": f"Final Answer: {answer}"})
        trace.write(
            agent_name="Coordinator Agent",
            pattern="Final Answer",
            thought_summary="도구 Observation과 Reflection 결과를 종합해 최종 답변을 생성합니다.",
            messages_count=len(messages),
            final_answer=answer,
        )
        return answer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ReAct-aurant 맛집 추천 AI Agent")
    parser.add_argument("natural_query", nargs="*", help="--query 없이 바로 입력하는 자연어 맛집 추천 요청")
    parser.add_argument("--query", default=None, help="맛집 추천 요청 문장")
    parser.add_argument("--trace", default="logs/trace_jeonju.jsonl", help="Trace JSONL 저장 경로")
    parser.add_argument(
        "--data-source",
        choices=["auto", "public", "local", "kakao"],
        default="auto",
        help="맛집 후보 데이터 소스입니다. kakao는 Kakao Local API를 1차 장소 검색 도구로 사용합니다.",
    )
    parser.add_argument("--use-llm", action="store_true", help="GPT Agent 모드를 명시적으로 사용합니다. 기본값은 OPENAI_API_KEY가 있으면 자동 사용입니다.")
    parser.add_argument("--no-llm", action="store_true", help="GPT Agent 모드를 끄고 규칙 기반 fallback으로 실행합니다.")
    return parser.parse_args()


def resolve_query(args: argparse.Namespace) -> str:
    if args.query:
        return args.query.strip()
    natural_query = " ".join(args.natural_query).strip()
    return natural_query or DEFAULT_QUERY


def resolve_llm_enabled(args: argparse.Namespace) -> bool:
    if args.no_llm:
        return False
    if args.use_llm:
        return True
    return bool(os.getenv("OPENAI_API_KEY"))


def main() -> None:
    load_dotenv()
    args = parse_args()
    query = resolve_query(args)
    use_llm = resolve_llm_enabled(args)
    trace_path = Path(args.trace) if args.trace else None
    answer = asyncio.run(run_agent(query, trace_path, use_llm, args.data_source))
    print(answer)
    if trace_path is not None:
        print()
        print(f"Trace 저장 위치: {trace_path}")


if __name__ == "__main__":
    main()
