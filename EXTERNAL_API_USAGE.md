# 외부 API 사용 방법

## 개요

프로젝트는 전주시 맛집 추천을 위해 Kakao Local API, TourAPI KorService2, OpenAI API, Open-Meteo를 사용합니다.

| API | 용도 | Key 필요 |
| --- | --- | --- |
| Kakao Local API | 장소 검색, 주소, 거리, 전화번호, 장소 링크 | 필요 |
| TourAPI KorService2 | 공공데이터 기반 전주시 음식점 후보 조회 | 필요 |
| OpenAI API | 요청 분석, 계획, Reflection, 최종 답변 생성 | 필요 |
| Open-Meteo | 전주 날씨 조회 | 불필요 |

API Key는 로컬 `.env`에만 입력합니다. `.env`는 GitHub에 올리지 않습니다.

## 1. Kakao Local API

가장 권장하는 장소 검색 경로입니다. 음식점, 카페, 술집, 빵집 등 실제 지도 장소 후보를 찾는 데 사용합니다.

설정 방법:

1. [Kakao Developers](https://developers.kakao.com/) 접속
2. 애플리케이션 생성
3. 앱 설정 > 앱 키에서 `REST API 키` 복사
4. 프로젝트 루트의 `.env`에 입력

```env
KAKAO_REST_API_KEY=발급받은_REST_API_KEY
```

실행 예시:

```powershell
.\.venv\Scripts\python react_client.py "전주 웨리단길 칵테일 바 추천" --data-source kakao --trace logs\trace_kakao.jsonl
```

주의:

- Kakao Local API 검색에는 REST API Key만 필요합니다.
- Kakao 로그인, Client Secret, 비즈니스 인증은 이 프로젝트의 Local API 검색에는 필요하지 않습니다.
- Kakao Local API는 특정 좌표와 반경을 기준으로 장소를 검색합니다. 객사, 객리단길, 전북대, 구정문, 신정문처럼 전주에서 로컬 상권명으로 쓰이는 지역은 `jeonju_gazetteer.py`의 기준 좌표와 반경을 먼저 사용하고, 사전에 없는 장소명만 Kakao 위치 검색으로 보정합니다.
- Kakao Local API 공식 응답에는 평점, 후기 수, 가격대 필드가 없습니다.
- 프로젝트는 Kakao 장소 링크/패널에서 관측 가능한 평점과 후기 수를 보강합니다.
- 관측되지 않은 값은 임의 생성하지 않고 데이터 한계로 표시합니다.

## 2. TourAPI KorService2

공공데이터포털의 무료 관광정보 API입니다. 비용 없이 전주시 음식점 후보를 조회하는 백업 경로로 사용합니다.

설정 방법:

1. [공공데이터포털](https://www.data.go.kr/) 접속
2. `한국관광공사_국문 관광정보 서비스_GW` 활용 신청
3. 일반 인증키 복사
4. 프로젝트 루트의 `.env`에 입력

```env
TOUR_API_SERVICE_KEY=발급받은_일반_인증키
TOUR_API_ENDPOINT=https://apis.data.go.kr/B551011/KorService2
```

실행 예시:

```powershell
.\.venv\Scripts\python react_client.py "전주 한옥마을 한식 맛집 추천" --data-source tourapi --trace logs\trace_tourapi.jsonl
```

사용 방식:

- 전주시 음식점 후보 조회
- `contentTypeId=39` 음식점 기준 사용
- 전북/전주 지역 코드 기준으로 조회
- 평점/후기 수/가격대가 공식 응답에 없으면 생성하지 않음

## 3. OpenAI API

GPT 기반 Agent 판단에 사용합니다.

역할:

- 사용자 요청 분석
- 검색 계획 생성
- 도구 Observation 검토
- Reflection 작성
- 최종 추천 답변 정리

설정:

```env
OPENAI_API_KEY=발급받은_OPENAI_API_KEY
OPENAI_MODEL=gpt-4.1-mini
```

API 비용을 쓰지 않으려면 `--no-llm` 옵션을 사용합니다.

```powershell
.\.venv\Scripts\python react_client.py "전주 객사 한식 맛집 추천" --data-source tourapi --no-llm
```

## 4. Open-Meteo

전주 날씨 조회에 사용합니다. 별도 API Key가 필요 없습니다.

사용 정보:

- 현재 기온
- 강수 여부
- 날씨 코드
- 날씨 기반 음식 추천 힌트

예시:

- 비 오는 날: 파전, 막걸리, 따뜻한 국물, 가까운 실내 좌석 선호
- 더운 날: 시원한 면류, 냉면, 카페, 빙수류 선호
- 추운 날: 국밥, 전골, 탕류, 따뜻한 실내 음식점 선호

날씨 API 호출에 실패하면 Agent가 Observation에 실패 내용을 기록하고 기본 날씨 컨텍스트로 대체합니다.

## 5. 실행 전 점검

`.env` 예시:

```env
OPENAI_API_KEY=
KAKAO_REST_API_KEY=
TOUR_API_SERVICE_KEY=
TOUR_API_ENDPOINT=https://apis.data.go.kr/B551011/KorService2
OPENAI_MODEL=gpt-4.1-mini
```

키가 들어간 `.env`는 GitHub에 올리지 않습니다.
