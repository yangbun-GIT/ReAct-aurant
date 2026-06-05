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
        self.assertIn("LLM 모드", html)
        self.assertIn("stderr 출력 없음", html)
        self.assertIn("answer-pre", html)
        self.assertIn("answer-view", html)
        self.assertIn("restaurant-card", html)
        self.assertIn("전체 삭제", html)
        self.assertIn("deleteRun", html)
        self.assertIn("log-pre", html)
        self.assertIn("--accent: #c2410c", html)
        self.assertIn("--herb: #2f7d4e", html)

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
                    "effective_data_source": "local → local sample",
                    "effective_llm_mode": "no → rule fallback",
                    "returncode": 0,
                    "trace_events": [{"step": 1}],
                    "final_answer": "최종 추천 결과",
                }

                web_dashboard.save_run_record(record)

                saved = web_dashboard._read_json(Path(temp_dir) / "test_001" / "run.json", {})
                index = web_dashboard.load_run_index()

                self.assertEqual(saved["query"], "전주 객사 맛집 추천")
                self.assertEqual(index[0]["run_id"], "test_001")
                self.assertEqual(index[0]["effective_data_source"], "local → local sample")
                self.assertEqual(index[0]["effective_llm_mode"], "no → rule fallback")
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
                self.assertEqual(record["effective_llm_mode"], "no → rule fallback")
            finally:
                web_dashboard.RUNS_ROOT = original_root

    def test_docker_config_runs_dashboard_with_fixed_container_port(self) -> None:
        dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
        compose = Path("docker-compose.yml").read_text(encoding="utf-8")
        dockerignore = Path(".dockerignore").read_text(encoding="utf-8")

        self.assertIn("python:3.13-slim", dockerfile)
        self.assertIn('CMD ["python", "web_dashboard.py", "--host", "0.0.0.0", "--port", "8765"]', dockerfile)
        self.assertIn("127.0.0.1:${WEB_DOCKER_PORT:-18765}:8765", compose)
        self.assertIn('WEB_TRUST_LOCAL_PROXY: "true"', compose)
        self.assertIn("TOUR_API_SERVICE_KEY: ${TOUR_API_SERVICE_KEY:-}", compose)
        self.assertIn("OPENAI_API_KEY: ${OPENAI_API_KEY:-}", compose)
        self.assertIn(".env", dockerignore)
        self.assertIn("logs/", dockerignore)

    def test_docker_local_proxy_can_use_auto_login_when_explicitly_trusted(self) -> None:
        original_settings = web_dashboard.WEB_SETTINGS
        try:
            web_dashboard.WEB_SETTINGS = {**original_settings, "trust_local_proxy": True}
            handler = SimpleNamespace(client_address=("172.17.0.1", 51234))

            self.assertTrue(web_dashboard.DashboardHandler._is_local_request(handler))
        finally:
            web_dashboard.WEB_SETTINGS = original_settings

    def test_delete_run_record_removes_directory_and_index_entry(self) -> None:
        original_root = web_dashboard.RUNS_ROOT
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                web_dashboard.RUNS_ROOT = Path(temp_dir)
                run_dir = Path(temp_dir) / "run_001"
                run_dir.mkdir()
                (run_dir / "run.json").write_text("{}", encoding="utf-8")
                web_dashboard.save_run_index([{"run_id": "run_001"}, {"run_id": "run_002"}])

                deleted = web_dashboard.delete_run_record("run_001")

                self.assertTrue(deleted)
                self.assertFalse(run_dir.exists())
                self.assertEqual(web_dashboard.load_run_index(), [{"run_id": "run_002"}])
            finally:
                web_dashboard.RUNS_ROOT = original_root

    def test_clear_run_records_removes_local_run_directories(self) -> None:
        original_root = web_dashboard.RUNS_ROOT
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                web_dashboard.RUNS_ROOT = Path(temp_dir)
                for run_id in ["run_001", "run_002"]:
                    run_dir = Path(temp_dir) / run_id
                    run_dir.mkdir()
                    (run_dir / "run.json").write_text("{}", encoding="utf-8")
                web_dashboard.save_run_index([{"run_id": "run_001"}, {"run_id": "run_002"}])

                removed = web_dashboard.clear_run_records()

                self.assertEqual(removed, 2)
                self.assertEqual(web_dashboard.load_run_index(), [])
                self.assertFalse((Path(temp_dir) / "run_001").exists())
                self.assertFalse((Path(temp_dir) / "run_002").exists())
            finally:
                web_dashboard.RUNS_ROOT = original_root


if __name__ == "__main__":
    unittest.main()
