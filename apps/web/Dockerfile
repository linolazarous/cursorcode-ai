# apps/web/Dockerfile
# =============================================
# Production-ready Dockerfile for CursorCode AI Web
# Multi-stage build • Small image • Security best practices
# =============================================

# ==================== BUILD STAGE ====================
FROM node:20-alpine AS builder

WORKDIR /app

# Enable pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copy package files first (for caching)
COPY package.json pnpm-lock.yaml ./

# Install dependencies
RUN pnpm install --frozen-lockfile

# Copy source code
COPY . .

# Build the Next.js app (uses output: "standalone" from next.config.mjs)
RUN pnpm build

# ==================== RUNTIME STAGE ====================
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Copy only the necessary files from builder
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

# Create non-root user for security
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs
USER nextjs

EXPOSE 3000

# Start the standalone Next.js server
CMD ["node", "server.js"]
