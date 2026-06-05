import json
import unittest
from pathlib import Path


TRACE_PATH = Path("sample_outputs/jeonju_trace_sample.jsonl")


def _load_trace_events() -> list[dict]:
    return [json.loads(line) for line in TRACE_PATH.read_text(encoding="utf-8").splitlines()]


class AgenticPatternTraceTests(unittest.TestCase):
    def test_sample_trace_contains_required_agentic_patterns(self) -> None:
        events = _load_trace_events()
        patterns = {event.get("pattern") for event in events}

        self.assertIn("ReAct Pattern", patterns)
        self.assertIn("Plan-and-Solve Pattern", patterns)
        self.assertIn("Tool Use Pattern", patterns)
        self.assertIn("Reflection Pattern", patterns)
        self.assertIn("Memory Pattern", patterns)
        self.assertIn("Final Answer", patterns)

    def test_react_loop_records_action_and_observation_before_final_answer(self) -> None:
        events = _load_trace_events()
        actions = {event.get("action_name"): event.get("step") for event in events}

        self.assertLess(actions["search_tourapi_restaurants"], actions["Observation:search_tourapi_restaurants"])
        self.assertLess(actions["rank_tourapi_restaurants"], actions["Observation:rank_tourapi_restaurants"])

        final_step = max(event["step"] for event in events if event.get("pattern") == "Final Answer")
        self.assertLess(actions["Observation:rank_tourapi_restaurants"], final_step)

    def test_plan_tool_memory_and_reflection_happen_in_order(self) -> None:
        events = _load_trace_events()
        first_step_by_pattern = {}
        for event in events:
            first_step_by_pattern.setdefault(event.get("pattern"), event["step"])

        self.assertLess(first_step_by_pattern["Plan-and-Solve Pattern"], first_step_by_pattern["ReAct Pattern"])
        self.assertLess(first_step_by_pattern["ReAct Pattern"], first_step_by_pattern["Reflection Pattern"])
        self.assertLess(first_step_by_pattern["Reflection Pattern"], first_step_by_pattern["Final Answer"])

        action_names = {event.get("action_name") for event in events}
        self.assertIn("tools/list", action_names)
        self.assertIn("get_user_profile", action_names)
        self.assertIn("remember_preference", action_names)

    def test_final_answer_preserves_data_limitations(self) -> None:
        events = _load_trace_events()
        final_answers = [event["final_answer"] for event in events if event.get("final_answer")]

        self.assertTrue(final_answers)
        self.assertIn("TourAPI는 평점, 리뷰 수, 가격대를 제공하지 않아", final_answers[-1])
        self.assertIn("평점/리뷰/가격대", final_answers[-1])

    def test_react_agent_client_loop_covers_required_stage_three_flow(self) -> None:
        events = _load_trace_events()
        actions = {event.get("action_name"): event.get("step") for event in events}

        parsed_event = next(event for event in events if event.get("agent_name") == "Context Specialist Agent" and event.get("pattern") == "Plan-and-Solve Pattern")
        self.assertIn("location", parsed_event["observation"])
        self.assertIn("extracted_conditions", parsed_event["observation"])

        self.assertIn("select_tools", actions)
        selected_event = next(event for event in events if event.get("action_name") == "select_tools")
        selected_tools = selected_event["observation"]["selected_tools"]
        self.assertTrue(any("search_tourapi_restaurants" in item["tools"] for item in selected_tools))

        self.assertLess(actions["select_tools"], actions["search_tourapi_restaurants"])
        self.assertLess(actions["search_tourapi_restaurants"], actions["Observation:search_tourapi_restaurants"])
        self.assertLess(actions["Observation:search_tourapi_restaurants"], actions["get_tourapi_restaurant_detail"])
        self.assertLess(actions["get_tourapi_restaurant_detail"], actions["rank_tourapi_restaurants"])
        self.assertLess(actions["rank_tourapi_restaurants"], actions["Observation:rank_tourapi_restaurants"])

        reflection_step = min(event["step"] for event in events if event.get("pattern") == "Reflection Pattern")
        final_step = max(event["step"] for event in events if event.get("pattern") == "Final Answer")
        self.assertLess(actions["Observation:rank_tourapi_restaurants"], reflection_step)
        self.assertLess(reflection_step, final_step)


if __name__ == "__main__":
    unittest.main()
