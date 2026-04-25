FROM node:20-alpine

WORKDIR /app

# Use pnpm via corepack
RUN corepack enable

# Install dependencies first for better layer caching
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# Copy source and build
COPY . .

# Browser-side API base URL baked into the frontend build
ARG NEXT_PUBLIC_API_URL=http://127.0.0.1:3000/api/v1
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_TELEMETRY_DISABLED=1

RUN pnpm build

EXPOSE 3000

CMD ["pnpm", "start", "-p", "3000"]
