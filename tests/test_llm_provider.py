import unittest
from unittest.mock import patch
from urllib.error import URLError
import json

from app.services.llm.json_utils import parse_json_object
from app.services.llm.mock_provider import MockProvider
from app.services.llm.openai_provider import OpenAIProvider
from app.services.llm.ollama_provider import OllamaProvider


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class LLMProviderTest(unittest.TestCase):
    def test_parse_json_object_recovers_embedded_json(self):
        data = parse_json_object('prefix {"status":"generated","query":"table logs"} suffix')
        self.assertEqual(data["query"], "table logs")

    def test_mock_provider_can_return_injected_json_string(self):
        provider = MockProvider(generation_response='{"status":"generated","query":"table logs"}')
        self.assertEqual(provider.generate_json("prompt", [])["query"], "table logs")

    def test_openai_provider_extracts_response_text_json(self):
        payload = {"output": [{"content": [{"text": '{"status":"generated","query":"table logs"}'}]}]}
        with patch("app.services.llm.openai_provider.settings.openai_api_key", "test-key"):
            with patch("app.services.llm.openai_provider.request.urlopen", return_value=FakeResponse(payload)):
                data = OpenAIProvider().generate_json("prompt", [])
        self.assertEqual(data["query"], "table logs")

    def test_ollama_provider_parses_response_json(self):
        payload = {"response": '{"status":"generated","query":"table logs"}'}
        with patch("app.services.llm.ollama_provider.request.urlopen", return_value=FakeResponse(payload)):
            data = OllamaProvider().generate_json("prompt", [])
        self.assertEqual(data["query"], "table logs")

    def test_openai_timeout_returns_safe_error_without_api_key(self):
        with patch("app.services.llm.openai_provider.settings.openai_api_key", "super-secret-key"):
            with patch("app.services.llm.openai_provider.request.urlopen", side_effect=TimeoutError):
                data = OpenAIProvider().generate_json("prompt", [])
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_type"], "timeout")
        self.assertNotIn("super-secret-key", str(data))

    def test_ollama_connection_failure_returns_safe_error(self):
        with patch(
            "app.services.llm.ollama_provider.request.urlopen",
            side_effect=URLError("private network detail"),
        ):
            data = OllamaProvider().generate_json("prompt", [])
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_type"], "connection_error")
        self.assertNotIn("private network detail", str(data))


if __name__ == "__main__":
    unittest.main()
