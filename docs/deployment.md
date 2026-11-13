# Deployment

Each service has its own environment variables and its own host. Docker is not part of the deployment path.

## Frontend — Vercel

Deploy the `frontend` directory as a Next.js project. Vercel builds it with its Node runtime. No Dockerfile is involved.

Set `NEXT_PUBLIC_API_URL` to the Render API origin, for example `https://vansoraai-api.onrender.com`.

The Hobby plan is personal and non-commercial. A product that takes payment needs a paid Vercel plan.

## Backend — Render native Python

`render.yaml` defines one free web service. Render installs `backend/requirements.txt` and starts Uvicorn. It does not build `backend/Dockerfile`.

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

`APP_ENV=production` rejects a `DATABASE_URL` that points at localhost.

The free web service sleeps after 15 minutes without traffic and has 512 MB of RAM. It is a portfolio host, not an uptime guarantee.

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

Redis and Celery are not installed. Add them only when document processing or workflow execution needs a broker, and run that worker as its own service. A Render background worker is a paid service, so the blueprint does not create one yet.

## Shared development data

Development uses one Supabase project for every computer. Production should use another project. Migrating either database means `alembic upgrade head` only. Do not downgrade, drop, or recreate the development project when a laptop is new. The steps are in [development.md](development.md).
