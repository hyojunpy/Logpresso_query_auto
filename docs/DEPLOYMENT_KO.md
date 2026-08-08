# 배포와 운영 안내

## 안전한 사용 범위

이 서비스는 Logpresso 쿼리 초안의 생성과 검증만 수행합니다. 고객사
Logpresso 서버 접속, 쿼리 실행, 스케줄 생성, 알림 발송은 구현하지 않았습니다.
생성된 쿼리는 검토 후 사용자가 Logpresso에서 직접 실행해야 합니다.

## 빠른 시작

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -c requirements.lock -e .[dev]
.\.venv\Scripts\python.exe -m streamlit run ui\streamlit_app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
```

브라우저에서 `http://127.0.0.1:8501`을 엽니다. API가 필요하면 별도
PowerShell에서 아래 명령을 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

## 카탈로그 없이 시작하기

카탈로그를 등록하지 않아도 방화벽, 로그인, 웹 오류, 인사 IP 같은 일반적인
업무 표현은 초안을 만들 수 있습니다. 이 경우 화면의 추론 가정과 검증 경고를
확인해야 합니다. 실제 테이블과 필드명이 다르면 생성 결과의 편집 영역에서
수정하고 재검증한 뒤, 검증을 통과한 테이블·필드를 이번 세션에만 기억시킬 수
있습니다.

## 고객사 카탈로그 파일을 받을 수 있는 경우

CSV는 UTF-8 인코딩과 다음 헤더를 사용합니다.

```text
table_name,field_name,field_type,description
```

선택 열은 `node`, `namespace`, `table_description`, `nullable`이며, `nullable`은
`true` 또는 `false`만 사용합니다. 기존 4열 CSV도 계속 지원합니다.

자동화 도구에서는 `POST /api/v1/catalog/import/csv`에 `Content-Type: text/csv`
로 같은 CSV 내용을 전송할 수 있습니다. 이 관리 API는 공유 배포 전에 기존
인증 시스템으로 보호해야 합니다.

저장된 카탈로그는 `GET /api/v1/catalog/export/csv`로 UTF-8 BOM CSV 형태로
내보낼 수 있습니다. Excel에서 한글 설명을 열어볼 때도 인코딩이 유지됩니다.

카탈로그를 갱신할 때는 기존 JSON이 자동으로 `data/catalog-backups/`에
보관됩니다. 관리자 API `GET /api/v1/catalog/backups`로 목록을 확인하고,
`POST /api/v1/catalog/backups/{backup_name}/restore`로 이전 버전을 복원할 수
있습니다.

업로드 시 누락 헤더, 빈 테이블·필드, 중복 필드를 행 번호와 함께 확인합니다.
카탈로그는 고객사 스키마 설명만 포함하고, 로그 원문이나 인증 정보는 넣지
않습니다.

## Ollama

로컬 Ollama가 준비됐다면 `.env`에 아래처럼 설정할 수 있습니다.

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2:3b
```

UI 기본 모드는 빠른 규칙 기반 생성입니다. Ollama 보조 모드는 애매한 요청을
보완할 수 있지만, 결과는 항상 로컬 검증을 거치며 실제 실행으로 이어지지
않습니다.

## 점검 명령

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall app tests ui -q
```

Docker Desktop을 사용하는 환경에서는 다음을 추가로 확인합니다.

```powershell
docker compose config
docker compose up --build
```

운영 카탈로그와 분리된 검증이 필요하면 별도 폴더를 지정합니다.

```powershell
$env:LOGPRESSO_DATA_DIR = '.docker-test-data'
docker compose up --build
```

이 경우 `data/`의 카탈로그·피드백·감사 데이터는 변경되지 않습니다.

컨테이너는 API `8000`, UI `8501` 포트를 사용하며 두 서비스 모두 healthcheck를
가집니다. Docker CLI가 설치되어 있지 않은 현재 PC에서는 Compose 기동 검증을
수행할 수 없습니다.

공유 배포 전에는 리버스 프록시 또는 기존 인증 시스템에서 카탈로그, 별칭,
피드백 리포트 관리 API를 역할별로 보호해야 합니다. 자세한 권한 경계는
`docs/OPERATIONS.md`를 참고합니다.
