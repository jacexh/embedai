.PHONY: up down dev-services dev-services-down migrate seed seed-prod \
        test-gateway test-pipeline test-all e2e-up e2e-down e2e prod-build

# ── Local development ─────────────────────────────────────────────────────

## Start infra only (postgres, minio, redis, label-studio)
up:
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down

## Start infra + Python backend services with hot-reload
## Gateway: DATABASE_URL=... JWT_SECRET=... go run ./services/gateway
## Web:     cd web && npm run dev
dev-services:
	docker compose -f infra/docker-compose.dev.yml up -d
	@echo ""
	@echo "  dataset-service → http://localhost:8100"
	@echo "  task-service    → http://localhost:8200"
	@echo ""
	@echo "  Run gateway:  DATABASE_URL=postgresql://embedai:embedai_dev@localhost:5432/embedai JWT_SECRET=dev-secret-change-in-production go run ./services/gateway"
	@echo "  Run web:      cd web && npm run dev"

dev-services-down:
	docker compose -f infra/docker-compose.dev.yml down

# Docker network and image used for migrate/seed (runs inside infra network to reach postgres/minio)
_DOCKER_MIGRATE = docker run --rm \
	--network infra_default \
	-v "$(CURDIR)/shared/migrations:/migrations" \
	-w /migrations \
	-e DATABASE_URL=postgresql://embedai:embedai_dev@postgres:5432/embedai \
	-e MINIO_ENDPOINT=minio:9000 \
	-e MINIO_SECURE=false \
	ghcr.io/astral-sh/uv:python3.12-bookworm-slim

migrate:
	$(_DOCKER_MIGRATE) uv run --with alembic --with psycopg2-binary --with sqlalchemy alembic upgrade head

seed:
	$(_DOCKER_MIGRATE) uv run --with minio --with psycopg2-binary --with bcrypt python seed.py

seed-prod:
	@test -n "$(ADMIN_PASSWORD)" || (echo "ERROR: ADMIN_PASSWORD is required  →  make seed-prod ADMIN_PASSWORD=xxx" && exit 1)
	$(_DOCKER_MIGRATE) \
	  -e CREATE_DEMO_USERS=false \
	  -e ADMIN_PASSWORD=$(ADMIN_PASSWORD) \
	  uv run --with minio --with psycopg2-binary --with bcrypt python seed.py

test-gateway:
	cd services/gateway && go test ./...

test-pipeline:
	cd services/pipeline && pytest tests/ -v

test-all:
	$(MAKE) test-gateway && $(MAKE) test-pipeline

# ── Production / E2E targets ──────────────────────────────────────────────

prod-build:
	docker compose -f infra/docker-compose.prod.yml build

## Start full prod stack (infra + all services) for E2E testing.
e2e-up:
	docker compose -f infra/docker-compose.prod.yml up -d
	@echo "Waiting for services to be healthy..."
	@sleep 15
	$(MAKE) migrate
	$(MAKE) seed

e2e-down:
	docker compose -f infra/docker-compose.prod.yml down

## Run end-to-end integration tests (requires e2e-up first).
e2e:
	cd tests && uv run pytest e2e/ -m e2e -v --timeout=600

## Run E2E tests for a specific module (auth/episodes/datasets/exports/tasks/gateway/pipeline).
## Usage: make e2e-module MODULE=exports
e2e-module:
	cd tests && uv run pytest e2e/test_$(MODULE).py -m e2e -v --timeout=300

## Run E2E tests and stop on first failure (fast feedback).
e2e-fast:
	cd tests && uv run pytest e2e/ -m e2e -x --timeout=300
