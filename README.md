# CursorCode AI

**Build Anything. Automatically. With AI.**

CursorCode AI is the world’s most powerful autonomous AI software engineering platform — powered by xAI's Grok family with intelligent multi-model routing.

It replaces entire development teams by understanding natural language prompts, designing architecture, writing production-grade code, testing, securing, deploying, and maintaining full-stack applications — all with zero manual DevOps.

Unlike Cursor AI (editor with agents), Emergent (conversational builder), Hercules (regulated workflows), or Code Conductor (no-code), CursorCode AI is a **self-directing AI engineering organization** that delivers enterprise-ready SaaS, mobile apps, and AI-native products.

**Live:** https://cursorcode.ai  
**Contact:** info@cursorcode.ai

## Features

- Natural language → full production codebases (Next.js, FastAPI, Postgres, Stripe, auth, RBAC, etc.)
- Multi-agent system (Architect → Frontend/Backend → Security/QA → DevOps)
- Grok-powered: `grok-4-latest` (deep reasoning), `grok-4-1-fast-reasoning` (agentic/tool use), `grok-4-1-fast-non-reasoning` (high-throughput)
- Real-time RAG/memory (pgvector), tools, self-debugging, auto-tests
- Native deployment (*.cursorcode.app), external (Vercel, Railway, etc.)
- Stripe billing (subscriptions + metered usage), SendGrid notifications
- Secure auth (JWT, OAuth, 2FA/TOTP), multi-tenant organizations
- User & admin dashboards, project history, credit metering

## Tech Stack

**Frontend** (Next.js App Router)
- React 18, TypeScript, Tailwind CSS + shadcn/ui
- NextAuth v5 / Auth.js (credentials + Google/GitHub OAuth)
- TanStack Query (data fetching/polling)
- Zod, react-hook-form, sonner (toasts)

**Backend** (FastAPI)
- Python 3.12, SQLAlchemy 2.0 + asyncpg
- Supabase PostgreSQL (managed DB + pgvector for RAG)
- LangGraph + LangChain-xAI (agent orchestration)
- Celery + Redis (async tasks, retries)
- Stripe (subscriptions + metered billing), SendGrid (email)

**Infra & DevOps**
- Docker + docker-compose (local – DB optional)
- Supabase (database + auth optional)
- Kubernetes manifests (production)
- GitHub Actions (CI/CD)
- Sentry (error monitoring)

**AI** — xAI Grok family (multi-model routing)

## Quick Start (Local Development with Supabase)

### Prerequisites

- Node.js 20+ & pnpm 9+
- Python 3.12+ & pip
- Docker + docker-compose (optional for Redis)
- Supabase account (free tier works great)

### 1. Clone & Install

```bash
git clone https://github.com/your-org/cursorcode-ai.git
cd cursorcode-ai
pnpm install

# Backend (apps/api/.env)
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@db.[project-ref].supabase.co:5432/postgres
REDIS_URL=redis://default:[password]@[upstash-host]:6379   # or local redis://redis:6379/0
XAI_API_KEY=your_xai_api_key_here
STRIPE_SECRET_KEY=sk_test_...
SENDGRID_API_KEY=SG....
JWT_SECRET_KEY=super-long-random-secret-32-chars-min
JWT_REFRESH_SECRET=another-long-random-secret
NEXTAUTH_SECRET=yet-another-secret-for-frontend

# Frontend (apps/web/.env.local)
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GITHUB_ID=...
GITHUB_SECRET=...

# Install Supabase CLI if not already
npm install -g supabase

# Login
supabase login

# Link to your project
supabase link --project-ref your-project-ref

# Push local migrations (if using Supabase CLI migrations)
supabase db push

# Start Redis (Postgres is Supabase – external)
docker compose up -d redis

# Backend (FastAPI)
cd apps/api
uvicorn app.main:app --reload --port 8000

# Frontend (Next.js)
cd apps/web
pnpm dev

# Frontend
cd apps/web
pnpm test

# Backend
cd apps/api
pytest


