# apps/web/Dockerfile
# =============================================
# Production-ready Dockerfile for CursorCode AI Web (Next.js 16)
# Multi-stage build • Small image • Security best practices
# Uses npm to match Vercel build environment
# =============================================

# ==================== BUILD STAGE ====================
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files first (better layer caching)
COPY package*.json ./

# Install dependencies using npm (matches Vercel)
RUN npm ci --frozen-lockfile

# Copy source code
COPY . .

# Build the Next.js app (uses output: "standalone" from next.config.mjs)
RUN npm run build

# ==================== RUNTIME STAGE ====================
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Copy only the necessary files from builder (standalone output)
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

# Create non-root user for security (best practice)
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs
USER nextjs

EXPOSE 3000

# Start the standalone Next.js server
CMD ["node", "server.js"]
