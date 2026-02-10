<p align="center">
  <img 
    src="https://raw.githubusercontent.com/linolazarous/cursorcode-ai/main/apps/web/public/logo.png" 
    alt="CursorCode AI Logo" 
    width="180" 
  />
</p>

<h1 align="center">CursorCode AI</h1>

<p align="center">
  <strong>Build Anything. Automatically. With AI.</strong>
</p>

<p align="center">
  <a href="https://cursorcode.ai">🌐 Live Demo</a> ·
  <a href="https://github.com/linolazarous/cursorcode-ai/issues/new">🐛 Report Bug</a> ·
  <a href="mailto:info@cursorcode.ai">📧 Contact</a>
</p>

<p align="center">
  <a href="https://github.com/linolazarous/cursorcode-ai/stargazers">
    <img src="https://img.shields.io/github/stars/linolazarous/cursorcode-ai?style=social" alt="GitHub stars" />
  </a>
  <a href="https://github.com/linolazarous/cursorcode-ai/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/linolazarous/cursorcode-ai" alt="License" />
  </a>
  <a href="https://github.com/linolazarous/cursorcode-ai/actions">
    <img src="https://img.shields.io/github/actions/workflow/status/linolazarous/cursorcode-ai/ci.yml?branch=main" alt="CI Status" />
  </a>
</p>

---

## What is CursorCode AI?

**CursorCode AI** is a fully autonomous AI software engineering platform powered by **xAI’s Grok family** with intelligent multi-model routing.

It goes far beyond code copilots, no-code builders, or conversational agents.

CursorCode AI takes a natural language prompt and **designs, codes, tests, secures, deploys, and maintains full-stack applications** — end-to-end, with **zero manual DevOps**.

Unlike:
- **Cursor AI** — powerful editor + agents
- **Emergent** — conversational builder
- **Hercules** — regulated workflows
- **Code Conductor** — no-code focus

CursorCode AI behaves like a **self-directed AI engineering team** capable of delivering enterprise-ready SaaS platforms, mobile apps, and AI-native products completely autonomously.

---

## Core Capabilities

- Natural language → complete production-grade codebases  
  (Next.js, FastAPI, PostgreSQL, Stripe, Auth, RBAC, and more)
- Multi-agent architecture  
  Architect → Frontend → Backend → Security/QA → DevOps
- Grok-powered intelligent model routing  
  - `grok-4-latest` — deep reasoning & architecture  
  - `grok-4-1-fast-reasoning` — agent execution & tools  
  - `grok-4-1-fast-non-reasoning` — high-throughput tasks
- Real-time memory & RAG (pgvector + long-term project memory)
- Automated testing & self-healing
- One-click deployments (Vercel, Railway, Render, Fly.io, custom domains)
- Built-in billing, usage metering & notifications (Stripe + Resend)
- Enterprise-grade security (JWT, OAuth, 2FA/TOTP, RBAC, multi-tenant orgs)
- User & admin dashboards (project history, usage analytics, credit metering)

---

## Technology Stack

**Frontend**  
- Next.js 15 (App Router)  
- React 19, TypeScript  
- Tailwind CSS + shadcn/ui  
- Auth.js v5 (Credentials, Google, GitHub)  
- TanStack Query, Zod, react-hook-form, sonner

**Backend**  
- FastAPI (Python 3.12)  
- SQLAlchemy 2.0 + asyncpg  
- Supabase PostgreSQL + pgvector  
- LangGraph + LangChain (xAI integration)  
- Celery + Upstash Redis  
- Stripe (subscriptions + metered usage)  
- Resend (email delivery)

**Infrastructure & DevOps**  
- Docker & docker-compose  
- Supabase (Postgres + Auth)  
- Upstash (Redis)  
- GitHub Actions (CI/CD)  
- Sentry (error monitoring)  
- Prometheus + custom metrics

**AI Layer**  
- xAI Grok family with intelligent routing

---

## Quick Start – Local Development

### Prerequisites
- Node.js 20+ & pnpm 9+
- Python 3.12+
- Docker (recommended)
- Supabase account (free tier works)
- Upstash Redis account (free tier works)

### 1. Clone & Install

```bash
git clone https://github.com/linolazarous/cursorcode-ai.git
cd cursorcode-ai
pnpm install
