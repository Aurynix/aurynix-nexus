# Deployment

---

## Local development (Docker Compose)

Start only the infrastructure (database, cache, vector DB):

```bash
docker compose up postgres redis qdrant -d
make seed-db
make run
```

Start everything including the app container:

```bash
docker compose up -d
```

Stop and remove containers (keeps volumes):
```bash
docker compose down
```

Stop and remove containers AND volumes (wipes all data):
```bash
docker compose down -v
```

---

## Docker image

The production image is in `docker/Dockerfile` — a two-stage build:

**Stage 1 — builder**
- Installs `uv`
- Runs `uv sync --frozen --no-dev` to install production deps only
- Result: `.venv/` with all packages

**Stage 2 — runtime**
- Copies `.venv/` from builder
- Copies `app/`, `alembic/`, `alembic.ini`, `scripts/`
- Runs as non-root user `appuser`
- Exposes port 8000

```bash
# Build
make docker-build

# Run (requires .env and postgres/redis/qdrant reachable)
docker run --env-file .env -p 8000:8000 aurynix-nexus
```

---

## Environment variables for production

Checklist of values that must change from development defaults:

```env
# Generate fresh — never reuse the dev value
SECRET_KEY=<openssl rand -hex 32>

# Your actual Groq key
GROQ_API_KEY=gsk_...

# Strong database password
POSTGRES_PASSWORD=<strong-random-password>

# Strong Redis password
REDIS_PASSWORD=<strong-random-password>

# Set to production to disable /docs and /redoc
ENVIRONMENT=production

# Your frontend origin(s)
CORS_ORIGINS=["https://yourapp.com"]
```

---

## Production considerations

### Single worker (required)

The compiled LangGraph graph is stored on `app.state`. Uvicorn **must** run with one worker per container:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Scale by running multiple containers behind a load balancer, not by increasing `--workers`.

### Database migrations

Run migrations before starting the app:

```bash
docker exec <app-container> python scripts/init_db.py
# or run alembic directly:
docker exec <app-container> python -m alembic upgrade head
```

### HTTPS

Always run behind a reverse proxy (nginx, Caddy, Traefik) that terminates TLS. The app itself speaks plain HTTP internally.

### Qdrant version

The Docker Compose file pins Qdrant to `v1.12.0`. The `qdrant-client` Python package may be a newer minor version — a warning is shown on startup but the app functions correctly within the compatibility window.

To suppress the warning, either pin `qdrant-client` to a matching version or set `check_compatibility=False` in `app/database/qdrant.py`.

---

## Remote deployment (VPS / cloud)

The Makefile includes SSH-based deployment targets. Set these values in the Makefile:

```makefile
SERVER_IP   := your.server.ip
SERVER_KEY  := ~/.ssh/aurynix.key
SERVER_USER := ubuntu
```

| Command | Description |
|---|---|
| `make deploy` | Run `scripts/deploy.sh` |
| `make ssh` | Open SSH session to server |
| `make ssh-logs` | Tail live app logs |
| `make ssh-deploy` | Pull latest code and redeploy on server |

`ssh-deploy` runs `git pull && docker compose up -d --build app` on the server.

---

## Health check endpoint

Use `GET /api/v1/health/ready` for load balancer health checks. It returns `200` only when PostgreSQL, Redis, and Qdrant are all reachable.

Example nginx upstream health check:
```nginx
upstream aurynix {
    server 127.0.0.1:8000;
}

location /api/v1/health/ready {
    proxy_pass http://aurynix;
}
```
