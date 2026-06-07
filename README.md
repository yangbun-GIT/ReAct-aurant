# ReAct-aurant

전주시 맛집 추천 AI Agent 프로젝트입니다. 사용자의 자연어 요청을 분석하고, MCP 도구로 지역/날씨/장소 후보/API 정보를 수집한 뒤 ReAct 흐름으로 최종 추천을 생성합니다.

## 제출 파일

| 항목 | 파일 |
| --- | --- |
| GitHub repo URL | `REPOSITORY_URL.txt` |
| 실행 환경 | `requirements.txt`, `EXECUTION_ENVIRONMENT.md` |
| 프로젝트 설명 | `README.md` |
| 실행 로그/Trace 예시 | `sample_outputs/jeonju_run_log.md`, `sample_outputs/jeonju_trace_sample.jsonl` |
| 패턴/Trace/API 설명 | `SUBMISSION_GUIDE.md` |

`.env`, `.venv`, `__pycache__`, `node_modules`, `logs`, `data/cache`, `docs` 등 제출에 필요 없거나 API Key가 포함될 수 있는 파일은 Git 추적에서 제외합니다.

## 실행 준비

Python 3.11 이상에서 실행할 수 있습니다. 개발과 검증은 Python 3.13 환경에서 진행했습니다.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
copy .env.example .env
```

`.env`에는 필요한 API Key만 로컬에서 입력합니다. 이 파일은 GitHub에 올리지 않습니다.

```env
OPENAI_API_KEY=
KAKAO_REST_API_KEY=
TOUR_API_SERVICE_KEY=
```

## CLI 실행

Kakao Local API 기반 추천:

```powershell
.\.venv\Scripts\python react_client.py "전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집을 찾아줘. 너무 비싸지 않고, 리뷰가 좋은 곳 위주로 3곳 추천해줘." --data-source kakao --trace logs\trace_required.jsonl
```

비용을 줄이는 TourAPI/규칙 기반 실행:

```powershell
.\.venv\Scripts\python react_client.py "전주 객사 한식 맛집 추천" --data-source tourapi --no-llm --trace logs\trace_no_llm.jsonl
```

## 웹 대시보드 실행

Docker 사용을 권장합니다.

```powershell
docker compose up --build
```

접속 주소:

```text
http://127.0.0.1:18765/app
```

웹 대시보드에서는 질문 입력, 최종 추천, 자연어 Trace, 코드 흐름 Trace, 실행 로그, JSONL Trace를 확인할 수 있습니다. 실행 결과는 `logs/web_runs`에 저장되며 GitHub에는 올라가지 않습니다.

## 핵심 구조

| 파일 | 역할 |
| --- | --- |
| `react_client.py` | ReAct Agent 실행 루프, 조건 분석, 도구 호출, 추천 생성 |
| `public_data_server.py` | Kakao Local API, TourAPI MCP 도구 |
| `gourmet_db_server.py` | 후보 검색/상세 조회/랭킹 MCP 도구 |
| `env_context_server.py` | 날씨, 사용자 선호, 메모리 MCP 도구 |
| `jeonju_gazetteer.py` | 전주시 세부 지역/별칭 인식 |
| `web_dashboard.py` | 로컬 관리자 대시보드 |
| `tests/` | 핵심 동작, Agentic Pattern, 웹 대시보드 테스트 |

## Agentic Design Pattern

적용 패턴은 ReAct, Tool Use, Plan-and-Solve, Reflection, Memory입니다. 자세한 설명은 `SUBMISSION_GUIDE.md`에 정리했습니다.

## 외부 API

- Kakao Local API: 음식점/카페/술집 등 장소 검색, 주소, 거리, 전화번호, 장소 링크 확인
- Kakao 장소 페이지/패널 보강: 관측 가능한 평점, 후기 수, 가격대만 추출하고 없는 값은 생성하지 않음
- TourAPI KorService2: 무료 공공데이터 기반 전주시 음식점 후보 조회
- OpenAI API: 요청 분석, 계획, Reflection, 최종 답변 생성
- Open-Meteo: API Key 없이 전주 날씨 조회

API 설정 방법은 `SUBMISSION_GUIDE.md`의 `외부 API 사용 방법` 섹션을 참고합니다.

## 검증

```powershell
python -m unittest discover -s tests
python -m py_compile react_client.py public_data_server.py gourmet_db_server.py env_context_server.py web_dashboard.py
```
