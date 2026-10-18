"""DeepSeek official search provider.

API: https://api.deepseek.com/v1/tools/search

DeepSeek exposes web search as a standalone Search endpoint next to its model
APIs, authenticated with the same API key. It returns plain SERP rows
(title/url/snippet/summary/content/date/authority) and never a model-written
answer, so ``supports_answer`` stays false and consolidation writes the answer,
exactly like the Bocha/Serper adapters.

The Responses API also has a server-side ``web_search`` tool, but official docs
limit it to ``deepseek-v4-pro``. This adapter keeps search independent of the
chat model: any chat binding can use it, and the search profile can reuse an
existing DeepSeek provider connection's key through ``provider_ref``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests

from ..base import BaseSearchProvider
from ..types import Citation, SearchResult, WebSearchResponse
from . import register_provider

_SEARCH_PATH = "/v1/tools/search"
_OFFICIAL_HOST = "api.deepseek.com"
# A connection URL may have been typed as the inference endpoint it was made for.
_INFERENCE_SUFFIXES = ("/chat/completions", "/responses", "/messages")


def search_endpoint(base_url: str | None = None) -> str:
    """Derive the Search endpoint from a configured provider URL.

    A DeepSeek connection usually carries no URL (the registry default is used)
    or ``https://api.deepseek.com``; users may also paste ``.../v1`` or a model
    endpoint. Normalize those instead of posting a search request to an
    endpoint that would reject it. Non-official hosts (relays) keep their path
    prefix, so a deployment that proxies DeepSeek can still be addressed.
    """
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return f"https://{_OFFICIAL_HOST}{_SEARCH_PATH}"
    for suffix in _INFERENCE_SUFFIXES:
        if base.endswith(suffix):
            base = base.removesuffix(suffix).rstrip("/")
            break
    if base.endswith(_SEARCH_PATH):
        return base
    parsed = urlsplit(base)
    if (parsed.hostname or "").lower() == _OFFICIAL_HOST:
        return urlunsplit(parsed._replace(path=_SEARCH_PATH, query="", fragment=""))
    if parsed.path.rstrip("/").endswith("/v1"):
        return base + "/tools/search"
    return base + _SEARCH_PATH


@register_provider("deepseek")
class DeepseekProvider(BaseSearchProvider):
    """DeepSeek official web search (Search API)."""

    description = "DeepSeek official web search (SERP)"
    BASE_URL = f"https://{_OFFICIAL_HOST}{_SEARCH_PATH}"
    API_KEY_ENV_VARS = ("DEEPSEEK_API_KEY", "SEARCH_API_KEY")

    def search(
        self,
        query: str,
        max_results: int = 5,
        need_content: bool = False,
        ori_question: str | None = None,
        localization: str = "",
        timeout: int = 30,
        **kwargs: Any,
    ) -> WebSearchResponse:
        """Search the web through DeepSeek's Search API.

        Args:
            query: Search query. DeepSeek caps it at 128 characters, so longer
                prompts are trimmed instead of failing the whole turn.
            max_results: Sent as the API's ``count`` (1-50).
            need_content: Ask for the page body in ``content``. Off by default:
                ``summary`` already carries the model-oriented extract.
            ori_question: The user's original question, for search intent.
            localization: Optional IP hint for localized results.
            timeout: Request timeout in seconds.
            **kwargs: Provider options, including ``base_url``.

        Returns:
            WebSearchResponse: Structured results with ``answer`` left empty.
        """
        query_text = str(query or "").strip()
        if len(query_text) > 128:
            query_text = query_text[:128]
        count = max(1, min(int(max_results), 50))
        payload: dict[str, Any] = {"query": query_text, "count": count}
        if need_content:
            payload["need_content"] = True
        if ori_question:
            payload["ori_question"] = str(ori_question).strip()[:128]
        if localization:
            payload["localization"] = str(localization).strip()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        request_kwargs: dict[str, Any] = {"headers": headers, "json": payload}
        if self.proxy:
            request_kwargs["proxies"] = {"http": self.proxy, "https": self.proxy}
        endpoint = search_endpoint(kwargs.get("base_url"))
        response = requests.post(endpoint, timeout=timeout, **request_kwargs)
        # HTTPError keeps status codes meaningful for the settings probe
        # (401 -> auth_error, 429 -> rate_limited) without echoing the key.
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and data.get("error"):
            raise ValueError(f"DeepSeek Search API error: {str(data['error'])[:300]}")
        rows = data.get("results") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise ValueError("DeepSeek Search API response contains no results list")

        citations: list[Citation] = []
        search_results: list[SearchResult] = []
        for row in rows[:count]:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "").strip()
            if not url:
                continue
            title = str(row.get("title") or "")
            snippet = str(row.get("snippet") or "").strip()
            summary = str(row.get("summary") or "").strip()
            # Without need_content the body is empty; the long summary is the
            # field DeepSeek documents for model consumption.
            content = str(row.get("content") or "").strip() or summary
            date = str(row.get("date") or "")
            site_name = str(row.get("site_name") or "") or "DeepSeek"
            site_icon = str(row.get("site_icon") or "")
            try:
                score = float(row.get("rerank_score"))
            except (TypeError, ValueError):
                score = 0.0
            idx = len(search_results) + 1
            search_results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet or summary[:200],
                    date=date,
                    source=site_name,
                    content=content,
                    score=score,
                    attributes={
                        "authority": row.get("authority"),
                        "rerank_score": score,
                        "site_icon": site_icon or None,
                    },
                )
            )
            citations.append(
                Citation(
                    id=idx,
                    reference=f"[{idx}]",
                    url=url,
                    title=title,
                    snippet=snippet,
                    date=date,
                    source=site_name,
                    content=content,
                    icon=site_icon,
                    website=site_name,
                )
            )

        return WebSearchResponse(
            query=str(query or ""),
            answer="",
            provider="deepseek",
            timestamp=datetime.now().isoformat(),
            model="deepseek-search",
            citations=citations,
            search_results=search_results,
            metadata={"finish_reason": "stop", "result_count": len(search_results)},
        )


__all__ = ["DeepseekProvider", "search_endpoint"]
