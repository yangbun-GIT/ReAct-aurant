# 실행 환경 정리

## 기본 환경

| 항목 | 내용 |
| --- | --- |
| OS | Windows, Linux, macOS 실행 가능 |
| Python | 3.11 이상 권장, 검증 환경은 Python 3.13 |
| 실행 방식 | CLI 또는 Docker 기반 웹 대시보드 |
| 저장 위치 | 실행 로그는 `logs/`, 웹 실행 기록은 `logs/web_runs/` |

`logs/`, `.env`, `.venv`는 제출/업로드 대상이 아닙니다.

## Python 패키지

`requirements.txt` 기준으로 설치합니다.

| 패키지 | 용도 |
| --- | --- |
| `mcp` | MCP 서버/클라이언트 구현 |
| `pydantic` | 데이터 모델 검증 |
| `python-dotenv` | 로컬 `.env` 로드 |
| `httpx` | 외부 API HTTP 요청 |
| `openai` | GPT 기반 Agent 판단/Reflection/답변 생성 |

설치 명령:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 환경 변수

`.env.example`을 복사해 `.env`를 만들고 로컬에서만 값을 입력합니다.

| 변수 | 필수 여부 | 설명 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 선택 | GPT Agent 모드 사용 시 필요 |
| `KAKAO_REST_API_KEY` | Kakao 모드 사용 시 필요 | Kakao Local API REST API Key |
| `TOUR_API_SERVICE_KEY` | TourAPI 모드 사용 시 필요 | 공공데이터포털 TourAPI 일반 인증키 |

## CLI 실행

```powershell
.\.venv\Scripts\python react_client.py "전주 객사 근처 맛집 3곳 추천해줘" --data-source kakao --trace logs\trace_required.jsonl
```

비용 없는 실행:

```powershell
.\.venv\Scripts\python react_client.py "전주 객사 한식 맛집 추천" --data-source tourapi --no-llm --trace logs\trace_no_llm.jsonl
```

## Docker 실행

```powershell
docker compose up --build
```

접속 주소:

```text
http://127.0.0.1:18765/app
```

종료:

```powershell
docker compose down
```
