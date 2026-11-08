"""Thin wrapper around the Anthropic SDK.

Two operations cover the whole app:
- extract(): one structured-output call validated into a Pydantic model (routing, extraction)
- stream_text(): token streaming for chat answers

Everything else (prompts, retrieval, scoring) lives outside this file. Tests use a fake that
implements the LLMClient protocol, so no test ever calls the real API.
"""

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal, Protocol, TypeVar

import anthropic
from anthropic.types import MessageParam
from pydantic import BaseModel

from app.llm.pricing import make_usage
from app.models import Usage

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
Effort = Literal["low", "medium", "high"]
REFUSAL_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(Exception):
    """A model call failed. `retryable` tells the caller whether trying again could help."""

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass
class TextDelta:
    text: str


@dataclass
class StreamDone:
    usage: Usage
    stop_reason: str | None


StreamEvent = TextDelta | StreamDone


class LLMClient(Protocol):
    def extract(
        self, *, model: str, system: str, user: str, schema: type[T], effort: Effort = "low",
        max_tokens: int = 16000,
    ) -> tuple[T, Usage]: ...

    def stream_text(
        self, *, model: str, system: str, messages: list[MessageParam], effort: Effort = "low",
        max_tokens: int = 8000,
    ) -> Iterator[StreamEvent]: ...


class ClaudeClient:
    def __init__(self, api_key: str, timeout_s: float = 60.0, max_retries: int = 2) -> None:
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s, max_retries=max_retries)

    def extract(
        self, *, model: str, system: str, user: str, schema: type[T], effort: Effort = "low",
        max_tokens: int = 16000,
    ) -> tuple[T, Usage]:
        """Structured output: the API constrains the response to `schema`'s JSON schema."""
        try:
            response = self._client.messages.parse(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=schema,
                output_config={"effort": effort},
            )
        except anthropic.APIError as exc:
            raise _to_llm_error(exc) from exc

        usage = make_usage(model, response.usage.input_tokens, response.usage.output_tokens)
        if response.stop_reason == "refusal":
            raise LLMError("The model declined to process this document.")
        if response.stop_reason == "max_tokens":
            raise LLMError("The model ran out of output tokens before finishing.", retryable=True)
        parsed = response.parsed_output
        if parsed is None:
            raise LLMError("The model returned output that did not match the schema.", retryable=True)
        logger.info(
            "llm extract",
            extra={"model": model, "schema": schema.__name__, **usage.model_dump(exclude={"model"})},
        )
        return parsed, usage

    def stream_text(
        self, *, model: str, system: str, messages: list[MessageParam], effort: Effort = "low",
        max_tokens: int = 8000,
    ) -> Iterator[StreamEvent]:
        """Yield TextDelta events as tokens arrive, then one StreamDone with usage.

        Server-side refusal fallback is on: if a safety classifier declines, the API retries on
        a fallback model by itself. `final.model` reports which model actually answered.
        """
        try:
            with self._client.beta.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,  # type: ignore[arg-type]
                output_config={"effort": effort},
                betas=[REFUSAL_FALLBACK_BETA],
                fallbacks="default",
            ) as stream:
                for text in stream.text_stream:
                    yield TextDelta(text)
                final = stream.get_final_message()
        except anthropic.APIError as exc:
            raise _to_llm_error(exc) from exc

        usage = make_usage(final.model, final.usage.input_tokens, final.usage.output_tokens)
        logger.info("llm stream", extra={"model": model, "stop_reason": final.stop_reason,
                                         **usage.model_dump(exclude={"model"})})
        yield StreamDone(usage=usage, stop_reason=final.stop_reason)


def _to_llm_error(exc: anthropic.APIError) -> LLMError:
    """Most-specific first: tell the caller whether a retry could help."""
    if isinstance(exc, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return LLMError("The Anthropic API key is missing or invalid.")
    if isinstance(exc, anthropic.RateLimitError):
        return LLMError("The model is rate limited. Try again shortly.", retryable=True)
    if isinstance(exc, anthropic.BadRequestError):
        logger.error("llm bad request", extra={"error": str(exc)})
        return LLMError("The model rejected the request.")
    if isinstance(exc, anthropic.APIStatusError):
        return LLMError("The model service returned an error.", retryable=exc.status_code >= 500)
    if isinstance(exc, anthropic.APIConnectionError):
        return LLMError("Could not reach the model service.", retryable=True)
    return LLMError("Unexpected model error.")
