# 제출 자료 정리

## 1. 소스 코드

GitHub 공개 repo 주소는 `REPOSITORY_URL.txt`에 정리했습니다.

```text
https://github.com/yangbun-GIT/ReAct-aurant
```

제출 제외 대상:

- `.env`, `.env.*`
- `.venv`, `venv`, `env`
- `__pycache__`, `*.pyc`
- `node_modules`
- `logs`, `data/cache`
- `docs`
- `*.zip`, `*.log`, `trace_*.jsonl`, `run_*.txt`

실제 API Key는 `.env`에만 둡니다. `.env.example`에는 빈 값만 제공합니다.

## 2. 실행 화면 또는 실행 로그

다음 중 하나 이상을 제출하면 됩니다.

### 웹 화면 캡처

Docker 실행 후 `http://127.0.0.1:18765/app`에 접속해 아래 화면을 캡처합니다.

1. 질문 입력 화면
2. 최종 추천 탭
3. Trace 자연어 탭
4. Trace JSONL 또는 실행 로그 탭

필수 테스트 문장:

```text
전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집을 찾아줘. 너무 비싸지 않고, 리뷰가 좋은 곳 위주로 3곳 추천해줘.
```

### 파일 로그

CLI로 실행하면 Trace 파일을 만들 수 있습니다.

```powershell
.\.venv\Scripts\python react_client.py "전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집을 찾아줘. 너무 비싸지 않고, 리뷰가 좋은 곳 위주로 3곳 추천해줘." --data-source kakao --trace logs\trace_required.jsonl
```

제출 예시 파일:

- `sample_outputs/jeonju_run_log.md`
- `sample_outputs/jeonju_trace_sample.jsonl`

## 3. 사용한 Agentic Design Pattern

| 패턴 | 사용 이유 | 적용 방식 |
| --- | --- | --- |
| ReAct | Agent가 생각, 도구 호출, 관찰, 최종 답변을 단계적으로 수행해야 함 | `react_client.py` 실행 루프에서 Thought, Action, Observation, Final Answer 흐름을 Trace에 기록 |
| Tool Use | 맛집 추천에 필요한 정보가 LLM 내부 지식만으로는 부족함 | MCP 도구로 날씨, 사용자 선호, Kakao/TourAPI 검색, 상세 조회, 랭킹을 호출 |
| Plan-and-Solve | 자연어 요청을 바로 추천하지 않고 조건별로 분해해야 함 | 지역, 음식 종류, 목적, 거리, 평점, 후기 수, 가격대 조건으로 나눈 뒤 검색 계획 생성 |
| Reflection | 추천 결과가 조건에 맞는지 스스로 재검토해야 함 | 추천 후보의 지역/업종/평점/후기/영업 상태/데이터 한계를 검토하고 부족하면 대안 제시 |
| Memory | 사용자 선호가 반복 추천에 영향을 줄 수 있음 | 가격 선호, 음식 선호, 방문 목적을 메모리 도구로 저장하고 이후 추천에 반영 |

핵심은 단순히 GPT에게 맛집을 묻는 구조가 아니라, Agent가 요청을 분석하고 도구를 호출한 뒤 관찰 결과를 근거로 답변한다는 점입니다.

## 4. ReAct Agent 도구 호출 Trace 작성 방법

Trace에는 아래 내용이 드러나야 합니다.

- Agent의 판단 과정
- 호출한 도구 이름
- 도구 입력값
- 도구 실행 결과
- 최종 추천 결과

CLI 실행 시 `--trace` 옵션으로 JSONL Trace를 저장합니다.

```powershell
.\.venv\Scripts\python react_client.py "전주 객사 근처 맛집 3곳 추천해줘" --data-source kakao --trace logs\trace_submit.jsonl
```

웹 대시보드에서는 실행 후 아래 탭을 확인합니다.

- `Trace 자연어`: 사람이 읽기 쉬운 단계별 설명
- `Trace 코드 흐름`: 코드 실행 흐름 중심 설명
- `Trace JSONL`: 제출용 원본 Trace
- `실행 로그`: 실행 상태와 예외 처리 기록

## 5. 외부 API 사용 방법

### Kakao Local API

가장 권장하는 장소 검색 API입니다. 음식점, 카페, 술집, 빵집 등 실제 지도 장소 후보를 찾는 데 사용합니다.

설정 방법:

1. [Kakao Developers](https://developers.kakao.com/) 접속
2. 애플리케이션 생성
3. 앱 설정 > 앱 키에서 `REST API 키` 복사
4. 로컬 `.env`에 입력

```env
KAKAO_REST_API_KEY=발급받은_REST_API_KEY
```

실행:

```powershell
.\.venv\Scripts\python react_client.py "전주 웨리단길 칵테일 바 추천" --data-source kakao --trace logs\trace_kakao.jsonl
```

주의:

- Kakao Local API 사용에는 REST API Key만 필요합니다.
- Kakao 로그인, Client Secret, 비즈니스 인증은 이 프로젝트의 Local API 검색에는 필요하지 않습니다.
- Kakao Local API 공식 응답에는 평점/후기 수/가격대 필드가 없습니다.
- 프로젝트는 장소 링크/패널에서 관측 가능한 평점과 후기 수를 보강하되, 관측되지 않은 값은 생성하지 않습니다.

### TourAPI KorService2

공공데이터포털의 무료 관광정보 API입니다. 비용 없이 전주시 음식점 후보를 조회하는 백업 경로로 사용합니다.

설정 방법:

1. [공공데이터포털](https://www.data.go.kr/) 접속
2. `한국관광공사_국문 관광정보 서비스_GW` 활용 신청
3. 일반 인증키를 복사
4. 로컬 `.env`에 입력

```env
TOUR_API_SERVICE_KEY=발급받은_일반_인증키
TOUR_API_ENDPOINT=https://apis.data.go.kr/B551011/KorService2
```

실행:

```powershell
.\.venv\Scripts\python react_client.py "전주 한옥마을 한식 맛집 추천" --data-source tourapi --trace logs\trace_tourapi.jsonl
```

### OpenAI API

GPT 기반 요청 분석, 계획 수립, Reflection, 최종 답변 생성을 위해 사용합니다.

```env
OPENAI_API_KEY=발급받은_OPENAI_API_KEY
OPENAI_MODEL=gpt-4.1-mini
```

비용을 쓰지 않으려면 `--no-llm` 옵션을 사용합니다.

```powershell
.\.venv\Scripts\python react_client.py "전주 객사 한식 맛집 추천" --data-source tourapi --no-llm
```

### Open-Meteo

전주 날씨 조회에 사용합니다. 별도 API Key가 필요 없습니다.

## 6. 제출 전 확인 명령

```powershell
python -m unittest discover -s tests
python -m py_compile react_client.py public_data_server.py gourmet_db_server.py env_context_server.py web_dashboard.py
git status --short
git ls-files
```

`git ls-files` 결과에 `.env`, `.venv`, `__pycache__`, `node_modules`, `logs`가 있으면 제출 전에 제거해야 합니다.
