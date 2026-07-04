"""Provider-agnostic structured-completion seam.

The mapping/ingest/matching engines never touch a vendor SDK directly — they
call `complete_structured`, which forces the model to answer via a single tool
call (the most portable "structured output" across OpenAI-compatible models)
and returns the parsed arguments dict.

Provider = Azure AI Foundry via the OpenAI SDK. `llm_provider="azure"` uses
`AzureOpenAI`; `"openai"` uses a plain `OpenAI(base_url=...)` for a generic
OpenAI-compatible endpoint (OpenAI, DeepSeek, a Foundry serverless URL, etc.).

The client is built lazily inside the call so the app and the test-suite import
without any credentials present.
"""

import asyncio
import json

from ..config import get_settings

TOOL_NAME = "emit_proposal"

_token_provider = None  # cached Entra ID bearer-token provider (auto-refreshing)


def _get_token_provider(scope: str):
    """Cache one DefaultAzureCredential token provider. It returns a fresh,
    internally-cached bearer token string on each call, so we can safely fetch a
    token per request without re-probing the credential chain each time."""
    global _token_provider
    if _token_provider is None:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider

        _token_provider = get_bearer_token_provider(DefaultAzureCredential(), scope)
    return _token_provider


def _build_client_and_model():
    settings = get_settings()
    if settings.llm_provider == "azure_ad":
        # Foundry /openai/v1 endpoint + Entra ID. The OpenAI client signs
        # Authorization: Bearer <api_key>, so we pass a fresh AAD token as the key.
        from openai import OpenAI

        token = _get_token_provider(settings.azure_ad_scope)()
        client = OpenAI(base_url=settings.azure_openai_endpoint, api_key=token)
        return client, settings.azure_openai_deployment

    if settings.llm_provider == "openai":
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.openai_api_key or "missing",
            base_url=settings.openai_base_url or None,
        )
        return client, settings.openai_model

    from openai import AzureOpenAI

    client = AzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )
    return client, settings.azure_openai_deployment


def _extract_arguments(completion) -> dict:
    """Pull the tool-call arguments out of a chat completion, tolerating models
    that answer with plain JSON content instead of a tool call."""
    message = completion.choices[0].message
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        return json.loads(tool_calls[0].function.arguments)
    # Fallback: some models ignore tool_choice and return JSON in the content.
    content = (message.content or "").strip()
    start, end = content.find("{"), content.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(content[start : end + 1])
    raise ValueError(f"model returned no tool call and no JSON object: {content[:200]!r}")


def _call_sync(system: str, user: str, tool_schema: dict) -> dict:
    client, model = _build_client_and_model()
    tool = {
        "type": "function",
        "function": {
            "name": TOOL_NAME,
            "description": "Emit exactly one structured proposal for this entity.",
            "parameters": tool_schema,
        },
    }
    kwargs = dict(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        tools=[tool],
        tool_choice={"type": "function", "function": {"name": TOOL_NAME}},
    )
    temperature = get_settings().llm_temperature
    if temperature is not None:
        kwargs["temperature"] = temperature
    completion = client.chat.completions.create(**kwargs)
    return _extract_arguments(completion)


async def complete_structured(system: str, user: str, tool_schema: dict) -> dict:
    """Force a single structured tool call and return its parsed arguments.

    The OpenAI SDK is synchronous, so the blocking call runs in a worker thread
    to avoid stalling the async request handler.
    """
    return await asyncio.to_thread(_call_sync, system, user, tool_schema)
