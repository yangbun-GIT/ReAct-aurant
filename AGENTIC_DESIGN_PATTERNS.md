# Agentic Design Pattern 설명

## 개요

ReAct-aurant는 LLM에게 바로 "맛집 추천해줘"라고 묻는 구조가 아닙니다. Agent가 사용자 요청을 분석하고, 필요한 도구를 고른 뒤, 도구 호출 결과를 Observation으로 받아 최종 추천을 구성합니다.

핵심 실행 흐름:

```text
User Request
-> Plan and Parse
-> Thought
-> Action: MCP Tool Call
-> Observation
-> Reflection
-> Final Answer
```

## 1. ReAct Pattern

사용 이유:

사용자 조건에 맞는 맛집 추천은 단순 문장 생성이 아니라, 지역 해석, 장소 검색, 날씨 반영, 후보 검증, 결과 설명이 필요합니다. ReAct 패턴을 사용하면 Agent가 어떤 판단으로 어떤 도구를 호출했는지 Trace로 확인할 수 있습니다.

적용 방식:

- `react_client.py`에서 실행 루프를 관리합니다.
- 각 단계는 Thought, Action, Observation, Final Answer 흐름으로 기록됩니다.
- Action에는 MCP 도구 호출 이름과 입력값이 남습니다.
- Observation에는 도구 실행 결과가 남습니다.

예시:

```text
Thought: 요청 지역과 음식 종류를 분석한다.
Action: search_kakao_local_places
Observation: Kakao Local API 후보 목록 수신
Final Answer: 조건에 맞는 후보를 추천하고 근거를 설명한다.
```

## 2. Tool Use Pattern

사용 이유:

LLM의 내부 지식만으로는 최신 장소 정보, 거리, 날씨, API 검색 결과를 보장할 수 없습니다. 따라서 외부 도구를 호출해 근거 데이터를 확보합니다.

적용 방식:

- MCP 서버를 도구 제공자로 사용합니다.
- `env_context_server.py`: 날씨, 사용자 선호, 메모리
- `public_data_server.py`: Kakao Local API, TourAPI, 장소 링크 지표 보강
- `gourmet_db_server.py`: 후보 검색, 상세 조회, 랭킹

Trace에는 호출 도구 이름, 입력값, 실행 결과가 남습니다.

## 3. Plan-and-Solve Pattern

사용 이유:

사용자 요청은 보통 "전주 객사 근처에서 친구랑 저녁 먹기 좋은 곳"처럼 여러 조건이 섞여 있습니다. 이를 바로 검색하면 지역, 음식 종류, 목적, 거리 조건이 누락될 수 있습니다.

적용 방식:

- 자연어 요청을 지역, 음식 종류, 방문 목적, 거리, 날씨, 평점, 후기 수 조건으로 나눕니다.
- 지역은 전주 로컬 별칭과 상권 범위를 먼저 해석합니다. `전북대 근처`처럼 넓은 표현은 구정문·신정문 권역을 포함하고, `전북대 구정문 근처`처럼 좁은 표현은 해당 상권 중심 반경으로 제한합니다.
- 조건이 부족하면 기본값을 보완하되, 최종 답변에 보완 사실을 표시합니다.
- 분석된 조건을 바탕으로 도구 호출 순서를 정합니다.

## 4. Reflection Pattern

사용 이유:

검색 결과가 사용자 조건과 어긋날 수 있습니다. 예를 들어 술집 요청에 일반 식당이 나오거나, 평점 조건을 만족하지 못하는 후보가 나올 수 있습니다.

적용 방식:

- 후보의 지역, 업종, 거리, 평점, 후기 수, 영업 상태, 데이터 한계를 다시 점검합니다.
- 조건을 충족하지 못하면 추천에서 제외하거나 대안 검색을 제시합니다.
- 데이터가 관측되지 않은 값은 임의 생성하지 않고 한계로 표시합니다.

## 5. Memory Pattern

사용 이유:

사용자 선호는 추천 품질에 영향을 줍니다. "너무 비싸지 않은 곳", "친구랑 저녁", "비 오는 날" 같은 선호 조건을 이후 판단에 반영할 수 있어야 합니다.

적용 방식:

- 요청에서 드러난 선호를 메모리 도구에 저장합니다.
- 같은 실행 흐름 안에서 가격, 목적, 음식 선호를 후보 정렬에 반영합니다.
- 저장된 선호는 도구 Observation으로 Trace에 남습니다.

## 6. Multi-Agent 역할 분리

프로젝트 내부에서는 다음 역할을 분리해 동작합니다.

| 역할 | 설명 |
| --- | --- |
| Coordinator | 사용자 요청을 구조화 |
| Planner | 도구 호출 계획 수립 |
| Context Specialist | 날씨와 사용자 선호 수집 |
| Public Data Agent | Kakao/TourAPI 후보 조회 |
| Ranking Agent | 후보 점수화와 정렬 |
| Reflection Reviewer | 조건 충족 여부 재검토 |
| Final Answer Agent | 최종 답변 생성 |

이 구조 덕분에 추천 결과뿐 아니라 추천 과정도 Trace로 확인할 수 있습니다.
