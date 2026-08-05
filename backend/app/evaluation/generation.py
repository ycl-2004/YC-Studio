"""Structured synthetic-question generation boundaries for Stage 2."""

import json
import re
from collections.abc import Callable
from typing import Protocol

import httpx
from pydantic import BaseModel, Field

_FORBIDDEN_REFERENCE_WORDS = re.compile(r"这段|本文|上述|该段|这篇|这个内容|其中")


class GeneratedQuestion(BaseModel):
    """The only shape accepted from a synthetic-question generator."""

    query: str = Field(min_length=8, max_length=500)
    rationale: str | None = Field(default=None, max_length=1_000)


class SyntheticQuestionGenerator(Protocol):
    """Async boundary so the dataset service does not depend on one LLM SDK."""

    async def generate(self, chunk_text: str) -> GeneratedQuestion:
        """Generate one answerable, chunk-grounded question."""


def build_synthetic_prompt(chunk_text: str) -> str:
    """Build the stable prompt used by any provider adapter."""

    return (
        "你是检索评测集构造器。请只根据给定知识片段生成一个具体问题，并输出 JSON："
        '{"query":"...","rationale":"..."}。问题必须满足：只能靠这一个片段回答；'
        "不能出现‘这段’、‘本文’、‘上述’、‘其中’等指代；不能问‘讲了什么’；"
        "答案应是一个明确事实、步骤、条件或工程取舍。不要回答问题。\n\n"
        f"知识片段：\n{chunk_text}"
    )


def validate_generated_question(question: GeneratedQuestion) -> GeneratedQuestion:
    """Reject low-signal or referential questions before they enter the dataset."""

    normalized = " ".join(question.query.split())
    if _FORBIDDEN_REFERENCE_WORDS.search(normalized):
        raise ValueError("synthetic question contains a forbidden reference word")
    if normalized in {"这是什么？", "这是什么?"} or "讲了什么" in normalized:
        raise ValueError("synthetic question is too broad")
    return question.model_copy(update={"query": normalized})


class HttpJsonQuestionGenerator:
    """Small OpenAI-compatible HTTP adapter, isolated until the provider stage."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        model: str,
        temperature: float = 0.0,
        client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.client_factory = client_factory

    async def generate(self, chunk_text: str) -> GeneratedQuestion:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "只输出合法 JSON，不要 Markdown。"},
                {"role": "user", "content": build_synthetic_prompt(chunk_text)},
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with self.client_factory(timeout=60.0) as client:
            response = await client.post(self.endpoint, json=payload, headers=headers)
            response.raise_for_status()
        try:
            content = response.json()["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content)
            parsed = json.loads(str(content).strip().strip("`"))
            return validate_generated_question(GeneratedQuestion.model_validate(parsed))
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError(
                "LLM response did not contain a valid GeneratedQuestion JSON"
            ) from error


class DeterministicQuestionGenerator:
    """Offline generator used for unit tests and smoke fixtures, never as quality evidence."""

    async def generate(self, chunk_text: str) -> GeneratedQuestion:
        first_sentence = re.split(r"[。！？!?\n]", chunk_text.strip(), maxsplit=1)[0]
        anchor = _FORBIDDEN_REFERENCE_WORDS.sub("", " ".join(first_sentence.split()))
        anchor = anchor.strip(" ，、:：;；")[:120]
        if len(anchor) < 8:
            anchor = "知识库中的工程事实"
        return GeneratedQuestion(
            query=f"关于{anchor}，最关键的工程结论或操作条件是什么？",
            rationale="offline deterministic smoke generator",
        )
