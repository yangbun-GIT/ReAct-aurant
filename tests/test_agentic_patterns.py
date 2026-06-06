import json
import unittest
from pathlib import Path


TRACE_PATH = Path("sample_outputs/jeonju_trace_sample.jsonl")
REQUIRED_SCENARIO_QUERY = "전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집을 찾아줘. 너무 비싸지 않고, 리뷰가 좋은 곳 위주로 3곳 추천해줘."
MCP_SERVER_FILES = [
    Path("env_context_server.py"),
    Path("gourmet_db_server.py"),
    Path("public_data_server.py"),
]


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

    def test_project_uses_real_mcp_sdk_and_multiple_stdio_servers(self) -> None:
        client_source = Path("react_client.py").read_text(encoding="utf-8")

        self.assertIn("from mcp import ClientSession, StdioServerParameters", client_source)
        self.assertIn("from mcp.client.stdio import stdio_client", client_source)
        self.assertGreaterEqual(client_source.count("StdioServerParameters("), 2)
        self.assertGreaterEqual(client_source.count("ClientSession("), 2)

        for server_file in MCP_SERVER_FILES:
            with self.subTest(server_file=str(server_file)):
                server_source = server_file.read_text(encoding="utf-8")
                self.assertIn("from mcp.server.fastmcp import FastMCP", server_source)
                self.assertIn("FastMCP(", server_source)
                self.assertIn('@mcp.tool()', server_source)
                self.assertIn('mcp.run("stdio")', server_source)

    def test_sample_trace_lists_and_calls_multiple_mcp_servers(self) -> None:
        events = _load_trace_events()
        listed_servers = {
            event.get("mcp_server")
            for event in events
            if event.get("jsonrpc_method") == "tools/list" and event.get("mcp_server")
        }
        called_servers = {
            event.get("mcp_server")
            for event in events
            if event.get("jsonrpc_method") == "tools/call" and event.get("mcp_server")
        }

        self.assertGreaterEqual(len(listed_servers), 2)
        self.assertGreaterEqual(len(called_servers), 2)
        self.assertIn("env_context_server.py", listed_servers)
        self.assertIn("gourmet_db_server.py", listed_servers)
        self.assertIn("public_data_server.py", listed_servers)
        self.assertIn("env_context_server.py", called_servers)
        self.assertIn("public_data_server.py", called_servers)

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

    def test_required_execution_scenario_trace_exposes_submission_fields(self) -> None:
        events = _load_trace_events()
        final_answers = [event["final_answer"] for event in events if event.get("final_answer")]

        self.assertTrue(final_answers)
        self.assertIn(REQUIRED_SCENARIO_QUERY, final_answers[-1])
        self.assertTrue(any(event.get("thought_summary") for event in events))

        tool_call_events = [
            event
            for event in events
            if event.get("jsonrpc_method") == "tools/call" and not event.get("action_name", "").startswith("Observation:")
        ]
        tool_result_events = [
            event
            for event in events
            if event.get("jsonrpc_method") == "tools/call/result" and event.get("observation")
        ]

        self.assertTrue(tool_call_events)
        self.assertTrue(tool_result_events)
        self.assertTrue(all("action_input" in event for event in tool_call_events))

        called_tools = {event["action_name"] for event in tool_call_events}
        observed_tools = {event["action_name"].replace("Observation:", "") for event in tool_result_events}
        required_tools = {
            "get_weather_context",
            "get_user_profile",
            "remember_preference",
            "search_tourapi_restaurants",
            "rank_tourapi_restaurants",
        }

        self.assertTrue(required_tools.issubset(called_tools))
        self.assertTrue(required_tools.issubset(observed_tools))

        search_event = next(event for event in tool_call_events if event["action_name"] == "search_tourapi_restaurants")
        self.assertEqual(search_event["action_input"]["area"], "전주 객사")
        self.assertEqual(search_event["action_input"]["max_price_level"], 2)
        self.assertEqual(search_event["action_input"]["min_rating"], 4.2)
        self.assertEqual(search_event["action_input"]["min_review_count"], 50)
        self.assertEqual(search_event["action_input"]["max_distance_m"], 1000)


if __name__ == "__main__":
    unittest.main()
