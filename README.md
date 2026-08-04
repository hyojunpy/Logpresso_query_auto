# 로그프레소 자연어 쿼리 생성기

이 프로젝트는 `docs/로그프레소 쿼리.docx`를 인덱싱하고, 한국어 자연어 요청을 로그프레소 쿼리 초안으로 변환합니다. 생성된 쿼리는 문서 인덱스 기반으로 검증하며, 부족한 테이블명이나 필드명은 임의로 만들지 않고 확인 질문으로 반환합니다.

## 지원 기능

- DOCX 문단과 표 추출
- SQLite 기반 문서 인덱스
- BM25 계열 로컬 검색
- 규칙 기반 자연어 의도 추출
- Mock, OpenAI, Ollama provider 인터페이스
- 쿼리 생성, 검증, 문서 근거 표시
- FastAPI Swagger와 Streamlit UI
- 쿼리 자동 실행 없음

현재 자연어 생성기는 다음 요청 유형을 지원합니다.

- 테이블 조회와 기간 지정: `최근 24시간`, `어제`, `YYYY-MM-DD부터 YYYY-MM-DD까지`
- 문자열, IP, 숫자 비교, 포함 검색 필터
- `stats`, `timechart`, `rollup` 기반 건수/합계/평균/비율 집계
- `rename`, `fields`, `eval` 기반 필드명 변경, 출력 필드 선택, 계산 필드
- 고유값/고유 개수 조회
- 그룹별 첫 번째/마지막 대표 로그: `first(line)`, `last(message)`
- `fulltext` 전체 텍스트 검색
- `set`과 `$()`를 이용한 동적 기간 매개변수 예제

## 설치

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
```

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## 환경 변수

`.env.example`을 참고해 `.env`를 만드십시오.

```env
LLM_PROVIDER=mock
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
```

API 키가 없어도 `mock` 모드에서 문서 검색, 예제 생성, UI 확인이 가능합니다.

## 문서 인덱스 생성

```bash
python scripts/build_index.py
```

문서 위치:

```text
docs/로그프레소 쿼리.docx
```

문서 변경 시 `/api/v1/documents/reindex` 또는 Streamlit 사이드바의 다시 인덱싱 버튼을 사용하십시오.

## FastAPI 실행

```bash
uvicorn app.api.main:app --reload --port 8000
```

Swagger:

```text
http://localhost:8000/docs
```

주요 API:

- `GET /api/v1/health`
- `POST /api/v1/documents/reindex`
- `GET /api/v1/documents/status`
- `POST /api/v1/query/generate`
- `POST /api/v1/query/validate`
- `GET /api/v1/commands/search?q=table`
- `GET /api/v1/commands/{command_name}`

### 생성 응답 상태

- `generated`: 쿼리가 생성되었고 검증을 통과했습니다.
- `needs_clarification`: 테이블명, 필드명, 기간, limit 등 필수 정보가 부족합니다. `questions`에 확인 질문이 들어갑니다.
- `unsupported`: 문서 인덱스 근거가 없거나 검증 실패를 복구하지 못했습니다. 이 경우 `query`는 `null`입니다.

확인 질문 예시:

```json
{
  "request": "에러 로그 보여줘",
  "context": {}
}
```

응답:

```json
{
  "status": "needs_clarification",
  "query": null,
  "questions": [
    "조회할 로그프레소 테이블 이름은 무엇인가요?",
    "필터에 사용할 필드명과 값은 무엇인가요?"
  ]
}
```

검증 실패 예시:

```json
{
  "query": "unknown firewall_logs"
}
```

응답에는 `valid=false`와 `errors`가 포함됩니다. 검증 실패한 쿼리는 생성 API에서 `generated`로 반환하지 않습니다.

검증기는 다음 오류와 경고를 확인합니다.

- 알 수 없는 명령어와 함수
- 명령어별 알 수 없는 옵션
- 빈 파이프 구간과 첫 명령어 누락
- 괄호, 서브쿼리 괄호, 따옴표 쌍
- `duration`과 `from/to`의 동시 사용
- `table`, `fulltext`, `stats` 계열의 필수 매개변수 누락
- 관리자 권한이 필요할 수 있는 명령어
- 주석 `#` 뒤 공백 규칙

문자열 안의 `|`, `#`, `duration=...`, `fake_func(...)` 같은 내용은 실제 문법으로 오해하지 않도록 제외합니다.

## Streamlit 실행

```bash
streamlit run ui/streamlit_app.py
```

Windows에서 가상환경을 만든 뒤 한 번에 실행하려면:

```bat
scripts\start_all.bat
```

이미 서버가 떠 있어도 `scripts\start_all.bat`는 `8000`, `8501` 포트를 정리한 뒤 새 API/UI를 가상환경 Python으로 다시 시작합니다. 로그는 `data/api.log`, `data/streamlit.log`에 남습니다.

Codex 샌드박스 안에서 재시작할 때 `Access denied`가 나오면 기존 서버 프로세스를 종료할 권한이 부족한 상태입니다. 이 경우 승인된 권한으로 `python scripts/restart_services.py`를 실행하거나, 일반 Windows 터미널에서 `scripts\start_all.bat`를 실행하십시오.

## 예제 요청

```json
{
  "request": "최근 24시간 동안 firewall_logs에서 출발지 IP별 차단 건수를 집계해서 많은 순으로 20개 보여줘",
  "context": {
    "product": "ENT",
    "version": null,
    "known_tables": ["firewall_logs"],
    "known_fields": ["src_ip", "action", "_time"]
  }
}
```

예상 쿼리 형태:

```text
table duration=24h firewall_logs
| search action == "deny"
| stats count by src_ip
| sort -count
| limit 20
```

추가 예시:

```text
firewall_logs의 src_ip를 할당ip로 rename해줘
```

```text
table firewall_logs
| rename src_ip as 할당ip
```

```text
최근 24시간 동안 전체 테이블에서 1.2.3.4 포함 로그 검색
```

```text
fulltext duration=24h "1.2.3.4"
```

```text
최근 7일간 YOUR_TABLE을 동적으로 조회하는 매개변수 예제를 만들어줘
```

```text
set from=ago("7d")
| set to=str(now())
| table from=$("from") to=$("to") YOUR_TABLE
```

## 테스트

```bash
pytest
```

정상 기준:

```text
139 passed
```

`pytest`가 없는 런타임에서는 표준 라이브러리 테스트도 실행할 수 있습니다.

```bash
python -m unittest discover -s tests
```

## Docker

```bash
docker compose up --build
```

서비스:

- API: `http://localhost:8000`
- UI: `http://localhost:8501`

`docs`와 `data` 디렉터리는 볼륨으로 연결됩니다. API 키는 이미지에 포함하지 않고 환경 변수로 주입합니다.
`.env`가 없어도 compose 기본값으로 `LLM_PROVIDER=mock` 모드가 사용됩니다. Ollama를 컨테이너에서 호출하려면 기본값은 `http://host.docker.internal:11434`입니다.

## 보안 및 제약

이 초기 버전은 쿼리 생성과 검증만 제공합니다. 사용자의 명시적인 별도 구현 없이 로그프레소 서버에서 쿼리를 자동 실행하지 않습니다.

다음 유형은 경고 또는 확인 질문 대상입니다.

- 관리자 권한 필요 명령
- 파일 시스템 접근
- 외부 DB, FTP, SFTP 연결
- 데이터 저장 또는 변경 가능 명령
- 기간 없는 대규모 조회
- 모든 테이블 대상 전체 텍스트 검색
- 제한 없는 대량 결과

비밀번호, API 키, 인증 정보는 로그에 기록하지 않아야 합니다.
