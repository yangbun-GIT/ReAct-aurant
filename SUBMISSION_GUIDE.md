# 실행 화면과 Trace 정리 가이드

## 실행 화면

웹 대시보드에서 실행 결과를 캡처하는 방식을 권장합니다.

실행:

```powershell
docker compose up --build
```

접속:

```text
http://127.0.0.1:18765/app
```

권장 테스트 문장:

```text
전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집을 찾아줘. 너무 비싸지 않고, 리뷰가 좋은 곳 위주로 3곳 추천해줘.
```

캡처하면 좋은 화면:

1. 질문 입력 영역
2. 최종 추천 탭
3. Trace 자연어 탭
4. Trace 코드 흐름 탭
5. 실행 로그 탭
6. Trace JSONL 탭

PDF로 정리할 때는 최종 추천 화면만 넣기보다, Trace 탭 중 하나를 함께 넣는 편이 좋습니다. 과제 핵심이 추천 결과보다 Agent가 어떤 방식으로 도구를 사용했는지 확인하는 것이기 때문입니다.

## 실행 로그

웹 실행 기록은 로컬 `logs/web_runs/<run_id>/`에 저장됩니다. 이 폴더는 Git 추적에서 제외됩니다.

CLI로 로그를 만들 때는 `--trace` 옵션을 사용합니다.

```powershell
.\.venv\Scripts\python react_client.py "전주 객사 근처 맛집 3곳 추천해줘" --data-source kakao --trace logs\trace_submit.jsonl
```

샘플 로그:

- `sample_outputs/jeonju_run_log.md`
- `sample_outputs/jeonju_trace_sample.jsonl`
- `sample_outputs/stage4_exception_run_log.md`

## ReAct Agent 도구 호출 Trace

Trace는 실행 화면 캡처나 실행 로그 PDF에 함께 포함해도 됩니다. 다만 단순 최종 추천 캡처만으로는 부족할 수 있으므로, 아래 내용이 보이도록 정리하는 것이 좋습니다.

Trace에 보여야 하는 내용:

- Agent의 판단 과정
- 호출한 도구 이름
- 도구 입력값
- 도구 실행 결과
- 최종 추천 결과

웹 대시보드 기준으로는 다음 탭을 사용합니다.

| 탭 | 용도 |
| --- | --- |
| `Trace 자연어` | 사람이 읽기 쉬운 판단 과정 설명 |
| `Trace 코드 흐름` | 어떤 코드 흐름과 도구가 실행됐는지 확인 |
| `실행 로그` | 실행 상태와 예외 처리 확인 |
| `Trace JSONL` | 원본 도구 호출 Trace 확인 |

PDF 제출을 생각한다면 다음 구성이 가장 깔끔합니다.

1. 최종 추천 화면 1장
2. Trace 자연어 화면 1장
3. Trace JSONL 또는 실행 로그 화면 1장

JSONL 원본 파일을 별도로 제출할 수 있으면 `sample_outputs/jeonju_trace_sample.jsonl` 형식처럼 제출하면 됩니다.

## 별도 설명 문서

자세한 설명은 아래 문서로 분리했습니다.

| 문서 | 내용 |
| --- | --- |
| `AGENTIC_DESIGN_PATTERNS.md` | 사용한 Agentic Design Pattern, 사용 이유, 적용 방식 |
| `EXTERNAL_API_USAGE.md` | 외부 API 설정 방법과 사용 방식 |
| `EXECUTION_ENVIRONMENT.md` | 실행 환경과 설치 방법 |

Google Docs로 정리할 경우 위 문서 내용을 각각 복사해 별도 문서로 만들면 됩니다.

## 공개 저장소 제외 항목

아래 항목은 GitHub에 올리지 않습니다.

- `.env`, `.env.*`
- `.venv`, `venv`, `env`
- `__pycache__`, `*.pyc`
- `node_modules`
- `logs`, `data/cache`
- `docs`
- `.pytest_cache`
- `*.zip`, `*.log`, `trace_*.jsonl`, `run_*.txt`

`git ls-files` 결과에 위 항목이 포함되어 있으면 제거해야 합니다.
