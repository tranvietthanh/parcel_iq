FROM node:22-alpine AS base
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copy workspace manifests first for better cache reuse
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/public-web/package.json ./apps/public-web/package.json
RUN pnpm install --frozen-lockfile --filter public-web...

FROM base AS builder
COPY apps/public-web ./apps/public-web

# Use deployment-provided key during build and avoid accidentally baking app-local .env values.
ARG NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
ARG NEXT_PUBLIC_MAPBOX_TOKEN
ARG NEXT_PUBLIC_CREDIT_PURCHASE_ENABLED
ARG NEXT_PUBLIC_TURNSTILE_SITE_KEY
ARG INTERNAL_API_URL
ENV NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=${NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY}
ENV NEXT_PUBLIC_MAPBOX_TOKEN=${NEXT_PUBLIC_MAPBOX_TOKEN}
ENV NEXT_PUBLIC_CREDIT_PURCHASE_ENABLED=${NEXT_PUBLIC_CREDIT_PURCHASE_ENABLED}
ENV NEXT_PUBLIC_TURNSTILE_SITE_KEY=${NEXT_PUBLIC_TURNSTILE_SITE_KEY}
ENV INTERNAL_API_URL=${INTERNAL_API_URL}
RUN rm -f apps/public-web/.env apps/public-web/.env.local apps/public-web/.env.development apps/public-web/.env.production

RUN pnpm --filter public-web build

FROM node:22-alpine AS runner
WORKDIR /app
COPY --from=builder /app/apps/public-web/.next/standalone ./
COPY --from=builder /app/apps/public-web/.next/static ./apps/public-web/.next/static
COPY --from=builder /app/apps/public-web/public ./apps/public-web/public
EXPOSE 3000
ENV NODE_ENV=production
CMD ["node", "apps/public-web/server.js"]
