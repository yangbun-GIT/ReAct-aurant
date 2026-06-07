from argparse import Namespace
import os
import unittest
from unittest.mock import patch

from env_context_server import _resolve_location as _resolve_weather_location
from gourmet_db_server import rank_restaurants, search_restaurants
from jeonju_gazetteer import JEONJU_SEARCH_AREAS
from public_data_server import (
    CUISINE_KEYWORDS,
    _kakao_keyword_queries,
    _matches_food_query,
    _is_jeonju_restaurant,
    _resolve_search_area,
    _resolve_search_area_for_kakao_query,
    _score_public_restaurant,
    _standardize_kakao_place,
    _standardize_restaurant,
    extract_kakao_place_metrics,
    rank_tourapi_restaurants,
    search_kakao_local_places,
    search_tourapi_restaurants,
)
from react_client import (
    ParsedRequest,
    _observed_metric_judgment,
    append_llm_fallback_recommendation,
    build_public_final_answer,
    build_ranking_policy,
    enrich_kakao_candidates_with_place_metrics,
    evaluate_input_guard,
    parse_llm_json,
    parse_user_request,
    _public_candidate_matches_cuisine,
    run_llm_kakao_metric_judgment,
    reflect_public_recommendations,
    resolve_llm_enabled,
    resolve_query,
)


class RequestParsingTests(unittest.TestCase):
    def test_parse_llm_json_accepts_fenced_json(self) -> None:
        parsed = parse_llm_json('```json\n{"steps": ["search", "rank"]}\n```')

        self.assertEqual(parsed["steps"], ["search", "rank"])

    def test_parse_jeonju_gaeksa_request(self) -> None:
        parsed = parse_user_request("전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집을 찾아줘")

        self.assertEqual(parsed.location, "전주 객사")
        self.assertEqual(parsed.purpose, "친구와 저녁")
        self.assertEqual(parsed.limit, 3)
        self.assertIn("지역=전주 객사", parsed.extracted_conditions)

    def test_parse_default_quality_filters_without_default_price_preference(self) -> None:
        parsed = parse_user_request("전주 객사 일본식라면 추천")

        self.assertIsNone(parsed.max_price_level)
        self.assertEqual(parsed.min_rating, 4.0)
        self.assertEqual(parsed.min_review_count, 20)
        self.assertNotIn("가격대", parsed.missing_conditions)
        self.assertFalse(any(condition.startswith("최대가격대=") for condition in parsed.extracted_conditions))
        self.assertIn("최소평점=4.0", parsed.extracted_conditions)
        self.assertIn("최소리뷰수=20", parsed.extracted_conditions)

    def test_parse_explicit_price_preference_only_when_user_requests_it(self) -> None:
        parsed = parse_user_request("전주 객사 일본식라면 추천 너무 비싸지 않게")

        self.assertEqual(parsed.max_price_level, 2)
        self.assertIn("최대가격대=2", parsed.extracted_conditions)

    def test_branch_name_jeonjujeom_does_not_create_bar_intent(self) -> None:
        parsed = parse_user_request("평양옥류관 전주점 근처 맛집 추천")

        self.assertNotEqual(parsed.cuisine, "술집")
        self.assertEqual(parsed.location, "전주")

    def test_parse_unsupported_region_keeps_fallback_reason(self) -> None:
        parsed = parse_user_request("서울 홍대 근처에서 친구랑 저녁 먹기 좋은 맛집 추천해줘")

        self.assertEqual(parsed.location, "서울 홍대")
        self.assertEqual(parsed.fallback_location, "전주 객사")
        self.assertIsNotNone(parsed.fallback_reason)

    def test_parse_general_unsupported_region_keeps_fallback_reason(self) -> None:
        parsed = parse_user_request("부산 서면 근처에서 친구랑 저녁 먹기 좋은 맛집 추천해줘")

        self.assertEqual(parsed.location, "부산")
        self.assertEqual(parsed.fallback_location, "전주 객사")
        self.assertIn("전주로 한정", parsed.fallback_reason or "")

    def test_parse_jeonju_detail_area_request(self) -> None:
        parsed = parse_user_request("전주 송천동에서 친구랑 저녁 먹기 좋은 맛집 추천해줘")

        self.assertEqual(parsed.location, "전주 송천동")
        self.assertEqual(parsed.fallback_location, "전주 객사")
        self.assertIsNone(parsed.fallback_reason)
        self.assertIn("지역=전주 송천동", parsed.extracted_conditions)
        self.assertFalse(any(condition.startswith("지역보정=") for condition in parsed.extracted_conditions))

    def test_parse_official_jeonju_areas_without_unsupported_warning(self) -> None:
        cases = {
            "전주 다가동1가 한식 맛집 추천": "전주 중앙동",
            "전주 중동 점심 맛집 추천": "전주 혁신동",
            "전주 동산동 카페 추천": "전주 여의동",
            "전주 호성동 저녁 맛집 추천": "전주 호성동",
            "전주 팔복동 백반 맛집 추천": "전주 팔복동",
            "전주 에코시티 가족 식사 추천": "전주 송천동",
            "전주 전동 근처 한식 추천": "전주 풍남동",
            "전주 도청 근처 점심 추천": "전주 전북도청",
            "전주 전주대 근처 파스타 추천": "전주 전주대",
            "전주 비전대 근처 카페 추천": "전주 비전대",
            "전주 병무청 근처 밥집 추천": "전주 노송동",
            "전북대 병원 근처 한식 추천": "전주 전북대병원",
            "시외버스 정류장 쪽 맛집 추천해봐": "전주 전주터미널",
            "전주 시외버스정류장 근처 국밥 추천": "전주 전주터미널",
            "전주 고속 터미널 주변 카페 추천": "전주 전주터미널",
            "전주 법원 근처 점심 추천": "전주 만성동",
            "전주 검찰청 주변 밥집 추천": "전주 만성동",
            "전주 월드컵경기장 근처 식당 추천": "전주 여의동",
        }

        for query, expected_location in cases.items():
            with self.subTest(query=query):
                parsed = parse_user_request(query)
                guard = evaluate_input_guard(query, parsed)

                self.assertEqual(parsed.location, expected_location)
                self.assertFalse(any(issue["type"] == "unsupported_or_unresolved_location" for issue in guard["issues"]))

    def test_all_registered_jeonju_aliases_parse_without_unsupported_warning(self) -> None:
        for expected_area, config in JEONJU_SEARCH_AREAS.items():
            for alias in config["aliases"]:
                query = f"전주 {alias} 근처 한식 맛집 추천"
                with self.subTest(alias=alias):
                    parsed = parse_user_request(query)
                    guard = evaluate_input_guard(query, parsed)

                    self.assertEqual(parsed.location, f"전주 {expected_area}")
                    self.assertFalse(any(issue["type"] == "unsupported_or_unresolved_location" for issue in guard["issues"]))

    def test_kakao_location_resolution_prefers_kakao_then_local_alias(self) -> None:
        captured_queries: list[str] = []

        def fake_kakao_request(path: str, params: dict[str, object]) -> dict[str, object]:
            captured_queries.append(str(params["query"]))
            if str(params["query"]) == "도청":
                return {
                    "status": "ok",
                    "payload": {
                        "documents": [
                            {
                                "id": "do-office",
                                "place_name": "전북특별자치도청",
                                "road_address_name": "전북특별자치도 전주시 완산구 효자로 225",
                                "x": "127.108976712012",
                                "y": "35.8201963639598",
                                "place_url": "http://place.map.kakao.com/20999654",
                            }
                        ]
                    },
                }
            return {"status": "ok", "payload": {"documents": []}}

        with patch("public_data_server._kakao_request", side_effect=fake_kakao_request):
            kakao_area = _resolve_search_area_for_kakao_query("전주 도청")
            local_area = _resolve_search_area_for_kakao_query("전주 전북대 신정문")

        self.assertIn("도청", captured_queries)
        self.assertEqual(kakao_area["resolution_source"], "Kakao Local API keyword search")
        self.assertAlmostEqual(kakao_area["longitude"], 127.108976712012)
        self.assertEqual(local_area["name"], "전북대 신정문")
        self.assertEqual(local_area["resolution_source"], "local_jeonju_gazetteer")

    def test_parse_freeform_jeonju_commercial_area_and_food(self) -> None:
        parsed = parse_user_request("전주 웨리단길 파스타 맛집 추천해줘")

        self.assertEqual(parsed.location, "전주 웨리단길")
        self.assertEqual(parsed.cuisine, "파스타")
        self.assertIn("음식종류=파스타", parsed.extracted_conditions)

    def test_parse_long_jeonju_alias_before_parent_area(self) -> None:
        parsed = parse_user_request("전주 전북대 구정문 소바 맛집 알려줘")

        self.assertEqual(parsed.location, "전주 전북대 구정문")
        self.assertEqual(parsed.cuisine, "소바")

    def test_parse_jeonbuk_university_new_gate_alias_before_parent_area(self) -> None:
        cases = [
            "전북대 신정문 근처 초밥 추천",
            "전북대학교 한옥정문 근처 카페 추천",
            "전북대 정문 근처 밥집 추천",
        ]

        for query in cases:
            with self.subTest(query=query):
                parsed = parse_user_request(query)

                self.assertEqual(parsed.location, "전주 전북대 신정문")

    def test_parse_diverse_food_types_beyond_basic_categories(self) -> None:
        cases = {
            "전주 신시가지 마라탕 맛집 추천": ("전주 전북도청", "마라탕"),
            "전주 한옥마을 디저트 맛집 추천": ("전주 한옥마을", "디저트"),
            "전주 송천동 초밥 맛집 추천": ("전주 송천동", "초밥"),
            "전주 웨리단길 파스타 맛집 추천": ("전주 웨리단길", "파스타"),
            "전주 객사 해산물 맛집 추천": ("전주 객사", "해산물"),
            "전주 객사 일본식라면 맛집 추천": ("전주 객사", "일본식라면"),
            "전주 신시가지 양꼬치 맛집 추천": ("전주 전북도청", "양꼬치"),
            "전주 한옥마을 브런치카페 추천": ("전주 한옥마을", "브런치카페"),
        }

        for query, (expected_location, expected_cuisine) in cases.items():
            with self.subTest(query=query):
                parsed = parse_user_request(query)

                self.assertEqual(parsed.location, expected_location)
                self.assertEqual(parsed.cuisine, expected_cuisine)

    def test_parse_meal_time_as_purpose_not_cuisine(self) -> None:
        parsed = parse_user_request("전주 중동 점심 맛집 추천")

        self.assertEqual(parsed.location, "전주 혁신동")
        self.assertIsNone(parsed.cuisine)
        self.assertIn("점심", parsed.purpose)

    def test_parse_directional_place_before_matjip_not_as_cuisine(self) -> None:
        parsed = parse_user_request("시외버스 정류장 쪽 맛집 추천해봐")

        self.assertEqual(parsed.location, "전주 전주터미널")
        self.assertIsNone(parsed.cuisine)
        self.assertNotIn("지역=전주 객사", parsed.extracted_conditions)
        self.assertFalse(any(condition.startswith("지역보정=") for condition in parsed.extracted_conditions))
        self.assertNotIn("음식종류=쪽", parsed.extracted_conditions)

    def test_parse_area_alias_does_not_become_cuisine_with_requested_weather(self) -> None:
        parsed = parse_user_request("웨리단길 맛집 추천 비오는 날씨")
        guard = evaluate_input_guard("웨리단길 맛집 추천 비오는 날씨", parsed)

        self.assertEqual(parsed.location, "전주 웨리단길")
        self.assertIsNone(parsed.cuisine)
        self.assertEqual(parsed.requested_weather, "비")
        self.assertEqual(parsed.purpose, "일반 식사")
        self.assertIn("지역=전주 웨리단길", parsed.extracted_conditions)
        self.assertIn("날씨조건=비", parsed.extracted_conditions)
        self.assertIn("목적=일반 식사", parsed.extracted_conditions)
        self.assertIn("최대거리=700m", parsed.extracted_conditions)
        self.assertFalse(any(issue["severity"] == "error" for issue in guard["issues"]))

    def test_nearby_or_surrounding_terms_expand_area_without_losing_center(self) -> None:
        cases = [
            "전주 객사 근처 고기집 추천",
            "전주 객사 주변 고기집 추천",
            "전주 객사 인근 고기집 추천",
            "전주 객사 부근 고기집 추천",
        ]

        for query in cases:
            with self.subTest(query=query):
                parsed = parse_user_request(query)

                self.assertEqual(parsed.location, "전주 객사")
                self.assertEqual(parsed.max_distance_m, 1000)
                self.assertIn("최대거리=1000m", parsed.extracted_conditions)

    def test_walkable_terms_keep_compact_area_narrower_than_surrounding_terms(self) -> None:
        parsed = parse_user_request("전주 객사에서 걸어서 가기 좋은 고기집 추천")

        self.assertEqual(parsed.location, "전주 객사")
        self.assertEqual(parsed.max_distance_m, 700)
        self.assertIn("최대거리=700m", parsed.extracted_conditions)

    def test_parse_alcohol_intent_as_bar_request(self) -> None:
        parsed = parse_user_request("전주 에코시티 혼술 할 곳 추천")

        self.assertEqual(parsed.location, "전주 송천동")
        self.assertEqual(parsed.cuisine, "술집")
        self.assertIn("혼술", parsed.purpose)
        self.assertIn("음식종류=술집", parsed.extracted_conditions)

    def test_parse_standalone_bar_as_strict_bar_request(self) -> None:
        parsed = parse_user_request("전주 객사 바 추천")

        self.assertEqual(parsed.location, "전주 객사")
        self.assertEqual(parsed.cuisine, "바")
        self.assertEqual(parsed.purpose, "술자리")
        self.assertIn("음식종류=바", parsed.extracted_conditions)
        self.assertIn("목적=술자리", parsed.extracted_conditions)
        self.assertIn("최대거리=800m", parsed.extracted_conditions)

    def test_parse_bar_place_intent_defaults_to_drinking_purpose(self) -> None:
        parsed = parse_user_request("비오는 날 신시가지 술집 추천")

        self.assertEqual(parsed.location, "전주 전북도청")
        self.assertEqual(parsed.cuisine, "술집")
        self.assertEqual(parsed.purpose, "술자리")
        self.assertNotIn("방문 목적", parsed.missing_conditions)

    def test_parse_bakery_as_bakery_not_cafe(self) -> None:
        parsed = parse_user_request("전주 객사 빵집 추천")

        self.assertEqual(parsed.location, "전주 객사")
        self.assertEqual(parsed.cuisine, "빵집")
        self.assertIn("음식종류=빵집", parsed.extracted_conditions)
        self.assertIn("최대거리=800m", parsed.extracted_conditions)

    def test_parse_dessert_cafe_before_general_cafe(self) -> None:
        parsed = parse_user_request("전주 객사 디저트카페 추천")

        self.assertEqual(parsed.location, "전주 객사")
        self.assertEqual(parsed.cuisine, "디저트카페")

    def test_parse_weather_condition_across_jeonju_aliases(self) -> None:
        cases = {
            "객사 맛집 비 오는 날": "전주 객사",
            "한옥마을 비 오는 날 디저트 추천": "전주 한옥마을",
            "신시가지 비오는날 마라탕 추천": "전주 전북도청",
        }

        for query, expected_location in cases.items():
            with self.subTest(query=query):
                parsed = parse_user_request(query)

                self.assertEqual(parsed.location, expected_location)
                self.assertEqual(parsed.requested_weather, "비")

    def test_weather_detection_does_not_treat_food_syllables_as_weather(self) -> None:
        parsed = parse_user_request("전주 객사 비빔밥 맛집 추천")

        self.assertEqual(parsed.cuisine, "비빔밥")
        self.assertIsNone(parsed.requested_weather)

    def test_requested_weather_overrides_actual_weather_for_ranking_policy(self) -> None:
        parsed = ParsedRequest(
            location="전주 웨리단길",
            requested_weather="비",
            extracted_conditions=["지역=전주 웨리단길", "날씨조건=비"],
        )

        policy = build_ranking_policy(
            parsed,
            {"weather": "맑음", "food_hints": ["양식"]},
            {"preferred_cuisines": ["한식"], "preferred_price_level": 2},
        )

        self.assertEqual(policy["weather"], "비")
        self.assertEqual(policy["actual_weather"], "맑음")
        self.assertEqual(policy["requested_weather"], "비")
        self.assertIn("실내 좌석", policy["weather_hints"])
        self.assertIn("막걸리", policy["weather_hints"])
        self.assertIn("파전", policy["weather_hints"])
        self.assertIn("양식", policy["weather_hints"])

    def test_resolve_query_accepts_positional_natural_language(self) -> None:
        args = Namespace(query=None, natural_query=["전주", "효자동", "한식", "추천"])

        self.assertEqual(resolve_query(args), "전주 효자동 한식 추천")

    def test_resolve_llm_enabled_honors_no_llm_flag(self) -> None:
        args = Namespace(no_llm=True, use_llm=True)

        self.assertFalse(resolve_llm_enabled(args))

    def test_input_guard_warns_for_insufficient_conditions(self) -> None:
        parsed = parse_user_request("추천해줘")
        guard = evaluate_input_guard("추천해줘", parsed)

        self.assertEqual(guard["status"], "warning")
        self.assertIn("지역", parsed.missing_conditions)
        self.assertTrue(any(issue["type"] == "insufficient_conditions" for issue in guard["issues"]))

    def test_input_guard_warns_for_ambiguous_food_but_continues(self) -> None:
        parsed = parse_user_request("전주 객사에서 아무거나 먹을 만한 곳 추천해줘")
        guard = evaluate_input_guard("전주 객사에서 아무거나 먹을 만한 곳 추천해줘", parsed)

        self.assertEqual(guard["status"], "warning")
        self.assertEqual(guard["routing_decision"], "continue_with_assumptions")
        self.assertTrue(any(issue["type"] == "ambiguous_food_type" for issue in guard["issues"]))

    def test_input_guard_blocks_unrelated_query(self) -> None:
        parsed = parse_user_request("파이썬 코드 알려줘")
        guard = evaluate_input_guard("파이썬 코드 알려줘", parsed)

        self.assertEqual(guard["status"], "blocked")
        self.assertTrue(any(issue["type"] == "unrelated_request" for issue in guard["issues"]))

    def test_input_guard_blocks_harmful_non_restaurant_query(self) -> None:
        parsed = parse_user_request("살인 방법 알려줘")
        guard = evaluate_input_guard("살인 방법 알려줘", parsed)

        self.assertEqual(guard["status"], "blocked")
        self.assertTrue(any(issue["type"] == "safety_blocked" for issue in guard["issues"]))

    def test_input_guard_blocks_sexual_restaurant_query(self) -> None:
        query = "전주 객사 성적인 맛집 추천해줘"
        parsed = parse_user_request(query)
        guard = evaluate_input_guard(query, parsed)

        self.assertEqual(guard["status"], "blocked")
        self.assertTrue(any(issue["type"] == "safety_blocked" for issue in guard["issues"]))

    def test_input_guard_keeps_odd_restaurant_context_with_warning(self) -> None:
        query = "전주 객사에서 살인적인 매운 맛집 추천해줘"
        parsed = parse_user_request(query)
        guard = evaluate_input_guard(query, parsed)

        self.assertEqual(guard["status"], "warning")
        self.assertFalse(any(issue["severity"] == "error" for issue in guard["issues"]))
        self.assertTrue(any(issue["type"] == "unsafe_expression_sanitized" for issue in guard["issues"]))


class PublicDataServerTests(unittest.TestCase):
    def test_standardize_restaurant_cleans_html_and_sets_public_fields(self) -> None:
        raw = {
            "contentid": "123",
            "title": "테스트식당",
            "addr1": "전북특별자치도 전주시 완산구 테스트길 1",
            "cat1": "A05",
            "cat3": "A05020100",
            "mapx": "127.1467",
            "mapy": "35.8187",
            "tel": "063-000-0000",
            "firstmenu": "비빔밥<br>김치찜",
            "overview": "전주 음식점<br>상세 소개",
        }

        restaurant = _standardize_restaurant(
            raw,
            reference_coordinates={"longitude": 127.1467, "latitude": 35.8187},
            reference_name="객사",
        )

        self.assertEqual(restaurant["restaurant_id"], "tourapi:123")
        self.assertEqual(restaurant["cuisine"], "한식")
        self.assertEqual(restaurant["distance_m"], 0)
        self.assertEqual(restaurant["distance_reference"], "객사")
        self.assertIsNone(restaurant["rating"])
        self.assertIsNone(restaurant["review_count"])
        self.assertNotIn("<", restaurant["overview"])
        self.assertIn("TourAPI는 평점, 리뷰 수, 가격대를 제공하지 않아", restaurant["source_note"])

    def test_resolve_search_area_supports_jeonju_detail_areas(self) -> None:
        search_area = _resolve_search_area("전주 효자동 맛집")

        self.assertIsNotNone(search_area)
        self.assertEqual(search_area["name"], "효자동")
        self.assertIn("longitude", search_area)

    def test_resolve_search_area_prefers_longest_alias(self) -> None:
        search_area = _resolve_search_area("전주 전북대 구정문 소바 맛집")

        self.assertIsNotNone(search_area)
        self.assertEqual(search_area["name"], "전북대 구정문")

    def test_resolve_search_area_supports_jeonbuk_university_new_gate_aliases(self) -> None:
        for query in ["전북대 신정문 초밥", "전북대학교 한옥정문 카페", "전북대 정문 밥집"]:
            with self.subTest(query=query):
                search_area = _resolve_search_area(query)

                self.assertIsNotNone(search_area)
                self.assertEqual(search_area["name"], "전북대 신정문")
                self.assertEqual(search_area["resolution_source"], "local_jeonju_gazetteer")
                self.assertAlmostEqual(search_area["longitude"], 127.1316, places=3)

    def test_gaeksa_area_uses_narrow_commercial_radius(self) -> None:
        search_area = _resolve_search_area("전주 객사 맛집")

        self.assertIsNotNone(search_area)
        self.assertEqual(search_area["name"], "객사")
        self.assertLessEqual(search_area["radius"], 800)

    def test_resolve_search_area_supports_official_jeonju_aliases(self) -> None:
        cases = {
            "전주 다가동1가 맛집": "중앙동",
            "전주 중동 맛집": "혁신동",
            "전주 동산동 맛집": "여의동",
            "전주 호성동 맛집": "호성동",
            "전주 팔복동 맛집": "팔복동",
            "전주 에코시티 맛집": "송천동",
            "전주 전동 한식": "풍남동",
        }

        for query, expected_area in cases.items():
            with self.subTest(query=query):
                search_area = _resolve_search_area(query)

                self.assertIsNotNone(search_area)
                self.assertEqual(search_area["name"], expected_area)
                self.assertIn("longitude", search_area)

    def test_all_registered_jeonju_aliases_resolve_to_public_search_area(self) -> None:
        for expected_area, config in JEONJU_SEARCH_AREAS.items():
            for alias in config["aliases"]:
                query = f"전주 {alias} 근처 맛집"
                with self.subTest(alias=alias):
                    search_area = _resolve_search_area(query)

                    self.assertIsNotNone(search_area)
                    self.assertEqual(search_area["name"], expected_area)
                    self.assertIn("longitude", search_area)

    def test_food_query_matches_specific_menu_terms(self) -> None:
        restaurant = {
            "name": "테스트 파스타",
            "cuisine": "양식",
            "address": "전주시 완산구",
            "overview": "크림 파스타와 리조또를 판매합니다.",
            "signature_menu": ["크림 파스타"],
            "operation": {},
        }

        self.assertTrue(_matches_food_query(restaurant, "파스타"))

    def test_specific_sushi_query_does_not_match_ramen_sibling_category(self) -> None:
        ramen = {
            "name": "치쿠린 전북대본점",
            "cuisine": "일본식라면",
            "address": "전북특별자치도 전주시 덕진구 명륜3길 9-1",
            "overview": "Kakao Local category: 음식점 > 일식 > 일본식라면",
            "signature_menu": [],
            "operation": {},
        }
        sushi = {
            "name": "도꾸이",
            "cuisine": "초밥,롤",
            "address": "전북특별자치도 전주시 덕진구 권삼득로 237",
            "overview": "Kakao Local category: 음식점 > 일식 > 초밥,롤",
            "signature_menu": [],
            "operation": {},
        }

        self.assertFalse(_matches_food_query(ramen, "초밥"))
        self.assertTrue(_matches_food_query(sushi, "초밥"))

    def test_food_query_expands_bar_intent_to_alcohol_terms(self) -> None:
        restaurant = {
            "name": "전주막걸리집",
            "cuisine": "한식",
            "address": "전주시 완산구",
            "overview": "막걸리와 해물파전을 판매합니다.",
            "signature_menu": ["막걸리", "해물파전"],
            "operation": {},
        }

        self.assertTrue(_matches_food_query(restaurant, "술집"))

    def test_bar_intent_does_not_match_unrelated_single_syllable_text(self) -> None:
        restaurant = {
            "name": "전주비빔밥집",
            "cuisine": "한식",
            "address": "전주시 완산구",
            "overview": "전주비빔밥을 판매합니다.",
            "signature_menu": ["육회비빔밥"],
            "operation": {},
        }

        self.assertFalse(_matches_food_query(restaurant, "술집"))

    def test_bar_intent_does_not_match_jeonjujeom_branch_name(self) -> None:
        restaurant = {
            "name": "미르밀옥류관 본점",
            "cuisine": "한식",
            "address": "전북특별자치도 전주시 완산구 마전들로 71",
            "overview": "평양 옥류관 전주점으로 시작한 냉면 전문점입니다.",
            "signature_menu": ["평양냉면"],
            "operation": {},
        }

        self.assertFalse(_matches_food_query(restaurant, "술집"))

    def test_strict_bar_query_only_matches_bar_like_candidates(self) -> None:
        bar = {
            "name": "객사 칵테일바",
            "cuisine": "술집",
            "address": "전주시 완산구",
            "overview": "Kakao Local category: 음식점 > 술집 > 칵테일바",
            "signature_menu": [],
            "operation": {},
        }
        restaurant = {
            "name": "객사 한식당",
            "cuisine": "한식",
            "address": "전주시 완산구",
            "overview": "Kakao Local category: 음식점 > 한식",
            "signature_menu": ["백반"],
            "operation": {},
        }

        self.assertTrue(_matches_food_query(bar, "바"))
        self.assertFalse(_matches_food_query(restaurant, "바"))

    def test_bakery_query_excludes_cafe_and_dessert_chains(self) -> None:
        bakery = {
            "name": "객사베이커리",
            "cuisine": "베이커리",
            "address": "전주시 완산구",
            "overview": "Kakao Local category: 음식점 > 간식 > 제과,베이커리",
            "signature_menu": [],
            "operation": {},
        }
        dessert_chain = {
            "name": "설빙 전주객사점",
            "cuisine": "카페",
            "address": "전주시 완산구",
            "overview": "Kakao Local category: 음식점 > 카페 > 디저트카페",
            "signature_menu": [],
            "operation": {},
        }
        coffee_chain = {
            "name": "더리터 전주객사점",
            "cuisine": "카페",
            "address": "전주시 완산구",
            "overview": "Kakao Local category: 음식점 > 카페",
            "signature_menu": [],
            "operation": {},
        }

        self.assertTrue(_matches_food_query(bakery, "빵집"))
        self.assertFalse(_matches_food_query(dessert_chain, "빵집"))
        self.assertFalse(_matches_food_query(coffee_chain, "빵집"))

    def test_kakao_standardization_does_not_treat_search_keyword_as_menu(self) -> None:
        restaurant = _standardize_kakao_place(
            {
                "id": "1",
                "place_name": "테스트 와인바",
                "category_name": "음식점 > 술집 > 와인바",
                "category_group_code": "FD6",
                "category_group_name": "음식점",
                "road_address_name": "전북특별자치도 전주시 완산구 전주객사길 1",
                "x": "127.1467",
                "y": "35.8187",
                "distance": "120",
                "place_url": "https://place.map.kakao.com/1",
            },
            reference_coordinates={"longitude": 127.1467, "latitude": 35.8187},
            reference_name="객사",
            requested_keyword="와인바",
        )

        self.assertEqual(restaurant["source"], "Kakao Local API")
        self.assertEqual(restaurant["signature_menu"], [])
        self.assertEqual(restaurant["search_keyword"], "와인바")

    def test_kakao_category_infers_fine_grained_cuisine(self) -> None:
        cases = [
            ("음식점 > 양식 > 이탈리안", "이탈리안"),
            ("음식점 > 아시아음식 > 베트남음식", "베트남음식"),
            ("음식점 > 카페 > 디저트카페", "디저트카페"),
            ("음식점 > 간식 > 제과,베이커리", "베이커리"),
            ("음식점 > 술집 > 와인바", "바"),
            ("음식점 > 일식 > 일본식라면", "일본식라면"),
            ("음식점 > 중식 > 양꼬치", "양꼬치"),
            ("음식점 > 양식 > 브런치카페", "브런치카페"),
        ]

        for category_name, expected in cases:
            with self.subTest(category_name=category_name):
                restaurant = _standardize_kakao_place(
                    {
                        "id": category_name,
                        "place_name": "테스트 장소",
                        "category_name": category_name,
                        "category_group_code": "FD6",
                        "category_group_name": "음식점",
                        "road_address_name": "전북특별자치도 전주시 완산구 전주객사길 1",
                        "x": "127.1467",
                        "y": "35.8187",
                    },
                    reference_coordinates={"longitude": 127.1467, "latitude": 35.8187},
                    reference_name="객사",
                    requested_keyword=None,
                )

                self.assertEqual(restaurant["cuisine"], expected)

    def test_kakao_meat_search_uses_area_qualified_queries(self) -> None:
        captured_queries: list[str] = []

        def fake_kakao_request(path: str, params: dict[str, object]) -> dict[str, object]:
            captured_queries.append(str(params["query"]))
            if params["query"] != "전주 객사 고기집":
                return {"status": "ok", "payload": {"documents": []}}
            return {
                "status": "ok",
                "payload": {
                    "documents": [
                        {
                            "id": "meat-1",
                            "place_name": "해율담",
                            "category_name": "음식점 > 한식 > 육류,고기",
                            "category_group_code": "FD6",
                            "category_group_name": "음식점",
                            "road_address_name": "전북특별자치도 전주시 완산구 현무1길 16",
                            "phone": "0507-1359-5506",
                            "x": "127.1455",
                            "y": "35.8188",
                            "distance": "340",
                            "place_url": "http://place.map.kakao.com/meat-1",
                        }
                    ]
                },
            }

        with patch("public_data_server._kakao_request", side_effect=fake_kakao_request):
            result = search_kakao_local_places(
                area="전주 객사",
                cuisine="고기집",
                min_rating=3.7,
                min_review_count=30,
                max_distance_m=1000,
            )

        self.assertIn("전주 객사 고기집", captured_queries)
        self.assertIn("육류고기", captured_queries)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["query"]["queries"][0], "전주 객사 고기집")
        self.assertEqual(result["candidates"][0]["name"], "해율담")
        self.assertEqual(result["candidates"][0]["cuisine"], "육류,고기")

    def test_kakao_registered_food_keywords_use_area_qualified_expansion(self) -> None:
        captured_queries: list[str] = []

        def fake_kakao_request(path: str, params: dict[str, object]) -> dict[str, object]:
            captured_queries.append(str(params["query"]))
            if params["query"] != "전주 객사 파스타":
                return {"status": "ok", "payload": {"documents": []}}
            return {
                "status": "ok",
                "payload": {
                    "documents": [
                        {
                            "id": "pasta-1",
                            "place_name": "객사파스타",
                            "category_name": "음식점 > 양식 > 이탈리안",
                            "category_group_code": "FD6",
                            "category_group_name": "음식점",
                            "road_address_name": "전북특별자치도 전주시 완산구 전주객사길 12",
                            "x": "127.1465",
                            "y": "35.8186",
                            "distance": "120",
                            "place_url": "http://place.map.kakao.com/pasta-1",
                        }
                    ]
                },
            }

        with patch("public_data_server._kakao_request", side_effect=fake_kakao_request):
            result = search_kakao_local_places(
                area="전주 객사",
                cuisine="파스타",
                max_distance_m=1000,
            )

        self.assertIn("전주 객사 파스타", captured_queries)
        self.assertIn("객사 파스타", captured_queries)
        self.assertIn("이탈리안", captured_queries)
        self.assertIn("양식", captured_queries)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["candidates"][0]["name"], "객사파스타")

    def test_all_registered_food_categories_build_area_qualified_kakao_queries(self) -> None:
        search_area = {"name": "객사"}

        for category, keywords in CUISINE_KEYWORDS.items():
            requested = category if category != "한식" else "한식"
            with self.subTest(category=category):
                queries = _kakao_keyword_queries(requested, search_area)

                self.assertTrue(queries)
                self.assertTrue(any(query.startswith(f"전주 객사 ") for query in queries))
                self.assertIn(requested, " ".join(queries + keywords))

    def test_parse_user_request_preserves_meat_house_intent(self) -> None:
        parsed = parse_user_request("전주 객사 고기집 추천해봐")

        self.assertEqual(parsed.location, "전주 객사")
        self.assertEqual(parsed.cuisine, "고기집")

    def test_public_candidate_match_uses_registered_food_expansion(self) -> None:
        candidate = {
            "name": "객사파스타",
            "cuisine": "이탈리안",
            "address": "전북특별자치도 전주시 완산구 전주객사길 12",
            "overview": "Kakao Local category: 음식점 > 양식 > 이탈리안",
            "search_keyword": "전주 객사 파스타",
            "category_codes": {"cat3": "음식점 > 양식 > 이탈리안"},
            "signature_menu": [],
        }

        self.assertTrue(_public_candidate_matches_cuisine(candidate, "파스타"))

    def test_public_candidate_match_does_not_treat_jeonju_address_as_hansik(self) -> None:
        candidate = {
            "name": "객사커피",
            "cuisine": "카페",
            "address": "전북특별자치도 전주시 완산구 전주객사길 12",
            "overview": "Kakao Local category: 음식점 > 카페 > 커피전문점",
            "search_keyword": "카페",
            "category_codes": {"cat3": "음식점 > 카페 > 커피전문점"},
            "signature_menu": [],
        }

        self.assertFalse(_public_candidate_matches_cuisine(candidate, "한식"))

    def test_public_candidate_match_does_not_treat_search_keyword_as_cuisine_match(self) -> None:
        candidate = {
            "name": "코츠모",
            "cuisine": "술집",
            "address": "전북특별자치도 전주시 덕진구 명륜3길 18-6",
            "overview": "Kakao Local category: 음식점 > 술집 > 일본식주점",
            "search_keyword": "초밥",
            "category_codes": {"cat3": "음식점 > 술집 > 일본식주점"},
            "signature_menu": [],
        }

        self.assertFalse(_public_candidate_matches_cuisine(candidate, "초밥"))

    def test_public_candidate_match_does_not_treat_parking_text_as_cafe(self) -> None:
        candidate = {
            "name": "사랑오리",
            "cuisine": "한식",
            "address": "전북특별자치도 전주시 완산구 쑥고개로 247",
            "overview": "오리요리 전문점이며 주차는 식당 앞에 할 수 있다.",
            "signature_menu": ["오리주물럭"],
        }

        self.assertFalse(_public_candidate_matches_cuisine(candidate, "카페"))

    def test_public_candidate_match_does_not_expand_specific_sushi_to_all_japanese_food(self) -> None:
        candidate = {
            "name": "치쿠린 전북대본점",
            "cuisine": "일본식라면",
            "address": "전북특별자치도 전주시 덕진구 명륜3길 9-1",
            "overview": "Kakao Local category: 음식점 > 일식 > 일본식라면",
            "search_keyword": "일식",
            "category_codes": {"cat3": "음식점 > 일식 > 일본식라면"},
            "signature_menu": [],
        }

        self.assertFalse(_public_candidate_matches_cuisine(candidate, "초밥"))

    def test_kakao_search_records_metric_proxy_without_fake_rating_review_price(self) -> None:
        kakao_payload = {
            "documents": [
                {
                    "id": "ramen-1",
                    "place_name": "객사라멘",
                    "category_name": "음식점 > 일식 > 일본식라면",
                    "category_group_code": "FD6",
                    "category_group_name": "음식점",
                    "road_address_name": "전북특별자치도 전주시 완산구 전주객사길 10",
                    "phone": "063-000-0000",
                    "x": "127.1467",
                    "y": "35.8187",
                    "distance": "91",
                    "place_url": "https://place.map.kakao.com/ramen-1",
                },
                {
                    "id": "ramen-2",
                    "place_name": "주소없는라멘",
                    "category_name": "음식점 > 일식 > 일본식라면",
                    "category_group_code": "FD6",
                    "category_group_name": "음식점",
                    "x": "127.1468",
                    "y": "35.8188",
                    "distance": "120",
                },
            ]
        }

        with patch("public_data_server._kakao_request", return_value={"status": "ok", "payload": kakao_payload}):
            result = search_kakao_local_places(
                area="전주 객사",
                cuisine="일본식라면",
                max_price_level=2,
                min_rating=4.0,
                min_review_count=50,
                max_distance_m=800,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["query"]["max_price_level"], 2)
        self.assertEqual(result["query"]["min_rating"], 4.0)
        self.assertEqual(result["query"]["min_review_count"], 50)
        self.assertIn("공식 메타데이터 검증", result["metric_proxy_policy"])
        self.assertEqual(set(result["unavailable_filters"]), {"rating", "review_count", "price_level"})
        self.assertEqual(len(result["candidates"]), 1)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["cuisine"], "일본식라면")
        self.assertIsNone(candidate["rating"])
        self.assertIsNone(candidate["review_count"])
        self.assertIsNone(candidate["average_price"])
        self.assertGreaterEqual(candidate["metadata_quality_score"], 4)
        self.assertIn("카카오 장소 링크 제공", candidate["metadata_quality_checks"])

    @patch.dict("os.environ", {"KAKAO_REST_API_KEY": ""})
    def test_kakao_local_search_reports_missing_key_as_observation(self) -> None:
        result = search_kakao_local_places(area="전주 신시가지", cuisine="술집", max_distance_m=700)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["source"], "Kakao Local API")
        self.assertIn("KAKAO_REST_API_KEY", result["message"])

    def test_extract_kakao_place_metrics_parses_static_page_evidence(self) -> None:
        class FakeResponse:
            status_code = 200
            text = "<html><body><main>평점 4.6 리뷰 128개 가격대 ₩₩</main></body></html>"

            def raise_for_status(self) -> None:
                return None

        with patch("public_data_server.httpx.get", return_value=FakeResponse()):
            result = extract_kakao_place_metrics(
                place_url="https://place.map.kakao.com/123",
                place_name="테스트라멘",
                min_rating=4.0,
                min_review_count=50,
                max_price_level=2,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["metrics_status"], "observed")
        self.assertEqual(result["rating"], 4.6)
        self.assertEqual(result["review_count"], 128)
        self.assertEqual(result["price_level"], 2)
        self.assertEqual(result["condition_checks"]["rating"], True)
        self.assertEqual(result["condition_checks"]["review_count"], True)
        self.assertEqual(result["condition_checks"]["price_level"], True)

    def test_extract_kakao_place_metrics_uses_panel_api_for_rating_review_price(self) -> None:
        class FakePanelResponse:
            status_code = 200
            text = "{}"

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {
                    "summary": {
                        "name": "Panel Ramen",
                        "category": {"name": "Japanese ramen"},
                    },
                    "kakaomap_review": {
                        "score_set": {
                            "average_score": 3.1,
                            "review_count": 30,
                        }
                    },
                    "blog_review": {"review_count": 57},
                    "ai_mate": {"price_level": {"symbol": "\u20a9\u20a9"}},
                    "menu": {"menus": {"items": [{"price": 7500}, {"price": 8000}]}},
                }

        with patch("public_data_server.httpx.get", return_value=FakePanelResponse()) as mocked_get:
            result = extract_kakao_place_metrics(
                place_url="https://place.map.kakao.com/27375643",
                place_name="Panel Ramen",
                min_rating=4.2,
                min_review_count=100,
                max_price_level=2,
            )

        self.assertEqual(mocked_get.call_count, 1)
        self.assertEqual(result["source"], "Kakao place panel API")
        self.assertEqual(result["metrics_status"], "observed")
        self.assertEqual(result["rating"], 3.1)
        self.assertEqual(result["review_count"], 30)
        self.assertEqual(result["blog_review_count"], 57)
        self.assertEqual(result["price_level"], 2)
        self.assertEqual(result["condition_checks"]["rating"], False)
        self.assertEqual(result["condition_checks"]["review_count"], False)
        self.assertEqual(result["condition_checks"]["price_level"], True)

    def test_extract_kakao_place_metrics_uses_panel_open_hours_for_closed_status(self) -> None:
        class FakePanelResponse:
            status_code = 200
            text = "{}"

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {
                    "summary": {
                        "name": "Closed Today",
                        "category": {"name": "Korean restaurant"},
                    },
                    "kakaomap_review": {
                        "score_set": {
                            "average_score": 4.8,
                            "review_count": 120,
                        }
                    },
                    "open_hours": {
                        "headline": {"code": "CLOSED", "display_text": "오늘 휴무", "display_text_info": ""},
                        "week_from_today": {
                            "week_periods": [
                                {
                                    "days": [
                                        {
                                            "is_highlight": True,
                                            "day_of_the_week_desc": "일(6/7)",
                                            "off_days": {"holiday_desc": "정기휴무"},
                                        }
                                    ]
                                }
                            ]
                        },
                    },
                }

        with patch("public_data_server.httpx.get", return_value=FakePanelResponse()):
            result = extract_kakao_place_metrics(
                place_url="https://place.map.kakao.com/999",
                place_name="Closed Today",
                min_rating=4.0,
                min_review_count=20,
            )

        self.assertEqual(result["source"], "Kakao place panel API")
        self.assertTrue(result["business_status_observed"])
        self.assertTrue(result["is_today_closed"])
        self.assertTrue(result["is_currently_unavailable"])
        self.assertEqual(result["opening_status"]["today_closed_text"], "정기휴무")

    def test_kakao_metric_judgment_rejects_failed_metrics_for_any_food_type(self) -> None:
        for cuisine in ["일본식라면", "술집", "빵집", "디저트카페", "한식"]:
            parsed = ParsedRequest(
                location="전주 객사",
                cuisine=cuisine,
                min_rating=4.2,
                min_review_count=100,
                max_price_level=2,
            )

            judgment = _observed_metric_judgment(
                {
                    "place_url": f"https://place.map.kakao.com/{abs(hash(cuisine))}",
                    "place_name": f"{cuisine} 후보",
                    "rating": 3.9,
                    "review_count": 30,
                    "price_level": 2,
                    "condition_checks": {
                        "rating": False,
                        "review_count": False,
                        "price_level": True,
                    },
                },
                parsed,
            )

            self.assertEqual(judgment["status"], "observed")
            self.assertFalse(judgment["meets_conditions"], cuisine)
            self.assertIn("평점 3.9 < 최소 4.2", judgment["reason"])
            self.assertIn("리뷰 수 30 < 최소 100", judgment["reason"])

    def test_kakao_metric_judgment_rejects_missing_required_metrics_for_any_food_type(self) -> None:
        for cuisine in ["술집", "바", "베이커리", "카페", "양식"]:
            parsed = ParsedRequest(
                location="전주 신시가지",
                cuisine=cuisine,
                min_rating=4.2,
                min_review_count=100,
                max_price_level=2,
            )

            judgment = _observed_metric_judgment(
                {
                    "place_url": f"https://place.map.kakao.com/missing-{abs(hash(cuisine))}",
                    "place_name": f"{cuisine} 후보",
                    "rating": None,
                    "review_count": None,
                    "price_level": 1,
                    "condition_checks": {
                        "rating": None,
                        "review_count": None,
                        "price_level": True,
                    },
                },
                parsed,
            )

            self.assertEqual(judgment["status"], "observed")
            self.assertFalse(judgment["meets_conditions"], cuisine)
            self.assertIn("평점 미관측", judgment["reason"])
            self.assertIn("리뷰 수 미관측", judgment["reason"])

    def test_public_rank_scores_jeonju_food_candidates(self) -> None:
        candidate = _standardize_restaurant(
            {
                "contentid": "456",
                "title": "전주한식집",
                "addr1": "전북특별자치도 전주시 완산구 전주객사3길 1",
                "cat1": "A05",
                "cat3": "A05020100",
                "mapx": "127.1467",
                "mapy": "35.8187",
                "firstmenu": "전주비빔밥",
            },
            reference_coordinates={"longitude": 127.1467, "latitude": 35.8187},
            reference_name="객사",
        )

        score, reasons = _score_public_restaurant(
            candidate,
            {
                "purpose": "친구와 저녁",
                "cuisine": "한식",
                "preferred_cuisines": ["한식"],
                "weather_hints": ["한식"],
                "requested_weather": "비",
            },
        )

        self.assertGreater(score, 40)
        self.assertIn("전주 주소 일치", reasons)
        self.assertIn("한식 조건 일치", reasons)
        self.assertIn("비 오는 날 이동 부담이 낮은 가까운 거리", reasons)

    def test_weather_location_resolves_jeonju_detail_aliases(self) -> None:
        location = _resolve_weather_location("전주 웨리단길")

        self.assertEqual(location["label"], "전주 웨리단길")
        self.assertIn("latitude", location)

    def test_public_search_rejects_non_jeonju_without_network(self) -> None:
        result = search_tourapi_restaurants(area="서울 홍대", use_cache=False)

        self.assertEqual(result["status"], "error")
        self.assertIn("전주", result["message"])

    def test_public_search_records_unavailable_review_rating_price_filters(self) -> None:
        fake_payload = {
            "response": {
                "body": {
                    "totalCount": 1,
                    "items": {
                        "item": [
                            {
                                "contentid": "public-1",
                                "title": "전주한식테스트",
                                "addr1": "전북특별자치도 전주시 완산구 전주객사3길 1",
                                "cat1": "A05",
                                "cat3": "A05020100",
                                "mapx": "127.1467",
                                "mapy": "35.8187",
                                "firstmenu": "전주비빔밥",
                            }
                        ]
                    },
                }
            }
        }

        with patch("public_data_server._tourapi_request", return_value={"status": "ok", "source": "mock", "cache_key": "test", "payload": fake_payload}):
            result = search_tourapi_restaurants(
                area="전주 객사",
                cuisine="한식",
                max_price_level=2,
                min_rating=4.2,
                min_review_count=100,
                max_distance_m=1000,
                use_cache=False,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["query"]["area"], "전주 객사")
        self.assertEqual(result["query"]["cuisine"], "한식")
        self.assertEqual(result["query"]["max_price_level"], 2)
        self.assertEqual(result["query"]["min_rating"], 4.2)
        self.assertEqual(result["query"]["min_review_count"], 100)
        self.assertEqual(result["query"]["max_distance_m"], 1000)
        self.assertEqual(result["query"]["target_area"], "객사")
        self.assertEqual(set(result["unavailable_filters"]), {"rating", "review_count", "price_level"})
        self.assertIn("TourAPI", result["data_limitations"])
        self.assertEqual(result["candidates"][0]["cuisine"], "한식")

    def test_public_filter_rejects_non_jeonju_addresses(self) -> None:
        self.assertTrue(_is_jeonju_restaurant({"address": "전북특별자치도 전주시 덕진구 중동로 1"}))
        self.assertFalse(_is_jeonju_restaurant({"address": "전북특별자치도 완주군 이서면 안전로 1"}))


class LocalRestaurantToolTests(unittest.TestCase):
    def test_local_search_filters_region_cuisine_price_rating_reviews_distance_and_purpose(self) -> None:
        result = search_restaurants(
            location="전주 객사",
            cuisine="한식",
            max_price_level=2,
            min_rating=4.5,
            min_review_count=300,
            max_distance_m=500,
            purpose="친구와 저녁",
            limit=10,
        )

        self.assertEqual(result["status"], "ok")
        self.assertGreater(result["count"], 0)
        self.assertEqual(result["query"]["location"], "전주 객사")
        self.assertEqual(result["query"]["cuisine"], "한식")
        self.assertEqual(result["query"]["max_price_level"], 2)
        self.assertEqual(result["query"]["min_rating"], 4.5)
        self.assertEqual(result["query"]["min_review_count"], 300)
        self.assertEqual(result["query"]["max_distance_m"], 500)

        for candidate in result["candidates"]:
            self.assertIn("전주 객사", candidate["location"])
            self.assertEqual(candidate["cuisine"], "한식")
            self.assertLessEqual(candidate["price_level"], 2)
            self.assertGreaterEqual(candidate["rating"], 4.5)
            self.assertGreaterEqual(candidate["review_count"], 300)
            self.assertLessEqual(candidate["distance_m"], 500)
            self.assertIn("친구", candidate["purpose_tags"])

    def test_local_rank_scores_weather_and_user_food_preferences(self) -> None:
        result = rank_restaurants(
            ["jj_gaeksa_001"],
            {
                "purpose": "친구와 저녁",
                "max_price_level": 2,
                "weather_hints": ["비"],
                "requested_weather": "비",
                "preferred_cuisines": ["한식"],
            },
        )

        self.assertEqual(result["status"], "ok")
        reasons = result["ranked_candidates"][0]["score_reasons"]

        self.assertTrue(any(reason.startswith("평점 ") for reason in reasons))
        self.assertTrue(any(reason.startswith("리뷰 ") for reason in reasons))
        self.assertIn("매우 가까움", reasons)
        self.assertIn("가격 조건 적합", reasons)
        self.assertIn("방문 목적 적합", reasons)
        self.assertIn("비 오는 날 이동 부담 낮음", reasons)
        self.assertIn("날씨/선호 힌트 적합", reasons)
        self.assertIn("사용자 선호 음식", reasons)


class PublicReflectionTests(unittest.TestCase):
    def test_ranked_kakao_recommendation_reason_explains_match_signals(self) -> None:
        result = rank_tourapi_restaurants(
            [
                {
                    "restaurant_id": "kakao:bar",
                    "name": "테스트바",
                    "source": "Kakao Local API",
                    "address": "전북특별자치도 전주시 완산구 전주객사1길 1",
                    "cuisine": "바",
                    "category_codes": {"cat1": "KAKAO_LOCAL", "cat3": "음식점 > 술집 > 칵테일바"},
                    "metadata_quality_score": 6,
                    "metadata_quality_checks": ["카카오 장소 링크 제공"],
                    "distance_m": 230,
                    "distance_reference": "객사",
                    "rating": 4.5,
                    "review_count": 40,
                    "price_level": 2,
                    "operation": {"open_time": "18:00 ~ 02:00"},
                }
            ],
            {"cuisine": "바", "purpose": "술자리", "target_location": "전주 객사", "min_rating": 4.0, "min_review_count": 20},
        )

        reason = result["ranked_candidates"][0]["recommendation_reason"]

        self.assertIn("바", reason)
        self.assertIn("230m", reason)
        self.assertIn("평점 4.5", reason)
        self.assertIn("리뷰 40개", reason)
        self.assertIn("영업 시간", reason)

    def test_kakao_ranking_penalizes_closed_not_before_open(self) -> None:
        base = {
            "restaurant_id": "kakao:bar",
            "name": "Bar",
            "source": "Kakao Local API",
            "address": "전북특별자치도 전주시 완산구 전주객사1길 1",
            "cuisine": "바",
            "category_codes": {"cat1": "KAKAO_LOCAL"},
            "metadata_quality_score": 6,
            "metadata_quality_checks": ["카카오 장소 링크 제공"],
            "distance_m": 300,
            "distance_reference": "객사",
        }
        policy = {"cuisine": "바", "purpose": "술자리", "max_distance_m": 1200}

        before_open = {
            **base,
            "opening_status": {"code": "BEFORE_OPEN", "display_text": "영업 전"},
            "is_currently_unavailable": True,
            "is_today_closed": False,
        }
        closed = {
            **base,
            "opening_status": {"code": "CLOSED", "display_text": "오늘 휴무"},
            "is_currently_unavailable": True,
            "is_today_closed": True,
        }

        before_score, before_reasons = _score_public_restaurant(before_open, policy)
        closed_score, closed_reasons = _score_public_restaurant(closed, policy)

        self.assertFalse(any("closed today" in reason for reason in before_reasons))
        self.assertTrue(any("closed today" in reason for reason in closed_reasons))
        self.assertLess(closed_score, before_score)

    def test_reflect_public_recommendations_does_not_require_fake_reviews(self) -> None:
        parsed = ParsedRequest(
            location="전주",
            cuisine="한식",
            limit=2,
            extracted_conditions=["지역=전주", "음식종류=한식"],
        )
        ranked = [
            {"restaurant_id": "tourapi:1", "name": "한식집", "cuisine": "한식"},
            {"restaurant_id": "tourapi:2", "name": "중식집", "cuisine": "중식"},
            {"restaurant_id": "tourapi:3", "name": "비빔밥집", "cuisine": "한식"},
        ]

        recommendations, reflection = reflect_public_recommendations(ranked, parsed)

        self.assertEqual([item["restaurant_id"] for item in recommendations], ["tourapi:1", "tourapi:3"])
        self.assertIn("TourAPI는 평점, 리뷰 수, 가격대를 제공하지 않아", reflection)

    def test_reflect_public_recommendations_does_not_pad_unmatched_food_type(self) -> None:
        parsed = ParsedRequest(
            location="전주 객사",
            cuisine="일본식라면",
            limit=3,
            extracted_conditions=["지역=전주 객사", "음식종류=일본식라면"],
        )
        ranked = [
            {"restaurant_id": "kakao:1", "name": "라멘집", "cuisine": "일본식라면", "source": "Kakao Local API"},
            {"restaurant_id": "kakao:2", "name": "한식집", "cuisine": "한식", "source": "Kakao Local API"},
        ]

        recommendations, reflection = reflect_public_recommendations(ranked, parsed)

        self.assertEqual([item["restaurant_id"] for item in recommendations], ["kakao:1"])
        self.assertIn("일본식라면 의도는 엄격히 유지했습니다", reflection)
        self.assertNotIn("대체 후보를 보완", reflection)

    def test_public_final_answer_shows_requested_weather_before_actual_weather(self) -> None:
        parsed = ParsedRequest(
            location="전주 웨리단길",
            requested_weather="비",
            extracted_conditions=["지역=전주 웨리단길", "날씨조건=비"],
        )

        answer = build_public_final_answer(
            "웨리단길 맛집 추천 비오는 날씨",
            parsed,
            {"location": "전주 웨리단길", "weather": "맑음", "temperature_c": 12.9},
            {"notes": ["걷기 부담 없는 거리"]},
            [],
            "검토 완료",
        )

        self.assertIn("사용자 요청 날씨 조건=비를 우선 반영", answer)
        self.assertIn("보편적인 기대: 비 오는 날은 파전, 막걸리", answer)
        self.assertIn("실제 날씨 조회: 전주 웨리단길 기준 맑음, 12.9도", answer)

    def test_public_final_answer_separates_unavailable_metric_conditions(self) -> None:
        parsed = ParsedRequest(
            location="전주 객사",
            cuisine="빵집",
            extracted_conditions=[
                "지역=전주 객사",
                "음식종류=빵집",
                "최대가격대=2",
                "최소평점=4.0",
                "최소리뷰수=50",
                "최대거리=800m",
            ],
        )

        answer = build_public_final_answer(
            "전주 객사 빵집 추천",
            parsed,
            {"location": "전주 객사", "weather": "맑음", "temperature_c": 21.5},
            {"notes": ["너무 비싸지 않은 곳", "리뷰가 좋은 곳", "걷기 부담 없는 거리"]},
            [
                {
                    "restaurant_id": "kakao:1",
                    "name": "PNB풍년제과 전주본점",
                    "cuisine": "베이커리",
                    "source": "Kakao Local API",
                    "address": "전주시 완산구",
                    "distance_m": 53,
                    "distance_reference": "객사",
                    "operation": {},
                    "score_reasons": ["빵집 조건 일치"],
                    "metadata_quality_score": 5,
                    "metadata_quality_checks": ["카카오 장소 링크 제공", "카카오 세부 카테고리 제공", "전주 주소 확인", "기준 위치와 거리 확인", "요청 업종 직접 일치"],
                    "place_metric_judgment": {
                        "status": "observed",
                        "rating": 4.5,
                        "review_count": 120,
                        "price_level": 2,
                        "meets_conditions": True,
                        "reason": "관측된 지표는 요청 조건을 위반하지 않습니다.",
                    },
                    "place_url": "https://place.map.kakao.com/1",
                }
            ],
            "Kakao Local API 검토 완료",
            data_source_label="Kakao Local API",
        )

        applied_line = next(line for line in answer.splitlines() if line.startswith("적용 조건:"))
        preference_line = next(line for line in answer.splitlines() if line.startswith("사용자 선호 반영:"))
        self.assertIn("최소평점", applied_line)
        self.assertIn("최소리뷰수", applied_line)
        self.assertIn("최대가격대", applied_line)
        self.assertIn("리뷰가 좋은 곳", preference_line)
        self.assertNotIn("미적용 조건:", answer)
        self.assertIn("카카오 장소 패널 API에서 관측된 평점/후기 수/가격대는 조건 필터링에 적용했습니다", answer)
        self.assertIn("공식 메타데이터 검증: 5점", answer)
        self.assertIn("장소 링크 지표 보강: observed", answer)
        self.assertIn("장소 링크: https://place.map.kakao.com/1", answer)


class KakaoMetricEnrichmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_metric_judgment_can_allow_unknown_metrics_during_recovery(self) -> None:
        parsed = ParsedRequest(
            location="전주 객사",
            cuisine="바",
            min_rating=3.5,
            min_review_count=0,
        )

        judgment = _observed_metric_judgment(
            {
                "place_url": "https://place.map.kakao.com/unknown",
                "place_name": "Metric Unknown Bar",
                "metrics_status": "not_found",
                "rating": None,
                "review_count": None,
                "condition_checks": {"rating": None, "review_count": None, "price_level": None},
                "business_status_observed": True,
                "opening_status": {"code": "BEFORE_OPEN", "display_text": "영업 전", "today_hours": "18:00 ~ 02:00"},
                "is_today_closed": False,
                "is_currently_unavailable": True,
            },
            parsed,
            allow_unknown_metrics=True,
        )

        self.assertEqual(judgment["status"], "observed")
        self.assertTrue(judgment["meets_conditions"])
        self.assertIn("보류 통과", judgment["reason"])

    async def test_metric_judgment_rejects_closed_place_even_with_good_metrics(self) -> None:
        parsed = ParsedRequest(
            location="?꾩＜ 媛앹궗",
            cuisine="怨좉린吏?",
            min_rating=4.0,
            min_review_count=20,
        )

        judgment = _observed_metric_judgment(
            {
                "place_url": "https://place.map.kakao.com/closed",
                "place_name": "Closed Meat",
                "metrics_status": "observed",
                "rating": 4.8,
                "review_count": 120,
                "condition_checks": {"rating": True, "review_count": True, "price_level": None},
                "business_status_observed": True,
                "opening_status": {"display_text": "오늘 휴무", "today_closed_text": "정기휴무"},
                "is_today_closed": True,
                "is_currently_unavailable": True,
            },
            parsed,
        )

        self.assertEqual(judgment["status"], "observed")
        self.assertFalse(judgment["meets_conditions"])
        self.assertIn("unavailable today", judgment["reason"])

    async def test_enrichment_excludes_closed_kakao_place(self) -> None:
        parsed = ParsedRequest(
            location="?꾩＜ 媛앹궗",
            cuisine="怨좉린吏?",
            min_rating=4.0,
            min_review_count=20,
            max_price_level=None,
        )
        candidates = [
            {
                "restaurant_id": "kakao:closed",
                "name": "Closed Meat",
                "place_url": "https://place.map.kakao.com/closed",
                "score_reasons": [],
            }
        ]

        class FakeClient:
            async def call_tool(self, action):
                class Result:
                    summary = "closed metrics observed"
                    data = {
                        "status": "ok",
                        "place_url": "https://place.map.kakao.com/closed",
                        "place_name": "Closed Meat",
                        "metrics_status": "observed",
                        "rating": 4.8,
                        "review_count": 120,
                        "price_level": None,
                        "condition_checks": {"rating": True, "review_count": True, "price_level": None},
                        "business_status_observed": True,
                        "opening_status": {"display_text": "오늘 휴무", "today_closed_text": "정기휴무"},
                        "is_today_closed": True,
                        "is_currently_unavailable": True,
                    }

                return Result()

        class DummyTrace:
            def write(self, **kwargs):
                return None

        enriched, reflection = await enrich_kakao_candidates_with_place_metrics(
            candidates=candidates,
            parsed=parsed,
            public_client=FakeClient(),
            trace=DummyTrace(),
            messages=[],
            use_llm=False,
            enabled=True,
        )

        self.assertEqual(enriched, [])
        self.assertIn("Closed Meat", reflection)
        self.assertIn("unavailable today", reflection)

    async def test_llm_metric_judgment_cannot_override_observed_failed_metrics(self) -> None:
        parsed = ParsedRequest(
            location="전주 객사",
            cuisine="일본식라면",
            min_rating=3.7,
            min_review_count=30,
        )

        class DummyTrace:
            def write(self, **kwargs):
                return None

        async def fake_llm(**kwargs):
            return '[{"place_url":"https://place.map.kakao.com/1","place_name":"산쪼메","status":"observed","rating":4.8,"review_count":200,"price_level":1,"meets_conditions":true,"reason":"GPT 추정 통과"}]'

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), patch("react_client.call_llm", side_effect=fake_llm):
            judgments = await run_llm_kakao_metric_judgment(
                metric_observations=[
                    {
                        "place_url": "https://place.map.kakao.com/1",
                        "place_name": "산쪼메",
                        "metrics_status": "observed",
                        "rating": 3.1,
                        "review_count": 30,
                        "price_level": None,
                        "condition_checks": {"rating": False, "review_count": True, "price_level": None},
                        "evidence_text": "kakaomap_average_score=3.1; kakaomap_review_count=30",
                    }
                ],
                parsed=parsed,
                trace=DummyTrace(),
                messages_count=1,
                use_llm=True,
            )

        self.assertEqual(judgments[0]["rating"], 3.1)
        self.assertEqual(judgments[0]["review_count"], 30)
        self.assertFalse(judgments[0]["meets_conditions"])
        self.assertIn("평점 3.1 < 최소 3.7", judgments[0]["reason"])

    async def test_llm_metric_judgment_can_fill_values_from_fetched_evidence(self) -> None:
        parsed = ParsedRequest(
            location="전주 객사",
            cuisine="고기집",
            min_rating=3.7,
            min_review_count=30,
            max_price_level=2,
        )

        class DummyTrace:
            def write(self, **kwargs):
                return None

        async def fake_llm(**kwargs):
            return '[{"place_url":"https://place.map.kakao.com/2","place_name":"검증고기","status":"observed","rating":4.1,"review_count":57,"price_level":2,"meets_conditions":true,"reason":"증거 텍스트에서 평점 4.1, 후기 57개, 가격대 2를 확인"}]'

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), patch("react_client.call_llm", side_effect=fake_llm):
            judgments = await run_llm_kakao_metric_judgment(
                metric_observations=[
                    {
                        "place_url": "https://place.map.kakao.com/2",
                        "place_name": "검증고기",
                        "metrics_status": "observed",
                        "rating": None,
                        "review_count": None,
                        "price_level": None,
                        "condition_checks": {"rating": None, "review_count": None, "price_level": None},
                        "evidence_text": "평점 4.1 후기 57개 가격대 ₩₩",
                    }
                ],
                parsed=parsed,
                trace=DummyTrace(),
                messages_count=1,
                use_llm=True,
            )

        self.assertEqual(judgments[0]["rating"], 4.1)
        self.assertEqual(judgments[0]["review_count"], 57)
        self.assertEqual(judgments[0]["price_level"], 2)
        self.assertTrue(judgments[0]["meets_conditions"])

    async def test_enrichment_excludes_missing_rating_and_review_by_default(self) -> None:
        parsed = ParsedRequest(
            location="전주 객사",
            cuisine="일본식라면",
            min_rating=3.7,
            min_review_count=30,
            max_price_level=None,
        )
        candidates = [
            {
                "restaurant_id": "kakao:1",
                "name": "후기없는가게",
                "place_url": "https://place.map.kakao.com/1",
                "score_reasons": [],
            }
        ]

        class FakeClient:
            async def call_tool(self, action):
                class Result:
                    summary = "metrics not found"
                    data = {
                        "status": "ok",
                        "place_url": "https://place.map.kakao.com/1",
                        "place_name": "후기없는가게",
                        "metrics_status": "not_found",
                        "rating": None,
                        "review_count": None,
                        "price_level": None,
                        "condition_checks": {"rating": None, "review_count": None, "price_level": None},
                    }

                return Result()

        class DummyTrace:
            def write(self, **kwargs):
                return None

        enriched, reflection = await enrich_kakao_candidates_with_place_metrics(
            candidates=candidates,
            parsed=parsed,
            public_client=FakeClient(),
            trace=DummyTrace(),
            messages=[],
            use_llm=False,
            enabled=True,
        )

        self.assertEqual(enriched, [])
        self.assertIn("모든 후보", reflection)

    async def test_enrichment_keeps_observed_rating_and_review_without_price_filter(self) -> None:
        parsed = ParsedRequest(
            location="전주 객사",
            cuisine="일본식라면",
            min_rating=3.7,
            min_review_count=30,
            max_price_level=None,
        )
        candidates = [
            {
                "restaurant_id": "kakao:1",
                "name": "검증된가게",
                "place_url": "https://place.map.kakao.com/1",
                "score_reasons": [],
            }
        ]

        class FakeClient:
            async def call_tool(self, action):
                class Result:
                    summary = "metrics observed"
                    data = {
                        "status": "ok",
                        "place_url": "https://place.map.kakao.com/1",
                        "place_name": "검증된가게",
                        "metrics_status": "ok",
                        "rating": 3.8,
                        "review_count": 30,
                        "price_level": None,
                        "condition_checks": {"rating": True, "review_count": True, "price_level": None},
                    }

                return Result()

        class DummyTrace:
            def write(self, **kwargs):
                return None

        enriched, reflection = await enrich_kakao_candidates_with_place_metrics(
            candidates=candidates,
            parsed=parsed,
            public_client=FakeClient(),
            trace=DummyTrace(),
            messages=[],
            use_llm=False,
            enabled=True,
        )

        self.assertEqual(len(enriched), 1)
        self.assertEqual(enriched[0]["rating"], 3.8)
        self.assertEqual(enriched[0]["review_count"], 30)
        self.assertIn("1개 후보", reflection)

    async def test_enrichment_excludes_unchecked_candidates_when_metric_conditions_exist(self) -> None:
        parsed = ParsedRequest(
            location="전주 전북대 신정문",
            cuisine="초밥",
            min_rating=3.7,
            min_review_count=30,
        )
        candidates = [
            {
                "restaurant_id": "kakao:1",
                "name": "검증된초밥",
                "place_url": "https://place.map.kakao.com/1",
                "score_reasons": [],
            },
            {
                "restaurant_id": "kakao:2",
                "name": "미검증일식",
                "place_url": "https://place.map.kakao.com/2",
                "score_reasons": [],
            },
        ]

        class FakeClient:
            async def call_tool(self, action):
                class Result:
                    summary = "metrics observed"
                    data = {
                        "status": "ok",
                        "place_url": "https://place.map.kakao.com/1",
                        "place_name": "검증된초밥",
                        "metrics_status": "ok",
                        "rating": 4.2,
                        "review_count": 40,
                        "price_level": None,
                        "condition_checks": {"rating": True, "review_count": True, "price_level": None},
                    }

                return Result()

        class DummyTrace:
            def write(self, **kwargs):
                return None

        enriched, reflection = await enrich_kakao_candidates_with_place_metrics(
            candidates=candidates,
            parsed=parsed,
            public_client=FakeClient(),
            trace=DummyTrace(),
            messages=[],
            use_llm=False,
            enabled=True,
            max_items=1,
        )

        self.assertEqual([candidate["name"] for candidate in enriched], ["검증된초밥"])
        self.assertIn("미검증일식", reflection)

    async def test_llm_fallback_recommendation_appends_only_when_enabled(self) -> None:
        parsed = ParsedRequest(location="전주 전북대 신정문", cuisine="초밥")

        class DummyTrace:
            def write(self, **kwargs):
                return None

        async def fake_llm(**kwargs):
            return "LLM 참고 추천\n- API 미검증 후보입니다. 전북대 신정문 초밥으로 다시 확인하세요."

        base_answer = "조건을 충족하는 추천 후보를 확보하지 못했습니다."
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}), patch("react_client.call_llm", side_effect=fake_llm):
            answer = await append_llm_fallback_recommendation(
                answer=base_answer,
                query="전북대 신정문 초밥 추천",
                parsed=parsed,
                trace=DummyTrace(),
                messages_count=1,
                use_llm=True,
                data_source="Kakao Local API",
            )

        self.assertIn("LLM 참고 추천", answer)

        disabled_answer = await append_llm_fallback_recommendation(
            answer=base_answer,
            query="전북대 신정문 초밥 추천",
            parsed=parsed,
            trace=DummyTrace(),
            messages_count=1,
            use_llm=False,
            data_source="Kakao Local API",
        )
        self.assertEqual(disabled_answer, base_answer)


if __name__ == "__main__":
    unittest.main()
