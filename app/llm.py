"""OpenAI model factories plus the two helpers guardrails use: an LLM judge and moderation."""

from functools import lru_cache
from typing import List, Optional

from agno.agent import Agent
from agno.models.openai import OpenAIResponses
from agno.run.base import RunStatus
from openai import OpenAI

from app import config


def main_model(max_output_tokens: Optional[int] = None) -> OpenAIResponses:
    return OpenAIResponses(id=config.MAIN_MODEL, api_key=config.OPENAI_API_KEY, max_output_tokens=max_output_tokens)


def judge_model() -> OpenAIResponses:
    return OpenAIResponses(id=config.JUDGE_MODEL, api_key=config.OPENAI_API_KEY)


@lru_cache(maxsize=1)
def _judge_agent() -> Agent:
    return Agent(
        name="Guardrail Judge",
        model=judge_model(),
        instructions="You are a strict classifier. Answer with exactly one of the labels you are given, nothing else.",
        telemetry=False,
    )


def judge(prompt: str) -> str:
    """Ask the judge model a classification question and return its upper-cased answer.

    Raises RuntimeError when the call fails, so each guardrail can decide whether to fail open or closed.
    """
    resp = _judge_agent().run(prompt)
    content = resp.content if isinstance(resp.content, str) else ""
    if resp.status == RunStatus.error or not content:
        raise RuntimeError(f"judge call failed: {content or 'empty response'}")
    return content.strip().upper()


@lru_cache(maxsize=1)
def _openai_client() -> OpenAI:
    return OpenAI(api_key=config.OPENAI_API_KEY)


def moderate(text: str) -> List[str]:
    """Return the moderation categories OpenAI flags for `text` (empty list when clean)."""
    result = _openai_client().moderations.create(model=config.MODERATION_MODEL, input=text).results[0]
    if not result.flagged:
        return []
    return [name for name, hit in result.categories.model_dump().items() if hit]
