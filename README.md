# ReAct-aurant

`ReAct-aurant`는 OSS 과제4 제출을 위한 Python 기반 맛집 추천 AI Agent 프로젝트입니다.

사용자의 자연어 요청을 분석한 뒤 MCP 서버들을 도구처럼 호출해 날씨, 사용자 선호도, 맛집 후보, 공공데이터 상세 정보를 수집합니다. 이후 ReAct 흐름으로 검색, 정렬, 검토, 최종 추천을 수행합니다.

## 제출 자료 빠른 확인

| 제출 항목 | 확인 위치 | 비고 |
| --- | --- | --- |
| 소스 코드 | `react_client.py`, `env_context_server.py`, `gourmet_db_server.py`, `public_data_server.py`, `jeonju_gazetteer.py`, `web_dashboard.py` | ReAct 실행 루프, MCP 도구 서버, 전주 지명 사전, 로컬 관리자 대시보드 구현 |
| 실행 환경 | `requirements.txt` | Python 패키지 고정 |
| README | `README.md` | 설치, 실행, 패턴, API 사용 방법 설명 |
| 실행 로그 | `sample_outputs/jeonju_run_log.md` | 대표 프롬프트 실행 결과와 도구 호출 요약 |
| ReAct 도구 호출 Trace | `sample_outputs/jeonju_trace_sample.jsonl` | JSONL 원본 trace |
| Agentic Design Pattern 설명 | README의 `Agentic Design Pattern` 섹션 | ReAct 포함 5개 패턴 설명 |
| 외부 API 사용 방법 | README의 `외부 API 사용 방법` 섹션 | Open-Meteo, TourAPI, Kakao Local API 설명 |

## 구현 요약

- 기본 데이터 경로는 `--data-source auto`입니다. 자동 모드는 TourAPI 공공데이터를 먼저 시도하고, 키가 없거나 지원 범위를 벗어나면 로컬 샘플 데이터셋으로 fallback합니다.
- `KAKAO_REST_API_KEY`가 있으면 `--data-source kakao` 또는 웹의 `Kakao Local API 우선 사용` 체크박스로 Kakao Local API를 1차 장소/위치 검색 도구로 사용할 수 있습니다. TourAPI는 공공데이터 근거는 좋지만 평점, 리뷰, 가격대와 술집/상권 장소 검색 품질이 제한적이므로, 실제 장소 후보 탐색은 Kakao Local 우선 모드가 더 적합합니다.
- `--enrich-kakao-place-metrics` 또는 웹의 `Kakao 장소 링크 지표 보강`을 켜면 Kakao Local 후보의 장소 링크를 최종 출력 전에 별도 도구로 가져옵니다. 도구는 Kakao 장소 패널 API를 먼저 확인하고, 실패하면 장소 페이지 정적 HTML을 파싱합니다. GPT Agent 모드가 켜져 있으면 가져온 `evidence_text`와 추출값만 GPT가 검토해 평점·후기 수·가격대 조건 충족 여부를 판정합니다. GPT가 URL을 직접 열거나 증거에 없는 숫자를 추정하지는 않습니다.
- 날씨는 API key가 필요 없는 Open-Meteo를 사용하고, 호출 실패 시 mock 날씨로 대체합니다.
- OpenAI API key가 있으면 기본 실행에서 GPT Agent 모드를 자동 사용합니다. GPT는 요청 분석 계획, Reflection, 최종 답변 생성을 담당하고 MCP 도구 호출 결과를 근거로만 답변합니다.
- MCP 서버는 공식 오픈소스 MCP Python SDK(`mcp`)로 구현했습니다.
- TourAPI와 Kakao Local 검색 API는 평점, 리뷰 수, 가격대를 공식 검색 응답으로 제공하지 않습니다. Kakao 우선 경로에서는 장소 링크 보강이 켜져 있을 때 Kakao 장소 패널/페이지에서 관측된 지표만 `적용 조건`에 반영하고, 관측되지 않은 값은 임의 생성하지 않습니다. 지표가 관측되지 않으면 최종 답변과 Reflection에 데이터 한계로 표시합니다.
- 전주 세부 위치는 `jeonju_gazetteer.py`의 전주 지명 사전으로 먼저 해석합니다. 이 사전은 전주시 공식 행정구역 자료의 완산구 19개 행정동/46개 법정동, 덕진구 16개 행정동/37개 법정동과 주요 생활권 별칭을 반영합니다. `객사`는 객리단길 중심 상권으로 좁게 해석하고, `웨리단길`, `한옥마을`과 별도 좌표/반경으로 구분합니다. Kakao 우선 모드에서 사전에 없는 전주 지명은 Kakao Local API 키워드 검색으로 좌표를 찾아 반경 검색을 시도합니다.
- 음식 종류는 한식/일식/양식/카페 같은 큰 분류뿐 아니라 파스타, 소바, 마라탕, 쌀국수, 베이커리, 곱창 등 구체 음식명도 검색어로 처리합니다.
- 비/눈/더움/추움/맑음 같은 날씨 조건은 사용자가 입력한 조건을 실제 조회 날씨보다 우선합니다. 비 오는 날은 파전, 막걸리, 따뜻한 국물, 가까운 실내 좌석처럼 보편적인 기대를 힌트로 반영하고, 최종 답변에도 그 근거를 표시합니다.
- `술집`, `혼술`, `포차`, `호프`, `이자카야` 등 술자리 의도는 일반 한식 후보로 임의 대체하지 않습니다. Kakao 우선 모드에서는 Kakao Local API 후보를 바로 정렬하고, 자동/TourAPI 모드에서는 TourAPI 후보가 부족할 때 Kakao Local API 보강을 시도합니다.

## Agent 구조 점검 기준

이 프로젝트는 LLM에게 바로 “맛집 추천해줘”를 묻는 단일 프롬프트 구조가 아닙니다. 실행 흐름은 아래 순서로 분리됩니다.

1. `Coordinator Agent`가 사용자 요청을 지역, 목적, 가격, 리뷰, 평점 조건으로 1차 구조화합니다.
2. `LLM Planner`가 구조화된 조건과 사용 가능한 MCP 도구 목록을 보고 도구 호출 계획과 검토 기준을 생성합니다.
3. `Context Specialist Agent`가 날씨, 사용자 선호, 단기 메모리 MCP 도구를 호출하고 Observation을 trace에 기록합니다.
4. `Public Data Agent`가 데이터 소스 설정에 따라 Kakao Local API 또는 TourAPI 검색, 상세 조회, 랭킹 MCP 도구를 `Thought -> Action -> Observation` 순서로 실행합니다.
5. `LLM Reflection Reviewer`가 도구 Observation과 후보 목록을 검토해 데이터 한계와 조건 충족 여부를 점검합니다.
6. `LLM Final Answer Agent`가 Observation, 랭킹 결과, Reflection을 근거로 최종 추천 문장을 생성합니다.

따라서 최종 답변은 GPT가 직접 상상한 결과가 아니라 MCP 도구 호출 결과와 Reflection을 거친 결과입니다. 단, 안정성을 위해 실제 도구 실행은 허용된 MCP 도구 목록 안에서 코드가 통제하며, GPT Planner는 실행 계획과 검토 기준을 생성하는 역할을 맡습니다.

## 프로젝트 구조

```text
env_context_server.py                    # 날씨, 사용자 선호도, 메모리 MCP 서버
gourmet_db_server.py                     # 로컬 맛집 검색, 상세 조회, 랭킹 MCP 서버
public_data_server.py                    # Kakao Local API, 한국관광공사 TourAPI 공공데이터 MCP 서버
jeonju_gazetteer.py                      # 전주 행정동/법정동/생활권 별칭 사전
react_client.py                          # ReAct Agent 실행 클라이언트
web_dashboard.py                         # 로컬 관리자 웹 대시보드
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

기본 실행은 API key가 없어도 동작합니다. 단, 과제 목적에 맞는 GPT Agent 모드를 사용하려면 `OPENAI_API_KEY`가 필요하고, 실제 TourAPI 공공데이터를 새로 조회하려면 `TOUR_API_SERVICE_KEY`가 필요합니다. Kakao 우선 모드를 사용하려면 `KAKAO_REST_API_KEY`가 필요합니다. 키가 없으면 Agent가 Observation으로 실패 사유를 기록하고 규칙 기반 또는 로컬 샘플 데이터셋으로 fallback하거나 후보 부족을 설명합니다.

공공데이터 사용 환경 변수:

- `TOUR_API_SERVICE_KEY`: 한국관광공사_국문 관광정보 서비스_GW의 일반 인증키를 입력합니다. 공공데이터 기반 추천을 사용하려면 필요합니다.
- `TOUR_API_BASE_URL`: 기본값은 `https://apis.data.go.kr/B551011/KorService2`입니다.
- `TOUR_API_MOBILE_OS`: 공공데이터포털 필수 파라미터입니다. CLI 실행은 `ETC`를 사용합니다.
- `TOUR_API_MOBILE_APP`: 공공데이터포털 필수 파라미터입니다. 기본값은 `ReAct-aurant`입니다.
- `TOUR_API_DEFAULT_AREA_CODE`: 전북 지역 코드 `37`입니다.
- `TOUR_API_DEFAULT_SIGUNGU_CODE`: 전주시 시군구 코드 `12`입니다.

LLM Agent 환경 변수:

- `OPENAI_API_KEY`: GPT Agent 모드에 필요합니다. 값이 있으면 기본 실행에서 자동 사용됩니다.
- `OPENAI_BASE_URL`: OpenAI 또는 OpenAI 호환 API base URL입니다.
- `OPENAI_MODEL`: 선택 LLM 모델명입니다.

선택 환경 변수:

- `KAKAO_REST_API_KEY`: Kakao Developers에서 발급받는 REST API 키입니다. 값이 있으면 웹의 `Kakao Local API 우선 사용` 체크박스 또는 CLI `--data-source kakao`로 Kakao Local API 키워드 검색을 1차 장소 검색 도구로 호출합니다. Kakao Local은 장소명, 주소, 세부 카테고리, 전화번호, 거리, 장소 URL을 제공하지만 평점/리뷰 수/가격대는 제공하지 않으므로 해당 값은 임의 생성하지 않습니다.
- `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`: Naver Search API를 추가로 붙이면 `sort=comment`로 블로그/카페 리뷰 언급이 많은 지역 검색 결과를 우선 조회할 수 있지만, 공식 응답에 개별 식당 평점/정확한 방문자 리뷰 수/가격대 필드는 없습니다.
- `GOOGLE_PLACES_API_KEY`: Google Places API를 추가로 붙이면 `rating`, `userRatingCount`, `priceLevel` 같은 지표를 공식 필드로 받을 수 있습니다. 단, Google Cloud 결제 설정 및 Places SKU 과금/무료 사용량 관리가 필요하므로 현재 기본 실행에서는 사용하지 않습니다.

로컬 관리자 웹 대시보드 환경 변수:

- `WEB_HOST`: 기본값은 `127.0.0.1`입니다. 키와 실행 로그 보호를 위해 로컬 바인딩을 권장합니다.
- `WEB_PORT`: 기본값은 `0`입니다. OS가 사용 가능한 포트를 자동 할당하고 실행 콘솔에 실제 URL을 출력합니다. 고정 포트를 원하면 예: `8765`처럼 지정합니다.
- `WEB_ADMIN_USERNAME`: 기본 관리자 계정명입니다. 기본값은 `admin`입니다.
- `WEB_ADMIN_PASSWORD`: `WEB_AUTO_LOGIN=false`로 둘 때만 로컬 `.env`에 입력합니다. `.env.example`이나 GitHub에는 실제 비밀번호를 넣지 않습니다.
- `WEB_AUTO_LOGIN`: 기본값은 `true`입니다. `127.0.0.1` 접속은 자동 관리자 로그인으로 처리합니다.
- `WEB_AGENT_TIMEOUT_SECONDS`: 웹에서 Agent 1회 실행을 기다리는 최대 시간입니다.

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
- `--data-source kakao`: Kakao Local API를 1차 장소/위치 검색 도구로 사용합니다. 웹에서는 `Kakao Local API 우선 사용` 체크박스를 켜면 이 모드로 실행됩니다.
- `--data-source local`: 공공데이터를 호출하지 않고 로컬 샘플 데이터셋만 사용합니다.
- `--enrich-kakao-place-metrics`: Kakao 장소 링크에서 평점/리뷰 수/가격대 지표 후보를 추출하고, GPT Agent가 추출 증거만 기준으로 조건 충족 여부를 판정합니다. 이 옵션은 보강용이며 실패 시 기존 Kakao Local 기준으로 자동 fallback합니다.

`auto`는 실행 시점에 실제 사용 경로가 달라질 수 있습니다. 웹 대시보드의 실행 요약에는 예를 들어 `auto -> TourAPI`, `kakao -> Kakao Local`, `auto -> GPT`, `auto -> rule fallback`처럼 실제 선택된 데이터 소스와 LLM 경로가 표시됩니다. 저장된 실행 목록은 가독성을 위해 질문과 실행 일시만 표시하고, 세부 실행 경로는 클릭 후 실행 요약에서 확인합니다.

지원하는 전주 세부 지역:

기준 자료: [전주시 대표사이트 행정구역](https://jeonju.go.kr/index.9is?contentUid=ff8080818990c349018b041a9ed03a70)

- 행정구: 완산구, 덕진구
- 완산구 주요 행정동/법정동: 중앙동, 다가동, 고사동, 태평동, 풍남동, 전동, 교동, 노송동, 완산동, 동서학동, 대성동, 서서학동, 중화산동, 평화동, 서신동, 삼천동, 효자동 등
- 덕진구 주요 행정동/법정동: 진북동, 인후동, 덕진동, 금암동, 팔복동, 우아동, 호성동, 송천동, 전미동, 조촌동, 여의동, 만성동, 혁신동, 중동, 장동 등
- 생활권/별칭: 객사, 객리단길, 웨리단길, 한옥마을, 남부시장, 전북대, 전북대 구정문, 신시가지, 에코시티, 전주역, 전주터미널, 덕진공원 등

예를 들어 `전주 다가동1가`, `전주 동산동`, `전주 중동`, `전주 호성동`, `전주 에코시티`처럼 입력해도 존재하지 않는 지역으로 처리하지 않고 전주 내부 검색 기준으로 정규화합니다. `--data-source local`은 로컬 샘플 데이터셋이 객사 후보만 포함하므로 세부 지역 검색에는 `--data-source auto` 또는 `--data-source public` 사용을 권장합니다.

LLM 실행 옵션:

```powershell
.\.venv\Scripts\python react_client.py --use-llm
```

`OPENAI_API_KEY`가 있으면 `--use-llm`을 붙이지 않아도 GPT Agent 모드가 자동으로 켜집니다. API 호출 없이 규칙 기반 fallback만 확인하려면 아래처럼 실행합니다.

```powershell
.\.venv\Scripts\python react_client.py "전주 객사 근처 맛집 추천해줘" --no-llm
```

## 로컬 관리자 웹 대시보드

입력과 출력, ReAct Agent Trace, 실행 로그를 한 화면에서 확인하려면 아래 명령으로 로컬 웹 서버를 실행합니다.

```powershell
.\.venv\Scripts\python web_dashboard.py
```

Docker로 실행하려면 아래 명령을 사용합니다. 컨테이너 내부 포트는 `8765`로 고정하고, 로컬 PC에서 열 포트는 `WEB_DOCKER_PORT`로 바꿀 수 있어 포트 충돌을 피하기 쉽습니다.

```powershell
docker compose up --build
```

다른 로컬 포트를 쓰려면 다음처럼 실행합니다.

```powershell
$env:WEB_DOCKER_PORT=18765
docker compose up --build
```

실행 후 브라우저에서 `http://127.0.0.1:18765/app` 또는 변경한 포트의 `/app` 주소를 엽니다. Compose 포트는 호스트의 `127.0.0.1`에만 바인딩되도록 설정되어 있습니다. `.env` 파일이 있으면 Docker Compose가 변수 치환에 사용하지만, `.dockerignore`에 의해 이미지에는 포함되지 않습니다.

명령 실행 후 콘솔에 출력되는 `ReAct-aurant Admin: http://127.0.0.1:<port>/app` 주소를 브라우저에서 엽니다. 기본 설정은 로컬 접속 자동 로그인입니다. 회원가입은 없고 관리자 계정 하나만 사용합니다.

웹 대시보드에서 확인할 수 있는 항목:

- 사용자 질문 입력 및 실행
- 최종 추천 결과
- Agent 판단 과정
- 호출한 MCP 도구 이름
- 도구 입력값
- 도구 실행 결과 Observation
- ReAct Trace 자연어 흐름
- ReAct Trace 코드 흐름
- 원본 Trace JSONL
- 질문별 저장된 실행 로그
- `auto` 설정이 실제로 선택한 데이터 소스와 LLM 경로

웹 실행 결과는 `logs/web_runs/<run_id>/`에 저장됩니다. 이 경로는 `.gitignore`의 `logs/` 규칙에 의해 GitHub와 zip 제출물에서 제외됩니다. 대시보드는 키 값을 화면에 표시하지 않으며, Agent 실행 명령과 Trace만 저장합니다.
저장된 실행은 대시보드의 항목별 `삭제` 또는 `전체 삭제` 버튼으로 지울 수 있습니다. Docker Compose 실행 시 `./logs`가 컨테이너에 마운트되므로 웹에서 삭제하면 로컬 `logs/web_runs` 폴더의 해당 기록도 같이 삭제됩니다.

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

- `search_tourapi_restaurants(area, keyword, cuisine, max_price_level, min_rating, min_review_count, max_distance_m, near_gaeksa, limit, use_cache)`: 전주 세부 위치를 좌표로 해석한 뒤 TourAPI 음식점 후보를 조회합니다. `cuisine`은 큰 분류와 구체 음식명 모두 받을 수 있고, TourAPI가 제공하지 않는 평점/리뷰/가격 조건은 응답의 `unavailable_filters`와 최종 답변의 데이터 한계로 표시합니다. 술집 의도는 막걸리, 전집, 포차, 호프, 이자카야 등 직접 관련 키워드로 확장하되 일반 식당으로 무리하게 채우지 않습니다.
- `search_kakao_local_places(area, keyword, cuisine, max_price_level, min_rating, min_review_count, max_distance_m, near_gaeksa, limit)`: `KAKAO_REST_API_KEY`가 있을 때 Kakao Local API 키워드 검색으로 장소 후보를 조회합니다. Kakao 우선 모드에서는 이 도구가 1차 검색 도구이며, 사전에 없는 전주 세부 위치는 Kakao Local API 키워드 검색으로 좌표를 해석합니다. Kakao의 `category_name`은 `음식점 > ... > 세부항목`의 마지막 항목을 보존해 일본식라면, 양꼬치, 브런치카페 같은 세부 업종을 넓은 대분류로 뭉개지 않습니다. 키가 없으면 error Observation을 반환해 Agent가 데이터 한계를 설명하도록 합니다.
- `extract_kakao_place_metrics(place_url, place_name, min_rating, min_review_count, max_price_level)`: Kakao 장소 링크 페이지를 가져와 평점, 리뷰 수, 가격대가 포함된 텍스트 증거를 추출합니다. 이 도구 Observation에 지표가 있을 때만 LLM이 조건 충족 여부를 판정하며, 지표가 없으면 후보를 임의 배제하지 않고 기존 Kakao Local 메타데이터 기준으로 fallback합니다.
- `get_tourapi_restaurant_detail(content_id, use_cache)`: `detailCommon2`, `detailIntro2` 기반 상세 정보를 조회합니다.
- `rank_tourapi_restaurants(candidates, ranking_policy)`: 공공데이터 후보를 주소, 거리, 상세정보 충실도, 음식 종류, 목적 적합성으로 점수화합니다.
- `cache_tourapi_response(cache_key, payload)`: 제출 검증용 공개 payload 캐시 저장 도구입니다.

## Agentic Design Pattern

| Pattern | 적용 방식 |
| --- | --- |
| Plan-and-Solve Pattern | 사용자 요청을 지역, 목적, 가격, 리뷰, 평점 조건으로 구조화한 뒤 GPT Planner가 MCP 도구 호출 계획을 생성합니다. |
| Tool Use Pattern | MCP `tools/list`, `tools/call`로 서버 도구를 발견하고 호출합니다. |
| ReAct Pattern | `Thought -> Action -> Observation` 형태로 날씨 조회, 후보 검색, 상세 조회, 정렬을 수행합니다. 필수 패턴입니다. |
| Reflection Pattern | GPT Reflection Reviewer가 Observation과 후보 목록을 검토하고, 공공데이터 후보가 없거나 지원 범위를 벗어나면 로컬 데이터셋 fallback을 수행합니다. |
| Memory Pattern | 사용자 선호 프로필을 조회하고 현재 요청을 단기 메모리에 저장합니다. |
| Multi-Agent 구조 | Coordinator Agent, LLM Planner, Context Specialist Agent, Public Data Agent, Culinary Finder Agent, LLM Reflection Reviewer, LLM Final Answer Agent로 역할을 분리했습니다. |

### 2단계 패턴 적용 점검

대표 trace `sample_outputs/jeonju_trace_sample.jsonl` 기준으로 다음 순서가 확인됩니다.

| 점검 항목 | Trace 근거 |
| --- | --- |
| Plan-and-Solve | step 1에서 전체 문제를 분해하고, step 5에서 요청 조건을 구조화하며, step 6에서 GPT Planner가 도구 호출 계획과 Reflection 기준을 생성합니다. |
| Tool Use | step 2~4에서 MCP `tools/list`로 사용 가능한 도구를 발견하고, step 7에서 `select_tools`로 실행 도구를 선택한 뒤 `tools/call`로 날씨, 메모리, Kakao Local/TourAPI 검색, 상세 조회, 랭킹 도구를 호출합니다. |
| ReAct 필수 패턴 | step 14 `Thought: 실제 공공데이터 기반 후보 확보 -> Action: search_tourapi_restaurants`, step 15 Observation, step 26 `rank_tourapi_restaurants`, step 27 Observation, step 31 Final Answer로 이어집니다. |
| Reflection | step 28에서 GPT Reflection Reviewer가 후보와 Observation을 검토하고, step 29에서 조건 충족 여부와 데이터 한계를 기록합니다. |
| Memory | step 10에서 사용자 선호 프로필을 조회하고, step 12에서 현재 요청을 단기 메모리에 저장합니다. |
| Multi-Agent | Coordinator, LLM Planner, Context Specialist, Public Data Agent, Reflection Reviewer, LLM Final Answer Agent가 역할을 나누어 실행됩니다. |

패턴 적용 여부는 `tests/test_agentic_patterns.py`에서 자동으로 검증합니다. 이 테스트는 ReAct의 Action/Observation 순서, Reflection 전후 관계, Memory 도구 호출, 최종 답변의 데이터 한계 보존 여부를 확인합니다.

### 3단계 ReAct Agent Client 실행 루프 점검

`react_client.py`의 `run_agent()`가 Agent Client 실행 루프입니다. 이 루프는 LLM에게 한 번에 답을 맡기지 않고, MCP 도구를 직접 호출하면서 다음 흐름을 수행합니다.

| 과제 요구 흐름 | 구현 위치와 Trace 근거 |
| --- | --- |
| 사용자 요청 분석 | `parse_user_request()`가 지역, 음식 종류, 목적, 가격, 평점, 리뷰, 거리 조건을 구조화하고 trace step 5에 Observation으로 기록합니다. |
| 필요한 도구 선택 | MCP `tools/list` 결과와 데이터 소스 설정을 바탕으로 step 7 `select_tools` trace를 기록합니다. 여기에는 환경, 메모리, Kakao Local 검색, TourAPI 검색/상세/랭킹, 로컬 fallback 도구 선택 이유가 포함됩니다. |
| 맛집 검색 도구 호출 | `MCPToolClient.call_tool()`이 step 14에서 `search_tourapi_restaurants` 또는 fallback의 `search_restaurants`를 `tools/call`로 직접 호출합니다. |
| 검색 결과 Observation 수신 | step 15 `Observation:search_tourapi_restaurants` 또는 fallback의 `Observation:search_restaurants`가 `tools/call/result`로 저장됩니다. |
| 조건에 맞는 후보 필터링 | step 26~27 `rank_tourapi_restaurants`와 `reflect_public_recommendations()`가 거리, 음식 종류, 상세정보 충실도, 데이터 한계를 반영해 후보를 정렬/검토합니다. |
| 필요 시 추가 도구 호출 | step 16~25에서 검색 후보 상위 5개에 대해 `get_tourapi_restaurant_detail`을 추가 호출해 전화번호, 메뉴, 영업정보를 보강합니다. 공공데이터 실패 시 로컬 검색 도구로 fallback합니다. |
| 최종 추천 답변 생성 | step 28~31 Reflection 이후 `build_public_final_answer()` 또는 `build_final_answer()`가 도구 Observation 기반 초안을 만들고, `LLM Final Answer Agent`가 초안의 근거를 보존해 최종 답변을 생성합니다. |

이 실행 루프는 `tests/test_agentic_patterns.py`의 `test_react_agent_client_loop_covers_required_stage_three_flow`에서 자동 검증합니다.

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
- `--data-source kakao`: Kakao Local API 후보 조회, Kakao 장소/거리/카테고리 기반 랭킹 수행
- `--data-source local`: 공공데이터 호출 없이 기존 로컬 샘플 데이터셋 실행
- 전주 외 지역 입력: TourAPI 지원 범위 제한을 Reflection으로 기록하고 로컬 데이터셋으로 fallback
- API key 없음: `TOUR_API_SERVICE_KEY` 누락을 Observation으로 기록하고 로컬 데이터셋으로 fallback
- 예외 처리 검증: `sample_outputs/stage4_exception_run_log.md`

## 에러 대응 및 예외 처리

Agent는 입력 검증과 도구 호출 결과를 모두 Observation으로 기록한 뒤, Reflection 단계에서 대안을 선택합니다. 단순히 오류를 출력하지 않고 가능한 경우 조건을 보완하거나 완화해 추천을 계속 진행합니다.

| 예외 상황 | 처리 방식 |
| --- | --- |
| 존재하지 않는 지역 또는 전주 외 지역 | `Input Guard Agent`가 warning을 남기고, 도구가 `status=error`를 반환하면 `전주 객사` 기준으로 fallback 검색합니다. |
| 검색 결과 없음 | 첫 검색 Observation의 `count=0`을 확인한 뒤 리뷰/평점 조건을 완화하고, 그래도 없으면 음식 종류 조건을 해제해 재검색합니다. |
| 음식 종류가 너무 모호함 | `ambiguous_food_type` warning을 기록하고 특정 메뉴로 제한하지 않은 전체 음식점 검색을 수행합니다. |
| API 호출 실패 | MCP `tools/call/result`에 error Observation을 기록하고, Kakao 우선 모드는 후보 부족/키 설정 문제를 최종 답변에 표시합니다. 자동/TourAPI 경로는 TourAPI 실패 시 로컬 샘플 데이터셋으로 fallback합니다. |
| 사용자 조건 부족 | `insufficient_conditions` warning을 기록하고 지역, 목적, 가격대 등 누락 조건을 과제 기본값으로 보완합니다. 최종 답변에 보완 내용을 표시합니다. |
| 맛집과 관계없는 입력 | `unrelated_request` error를 기록하고 도구 호출 없이 전주 맛집 추천 요청 예시를 제시합니다. |
| 선정적, 폭력적, 불법적 요청 | `safety_blocked` error를 기록하고 도구 호출 없이 안전한 입력 형식으로 유도합니다. |
| 맛집 맥락 안의 과한 표현 | 너무 엄격하게 차단하지 않고 `unsafe_expression_sanitized` warning으로 처리한 뒤, 지역/음식/거리/가격 같은 안전한 조건만 반영합니다. |

예외 처리 검증 명령:

```powershell
.\.venv\Scripts\python react_client.py "추천해줘" --no-llm --data-source local --trace logs\stage4_insufficient_trace.jsonl
.\.venv\Scripts\python react_client.py "전주 객사 우주젤리 맛집 추천해줘" --no-llm --data-source local --trace logs\stage4_no_results_trace.jsonl
.\.venv\Scripts\python react_client.py "부산 서면 근처에서 친구랑 저녁 먹기 좋은 맛집 추천해줘" --no-llm --data-source local --trace logs\stage4_unsupported_region_trace.jsonl
.\.venv\Scripts\python react_client.py "파이썬 코드 알려줘" --no-llm --data-source local --trace logs\stage4_unrelated_trace.jsonl
.\.venv\Scripts\python react_client.py "전주 객사 성적인 맛집 추천해줘" --no-llm --data-source local --trace logs\stage4_safety_trace.jsonl
.\.venv\Scripts\python react_client.py "전주 객사에서 살인적인 매운 맛집 추천해줘" --no-llm --data-source local --trace logs\stage4_contextual_safety_trace.jsonl
```

## 외부 API 사용 방법

실제로 사용하는 외부 API는 Open-Meteo, 한국관광공사 TourAPI, Kakao Local API입니다.

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

Kakao Local API:

- 사용 위치: `public_data_server.py`
- 용도: 웹의 `Kakao Local API 우선 사용` 또는 CLI `--data-source kakao` 실행 시 전주 세부 위치 해석, 장소 후보 검색, 거리 기반 추천
- 인증: `KAKAO_REST_API_KEY`
- 호출 도구: `search_kakao_local_places`
- 제공 정보: 장소명, 주소, 전화번호, 카테고리, 거리, 장소 URL
- 미제공 정보: Kakao Local 검색 API 응답 자체에는 평점, 리뷰 수, 가격대가 없습니다. 해당 값은 임의 생성하지 않고 최종 답변의 데이터 한계로 표시합니다.
- 선택 보강: `--enrich-kakao-place-metrics`를 켜면 `extract_kakao_place_metrics` 도구가 후보별 장소 URL을 최종 출력 전에 가져와 Kakao 장소 패널 API와 장소 페이지 정적 HTML에서 평점/후기 수/가격대 증거를 수집합니다. GPT Agent 모드에서는 이 도구 Observation의 `evidence_text`와 추출값만 GPT가 검토해 조건 충족 여부를 판정합니다. 도구가 이미 관측한 숫자는 GPT가 덮어쓸 수 없고, GPT가 증거 텍스트에서 보완한 값도 범위 검증 후에만 사용됩니다. 평점/후기 수가 관측되지 않으면 기본 품질 조건을 검증할 수 없으므로 추천에서 제외하거나 후보 부족 사유로 표시합니다.

Naver Search API와 Google Places API는 현재 기본 실행에서 제외했습니다. Naver Search API는 지역 검색 결과를 `comment` 정렬로 받을 수 있어 리뷰 언급량 보조 신호로는 쓸 수 있지만, 공식 응답에 평점/방문자 리뷰 수/가격대가 없습니다. Google Places API는 `rating`, `userRatingCount`, `priceLevel`을 제공하므로 평점/리뷰/가격을 실제 추천 기준으로 반영하려면 가장 직접적인 공식 대안입니다. 다만 Google Places는 결제 설정과 SKU별 무료 사용량/초과 과금 관리가 필요하므로, 비용 0원 제출 조건에서는 기본 비활성으로 둡니다. Kakao 장소 URL은 GPT가 직접 열지 않고, MCP 도구가 먼저 가져온 장소 패널/페이지 증거만 GPT 판정 입력으로 사용합니다.

## 테스트

```powershell
.\.venv\Scripts\python -m compileall react_client.py public_data_server.py env_context_server.py gourmet_db_server.py
.\.venv\Scripts\python -m unittest discover -s tests
```

## 제출 체크리스트

- 소스 코드: `react_client.py`, `env_context_server.py`, `gourmet_db_server.py`, `public_data_server.py`, `jeonju_gazetteer.py`
- 실행 환경: `requirements.txt`
- README: `README.md`
- 실행 로그: `sample_outputs/jeonju_run_log.md`
- 예외 처리 실행 로그: `sample_outputs/stage4_exception_run_log.md`
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
