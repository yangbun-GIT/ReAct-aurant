# ReAct-aurant

`ReAct-aurant`는 OSS 과제4를 위한 Python 기반 맛집 추천 AI Agent 프로젝트입니다.

이 프로젝트는 사용자의 맛집 요청을 분석하고, 로컬 MCP 서버 2개를 호출해 날씨, 사용자 선호도, 맛집 후보 정보를 수집한 뒤 ReAct 흐름으로 최종 맛집 3곳을 추천합니다.

## 현재 구현 방향

- 맛집 검색 외부 API는 사용하지 않습니다.
- 비용 0원 조건과 과제 재현성을 위해 로컬 샘플 맛집 데이터셋을 사용합니다.
- 날씨 정보는 API key가 필요 없는 Open-Meteo를 우선 사용하고, 실패하면 mock 날씨 데이터로 대체합니다.
- GPT API는 선택 사항입니다. `OPENAI_API_KEY`가 없거나 호출이 실패해도 규칙 기반 fallback으로 실행됩니다.
- MCP 서버는 공식 오픈소스 MCP Python SDK를 사용합니다.

## 실행 환경

- Python 3.11 이상
- 권장: Python 3.13

## 설치

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 환경 변수

실제 API key는 `.env`에만 입력합니다. `.env`는 GitHub에 업로드되지 않습니다.

```powershell
copy .env.example .env
```

기본 과제 실행에는 Kakao, Naver, Google Places API key가 필요하지 않습니다.

## 실행

기본 테스트 프롬프트:

```powershell
python react_client.py --query "전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집을 찾아줘. 너무 비싸지 않고, 리뷰가 좋은 곳 위주로 3곳 추천해줘." --trace logs/trace_jeonju.jsonl
```

## 프로젝트 구조

```text
env_context_server.py   # 날씨와 사용자 선호도를 제공하는 MCP 서버
gourmet_db_server.py    # 맛집 샘플 데이터 검색과 정렬을 제공하는 MCP 서버
react_client.py         # Multi-Agent Coordinator와 ReAct 실행 클라이언트
requirements.txt        # 실행 환경 의존성
README.md               # 실행 및 제출 안내
```

## Agentic Design Pattern

구현 완료 후 이 섹션에 실제 적용 내용을 정리합니다.

- ReAct Pattern
- Tool Use Pattern
- Plan-and-Solve Pattern
- Reflection Pattern
- Memory Pattern

## 제출 제외 항목

다음 항목은 제출물과 GitHub에 포함하지 않습니다.

- `.env`
- `.venv`
- `__pycache__`
- `node_modules`
- API key, token, secret
