# ── Build stage: compile React app ─────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

COPY . .
RUN npm run build

# ── Runtime stage: serve static files with nginx ───────────────────────────
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx config: proxy /auth and /api/v1 to gateway, serve SPA for everything else.
# GATEWAY_URL is substituted at container start via envsubst.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 80
