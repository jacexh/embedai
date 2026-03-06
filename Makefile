.PHONY: up down migrate test-gateway test-pipeline test-all

up:
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down

migrate:
	cd shared/migrations && alembic upgrade head

test-gateway:
	cd services/gateway && go test ./...

test-pipeline:
	cd services/pipeline && pytest tests/ -v

test-all:
	$(MAKE) test-gateway && $(MAKE) test-pipeline
