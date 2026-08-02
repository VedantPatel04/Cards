"""
llm_lookup_mcc tests.

Never hit the real OpenAI API. Mock OpenAI(...).responses.create and
known_mcc_codes() so tests are free, deterministic, and CI-safe.
"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

import services.llm_client as llm_module
from services.llm_client import LLMUnavailable, llm_lookup_mcc


def _mock_response(text: str):
    resp = MagicMock()
    resp.output_text = text
    return resp


class LlmLookupGuardTests(SimpleTestCase):
    @override_settings(LLM_ENABLED=False, LLM_API_KEY="sk-test")
    def test_disabled_returns_none(self):
        self.assertIsNone(llm_lookup_mcc("SHAKE SHACK"))

    @override_settings(LLM_ENABLED=True, LLM_API_KEY="")
    def test_missing_api_key_returns_none(self):
        self.assertIsNone(llm_lookup_mcc("SHAKE SHACK"))


class LlmLookupHappyPathTests(SimpleTestCase):
    @override_settings(LLM_ENABLED=True, LLM_API_KEY="sk-test", LLM_MODEL="gpt-test")
    @patch.object(llm_module, "known_mcc_codes", return_value={"5814", "5411"})
    @patch.object(llm_module, "OpenAI")
    def test_valid_json_known_mcc_returned(self, mock_openai_cls, _known):
        client = MagicMock()
        client.responses.create.return_value = _mock_response('{"mcc":"5814"}')
        mock_openai_cls.return_value = client

        self.assertEqual(llm_lookup_mcc("SHAKE SHACK"), "5814")
        client.responses.create.assert_called_once()
        kwargs = client.responses.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-test")
        self.assertEqual(kwargs["temperature"], 0.0)
        self.assertEqual(kwargs["max_output_tokens"], 30)
        self.assertIn("SHAKE SHACK", kwargs["input"])
        self.assertIn("JSON only", kwargs["input"])

    @override_settings(LLM_ENABLED=True, LLM_API_KEY="sk-test", LLM_MODEL="gpt-test")
    @patch.object(llm_module, "known_mcc_codes", return_value={"5814"})
    @patch.object(llm_module, "OpenAI")
    def test_numeric_mcc_coerced_to_string(self, mock_openai_cls, _known):
        client = MagicMock()
        client.responses.create.return_value = _mock_response('{"mcc":5814}')
        mock_openai_cls.return_value = client
        self.assertEqual(llm_lookup_mcc("MCDONALDS"), "5814")


class LlmLookupValidationTests(SimpleTestCase):
    @override_settings(LLM_ENABLED=True, LLM_API_KEY="sk-test", LLM_MODEL="gpt-test")
    @patch.object(llm_module, "known_mcc_codes", return_value={"5814"})
    @patch.object(llm_module, "OpenAI")
    def test_hallucinated_mcc_returns_none(self, mock_openai_cls, _known):
        client = MagicMock()
        client.responses.create.return_value = _mock_response('{"mcc":"9999"}')
        mock_openai_cls.return_value = client
        self.assertIsNone(llm_lookup_mcc("FAKE MERCHANT"))

    @override_settings(LLM_ENABLED=True, LLM_API_KEY="sk-test", LLM_MODEL="gpt-test")
    @patch.object(llm_module, "known_mcc_codes", return_value={"5814"})
    @patch.object(llm_module, "OpenAI")
    def test_missing_mcc_key_returns_none(self, mock_openai_cls, _known):
        client = MagicMock()
        client.responses.create.return_value = _mock_response('{"code":"5814"}')
        mock_openai_cls.return_value = client
        self.assertIsNone(llm_lookup_mcc("X"))


class LlmLookupFailOpenTests(SimpleTestCase):
    @override_settings(LLM_ENABLED=True, LLM_API_KEY="sk-test", LLM_MODEL="gpt-test")
    @patch.object(llm_module, "OpenAI")
    def test_bad_json_returns_none(self, mock_openai_cls):
        client = MagicMock()
        client.responses.create.return_value = _mock_response("not json at all")
        mock_openai_cls.return_value = client
        self.assertIsNone(llm_lookup_mcc("X"))

    @override_settings(LLM_ENABLED=True, LLM_API_KEY="sk-test", LLM_MODEL="gpt-test")
    @patch.object(llm_module, "OpenAI")
    def test_network_error_raises_llm_unavailable(self, mock_openai_cls):
        """
        'We could not ask' is not 'the answer is unknown'. The caller persists
        None forever, so an outage has to be a different signal than a miss.
        """
        client = MagicMock()
        client.responses.create.side_effect = RuntimeError("timeout")
        mock_openai_cls.return_value = client
        with self.assertRaises(LLMUnavailable):
            llm_lookup_mcc("X")

    @override_settings(LLM_ENABLED=True, LLM_API_KEY="sk-test", LLM_MODEL="gpt-test")
    @patch.object(llm_module, "known_mcc_codes", return_value={"5814"})
    @patch.object(llm_module, "OpenAI")
    def test_markdown_fenced_json_is_tolerated(self, mock_openai_cls, _known):
        """Models wrap JSON in ```json fences constantly; that is still an answer."""
        client = MagicMock()
        client.responses.create.return_value = _mock_response(
            '```json\n{"mcc": "5814"}\n```'
        )
        mock_openai_cls.return_value = client
        self.assertEqual(llm_lookup_mcc("SHAKE SHACK"), "5814")

    @override_settings(LLM_ENABLED=True, LLM_API_KEY="sk-test", LLM_MODEL="gpt-test")
    @patch.object(llm_module, "known_mcc_codes", return_value={"5814"})
    @patch.object(llm_module, "OpenAI")
    def test_empty_reply_returns_none(self, mock_openai_cls, _known):
        client = MagicMock()
        client.responses.create.return_value = _mock_response("")
        mock_openai_cls.return_value = client
        self.assertIsNone(llm_lookup_mcc("X"))

    @override_settings(LLM_ENABLED=True, LLM_API_KEY="sk-test", LLM_MODEL="gpt-test")
    @patch.object(llm_module, "known_mcc_codes", return_value={"5814"})
    @patch.object(llm_module, "OpenAI")
    def test_uses_responses_api_with_short_timeout_and_cap(self, mock_openai_cls, _known):
        """Locks the Responses-API contract that Completions params would break."""
        client = MagicMock()
        client.responses.create.return_value = _mock_response('{"mcc":"5814"}')
        mock_openai_cls.return_value = client
        llm_lookup_mcc("X")
        self.assertEqual(mock_openai_cls.call_args.kwargs.get("timeout"), 10)
        kwargs = client.responses.create.call_args.kwargs
        self.assertEqual(kwargs.get("max_output_tokens"), 30)
        self.assertNotIn("max_tokens", kwargs)
