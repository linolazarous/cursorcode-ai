# apps/api/app/ai/llm.py
"""
Grok LLM Factory - CursorCode AI
Creates routed ChatXAI instances with optimal model, parameters, and tools.
Production-ready (February 2026): caching, tier-aware routing, dynamic params.
Uses custom programmatic monitoring instead of Sentry.
"""

import logging
from functools import lru_cache
from typing import List, Optional, Dict, Any

from langchain_xai import ChatXAI
from langchain_core.tools import BaseTool

from app.core.config import settings
from app.ai.router import get_model_for_agent
from app.services.logging import audit_log

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────
# LLM Cache (per model + params combination)
# ────────────────────────────────────────────────
@lru_cache(maxsize=32)  # Adjust size based on concurrency
def get_llm(
    model_name: str,
    temperature: float = 0.7,
    max_tokens: int = 8192,
    top_p: float = 0.9,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    tools: Optional[List[BaseTool]] = None,
) -> ChatXAI:
    """
    Cached LLM instance factory.
    Caches based on model + generation params to avoid recreating objects.
    """
    llm = ChatXAI(
        model=model_name,
        api_key=settings.XAI_API_KEY.get_secret_value(),
        base_url="https://api.x.ai/v1",
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
    )

    if tools:
        llm = llm.bind_tools(tools)

    logger.debug(f"Created/cached LLM: {model_name} (temp={temperature}, tokens={max_tokens})")

    return llm


# ────────────────────────────────────────────────
# Routed LLM Factory (main entry point)
# ────────────────────────────────────────────────
def get_routed_llm(
    agent_type: str,
    user_tier: str = "starter",           # starter/standard/pro/premier/ultra
    task_complexity: str = "medium",      # low/medium/high
    tools: Optional[List[BaseTool]] = None,
    override_temperature: Optional[float] = None,
    override_max_tokens: Optional[int] = None,
) -> ChatXAI:
    """
    Returns fully configured ChatXAI instance for the given agent/task.
    Uses router to select model, applies tier/complexity-aware params.
    """
    # 1. Route to optimal model
    model_name = get_model_for_agent(
        agent_type=agent_type,
        user_tier=user_tier,
        task_complexity=task_complexity,
    )

    # 2. Dynamic generation parameters
    if agent_type in ["architect", "security", "product"]:
        temperature = 0.2 if override_temperature is None else override_temperature
        max_tokens = 12288 if override_max_tokens is None else override_max_tokens  # Longer context
        top_p = 0.85
        frequency_penalty = 0.1
    elif agent_type in ["frontend", "backend"]:
        temperature = 0.5
        max_tokens = 8192
        top_p = 0.9
        frequency_penalty = 0.0
    else:  # qa, devops, high-throughput
        temperature = 0.7
        max_tokens = 4096
        top_p = 0.95
        frequency_penalty = 0.0

    # Override if explicitly passed
    temperature = override_temperature if override_temperature is not None else temperature
    max_tokens = override_max_tokens if override_max_tokens is not None else max_tokens

    # 3. Create/cached LLM
    llm = get_llm(
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=0.9 if "reasoning" in model_name else 0.95,
        frequency_penalty=frequency_penalty,
        tools=tools,
    )

    # 4. Audit model choice (custom monitoring)
    audit_log.delay(
        user_id=None,  # Filled by caller context
        action="grok_llm_routed",
        metadata={
            "agent_type": agent_type,
            "user_tier": user_tier,
            "task_complexity": task_complexity,
            "model": model_name,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "tools_count": len(tools) if tools else 0,
        }
    )

    logger.info(
        f"Routed LLM for {agent_type} (tier={user_tier}, complexity={task_complexity}): "
        f"{model_name} @ temp={temperature}, tokens={max_tokens}"
    )

    return llm


# ────────────────────────────────────────────────
# Utility: Estimate tokens for pre-check (fallback)
# ────────────────────────────────────────────────
def estimate_prompt_tokens(messages: List[Dict[str, str]]) -> int:
    """
    Rough token estimation before call (4 chars ≈ 1 token).
    Used for credit pre-check in orchestrator.
    """
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        total += len(content) // 4 + 10  # Overhead per message
    return total
