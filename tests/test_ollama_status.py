import json
from unittest.mock import patch
from urllib.error import URLError

from app.services.ollama_status import check_ollama


class FakeResponse:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return json.dumps({"models": [{"name": "llama3.1:latest"}]}).encode()


def test_explicit_ollama_check_reports_model_availability():
    with patch("app.services.ollama_status.request.urlopen", return_value=FakeResponse()):
        result = check_ollama("http://localhost:11434", "llama3.1")
    assert result["status"] == "reachable"
    assert result["model_available"] is True
    assert result["external_call_made"] is True


def test_explicit_ollama_check_hides_connection_details():
    with patch("app.services.ollama_status.request.urlopen", side_effect=URLError("private address")):
        result = check_ollama("http://localhost:11434", "llama3.1")
    assert result["status"] == "unreachable"
    assert "private address" not in str(result)
