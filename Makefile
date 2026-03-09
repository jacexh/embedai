.PHONY: up down migrate test-gateway test-pipeline test-all \
        e2e-up e2e-down e2e prod-build

up:
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down

migrate:
	cd shared/migrations && alembic upgrade head

seed:
	cd shared/migrations && uv run --with minio --with psycopg2-binary --with bcrypt python seed.py

seed-prod:
	@test -n "$(ADMIN_PASSWORD)" || (echo "ERROR: ADMIN_PASSWORD is required  →  make seed-prod ADMIN_PASSWORD=xxx" && exit 1)
	cd shared/migrations && \
	  CREATE_DEMO_USERS=false ADMIN_PASSWORD=$(ADMIN_PASSWORD) \
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
