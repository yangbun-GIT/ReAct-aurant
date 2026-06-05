import unittest
from argparse import Namespace

from jeonju_gazetteer import JEONJU_SEARCH_AREAS
from public_data_server import (
    _matches_food_query,
    _is_jeonju_restaurant,
    _resolve_search_area,
    _score_public_restaurant,
    _standardize_restaurant,
    search_tourapi_restaurants,
)
from react_client import (
    ParsedRequest,
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

    def test_parse_meal_time_as_purpose_not_cuisine(self) -> None:
        parsed = parse_user_request("전주 중동 점심 맛집 추천")

        self.assertEqual(parsed.location, "전주 혁신동")
        self.assertIsNone(parsed.cuisine)
        self.assertIn("점심", parsed.purpose)

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
            },
        )

        self.assertGreater(score, 40)
        self.assertIn("전주 주소 일치", reasons)
        self.assertIn("한식 조건 일치", reasons)

    def test_public_search_rejects_non_jeonju_without_network(self) -> None:
        result = search_tourapi_restaurants(area="서울 홍대", use_cache=False)

        self.assertEqual(result["status"], "error")
        self.assertIn("전주", result["message"])

    def test_public_filter_rejects_non_jeonju_addresses(self) -> None:
        self.assertTrue(_is_jeonju_restaurant({"address": "전북특별자치도 전주시 덕진구 중동로 1"}))
        self.assertFalse(_is_jeonju_restaurant({"address": "전북특별자치도 완주군 이서면 안전로 1"}))


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


if __name__ == "__main__":
    unittest.main()
