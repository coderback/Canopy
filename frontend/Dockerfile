# Canopy frontend — Next.js standalone build, multi-stage.
# node:22-slim (Debian/glibc) matches the linux-gnu native binaries pinned in
# package-lock.json (lightningcss, @tailwindcss/oxide, @next/swc) — alpine/musl
# would need different variants.

# ---- build ----
FROM node:22-slim AS builder
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# NEXT_PUBLIC_* is inlined at build time. The browser (not this container) calls
# the backend, so this must be a host-reachable URL, not the compose service name.
ARG NEXT_PUBLIC_API_BASE=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# ---- runtime ----
FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN useradd --system nextjs

# Standalone output ships only the traced runtime deps + a minimal server.js.
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nextjs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nextjs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

CMD ["node", "server.js"]
