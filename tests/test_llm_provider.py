import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
import json

from app.core.config import settings
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

    def test_parse_json_object_recovers_fenced_json_with_trailing_comma(self):
        data = parse_json_object('```json\n{"status":"generated","query":"table logs",}\n```')
        self.assertEqual(data["query"], "table logs")

    def test_parse_json_object_uses_first_balanced_object(self):
        data = parse_json_object('result {"status":"generated","query":"table logs"} commentary {ignored}')
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
        payload = {
            "response": '{"status":"generated","query":"table logs"}',
            "total_duration": 2_000_000,
            "load_duration": 1_000_000,
        }
        with patch("app.services.llm.ollama_provider.request.urlopen", return_value=FakeResponse(payload)):
            data = OllamaProvider().generate_json("prompt", [])
        self.assertEqual(data["query"], "table logs")
        self.assertEqual(data["timing"]["total_duration_ms"], 2)
        self.assertEqual(data["timing"]["load_duration_ms"], 1)

    def test_ollama_provider_sends_configured_context_window(self):
        payload = {"response": '{"status":"generated","query":"table logs"}'}
        with patch.object(settings, "ollama_num_ctx", 2048), patch(
            "app.services.llm.ollama_provider.request.urlopen", return_value=FakeResponse(payload)
        ) as urlopen:
            OllamaProvider().generate_json("prompt", [])

        body = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(body["options"]["num_ctx"], 2048)

    def test_ollama_provider_retries_temporary_connection_failure_once(self):
        payload = {"response": '{"status":"generated","query":"table logs"}'}
        with patch("app.services.llm.ollama_provider.request.urlopen", side_effect=[URLError("offline"), FakeResponse(payload)]):
            data = OllamaProvider().generate_json("prompt", [])
        self.assertEqual(data["query"], "table logs")
        self.assertEqual(data["retry_count"], 1)

    def test_ollama_provider_retries_http_5xx_once(self):
        payload = {"response": '{"status":"generated","query":"table logs"}'}
        server_error = HTTPError("http://ollama.invalid", 500, "error", None, None)
        with patch(
            "app.services.llm.ollama_provider.request.urlopen",
            side_effect=[server_error, FakeResponse(payload)],
        ) as urlopen:
            data = OllamaProvider().generate_json("prompt", [])

        self.assertEqual(data["query"], "table logs")
        self.assertEqual(data["retry_count"], 1)
        self.assertEqual(urlopen.call_count, 2)

    def test_ollama_provider_does_not_retry_http_4xx(self):
        client_error = HTTPError("http://ollama.invalid", 400, "error", None, None)
        with patch(
            "app.services.llm.ollama_provider.request.urlopen",
            side_effect=client_error,
        ) as urlopen:
            data = OllamaProvider().generate_json("prompt", [])

        self.assertEqual(data["error_type"], "http_error")
        self.assertEqual(data["retry_count"], 0)
        urlopen.assert_called_once()

    def test_ollama_provider_does_not_retry_a_timeout(self):
        with patch(
            "app.services.llm.ollama_provider.request.urlopen",
            side_effect=TimeoutError,
        ) as urlopen:
            data = OllamaProvider().generate_json("prompt", [])

        self.assertEqual(data["error_type"], "timeout")
        self.assertEqual(data["retry_count"], 0)
        urlopen.assert_called_once()

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

    def test_ollama_provider_does_not_retry_timeout_wrapped_by_url_error(self):
        with patch(
            "app.services.llm.ollama_provider.request.urlopen",
            side_effect=URLError(TimeoutError()),
        ) as urlopen:
            data = OllamaProvider().generate_json("prompt", [])

        self.assertEqual(data["error_type"], "timeout")
        urlopen.assert_called_once()

    def test_ollama_provider_marks_malformed_model_output_as_invalid_response(self):
        payload = {"response": "not a JSON response", "total_duration": 2_000_000}
        with patch("app.services.llm.ollama_provider.request.urlopen", return_value=FakeResponse(payload)):
            data = OllamaProvider().generate_json("prompt", [])

        self.assertEqual(data["error_type"], "invalid_response")
        self.assertEqual(data["timing"]["total_duration_ms"], 2)


if __name__ == "__main__":
    unittest.main()
