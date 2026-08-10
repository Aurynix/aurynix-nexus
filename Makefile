.PHONY: help install run seed-db fmt fmtcheck lint test docker-build docker-up docker-down deploy ssh ssh-logs ssh-deploy clean

# -----------------------------
# OS detection
# -----------------------------
ifeq ($(OS),Windows_NT)
    VENV_BIN := .venv/Scripts
else
    VENV_BIN := .venv/bin
endif

PYTHON  := uv run python
UVICORN := uv run uvicorn
PYTEST  := uv run pytest
RUFF    := uv run ruff

SERVER_IP   := YOUR_SERVER_IP
SERVER_KEY  := ~/.ssh/aurynix.key
SERVER_USER := ubuntu

# -----------------------------
# Help
# -----------------------------
help:
	@echo "Available commands:"
	@echo "  make install       - sync all dependencies via uv"
	@echo "  make run           - start dev server with hot reload"
	@echo "  make seed-db       - run migrations, init Qdrant collection, set up LangGraph tables"
	@echo "  make fmt           - auto-fix lint and formatting"
	@echo "  make fmtcheck      - check lint and formatting (no changes)"
	@echo "  make lint          - run ruff linter"
	@echo "  make test          - run all tests"
	@echo "  make docker-build  - build Docker image"
	@echo "  make docker-up     - start all containers (detached)"
	@echo "  make docker-down   - stop all containers"
	@echo "  make deploy        - deploy to production server"
	@echo "  make ssh           - SSH into the production server"
	@echo "  make ssh-logs      - tail live app logs from the server"
	@echo "  make ssh-deploy    - pull latest code and redeploy on server"
	@echo "  make clean         - remove venv and caches"

# -----------------------------
# Setup
# -----------------------------
install:
	uv sync --extra dev

# -----------------------------
# Dev
# -----------------------------
run:
	$(UVICORN) app.main:app --reload --host 0.0.0.0 --port 8000

seed-db:
	$(PYTHON) scripts/init_db.py

# -----------------------------
# Code Quality
# -----------------------------
fmt:
	$(RUFF) check app/ tests/ --fix
	$(RUFF) format app/ tests/

fmtcheck:
	@$(RUFF) check app/ tests/
	@$(RUFF) format app/ tests/ --check

lint:
	$(RUFF) check app/ tests/

# -----------------------------
# Test
# -----------------------------
test:
	$(PYTEST) tests/ -v

# -----------------------------
# Docker
# -----------------------------
docker-build:
	docker build -t aurynix-nexus -f docker/Dockerfile .

docker-up:
	docker compose up -d

docker-down:
	docker compose down

# -----------------------------
# Deploy
# -----------------------------
deploy:
	bash scripts/deploy.sh

ssh:
	ssh -i $(SERVER_KEY) $(SERVER_USER)@$(SERVER_IP)

ssh-logs:
	ssh -i $(SERVER_KEY) $(SERVER_USER)@$(SERVER_IP) \
		"cd /opt/aurynix/app && docker compose logs -f app"

ssh-deploy:
	ssh -i $(SERVER_KEY) $(SERVER_USER)@$(SERVER_IP) \
		"cd /opt/aurynix/app && git pull && docker compose up -d --build app"

# -----------------------------
# Clean
# -----------------------------
clean:
ifeq ($(OS),Windows_NT)
	if exist .venv rmdir /s /q .venv
	if exist .pytest_cache rmdir /s /q .pytest_cache
	if exist .ruff_cache rmdir /s /q .ruff_cache
	if exist uploads rmdir /s /q uploads
else
	rm -rf .venv .pytest_cache .ruff_cache uploads
	find . -type d -name __pycache__ -exec rm -rf {} +
endif
