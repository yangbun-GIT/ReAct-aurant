import unittest
from argparse import Namespace

from public_data_server import _resolve_search_area, _score_public_restaurant, _standardize_restaurant, search_tourapi_restaurants
from react_client import ParsedRequest, parse_llm_json, parse_user_request, reflect_public_recommendations, resolve_llm_enabled, resolve_query


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

    def test_parse_jeonju_detail_area_request(self) -> None:
        parsed = parse_user_request("전주 송천동에서 친구랑 저녁 먹기 좋은 맛집 추천해줘")

        self.assertEqual(parsed.location, "전주 송천동")
        self.assertEqual(parsed.fallback_location, "전주 객사")
        self.assertIn("지역=전주 송천동", parsed.extracted_conditions)
        self.assertFalse(any(condition.startswith("지역보정=") for condition in parsed.extracted_conditions))

    def test_resolve_query_accepts_positional_natural_language(self) -> None:
        args = Namespace(query=None, natural_query=["전주", "효자동", "한식", "추천"])

        self.assertEqual(resolve_query(args), "전주 효자동 한식 추천")

    def test_resolve_llm_enabled_honors_no_llm_flag(self) -> None:
        args = Namespace(no_llm=True, use_llm=True)

        self.assertFalse(resolve_llm_enabled(args))


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
        self.assertIn("TourAPI는 리뷰 수와 평점을 제공하지 않아", restaurant["source_note"])

    def test_resolve_search_area_supports_jeonju_detail_areas(self) -> None:
        search_area = _resolve_search_area("전주 효자동 맛집")

        self.assertIsNotNone(search_area)
        self.assertEqual(search_area["name"], "효자동")
        self.assertIn("longitude", search_area)

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
        self.assertIn("TourAPI는 리뷰 수와 평점을 제공하지 않아", reflection)


if __name__ == "__main__":
    unittest.main()
