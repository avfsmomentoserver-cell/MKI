"""AI provider implementations for MKC.

Supports external LLM APIs (OpenAI, Anthropic) and local models (Ollama)
with automatic fallback and cost tracking.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("mkc.ai.providers")


@dataclass
class AIUsage:
    """Usage metrics for an AI call."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_estimate_usd: float = 0.0


@dataclass
class AIMessage:
    """A message in an AI conversation."""
    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class AIResponse:
    """Response from an AI provider."""
    content: str
    usage: AIUsage
    model: str
    provider: str


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    def __init__(self, model: str = "gpt-4"):
        self.model = model
        self._total_usage = AIUsage()

    @abstractmethod
    async def generate(self, prompt: str, **kwargs: Any) -> AIResponse:
        """Generate text from a prompt."""
        pass

    @abstractmethod
    async def chat(self, messages: list[AIMessage], **kwargs: Any) -> AIResponse:
        """Generate text from a conversation."""
        pass

    @abstractmethod
    async def embed(self, text: str, **kwargs: Any) -> list[float]:
        """Generate embedding for text."""
        pass

    def get_total_usage(self) -> AIUsage:
        """Get cumulative usage metrics."""
        return self._total_usage

    def _accumulate_usage(self, usage: AIUsage) -> None:
        """Accumulate usage metrics."""
        self._total_usage.prompt_tokens += usage.prompt_tokens
        self._total_usage.completion_tokens += usage.completion_tokens
        self._total_usage.total_tokens += usage.total_tokens
        self._total_usage.cost_estimate_usd += usage.cost_estimate_usd


class OpenAIProvider(AIProvider):
    """OpenAI API provider."""

    def __init__(self, model: str = "gpt-4", api_key: Optional[str] = None):
        super().__init__(model)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("OpenAI API key not set; provider will fail")
        # Import lazily to avoid hard dependency
        try:
            import openai
            self._client = openai.AsyncOpenAI(api_key=self.api_key)
        except ImportError:
            logger.error("openai package not installed; install with: pip install openai")
            self._client = None

    async def generate(self, prompt: str, **kwargs: Any) -> AIResponse:
        if not self._client:
            raise RuntimeError("OpenAI client not available")
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )
        usage = AIUsage(
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            cost_estimate_usd=self._estimate_cost(response.usage.prompt_tokens, response.usage.completion_tokens)
        )
        self._accumulate_usage(usage)
        return AIResponse(
            content=response.choices[0].message.content,
            usage=usage,
            model=self.model,
            provider="openai"
        )

    async def chat(self, messages: list[AIMessage], **kwargs: Any) -> AIResponse:
        if not self._client:
            raise RuntimeError("OpenAI client not available")
        openai_messages = [{"role": m.role, "content": m.content} for m in messages]
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            **kwargs
        )
        usage = AIUsage(
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            cost_estimate_usd=self._estimate_cost(response.usage.prompt_tokens, response.usage.completion_tokens)
        )
        self._accumulate_usage(usage)
        return AIResponse(
            content=response.choices[0].message.content,
            usage=usage,
            model=self.model,
            provider="openai"
        )

    async def embed(self, text: str, **kwargs: Any) -> list[float]:
        if not self._client:
            raise RuntimeError("OpenAI client not available")
        response = await self._client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
            **kwargs
        )
        return response.data[0].embedding

    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost in USD for GPT-4."""
        # GPT-4 pricing (approximate): $0.03/1K prompt tokens, $0.06/1K completion tokens
        prompt_cost = (prompt_tokens / 1000) * 0.03
        completion_cost = (completion_tokens / 1000) * 0.06
        return prompt_cost + completion_cost


class LocalLLMProvider(AIProvider):
    """Local LLM provider (Ollama)."""

    def __init__(self, model: str = "llama2", base_url: Optional[str] = None):
        super().__init__(model)
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        # Import lazily
        try:
            import httpx
            self._client = httpx.AsyncClient(timeout=300.0)  # 5 minute timeout for local models
        except ImportError:
            logger.error("httpx package not installed")
            self._client = None

    async def generate(self, prompt: str, **kwargs: Any) -> AIResponse:
        if not self._client:
            raise RuntimeError("HTTP client not available")
        response = await self._client.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, **kwargs}
        )
        response.raise_for_status()
        data = response.json()
        usage = AIUsage(
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            total_tokens=data.get("eval_count", 0) + data.get("prompt_eval_count", 0),
            cost_estimate_usd=0.0  # Local models are free
        )
        self._accumulate_usage(usage)
        return AIResponse(
            content=data.get("response", ""),
            usage=usage,
            model=self.model,
            provider="ollama"
        )

    async def chat(self, messages: list[AIMessage], **kwargs: Any) -> AIResponse:
        if not self._client:
            raise RuntimeError("HTTP client not available")
        # Ollama chat API
        response = await self._client.post(
            f"{self.base_url}/api/chat",
            json={"model": self.model, "messages": [{"role": m.role, "content": m.content} for m in messages], **kwargs}
        )
        response.raise_for_status()
        data = response.json()
        usage = AIUsage(
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            total_tokens=data.get("eval_count", 0) + data.get("prompt_eval_count", 0),
            cost_estimate_usd=0.0
        )
        self._accumulate_usage(usage)
        return AIResponse(
            content=data.get("message", {}).get("content", ""),
            usage=usage,
            model=self.model,
            provider="ollama"
        )

    async def embed(self, text: str, **kwargs: Any) -> list[float]:
        if not self._client:
            raise RuntimeError("HTTP client not available")
        response = await self._client.post(
            f"{self.base_url}/api/embed",
            json={"model": self.model, "input": text, **kwargs}
        )
        response.raise_for_status()
        data = response.json()
        return data.get("embedding", [])


class EntrimProvider(AIProvider):
    """Entrim AI API provider (OpenAI-compatible)."""

    def __init__(self, model: str = "deepseek-ai/DeepSeek-V4-Flash", api_key: Optional[str] = None, base_url: Optional[str] = None):
        super().__init__(model)
        self.api_key = api_key or os.getenv("ENTRIM_API_KEY")
        self.base_url = base_url or os.getenv("ENTRIM_BASE_URL", "https://api.entrim.ai/v1")
        if not self.api_key:
            logger.warning("Entrim API key not set; provider will fail")
        # Use OpenAI-compatible client
        try:
            import openai
            self._client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
        except ImportError:
            logger.error("openai package not installed; install with: pip install openai")
            self._client = None

    async def generate(self, prompt: str, **kwargs: Any) -> AIResponse:
        if not self._client:
            raise RuntimeError("OpenAI client not available")
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )
        usage = AIUsage(
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            cost_estimate_usd=0.0  # Entrim pricing not documented
        )
        self._accumulate_usage(usage)
        return AIResponse(
            content=response.choices[0].message.content,
            usage=usage,
            model=self.model,
            provider="entrim"
        )

    async def chat(self, messages: list[AIMessage], **kwargs: Any) -> AIResponse:
        if not self._client:
            raise RuntimeError("OpenAI client not available")
        openai_messages = [{"role": m.role, "content": m.content} for m in messages]
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            **kwargs
        )
        usage = AIUsage(
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            cost_estimate_usd=0.0
        )
        self._accumulate_usage(usage)
        return AIResponse(
            content=response.choices[0].message.content,
            usage=usage,
            model=self.model,
            provider="entrim"
        )

    async def embed(self, text: str, **kwargs: Any) -> list[float]:
        if not self._client:
            raise RuntimeError("OpenAI client not available")
        response = await self._client.embeddings.create(
            model=self.model,
            input=text,
            **kwargs
        )
        return response.data[0].embedding


class HybridProvider(AIProvider):
    """Hybrid provider that routes based on task type and cost."""

    def __init__(self, primary: AIProvider, fallback: AIProvider):
        super().__init__(primary.model)
        self.primary = primary
        self.fallback = fallback

    async def generate(self, prompt: str, **kwargs: Any) -> AIResponse:
        # Try primary first, fallback on error
        try:
            return await self.primary.generate(prompt, **kwargs)
        except Exception as e:
            logger.warning(f"Primary provider failed: {e}, using fallback")
            return await self.fallback.generate(prompt, **kwargs)

    async def chat(self, messages: list[AIMessage], **kwargs: Any) -> AIResponse:
        try:
            return await self.primary.chat(messages, **kwargs)
        except Exception as e:
            logger.warning(f"Primary provider failed: {e}, using fallback")
            return await self.fallback.chat(messages, **kwargs)

    async def embed(self, text: str, **kwargs: Any) -> list[float]:
        # Always use local for embeddings (faster, cheaper)
        try:
            return await self.fallback.embed(text, **kwargs)
        except Exception as e:
            logger.warning(f"Fallback provider failed: {e}, trying primary")
            return await self.primary.embed(text, **kwargs)


def get_provider(provider_type: str = "openai", **kwargs: Any) -> AIProvider:
    """Factory function to get an AI provider instance.

    Args:
        provider_type: "openai", "ollama", "entrim", or "hybrid"
        **kwargs: Additional arguments for provider initialization

    Returns:
        Configured AI provider instance
    """
    provider_type = provider_type.lower()
    
    if provider_type == "openai":
        return OpenAIProvider(**kwargs)
    elif provider_type == "ollama":
        return LocalLLMProvider(**kwargs)
    elif provider_type == "entrim":
        return EntrimProvider(**kwargs)
    elif provider_type == "hybrid":
        # Use Entrim as primary, Ollama as fallback
        primary = EntrimProvider(**kwargs)
        fallback = LocalLLMProvider(**kwargs)
        return HybridProvider(primary, fallback)
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")
