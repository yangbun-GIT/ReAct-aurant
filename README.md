# ReAct-aurant

`ReAct-aurant`는 OSS 과제4 제출을 위한 Python 기반 맛집 추천 AI Agent 프로젝트입니다.

사용자의 자연어 요청을 분석한 뒤 MCP 서버들을 도구처럼 호출해 날씨, 사용자 선호도, 맛집 후보, 공공데이터 상세 정보를 수집합니다. 이후 ReAct 흐름으로 검색, 정렬, 검토, 최종 추천을 수행합니다.

## 제출 자료 빠른 확인

| 제출 항목 | 확인 위치 | 비고 |
| --- | --- | --- |
| 소스 코드 | `react_client.py`, `env_context_server.py`, `gourmet_db_server.py`, `public_data_server.py` | ReAct 실행 루프와 MCP 도구 서버 구현 |
| 실행 환경 | `requirements.txt` | Python 패키지 고정 |
| README | `README.md` | 설치, 실행, 패턴, API 사용 방법 설명 |
| 실행 로그 | `sample_outputs/jeonju_run_log.md` | 대표 프롬프트 실행 결과와 도구 호출 요약 |
| ReAct 도구 호출 Trace | `sample_outputs/jeonju_trace_sample.jsonl` | JSONL 원본 trace |
| Agentic Design Pattern 설명 | README의 `Agentic Design Pattern` 섹션 | ReAct 포함 5개 패턴 설명 |
| 외부 API 사용 방법 | README의 `외부 API 사용 방법` 섹션 | Open-Meteo, TourAPI 설명 |

## 구현 요약

- 기본 데이터 경로는 `--data-source auto`입니다. 한국관광공사 TourAPI 공공데이터를 먼저 시도하고, 키가 없거나 지원 범위를 벗어나면 로컬 샘플 데이터셋으로 fallback합니다.
- 과금이 발생하지 않도록 Kakao Local API, Naver Search API, Google Places API는 사용하지 않습니다.
- 날씨는 API key가 필요 없는 Open-Meteo를 사용하고, 호출 실패 시 mock 날씨로 대체합니다.
- GPT/OpenAI API는 선택 사항입니다. 기본 실행은 `--use-llm`을 주지 않으므로 LLM API 비용이 발생하지 않습니다.
- MCP 서버는 공식 오픈소스 MCP Python SDK(`mcp`)로 구현했습니다.
- TourAPI는 평점과 리뷰 수를 제공하지 않으므로, 공공데이터 경로에서는 주소, 좌표, 상세정보 충실도, 요청 조건 일치도로 추천하고 임의 평점/리뷰를 생성하지 않습니다.

## 프로젝트 구조

```text
env_context_server.py                    # 날씨, 사용자 선호도, 메모리 MCP 서버
gourmet_db_server.py                     # 로컬 맛집 검색, 상세 조회, 랭킹 MCP 서버
public_data_server.py                    # 한국관광공사 TourAPI 공공데이터 MCP 서버
react_client.py                          # ReAct Agent 실행 클라이언트
requirements.txt                         # Python 실행 환경
.env.example                             # 환경 변수 예시, 실제 key 없음
sample_outputs/jeonju_run_log.md         # 대표 실행 로그
sample_outputs/jeonju_trace_sample.jsonl # ReAct 도구 호출 trace 샘플
README.md                                # 실행 및 제출 문서
tests/                                   # 단위 테스트
```

## 설치

Python 3.11 이상에서 실행할 수 있습니다. 개발 및 검증은 Python 3.13 가상환경에서 진행했습니다.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

이미 `.venv`가 생성되어 있다면 아래처럼 바로 실행할 수 있습니다.

```powershell
.\.venv\Scripts\python react_client.py "전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집을 찾아줘"
```

## 환경 변수

`.env`는 로컬 전용 파일입니다. `.gitignore`에 의해 GitHub와 zip 제출물에 포함되지 않습니다.

```powershell
copy .env.example .env
```

기본 실행은 API key가 없어도 동작합니다. 단, 실제 TourAPI 공공데이터를 새로 조회하려면 `TOUR_API_SERVICE_KEY`가 필요합니다. 키가 없으면 Agent가 Observation으로 실패 사유를 기록하고 로컬 샘플 데이터셋으로 fallback합니다.

공공데이터 사용 환경 변수:

- `TOUR_API_SERVICE_KEY`: 한국관광공사_국문 관광정보 서비스_GW의 일반 인증키를 입력합니다. 공공데이터 기반 추천을 사용하려면 필요합니다.
- `TOUR_API_BASE_URL`: 기본값은 `https://apis.data.go.kr/B551011/KorService2`입니다.
- `TOUR_API_MOBILE_OS`: 공공데이터포털 필수 파라미터입니다. CLI 실행은 `ETC`를 사용합니다.
- `TOUR_API_MOBILE_APP`: 공공데이터포털 필수 파라미터입니다. 기본값은 `ReAct-aurant`입니다.
- `TOUR_API_DEFAULT_AREA_CODE`: 전북 지역 코드 `37`입니다.
- `TOUR_API_DEFAULT_SIGUNGU_CODE`: 전주시 시군구 코드 `12`입니다.

선택 환경 변수:

- `OPENAI_API_KEY`: `--use-llm` 옵션으로 최종 문장 다듬기를 사용할 때만 필요합니다.
- `OPENAI_BASE_URL`: OpenAI 또는 OpenAI 호환 API base URL입니다.
- `OPENAI_MODEL`: 선택 LLM 모델명입니다.
- `KAKAO_REST_API_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `GOOGLE_PLACES_API_KEY`: 비용 및 키 관리 부담 때문에 기본 구현에서는 사용하지 않습니다.

## 실행

대표 과제 요청:

```powershell
.\.venv\Scripts\python react_client.py "전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집을 찾아줘. 너무 비싸지 않고, 리뷰가 좋은 곳 위주로 3곳 추천해줘."
```

`--query`를 쓰는 방식도 계속 지원합니다.

```powershell
.\.venv\Scripts\python react_client.py --query "전주 효자동 한식 맛집 추천해줘" --data-source auto --trace logs\trace_jeonju.jsonl
```

데이터 소스 옵션:

- `--data-source auto`: TourAPI 공공데이터를 먼저 사용하고 실패 시 로컬 샘플 데이터셋으로 fallback합니다.
- `--data-source public`: TourAPI 공공데이터 경로를 우선 사용합니다. 전주 외 지역이거나 키가 없으면 로컬 fallback을 기록합니다.
- `--data-source local`: 공공데이터를 호출하지 않고 로컬 샘플 데이터셋만 사용합니다.

지원하는 전주 세부 지역:

- 객사/객리단길
- 한옥마을
- 전북대/전북대학교
- 송천동
- 효자동/신시가지
- 혁신도시
- 아중리/아중/인후동
- 서신동
- 평화동
- 삼천동
- 중화산동
- 전주역
- 전주터미널/고속버스터미널/시외버스터미널

LLM API로 최종 문장만 다듬고 싶을 때는 선택적으로 실행합니다. 비용 방지를 위해 기본값은 비활성입니다.

```powershell
.\.venv\Scripts\python react_client.py --use-llm
```

## MCP 서버와 도구

`env_context_server.py`

- `get_weather_context(location)`: Open-Meteo 또는 mock 기반 날씨와 음식 힌트를 반환합니다.
- `get_user_profile(user_id)`: 과제용 사용자 선호 프로필을 반환합니다.
- `remember_preference(user_id, preference_note)`: 현재 요청을 단기 메모리에 저장합니다.

`gourmet_db_server.py`

- `search_restaurants(...)`: 지역, 음식 종류, 가격대, 평점, 리뷰 수, 거리, 목적 조건으로 로컬 후보를 검색합니다.
- `rank_restaurants(candidate_ids, ranking_policy)`: 후보를 평점, 리뷰 수, 가격, 거리, 목적 적합성, 날씨 힌트로 정렬합니다.
- `get_restaurant_detail(restaurant_id)`: 최종 답변 근거 보강용 상세 정보를 조회합니다.

`public_data_server.py`

- `search_tourapi_restaurants(area, keyword, near_gaeksa, limit, use_cache)`: 한국관광공사 TourAPI에서 전주시 전체 또는 세부 지역 반경 음식점 후보를 조회합니다.
- `get_tourapi_restaurant_detail(content_id, use_cache)`: `detailCommon2`, `detailIntro2` 기반 상세 정보를 조회합니다.
- `rank_tourapi_restaurants(candidates, ranking_policy)`: 공공데이터 후보를 주소, 거리, 상세정보 충실도, 음식 종류, 목적 적합성으로 점수화합니다.
- `cache_tourapi_response(cache_key, payload)`: 제출 검증용 공개 payload 캐시 저장 도구입니다.

## Agentic Design Pattern

| Pattern | 적용 방식 |
| --- | --- |
| Plan-and-Solve Pattern | 사용자 요청을 지역, 목적, 가격, 리뷰, 평점 조건으로 구조화한 뒤 실행 단계를 나눕니다. |
| Tool Use Pattern | MCP `tools/list`, `tools/call`로 서버 도구를 발견하고 호출합니다. |
| ReAct Pattern | `Thought -> Action -> Observation` 형태로 날씨 조회, 후보 검색, 상세 조회, 정렬을 수행합니다. 필수 패턴입니다. |
| Reflection Pattern | 공공데이터 후보가 없거나 지원 범위를 벗어나면 Observation을 검토하고 로컬 데이터셋 fallback을 수행합니다. |
| Memory Pattern | 사용자 선호 프로필을 조회하고 현재 요청을 단기 메모리에 저장합니다. |
| Multi-Agent 구조 | Coordinator Agent, Context Specialist Agent, Public Data Agent, Culinary Finder Agent, Reflection Reviewer로 역할을 분리했습니다. |

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

대표 실행 로그는 `sample_outputs/jeonju_run_log.md`에 포함했습니다. 이 파일에는 대표 프롬프트, Agent 판단 과정 요약, 호출 도구 이름, 도구 입력값, Observation 요약, 최종 추천 결과가 들어 있습니다.

검증한 추가 케이스:

- `--data-source public`: TourAPI 후보 조회, 상세정보 조회, 공공데이터 전용 랭킹 수행
- `--data-source local`: 공공데이터 호출 없이 기존 로컬 샘플 데이터셋 실행
- 전주 외 지역 입력: TourAPI 지원 범위 제한을 Reflection으로 기록하고 로컬 데이터셋으로 fallback
- API key 없음: `TOUR_API_SERVICE_KEY` 누락을 Observation으로 기록하고 로컬 데이터셋으로 fallback

## 외부 API 사용 방법

실제로 사용하는 외부 API는 Open-Meteo와 한국관광공사 TourAPI입니다.

Open-Meteo Forecast API:

- 인증: API key 필요 없음
- 비용: 무료 공개 API
- 용도: 현재 기온, 강수량, 날씨 코드 기반 음식 힌트 생성
- 실패 처리: 네트워크 오류나 응답 오류 발생 시 mock 날씨 데이터 사용

한국관광공사 TourAPI KorService2:

- 데이터명: 한국관광공사_국문 관광정보 서비스_GW
- 엔드포인트: `https://apis.data.go.kr/B551011/KorService2`
- 인증: 공공데이터포털 일반 인증키 필요
- 비용: 무료 공개 API
- 사용 작업: `areaBasedList2`, `locationBasedList2`, `detailCommon2`, `detailIntro2`
- 음식점 기준: `contentTypeId=39`
- 전주 기준: `areaCode=37`, `sigunguCode=12`
- 세부 지역 기준: 객사, 한옥마을, 전북대, 송천동, 효자동 등 중심 좌표 주변 `locationBasedList2` 반경 검색
- 캐시: `data/cache/tourapi`에 24시간 캐시 저장, 제출물과 GitHub에는 포함하지 않음

Kakao Local API, Naver Search API, Google Places API는 과금 또는 키 관리 부담을 피하기 위해 기본 구현에서 제외했습니다.

## 테스트

```powershell
.\.venv\Scripts\python -m compileall react_client.py public_data_server.py env_context_server.py gourmet_db_server.py
.\.venv\Scripts\python -m unittest discover -s tests
```

## 제출 체크리스트

- 소스 코드: `react_client.py`, `env_context_server.py`, `gourmet_db_server.py`, `public_data_server.py`
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
- `data/cache/`
- API key, token, secret
