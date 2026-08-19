# 사내망 배포 및 운영 안내

## 접속 범위

이 구성은 같은 사내망/공유기 안에서만 UI를 공유합니다. API는
`127.0.0.1:8000`에만 바인딩되어 다른 PC에 공개되지 않습니다. UI 주소는
현재 서버 PC의 IPv4 주소를 사용합니다(예: `http://192.168.202.5:8501/`).

서버 PC에서 관리자 PowerShell을 열어 다음을 실행합니다.

```powershell
scripts/configure_lan.ps1
scripts/start_dev.ps1
```

첫 명령은 활성 IPv4를 `.env`에 기록하고 TCP 8501 방화벽 규칙을 같은
서브넷으로 제한합니다. IP가 변경되면 다시 실행해야 합니다.

## 사용자 로그인

```powershell
scripts/new_ui_user.ps1 -Username admin
scripts/start_dev.ps1
```

비밀번호는 PBKDF2-SHA256 해시로만 `.env`에 저장됩니다. 계정 추가 후에는
서비스를 재시작합니다. 로그인 이후 사용자 요청, 결과, 편집 이력과 힌트는
각 브라우저 세션에 분리되며 기본 60분 동안 활동이 없으면 로그아웃됩니다.

## 상태·로그·부하 확인

```powershell
scripts/status.ps1
docker compose exec -T api python /app/scripts/load_test.py --requests 100 --concurrency 10
```

API 구조화 로그는 `data/logs/app.jsonl` 또는 개발 구성의
`.docker-dev/logs/app.jsonl`에 남습니다. 요청 본문과 생성 쿼리는 기록하지
않습니다. 집계 지표는 UI의 운영 지표 영역에서 확인합니다.

## 자동 시작

Docker Desktop의 로그인 시 시작 옵션을 켠 뒤 다음을 실행합니다.

```powershell
scripts/install_autostart.ps1
```

현재 Windows 사용자가 로그인할 때 숨김 PowerShell 작업으로 Compose를
시작합니다. 제거는 `scripts/install_autostart.ps1 -Uninstall`입니다.

## 백업과 복구

```powershell
scripts/backup.ps1
```

기본 백업은 `backups/` 아래 ZIP과 SHA-256 확인값을 생성합니다. 정기적으로
다른 사내 저장소에 복사하십시오. 복구 전 컨테이너를 중지하고 기존
`.docker-dev`를 별도 위치로 옮긴 뒤 다음을 실행합니다.

```powershell
scripts/restore_backup.ps1 -Archive <zip 경로> -ConfirmRestore
scripts/start_dev.ps1
```

복구 스크립트는 기존 데이터 디렉터리가 남아 있으면 안전을 위해 중단합니다.

## 다른 PC 접속 점검

다른 PC에서 `Test-NetConnection 192.168.202.5 -Port 8501`을 실행한 후 브라우저로
UI 주소를 엽니다. 실패하면 두 PC가 같은 서브넷인지, 서버 PC가 절전 상태인지,
방화벽 규칙의 원격 주소 범위가 현재 서브넷과 일치하는지 확인합니다.
