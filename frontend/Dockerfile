FROM node:22-alpine AS builder

WORKDIR /app

# Keep Docker installs aligned with the lockfile and workspace policy.
RUN corepack enable && corepack prepare pnpm@11.11.0 --activate

# Install dependencies first for better layer caching
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --no-frozen-lockfile

# Copy frontend source
COPY frontend/ ./

# Browser-side API base URL baked into the frontend build
# Use relative path for browser requests (will proxy to backend)
ARG NEXT_PUBLIC_API_URL=/api/v1
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ARG NEXT_PUBLIC_STREAM_API_URL=http://localhost:3000/api/v1
ENV NEXT_PUBLIC_STREAM_API_URL=${NEXT_PUBLIC_STREAM_API_URL}
ENV NEXT_TELEMETRY_DISABLED=1

RUN pnpm build

EXPOSE 3000

FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
