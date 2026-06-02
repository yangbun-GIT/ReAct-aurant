# ReAct-aurant

`ReAct-aurant`는 OSS 과제4 제출을 위한 Python 기반 맛집 추천 AI Agent 프로젝트입니다.

사용자의 자연어 요청을 분석한 뒤, 2개의 MCP 서버를 도구처럼 호출해 환경 정보, 사용자 선호도, 로컬 맛집 데이터셋을 수집합니다. 이후 ReAct 흐름으로 검색, 정렬, 검토, 최종 추천을 수행합니다.

## 구현 요약

- 비용 발생을 막기 위해 맛집 검색 외부 API는 기본 구현에서 사용하지 않습니다.
- 맛집 후보는 로컬 샘플 데이터셋을 사용합니다.
- 날씨는 API key가 필요 없는 Open-Meteo를 사용하고, 호출 실패 시 mock 날씨로 대체합니다.
- GPT/OpenAI API는 선택 사항입니다. 기본 실행은 `--use-llm`을 주지 않으므로 API 비용이 발생하지 않습니다.
- MCP 서버는 공식 오픈소스 MCP Python SDK(`mcp`)로 구현했습니다.

## 프로젝트 구조

```text
env_context_server.py                # 날씨, 사용자 선호도, 메모리 MCP 서버
gourmet_db_server.py                 # 맛집 검색, 상세 조회, 랭킹 MCP 서버
react_client.py                      # ReAct Agent 실행 클라이언트
requirements.txt                     # Python 실행 환경
.env.example                         # 환경 변수 예시, 실제 key 없음
sample_outputs/jeonju_run_log.md     # 대표 실행 로그
sample_outputs/jeonju_trace_sample.jsonl # ReAct 도구 호출 trace 샘플
README.md                            # 실행 및 제출 문서
```

## 설치

Python 3.11 이상에서 실행할 수 있습니다. 개발 및 검증은 Python 3.13 가상환경에서 진행했습니다.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 환경 변수

기본 실행에는 API key가 필요하지 않습니다.

`.env`가 필요하면 아래처럼 예시 파일을 복사한 뒤 로컬에서만 값을 입력합니다. `.env`는 `.gitignore`에 의해 GitHub에 업로드되지 않습니다.

```powershell
copy .env.example .env
```

선택 환경 변수:

- `OPENAI_API_KEY`: `--use-llm` 옵션으로 최종 문장 다듬기를 사용할 때만 필요합니다.
- `OPENAI_BASE_URL`: OpenAI 또는 OpenAI 호환 API base URL입니다.
- `OPENAI_MODEL`: 선택 LLM 모델명입니다.
- `KAKAO_REST_API_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `GOOGLE_PLACES_API_KEY`: 외부 맛집 API 실험용 자리만 마련했습니다. 기본 구현에서는 사용하지 않습니다.

## 실행

대표 과제 요청:

```powershell
python react_client.py --query "전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집을 찾아줘. 너무 비싸지 않고, 리뷰가 좋은 곳 위주로 3곳 추천해줘." --trace logs/trace_jeonju.jsonl
```

기본 실행은 LLM API를 호출하지 않습니다. OpenAI API로 최종 문장을 다듬고 싶을 때만 아래처럼 실행합니다.

```powershell
python react_client.py --use-llm
```

## MCP 서버와 도구

`env_context_server.py`

- `get_weather_context(location)`: Open-Meteo 또는 mock 기반 날씨와 음식 힌트를 반환합니다.
- `get_user_profile(user_id)`: 과제용 사용자 선호 프로필을 반환합니다.
- `remember_preference(user_id, preference_note)`: 현재 요청을 단기 메모리에 저장합니다.

`gourmet_db_server.py`

- `search_restaurants(...)`: 지역, 음식 종류, 가격대, 평점, 리뷰 수, 거리, 목적 조건으로 후보를 검색합니다.
- `rank_restaurants(candidate_ids, ranking_policy)`: 후보를 평점, 리뷰 수, 가격, 거리, 목적 적합성, 날씨 힌트로 정렬합니다.
- `get_restaurant_detail(restaurant_id)`: 최종 답변 근거 보강용 상세 정보를 조회합니다.

## Agentic Design Pattern

- Plan-and-Solve Pattern: 요청을 지역, 목적, 가격, 리뷰, 평점 조건으로 구조화한 뒤 실행 단계를 나눕니다.
- Tool Use Pattern: MCP `tools/list`, `tools/call`로 서버 도구를 발견하고 호출합니다.
- ReAct Pattern: `Thought -> Action -> Observation` 형태로 맛집 검색, 정렬, 상세 조회를 반복합니다.
- Reflection Pattern: 후보가 없거나 미지원 지역이 들어오면 Observation을 검토하고 조건 완화 또는 기본 지역 대체를 수행합니다.
- Memory Pattern: 사용자 선호 프로필을 조회하고 현재 요청을 단기 메모리에 저장합니다.
- Multi-Agent 구조: Coordinator Agent, Context Specialist Agent, Culinary Finder Agent, Reflection Reviewer 역할을 분리했습니다.

## ReAct 도구 호출 Trace

실행 시 `--trace`로 JSONL trace를 저장합니다. trace에는 다음 정보가 포함됩니다.

- agent name
- pattern
- thought summary
- MCP server
- JSON-RPC method(`tools/list`, `tools/call`, `tools/call/result`)
- action input
- observation
- reflection
- final answer

대표 trace 샘플은 `sample_outputs/jeonju_trace_sample.jsonl`에 포함했습니다.

## 실행 로그

대표 실행 로그는 `sample_outputs/jeonju_run_log.md`에 포함했습니다.

검증한 추가 케이스:

- 미지원 지역 입력: 도구가 error Observation을 반환하고 Reflection 단계에서 `전주 객사`로 대체합니다.
- 과도하게 엄격한 조건: 후보 0개 Observation 이후 리뷰/평점 조건을 완화해 재검색합니다.

## 외부 API 사용 방법

기본 구현에서 실제로 사용하는 외부 API는 Open-Meteo뿐입니다.

- API: Open-Meteo Forecast API
- 인증: API key 필요 없음
- 비용: 무료 공개 API
- 용도: 현재 기온, 강수량, 날씨 코드 기반 음식 힌트 생성
- 실패 처리: 네트워크 오류나 응답 오류 발생 시 mock 날씨 데이터 사용

Kakao Local API, Naver Search API, Google Places API는 과금 또는 키 관리 부담을 피하기 위해 기본 구현에서 제외했습니다. 필요한 경우 `.env.example`의 주석에 맞춰 키를 입력하고 별도 MCP 도구를 추가하면 됩니다.

## 제출 체크리스트

- 소스 코드: `react_client.py`, `env_context_server.py`, `gourmet_db_server.py`
- 실행 환경: `requirements.txt`
- README: `README.md`
- 실행 로그: `sample_outputs/jeonju_run_log.md`
- ReAct 도구 호출 trace: `sample_outputs/jeonju_trace_sample.jsonl`
- Agentic Design Pattern 설명: README의 `Agentic Design Pattern` 섹션
- 외부 API 사용 방법: README의 `외부 API 사용 방법` 섹션

## 제출 제외 항목

다음 항목은 GitHub와 zip 제출물에 포함하지 않습니다.

- `.env`
- `.venv`
- `__pycache__`
- `node_modules`
- `logs/`
- API key, token, secret
