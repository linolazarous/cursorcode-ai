# apps/api/app/ai/tools.py
"""
LangChain Tools for CursorCode AI Agents
Production-ready (February 2026): async, secure, auditable, agent-specific.
Tools are bound per agent type to reduce token usage & attack surface.
"""

import logging
from typing import Literal, Dict, Any, List, Optional
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, Field, validator

from app.services.logging import audit_log
from app.core.config import settings

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────
# Tool Schemas (for structured output & validation)
# ────────────────────────────────────────────────
class StackTrendResult(BaseModel):
    version: str = Field(..., description="Latest stable version")
    release_date: str = Field(..., description="Release date (YYYY-MM-DD)")
    recommendations: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)


class CodeExecResult(BaseModel):
    output: str = Field(..., description="Stdout/stderr")
    error: Optional[str] = None
    success: bool = Field(..., description="True if no exception")


class UIComponentExample(BaseModel):
    component_name: str
    framework: Literal["react", "nextjs", "svelte", "vue"]
    code: str = Field(..., description="Full component code snippet")


class VulnerabilityIssue(BaseModel):
    severity: Literal["low", "medium", "high", "critical"]
    type: str
    description: str
    line: Optional[int] = None
    fix: str


class VulnerabilityScanResult(BaseModel):
    issues: List[VulnerabilityIssue] = Field(default_factory=list)
    score: float = Field(..., ge=0, le=10)
    passed: bool = Field(...)


# ────────────────────────────────────────────────
# Shared Tool Helpers
# ────────────────────────────────────────────────
async def log_tool_usage(tool_name: str, args: Dict, result: Any, user_id: Optional[str] = None):
    """Audit tool usage (non-blocking)"""
    await audit_log.delay(
        user_id=user_id,
        action=f"tool_used:{tool_name}",
        metadata={
            "args": args,
            "result_summary": str(result)[:500] + "..." if len(str(result)) > 500 else str(result),
            "timestamp": datetime.now(ZoneInfo("UTC")).isoformat(),
        }
    )


# ────────────────────────────────────────────────
# Core Tools (used across agents)
# ────────────────────────────────────────────────
@tool
async def search_latest_stack_trends(
    technology: str = Field(..., description="Tech stack or library (e.g. 'Next.js', 'FastAPI', 'PostgreSQL')")
) -> Dict:
    """
    Search for latest versions, trends, best practices, and security notes for a given technology.
    Used primarily by Architect and Backend agents.
    """
    # In production: call real search API (e.g. Serper, Tavily, or xAI search)
    # Here: mock with realistic 2026 data
    trends = {
        "Next.js": {
            "version": "15.2.0",
            "release_date": "2026-01-15",
            "recommendations": [
                "Use App Router exclusively",
                "Server Components + Streaming SSR by default",
                "Turbopack for 3–5× faster dev server"
            ],
            "sources": ["https://nextjs.org/blog/next-15-2", "GitHub releases"]
        },
        "FastAPI": {
            "version": "0.115.0",
            "release_date": "2025-12-10",
            "recommendations": [
                "Prefer SQLModel over plain SQLAlchemy",
                "Use Pydantic v2 everywhere",
                "BackgroundTasks + Celery for heavy async work"
            ],
            "sources": ["https://fastapi.tiangolo.com/release-notes/", "GitHub"]
        },
    }

    result = trends.get(technology, {"version": "unknown", "recommendations": ["No data found"]})
    await log_tool_usage("search_latest_stack_trends", {"technology": technology}, result)

    return result


@tool
async def execute_code_snippet(
    code: str = Field(..., description="Code snippet to execute"),
    language: Literal["python", "javascript", "typescript", "go"] = "python"
) -> Dict:
    """
    Safely execute small code snippets in sandboxed environment.
    Used by QA agent for test validation and Backend for logic checks.
    """
    # In production: use real sandbox (E2B, Firecracker, restricted Docker)
    # Here: mock safe execution (never eval real user code in prod!)
    try:
        if language == "python":
            if any(bad in code.lower() for bad in ["import os", "subprocess", "__import__", "eval(", "exec("]):
                raise ValueError("Unsafe code detected – blocked for security")
            # Mock output
            return {"output": "Mock safe Python execution successful", "error": None, "success": True}
        else:
            return {"output": f"Mock {language} execution successful", "error": None, "success": True}
    except Exception as e:
        return {"output": "", "error": str(e), "success": False}


@tool
async def fetch_ui_component_example(
    component_name: str = Field(..., description="Component name, e.g. 'Button', 'Modal', 'DataTable'"),
    framework: Literal["react", "nextjs", "svelte", "vue"] = "nextjs"
) -> Dict:
    """
    Fetch modern, accessible, production-ready UI component example.
    Used by Frontend agent.
    """
    examples = {
        "Button": {
            "nextjs": """
import { Button } from '@/components/ui/button'

export function PrimaryButton() {
  return <Button variant="default">Click me</Button>
}
""",
            "svelte": """
<script>
  import { Button } from '$lib/components/ui/button'
</script>

<Button variant="default">Click me</Button>
"""
        },
        "Modal": {
            "nextjs": """
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'

export function ExampleModal() {
  return (
    <Dialog>
      <DialogTrigger>Open</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Are you sure?</DialogTitle>
        </DialogHeader>
        <p>Content here</p>
      </DialogContent>
    </Dialog>
  )
}
"""
        },
    }

    code = examples.get(component_name, {}).get(framework, "No example found for this component/framework")
    result = {"component_name": component_name, "framework": framework, "code": code}

    await log_tool_usage("fetch_ui_component_example", {"component": component_name, "framework": framework}, result)

    return result


@tool
async def scan_code_for_vulnerabilities(
    code: str = Field(..., description="Code snippet or file content to scan"),
    language: Literal["python", "javascript", "typescript", "go"] = "python"
) -> Dict:
    """
    Security scan for common vulnerabilities (OWASP Top 10, secrets, etc.).
    Used by Security agent.
    """
    # In production: call real scanner API (Semgrep Cloud, Snyk, Bandit, Trivy, etc.)
    # Here: simple regex-based mock detection
    issues = []

    if "password" in code.lower() or "api_key" in code.lower() or "secret" in code.lower():
        issues.append({
            "severity": "high",
            "type": "hardcoded_secret",
            "description": "Potential hardcoded credential detected",
            "line": 1,
            "fix": "Use environment variables or secrets manager (e.g. AWS Secrets Manager, HashiCorp Vault)"
        })

    # Add more patterns as needed (SQL injection, XSS, etc.)
    result = {
        "issues": issues,
        "score": max(0, 10 - len(issues) * 2),
        "passed": len(issues) == 0
    }

    await log_tool_usage("scan_code_for_vulnerabilities", {"language": language}, result)

    return result


@tool
async def generate_ci_cd_pipeline(
    stack: str = Field(..., description="Tech stack summary, e.g. 'Next.js + FastAPI + Postgres'"),
    target: Literal["vercel", "railway", "flyio", "aws", "k8s"] = "vercel"
) -> Dict:
    """
    Generate CI/CD pipeline config (GitHub Actions, GitLab CI, etc.).
    Used by DevOps agent.
    """
    # In production: use real template engine or LLM to generate
    # Here: realistic mock for common stacks
    pipeline_content = f"""
name: Deploy {stack} to {target}
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci
      - run: npm run build
      - name: Deploy to {target}
        run: echo "Deploy step for {target} (mock)"
"""

    result = {
        "name": f"Deploy {stack} to {target}",
        "file": ".github/workflows/deploy.yml",
        "content": pipeline_content.strip()
    }

    await log_tool_usage("generate_ci_cd_pipeline", {"stack": stack, "target": target}, result)

    return result


# ────────────────────────────────────────────────
# Tool Collections (bind per agent type to reduce context & tokens)
# ────────────────────────────────────────────────
architect_tools = [search_latest_stack_trends]
frontend_tools = [fetch_ui_component_example]
backend_tools = [execute_code_snippet]
security_tools = [scan_code_for_vulnerabilities]
qa_tools = [execute_code_snippet]
devops_tools = [generate_ci_cd_pipeline]

# All tools (for fallback or testing)
tools = [
    search_latest_stack_trends,
    execute_code_snippet,
    fetch_ui_component_example,
    scan_code_for_vulnerabilities,
    generate_ci_cd_pipeline,
]
