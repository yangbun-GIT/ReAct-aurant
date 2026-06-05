import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import web_dashboard


class WebDashboardTests(unittest.TestCase):
    def test_dashboard_html_contains_required_review_surfaces(self) -> None:
        html = web_dashboard.render_dashboard()

        self.assertIn("입력 실행", html)
        self.assertIn("최종 추천", html)
        self.assertIn("Trace 자연어", html)
        self.assertIn("Trace 코드 흐름", html)
        self.assertIn("실행 로그", html)
        self.assertIn("Trace JSONL", html)
        self.assertIn("stderr 출력 없음", html)

    def test_trace_views_expose_natural_language_and_code_flow(self) -> None:
        events = web_dashboard.load_trace_events(Path("sample_outputs/jeonju_trace_sample.jsonl"))
        natural = web_dashboard.build_natural_trace(events)
        code = web_dashboard.build_code_trace(events)

        self.assertTrue(any("도구를 호출" in item["title"] for item in natural))
        self.assertTrue(any("Observation" in item["title"] for item in natural))
        self.assertTrue(any("call_tool" in item["code"] for item in code))
        self.assertTrue(any(item["input"] for item in code))
        self.assertTrue(any(item["observation"] for item in code))

    def test_save_run_record_keeps_each_question_history(self) -> None:
        original_root = web_dashboard.RUNS_ROOT
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                web_dashboard.RUNS_ROOT = Path(temp_dir)
                record = {
                    "run_id": "test_001",
                    "created_at": "2026-06-06T12:00:00",
                    "query": "전주 객사 맛집 추천",
                    "data_source": "local",
                    "llm_mode": "no",
                    "returncode": 0,
                    "trace_events": [{"step": 1}],
                    "final_answer": "최종 추천 결과",
                }

                web_dashboard.save_run_record(record)

                saved = web_dashboard._read_json(Path(temp_dir) / "test_001" / "run.json", {})
                index = web_dashboard.load_run_index()

                self.assertEqual(saved["query"], "전주 객사 맛집 추천")
                self.assertEqual(index[0]["run_id"], "test_001")
                self.assertEqual(index[0]["event_count"], 1)
            finally:
                web_dashboard.RUNS_ROOT = original_root

    def test_run_record_preserves_llm_mode_flag_in_display_command(self) -> None:
        original_root = web_dashboard.RUNS_ROOT

        def fake_run(command, **kwargs):
            trace_path = Path(command[command.index("--trace") + 1])
            trace_path.parent.mkdir(parents=True, exist_ok=True)
            trace_path.write_text(
                '{"step":1,"agent_name":"Coordinator Agent","pattern":"Final Answer","final_answer":"최종 추천 결과"}\n',
                encoding="utf-8",
            )
            return SimpleNamespace(stdout="최종 추천 결과", stderr="", returncode=0)

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                web_dashboard.RUNS_ROOT = Path(temp_dir)
                with patch("web_dashboard.subprocess.run", side_effect=fake_run):
                    record = web_dashboard.run_agent_for_dashboard(
                        query="전주 객사 맛집 추천",
                        data_source="local",
                        llm_mode="no",
                    )

                self.assertIn("--no-llm", record["command"])
                self.assertIn("--trace", record["command"])
                self.assertEqual(record["returncode"], 0)
                self.assertEqual(record["final_answer"], "최종 추천 결과")
            finally:
                web_dashboard.RUNS_ROOT = original_root


if __name__ == "__main__":
    unittest.main()
