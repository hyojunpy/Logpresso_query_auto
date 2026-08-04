import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    subprocess.run([sys.executable, "scripts/build_index.py"], check=True)
    print("Run API: uvicorn app.api.main:app --reload --port 8000")
    print("Run UI : streamlit run ui/streamlit_app.py")


if __name__ == "__main__":
    main()
