# syntax=docker/dockerfile:1.6
# ==============================================================
# Mies frontend — Next.js 16 with standalone output
#
# Two-stage build. The `builder` stage installs every dep and runs
# `next build`; the `runner` stage only ships the self-contained
# server bundle that Next emits at `.next/standalone` + a copy of
# `public/` and `.next/static`. Result: ~200 MB image vs ~1 GB
# if we shipped the full node_modules tree.
# ==============================================================

# ── Stage 1: build ─────────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app

# Native deps some npm packages (lightningcss, sharp, etc.) need.
RUN apk add --no-cache libc6-compat

# Copy manifests first for cached installs. We use `npm install`
# (not `npm ci`) because Tailwind v4's native oxide binaries are
# listed as optionalDependencies — `npm install` handles those
# cleanly across platforms, which matters when the dev machine is
# darwin-arm64 and the build runs on linux-x64.
COPY package.json package-lock.json* ./
RUN npm install --no-audit --prefer-offline

# Everything else
COPY . .

# NEXT_PUBLIC_* values are baked into the client bundle at build
# time. Railway provides them via ARG → ENV; we also keep a sane
# dev default so `docker build` works standalone.
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL:-http://localhost:8000/api}

RUN npm run build


# ── Stage 2: runner ────────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Next.js standalone output: a single `server.js` + its minimal
# node_modules subset. Copy the static assets separately because
# the standalone mode intentionally leaves them out (it assumes
# a CDN; on Railway we serve them ourselves).
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
