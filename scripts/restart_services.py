from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
PYTHON = VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable)
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

DETACHED_FLAGS = 0
if os.name == "nt":
    DETACHED_FLAGS = 0x00000008 | 0x00000200 | 0x08000000


def pids_listening_on(*ports: int) -> set[int]:
    result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, check=False)
    pids: set[int] = set()
    for line in result.stdout.splitlines():
        if "LISTENING" not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        local_address = parts[1]
        pid = parts[-1]
        if any(local_address.endswith(f":{port}") for port in ports) and pid.isdigit():
            pids.add(int(pid))
    return pids


def stop_ports(*ports: int) -> bool:
    current_pid = os.getpid()
    ok = True
    for pid in sorted(pids_listening_on(*ports)):
        if pid == current_pid:
            continue
        result = subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            ok = False
            message = (result.stderr or result.stdout).strip()
            print(f"failed to stop pid={pid}: {message}")
        else:
            print(f"stopped pid={pid}")
    return ok


def wait_ports_free(*ports: int, timeout_seconds: int = 10) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not pids_listening_on(*ports):
            return True
        time.sleep(0.5)
    return not pids_listening_on(*ports)


def start_process(name: str, args: list[str], log_name: str) -> int:
    log_path = DATA_DIR / log_name
    log_file = log_path.open("ab")
    process = subprocess.Popen(
        [str(PYTHON), *args],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=DETACHED_FLAGS,
        close_fds=True,
    )
    print(f"{name} pid={process.pid} log={log_path}")
    return process.pid


def wait_for(url: str, timeout_seconds: int = 20) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=3) as response:
                if 200 <= response.status < 500:
                    return True
        except URLError:
            time.sleep(1)
        except TimeoutError:
            time.sleep(1)
    return False


def main() -> int:
    stopped = stop_ports(8000, 8501)
    if not wait_ports_free(8000, 8501):
        print("ports 8000/8501 are still in use; restart aborted")
        return 1 if stopped else 2
    start_process("api", ["-m", "uvicorn", "app.api.main:app", "--host", "127.0.0.1", "--port", "8000"], "api.log")
    start_process(
        "ui",
        [
            "-m",
            "streamlit",
            "run",
            "ui/streamlit_app.py",
            "--server.address",
            "127.0.0.1",
            "--server.port",
            "8501",
            "--server.headless",
            "true",
        ],
        "streamlit.log",
    )
    api_ok = wait_for("http://127.0.0.1:8000/api/v1/health")
    ui_ok = wait_for("http://127.0.0.1:8501")
    print(f"API: {'ok' if api_ok else 'failed'} http://127.0.0.1:8000/docs")
    print(f"UI : {'ok' if ui_ok else 'failed'} http://127.0.0.1:8501")
    return 0 if api_ok and ui_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
