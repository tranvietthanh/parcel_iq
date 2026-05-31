FROM node:22-alpine AS base
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@latest --activate
# Copy lockfile from repo root for dependency resolution
COPY pnpm-lock.yaml ./
COPY apps/public-web/package.json ./
RUN pnpm fetch

FROM base AS builder
RUN pnpm install --frozen-lockfile
COPY apps/public-web/ .

RUN pnpm build

FROM node:22-alpine AS runner
WORKDIR /app
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
ENV NODE_ENV=production
CMD ["node", "server.js"]
