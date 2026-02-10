# apps/api/app/ai/orchestrator.py
"""
Core AI Agent Orchestration - CursorCode AI
LangGraph-based multi-agent system powered by xAI Grok (multi-model routing).
Handles: architecture → frontend/backend → security/qa → devops → deploy.
With tools, RAG/memory, credit metering, email notifications, persistence.
"""

import logging
import asyncio
from typing import TypedDict, Annotated, Sequence, Dict, Any, List
from uuid import uuid4

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
# Removed broken import: from langchain_xai import ChatXAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.db.session import async_session_factory
from app.models.project import Project, ProjectStatus
from app.services.billing import deduct_credits, refund_credits
from app.services.email import send_deployment_success_email
from app.services.logging import audit_log
from app.tasks.metering import report_grok_usage
from .nodes import agent_node  # Per-agent node factory
from .tools import tools       # All available tools
from .router import route_model  # Grok model router

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
    """
    Retrieve similar past projects via vector similarity (pgvector).
    Placeholder → replace with real embedding generation + query.
    """
    try:
        async with async_session_factory() as db:
            # Mock: in real impl, generate embedding from prompt using Grok/OpenAI
            embedding = [0.0] * 1536

            # Query similar embeddings (assumes embeddings table exists)
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
        # Refund credits
        await refund_credits(
            user_id=state["user_id"],
            amount=10,  # Adjust based on actual usage
            reason="Project orchestration failed",
            db=db,
        )

        # Update project status
        project = await db.get(Project, state["project_id"])
        if project:
            project.status = ProjectStatus.FAILED
            project.error_message = "\n".join(state["errors"])
            await db.commit()

    # Notify user (async)
    asyncio.create_task(
        send_deployment_success_email(
            email="user_email_placeholder",  # Resolve from DB in real impl
            project_title="Failed Project",
            deploy_url="N/A",
        )
    )

    return {"messages": [AIMessage(content="Build failed due to errors")]}


# ────────────────────────────────────────────────
# Build Graph
# ────────────────────────────────────────────────
def build_agent_graph():
    graph = StateGraph(AgentState)

    # RAG Inject Node
    async def rag_inject(state: AgentState):
        memory = await get_project_memory(state["prompt"], state["org_id"])
        return {
            "memory": memory,
            "messages": [HumanMessage(content=state["prompt"])]
        }

    graph.add_node("rag_inject", rag_inject)

    # Agent Nodes (using factory)
    graph.add_node("architect", lambda s: agent_node(s, "architect", 
        "Design full system architecture. Use memory: {memory}. Prompt: {prompt}"))
    graph.add_node("frontend", lambda s: agent_node(s, "frontend", 
        "Generate frontend code (Next.js/React) from architecture: {architecture}"))
    graph.add_node("backend", lambda s: agent_node(s, "backend", 
        "Generate backend code (FastAPI/Node) from architecture: {architecture}"))
    graph.add_node("security", lambda s: agent_node(s, "security", 
        "Scan generated code for vulnerabilities and compliance issues"))
    graph.add_node("qa", lambda s: agent_node(s, "qa", 
        "Write unit/integration/E2E tests and debug issues"))
    graph.add_node("devops", lambda s: agent_node(s, "devops", 
        "Generate CI/CD pipelines, Dockerfiles, deployment scripts"))

    graph.add_node("tools", tool_node)
    graph.add_node("error_handler", error_handler)

    # Edges
    graph.set_entry_point("rag_inject")
    graph.add_edge("rag_inject", "architect")

    # Conditional routing after each agent
    for agent in ["architect", "frontend", "backend", "security", "qa", "devops"]:
        graph.add_conditional_edges(
            agent,
            should_continue,
            {"tools": "tools", "next": "next_agent", "error_handler": "error_handler"}
        )
        graph.add_edge("tools", agent)  # Loop back to retry

    # End after devops
    graph.add_edge("devops", END)

    # No Redis persistence – use default in-memory checkpointer
    return graph.compile()


# ────────────────────────────────────────────────
# Trigger Task (Celery)
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
    Celery task to run full agent graph.
    Handles credit gate, execution, metering, notifications.
    """
    estimated_cost = 10  # Credits - adjust based on complexity

    async def _run():
        async with async_session_factory() as db:
            # Credit gate
            success, msg = await deduct_credits(
                user_id=user_id,
                amount=estimated_cost,
                reason=f"Project orchestration: {prompt[:50]}...",
                db=db,
            )
            if not success:
                await send_email_task(
                    to="user_email_placeholder",  # Resolve from DB
                    subject="Insufficient Credits",
                    html=f"<p>You have insufficient credits ({msg}). Please top up.</p>",
                )
                raise ValueError(msg)

            # Build & run graph
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

                # Save results
                project = await db.get(Project, project_id)
                if project:
                    project.status = ProjectStatus.COMPLETED
                    project.code_repo_url = "git-generated-repo-url"  # In prod: real upload
                    project.deploy_url = "https://project.cursorcode.app"  # Real deploy
                    await db.commit()

                # Notify success
                await send_deployment_success_email(
                    email="user_email_placeholder",  # Resolve
                    project_title=project.title or "New Project",
                    deploy_url=project.deploy_url,
                )

                # Meter actual usage
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
                # Refund on failure
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
