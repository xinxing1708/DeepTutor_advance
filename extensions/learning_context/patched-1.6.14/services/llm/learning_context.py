"""Optional deployment-wide educational context, loaded for each LLM request."""
from __future__ import annotations

import logging
from typing import Any

from deeptutor.services.path_service import get_path_service

logger = logging.getLogger(__name__)


def inject_learning_context(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prefix the first system instruction; never edit caller-owned history.

    Missing/empty configuration disables this addition. Tools, attachments,
    provider state and later instructions retain their ordering and values.
    """
    path = get_path_service().get_settings_file("global_learning_context.md")
    try:
        prefix = path.read_text(encoding="utf-8-sig").strip()
    except FileNotFoundError:
        return messages
    except (OSError, UnicodeError):
        logger.warning("Unable to read global learning context; retaining original request")
        return messages
    if not prefix:
        return messages
    result = list(messages)
    if result and result[0].get("role") == "system":
        first = dict(result[0])
        content = first.get("content")
        if isinstance(content, str):
            if content == prefix or content.startswith(prefix + chr(10)*2):
                return messages
            first["content"] = prefix + (chr(10)*2 + content if content else "")
        elif isinstance(content, list):
            if content and content[0] == {"type": "text", "text": prefix}:
                return messages
            first["content"] = [{"type": "text", "text": prefix}, *content]
        elif content is None:
            first["content"] = prefix
        else:
            return [{"role": "system", "content": prefix}, *result]
        result[0] = first
    else:
        result.insert(0, {"role": "system", "content": prefix})
    return result


class _LearningCompletions:
    def __init__(self, delegate: Any):
        self._delegate = delegate

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    async def create(self, **kwargs: Any) -> Any:
        if "messages" in kwargs:
            kwargs = {**kwargs, "messages": inject_learning_context(list(kwargs["messages"]))}
        return await self._delegate.create(**kwargs)


class _LearningChat:
    def __init__(self, delegate: Any):
        self._delegate = delegate
        self.completions = _LearningCompletions(delegate.completions)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


class LearningContextClient:
    """Keep pooled SDK/provider lifecycle intact, transform only chat input."""
    def __init__(self, delegate: Any):
        self._delegate = delegate
        self.chat = _LearningChat(delegate.chat)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


def with_learning_context(client: Any) -> Any:
    return client if isinstance(client, LearningContextClient) else LearningContextClient(client)
