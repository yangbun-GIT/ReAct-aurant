import unittest
from argparse import Namespace
from unittest.mock import patch

from env_context_server import _resolve_location as _resolve_weather_location
from gourmet_db_server import rank_restaurants, search_restaurants
from jeonju_gazetteer import JEONJU_SEARCH_AREAS
from public_data_server import (
    _matches_food_query,
    _is_jeonju_restaurant,
    _resolve_search_area,
    _score_public_restaurant,
    _standardize_kakao_place,
    _standardize_restaurant,
    search_kakao_local_places,
    search_tourapi_restaurants,
)
from react_client import (
    ParsedRequest,
    build_public_final_answer,
    build_ranking_policy,
    evaluate_input_guard,
    parse_llm_json,
    parse_user_request,
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

    def test_parse_freeform_jeonju_commercial_area_and_food(self) -> None:
        parsed = parse_user_request("전주 웨리단길 파스타 맛집 추천해줘")

        self.assertEqual(parsed.location, "전주 웨리단길")
        self.assertEqual(parsed.cuisine, "파스타")
        self.assertIn("음식종류=파스타", parsed.extracted_conditions)

    def test_parse_long_jeonju_alias_before_parent_area(self) -> None:
        parsed = parse_user_request("전주 전북대 구정문 소바 맛집 알려줘")

        self.assertEqual(parsed.location, "전주 전북대 구정문")
        self.assertEqual(parsed.cuisine, "소바")

    def test_parse_diverse_food_types_beyond_basic_categories(self) -> None:
        cases = {
            "전주 신시가지 마라탕 맛집 추천": ("전주 효자동", "마라탕"),
            "전주 한옥마을 디저트 맛집 추천": ("전주 한옥마을", "디저트"),
            "전주 송천동 초밥 맛집 추천": ("전주 송천동", "초밥"),
            "전주 웨리단길 파스타 맛집 추천": ("전주 웨리단길", "파스타"),
            "전주 객사 해산물 맛집 추천": ("전주 객사", "해산물"),
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

        self.assertEqual(parsed.location, "전주 효자동")
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
            "신시가지 비오는날 마라탕 추천": "전주 효자동",
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
            ("음식점 > 아시아음식 > 베트남음식", "베트남"),
            ("음식점 > 카페 > 디저트카페", "디저트 카페"),
            ("음식점 > 간식 > 제과,베이커리", "베이커리"),
            ("음식점 > 술집 > 와인바", "바"),
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

    @patch.dict("os.environ", {"KAKAO_REST_API_KEY": ""})
    def test_kakao_local_search_reports_missing_key_as_observation(self) -> None:
        result = search_kakao_local_places(area="전주 신시가지", cuisine="술집", max_distance_m=700)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["source"], "Kakao Local API")
        self.assertIn("KAKAO_REST_API_KEY", result["message"])

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
                }
            ],
            "Kakao Local API 검토 완료",
            data_source_label="Kakao Local API",
        )

        applied_line = next(line for line in answer.splitlines() if line.startswith("적용 조건:"))
        preference_line = next(line for line in answer.splitlines() if line.startswith("사용자 선호 반영:"))
        self.assertNotIn("최소평점", applied_line)
        self.assertNotIn("최소리뷰수", applied_line)
        self.assertNotIn("최대가격대", applied_line)
        self.assertNotIn("리뷰가 좋은 곳", preference_line)
        self.assertIn("미적용 조건:", answer)
        self.assertIn("공식 응답이 평점/리뷰 수/가격대 필드를 제공하지 않아", answer)


if __name__ == "__main__":
    unittest.main()
