from __future__ import annotations

import argparse
import html
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from datetime import datetime
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent
RUNS_ROOT = ROOT / "logs" / "web_runs"
SESSION_COOKIE = "reactaurant_admin_session"
SESSION_STORE: dict[str, dict[str, Any]] = {}
DEFAULT_QUERY = "전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집을 찾아줘. 너무 비싸지 않고, 리뷰가 좋은 곳 위주로 3곳 추천해줘."
VALID_DATA_SOURCES = {"auto", "public", "local", "kakao"}
VALID_LLM_MODES = {"auto", "use", "no"}


def _load_web_settings() -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    return {
        "admin_username": os.getenv("WEB_ADMIN_USERNAME", "admin").strip() or "admin",
        "admin_password": os.getenv("WEB_ADMIN_PASSWORD", "").strip(),
        "auto_login": os.getenv("WEB_AUTO_LOGIN", "true").strip().lower() in {"1", "true", "yes", "on"},
        "trust_local_proxy": os.getenv("WEB_TRUST_LOCAL_PROXY", "false").strip().lower() in {"1", "true", "yes", "on"},
        "timeout_seconds": int(os.getenv("WEB_AGENT_TIMEOUT_SECONDS", "180")),
    }


WEB_SETTINGS = _load_web_settings()


def _json_default(value: Any) -> str:
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")


def _safe_run_id(value: str) -> str | None:
    if re.fullmatch(r"[0-9A-Za-z_-]+", value or ""):
        return value
    return None


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _short_json(value: Any, max_length: int = 1200) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=_json_default)
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "\n..."


def _compact_value(value: Any, max_length: int = 180) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, default=_json_default)
    else:
        text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "..."


def load_trace_events(trace_path: Path) -> list[dict[str, Any]]:
    if not trace_path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in trace_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"step": len(events) + 1, "raw": line, "parse_error": True})
    return events


def build_natural_trace(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    natural: list[dict[str, Any]] = []
    for event in events:
        step = event.get("step")
        agent = event.get("agent_name", "Agent")
        pattern = event.get("pattern", "Pattern")
        action = event.get("action_name")
        method = event.get("jsonrpc_method")
        thought = event.get("thought_summary")
        observation = event.get("observation")
        final_answer = event.get("final_answer")

        if method == "tools/list":
            tools = observation.get("tools", []) if isinstance(observation, dict) else []
            sentence = f"{agent}가 {event.get('mcp_server')}에서 사용 가능한 도구 목록을 확인했습니다."
            detail = f"확인된 도구: {', '.join(tools)}" if tools else "도구 목록 Observation을 수신했습니다."
        elif method == "tools/call":
            sentence = f"{agent}가 {event.get('mcp_server')}의 `{action}` 도구를 호출했습니다."
            detail = f"도구 입력값: {_compact_value(event.get('action_input', {}), 260)}"
        elif method == "tools/call/result":
            source = str(action or "").replace("Observation:", "")
            summary = observation.get("summary") if isinstance(observation, dict) else None
            sentence = f"{agent}가 `{source}` 도구 실행 결과를 Observation으로 받았습니다."
            detail = summary or _compact_value(observation, 260)
        elif final_answer:
            sentence = f"{agent}가 도구 Observation과 Reflection을 근거로 최종 추천 결과를 생성했습니다."
            detail = _compact_value(final_answer, 260)
        elif event.get("reflection"):
            sentence = f"{agent}가 추천 후보와 예외 상황을 검토했습니다."
            detail = _compact_value(event.get("reflection"), 260)
        else:
            sentence = f"{agent}가 다음 실행 단계를 판단했습니다."
            detail = thought or _compact_value(observation, 260)

        natural.append(
            {
                "step": step,
                "agent": agent,
                "pattern": pattern,
                "title": sentence,
                "detail": detail,
                "thought": thought,
            }
        )
    return natural


def build_code_trace(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    code_flow: list[dict[str, Any]] = []
    for event in events:
        action = event.get("action_name")
        method = event.get("jsonrpc_method")
        if method == "tools/list":
            code = f"await {event.get('mcp_server')}.list_tools()"
        elif method == "tools/call":
            code = f"await {event.get('mcp_server')}.call_tool('{action}', action_input)"
        elif method == "tools/call/result":
            code = f"Observation <- result of {str(action or '').replace('Observation:', '')}"
        elif action == "openai.chat.completions.create":
            code = "await openai.chat.completions.create(...)"
        elif action:
            code = str(action)
        elif event.get("final_answer"):
            code = "final_answer <- build answer from observations"
        else:
            code = "agent_loop.next_step()"

        code_flow.append(
            {
                "step": event.get("step"),
                "agent": event.get("agent_name"),
                "pattern": event.get("pattern"),
                "code": code,
                "input": event.get("action_input"),
                "observation": event.get("observation"),
            }
        )
    return code_flow


def infer_effective_data_source(data_source: str, events: list[dict[str, Any]], final_answer: str = "") -> str:
    actions = [str(event.get("action_name") or "") for event in events]
    used_kakao = any(action == "search_kakao_local_places" for action in actions) or "Kakao Local API" in final_answer
    used_tourapi_action = any(
        action in {"search_tourapi_restaurants", "get_tourapi_restaurant_detail", "rank_tourapi_restaurants"}
        for action in actions
    )
    used_public = used_tourapi_action or (not used_kakao and "TourAPI" in final_answer)
    used_local = any(action in {"search_restaurants", "get_restaurant_detail", "rank_restaurants"} for action in actions)

    if used_kakao and used_public:
        effective = "Kakao Local → TourAPI"
    elif used_kakao:
        effective = "Kakao Local"
    elif used_public and used_local:
        effective = "TourAPI → local fallback"
    elif used_public:
        effective = "TourAPI"
    elif used_local:
        effective = "local sample"
    elif data_source == "public":
        effective = "TourAPI"
    elif data_source == "local":
        effective = "local sample"
    elif data_source == "kakao":
        effective = "Kakao Local"
    else:
        effective = "not resolved"

    return f"{data_source} → {effective}"


def infer_effective_llm_mode(llm_mode: str, events: list[dict[str, Any]]) -> str:
    used_gpt = any(str(event.get("action_name") or "") == "openai.chat.completions.create" for event in events)
    disabled = any(
        event.get("agent_name") == "LLM Planner"
        and isinstance(event.get("observation"), dict)
        and event["observation"].get("llm_enabled") is False
        for event in events
    )
    if used_gpt:
        effective = "GPT"
    elif disabled or llm_mode == "no":
        effective = "rule fallback"
    else:
        effective = "not resolved"
    return f"{llm_mode} → {effective}" if llm_mode == "auto" else f"{llm_mode} → {effective}"


def enrich_run_record(record: dict[str, Any]) -> dict[str, Any]:
    events = record.get("trace_events", [])
    final_answer = str(record.get("final_answer", ""))
    record["effective_data_source"] = record.get("effective_data_source") or infer_effective_data_source(
        str(record.get("data_source", "auto")), events, final_answer
    )
    record["effective_llm_mode"] = record.get("effective_llm_mode") or infer_effective_llm_mode(
        str(record.get("llm_mode", "auto")), events
    )
    return record


def extract_final_answer(stdout: str, events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        answer = event.get("final_answer")
        if isinstance(answer, str) and answer.strip():
            return answer.strip()
    marker = "Trace 저장 위치:"
    if marker in stdout:
        return stdout.split(marker, 1)[0].strip()
    return stdout.strip()


def _index_path() -> Path:
    return RUNS_ROOT / "index.json"


def load_run_index() -> list[dict[str, Any]]:
    return _read_json(_index_path(), [])


def load_enriched_run_index() -> list[dict[str, Any]]:
    enriched_items: list[dict[str, Any]] = []
    for item in load_run_index():
        run_id = _safe_run_id(str(item.get("run_id", "")))
        record_path = RUNS_ROOT / run_id / "run.json" if run_id else None
        if record_path and record_path.exists():
            record = enrich_run_record(_read_json(record_path, {}))
            merged = {**item}
            for key in ["effective_data_source", "effective_llm_mode"]:
                merged[key] = record.get(key)
            enriched_items.append(merged)
        else:
            enriched_items.append(item)
    return enriched_items


def save_run_index(items: list[dict[str, Any]]) -> None:
    _write_json(_index_path(), items[:100])


def save_run_record(record: dict[str, Any]) -> None:
    record = enrich_run_record(record)
    run_dir = RUNS_ROOT / record["run_id"]
    _write_json(run_dir / "run.json", record)
    index = [item for item in load_run_index() if item.get("run_id") != record["run_id"]]
    index.insert(
        0,
        {
            "run_id": record["run_id"],
            "created_at": record["created_at"],
            "query": record["query"],
            "data_source": record["data_source"],
            "effective_data_source": record["effective_data_source"],
            "llm_mode": record["llm_mode"],
            "effective_llm_mode": record["effective_llm_mode"],
            "returncode": record["returncode"],
            "event_count": len(record.get("trace_events", [])),
            "final_answer_preview": _compact_value(record.get("final_answer", ""), 160),
        },
    )
    save_run_index(index)


def _is_inside_directory(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def delete_run_record(run_id: str) -> bool:
    safe_run_id = _safe_run_id(run_id)
    if not safe_run_id:
        raise ValueError("잘못된 run_id입니다.")

    root = RUNS_ROOT.resolve()
    run_dir = (RUNS_ROOT / safe_run_id).resolve()
    if not _is_inside_directory(run_dir, root):
        raise ValueError("삭제할 수 없는 실행 경로입니다.")

    existed = run_dir.exists()
    if existed:
        shutil.rmtree(run_dir)

    save_run_index([item for item in load_run_index() if item.get("run_id") != safe_run_id])
    return existed


def clear_run_records() -> int:
    if not RUNS_ROOT.exists():
        save_run_index([])
        return 0

    root = RUNS_ROOT.resolve()
    removed = 0
    for child in RUNS_ROOT.iterdir():
        resolved = child.resolve()
        if not _is_inside_directory(resolved, root):
            continue
        if child.name == "index.json":
            continue
        if child.is_dir():
            shutil.rmtree(child)
            removed += 1
        elif child.is_file():
            child.unlink()
            removed += 1

    save_run_index([])
    return removed


def run_agent_for_dashboard(query: str, data_source: str, llm_mode: str) -> dict[str, Any]:
    if data_source not in VALID_DATA_SOURCES:
        raise ValueError("지원하지 않는 데이터 소스입니다.")
    if llm_mode not in VALID_LLM_MODES:
        raise ValueError("지원하지 않는 LLM 모드입니다.")
    if not query.strip():
        raise ValueError("질문을 입력해야 합니다.")

    created_at = datetime.now().isoformat(timespec="seconds")
    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(3)}"
    run_dir = RUNS_ROOT / run_id
    trace_path = run_dir / "trace.jsonl"
    command = [
        sys.executable,
        "react_client.py",
        "--query",
        query.strip(),
        "--data-source",
        data_source,
        "--trace",
        str(trace_path),
    ]
    if llm_mode == "use":
        command.append("--use-llm")
    elif llm_mode == "no":
        command.append("--no-llm")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    run_dir.mkdir(parents=True, exist_ok=True)

    timed_out = False
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=WEB_SETTINGS["timeout_seconds"],
        )
        stdout = completed.stdout
        stderr = completed.stderr
        returncode = completed.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        stderr = (stderr + f"\n실행 시간이 {WEB_SETTINGS['timeout_seconds']}초를 초과했습니다.").strip()
        returncode = 124

    trace_events = load_trace_events(trace_path)
    final_answer = extract_final_answer(stdout, trace_events)
    display_command = command.copy()
    try:
        trace_index = display_command.index(str(trace_path))
        display_command[trace_index] = _display_path(trace_path)
    except ValueError:
        pass

    record = {
        "run_id": run_id,
        "created_at": created_at,
        "query": query.strip(),
        "data_source": data_source,
        "llm_mode": llm_mode,
        "returncode": returncode,
        "timed_out": timed_out,
        "command": display_command,
        "stdout": stdout,
        "stderr": stderr,
        "trace_file": _display_path(trace_path),
        "trace_events": trace_events,
        "trace_natural": build_natural_trace(trace_events),
        "trace_code": build_code_trace(trace_events),
        "final_answer": final_answer,
    }
    save_run_record(record)
    return record


def render_dashboard() -> str:
    safe_default_query = html.escape(DEFAULT_QUERY)
    admin_name = html.escape(WEB_SETTINGS["admin_username"])
    auto_login = "켜짐" if WEB_SETTINGS["auto_login"] else "꺼짐"
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ReAct-aurant Admin</title>
  <style>
    :root {{
      --bg: #f7f7f4;
      --surface: #ffffff;
      --surface-soft: #fbf7f1;
      --line: #ece4da;
      --line-strong: #d9cabb;
      --text: #202124;
      --muted: #6b6259;
      --accent: #c2410c;
      --accent-dark: #9a3412;
      --herb: #2f7d4e;
      --herb-dark: #1f5e3b;
      --saffron: #d97706;
      --focus: #2563eb;
      --warn: #9a3412;
      --error: #b91c1c;
      --code: #18181b;
      --code-line: #27272a;
      --shadow: 0 18px 40px rgba(31, 28, 23, .08);
      --shadow-soft: 0 8px 22px rgba(31, 28, 23, .06);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "Segoe UI", Arial, sans-serif;
      line-height: 1.5;
      letter-spacing: 0;
    }}
    header {{
      background: var(--surface);
      border-top: 4px solid var(--accent);
      box-shadow: 0 1px 0 rgba(31, 28, 23, .05);
    }}
    .topbar {{
      max-width: 1440px;
      margin: 0 auto;
      padding: 16px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
    }}
    .brand {{
      display: flex;
      flex-direction: column;
      gap: 2px;
    }}
    h1 {{
      margin: 0;
      font-size: 22px;
      font-weight: 700;
      color: #171412;
    }}
    .subtle {{
      color: var(--muted);
      font-size: 13px;
    }}
    main {{
      max-width: 1440px;
      margin: 0 auto;
      padding: 22px 24px 28px;
      display: grid;
      grid-template-columns: 370px minmax(0, 1fr);
      gap: 18px;
    }}
    section, aside {{
      background: var(--surface);
      border: 0;
      border-radius: 8px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .panel-header {{
      padding: 15px 18px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      background: var(--surface-soft);
      box-shadow: inset 0 -1px rgba(31, 28, 23, .05);
    }}
    h2 {{
      margin: 0;
      font-size: 15px;
      font-weight: 700;
      color: #241c18;
    }}
    .panel-body {{
      padding: 18px;
    }}
    label {{
      display: block;
      margin-bottom: 6px;
      font-weight: 600;
      font-size: 13px;
      color: #3b322b;
    }}
    textarea, select, input {{
      width: 100%;
      border: 1px solid #ded4c8;
      border-radius: 6px;
      padding: 11px 12px;
      font: inherit;
      background: #fff;
      color: var(--text);
    }}
    textarea:focus, select:focus, input:focus {{
      outline: 2px solid rgba(194, 65, 12, .18);
      border-color: var(--accent);
    }}
    textarea {{
      min-height: 128px;
      resize: vertical;
    }}
    .field {{
      margin-bottom: 14px;
    }}
    .controls {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }}
    .toggle-field {{
      margin: 2px 0 14px;
    }}
    .toggle-label {{
      display: flex;
      align-items: center;
      gap: 10px;
      border: 1px solid #d8cfc4;
      background: #fffaf5;
      border-radius: 6px;
      padding: 10px 12px;
      color: var(--text);
      font-weight: 700;
      cursor: pointer;
    }}
    .toggle-label input {{
      width: 18px;
      height: 18px;
      accent-color: var(--herb);
    }}
    .toggle-help {{
      display: block;
      color: var(--muted);
      font-weight: 500;
      font-size: 12px;
      margin-top: 2px;
    }}
    button {{
      border: 1px solid var(--accent);
      background: var(--accent);
      color: #fff;
      border-radius: 6px;
      padding: 11px 14px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      min-height: 42px;
      transition: background .16s ease, border-color .16s ease, transform .16s ease, box-shadow .16s ease;
    }}
    button:hover {{
      background: var(--accent-dark);
      border-color: var(--accent-dark);
      transform: translateY(-1px);
    }}
    button:focus-visible {{
      outline: 3px solid rgba(37, 99, 235, .24);
      outline-offset: 2px;
    }}
    button.secondary {{
      background: #fff;
      color: var(--herb-dark);
      border-color: #9fc6ae;
    }}
    button.secondary:hover {{
      background: #eef7ef;
      border-color: var(--herb);
    }}
    button:disabled {{
      opacity: .58;
      cursor: wait;
      transform: none;
    }}
    .status {{
      padding: 11px 12px;
      border: 0;
      box-shadow: inset 4px 0 var(--herb), var(--shadow-soft);
      border-radius: 6px;
      background: #f7fbf7;
      color: var(--muted);
      font-size: 13px;
      min-height: 42px;
    }}
    .history-list {{
      display: flex;
      flex-direction: column;
      gap: 8px;
      max-height: 520px;
      overflow: auto;
    }}
    .history-item {{
      width: 100%;
      background: #fff;
      color: var(--text);
      border: 0;
      border-radius: 6px;
      box-shadow: var(--shadow-soft);
      display: grid;
      grid-template-columns: minmax(0, 1fr) 64px;
      align-items: stretch;
      min-height: 78px;
      overflow: hidden;
    }}
    .history-item:hover {{
      background: #fff9f5;
      box-shadow: inset 4px 0 var(--accent), var(--shadow-soft);
    }}
    .history-open {{
      border: 0;
      background: transparent;
      color: var(--text);
      text-align: left;
      padding: 12px 14px;
      font-weight: 700;
      min-width: 0;
      display: flex;
      flex-direction: column;
      justify-content: flex-start;
      align-items: stretch;
      gap: 7px;
    }}
    .history-open:hover {{
      background: transparent;
      color: var(--accent-dark);
      transform: none;
    }}
    .delete-run {{
      align-self: stretch;
      border: 0;
      border-radius: 0;
      background: #fff7f7;
      color: var(--error);
      min-width: 64px;
      padding: 8px;
      font-size: 12px;
    }}
    .delete-run:hover {{
      background: #fee2e2;
      color: #991b1b;
      transform: none;
    }}
    button.danger {{
      border-color: #fecaca;
      color: var(--error);
      background: #fff;
      min-height: 34px;
      padding: 7px 10px;
      font-size: 12px;
    }}
    button.danger:hover {{
      background: #fee2e2;
      border-color: #fca5a5;
      color: #991b1b;
    }}
    .history-title {{
      line-height: 1.35;
      display: block;
      max-height: 2.7em;
      overflow: hidden;
      word-break: keep-all;
      overflow-wrap: anywhere;
      flex-shrink: 0;
    }}
    .history-meta {{
      display: grid;
      gap: 0;
      color: var(--muted);
      font-size: 12px;
      margin-top: 4px;
      font-weight: 600;
      min-width: 0;
      flex-shrink: 0;
    }}
    .history-meta span {{
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .workspace {{
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
      gap: 18px;
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 12px;
    }}
    .metric {{
      border: 0;
      border-radius: 6px;
      padding: 12px;
      background: #fff;
      min-height: 72px;
      box-shadow: inset 0 4px var(--accent), var(--shadow-soft);
    }}
    .metric:nth-child(2) {{
      box-shadow: inset 0 4px var(--herb), var(--shadow-soft);
    }}
    .metric:nth-child(3) {{
      box-shadow: inset 0 4px var(--saffron), var(--shadow-soft);
    }}
    .metric:nth-child(4) {{
      box-shadow: inset 0 4px #64748b, var(--shadow-soft);
    }}
    .metric:nth-child(5) {{
      box-shadow: inset 0 4px #7c3aed, var(--shadow-soft);
    }}
    .metric strong {{
      display: block;
      font-size: 18px;
      margin-top: 4px;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }}
    .tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 10px;
      background: var(--surface-soft);
      box-shadow: inset 0 -1px rgba(31, 28, 23, .05);
    }}
    .tab-button {{
      border: 1px solid transparent;
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      min-height: 44px;
      padding: 10px 13px;
      box-shadow: none;
    }}
    .tab-button.active {{
      background: #fff3ec;
      color: var(--accent-dark);
      border-color: transparent;
      box-shadow: inset 0 -3px var(--accent);
    }}
    .tab-button:hover {{
      transform: none;
    }}
    .tab-panel {{
      display: none;
      padding: 18px;
    }}
    .tab-panel.active {{
      display: block;
    }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      background: #fff;
      color: var(--text);
      border: 0;
      border-radius: 6px;
      padding: 16px;
      overflow: auto;
      max-height: 620px;
      font-size: 13px;
      line-height: 1.55;
    }}
    .answer-pre {{
      background: #fffdfb;
      border-color: #ead8c6;
      font-size: 14px;
    }}
    .answer-view {{
      display: grid;
      gap: 14px;
    }}
    .answer-summary {{
      display: grid;
      gap: 8px;
      padding: 14px;
      border-radius: 6px;
      background: #fffdfb;
      box-shadow: var(--shadow-soft);
    }}
    .answer-line {{
      display: grid;
      grid-template-columns: 112px minmax(0, 1fr);
      gap: 10px;
      align-items: start;
      font-size: 14px;
    }}
    .answer-label {{
      color: var(--muted);
      font-weight: 700;
    }}
    .answer-value {{
      color: var(--text);
      word-break: keep-all;
      overflow-wrap: anywhere;
    }}
    .restaurant-cards {{
      display: grid;
      gap: 12px;
    }}
    .restaurant-card {{
      border: 0;
      border-radius: 8px;
      background: #fff;
      padding: 15px;
      display: grid;
      gap: 12px;
      box-shadow: inset 5px 0 var(--accent), var(--shadow-soft);
    }}
    .restaurant-title {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .rank-badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 30px;
      height: 30px;
      border-radius: 999px;
      background: var(--accent);
      color: #fff;
      font-weight: 800;
      flex: 0 0 auto;
    }}
    .restaurant-title h3 {{
      margin: 0;
      font-size: 18px;
      line-height: 1.25;
    }}
    .cuisine-pill {{
      display: inline-flex;
      align-items: center;
      min-height: 26px;
      padding: 3px 9px;
      border-radius: 999px;
      background: #eef7ef;
      color: var(--herb-dark);
      font-size: 12px;
      font-weight: 700;
    }}
    .detail-list {{
      display: grid;
      gap: 8px;
    }}
    .detail-row {{
      display: grid;
      grid-template-columns: 112px minmax(0, 1fr);
      gap: 10px;
      padding: 9px 10px;
      border-radius: 6px;
      background: #fbfaf8;
      font-size: 14px;
    }}
    .detail-key {{
      color: var(--muted);
      font-weight: 700;
    }}
    .detail-value {{
      color: var(--text);
      word-break: keep-all;
      overflow-wrap: anywhere;
    }}
    .reason-chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}
    .reason-chip {{
      display: inline-flex;
      align-items: center;
      min-height: 26px;
      padding: 4px 8px;
      border-radius: 999px;
      background: #fff7ed;
      color: var(--accent-dark);
      font-size: 12px;
      font-weight: 600;
    }}
    .reflection-box {{
      background: #f7fbf7;
      border-radius: 8px;
      padding: 13px 14px;
      color: #244634;
      font-size: 14px;
      box-shadow: inset 5px 0 var(--herb), var(--shadow-soft);
    }}
    .raw-answer {{
      border-radius: 8px;
      background: #fff;
      overflow: hidden;
      box-shadow: var(--shadow-soft);
    }}
    .raw-answer summary {{
      cursor: pointer;
      padding: 11px 14px;
      font-weight: 700;
      color: var(--muted);
      background: var(--surface-soft);
    }}
    .raw-answer pre {{
      border: 0;
      border-radius: 0;
      max-height: 360px;
    }}
    .log-pre, .json-pre, .code-line pre {{
      background: var(--code);
      color: #f8fafc;
      border-color: #27272a;
    }}
    .trace-list {{
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    .trace-row {{
      border-radius: 6px;
      padding: 13px 14px;
      background: #fff;
      box-shadow: inset 4px 0 var(--herb), var(--shadow-soft);
    }}
    .trace-row h3 {{
      margin: 0 0 6px;
      font-size: 14px;
      color: #2f231d;
    }}
    .trace-row p {{
      margin: 4px 0;
      color: var(--muted);
      font-size: 13px;
    }}
    .code-flow {{
      display: grid;
      gap: 10px;
    }}
    .code-line {{
      border-radius: 6px;
      overflow: hidden;
      background: #fff;
      box-shadow: var(--shadow-soft);
    }}
    .code-line code {{
      display: block;
      padding: 10px 12px;
      background: var(--code-line);
      color: #f8fafc;
      font-family: Consolas, "Courier New", monospace;
      font-size: 13px;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .code-line details {{
      padding: 8px 12px 10px;
    }}
    .empty {{
      padding: 28px;
      text-align: center;
      color: var(--muted);
      border-radius: 6px;
      background: var(--surface-soft);
    }}
    .login {{
      max-width: 420px;
      margin: 64px auto;
      padding: 20px;
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}
    @media (max-width: 980px) {{
      main {{
        grid-template-columns: 1fr;
      }}
      .summary-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
    @media (max-width: 560px) {{
      .topbar {{
        flex-direction: column;
        align-items: flex-start;
      }}
      .controls, .summary-grid {{
        grid-template-columns: 1fr;
      }}
      .answer-line, .detail-row {{
        grid-template-columns: 1fr;
        gap: 4px;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="topbar">
      <div class="brand">
        <h1>ReAct-aurant Admin</h1>
        <span class="subtle">관리자: {admin_name} · 로컬 자동 로그인: {auto_login} · 저장 위치: logs/web_runs</span>
      </div>
      <button class="secondary" id="refreshBtn" type="button">새로고침</button>
    </div>
  </header>
  <main>
    <aside>
      <div class="panel-header">
        <h2>입력 실행</h2>
      </div>
      <div class="panel-body">
        <form id="runForm">
          <div class="field">
            <label for="query">질문</label>
            <textarea id="query" name="query">{safe_default_query}</textarea>
          </div>
          <div class="controls">
            <div class="field">
              <label for="dataSource">데이터 소스</label>
              <select id="dataSource" name="dataSource">
                <option value="auto">auto</option>
                <option value="public">public</option>
                <option value="local">local</option>
              </select>
            </div>
            <div class="field">
              <label for="llmMode">LLM 모드</label>
              <select id="llmMode" name="llmMode">
                <option value="auto">auto</option>
                <option value="use">use</option>
                <option value="no">no</option>
              </select>
            </div>
          </div>
          <div class="toggle-field">
            <label class="toggle-label" for="kakaoEnabled">
              <input id="kakaoEnabled" name="kakaoEnabled" type="checkbox">
              <span>
                Kakao Local API 우선 사용
                <span class="toggle-help">활성화하면 음식점 후보와 위치 검색을 Kakao Local API 기준으로 실행합니다.</span>
              </span>
            </label>
          </div>
          <button id="runBtn" type="submit">실행</button>
        </form>
        <div class="field" style="margin-top:14px">
          <div class="status" id="status">대기 중</div>
        </div>
      </div>
      <div class="panel-header">
        <h2>저장된 실행</h2>
        <button class="secondary danger" id="clearHistoryBtn" type="button">전체 삭제</button>
      </div>
      <div class="panel-body">
        <div class="history-list" id="historyList"></div>
      </div>
    </aside>
    <div class="workspace">
      <section>
        <div class="panel-header">
          <h2>실행 요약</h2>
          <span class="subtle" id="selectedRun">선택된 실행 없음</span>
        </div>
        <div class="panel-body">
          <div class="summary-grid">
            <div class="metric"><span class="subtle">상태 코드</span><strong id="metricReturn">-</strong></div>
            <div class="metric"><span class="subtle">Trace 이벤트</span><strong id="metricEvents">-</strong></div>
            <div class="metric"><span class="subtle">도구 호출</span><strong id="metricCalls">-</strong></div>
            <div class="metric"><span class="subtle">데이터 소스</span><strong id="metricSource">-</strong></div>
            <div class="metric"><span class="subtle">LLM 모드</span><strong id="metricLlm">-</strong></div>
          </div>
        </div>
      </section>
      <section>
        <div class="tabs">
          <button class="tab-button active" type="button" data-tab="answer">최종 추천</button>
          <button class="tab-button" type="button" data-tab="natural">Trace 자연어</button>
          <button class="tab-button" type="button" data-tab="code">Trace 코드 흐름</button>
          <button class="tab-button" type="button" data-tab="log">실행 로그</button>
          <button class="tab-button" type="button" data-tab="json">Trace JSONL</button>
        </div>
        <div class="tab-panel active" id="tab-answer"><div class="answer-view" id="finalAnswer"><div class="empty">아직 실행 결과가 없습니다.</div></div></div>
        <div class="tab-panel" id="tab-natural"><div class="trace-list" id="naturalTrace"></div></div>
        <div class="tab-panel" id="tab-code"><div class="code-flow" id="codeTrace"></div></div>
        <div class="tab-panel" id="tab-log"><pre class="log-pre" id="runLog"></pre></div>
        <div class="tab-panel" id="tab-json"><pre class="json-pre" id="jsonTrace"></pre></div>
      </section>
    </div>
  </main>
  <script>
    const state = {{ currentRun: null }};
    const statusEl = document.getElementById('status');
    const historyList = document.getElementById('historyList');
    const runBtn = document.getElementById('runBtn');

    function setStatus(text) {{
      statusEl.textContent = text;
    }}

    function escapeHtml(value) {{
      return String(value ?? '').replace(/[&<>"']/g, ch => ({{
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }}[ch]));
    }}

    function countToolCalls(run) {{
      return (run.trace_events || []).filter(event =>
        event.jsonrpc_method === 'tools/call' && !(event.action_name || '').startsWith('Observation:')
      ).length;
    }}

    function splitLabel(line) {{
      const index = line.indexOf(':');
      if (index > 0 && index <= 16) {{
        return [line.slice(0, index).trim(), line.slice(index + 1).trim()];
      }}
      return ['', line];
    }}

    function parseFinalAnswer(answer) {{
      const lines = String(answer || '').split(/\\r?\\n/);
      const intro = [];
      const cards = [];
      const reflection = [];
      let current = null;
      for (const rawLine of lines) {{
        const line = rawLine.trim();
        if (!line || line === '최종 추천 결과') continue;

        const cardMatch = line.match(/^(\\d+)\\.\\s+(.+?)(?:\\s+\\((.+)\\))?$/);
        if (cardMatch) {{
          if (current) cards.push(current);
          current = {{
            rank: cardMatch[1],
            name: cardMatch[2],
            cuisine: cardMatch[3] || '',
            details: []
          }};
          continue;
        }}

        if (line.startsWith('Reflection:')) {{
          if (current) {{
            cards.push(current);
            current = null;
          }}
          reflection.push(line.replace(/^Reflection:\\s*/, ''));
          continue;
        }}

        if (reflection.length > 0) {{
          reflection.push(line);
        }} else if (current) {{
          current.details.push(line.replace(/^[-*]\\s*/, ''));
        }} else {{
          intro.push(line.replace(/^[-*]\\s*/, ''));
        }}
      }}
      if (current) cards.push(current);
      return {{ intro, cards, reflection: reflection.join(' ') }};
    }}

    function renderDetail(detail) {{
      const [key, value] = splitLabel(detail);
      if (key.includes('점수 근거')) {{
        const chips = value.split(',').map(item => item.trim()).filter(Boolean);
        return `
          <div class="detail-row">
            <span class="detail-key">${{escapeHtml(key)}}</span>
            <span class="detail-value reason-chips">
              ${{chips.map(chip => `<span class="reason-chip">${{escapeHtml(chip)}}</span>`).join('')}}
            </span>
          </div>
        `;
      }}
      return `
        <div class="detail-row">
          <span class="detail-key">${{escapeHtml(key || '근거')}}</span>
          <span class="detail-value">${{escapeHtml(value)}}</span>
        </div>
      `;
    }}

    function renderFinalAnswer(answer) {{
      const target = document.getElementById('finalAnswer');
      const text = String(answer || '').trim();
      if (!text) {{
        target.innerHTML = '<div class="empty">아직 실행 결과가 없습니다.</div>';
        return;
      }}

      const parsed = parseFinalAnswer(text);
      if (parsed.cards.length === 0) {{
        target.innerHTML = `<pre class="answer-pre">${{escapeHtml(text)}}</pre>`;
        return;
      }}

      const summaryHtml = parsed.intro.length
        ? `<div class="answer-summary">
            ${{parsed.intro.map(line => {{
              const [key, value] = splitLabel(line);
              return `<div class="answer-line"><span class="answer-label">${{escapeHtml(key || '정보')}}</span><span class="answer-value">${{escapeHtml(value)}}</span></div>`;
            }}).join('')}}
          </div>`
        : '';

      const cardHtml = parsed.cards.map(card => `
        <article class="restaurant-card">
          <div class="restaurant-title">
            <span class="rank-badge">${{escapeHtml(card.rank)}}</span>
            <h3>${{escapeHtml(card.name)}}</h3>
            ${{card.cuisine ? `<span class="cuisine-pill">${{escapeHtml(card.cuisine)}}</span>` : ''}}
          </div>
          <div class="detail-list">
            ${{card.details.map(renderDetail).join('')}}
          </div>
        </article>
      `).join('');

      const reflectionHtml = parsed.reflection
        ? `<div class="reflection-box"><strong>Reflection</strong><br>${{escapeHtml(parsed.reflection)}}</div>`
        : '';

      target.innerHTML = `
        ${{summaryHtml}}
        <div class="restaurant-cards">${{cardHtml}}</div>
        ${{reflectionHtml}}
        <details class="raw-answer">
          <summary>원문 답변 보기</summary>
          <pre class="answer-pre">${{escapeHtml(text)}}</pre>
        </details>
      `;
    }}

    function activateTab(name) {{
      document.querySelectorAll('.tab-button').forEach(button => {{
        button.classList.toggle('active', button.dataset.tab === name);
      }});
      document.querySelectorAll('.tab-panel').forEach(panel => {{
        panel.classList.toggle('active', panel.id === `tab-${{name}}`);
      }});
    }}

    function renderRun(run) {{
      state.currentRun = run;
      document.getElementById('selectedRun').textContent = run.run_id ? `${{run.run_id}} · ${{run.created_at}}` : '선택된 실행 없음';
      document.getElementById('metricReturn').textContent = run.returncode ?? '-';
      document.getElementById('metricEvents').textContent = (run.trace_events || []).length;
      document.getElementById('metricCalls').textContent = countToolCalls(run);
      document.getElementById('metricSource').textContent = run.effective_data_source || run.data_source || '-';
      document.getElementById('metricLlm').textContent = run.effective_llm_mode || run.llm_mode || '-';
      renderFinalAnswer(run.final_answer || '');
      const stderrText = (run.stderr || '').trim();
      const logSections = [
        '[stdout]',
        run.stdout || ''
      ];
      if (stderrText) {{
        logSections.push('', '[stderr]', run.stderr);
      }} else {{
        logSections.push('', 'stderr 출력 없음: 실행 중 표준 오류로 기록된 내용이 없습니다.');
      }}
      document.getElementById('runLog').textContent = logSections.join('\\n');
      document.getElementById('jsonTrace').textContent = (run.trace_events || []).map(event => JSON.stringify(event, null, 2)).join('\\n');

      const naturalTrace = document.getElementById('naturalTrace');
      naturalTrace.innerHTML = '';
      if (!run.trace_natural || run.trace_natural.length === 0) {{
        naturalTrace.innerHTML = '<div class="empty">Trace 자연어 흐름이 없습니다.</div>';
      }} else {{
        run.trace_natural.forEach(item => {{
          const row = document.createElement('div');
          row.className = 'trace-row';
          row.innerHTML = `
            <h3>Step ${{escapeHtml(item.step)}} · ${{escapeHtml(item.pattern)}}</h3>
            <p><strong>${{escapeHtml(item.agent)}}</strong></p>
            <p>${{escapeHtml(item.title)}}</p>
            <p>${{escapeHtml(item.detail || '')}}</p>
          `;
          naturalTrace.appendChild(row);
        }});
      }}

      const codeTrace = document.getElementById('codeTrace');
      codeTrace.innerHTML = '';
      if (!run.trace_code || run.trace_code.length === 0) {{
        codeTrace.innerHTML = '<div class="empty">Trace 코드 흐름이 없습니다.</div>';
      }} else {{
        run.trace_code.forEach(item => {{
          const row = document.createElement('div');
          row.className = 'code-line';
          row.innerHTML = `
            <code>Step ${{escapeHtml(item.step)}} · ${{escapeHtml(item.code)}}</code>
            <details>
              <summary>입력값과 Observation</summary>
              <pre>${{escapeHtml(JSON.stringify({{ input: item.input, observation: item.observation }}, null, 2))}}</pre>
            </details>
          `;
          codeTrace.appendChild(row);
        }});
      }}
    }}

    async function loadHistory() {{
      const response = await fetch('/api/runs');
      if (!response.ok) throw new Error('실행 이력을 불러오지 못했습니다.');
      const items = await response.json();
      historyList.innerHTML = '';
      if (items.length === 0) {{
        historyList.innerHTML = '<div class="empty">저장된 실행이 없습니다.</div>';
        return;
      }}
      items.forEach(item => {{
        const row = document.createElement('div');
        row.className = 'history-item';
        row.innerHTML = `
          <button class="history-open" type="button">
            <div class="history-title">${{escapeHtml(item.query)}}</div>
            <div class="history-meta">
              <span>${{escapeHtml(item.created_at)}}</span>
            </div>
          </button>
          <button class="delete-run" type="button" aria-label="실행 삭제">삭제</button>
        `;
        row.querySelector('.history-open').addEventListener('click', () => loadRun(item.run_id));
        row.querySelector('.delete-run').addEventListener('click', () => {{
          deleteRun(item.run_id).catch(error => setStatus(error.message));
        }});
        historyList.appendChild(row);
      }});
    }}

    async function loadRun(runId) {{
      const response = await fetch(`/api/runs/${{encodeURIComponent(runId)}}`);
      if (!response.ok) throw new Error('실행 상세를 불러오지 못했습니다.');
      const run = await response.json();
      renderRun(run);
      setStatus(`실행 ${{runId}} 불러옴`);
    }}

    function resetRunView() {{
      state.currentRun = null;
      document.getElementById('selectedRun').textContent = '선택된 실행 없음';
      document.getElementById('metricReturn').textContent = '-';
      document.getElementById('metricEvents').textContent = '-';
      document.getElementById('metricCalls').textContent = '-';
      document.getElementById('metricSource').textContent = '-';
      document.getElementById('metricLlm').textContent = '-';
      renderFinalAnswer('');
      document.getElementById('runLog').textContent = '';
      document.getElementById('jsonTrace').textContent = '';
      document.getElementById('naturalTrace').innerHTML = '<div class="empty">Trace 자연어 흐름이 없습니다.</div>';
      document.getElementById('codeTrace').innerHTML = '<div class="empty">Trace 코드 흐름이 없습니다.</div>';
    }}

    async function deleteRun(runId) {{
      if (!confirm('선택한 실행 기록을 삭제할까요? 로컬 logs/web_runs의 해당 폴더도 삭제됩니다.')) return;
      const response = await fetch(`/api/runs/${{encodeURIComponent(runId)}}`, {{ method: 'DELETE' }});
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || '실행 기록 삭제에 실패했습니다.');
      if (state.currentRun && state.currentRun.run_id === runId) resetRunView();
      await loadHistory();
      setStatus(`실행 기록 삭제 완료: ${{runId}}`);
    }}

    async function clearHistory() {{
      if (!confirm('저장된 모든 실행 기록을 삭제할까요? 로컬 logs/web_runs 내용도 삭제됩니다.')) return;
      const response = await fetch('/api/runs', {{ method: 'DELETE' }});
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || '전체 실행 기록 삭제에 실패했습니다.');
      resetRunView();
      await loadHistory();
      setStatus(`전체 실행 기록 삭제 완료: ${{body.removed}}개`);
    }}

    document.getElementById('runForm').addEventListener('submit', async event => {{
      event.preventDefault();
      runBtn.disabled = true;
      setStatus('Agent 실행 중입니다. MCP 서버 연결과 도구 호출이 끝날 때까지 기다리세요.');
      try {{
        const payload = {{
          query: document.getElementById('query').value,
          data_source: document.getElementById('kakaoEnabled').checked ? 'kakao' : document.getElementById('dataSource').value,
          llm_mode: document.getElementById('llmMode').value
        }};
        const response = await fetch('/api/run', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload)
        }});
        const body = await response.json();
        if (!response.ok) throw new Error(body.error || '실행에 실패했습니다.');
        renderRun(body);
        await loadHistory();
        setStatus(`실행 완료: ${{body.run_id}}`);
      }} catch (error) {{
        setStatus(error.message);
      }} finally {{
        runBtn.disabled = false;
      }}
    }});

    document.querySelectorAll('.tab-button').forEach(button => {{
      button.addEventListener('click', () => activateTab(button.dataset.tab));
    }});
    document.getElementById('refreshBtn').addEventListener('click', loadHistory);
    document.getElementById('clearHistoryBtn').addEventListener('click', () => {{
      clearHistory().catch(error => setStatus(error.message));
    }});

    loadHistory().catch(error => setStatus(error.message));
  </script>
</body>
</html>"""


def render_login() -> str:
    admin_name = html.escape(WEB_SETTINGS["admin_username"])
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ReAct-aurant Login</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #f7f7f4;
      color: #202124;
      font-family: "Segoe UI", Arial, sans-serif;
      letter-spacing: 0;
    }}
    .login {{
      width: min(420px, calc(100vw - 32px));
      background: #fff;
      border: 1px solid #e2ded6;
      border-top: 4px solid #c2410c;
      border-radius: 8px;
      padding: 24px;
      box-shadow: 0 18px 40px rgba(31, 28, 23, .08);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 22px;
    }}
    p {{
      margin: 0 0 18px;
      color: #6b6259;
      font-size: 14px;
    }}
    label {{
      display: block;
      margin-bottom: 12px;
      font-weight: 600;
      font-size: 13px;
    }}
    input {{
      width: 100%;
      margin-top: 6px;
      border: 1px solid #e2ded6;
      border-radius: 6px;
      padding: 11px 12px;
      font: inherit;
    }}
    input:focus {{
      outline: 2px solid rgba(194, 65, 12, .18);
      border-color: #c2410c;
    }}
    button {{
      width: 100%;
      border: 1px solid #c2410c;
      background: #c2410c;
      color: #fff;
      border-radius: 6px;
      padding: 11px 14px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      min-height: 42px;
    }}
    button:hover {{
      background: #9a3412;
      border-color: #9a3412;
    }}
  </style>
</head>
<body>
  <main class="login">
    <h1>ReAct-aurant Admin</h1>
    <p>로컬 자동 로그인이 꺼져 있습니다. 관리자 계정 하나만 사용할 수 있습니다.</p>
    <form method="post" action="/login">
      <label>아이디 <input name="username" value="{admin_name}"></label>
      <label>비밀번호 <input name="password" type="password"></label>
      <button type="submit">로그인</button>
    </form>
  </main>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "ReActaurantDashboard/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _is_local_request(self) -> bool:
        client_ip = self.client_address[0]
        if client_ip in {"127.0.0.1", "::1"}:
            return True
        if WEB_SETTINGS.get("trust_local_proxy") and (
            client_ip.startswith("172.") or client_ip.startswith("10.") or client_ip.startswith("192.168.")
        ):
            return True
        return False

    def _session_id(self) -> str | None:
        cookie = SimpleCookie(self.headers.get("Cookie"))
        morsel = cookie.get(SESSION_COOKIE)
        if morsel and morsel.value in SESSION_STORE:
            return morsel.value
        return None

    def _create_session(self) -> str:
        session_id = secrets.token_urlsafe(24)
        SESSION_STORE[session_id] = {
            "username": WEB_SETTINGS["admin_username"],
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        return session_id

    def _authenticated(self) -> bool:
        if self._session_id():
            return True
        return bool(WEB_SETTINGS["auto_login"] and self._is_local_request())

    def _send(self, status: int, body: bytes, content_type: str, extra_headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _send_html(self, status: int, payload: str, set_session: bool = False) -> None:
        headers = None
        if set_session:
            session_id = self._session_id() or self._create_session()
            headers = {"Set-Cookie": f"{SESSION_COOKIE}={session_id}; HttpOnly; SameSite=Lax; Path=/"}
        self._send(status, payload.encode("utf-8"), "text/html; charset=utf-8", headers)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(raw or "{}")

    def do_GET(self) -> None:
        if self.path in {"/", "/app"}:
            if not self._authenticated():
                self._send_html(HTTPStatus.OK, render_login())
                return
            self._send_html(HTTPStatus.OK, render_dashboard(), set_session=True)
            return

        if self.path == "/api/session":
            self._send_json(
                HTTPStatus.OK,
                {
                    "authenticated": self._authenticated(),
                    "username": WEB_SETTINGS["admin_username"] if self._authenticated() else None,
                    "auto_login": WEB_SETTINGS["auto_login"],
                },
            )
            return

        if self.path == "/api/runs":
            if not self._authenticated():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "인증이 필요합니다."})
                return
            self._send_json(HTTPStatus.OK, load_enriched_run_index())
            return

        match = re.fullmatch(r"/api/runs/([^/?#]+)", self.path)
        if match:
            if not self._authenticated():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "인증이 필요합니다."})
                return
            run_id = _safe_run_id(match.group(1))
            if not run_id:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "잘못된 run_id입니다."})
                return
            record_path = RUNS_ROOT / run_id / "run.json"
            if not record_path.exists():
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "실행 기록을 찾을 수 없습니다."})
                return
            self._send_json(HTTPStatus.OK, enrich_run_record(_read_json(record_path, {})))
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "찾을 수 없는 경로입니다."})

    def do_POST(self) -> None:
        if self.path == "/login":
            form_raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0)).decode("utf-8")
            from urllib.parse import parse_qs

            form = parse_qs(form_raw)
            username = form.get("username", [""])[0]
            password = form.get("password", [""])[0]
            expected_password = WEB_SETTINGS["admin_password"]
            if username == WEB_SETTINGS["admin_username"] and expected_password and secrets.compare_digest(password, expected_password):
                self._send(
                    HTTPStatus.FOUND,
                    b"",
                    "text/plain; charset=utf-8",
                    {
                        "Location": "/app",
                        "Set-Cookie": f"{SESSION_COOKIE}={self._create_session()}; HttpOnly; SameSite=Lax; Path=/",
                    },
                )
                return
            self._send_html(HTTPStatus.UNAUTHORIZED, render_login())
            return

        if self.path == "/api/run":
            if not self._authenticated():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "인증이 필요합니다."})
                return
            try:
                payload = self._read_json_body()
                record = run_agent_for_dashboard(
                    query=str(payload.get("query", "")),
                    data_source=str(payload.get("data_source", "auto")),
                    llm_mode=str(payload.get("llm_mode", "auto")),
                )
            except Exception as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send_json(HTTPStatus.OK, record)
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "찾을 수 없는 경로입니다."})

    def do_DELETE(self) -> None:
        if not self._authenticated():
            self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "인증이 필요합니다."})
            return

        if self.path == "/api/runs":
            removed = clear_run_records()
            self._send_json(HTTPStatus.OK, {"status": "ok", "removed": removed})
            return

        match = re.fullmatch(r"/api/runs/([^/?#]+)", self.path)
        if match:
            run_id = _safe_run_id(match.group(1))
            if not run_id:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "잘못된 run_id입니다."})
                return
            try:
                existed = delete_run_record(run_id)
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            if not existed:
                self._send_json(
                    HTTPStatus.NOT_FOUND,
                    {"status": "error", "deleted": False, "run_id": run_id, "error": "실행 기록을 찾을 수 없습니다."},
                )
                return
            self._send_json(HTTPStatus.OK, {"status": "ok", "deleted": True, "run_id": run_id})
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "찾을 수 없는 경로입니다."})


def main() -> None:
    parser = argparse.ArgumentParser(description="ReAct-aurant 로컬 관리자 웹 대시보드")
    parser.add_argument("--host", default=os.getenv("WEB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("WEB_PORT", "0")))
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    actual_host, actual_port = server.server_address[:2]
    print(f"ReAct-aurant Admin: http://{actual_host}:{actual_port}/app")
    print("종료: Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n서버를 종료합니다.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
