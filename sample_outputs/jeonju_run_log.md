# 대표 실행 로그

실행 명령:

```powershell
.\.venv\Scripts\python react_client.py "전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집을 찾아줘. 너무 비싸지 않고, 리뷰가 좋은 곳 위주로 3곳 추천해줘." --use-llm --trace logs\trace_jeonju.jsonl
```

## Agent 판단 과정 요약

| 단계 | Agent | Pattern | 판단 및 수행 내용 |
| --- | --- | --- | --- |
| 1 | Coordinator Agent | Plan-and-Solve | 요청을 지역, 목적, 가격, 리뷰, 평점 조건으로 분해하고 MCP 서버 연결을 준비 |
| 2 | LLM Planner | Plan-and-Solve | GPT가 1차 파싱 결과를 검토하고 MCP 도구 호출 계획과 Reflection 기준 생성 |
| 3 | Context Specialist Agent | Tool Use / Memory | 날씨, 사용자 선호도, 단기 메모리 도구 호출 |
| 4 | Public Data Agent | ReAct | TourAPI 공공데이터에서 전주 객사 근처 음식점 후보 검색 |
| 5 | Public Data Agent | Tool Use | 상위 후보의 상세 정보 조회 |
| 6 | Public Data Agent | ReAct | 주소, 거리, 상세정보 충실도, 사용자 조건 일치도로 후보 정렬 |
| 7 | LLM Reflection Reviewer | Reflection | GPT가 Observation과 후보 목록을 검토하고 데이터 한계와 조건 충족 여부 확인 |
| 8 | LLM Final Answer Agent | Final Answer | GPT가 도구 결과와 Reflection을 보존해 최종 답변 생성 |

## 도구 호출 요약

| 순서 | MCP 서버 | 도구 | 주요 입력값 | Observation 요약 |
| --- | --- | --- | --- | --- |
| 1 | OpenAI API | `chat.completions.create` | 사용자 요청, 1차 파싱 결과, 사용 가능한 MCP 도구 | GPT가 도구 호출 계획과 검토 기준 생성 |
| 2 | `env_context_server.py` | `get_weather_context` | `location=전주 객사` | 전주 객사 기준 날씨와 음식 힌트 수신 |
| 3 | `env_context_server.py` | `get_user_profile` | `user_id=default` | 가격 민감도, 선호 음식, 도보 선호 수신 |
| 4 | `env_context_server.py` | `remember_preference` | 최근 요청 문장 | 현재 요청을 단기 메모리에 저장 |
| 5 | `public_data_server.py` | `search_tourapi_restaurants` | `area=전주 객사`, `cuisine=null`, `min_rating=4.2`, `min_review_count=100`, `max_distance_m=1000`, `target_area=객사`, `near_gaeksa=true`, `limit=8` | TourAPI 음식점 후보 8개 수신 |
| 6 | `public_data_server.py` | `get_tourapi_restaurant_detail` | `content_id=1597886` | 하숙영 가마솥비빔밥 상세 정보 수신 |
| 7 | `public_data_server.py` | `get_tourapi_restaurant_detail` | `content_id=2759623` | 성미당 상세 정보 수신 |
| 8 | `public_data_server.py` | `get_tourapi_restaurant_detail` | `content_id=133228` | 한국집 상세 정보 수신 |
| 9 | `public_data_server.py` | `get_tourapi_restaurant_detail` | `content_id=3444028` | 진미반점 상세 정보 수신 |
| 10 | `public_data_server.py` | `get_tourapi_restaurant_detail` | `content_id=2907462` | 또순이네집 상세 정보 수신 |
| 11 | `public_data_server.py` | `rank_tourapi_restaurants` | 상세 후보 5개, 랭킹 정책 | 한국집, 또순이네집, 하숙영 가마솥비빔밥 순으로 최종 후보 정렬 |
| 12 | OpenAI API | `chat.completions.create` | 추천 후보, Observation, 규칙 기반 Reflection | GPT가 Reflection 생성 |
| 13 | OpenAI API | `chat.completions.create` | 도구 결과 기반 답변 초안 | GPT가 최종 답변 생성 |

상세 JSONL trace는 `sample_outputs/jeonju_trace_sample.jsonl`에 저장되어 있습니다.

## 실행 결과

```text
최종 추천 결과

요청: 전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집을 찾아줘. 너무 비싸지 않고, 리뷰가 좋은 곳 위주로 3곳 추천해줘.
분석 조건: 지역=전주 객사, 목적=친구와 저녁, 최대가격대=2, 최소평점=4.2, 최소리뷰수=100
데이터 출처: 한국관광공사 TourAPI KorService2
데이터 한계: TourAPI는 평점, 리뷰 수, 가격대를 제공하지 않아 임의 수치를 생성하지 않았습니다.
날씨 반영: 전주 객사 기준 흐림, 12.6도
사용자 선호 반영: 너무 비싸지 않은 곳, 리뷰가 좋은 곳, 걷기 부담 없는 거리

1. 한국집 (한식)
- 추천 이유: 한국관광공사 TourAPI 등록 정보 기준으로 주소, 거리, 상세정보 충실도, 요청 조건 일치도를 반영했습니다.
- 주소: 전북특별자치도 전주시 완산구 어진길 119
- 거리: 객사 기준 277m
- 평점/리뷰/가격대: 평점 TourAPI 미제공, 리뷰 TourAPI 미제공, 가격대 TourAPI 미제공
- 전화: 063-284-2224
- 대표 메뉴: 전주비빔밥
- 영업 정보: 09:50~21:00 (마지막 주문 20:15), 휴무 연중무휴
- 점수 근거: 전주 주소 일치, 객사 기준 500m 이내, 음식점 분류, 상세정보 7개 확보, 사용자 선호 음식 분류, 친구 방문 목적에 활용 가능한 음식점 정보, 카페보다 식사 후보에 가까움, 날씨 힌트 매칭: 한식, 요청 거리 1000m 이내, TourAPI 평점 미제공, TourAPI 리뷰 수 미제공, TourAPI 가격대 미제공

2. 또순이네집 (한식)
- 추천 이유: 한국관광공사 TourAPI 등록 정보 기준으로 주소, 거리, 상세정보 충실도, 요청 조건 일치도를 반영했습니다.
- 주소: 전북특별자치도 전주시 완산구 전주객사3길 11-8
- 거리: 객사 기준 442m
- 평점/리뷰/가격대: 평점 TourAPI 미제공, 리뷰 TourAPI 미제공, 가격대 TourAPI 미제공
- 전화: 063-231-3123
- 대표 메뉴: 김치찜
- 영업 정보: 10:30~21:00 (평일 브레이크타임 16:00~17:00 / 라스트오더 20:40), 휴무 매주 월요일, 화요일
- 점수 근거: 전주 주소 일치, 객사 기준 500m 이내, 음식점 분류, 상세정보 7개 확보, 사용자 선호 음식 분류, 친구 방문 목적에 활용 가능한 음식점 정보, 카페보다 식사 후보에 가까움, 날씨 힌트 매칭: 한식, 요청 거리 1000m 이내, TourAPI 평점 미제공, TourAPI 리뷰 수 미제공, TourAPI 가격대 미제공

3. 하숙영 가마솥비빔밥 (한식)
- 추천 이유: 한국관광공사 TourAPI 등록 정보 기준으로 주소, 거리, 상세정보 충실도, 요청 조건 일치도를 반영했습니다.
- 주소: 전북특별자치도 전주시 완산구 전라감영5길 19-3
- 거리: 객사 기준 161m
- 평점/리뷰/가격대: 평점 TourAPI 미제공, 리뷰 TourAPI 미제공, 가격대 TourAPI 미제공
- 전화: 063-285-8288
- 대표 메뉴: 옛날가마솥 육회비빔밥
- 영업 정보: 11:00~19:50 - 준비시간 15:30~17:30 - 마지막 주문 19:20, 휴무 연중무휴
- 점수 근거: 전주 주소 일치, 객사 기준 500m 이내, 음식점 분류, 상세정보 6개 확보, 사용자 선호 음식 분류, 친구 방문 목적에 활용 가능한 음식점 정보, 카페보다 식사 후보에 가까움, 날씨 힌트 매칭: 한식, 요청 거리 1000m 이내, TourAPI 평점 미제공, TourAPI 리뷰 수 미제공, TourAPI 가격대 미제공

Reflection: 추천된 맛집들은 전주 객사 근처에 위치하고, 친구와 저녁을 먹기에 적합한 한식집입니다. 그러나 평점, 리뷰 수, 가격대 정보가 제공되지 않아 데이터 한계가 있습니다.

Trace 저장 위치: logs\trace_jeonju.jsonl
```

관련 trace 샘플:

```text
sample_outputs/jeonju_trace_sample.jsonl
```
