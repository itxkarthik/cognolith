FROM node:20-alpine

WORKDIR /app

# Use a pnpm version that is compatible with Node 20
RUN corepack enable && corepack prepare pnpm@10.15.1 --activate

# Install dependencies first for better layer caching
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --no-frozen-lockfile

# Copy frontend source
COPY frontend/ ./

# Browser-side API base URL baked into the frontend build
# Use relative path for browser requests (will proxy to backend)
ARG NEXT_PUBLIC_API_URL=/api/v1
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_TELEMETRY_DISABLED=1

RUN pnpm build

EXPOSE 3000

CMD ["pnpm", "start", "-p", "3000"]
