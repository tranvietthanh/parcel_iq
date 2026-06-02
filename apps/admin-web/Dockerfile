FROM node:22-alpine AS base
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copy workspace manifests first for better cache reuse
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/admin-web/package.json ./apps/admin-web/package.json
RUN pnpm install --frozen-lockfile --filter admin-web...

FROM base AS builder
COPY apps/admin-web ./apps/admin-web

# Use deployment-provided key during build and avoid accidentally baking app-local .env values.
ARG NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
ENV NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=${NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY}
RUN rm -f apps/admin-web/.env apps/admin-web/.env.local apps/admin-web/.env.development apps/admin-web/.env.production

RUN pnpm --filter admin-web build

FROM node:22-alpine AS runner
WORKDIR /app
COPY --from=builder /app/apps/admin-web/.next/standalone ./
COPY --from=builder /app/apps/admin-web/.next/static ./apps/admin-web/.next/static
COPY --from=builder /app/apps/admin-web/public ./apps/admin-web/public
EXPOSE 3001
ENV NODE_ENV=production
ENV PORT=3001
CMD ["node", "apps/admin-web/server.js"]
