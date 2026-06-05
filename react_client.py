from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, Field


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


DEFAULT_QUERY = "전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집을 찾아줘. 너무 비싸지 않고, 리뷰가 좋은 곳 위주로 3곳 추천해줘."
DEFAULT_LOCATION = "전주 객사"
JEONJU_DETAIL_AREA_ALIASES: dict[str, list[str]] = {
    "객사": ["객사", "객리단길", "전주객사"],
    "한옥마을": ["한옥마을", "전주한옥마을"],
    "전북대": ["전북대", "전북대학교", "전대"],
    "송천동": ["송천동", "송천"],
    "효자동": ["효자동", "신시가지"],
    "혁신도시": ["혁신도시", "전주혁신도시"],
    "아중리": ["아중리", "아중", "인후동"],
    "서신동": ["서신동", "서신"],
    "평화동": ["평화동", "평화"],
    "삼천동": ["삼천동", "삼천"],
    "중화산동": ["중화산동", "중화산"],
    "전주역": ["전주역", "역 앞", "역앞"],
    "전주터미널": ["터미널", "고속버스터미널", "시외버스터미널", "전주터미널"],
}


class ParsedRequest(BaseModel):
    location: str = DEFAULT_LOCATION
    cuisine: str | None = None
    purpose: str = "친구와 저녁"
    max_price_level: int = 2
    min_rating: float = 4.2
    min_review_count: int = 100
    max_distance_m: int = 1000
    limit: int = 3
    extracted_conditions: list[str] = Field(default_factory=list)
    fallback_location: str | None = None
    fallback_reason: str | None = None
    fallback_applied: bool = False


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


def detect_jeonju_location(query: str) -> str | None:
    for area_name, aliases in JEONJU_DETAIL_AREA_ALIASES.items():
        if any(alias in query for alias in aliases):
            return f"전주 {area_name}"
    if "전주" in query:
        return "전주"
    return None


def parse_user_request(query: str) -> ParsedRequest:
    conditions: list[str] = []
    fallback_location: str | None = None
    fallback_reason: str | None = None

    if "홍대" in query:
        location = "서울 홍대"
        fallback_location = DEFAULT_LOCATION
        fallback_reason = "로컬 맛집 데이터셋은 전주 객사 지역을 기준으로 구성되어, 맛집 검색 실패 시 전주 객사로 대체합니다."
    elif "존재하지 않는" in query or "없는 지역" in query or "미지원" in query:
        location = "존재하지 않는 지역"
        fallback_location = DEFAULT_LOCATION
        fallback_reason = "요청 지역을 지원하지 않아 과제 기본 지역인 전주 객사로 대체합니다."
    elif detected_location := detect_jeonju_location(query):
        location = detected_location
        if location != DEFAULT_LOCATION:
            fallback_location = DEFAULT_LOCATION
            fallback_reason = "공공데이터 경로를 사용할 수 없으면 로컬 샘플 데이터셋 기준 지역인 전주 객사로 대체합니다."
    else:
        location = DEFAULT_LOCATION
        fallback_reason = "요청에 명확한 지원 지역이 없어 과제 기본 지역인 전주 객사를 사용합니다."
    conditions.append(f"지역={location}")
    if fallback_reason and not (location.startswith("전주") and fallback_location == DEFAULT_LOCATION):
        conditions.append(f"지역보정={fallback_reason}")

    cuisine: str | None = None
    for candidate in ["한식", "일식", "양식", "분식", "카페", "고기"]:
        if candidate in query:
            cuisine = candidate
            conditions.append(f"음식종류={candidate}")
            break

    purpose_parts: list[str] = []
    if "친구" in query:
        purpose_parts.append("친구")
    if "저녁" in query:
        purpose_parts.append("저녁")
    purpose = "와 ".join(purpose_parts) if purpose_parts else "친구와 저녁"
    conditions.append(f"목적={purpose}")

    max_price_level = 2
    if "아주 저렴" in query or "저렴" in query:
        max_price_level = 1
    elif "비싸" in query or "가성비" in query or "부담" in query:
        max_price_level = 2
    conditions.append(f"최대가격대={max_price_level}")

    min_rating = 4.2 if "리뷰" in query or "평점" in query or "좋은" in query else 4.0
    min_review_count = 100 if "리뷰" in query else 50
    if "10000" in query:
        min_review_count = 10000
    conditions.append(f"최소평점={min_rating}")
    conditions.append(f"최소리뷰수={min_review_count}")

    return ParsedRequest(
        location=location,
        cuisine=cuisine,
        purpose=purpose,
        max_price_level=max_price_level,
        min_rating=min_rating,
        min_review_count=min_review_count,
        max_distance_m=1000,
        limit=3,
        extracted_conditions=conditions,
        fallback_location=fallback_location,
        fallback_reason=fallback_reason,
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
    return {
        "purpose": parsed.purpose,
        "cuisine": parsed.cuisine,
        "max_price_level": parsed.max_price_level,
        "weather": weather.get("weather"),
        "weather_hints": weather.get("food_hints", []),
        "preferred_cuisines": profile.get("preferred_cuisines", []),
        "preferred_price_level": profile.get("preferred_price_level", parsed.max_price_level),
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

    reflection = "조건 검토 완료: 가격, 리뷰 수, 평점, 거리, 친구와 저녁 목적을 확인했습니다."
    if warnings:
        reflection += " " + " ".join(warnings)
    return accepted[: parsed.limit], reflection


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
        f"날씨 반영: {weather.get('location', parsed.location)} 기준 {weather.get('weather', '알 수 없음')}, {weather.get('temperature_c', '알 수 없음')}도",
        f"사용자 선호 반영: {', '.join(profile.get('notes', []))}",
    ]
    if data_source_note:
        lines.append(f"데이터 처리: {data_source_note}")
    if parsed.fallback_applied and parsed.fallback_reason:
        lines.append(f"대체 처리: {parsed.fallback_reason} 현재 추천 기준 지역은 {parsed.location}입니다.")
    elif parsed.fallback_reason:
        lines.append(f"요청 보정: {parsed.fallback_reason}")
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

    for candidate in ranked_candidates:
        if parsed.cuisine and candidate.get("cuisine") and candidate.get("cuisine") != parsed.cuisine:
            warnings.append(f"{candidate.get('name', '후보')}: 요청 음식 종류와 달라 후순위로 두었습니다.")
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
        if len(accepted) < parsed.limit:
            warnings.append(f"공공데이터 후보가 {len(accepted)}곳만 확보되었습니다.")
        elif warnings:
            warnings.append("음식 종류 조건을 엄격히 적용하면 후보가 부족해 점수 순 대체 후보를 보완했습니다.")

    reflection = (
        "공공데이터 검토 완료: 한국관광공사 TourAPI의 주소, 좌표, 상세정보 충실도, 요청 조건 일치도를 확인했습니다. "
        "TourAPI는 리뷰 수와 평점을 제공하지 않아 해당 항목은 추천 기준에서 제외했습니다."
    )
    if warnings:
        reflection += " " + " ".join(warnings)
    return accepted[: parsed.limit], reflection


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
) -> str:
    lines = [
        "최종 추천 결과",
        "",
        f"요청: {query}",
        f"분석 조건: {', '.join(parsed.extracted_conditions)}",
        "데이터 출처: 한국관광공사 TourAPI KorService2",
        "데이터 한계: TourAPI는 리뷰 수와 평점을 제공하지 않아 임의 수치를 생성하지 않았습니다.",
        f"날씨 반영: {weather.get('location', parsed.location)} 기준 {weather.get('weather', '알 수 없음')}, {weather.get('temperature_c', '알 수 없음')}도",
        f"사용자 선호 반영: {', '.join(profile.get('notes', []))}",
        "",
    ]

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
        lines.extend(
            [
                f"{index}. {restaurant['name']} ({restaurant.get('cuisine') or '음식점'})",
                f"- 추천 이유: {restaurant.get('recommendation_reason', 'TourAPI 등록 음식점 정보 기준으로 추천했습니다.')}",
                f"- 주소: {_public_value(restaurant.get('address'))}",
                f"- 거리: {distance_reference} 기준 {distance_text}",
                f"- 전화: {_public_value(restaurant.get('phone'))}",
                f"- 대표 메뉴: {', '.join(menus) if menus else 'TourAPI 상세 메뉴 정보 없음'}",
                f"- 영업 정보: {_public_value(operation.get('open_time'))}, 휴무 {_public_value(operation.get('rest_date'))}",
                f"- 점수 근거: {score_reasons}",
                "",
            ]
        )

    lines.append(f"Reflection: {reflection}")
    return "\n".join(lines).strip()


async def maybe_polish_with_llm(answer: str, use_llm: bool) -> str:
    if not use_llm:
        return answer
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if not api_key:
        return answer + "\n\nLLM 보조: OPENAI_API_KEY가 없어 규칙 기반 답변을 그대로 사용했습니다."

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key, base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "한국어 과제 제출용 답변을 간결하고 명확하게 다듬어 주세요. 근거 숫자는 바꾸지 마세요."},
                {"role": "user", "content": answer},
            ],
            temperature=0.2,
            max_tokens=900,
        )
        content = response.choices[0].message.content
        return content or answer
    except Exception as exc:
        return answer + f"\n\nLLM 보조 실패 Observation: {exc}"


async def run_agent(
    query: str,
    trace_path: Path | None,
    use_llm: bool,
    data_source: Literal["local", "public", "auto"] = "auto",
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
        if data_source in {"public", "auto"}:
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
        await env_client.list_tools()
        await gourmet_client.list_tools()
        if public_client is not None:
            await public_client.list_tools()

        parsed = parse_user_request(query)
        trace.write(
            agent_name="Context Specialist Agent",
            pattern="Plan-and-Solve Pattern",
            thought_summary="사용자 요청에서 지역, 목적, 가격, 리뷰 조건을 구조화했습니다.",
            observation=parsed.model_dump(),
            messages_count=len(messages),
        )
        messages.append({"role": "assistant", "content": f"Thought: {parsed.extracted_conditions}"})

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
            public_search_observation = await public_client.call_tool(
                ToolAction(
                    agent_name="Public Data Agent",
                    pattern="ReAct Pattern",
                    tool_name="search_tourapi_restaurants",
                    tool_input={
                        "area": public_area,
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
                    recommendations, reflection = reflect_public_recommendations(public_ranked_candidates, parsed)
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
                    answer = await maybe_polish_with_llm(answer, use_llm=use_llm)
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
                    trace.write(
                        agent_name="Culinary Finder Agent",
                        pattern="Reflection Pattern",
                        thought_summary="맛집 검색 도구가 지원하지 않는 지역 error를 반환해 기본 과제 지역으로 대체합니다.",
                        reflection=parsed.fallback_reason,
                        observation=search_payload,
                        messages_count=len(messages),
                    )
                    parsed.location = parsed.fallback_location
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
        recommendations, reflection = reflect_recommendations(ranked_candidates, parsed)
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
        answer = await maybe_polish_with_llm(answer, use_llm=use_llm)
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
        choices=["auto", "public", "local"],
        default="auto",
        help="맛집 후보 데이터 소스입니다. auto는 TourAPI를 먼저 시도하고 실패 시 로컬 샘플로 대체합니다.",
    )
    parser.add_argument("--use-llm", action="store_true", help="선택적으로 GPT API로 최종 문장을 다듬습니다. 기본값은 비용 방지를 위해 비활성입니다.")
    return parser.parse_args()


def resolve_query(args: argparse.Namespace) -> str:
    if args.query:
        return args.query.strip()
    natural_query = " ".join(args.natural_query).strip()
    return natural_query or DEFAULT_QUERY


def main() -> None:
    args = parse_args()
    query = resolve_query(args)
    trace_path = Path(args.trace) if args.trace else None
    answer = asyncio.run(run_agent(query, trace_path, args.use_llm, args.data_source))
    print(answer)
    if trace_path is not None:
        print()
        print(f"Trace 저장 위치: {trace_path}")


if __name__ == "__main__":
    main()
