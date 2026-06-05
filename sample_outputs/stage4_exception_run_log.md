# 4단계 예외 처리 실행 로그

이 문서는 `에러 대응 및 예외 처리` 단계 검증용 실행 로그입니다. 모든 명령은 비용이 들지 않도록 `--no-llm --data-source local`로 실행했습니다.

## 검증 명령

```powershell
.\.venv\Scripts\python react_client.py "파이썬 코드 알려줘" --no-llm --data-source local --trace logs\stage4_unrelated_trace.jsonl
.\.venv\Scripts\python react_client.py "추천해줘" --no-llm --data-source local --trace logs\stage4_insufficient_trace.jsonl
.\.venv\Scripts\python react_client.py "전주 객사 우주젤리 맛집 추천해줘" --no-llm --data-source local --trace logs\stage4_no_results_trace.jsonl
.\.venv\Scripts\python react_client.py "부산 서면 근처에서 친구랑 저녁 먹기 좋은 맛집 추천해줘" --no-llm --data-source local --trace logs\stage4_unsupported_region_trace.jsonl
.\.venv\Scripts\python react_client.py "전주 객사 성적인 맛집 추천해줘" --no-llm --data-source local --trace logs\stage4_safety_trace.jsonl
.\.venv\Scripts\python react_client.py "전주 객사에서 살인적인 매운 맛집 추천해줘" --no-llm --data-source local --trace logs\stage4_contextual_safety_trace.jsonl
```

## 예외 처리 결과

| 상황 | Agent Observation | Agent 대안 |
| --- | --- | --- |
| 존재하지 않거나 지원하지 않는 지역 | `search_restaurants`가 `status=error`, `지원하지 않는 지역` Observation 반환 | Reflection 후 과제 기본 지역인 `전주 객사`로 재검색 |
| 검색 결과가 없는 음식 종류 | `우주젤리` 조건으로 `count=0` Observation 반환 | 리뷰/평점 조건 완화 후에도 후보가 없으면 음식 종류 조건을 해제하고 재검색 |
| 음식 종류가 모호한 경우 | `Input Guard Agent`가 `ambiguous_food_type` warning 기록 | 특정 메뉴로 제한하지 않고 전체 음식점 후보를 검색 |
| 사용자의 조건이 부족한 경우 | `Input Guard Agent`가 `insufficient_conditions` warning 기록 | 지역, 목적, 가격대 등 누락 조건을 기본값으로 보완하고 최종 답변에 표시 |
| API 호출 실패 | MCP `tools/call/result`에 `status=error` Observation 기록 | 공공데이터 실패 시 로컬 샘플 데이터셋으로 fallback |
| 맛집과 관계없는 입력 | `Input Guard Agent`가 `unrelated_request` error 기록 | 도구를 호출하지 않고 전주 맛집 요청 예시를 제시 |
| 선정적/폭력적/불법적 요청 | `Input Guard Agent`가 `safety_blocked` error 기록 | 도구를 호출하지 않고 안전한 맛집 추천 입력 형식으로 유도 |
| 맛집 맥락의 과한 표현 | `unsafe_expression_sanitized` warning 기록 | 표현은 추천 조건에서 제외하고 지역, 음식, 거리, 가격 조건만 반영 |

## 대표 Trace 흐름

무관 입력:

```text
Plan-and-Solve -> validate_user_request Observation(error) -> Reflection -> Final Answer
```

후보 없음:

```text
validate_user_request Observation(warning)
-> search_restaurants Observation(count=0)
-> 조건 완화 search_restaurants Observation(count=0)
-> 음식 종류 해제 Reflection
-> Fallback Action search_restaurants Observation(count=8)
-> rank_restaurants
-> get_restaurant_detail
-> Final Answer
```

지원하지 않는 지역:

```text
validate_user_request Observation(warning)
-> get_weather_context Observation(error)
-> Fallback Action get_weather_context(전주 객사)
-> search_restaurants Observation(error)
-> Fallback Action search_restaurants(전주 객사)
-> Final Answer
```

이 흐름은 단순 오류 출력이 아니라, Agent가 Observation을 보고 Reflection으로 대안을 선택한 뒤 다음 Action을 수행하도록 구성되어 있습니다.
