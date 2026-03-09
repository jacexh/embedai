# ── Build stage ────────────────────────────────────────────────────────────
FROM golang:1.22-alpine AS builder

WORKDIR /app

# Copy go workspace files so the replace directive resolves.
COPY go.work go.work.sum ./

# Fetch module manifests before copying source (layer-cache friendly).
COPY services/gateway/go.mod services/gateway/go.sum ./services/gateway/
COPY shared/proto/github.com/embedai/datahub/shared/proto/go.mod \
     shared/proto/github.com/embedai/datahub/shared/proto/go.sum \
     ./shared/proto/github.com/embedai/datahub/shared/proto/

RUN cd services/gateway && go mod download

# Copy full source.
COPY services/gateway/ ./services/gateway/
COPY shared/proto/ ./shared/proto/

RUN CGO_ENABLED=0 GOOS=linux \
    go build -C services/gateway -ldflags="-w -s" -o /gateway ./main.go

# ── Runtime stage ───────────────────────────────────────────────────────────
FROM alpine:3.19

RUN apk add --no-cache ca-certificates tzdata

COPY --from=builder /gateway /gateway

EXPOSE 8000
CMD ["/gateway"]
