"""AI integration layer for MKC.

Provides a unified interface for using external LLM APIs (OpenAI, Anthropic, etc.)
and local models (Ollama, etc.) with automatic fallback and cost tracking.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from mkc.intelligence.ai.providers import AIProvider, get_provider

logger = logging.getLogger("mkc.ai")

__all__ = ["AIProvider", "get_provider"]
