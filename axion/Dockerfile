# Dockerfile — Axion frontend (Next.js standalone)
#
# Build context is the axion/ directory:
#   docker build -t axion-web ./axion \
#     --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000
#
# IMPORTANT: NEXT_PUBLIC_* values are inlined into the client bundle at BUILD
# time. Changing them requires a rebuild, not just a restart.

FROM node:20-alpine AS base
RUN corepack enable

# ── deps: install node_modules from the lockfile only ────────────────────────
FROM base AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# ── builder: compile the standalone server ───────────────────────────────────
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_TELEMETRY_DISABLED=1

RUN pnpm build

# ── runner: minimal image with just the standalone output ────────────────────
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
    CMD node -e "require('http').get('http://127.0.0.1:3000/', r => process.exit(r.statusCode < 500 ? 0 : 1)).on('error', () => process.exit(1))"

CMD ["node", "server.js"]
