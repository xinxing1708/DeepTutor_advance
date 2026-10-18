r"""Offline checks for the DeepSeek Search API integration.

Run from the DeepTutor install root with its venv python after applying the
patch:

    .venv\Scripts\python.exe extensions\deepseek_search\tests\test_deepseek_search_provider.py

No network and no real API key are used: ``requests.post`` is replaced with a
fixture. Live connectivity is the user's own Settings > Search test.
"""

from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest import mock

os.environ.setdefault("DEEPTUTOR_HOME", str(Path.cwd()))

import requests  # noqa: E402

from deeptutor.services.config.provider_runtime import (  # noqa: E402
    SEARCH_PROVIDERS,
    resolve_search_runtime_config,
    search_missing_credential,
)
from deeptutor.services.provider_registry import find_by_name  # noqa: E402
from deeptutor.services.search.providers import (  # noqa: E402
    get_provider,
    list_providers,
)
from deeptutor.services.search.providers.deepseek import (  # noqa: E402
    DeepseekProvider,
    search_endpoint,
)


class _FakeResponse:
    def __init__(self, payload=None, status_code: int = 200):
        self._payload = payload or {}
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"{self.status_code} Client Error", response=self
            )


def _entry(url: str = "https://example.com/a", **overrides) -> dict:
    entry = {
        "rerank_score": 2.4,
        "title": "DeepSeek V4 模型发布",
        "url": url,
        "snippet": "短摘要",
        "summary": "长摘要（给模型阅读）",
        "content": "",
        "site_name": "Example News",
        "site_icon": "https://example.com/favicon.ico",
        "date": "2026-06-01T00:00:00+00:00",
        "authority": 3,
    }
    entry.update(overrides)
    return entry


class RegistryTests(unittest.TestCase):
    def test_spec_is_registered_once(self):
        self.assertIn("deepseek", SEARCH_PROVIDERS)
        spec = SEARCH_PROVIDERS["deepseek"]
        self.assertTrue(spec.requires_api_key)
        self.assertFalse(spec.requires_base_url)
        self.assertFalse(spec.soft_fallback)
        self.assertFalse(spec.supports_answer)

    def test_adapter_registers(self):
        self.assertIn("deepseek", list_providers())
        provider = get_provider("deepseek", api_key="dummy")
        self.assertIsInstance(provider, DeepseekProvider)
        self.assertEqual(provider.name, "deepseek")

    def test_previous_adapters_still_registered(self):
        names = set(list_providers())
        expected = {
            "brave",
            "tavily",
            "jina",
            "searxng",
            "duckduckgo",
            "perplexity",
            "serper",
            "serply",
            "firecrawl",
            "doubao",
            "bocha",
            "zhipu",
            "qianfan",
            "aliyun_iqs",
        }
        self.assertTrue(expected <= names)

    def test_missing_key_is_explicit(self):
        self.assertEqual(search_missing_credential("deepseek", "", ""), "api_key")
        self.assertIsNone(search_missing_credential("deepseek", "sk-x", ""))

    def test_runtime_config_does_not_silently_fallback(self):
        catalog = {
            "connections": [],
            "services": {
                "search": {
                    "active_profile_id": "search-deepseek",
                    "profiles": [
                        {"id": "search-deepseek", "provider": "deepseek", "api_key": ""}
                    ],
                }
            },
        }
        missing = resolve_search_runtime_config(catalog=catalog)
        self.assertEqual(missing.provider, "deepseek")
        self.assertTrue(missing.missing_credentials)
        catalog["services"]["search"]["profiles"][0]["api_key"] = "sk-test"
        ready = resolve_search_runtime_config(catalog=catalog)
        self.assertEqual(ready.provider, "deepseek")
        self.assertFalse(ready.missing_credentials)

    def test_native_web_search_only_for_v4_pro(self):
        spec = find_by_name("deepseek")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.native_web_search_models, ("deepseek-v4-pro",))

    def test_provider_choices_expose_search_capability(self):
        from deeptutor.api.routers.settings import _provider_choices

        choices = _provider_choices()
        search = {item["value"]: item for item in choices["search"]}
        self.assertIn("deepseek", search)
        self.assertEqual(search["deepseek"]["label"], "DeepSeek")
        self.assertTrue(search["deepseek"]["requires_api_key"])


class EndpointTests(unittest.TestCase):
    def test_defaults_to_official_search_endpoint(self):
        expected = "https://api.deepseek.com/v1/tools/search"
        self.assertEqual(search_endpoint(""), expected)
        self.assertEqual(search_endpoint(None), expected)

    def test_normalizes_common_connection_urls(self):
        expected = "https://api.deepseek.com/v1/tools/search"
        for value in (
            "https://api.deepseek.com",
            "https://api.deepseek.com/",
            "https://api.deepseek.com/v1",
            "https://api.deepseek.com/v1/",
            "https://api.deepseek.com/v1/chat/completions",
            "https://api.deepseek.com/responses",
            "https://api.deepseek.com/anthropic",
            "https://api.deepseek.com/v1/tools/search",
        ):
            self.assertEqual(search_endpoint(value), expected, value)

    def test_keeps_relay_path_prefix(self):
        self.assertEqual(
            search_endpoint("https://relay.example.com/deepseek/v1"),
            "https://relay.example.com/deepseek/v1/tools/search",
        )
        self.assertEqual(
            search_endpoint("https://relay.example.com/deepseek"),
            "https://relay.example.com/deepseek/v1/tools/search",
        )


class SearchTests(unittest.TestCase):
    def _search(self, payload=None, status_code=200, **kwargs):
        fake = _FakeResponse(payload, status_code=status_code)
        provider = get_provider("deepseek", api_key="dummy")
        with mock.patch(
            "deeptutor.services.search.providers.deepseek.requests.post",
            return_value=fake,
        ) as post:
            result = provider.search("DeepSeek V4", **kwargs)
        return result, post

    def test_maps_results_and_citations(self):
        payload = {"results": [_entry(), _entry(url="https://example.com/b")]}
        result, post = self._search(payload, max_results=7)
        self.assertEqual(result.provider, "deepseek")
        self.assertEqual(result.answer, "")
        self.assertEqual(result.model, "deepseek-search")
        self.assertEqual(len(result.search_results), 2)
        self.assertEqual(len(result.citations), 2)
        first = result.search_results[0]
        self.assertEqual(first.title, "DeepSeek V4 模型发布")
        self.assertEqual(first.url, "https://example.com/a")
        self.assertEqual(first.snippet, "短摘要")
        self.assertEqual(first.content, "长摘要（给模型阅读）")
        self.assertEqual(first.source, "Example News")
        self.assertEqual(first.score, 2.4)
        self.assertEqual(first.attributes["authority"], 3)
        citation = result.citations[0]
        self.assertEqual(citation.id, 1)
        self.assertEqual(citation.reference, "[1]")
        self.assertEqual(citation.icon, "https://example.com/favicon.ico")
        self.assertEqual(citation.website, "Example News")
        sent = post.call_args.kwargs["json"]
        self.assertEqual(sent["query"], "DeepSeek V4")
        self.assertEqual(sent["count"], 7)
        self.assertNotIn("need_content", sent)

    def test_payload_options_and_clamp(self):
        payload = {"results": [_entry()]}
        _, post = self._search(
            payload,
            max_results=99,
            need_content=True,
            ori_question="原始问题",
            localization="1.2.3.4",
        )
        sent = post.call_args.kwargs["json"]
        self.assertEqual(sent["count"], 50)
        self.assertTrue(sent["need_content"])
        self.assertEqual(sent["ori_question"], "原始问题")
        self.assertEqual(sent["localization"], "1.2.3.4")

    def test_uses_configured_base_url(self):
        _, post = self._search(
            {"results": []}, base_url="https://api.deepseek.com/v1"
        )
        self.assertEqual(
            post.call_args.args[0], "https://api.deepseek.com/v1/tools/search"
        )

    def test_empty_results_are_not_an_error(self):
        result, _ = self._search({"results": []})
        self.assertEqual(result.search_results, [])
        self.assertEqual(result.citations, [])
        self.assertEqual(result.metadata["result_count"], 0)

    def test_auth_and_rate_limit_errors_raise_http_error(self):
        for status in (401, 429, 402):
            with self.assertRaises(requests.HTTPError):
                self._search({}, status_code=status)

    def test_skips_rows_without_url(self):
        payload = {"results": [_entry(url=""), _entry(url="https://example.com/c")]}
        result, _ = self._search(payload)
        self.assertEqual([r.url for r in result.search_results], ["https://example.com/c"])
        self.assertEqual(result.citations[0].id, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
