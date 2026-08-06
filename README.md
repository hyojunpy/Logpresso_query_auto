# Logpresso Query Assistant

Logpresso Query Assistant는 자연어 요청을 Logpresso 쿼리 초안으로 변환하는 FastAPI + Streamlit 기반 도구입니다. 제공된 Logpresso 문서를 BM25 방식으로 검색하고, 규칙 기반 파서와 선택적 LLM provider를 조합해 쿼리를 생성합니다.

이 프로젝트는 **쿼리를 자동 실행하지 않습니다.** 생성, 검증, 품질 진단, 실행 준비 정보까지만 제공하며, 사용자가 결과를 검토한 뒤 Logpresso에서 직접 실행하는 흐름을 전제로 합니다.

## 주요 기능

- 자연어 기반 테이블, 필드, 기간, 필터, 정렬, limit 추출
- `table`, `fulltext`, `logger`, `stream`, `stats`, `timechart`, `rollup`, `fields`, `rename`, `eval`, `join`, `streamjoin` 조합 생성
- 다중 테이블 join, 조인 전 필터, 오른쪽 서브쿼리 필터 지원
- JSON 기반 테이블/필드 카탈로그와 요청별 임시 스키마 지원
- 문법, 카탈로그, 타입, 조인 키, 성능, 안전성, 완성도 진단
- 위험도와 실행 준비 상태 표시. 실제 실행은 수행하지 않음
- Streamlit UI에서 결과 편집 및 재검증, 피드백 저장, 카탈로그 편집/다운로드
- Gold Set 기반 회귀 평가와 GitHub Actions CI

## 지원 예시

```text
최근 24시간 firewall_logs에서 출발지 IP별 차단 건수를 많은 순으로 20개 보여줘
```

```logpresso
table duration=24h firewall_logs
| search action == "deny"
| stats count by src_ip
| sort -count
| limit 20
```

```text
firewall_logs의 src_ip와 firewall_djt의 dst_ip를 src_ip를 기준으로 left join 해줘
```

```logpresso
table firewall_logs
| eval _join_key = src_ip
| join type=left _join_key [
    table firewall_djt
    | eval _join_key = dst_ip
]
```

요청에 실제 테이블과 필드명을 함께 주면 정확도가 높아집니다.

```text
인사와 방화벽을 IP로 left join해줘
추가 조건: 테이블은 insa, firewall / 조인키는 둘 다 ip
```

## 구성

```text
app/
  api/             FastAPI 라우트
  models/          Pydantic 요청/응답 모델
  services/        파서, 생성기, 검증기, 검색, 카탈로그, 진단 서비스
docs/              Logpresso 기준 문서 DOCX
ui/                Streamlit UI
tests/             단위, API, UI, Gold Set 테스트
scripts/           인덱싱 및 서비스 실행 스크립트
data/              SQLite 인덱스, 카탈로그, 로컬 피드백 저장소
```

## 요구 사항

- Python 3.12 이상
- 선택 사항: Docker Desktop
- 선택 사항: OpenAI API 키 또는 로컬 Ollama 서버

## 설치

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -c requirements.lock -e .[dev]
```

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -c requirements.lock -e '.[dev]'
```

## 환경 변수

`.env.example`을 참고해 필요한 값을 설정합니다. 기본값은 외부 모델 호출이 없는 `mock` 모드입니다.

```env
LLM_PROVIDER=mock
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
RETRIEVAL_LIMIT=8
LOG_LEVEL=INFO
CORS_ALLOWED_ORIGINS=http://localhost:8501,http://127.0.0.1:8501
ENABLE_DEV_EVALUATION=false
ENABLE_LLM_INTENT_FALLBACK=true
```

`LLM_PROVIDER` 값:

- `mock`: 외부 LLM 없이 규칙 및 문서 검색 기반 생성
- `openai`: `OPENAI_API_KEY` 필요
- `ollama`: `OLLAMA_BASE_URL`의 로컬 Ollama 서버 사용

## 문서 인덱싱

기준 문서를 `docs/로그프레소 쿼리.docx`에 둔 뒤 실행합니다.

```powershell
.\.venv\Scripts\python.exe scripts\build_index.py
```

문서가 바뀌면 Streamlit 사이드바의 재인덱싱 버튼 또는 아래 API를 사용합니다.

```text
POST /api/v1/documents/reindex
```

## 실행

### 로컬 실행

터미널 두 개에서 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload
```

```powershell
.\.venv\Scripts\python.exe -m streamlit run ui\streamlit_app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
```

- UI: http://127.0.0.1:8501
- API Swagger: http://127.0.0.1:8000/docs

기존 서버를 정리하고 다시 띄우려면 다음 스크립트를 사용합니다.

```powershell
.\.venv\Scripts\python.exe scripts\restart_services.py
```

Windows에서 다른 계정 소유 프로세스 때문에 `Access denied`가 발생하면 관리자 PowerShell에서 실행해야 할 수 있습니다.

### Docker Compose

```bash
docker compose up --build
```

`docs`와 `data`는 컨테이너에 볼륨으로 연결됩니다. Docker 환경에서 Ollama를 호스트에서 실행 중이면 기본 `OLLAMA_BASE_URL`을 `http://host.docker.internal:11434`로 설정할 수 있습니다.

## Streamlit 사용법

1. 자연어 요청을 입력하고 `쿼리 생성`을 누릅니다.
2. 필요하면 사이드바에 테이블/필드 힌트나 JSON 카탈로그를 제공합니다.
3. 요청별 임시 스키마는 아래 형식으로 입력합니다.

```text
firewall_logs: src_ip, action, _time
insa: ip, employee_id
```

4. 생성 쿼리, 문서 근거, 스키마 검증, 품질 진단, 위험도, 실행 준비 상태를 확인합니다.
5. 생성 쿼리 편집 영역에서 수정 후 재검증할 수 있습니다.

사이드바의 카탈로그 편집기에서는 테이블, 필드, 타입, 설명을 행 단위로 저장하거나 JSON으로 내려받을 수 있습니다. 저장 카탈로그는 `data/catalog.json`에 기록됩니다.

## API

주요 엔드포인트:

| Method | Path | 설명 |
| --- | --- | --- |
| `GET` | `/api/v1/health` | 상태 확인 |
| `POST` | `/api/v1/query/generate` | 자연어 요청으로 쿼리 생성 |
| `POST` | `/api/v1/query/validate` | 문법 및 스키마 검증 |
| `POST` | `/api/v1/query/analyze` | 검증, 품질, 실행 준비 정보 분석 |
| `GET`, `PUT` | `/api/v1/catalog` | 로컬 카탈로그 조회 및 저장 |
| `POST` | `/api/v1/feedback` | 생성 결과 피드백 저장 |
| `GET` | `/api/v1/feedback/summary` | 피드백 요약 |
| `GET` | `/api/v1/documents/status` | 문서 인덱스 상태 |
| `POST` | `/api/v1/documents/reindex` | 문서 재인덱싱 |

생성 요청 예시:

```json
{
  "request": "최근 24시간 firewall_logs에서 src_ip별 차단 건수를 20개 보여줘",
  "context": {
    "known_tables": ["firewall_logs"],
    "known_fields": ["src_ip", "action", "_time"]
  }
}
```

응답에는 기존 생성 정보 외에 다음 확장 정보가 포함됩니다.

- `schema_validation`: 테이블/필드/타입 기반 검증 결과
- `quality`: 점수, 위험도, 진단 코드, 점수 감점 근거
- `execution_preview`: 실행 준비 상태와 확인 필요 사유

## 카탈로그 검증

카탈로그에는 테이블, 필드, 타입, 설명을 정의할 수 있습니다.

```json
{
  "source": "manual",
  "tables": [
    {
      "table_name": "firewall_logs",
      "fields": [
        {"field_name": "src_ip", "field_type": "ip"},
        {"field_name": "action", "field_type": "string"},
        {"field_name": "_time", "field_type": "time"}
      ]
    }
  ]
}
```

요청별 임시 스키마는 저장 카탈로그를 바꾸지 않습니다. 해당 스키마를 기준으로 생성하되 `request_schema_unverified` 경고를 남깁니다.

## 품질 및 실행 준비 정책

다음 항목을 진단합니다.

- 기간 또는 결과 제한 누락
- 범위가 넓은 Fulltext 검색
- 과도한 결과 제한
- 조인 전 필터 부재와 무제한 조인
- 집계 정렬, 시간 차트 버킷, 모순 필터
- 관리자 권한 또는 데이터 전달 가능성이 있는 명령

점수는 `safety_score`, `performance_score`, `completeness_score`, `confidence_score`로 반환됩니다. `execution_preview`는 `not_requested`, `preview_ready`, `requires_confirmation`, `blocked`, `unsupported` 중 하나로 표시됩니다.

## 실험적 eval

기본 생성은 문서와 카탈로그 근거를 우선합니다. 다만 사용자가 명시적으로 자유로운 조건부 계산을 요청하면 실험적 `eval` 표현식을 생성할 수 있습니다.

예를 들어 join 뒤 매칭 여부 컬럼을 요청하면 다음과 유사한 초안을 생성합니다.

```logpresso
| eval insa_ip_match = if(isnull(insa_ip), "unmatched", "matched")
```

문서 인덱스에 없는 함수는 `unknown_function` 경고가 표시될 수 있습니다. 실제 Logpresso 환경에서 함수 지원 여부를 확인한 뒤 사용하세요.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall app tests ui -q
```

브라우저 회귀 테스트는 Playwright와 Chromium 설치가 필요합니다.

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
$env:RUN_BROWSER_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest tests\test_streamlit_browser.py -q
```

## 보안 및 제약

- 이 애플리케이션은 Logpresso, DB, FTP, SFTP 등에 실제로 연결하거나 쿼리를 실행하지 않습니다.
- API 인증 체계는 아직 제공하지 않습니다. 카탈로그 관리 API를 외부에 노출하기 전 인증 및 권한 제어를 추가해야 합니다.
- 피드백 저장소는 기본적으로 원문 요청과 생성 쿼리를 저장하지 않습니다.
- `docs/로그프레소 쿼리.docx`의 공개 및 재배포 권한은 별도로 확인해야 합니다.

## 라이선스

이 저장소에는 아직 명시적인 오픈소스 라이선스가 없습니다. 외부 배포 또는 재사용 전 코드 소유자와 기준 문서의 권리 상태를 확인하세요.
