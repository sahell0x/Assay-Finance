# Multi-stage: the runner carries only the standalone output, not the toolchain.
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Baked into the bundle at build time, so it must be present here rather than at runtime.
ARG NEXT_PUBLIC_API_URL=/api
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
# BACKEND_URL is needed at BUILD time too, which is easy to miss because it never
# reaches the browser. `rewrites()` in next.config.ts is evaluated by `next build` and
# serialised into .next/routes-manifest.json; a value supplied only at runtime arrives
# after that file is already written, so the /api/* proxy is built with zero rules and
# every call through it 404s while the backend itself is perfectly healthy.
# It stays a runtime variable as well, for the server's own fetches.
ARG BACKEND_URL=http://api:8000
ENV BACKEND_URL=$BACKEND_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
# HOSTNAME=0.0.0.0 is load-bearing, and its absence is invisible from outside the
# container. Next's standalone server binds to process.env.HOSTNAME, and Docker sets
# HOSTNAME to the container id -- which resolves to the container's own eth0 address.
# The server then listens on 172.x.x.x:3000 alone: published ports still work, because
# docker-proxy dials that address, but anything inside the container reaching for
# localhost is refused. That includes the healthcheck, so the container reports
# unhealthy forever while serving traffic perfectly well.
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
