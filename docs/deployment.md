# Deployment

Each service has its own environment variables and its own host. Docker is not part of the deployment path.

## Frontend — Vercel

Deploy the `frontend` directory as a Next.js project. Vercel builds it with its Node runtime. No Dockerfile is involved.

Set `NEXT_PUBLIC_API_URL` to the Render API origin, for example `https://vansoraai-api.onrender.com`.

The Hobby plan is personal and non-commercial. A product that takes payment needs a paid Vercel plan.

## Backend — Render native Python

`render.yaml` defines one free web service. Render installs `backend/requirements-hosted.txt` and starts Uvicorn. It does not build `backend/Dockerfile`. The hosted install omits the local embedding model.

Set these on the Render service:

| Variable | Value |
| --- | --- |
| `APP_ENV` | `production` |
| `AUTH_MODE` | `supabase` |
| `EXPOSE_DEV_TOKENS` | `false` |
| `DATABASE_URL` | Supabase session-pooler URI, with the `postgresql+psycopg://` prefix |
| `SECRET_KEY` | A long random string |
| `SUPABASE_URL` | Project URL |
| `SUPABASE_JWT_SECRET` | JWT secret, or leave empty to verify via JWKS |
| `SUPABASE_SERVICE_ROLE_KEY` | Server only. Never put this in the frontend project |
| `SUPABASE_STORAGE_BUCKET` | `documents` |
| `CORS_ORIGINS` | The Vercel origin |

`APP_ENV=production` rejects a localhost database, a localhost `CORS_ORIGINS` value, the development `SECRET_KEY`, and an Ollama server on this computer. `render.yaml` sets `AI_FALLBACK_PROVIDERS=groq` and leaves `OLLAMA_BASE_URL` empty. Render's health check is `GET /api/v1/health`.

The free web service sleeps after 15 minutes without traffic and has 512 MB of RAM. `KNOWLEDGE_MODE=demo` keeps the embedding model out of that process. Render installs `requirements-hosted.txt`, which does not include FastEmbed. Visitors can ask about the prepared sample through Postgres text search. Uploads and semantic indexing stay on a computer running `KNOWLEDGE_MODE=full`. The first request after sleep can take about a minute. If Supabase has paused the project, resume it from the Supabase dashboard.

## Database — Supabase

Use Supabase Postgres with the `vector` extension. The free tier's direct host is IPv6-only, and Render reaches the shared pooler over IPv4. Use session mode (pooler host, port 5432) so SQLAlchemy prepared statements work.

Run migrations from a machine that can reach the pooler:

```powershell
cd backend
.\.venv\Scripts\python -m alembic upgrade head
```

Do not run the API against a database that lives only on a laptop.

## Background work

HTTP handlers insert rows into `jobs`. They do not execute those rows.

The worker is a second process:

```powershell
cd backend
.\.venv\Scripts\python -m app.workers
```

Workflow runs happen inside the manual request. Support drafts are created in that same kind of request, stay in the conversation until a person approves them, and are not emailed. Hosted support search uses the Knowledge text index. Redis and Celery are not installed. A Render background worker is a paid service, so the blueprint does not create one.

## Shared development data

Development uses one Supabase project for every computer. Production should use another project. Migrating either database means `alembic upgrade head` only. Do not downgrade, drop, or recreate the development project when a laptop is new. The steps are in [development.md](development.md).
