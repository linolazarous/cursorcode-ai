# apps/api/app/ai/orchestrator.py
"""
Core AI Agent Orchestration - CursorCode AI
LangGraph-based multi-agent system powered by xAI Grok (multi-model routing).
Handles: architecture → frontend/backend → security/qa → devops → deploy.
With tools, RAG/memory, credit metering, email notifications, persistence.
Now supports real-time token streaming for frontend display.
"""

import logging
import asyncio
from typing import TypedDict, Annotated, Sequence, Dict, Any, List, AsyncGenerator
from uuid import uuid4

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import settings
from app.db.session import async_session_factory
from app.models.project import Project, ProjectStatus
from app.services.billing import deduct_credits, refund_credits
from app.services.email import send_deployment_success_email
from app.services.logging import audit_log
from app.tasks.metering import report_grok_usage
from .nodes import agent_node  # Per-agent node factory
from .tools import tools       # All available tools
from .llm import stream_routed_llm  # ← Streaming version from llm.py
from .router import get_model_for_agent

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────
# Agent State
# ────────────────────────────────────────────────
class AgentState(TypedDict):
    project_id: str
    user_id: str
    org_id: str
    messages: Annotated[Sequence[BaseMessage], "add_messages"]
    prompt: str
    architecture: Dict[str, Any] | None
    frontend_code: str | None
    backend_code: str | None
    tests: List[str] | None
    deployment_scripts: str | None
    errors: List[str]
    memory: Dict[str, Any]  # RAG results
    total_tokens_used: int = 0  # For metering


# ────────────────────────────────────────────────
# RAG Helper (pgvector)
# ────────────────────────────────────────────────
async def get_project_memory(prompt: str, org_id: str) -> Dict:
    try:
        async with async_session_factory() as db:
            embedding = [0.0] * 1536
            result = await db.execute(
                """
                SELECT content, metadata, 1 - (embedding <=> :emb) as similarity
                FROM embeddings
                WHERE org_id = :org_id
                ORDER BY embedding <=> :emb
                LIMIT 3
                """,
                {"emb": embedding, "org_id": org_id}
            )
            rows = result.fetchall()
            return {
                "similar_projects": [
                    {"content": r[0], "metadata": r[1], "similarity": r[2]}
                    for r in rows
                ]
            }
    except Exception as e:
        logger.exception("RAG retrieval failed")
        return {"similar_projects": []}


# ────────────────────────────────────────────────
# Tool Node
# ────────────────────────────────────────────────
tool_node = ToolNode(tools)


# ────────────────────────────────────────────────
# Conditional Routing
# ────────────────────────────────────────────────
def should_continue(state: AgentState) -> str:
    if state["errors"]:
        return "error_handler"
    last_msg = state["messages"][-1]
    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        return "tools"
    return "next"


# ────────────────────────────────────────────────
# Error Handler Node
# ────────────────────────────────────────────────
async def error_handler(state: AgentState) -> Dict:
    logger.error(f"Project {state['project_id']} failed: {state['errors']}")

    async with async_session_factory() as db:
        await refund_credits(
            user_id=state["user_id"],
            amount=10,
            reason="Project orchestration failed",
            db=db,
        )
        project = await db.get(Project, state["project_id"])
        if project:
            project.status = ProjectStatus.FAILED
            project.error_message = "\n".join(state["errors"])
            await db.commit()

    asyncio.create_task(
        send_deployment_success_email(
            email="user_email_placeholder",
            project_title="Failed Project",
            deploy_url="N/A",
        )
    )

    return {"messages": [AIMessage(content="Build failed due to errors")]}


# ────────────────────────────────────────────────
# Build Graph (non-streaming internal execution)
# ────────────────────────────────────────────────
def build_agent_graph():
    graph = StateGraph(AgentState)

    async def rag_inject(state: AgentState):
        memory = await get_project_memory(state["prompt"], state["org_id"])
        return {
            "memory": memory,
            "messages": [HumanMessage(content=state["prompt"])]
        }

    graph.add_node("rag_inject", rag_inject)

    # Agent nodes (non-streaming wrapper around streaming LLM)
    async def run_agent_step(state: AgentState, agent_type: str):
        # Use streaming LLM under the hood
        system_prompt = f"Act as {agent_type} agent. Follow instructions precisely."
        full_messages = [{"role": "system", "content": system_prompt}] + [
            {"role": m.type, "content": m.content} for m in state["messages"]
        ]

        full_response = ""
        async for chunk in stream_routed_llm(
            agent_type=agent_type,
            messages=full_messages,
            user_tier="starter",  # from auth in real use
            task_complexity="medium",
            tools=tools,  # or agent-specific subset
        ):
            full_response += chunk

        return {
            "messages": state["messages"] + [AIMessage(content=full_response)]
        }

    graph.add_node("architect", lambda s: run_agent_step(s, "architect"))
    graph.add_node("frontend", lambda s: run_agent_step(s, "frontend"))
    graph.add_node("backend", lambda s: run_agent_step(s, "backend"))
    graph.add_node("security", lambda s: run_agent_step(s, "security"))
    graph.add_node("qa", lambda s: run_agent_step(s, "qa"))
    graph.add_node("devops", lambda s: run_agent_step(s, "devops"))

    graph.add_node("tools", tool_node)
    graph.add_node("error_handler", error_handler)

    graph.set_entry_point("rag_inject")
    graph.add_edge("rag_inject", "architect")

    for agent in ["architect", "frontend", "backend", "security", "qa", "devops"]:
        graph.add_conditional_edges(
            agent,
            should_continue,
            {"tools": "tools", "next": "next_agent", "error_handler": "error_handler"}
        )
        graph.add_edge("tools", agent)

    graph.add_edge("devops", END)

    return graph.compile()


# ────────────────────────────────────────────────
# Streaming Orchestration (public API for frontend)
# ────────────────────────────────────────────────
async def stream_orchestration(
    project_id: str,
    prompt: str,
    user_id: str,
    org_id: str,
    user_tier: str = "starter",
) -> AsyncGenerator[str, None]:
    """
    Async generator that streams tokens as the full orchestration runs.
    Yields chunks from each agent's response in real time.
    """
    estimated_cost = 10

    async with async_session_factory() as db:
        success, msg = await deduct_credits(
            user_id=user_id,
            amount=estimated_cost,
            reason=f"Streaming orchestration: {prompt[:50]}...",
            db=db,
        )
        if not success:
            yield f"[ERROR] Insufficient credits: {msg}"
            return

        graph = build_agent_graph()
        config = {"configurable": {"thread_id": project_id}}

        initial_state = AgentState(
            project_id=project_id,
            user_id=user_id,
            org_id=org_id,
            messages=[],
            prompt=prompt,
            errors=[],
            total_tokens_used=0,
        )

        try:
            # Run graph step by step, streaming agent outputs
            current_state = initial_state
            for node in ["rag_inject", "architect", "frontend", "backend", "security", "qa", "devops"]:
                if node == "rag_inject":
                    update = await rag_inject(current_state)
                else:
                    # Stream per agent
                    yield f"[AGENT_START]{node.upper()}[/AGENT_START]"
                    full_response = ""
                    async for chunk in stream_routed_llm(
                        agent_type=node,
                        messages=[{"role": m.type, "content": m.content} for m in current_state["messages"]],
                        user_tier=user_tier,
                        task_complexity="medium",
                    ):
                        full_response += chunk
                        yield chunk
                    yield "[AGENT_END]"

                    update = {"messages": current_state["messages"] + [AIMessage(content=full_response)]}

                current_state.update(update)

            # Final success handling (non-streamed part)
            project = await db.get(Project, project_id)
            if project:
                project.status = ProjectStatus.COMPLETED
                project.code_repo_url = "git-generated-repo-url"
                project.deploy_url = "https://project.cursorcode.app"
                await db.commit()

            await send_deployment_success_email(
                email="user_email_placeholder",
                project_title=project.title or "New Project",
                deploy_url=project.deploy_url,
            )

            total_tokens = current_state.get("total_tokens_used", 5000)
            report_grok_usage.delay(
                user_id=user_id,
                tokens_used=total_tokens,
                model_name="mixed_grok",
            )

            audit_log.delay(
                user_id=user_id,
                action="project_completed_stream",
                metadata={"project_id": project_id, "tokens": total_tokens}
            )

            yield "[COMPLETE]"

        except Exception as exc:
            await refund_credits(user_id=user_id, amount=estimated_cost, reason="Streaming orchestration failed", db=db)
            if project:
                project.status = ProjectStatus.FAILED
                project.error_message = str(exc)
                await db.commit()

            await send_email_task(
                to="user_email_placeholder",
                subject="Project Build Failed",
                html=f"<p>Project {project_id} failed: {str(exc)}</p>",
            )

            yield f"[ERROR]{str(exc)}"
            raise


# ────────────────────────────────────────────────
# Legacy non-streaming Celery task (for background / non-UI use)
# ────────────────────────────────────────────────
@shared_task(name="ai.run_agent_graph", bind=True, max_retries=3)
def run_agent_graph_task(
    self,
    project_id: str,
    prompt: str,
    user_id: str,
    org_id: str,
):
    """
    Legacy Celery task – non-streaming version.
    Use stream_orchestration() for real-time UI streaming.
    """
    estimated_cost = 10

    async def _run():
        async with async_session_factory() as db:
            success, msg = await deduct_credits(
                user_id=user_id,
                amount=estimated_cost,
                reason=f"Project orchestration: {prompt[:50]}...",
                db=db,
            )
            if not success:
                await send_email_task(
                    to="user_email_placeholder",
                    subject="Insufficient Credits",
                    html=f"<p>You have insufficient credits ({msg}). Please top up.</p>",
                )
                raise ValueError(msg)

            graph = build_agent_graph()
            config = {"configurable": {"thread_id": project_id}}

            initial_state = AgentState(
                project_id=project_id,
                user_id=user_id,
                org_id=org_id,
                messages=[],
                prompt=prompt,
                errors=[],
                total_tokens_used=0,
            )

            try:
                final_state = await graph.ainvoke(initial_state, config)

                project = await db.get(Project, project_id)
                if project:
                    project.status = ProjectStatus.COMPLETED
                    project.code_repo_url = "git-generated-repo-url"
                    project.deploy_url = "https://project.cursorcode.app"
                    await db.commit()

                await send_deployment_success_email(
                    email="user_email_placeholder",
                    project_title=project.title or "New Project",
                    deploy_url=project.deploy_url,
                )

                total_tokens = final_state.get("total_tokens_used", 5000)
                report_grok_usage.delay(
                    user_id=user_id,
                    tokens_used=total_tokens,
                    model_name="mixed_grok",
                )

                audit_log.delay(
                    user_id=user_id,
                    action="project_completed",
                    metadata={"project_id": project_id, "tokens": total_tokens}
                )

            except Exception as exc:
                await refund_credits(
                    user_id=user_id,
                    amount=estimated_cost,
                    reason="Orchestration failed",
                    db=db,
                )
                if project:
                    project.status = ProjectStatus.FAILED
                    project.error_message = str(exc)
                    await db.commit()

                await send_email_task(
                    to="user_email_placeholder",
                    subject="Project Build Failed",
                    html=f"<p>Project {project_id} failed: {str(exc)}</p>",
                )

                raise self.retry(exc=exc)

    asyncio.run(_run())
