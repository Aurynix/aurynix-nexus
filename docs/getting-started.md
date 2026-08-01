# Getting Started

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Docker + Docker Compose | Latest | PostgreSQL, Redis, Qdrant |
| Python | 3.11+ | Runtime |
| uv | Latest | Package manager |
| make | Any | Task runner |

Install uv if you don't have it:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## 1. Clone and configure

```bash
git clone <repo-url> && cd aurynix-nexus
cp .env.example .env
```

Edit `.env` and fill in the required values:

```env
GROQ_API_KEY=gsk_...              # get from console.groq.com
SECRET_KEY=<openssl rand -hex 32>  # generate once, keep secret
POSTGRES_PASSWORD=yourpassword
```

Everything else has sensible defaults for local development.

> **Note:** If your `POSTGRES_PASSWORD` contains special characters (`@`, `/`, etc.), they are safely URL-encoded automatically — no escaping needed in `.env`.

---

## 2. Start infrastructure

```bash
docker compose up postgres redis qdrant -d
```

Wait ~10 seconds for all containers to become healthy:
```bash
docker compose ps   # all three should show "healthy"
```

---

## 3. Install dependencies

```bash
uv sync
```

---

## 4. Initialize the database

```bash
make seed-db
```

This runs three steps in order:
1. Alembic migrations (creates all tables)
2. Qdrant collection setup
3. LangGraph checkpointer + memory store tables

Expected output:
```
Running Alembic migrations...
Migrations complete.
Initializing Qdrant collection...
Qdrant collection ready.
Initializing LangGraph checkpointer tables...
LangGraph tables ready.

Database initialization complete. Ready to launch.
```

---

## 5. Start the server

```bash
make run
```

The server starts at `http://0.0.0.0:8000` with hot-reload.

---

## 6. Verify everything is healthy

```bash
curl -s http://localhost:8000/api/v1/health/ready | python3 -m json.tool
```

Expected:
```json
{
    "status": "ready",
    "checks": {
        "postgres": "ok",
        "redis": "ok",
        "qdrant": "ok"
    }
}
```

---

## 7. Register and chat

```bash
# Register
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"password123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Stream a chat response
curl -N http://localhost:8000/api/v1/chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"What can you help me with?"}'
```

You will see Server-Sent Events streaming token by token.

---

## Available Make targets

| Command | Description |
|---|---|
| `make install` | Sync dependencies via uv |
| `make run` | Start dev server with hot reload |
| `make seed-db` | Run migrations + init Qdrant + LangGraph tables |
| `make fmt` | Auto-fix lint and formatting |
| `make fmtcheck` | Check lint/format without changes |
| `make lint` | Run ruff linter |
| `make test` | Run all tests |
| `make docker-up` | Start all Docker containers (including app) |
| `make docker-down` | Stop all containers |
| `make clean` | Remove venv and caches |

---

## WSL users

If running in WSL, ensure `uv` is on your PATH:

```bash
# Add to ~/.zshrc or ~/.bashrc
export PATH="$HOME/.local/bin:$PATH"
```

Docker containers run on the Windows host and are accessible from WSL via `localhost`.
