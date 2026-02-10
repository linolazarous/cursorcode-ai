# apps/api/app/ai/nodes.py
"""
Per-Agent Node Implementations - CursorCode AI
Each agent has specialized prompt, tools, model routing, and state updates.
Integrates token metering, retries, error handling, and audit logging.
Uses raw httpx-based LLM from llm.py (no LangChain LLM classes).
"""

import logging
import json
from typing import Dict, Any, Optional
from uuid import uuid4

from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.services.logging import audit_log
from app.tasks.metering import report_grok_usage
from .llm import get_routed_llm, estimate_prompt_tokens
from .tools import (
    tools,  # Full set
    architect_tools, frontend_tools, backend_tools, security_tools, qa_tools, devops_tools
)

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────
# Agent-specific system prompts (concise, role-focused)
# ────────────────────────────────────────────────
AGENT_PROMPTS = {
    "architect": """
You are the Architect Agent for CursorCode AI.
Design complete, scalable system architecture based on user prompt.
Use memory and tools to get latest stack info.
Output structured JSON: {"stack": "...", "db": "...", "auth": "...", "api": "...", "reasoning": "..."}
Be precise, production-ready, and cost-aware.
""",
    "frontend": """
You are the Frontend Agent.
Generate modern, responsive UI/UX code (Next.js App Router + Tailwind + Shadcn preferred).
Use architecture from previous step.
Output code files as dict: {"path": "content", ...}
Focus on accessibility, performance, best practices.
""",
    "backend": """
You are the Backend Agent.
Generate secure, scalable backend (FastAPI preferred, or Node/Express/Go).
Use architecture from previous step.
Output code files as dict: {"path": "content", ...}
Include REST/GraphQL APIs, DB models, auth, error handling.
""",
    "security": """
You are the Security Agent.
Audit code for vulnerabilities (OWASP Top 10, secrets, injection, auth bypass, etc.).
Use tools to scan if needed.
Output: {"issues": [{"severity": "high", "description": "...", "fix": "..."}], "score": 8/10}
""",
    "qa": """
You are the QA Agent.
Write unit, integration, E2E tests.
Debug issues, suggest fixes.
Use code execution tool to validate.
Output: {"tests": [{"file": "tests/test_xx.py", "content": "..."}], "coverage": "85%", "issues_fixed": [...]}
""",
    "devops": """
You are the DevOps Agent.
Generate CI/CD (GitHub Actions), Dockerfiles, deployment scripts (K8s or Vercel).
Output files as dict: {"Dockerfile": "...", ".github/workflows/deploy.yml": "..."}
Focus on zero-downtime, auto-scaling, monitoring.
"""
}

# ────────────────────────────────────────────────
# Per-agent tool subsets (optimize token usage & security)
# ────────────────────────────────────────────────
AGENT_TOOLS = {
    "architect": architect_tools,
    "frontend": frontend_tools,
    "backend": backend_tools,
    "security": security_tools,
    "qa": qa_tools,
    "devops": devops_tools,
}


# ────────────────────────────────────────────────
# Generic Agent Node (with token metering)
# ────────────────────────────────────────────────
@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=4, max=30),
    reraise=True,
)
async def agent_node(
    state: Dict[str, Any],
    agent_type: str,
    system_prompt_key: str = None,
) -> Dict[str, Any]:
    """
    Generic node for any agent.
    - Routes to correct model via raw httpx callable
    - Runs LLM call
    - Tracks tokens for metering (estimate-based)
    - Updates state
    - Audits call
    """
    # Get system prompt (use key or fallback to agent_type)
    system_prompt = AGENT_PROMPTS.get(system_prompt_key or agent_type, AGENT_PROMPTS[agent_type])

    # Get agent-specific tools
    tools_subset = AGENT_TOOLS.get(agent_type, tools)

    # Get routed LLM callable (raw httpx async function)
    llm_callable = get_routed_llm(
        agent_type=agent_type,
        user_tier=state.get("user_tier", "starter"),
        task_complexity=state.get("task_complexity", "medium"),
        tools=tools_subset,
    )

    # Build messages list (system prompt + history)
    messages = [{"role": "system", "content": system_prompt}] + [
        {"role": m.type, "content": m.content} for m in state["messages"]
    ]

    # Add initial prompt if this is the first agent call
    if not state["messages"]:
        messages.append({"role": "user", "content": state["prompt"]})

    try:
        # Call raw LLM (await the callable)
        response_content = await llm_callable(messages)

        # Rough token estimation (input + output)
        input_tokens = estimate_prompt_tokens(messages)
        output_tokens = len(response_content) // 4
        tokens_used = input_tokens + output_tokens

        # Queue metering
        report_grok_usage.delay(
            user_id=state.get("user_id"),
            tokens_used=tokens_used,
            model_name="mixed_grok",  # Update if you want model-specific
            request_id=str(uuid4()),
        )

        # Audit
        audit_log.delay(
            user_id=state.get("user_id"),
            action=f"agent_{agent_type}_executed",
            metadata={
                "project_id": state.get("project_id"),
                "tokens": tokens_used,
                "model": "mixed_grok",
                "has_tool_calls": False,  # Raw httpx doesn't support tool calls yet
            },
        )

        # Update state
        updates = {
            "messages": state["messages"] + [AIMessage(content=response_content)],
            "total_tokens_used": state.get("total_tokens_used", 0) + tokens_used,
        }

        # Agent-specific state updates (structured parsing attempt)
        if agent_type in ["architect", "security", "qa"]:
            try:
                parsed = json.loads(response_content.strip())
                updates[agent_type] = parsed
            except json.JSONDecodeError:
                updates[f"{agent_type}_raw"] = response_content

        return updates

    except Exception as exc:
        logger.exception(f"Agent {agent_type} failed for project {state.get('project_id')}")
        return {
            "messages": state["messages"] + [AIMessage(content=f"Agent {agent_type} failed: {str(exc)}")],
            "errors": state.get("errors", []) + [f"{agent_type}: {str(exc)}"],
        }


# ────────────────────────────────────────────────
# Specialized Node Wrappers (for readability)
# ────────────────────────────────────────────────
async def architect_node(state: Dict[str, Any]) -> Dict[str, Any]:
    return await agent_node(state, "architect")

async def frontend_node(state: Dict[str, Any]) -> Dict[str, Any]:
    return await agent_node(state, "frontend")

async def backend_node(state: Dict[str, Any]) -> Dict[str, Any]:
    return await agent_node(state, "backend")

async def security_node(state: Dict[str, Any]) -> Dict[str, Any]:
    return await agent_node(state, "security")

async def qa_node(state: Dict[str, Any]) -> Dict[str, Any]:
    return await agent_node(state, "qa")

async def devops_node(state: Dict[str, Any]) -> Dict[str, Any]:
    return await agent_node(state, "devops")
