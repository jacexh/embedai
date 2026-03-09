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

# Single-page app routing: fall back to index.html for client-side routes.
RUN printf 'server {\n\
    listen 80;\n\
    root /usr/share/nginx/html;\n\
    index index.html;\n\
    location / {\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
}\n' > /etc/nginx/conf.d/default.conf

EXPOSE 80
