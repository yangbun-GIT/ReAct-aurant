# ReAct-aurant 문서 인덱스

이 디렉터리는 과제 구현 중 참조해야 하는 문서를 모아 둡니다.

## 먼저 읽을 문서

1. [DEVELOPMENT_PROMPT.md](../DEVELOPMENT_PROMPT.md)
   - 프로젝트 개발 원칙, 아키텍처 경계, 구현 순서, 검증 정책을 정의합니다.
2. [ASSIGNMENT_REQUIREMENTS.md](ASSIGNMENT_REQUIREMENTS.md)
   - 과제4에서 반드시 구현해야 하는 요구사항과 제출 기준을 체크리스트로 정리합니다.
3. [README.md](../README.md)
   - 구현 완료 후 실행 방법과 제출 안내를 담는 최종 사용자 문서입니다. 아직 구현 전이면 없을 수 있습니다.

## 문서 갱신 규칙

- 과제 요구사항 해석이나 구현 범위가 바뀌면 `ASSIGNMENT_REQUIREMENTS.md`를 먼저 갱신합니다.
- 개발 원칙, 필수 파일, 검증 정책이 바뀌면 `DEVELOPMENT_PROMPT.md`도 함께 갱신합니다.
- 구현 완료 후 실행 방법, Trace 확인 방법, 사용한 Agentic Design Pattern 설명은 루트 `README.md`에 정리합니다.

## Git 작업 규칙

- 원격 저장소: `https://github.com/yangbun-GIT/ReAct-aurant.git`
- 의미 있는 작업 단위가 완료되면 커밋합니다.
- 커밋 제목은 한국어로 작성합니다.
- 커밋 본문은 필요할 때만 짧게 작성합니다.
- `.venv`, `__pycache__`, `node_modules`, `.env`, API key, token, secret, 실행 로그 원본은 커밋하지 않습니다.
