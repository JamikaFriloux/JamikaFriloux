"""Anthropic Claude implementation of the LLM interface (structured outputs)."""

from __future__ import annotations

import anthropic
from pydantic import BaseModel, ValidationError

from atlas.core.configuration.settings import LLMSettings
from atlas.integrations.llm.base import (
    UNTRUSTED_CONTENT_POLICY,
    LLMError,
    LLMProvider,
    LLMRefusalError,
    LLMResult,
    LLMSchemaError,
)

# Server-side refusal fallback: on a safety decline the API re-runs the request on a fallback
# model chosen by refusal category, inside the same call.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, settings: LLMSettings, client: anthropic.Anthropic | None = None):
        if client is None:
            if settings.anthropic_api_key is None:
                raise LLMError("ATLAS_LLM_ANTHROPIC_API_KEY is not set")
            client = anthropic.Anthropic(
                api_key=settings.anthropic_api_key.get_secret_value(),
                timeout=settings.timeout_seconds,
            )
        self._client = client
        self._settings = settings

    def structured[T: BaseModel](
        self, *, system: str, prompt: str, schema: type[T]
    ) -> LLMResult[T]:
        try:
            response = self._client.beta.messages.parse(
                model=self._settings.model,
                max_tokens=self._settings.max_tokens,
                system=f"{UNTRUSTED_CONTENT_POLICY}\n\n{system}",
                messages=[{"role": "user", "content": prompt}],
                output_format=schema,
                output_config={"effort": "medium"},
                betas=[_FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.APIStatusError as exc:
            raise LLMError(f"anthropic API error {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("anthropic connection error") from exc

        if response.stop_reason == "refusal":
            raise LLMRefusalError("model declined the request")
        if response.stop_reason == "max_tokens":
            raise LLMSchemaError("output truncated at max_tokens")
        parsed = response.parsed_output
        if parsed is None:
            raise LLMSchemaError("no structured output returned")
        try:
            # Re-validate: never trust a parsed object we did not validate ourselves.
            output = schema.model_validate(parsed.model_dump())
        except ValidationError as exc:
            raise LLMSchemaError(str(exc)) from exc
        return LLMResult(
            output=output,
            provider=self.name,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            request_id=getattr(response, "_request_id", None),
        )


def build_provider(settings: LLMSettings | None = None) -> LLMProvider:
    from atlas.integrations.llm.base import DisabledProvider

    settings = settings or LLMSettings()
    if settings.provider == "anthropic":
        return AnthropicProvider(settings)
    return DisabledProvider()
